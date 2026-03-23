use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

use anyhow::Context;
use chrono::Utc;
use serde::{Deserialize, Serialize};

use aios_contracts::{
    UpdateApplyRequest, UpdateApplyResponse, UpdateCheckRequest, UpdateCheckResponse,
    UpdateRollbackRequest, UpdateRollbackResponse,
};

use crate::{boot, sysupdate};

fn default_deployment_status() -> String {
    "idle".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeploymentState {
    pub service_id: String,
    pub update_stack: String,
    pub current_channel: String,
    pub current_version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub next_version: Option<String>,
    #[serde(default = "default_deployment_status")]
    pub status: String,
    #[serde(default)]
    pub rollback_ready: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_check_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub active_recovery_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pending_action: Option<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RecoveryPointRecord {
    recovery_id: String,
    created_at: String,
    current_version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    target_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    boot_slot_before: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    boot_slot_after: Option<String>,
    status: String,
}

#[derive(Debug, Clone)]
pub struct DeploymentStoreConfig {
    pub service_id: String,
    pub state_path: PathBuf,
    pub sysupdate_dir: PathBuf,
    pub sysupdate_definitions_dir: PathBuf,
    pub sysupdate_root: Option<PathBuf>,
    pub sysupdate_component: Option<String>,
    pub sysupdate_extra_args: Vec<String>,
    pub diagnostics_dir: PathBuf,
    pub recovery_dir: PathBuf,
    pub boot_state_path: PathBuf,
    pub sysupdate_binary: String,
    pub boot_current_slot: String,
    pub boot_backend: String,
    pub bootctl_binary: String,
    pub firmwarectl_binary: String,
    pub boot_cmdline_path: PathBuf,
    pub boot_entry_state_dir: PathBuf,
    pub boot_success_marker_path: PathBuf,
    pub boot_slot_command: Option<String>,
    pub boot_switch_command: Option<String>,
    pub boot_success_command: Option<String>,
    pub update_stack: String,
    pub current_channel: String,
    pub current_version: String,
    pub target_version_hint: Option<String>,
    pub failure_injection_stage: Option<String>,
    pub failure_injection_reason: Option<String>,
    pub sysupdate_check_command: Option<String>,
    pub sysupdate_apply_command: Option<String>,
    pub rollback_command: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct FailureInjectionRecord {
    schema_version: String,
    service_id: String,
    operation: String,
    stage: String,
    reason: String,
    triggered_at: String,
    deployment_status: String,
    current_version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    target_version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    rollback_target: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    recovery_id: Option<String>,
    boot_backend: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    boot_current_slot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    boot_last_good_slot: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    notes: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct DeploymentStore {
    config: DeploymentStoreConfig,
}

impl DeploymentStore {
    pub fn new(config: DeploymentStoreConfig) -> anyhow::Result<Self> {
        if let Some(parent) = config.state_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::create_dir_all(&config.diagnostics_dir)?;
        fs::create_dir_all(&config.recovery_dir)?;

        Ok(Self { config })
    }

    pub fn snapshot(&self) -> anyhow::Result<DeploymentState> {
        if !self.config.state_path.exists() {
            return Ok(self.default_state());
        }

        let content = fs::read_to_string(&self.config.state_path).with_context(|| {
            format!(
                "failed to read deployment state {}",
                self.config.state_path.display()
            )
        })?;

        serde_json::from_str(&content).with_context(|| {
            format!(
                "invalid deployment state {}",
                self.config.state_path.display()
            )
        })
    }

    pub fn boot_state(&self) -> anyhow::Result<boot::BootState> {
        self.boot_control().snapshot()
    }

    pub fn refresh_boot_state(&self) -> anyhow::Result<boot::BootState> {
        self.boot_control().refresh(
            self.config.boot_slot_command.as_deref(),
            self.config.boot_success_command.as_deref(),
        )
    }

    pub fn verify_boot_state(&self, healthy: bool) -> anyhow::Result<boot::BootState> {
        self.boot_control().verify_boot(
            self.config.boot_slot_command.as_deref(),
            self.config.boot_success_command.as_deref(),
            healthy,
        )
    }

    pub fn reconcile_post_boot(
        &self,
        healthy: bool,
    ) -> anyhow::Result<(DeploymentState, boot::BootState)> {
        let boot_state = self.verify_boot_state(healthy)?;
        let mut state = self.snapshot()?;
        let mut changed = false;
        let mut notes = state.notes.clone();

        if healthy
            && boot_state.staged_slot.is_none()
            && boot_state.current_slot == boot_state.last_good_slot
        {
            match state.pending_action.as_deref() {
                Some("apply")
                    if matches!(state.status.as_str(), "apply-triggered" | "staged-update") =>
                {
                    let next_version = state
                        .active_recovery_id
                        .as_deref()
                        .and_then(|recovery_id| {
                            self.recovery_point(recovery_id)
                                .ok()
                                .flatten()
                                .and_then(|record| record.target_version)
                        })
                        .or_else(|| state.next_version.clone());
                    if let Some(next_version) = next_version {
                        state.current_version = next_version;
                    }
                    if let Some(recovery_id) = state.active_recovery_id.as_deref() {
                        self.update_recovery_point_status(recovery_id, "verified")?;
                        notes.push(format!("recovery_point_verified={recovery_id}"));
                    }
                    state.next_version = None;
                    state.status = "up-to-date".to_string();
                    state.pending_action = None;
                    state.active_recovery_id = None;
                    state.last_check_at = Some(Utc::now().to_rfc3339());
                    notes.push(format!("boot_reconciled=apply:{}", boot_state.current_slot));
                    changed = true;
                }
                Some("rollback")
                    if matches!(
                        state.status.as_str(),
                        "rollback-triggered" | "rollback-staged"
                    ) =>
                {
                    let restored_version =
                        state.active_recovery_id.as_deref().and_then(|recovery_id| {
                            self.recovery_point(recovery_id)
                                .ok()
                                .flatten()
                                .map(|record| record.current_version)
                        });
                    if let Some(restored_version) = restored_version {
                        state.current_version = restored_version;
                    }
                    if let Some(recovery_id) = state.active_recovery_id.as_deref() {
                        self.update_recovery_point_status(recovery_id, "rolled-back")?;
                        notes.push(format!("recovery_point_rolled_back={recovery_id}"));
                    }
                    state.next_version = None;
                    state.status = "up-to-date".to_string();
                    state.pending_action = None;
                    state.active_recovery_id = None;
                    state.last_check_at = Some(Utc::now().to_rfc3339());
                    notes.push(format!(
                        "boot_reconciled=rollback:{}",
                        boot_state.current_slot
                    ));
                    changed = true;
                }
                _ => {}
            }
        }

        if changed {
            state.notes = notes;
            self.persist(&state)?;
        }

        Ok((state, boot_state))
    }

    fn boot_control(&self) -> boot::BootControl {
        boot::BootControl::new(
            self.config.boot_state_path.clone(),
            self.config.boot_current_slot.clone(),
            self.config.current_version.clone(),
            boot::BootBackendConfig {
                backend: self.config.boot_backend.clone(),
                bootctl_binary: self.config.bootctl_binary.clone(),
                firmwarectl_binary: self.config.firmwarectl_binary.clone(),
                cmdline_path: self.config.boot_cmdline_path.clone(),
                entry_state_dir: self.config.boot_entry_state_dir.clone(),
                success_marker_path: self.config.boot_success_marker_path.clone(),
            },
        )
    }

    fn sysupdate_backend(&self) -> sysupdate::BackendConfig {
        sysupdate::BackendConfig {
            binary: self.config.sysupdate_binary.clone(),
            definitions_dir: self.config.sysupdate_definitions_dir.clone(),
            root: self.config.sysupdate_root.clone(),
            component: self.config.sysupdate_component.clone(),
            extra_args: self.config.sysupdate_extra_args.clone(),
        }
    }

    pub fn command_environment(
        &self,
        state: &DeploymentState,
        operation: &str,
    ) -> Vec<(String, String)> {
        let mut environment = vec![
            ("AIOS_UPDATED_OPERATION".to_string(), operation.to_string()),
            (
                "AIOS_UPDATED_SERVICE_ID".to_string(),
                self.config.service_id.clone(),
            ),
            (
                "AIOS_UPDATED_DEPLOYMENT_STATE_PATH".to_string(),
                self.config.state_path.display().to_string(),
            ),
            (
                "AIOS_UPDATED_SYSUPDATE_DIR".to_string(),
                self.config.sysupdate_dir.display().to_string(),
            ),
            (
                "AIOS_UPDATED_DIAGNOSTICS_DIR".to_string(),
                self.config.diagnostics_dir.display().to_string(),
            ),
            (
                "AIOS_UPDATED_RECOVERY_DIR".to_string(),
                self.config.recovery_dir.display().to_string(),
            ),
            (
                "AIOS_UPDATED_BOOT_STATE_PATH".to_string(),
                self.config.boot_state_path.display().to_string(),
            ),
            (
                "AIOS_UPDATED_BOOT_BACKEND".to_string(),
                self.config.boot_backend.clone(),
            ),
            (
                "AIOS_UPDATED_BOOTCTL_BIN".to_string(),
                self.config.bootctl_binary.clone(),
            ),
            (
                "AIOS_UPDATED_FIRMWARECTL_BIN".to_string(),
                self.config.firmwarectl_binary.clone(),
            ),
            (
                "AIOS_UPDATED_SYSUPDATE_DEFINITIONS_DIR".to_string(),
                self.config.sysupdate_definitions_dir.display().to_string(),
            ),
            (
                "AIOS_UPDATED_BOOT_CMDLINE_PATH".to_string(),
                self.config.boot_cmdline_path.display().to_string(),
            ),
            (
                "AIOS_UPDATED_BOOT_ENTRY_STATE_DIR".to_string(),
                self.config.boot_entry_state_dir.display().to_string(),
            ),
            (
                "AIOS_UPDATED_BOOT_SUCCESS_MARKER_PATH".to_string(),
                self.config.boot_success_marker_path.display().to_string(),
            ),
            (
                "AIOS_UPDATED_UPDATE_STACK".to_string(),
                state.update_stack.clone(),
            ),
            (
                "AIOS_UPDATED_CURRENT_CHANNEL".to_string(),
                state.current_channel.clone(),
            ),
            (
                "AIOS_UPDATED_CURRENT_VERSION".to_string(),
                state.current_version.clone(),
            ),
            (
                "AIOS_UPDATED_DEPLOYMENT_STATUS".to_string(),
                state.status.clone(),
            ),
            (
                "AIOS_UPDATED_ROLLBACK_READY".to_string(),
                state.rollback_ready.to_string(),
            ),
        ];

        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_NEXT_VERSION",
            state.next_version.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_LAST_CHECK_AT",
            state.last_check_at.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_SYSUPDATE_COMPONENT",
            self.config.sysupdate_component.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_SYSROOT",
            self.config
                .sysupdate_root
                .as_ref()
                .map(|path| path.display().to_string())
                .as_deref(),
        );
        if !self.config.sysupdate_extra_args.is_empty() {
            environment.push((
                "AIOS_UPDATED_SYSUPDATE_EXTRA_ARGS".to_string(),
                self.config.sysupdate_extra_args.join(" "),
            ));
        }

        if let Ok(boot_state) = self.boot_state() {
            environment.push((
                "AIOS_UPDATED_CURRENT_SLOT".to_string(),
                boot_state.current_slot.clone(),
            ));
            environment.push((
                "AIOS_UPDATED_LAST_GOOD_SLOT".to_string(),
                boot_state.last_good_slot.clone(),
            ));
            environment.push((
                "AIOS_UPDATED_BOOT_SUCCESS".to_string(),
                boot_state.boot_success.to_string(),
            ));
            push_optional_env(
                &mut environment,
                "AIOS_UPDATED_STAGED_SLOT",
                boot_state.staged_slot.as_deref(),
            );
        }

        environment
    }

    fn check_command_environment(
        &self,
        state: &DeploymentState,
        request: &UpdateCheckRequest,
        artifacts: &[String],
        recovery_points: &[String],
    ) -> Vec<(String, String)> {
        let mut environment = self.command_environment(state, "check");
        environment.push((
            "AIOS_UPDATED_ARTIFACT_COUNT".to_string(),
            artifacts.len().to_string(),
        ));
        environment.push((
            "AIOS_UPDATED_RECOVERY_POINT_COUNT".to_string(),
            recovery_points.len().to_string(),
        ));
        environment.push(("AIOS_UPDATED_ARTIFACTS".to_string(), artifacts.join(",")));
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_REQUEST_CHANNEL",
            request.channel.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_REQUEST_CURRENT_VERSION",
            request.current_version.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_TARGET_VERSION_HINT",
            state.next_version.as_deref(),
        );
        environment
    }

    fn apply_command_environment(
        &self,
        state: &DeploymentState,
        request: &UpdateApplyRequest,
        staged_artifacts: &[String],
        target_version: Option<&str>,
        recovery_id: &str,
    ) -> Vec<(String, String)> {
        let mut environment = self.command_environment(state, "apply");
        environment.push((
            "AIOS_UPDATED_STAGED_ARTIFACT_COUNT".to_string(),
            staged_artifacts.len().to_string(),
        ));
        environment.push((
            "AIOS_UPDATED_STAGED_ARTIFACTS".to_string(),
            staged_artifacts.join(","),
        ));
        environment.push((
            "AIOS_UPDATED_REQUEST_DRY_RUN".to_string(),
            request.dry_run.to_string(),
        ));
        environment.push((
            "AIOS_UPDATED_RECOVERY_ID".to_string(),
            recovery_id.to_string(),
        ));
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_REQUEST_REASON",
            request.reason.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_REQUEST_TARGET_VERSION",
            request.target_version.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_TARGET_VERSION",
            target_version,
        );
        environment
    }

    fn rollback_command_environment(
        &self,
        state: &DeploymentState,
        request: &UpdateRollbackRequest,
        rollback_target: &str,
        recovery_points: &[String],
    ) -> Vec<(String, String)> {
        let mut environment = self.command_environment(state, "rollback");
        environment.push((
            "AIOS_UPDATED_RECOVERY_POINT_COUNT".to_string(),
            recovery_points.len().to_string(),
        ));
        environment.push((
            "AIOS_UPDATED_REQUEST_DRY_RUN".to_string(),
            request.dry_run.to_string(),
        ));
        environment.push((
            "AIOS_UPDATED_ROLLBACK_TARGET".to_string(),
            rollback_target.to_string(),
        ));
        environment.push((
            "AIOS_UPDATED_RECOVERY_POINTS".to_string(),
            recovery_points.join(","),
        ));
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_REQUEST_REASON",
            request.reason.as_deref(),
        );
        push_optional_env(
            &mut environment,
            "AIOS_UPDATED_REQUEST_RECOVERY_ID",
            request.recovery_id.as_deref(),
        );
        environment
    }

    fn failure_injection_matches(&self, stage: &str) -> bool {
        self.config
            .failure_injection_stage
            .as_deref()
            .map(|configured| {
                configured
                    .split(',')
                    .map(str::trim)
                    .filter(|item| !item.is_empty())
                    .any(|item| item == stage)
            })
            .unwrap_or(false)
    }

    fn maybe_inject_failure(
        &self,
        state: &mut DeploymentState,
        stage: &str,
        operation: &str,
        failure_status: &str,
        notes: &mut Vec<String>,
        recovery_id: Option<&str>,
        target_version: Option<&str>,
        rollback_target: Option<&str>,
    ) -> anyhow::Result<Option<PathBuf>> {
        if !self.failure_injection_matches(stage) {
            return Ok(None);
        }

        let reason = self
            .config
            .failure_injection_reason
            .clone()
            .unwrap_or_else(|| "simulated failure injection".to_string());
        let triggered_at = Utc::now().to_rfc3339();
        let stage_slug = stage
            .chars()
            .map(|character| {
                if character.is_ascii_alphanumeric() {
                    character
                } else {
                    '-'
                }
            })
            .collect::<String>();
        let artifact_name = format!(
            "failure-injection-{}-{}.json",
            stage_slug.trim_matches('-'),
            Utc::now().timestamp_millis()
        );
        let artifact_path = self.config.diagnostics_dir.join(artifact_name);
        let boot_state = self.boot_state().ok();
        let record = FailureInjectionRecord {
            schema_version: "1.0.0".to_string(),
            service_id: self.config.service_id.clone(),
            operation: operation.to_string(),
            stage: stage.to_string(),
            reason: reason.clone(),
            triggered_at,
            deployment_status: failure_status.to_string(),
            current_version: state.current_version.clone(),
            target_version: target_version.map(ToOwned::to_owned),
            rollback_target: rollback_target.map(ToOwned::to_owned),
            recovery_id: recovery_id.map(ToOwned::to_owned),
            boot_backend: self.config.boot_backend.clone(),
            boot_current_slot: boot_state
                .as_ref()
                .map(|snapshot| snapshot.current_slot.clone()),
            boot_last_good_slot: boot_state
                .as_ref()
                .map(|snapshot| snapshot.last_good_slot.clone()),
            notes: notes.clone(),
        };

        if let Some(parent) = artifact_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&artifact_path, serde_json::to_vec_pretty(&record)?)?;

        notes.push(format!("failure_injection_stage={stage}"));
        notes.push(format!("failure_injection_reason={reason}"));
        notes.push(format!(
            "failure_injection_artifact={}",
            artifact_path.display()
        ));
        state.status = failure_status.to_string();
        state.notes = notes.clone();
        self.persist(state)?;
        Ok(Some(artifact_path))
    }

    pub fn check(&self, request: &UpdateCheckRequest) -> anyhow::Result<UpdateCheckResponse> {
        let mut state = self.snapshot()?;
        if let Some(channel) = &request.channel {
            state.current_channel = channel.clone();
        }
        if let Some(current_version) = &request.current_version {
            state.current_version = current_version.clone();
        }

        state.next_version = self.config.target_version_hint.clone();
        state.last_check_at = Some(Utc::now().to_rfc3339());

        let artifacts = list_named_entries(&self.config.sysupdate_dir)?;
        let recovery_points = list_named_entries(&self.config.recovery_dir)?;

        let mut notes = vec![
            format!("sysupdate_dir={}", self.config.sysupdate_dir.display()),
            format!("recovery_dir={}", self.config.recovery_dir.display()),
        ];

        if let Some(next_version) = &state.next_version {
            notes.push(format!("target_version_hint={next_version}"));
        }

        let command_environment =
            self.check_command_environment(&state, request, &artifacts, &recovery_points);

        let mut check_command_failed = false;
        let mut sysupdate_available = None;
        if let Some(command) = &self.config.sysupdate_check_command {
            let execution = execute_command(command, &command_environment)?;
            notes.extend(execution_notes("sysupdate_check", &execution));
            if !execution.success {
                check_command_failed = true;
                state.status = "sysupdate-check-failed".to_string();
            }
        } else if self.config.update_stack == "systemd-sysupdate" {
            match sysupdate::check(&self.sysupdate_backend(), &command_environment) {
                Ok(sysupdate_check) => {
                    sysupdate_available = sysupdate_check.available;
                    notes.extend(sysupdate_check.notes);
                    if state.next_version.is_none() {
                        state.next_version = sysupdate_check.next_version;
                    }
                }
                Err(error) => {
                    notes.push(format!("systemd_sysupdate_backend_error={error}"));
                    notes.push(
                        "systemd-sysupdate backend unavailable; falling back to directory scan"
                            .to_string(),
                    );
                }
            }
        } else {
            notes.push(
                "sysupdate_check_command not configured; using directory scan only".to_string(),
            );
        }

        if artifacts.is_empty() {
            if sysupdate_available == Some(true) {
                notes.push("systemd-sysupdate reports a pending deployment".to_string());
                if !check_command_failed {
                    state.status = "ready-to-stage".to_string();
                }
            } else if sysupdate_available == Some(false) {
                notes.push("systemd-sysupdate reports no pending deployment".to_string());
                if !check_command_failed {
                    state.status = "up-to-date".to_string();
                }
            } else if self.config.sysupdate_dir.exists() {
                notes.push(
                    "sysupdate directory exists but no transfer entries were found".to_string(),
                );
                if !check_command_failed {
                    state.status = "waiting-for-artifacts".to_string();
                }
            } else {
                notes.push("sysupdate directory does not exist yet".to_string());
                if !check_command_failed {
                    state.status = "missing-sysupdate-dir".to_string();
                }
            }
        } else {
            notes.push(format!("found {} sysupdate entries", artifacts.len()));
            if !check_command_failed {
                state.status = "ready-to-stage".to_string();
            }
        }

        if check_command_failed {
            notes.push("sysupdate check command failed; keeping failure status".to_string());
        }

        if let Ok(boot_state) = self.refresh_boot_state() {
            notes.push(format!("boot_current_slot={}", boot_state.current_slot));
            notes.push(format!("boot_last_good_slot={}", boot_state.last_good_slot));
            notes.push(format!("boot_success={}", boot_state.boot_success));
            if let Some(staged_slot) = boot_state.staged_slot.as_deref() {
                notes.push(format!("boot_staged_slot={staged_slot}"));
            }
            state.rollback_ready = state.rollback_ready
                || !artifacts.is_empty()
                || !recovery_points.is_empty()
                || boot_state.staged_slot.is_some();
        } else {
            state.rollback_ready = !artifacts.is_empty() || !recovery_points.is_empty();
        }
        notes.push(format!("recovery_points={}", recovery_points.len()));
        state.notes = notes.clone();

        self.persist(&state)?;

        Ok(UpdateCheckResponse {
            service_id: self.config.service_id.clone(),
            update_stack: self.config.update_stack.clone(),
            configured_channel: state.current_channel,
            current_version: state.current_version,
            next_version: state.next_version,
            status: state.status,
            artifacts,
            notes,
        })
    }

    pub fn apply(&self, request: &UpdateApplyRequest) -> anyhow::Result<UpdateApplyResponse> {
        let mut state = self.snapshot()?;
        let staged_artifacts = list_named_entries(&self.config.sysupdate_dir)?;
        let target_version = request
            .target_version
            .clone()
            .or_else(|| state.next_version.clone())
            .or_else(|| self.config.target_version_hint.clone());

        let mut notes = vec![
            format!("sysupdate_dir={}", self.config.sysupdate_dir.display()),
            format!("artifact_count={}", staged_artifacts.len()),
        ];
        if let Some(reason) = &request.reason {
            notes.push(format!("reason={reason}"));
        }
        if let Some(target_version) = &target_version {
            notes.push(format!("target_version={target_version}"));
        }

        let allow_systemd_sysupdate = self.config.update_stack == "systemd-sysupdate"
            && self.config.sysupdate_apply_command.is_none();
        let boot_state_before = self.refresh_boot_state().ok();
        if let Some(boot_state) = &boot_state_before {
            notes.push(format!("boot_current_slot={}", boot_state.current_slot));
            notes.push(format!("boot_last_good_slot={}", boot_state.last_good_slot));
        }

        if staged_artifacts.is_empty() && !allow_systemd_sysupdate {
            return Ok(UpdateApplyResponse {
                service_id: self.config.service_id.clone(),
                status: "blocked".to_string(),
                deployment_status: state.status,
                dry_run: request.dry_run,
                target_version,
                recovery_ref: None,
                staged_artifacts,
                notes: {
                    notes.push("no sysupdate artifacts available to stage".to_string());
                    notes
                },
            });
        }

        let recovery_id = format!("recovery-{}", Utc::now().timestamp_millis());
        if request.dry_run {
            notes.push("dry run only; no deployment state mutated".to_string());
            return Ok(UpdateApplyResponse {
                service_id: self.config.service_id.clone(),
                status: "dry-run".to_string(),
                deployment_status: "staged-update".to_string(),
                dry_run: true,
                target_version,
                recovery_ref: Some(recovery_id),
                staged_artifacts,
                notes,
            });
        }

        if self
            .maybe_inject_failure(
                &mut state,
                "apply.preflight",
                "apply",
                "apply-failed",
                &mut notes,
                None,
                target_version.as_deref(),
                None,
            )?
            .is_some()
        {
            return Ok(UpdateApplyResponse {
                service_id: self.config.service_id.clone(),
                status: "failed".to_string(),
                deployment_status: state.status,
                dry_run: false,
                target_version,
                recovery_ref: None,
                staged_artifacts,
                notes,
            });
        }

        let command_environment = self.apply_command_environment(
            &state,
            request,
            &staged_artifacts,
            target_version.as_deref(),
            &recovery_id,
        );

        if let Some(command) = &self.config.sysupdate_apply_command {
            let execution = execute_command(command, &command_environment)?;
            notes.extend(execution_notes("sysupdate_apply", &execution));
            if !execution.success {
                state.status = "apply-failed".to_string();
                state.notes = notes.clone();
                self.persist(&state)?;
                return Ok(UpdateApplyResponse {
                    service_id: self.config.service_id.clone(),
                    status: "failed".to_string(),
                    deployment_status: state.status,
                    dry_run: false,
                    target_version,
                    recovery_ref: None,
                    staged_artifacts,
                    notes,
                });
            }
        } else if allow_systemd_sysupdate {
            match sysupdate::apply(&self.sysupdate_backend(), &command_environment) {
                Ok(sysupdate_apply) => {
                    notes.extend(sysupdate_apply.notes);
                    if !sysupdate_apply.success {
                        state.status = "apply-failed".to_string();
                        state.notes = notes.clone();
                        self.persist(&state)?;
                        return Ok(UpdateApplyResponse {
                            service_id: self.config.service_id.clone(),
                            status: "failed".to_string(),
                            deployment_status: state.status,
                            dry_run: false,
                            target_version,
                            recovery_ref: None,
                            staged_artifacts,
                            notes,
                        });
                    }
                }
                Err(error) => {
                    notes.push(format!("systemd_sysupdate_backend_error={error}"));
                    state.status = "apply-failed".to_string();
                    state.notes = notes.clone();
                    self.persist(&state)?;
                    return Ok(UpdateApplyResponse {
                        service_id: self.config.service_id.clone(),
                        status: "failed".to_string(),
                        deployment_status: state.status,
                        dry_run: false,
                        target_version,
                        recovery_ref: None,
                        staged_artifacts,
                        notes,
                    });
                }
            }
        } else {
            notes.push(
                "sysupdate_apply_command not configured; keeping staged-update state only"
                    .to_string(),
            );
        }

        let staged_boot_state = self
            .boot_control()
            .stage_update(target_version.as_deref())?;
        let now = Utc::now().to_rfc3339();
        let recovery_point = RecoveryPointRecord {
            recovery_id: recovery_id.clone(),
            created_at: now.clone(),
            current_version: state.current_version.clone(),
            target_version: target_version.clone(),
            reason: request.reason.clone(),
            boot_slot_before: boot_state_before
                .as_ref()
                .map(|boot_state| boot_state.current_slot.clone()),
            boot_slot_after: staged_boot_state.staged_slot.clone(),
            status: "created".to_string(),
        };
        let recovery_path = self.config.recovery_dir.join(format!("{recovery_id}.json"));
        if let Some(parent) = recovery_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(recovery_path, serde_json::to_vec_pretty(&recovery_point)?)?;
        notes.push("recovery point recorded before boot switch".to_string());

        if let Some(target_slot) = staged_boot_state.staged_slot.clone() {
            notes.push(format!("boot_staged_slot={target_slot}"));
            if self
                .maybe_inject_failure(
                    &mut state,
                    "apply.boot-switch",
                    "apply",
                    "boot-switch-failed",
                    &mut notes,
                    Some(&recovery_id),
                    target_version.as_deref(),
                    None,
                )?
                .is_some()
            {
                return Ok(UpdateApplyResponse {
                    service_id: self.config.service_id.clone(),
                    status: "failed".to_string(),
                    deployment_status: state.status,
                    dry_run: false,
                    target_version,
                    recovery_ref: Some(recovery_id),
                    staged_artifacts,
                    notes,
                });
            }
            if let Some(command) = &self.config.boot_switch_command {
                let mut boot_switch_environment = command_environment.clone();
                boot_switch_environment
                    .push(("AIOS_UPDATED_TARGET_SLOT".to_string(), target_slot.clone()));
                let execution = execute_command(command, &boot_switch_environment)?;
                notes.extend(execution_notes("boot_switch", &execution));
                if !execution.success {
                    state.status = "boot-switch-failed".to_string();
                    state.notes = notes.clone();
                    self.persist(&state)?;
                    return Ok(UpdateApplyResponse {
                        service_id: self.config.service_id.clone(),
                        status: "failed".to_string(),
                        deployment_status: state.status,
                        dry_run: false,
                        target_version,
                        recovery_ref: Some(recovery_id),
                        staged_artifacts,
                        notes,
                    });
                }
            } else {
                match self.boot_control().switch_slot(&target_slot) {
                    Ok(backend_notes) => notes.extend(backend_notes),
                    Err(error) => {
                        notes.push(format!("boot_switch_error={error}"));
                        state.status = "boot-switch-failed".to_string();
                        state.notes = notes.clone();
                        self.persist(&state)?;
                        return Ok(UpdateApplyResponse {
                            service_id: self.config.service_id.clone(),
                            status: "failed".to_string(),
                            deployment_status: state.status,
                            dry_run: false,
                            target_version,
                            recovery_ref: Some(recovery_id),
                            staged_artifacts,
                            notes,
                        });
                    }
                }
            }
        }

        state.next_version = target_version.clone();
        state.active_recovery_id = Some(recovery_id.clone());
        state.pending_action = Some("apply".to_string());
        state.status = if self.config.sysupdate_apply_command.is_some() || allow_systemd_sysupdate {
            "apply-triggered".to_string()
        } else {
            "staged-update".to_string()
        };
        state.rollback_ready = true;
        state.last_check_at = Some(now);
        state.notes = notes.clone();
        self.persist(&state)?;

        Ok(UpdateApplyResponse {
            service_id: self.config.service_id.clone(),
            status: "accepted".to_string(),
            deployment_status: state.status,
            dry_run: false,
            target_version,
            recovery_ref: Some(recovery_id),
            staged_artifacts,
            notes,
        })
    }

    pub fn rollback(
        &self,
        request: &UpdateRollbackRequest,
    ) -> anyhow::Result<UpdateRollbackResponse> {
        let mut state = self.snapshot()?;
        let recovery_points = self.recovery_points()?;
        let rollback_target = match &request.recovery_id {
            Some(recovery_id) => {
                let expected = format!("{recovery_id}.json");
                if recovery_points.iter().any(|item| item == &expected) {
                    Some(recovery_id.clone())
                } else {
                    anyhow::bail!("unknown recovery point: {recovery_id}")
                }
            }
            None => recovery_points
                .last()
                .map(|item| item.trim_end_matches(".json").to_string()),
        };

        let mut notes = vec![format!("recovery_points={}", recovery_points.len())];
        if let Some(reason) = &request.reason {
            notes.push(format!("reason={reason}"));
        }

        let Some(rollback_target) = rollback_target else {
            notes.push("no recovery point available for rollback".to_string());
            return Ok(UpdateRollbackResponse {
                service_id: self.config.service_id.clone(),
                status: "blocked".to_string(),
                deployment_status: state.status,
                dry_run: request.dry_run,
                rollback_target: None,
                notes,
            });
        };

        let boot_state_before = self.refresh_boot_state().ok();
        if let Some(boot_state) = &boot_state_before {
            notes.push(format!("boot_current_slot={}", boot_state.current_slot));
            notes.push(format!("boot_last_good_slot={}", boot_state.last_good_slot));
        }

        let boot_slot_target = self.recovery_slot_hint(&rollback_target)?.or_else(|| {
            boot_state_before
                .as_ref()
                .map(|boot_state| boot_state.last_good_slot.clone())
        });
        if let Some(boot_slot_target) = &boot_slot_target {
            notes.push(format!("boot_rollback_slot={boot_slot_target}"));
        }

        if request.dry_run {
            notes.push("dry run only; rollback not staged".to_string());
            return Ok(UpdateRollbackResponse {
                service_id: self.config.service_id.clone(),
                status: "dry-run".to_string(),
                deployment_status: "rollback-staged".to_string(),
                dry_run: true,
                rollback_target: Some(rollback_target),
                notes,
            });
        }

        if self
            .maybe_inject_failure(
                &mut state,
                "rollback.preflight",
                "rollback",
                "rollback-failed",
                &mut notes,
                Some(&rollback_target),
                None,
                Some(&rollback_target),
            )?
            .is_some()
        {
            return Ok(UpdateRollbackResponse {
                service_id: self.config.service_id.clone(),
                status: "failed".to_string(),
                deployment_status: state.status,
                dry_run: false,
                rollback_target: Some(rollback_target),
                notes,
            });
        }

        let command_environment =
            self.rollback_command_environment(&state, request, &rollback_target, &recovery_points);

        if let Some(command) = &self.config.rollback_command {
            let execution = execute_command(command, &command_environment)?;
            notes.extend(execution_notes("rollback", &execution));
            if !execution.success {
                state.status = "rollback-failed".to_string();
                state.notes = notes.clone();
                self.persist(&state)?;
                return Ok(UpdateRollbackResponse {
                    service_id: self.config.service_id.clone(),
                    status: "failed".to_string(),
                    deployment_status: state.status,
                    dry_run: false,
                    rollback_target: Some(rollback_target),
                    notes,
                });
            }
        } else {
            notes.push(
                "rollback_command not configured; keeping rollback-staged state only".to_string(),
            );
        }

        let rollback_boot_state = self
            .boot_control()
            .stage_rollback(boot_slot_target.as_deref())?;
        if let Some(target_slot) = rollback_boot_state.staged_slot.clone() {
            if self
                .maybe_inject_failure(
                    &mut state,
                    "rollback.boot-switch",
                    "rollback",
                    "boot-switch-failed",
                    &mut notes,
                    Some(&rollback_target),
                    None,
                    Some(&rollback_target),
                )?
                .is_some()
            {
                return Ok(UpdateRollbackResponse {
                    service_id: self.config.service_id.clone(),
                    status: "failed".to_string(),
                    deployment_status: state.status,
                    dry_run: false,
                    rollback_target: Some(rollback_target),
                    notes,
                });
            }
            if let Some(command) = &self.config.boot_switch_command {
                let mut boot_switch_environment = command_environment.clone();
                boot_switch_environment
                    .push(("AIOS_UPDATED_TARGET_SLOT".to_string(), target_slot.clone()));
                let execution = execute_command(command, &boot_switch_environment)?;
                notes.extend(execution_notes("boot_switch", &execution));
                if !execution.success {
                    state.status = "boot-switch-failed".to_string();
                    state.notes = notes.clone();
                    self.persist(&state)?;
                    return Ok(UpdateRollbackResponse {
                        service_id: self.config.service_id.clone(),
                        status: "failed".to_string(),
                        deployment_status: state.status,
                        dry_run: false,
                        rollback_target: Some(rollback_target),
                        notes,
                    });
                }
            } else {
                match self.boot_control().switch_slot(&target_slot) {
                    Ok(backend_notes) => notes.extend(backend_notes),
                    Err(error) => {
                        notes.push(format!("boot_switch_error={error}"));
                        state.status = "boot-switch-failed".to_string();
                        state.notes = notes.clone();
                        self.persist(&state)?;
                        return Ok(UpdateRollbackResponse {
                            service_id: self.config.service_id.clone(),
                            status: "failed".to_string(),
                            deployment_status: state.status,
                            dry_run: false,
                            rollback_target: Some(rollback_target),
                            notes,
                        });
                    }
                }
            }
        }

        state.status = if self.config.rollback_command.is_some() || boot_slot_target.is_some() {
            "rollback-triggered".to_string()
        } else {
            "rollback-staged".to_string()
        };
        state.active_recovery_id = Some(rollback_target.clone());
        state.pending_action = Some("rollback".to_string());
        state.next_version = None;
        state.rollback_ready = true;
        state.last_check_at = Some(Utc::now().to_rfc3339());
        notes.push(format!("rollback_target={rollback_target}"));
        state.notes = notes.clone();
        self.persist(&state)?;

        Ok(UpdateRollbackResponse {
            service_id: self.config.service_id.clone(),
            status: "accepted".to_string(),
            deployment_status: state.status,
            dry_run: false,
            rollback_target: Some(rollback_target),
            notes,
        })
    }

    pub fn recovery_points(&self) -> anyhow::Result<Vec<String>> {
        list_named_entries(&self.config.recovery_dir)
    }

    pub fn deployment_state_path(&self) -> &Path {
        &self.config.state_path
    }

    pub fn sysupdate_dir(&self) -> &Path {
        &self.config.sysupdate_dir
    }

    pub fn diagnostics_dir(&self) -> &Path {
        &self.config.diagnostics_dir
    }

    pub fn recovery_dir(&self) -> &Path {
        &self.config.recovery_dir
    }

    pub fn service_id(&self) -> &str {
        &self.config.service_id
    }

    fn recovery_slot_hint(&self, recovery_id: &str) -> anyhow::Result<Option<String>> {
        let path = self.config.recovery_dir.join(format!("{recovery_id}.json"));
        if !path.exists() {
            return Ok(None);
        }

        let value = serde_json::from_str::<serde_json::Value>(&fs::read_to_string(&path)?)?;
        Ok(value
            .get("boot_slot_before")
            .and_then(serde_json::Value::as_str)
            .map(ToOwned::to_owned)
            .or_else(|| {
                value
                    .get("boot_slot_after")
                    .and_then(serde_json::Value::as_str)
                    .map(ToOwned::to_owned)
            }))
    }

    fn recovery_point(&self, recovery_id: &str) -> anyhow::Result<Option<RecoveryPointRecord>> {
        let path = self.config.recovery_dir.join(format!("{recovery_id}.json"));
        if !path.exists() {
            return Ok(None);
        }
        let content = fs::read_to_string(&path)?;
        Ok(Some(serde_json::from_str(&content)?))
    }

    fn save_recovery_point(
        &self,
        recovery_id: &str,
        record: &RecoveryPointRecord,
    ) -> anyhow::Result<()> {
        let path = self.config.recovery_dir.join(format!("{recovery_id}.json"));
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, serde_json::to_vec_pretty(record)?)?;
        Ok(())
    }

    fn update_recovery_point_status(&self, recovery_id: &str, status: &str) -> anyhow::Result<()> {
        let Some(mut record) = self.recovery_point(recovery_id)? else {
            return Ok(());
        };
        record.status = status.to_string();
        self.save_recovery_point(recovery_id, &record)
    }

    fn persist(&self, state: &DeploymentState) -> anyhow::Result<()> {
        if let Some(parent) = self.config.state_path.parent() {
            fs::create_dir_all(parent)?;
        }

        fs::write(&self.config.state_path, serde_json::to_vec_pretty(state)?)?;
        Ok(())
    }

    fn default_state(&self) -> DeploymentState {
        DeploymentState {
            service_id: self.config.service_id.clone(),
            update_stack: self.config.update_stack.clone(),
            current_channel: self.config.current_channel.clone(),
            current_version: self.config.current_version.clone(),
            next_version: self.config.target_version_hint.clone(),
            status: default_deployment_status(),
            rollback_ready: false,
            last_check_at: None,
            active_recovery_id: None,
            pending_action: None,
            notes: Vec::new(),
        }
    }
}

