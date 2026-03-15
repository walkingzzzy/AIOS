use aios_contracts::{RuntimeInferRequest, RuntimeInferResponse};

use super::{
    capability::{any_device_present, configured_command_readiness, env_truthy, BackendReadiness},
    wrapper, BackendExecutionError, BackendFailureClass, RuntimeBackend,
};

const NPU_DEVICE_PATHS: &[&str] = &["/dev/accel/accel0", "/dev/npu0", "/dev/apex_0"];

#[derive(Debug, Clone, Copy)]
pub struct LocalNpuBackend;

impl RuntimeBackend for LocalNpuBackend {
    fn backend_id(&self) -> &'static str {
        "local-npu"
    }

    fn readiness(&self, command: Option<&str>) -> BackendReadiness {
        if env_truthy("AIOS_RUNTIMED_DISABLE_LOCAL_NPU") {
            return BackendReadiness::unavailable(
                "disabled",
                "runtime-config",
                "local-npu backend disabled by environment",
            );
        }

        if let Some(readiness) = configured_command_readiness(self.backend_id(), command) {
            return readiness;
        }

        if any_device_present(NPU_DEVICE_PATHS) {
            return BackendReadiness::unavailable(
                "dependency-missing",
                "hardware-present+vendor-runtime-missing",
                "npu device detected but no vendor runtime wrapper configured",
            );
        }

        BackendReadiness::unavailable(
            "device-missing",
            "vendor-backend+hardware-profile",
            "no supported npu device detected",
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
