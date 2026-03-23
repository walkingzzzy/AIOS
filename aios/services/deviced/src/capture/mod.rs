use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use chrono::Utc;
use serde_json::Value;
use uuid::Uuid;

use aios_contracts::{
    DeviceCapabilityDescriptor, DeviceCaptureRecord, DeviceCaptureRequest, DeviceCaptureResponse,
    DeviceCaptureStopRequest, DeviceCaptureStopResponse, DeviceRetentionApplyRequest,
};

use crate::{adapters, approval, config::Config, indicator, retention, taint};

pub mod audio;
pub mod camera;
pub mod input;
pub mod screen;
pub mod ui_tree;

#[derive(Debug, Clone, Default)]
struct StartupRecoverySummary {
    restored_captures: usize,
    interrupted_captures: usize,
    active_indicators: usize,
}

impl StartupRecoverySummary {
    fn notes(&self) -> Vec<String> {
        vec![
            format!("startup_restored_captures={}", self.restored_captures),
            format!("startup_interrupted_captures={}", self.interrupted_captures),
            format!("startup_active_indicators={}", self.active_indicators),
        ]
    }
}

#[derive(Debug, Default)]
pub struct CaptureStore {
    state_path: PathBuf,
    captures: BTreeMap<String, DeviceCaptureRecord>,
    startup_notes: Vec<String>,
}

pub(crate) fn is_active_capture(capture: &DeviceCaptureRecord) -> bool {
    matches!(capture.status.as_str(), "capturing" | "sampled")
}

impl CaptureStore {
    pub fn load(state_path: PathBuf) -> anyhow::Result<Self> {
        if !state_path.exists() {
            return Ok(Self {
                state_path,
                captures: BTreeMap::new(),
                startup_notes: Vec::new(),
            });
        }

        let content = fs::read_to_string(&state_path)?;
        let captures = serde_json::from_str::<BTreeMap<String, DeviceCaptureRecord>>(&content)?;
        Ok(Self {
            state_path,
            captures,
            startup_notes: Vec::new(),
        })
    }

    pub fn load_with_config(config: &Config) -> anyhow::Result<Self> {
        let mut store = Self::load(config.capture_state_path.clone())?;
        store.reconcile_startup(config)?;
        Ok(store)
    }

    fn reconcile_startup(&mut self, config: &Config) -> anyhow::Result<()> {
        let mut summary = StartupRecoverySummary {
            restored_captures: self.captures.len(),
            ..StartupRecoverySummary::default()
        };
        let interrupted_at = Utc::now().to_rfc3339();
        let mut changed = false;

        for record in self.captures.values_mut() {
            if is_active_capture(record) {
                record.status = "interrupted".to_string();
                if record.stopped_at.is_none() {
                    record.stopped_at = Some(interrupted_at.clone());
                }
                if record.stopped_reason.is_none() {
                    record.stopped_reason = Some("startup-reconciliation-interrupted".to_string());
                }
                summary.interrupted_captures += 1;
                changed = true;
            }
        }

        if changed {
            self.persist()?;
        }

        let indicator_state =
            indicator::write_state(&config.indicator_state_path, &self.active_captures())?;
        summary.active_indicators = indicator_state.active.len();
        self.startup_notes = summary.notes();
        Ok(())
    }

