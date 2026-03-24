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

pub async fn fetch_device_state_async(state: &AppState) -> anyhow::Result<DeviceStateGetResponse> {
    let socket = state.config.deviced_socket.clone();
    tokio::task::spawn_blocking(move || {
        aios_rpc::call_unix(
            &socket,
            methods::DEVICE_STATE_GET,
            &DeviceStateGetRequest {},
        )
    })
    .await
    .map_err(|error| anyhow::anyhow!("device state task failed: {error}"))?
}

pub async fn report_provider_health(
    state: &AppState,
    status: &str,
    last_error: Option<String>,
) -> anyhow::Result<ProviderHealthState> {
    let socket = state.config.agentd_socket.clone();
    let request = ProviderHealthReportRequest {
        provider_id: state.config.provider_id.clone(),
        status: status.to_string(),
        last_error,
        circuit_open: false,
        resource_pressure: None,
    };

    tokio::task::spawn_blocking(move || {
        aios_rpc::call_unix(&socket, methods::PROVIDER_HEALTH_REPORT, &request)
    })
    .await
    .map_err(|error| anyhow::anyhow!("provider health report task failed: {error}"))?
}

pub async fn register_provider(state: &AppState) -> anyhow::Result<ProviderRecord> {
    let descriptor_path = state.config.descriptor_path.clone();
    let agentd_socket = state.config.agentd_socket.clone();
    tokio::task::spawn_blocking(move || {
        let descriptor = load_provider_descriptor(&descriptor_path)?;
        aios_rpc::call_unix(
            &agentd_socket,
            methods::PROVIDER_REGISTER,
            &ProviderRegisterRequest { descriptor },
        )
    })
    .await
    .map_err(|error| anyhow::anyhow!("provider registration task failed: {error}"))?
}

fn load_provider_descriptor(path: &std::path::Path) -> anyhow::Result<ProviderDescriptor> {
    let content = std::fs::read_to_string(path)?;
    let descriptor = serde_json::from_str::<ProviderDescriptor>(&content)?;
    Ok(descriptor)
}
