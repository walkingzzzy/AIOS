use std::{
    collections::VecDeque,
    fs::{File, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::PathBuf,
};

use aios_contracts::{TraceEventRecord, TraceQueryRequest};

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

fn matches_request(entry: &TraceEventRecord, request: &TraceQueryRequest) -> bool {
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

    true
}

#[cfg(test)]
mod tests {
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
}
