use std::collections::BTreeSet;

use serde_json::json;

use aios_contracts::{
    methods, ExecutionToken, HealthResponse, RuntimeEmbedRequest, RuntimeEmbedResponse,
    RuntimeEmbeddingRecord, RuntimeInferRequest, RuntimeInferResponse, RuntimeQueueResponse,
    RuntimeRerankRequest, RuntimeRerankResponse, RuntimeRerankResult,
};

use crate::{config::AiReadinessSummary, AppState};

const DEFAULT_EMBEDDING_VECTOR_DIMENSION: u32 = 8;
const EMBEDDING_ROUTE_STATE: &str = "provider-local-embedding";
const RERANK_ROUTE_STATE: &str = "provider-local-rerank";
const EMBEDDING_ALGORITHM: &str = "deterministic-embedding-v1";
const RERANK_ALGORITHM: &str = "lexical-overlap-v1";
const REMOTE_BACKEND_ID: &str = "openai-compatible-remote";
const REMOTE_EMBEDDING_BACKEND_ID: &str = "openai-compatible-remote-embedding";
const REMOTE_RERANK_BACKEND_ID: &str = "openai-compatible-remote-rerank";
const REMOTE_RUNTIME_SERVICE_ID: &str = "openai-compatible-endpoint";
const REMOTE_EMBEDDING_ROUTE_STATE: &str = "provider-remote-embedding";
const REMOTE_RERANK_ROUTE_STATE: &str = "provider-remote-rerank";
const REMOTE_EMBEDDING_ALGORITHM: &str = "openai-compatible-embedding-v1";
const REMOTE_RERANK_ALGORITHM: &str = "cosine-similarity-via-embedding-v1";

#[derive(Debug, Clone)]
struct LocalFailureContext {
    route_state: String,
    reason: String,
}

pub fn infer(
    state: &AppState,
    request: &RuntimeInferRequest,
) -> anyhow::Result<RuntimeInferResponse> {
    let _permit = state
        .concurrency_budget
        .try_acquire(methods::RUNTIME_INFER_SUBMIT)?;
    let token = request
        .execution_token
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("execution_token is required"))?;
    if request.prompt.trim().is_empty() {
        anyhow::bail!("prompt cannot be empty");
    }

    ensure_token_context(
        token,
        methods::RUNTIME_INFER_SUBMIT,
        &request.session_id,
        &request.task_id,
    )?;
    let verification = crate::clients::verify_token(state, token)?;
    if !verification.valid {
        anyhow::bail!("execution token rejected: {}", verification.reason);
    }

    let ai_readiness = state.config.load_ai_readiness_summary();
    let remote_endpoint = state.config.remote_endpoint_config();
    let queue_snapshot = crate::clients::fetch_runtime_queue(state).ok();
    let runtime_health = crate::clients::fetch_runtime_health(state).ok();
    if !ai_readiness.provider_enabled() {
        let response = build_provider_disabled_infer_response(
            state,
            request,
            token,
            &ai_readiness,
            queue_snapshot.as_ref(),
            runtime_health.as_ref(),
        );
        let _ = crate::clients::report_provider_health(state, "disabled", response.reason.clone());
        emit_infer_trace(state, request, &response);
        return Ok(response);
    }
    if ai_readiness.remote_only_preferred() && remote_endpoint.is_none() {
        let response = build_remote_route_unavailable_response(
            state,
            request,
            token,
            &ai_readiness,
            queue_snapshot.as_ref(),
            runtime_health.as_ref(),
            "remote-only route selected but endpoint is not configured",
        );
        let _ =
            crate::clients::report_provider_health(state, "unavailable", response.reason.clone());
        emit_infer_trace(state, request, &response);
        return Ok(response);
    }

    if should_use_remote_only(&ai_readiness, remote_endpoint.as_ref()) {
        let response = execute_remote_infer(
            state,
            request,
            token,
            &ai_readiness,
            remote_endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("remote endpoint is not configured"))?,
            None,
            queue_snapshot.as_ref(),
        )?;
        let _ = crate::clients::report_provider_health(state, "available", None);
        emit_infer_trace(state, request, &response);
        return Ok(response);
    }

    let mut remote_preference_failure: Option<String> = None;
    if should_use_remote_first(&ai_readiness, remote_endpoint.as_ref()) {
        let remote_result = execute_remote_infer(
            state,
            request,
            token,
            &ai_readiness,
            remote_endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("remote endpoint is not configured"))?,
            None,
            queue_snapshot.as_ref(),
        );
        match remote_result {
            Ok(response) => {
                let _ = crate::clients::report_provider_health(state, "available", None);
                emit_infer_trace(state, request, &response);
                return Ok(response);
            }
            Err(error) => {
                remote_preference_failure = Some(error.to_string());
            }
        }
    }

    let result = crate::clients::submit_runtime_infer(state, request);

    match result {
        Ok(mut response) => {
            if remote_preference_failure.is_none()
                && should_fallback_to_remote_from_response(
                    &response,
                    &ai_readiness,
                    remote_endpoint.as_ref(),
                )
            {
                let local_failure = LocalFailureContext {
                    route_state: response.route_state.clone(),
                    reason: response
                        .reason
                        .clone()
                        .unwrap_or_else(|| "local runtime rejected the request".to_string()),
                };
                let remote_result = execute_remote_infer(
                    state,
                    request,
                    token,
                    &ai_readiness,
                    remote_endpoint
                        .as_ref()
                        .ok_or_else(|| anyhow::anyhow!("remote endpoint is not configured"))?,
                    Some(local_failure),
                    None,
                );
                match remote_result {
                    Ok(fallback_response) => {
                        let _ = crate::clients::report_provider_health(
                            state,
                            "degraded",
                            Some(
                                "local runtime unavailable; remote endpoint served request"
                                    .to_string(),
                            ),
                        );
                        emit_infer_trace(state, request, &fallback_response);
                        return Ok(fallback_response);
                    }
                    Err(error) => {
                        let response = build_remote_failure_response(
                            state,
                            token,
                            &ai_readiness,
                            queue_snapshot.as_ref(),
                            runtime_health.as_ref(),
                            Some(LocalFailureContext {
                                route_state: response.route_state.clone(),
                                reason: response.reason.clone().unwrap_or_default(),
                            }),
                            error.to_string(),
                        );
                        let _ = crate::clients::report_provider_health(
                            state,
                            "unavailable",
                            response.reason.clone(),
                        );
                        emit_infer_trace(state, request, &response);
                        return Ok(response);
                    }
                }
            }

            let (_, _, runtime_dependency) =
                provider_runtime_dependency_state(runtime_health.as_ref());
            append_provider_operation_notes(&mut response.notes, "infer", runtime_dependency);
            append_ai_readiness_notes(&mut response.notes, &ai_readiness);
            attach_runtime_metadata(
                state,
                token,
                &mut response.notes,
                queue_snapshot.as_ref(),
                runtime_health.as_ref().map(|item| item.service_id.clone()),
            );
            response.provider_id = Some(state.config.provider_id.clone());
            response.runtime_service_id =
                runtime_health.as_ref().map(|item| item.service_id.clone());
            if let Some(remote_preference_failure) = remote_preference_failure.as_deref() {
                response.degraded = true;
                response.provider_status = Some("degraded".to_string());
                response.notes.push(format!(
                    "remote_preference_failure={remote_preference_failure}"
                ));
                let _ = crate::clients::report_provider_health(
                    state,
                    "degraded",
                    Some(remote_preference_failure.to_string()),
                );
            } else {
                response.provider_status = Some("available".to_string());
                let _ = crate::clients::report_provider_health(state, "available", None);
            }
            response.queue_saturated = queue_snapshot.as_ref().map(|item| item.saturated);
            response.runtime_budget = crate::clients::fetch_runtime_budget(state).ok();
            emit_infer_trace(state, request, &response);
            Ok(response)
        }
        Err(error) => {
            let error_text = error.to_string();
            let classification = classify_runtime_error(&error_text);

            if remote_preference_failure.is_none()
                && should_fallback_to_remote_from_error(
                    &classification,
                    &ai_readiness,
                    remote_endpoint.as_ref(),
                )
            {
                let remote_result = execute_remote_infer(
                    state,
                    request,
                    token,
                    &ai_readiness,
                    remote_endpoint
                        .as_ref()
                        .ok_or_else(|| anyhow::anyhow!("remote endpoint is not configured"))?,
                    Some(LocalFailureContext {
                        route_state: classification.route_state.to_string(),
                        reason: error_text.clone(),
                    }),
                    None,
                );
                match remote_result {
                    Ok(fallback_response) => {
                        let _ = crate::clients::report_provider_health(
                            state,
                            "degraded",
                            Some(
                                "local runtime unavailable; remote endpoint served request"
                                    .to_string(),
                            ),
                        );
                        emit_infer_trace(state, request, &fallback_response);
                        return Ok(fallback_response);
                    }
                    Err(remote_error) => {
                        let response = build_remote_failure_response(
                            state,
                            token,
                            &ai_readiness,
                            queue_snapshot.as_ref(),
                            runtime_health.as_ref(),
                            Some(LocalFailureContext {
                                route_state: classification.route_state.to_string(),
                                reason: error_text.clone(),
                            }),
                            remote_error.to_string(),
                        );
                        let _ = crate::clients::report_provider_health(
                            state,
                            "unavailable",
                            response.reason.clone(),
                        );
                        emit_infer_trace(state, request, &response);
                        return Ok(response);
                    }
                }
            }

            let _ = crate::clients::report_provider_health(
                state,
                classification.reported_status,
                Some(error_text.clone()),
            );

            let mut notes = Vec::new();
            let (_, _, runtime_dependency) =
                provider_runtime_dependency_state(runtime_health.as_ref());
            append_provider_operation_notes(&mut notes, "infer", runtime_dependency);
            append_ai_readiness_notes(&mut notes, &ai_readiness);
            if let Some(remote_preference_failure) = remote_preference_failure.as_deref() {
                notes.push(format!(
                    "remote_preference_failure={remote_preference_failure}"
                ));
            }
            attach_runtime_metadata(
                state,
                token,
                &mut notes,
                queue_snapshot.as_ref(),
                runtime_health.as_ref().map(|item| item.service_id.clone()),
            );

            let response = RuntimeInferResponse {
                backend_id: request
                    .preferred_backend
                    .clone()
                    .unwrap_or_else(|| "unresolved".to_string()),
                route_state: classification.route_state.to_string(),
                content: String::new(),
                degraded: classification.degraded,
                rejected: true,
                reason: Some(error_text),
                estimated_latency_ms: None,
                provider_id: Some(state.config.provider_id.clone()),
                runtime_service_id: runtime_health.as_ref().map(|item| item.service_id.clone()),
                provider_status: Some(classification.provider_status.to_string()),
                queue_saturated: queue_snapshot.as_ref().map(|item| item.saturated),
                runtime_budget: None,
                notes,
            };
            emit_infer_trace(state, request, &response);
            Ok(response)
        }
    }
}

