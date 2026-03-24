use std::{
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};

use aios_contracts::RuntimeBackendDescriptor;

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

    pub fn enrich_descriptors(
        &self,
        descriptors: &mut [RuntimeBackendDescriptor],
        worker_contract: Option<&str>,
    ) {
        for descriptor in descriptors {
            if let Some(contract) = worker_contract {
                descriptor.worker_contract = Some(contract.to_string());
            }
            if let Some(status) = self.status_for(&descriptor.backend_id) {
                descriptor.worker_state = Some(status.state.clone());
                descriptor.command_source = Some(status.command_source.clone());
                descriptor.detail = Some(status.detail.clone());
                descriptor.socket_path = status
                    .socket_path
                    .as_ref()
                    .map(|path| path.display().to_string());
                descriptor.managed = status.command_source != "backend-command";
                descriptor.health_state =
                    normalize_health_state(status.state.as_str(), &descriptor.availability);
            }
        }
    }

    fn status_for(&self, backend_id: &str) -> Option<&ManagedWorkerStatus> {
        self.statuses
            .iter()
            .find(|status| status.backend_id == backend_id)
    }
}

#[derive(Clone, Debug, Default)]
pub struct SharedManagedWorkerSummary {
    inner: Arc<Mutex<ManagedWorkerSummary>>,
}

impl SharedManagedWorkerSummary {
    pub fn new(summary: ManagedWorkerSummary) -> Self {
        Self {
            inner: Arc::new(Mutex::new(summary)),
        }
    }

    pub fn snapshot(&self) -> ManagedWorkerSummary {
        self.inner
            .lock()
            .expect("managed worker summary mutex poisoned")
            .clone()
    }

    pub fn notes(&self) -> Vec<String> {
        self.snapshot().notes()
    }

    pub fn enrich_descriptors(
        &self,
        descriptors: &mut [RuntimeBackendDescriptor],
        worker_contract: Option<&str>,
    ) {
        self.snapshot()
            .enrich_descriptors(descriptors, worker_contract);
    }

