use std::{
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
};

use anyhow::Context;
use serde_json::Value;

use aios_core::schema::{self, CompiledJsonSchema, ObservabilitySchema};

#[derive(Debug, Clone)]
pub struct ObservabilitySink {
    path: PathBuf,
    audit_validator: CompiledJsonSchema,
}

impl ObservabilitySink {
    pub fn new(path: PathBuf) -> anyhow::Result<Self> {
        Ok(Self {
            path,
            audit_validator: schema::compile_observability_schema(ObservabilitySchema::AuditEvent)?,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn append_record(&self, payload: &Value) -> anyhow::Result<()> {
        self.audit_validator
            .validate_value(payload)
            .with_context(|| "failed to validate policyd observability audit record")?;
        self.append_json(payload)
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

    use chrono::Utc;
    use serde_json::json;

    use super::*;
    use aios_core::schema::CURRENT_OBSERVABILITY_SCHEMA_VERSION;

    #[test]
    fn append_record_writes_valid_audit_event() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-policyd-observability-sink-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        let sink = ObservabilitySink::new(path.clone())?;

        let payload = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "audit_id": "audit-1",
            "timestamp": "2026-03-14T00:00:00Z",
            "generated_at": "2026-03-14T00:00:00Z",
            "user_id": "u1",
            "session_id": "s1",
            "task_id": "t1",
            "approval_id": "apr-1",
            "capability_id": "system.file.bulk_delete",
            "decision": "approval-pending",
            "execution_location": "local",
            "artifact_path": "/tmp/audit.jsonl",
            "result": {"approval_ref": "apr-1"}
        });

        sink.append_record(&payload)?;

        let contents = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(contents.lines().next().expect("entry"))?;
        assert_eq!(entry["decision"], "approval-pending");
        assert_eq!(
            entry["schema_version"],
            CURRENT_OBSERVABILITY_SCHEMA_VERSION
        );

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