fn should_use_remote_only(
    ai_readiness: &AiReadinessSummary,
    remote_endpoint: Option<&crate::config::RemoteEndpointConfig>,
) -> bool {
    remote_endpoint.is_some()
        && ai_readiness.remote_fallback_allowed()
        && ai_readiness.remote_only_preferred()
}

fn should_use_remote_first(
    ai_readiness: &AiReadinessSummary,
    remote_endpoint: Option<&crate::config::RemoteEndpointConfig>,
) -> bool {
    remote_endpoint.is_some()
        && ai_readiness.remote_fallback_allowed()
        && ai_readiness.remote_first_preferred()
        && !ai_readiness.remote_only_preferred()
}

fn preferred_backend_requests_remote(preferred_backend: Option<&String>) -> bool {
    preferred_backend
        .map(|value| value.trim().to_ascii_lowercase())
        .map(|value| value.contains("remote"))
        .unwrap_or(false)
}

fn should_fallback_to_remote_from_response(
    response: &RuntimeInferResponse,
    ai_readiness: &AiReadinessSummary,
    remote_endpoint: Option<&crate::config::RemoteEndpointConfig>,
) -> bool {
    remote_endpoint.is_some()
        && ai_readiness.remote_fallback_allowed()
        && response.rejected
        && local_response_requires_remote(response)
}

fn should_fallback_to_remote_from_error(
    classification: &RuntimeErrorClassification,
    ai_readiness: &AiReadinessSummary,
    remote_endpoint: Option<&crate::config::RemoteEndpointConfig>,
) -> bool {
    remote_endpoint.is_some()
        && ai_readiness.remote_fallback_allowed()
        && matches!(classification.route_state, "runtime-unavailable")
}

fn local_response_requires_remote(response: &RuntimeInferResponse) -> bool {
    if matches!(
        response.route_state.as_str(),
        "setup-pending"
            | "runtime-unavailable"
            | "backend-worker-required"
            | "backend-worker-unreachable"
            | "capability-rejected"
    ) {
        return true;
    }

    response
        .reason
        .as_deref()
        .map(str::to_ascii_lowercase)
        .map(|reason| {
            [
                "product mode requires",
                "backend is not executable",
                "worker is not executable",
                "failed to connect to",
                "connection refused",
                "no such file or directory",
            ]
            .iter()
            .any(|pattern| reason.contains(pattern))
        })
        .unwrap_or(false)
}

fn execute_remote_infer(
    state: &AppState,
    request: &RuntimeInferRequest,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    remote_endpoint: &crate::config::RemoteEndpointConfig,
    local_failure: Option<LocalFailureContext>,
    queue_snapshot: Option<&RuntimeQueueResponse>,
) -> anyhow::Result<RuntimeInferResponse> {
    let remote_result = crate::clients::submit_remote_infer(state, request, remote_endpoint)?;
    let provider_status = if local_failure.is_some() && !ai_readiness.remote_only_preferred() {
        "degraded"
    } else {
        "available"
    };
    let mut notes = vec![
        "provider_operation=infer".to_string(),
        "runtime_dependency=remote-endpoint".to_string(),
        format!("remote_backend={REMOTE_BACKEND_ID}"),
        format!("remote_model={}", remote_result.model),
        format!("remote_base_url={}", remote_endpoint.base_url),
        format!(
            "remote_api_key_configured={}",
            if remote_endpoint.api_key.is_some() {
                "true"
            } else {
                "false"
            }
        ),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    if let Some(total_tokens) = remote_result.usage_total_tokens {
        notes.push(format!("remote_total_tokens={total_tokens}"));
    }
    if let Some(local_failure) = local_failure {
        notes.push(format!(
            "local_failure_route_state={}",
            local_failure.route_state
        ));
        notes.push(format!("local_failure_reason={}", local_failure.reason));
    }
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        Some(REMOTE_RUNTIME_SERVICE_ID.to_string()),
    );

    Ok(RuntimeInferResponse {
        backend_id: REMOTE_BACKEND_ID.to_string(),
        route_state: ai_readiness.remote_route_state().to_string(),
        content: remote_result.content,
        degraded: provider_status == "degraded",
        rejected: false,
        reason: Some("served by openai-compatible remote endpoint".to_string()),
        estimated_latency_ms: Some(remote_result.estimated_latency_ms),
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: Some(REMOTE_RUNTIME_SERVICE_ID.to_string()),
        provider_status: Some(provider_status.to_string()),
        queue_saturated: None,
        runtime_budget: None,
        notes,
    })
}

