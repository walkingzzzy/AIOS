use std::{fs, path::Path};

use chrono::Utc;
use serde::Serialize;

use aios_contracts::RecoverySurfaceGetResponse;

use crate::{deployment::DeploymentStore, diagnostics, health};

#[derive(Debug, Clone, Serialize)]
pub struct RecoverySurfaceModel {
    pub generated_at: String,
    pub service_id: String,
    pub deployment_status: String,
    pub overall_status: String,
    pub rollback_ready: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub current_slot: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_good_slot: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub staged_slot: Option<String>,
    #[serde(default)]
    pub recovery_points: Vec<String>,
    #[serde(default)]
    pub diagnostic_bundles: Vec<String>,
    #[serde(default)]
    pub available_actions: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

pub fn build_surface(
    store: &DeploymentStore,
    probe_path: &Path,
) -> anyhow::Result<RecoverySurfaceModel> {
    let report = health::build_report(
        store,
        probe_path,
        &aios_contracts::UpdateHealthGetRequest::default(),
    )?;
    let deployment = store.snapshot()?;
    let boot_state = store.boot_state().ok();
    let diagnostic_bundles = diagnostics::list_bundle_names(store.diagnostics_dir())?;

    let mut available_actions = vec!["refresh-health".to_string(), "export-bundle".to_string()];
    if report.overall_status != "blocked" {
        available_actions.push("check-updates".to_string());
    }
    if deployment.status == "ready-to-stage" || deployment.status == "up-to-date" {
        available_actions.push("apply-update".to_string());
    }
    if report.rollback_ready {
        available_actions.push("rollback".to_string());
    }

    let mut notes = report.notes.clone();
    if let Some(boot_state) = &boot_state {
        notes.push(format!("boot_current_slot={}", boot_state.current_slot));
        notes.push(format!("boot_last_good_slot={}", boot_state.last_good_slot));
        if let Some(staged_slot) = &boot_state.staged_slot {
            notes.push(format!("boot_staged_slot={staged_slot}"));
        }
    }

    Ok(RecoverySurfaceModel {
        generated_at: Utc::now().to_rfc3339(),
        service_id: report.service_id,
        deployment_status: deployment.status,
        overall_status: report.overall_status,
        rollback_ready: report.rollback_ready,
        current_slot: boot_state.as_ref().map(|state| state.current_slot.clone()),
        last_good_slot: boot_state
            .as_ref()
            .map(|state| state.last_good_slot.clone()),
        staged_slot: boot_state
            .as_ref()
            .and_then(|state| state.staged_slot.clone()),
        recovery_points: report.recovery_points,
        diagnostic_bundles,
        available_actions,
        notes,
    })
}

pub fn build_response(
    store: &DeploymentStore,
    probe_path: &Path,
) -> anyhow::Result<RecoverySurfaceGetResponse> {
    let model = build_surface(store, probe_path)?;
    Ok(RecoverySurfaceGetResponse {
        service_id: model.service_id,
        generated_at: model.generated_at,
        deployment_status: model.deployment_status,
        overall_status: model.overall_status,
        rollback_ready: model.rollback_ready,
        current_slot: model.current_slot,
        last_good_slot: model.last_good_slot,
        staged_slot: model.staged_slot,
        recovery_points: model.recovery_points,
        diagnostic_bundles: model.diagnostic_bundles,
        available_actions: model.available_actions,
        notes: model.notes,
    })
}

pub fn write_surface(
    store: &DeploymentStore,
    probe_path: &Path,
    output_path: &Path,
) -> anyhow::Result<RecoverySurfaceModel> {
    let model = build_surface(store, probe_path)?;

    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(output_path, serde_json::to_vec_pretty(&model)?)?;

    Ok(model)
}
