use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::{json as json_value, Value};

use aios_contracts::{
    methods, ExecutionToken, RuntimeBackendEventPayload, RuntimeInferRequest, RuntimeInferResponse,
    RuntimeObservabilityExportRequest, RuntimeQueueResponse, RuntimeRouteResolveRequest,
    RuntimeRouteResolveResponse, ServiceContractResponse, TraceQueryRequest,
};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::AppState;

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("runtimed");

    let health_state = state.clone();
    router.register_method(methods::SYSTEM_HEALTH_GET, move |_| {
        json(health_state.health())
    });

    let contract_state = state.clone();
    router.register_method(methods::SYSTEM_CONTRACT_GET, move |_| {
        json(ServiceContractResponse {
            service_id: contract_state.config.service_id.clone(),
            contract: aios_contracts::shared_contract_manifest(),
        })
    });

    let backend_state = state.clone();
    router.register_method(methods::RUNTIME_BACKEND_LIST, move |_| {
        json(backend_state.runtime_backends())
    });

    let route_state = state.clone();
    router.register_method(methods::RUNTIME_ROUTE_RESOLVE, move |params| {
        let request: RuntimeRouteResolveRequest = parse_params(params)?;
        json(route_state.scheduler.resolve(&request))
    });

    let queue_state = state.clone();
    router.register_method(methods::RUNTIME_QUEUE_GET, move |_| {
        let pending = queue_state.queue.snapshot();
        let max_concurrency = queue_state.budget.max_concurrency;
        json(RuntimeQueueResponse {
            pending,
            max_concurrency,
            available_slots: queue_state.queue.available_slots(max_concurrency),
            saturated: queue_state.queue.is_saturated(max_concurrency),
        })
    });

    let budget_state = state.clone();
    router.register_method(methods::RUNTIME_BUDGET_GET, move |_| {
        json(budget_state.budget.snapshot())
    });

    let events_state = state.clone();
    router.register_method(methods::RUNTIME_EVENTS_GET, move |params| {
        let request: TraceQueryRequest = parse_params_or_default(params)?;
        json(events_state.events.query(&request))
    });

    let export_state = state.clone();
    router.register_method(methods::RUNTIME_OBSERVABILITY_EXPORT, move |params| {
        let request: RuntimeObservabilityExportRequest = parse_params_or_default(params)?;
        let response = crate::export::export_bundle(&export_state, &request).map_err(|error| {
            RpcError::internal_code("runtime_observability_export_failed", error.to_string())
        })?;
        json(response)
    });
    let infer_state = state.clone();
    router.register_method(methods::RUNTIME_INFER_SUBMIT, move |params| {
        let request: RuntimeInferRequest = parse_params(params)?;
        let route = infer_state.scheduler.resolve(&RuntimeRouteResolveRequest {
            preferred_backend: request.preferred_backend.clone(),
            allow_remote: true,
        });

        record_submit_event(&infer_state, &request, &route);

        let remote_token = if route.selected_backend == "attested-remote" {
            match crate::remote_security::authorize_attested_remote_request(
                &infer_state.config.policyd_socket,
                &request,
                infer_state.config.attested_remote_target_hash.as_deref(),
            ) {
                Ok(token) => Some(token),
                Err(error) => {
                    let response = reject_response(
                        &route,
                        &error.route_state,
                        Some(error.reason.clone()),
                        None,
                    );
                    let event_payload = response_event_payload(
                        &infer_state,
                        "rejected",
                        &request,
                        &route,
                        &response,
                    );
                    record_runtime_event(
                        &infer_state,
                        "runtime.infer.rejected",
                        &request,
                        event_payload,
                    );
                    infer_state
                        .remote_audit
                        .append_error(
                            request.execution_token.as_ref(),
                            &request,
                            &route,
                            &response.route_state,
                            response
                                .reason
                                .as_deref()
                                .unwrap_or("unknown remote authorization failure"),
                        )
                        .unwrap_or_else(|audit_error| {
                            tracing::warn!(
                                ?audit_error,
                                "failed to append attested-remote audit error"
                            );
                        });
                    infer_state
                        .budget
                        .record_response(&response.backend_id, &response.route_state);
                    return json(response);
                }
            }
        } else {
            None
        };

        let queue_permit = match infer_state.queue.admit(infer_state.budget.max_concurrency) {
            Ok(permit) => permit,
            Err(pending) => {
                let response = reject_response(
                    &route,
                    "queue-rejected",
                    Some(format!(
                        "runtime queue is saturated: pending={}, max_concurrency={}",
                        pending, infer_state.budget.max_concurrency
                    )),
                    None,
                );
                let mut event_payload =
                    response_event_payload(&infer_state, "rejected", &request, &route, &response);
                event_payload.pending_queue = Some(pending);
                event_payload.queue_saturated = Some(true);
                record_runtime_event(
                    &infer_state,
                    "runtime.infer.rejected",
                    &request,
                    event_payload,
                );
                append_remote_audit_result(
                    &infer_state,
                    remote_token.as_ref(),
                    &request,
                    &route,
                    &response,
                );
                infer_state
                    .budget
                    .record_response(&response.backend_id, &response.route_state);
                return json(response);
            }
        };

        let budget_permit = match infer_state
            .budget
            .admit(request.model.as_deref(), &request.prompt)
        {
            Ok(permit) => permit,
            Err(error) => {
                let response =
                    reject_response(&route, "budget-rejected", Some(error.to_string()), None);
                let event_payload =
                    response_event_payload(&infer_state, "rejected", &request, &route, &response);
                record_runtime_event(
                    &infer_state,
                    "runtime.infer.rejected",
                    &request,
                    event_payload,
                );
                append_remote_audit_result(
                    &infer_state,
                    remote_token.as_ref(),
                    &request,
                    &route,
                    &response,
                );
                infer_state
                    .budget
                    .record_response(&response.backend_id, &response.route_state);
                drop(queue_permit);
                return json(response);
            }
        };

        record_admitted_event(&infer_state, &request, &route);
        record_started_event(&infer_state, &request, &route);

        let response = infer_state.scheduler.infer_on_route(&request, &route);
        record_terminal_events(&infer_state, &request, &route, &response);
        append_remote_audit_result(
            &infer_state,
            remote_token.as_ref(),
            &request,
            &route,
            &response,
        );
        infer_state
            .budget
            .record_response(&response.backend_id, &response.route_state);
        drop(budget_permit);
        drop(queue_permit);
        json(response)
    });

    Arc::new(router)
}

