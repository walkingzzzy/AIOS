use aios_contracts::{RuntimeBackendDescriptor, RuntimeInferRequest, RuntimeInferResponse};

pub mod capability;
pub mod cpu;
pub mod gpu;
pub mod npu;
pub mod remote;
pub mod wrapper;

pub use capability::BackendReadiness;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackendFailureClass {
    Timeout,
    Unavailable,
    Unreachable,
    CommandFailed,
    InvalidResponse,
}

#[derive(Debug, Clone)]
pub struct BackendExecutionError {
    pub class: BackendFailureClass,
    pub route_state: String,
    pub reason: String,
    pub fallback_backend: Option<&'static str>,
}

impl BackendExecutionError {
    pub fn new(
        class: BackendFailureClass,
        route_state: &str,
        reason: impl Into<String>,
        fallback_backend: Option<&'static str>,
    ) -> Self {
        Self {
            class,
            route_state: route_state.to_string(),
            reason: reason.into(),
            fallback_backend,
        }
    }
}

pub trait RuntimeBackend: Sync {
    fn backend_id(&self) -> &'static str;
    fn readiness(&self, command: Option<&str>) -> BackendReadiness;

    fn descriptor(&self, command: Option<&str>) -> RuntimeBackendDescriptor {
        self.readiness(command).descriptor(self.backend_id())
    }

    fn execute(
        &self,
        request: &RuntimeInferRequest,
        estimated_latency_ms: u64,
        timeout_ms: u64,
        command: Option<&str>,
    ) -> Result<RuntimeInferResponse, BackendExecutionError>;
}

static LOCAL_CPU_BACKEND: cpu::LocalCpuBackend = cpu::LocalCpuBackend;
static LOCAL_GPU_BACKEND: gpu::LocalGpuBackend = gpu::LocalGpuBackend;
static LOCAL_NPU_BACKEND: npu::LocalNpuBackend = npu::LocalNpuBackend;
static ATTESTED_REMOTE_BACKEND: remote::AttestedRemoteBackend = remote::AttestedRemoteBackend;

fn lookup_backend(backend_id: &str) -> Option<&'static dyn RuntimeBackend> {
    match backend_id {
        "local-cpu" => Some(&LOCAL_CPU_BACKEND),
        "local-gpu" => Some(&LOCAL_GPU_BACKEND),
        "local-npu" => Some(&LOCAL_NPU_BACKEND),
        "attested-remote" => Some(&ATTESTED_REMOTE_BACKEND),
        _ => None,
    }
}

#[derive(Debug, Clone, Default)]
pub struct BackendCommands {
    pub local_cpu: Option<String>,
    pub local_gpu: Option<String>,
    pub local_npu: Option<String>,
    pub attested_remote: Option<String>,
}

impl BackendCommands {
    pub fn for_backend(&self, backend_id: &str) -> Option<&str> {
        match backend_id {
            "local-cpu" => self.local_cpu.as_deref(),
            "local-gpu" => self.local_gpu.as_deref(),
            "local-npu" => self.local_npu.as_deref(),
            "attested-remote" => self.attested_remote.as_deref(),
            _ => None,
        }
    }

    pub fn set_backend(&mut self, backend_id: &str, command: Option<String>) {
        match backend_id {
            "local-cpu" => self.local_cpu = command,
            "local-gpu" => self.local_gpu = command,
            "local-npu" => self.local_npu = command,
            "attested-remote" => self.attested_remote = command,
            _ => {}
        }
    }
}

pub fn readiness(backend_id: &str, commands: &BackendCommands) -> Option<BackendReadiness> {
    lookup_backend(backend_id).map(|backend| backend.readiness(commands.for_backend(backend_id)))
}

pub fn descriptors(
    allowed_backends: &[String],
    commands: &BackendCommands,
) -> Vec<RuntimeBackendDescriptor> {
    allowed_backends
        .iter()
        .map(|backend| match lookup_backend(backend) {
            Some(runtime_backend) => runtime_backend.descriptor(commands.for_backend(backend)),
            None => RuntimeBackendDescriptor {
                backend_id: backend.clone(),
                availability: "unknown".to_string(),
                activation: "not-modeled-yet".to_string(),
            },
        })
        .collect()
}

