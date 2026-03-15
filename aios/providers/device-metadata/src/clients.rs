use aios_contracts::{
    methods, DeviceStateGetRequest, DeviceStateGetResponse, ProviderDescriptor,
    ProviderHealthReportRequest, ProviderHealthState, ProviderRecord, ProviderRegisterRequest,
};

use crate::AppState;

pub fn fetch_device_state(state: &AppState) -> anyhow::Result<DeviceStateGetResponse> {
    aios_rpc::call_unix(
        &state.config.deviced_socket,
        methods::DEVICE_STATE_GET,
        &DeviceStateGetRequest {},
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
