use std::time::Duration;

use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};

use aios_contracts::{
    methods, HealthResponse, ProviderDescriptor, ProviderHealthReportRequest, ProviderHealthState,
    ProviderRecord, ProviderRegisterRequest, RuntimeBudgetResponse, RuntimeInferRequest,
    RuntimeInferResponse, RuntimeQueueResponse, TokenVerifyRequest, TokenVerifyResponse,
};

use crate::{config::RemoteEndpointConfig, AppState};

#[derive(Debug, Clone)]
pub struct RemoteInferResult {
    pub content: String,
    pub model: String,
    pub estimated_latency_ms: u64,
    pub usage_total_tokens: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct RemoteEmbeddingResult {
    pub embeddings: Vec<Vec<f32>>,
    pub model: String,
    pub vector_dimension: u32,
    pub estimated_latency_ms: u64,
    pub usage_total_tokens: Option<u64>,
}

pub fn verify_token(
    state: &AppState,
    token: &aios_contracts::ExecutionToken,
) -> anyhow::Result<TokenVerifyResponse> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_TOKEN_VERIFY,
        &TokenVerifyRequest {
            token: token.clone(),
            target_hash: None,
            consume: false,
        },
    )
}

pub fn fetch_runtime_health(state: &AppState) -> anyhow::Result<HealthResponse> {
    aios_rpc::call_unix(
        &state.config.runtimed_socket,
        methods::SYSTEM_HEALTH_GET,
        &serde_json::json!({}),
    )
}

pub fn fetch_runtime_budget(state: &AppState) -> anyhow::Result<RuntimeBudgetResponse> {
    aios_rpc::call_unix(
        &state.config.runtimed_socket,
        methods::RUNTIME_BUDGET_GET,
        &serde_json::json!({}),
    )
}

pub fn fetch_runtime_queue(state: &AppState) -> anyhow::Result<RuntimeQueueResponse> {
    aios_rpc::call_unix(
        &state.config.runtimed_socket,
        methods::RUNTIME_QUEUE_GET,
        &serde_json::json!({}),
    )
}

pub fn submit_runtime_infer(
    state: &AppState,
    request: &RuntimeInferRequest,
) -> anyhow::Result<RuntimeInferResponse> {
    let mut forwarded = request.clone();
    forwarded.execution_token = None;
    aios_rpc::call_unix(
        &state.config.runtimed_socket,
        methods::RUNTIME_INFER_SUBMIT,
        &forwarded,
    )
}

pub fn submit_remote_infer(
    state: &AppState,
    request: &RuntimeInferRequest,
    remote: &RemoteEndpointConfig,
) -> anyhow::Result<RemoteInferResult> {
    let client = Client::builder()
        .timeout(Duration::from_millis(remote.timeout_ms))
        .build()?;
    let request_model = request
        .model
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(remote.model.as_str())
        .to_string();
    let body = OpenAiChatCompletionRequest {
        model: request_model.clone(),
        messages: vec![OpenAiMessage {
            role: "user",
            content: request.prompt.clone(),
        }],
        stream: false,
    };

    let mut builder = client
        .post(remote.chat_completions_url())
        .header(
            reqwest::header::USER_AGENT,
            format!(
                "aios-runtime-local-inference-provider/{}",
                state.config.version
            ),
        )
        .json(&body);
    if let Some(api_key) = remote.api_key.as_deref() {
        builder = builder.bearer_auth(api_key);
    }

    let started = std::time::Instant::now();
    let response = builder.send()?;
    let status = response.status();
    let response_text = response.text()?;
    if !status.is_success() {
        let remote_error = serde_json::from_str::<OpenAiErrorEnvelope>(&response_text)
            .ok()
            .and_then(|payload| payload.error)
            .and_then(|payload| payload.message)
            .unwrap_or_else(|| truncate_text(&response_text, 240));
        anyhow::bail!(
            "remote endpoint returned {}: {}",
            status.as_u16(),
            remote_error
        );
    }

    let payload: OpenAiChatCompletionResponse = serde_json::from_str(&response_text)?;
    let content = payload
        .choices
        .iter()
        .find_map(|choice| choice.content())
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| anyhow::anyhow!("remote endpoint returned an empty completion"))?;

    Ok(RemoteInferResult {
        content,
        model: payload.model.unwrap_or(request_model),
        estimated_latency_ms: started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64,
        usage_total_tokens: payload.usage.and_then(|usage| usage.total_tokens),
    })
}

