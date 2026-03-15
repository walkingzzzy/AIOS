use std::path::Path;
use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::Value;

use aios_contracts::{
    methods, RecoveryBundleExportRequest, RecoverySurfaceGetRequest, UpdateApplyRequest,
    UpdateCheckRequest, UpdateHealthGetRequest, UpdateRollbackRequest,
};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::AppState;

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("updated");

    let health_state = state.clone();
    router.register_method(methods::SYSTEM_HEALTH_GET, move |_| {
        json(health_state.health())
    });

    let update_check_state = state.clone();
    router.register_method(methods::UPDATE_CHECK, move |params| {
        let request: UpdateCheckRequest = parse_params(params)?;
        let response = update_check_state
            .deployment
            .check(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        sync_recovery_surface(&update_check_state);
        record_event(
            &update_check_state,
            "update.check.completed",
            Some(&update_check_state.config.deployment_state_path),
            None,
            serde_json::json!({
                "status": response.status.clone(),
                "configured_channel": response.configured_channel.clone(),
                "current_version": response.current_version.clone(),
                "next_version": response.next_version.clone(),
                "artifact_count": response.artifacts.len(),
            }),
            response.notes.clone(),
        );
        json(response)
    });

    let update_apply_state = state.clone();
    router.register_method(methods::UPDATE_APPLY, move |params| {
        let request: UpdateApplyRequest = parse_params(params)?;
        let response = update_apply_state
            .deployment
            .apply(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        sync_recovery_surface(&update_apply_state);
        record_event(
            &update_apply_state,
            "update.apply.completed",
            Some(&update_apply_state.config.deployment_state_path),
            response.recovery_ref.as_deref(),
            serde_json::json!({
                "status": response.status.clone(),
                "deployment_status": response.deployment_status.clone(),
                "target_version": response.target_version.clone(),
                "dry_run": response.dry_run,
                "staged_artifact_count": response.staged_artifacts.len(),
            }),
            response.notes.clone(),
        );
        json(response)
    });

    let update_health_state = state.clone();
    router.register_method(methods::UPDATE_HEALTH_GET, move |params| {
        let request: UpdateHealthGetRequest = parse_params(params)?;
        crate::health::refresh_probe(
            &update_health_state.deployment,
            update_health_state.config.health_probe_command.as_deref(),
            &update_health_state.config.health_probe_path,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        let response = crate::health::build_report(
            &update_health_state.deployment,
            &update_health_state.config.health_probe_path,
            &request,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        sync_recovery_surface(&update_health_state);
        record_event(
            &update_health_state,
            "update.health.reported",
            Some(&update_health_state.config.health_probe_path),
            update_health_state
                .deployment
                .snapshot()
                .ok()
                .and_then(|state| state.active_recovery_id)
                .as_deref(),
            serde_json::json!({
                "overall_status": response.overall_status.clone(),
                "rollback_ready": response.rollback_ready,
                "recovery_point_count": response.recovery_points.len(),
                "diagnostic_bundle_count": response.diagnostic_bundles.len(),
                "last_check_at": response.last_check_at.clone(),
            }),
            response.notes.clone(),
        );
        json(response)
    });

    let update_rollback_state = state.clone();
    router.register_method(methods::UPDATE_ROLLBACK, move |params| {
        let request: UpdateRollbackRequest = parse_params(params)?;
        let response = update_rollback_state
            .deployment
            .rollback(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        sync_recovery_surface(&update_rollback_state);
        record_event(
            &update_rollback_state,
            "update.rollback.completed",
            Some(&update_rollback_state.config.deployment_state_path),
            response.rollback_target.as_deref(),
            serde_json::json!({
                "status": response.status.clone(),
                "deployment_status": response.deployment_status.clone(),
                "dry_run": response.dry_run,
                "rollback_target": response.rollback_target.clone(),
            }),
            response.notes.clone(),
        );
        json(response)
    });

    let recovery_surface_state = state.clone();
    router.register_method(methods::RECOVERY_SURFACE_GET, move |params| {
        let _request: RecoverySurfaceGetRequest = parse_params(params)?;
        crate::health::refresh_probe(
            &recovery_surface_state.deployment,
            recovery_surface_state
                .config
                .health_probe_command
                .as_deref(),
            &recovery_surface_state.config.health_probe_path,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        let response = crate::recovery_ui::build_response(
            &recovery_surface_state.deployment,
            &recovery_surface_state.config.health_probe_path,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        sync_recovery_surface(&recovery_surface_state);
        record_event(
            &recovery_surface_state,
            "recovery.surface.reported",
            Some(&recovery_surface_state.config.recovery_surface_path),
            recovery_surface_state
                .deployment
                .snapshot()
                .ok()
                .and_then(|state| state.active_recovery_id)
                .as_deref(),
            serde_json::json!({
                "deployment_status": response.deployment_status.clone(),
                "overall_status": response.overall_status.clone(),
                "rollback_ready": response.rollback_ready,
                "current_slot": response.current_slot.clone(),
                "last_good_slot": response.last_good_slot.clone(),
                "staged_slot": response.staged_slot.clone(),
                "action_count": response.available_actions.len(),
            }),
            response.notes.clone(),
        );
        json(response)
    });

    let recovery_bundle_state = state.clone();
    router.register_method(methods::RECOVERY_BUNDLE_EXPORT, move |params| {
        let request: RecoveryBundleExportRequest = parse_params(params)?;
        let response = crate::diagnostics::export_bundle(
            &recovery_bundle_state.deployment,
            &recovery_bundle_state.config.health_probe_path,
            &request,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        sync_recovery_surface(&recovery_bundle_state);
        record_event(
            &recovery_bundle_state,
            "recovery.bundle.exported",
            Some(Path::new(&response.bundle_path)),
            recovery_bundle_state
                .deployment
                .snapshot()
                .ok()
                .and_then(|state| state.active_recovery_id)
                .as_deref(),
            serde_json::json!({
                "bundle_id": response.bundle_id.clone(),
                "deployment_status": response.deployment_status.clone(),
                "recovery_point_count": response.recovery_points.len(),
                "diagnostic_bundle_count": response.diagnostic_bundles.len(),
            }),
            response.notes.clone(),
        );
        json(response)
    });

    Arc::new(router)
}

fn sync_recovery_surface(state: &AppState) {
    if let Err(error) = crate::recovery_ui::write_surface(
        &state.deployment,
        &state.config.health_probe_path,
        &state.config.recovery_surface_path,
    ) {
        tracing::warn!(error = %error, "failed to sync recovery surface");
    }
}

fn record_event(
    state: &AppState,
    kind: &str,
    artifact_path: Option<&Path>,
    update_id: Option<&str>,
    payload: Value,
    notes: Vec<String>,
) {
    if let Err(error) =
        state
            .observability
            .append_record(kind, artifact_path, update_id, payload, notes)
    {
        tracing::warn!(?error, kind, "failed to append updated observability event");
    }
}

fn parse_params<T>(params: Option<Value>) -> Result<T, RpcError>
where
    T: DeserializeOwned,
{
    serde_json::from_value(params.unwrap_or(Value::Null))
        .map_err(|error| RpcError::InvalidParams(error.to_string()))
}

fn json<T>(value: T) -> RpcResult
where
    T: Serialize,
{
    serde_json::to_value(value).map_err(|error| RpcError::Internal(error.to_string()))
}