fn push_optional_env(environment: &mut Vec<(String, String)>, key: &str, value: Option<&str>) {
    if let Some(value) = value {
        environment.push((key.to_string(), value.to_string()));
    }
}

fn list_named_entries(root: &Path) -> anyhow::Result<Vec<String>> {
    if !root.exists() {
        return Ok(Vec::new());
    }

    let mut names = fs::read_dir(root)?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.file_name().to_string_lossy().to_string())
        .collect::<Vec<_>>();
    names.sort();
    Ok(names)
}

#[derive(Debug, Clone)]
struct CommandExecution {
    command: String,
    environment_keys: Vec<String>,
    success: bool,
    exit_code: Option<i32>,
    stdout: String,
    stderr: String,
}

fn spawn_shell(command: &str) -> Command {
    if cfg!(windows) {
        let mut shell = Command::new("powershell.exe");
        shell
            .arg("-NoProfile")
            .arg("-NonInteractive")
            .arg("-Command")
            .arg(command);
        shell
    } else {
        let mut shell = Command::new("/bin/sh");
        shell.arg("-lc").arg(command);
        shell
    }
}

fn execute_command(
    command: &str,
    environment: &[(String, String)],
) -> anyhow::Result<CommandExecution> {
    let mut shell = spawn_shell(command);
    for (key, value) in environment {
        shell.env(key, value);
    }

    let output = shell.output()?;
    Ok(CommandExecution {
        command: command.to_string(),
        environment_keys: environment.iter().map(|(key, _)| key.clone()).collect(),
        success: output.status.success(),
        exit_code: output.status.code(),
        stdout: String::from_utf8_lossy(&output.stdout).trim().to_string(),
        stderr: String::from_utf8_lossy(&output.stderr).trim().to_string(),
    })
}

