use std::{
    collections::{BTreeSet, VecDeque},
    fs::{self, File},
    io::{BufRead, BufReader, Write},
    path::Path,
};

use chrono::Utc;
use serde::Serialize;
use serde_json::Value;

use aios_contracts::{
    RuntimeBackendDescriptor, RuntimeBudgetResponse, RuntimeObservabilityExportRequest,
    RuntimeObservabilityExportResponse, RuntimeQueueResponse, TraceEventRecord, TraceQueryRequest,
};

use crate::{trace_query::matches_request, AppState};

#[derive(Debug, Clone, Serialize)]
struct RuntimeObservabilityExportCounts {
    runtime_event_count: u32,
    observability_count: u32,
    remote_audit_count: u32,
    backend_count: u32,
    correlated_session_count: u32,
    correlated_task_count: u32,
    artifact_count: u32,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeObservabilityExportProfiles {
    runtime_profile_id: String,
    route_profile_id: String,
    runtime_profile_path: String,
    route_profile_path: String,
    hardware_profile_id: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeObservabilityExportSourceLogs {
    runtime_events_log_path: String,
    observability_log_path: String,
    remote_audit_log_path: String,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeObservabilityExportArtifacts {
    manifest_path: String,
    runtime_events_path: String,
    observability_path: String,
    remote_audit_path: String,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeObservabilityExportSnapshots {
    backends: Vec<RuntimeBackendDescriptor>,
    queue: RuntimeQueueResponse,
    budget: RuntimeBudgetResponse,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeObservabilityCorrelationSummary {
    session_ids: Vec<String>,
    task_ids: Vec<String>,
    runtime_event_kinds: Vec<String>,
    observability_kinds: Vec<String>,
    remote_audit_statuses: Vec<String>,
    backend_ids: Vec<String>,
    artifact_paths: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct RuntimeObservabilityExportBundle {
    export_id: String,
    created_at: String,
    service_id: String,
    reason: Option<String>,
    query: RuntimeObservabilityExportRequest,
    counts: RuntimeObservabilityExportCounts,
    notes: Vec<String>,
    profiles: RuntimeObservabilityExportProfiles,
    source_logs: RuntimeObservabilityExportSourceLogs,
    exported_artifacts: RuntimeObservabilityExportArtifacts,
    snapshots: RuntimeObservabilityExportSnapshots,
    correlation: RuntimeObservabilityCorrelationSummary,
    runtime_events: Vec<TraceEventRecord>,
    observability: Vec<Value>,
    remote_audit: Vec<Value>,
}

pub fn export_bundle(
    state: &AppState,
    request: &RuntimeObservabilityExportRequest,
) -> anyhow::Result<RuntimeObservabilityExportResponse> {
    let created_at = Utc::now().to_rfc3339();
    let export_id = format!("runtime-observability-{}", Utc::now().timestamp_millis());
    let export_root = state
        .config
        .paths
        .state_dir
        .join("exports")
        .join(&export_id);
    fs::create_dir_all(&export_root)?;

    let runtime_events = if request.include_runtime_events {
        state.events.query(&request.query).entries
    } else {
        Vec::new()
    };
    let observability = if request.include_observability {
        load_trace_jsonl_values(&state.config.observability_log_path, &request.query)?
    } else {
        Vec::new()
    };
    let remote_audit = if request.include_remote_audit {
        load_remote_audit_values(state.remote_audit.path(), &request.query)?
    } else {
        Vec::new()
    };

    let runtime_events_path = export_root.join("runtime-events.jsonl");
    let observability_path = export_root.join("observability.jsonl");
    let remote_audit_path = export_root.join("attested-remote-audit.jsonl");
    let manifest_path = export_root.join("manifest.json");

    let runtime_event_values = runtime_events
        .iter()
        .map(serde_json::to_value)
        .collect::<Result<Vec<_>, _>>()?;
    write_jsonl_values(&runtime_events_path, &runtime_event_values)?;
    write_jsonl_values(&observability_path, &observability)?;
    write_jsonl_values(&remote_audit_path, &remote_audit)?;

    let backends = state.runtime_backends();
    let queue = queue_snapshot(state);
    let budget = state.budget.snapshot();
    let correlation =
        build_correlation_summary(&runtime_events, &observability, &remote_audit, &backends);
    let counts = RuntimeObservabilityExportCounts {
        runtime_event_count: count_u32(runtime_events.len()),
        observability_count: count_u32(observability.len()),
        remote_audit_count: count_u32(remote_audit.len()),
        backend_count: count_u32(backends.len()),
        correlated_session_count: count_u32(correlation.session_ids.len()),
        correlated_task_count: count_u32(correlation.task_ids.len()),
        artifact_count: count_u32(correlation.artifact_paths.len()),
    };
    let notes = build_notes(state, request, &counts);

    let bundle = RuntimeObservabilityExportBundle {
        export_id: export_id.clone(),
        created_at: created_at.clone(),
        service_id: state.config.service_id.clone(),
        reason: request.reason.clone(),
        query: request.clone(),
        counts: counts.clone(),
        notes: notes.clone(),
        profiles: RuntimeObservabilityExportProfiles {
            runtime_profile_id: state.scheduler.runtime_profile.profile_id.clone(),
            route_profile_id: state.scheduler.route_profile.profile_id.clone(),
            runtime_profile_path: state.config.runtime_profile_path.display().to_string(),
            route_profile_path: state.config.route_profile_path.display().to_string(),
            hardware_profile_id: state.config.hardware_profile_id.clone(),
        },
        source_logs: RuntimeObservabilityExportSourceLogs {
            runtime_events_log_path: state
                .config
                .paths
                .state_dir
                .join("runtime-events.jsonl")
                .display()
                .to_string(),
            observability_log_path: state.config.observability_log_path.display().to_string(),
            remote_audit_log_path: state.remote_audit.path().display().to_string(),
        },
        exported_artifacts: RuntimeObservabilityExportArtifacts {
            manifest_path: manifest_path.display().to_string(),
            runtime_events_path: runtime_events_path.display().to_string(),
            observability_path: observability_path.display().to_string(),
            remote_audit_path: remote_audit_path.display().to_string(),
        },
        snapshots: RuntimeObservabilityExportSnapshots {
            backends: backends.clone(),
            queue,
            budget,
        },
        correlation,
        runtime_events,
        observability,
        remote_audit,
    };

    fs::write(&manifest_path, serde_json::to_vec_pretty(&bundle)?)?;

    Ok(RuntimeObservabilityExportResponse {
        service_id: state.config.service_id.clone(),
        export_id,
        export_path: manifest_path.display().to_string(),
        created_at,
        runtime_event_count: counts.runtime_event_count,
        observability_count: counts.observability_count,
        remote_audit_count: counts.remote_audit_count,
        backend_count: counts.backend_count,
        correlated_session_count: counts.correlated_session_count,
        correlated_task_count: counts.correlated_task_count,
        artifact_count: counts.artifact_count,
        notes,
    })
}

fn queue_snapshot(state: &AppState) -> RuntimeQueueResponse {
    let pending = state.queue.snapshot();
    let max_concurrency = state.budget.max_concurrency;
    RuntimeQueueResponse {
        pending,
        max_concurrency,
        available_slots: state.queue.available_slots(max_concurrency),
        saturated: state.queue.is_saturated(max_concurrency),
    }
}

fn build_notes(
    state: &AppState,
    request: &RuntimeObservabilityExportRequest,
    counts: &RuntimeObservabilityExportCounts,
) -> Vec<String> {
    let mut notes = vec![
        format!("limit={}", request.query.limit),
        format!("reverse={}", request.query.reverse),
        format!("include_runtime_events={}", request.include_runtime_events),
        format!("include_observability={}", request.include_observability),
        format!("include_remote_audit={}", request.include_remote_audit),
        format!(
            "runtime_profile_id={}",
            state.scheduler.runtime_profile.profile_id
        ),
        format!(
            "route_profile_id={}",
            state.scheduler.route_profile.profile_id
        ),
        format!("runtime_event_count={}", counts.runtime_event_count),
        format!("observability_count={}", counts.observability_count),
        format!("remote_audit_count={}", counts.remote_audit_count),
    ];
    if let Some(session_id) = request.query.session_id.as_deref() {
        notes.push(format!("filter_session_id={session_id}"));
    }
    if let Some(task_id) = request.query.task_id.as_deref() {
        notes.push(format!("filter_task_id={task_id}"));
    }
    if let Some(kind) = request.query.kind.as_deref() {
        notes.push(format!("filter_kind={kind}"));
    }
    if let Some(source) = request.query.source.as_deref() {
        notes.push(format!("filter_source={source}"));
    }
    if let Some(reason) = request.reason.as_deref() {
        notes.push(format!("reason={reason}"));
    }
    if !request.query.payload_equals.is_empty() {
        notes.push(format!(
            "payload_equals_keys={}",
            request
                .query
                .payload_equals
                .keys()
                .cloned()
                .collect::<Vec<_>>()
                .join(",")
        ));
    }
    if let Some(needle) = request.query.payload_contains.as_deref() {
        notes.push(format!("payload_contains={needle}"));
    }
    notes.push("remote_audit_filter=task-session-payload".to_string());
    notes
}

fn build_correlation_summary(
    runtime_events: &[TraceEventRecord],
    observability: &[Value],
    remote_audit: &[Value],
    backends: &[RuntimeBackendDescriptor],
) -> RuntimeObservabilityCorrelationSummary {
    let mut session_ids = BTreeSet::new();
    let mut task_ids = BTreeSet::new();
    let mut runtime_event_kinds = BTreeSet::new();
    let mut observability_kinds = BTreeSet::new();
    let mut remote_audit_statuses = BTreeSet::new();
    let mut backend_ids = BTreeSet::new();
    let mut artifact_paths = BTreeSet::new();

    for backend in backends {
        backend_ids.insert(backend.backend_id.clone());
    }

    for entry in runtime_events {
        if let Some(session_id) = entry.session_id.as_deref() {
            session_ids.insert(session_id.to_string());
        }
        if let Some(task_id) = entry.task_id.as_deref() {
            task_ids.insert(task_id.to_string());
        }
        runtime_event_kinds.insert(entry.kind.clone());
        collect_backend_from_value(
            &mut backend_ids,
            &entry.payload,
            &["backend_id", "resolved_backend", "fallback_backend"],
        );
        collect_artifact_from_value(&mut artifact_paths, &entry.payload, &["artifact_path"]);
    }

    for value in observability {
        if let Some(session_id) = value.get("session_id").and_then(Value::as_str) {
            session_ids.insert(session_id.to_string());
        }
        if let Some(task_id) = value.get("task_id").and_then(Value::as_str) {
            task_ids.insert(task_id.to_string());
        }
        if let Some(kind) = value.get("kind").and_then(Value::as_str) {
            observability_kinds.insert(kind.to_string());
        }
        if let Some(payload) = value.get("payload") {
            collect_backend_from_value(
                &mut backend_ids,
                payload,
                &["backend_id", "resolved_backend", "fallback_backend"],
            );
            collect_artifact_from_value(&mut artifact_paths, payload, &["artifact_path"]);
        }
    }

    for value in remote_audit {
        if let Some(session_id) = value.get("session_id").and_then(Value::as_str) {
            session_ids.insert(session_id.to_string());
        }
        if let Some(task_id) = value.get("task_id").and_then(Value::as_str) {
            task_ids.insert(task_id.to_string());
        }
        if let Some(status) = value.get("status").and_then(Value::as_str) {
            remote_audit_statuses.insert(status.to_string());
        }
        collect_backend_from_value(
            &mut backend_ids,
            value,
            &["selected_backend", "requested_backend", "actual_backend"],
        );
        collect_artifact_from_value(&mut artifact_paths, value, &["artifact_path"]);
    }

    RuntimeObservabilityCorrelationSummary {
        session_ids: session_ids.into_iter().collect(),
        task_ids: task_ids.into_iter().collect(),
        runtime_event_kinds: runtime_event_kinds.into_iter().collect(),
        observability_kinds: observability_kinds.into_iter().collect(),
        remote_audit_statuses: remote_audit_statuses.into_iter().collect(),
        backend_ids: backend_ids.into_iter().collect(),
        artifact_paths: artifact_paths.into_iter().collect(),
    }
}

fn collect_backend_from_value(target: &mut BTreeSet<String>, value: &Value, keys: &[&str]) {
    for key in keys {
        if let Some(text) = value
            .get(*key)
            .and_then(Value::as_str)
            .filter(|item| !item.is_empty())
        {
            target.insert(text.to_string());
        }
    }
}

fn collect_artifact_from_value(target: &mut BTreeSet<String>, value: &Value, keys: &[&str]) {
    for key in keys {
        if let Some(text) = value
            .get(*key)
            .and_then(Value::as_str)
            .filter(|item| !item.is_empty())
        {
            target.insert(text.to_string());
        }
    }
}

fn load_trace_jsonl_values(path: &Path, request: &TraceQueryRequest) -> anyhow::Result<Vec<Value>> {
    load_jsonl_values(path, request.query_limit(), request.reverse, |value| {
        let Ok(record) = serde_json::from_value::<TraceEventRecord>(value.clone()) else {
            return Ok(false);
        };
        Ok(matches_request(&record, request))
    })
}

fn load_remote_audit_values(
    path: &Path,
    request: &TraceQueryRequest,
) -> anyhow::Result<Vec<Value>> {
    load_jsonl_values(path, request.query_limit(), request.reverse, |value| {
        Ok(remote_audit_matches_request(value, request))
    })
}

fn load_jsonl_values<F>(
    path: &Path,
    limit: usize,
    reverse: bool,
    mut predicate: F,
) -> anyhow::Result<Vec<Value>>
where
    F: FnMut(&Value) -> anyhow::Result<bool>,
{
    if !path.exists() {
        return Ok(Vec::new());
    }

    let file = File::open(path)?;
    let reader = BufReader::new(file);

    if reverse {
        let mut entries = VecDeque::with_capacity(limit);
        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            let value: Value = serde_json::from_str(&line)?;
            if !predicate(&value)? {
                continue;
            }
            if entries.len() >= limit {
                entries.pop_front();
            }
            entries.push_back(value);
        }
        let mut result = entries.into_iter().collect::<Vec<_>>();
        result.reverse();
        return Ok(result);
    }

    let mut entries = Vec::with_capacity(limit);
    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let value: Value = serde_json::from_str(&line)?;
        if !predicate(&value)? {
            continue;
        }
        entries.push(value);
        if entries.len() >= limit {
            break;
        }
    }
    Ok(entries)
}

fn write_jsonl_values(path: &Path, values: &[Value]) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = File::create(path)?;
    for value in values {
        writeln!(file, "{}", serde_json::to_string(value)?)?;
    }
    Ok(())
}

fn remote_audit_matches_request(value: &Value, request: &TraceQueryRequest) -> bool {
    if let Some(session_id) = request.query_session_id() {
        if value.get("session_id").and_then(Value::as_str) != Some(session_id) {
            return false;
        }
    }
    if let Some(task_id) = request.query_task_id() {
        if value.get("task_id").and_then(Value::as_str) != Some(task_id) {
            return false;
        }
    }
    if let Some(needle) = request.payload_contains.as_deref() {
        if !value_contains(value, needle) {
            return false;
        }
    }
    for (path, expected) in &request.payload_equals {
        let Some(actual) = remote_audit_value_at_path(value, path) else {
            return false;
        };
        if actual != expected {
            return false;
        }
    }
    true
}

fn remote_audit_value_at_path<'a>(value: &'a Value, path: &str) -> Option<&'a Value> {
    value_at_path(value, path).or_else(|| match path {
        "backend_id" | "fallback_backend" => value_at_path(value, "actual_backend"),
        "resolved_backend" => value_at_path(value, "selected_backend"),
        _ => None,
    })
}

fn value_contains(value: &Value, needle: &str) -> bool {
    let needle = needle.trim();
    if needle.is_empty() {
        return true;
    }
    serde_json::to_string(value)
        .map(|body| body.to_lowercase().contains(&needle.to_lowercase()))
        .unwrap_or(false)
}

fn value_at_path<'a>(value: &'a Value, path: &str) -> Option<&'a Value> {
    if path.is_empty() {
        return Some(value);
    }
    let mut current = value;
    for segment in path.split('.') {
        if segment.is_empty() {
            return None;
        }
        current = current.get(segment)?;
    }
    Some(current)
}