fn build_remote_failure_response(
    state: &AppState,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_health: Option<&HealthResponse>,
    local_failure: Option<LocalFailureContext>,
    remote_error: String,
) -> RuntimeInferResponse {
    let mut notes = vec![
        "provider_operation=infer".to_string(),
        "runtime_dependency=remote-endpoint".to_string(),
        format!("remote_backend={REMOTE_BACKEND_ID}"),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    if let Some(local_failure) = local_failure.as_ref() {
        notes.push(format!(
            "local_failure_route_state={}",
            local_failure.route_state
        ));
        notes.push(format!("local_failure_reason={}", local_failure.reason));
    }
    notes.push(format!("remote_failure_reason={remote_error}"));
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
    );

    let reason = local_failure
        .map(|failure| {
            format!(
                "local route {} failed: {}; remote fallback failed: {}",
                failure.route_state, failure.reason, remote_error
            )
        })
        .unwrap_or_else(|| format!("remote fallback failed: {remote_error}"));

    RuntimeInferResponse {
        backend_id: REMOTE_BACKEND_ID.to_string(),
        route_state: "remote-unavailable".to_string(),
        content: String::new(),
        degraded: true,
        rejected: true,
        reason: Some(reason),
        estimated_latency_ms: None,
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
        provider_status: Some("degraded".to_string()),
        queue_saturated: queue_snapshot.map(|item| item.saturated),
        runtime_budget: None,
        notes,
    }
}

fn build_provider_disabled_infer_response(
    state: &AppState,
    request: &RuntimeInferRequest,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_health: Option<&HealthResponse>,
) -> RuntimeInferResponse {
    let mut notes = vec![
        "provider_operation=infer".to_string(),
        "runtime_dependency=disabled".to_string(),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        runtime_health.map(|item| item.service_id.clone()),
    );
    RuntimeInferResponse {
        backend_id: request
            .preferred_backend
            .clone()
            .unwrap_or_else(|| "disabled".to_string()),
        route_state: "disabled".to_string(),
        content: String::new(),
        degraded: false,
        rejected: true,
        reason: Some("AI provider disabled via runtime platform env".to_string()),
        estimated_latency_ms: None,
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health.map(|item| item.service_id.clone()),
        provider_status: Some("disabled".to_string()),
        queue_saturated: queue_snapshot.map(|item| item.saturated),
        runtime_budget: None,
        notes,
    }
}

fn build_remote_route_unavailable_response(
    state: &AppState,
    request: &RuntimeInferRequest,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_health: Option<&HealthResponse>,
    reason: &str,
) -> RuntimeInferResponse {
    let mut notes = vec![
        "provider_operation=infer".to_string(),
        "runtime_dependency=remote-endpoint".to_string(),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        runtime_health.map(|item| item.service_id.clone()),
    );
    RuntimeInferResponse {
        backend_id: request
            .preferred_backend
            .clone()
            .unwrap_or_else(|| REMOTE_BACKEND_ID.to_string()),
        route_state: "remote-unavailable".to_string(),
        content: String::new(),
        degraded: true,
        rejected: true,
        reason: Some(reason.to_string()),
        estimated_latency_ms: None,
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
        provider_status: Some("degraded".to_string()),
        queue_saturated: queue_snapshot.map(|item| item.saturated),
        runtime_budget: None,
        notes,
    }
}

fn execute_remote_embed(
    state: &AppState,
    request: &RuntimeEmbedRequest,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    remote_endpoint: &crate::config::RemoteEndpointConfig,
    queue_snapshot: Option<&RuntimeQueueResponse>,
) -> anyhow::Result<RuntimeEmbedResponse> {
    let remote_result =
        crate::clients::submit_remote_embed(state, &request.inputs, remote_endpoint)?;
    let crate::clients::RemoteEmbeddingResult {
        embeddings: remote_vectors,
        model: remote_model,
        vector_dimension,
        estimated_latency_ms,
        usage_total_tokens,
    } = remote_result;
    let embeddings = request
        .inputs
        .iter()
        .enumerate()
        .zip(remote_vectors)
        .map(|((index, input), vector)| RuntimeEmbeddingRecord {
            input_index: index,
            vector,
            text_length: input.chars().count(),
        })
        .collect::<Vec<_>>();
    let mut notes = vec![
        "provider_operation=embedding".to_string(),
        format!("provider_algorithm={REMOTE_EMBEDDING_ALGORITHM}"),
        format!("embedding_backend={REMOTE_EMBEDDING_BACKEND_ID}"),
        format!("embedding_count={}", embeddings.len()),
        format!("embedding_vector_dimension={vector_dimension}"),
        "backend_selection=remote-endpoint".to_string(),
        "runtime_dependency=remote-endpoint".to_string(),
        format!("remote_backend={REMOTE_EMBEDDING_BACKEND_ID}"),
        format!("remote_model={remote_model}"),
        format!("embedding_model={remote_model}"),
        format!("remote_estimated_latency_ms={estimated_latency_ms}"),
        format!("remote_base_url={}", remote_endpoint.base_url),
        format!(
            "remote_api_key_configured={}",
            if remote_endpoint.api_key.is_some() {
                "true"
            } else {
                "false"
            }
        ),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    if let Some(total_tokens) = usage_total_tokens {
        notes.push(format!("remote_total_tokens={total_tokens}"));
    }
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        Some(REMOTE_RUNTIME_SERVICE_ID.to_string()),
    );

    Ok(RuntimeEmbedResponse {
        backend_id: REMOTE_EMBEDDING_BACKEND_ID.to_string(),
        route_state: REMOTE_EMBEDDING_ROUTE_STATE.to_string(),
        vector_dimension,
        embeddings,
        degraded: false,
        rejected: false,
        reason: Some("served by openai-compatible remote embedding endpoint".to_string()),
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: Some(REMOTE_RUNTIME_SERVICE_ID.to_string()),
        provider_status: Some("available".to_string()),
        queue_saturated: None,
        runtime_budget: None,
        notes,
    })
}

fn build_remote_route_unavailable_embed_response(
    state: &AppState,
    request: &RuntimeEmbedRequest,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_health: Option<&HealthResponse>,
    reason: &str,
) -> RuntimeEmbedResponse {
    let mut notes = vec![
        "provider_operation=embedding".to_string(),
        format!("provider_algorithm={REMOTE_EMBEDDING_ALGORITHM}"),
        "runtime_dependency=remote-endpoint".to_string(),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
    );
    RuntimeEmbedResponse {
        backend_id: request
            .preferred_backend
            .clone()
            .unwrap_or_else(|| REMOTE_EMBEDDING_BACKEND_ID.to_string()),
        route_state: "remote-unavailable".to_string(),
        vector_dimension: 0,
        embeddings: Vec::new(),
        degraded: true,
        rejected: true,
        reason: Some(reason.to_string()),
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
        provider_status: Some("degraded".to_string()),
        queue_saturated: queue_snapshot.map(|item| item.saturated),
        runtime_budget: None,
        notes,
    }
}

