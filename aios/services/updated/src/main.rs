mod boot;
mod config;
mod deployment;
mod diagnostics;
mod health;
mod observability;
mod recovery_ui;
mod rollback;
mod rpc;
mod sysupdate;

use chrono::{DateTime, Utc};

use aios_contracts::HealthResponse;
use deployment::{DeploymentStore, DeploymentStoreConfig};
use observability::ObservabilitySink;

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub started_at: DateTime<Utc>,
    pub deployment: DeploymentStore,
    pub observability: ObservabilitySink,
}

impl AppState {
    fn health(&self) -> HealthResponse {
        let mut status = if self.config.sysupdate_dir.exists() {
            "ready".to_string()
        } else {
            "degraded".to_string()
        };
        let mut notes = vec![
            format!(
                "deployment_state={}",
                self.config.deployment_state_path.display()
            ),
            format!("sysupdate_dir={}", self.config.sysupdate_dir.display()),
            format!(
                "observability_log={}",
                self.config.observability_log_path.display()
            ),
            format!("diagnostics_dir={}", self.config.diagnostics_dir.display()),
            format!("recovery_dir={}", self.config.recovery_dir.display()),
            format!(
                "health_probe_path={}",
                self.config.health_probe_path.display()
            ),
            format!(
                "recovery_surface_path={}",
                self.config.recovery_surface_path.display()
            ),
            format!("boot_state_path={}", self.config.boot_state_path.display()),
            format!("boot_backend={}", self.config.boot_backend),
            format!("bootctl_binary={}", self.config.bootctl_binary),
            format!("firmwarectl_binary={}", self.config.firmwarectl_binary),
            format!(
                "boot_cmdline_path={}",
                self.config.boot_cmdline_path.display()
            ),
            format!(
                "boot_entry_state_dir={}",
                self.config.boot_entry_state_dir.display()
            ),
            format!(
                "boot_success_marker_path={}",
                self.config.boot_success_marker_path.display()
            ),
            format!("sysupdate_binary={}", self.config.sysupdate_binary),
            format!(
                "sysupdate_definitions_dir={}",
                self.config.sysupdate_definitions_dir.display()
            ),
            format!(
                "sysupdate_component={}",
                self.config
                    .sysupdate_component
                    .as_deref()
                    .unwrap_or("<none>")
            ),
            format!(
                "sysupdate_root={}",
                self.config
                    .sysupdate_root
                    .as_ref()
                    .map(|path| path.display().to_string())
                    .unwrap_or_else(|| "<none>".to_string())
            ),
            format!("current_slot={}", self.config.current_slot),
            format!(
                "platform_profile_path={}",
                self.config
                    .platform_profile_path
                    .as_ref()
                    .map(|path| path.display().to_string())
                    .unwrap_or_else(|| "<none>".to_string())
            ),
            format!(
                "platform_profile_id={}",
                self.config
                    .platform_profile_id
                    .as_deref()
                    .unwrap_or("<none>")
            ),
            format!(
                "failure_injection_stage={}",
                self.config
                    .failure_injection_stage
                    .as_deref()
                    .unwrap_or("<none>")
            ),
            format!(
                "failure_injection_reason={}",
                self.config
                    .failure_injection_reason
                    .as_deref()
                    .unwrap_or("<none>")
            ),
            format!(
                "health_probe_command_configured={}",
                self.config.health_probe_command.is_some()
            ),
            format!(
                "sysupdate_check_command_configured={}",
                self.config.sysupdate_check_command.is_some()
            ),
            format!(
                "sysupdate_apply_command_configured={}",
                self.config.sysupdate_apply_command.is_some()
            ),
            format!(
                "rollback_command_configured={}",
                self.config.rollback_command.is_some()
            ),
            format!(
                "boot_slot_command_configured={}",
                self.config.boot_slot_command.is_some()
            ),
            format!(
                "boot_switch_command_configured={}",
                self.config.boot_switch_command.is_some()
            ),
            format!(
                "boot_success_command_configured={}",
                self.config.boot_success_command.is_some()
            ),
        ];

        if let Ok(snapshot) = self.deployment.snapshot() {
            notes.push(format!("update_status={}", snapshot.status));
            if let Some(last_check_at) = snapshot.last_check_at {
                notes.push(format!("last_check_at={last_check_at}"));
            }
        }

        if let Ok(boot_state) = self.deployment.boot_state() {
            notes.push(format!("boot_current_slot={}", boot_state.current_slot));
            notes.push(format!("boot_last_good_slot={}", boot_state.last_good_slot));
            notes.push(format!("boot_success={}", boot_state.boot_success));
            if let Some(staged_slot) = boot_state.staged_slot {
                notes.push(format!("boot_staged_slot={staged_slot}"));
            }
        }

        if let Ok(Some(snapshot)) = crate::health::load_probe(&self.config.health_probe_path) {
            let probe_status = service_status_from_probe(&snapshot.overall_status);
            if service_status_rank(probe_status) > service_status_rank(&status) {
                status = probe_status.to_string();
            }
            notes.push(format!("probe_overall_status={}", snapshot.overall_status));
            if let Some(checked_at) = snapshot.checked_at {
                notes.push(format!("probe_checked_at={checked_at}"));
            }
            if let Some(summary) = snapshot.summary {
                notes.push(format!("probe_summary={summary}"));
            }
        }

        HealthResponse {
            service_id: self.config.service_id.clone(),
            status,
            version: self.config.version.clone(),
            started_at: self.started_at.to_rfc3339(),
            socket_path: self.config.paths.socket_path.display().to_string(),
            notes,
        }
    }
}

