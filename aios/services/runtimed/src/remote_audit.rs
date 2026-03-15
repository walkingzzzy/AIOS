use std::{fs::OpenOptions, io::Write, path::PathBuf};

use chrono::Utc;
use serde_json::json;

use aios_contracts::{
    methods, ExecutionToken, RuntimeInferRequest, RuntimeInferResponse, RuntimeRouteResolveResponse,
};

use crate::observability::ObservabilitySink;

#[derive(Debug, Clone)]
pub struct RemoteAuditWriter {
    path: PathBuf,
    sink: Option<ObservabilitySink>,
}

impl RemoteAuditWriter {
    pub fn new(path: PathBuf) -> Self {
        Self { path, sink: None }
    }

    pub fn with_sink(path: PathBuf, sink: Option<ObservabilitySink>) -> Self {
        Self { path, sink }
    }

    pub fn path(&self) -> &PathBuf {
        &self.path
    }

    pub fn append_result(
        &self,
        token: &ExecutionToken,
        request: &RuntimeInferRequest,
        route: &RuntimeRouteResolveResponse,
        response: &RuntimeInferResponse,
    ) -> anyhow::Result<()> {
        let status = if response.rejected {
            "rejected"
        } else if response.route_state.contains("fallback") {
            "fallback"
        } else {
            "completed"
        };

        self.append_json(json!({
            "audit_id": format!("runtimed-remote-audit-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": Utc::now().to_rfc3339(),
            "service_id": "aios-runtimed",
            "operation": methods::RUNTIME_INFER_SUBMIT,
            "status": status,
            "user_id": token.user_id,
            "session_id": token.session_id,
            "task_id": token.task_id,
            "capability_id": token.capability_id,
            "execution_location": token.execution_location,
            "approval_ref": token.approval_ref,
            "target_hash": token.target_hash,
            "selected_backend": route.selected_backend,
            "requested_backend": request.preferred_backend,
            "actual_backend": response.backend_id,
            "route_state": response.route_state,
            "degraded": response.degraded,
            "rejected": response.rejected,
            "estimated_latency_ms": response.estimated_latency_ms,
            "taint_summary": token.taint_summary,
            "result": {
                "reason": response.reason,
                "content_chars": response.content.chars().count(),
                "model": request.model,
            },
        }))
    }

    pub fn append_error(
        &self,
        token: Option<&ExecutionToken>,
        request: &RuntimeInferRequest,
        route: &RuntimeRouteResolveResponse,
        route_state: &str,
        error: &str,
    ) -> anyhow::Result<()> {
        self.append_json(json!({
            "audit_id": format!("runtimed-remote-audit-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": Utc::now().to_rfc3339(),
            "service_id": "aios-runtimed",
            "operation": methods::RUNTIME_INFER_SUBMIT,
            "status": "error",
            "user_id": token.map(|item| item.user_id.clone()).unwrap_or_else(|| "unknown".to_string()),
            "session_id": request.session_id,
            "task_id": request.task_id,
            "capability_id": token.map(|item| item.capability_id.clone()).unwrap_or_else(|| methods::RUNTIME_INFER_SUBMIT.to_string()),
            "execution_location": token.map(|item| item.execution_location.clone()).unwrap_or_else(|| "attested_remote".to_string()),
            "approval_ref": token.and_then(|item| item.approval_ref.clone()),
            "target_hash": token.and_then(|item| item.target_hash.clone()),
            "selected_backend": route.selected_backend,
            "requested_backend": request.preferred_backend,
            "actual_backend": route.selected_backend,
            "route_state": route_state,
            "degraded": route.degraded,
            "rejected": true,
            "estimated_latency_ms": null,
            "taint_summary": token.and_then(|item| item.taint_summary.clone()),
            "result": {
                "error": error,
                "model": request.model,
            },
        }))
    }

    fn append_json(&self, payload: serde_json::Value) -> anyhow::Result<()> {
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        writeln!(file, "{}", serde_json::to_string(&payload)?)?;

        if let Some(sink) = &self.sink {
            let session_id = payload.get("session_id").and_then(|item| item.as_str());
            let task_id = payload.get("task_id").and_then(|item| item.as_str());
            sink.append_record(
                "aios-runtimed",
                "attested-remote-audit",
                session_id,
                task_id,
                payload.clone(),
            )?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::{collections::BTreeMap, fs};

    use super::*;

    fn token() -> ExecutionToken {
        ExecutionToken {
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: methods::RUNTIME_INFER_SUBMIT.to_string(),
            target_hash: None,
            expiry: "2099-01-01T00:00:00Z".to_string(),
            approval_ref: Some("approval-1".to_string()),
            constraints: BTreeMap::new(),
            execution_location: "attested_remote".to_string(),
            taint_summary: Some("remote-execution-path".to_string()),
            signature: Some("sig".to_string()),
        }
    }

    #[test]
    fn append_result_writes_structured_remote_audit_entry() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-runtimed-remote-audit-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("remote-audit.jsonl");
        let writer = RemoteAuditWriter::new(path.clone());

        writer.append_result(
            &token(),
            &RuntimeInferRequest {
                session_id: "session-1".to_string(),
                task_id: "task-1".to_string(),
                prompt: "remote test".to_string(),
                model: Some("smoke-model".to_string()),
                execution_token: None,
                preferred_backend: Some("attested-remote".to_string()),
            },
            &RuntimeRouteResolveResponse {
                selected_backend: "attested-remote".to_string(),
                route_state: "attested-remote".to_string(),
                degraded: false,
                reason: "remote".to_string(),
            },
            &RuntimeInferResponse {
                backend_id: "attested-remote".to_string(),
                route_state: "attested-remote".to_string(),
                content: "remote-ok".to_string(),
                degraded: false,
                rejected: false,
                reason: Some("ok".to_string()),
                estimated_latency_ms: Some(42),
                provider_id: None,
                runtime_service_id: None,
                provider_status: None,
                queue_saturated: None,
                runtime_budget: None,
                notes: Vec::new(),
            },
        )?;

        let lines = fs::read_to_string(&path)?;
        let entry: serde_json::Value =
            serde_json::from_str(lines.lines().next().expect("audit entry"))?;
        assert_eq!(entry["status"], "completed");
        assert_eq!(entry["actual_backend"], "attested-remote");
        assert_eq!(entry["execution_location"], "attested_remote");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn append_result_mirrors_to_observability_sink() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-runtimed-remote-audit-sink-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let audit_path = root.join("remote-audit.jsonl");
        let sink_path = root.join("observability.jsonl");
        let writer = RemoteAuditWriter::with_sink(
            audit_path,
            Some(ObservabilitySink::new(sink_path.clone())?),
        );

        writer.append_error(
            Some(&token()),
            &RuntimeInferRequest {
                session_id: "session-1".to_string(),
                task_id: "task-1".to_string(),
                prompt: "remote test".to_string(),
                model: Some("smoke-model".to_string()),
                execution_token: None,
                preferred_backend: Some("attested-remote".to_string()),
            },
            &RuntimeRouteResolveResponse {
                selected_backend: "attested-remote".to_string(),
                route_state: "attested-remote".to_string(),
                degraded: false,
                reason: "remote".to_string(),
            },
            "remote-error",
            "backend offline",
        )?;

        let lines = fs::read_to_string(&sink_path)?;
        let entry: serde_json::Value =
            serde_json::from_str(lines.lines().next().expect("sink entry"))?;
        assert_eq!(entry["kind"], "attested-remote-audit");
        assert_eq!(entry["payload"]["result"]["error"], "backend offline");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
