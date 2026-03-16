use std::sync::{Arc, Mutex};

use serde::{de::DeserializeOwned, Serialize};
use serde_json::{json, Map, Value};

use aios_contracts::{
    methods, DeviceCaptureRecord, DeviceCaptureRequest, DeviceCaptureStopRequest,
    DeviceObjectNormalizeRequest, DeviceRetentionApplyRequest, DeviceStateGetRequest,
    DeviceStateGetResponse,
};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::{backend, capture, indicator, AppState};

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("deviced");

    let health_state = state.clone();
    router.register_method(methods::SYSTEM_HEALTH_GET, move |_| {
        json(health_state.health())
    });

    let state_get_state = state.clone();
    router.register_method(methods::DEVICE_STATE_GET, move |params| {
        let _request: DeviceStateGetRequest = parse_params(params)?;
        let (active_captures, startup_notes) = {
            let store = lock_store(&state_get_state.capture_store)?;
            (store.active_captures(), store.startup_notes().to_vec())
        };
        let continuous_collectors = state_get_state
            .continuous_capture_manager
            .lock()
            .map_err(|error| {
                RpcError::Internal(format!("continuous collector manager poisoned: {error}"))
            })?
            .snapshot();
        let indicator_count = indicator::read_state(&state_get_state.config.indicator_state_path)
            .map_err(|error| RpcError::Internal(error.to_string()))?
            .map(|state| state.active.len())
            .unwrap_or(0);
        let snapshot = refresh_backend_snapshot(&state_get_state.config)?;
        let ui_tree_snapshot = crate::adapters::state_ui_tree_snapshot(&state_get_state.config)
            .map_err(|error| {
                RpcError::Internal(format!("ui_tree snapshot refresh failed: {error}"))
            })?;
        let mut notes = vec![
            format!(
                "ui_tree_supported={}",
                state_get_state.config.ui_tree_supported
            ),
            format!("approval_mode={}", state_get_state.config.approval_mode),
            format!(
                "indicator_state_path={}",
                state_get_state.config.indicator_state_path.display()
            ),
            format!(
                "backend_state_path={}",
                state_get_state.config.backend_state_path.display()
            ),
            format!(
                "backend_evidence_dir={}",
                state_get_state.config.backend_evidence_dir.display()
            ),
            format!(
                "ui_tree_support_matrix_path={}",
                state_get_state
                    .config
                    .backend_state_path
                    .parent()
                    .unwrap_or_else(|| std::path::Path::new("."))
                    .join("ui-tree-support-matrix.json")
                    .display()
            ),
            format!(
                "policy_socket_path={}",
                state_get_state.config.policy_socket_path.display()
            ),
            format!(
                "policy_socket_present={}",
                state_get_state.config.policy_socket_path.exists()
            ),
            format!(
                "approval_rpc_timeout_ms={}",
                state_get_state.config.approval_rpc_timeout_ms
            ),
            format!("active_indicators={indicator_count}"),
        ];
        notes.extend(startup_notes);
        notes.extend(snapshot.notes.clone());
        let response = DeviceStateGetResponse {
            service_id: state_get_state.config.service_id.clone(),
            capabilities: capture::capabilities(&state_get_state.config),
            active_captures,
            backend_statuses: snapshot.statuses,
            capture_adapters: snapshot.adapters,
            ui_tree_snapshot,
            continuous_collectors,
            backend_summary: snapshot.backend_summary,
            ui_tree_support_matrix: snapshot.ui_tree_support_matrix,
            notes,
        };
        record_trace(
            &state_get_state,
            "device.state.reported",
            None,
            None,
            None,
            None,
            Some(&state_get_state.config.backend_state_path),
            json!({
                "capability_count": response.capabilities.len(),
                "active_capture_count": response.active_captures.len(),
                "backend_status_count": response.backend_statuses.len(),
                "capture_adapter_count": response.capture_adapters.len(),
                "continuous_collector_count": response.continuous_collectors.len(),
                "ui_tree_snapshot_present": response.ui_tree_snapshot.is_some(),
                "ui_tree_support_entries": response.ui_tree_support_matrix.len(),
                "backend_overall_status": response.backend_summary.overall_status.clone(),
                "backend_attention_count": response.backend_summary.attention_count,
            }),
            response.notes.clone(),
        );
        json(response)
    });

    let capture_request_state = state.clone();
    router.register_method(methods::DEVICE_CAPTURE_REQUEST, move |params| {
        let request: DeviceCaptureRequest = parse_params(params)?;
        let response = match lock_store(&capture_request_state.capture_store)?
            .request(&capture_request_state.config, &request)
        {
            Ok(response) => response,
            Err(error) => {
                let message = error.to_string();
                record_trace(
                    &capture_request_state,
                    "device.capture.rejected",
                    request.session_id.as_deref(),
                    request.task_id.as_deref(),
                    backend_for_modality(&capture_request_state.config, &request.modality),
                    None,
                    Some(&capture_request_state.config.capture_state_path),
                    request_trace_payload(&request, Some(message.clone())),
                    Vec::new(),
                );
                return Err(RpcError::Internal(message));
            }
        };
        if response.capture.continuous {
            capture_request_state
                .continuous_capture_manager
                .lock()
                .map_err(|error| {
                    RpcError::Internal(format!("continuous collector manager poisoned: {error}"))
                })?
                .start(&capture_request_state.config, &response.capture)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        }
        refresh_backend_snapshot_best_effort(&capture_request_state.config);
        record_capture_event(
            &capture_request_state,
            "device.capture.requested",
            &response.capture,
            request_success_extra_payload(
                request.window_ref.as_deref(),
                request.source_device.as_deref(),
                response.preview_object.is_some(),
            ),
        );
        json(response)
    });

    let capture_stop_state = state.clone();
    router.register_method(methods::DEVICE_CAPTURE_STOP, move |params| {
        let request: DeviceCaptureStopRequest = parse_params(params)?;
        let response = lock_store(&capture_stop_state.capture_store)?
            .stop(&capture_stop_state.config, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        capture_stop_state
            .continuous_capture_manager
            .lock()
            .map_err(|error| {
                RpcError::Internal(format!("continuous collector manager poisoned: {error}"))
            })?
            .stop(&request.capture_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        refresh_backend_snapshot_best_effort(&capture_stop_state.config);
        if let Some(capture) = &response.capture {
            record_capture_event(
                &capture_stop_state,
                "device.capture.stopped",
                capture,
                json!({
                    "reason": request.reason.clone(),
                    "capture_found": true,
                }),
            );
        } else {
            record_trace(
                &capture_stop_state,
                "device.capture.stop.missed",
                None,
                None,
                None,
                None,
                Some(&capture_stop_state.config.capture_state_path),
                stop_missed_payload(&request),
                Vec::new(),
            );
        }
        json(response)
    });

    router.register_method(methods::DEVICE_OBJECT_NORMALIZE, move |params| {
        let request: DeviceObjectNormalizeRequest = parse_params(params)?;
        let response = crate::normalize::apply(&request);
        json(response)
    });

    router.register_method(methods::DEVICE_RETENTION_APPLY, move |params| {
        let request: DeviceRetentionApplyRequest = parse_params(params)?;
        let response = crate::retention::apply(&request);
        json(response)
    });

    Arc::new(router)
}

fn refresh_backend_snapshot(
    config: &crate::config::Config,
) -> Result<backend::BackendSnapshot, RpcError> {
    backend::write_snapshot(&config.backend_state_path, config)
        .map_err(|error| RpcError::Internal(format!("backend snapshot refresh failed: {error}")))
}

fn refresh_backend_snapshot_best_effort(config: &crate::config::Config) {
    let _ = backend::write_snapshot(&config.backend_state_path, config);
}

fn lock_store(
    store: &Arc<Mutex<capture::CaptureStore>>,
) -> Result<std::sync::MutexGuard<'_, capture::CaptureStore>, RpcError> {
    store
        .lock()
        .map_err(|error| RpcError::Internal(format!("capture store poisoned: {error}")))
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

#[allow(clippy::too_many_arguments)]
fn record_trace(
    state: &AppState,
    kind: &str,
    session_id: Option<&str>,
    task_id: Option<&str>,
    provider_id: Option<&str>,
    approval_id: Option<&str>,
    artifact_path: Option<&std::path::Path>,
    payload: Value,
    notes: Vec<String>,
) {
    if let Err(error) = state.observability.append_record(
        kind,
        session_id,
        task_id,
        provider_id,
        approval_id,
        artifact_path,
        payload,
        notes,
    ) {
        tracing::warn!(?error, kind, "failed to append deviced observability event");
    }
}

fn record_capture_event(
    state: &AppState,
    kind: &str,
    capture: &DeviceCaptureRecord,
    extra_payload: Value,
) {
    let mut payload = Map::new();
    payload.insert(
        "capture_id".to_string(),
        Value::String(capture.capture_id.clone()),
    );
    payload.insert(
        "modality".to_string(),
        Value::String(capture.modality.clone()),
    );
    payload.insert("status".to_string(), Value::String(capture.status.clone()));
    payload.insert("continuous".to_string(), Value::Bool(capture.continuous));
    payload.insert("tainted".to_string(), Value::Bool(capture.tainted));
    insert_optional_string(
        &mut payload,
        "preview_object_kind",
        capture.preview_object_kind.as_deref(),
    );
    insert_optional_string(&mut payload, "adapter_id", capture.adapter_id.as_deref());
    insert_optional_string(
        &mut payload,
        "adapter_execution_path",
        capture.adapter_execution_path.as_deref(),
    );
    payload.insert(
        "approval_required".to_string(),
        Value::Bool(capture.approval_required),
    );
    insert_optional_string(
        &mut payload,
        "approval_status",
        capture.approval_status.as_deref(),
    );
    insert_optional_string(
        &mut payload,
        "approval_source",
        capture.approval_source.as_deref(),
    );
    insert_optional_string(
        &mut payload,
        "indicator_id",
        capture.indicator_id.as_deref(),
    );
    insert_optional_string(
        &mut payload,
        "retention_class",
        capture.retention_class.as_deref(),
    );
    if let Some(retention_ttl_seconds) = capture.retention_ttl_seconds {
        payload.insert(
            "retention_ttl_seconds".to_string(),
            json!(retention_ttl_seconds),
        );
    }
    payload.insert("extra".to_string(), extra_payload);

    record_trace(
        state,
        kind,
        capture.session_id.as_deref(),
        capture.task_id.as_deref(),
        Some(&capture.source_backend),
        capture.approval_ref.as_deref(),
        Some(&state.config.capture_state_path),
        Value::Object(payload),
        Vec::new(),
    );
}

fn backend_for_modality<'a>(config: &'a crate::config::Config, modality: &str) -> Option<&'a str> {
    match modality {
        "screen" => Some(config.screen_backend.as_str()),
        "audio" => Some(config.audio_backend.as_str()),
        "input" => Some(config.input_backend.as_str()),
        "camera" => Some(config.camera_backend.as_str()),
        "ui_tree" => Some("ui_tree"),
        _ => None,
    }
}