fn count_u32(len: usize) -> u32 {
    len.try_into().unwrap_or(u32::MAX)
}

trait TraceQueryRequestExt {
    fn query_limit(&self) -> usize;
    fn query_session_id(&self) -> Option<&str>;
    fn query_task_id(&self) -> Option<&str>;
}

impl TraceQueryRequestExt for TraceQueryRequest {
    fn query_limit(&self) -> usize {
        self.limit.max(1) as usize
    }

    fn query_session_id(&self) -> Option<&str> {
        self.session_id.as_deref()
    }

    fn query_task_id(&self) -> Option<&str> {
        self.task_id.as_deref()
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use serde_json::json;

    use super::*;

    #[test]
    fn load_trace_jsonl_values_respects_trace_filters() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-export-trace-query");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        write_jsonl_values(
            &path,
            &[
                json!({
                    "event_id": "obs-1",
                    "timestamp": "2026-03-16T00:00:00Z",
                    "source": "aios-runtimed",
                    "kind": "runtime.infer.fallback",
                    "session_id": "session-1",
                    "task_id": "task-1",
                    "payload": {
                        "backend_id": "local-cpu",
                        "artifact_path": "/tmp/vendor-error.json"
                    }
                }),
                json!({
                    "event_id": "obs-2",
                    "timestamp": "2026-03-16T00:00:01Z",
                    "source": "aios-runtimed",
                    "kind": "runtime.infer.completed",
                    "session_id": "session-1",
                    "task_id": "task-2",
                    "payload": {
                        "backend_id": "attested-remote"
                    }
                }),
            ],
        )?;