pub fn submit_remote_embed(
    state: &AppState,
    inputs: &[String],
    remote: &RemoteEndpointConfig,
) -> anyhow::Result<RemoteEmbeddingResult> {
    let client = Client::builder()
        .timeout(Duration::from_millis(remote.timeout_ms))
        .build()?;
    let body = OpenAiEmbeddingRequest {
        model: remote.model.clone(),
        input: inputs.to_vec(),
    };

    let mut builder = client
        .post(remote.embeddings_url())
        .header(
            reqwest::header::USER_AGENT,
            format!(
                "aios-runtime-local-inference-provider/{}",
                state.config.version
            ),
        )
        .json(&body);
    if let Some(api_key) = remote.api_key.as_deref() {
        builder = builder.bearer_auth(api_key);
    }

    let started = std::time::Instant::now();
    let response = builder.send()?;
    let status = response.status();
    let response_text = response.text()?;
    if !status.is_success() {
        let remote_error = serde_json::from_str::<OpenAiErrorEnvelope>(&response_text)
            .ok()
            .and_then(|payload| payload.error)
            .and_then(|payload| payload.message)
            .unwrap_or_else(|| truncate_text(&response_text, 240));
        anyhow::bail!(
            "remote embedding endpoint returned {}: {}",
            status.as_u16(),
            remote_error
        );
    }

    let payload: OpenAiEmbeddingResponse = serde_json::from_str(&response_text)?;
    let mut data = payload.data;
    if data.is_empty() {
        anyhow::bail!("remote embedding endpoint returned no vectors");
    }
    data.sort_by_key(|item| item.index);
    let vector_dimension = data
        .first()
        .map(|item| item.embedding.len())
        .unwrap_or_default();
    if vector_dimension == 0 {
        anyhow::bail!("remote embedding endpoint returned empty vectors");
    }
    if data
        .iter()
        .any(|item| item.embedding.len() != vector_dimension)
    {
        anyhow::bail!("remote embedding endpoint returned inconsistent vector dimensions");
    }

    Ok(RemoteEmbeddingResult {
        embeddings: data.into_iter().map(|item| item.embedding).collect(),
        model: payload.model.unwrap_or_else(|| remote.model.clone()),
        vector_dimension: vector_dimension as u32,
        estimated_latency_ms: started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64,
        usage_total_tokens: payload.usage.and_then(|usage| usage.total_tokens),
    })
}

pub fn report_provider_health(
    state: &AppState,
    status: &str,
    last_error: Option<String>,
) -> anyhow::Result<ProviderHealthState> {
    aios_rpc::call_unix(
        &state.config.agentd_socket,
        methods::PROVIDER_HEALTH_REPORT,
        &ProviderHealthReportRequest {
            provider_id: state.config.provider_id.clone(),
            status: status.to_string(),
            last_error,
            circuit_open: false,
            resource_pressure: None,
        },
    )
}

pub fn register_provider(state: &AppState) -> anyhow::Result<ProviderRecord> {
    let descriptor = load_provider_descriptor(&state.config.descriptor_path)?;
    aios_rpc::call_unix(
        &state.config.agentd_socket,
        methods::PROVIDER_REGISTER,
        &ProviderRegisterRequest { descriptor },
    )
}

fn load_provider_descriptor(path: &std::path::Path) -> anyhow::Result<ProviderDescriptor> {
    let content = std::fs::read_to_string(path)?;
    Ok(serde_json::from_str::<ProviderDescriptor>(&content)?)
}

fn truncate_text(input: &str, max_chars: usize) -> String {
    let mut truncated = String::new();
    for character in input.chars().take(max_chars) {
        truncated.push(character);
    }
    if input.chars().count() > max_chars {
        truncated.push_str("...");
    }
    truncated
}

#[derive(Debug, Serialize)]
struct OpenAiChatCompletionRequest {
    model: String,
    messages: Vec<OpenAiMessage>,
    stream: bool,
}

#[derive(Debug, Serialize)]
struct OpenAiEmbeddingRequest {
    model: String,
    input: Vec<String>,
}

#[derive(Debug, Serialize)]
struct OpenAiMessage {
    role: &'static str,
    content: String,
}

#[derive(Debug, Deserialize)]
struct OpenAiChatCompletionResponse {
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    choices: Vec<OpenAiChoice>,
    #[serde(default)]
    usage: Option<OpenAiUsage>,
}

#[derive(Debug, Deserialize)]
struct OpenAiEmbeddingResponse {
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    data: Vec<OpenAiEmbeddingDatum>,
    #[serde(default)]
    usage: Option<OpenAiUsage>,
}

#[derive(Debug, Deserialize)]
struct OpenAiEmbeddingDatum {
    #[serde(default)]
    index: usize,
    #[serde(default)]
    embedding: Vec<f32>,
}

#[derive(Debug, Deserialize)]
struct OpenAiChoice {
    #[serde(default)]
    message: Option<OpenAiAssistantMessage>,
    #[serde(default)]
    text: Option<String>,
}

impl OpenAiChoice {
    fn content(&self) -> Option<String> {
        self.message
            .as_ref()
            .and_then(OpenAiAssistantMessage::content)
            .or_else(|| {
                self.text
                    .as_deref()
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_string)
            })
    }
}

#[derive(Debug, Deserialize)]
struct OpenAiAssistantMessage {
    #[serde(default)]
    content: Option<serde_json::Value>,
}

impl OpenAiAssistantMessage {
    fn content(&self) -> Option<String> {
        match self.content.as_ref()? {
            serde_json::Value::String(value) => Some(value.trim().to_string()),
            serde_json::Value::Array(items) => {
                let content = items
                    .iter()
                    .filter_map(|item| item.as_object())
                    .filter_map(|item| item.get("text"))
                    .filter_map(|item| item.as_str())
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .collect::<Vec<_>>()
                    .join("\n");
                (!content.is_empty()).then_some(content)
            }
            _ => None,
        }
    }
}

#[derive(Debug, Deserialize)]
struct OpenAiUsage {
    #[serde(default)]
    total_tokens: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct OpenAiErrorEnvelope {
    #[serde(default)]
    error: Option<OpenAiError>,
}

#[derive(Debug, Deserialize)]
struct OpenAiError {
    #[serde(default)]
    message: Option<String>,
}
