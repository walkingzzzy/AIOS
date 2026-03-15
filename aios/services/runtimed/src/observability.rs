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
        source: &str,
        kind: &str,
        session_id: Option<&str>,
        task_id: Option<&str>,
        payload: Value,
    ) -> anyhow::Result<()> {
        let timestamp = Utc::now().to_rfc3339();
        let record = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "event_id": format!("obs-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "generated_at": timestamp.clone(),
            "timestamp": timestamp,
            "source": source,
            "kind": kind,
            "session_id": session_id,
            "task_id": task_id,
            "artifact_path": self.path.display().to_string(),
            "payload": payload,
        });
        self.trace_validator
            .validate_value(&record)
            .with_context(|| {
                format!("failed to validate observability sink record for kind={kind}")
            })?;
        self.append_json(record)
    }

    fn append_json(&self, payload: Value) -> anyhow::Result<()> {
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        writeln!(file, "{}", serde_json::to_string(&payload)?)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    #[test]
    fn append_record_writes_machine_readable_entry() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-observability-sink");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        let sink = ObservabilitySink::new(path.clone())?;

        sink.append_record(
            "aios-runtimed",
            "runtime.trace",
            Some("session-1"),
            Some("task-1"),
            json!({"backend_id": "local-cpu"}),
        )?;

        let contents = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(contents.lines().next().expect("entry"))?;
        assert_eq!(
            entry["schema_version"],
            CURRENT_OBSERVABILITY_SCHEMA_VERSION
        );
        assert_eq!(entry["artifact_path"], path.display().to_string());
        assert_eq!(entry["source"], "aios-runtimed");
        assert_eq!(entry["kind"], "runtime.trace");
        assert_eq!(entry["payload"]["backend_id"], "local-cpu");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn append_record_rejects_invalid_trace_shape() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-observability-invalid");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        let sink = ObservabilitySink::new(path.clone())?;

        let error = sink
            .append_record(
                "",
                "runtime.trace",
                Some("session-1"),
                Some("task-1"),
                json!({"backend_id": "local-cpu"}),
            )
            .expect_err("empty source should be rejected by trace schema runtime validation");
        assert!(error
            .to_string()
            .contains("failed to validate observability sink record"));

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