fn build_remote_failure_embed_response(
    state: &AppState,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_health: Option<&HealthResponse>,
    remote_error: String,
) -> RuntimeEmbedResponse {
    let mut notes = vec![
        "provider_operation=embedding".to_string(),
        format!("provider_algorithm={REMOTE_EMBEDDING_ALGORITHM}"),
        "runtime_dependency=remote-endpoint".to_string(),
        format!("remote_failure_reason={remote_error}"),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
    );

    RuntimeEmbedResponse {
        backend_id: REMOTE_EMBEDDING_BACKEND_ID.to_string(),
        route_state: "remote-unavailable".to_string(),
        vector_dimension: 0,
        embeddings: Vec::new(),
        degraded: true,
        rejected: true,
        reason: Some(format!("remote embedding failed: {remote_error}")),
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
        provider_status: Some("degraded".to_string()),
        queue_saturated: queue_snapshot.map(|item| item.saturated),
        runtime_budget: None,
        notes,
    }
}

fn execute_remote_rerank(
    state: &AppState,
    request: &RuntimeRerankRequest,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    remote_endpoint: &crate::config::RemoteEndpointConfig,
    queue_snapshot: Option<&RuntimeQueueResponse>,
) -> anyhow::Result<RuntimeRerankResponse> {
    let mut inputs = Vec::with_capacity(request.documents.len() + 1);
    inputs.push(request.query.clone());
    inputs.extend(request.documents.iter().cloned());
    let remote_result = crate::clients::submit_remote_embed(state, &inputs, remote_endpoint)?;
    if remote_result.embeddings.len() != request.documents.len() + 1 {
        anyhow::bail!(
            "remote embedding endpoint returned {} vectors for {} rerank inputs",
            remote_result.embeddings.len(),
            request.documents.len() + 1
        );
    }
    let query_vector = remote_result
        .embeddings
        .first()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("remote rerank query embedding missing"))?;
    let results = rank_documents_by_embedding(
        &query_vector,
        &remote_result.embeddings[1..],
        &request.documents,
        request.top_k,
    );
    let mut notes = vec![
        "provider_operation=rerank".to_string(),
        format!("provider_algorithm={REMOTE_RERANK_ALGORITHM}"),
        format!("rerank_backend={REMOTE_RERANK_BACKEND_ID}"),
        format!("document_count={}", request.documents.len()),
        format!(
            "top_k_requested={}",
            request.top_k.unwrap_or(request.documents.len() as u32)
        ),
        format!("top_k_returned={}", results.len()),
        format!(
            "remote_embedding_dimension={}",
            remote_result.vector_dimension
        ),
        "backend_selection=remote-endpoint".to_string(),
        "runtime_dependency=remote-endpoint".to_string(),
        format!("remote_backend={REMOTE_RERANK_BACKEND_ID}"),
        format!("remote_model={}", remote_result.model),
        format!("rerank_model={}", remote_result.model),
        format!(
            "remote_estimated_latency_ms={}",
            remote_result.estimated_latency_ms
        ),
        format!("remote_base_url={}", remote_endpoint.base_url),
        format!(
            "remote_api_key_configured={}",
            if remote_endpoint.api_key.is_some() {
                "true"
            } else {
                "false"
            }
        ),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    if let Some(total_tokens) = remote_result.usage_total_tokens {
        notes.push(format!("remote_total_tokens={total_tokens}"));
    }
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        Some(REMOTE_RUNTIME_SERVICE_ID.to_string()),
    );

    Ok(RuntimeRerankResponse {
        backend_id: REMOTE_RERANK_BACKEND_ID.to_string(),
        route_state: REMOTE_RERANK_ROUTE_STATE.to_string(),
        results,
        degraded: false,
        rejected: false,
        reason: Some("served by openai-compatible remote rerank endpoint".to_string()),
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: Some(REMOTE_RUNTIME_SERVICE_ID.to_string()),
        provider_status: Some("available".to_string()),
        queue_saturated: None,
        runtime_budget: None,
        notes,
    })
}

fn build_remote_route_unavailable_rerank_response(
    state: &AppState,
    request: &RuntimeRerankRequest,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_health: Option<&HealthResponse>,
    reason: &str,
) -> RuntimeRerankResponse {
    let mut notes = vec![
        "provider_operation=rerank".to_string(),
        format!("provider_algorithm={REMOTE_RERANK_ALGORITHM}"),
        "runtime_dependency=remote-endpoint".to_string(),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
    );
    RuntimeRerankResponse {
        backend_id: request
            .preferred_backend
            .clone()
            .unwrap_or_else(|| REMOTE_RERANK_BACKEND_ID.to_string()),
        route_state: "remote-unavailable".to_string(),
        results: Vec::new(),
        degraded: true,
        rejected: true,
        reason: Some(reason.to_string()),
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
        provider_status: Some("degraded".to_string()),
        queue_saturated: queue_snapshot.map(|item| item.saturated),
        runtime_budget: None,
        notes,
    }
}

fn build_remote_failure_rerank_response(
    state: &AppState,
    token: &ExecutionToken,
    ai_readiness: &AiReadinessSummary,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_health: Option<&HealthResponse>,
    remote_error: String,
) -> RuntimeRerankResponse {
    let mut notes = vec![
        "provider_operation=rerank".to_string(),
        format!("provider_algorithm={REMOTE_RERANK_ALGORITHM}"),
        "runtime_dependency=remote-endpoint".to_string(),
        format!("remote_failure_reason={remote_error}"),
    ];
    append_ai_readiness_notes(&mut notes, ai_readiness);
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot,
        runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
    );

    RuntimeRerankResponse {
        backend_id: REMOTE_RERANK_BACKEND_ID.to_string(),
        route_state: "remote-unavailable".to_string(),
        results: Vec::new(),
        degraded: true,
        rejected: true,
        reason: Some(format!("remote rerank failed: {remote_error}")),
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health
            .map(|item| item.service_id.clone())
            .or_else(|| Some(REMOTE_RUNTIME_SERVICE_ID.to_string())),
        provider_status: Some("degraded".to_string()),
        queue_saturated: queue_snapshot.map(|item| item.saturated),
        runtime_budget: None,
        notes,
    }
}

fn append_ai_readiness_notes(notes: &mut Vec<String>, ai_readiness: &AiReadinessSummary) {
    notes.push(format!(
        "ai_readiness_source={}",
        if ai_readiness.source_available {
            "published"
        } else {
            "default"
        }
    ));
    notes.push(format!(
        "ai_readiness_state={}",
        ai_readiness.state.as_deref().unwrap_or("unknown")
    ));
    notes.push(format!(
        "ai_endpoint_configured={}",
        if ai_readiness.endpoint_configured {
            "true"
        } else {
            "false"
        }
    ));
    if let Some(reason) = ai_readiness.reason.as_deref() {
        notes.push(format!("ai_readiness_reason={reason}"));
    }
    if let Some(next_action) = ai_readiness.next_action.as_deref() {
        notes.push(format!("ai_next_action={next_action}"));
    }
    if let Some(ai_mode) = ai_readiness.ai_mode.as_deref() {
        notes.push(format!("ai_mode={ai_mode}"));
    }
    notes.push(format!(
        "route_preference={}",
        ai_readiness.effective_route_preference()
    ));
    if let Some(local_model_count) = ai_readiness.local_model_count {
        notes.push(format!("local_model_count={local_model_count}"));
    }
}

