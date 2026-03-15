use std::{
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
};

use anyhow::Context;
use chrono::Utc;
use serde_json::{json, Value};

use aios_contracts::{
    ExecutionToken, PortalHandleRecord, ProviderFsBulkDeleteResponse, ProviderFsOpenResponse,
};
use aios_core::schema::{
    self, CompiledJsonSchema, ObservabilitySchema, CURRENT_OBSERVABILITY_SCHEMA_VERSION,
};

#[derive(Debug, Clone)]
pub struct AuditWriter {
    path: PathBuf,
    provider_id: String,
    validator: CompiledJsonSchema,
}

impl AuditWriter {
    pub fn new(path: PathBuf) -> anyhow::Result<Self> {
        Self::with_provider_id(path, "system.files.local")
    }

    pub fn with_provider_id(path: PathBuf, provider_id: impl Into<String>) -> anyhow::Result<Self> {
        Ok(Self {
            path,
            provider_id: provider_id.into(),
            validator: schema::compile_observability_schema(ObservabilitySchema::AuditEvent)?,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn append_open(
        &self,
        token: &ExecutionToken,
        response: &ProviderFsOpenResponse,
    ) -> anyhow::Result<()> {
        self.append_entry(
            token,
            Some(&response.handle),
            "provider.fs.open",
            "opened",
            "allowed",
            json!({
                "object_kind": response.object_kind,
                "target_path": response.target_path,
                "target_hash": response.target_hash,
                "size_bytes": response.size_bytes,
                "entry_count": response.entries.len(),
                "has_content_preview": response.content_preview.is_some(),
                "truncated": response.truncated,
            }),
        )
    }

    pub fn append_delete(
        &self,
        token: &ExecutionToken,
        response: &ProviderFsBulkDeleteResponse,
    ) -> anyhow::Result<()> {
        self.append_entry(
            token,
            Some(&response.handle),
            "system.file.bulk_delete",
            &response.status,
            decision_for_delete(response),
            json!({
                "target_path": response.target_path,
                "dry_run": response.dry_run,
                "affected_count": response.affected_paths.len(),
                "affected_paths": response.affected_paths,
                "reason": response.reason,
            }),
        )
    }

    pub fn append_error(
        &self,
        operation: &str,
        token: Option<&ExecutionToken>,
        handle_id: Option<&str>,
        error: &str,
    ) -> anyhow::Result<()> {
        let timestamp = Utc::now().to_rfc3339();
        let mut payload = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "audit_id": format!("provider-audit-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": timestamp.clone(),
            "generated_at": timestamp,
            "provider_id": self.provider_id,
            "operation": operation,
            "status": "error",
            "decision": "denied",
            "user_id": token.map(|item| item.user_id.clone()).unwrap_or_else(|| "unknown".to_string()),
            "session_id": token.map(|item| item.session_id.clone()).unwrap_or_else(|| "unknown".to_string()),
            "task_id": token.map(|item| item.task_id.clone()).unwrap_or_else(|| "unknown".to_string()),
            "capability_id": token.map(|item| item.capability_id.clone()).unwrap_or_else(|| operation.to_string()),
            "execution_location": token.map(|item| item.execution_location.clone()).unwrap_or_else(|| "local".to_string()),
            "artifact_path": self.path.display().to_string(),
            "notes": [
                format!("operation={operation}"),
                "status=error".to_string(),
            ],
            "result": {
                "error": error,
            },
        });

        if let Some(item) = token.and_then(|value| value.target_hash.clone()) {
            payload["target_hash"] = Value::String(item);
        }
        if let Some(item) = token.and_then(|value| value.approval_ref.clone()) {
            payload["approval_id"] = Value::String(item);
        }
        if let Some(item) = token.and_then(|value| value.taint_summary.clone()) {
            payload["taint_summary"] = Value::String(item);
        }
        if let Some(item) = handle_id {
            payload["handle_id"] = Value::String(item.to_string());
        }

        self.append_json(payload)
    }

    fn append_entry(
        &self,
        token: &ExecutionToken,
        handle: Option<&PortalHandleRecord>,
        operation: &str,
        status: &str,
        decision: &str,
        result: Value,
    ) -> anyhow::Result<()> {
        let timestamp = Utc::now().to_rfc3339();
        let mut payload = json!({
            "schema_version": CURRENT_OBSERVABILITY_SCHEMA_VERSION,
            "audit_id": format!("provider-audit-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": timestamp.clone(),
            "generated_at": timestamp,
            "provider_id": self.provider_id,
            "operation": operation,
            "status": status,
            "decision": decision,
            "user_id": token.user_id,
            "session_id": token.session_id,
            "task_id": token.task_id,
            "capability_id": token.capability_id,
            "execution_location": token.execution_location,
            "artifact_path": self.path.display().to_string(),
            "notes": [
                format!("operation={operation}"),
                format!("status={status}"),
            ],
            "result": result,
        });

        if let Some(item) = &token.target_hash {
            payload["target_hash"] = Value::String(item.clone());
        }
        if let Some(item) = &token.approval_ref {
            payload["approval_id"] = Value::String(item.clone());
        }
        if let Some(item) = &token.taint_summary {
            payload["taint_summary"] = Value::String(item.clone());
        }
        if let Some(handle) = handle {
            payload["handle_id"] = Value::String(handle.handle_id.clone());
            payload["handle_kind"] = Value::String(handle.kind.clone());
            payload["handle_target"] = Value::String(handle.target.clone());
            payload["handle_audit_tags"] = Value::Array(
                handle
                    .audit_tags
                    .iter()
                    .cloned()
                    .map(Value::String)
                    .collect(),
            );
        }

        self.append_json(payload)
    }

    fn append_json(&self, mut payload: Value) -> anyhow::Result<()> {
        let object = payload
            .as_object_mut()
            .context("provider audit payload must be a JSON object")?;
        let nullable_keys = object
            .iter()
            .filter_map(|(key, value)| {
                if value.is_null() && key != "result" {
                    Some(key.clone())
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        for key in nullable_keys {
            object.remove(&key);
        }

        self.validator
            .validate_value(&payload)
            .with_context(|| {
                format!(
                    "failed to validate provider audit record for provider_id={}",
                    self.provider_id
                )
            })?;

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

fn decision_for_delete(response: &ProviderFsBulkDeleteResponse) -> &'static str {
    if response.dry_run || response.status == "would-delete" {
        return "dry-run";
    }

    match response.status.as_str() {
        "deleted" => "allowed",
        "skipped" => {
            if response
                .reason
                .as_deref()
                .unwrap_or_default()
                .contains("approval_ref")
            {
                "needs-approval"
            } else {
                "denied"
            }
        }
        _ => "denied",
    }
}

#[cfg(test)]
mod tests {
    use std::{collections::BTreeMap, fs};

    use super::*;

    fn token() -> ExecutionToken {
        ExecutionToken {
            user_id: "u1".to_string(),
            session_id: "s1".to_string(),
            task_id: "t1".to_string(),
            capability_id: "provider.fs.open".to_string(),
            target_hash: Some("sha256:abc".to_string()),
            expiry: "2099-01-01T00:00:00Z".to_string(),
            approval_ref: None,
            constraints: BTreeMap::new(),
            execution_location: "local".to_string(),
            taint_summary: None,
            signature: None,
        }
    }

    fn handle() -> PortalHandleRecord {
        PortalHandleRecord {
            handle_id: "ph-1".to_string(),
            kind: "file_handle".to_string(),
            user_id: "u1".to_string(),
            session_id: "s1".to_string(),
            target: "/tmp/demo.txt".to_string(),
            scope: BTreeMap::new(),
            expiry: "2099-01-01T00:00:00Z".to_string(),
            revocable: true,
            issued_at: "2026-01-01T00:00:00Z".to_string(),
            revoked_at: None,
            revocation_reason: None,
            audit_tags: vec!["provider-smoke".to_string()],
        }
    }

    #[test]
    fn append_open_writes_schema_aligned_entry() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-system-files-audit-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("audit.jsonl");
        let writer = AuditWriter::new(path.clone())?;
        writer.append_open(
            &token(),
            &ProviderFsOpenResponse {
                provider_id: "system.files.local".to_string(),
                handle: handle(),
                object_kind: "file".to_string(),
                target_path: "/tmp/demo.txt".to_string(),
                target_hash: "sha256:abc".to_string(),
                size_bytes: Some(12),
                entries: Vec::new(),
                content_preview: Some("demo".to_string()),
                truncated: false,
            },
        )?;

        let lines = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(lines.lines().next().expect("audit entry"))?;
        assert_eq!(entry["operation"], "provider.fs.open");
        assert_eq!(entry["status"], "opened");
        assert_eq!(entry["decision"], "allowed");
        assert_eq!(entry["handle_id"], "ph-1");
        assert_eq!(
            entry["schema_version"],
            CURRENT_OBSERVABILITY_SCHEMA_VERSION
        );
        assert_eq!(entry["artifact_path"], path.display().to_string());

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn append_delete_dry_run_uses_dry_run_decision() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-system-files-audit-delete-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("audit.jsonl");
        let writer = AuditWriter::new(path.clone())?;
        writer.append_delete(
            &token(),
            &ProviderFsBulkDeleteResponse {
                provider_id: "system.files.local".to_string(),
                handle: handle(),
                target_path: "/tmp/demo.txt".to_string(),
                dry_run: true,
                status: "would-delete".to_string(),
                affected_paths: vec!["/tmp/demo.txt".to_string()],
                reason: None,
            },
        )?;

        let lines = fs::read_to_string(&path)?;
        let entry: Value = serde_json::from_str(lines.lines().next().expect("audit entry"))?;
        assert_eq!(entry["operation"], "system.file.bulk_delete");
        assert_eq!(entry["status"], "would-delete");
        assert_eq!(entry["decision"], "dry-run");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
