use std::sync::{Arc, Mutex};

use chrono::Utc;

#[derive(Clone)]
pub struct RegistrySyncStatus {
    inner: Arc<Mutex<RegistrySyncSnapshot>>,
}

impl RegistrySyncStatus {
    pub fn new(interval_seconds: u64) -> Self {
        Self {
            inner: Arc::new(Mutex::new(RegistrySyncSnapshot {
                interval_seconds,
                registration_state: "startup-pending".to_string(),
                last_reported_status: None,
                last_reported_error: None,
                last_sync_failure: None,
                last_update_at: None,
            })),
        }
    }

    pub fn record_descriptor_missing(&self) {
        self.update(|snapshot| {
            snapshot.registration_state = "descriptor-missing".to_string();
            snapshot.last_update_at = Some(now_rfc3339());
        });
    }

    pub fn record_startup_registration_succeeded(&self) {
        self.update(|snapshot| {
            snapshot.registration_state = "startup-registered".to_string();
            snapshot.last_sync_failure = None;
            snapshot.last_update_at = Some(now_rfc3339());
        });
    }

    pub fn record_startup_registration_failed(&self, error: impl ToString) {
        self.update(|snapshot| {
            snapshot.registration_state = "startup-pending".to_string();
            snapshot.last_sync_failure = Some(compact_note_value(error));
            snapshot.last_update_at = Some(now_rfc3339());
        });
    }

    pub fn record_registration_retry_failed(&self, error: impl ToString) {
        self.update(|snapshot| {
            snapshot.registration_state = "retrying".to_string();
            snapshot.last_sync_failure = Some(compact_note_value(error));
            snapshot.last_update_at = Some(now_rfc3339());
        });
    }

    pub fn record_registration_recovered(&self) {
        self.update(|snapshot| {
            snapshot.registration_state = "recovered".to_string();
            snapshot.last_sync_failure = None;
            snapshot.last_update_at = Some(now_rfc3339());
        });
    }

    pub fn record_health_report(&self, status: &str, error: Option<String>) {
        self.update(|snapshot| {
            snapshot.last_reported_status = Some(status.to_string());
            snapshot.last_reported_error = error.map(compact_note_value);
            snapshot.last_sync_failure = None;
            snapshot.last_update_at = Some(now_rfc3339());
        });
    }

    pub fn record_health_sync_failure(&self, error: impl ToString) {
        self.update(|snapshot| {
            snapshot.last_sync_failure = Some(compact_note_value(error));
            snapshot.last_update_at = Some(now_rfc3339());
        });
    }

    pub fn health_notes(&self) -> Vec<String> {
        let snapshot = self.snapshot();
        let mut notes = vec![
            "registry_sync_enabled=true".to_string(),
            format!(
                "registry_sync_interval_seconds={}",
                snapshot.interval_seconds
            ),
            format!(
                "registry_registration_state={}",
                snapshot.registration_state
            ),
            format!(
                "registry_last_reported_status={}",
                snapshot
                    .last_reported_status
                    .unwrap_or_else(|| "unknown".to_string())
            ),
        ];

        if let Some(last_reported_error) = snapshot.last_reported_error {
            notes.push(format!(
                "registry_last_reported_error={last_reported_error}"
            ));
        }
        if let Some(last_sync_failure) = snapshot.last_sync_failure {
            notes.push(format!("registry_last_sync_failure={last_sync_failure}"));
        }
        if let Some(last_update_at) = snapshot.last_update_at {
            notes.push(format!("registry_last_sync_at={last_update_at}"));
        }

        notes
    }

    fn snapshot(&self) -> RegistrySyncSnapshot {
        self.inner
            .lock()
            .expect("registry sync status lock poisoned")
            .clone()
    }

    fn update(&self, update: impl FnOnce(&mut RegistrySyncSnapshot)) {
        let mut guard = self
            .inner
            .lock()
            .expect("registry sync status lock poisoned");
        update(&mut guard);
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct RegistrySyncSnapshot {
    interval_seconds: u64,
    registration_state: String,
    last_reported_status: Option<String>,
    last_reported_error: Option<String>,
    last_sync_failure: Option<String>,
    last_update_at: Option<String>,
}

fn now_rfc3339() -> String {
    Utc::now().to_rfc3339()
}

fn compact_note_value(value: impl ToString) -> String {
    let mut compact = value.to_string().replace('\n', " ");
    if compact.len() > 160 {
        compact.truncate(157);
        compact.push_str("...");
    }
    compact
}

#[cfg(test)]
mod tests {
    use super::*;

    fn note_value<'a>(notes: &'a [String], key: &str) -> Option<&'a str> {
        notes.iter().find_map(|note| {
            let (candidate, value) = note.split_once('=')?;
            (candidate == key).then_some(value)
        })
    }

    #[test]
    fn reports_recovered_registration_and_available_health() {
        let status = RegistrySyncStatus::new(1);

        status.record_startup_registration_failed("failed to connect to agentd");
        status.record_registration_recovered();
        status.record_health_report("available", None);

        let notes = status.health_notes();
        assert_eq!(
            note_value(&notes, "registry_registration_state"),
            Some("recovered")
        );
        assert_eq!(
            note_value(&notes, "registry_last_reported_status"),
            Some("available")
        );
        assert!(
            note_value(&notes, "registry_last_sync_failure").is_none(),
            "successful recovery should clear sync failure note"
        );
    }

    #[test]
    fn truncates_long_sync_failures_for_health_notes() {
        let status = RegistrySyncStatus::new(1);
        let long_error = format!("failed to connect: {}", "x".repeat(240));

        status.record_health_sync_failure(long_error);

        let notes = status.health_notes();
        let failure = note_value(&notes, "registry_last_sync_failure")
            .expect("registry_last_sync_failure note should exist");
        assert!(failure.len() <= 160);
        assert!(failure.ends_with("..."));
    }
}
