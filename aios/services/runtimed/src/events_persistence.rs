use std::{
    collections::VecDeque,
    fs::{File, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::PathBuf,
};

use aios_contracts::{TraceEventRecord, TraceQueryRequest};

use crate::trace_query::matches_request;

#[derive(Debug, Clone)]
pub struct EventLog {
    path: PathBuf,
}

impl EventLog {
    pub fn new(path: PathBuf) -> Self {
        Self { path }
    }

    pub fn load_recent(&self, capacity: usize) -> anyhow::Result<VecDeque<TraceEventRecord>> {
        let mut entries = VecDeque::with_capacity(capacity);
        if !self.path.exists() {
            return Ok(entries);
        }

        let file = File::open(&self.path)?;
        for line in BufReader::new(file).lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }

            let record = serde_json::from_str::<TraceEventRecord>(&line)?;
            if entries.len() >= capacity {
                entries.pop_front();
            }
            entries.push_back(record);
        }

        Ok(entries)
    }

    pub fn append(&self, record: &TraceEventRecord) -> anyhow::Result<()> {
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        writeln!(file, "{}", serde_json::to_string(record)?)?;
        Ok(())
    }

    pub fn query(&self, request: &TraceQueryRequest) -> anyhow::Result<Vec<TraceEventRecord>> {
        if !self.path.exists() {
            return Ok(Vec::new());
        }

        let limit = request.limit.max(1) as usize;
        let file = File::open(&self.path)?;
        let reader = BufReader::new(file);

        if request.reverse {
            let mut entries = VecDeque::with_capacity(limit);
            for line in reader.lines() {
                let line = line?;
                if line.trim().is_empty() {
                    continue;
                }

                let record = serde_json::from_str::<TraceEventRecord>(&line)?;
                if !matches_request(&record, request) {
                    continue;
                }

                if entries.len() >= limit {
                    entries.pop_front();
                }
                entries.push_back(record);
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

            let record = serde_json::from_str::<TraceEventRecord>(&line)?;
            if !matches_request(&record, request) {
                continue;
            }

            entries.push(record);
            if entries.len() >= limit {
                break;
            }
        }

        Ok(entries)
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::fs;

    use serde_json::json;

    use super::*;

    fn event(index: usize, kind: &str) -> TraceEventRecord {
        TraceEventRecord {
            event_id: format!("runtimed-evt-{index}"),
            timestamp: format!("2026-03-11T00:00:{index:02}Z"),
            source: "aios-runtimed".to_string(),
            kind: kind.to_string(),
            task_id: Some("task-1".to_string()),
            session_id: Some("session-1".to_string()),
            payload: json!({ "index": index }),
        }
    }

    #[test]
    fn query_returns_oldest_matches_in_forward_order() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-event-log-forward");
        fs::create_dir_all(&root)?;
        let path = root.join("runtime-events.jsonl");
        let log = EventLog::new(path.clone());

        log.append(&event(1, "runtime.infer.submit"))?;
        log.append(&event(2, "runtime.infer.completed"))?;
        log.append(&event(3, "runtime.infer.completed"))?;

        let entries = log.query(&TraceQueryRequest {
            session_id: Some("session-1".to_string()),
            kind: Some("runtime.infer.completed".to_string()),
            limit: 2,
            reverse: false,
            ..TraceQueryRequest::default()
        })?;

        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].event_id, "runtimed-evt-2");
        assert_eq!(entries[1].event_id, "runtimed-evt-3");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn query_returns_latest_matches_in_reverse_order() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-event-log-reverse");
        fs::create_dir_all(&root)?;
        let path = root.join("runtime-events.jsonl");
        let log = EventLog::new(path.clone());

        log.append(&event(1, "runtime.infer.completed"))?;
        log.append(&event(2, "runtime.infer.completed"))?;
        log.append(&event(3, "runtime.infer.completed"))?;

        let entries = log.query(&TraceQueryRequest {
            task_id: Some("task-1".to_string()),
            kind: Some("runtime.infer.completed".to_string()),
            limit: 2,
            reverse: true,
            ..TraceQueryRequest::default()
        })?;

        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].event_id, "runtimed-evt-3");
        assert_eq!(entries[1].event_id, "runtimed-evt-2");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn query_filters_by_payload_fields_and_substring() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join("aios-runtimed-event-log-payload-filter");
        fs::create_dir_all(&root)?;
        let path = root.join("runtime-events.jsonl");
        let log = EventLog::new(path.clone());

        log.append(&TraceEventRecord {
            event_id: "runtimed-evt-gpu".to_string(),
            timestamp: "2026-03-16T00:00:01Z".to_string(),
            source: "aios-runtimed".to_string(),
            kind: "runtime.backend.health".to_string(),
            task_id: None,
            session_id: None,
            payload: json!({
                "backend_id": "local-gpu",
                "detail": {
                    "route_state": "backend-fallback-local-cpu"
                }
            }),
        })?;
        log.append(&TraceEventRecord {
            event_id: "runtimed-evt-npu".to_string(),
            timestamp: "2026-03-16T00:00:02Z".to_string(),
            source: "aios-runtimed".to_string(),
            kind: "runtime.backend.health".to_string(),
            task_id: None,
            session_id: None,
            payload: json!({
                "backend_id": "local-npu",
                "detail": {
                    "route_state": "local-npu-worker-v1"
                }
            }),
        })?;

        let entries = log.query(&TraceQueryRequest {
            source: Some("aios-runtimed".to_string()),
            payload_equals: BTreeMap::from([
                ("backend_id".to_string(), json!("local-gpu")),
                (
                    "detail.route_state".to_string(),
                    json!("backend-fallback-local-cpu"),
                ),
            ]),
            payload_contains: Some("FALLBACK-LOCAL-CPU".to_string()),
            limit: 10,
            ..TraceQueryRequest::default()
        })?;

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].event_id, "runtimed-evt-gpu");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