fn insert_optional_string(payload: &mut Map<String, Value>, key: &str, value: Option<&str>) {
    if let Some(value) = value {
        payload.insert(key.to_string(), Value::String(value.to_string()));
    }
}

fn request_trace_payload(request: &DeviceCaptureRequest, error: Option<String>) -> Value {
    let mut payload = Map::new();
    payload.insert(
        "modality".to_string(),
        Value::String(request.modality.clone()),
    );
    payload.insert("continuous".to_string(), Value::Bool(request.continuous));
    insert_optional_string(&mut payload, "window_ref", request.window_ref.as_deref());
    insert_optional_string(
        &mut payload,
        "source_device",
        request.source_device.as_deref(),
    );
    if let Some(error) = error {
        payload.insert("error".to_string(), Value::String(error));
    }
    Value::Object(payload)
}

fn request_success_extra_payload(
    window_ref: Option<&str>,
    source_device: Option<&str>,
    preview_object_present: bool,
) -> Value {
    let mut payload = Map::new();
    insert_optional_string(&mut payload, "window_ref", window_ref);
    insert_optional_string(&mut payload, "source_device", source_device);
    payload.insert(
        "preview_object_present".to_string(),
        Value::Bool(preview_object_present),
    );
    Value::Object(payload)
}

fn stop_missed_payload(request: &DeviceCaptureStopRequest) -> Value {
    let mut payload = Map::new();
    payload.insert(
        "capture_id".to_string(),
        Value::String(request.capture_id.clone()),
    );
    insert_optional_string(&mut payload, "reason", request.reason.as_deref());
    payload.insert("capture_found".to_string(), Value::Bool(false));
    Value::Object(payload)
}
