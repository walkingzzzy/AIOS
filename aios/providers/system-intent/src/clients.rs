use aios_contracts::{
    methods, AgentPlan, HealthResponse, ProviderDescriptor, ProviderHealthReportRequest,
    ProviderHealthState, ProviderRecord, ProviderRegisterRequest, TaskGetRequest,
    TaskPlanGetRequest, TaskPlanRecord, TaskRecord, TokenVerifyRequest, TokenVerifyResponse,
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

pub fn fetch_task(state: &AppState, task_id: &str) -> anyhow::Result<TaskRecord> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_GET,
        &TaskGetRequest {
            task_id: task_id.to_string(),
        },
    )
}

pub fn fetch_task_plan(state: &AppState, task_id: &str) -> anyhow::Result<Option<AgentPlan>> {
    let record: TaskPlanRecord = match aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_PLAN_GET,
        &TaskPlanGetRequest {
            task_id: task_id.to_string(),
        },
    ) {
        Ok(record) => record,
        Err(error) if error.to_string().contains("unknown task_id") => return Ok(None),
        Err(error) => return Err(error),
    };

    Ok(Some(serde_json::from_value(record.plan)?))
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

pub fn fetch_sessiond_health(state: &AppState) -> anyhow::Result<HealthResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::SYSTEM_HEALTH_GET,
        &serde_json::json!({}),
    )
}

fn load_provider_descriptor(path: &std::path::Path) -> anyhow::Result<ProviderDescriptor> {
    let content = std::fs::read_to_string(path)?;
    Ok(serde_json::from_str::<ProviderDescriptor>(&content)?)
}
