use std::{
    collections::hash_map::DefaultHasher,
    hash::{Hash, Hasher},
    thread,
    time::Duration,
};

use aios_contracts::{RuntimeInferRequest, RuntimeInferResponse};

use super::{
    capability::BackendReadiness, wrapper, BackendExecutionError, BackendFailureClass,
    RuntimeBackend,
};

#[derive(Debug, Clone, Copy)]
pub struct LocalCpuBackend;

impl RuntimeBackend for LocalCpuBackend {
    fn backend_id(&self) -> &'static str {
        "local-cpu"
    }

    fn readiness(&self, command: Option<&str>) -> BackendReadiness {
        match command {
            Some(_) => {
                BackendReadiness::available("configured-wrapper", "local-cpu wrapper configured")
            }
            None => {
                BackendReadiness::available("built-in-worker", "local-cpu built-in worker ready")
            }
        }
    }

    fn execute(
        &self,
        request: &RuntimeInferRequest,
        estimated_latency_ms: u64,
        timeout_ms: u64,
        command: Option<&str>,
    ) -> Result<RuntimeInferResponse, BackendExecutionError> {
        match command {
            Some(command) => wrapper::execute(wrapper::WrapperExecution {
                backend_id: self.backend_id(),
                request,
                estimated_latency_ms,
                timeout_ms,
                command,
                default_route_state: "local-wrapper",
            }),
            None => execute_inline_worker(request, estimated_latency_ms, timeout_ms),
        }
    }
}

fn execute_inline_worker(
    request: &RuntimeInferRequest,
    estimated_latency_ms: u64,
    timeout_ms: u64,
) -> Result<RuntimeInferResponse, BackendExecutionError> {
    let simulated_work_ms = if request.prompt.contains("#sleep-cpu") {
        1_200
    } else {
        15
    };

    if simulated_work_ms > timeout_ms {
        return Err(BackendExecutionError::new(
            BackendFailureClass::Timeout,
            "backend-timeout",
            format!(
                "local-cpu built-in worker exceeded timeout budget of {}ms",
                timeout_ms
            ),
            None,
        ));
    }

    thread::sleep(Duration::from_millis(simulated_work_ms));

    let prompt_chars = request.prompt.chars().count();
    let prompt_words = request.prompt.split_whitespace().count();
    let mut hasher = DefaultHasher::new();
    request.prompt.hash(&mut hasher);
    request.model.hash(&mut hasher);
    let digest = format!("{:016x}", hasher.finish());

    Ok(RuntimeInferResponse {
        backend_id: "local-cpu".to_string(),
        route_state: "local-worker".to_string(),
        content: format!(
            "local-cpu worker completed task {} model={} prompt_chars={} prompt_words={} digest={}",
            request.task_id,
            request
                .model
                .clone()
                .unwrap_or_else(|| "default-local-model".to_string()),
            prompt_chars,
            prompt_words,
            digest
        ),
        degraded: false,
        rejected: false,
        reason: Some("local-cpu built-in worker executed request".to_string()),
        estimated_latency_ms: Some(estimated_latency_ms),
        provider_id: None,
        runtime_service_id: None,
        provider_status: None,
        queue_saturated: None,
        runtime_budget: None,
        notes: Vec::new(),
    })
}