        let entries = load_trace_jsonl_values(
            &path,
            &TraceQueryRequest {
                kind: Some("runtime.infer.fallback".to_string()),
                payload_equals: BTreeMap::from([("backend_id".to_string(), json!("local-cpu"))]),
                limit: 10,
                reverse: false,
                ..TraceQueryRequest::default()
            },
        )?;

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0]["task_id"], "task-1");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn load_trace_jsonl_values_skips_non_trace_observability_records() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-export-non-trace-query");
        fs::create_dir_all(&root)?;
        let path = root.join("observability.jsonl");
        write_jsonl_values(
            &path,
            &[
                json!({
                    "event_id": "hlt-1",
                    "generated_at": "2026-03-16T00:00:00Z",
                    "service_id": "aios-system-files-provider",
                    "component_id": "system.files.local",
                    "component_kind": "provider",
                    "provider_id": "system.files.local",
                    "source": "startup",
                    "overall_status": "ready",
                    "readiness": true,
                    "last_check_at": "2026-03-16T00:00:00Z"
                }),
                json!({
                    "event_id": "obs-2",
                    "timestamp": "2026-03-16T00:00:01Z",
                    "source": "aios-runtimed",
                    "kind": "runtime.infer.completed",
                    "session_id": "session-1",
                    "task_id": "task-2",
                    "payload": {
                        "backend_id": "local-cpu"
                    }
                }),
            ],
        )?;

        let entries = load_trace_jsonl_values(&path, &TraceQueryRequest::default())?;

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0]["event_id"], "obs-2");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn load_remote_audit_values_filters_without_runtime_kind_requirement() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-export-remote-audit-query");
        fs::create_dir_all(&root)?;
        let path = root.join("attested-remote-audit.jsonl");
        write_jsonl_values(
            &path,
            &[
                json!({
                    "audit_id": "audit-1",
                    "timestamp": "2026-03-16T00:00:00Z",
                    "service_id": "aios-runtimed",
                    "status": "fallback",
                    "session_id": "session-1",
                    "task_id": "task-1",
                    "actual_backend": "local-cpu",
                    "artifact_path": "/tmp/vendor-error.json"
                }),
                json!({
                    "audit_id": "audit-2",
                    "timestamp": "2026-03-16T00:00:01Z",
                    "service_id": "aios-runtimed",
                    "status": "completed",
                    "session_id": "session-1",
                    "task_id": "task-2",
                    "actual_backend": "attested-remote"
                }),
            ],
        )?;

        let entries = load_remote_audit_values(
            &path,
            &TraceQueryRequest {
                task_id: Some("task-1".to_string()),
                kind: Some("runtime.infer.fallback".to_string()),
                payload_equals: BTreeMap::from([(
                    "actual_backend".to_string(),
                    json!("local-cpu"),
                )]),
                limit: 10,
                reverse: false,
                ..TraceQueryRequest::default()
            },
        )?;

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0]["status"], "fallback");
        assert_eq!(entries[0]["artifact_path"], "/tmp/vendor-error.json");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn load_remote_audit_values_supports_runtime_payload_aliases() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-export-remote-audit-alias-query");
        fs::create_dir_all(&root)?;
        let path = root.join("attested-remote-audit.jsonl");
        write_jsonl_values(
            &path,
            &[json!({
                "audit_id": "audit-alias-1",
                "timestamp": "2026-03-16T00:00:00Z",
                "service_id": "aios-runtimed",
                "status": "fallback",
                "session_id": "session-events",
                "task_id": "task-remote-fallback",
                "selected_backend": "attested-remote",
                "requested_backend": "attested-remote",
                "actual_backend": "local-cpu",
                "artifact_path": "/tmp/vendor-error.json"
            })],
        )?;

        let entries = load_remote_audit_values(
            &path,
            &TraceQueryRequest {
                task_id: Some("task-remote-fallback".to_string()),
                kind: Some("runtime.infer.fallback".to_string()),
                payload_equals: BTreeMap::from([
                    ("backend_id".to_string(), json!("local-cpu")),
                    ("resolved_backend".to_string(), json!("attested-remote")),
                ]),
                limit: 10,
                reverse: false,
                ..TraceQueryRequest::default()
            },
        )?;

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0]["status"], "fallback");
        assert_eq!(entries[0]["actual_backend"], "local-cpu");
        assert_eq!(entries[0]["selected_backend"], "attested-remote");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}