    pub fn request(
        &mut self,
        config: &Config,
        request: &DeviceCaptureRequest,
    ) -> anyhow::Result<DeviceCaptureResponse> {
        let available = match request.modality.as_str() {
            "screen" => config.screen_enabled,
            "audio" => config.audio_enabled,
            "input" => config.input_enabled,
            "camera" => config.camera_enabled,
            other => anyhow::bail!("unsupported capture modality: {other}"),
        };

        if !available {
            anyhow::bail!("capture modality is disabled: {}", request.modality);
        }

        let approval = approval::evaluate(config, request);
        if config.approval_mode == "enforced" && approval.approval_required && !approval.approved {
            let details = if approval.notes.is_empty() {
                "session/task not pre-approved".to_string()
            } else {
                approval.notes.join("; ")
            };
            anyhow::bail!(
                "approval required for {} capture ({details})",
                request.modality
            );
        }

        let mut preview = adapters::capture_preview(config, request)?;
        let capture_id = format!("cap-{}", Uuid::new_v4());
        let retention = retention::apply(&DeviceRetentionApplyRequest {
            object_kind: preview
                .preview_object_kind
                .clone()
                .unwrap_or_else(|| "device_object".to_string()),
            object_id: capture_id.clone(),
            retention_class: None,
            continuous: request.continuous,
            contains_sensitive_data: preview.contains_sensitive_data || approval.high_risk,
        });
        if let Some(preview_object) = preview.preview_object.as_mut() {
            if let Some(object) = preview_object.as_object_mut() {
                object.insert(
                    "adapter_notes".to_string(),
                    serde_json::json!(preview.notes.clone()),
                );
                object.insert(
                    "approval_notes".to_string(),
                    serde_json::json!(approval.notes.clone()),
                );
                object.insert(
                    "retention_notes".to_string(),
                    serde_json::json!(retention.notes.clone()),
                );
                object.insert(
                    "approval_context".to_string(),
                    serde_json::json!({
                        "approval_required": approval.approval_required,
                        "approved": approval.approved,
                        "approval_status": approval.approval_status.clone(),
                        "approval_source": approval.approval_source.clone(),
                        "approval_ref": approval.approval_ref.clone(),
                        "high_risk": approval.high_risk,
                        "visible_indicator": approval.visible_indicator,
                    }),
                );
                object.insert(
                    "retention_context".to_string(),
                    serde_json::json!({
                        "retention_class": retention.retention_class.clone(),
                        "expires_in_seconds": retention.expires_in_seconds,
                    }),
                );
            }
        }
        let indicator_id = if approval.visible_indicator {
            Some(format!("indicator-{capture_id}"))
        } else {
            None
        };
        let adapter_id = preview_string_field(preview.preview_object.as_ref(), "adapter_id");
        let adapter_execution_path =
            preview_string_field(preview.preview_object.as_ref(), "adapter_execution_path");
        let approval_source = Some(approval.approval_source.clone());
        let approval_ref = approval.approval_ref.clone();

        let record = DeviceCaptureRecord {
            capture_id: capture_id.clone(),
            modality: request.modality.clone(),
            status: if request.continuous {
                "capturing".to_string()
            } else {
                "sampled".to_string()
            },
            continuous: request.continuous,
            started_at: Utc::now().to_rfc3339(),
            stopped_at: None,
            stopped_reason: None,
            session_id: request.session_id.clone(),
            task_id: request.task_id.clone(),
            taint_summary: taint::summarize(&request.modality, true, request.continuous),
            tainted: approval.high_risk,
            source_backend: preview.source_backend,
            preview_object_kind: preview.preview_object_kind,
            adapter_id,
            adapter_execution_path,
            approval_required: approval.approval_required,
            approval_status: Some(approval.approval_status),
            approval_source,
            approval_ref,
            indicator_id,
            retention_class: Some(retention.retention_class),
            retention_ttl_seconds: Some(retention.expires_in_seconds),
        };

        self.captures
            .insert(record.capture_id.clone(), record.clone());
        self.persist()?;
        indicator::write_state(&config.indicator_state_path, &self.active_captures())?;

        Ok(DeviceCaptureResponse {
            capture: record,
            preview_object: preview.preview_object,
        })
    }

    pub fn stop(
        &mut self,
        config: &Config,
        request: &DeviceCaptureStopRequest,
    ) -> anyhow::Result<DeviceCaptureStopResponse> {
        let capture = self.captures.get_mut(&request.capture_id).map(|record| {
            record.status = "stopped".to_string();
            record.stopped_at = Some(Utc::now().to_rfc3339());
            record.stopped_reason = Some(
                request
                    .reason
                    .clone()
                    .unwrap_or_else(|| "unspecified-stop".to_string()),
            );
            record.clone()
        });

        self.persist()?;
        indicator::write_state(&config.indicator_state_path, &self.active_captures())?;

        Ok(DeviceCaptureStopResponse { capture })
    }

