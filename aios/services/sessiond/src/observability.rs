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
        session_id: Option<&str>,
        task_id: Option<&str>,
        artifact_path: Option<&Path>,
        payload: Value,
    ) -> anyhow::Result<()> {
        let timestamp = Utc::now().to_rfc3339();
        let mut record = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "event_id": format!("obs-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "generated_at": timestamp.clone(),
            "timestamp": timestamp,
            "source": "aios-sessiond",
            "kind": kind,
            "payload": payload,
        });
        if let Some(item) = session_id {
            record["session_id"] = Value::String(item.to_string());
        }
        if let Some(item) = task_id {
            record["task_id"] = Value::String(item.to_string());
        }
        if let Some(path) = artifact_path {
            record["artifact_path"] = Value::String(path.display().to_string());
        }
        self.trace_validator
            .validate_value(&record)
            .with_context(|| {
                format!("failed to validate sessiond observability record for kind={kind}")
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
        let root = std::env::temp_dir().join("aios-sessiond-observability-sink");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        let sink = ObservabilitySink::new(path.clone())?;
        let database_path = root.join("sessiond.sqlite3");

        sink.append_record(
            "task.state.updated",
            Some("session-1"),
            Some("task-1"),
            Some(&database_path),
            json!({"from_state": "planned", "to_state": "approved"}),
        )?;

        let contents = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(contents.lines().next().expect("entry"))?;
        assert_eq!(entry["source"], "aios-sessiond");
        assert_eq!(entry["kind"], "task.state.updated");
        assert_eq!(entry["artifact_path"], database_path.display().to_string());

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