pub fn embed(
    state: &AppState,
    request: &RuntimeEmbedRequest,
) -> anyhow::Result<RuntimeEmbedResponse> {
    let _permit = state
        .concurrency_budget
        .try_acquire(methods::RUNTIME_EMBED_VECTORIZE)?;
    let token = request
        .execution_token
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("execution_token is required"))?;
    if request.inputs.is_empty() {
        anyhow::bail!("inputs cannot be empty");
    }
    if request.inputs.iter().any(|value| value.trim().is_empty()) {
        anyhow::bail!("inputs cannot contain blank items");
    }

    ensure_token_context(
        token,
        methods::RUNTIME_EMBED_VECTORIZE,
        &request.session_id,
        &request.task_id,
    )?;
    let verification = crate::clients::verify_token(state, token)?;
    if !verification.valid {
        anyhow::bail!("execution token rejected: {}", verification.reason);
    }

    let ai_readiness = state.config.load_ai_readiness_summary();
    let queue_snapshot = crate::clients::fetch_runtime_queue(state).ok();
    let runtime_health = crate::clients::fetch_runtime_health(state).ok();
    let runtime_budget = crate::clients::fetch_runtime_budget(state).ok();
    let remote_endpoint = state
        .config
        .remote_embedding_endpoint_config(request.model.as_deref());
    let explicit_remote_backend =
        preferred_backend_requests_remote(request.preferred_backend.as_ref());
    if !ai_readiness.provider_enabled() {
        let response = RuntimeEmbedResponse {
            backend_id: state.config.embedding_backend.clone(),
            route_state: "disabled".to_string(),
            vector_dimension: DEFAULT_EMBEDDING_VECTOR_DIMENSION,
            embeddings: Vec::new(),
            degraded: false,
            rejected: true,
            reason: Some("AI provider disabled via runtime platform env".to_string()),
            provider_id: Some(state.config.provider_id.clone()),
            runtime_service_id: None,
            provider_status: Some("disabled".to_string()),
            queue_saturated: None,
            runtime_budget: None,
            notes: vec![
                "provider_operation=embedding".to_string(),
                "runtime_dependency=disabled".to_string(),
            ],
        };
        emit_embedding_trace(state, request, &response);
        return Ok(response);
    }
    if (ai_readiness.remote_only_preferred() || explicit_remote_backend)
        && remote_endpoint.is_none()
    {
        let response = build_remote_route_unavailable_embed_response(
            state,
            request,
            token,
            &ai_readiness,
            queue_snapshot.as_ref(),
            runtime_health.as_ref(),
            if ai_readiness.remote_only_preferred() {
                "remote-only route selected but embedding endpoint is not configured"
            } else {
                "remote embedding backend requested but endpoint is not configured"
            },
        );
        emit_embedding_trace(state, request, &response);
        return Ok(response);
    }

    let mut remote_preference_failure: Option<String> = None;
    if explicit_remote_backend || should_use_remote_only(&ai_readiness, remote_endpoint.as_ref()) {
        let response = execute_remote_embed(
            state,
            request,
            token,
            &ai_readiness,
            remote_endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("remote embedding endpoint is not configured"))?,
            queue_snapshot.as_ref(),
        );
        match response {
            Ok(response) => {
                emit_embedding_trace(state, request, &response);
                return Ok(response);
            }
            Err(error) if explicit_remote_backend && !ai_readiness.remote_only_preferred() => {
                remote_preference_failure = Some(error.to_string());
            }
            Err(error) => {
                let response = build_remote_failure_embed_response(
                    state,
                    token,
                    &ai_readiness,
                    queue_snapshot.as_ref(),
                    runtime_health.as_ref(),
                    error.to_string(),
                );
                emit_embedding_trace(state, request, &response);
                return Ok(response);
            }
        }
    } else if should_use_remote_first(&ai_readiness, remote_endpoint.as_ref()) {
        match execute_remote_embed(
            state,
            request,
            token,
            &ai_readiness,
            remote_endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("remote embedding endpoint is not configured"))?,
            queue_snapshot.as_ref(),
        ) {
            Ok(response) => {
                emit_embedding_trace(state, request, &response);
                return Ok(response);
            }
            Err(error) => {
                remote_preference_failure = Some(error.to_string());
            }
        }
    }

    let (provider_status, degraded, runtime_dependency) =
        provider_runtime_dependency_state(runtime_health.as_ref());
    let vector_dimension = DEFAULT_EMBEDDING_VECTOR_DIMENSION;
    let (backend_id, backend_source) = resolve_backend_id(
        request.preferred_backend.as_ref(),
        &state.config.embedding_backend,
    );
    let embeddings = build_embedding_records(&request.inputs, vector_dimension as usize);

    let mut notes = embedding_notes(
        &backend_id,
        backend_source,
        vector_dimension,
        embeddings.len(),
        request.model.as_deref(),
        runtime_dependency,
    );
    if let Some(remote_preference_failure) = remote_preference_failure.as_deref() {
        notes.push(format!(
            "remote_preference_failure={remote_preference_failure}"
        ));
    }
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot.as_ref(),
        runtime_health.as_ref().map(|item| item.service_id.clone()),
    );

    let provider_status = if remote_preference_failure.is_some() {
        "degraded"
    } else {
        provider_status
    };
    let response = RuntimeEmbedResponse {
        backend_id,
        route_state: EMBEDDING_ROUTE_STATE.to_string(),
        vector_dimension,
        embeddings,
        degraded: degraded || remote_preference_failure.is_some(),
        rejected: false,
        reason: None,
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health.as_ref().map(|item| item.service_id.clone()),
        provider_status: Some(provider_status.to_string()),
        queue_saturated: queue_snapshot.as_ref().map(|item| item.saturated),
        runtime_budget,
        notes,
    };
    emit_embedding_trace(state, request, &response);

    Ok(response)
}