    pub fn active_captures(&self) -> Vec<DeviceCaptureRecord> {
        self.captures
            .values()
            .filter(|record| is_active_capture(record))
            .cloned()
            .collect()
    }

    pub fn startup_notes(&self) -> &[String] {
        &self.startup_notes
    }

    pub fn state_path(&self) -> &Path {
        &self.state_path
    }

    fn persist(&self) -> anyhow::Result<()> {
        if let Some(parent) = self.state_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&self.state_path, serde_json::to_vec_pretty(&self.captures)?)?;
        Ok(())
    }
}

fn preview_string_field(preview: Option<&Value>, key: &str) -> Option<String> {
    preview
        .and_then(Value::as_object)
        .and_then(|object| object.get(key))
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}

pub fn capabilities(config: &Config) -> Vec<DeviceCapabilityDescriptor> {
    let mut capabilities = vec![
        screen::capability(config),
        audio::capability(config),
        input::capability(config),
        camera::capability(config),
    ];
    if config.ui_tree_supported {
        capabilities.push(ui_tree::capability(config));
    }
    for capability in &mut capabilities {
        adapters::extend_capability_notes(config, capability);
    }
    capabilities
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    fn config() -> Config {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        let unique = TEST_COUNTER.fetch_add(1, Ordering::Relaxed);
        let state_root = std::env::temp_dir().join(format!("aios-deviced-test-{stamp}-{unique}"));
        Config {
            service_id: "aios-deviced".to_string(),
            version: "0.1.0".to_string(),
            paths: aios_core::ServicePaths::from_service_name("deviced-test"),
            capture_state_path: state_root.join("captures.json"),
            observability_log_path: state_root.join("observability.jsonl"),
            indicator_state_path: state_root.join("indicator-state.json"),
            backend_state_path: state_root.join("backend-state.json"),
            backend_evidence_dir: state_root.join("backend-evidence"),
            continuous_capture_state_path: state_root.join("continuous-captures.json"),
            policy_socket_path: state_root.join("policyd.sock"),
            approval_rpc_timeout_ms: 500,
            screen_backend: "screen-capture-portal".to_string(),
            audio_backend: "pipewire".to_string(),
            input_backend: "libinput".to_string(),
            camera_backend: "pipewire-camera".to_string(),
            screen_enabled: true,
            audio_enabled: true,
            input_enabled: true,
            camera_enabled: false,
            ui_tree_supported: false,
            pipewire_socket_path: state_root.join("pipewire-0"),
            input_device_root: state_root.join("input"),
            camera_device_root: state_root.join("camera"),
            screencast_state_path: state_root.join("screencast-state.json"),
            pipewire_node_path: state_root.join("pipewire-node.json"),
            ui_tree_state_path: state_root.join("ui-tree-state.json"),
            default_resolution: "1920x1080".to_string(),
            approval_mode: "metadata-only".to_string(),
            approved_sessions: vec!["session-1".to_string()],
            approved_tasks: Vec::new(),
            screen_capture_command: None,
            audio_capture_command: None,
            input_capture_command: None,
            camera_capture_command: None,
            ui_tree_command: None,
            screen_probe_command: None,
            audio_probe_command: None,
            input_probe_command: None,
            camera_probe_command: None,
            ui_tree_probe_command: None,
            screen_live_command: None,
            audio_live_command: None,
            input_live_command: None,
            camera_live_command: None,
            ui_tree_live_command: None,
            continuous_capture_interval_ms: 500,
        }
    }

    #[test]
    fn capabilities_include_ui_tree_when_supported() {
        let mut config = config();
        config.ui_tree_supported = true;
        if let Some(parent) = config.ui_tree_state_path.parent() {
            fs::create_dir_all(parent).expect("create ui_tree state dir");
        }
        fs::write(&config.ui_tree_state_path, b"{}").expect("write ui_tree state file");

        let capabilities = capabilities(&config);
        let ui_tree = capabilities
            .iter()
            .find(|item| item.modality == "ui_tree")
            .expect("ui_tree capability");
        assert!(ui_tree.available);
        assert!(ui_tree.conditional);
        assert_eq!(ui_tree.source_backend, "at-spi");
        assert!(ui_tree
            .notes
            .iter()
            .any(|note| note == "adapter_id=ui_tree.atspi-state-file"));
        assert!(ui_tree
            .notes
            .iter()
            .any(|note| note == "adapter_execution_path=native-state-bridge"));

        if let Some(parent) = config.capture_state_path.parent() {
            fs::remove_dir_all(parent).ok();
        }
    }

    #[test]
    fn request_screen_capture_returns_preview() {
        let config = config();
        let mut store =
            CaptureStore::load(config.capture_state_path.clone()).expect("load capture store");
        let response = store
            .request(
                &config,
                &DeviceCaptureRequest {
                    modality: "screen".to_string(),
                    session_id: Some("session-1".to_string()),
                    task_id: None,
                    continuous: false,
                    window_ref: Some("window-1".to_string()),
                    source_device: None,
                },
            )
            .expect("request screen capture");

        assert_eq!(response.capture.modality, "screen");
        assert_eq!(response.capture.status, "sampled");
        assert_eq!(
            response.capture.approval_status.as_deref(),
            Some("not-required")
        );
        assert_eq!(
            response.capture.approval_source.as_deref(),
            response
                .preview_object
                .as_ref()
                .and_then(|item| item.get("approval_context"))
                .and_then(|item| item.get("approval_source"))
                .and_then(Value::as_str)
        );
        assert_eq!(response.capture.retention_class.as_deref(), Some("session"));
        assert_eq!(
            response.capture.adapter_id.as_deref(),
            response
                .preview_object
                .as_ref()
                .and_then(|item| item.get("adapter_id"))
                .and_then(Value::as_str)
        );
        assert_eq!(
            response.capture.adapter_execution_path.as_deref(),
            response
                .preview_object
                .as_ref()
                .and_then(|item| item.get("adapter_execution_path"))
                .and_then(Value::as_str)
        );
        assert_eq!(
            response
                .preview_object
                .as_ref()
                .and_then(|item| item.get("window_ref"))
                .and_then(Value::as_str),
            Some("window-1")
        );
        assert!(store.state_path().exists());
        assert!(config.indicator_state_path.exists());

        if let Some(parent) = config.capture_state_path.parent() {
            fs::remove_dir_all(parent).ok();
        }
    }

    #[test]
    fn stopping_capture_marks_it_stopped() {
        let config = config();
        let mut store =
            CaptureStore::load(config.capture_state_path.clone()).expect("load capture store");
        let response = store
            .request(
                &config,
                &DeviceCaptureRequest {
                    modality: "audio".to_string(),
                    session_id: Some("session-1".to_string()),
                    task_id: None,
                    continuous: true,
                    window_ref: None,
                    source_device: Some("mic-1".to_string()),
                },
            )
            .expect("request audio capture");

        assert_eq!(
            response.capture.approval_source.as_deref(),
            Some("session-allowlist")
        );
        assert!(response.capture.approval_ref.is_none());

        let stop = store
            .stop(
                &config,
                &DeviceCaptureStopRequest {
                    capture_id: response.capture.capture_id,
                    reason: Some("done".to_string()),
                },
            )
            .expect("stop capture");

        assert_eq!(
            stop.capture.as_ref().map(|item| item.status.as_str()),
            Some("stopped")
        );
        assert_eq!(
            stop.capture
                .as_ref()
                .and_then(|item| item.stopped_reason.as_deref()),
            Some("done")
        );
        assert!(store.active_captures().is_empty());

        if let Some(parent) = config.capture_state_path.parent() {
            fs::remove_dir_all(parent).ok();
        }
    }

    #[test]
    fn capture_store_restores_previous_captures() {
        let config = config();
        let mut store =
            CaptureStore::load(config.capture_state_path.clone()).expect("load capture store");
        let response = store
            .request(
                &config,
                &DeviceCaptureRequest {
                    modality: "screen".to_string(),
                    session_id: None,
                    task_id: None,
                    continuous: false,
                    window_ref: Some("window-restore".to_string()),
                    source_device: None,
                },
            )
            .expect("request screen capture");
        drop(store);

        let restored =
            CaptureStore::load(config.capture_state_path.clone()).expect("reload capture store");
        let restored_capture = restored
            .active_captures()
            .into_iter()
            .find(|item| item.capture_id == response.capture.capture_id)
            .expect("restored capture missing");
        assert_eq!(restored_capture.adapter_id, response.capture.adapter_id);
        assert_eq!(
            restored_capture.adapter_execution_path,
            response.capture.adapter_execution_path
        );
        assert_eq!(
            restored_capture.approval_source,
            response.capture.approval_source
        );
        assert_eq!(restored_capture.approval_ref, response.capture.approval_ref);

        if let Some(parent) = config.capture_state_path.parent() {
            fs::remove_dir_all(parent).ok();
        }
    }

    #[test]
    fn startup_reconciliation_marks_unfinished_captures_interrupted() {
        let config = config();
        let mut store =
            CaptureStore::load(config.capture_state_path.clone()).expect("load capture store");
        let sampled = store
            .request(
                &config,
                &DeviceCaptureRequest {
                    modality: "screen".to_string(),
                    session_id: Some("session-1".to_string()),
                    task_id: None,
                    continuous: false,
                    window_ref: Some("window-startup".to_string()),
                    source_device: None,
                },
            )
            .expect("request sampled capture");
        let continuous = store
            .request(
                &config,
                &DeviceCaptureRequest {
                    modality: "audio".to_string(),
                    session_id: Some("session-1".to_string()),
                    task_id: None,
                    continuous: true,
                    window_ref: None,
                    source_device: Some("mic-startup".to_string()),
                },
            )
            .expect("request continuous capture");
        drop(store);

        let recovered = CaptureStore::load_with_config(&config).expect("reconcile startup state");
        assert!(recovered.active_captures().is_empty());
        assert_eq!(
            recovered
                .captures
                .get(&sampled.capture.capture_id)
                .map(|item| item.status.as_str()),
            Some("interrupted")
        );
        assert_eq!(
            recovered
                .captures
                .get(&continuous.capture.capture_id)
                .map(|item| item.status.as_str()),
            Some("interrupted")
        );
        assert!(recovered
            .captures
            .get(&continuous.capture.capture_id)
            .and_then(|item| item.stopped_at.as_ref())
            .is_some());
        assert_eq!(
            recovered
                .captures
                .get(&continuous.capture.capture_id)
                .and_then(|item| item.stopped_reason.as_deref()),
            Some("startup-reconciliation-interrupted")
        );
        assert_eq!(
            recovered
                .captures
                .get(&continuous.capture.capture_id)
                .and_then(|item| item.adapter_id.as_deref()),
            continuous.capture.adapter_id.as_deref()
        );
        assert_eq!(
            recovered
                .captures
                .get(&continuous.capture.capture_id)
                .and_then(|item| item.approval_source.as_deref()),
            continuous.capture.approval_source.as_deref()
        );
        assert!(recovered
            .startup_notes()
            .iter()
            .any(|note| note == "startup_interrupted_captures=2"));
        let indicator_state = serde_json::from_str::<Value>(
            &fs::read_to_string(&config.indicator_state_path).expect("read indicator state"),
        )
        .expect("parse indicator state");
        assert_eq!(indicator_state["active"].as_array().map(Vec::len), Some(0));

        if let Some(parent) = config.capture_state_path.parent() {
            fs::remove_dir_all(parent).ok();
        }
    }
}
