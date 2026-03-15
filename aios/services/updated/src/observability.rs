use std::{
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
};

use anyhow::Context;
use chrono::Utc;
use serde_json::{json, Value};

use aios_core::schema::{
    self, CompiledJsonSchema, ObservabilitySchema, CURRENT_OBSERVABILITY_SCHEMA_VERSION,
};

#[derive(Debug, Clone)]
pub struct ObservabilitySink {
    path: PathBuf,
    trace_validator: CompiledJsonSchema,
}

impl ObservabilitySink {
    pub fn new(path: PathBuf) -> anyhow::Result<Self> {
        Ok(Self {
            path,
            trace_validator: schema::compile_observability_schema(ObservabilitySchema::TraceEvent)?,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn append_record(
        &self,
        kind: &str,
        artifact_path: Option<&Path>,
        update_id: Option<&str>,
        payload: Value,
        notes: Vec<String>,
    ) -> anyhow::Result<()> {
        let timestamp = Utc::now().to_rfc3339();
        let mut record = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "event_id": format!("obs-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "generated_at": timestamp.clone(),
            "timestamp": timestamp,
            "source": "aios-updated",
            "kind": kind,
            "payload": payload,
        });
        if let Some(path) = artifact_path {
            record["artifact_path"] = Value::String(path.display().to_string());
        }
        if let Some(item) = update_id {
            record["update_id"] = Value::String(item.to_string());
        }
        if !notes.is_empty() {
            record["notes"] = Value::Array(notes.into_iter().map(Value::String).collect());
        }
        self.trace_validator
            .validate_value(&record)
            .with_context(|| {
                format!("failed to validate updated observability record for kind={kind}")
            })?;
        self.append_json(&record)
    }

    fn append_json(&self, payload: &Value) -> anyhow::Result<()> {
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        writeln!(file, "{}", serde_json::to_string(payload)?)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    #[test]
    fn append_record_writes_valid_trace_event() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-updated-observability-sink");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        let sink = ObservabilitySink::new(path.clone())?;
        let deployment_state = root.join("deployment-state.json");

        sink.append_record(
            "update.apply.completed",
            Some(&deployment_state),
            Some("recovery-1"),
            json!({"status": "accepted", "deployment_status": "apply-triggered"}),
            vec!["note=ok".to_string()],
        )?;

        let contents = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(contents.lines().next().expect("entry"))?;
        assert_eq!(entry["source"], "aios-updated");
        assert_eq!(entry["kind"], "update.apply.completed");
        assert_eq!(entry["update_id"], "recovery-1");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