fn sync_startup_artifacts(state: &AppState) {
    if let Err(error) = crate::health::refresh_probe(
        &state.deployment,
        state.config.health_probe_command.as_deref(),
        &state.config.health_probe_path,
    ) {
        tracing::warn!(error = %error, "failed to refresh health probe during startup sync");
    }

    if let Err(error) = crate::recovery_ui::write_surface(
        &state.deployment,
        &state.config.health_probe_path,
        &state.config.recovery_surface_path,
    ) {
        tracing::warn!(error = %error, "failed to write recovery surface during startup sync");
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("updated");

    let config = config::Config::load().await?;
    let observability = ObservabilitySink::new(config.observability_log_path.clone())?;
    let deployment = DeploymentStore::new(DeploymentStoreConfig {
        service_id: config.service_id.clone(),
        state_path: config.deployment_state_path.clone(),
        sysupdate_dir: config.sysupdate_dir.clone(),
        sysupdate_definitions_dir: config.sysupdate_definitions_dir.clone(),
        sysupdate_root: config.sysupdate_root.clone(),
        sysupdate_component: config.sysupdate_component.clone(),
        sysupdate_extra_args: config.sysupdate_extra_args.clone(),
        diagnostics_dir: config.diagnostics_dir.clone(),
        recovery_dir: config.recovery_dir.clone(),
        boot_state_path: config.boot_state_path.clone(),
        sysupdate_binary: config.sysupdate_binary.clone(),
        boot_current_slot: config.current_slot.clone(),
        boot_backend: config.boot_backend.clone(),
        bootctl_binary: config.bootctl_binary.clone(),
        firmwarectl_binary: config.firmwarectl_binary.clone(),
        boot_cmdline_path: config.boot_cmdline_path.clone(),
        boot_entry_state_dir: config.boot_entry_state_dir.clone(),
        boot_success_marker_path: config.boot_success_marker_path.clone(),
        boot_slot_command: config.boot_slot_command.clone(),
        boot_switch_command: config.boot_switch_command.clone(),
        boot_success_command: config.boot_success_command.clone(),
        update_stack: config.update_stack.clone(),
        current_channel: config.current_channel.clone(),
        current_version: config.current_version.clone(),
        target_version_hint: config.target_version_hint.clone(),
        failure_injection_stage: config.failure_injection_stage.clone(),
        failure_injection_reason: config.failure_injection_reason.clone(),
        sysupdate_check_command: config.sysupdate_check_command.clone(),
        sysupdate_apply_command: config.sysupdate_apply_command.clone(),
        rollback_command: config.rollback_command.clone(),
    })?;

    let state = AppState {
        config: config.clone(),
        started_at: Utc::now(),
        deployment,
        observability,
    };

    sync_startup_artifacts(&state);

    let router = rpc::build_router(state);

    tracing::info!(socket = %config.paths.socket_path.display(), "starting aios-updated");

    tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => result?,
        _ = tokio::signal::ctrl_c() => tracing::info!("received shutdown signal"),
    }

    Ok(())
}

fn service_status_from_probe(status: &str) -> &str {
    match status {
        "healthy" => "ready",
        "warning" => "degraded",
        "failed" | "unhealthy" => "blocked",
        other => other,
    }
}

fn service_status_rank(status: &str) -> u8 {
    match status {
        "ready" => 0,
        "idle" => 1,
        "degraded" => 2,
        "blocked" => 3,
        _ => 1,
    }
}

#[cfg(test)]
mod tests {
    use super::{service_status_from_probe, service_status_rank};

    #[test]
    fn probe_status_maps_to_service_status() {
        assert_eq!(service_status_from_probe("healthy"), "ready");
        assert_eq!(service_status_from_probe("warning"), "degraded");
        assert_eq!(service_status_from_probe("failed"), "blocked");
        assert_eq!(service_status_from_probe("custom"), "custom");
    }

    #[test]
    fn service_status_rank_orders_more_severe_states_higher() {
        assert!(service_status_rank("degraded") > service_status_rank("ready"));
        assert!(service_status_rank("blocked") > service_status_rank("degraded"));
        assert_eq!(service_status_rank("unknown"), service_status_rank("idle"));
    }
}
