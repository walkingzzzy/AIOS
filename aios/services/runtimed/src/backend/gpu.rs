use aios_contracts::{RuntimeInferRequest, RuntimeInferResponse};

use super::{
    capability::{any_device_present, configured_command_readiness, env_truthy, BackendReadiness},
    wrapper, BackendExecutionError, BackendFailureClass, RuntimeBackend,
};

const GPU_DEVICE_PATHS: &[&str] = &[
    "/dev/nvidiactl",
    "/dev/dri/renderD128",
    "/dev/dri/renderD129",
    "/dev/kfd",
];

#[derive(Debug, Clone, Copy)]
pub struct LocalGpuBackend;

impl RuntimeBackend for LocalGpuBackend {
    fn backend_id(&self) -> &'static str {
        "local-gpu"
    }

    fn readiness(&self, command: Option<&str>) -> BackendReadiness {
        if env_truthy("AIOS_RUNTIMED_DISABLE_LOCAL_GPU") {
            return BackendReadiness::unavailable(
                "disabled",
                "runtime-config",
                "local-gpu backend disabled by environment",
            );
        }

        if let Some(readiness) = configured_command_readiness(self.backend_id(), command) {
            return readiness;
        }

        if any_device_present(GPU_DEVICE_PATHS) {
            return BackendReadiness::unavailable(
                "dependency-missing",
                "hardware-present+runtime-missing",
                "gpu device detected but no runtime wrapper configured",
            );
        }

        BackendReadiness::unavailable(
            "device-missing",
            "hardware-profile+driver+runtime-profile",
            "no supported gpu device detected",
        )
    }

    fn execute(
        &self,
        request: &RuntimeInferRequest,
        estimated_latency_ms: u64,
        timeout_ms: u64,
        command: Option<&str>,
    ) -> Result<RuntimeInferResponse, BackendExecutionError> {
        let readiness = self.readiness(command);
        let Some(command) = command else {
            return Err(BackendExecutionError::new(
                BackendFailureClass::Unavailable,
                "capability-gated",
                readiness.reason,
                Some("local-cpu"),
            ));
        };

        wrapper::execute(wrapper::WrapperExecution {
            backend_id: self.backend_id(),
            request,
            estimated_latency_ms,
            timeout_ms,
            command,
            default_route_state: "local-wrapper",
        })
    }
}
