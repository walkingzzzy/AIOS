use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::{json as json_value, Value};

use aios_contracts::{
    methods, ExecutionToken, RuntimeInferRequest, RuntimeInferResponse, RuntimeQueueResponse,
    RuntimeRouteResolveRequest, RuntimeRouteResolveResponse, ServiceContractResponse,
    TraceQueryRequest,
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
        json(backend_state.scheduler.backends())
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
                    infer_state.events.record(
                        "runtime.infer.rejected",
                        Some(&request.session_id),
                        Some(&request.task_id),
                        json_value!({
                            "backend_id": response.backend_id,
                            "route_state": response.route_state,
                            "reason": response.reason,
                        }),
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
                infer_state.events.record(
                    "runtime.infer.rejected",
                    Some(&request.session_id),
                    Some(&request.task_id),
                    json_value!({
                        "backend_id": response.backend_id,
                        "route_state": response.route_state,
                        "reason": response.reason,
                        "pending": pending,
                        "max_concurrency": infer_state.budget.max_concurrency,
                    }),
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
                infer_state.events.record(
                    "runtime.infer.rejected",
                    Some(&request.session_id),
                    Some(&request.task_id),
                    json_value!({
                        "backend_id": response.backend_id,
                        "route_state": response.route_state,
                        "reason": response.reason,
                        "model": request.model,
                    }),
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
        record_terminal_events(&infer_state, &request, &response);
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
    state.events.record(
        "runtime.infer.submit",
        Some(&request.session_id),
        Some(&request.task_id),
        json_value!({
            "selected_backend": route.selected_backend,
            "route_state": route.route_state,
            "degraded": route.degraded,
            "reason": route.reason,
            "model": request.model,
        }),
    );
}

fn record_admitted_event(
    state: &AppState,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
) {
    state.events.record(
        "runtime.infer.admitted",
        Some(&request.session_id),
        Some(&request.task_id),
        json_value!({
            "selected_backend": route.selected_backend,
            "route_state": route.route_state,
            "pending": state.queue.snapshot(),
            "active_requests": state.budget.snapshot().active_requests,
        }),
    );
}

fn record_started_event(
    state: &AppState,
    request: &RuntimeInferRequest,
    route: &RuntimeRouteResolveResponse,
) {
    state.events.record(
        "runtime.infer.started",
        Some(&request.session_id),
        Some(&request.task_id),
        json_value!({
            "selected_backend": route.selected_backend,
            "route_state": route.route_state,
            "model": request.model,
        }),
    );
}

fn record_terminal_events(
    state: &AppState,
    request: &RuntimeInferRequest,
    response: &RuntimeInferResponse,
) {
    let payload = json_value!({
        "backend_id": response.backend_id,
        "route_state": response.route_state,
        "degraded": response.degraded,
        "rejected": response.rejected,
        "reason": response.reason,
        "estimated_latency_ms": response.estimated_latency_ms,
    });

    if response.route_state.contains("timeout") {
        state.events.record(
            "runtime.infer.timeout",
            Some(&request.session_id),
            Some(&request.task_id),
            payload.clone(),
        );
    }

    if response.route_state.contains("fallback") {
        state.events.record(
            "runtime.infer.fallback",
            Some(&request.session_id),
            Some(&request.task_id),
            payload.clone(),
        );
    }

    if response.rejected {
        state.events.record(
            "runtime.infer.rejected",
            Some(&request.session_id),
            Some(&request.task_id),
            payload.clone(),
        );
        return;
    }

    if response.route_state.contains("failed")
        || response.route_state.contains("unreachable")
        || response.route_state.contains("invalid-response")
    {
        state.events.record(
            "runtime.infer.failed",
            Some(&request.session_id),
            Some(&request.task_id),
            payload.clone(),
        );
        return;
    }

    state.events.record(
        "runtime.infer.completed",
        Some(&request.session_id),
        Some(&request.task_id),
        payload.clone(),
    );

    if response.degraded {
        state.events.record(
            "runtime.infer.degraded",
            Some(&request.session_id),
            Some(&request.task_id),
            payload,
        );
    }
}
