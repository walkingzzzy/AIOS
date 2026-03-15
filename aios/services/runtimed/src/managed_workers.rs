use std::{
    path::{Path, PathBuf},
    process::{Child, Command},
    thread,
    time::{Duration, Instant},
};

use crate::{backend::BackendCommands, config::Config, scheduler::RuntimeProfile};

#[derive(Clone, Debug, Default)]
pub struct ManagedWorkerSummary {
    pub statuses: Vec<ManagedWorkerStatus>,
}

impl ManagedWorkerSummary {
    pub fn notes(&self) -> Vec<String> {
        let ready_count = self
            .statuses
            .iter()
            .filter(|status| status.state == "ready")
            .count();
        let mut notes = vec![format!("managed_worker_count={ready_count}")];
        for status in &self.statuses {
            notes.push(format!(
                "managed_worker.{}={}",
                status.backend_id, status.state
            ));
            if let Some(socket_path) = status.socket_path.as_ref() {
                notes.push(format!(
                    "managed_worker_socket.{}={}",
                    status.backend_id,
                    socket_path.display()
                ));
            }
            notes.push(format!(
                "managed_worker_source.{}={}",
                status.backend_id, status.command_source
            ));
            notes.push(format!(
                "managed_worker_detail.{}={}",
                status.backend_id, status.detail
            ));
        }
        notes
    }
}

#[derive(Clone, Debug)]
pub struct ManagedWorkerStatus {
    pub backend_id: String,
    pub state: String,
    pub command_source: String,
    pub detail: String,
    pub socket_path: Option<PathBuf>,
}

#[derive(Debug)]
struct ManagedWorkerChild {
    backend_id: String,
    socket_path: PathBuf,
    child: Child,
}

#[derive(Debug, Default)]
pub struct ManagedAccelWorkers {
    summary: ManagedWorkerSummary,
    children: Vec<ManagedWorkerChild>,
}

impl ManagedAccelWorkers {
    pub fn launch(
        config: &Config,
        runtime_profile: &RuntimeProfile,
        backend_commands: &mut BackendCommands,
    ) -> anyhow::Result<Self> {
        let mut workers = Self::default();
        for backend_id in ["local-gpu", "local-npu"] {
            if backend_commands.for_backend(backend_id).is_some() {
                workers.summary.statuses.push(ManagedWorkerStatus {
                    backend_id: backend_id.to_string(),
                    state: "external-command".to_string(),
                    command_source: "backend-command".to_string(),
                    detail: "backend command already configured".to_string(),
                    socket_path: None,
                });
                continue;
            }

            let (launch_command, command_source) =
                managed_worker_command(config, runtime_profile, backend_id);
            let Some(launch_command) = launch_command else {
                workers.summary.statuses.push(ManagedWorkerStatus {
                    backend_id: backend_id.to_string(),
                    state: "not-configured".to_string(),
                    command_source,
                    detail: "managed worker command missing".to_string(),
                    socket_path: None,
                });
                continue;
            };

            let socket_path = config
                .paths
                .runtime_dir
                .join(format!("{backend_id}.managed-worker.sock"));
            let _ = std::fs::remove_file(&socket_path);
            let child = spawn_managed_worker(
                &launch_command,
                &socket_path,
                backend_id,
                runtime_profile.backend_worker_contract.as_deref(),
            )?;
            match wait_for_socket(
                &socket_path,
                Duration::from_millis(config.managed_worker_timeout_ms.max(1)),
                child,
            ) {
                WaitOutcome::Ready(child) => {
                    backend_commands.set_backend(
                        backend_id,
                        Some(format!("unix://{}", socket_path.display())),
                    );
                    workers.summary.statuses.push(ManagedWorkerStatus {
                        backend_id: backend_id.to_string(),
                        state: "ready".to_string(),
                        command_source,
                        detail: format!("managed worker ready at {}", socket_path.display()),
                        socket_path: Some(socket_path.clone()),
                    });
                    workers.children.push(ManagedWorkerChild {
                        backend_id: backend_id.to_string(),
                        socket_path,
                        child,
                    });
                }
                WaitOutcome::Exited(code) => {
                    workers.summary.statuses.push(ManagedWorkerStatus {
                        backend_id: backend_id.to_string(),
                        state: "launch-failed".to_string(),
                        command_source,
                        detail: format!("managed worker exited before socket was ready ({code})"),
                        socket_path: Some(socket_path),
                    });
                }
                WaitOutcome::TimedOut(mut child) => {
                    terminate_child(&mut child);
                    workers.summary.statuses.push(ManagedWorkerStatus {
                        backend_id: backend_id.to_string(),
                        state: "launch-timeout".to_string(),
                        command_source,
                        detail: "managed worker socket readiness timed out".to_string(),
                        socket_path: Some(socket_path),
                    });
                }
            }
        }

        Ok(workers)
    }

