mod adapters;
mod approval;
mod backend;
mod capture;
mod config;
mod continuous;
mod indicator;
mod normalize;
mod observability;
mod probe;
mod retention;
mod rpc;
mod taint;

use std::sync::{Arc, Mutex};

use chrono::{DateTime, Utc};

use aios_contracts::HealthResponse;
use observability::ObservabilitySink;

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub started_at: DateTime<Utc>,
    pub capture_store: Arc<Mutex<capture::CaptureStore>>,
    pub continuous_capture_manager: Arc<Mutex<continuous::ContinuousCaptureManager>>,
    pub observability: ObservabilitySink,
}

impl AppState {
    fn health(&self) -> HealthResponse {
        let indicator_count = crate::indicator::read_state(&self.config.indicator_state_path)
            .ok()
            .flatten()
            .map(|state| state.active.len())
            .unwrap_or(0);
        let configured_probes = crate::probe::configured_modalities(&self.config);
        let probe_summary = if configured_probes.is_empty() {
            "none".to_string()
        } else {
            configured_probes.join(",")
        };
        let startup_notes = self
            .capture_store
            .lock()
            .ok()
            .map(|store| store.startup_notes().to_vec())
            .unwrap_or_default();
        let active_continuous_collectors = self
            .continuous_capture_manager
            .lock()
            .ok()
            .map(|manager| manager.active_count())
            .unwrap_or(0);
        let mut notes = vec![
            format!(
                "capture_state_path={}",
                self.config.capture_state_path.display()
            ),
            format!(
                "observability_log={}",
                self.config.observability_log_path.display()
            ),
            format!(
                "indicator_state_path={}",
                self.config.indicator_state_path.display()
            ),
            format!(
                "backend_state_path={}",
                self.config.backend_state_path.display()
            ),
            format!(
                "backend_evidence_dir={}",
                self.config.backend_evidence_dir.display()
            ),
            format!(
                "continuous_capture_state_path={}",
                self.config.continuous_capture_state_path.display()
            ),
            format!("screen_backend={}", self.config.screen_backend),
            format!("audio_backend={}", self.config.audio_backend),
            format!("input_backend={}", self.config.input_backend),
            format!("camera_backend={}", self.config.camera_backend),
            format!("ui_tree_supported={}", self.config.ui_tree_supported),
            format!(
                "pipewire_socket_path={}",
                self.config.pipewire_socket_path.display()
            ),
            format!(
                "input_device_root={}",
                self.config.input_device_root.display()
            ),
            format!(
                "camera_device_root={}",
                self.config.camera_device_root.display()
            ),
            format!(
                "screencast_state_path={}",
                self.config.screencast_state_path.display()
            ),
            format!(
                "pipewire_node_path={}",
                self.config.pipewire_node_path.display()
            ),
            format!(
                "ui_tree_state_path={}",
                self.config.ui_tree_state_path.display()
            ),
            format!(
                "ui_tree_support_matrix_path={}",
                self.config
                    .backend_state_path
                    .parent()
                    .unwrap_or_else(|| std::path::Path::new("."))
                    .join("ui-tree-support-matrix.json")
                    .display()
            ),
            format!("approval_mode={}", self.config.approval_mode),
            format!(
                "policy_socket_path={}",
                self.config.policy_socket_path.display()
            ),
            format!(
                "policy_socket_present={}",
                self.config.policy_socket_path.exists()
            ),
            format!(
                "approval_rpc_timeout_ms={}",
                self.config.approval_rpc_timeout_ms
            ),
            format!(
                "backend_statuses={}",
                crate::backend::collect(&self.config).len()
            ),
            format!(
                "capture_adapters={}",
                crate::adapters::describe(&self.config).len()
            ),
            format!("active_indicators={indicator_count}"),
            format!("active_continuous_collectors={active_continuous_collectors}"),
        ];
        notes.extend(startup_notes);
        notes.extend(vec![
            format!(
                "screen_capture_command_configured={}",
                self.config.screen_capture_command.is_some()
            ),
            format!(
                "audio_capture_command_configured={}",
                self.config.audio_capture_command.is_some()
            ),
            format!(
                "input_capture_command_configured={}",
                self.config.input_capture_command.is_some()
            ),
            format!(
                "camera_capture_command_configured={}",
                self.config.camera_capture_command.is_some()
            ),
            format!(
                "ui_tree_command_configured={}",
                self.config.ui_tree_command.is_some()
            ),
            format!(
                "screen_probe_command_configured={}",
                self.config.screen_probe_command.is_some()
            ),
            format!(
                "screen_live_command_configured={}",
                self.config.screen_live_command.is_some()
            ),
            format!(
                "audio_probe_command_configured={}",
                self.config.audio_probe_command.is_some()
            ),
            format!(
                "audio_live_command_configured={}",
                self.config.audio_live_command.is_some()
            ),
            format!(
                "input_probe_command_configured={}",
                self.config.input_probe_command.is_some()
            ),
            format!(
                "input_live_command_configured={}",
                self.config.input_live_command.is_some()
            ),
            format!(
                "camera_probe_command_configured={}",
                self.config.camera_probe_command.is_some()
            ),
            format!(
                "camera_live_command_configured={}",
                self.config.camera_live_command.is_some()
            ),
            format!(
                "ui_tree_probe_command_configured={}",
                self.config.ui_tree_probe_command.is_some()
            ),
            format!(
                "ui_tree_live_command_configured={}",
                self.config.ui_tree_live_command.is_some()
            ),
            format!("probe_command_count={}", configured_probes.len()),
            format!("probe_commands={probe_summary}"),
        ]);

        HealthResponse {
            service_id: self.config.service_id.clone(),
            status: "ready".to_string(),
            version: self.config.version.clone(),
            started_at: self.started_at.to_rfc3339(),
            socket_path: self.config.paths.socket_path.display().to_string(),
            notes,
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("deviced");

    let config = config::Config::load().await?;
    let observability = ObservabilitySink::new(config.observability_log_path.clone())?;
    backend::write_snapshot(&config.backend_state_path, &config)?;
    let continuous_capture_manager = Arc::new(Mutex::new(
        continuous::ContinuousCaptureManager::new(&config)?,
    ));
    let state = AppState {
        config: config.clone(),
        started_at: Utc::now(),
        capture_store: Arc::new(Mutex::new(capture::CaptureStore::load_with_config(
            &config,
        )?)),
        continuous_capture_manager,
        observability,
    };

    let router = rpc::build_router(state.clone());

    tracing::info!(socket = %config.paths.socket_path.display(), "starting aios-deviced skeleton");

    tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => result?,
        _ = tokio::signal::ctrl_c() => tracing::info!("received shutdown signal"),
    }

    if let Ok(mut manager) = state.continuous_capture_manager.lock() {
        let _ = manager.shutdown();
    }

    Ok(())
}