fn parse_params<T>(params: Option<Value>) -> Result<T, RpcError>
where
    T: DeserializeOwned,
{
    serde_json::from_value(params.unwrap_or(Value::Null))
        .map_err(|error| RpcError::invalid_params_code("invalid_json_params", error.to_string()))
}

fn parse_params_or_default<T>(params: Option<Value>) -> Result<T, RpcError>
where
    T: Default + DeserializeOwned,
{
    match params {
        None | Some(Value::Null) => Ok(T::default()),
        Some(value) => serde_json::from_value(value).map_err(|error| {
            RpcError::invalid_params_code("invalid_json_params", error.to_string())
        }),
    }
}

fn json<T>(value: T) -> RpcResult
where
    T: Serialize,
{
    serde_json::to_value(value).map_err(|error| {
        RpcError::internal_code("response_serialization_failed", error.to_string())
    })
}

fn reject_response(
    route: &RuntimeRouteResolveResponse,
    route_state: &str,
    reason: Option<String>,
    estimated_latency_ms: Option<u64>,
) -> RuntimeInferResponse {
    RuntimeInferResponse {
        backend_id: route.selected_backend.clone(),
        route_state: route_state.to_string(),
        content: String::new(),
        degraded: route.degraded,
        rejected: true,
        reason,
        estimated_latency_ms,
        provider_id: None,
        runtime_service_id: None,
        provider_status: None,
        queue_saturated: None,
        runtime_budget: None,
        notes: Vec::new(),
    }
}

fn append_remote_audit_result(
    state: &AppState,
    remote_token: Option<&ExecutionToken>,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
    response: &RuntimeInferResponse,
) {
    let Some(token) = remote_token else {
        return;
    };

    state
        .remote_audit
        .append_result(token, request, route, response)
        .unwrap_or_else(|error| {
            tracing::warn!(?error, "failed to append attested-remote audit entry");
        });
}

fn record_submit_event(
    state: &AppState,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
) {
    record_runtime_event(
        state,
        "runtime.infer.submit",
        request,
        route_event_payload(state, "submit", request, route),
    );
}

fn record_admitted_event(
    state: &AppState,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
) {
    let mut payload = route_event_payload(state, "admitted", request, route);
    payload.pending_queue = Some(state.queue.snapshot());
    payload.active_requests = Some(state.budget.snapshot().active_requests);
    record_runtime_event(state, "runtime.infer.admitted", request, payload);
}