    pub fn summary(&self) -> ManagedWorkerSummary {
        self.summary.clone()
    }

    pub fn shutdown(&mut self) {
        for child in &mut self.children {
            terminate_child(&mut child.child);
            let _ = std::fs::remove_file(&child.socket_path);
            for status in &mut self.summary.statuses {
                if status.backend_id == child.backend_id && status.state == "ready" {
                    status.state = "stopped".to_string();
                    status.detail = "managed worker stopped".to_string();
                }
            }
        }
        self.children.clear();
    }
}

impl Drop for ManagedAccelWorkers {
    fn drop(&mut self) {
        self.shutdown();
    }
}

enum WaitOutcome {
    Ready(Child),
    Exited(i32),
    TimedOut(Child),
}

fn managed_worker_command(
    config: &Config,
    runtime_profile: &RuntimeProfile,
    backend_id: &str,
) -> (Option<String>, String) {
    match backend_id {
        "local-gpu" => {
            if let Some(command) = config.local_gpu_worker_command.clone() {
                (Some(command), "env".to_string())
            } else if let Some(command) =
                hardware_profile_managed_worker_command(config, runtime_profile, backend_id)
            {
                (Some(command), "hardware-profile".to_string())
            } else {
                (
                    runtime_profile
                        .managed_worker_commands
                        .get(backend_id)
                        .cloned(),
                    "runtime-profile".to_string(),
                )
            }
        }
        "local-npu" => {
            if let Some(command) = config.local_npu_worker_command.clone() {
                (Some(command), "env".to_string())
            } else if let Some(command) =
                hardware_profile_managed_worker_command(config, runtime_profile, backend_id)
            {
                (Some(command), "hardware-profile".to_string())
            } else {
                (
                    runtime_profile
                        .managed_worker_commands
                        .get(backend_id)
                        .cloned(),
                    "runtime-profile".to_string(),
                )
            }
        }
        _ => (None, "unsupported".to_string()),
    }
}

fn hardware_profile_managed_worker_command(
    config: &Config,
    runtime_profile: &RuntimeProfile,
    backend_id: &str,
) -> Option<String> {
    let hardware_profile_id = config.hardware_profile_id.as_deref()?;
    runtime_profile
        .hardware_profile_managed_worker_commands
        .get(hardware_profile_id)
        .and_then(|commands| commands.get(backend_id))
        .cloned()
}

fn spawn_managed_worker(
    launch_command: &str,
    socket_path: &Path,
    backend_id: &str,
    worker_contract: Option<&str>,
) -> anyhow::Result<Child> {
    let mut command = Command::new("/bin/sh");
    command.arg("-lc").arg(launch_command);
    command.env("AIOS_RUNTIME_WORKER_MODE", "unix");
    command.env("AIOS_RUNTIME_WORKER_SOCKET_PATH", socket_path);
    command.env("AIOS_RUNTIME_WORKER_BACKEND_ID", backend_id);
    if let Some(worker_contract) = worker_contract {
        command.env("AIOS_RUNTIME_WORKER_CONTRACT", worker_contract);
    }
    Ok(command.spawn()?)
}

fn wait_for_socket(socket_path: &Path, timeout: Duration, mut child: Child) -> WaitOutcome {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if socket_path.exists() {
            return WaitOutcome::Ready(child);
        }
        if let Ok(Some(status)) = child.try_wait() {
            return WaitOutcome::Exited(status.code().unwrap_or(1));
        }
        thread::sleep(Duration::from_millis(25));
    }

    if socket_path.exists() {
        WaitOutcome::Ready(child)
    } else {
        WaitOutcome::TimedOut(child)
    }
}

