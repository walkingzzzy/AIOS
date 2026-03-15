use std::{fs, path::Path, process::Command};

use anyhow::Context;

use chrono::Utc;
use serde::{Deserialize, Serialize};

use aios_contracts::{UpdateHealthGetRequest, UpdateHealthGetResponse};

use crate::{deployment::DeploymentStore, diagnostics, rollback};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProbeSnapshot {
    pub overall_status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub checked_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub summary: Option<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

pub fn load_probe(path: &Path) -> anyhow::Result<Option<ProbeSnapshot>> {
    if !path.exists() {
        return Ok(None);
    }

    let content = fs::read_to_string(path)
        .with_context(|| format!("failed to read health probe {}", path.display()))?;
    let snapshot = serde_json::from_str::<ProbeSnapshot>(&content)?;
    Ok(Some(snapshot))
}

pub fn refresh_probe(
    store: &DeploymentStore,
    command: Option<&str>,
    probe_path: &Path,
) -> anyhow::Result<Option<ProbeSnapshot>> {
    let Some(command) = command else {
        return load_probe(probe_path);
    };

    let state = store.snapshot()?;
    let recovery_points = store.recovery_points()?;
    let diagnostic_bundles = diagnostics::list_bundle_names(store.diagnostics_dir())?;
    let environment = probe_environment(
        store,
        probe_path,
        &state,
        &recovery_points,
        &diagnostic_bundles,
    );

    let output = run_probe_command(command, &environment);
    let checked_at = Utc::now().to_rfc3339();

    let snapshot = match output {
        Ok(output) => {
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

            if let Ok(mut parsed) = serde_json::from_str::<ProbeSnapshot>(&stdout) {
                if parsed.checked_at.is_none() {
                    parsed.checked_at = Some(checked_at.clone());
                }
                if !stderr.is_empty() {
                    parsed.notes.push(format!("stderr={stderr}"));
                }
                parsed
            } else {
                let mut notes = vec![format!("command={command}")];
                notes.push(format!("probe_path={}", probe_path.display()));
                notes.push(format!("deployment_status={}", state.status));
                if !stdout.is_empty() {
                    notes.push(format!("stdout={stdout}"));
                }
                if !stderr.is_empty() {
                    notes.push(format!("stderr={stderr}"));
                }

                ProbeSnapshot {
                    overall_status: if output.status.success() {
                        "healthy".to_string()
                    } else {
                        "failed".to_string()
                    },
                    checked_at: Some(checked_at.clone()),
                    summary: Some(if output.status.success() {
                        "probe command completed".to_string()
                    } else {
                        format!(
                            "probe command failed with status {:?}",
                            output.status.code()
                        )
                    }),
                    notes,
                }
            }
        }
        Err(error) => ProbeSnapshot {
            overall_status: "failed".to_string(),
            checked_at: Some(checked_at.clone()),
            summary: Some("probe command execution failed".to_string()),
            notes: vec![
                format!("command={command}"),
                format!("probe_path={}", probe_path.display()),
                format!("deployment_status={}", state.status),
                format!("error={error}"),
            ],
        },
    };

    persist_probe(probe_path, &snapshot)?;
    Ok(Some(snapshot))
}

fn run_probe_command(
    command: &str,
    environment: &[(String, String)],
) -> std::io::Result<std::process::Output> {
    let mut shell = Command::new("/bin/sh");
    shell.arg("-lc").arg(command);
    for (key, value) in environment {
        shell.env(key, value);
    }
    shell.output()
}

fn probe_environment(
    store: &DeploymentStore,
    probe_path: &Path,
    state: &crate::deployment::DeploymentState,
    recovery_points: &[String],
    diagnostic_bundles: &[String],
) -> Vec<(String, String)> {
    let mut environment = store.command_environment(state, "health_probe");
    environment.push((
        "AIOS_UPDATED_HEALTH_PROBE_PATH".to_string(),
        probe_path.display().to_string(),
    ));
    environment.push((
        "AIOS_UPDATED_RECOVERY_POINT_COUNT".to_string(),
        recovery_points.len().to_string(),
    ));
    environment.push((
        "AIOS_UPDATED_DIAGNOSTIC_BUNDLE_COUNT".to_string(),
        diagnostic_bundles.len().to_string(),
    ));
    environment.push((
        "AIOS_UPDATED_RECOVERY_POINTS".to_string(),
        recovery_points.join(","),
    ));
    environment.push((
        "AIOS_UPDATED_DIAGNOSTIC_BUNDLES".to_string(),
        diagnostic_bundles.join(","),
    ));
    environment
}

pub fn build_report(
    store: &DeploymentStore,
    probe_path: &Path,
    _request: &UpdateHealthGetRequest,
) -> anyhow::Result<UpdateHealthGetResponse> {
    let mut state = store.snapshot()?;
    let recovery_points = store.recovery_points()?;
    let diagnostic_bundles = diagnostics::list_bundle_names(store.diagnostics_dir())?;
    let probe = load_probe(probe_path)?;

    let boot_healthy = probe
        .as_ref()
        .map(|probe| normalize_probe_status(&probe.overall_status) == "ready")
        .unwrap_or(deployment_status_overall(&state.status) == "ready");

    let mut notes = vec![
        format!(
            "deployment_state={}",
            store.deployment_state_path().display()
        ),
        format!("sysupdate_dir={}", store.sysupdate_dir().display()),
        format!("probe_path={}", probe_path.display()),
        format!("diagnostic_bundles={}", diagnostic_bundles.len()),
    ];

    if let Ok((reconciled_state, boot_state)) = store.reconcile_post_boot(boot_healthy) {
        state = reconciled_state;
        notes.push(format!("boot_current_slot={}", boot_state.current_slot));
        notes.push(format!("boot_last_good_slot={}", boot_state.last_good_slot));
        notes.push(format!("boot_success={}", boot_state.boot_success));
        if let Some(staged_slot) = boot_state.staged_slot {
            notes.push(format!("boot_staged_slot={staged_slot}"));
        }
        notes.extend(boot_state.notes);
    }

    let rollback_ready = rollback::rollback_ready(&state, &recovery_points);
    if rollback_ready {
        notes.push(format!("recovery_points={}", recovery_points.len()));
    } else {
        notes.push("no recovery points recorded yet".to_string());
    }

    if diagnostic_bundles.is_empty() {
        notes.push("no diagnostic bundles exported yet".to_string());
    }

    notes.extend(state.notes.iter().cloned());

    let mut overall_status = deployment_status_overall(&state.status).to_string();
    if let Some(probe) = &probe {
        let probe_status = normalize_probe_status(&probe.overall_status);
        if status_rank(probe_status) > status_rank(&overall_status) {
            overall_status = probe_status.to_string();
        }
        if let Some(checked_at) = &probe.checked_at {
            notes.push(format!("probe_checked_at={checked_at}"));
        }
        if let Some(summary) = &probe.summary {
            notes.push(format!("probe_summary={summary}"));
        }
        notes.extend(probe.notes.iter().cloned());
    } else {
        notes.push("health probe snapshot missing".to_string());
    }

    Ok(UpdateHealthGetResponse {
        service_id: state.service_id,
        overall_status,
        rollback_ready,
        last_check_at: state.last_check_at,
        recovery_points,
        diagnostic_bundles,
        notes,
    })
}

fn persist_probe(path: &Path, snapshot: &ProbeSnapshot) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    fs::write(path, serde_json::to_vec_pretty(snapshot)?)?;
    Ok(())
}