pub fn execute(
    backend_id: &str,
    request: &RuntimeInferRequest,
    estimated_latency_ms: u64,
    timeout_ms: u64,
    commands: &BackendCommands,
) -> Result<RuntimeInferResponse, BackendExecutionError> {
    let Some(runtime_backend) = lookup_backend(backend_id) else {
        return Err(BackendExecutionError::new(
            BackendFailureClass::Unavailable,
            "backend-unknown",
            format!("runtime backend {} is not registered", backend_id),
            Some("local-cpu"),
        ));
    };

    runtime_backend.execute(
        request,
        estimated_latency_ms,
        timeout_ms,
        commands.for_backend(backend_id),
    )
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    fn request(task_id: &str) -> RuntimeInferRequest {
        RuntimeInferRequest {
            session_id: "session-1".to_string(),
            task_id: task_id.to_string(),
            prompt: "Summarize runtime state".to_string(),
            model: Some("smoke-model".to_string()),
            execution_token: None,
            preferred_backend: None,
        }
    }

    #[test]
    fn descriptors_resolve_through_runtime_backend_trait() {
        let descriptors = descriptors(
            &[
                "local-cpu".to_string(),
                "local-gpu".to_string(),
                "unknown-backend".to_string(),
            ],
            &BackendCommands {
                local_gpu: Some("printf configured".to_string()),
                ..BackendCommands::default()
            },
        );

        assert_eq!(descriptors[0].backend_id, "local-cpu");
        assert_eq!(descriptors[0].availability, "available");
        assert_eq!(descriptors[1].backend_id, "local-gpu");
        assert_eq!(descriptors[1].availability, "available");
        assert_eq!(descriptors[2].backend_id, "unknown-backend");
        assert_eq!(descriptors[2].availability, "unknown");
    }

    #[test]
    fn execute_uses_trait_registered_wrapper_backend() {
        let response = execute(
            "local-gpu",
            &request("task-wrapper"),
            42,
            1_000,
            &BackendCommands {
                local_gpu: Some(
                    r#"printf '%s' '{"content":"gpu-ok","route_state":"local-wrapper"}'"#
                        .to_string(),
                ),
                ..BackendCommands::default()
            },
        )
        .expect("wrapper execution should succeed");

        assert_eq!(response.backend_id, "local-gpu");
        assert_eq!(response.route_state, "local-wrapper");
        assert_eq!(response.content, "gpu-ok");
        assert_eq!(response.estimated_latency_ms, Some(42));
    }

    #[test]
    fn execute_keeps_inline_cpu_worker_when_unconfigured() {
        let response = execute(
            "local-cpu",
            &request("task-inline"),
            21,
            1_000,
            &BackendCommands::default(),
        )
        .expect("inline cpu execution should succeed");

        assert_eq!(response.backend_id, "local-cpu");
        assert_eq!(response.route_state, "local-worker");
        assert!(response.content.contains("task-inline"));
    }

    #[test]
    fn remote_descriptor_reports_available_when_http_endpoint_is_configured() {
        let readiness = readiness(
            "attested-remote",
            &BackendCommands {
                attested_remote: Some("http://127.0.0.1:8081/infer".to_string()),
                ..BackendCommands::default()
            },
        )
        .expect("remote readiness");

        assert_eq!(readiness.availability, "available");
        assert_eq!(readiness.activation, "configured-remote-endpoint");
    }

    #[test]
    fn gpu_descriptor_reports_missing_unix_worker_socket_as_unavailable() {
        let readiness = readiness(
            "local-gpu",
            &BackendCommands {
                local_gpu: Some("unix:///tmp/aios-runtimed-missing-gpu.sock".to_string()),
                ..BackendCommands::default()
            },
        )
        .expect("gpu readiness");

        assert_eq!(readiness.availability, "worker-socket-missing");
        assert_eq!(readiness.activation, "configured-unix-worker");
    }

    #[test]
    fn npu_descriptor_reports_existing_unix_worker_socket_as_available() {
        let temp_root = std::env::temp_dir().join(format!(
            "aios-runtimed-npu-readiness-{}",
            std::process::id()
        ));
        fs::create_dir_all(&temp_root).expect("create temp root");
        let socket_path = temp_root.join("worker.sock");
        fs::write(&socket_path, b"ready\n").expect("write worker socket placeholder");

        let readiness = readiness(
            "local-npu",
            &BackendCommands {
                local_npu: Some(format!("unix://{}", socket_path.display())),
                ..BackendCommands::default()
            },
        )
        .expect("npu readiness");

        assert_eq!(readiness.availability, "available");
        assert_eq!(readiness.activation, "configured-unix-worker");

        fs::remove_dir_all(&temp_root).ok();
    }
}