fn terminate_child(child: &mut Child) {
    if child.try_wait().ok().flatten().is_some() {
        return;
    }
    let _ = child.kill();
    let _ = child.wait();
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::path::PathBuf;

    use aios_core::ServicePaths;

    use crate::config::Config;
    use crate::scheduler::RuntimeProfile;

    use super::managed_worker_command;

    fn config() -> Config {
        Config {
            service_id: "aios-runtimed".to_string(),
            version: "0.1.0".to_string(),
            paths: ServicePaths {
                state_dir: PathBuf::from("/tmp/runtimed-state"),
                runtime_dir: PathBuf::from("/tmp/runtimed-run"),
                socket_path: PathBuf::from("/tmp/runtimed-run/runtimed.sock"),
            },
            runtime_profile_path: PathBuf::from("/tmp/runtime-profile.yaml"),
            route_profile_path: PathBuf::from("/tmp/route-profile.yaml"),
            policyd_socket: PathBuf::from("/tmp/policyd.sock"),
            remote_audit_log_path: PathBuf::from("/tmp/remote-audit.jsonl"),
            observability_log_path: PathBuf::from("/tmp/observability.jsonl"),
            local_cpu_command: None,
            local_gpu_command: None,
            local_npu_command: None,
            local_gpu_worker_command: None,
            local_npu_worker_command: None,
            hardware_profile_id: None,
            attested_remote_command: None,
            attested_remote_target_hash: None,
            managed_worker_timeout_ms: 5_000,
        }
    }

    fn runtime_profile() -> RuntimeProfile {
        RuntimeProfile {
            profile_id: "smoke".to_string(),
            scope: "system".to_string(),
            default_backend: "local-cpu".to_string(),
            allowed_backends: vec!["local-cpu".to_string(), "local-gpu".to_string()],
            local_model_pool: vec!["smoke-model".to_string()],
            remote_model_pool: Vec::new(),
            backend_worker_contract: Some("runtime-worker-v1".to_string()),
            backend_commands: BTreeMap::new(),
            managed_worker_commands: BTreeMap::new(),
            hardware_profile_managed_worker_commands: BTreeMap::new(),
            embedding_backend: "local-embedding".to_string(),
            rerank_backend: "local-reranker".to_string(),
            cpu_fallback: true,
            memory_budget_mb: 2048,
            kv_cache_budget_mb: 512,
            timeout_ms: 30_000,
            max_concurrency: 2,
            max_parallel_models: 1,
            offload_policy: "manual-only".to_string(),
            degradation_policy: "fallback-local-cpu".to_string(),
            observability_level: "standard".to_string(),
        }
    }

    #[test]
    fn hardware_profile_worker_command_overrides_generic_profile_command() {
        let mut config = config();
        config.hardware_profile_id = Some("nvidia-jetson-orin-agx".to_string());

        let mut runtime_profile = runtime_profile();
        runtime_profile
            .managed_worker_commands
            .insert("local-gpu".to_string(), "echo generic".to_string());
        runtime_profile
            .hardware_profile_managed_worker_commands
            .insert(
                "nvidia-jetson-orin-agx".to_string(),
                BTreeMap::from([("local-gpu".to_string(), "echo jetson".to_string())]),
            );

        let (command, source) = managed_worker_command(&config, &runtime_profile, "local-gpu");

        assert_eq!(command.as_deref(), Some("echo jetson"));
        assert_eq!(source, "hardware-profile");
    }

    #[test]
    fn env_worker_command_overrides_hardware_profile_command() {
        let mut config = config();
        config.hardware_profile_id = Some("nvidia-jetson-orin-agx".to_string());
        config.local_gpu_worker_command = Some("echo env".to_string());

        let mut runtime_profile = runtime_profile();
        runtime_profile
            .hardware_profile_managed_worker_commands
            .insert(
                "nvidia-jetson-orin-agx".to_string(),
                BTreeMap::from([("local-gpu".to_string(), "echo jetson".to_string())]),
            );

        let (command, source) = managed_worker_command(&config, &runtime_profile, "local-gpu");

        assert_eq!(command.as_deref(), Some("echo env"));
        assert_eq!(source, "env");
    }

    #[test]
    fn generic_profile_worker_command_remains_fallback_when_hardware_profile_missing() {
        let mut config = config();
        config.hardware_profile_id = Some("unknown-profile".to_string());

        let mut runtime_profile = runtime_profile();
        runtime_profile
            .managed_worker_commands
            .insert("local-gpu".to_string(), "echo generic".to_string());

        let (command, source) = managed_worker_command(&config, &runtime_profile, "local-gpu");

        assert_eq!(command.as_deref(), Some("echo generic"));
        assert_eq!(source, "runtime-profile");
    }

    #[test]
    fn returns_not_configured_when_no_source_is_available() {
        let (command, source) = managed_worker_command(&config(), &runtime_profile(), "local-gpu");

        assert!(command.is_none());
        assert_eq!(source, "runtime-profile");
    }
}