fn record_started_event(
    state: &AppState,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
) {
    record_runtime_event(
        state,
        "runtime.infer.started",
        request,
        route_event_payload(state, "started", request, route),
    );
}

fn record_terminal_events(
    state: &AppState,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
    response: &RuntimeInferResponse,
) {
    let payload = response_event_payload(state, "completed", request, route, response);

    if response.route_state.contains("timeout") {
        let mut timeout_payload = payload.clone();
        timeout_payload.event_phase = "timeout".to_string();
        record_runtime_event(state, "runtime.infer.timeout", request, timeout_payload);
    }

    if response.route_state.contains("fallback") {
        let mut fallback_payload = payload.clone();
        fallback_payload.event_phase = "fallback".to_string();
        record_runtime_event(state, "runtime.infer.fallback", request, fallback_payload);
    }

    if response.rejected {
        let mut rejected_payload = payload.clone();
        rejected_payload.event_phase = "rejected".to_string();
        record_runtime_event(state, "runtime.infer.rejected", request, rejected_payload);
        return;
    }

    if response.route_state.contains("failed")
        || response.route_state.contains("unreachable")
        || response.route_state.contains("invalid-response")
    {
        let mut failed_payload = payload.clone();
        failed_payload.event_phase = "failed".to_string();
        record_runtime_event(state, "runtime.infer.failed", request, failed_payload);
        return;
    }

    record_runtime_event(state, "runtime.infer.completed", request, payload.clone());

    if response.degraded {
        let mut degraded_payload = payload;
        degraded_payload.event_phase = "degraded".to_string();
        record_runtime_event(state, "runtime.infer.degraded", request, degraded_payload);
    }
}

fn record_runtime_event(
    state: &AppState,
    kind: &str,
    request: &RuntimeInferRequest,
    payload: RuntimeBackendEventPayload,
) {
    let event_payload = serde_json::to_value(&payload).unwrap_or_else(|error| {
        json_value!({
            "event_phase": payload.event_phase,
            "backend_id": payload.backend_id,
            "resolved_backend": payload.resolved_backend,
            "route_state": payload.route_state,
            "reason": format!("failed to serialize runtime event payload: {error}"),
        })
    });
    state.events.record(
        kind,
        Some(&request.session_id),
        Some(&request.task_id),
        event_payload,
    );
}

fn response_note_value(response: &RuntimeInferResponse, prefix: &str) -> Option<String> {
    response
        .notes
        .iter()
        .find_map(|note| note.strip_prefix(prefix).map(str::to_string))
}

fn route_event_payload(
    state: &AppState,
    event_phase: &str,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
) -> RuntimeBackendEventPayload {
    RuntimeBackendEventPayload {
        event_phase: event_phase.to_string(),
        backend_id: route.selected_backend.clone(),
        resolved_backend: route.selected_backend.clone(),
        route_state: route.route_state.clone(),
        degraded: route.degraded,
        rejected: false,
        requested_backend: request.preferred_backend.clone(),
        fallback_backend: None,
        reason: Some(route.reason.clone()),
        model: request.model.clone(),
        estimated_latency_ms: None,
        pending_queue: Some(state.queue.snapshot()),
        active_requests: None,
        queue_saturated: Some(state.queue.is_saturated(state.budget.max_concurrency)),
        provider_id: None,
        runtime_service_id: None,
        provider_status: None,
        artifact_path: None,
    }
}

fn response_event_payload(
    state: &AppState,
    event_phase: &str,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
    response: &RuntimeInferResponse,
) -> RuntimeBackendEventPayload {
    RuntimeBackendEventPayload {
        event_phase: event_phase.to_string(),
        backend_id: response.backend_id.clone(),
        resolved_backend: route.selected_backend.clone(),
        route_state: response.route_state.clone(),
        degraded: response.degraded,
        rejected: response.rejected,
        requested_backend: request.preferred_backend.clone(),
        fallback_backend: if response.backend_id != route.selected_backend {
            Some(response.backend_id.clone())
        } else {
            None
        },
        reason: response.reason.clone(),
        model: request.model.clone(),
        estimated_latency_ms: response.estimated_latency_ms,
        pending_queue: Some(state.queue.snapshot()),
        active_requests: Some(state.budget.snapshot().active_requests),
        queue_saturated: response
            .queue_saturated
            .or(Some(state.queue.is_saturated(state.budget.max_concurrency))),
        provider_id: response.provider_id.clone(),
        runtime_service_id: response.runtime_service_id.clone(),
        provider_status: response.provider_status.clone(),
        artifact_path: response_note_value(response, "vendor_evidence_path="),
    }
}