fn deployment_status_overall(status: &str) -> &str {
    match status {
        "ready-to-stage" => "ready",
        "staged-update" => "ready",
        "up-to-date" => "ready",
        "rollback-staged" => "degraded",
        "waiting-for-artifacts" => "degraded",
        "missing-sysupdate-dir" => "blocked",
        _ => "idle",
    }
}

fn normalize_probe_status(status: &str) -> &str {
    match status {
        "healthy" => "ready",
        "warning" => "degraded",
        "failed" | "unhealthy" => "blocked",
        other => other,
    }
}

fn status_rank(status: &str) -> u8 {
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
    use std::{
        fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use aios_contracts::UpdateCheckRequest;

    use crate::deployment::{DeploymentStore, DeploymentStoreConfig};

    use super::*;

    fn root() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("aios-updated-health-{stamp}"))
    }

    fn store(root: &PathBuf) -> DeploymentStore {
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
            update_stack: "systemd-sysupdate".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            target_version_hint: None,
            sysupdate_check_command: None,
            sysupdate_apply_command: None,
            rollback_command: None,
        })
        .expect("create store")
    }

    #[test]
    fn deployment_and_probe_status_mapping_matches_expected_levels() {
        assert_eq!(deployment_status_overall("ready-to-stage"), "ready");
        assert_eq!(deployment_status_overall("rollback-staged"), "degraded");
        assert_eq!(
            deployment_status_overall("missing-sysupdate-dir"),
            "blocked"
        );
        assert_eq!(deployment_status_overall("idle"), "idle");

        assert_eq!(normalize_probe_status("healthy"), "ready");
        assert_eq!(normalize_probe_status("warning"), "degraded");
        assert_eq!(normalize_probe_status("failed"), "blocked");
        assert_eq!(normalize_probe_status("custom"), "custom");
    }

    #[test]
    fn load_probe_returns_none_when_snapshot_is_missing() {
        let root = root();
        let probe_path = root.join("state").join("health-probe.json");

        let probe = load_probe(&probe_path).expect("load missing probe");

        assert!(probe.is_none());
    }

    #[test]
    fn health_report_includes_diagnostics_and_recovery_points() {
        let root = root();
        let store = store(&root);

        fs::create_dir_all(root.join("sysupdate")).expect("create sysupdate dir");
        fs::write(root.join("sysupdate").join("00-root.transfer"), b"transfer")
            .expect("write transfer file");
        fs::write(root.join("recovery").join("recovery-001.json"), b"{}")
            .expect("write recovery file");
        fs::write(root.join("diagnostics").join("bundle-001.json"), b"{}")
            .expect("write diagnostic bundle");
        let probe_path = root.join("state").join("health-probe.json");
        fs::create_dir_all(probe_path.parent().expect("probe parent")).expect("create probe dir");
        fs::write(
            &probe_path,
            br#"{"overall_status":"healthy","summary":"boot ok","checked_at":"2026-03-08T00:00:00Z"}"#,
        )
        .expect("write probe snapshot");

        store
            .check(&UpdateCheckRequest::default())
            .expect("run update check");
        let report = build_report(&store, &probe_path, &UpdateHealthGetRequest::default())
            .expect("build health report");

        assert_eq!(report.overall_status, "ready");
        assert!(report.rollback_ready);
        assert_eq!(
            report.recovery_points,
            vec!["recovery-001.json".to_string()]
        );
        assert_eq!(
            report.diagnostic_bundles,
            vec!["bundle-001.json".to_string()]
        );
        assert!(report
            .notes
            .iter()
            .any(|item| item.contains("probe_summary=boot ok")));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn missing_probe_snapshot_keeps_deployment_based_status_and_records_note() {
        let root = root();
        let store = store(&root);
        let probe_path = root.join("state").join("health-probe.json");

        let report = build_report(&store, &probe_path, &UpdateHealthGetRequest::default())
            .expect("build health report");

        assert_eq!(report.overall_status, "idle");
        assert!(report
            .notes
            .iter()
            .any(|item| item == "health probe snapshot missing"));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn health_probe_can_degrade_overall_status() {
        let root = root();
        let store = store(&root);
        let probe_path = root.join("state").join("health-probe.json");
        fs::create_dir_all(probe_path.parent().expect("probe parent")).expect("create probe dir");
        fs::write(
            &probe_path,
            br#"{"overall_status":"failed","summary":"boot failed"}"#,
        )
        .expect("write probe snapshot");

        let report = build_report(&store, &probe_path, &UpdateHealthGetRequest::default())
            .expect("build health report");

        assert_eq!(report.overall_status, "blocked");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn warning_probe_results_in_degraded_overall_status() {
        let root = root();
        let store = store(&root);
        let probe_path = root.join("state").join("health-probe.json");
        fs::create_dir_all(probe_path.parent().expect("probe parent")).expect("create probe dir");
        fs::write(
            &probe_path,
            br#"{"overall_status":"warning","summary":"boot degraded"}"#,
        )
        .expect("write probe snapshot");

        let report = build_report(&store, &probe_path, &UpdateHealthGetRequest::default())
            .expect("build health report");

        assert_eq!(report.overall_status, "degraded");
        assert!(report
            .notes
            .iter()
            .any(|item| item.contains("probe_summary=boot degraded")));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn refresh_probe_persists_command_output() {
        let root = root();
        let store = store(&root);
        let probe_path = root.join("state").join("health-probe.json");

        let probe = refresh_probe(
            &store,
            Some("printf '%s' '{\"overall_status\":\"healthy\",\"summary\":\"probe ok\"}'"),
            &probe_path,
        )
        .expect("refresh probe")
        .expect("probe snapshot");

        assert_eq!(probe.overall_status, "healthy");
        assert!(probe_path.exists());

        fs::remove_dir_all(root).ok();
    }
}
