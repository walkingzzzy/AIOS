use std::{
    collections::VecDeque,
    path::PathBuf,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
};

use chrono::Utc;
use serde_json::Value;

use aios_contracts::{TraceEventRecord, TraceQueryRequest, TraceQueryResponse};

use crate::{events_persistence::EventLog, observability::ObservabilitySink};

const DEFAULT_EVENT_CAPACITY: usize = 128;

#[derive(Debug, Clone)]
pub struct EventStore {
    entries: Arc<Mutex<VecDeque<TraceEventRecord>>>,
    next_id: Arc<AtomicU64>,
    capacity: usize,
    persistence: Option<EventLog>,
    sink: Option<ObservabilitySink>,
}

impl Default for EventStore {
    fn default() -> Self {
        Self::new(DEFAULT_EVENT_CAPACITY, None)
    }
}

impl EventStore {
    pub fn new(capacity: usize, persistence: Option<EventLog>) -> Self {
        Self::new_with_sink(capacity, persistence, None)
    }

    pub fn new_with_sink(
        capacity: usize,
        persistence: Option<EventLog>,
        sink: Option<ObservabilitySink>,
    ) -> Self {
        let entries = persistence
            .as_ref()
            .and_then(|log| match log.load_recent(capacity) {
                Ok(entries) => Some(entries),
                Err(error) => {
                    tracing::warn!(?error, "failed to preload runtimed event log");
                    None
                }
            })
            .unwrap_or_else(|| VecDeque::with_capacity(capacity));

        let next_id = entries
            .back()
            .and_then(|entry| entry.event_id.rsplit('-').next())
            .and_then(|suffix| suffix.parse::<u64>().ok())
            .map(|id| id + 1)
            .unwrap_or(1);

        Self {
            entries: Arc::new(Mutex::new(entries)),
            next_id: Arc::new(AtomicU64::new(next_id)),
            capacity,
            persistence,
            sink,
        }
    }

    pub fn with_persistence(path: PathBuf) -> Self {
        Self::new(DEFAULT_EVENT_CAPACITY, Some(EventLog::new(path)))
    }

    pub fn with_persistence_and_sink(path: PathBuf, sink: Option<ObservabilitySink>) -> Self {
        Self::new_with_sink(DEFAULT_EVENT_CAPACITY, Some(EventLog::new(path)), sink)
    }

    pub fn record(
        &self,
        kind: &str,
        session_id: Option<&str>,
        task_id: Option<&str>,
        payload: Value,
    ) {
        let event = TraceEventRecord {
            event_id: format!(
                "runtimed-evt-{}",
                self.next_id.fetch_add(1, Ordering::SeqCst)
            ),
            timestamp: Utc::now().to_rfc3339(),
            source: "aios-runtimed".to_string(),
            kind: kind.to_string(),
            task_id: task_id.map(str::to_string),
            session_id: session_id.map(str::to_string),
            payload,
        };

        let mut entries = self.entries.lock().expect("runtime events mutex poisoned");
        if entries.len() >= self.capacity {
            entries.pop_front();
        }
        entries.push_back(event.clone());
        drop(entries);

        if let Some(log) = &self.persistence {
            if let Err(error) = log.append(&event) {
                tracing::warn!(?error, "failed to persist runtimed event");
            }
        }
        if let Some(sink) = &self.sink {
            if let Err(error) = sink.append_record(
                &event.source,
                &event.kind,
                event.session_id.as_deref(),
                event.task_id.as_deref(),
                event.payload.clone(),
            ) {
                tracing::warn!(?error, "failed to append observability event");
            }
        }
    }

    pub fn query(&self, request: &TraceQueryRequest) -> TraceQueryResponse {
        if let Some(log) = &self.persistence {
            match log.query(request) {
                Ok(entries) => return TraceQueryResponse { entries },
                Err(error) => {
                    tracing::warn!(?error, "failed to query persisted runtimed event log");
                }
            }
        }

        let entries = self.entries.lock().expect("runtime events mutex poisoned");
        let mut filtered = entries
            .iter()
            .filter(|entry| matches_request(entry, request))
            .cloned()
            .collect::<Vec<_>>();

        if request.reverse {
            filtered.reverse();
        }

        filtered.truncate(request.limit.max(1) as usize);
        TraceQueryResponse { entries: filtered }
    }

    pub fn len(&self) -> usize {
        self.entries
            .lock()
            .expect("runtime events mutex poisoned")
            .len()
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

    use super::*;
    use serde_json::json;

    #[test]
    fn event_store_filters_and_orders_events() {
        let store = EventStore::default();
        store.record(
            "runtime.infer.completed",
            Some("session-1"),
            Some("task-1"),
            json!({"ok": true}),
        );
        store.record(
            "runtime.infer.fallback",
            Some("session-1"),
            Some("task-2"),
            json!({"ok": true}),
        );

        let response = store.query(&TraceQueryRequest {
            session_id: Some("session-1".to_string()),
            kind: Some("runtime.infer.fallback".to_string()),
            limit: 10,
            reverse: true,
            ..TraceQueryRequest::default()
        });
        assert_eq!(response.entries.len(), 1);
        assert_eq!(response.entries[0].kind, "runtime.infer.fallback");
    }

    #[test]
    fn event_store_preloads_persisted_records() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-runtimed-events-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("runtime-events.jsonl");

        let store = EventStore::with_persistence(path.clone());
        store.record(
            "runtime.infer.completed",
            Some("session-1"),
            Some("task-1"),
            json!({"status": "ok"}),
        );
        drop(store);

        let reloaded = EventStore::with_persistence(path);
        let entries = reloaded.query(&TraceQueryRequest::default());
        assert_eq!(entries.entries.len(), 1);
        assert_eq!(entries.entries[0].kind, "runtime.infer.completed");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn event_store_queries_full_persisted_history_beyond_ring_capacity() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-runtimed-events-history-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("runtime-events.jsonl");

        let store = EventStore::new(2, Some(EventLog::new(path.clone())));
        store.record(
            "runtime.infer.completed",
            Some("session-1"),
            Some("task-1"),
            json!({"index": 1}),
        );
        store.record(
            "runtime.infer.completed",
            Some("session-1"),
            Some("task-2"),
            json!({"index": 2}),
        );
        store.record(
            "runtime.infer.completed",
            Some("session-1"),
            Some("task-3"),
            json!({"index": 3}),
        );

        assert_eq!(
            store.len(),
            2,
            "ring buffer should still cap in-memory entries"
        );

        let response = store.query(&TraceQueryRequest {
            session_id: Some("session-1".to_string()),
            kind: Some("runtime.infer.completed".to_string()),
            limit: 10,
            reverse: false,
            ..TraceQueryRequest::default()
        });

        let task_ids = response
            .entries
            .iter()
            .filter_map(|entry| entry.task_id.clone())
            .collect::<Vec<_>>();
        assert_eq!(task_ids, vec!["task-1", "task-2", "task-3"]);

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