    fn upsert_status(&self, status: ManagedWorkerStatus) {
        let mut summary = self
            .inner
            .lock()
            .expect("managed worker summary mutex poisoned");
        if let Some(existing) = summary
            .statuses
            .iter_mut()
            .find(|item| item.backend_id == status.backend_id)
        {
            *existing = status;
        } else {
            summary.statuses.push(status);
        }
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
    command_source: String,
    launch_command: String,
    restart_attempts: u32,
    child: Child,
}

#[derive(Clone, Debug)]
struct ManagedWorkerMonitorConfig {
    timeout: Duration,
    restart_backoff: Duration,
    monitor_interval: Duration,
    restart_limit: u32,
    worker_contract: Option<String>,
}

#[derive(Debug)]
pub struct ManagedAccelWorkers {
    summary: SharedManagedWorkerSummary,
    children: Arc<Mutex<Vec<ManagedWorkerChild>>>,
    stop_flag: Arc<AtomicBool>,
    monitor_thread: Option<thread::JoinHandle<()>>,
}

impl Default for ManagedAccelWorkers {
    fn default() -> Self {
        Self {
            summary: SharedManagedWorkerSummary::default(),
            children: Arc::new(Mutex::new(Vec::new())),
            stop_flag: Arc::new(AtomicBool::new(false)),
            monitor_thread: None,
        }
    }
}

impl ManagedAccelWorkers {
    pub fn launch(
        config: &Config,
        runtime_profile: &RuntimeProfile,
        backend_commands: &mut BackendCommands,
    ) -> anyhow::Result<Self> {
        let timeout = Duration::from_millis(config.managed_worker_timeout_ms.max(1));
        let mut summary = ManagedWorkerSummary::default();
        let mut children = Vec::new();

        for backend_id in ["local-gpu", "local-npu"] {
            if backend_commands.for_backend(backend_id).is_some() {
                summary.statuses.push(ManagedWorkerStatus {
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
                summary.statuses.push(ManagedWorkerStatus {
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
            match wait_for_socket(&socket_path, timeout, child) {
                WaitOutcome::Ready(child) => {
                    backend_commands.set_backend(
                        backend_id,
                        Some(format!("unix://{}", socket_path.display())),
                    );
                    summary.statuses.push(ManagedWorkerStatus {
                        backend_id: backend_id.to_string(),
                        state: "ready".to_string(),
                        command_source: command_source.clone(),
                        detail: format!("managed worker ready at {}", socket_path.display()),
                        socket_path: Some(socket_path.clone()),
                    });
                    children.push(ManagedWorkerChild {
                        backend_id: backend_id.to_string(),
                        socket_path,
                        command_source,
                        launch_command,
                        restart_attempts: 0,
                        child,
                    });
                }
                WaitOutcome::Exited(code) => {
                    summary.statuses.push(ManagedWorkerStatus {
                        backend_id: backend_id.to_string(),
                        state: "launch-failed".to_string(),
                        command_source,
                        detail: format!("managed worker exited before socket was ready ({code})"),
                        socket_path: Some(socket_path),
                    });
                }
                WaitOutcome::TimedOut(mut child) => {
                    terminate_child(&mut child);
                    summary.statuses.push(ManagedWorkerStatus {
                        backend_id: backend_id.to_string(),
                        state: "launch-timeout".to_string(),
                        command_source,
                        detail: "managed worker socket readiness timed out".to_string(),
                        socket_path: Some(socket_path),
                    });
                }
            }
        }

        let summary = SharedManagedWorkerSummary::new(summary);
        let children = Arc::new(Mutex::new(children));
        let stop_flag = Arc::new(AtomicBool::new(false));
        let monitor_thread = if children
            .lock()
            .expect("managed worker children mutex poisoned")
            .is_empty()
        {
            None
        } else {
            Some(spawn_monitor_thread(
                Arc::clone(&children),
                summary.clone(),
                Arc::clone(&stop_flag),
                ManagedWorkerMonitorConfig {
                    timeout,
                    restart_backoff: Duration::from_millis(
                        config.managed_worker_restart_backoff_ms.max(1),
                    ),
                    monitor_interval: Duration::from_millis(config.backend_health_poll_ms.max(50)),
                    restart_limit: config.managed_worker_restart_limit,
                    worker_contract: runtime_profile.backend_worker_contract.clone(),
                },
            ))
        };

        Ok(Self {
            summary,
            children,
            stop_flag,
            monitor_thread,
        })
    }

    pub fn summary(&self) -> SharedManagedWorkerSummary {
        self.summary.clone()
    }

    pub fn shutdown(&mut self) {
        self.stop_flag.store(true, Ordering::SeqCst);
        if let Some(handle) = self.monitor_thread.take() {
            let _ = handle.join();
        }

        let mut children = self
            .children
            .lock()
            .expect("managed worker children mutex poisoned");
        for child in children.iter_mut() {
            terminate_child(&mut child.child);
            let _ = std::fs::remove_file(&child.socket_path);
            self.summary.upsert_status(ManagedWorkerStatus {
                backend_id: child.backend_id.clone(),
                state: "stopped".to_string(),
                command_source: child.command_source.clone(),
                detail: "managed worker stopped".to_string(),
                socket_path: Some(child.socket_path.clone()),
            });
        }
        children.clear();
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

enum WorkerHealthCheck {
    Healthy,
    Exited(i32),
    SocketMissing,
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

fn managed_worker_shell_command(command: &str) -> Command {
    #[cfg(windows)]
    {
        let mut process = Command::new("powershell.exe");
        process.arg("-Command").arg(command);
        process
    }

    #[cfg(not(windows))]
    {
        let mut process = Command::new("/bin/sh");
        process.arg("-lc").arg(command);
        process
    }
}

fn spawn_managed_worker(
    launch_command: &str,
    socket_path: &Path,
    backend_id: &str,
    worker_contract: Option<&str>,
) -> anyhow::Result<Child> {
    let mut command = managed_worker_shell_command(launch_command);
    command.env("AIOS_RUNTIME_WORKER_MODE", "unix");
    command.env("AIOS_RUNTIME_WORKER_SOCKET_PATH", socket_path);
    command.env("AIOS_RUNTIME_WORKER_BACKEND_ID", backend_id);
    command.stdin(Stdio::null());
    command.stdout(Stdio::null());
    command.stderr(Stdio::null());
    if let Some(worker_contract) = worker_contract {
        command.env("AIOS_RUNTIME_WORKER_CONTRACT", worker_contract);
    }
    Ok(command.spawn()?)
}

fn spawn_monitor_thread(
    children: Arc<Mutex<Vec<ManagedWorkerChild>>>,
    summary: SharedManagedWorkerSummary,
    stop_flag: Arc<AtomicBool>,
    config: ManagedWorkerMonitorConfig,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        while !stop_flag.load(Ordering::SeqCst) {
            let restart_target = {
                let mut guard = children
                    .lock()
                    .expect("managed worker children mutex poisoned");
                guard
                    .iter_mut()
                    .enumerate()
                    .find_map(|(index, child)| match inspect_child(child) {
                        WorkerHealthCheck::Healthy => None,
                        WorkerHealthCheck::Exited(code) => Some((
                            index,
                            format!("managed worker exited unexpectedly ({code})"),
                        )),
                        WorkerHealthCheck::SocketMissing => Some((
                            index,
                            "managed worker socket disappeared while process was still running"
                                .to_string(),
                        )),
                    })
            };

            let Some((index, reason)) = restart_target else {
                thread::sleep(config.monitor_interval);
                continue;
            };

            let child = {
                let mut guard = children
                    .lock()
                    .expect("managed worker children mutex poisoned");
                if index >= guard.len() {
                    continue;
                }
                guard.remove(index)
            };

            let Some(child) = restart_child(child, &summary, &config, &stop_flag, &reason) else {
                continue;
            };

            let mut guard = children
                .lock()
                .expect("managed worker children mutex poisoned");
            let insertion_index = index.min(guard.len());
            guard.insert(insertion_index, child);
        }
    })
}

fn inspect_child(child: &mut ManagedWorkerChild) -> WorkerHealthCheck {
    match child.child.try_wait() {
        Ok(Some(status)) => WorkerHealthCheck::Exited(status.code().unwrap_or(1)),
        Ok(None) => {
            if child.socket_path.exists() {
                WorkerHealthCheck::Healthy
            } else {
                WorkerHealthCheck::SocketMissing
            }
        }
        Err(_) => WorkerHealthCheck::SocketMissing,
    }
}

fn restart_child(
    mut child: ManagedWorkerChild,
    summary: &SharedManagedWorkerSummary,
    config: &ManagedWorkerMonitorConfig,
    stop_flag: &AtomicBool,
    reason: &str,
) -> Option<ManagedWorkerChild> {
    terminate_child(&mut child.child);
    let _ = std::fs::remove_file(&child.socket_path);

    if config.restart_limit == 0 {
        summary.upsert_status(ManagedWorkerStatus {
            backend_id: child.backend_id.clone(),
            state: "restart-exhausted".to_string(),
            command_source: child.command_source.clone(),
            detail: format!(
                "{reason}; automatic restart disabled by managed_worker_restart_limit=0"
            ),
            socket_path: Some(child.socket_path.clone()),
        });
        return None;
    }

    let mut last_detail = format!("{reason}; managed worker restart was not attempted");

    while child.restart_attempts < config.restart_limit && !stop_flag.load(Ordering::SeqCst) {
        child.restart_attempts += 1;
        summary.upsert_status(ManagedWorkerStatus {
            backend_id: child.backend_id.clone(),
            state: "restarting".to_string(),
            command_source: child.command_source.clone(),
            detail: format!(
                "{reason}; restarting attempt {}/{}",
                child.restart_attempts, config.restart_limit
            ),
            socket_path: Some(child.socket_path.clone()),
        });

        thread::sleep(config.restart_backoff);
        let _ = std::fs::remove_file(&child.socket_path);

        let spawned = match spawn_managed_worker(
            &child.launch_command,
            &child.socket_path,
            &child.backend_id,
            config.worker_contract.as_deref(),
        ) {
            Ok(spawned) => spawned,
            Err(error) => {
                last_detail = format!(
                    "managed worker restart spawn failed on attempt {}/{}: {}",
                    child.restart_attempts, config.restart_limit, error
                );
                continue;
            }
        };

        match wait_for_socket(&child.socket_path, config.timeout, spawned) {
            WaitOutcome::Ready(restarted_child) => {
                child.child = restarted_child;
                summary.upsert_status(ManagedWorkerStatus {
                    backend_id: child.backend_id.clone(),
                    state: "ready".to_string(),
                    command_source: child.command_source.clone(),
                    detail: format!(
                        "managed worker restarted at {} (restart_count={})",
                        child.socket_path.display(),
                        child.restart_attempts
                    ),
                    socket_path: Some(child.socket_path.clone()),
                });
                return Some(child);
            }
            WaitOutcome::Exited(code) => {
                last_detail = format!(
                    "managed worker restart exited before socket was ready on attempt {}/{} ({code})",
                    child.restart_attempts, config.restart_limit
                );
            }
            WaitOutcome::TimedOut(mut restarted_child) => {
                terminate_child(&mut restarted_child);
                last_detail = format!(
                    "managed worker restart timed out on attempt {}/{}",
                    child.restart_attempts, config.restart_limit
                );
            }
        }
    }

    summary.upsert_status(ManagedWorkerStatus {
        backend_id: child.backend_id.clone(),
        state: "restart-exhausted".to_string(),
        command_source: child.command_source.clone(),
        detail: last_detail,
        socket_path: Some(child.socket_path.clone()),
    });
    None
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

fn normalize_health_state(worker_state: &str, availability: &str) -> String {
    match worker_state {
        "ready" => "ready".to_string(),
        "external-command" => {
            if availability == "available" || availability == "baseline" {
                "ready".to_string()
            } else {
                "unavailable".to_string()
            }
        }
        "launch-failed" | "launch-timeout" | "not-configured" | "stopped" | "restarting"
        | "restart-exhausted" => "unavailable".to_string(),
        _ if availability == "available" || availability == "baseline" => "ready".to_string(),
        _ => "unavailable".to_string(),
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
    use std::{
        collections::BTreeMap,
        path::PathBuf,
        sync::atomic::AtomicBool,
        time::{Duration, SystemTime, UNIX_EPOCH},
    };

    use aios_contracts::RuntimeBackendDescriptor;
    use aios_core::ServicePaths;

    use crate::config::Config;
    use crate::scheduler::RuntimeProfile;

    use super::{
        managed_worker_command, managed_worker_shell_command, normalize_health_state,
        restart_child, ManagedWorkerChild, ManagedWorkerMonitorConfig, ManagedWorkerStatus,
        ManagedWorkerSummary, SharedManagedWorkerSummary,
    };

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
            managed_worker_restart_backoff_ms: 250,
            managed_worker_restart_limit: 3,
            backend_health_poll_ms: 250,
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

    fn exit_command(code: i32) -> String {
        format!("exit {code}")
    }

    fn temp_socket_path(name: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time")
            .as_nanos();
        std::env::temp_dir().join(format!("aios-{name}-{suffix}.sock"))
    }

    fn spawn_exit_child(code: i32) -> std::process::Child {
        managed_worker_shell_command(&exit_command(code))
            .spawn()
            .expect("spawn exit child")
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

    #[test]
    fn enriches_backend_descriptor_with_managed_worker_status() {
        let summary = ManagedWorkerSummary {
            statuses: vec![ManagedWorkerStatus {
                backend_id: "local-gpu".to_string(),
                state: "ready".to_string(),
                command_source: "runtime-profile".to_string(),
                detail: "managed worker ready".to_string(),
                socket_path: Some(PathBuf::from("/tmp/local-gpu.sock")),
            }],
        };
        let mut descriptors = vec![RuntimeBackendDescriptor {
            backend_id: "local-gpu".to_string(),
            availability: "available".to_string(),
            activation: "configured-unix-worker".to_string(),
            health_state: "unknown".to_string(),
            reason: "gpu worker ready".to_string(),
            managed: false,
            fallback_backend: Some("local-cpu".to_string()),
            worker_contract: None,
            worker_state: None,
            command_source: None,
            detail: None,
            socket_path: None,
        }];

        summary.enrich_descriptors(&mut descriptors, Some("runtime-worker-v1"));

        assert_eq!(descriptors[0].health_state, "ready");
        assert!(descriptors[0].managed);
        assert_eq!(
            descriptors[0].worker_contract.as_deref(),
            Some("runtime-worker-v1")
        );
        assert_eq!(descriptors[0].worker_state.as_deref(), Some("ready"));
        assert_eq!(
            descriptors[0].socket_path.as_deref(),
            Some("/tmp/local-gpu.sock")
        );
    }

    #[test]
    fn shared_summary_updates_existing_status_in_place() {
        let shared = SharedManagedWorkerSummary::new(ManagedWorkerSummary {
            statuses: vec![ManagedWorkerStatus {
                backend_id: "local-gpu".to_string(),
                state: "ready".to_string(),
                command_source: "runtime-profile".to_string(),
                detail: "managed worker ready".to_string(),
                socket_path: Some(PathBuf::from("/tmp/local-gpu.sock")),
            }],
        });

        shared.upsert_status(ManagedWorkerStatus {
            backend_id: "local-gpu".to_string(),
            state: "restarting".to_string(),
            command_source: "runtime-profile".to_string(),
            detail: "managed worker restarting".to_string(),
            socket_path: Some(PathBuf::from("/tmp/local-gpu.sock")),
        });

        let snapshot = shared.snapshot();
        assert_eq!(snapshot.statuses.len(), 1);
        assert_eq!(snapshot.statuses[0].state, "restarting");
    }

    #[test]
    fn restart_child_reports_restart_exhausted_when_automatic_restart_is_disabled() {
        let summary = SharedManagedWorkerSummary::default();
        let socket_path = temp_socket_path("restart-disabled");
        let result = restart_child(
            ManagedWorkerChild {
                backend_id: "local-gpu".to_string(),
                socket_path: socket_path.clone(),
                command_source: "runtime-profile".to_string(),
                launch_command: exit_command(23),
                restart_attempts: 0,
                child: spawn_exit_child(23),
            },
            &summary,
            &ManagedWorkerMonitorConfig {
                timeout: Duration::from_millis(25),
                restart_backoff: Duration::from_millis(1),
                monitor_interval: Duration::from_millis(1),
                restart_limit: 0,
                worker_contract: None,
            },
            &AtomicBool::new(false),
            "managed worker crashed during shutdown window",
        );

        assert!(result.is_none());
        let snapshot = summary.snapshot();
        assert_eq!(snapshot.statuses.len(), 1);
        assert_eq!(snapshot.statuses[0].state, "restart-exhausted");
        assert!(snapshot.statuses[0]
            .detail
            .contains("managed_worker_restart_limit=0"));
        assert_eq!(
            snapshot.statuses[0].socket_path.as_ref(),
            Some(&socket_path)
        );
    }

    #[test]
    fn restart_child_marks_restart_exhausted_after_repeated_spawn_failures() {
        let summary = SharedManagedWorkerSummary::default();
        let socket_path = temp_socket_path("restart-exhausted");
        let result = restart_child(
            ManagedWorkerChild {
                backend_id: "local-gpu".to_string(),
                socket_path: socket_path.clone(),
                command_source: "runtime-profile".to_string(),
                launch_command: exit_command(17),
                restart_attempts: 0,
                child: spawn_exit_child(17),
            },
            &summary,
            &ManagedWorkerMonitorConfig {
                timeout: Duration::from_millis(25),
                restart_backoff: Duration::from_millis(1),
                monitor_interval: Duration::from_millis(1),
                restart_limit: 2,
                worker_contract: None,
            },
            &AtomicBool::new(false),
            "managed worker exited unexpectedly (17)",
        );

        assert!(result.is_none());
        let snapshot = summary.snapshot();
        assert_eq!(snapshot.statuses.len(), 1);
        assert_eq!(snapshot.statuses[0].state, "restart-exhausted");
        assert!(snapshot.statuses[0].detail.contains("attempt 2/2"));
        assert_eq!(
            snapshot.statuses[0].socket_path.as_ref(),
            Some(&socket_path)
        );
    }

    #[test]
    fn restarting_worker_state_is_marked_unavailable() {
        assert_eq!(
            normalize_health_state("restarting", "available"),
            "unavailable"
        );
        assert_eq!(
            normalize_health_state("restart-exhausted", "available"),
            "unavailable"
        );
    }
}
