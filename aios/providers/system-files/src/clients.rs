use aios_contracts::{
    methods, ExecutionToken, PortalHandleRecord, PortalLookupHandleRequest,
    PortalLookupHandleResponse, ProviderDescriptor, ProviderHealthReportRequest,
    ProviderHealthState, ProviderRecord, ProviderRegisterRequest, TokenVerifyRequest,
    TokenVerifyResponse,
};

use crate::AppState;

pub fn lookup_handle(
    state: &AppState,
    handle_id: &str,
    token: &ExecutionToken,
) -> anyhow::Result<PortalHandleRecord> {
    let response: PortalLookupHandleResponse = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::PORTAL_HANDLE_LOOKUP,
        &PortalLookupHandleRequest {
            handle_id: handle_id.to_string(),
            session_id: Some(token.session_id.clone()),
            user_id: Some(token.user_id.clone()),
        },
    )?;

    response
        .handle
        .ok_or_else(|| anyhow::anyhow!("unknown portal handle: {handle_id}"))
}

pub fn verify_token(
    state: &AppState,
    token: &ExecutionToken,
    target_hash: &str,
    consume: bool,
) -> anyhow::Result<TokenVerifyResponse> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_TOKEN_VERIFY,
        &TokenVerifyRequest {
            token: token.clone(),
            target_hash: Some(target_hash.to_string()),
            consume,
        },
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
    let descriptor = serde_json::from_str::<ProviderDescriptor>(&content)?;
    Ok(descriptor)
}
