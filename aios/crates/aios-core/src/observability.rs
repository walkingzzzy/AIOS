use std::{
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
};

use anyhow::Context;
use chrono::Utc;
use serde_json::{json, Value};

use crate::schema::{
    self, CompiledJsonSchema, ObservabilitySchema, CURRENT_OBSERVABILITY_SCHEMA_VERSION,
};

#[derive(Debug, Clone)]
pub struct ProviderObservabilitySink {
    path: PathBuf,
    service_id: String,
    provider_id: String,
    trace_validator: CompiledJsonSchema,
    health_validator: CompiledJsonSchema,
}

impl ProviderObservabilitySink {
    pub fn new(
        path: PathBuf,
        service_id: impl Into<String>,
        provider_id: impl Into<String>,
    ) -> anyhow::Result<Self> {
        Ok(Self {
            path,
            service_id: service_id.into(),
            provider_id: provider_id.into(),
            trace_validator: schema::compile_observability_schema(ObservabilitySchema::TraceEvent)?,
            health_validator: schema::compile_observability_schema(
                ObservabilitySchema::HealthEvent,
            )?,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn append_trace(
        &self,
        kind: &str,
        artifact_path: Option<&Path>,
        payload: Value,
        notes: Vec<String>,
    ) -> anyhow::Result<()> {
        let timestamp = Utc::now().to_rfc3339();
        let mut record = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "event_id": format!("obs-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "generated_at": timestamp.clone(),
            "timestamp": timestamp,
            "source": self.service_id,
            "kind": kind,
            "provider_id": self.provider_id,
            "payload": payload,
        });
        if let Some(path) = artifact_path {
            record["artifact_path"] = Value::String(path.display().to_string());
        }
        if !notes.is_empty() {
            record["notes"] = Value::Array(notes.into_iter().map(Value::String).collect());
        }
        self.trace_validator
            .validate_value(&record)
            .with_context(|| {
                format!(
                    "failed to validate provider observability trace record for service_id={} kind={kind}",
                    self.service_id
                )
            })?;
        self.append_json(&record)
    }

    pub fn append_health_event(
        &self,
        source: &str,
        overall_status: &str,
        summary: Option<&str>,
        artifact_path: Option<&Path>,
        notes: Vec<String>,
    ) -> anyhow::Result<()> {
        let generated_at = Utc::now().to_rfc3339();
        let mut record = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "event_id": format!("hlt-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "generated_at": generated_at.clone(),
            "service_id": self.service_id,
            "component_id": self.provider_id,
            "component_kind": "provider",
            "provider_id": self.provider_id,
            "source": source,
            "overall_status": overall_status,
            "readiness": matches!(overall_status, "ready" | "idle"),
            "last_check_at": generated_at,
        });
        if let Some(item) = summary {
            record["summary"] = Value::String(item.to_string());
        }
        if let Some(path) = artifact_path {
            record["artifact_path"] = Value::String(path.display().to_string());
        }
        if !notes.is_empty() {
            record["notes"] = Value::Array(notes.into_iter().map(Value::String).collect());
        }
        self.health_validator
            .validate_value(&record)
            .with_context(|| {
                format!(
                    "failed to validate provider observability health record for service_id={} overall_status={overall_status}",
                    self.service_id
                )
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
        let mut line = serde_json::to_vec(payload)?;
        line.push(b'\n');
        file.write_all(&line)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    #[test]
    fn append_trace_writes_valid_trace_event() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-provider-observability-trace");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        let sink = ProviderObservabilitySink::new(
            path.clone(),
            "aios-system-intent-provider",
            "system.intent.local",
        )?;

        sink.append_trace(
            "provider.runtime.started",
            Some(&path),
            json!({"socket_path": "/tmp/provider.sock"}),
            vec!["lifecycle=startup".to_string()],
        )?;

        let contents = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(contents.lines().next().expect("entry"))?;
        assert_eq!(entry["source"], "aios-system-intent-provider");
        assert_eq!(entry["kind"], "provider.runtime.started");
        assert_eq!(entry["provider_id"], "system.intent.local");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn append_health_writes_valid_health_event() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-provider-observability-health");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        let sink = ProviderObservabilitySink::new(
            path.clone(),
            "aios-runtime-local-inference-provider",
            "runtime.local.inference",
        )?;

        sink.append_health_event(
            "startup",
            "ready",
            Some("reported provider availability"),
            Some(&path),
            vec!["registry_status=available".to_string()],
        )?;

        let contents = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(contents.lines().next().expect("entry"))?;
        assert_eq!(entry["component_kind"], "provider");
        assert_eq!(entry["provider_id"], "runtime.local.inference");
        assert_eq!(entry["overall_status"], "ready");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}

