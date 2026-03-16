use std::path::PathBuf;

use aios_core::ServicePaths;

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub paths: ServicePaths,
    pub runtime_profile_path: PathBuf,
    pub route_profile_path: PathBuf,
    pub policyd_socket: PathBuf,
    pub remote_audit_log_path: PathBuf,
    pub observability_log_path: PathBuf,
    pub local_cpu_command: Option<String>,
    pub local_gpu_command: Option<String>,
    pub local_npu_command: Option<String>,
    pub local_gpu_worker_command: Option<String>,
    pub local_npu_worker_command: Option<String>,
    pub hardware_profile_id: Option<String>,
    pub attested_remote_command: Option<String>,
    pub attested_remote_target_hash: Option<String>,
    pub managed_worker_timeout_ms: u64,
    pub managed_worker_restart_backoff_ms: u64,
    pub managed_worker_restart_limit: u32,
    pub backend_health_poll_ms: u64,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("runtimed");
        paths.ensure_base_dirs().await?;

        let runtime_profile_path =
            aios_core::config::env_path_or("AIOS_RUNTIMED_RUNTIME_PROFILE", || {
                PathBuf::from("/etc/aios/runtime/default-runtime-profile.yaml")
            });

        let route_profile_path =
            aios_core::config::env_path_or("AIOS_RUNTIMED_ROUTE_PROFILE", || {
                PathBuf::from("/etc/aios/runtime/default-route-profile.yaml")
            });
        let policyd_socket = aios_core::config::env_path_or("AIOS_RUNTIMED_POLICYD_SOCKET", || {
            PathBuf::from("/run/aios/policyd/policyd.sock")
        });
        let remote_audit_log_path =
            aios_core::config::env_path_or("AIOS_RUNTIMED_REMOTE_AUDIT_LOG", || {
                paths.state_dir.join("attested-remote-audit.jsonl")
            });
        let observability_log_path =
            aios_core::config::env_path_or("AIOS_RUNTIMED_OBSERVABILITY_LOG", || {
                paths.state_dir.join("observability.jsonl")
            });
        let local_cpu_command =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_LOCAL_CPU_COMMAND");
        let local_gpu_command =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_LOCAL_GPU_COMMAND");
        let local_npu_command =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_LOCAL_NPU_COMMAND");
        let local_gpu_worker_command =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_LOCAL_GPU_WORKER_COMMAND");
        let local_npu_worker_command =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_LOCAL_NPU_WORKER_COMMAND");
        let hardware_profile_id =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_HARDWARE_PROFILE_ID");
        let attested_remote_command =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_ATTESTED_REMOTE_COMMAND");
        let attested_remote_target_hash = attested_remote_command
            .as_deref()
            .map(crate::remote_security::attested_remote_target_hash);
        let managed_worker_timeout_ms =
            aios_core::config::env_u64_or("AIOS_RUNTIMED_MANAGED_WORKER_TIMEOUT_MS", 5_000);
        let managed_worker_restart_backoff_ms =
            aios_core::config::env_u64_or("AIOS_RUNTIMED_MANAGED_WORKER_RESTART_BACKOFF_MS", 250);
        let managed_worker_restart_limit =
            aios_core::config::env_u64_or("AIOS_RUNTIMED_MANAGED_WORKER_RESTART_LIMIT", 3)
                .min(u32::MAX as u64) as u32;
        let backend_health_poll_ms =
            aios_core::config::env_u64_or("AIOS_RUNTIMED_BACKEND_HEALTH_POLL_MS", 250);

        Ok(Self {
            service_id: "aios-runtimed".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            paths,
            runtime_profile_path,
            route_profile_path,
            policyd_socket,
            remote_audit_log_path,
            observability_log_path,
            local_cpu_command,
            local_gpu_command,
            local_npu_command,
            local_gpu_worker_command,
            local_npu_worker_command,
            hardware_profile_id,
            attested_remote_command,
            attested_remote_target_hash,
            managed_worker_timeout_ms,
            managed_worker_restart_backoff_ms,
            managed_worker_restart_limit,
            backend_health_poll_ms,
        })
    }
}