pub fn rerank(
    state: &AppState,
    request: &RuntimeRerankRequest,
) -> anyhow::Result<RuntimeRerankResponse> {
    let _permit = state
        .concurrency_budget
        .try_acquire(methods::RUNTIME_RERANK_SCORE)?;
    let token = request
        .execution_token
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("execution_token is required"))?;
    if request.query.trim().is_empty() {
        anyhow::bail!("query cannot be empty");
    }
    if request.documents.is_empty() {
        anyhow::bail!("documents cannot be empty");
    }
    if request
        .documents
        .iter()
        .any(|value| value.trim().is_empty())
    {
        anyhow::bail!("documents cannot contain blank items");
    }

    ensure_token_context(
        token,
        methods::RUNTIME_RERANK_SCORE,
        &request.session_id,
        &request.task_id,
    )?;
    let verification = crate::clients::verify_token(state, token)?;
    if !verification.valid {
        anyhow::bail!("execution token rejected: {}", verification.reason);
    }

    let ai_readiness = state.config.load_ai_readiness_summary();
    let queue_snapshot = crate::clients::fetch_runtime_queue(state).ok();
    let runtime_health = crate::clients::fetch_runtime_health(state).ok();
    let runtime_budget = crate::clients::fetch_runtime_budget(state).ok();
    let remote_endpoint = state
        .config
        .remote_rerank_endpoint_config(request.model.as_deref());
    let explicit_remote_backend =
        preferred_backend_requests_remote(request.preferred_backend.as_ref());
    if !ai_readiness.provider_enabled() {
        let response = RuntimeRerankResponse {
            backend_id: state.config.rerank_backend.clone(),
            route_state: "disabled".to_string(),
            results: Vec::new(),
            degraded: false,
            rejected: true,
            reason: Some("AI provider disabled via runtime platform env".to_string()),
            provider_id: Some(state.config.provider_id.clone()),
            runtime_service_id: None,
            provider_status: Some("disabled".to_string()),
            queue_saturated: None,
            runtime_budget: None,
            notes: vec![
                "provider_operation=rerank".to_string(),
                "runtime_dependency=disabled".to_string(),
            ],
        };
        emit_rerank_trace(state, request, &response);
        return Ok(response);
    }
    if (ai_readiness.remote_only_preferred() || explicit_remote_backend)
        && remote_endpoint.is_none()
    {
        let response = build_remote_route_unavailable_rerank_response(
            state,
            request,
            token,
            &ai_readiness,
            queue_snapshot.as_ref(),
            runtime_health.as_ref(),
            if ai_readiness.remote_only_preferred() {
                "remote-only route selected but rerank endpoint is not configured"
            } else {
                "remote rerank backend requested but endpoint is not configured"
            },
        );
        emit_rerank_trace(state, request, &response);
        return Ok(response);
    }

    let mut remote_preference_failure: Option<String> = None;
    if explicit_remote_backend || should_use_remote_only(&ai_readiness, remote_endpoint.as_ref()) {
        let response = execute_remote_rerank(
            state,
            request,
            token,
            &ai_readiness,
            remote_endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("remote rerank endpoint is not configured"))?,
            queue_snapshot.as_ref(),
        );
        match response {
            Ok(response) => {
                emit_rerank_trace(state, request, &response);
                return Ok(response);
            }
            Err(error) if explicit_remote_backend && !ai_readiness.remote_only_preferred() => {
                remote_preference_failure = Some(error.to_string());
            }
            Err(error) => {
                let response = build_remote_failure_rerank_response(
                    state,
                    token,
                    &ai_readiness,
                    queue_snapshot.as_ref(),
                    runtime_health.as_ref(),
                    error.to_string(),
                );
                emit_rerank_trace(state, request, &response);
                return Ok(response);
            }
        }
    } else if should_use_remote_first(&ai_readiness, remote_endpoint.as_ref()) {
        match execute_remote_rerank(
            state,
            request,
            token,
            &ai_readiness,
            remote_endpoint
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("remote rerank endpoint is not configured"))?,
            queue_snapshot.as_ref(),
        ) {
            Ok(response) => {
                emit_rerank_trace(state, request, &response);
                return Ok(response);
            }
            Err(error) => {
                remote_preference_failure = Some(error.to_string());
            }
        }
    }

    let (provider_status, degraded, runtime_dependency) =
        provider_runtime_dependency_state(runtime_health.as_ref());
    let (backend_id, backend_source) = resolve_backend_id(
        request.preferred_backend.as_ref(),
        &state.config.rerank_backend,
    );
    let results = rank_documents(&request.query, &request.documents, request.top_k);

    let mut notes = rerank_notes(
        &backend_id,
        backend_source,
        request.documents.len(),
        results.len(),
        request.top_k,
        request.model.as_deref(),
        runtime_dependency,
    );
    if let Some(remote_preference_failure) = remote_preference_failure.as_deref() {
        notes.push(format!(
            "remote_preference_failure={remote_preference_failure}"
        ));
    }
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot.as_ref(),
        runtime_health.as_ref().map(|item| item.service_id.clone()),
    );

    let provider_status = if remote_preference_failure.is_some() {
        "degraded"
    } else {
        provider_status
    };
    let response = RuntimeRerankResponse {
        backend_id,
        route_state: RERANK_ROUTE_STATE.to_string(),
        results,
        degraded: degraded || remote_preference_failure.is_some(),
        rejected: false,
        reason: None,
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health.as_ref().map(|item| item.service_id.clone()),
        provider_status: Some(provider_status.to_string()),
        queue_saturated: queue_snapshot.as_ref().map(|item| item.saturated),
        runtime_budget,
        notes,
    };
    emit_rerank_trace(state, request, &response);

    Ok(response)
}

fn resolve_backend_id(
    preferred_backend: Option<&String>,
    configured_backend: &str,
) -> (String, &'static str) {
    preferred_backend
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
        .map(|value| (value.to_string(), "preferred-backend"))
        .unwrap_or_else(|| (configured_backend.to_string(), "provider-config"))
}

fn provider_runtime_dependency_state(
    runtime_health: Option<&HealthResponse>,
) -> (&'static str, bool, &'static str) {
    if runtime_health.is_some() {
        ("available", false, "available")
    } else {
        ("degraded", true, "unavailable")
    }
}

fn append_provider_operation_notes(
    notes: &mut Vec<String>,
    operation: &str,
    runtime_dependency: &str,
) {
    notes.push(format!("provider_operation={operation}"));
    notes.push(format!("runtime_dependency={runtime_dependency}"));
}

fn embedding_notes(
    backend_id: &str,
    backend_source: &str,
    vector_dimension: u32,
    embedding_count: usize,
    model: Option<&str>,
    runtime_dependency: &str,
) -> Vec<String> {
    let mut notes = vec![
        "provider_operation=embedding".to_string(),
        format!("provider_algorithm={EMBEDDING_ALGORITHM}"),
        format!("embedding_backend={backend_id}"),
        format!("backend_selection={backend_source}"),
        format!("embedding_vector_dimension={vector_dimension}"),
        format!("embedding_count={embedding_count}"),
        format!("runtime_dependency={runtime_dependency}"),
    ];
    push_optional_note(&mut notes, "embedding_model", model);
    notes
}

fn rerank_notes(
    backend_id: &str,
    backend_source: &str,
    document_count: usize,
    result_count: usize,
    top_k: Option<u32>,
    model: Option<&str>,
    runtime_dependency: &str,
) -> Vec<String> {
    let mut notes = vec![
        "provider_operation=rerank".to_string(),
        format!("provider_algorithm={RERANK_ALGORITHM}"),
        format!("rerank_backend={backend_id}"),
        format!("backend_selection={backend_source}"),
        format!("document_count={document_count}"),
        format!("top_k_requested={}", top_k.unwrap_or(document_count as u32)),
        format!("top_k_returned={result_count}"),
        format!("runtime_dependency={runtime_dependency}"),
    ];
    push_optional_note(&mut notes, "rerank_model", model);
    notes
}

fn push_optional_note(notes: &mut Vec<String>, key: &str, value: Option<&str>) {
    if let Some(value) = value.map(str::trim).filter(|value| !value.is_empty()) {
        notes.push(format!("{key}={value}"));
    }
}

fn ensure_token_context(
    token: &ExecutionToken,
    capability_id: &str,
    session_id: &str,
    task_id: &str,
) -> anyhow::Result<()> {
    if token.capability_id != capability_id {
        anyhow::bail!(
            "execution token capability {} does not match {}",
            token.capability_id,
            capability_id
        );
    }
    if token.execution_location != "local" {
        anyhow::bail!("runtime-local-inference provider only supports local execution tokens");
    }
    if token.session_id != session_id {
        anyhow::bail!(
            "request session_id {} does not match token session_id {}",
            session_id,
            token.session_id
        );
    }
    if token.task_id != task_id {
        anyhow::bail!(
            "request task_id {} does not match token task_id {}",
            task_id,
            token.task_id
        );
    }

    Ok(())
}