fn execution_notes(prefix: &str, execution: &CommandExecution) -> Vec<String> {
    let mut notes = vec![
        format!("{prefix}_command={}", execution.command),
        format!("{prefix}_success={}", execution.success),
        format!("{prefix}_exit_code={:?}", execution.exit_code),
        format!(
            "{prefix}_env_keys={}",
            truncate_note(&execution.environment_keys.join(","))
        ),
    ];

    if !execution.stdout.is_empty() {
        notes.push(format!(
            "{prefix}_stdout={}",
            truncate_note(&execution.stdout)
        ));
    }
    if !execution.stderr.is_empty() {
        notes.push(format!(
            "{prefix}_stderr={}",
            truncate_note(&execution.stderr)
        ));
    }

    notes
}

fn truncate_note(value: &str) -> String {
    const MAX_NOTE_LEN: usize = 160;
    if value.chars().count() <= MAX_NOTE_LEN {
        return value.to_string();
    }

    let truncated = value.chars().take(MAX_NOTE_LEN).collect::<String>();
    format!("{truncated}...")
}

#[cfg(test)]
mod tests {
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::*;

    fn test_root(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("aios-updated-{name}-{stamp}"))
    }

    fn store(root: &Path) -> DeploymentStore {
        DeploymentStore::new(DeploymentStoreConfig {
            service_id: "aios-updated".to_string(),
            state_path: root.join("state").join("deployment-state.json"),
            sysupdate_dir: root.join("sysupdate"),
            sysupdate_definitions_dir: root.join("sysupdate"),
            sysupdate_root: None,
            sysupdate_component: None,
            sysupdate_extra_args: Vec::new(),
            diagnostics_dir: root.join("diagnostics"),
            recovery_dir: root.join("recovery"),
            boot_state_path: root.join("state").join("boot-control.json"),
            sysupdate_binary: "systemd-sysupdate".to_string(),
            boot_current_slot: "a".to_string(),
            boot_backend: "state-file".to_string(),
            bootctl_binary: "bootctl".to_string(),
            firmwarectl_binary: "firmwarectl".to_string(),
            boot_cmdline_path: root.join("state").join("cmdline"),
            boot_entry_state_dir: root.join("state").join("boot"),
            boot_success_marker_path: root.join("state").join("boot-success"),
            boot_slot_command: None,
            boot_switch_command: None,
            boot_success_command: None,
            update_stack: "manual-stage".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            target_version_hint: Some("0.1.1".to_string()),
            failure_injection_stage: None,
            failure_injection_reason: None,
            sysupdate_check_command: None,
            sysupdate_apply_command: None,
            rollback_command: None,
        })
        .expect("create deployment store")
    }

    fn store_with_failure(
        root: &Path,
        stage: Option<&str>,
        reason: Option<&str>,
    ) -> DeploymentStore {
        DeploymentStore::new(DeploymentStoreConfig {
            service_id: "aios-updated".to_string(),
            state_path: root.join("state").join("deployment-state.json"),
            sysupdate_dir: root.join("sysupdate"),
            sysupdate_definitions_dir: root.join("sysupdate"),
            sysupdate_root: None,
            sysupdate_component: None,
            sysupdate_extra_args: Vec::new(),
            diagnostics_dir: root.join("diagnostics"),
            recovery_dir: root.join("recovery"),
            boot_state_path: root.join("state").join("boot-control.json"),
            sysupdate_binary: "systemd-sysupdate".to_string(),
            boot_current_slot: "a".to_string(),
            boot_backend: "state-file".to_string(),
            bootctl_binary: "bootctl".to_string(),
            firmwarectl_binary: "firmwarectl".to_string(),
            boot_cmdline_path: root.join("state").join("cmdline"),
            boot_entry_state_dir: root.join("state").join("boot"),
            boot_success_marker_path: root.join("state").join("boot-success"),
            boot_slot_command: None,
            boot_switch_command: None,
            boot_success_command: None,
            update_stack: "manual-stage".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            target_version_hint: Some("0.1.1".to_string()),
            failure_injection_stage: stage.map(ToOwned::to_owned),
            failure_injection_reason: reason.map(ToOwned::to_owned),
            sysupdate_check_command: None,
            sysupdate_apply_command: None,
            rollback_command: None,
        })
        .expect("create deployment store")
    }

    fn apply_ok_command() -> String {
        if cfg!(windows) {
            "Write-Output 'apply ok'".to_string()
        } else {
            "printf 'apply ok'".to_string()
        }
    }

    fn apply_context_command() -> String {
        if cfg!(windows) {
            r#"Write-Output "$env:AIOS_UPDATED_OPERATION|$env:AIOS_UPDATED_REQUEST_TARGET_VERSION|$env:AIOS_UPDATED_REQUEST_REASON|$env:AIOS_UPDATED_RECOVERY_ID""#
                .to_string()
        } else {
            r#"printf '%s' "$AIOS_UPDATED_OPERATION|$AIOS_UPDATED_REQUEST_TARGET_VERSION|$AIOS_UPDATED_REQUEST_REASON|$AIOS_UPDATED_RECOVERY_ID""#
                .to_string()
        }
    }

    #[test]
    fn update_check_reports_available_sysupdate_entries() {
        let root = test_root("check-ready");
        let store = store(&root);
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer config");

        let response = store
            .check(&UpdateCheckRequest {
                channel: Some("beta".to_string()),
                current_version: Some("1.2.3".to_string()),
            })
            .expect("run update check");

        assert_eq!(response.status, "ready-to-stage");
        assert_eq!(response.configured_channel, "beta");
        assert_eq!(response.current_version, "1.2.3");
        assert!(response
            .artifacts
            .iter()
            .any(|item| item == "00-aios-root.transfer"));

        let snapshot = store.snapshot().expect("read persisted state");
        assert_eq!(snapshot.status, "ready-to-stage");
        assert!(snapshot.rollback_ready);
        assert!(snapshot.last_check_at.is_some());

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn update_check_marks_missing_sysupdate_directory() {
        let root = test_root("check-missing");
        let store = store(&root);

        let response = store
            .check(&UpdateCheckRequest::default())
            .expect("run update check without sysupdate dir");

        assert_eq!(response.status, "missing-sysupdate-dir");
        assert!(response.artifacts.is_empty());
        assert!(response
            .notes
            .iter()
            .any(|item| item.contains("does not exist yet")));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn configured_check_command_failure_preserves_failed_status() {
        let root = test_root("check-command-failure");
        let store = DeploymentStore::new(DeploymentStoreConfig {
            service_id: "aios-updated".to_string(),
            state_path: root.join("state").join("deployment-state.json"),
            sysupdate_dir: root.join("sysupdate"),
            sysupdate_definitions_dir: root.join("sysupdate"),
            sysupdate_root: None,
            sysupdate_component: None,
            sysupdate_extra_args: Vec::new(),
            diagnostics_dir: root.join("diagnostics"),
            recovery_dir: root.join("recovery"),
            boot_state_path: root.join("state").join("boot-control.json"),
            sysupdate_binary: "systemd-sysupdate".to_string(),
            boot_current_slot: "a".to_string(),
            boot_backend: "state-file".to_string(),
            bootctl_binary: "bootctl".to_string(),
            firmwarectl_binary: "firmwarectl".to_string(),
            boot_cmdline_path: root.join("state").join("cmdline"),
            boot_entry_state_dir: root.join("state").join("boot"),
            boot_success_marker_path: root.join("state").join("boot-success"),
            boot_slot_command: None,
            boot_switch_command: None,
            boot_success_command: None,
            update_stack: "systemd-sysupdate".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            target_version_hint: Some("0.1.1".to_string()),
            failure_injection_stage: None,
            failure_injection_reason: None,
            sysupdate_check_command: Some("exit 7".to_string()),
            sysupdate_apply_command: None,
            rollback_command: None,
        })
        .expect("create deployment store");
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer config");

        let response = store
            .check(&UpdateCheckRequest::default())
            .expect("run update check with failing command");

        assert_eq!(response.status, "sysupdate-check-failed");
        assert!(response
            .notes
            .iter()
            .any(|item| item.contains("keeping failure status")));
        assert!(response
            .artifacts
            .iter()
            .any(|item| item == "00-aios-root.transfer"));

        let snapshot = store.snapshot().expect("snapshot");
        assert_eq!(snapshot.status, "sysupdate-check-failed");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn update_apply_records_recovery_point_and_stages_state() {
        let root = test_root("apply");
        let store = store(&root);
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer config");

        let response = store
            .apply(&UpdateApplyRequest {
                target_version: Some("1.0.1".to_string()),
                reason: Some("stage update".to_string()),
                dry_run: false,
            })
            .expect("apply update");

        assert_eq!(response.status, "accepted");
        assert_eq!(response.deployment_status, "staged-update");
        assert!(response.recovery_ref.is_some());
        assert!(store.recovery_points().expect("recovery points").len() == 1);

        let snapshot = store.snapshot().expect("snapshot");
        assert_eq!(snapshot.status, "staged-update");
        assert_eq!(snapshot.next_version.as_deref(), Some("1.0.1"));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn update_rollback_uses_latest_recovery_point() {
        let root = test_root("rollback");
        let store = store(&root);
        fs::create_dir_all(root.join("recovery")).expect("create recovery dir");
        fs::write(root.join("recovery").join("recovery-100.json"), b"{}")
            .expect("write recovery 100");
        fs::write(root.join("recovery").join("recovery-200.json"), b"{}")
            .expect("write recovery 200");

        let response = store
            .rollback(&UpdateRollbackRequest {
                recovery_id: None,
                reason: Some("operator rollback".to_string()),
                dry_run: false,
            })
            .expect("rollback update");

        assert_eq!(response.status, "accepted");
        assert_eq!(response.rollback_target.as_deref(), Some("recovery-200"));
        assert_eq!(response.deployment_status, "rollback-triggered");
        assert!(response
            .notes
            .iter()
            .any(|note| note.starts_with("boot_rollback_slot=")));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn configured_apply_command_receives_request_context() {
        let root = test_root("apply-command-context");
        let store = DeploymentStore::new(DeploymentStoreConfig {
            service_id: "aios-updated".to_string(),
            state_path: root.join("state").join("deployment-state.json"),
            sysupdate_dir: root.join("sysupdate"),
            sysupdate_definitions_dir: root.join("sysupdate"),
            sysupdate_root: None,
            sysupdate_component: None,
            sysupdate_extra_args: Vec::new(),
            diagnostics_dir: root.join("diagnostics"),
            recovery_dir: root.join("recovery"),
            boot_state_path: root.join("state").join("boot-control.json"),
            sysupdate_binary: "systemd-sysupdate".to_string(),
            boot_current_slot: "a".to_string(),
            boot_backend: "state-file".to_string(),
            bootctl_binary: "bootctl".to_string(),
            firmwarectl_binary: "firmwarectl".to_string(),
            boot_cmdline_path: root.join("state").join("cmdline"),
            boot_entry_state_dir: root.join("state").join("boot"),
            boot_success_marker_path: root.join("state").join("boot-success"),
            boot_slot_command: None,
            boot_switch_command: None,
            boot_success_command: None,
            update_stack: "systemd-sysupdate".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            target_version_hint: Some("0.1.1".to_string()),
            failure_injection_stage: None,
            failure_injection_reason: None,
            sysupdate_check_command: None,
            sysupdate_apply_command: Some(apply_context_command()),
            rollback_command: None,
        })
        .expect("create store");
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer file");

        let response = store
            .apply(&UpdateApplyRequest {
                target_version: Some("0.1.1".to_string()),
                reason: Some("stage update".to_string()),
                dry_run: false,
            })
            .expect("apply update");

        let stdout_note = response
            .notes
            .iter()
            .find(|item| item.starts_with("sysupdate_apply_stdout="))
            .expect("stdout note");
        assert!(
            stdout_note.starts_with("sysupdate_apply_stdout=apply|0.1.1|stage update|recovery-")
        );

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn configured_apply_command_moves_status_to_apply_triggered() {
        let root = test_root("apply-command");
        let store = DeploymentStore::new(DeploymentStoreConfig {
            service_id: "aios-updated".to_string(),
            state_path: root.join("state").join("deployment-state.json"),
            sysupdate_dir: root.join("sysupdate"),
            sysupdate_definitions_dir: root.join("sysupdate"),
            sysupdate_root: None,
            sysupdate_component: None,
            sysupdate_extra_args: Vec::new(),
            diagnostics_dir: root.join("diagnostics"),
            recovery_dir: root.join("recovery"),
            boot_state_path: root.join("state").join("boot-control.json"),
            sysupdate_binary: "systemd-sysupdate".to_string(),
            boot_current_slot: "a".to_string(),
            boot_backend: "state-file".to_string(),
            bootctl_binary: "bootctl".to_string(),
            firmwarectl_binary: "firmwarectl".to_string(),
            boot_cmdline_path: root.join("state").join("cmdline"),
            boot_entry_state_dir: root.join("state").join("boot"),
            boot_success_marker_path: root.join("state").join("boot-success"),
            boot_slot_command: None,
            boot_switch_command: None,
            boot_success_command: None,
            update_stack: "systemd-sysupdate".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            target_version_hint: Some("0.1.1".to_string()),
            failure_injection_stage: None,
            failure_injection_reason: None,
            sysupdate_check_command: None,
            sysupdate_apply_command: Some(apply_ok_command()),
            rollback_command: None,
        })
        .expect("create store");
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer file");

        let response = store
            .apply(&UpdateApplyRequest {
                target_version: Some("0.1.1".to_string()),
                reason: None,
                dry_run: false,
            })
            .expect("apply update");

        assert_eq!(response.status, "accepted");
        assert_eq!(response.deployment_status, "apply-triggered");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn apply_failure_injection_writes_artifact_and_keeps_recovery_point() {
        let root = test_root("apply-failure-injection");
        let store = store_with_failure(
            &root,
            Some("apply.boot-switch"),
            Some("simulate vendor hook failure"),
        );
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer file");

        let response = store
            .apply(&UpdateApplyRequest {
                target_version: Some("1.0.1".to_string()),
                reason: Some("inject boot switch failure".to_string()),
                dry_run: false,
            })
            .expect("apply update");

        assert_eq!(response.status, "failed");
        assert_eq!(response.deployment_status, "boot-switch-failed");
        assert!(response.recovery_ref.is_some());
        assert!(response
            .notes
            .iter()
            .any(|note| note == "failure_injection_stage=apply.boot-switch"));

        let artifact_path = response
            .notes
            .iter()
            .find_map(|note| note.strip_prefix("failure_injection_artifact="))
            .map(PathBuf::from)
            .expect("failure artifact path");
        assert!(artifact_path.exists());

        let artifact: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&artifact_path).expect("read artifact"))
                .expect("parse artifact");
        assert_eq!(artifact["stage"], "apply.boot-switch");
        assert_eq!(artifact["reason"], "simulate vendor hook failure");
        assert_eq!(
            artifact["recovery_id"],
            response.recovery_ref.clone().unwrap()
        );

        let snapshot = store.snapshot().expect("snapshot");
        assert_eq!(snapshot.status, "boot-switch-failed");
        assert_eq!(store.recovery_points().expect("recovery points").len(), 1);

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn rollback_failure_injection_writes_artifact() {
        let root = test_root("rollback-failure-injection");
        let store = store_with_failure(
            &root,
            Some("rollback.preflight"),
            Some("simulate rollback preflight failure"),
        );
        fs::create_dir_all(root.join("recovery")).expect("create recovery dir");
        fs::write(root.join("recovery").join("recovery-200.json"), b"{}")
            .expect("write recovery record");

        let response = store
            .rollback(&UpdateRollbackRequest {
                recovery_id: Some("recovery-200".to_string()),
                reason: Some("inject rollback failure".to_string()),
                dry_run: false,
            })
            .expect("rollback update");

        assert_eq!(response.status, "failed");
        assert_eq!(response.deployment_status, "rollback-failed");
        assert_eq!(response.rollback_target.as_deref(), Some("recovery-200"));
        assert!(response
            .notes
            .iter()
            .any(|note| note == "failure_injection_stage=rollback.preflight"));

        let artifact_path = response
            .notes
            .iter()
            .find_map(|note| note.strip_prefix("failure_injection_artifact="))
            .map(PathBuf::from)
            .expect("failure artifact path");
        assert!(artifact_path.exists());

        let artifact: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&artifact_path).expect("read artifact"))
                .expect("parse artifact");
        assert_eq!(artifact["stage"], "rollback.preflight");
        assert_eq!(artifact["rollback_target"], "recovery-200");

        let snapshot = store.snapshot().expect("snapshot");
        assert_eq!(snapshot.status, "rollback-failed");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn reconcile_post_boot_promotes_applied_version() {
        let root = test_root("reconcile-apply");
        let store = store(&root);
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer file");

        let response = store
            .apply(&UpdateApplyRequest {
                target_version: Some("1.0.1".to_string()),
                reason: Some("boot into new slot".to_string()),
                dry_run: false,
            })
            .expect("apply update");
        let recovery_id = response.recovery_ref.expect("recovery id");

        fs::write(
            root.join("state").join("cmdline"),
            b"quiet splash aios.slot=b
",
        )
        .expect("write cmdline");
        fs::write(
            root.join("state").join("boot-success"),
            b"success
",
        )
        .expect("write success marker");

        let (state, boot_state) = store
            .reconcile_post_boot(true)
            .expect("reconcile post boot");
        assert_eq!(boot_state.current_slot, "b");
        assert_eq!(state.status, "up-to-date");
        assert_eq!(state.current_version, "1.0.1");
        assert_eq!(state.next_version, None);
        assert_eq!(state.pending_action, None);
        assert_eq!(state.active_recovery_id, None);
        assert!(state
            .notes
            .iter()
            .any(|note| note.starts_with("recovery_point_verified=")));

        let recovery_record = store
            .recovery_point(&recovery_id)
            .expect("load recovery point")
            .expect("recovery point exists");
        assert_eq!(recovery_record.status, "verified");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn reconcile_post_boot_restores_version_after_rollback() {
        let root = test_root("reconcile-rollback");
        let store = store(&root);
        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(
            root.join("sysupdate").join("00-aios-root.transfer"),
            b"transfer",
        )
        .expect("write transfer file");

        let response = store
            .apply(&UpdateApplyRequest {
                target_version: Some("1.0.1".to_string()),
                reason: Some("boot into new slot".to_string()),
                dry_run: false,
            })
            .expect("apply update");
        let recovery_id = response.recovery_ref.expect("recovery id");

        fs::write(
            root.join("state").join("cmdline"),
            b"quiet splash aios.slot=b
",
        )
        .expect("write cmdline");
        fs::write(
            root.join("state").join("boot-success"),
            b"success
",
        )
        .expect("write success marker");
        store
            .reconcile_post_boot(true)
            .expect("reconcile apply boot");

        store
            .rollback(&UpdateRollbackRequest {
                recovery_id: Some(recovery_id.clone()),
                reason: Some("return to slot a".to_string()),
                dry_run: false,
            })
            .expect("rollback update");

        fs::write(
            root.join("state").join("cmdline"),
            b"quiet splash aios.slot=a
",
        )
        .expect("write rollback cmdline");
        fs::write(
            root.join("state").join("boot-success"),
            b"success
",
        )
        .expect("write rollback success marker");

        let (state, boot_state) = store
            .reconcile_post_boot(true)
            .expect("reconcile rollback boot");
        assert_eq!(boot_state.current_slot, "a");
        assert_eq!(state.status, "up-to-date");
        assert_eq!(state.current_version, "0.1.0");
        assert_eq!(state.next_version, None);
        assert_eq!(state.pending_action, None);
        assert_eq!(state.active_recovery_id, None);
        assert!(state
            .notes
            .iter()
            .any(|note| note.starts_with("recovery_point_rolled_back=")));

        let recovery_record = store
            .recovery_point(&recovery_id)
            .expect("load recovery point")
            .expect("recovery point exists");
        assert_eq!(recovery_record.status, "rolled-back");

        fs::remove_dir_all(root).ok();
    }
}
