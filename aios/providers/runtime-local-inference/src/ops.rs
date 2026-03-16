use std::collections::BTreeSet;

use serde_json::json;

use aios_contracts::{
    methods, ExecutionToken, HealthResponse, RuntimeEmbedRequest, RuntimeEmbedResponse,
    RuntimeEmbeddingRecord, RuntimeInferRequest, RuntimeInferResponse, RuntimeQueueResponse,
    RuntimeRerankRequest, RuntimeRerankResponse, RuntimeRerankResult,
};

use crate::AppState;

const DEFAULT_EMBEDDING_VECTOR_DIMENSION: u32 = 8;
const EMBEDDING_ROUTE_STATE: &str = "provider-local-embedding";
const RERANK_ROUTE_STATE: &str = "provider-local-rerank";
const EMBEDDING_ALGORITHM: &str = "deterministic-embedding-v1";
const RERANK_ALGORITHM: &str = "lexical-overlap-v1";

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

    let queue_snapshot = crate::clients::fetch_runtime_queue(state).ok();
    let runtime_health = crate::clients::fetch_runtime_health(state).ok();
    let result = crate::clients::submit_runtime_infer(state, request);

    match result {
        Ok(mut response) => {
            let (_, _, runtime_dependency) =
                provider_runtime_dependency_state(runtime_health.as_ref());
            append_provider_operation_notes(&mut response.notes, "infer", runtime_dependency);
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
            response.provider_status = Some("available".to_string());
            response.queue_saturated = queue_snapshot.as_ref().map(|item| item.saturated);
            response.runtime_budget = crate::clients::fetch_runtime_budget(state).ok();
            let _ = crate::clients::report_provider_health(state, "available", None);
            emit_infer_trace(state, request, &response);
            Ok(response)
        }
        Err(error) => {
            let error_text = error.to_string();
            let classification = classify_runtime_error(&error_text);
            let _ = crate::clients::report_provider_health(
                state,
                classification.reported_status,
                Some(error_text.clone()),
            );

            let mut notes = Vec::new();
            let (_, _, runtime_dependency) =
                provider_runtime_dependency_state(runtime_health.as_ref());
            append_provider_operation_notes(&mut notes, "infer", runtime_dependency);
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

    let queue_snapshot = crate::clients::fetch_runtime_queue(state).ok();
    let runtime_health = crate::clients::fetch_runtime_health(state).ok();
    let runtime_budget = crate::clients::fetch_runtime_budget(state).ok();
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
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot.as_ref(),
        runtime_health.as_ref().map(|item| item.service_id.clone()),
    );

    let response = RuntimeEmbedResponse {
        backend_id,
        route_state: EMBEDDING_ROUTE_STATE.to_string(),
        vector_dimension,
        embeddings,
        degraded,
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

    let queue_snapshot = crate::clients::fetch_runtime_queue(state).ok();
    let runtime_health = crate::clients::fetch_runtime_health(state).ok();
    let runtime_budget = crate::clients::fetch_runtime_budget(state).ok();
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
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot.as_ref(),
        runtime_health.as_ref().map(|item| item.service_id.clone()),
    );

    let response = RuntimeRerankResponse {
        backend_id,
        route_state: RERANK_ROUTE_STATE.to_string(),
        results,
        degraded,
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
    if message.contains("failed to connect to") || message.contains("No such file or directory") {
        return RuntimeErrorClassification {
            route_state: "runtime-unavailable",
            degraded: true,
            provider_status: "degraded",
            reported_status: "unavailable",
        };
    }

    if message.contains("remote rpc error") {
        return RuntimeErrorClassification {
            route_state: "runtime-rejected",
            degraded: false,
            provider_status: "available",
            reported_status: "available",
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
}
