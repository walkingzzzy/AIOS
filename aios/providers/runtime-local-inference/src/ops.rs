use std::collections::BTreeSet;

use aios_contracts::{
    methods, ExecutionToken, RuntimeEmbedRequest, RuntimeEmbedResponse, RuntimeEmbeddingRecord,
    RuntimeInferRequest, RuntimeInferResponse, RuntimeQueueResponse, RuntimeRerankRequest,
    RuntimeRerankResponse, RuntimeRerankResult,
};

use crate::AppState;

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
            attach_runtime_metadata(
                state,
                token,
                &mut notes,
                queue_snapshot.as_ref(),
                runtime_health.as_ref().map(|item| item.service_id.clone()),
            );

            Ok(RuntimeInferResponse {
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
            })
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
    let vector_dimension = 8u32;
    let embeddings = request
        .inputs
        .iter()
        .enumerate()
        .map(|(index, input)| RuntimeEmbeddingRecord {
            input_index: index,
            vector: deterministic_embedding(input, vector_dimension as usize),
            text_length: input.chars().count(),
        })
        .collect::<Vec<_>>();

    let mut notes = vec![
        "provider_operation=embedding-skeleton".to_string(),
        format!("embedding_backend={}", state.config.embedding_backend),
        format!("embedding_count={}", embeddings.len()),
    ];
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot.as_ref(),
        runtime_health.as_ref().map(|item| item.service_id.clone()),
    );

    Ok(RuntimeEmbedResponse {
        backend_id: request
            .preferred_backend
            .clone()
            .unwrap_or_else(|| state.config.embedding_backend.clone()),
        route_state: "provider-skeleton".to_string(),
        vector_dimension,
        embeddings,
        degraded: runtime_health.is_none(),
        rejected: false,
        reason: None,
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health.as_ref().map(|item| item.service_id.clone()),
        provider_status: Some(if runtime_health.is_some() {
            "available".to_string()
        } else {
            "degraded".to_string()
        }),
        queue_saturated: queue_snapshot.as_ref().map(|item| item.saturated),
        runtime_budget,
        notes,
    })
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
    let mut results = request
        .documents
        .iter()
        .enumerate()
        .map(|(index, document)| RuntimeRerankResult {
            document_index: index,
            score: lexical_rerank_score(&request.query, document),
            document: document.clone(),
        })
        .collect::<Vec<_>>();
    results.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| left.document_index.cmp(&right.document_index))
    });
    if let Some(top_k) = request.top_k {
        results.truncate(top_k.max(1) as usize);
    }

    let mut notes = vec![
        "provider_operation=rerank-skeleton".to_string(),
        format!("rerank_backend={}", state.config.rerank_backend),
        format!("document_count={}", request.documents.len()),
    ];
    attach_runtime_metadata(
        state,
        token,
        &mut notes,
        queue_snapshot.as_ref(),
        runtime_health.as_ref().map(|item| item.service_id.clone()),
    );

    Ok(RuntimeRerankResponse {
        backend_id: request
            .preferred_backend
            .clone()
            .unwrap_or_else(|| state.config.rerank_backend.clone()),
        route_state: "provider-skeleton".to_string(),
        results,
        degraded: runtime_health.is_none(),
        rejected: false,
        reason: None,
        provider_id: Some(state.config.provider_id.clone()),
        runtime_service_id: runtime_health.as_ref().map(|item| item.service_id.clone()),
        provider_status: Some(if runtime_health.is_some() {
            "available".to_string()
        } else {
            "degraded".to_string()
        }),
        queue_saturated: queue_snapshot.as_ref().map(|item| item.saturated),
        runtime_budget,
        notes,
    })
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
}