fn attach_runtime_metadata(
    state: &AppState,
    token: &ExecutionToken,
    notes: &mut Vec<String>,
    queue_snapshot: Option<&RuntimeQueueResponse>,
    runtime_service_id: Option<String>,
) {
    notes.push(format!(
        "provider_in_flight={}",
        state.concurrency_budget.in_flight()
    ));
    notes.push(format!(
        "provider_max_concurrency={}",
        state.config.max_concurrency
    ));
    if let Some(queue) = queue_snapshot {
        notes.push(format!("runtime_pending={}", queue.pending));
        notes.push(format!("runtime_available_slots={}", queue.available_slots));
    }
    if let Some(taint_summary) = token.taint_summary.as_deref() {
        notes.push(format!("token_taint={taint_summary}"));
    }
    if let Some(service_id) = runtime_service_id {
        notes.push(format!("runtime_service_id={service_id}"));
    } else {
        notes.push("runtime_service_id=unavailable".to_string());
    }
}

fn build_embedding_records(inputs: &[String], dimension: usize) -> Vec<RuntimeEmbeddingRecord> {
    inputs
        .iter()
        .enumerate()
        .map(|(index, input)| RuntimeEmbeddingRecord {
            input_index: index,
            vector: deterministic_embedding(input, dimension),
            text_length: input.chars().count(),
        })
        .collect()
}

fn rank_documents(
    query: &str,
    documents: &[String],
    top_k: Option<u32>,
) -> Vec<RuntimeRerankResult> {
    let mut results = documents
        .iter()
        .enumerate()
        .map(|(index, document)| RuntimeRerankResult {
            document_index: index,
            score: lexical_rerank_score(query, document),
            document: document.clone(),
        })
        .collect::<Vec<_>>();
    results.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| left.document_index.cmp(&right.document_index))
    });
    if let Some(top_k) = top_k {
        results.truncate(top_k.max(1) as usize);
    }
    results
}

fn rank_documents_by_embedding(
    query_vector: &[f32],
    document_vectors: &[Vec<f32>],
    documents: &[String],
    top_k: Option<u32>,
) -> Vec<RuntimeRerankResult> {
    let mut results = documents
        .iter()
        .enumerate()
        .map(|(index, document)| RuntimeRerankResult {
            document_index: index,
            score: document_vectors
                .get(index)
                .map(|vector| cosine_similarity(query_vector, vector))
                .unwrap_or(0.0),
            document: document.clone(),
        })
        .collect::<Vec<_>>();
    results.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| left.document_index.cmp(&right.document_index))
    });
    if let Some(top_k) = top_k {
        results.truncate(top_k.max(1) as usize);
    }
    results
}

fn cosine_similarity(left: &[f32], right: &[f32]) -> f32 {
    if left.is_empty() || right.is_empty() || left.len() != right.len() {
        return 0.0;
    }

    let dot = left
        .iter()
        .zip(right.iter())
        .map(|(left, right)| left * right)
        .sum::<f32>();
    let left_norm = left.iter().map(|value| value * value).sum::<f32>().sqrt();
    let right_norm = right.iter().map(|value| value * value).sum::<f32>().sqrt();
    if left_norm == 0.0 || right_norm == 0.0 {
        return 0.0;
    }
    dot / (left_norm * right_norm)
}

fn emit_infer_trace(
    state: &AppState,
    request: &RuntimeInferRequest,
    response: &RuntimeInferResponse,
) {
    crate::emit_trace(
        state,
        "provider.runtime.infer.result",
        json!({
            "capability_id": methods::RUNTIME_INFER_SUBMIT,
            "session_id": request.session_id,
            "task_id": request.task_id,
            "requested_backend": request.preferred_backend,
            "backend_id": response.backend_id,
            "route_state": response.route_state,
            "degraded": response.degraded,
            "rejected": response.rejected,
            "provider_status": response.provider_status,
            "runtime_service_id": response.runtime_service_id,
            "queue_saturated": response.queue_saturated,
            "estimated_latency_ms": response.estimated_latency_ms,
            "model": request.model,
            "reason": response.reason,
        }),
        response.notes.clone(),
    );
}

fn emit_embedding_trace(
    state: &AppState,
    request: &RuntimeEmbedRequest,
    response: &RuntimeEmbedResponse,
) {
    crate::emit_trace(
        state,
        "provider.runtime.embed.result",
        json!({
            "capability_id": methods::RUNTIME_EMBED_VECTORIZE,
            "session_id": request.session_id,
            "task_id": request.task_id,
            "requested_backend": request.preferred_backend,
            "backend_id": response.backend_id,
            "route_state": response.route_state,
            "vector_dimension": response.vector_dimension,
            "embedding_count": response.embeddings.len(),
            "degraded": response.degraded,
            "rejected": response.rejected,
            "provider_status": response.provider_status,
            "runtime_service_id": response.runtime_service_id,
            "queue_saturated": response.queue_saturated,
            "model": request.model,
            "reason": response.reason,
        }),
        response.notes.clone(),
    );
}

fn emit_rerank_trace(
    state: &AppState,
    request: &RuntimeRerankRequest,
    response: &RuntimeRerankResponse,
) {
    crate::emit_trace(
        state,
        "provider.runtime.rerank.result",
        json!({
            "capability_id": methods::RUNTIME_RERANK_SCORE,
            "session_id": request.session_id,
            "task_id": request.task_id,
            "requested_backend": request.preferred_backend,
            "backend_id": response.backend_id,
            "route_state": response.route_state,
            "result_count": response.results.len(),
            "top_document_index": response.results.first().map(|item| item.document_index),
            "top_score": response.results.first().map(|item| item.score),
            "degraded": response.degraded,
            "rejected": response.rejected,
            "provider_status": response.provider_status,
            "runtime_service_id": response.runtime_service_id,
            "queue_saturated": response.queue_saturated,
            "model": request.model,
            "reason": response.reason,
        }),
        response.notes.clone(),
    );
}

fn deterministic_embedding(text: &str, dimension: usize) -> Vec<f32> {
    let mut vector = vec![0.0f32; dimension.max(1)];
    for (index, byte) in text.bytes().enumerate() {
        let bucket = index % vector.len();
        let centered = (byte as f32 / 255.0) * 2.0 - 1.0;
        vector[bucket] += centered;
    }

    let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
    if norm > 0.0 {
        for value in &mut vector {
            *value /= norm;
        }
    }

    vector
}

fn lexical_rerank_score(query: &str, document: &str) -> f32 {
    let query_tokens = lexical_tokens(query);
    let document_tokens = lexical_tokens(document);
    if query_tokens.is_empty() || document_tokens.is_empty() {
        return 0.0;
    }

    let overlap = query_tokens.intersection(&document_tokens).count() as f32;
    let coverage = overlap / query_tokens.len() as f32;
    let density = overlap / document_tokens.len() as f32;
    let exact_phrase_bonus = if document
        .to_ascii_lowercase()
        .contains(&query.to_ascii_lowercase())
    {
        0.25
    } else {
        0.0
    };

    coverage * 0.7 + density * 0.3 + exact_phrase_bonus
}

fn lexical_tokens(input: &str) -> BTreeSet<String> {
    input
        .split(|character: char| !character.is_alphanumeric())
        .map(|token| token.trim().to_ascii_lowercase())
        .filter(|token| !token.is_empty())
        .collect()
}

struct RuntimeErrorClassification {
    route_state: &'static str,
    degraded: bool,
    provider_status: &'static str,
    reported_status: &'static str,
}

