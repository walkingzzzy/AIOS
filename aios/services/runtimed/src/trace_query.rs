use aios_contracts::{TraceEventRecord, TraceQueryRequest};
use serde_json::Value;

pub fn matches_request(entry: &TraceEventRecord, request: &TraceQueryRequest) -> bool {
    if let Some(session_id) = &request.session_id {
        if entry.session_id.as_deref() != Some(session_id.as_str()) {
            return false;
        }
    }
    if let Some(task_id) = &request.task_id {
        if entry.task_id.as_deref() != Some(task_id.as_str()) {
            return false;
        }
    }
    if let Some(kind) = &request.kind {
        if &entry.kind != kind {
            return false;
        }
    }
    if let Some(source) = &request.source {
        if &entry.source != source {
            return false;
        }
    }
    if let Some(needle) = request.payload_contains.as_deref() {
        if !payload_contains(&entry.payload, needle) {
            return false;
        }
    }
    for (path, expected) in &request.payload_equals {
        let Some(actual) = payload_value_at_path(&entry.payload, path) else {
            return false;
        };
        if actual != expected {
            return false;
        }
    }

    true
}

fn payload_contains(payload: &Value, needle: &str) -> bool {
    let needle = needle.trim();
    if needle.is_empty() {
        return true;
    }

    serde_json::to_string(payload)
        .map(|body| body.to_lowercase().contains(&needle.to_lowercase()))
        .unwrap_or(false)
}

fn payload_value_at_path<'a>(payload: &'a Value, path: &str) -> Option<&'a Value> {
    if path.is_empty() {
        return Some(payload);
    }

    let mut current = payload;
    for segment in path.split('.') {
        if segment.is_empty() {
            return None;
        }
        current = current.get(segment)?;
    }
    Some(current)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn event(payload: Value) -> TraceEventRecord {
        TraceEventRecord {
            event_id: "runtimed-evt-1".to_string(),
            timestamp: "2026-03-16T00:00:00Z".to_string(),
            source: "aios-runtimed".to_string(),
            kind: "runtime.backend.health".to_string(),
            task_id: Some("task-1".to_string()),
            session_id: Some("session-1".to_string()),
            payload,
        }
    }

    #[test]
    fn matches_request_supports_source_nested_payload_and_text_filters() {
        let entry = event(json!({
            "backend_id": "local-gpu",
            "health_state": "unavailable",
            "detail": {
                "route_state": "backend-fallback-local-cpu"
            }
        }));

        let request = TraceQueryRequest {
            source: Some("aios-runtimed".to_string()),
            payload_equals: std::collections::BTreeMap::from([
                ("backend_id".to_string(), json!("local-gpu")),
                (
                    "detail.route_state".to_string(),
                    json!("backend-fallback-local-cpu"),
                ),
            ]),
            payload_contains: Some("FALLBACK-LOCAL-CPU".to_string()),
            ..TraceQueryRequest::default()
        };

        assert!(matches_request(&entry, &request));
    }
}
