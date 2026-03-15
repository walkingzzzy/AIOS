use std::{fs, path::Path};

use chrono::Utc;
use serde::Serialize;

use aios_contracts::{RecoveryBundleExportRequest, RecoveryBundleExportResponse};

use crate::{
    boot,
    deployment::{DeploymentState, DeploymentStore},
    health,
};

#[derive(Debug, Clone, Serialize)]
struct DiagnosticBundle {
    bundle_id: String,
    created_at: String,
    service_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    deployment: DeploymentState,
    #[serde(skip_serializing_if = "Option::is_none")]
    probe: Option<health::ProbeSnapshot>,
    #[serde(skip_serializing_if = "Option::is_none")]
    boot_state: Option<boot::BootState>,
    #[serde(default)]
    recovery_points: Vec<String>,
    #[serde(default)]
    diagnostic_bundles: Vec<String>,
    #[serde(default)]
    notes: Vec<String>,
}

pub fn list_bundle_names(root: &Path) -> anyhow::Result<Vec<String>> {
    if !root.exists() {
        return Ok(Vec::new());
    }

    let mut bundles = fs::read_dir(root)?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.file_name().to_string_lossy().to_string())
        .collect::<Vec<_>>();
    bundles.sort();
    Ok(bundles)
}

pub fn export_bundle(
    store: &DeploymentStore,
    probe_path: &Path,
    request: &RecoveryBundleExportRequest,
) -> anyhow::Result<RecoveryBundleExportResponse> {
    let deployment = store.snapshot()?;
    let recovery_points = store.recovery_points()?;
    let diagnostic_bundles = list_bundle_names(store.diagnostics_dir())?;
    let probe = health::load_probe(probe_path)?;
    let boot_state = store.boot_state().ok();
    let created_at = Utc::now().to_rfc3339();
    let bundle_id = format!("diag-{}", Utc::now().timestamp_millis());
    let bundle_name = format!("{bundle_id}.json");
    let bundle_path = store.diagnostics_dir().join(&bundle_name);

    let mut notes = vec![
        format!("probe_path={}", probe_path.display()),
        format!(
            "deployment_state={}",
            store.deployment_state_path().display()
        ),
    ];

    if let Some(reason) = &request.reason {
        notes.push(format!("reason={reason}"));
    }

    if probe.is_none() {
        notes.push("health probe snapshot missing".to_string());
    }

    let mut all_diagnostic_bundles = diagnostic_bundles.clone();
    all_diagnostic_bundles.push(bundle_name.clone());
    all_diagnostic_bundles.sort();

    let bundle = DiagnosticBundle {
        bundle_id: bundle_id.clone(),
        created_at: created_at.clone(),
        service_id: store.service_id().to_string(),
        reason: request.reason.clone(),
        deployment: deployment.clone(),
        probe,
        boot_state,
        recovery_points: recovery_points.clone(),
        diagnostic_bundles: all_diagnostic_bundles.clone(),
        notes: notes.clone(),
    };

    if let Some(parent) = bundle_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&bundle_path, serde_json::to_vec_pretty(&bundle)?)?;

    Ok(RecoveryBundleExportResponse {
        service_id: store.service_id().to_string(),
        bundle_id,
        bundle_path: bundle_path.display().to_string(),
        created_at,
        deployment_status: deployment.status,
        recovery_points,
        diagnostic_bundles: all_diagnostic_bundles,
        notes,
    })
}

#[cfg(test)]
mod tests {
    use std::{
        fs,
        path::{Path, PathBuf},
        time::{SystemTime, UNIX_EPOCH},
    };

    use aios_contracts::RecoveryBundleExportRequest;

    use crate::deployment::{DeploymentStore, DeploymentStoreConfig};

    use super::*;

    fn test_root(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("aios-updated-diagnostics-{name}-{stamp}"))
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
            update_stack: "systemd-sysupdate".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            target_version_hint: Some("0.1.1".to_string()),
            sysupdate_check_command: None,
            sysupdate_apply_command: None,
            rollback_command: None,
        })
        .expect("create store")
    }

    #[test]
    fn bundle_names_are_sorted() {
        let root = test_root("sorted");
        fs::create_dir_all(&root).expect("create diagnostics root");
        fs::write(root.join("z-last.json"), b"{}").expect("write bundle");
        fs::write(root.join("a-first.json"), b"{}").expect("write bundle");

        let bundles = list_bundle_names(&root).expect("list bundles");
        assert_eq!(
            bundles,
            vec!["a-first.json".to_string(), "z-last.json".to_string()]
        );

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn recovery_bundle_export_writes_bundle_file() {
        let root = test_root("export");
        let store = store(&root);
        fs::create_dir_all(root.join("recovery")).expect("create recovery dir");
        fs::write(root.join("recovery").join("recovery-001.json"), b"{}")
            .expect("write recovery ref");
        let probe_path = root.join("state").join("health-probe.json");
        fs::create_dir_all(probe_path.parent().expect("probe parent")).expect("create probe dir");
        fs::write(
            &probe_path,
            br#"{"overall_status":"healthy","summary":"boot ok","checked_at":"2026-03-08T00:00:00Z"}"#,
        )
        .expect("write probe snapshot");

        let response = export_bundle(
            &store,
            &probe_path,
            &RecoveryBundleExportRequest {
                reason: Some("manual-export".to_string()),
            },
        )
        .expect("export recovery bundle");

        assert!(response.bundle_id.starts_with("diag-"));
        assert!(PathBuf::from(&response.bundle_path).exists());
        assert_eq!(
            response.recovery_points,
            vec!["recovery-001.json".to_string()]
        );
        assert!(response
            .diagnostic_bundles
            .iter()
            .any(|item| item == &format!("{}.json", response.bundle_id)));

        fs::remove_dir_all(root).ok();
    }
}