fn classify_runtime_error(message: &str) -> RuntimeErrorClassification {
    let message_lower = message.to_ascii_lowercase();

    if message_lower.contains("remote rpc error") {
        return RuntimeErrorClassification {
            route_state: "runtime-rejected",
            degraded: false,
            provider_status: "available",
            reported_status: "available",
        };
    }

    let runtime_unavailable_patterns = [
        "failed to connect to",
        "no such file or directory",
        "connection refused",
        "connection reset",
        "broken pipe",
        "rpc response missing result",
        "unix rpc transport is not supported",
        "timed out",
    ];
    if runtime_unavailable_patterns
        .iter()
        .any(|pattern| message_lower.contains(pattern))
    {
        return RuntimeErrorClassification {
            route_state: "runtime-unavailable",
            degraded: true,
            provider_status: "degraded",
            reported_status: "unavailable",
        };
    }

    RuntimeErrorClassification {
        route_state: "runtime-error",
        degraded: true,
        provider_status: "degraded",
        reported_status: "unavailable",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::AiReadinessSummary;

    #[test]
    fn classify_runtime_error_marks_socket_failures_as_unavailable() {
        let classification = classify_runtime_error(
            "failed to connect to /run/aios/runtimed/runtimed.sock: No such file or directory",
        );

        assert_eq!(classification.route_state, "runtime-unavailable");
        assert!(classification.degraded);
        assert_eq!(classification.reported_status, "unavailable");
    }

    #[test]
    fn classify_runtime_error_keeps_remote_rpc_rejections_available() {
        let classification =
            classify_runtime_error("remote rpc error -32603: internal error: backend failed");

        assert_eq!(classification.route_state, "runtime-rejected");
        assert!(!classification.degraded);
        assert_eq!(classification.provider_status, "available");
    }

    #[test]
    fn classify_runtime_error_marks_connection_refused_as_unavailable() {
        let classification = classify_runtime_error(
            "failed to read provider response: Connection refused (os error 111)",
        );

        assert_eq!(classification.route_state, "runtime-unavailable");
        assert!(classification.degraded);
        assert_eq!(classification.reported_status, "unavailable");
    }

    #[test]
    fn classify_runtime_error_prioritizes_remote_rpc_response_over_local_io_keywords() {
        let classification = classify_runtime_error(
            "remote rpc error -32603: internal error: backend wrapper failed: No such file or directory",
        );

        assert_eq!(classification.route_state, "runtime-rejected");
        assert!(!classification.degraded);
        assert_eq!(classification.provider_status, "available");
    }

    #[test]
    fn deterministic_embedding_is_stable_and_normalized() {
        let vector = deterministic_embedding("device provider smoke", 8);

        assert_eq!(vector.len(), 8);
        let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 0.001);
        assert_eq!(vector, deterministic_embedding("device provider smoke", 8));
    }

    #[test]
    fn lexical_rerank_score_prefers_exact_overlap() {
        let strong = lexical_rerank_score(
            "runtime provider health",
            "runtime provider health summary and diagnostics",
        );
        let weak = lexical_rerank_score("runtime provider health", "shell notification center");

        assert!(strong > weak);
    }

    #[test]
    fn resolve_backend_id_prefers_non_empty_request_override() {
        let (backend_id, source) =
            resolve_backend_id(Some(&" custom-backend ".to_string()), "local-embedding");

        assert_eq!(backend_id, "custom-backend");
        assert_eq!(source, "preferred-backend");
    }

    #[test]
    fn missing_runtime_health_marks_provider_as_degraded() {
        let (provider_status, degraded, runtime_dependency) =
            provider_runtime_dependency_state(None);

        assert_eq!(provider_status, "degraded");
        assert!(degraded);
        assert_eq!(runtime_dependency, "unavailable");
    }

    #[test]
    fn embedding_notes_use_formal_markers() {
        let notes = embedding_notes(
            "local-embedding",
            "provider-config",
            DEFAULT_EMBEDDING_VECTOR_DIMENSION,
            2,
            Some("smoke-embedding-model"),
            "available",
        );

        assert!(notes
            .iter()
            .any(|note| note == "provider_operation=embedding"));
        assert!(notes
            .iter()
            .any(|note| note == "provider_algorithm=deterministic-embedding-v1"));
        assert!(notes
            .iter()
            .all(|note| !note.to_ascii_lowercase().contains("skeleton")));
    }

    #[test]
    fn rank_documents_applies_top_k_and_stable_tie_breaks() {
        let documents = vec![
            "provider health summary with audit notes".to_string(),
            "provider health summary with registry notes".to_string(),
            "shell compositor backlog".to_string(),
        ];

        let results = rank_documents("provider health summary", &documents, Some(2));

        assert_eq!(results.len(), 2);
        assert_eq!(results[0].document_index, 0);
        assert_eq!(results[1].document_index, 1);
        assert!(results[0].score >= results[1].score);
    }

    #[test]
    fn rank_documents_by_embedding_prefers_closest_vector() {
        let query = vec![1.0, 0.0, 0.0];
        let vectors = vec![
            vec![0.95, 0.05, 0.0],
            vec![0.2, 0.8, 0.0],
            vec![0.0, 0.0, 1.0],
        ];
        let documents = vec![
            "provider health summary".to_string(),
            "device metadata stream".to_string(),
            "shell panel route".to_string(),
        ];

        let results = rank_documents_by_embedding(&query, &vectors, &documents, Some(2));

        assert_eq!(results.len(), 2);
        assert_eq!(results[0].document_index, 0);
        assert!(results[0].score > results[1].score);
    }

    #[test]
    fn preferred_backend_requests_remote_for_remote_names() {
        assert!(preferred_backend_requests_remote(Some(
            &"openai-compatible-remote".to_string()
        )));
        assert!(preferred_backend_requests_remote(Some(
            &"REMOTE-gpu".to_string()
        )));
        assert!(!preferred_backend_requests_remote(Some(
            &"local-embedding".to_string()
        )));
        assert!(!preferred_backend_requests_remote(None));
    }

    #[test]
    fn cloud_ready_state_prefers_remote_only_execution() {
        let readiness = AiReadinessSummary {
            state: Some("cloud-ready".to_string()),
            ai_enabled: Some(true),
            endpoint_configured: true,
            ..AiReadinessSummary::default()
        };

        assert!(should_use_remote_only(
            &readiness,
            Some(&remote_endpoint_fixture())
        ));
    }

    #[test]
    fn setup_pending_local_response_can_fallback_remote() {
        let readiness = AiReadinessSummary {
            state: Some("setup-pending".to_string()),
            ai_enabled: Some(true),
            endpoint_configured: true,
            ..AiReadinessSummary::default()
        };
        let response = RuntimeInferResponse {
            backend_id: "local-cpu".to_string(),
            route_state: "setup-pending".to_string(),
            content: String::new(),
            degraded: true,
            rejected: true,
            reason: Some("selected local-cpu but backend is not executable".to_string()),
            estimated_latency_ms: None,
            provider_id: None,
            runtime_service_id: None,
            provider_status: None,
            queue_saturated: None,
            runtime_budget: None,
            notes: Vec::new(),
        };

        assert!(should_fallback_to_remote_from_response(
            &response,
            &readiness,
            Some(&remote_endpoint_fixture())
        ));
    }

    fn remote_endpoint_fixture() -> crate::config::RemoteEndpointConfig {
        crate::config::RemoteEndpointConfig {
            base_url: "http://127.0.0.1:11434/v1".to_string(),
            model: "qwen2.5:7b-instruct".to_string(),
            api_key: None,
            timeout_ms: 30_000,
        }
    }
}
