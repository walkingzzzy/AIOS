use aios_contracts::{
    methods, HealthResponse, ProviderDescriptor, ProviderHealthReportRequest, ProviderHealthState,
    ProviderRecord, ProviderRegisterRequest, RuntimeBudgetResponse, RuntimeInferRequest,
    RuntimeInferResponse, RuntimeQueueResponse, TokenVerifyRequest, TokenVerifyResponse,
};

use crate::AppState;

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
