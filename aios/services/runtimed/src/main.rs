mod backend;
mod budget;
mod config;
mod events;
mod events_persistence;
mod export;
mod managed_workers;
mod observability;
mod queue;
mod remote_audit;
mod remote_security;
mod rpc;
mod scheduler;
mod trace_query;

use std::time::Duration;

use chrono::{DateTime, Utc};
use serde_json::json;
use tokio::{
    sync::watch,
    time::{self, MissedTickBehavior},
};

use aios_contracts::{HealthResponse, RuntimeBackendDescriptor};
use budget::BudgetState;
use events::EventStore;
use managed_workers::SharedManagedWorkerSummary;
use observability::ObservabilitySink;
use queue::QueueStats;
use remote_audit::RemoteAuditWriter;
use scheduler::Scheduler;

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub started_at: DateTime<Utc>,
    pub scheduler: Scheduler,
    pub queue: QueueStats,
    pub budget: BudgetState,
    pub events: EventStore,
    pub remote_audit: RemoteAuditWriter,
    pub managed_workers: SharedManagedWorkerSummary,
}

impl AppState {
    fn runtime_backends(&self) -> Vec<RuntimeBackendDescriptor> {
        let mut backends = self.scheduler.backends();
        self.managed_workers.enrich_descriptors(
            &mut backends,
            self.scheduler
                .runtime_profile
                .backend_worker_contract
                .as_deref(),
        );
        backends
    }

    fn backend_health_fingerprint(&self) -> String {
        runtime_backend_fingerprint(&self.runtime_backends())
    }

    fn emit_backend_health_events(&self) {
        for backend in self.runtime_backends() {
            let payload = serde_json::to_value(&backend).unwrap_or_else(|error| {
                json!({
                    "backend_id": backend.backend_id,
                    "health_state": backend.health_state,
                    "reason": format!("failed to serialize runtime backend health: {error}"),
                })
            });
            self.events
                .record("runtime.backend.health", None, None, payload);
        }
    }

    fn health(&self) -> HealthResponse {
        let backends = self.runtime_backends();
        let mut notes = self.budget.notes();
        notes.push(format!(
            "runtime_profile={}",
            self.config.runtime_profile_path.display()
        ));
        notes.push(format!(
            "route_profile={}",
            self.config.route_profile_path.display()
        ));
        notes.push(format!(
            "configured_wrappers={}",
            [
                self.scheduler.backend_commands.local_cpu.is_some(),
                self.scheduler.backend_commands.local_gpu.is_some(),
                self.scheduler.backend_commands.local_npu.is_some(),
                self.scheduler.backend_commands.attested_remote.is_some(),
            ]
            .into_iter()
            .filter(|item| *item)
            .count()
        ));
        if let Some(contract) = self
            .scheduler
            .runtime_profile
            .backend_worker_contract
            .as_deref()
        {
            notes.push(format!("backend_worker_contract={contract}"));
        }
        notes.push(format!(
            "backend_health_poll_ms={}",
            self.config.backend_health_poll_ms
        ));
        notes.push(format!("pending_queue={}", self.queue.snapshot()));
        notes.push(format!("runtime_events={}", self.events.len()));
        notes.push(format!(
            "policyd_socket={}",
            self.config.policyd_socket.display()
        ));
        notes.push(format!(
            "remote_audit_log={}",
            self.remote_audit.path().display()
        ));
        notes.push(format!(
            "observability_log={}",
            self.config.observability_log_path.display()
        ));
        if let Some(hardware_profile_id) = &self.config.hardware_profile_id {
            notes.push(format!("hardware_profile_id={hardware_profile_id}"));
        }
        if let Some(target_hash) = &self.config.attested_remote_target_hash {
            notes.push(format!("attested_remote_target_hash={target_hash}"));
        }
        notes.extend(runtime_backend_notes(&backends));
        notes.extend(self.managed_workers.notes());

        HealthResponse {
            service_id: self.config.service_id.clone(),
            status: "ready".to_string(),
            version: self.config.version.clone(),
            started_at: self.started_at.to_rfc3339(),
            socket_path: self.config.paths.socket_path.display().to_string(),
            notes,
        }
    }
}

fn runtime_backend_notes(backends: &[RuntimeBackendDescriptor]) -> Vec<String> {
    let mut notes = Vec::new();
    for backend in backends {
        notes.push(format!(
            "backend_availability.{}={}",
            backend.backend_id, backend.availability
        ));
        notes.push(format!(
            "backend_activation.{}={}",
            backend.backend_id, backend.activation
        ));
        notes.push(format!(
            "backend_health_state.{}={}",
            backend.backend_id, backend.health_state
        ));
        if !backend.reason.is_empty() {
            notes.push(format!(
                "backend_reason.{}={}",
                backend.backend_id, backend.reason
            ));
        }
        if let Some(worker_state) = &backend.worker_state {
            notes.push(format!(
                "backend_worker_state.{}={}",
                backend.backend_id, worker_state
            ));
        }
        if let Some(command_source) = &backend.command_source {
            notes.push(format!(
                "backend_command_source.{}={}",
                backend.backend_id, command_source
            ));
        }
        if let Some(socket_path) = &backend.socket_path {
            notes.push(format!(
                "backend_socket_path.{}={}",
                backend.backend_id, socket_path
            ));
        }
        if let Some(fallback_backend) = &backend.fallback_backend {
            notes.push(format!(
                "backend_fallback.{}={}",
                backend.backend_id, fallback_backend
            ));
        }
    }
    notes
}

fn runtime_backend_fingerprint(backends: &[RuntimeBackendDescriptor]) -> String {
    let mut normalized = backends.to_vec();
    normalized.sort_by(|left, right| left.backend_id.cmp(&right.backend_id));
    serde_json::to_string(&normalized).unwrap_or_else(|_| {
        normalized
            .iter()
            .map(|backend| {
                format!(
                    "{}:{}:{}:{}:{}:{:?}:{:?}:{:?}:{:?}",
                    backend.backend_id,
                    backend.availability,
                    backend.activation,
                    backend.health_state,
                    backend.reason,
                    backend.worker_state,
                    backend.command_source,
                    backend.detail,
                    backend.socket_path,
                )
            })
            .collect::<Vec<_>>()
            .join("|")
    })
}

fn spawn_backend_health_watcher(
    state: AppState,
) -> (watch::Sender<bool>, tokio::task::JoinHandle<()>) {
    let (shutdown_tx, mut shutdown_rx) = watch::channel(false);
    let mut last_fingerprint = state.backend_health_fingerprint();
    let poll_interval = Duration::from_millis(state.config.backend_health_poll_ms.max(50));

    let handle = tokio::spawn(async move {
        let mut interval = time::interval(poll_interval);
        interval.set_missed_tick_behavior(MissedTickBehavior::Delay);

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    let backends = state.runtime_backends();
                    let fingerprint = runtime_backend_fingerprint(&backends);
                    if fingerprint != last_fingerprint {
                        last_fingerprint = fingerprint;
                        state.emit_backend_health_events();
                    }
                }
                changed = shutdown_rx.changed() => match changed {
                    Ok(()) if *shutdown_rx.borrow() => break,
                    Ok(()) => {}
                    Err(_) => break,
                },
            }
        }
    });

    (shutdown_tx, handle)
}

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("runtimed");

    let config = config::Config::load().await?;
    let mut scheduler = Scheduler::load(
        &config.runtime_profile_path,
        &config.route_profile_path,
        backend::BackendCommands {
            local_cpu: config.local_cpu_command.clone(),
            local_gpu: config.local_gpu_command.clone(),
            local_npu: config.local_npu_command.clone(),
            attested_remote: config.attested_remote_command.clone(),
        },
    )?;
    let mut managed_workers = managed_workers::ManagedAccelWorkers::launch(
        &config,
        &scheduler.runtime_profile,
        &mut scheduler.backend_commands,
    )?;
    let queue = QueueStats::default();
    let budget = BudgetState::from_scheduler(&scheduler);
    let observability_sink = ObservabilitySink::new(config.observability_log_path.clone())?;
    let events = EventStore::with_persistence_and_sink(
        config.paths.state_dir.join("runtime-events.jsonl"),
        Some(observability_sink.clone()),
    );
    let remote_audit = RemoteAuditWriter::with_sink(
        config.remote_audit_log_path.clone(),
        Some(observability_sink),
    );

    let state = AppState {
        config: config.clone(),
        started_at: Utc::now(),
        scheduler,
        queue,
        budget,
        events,
        remote_audit,
        managed_workers: managed_workers.summary(),
    };
    state.emit_backend_health_events();
    let (backend_health_stop, backend_health_task) = spawn_backend_health_watcher(state.clone());

    let router = rpc::build_router(state.clone());

    tracing::info!(socket = %config.paths.socket_path.display(), "starting aios-runtimed");

    let server_result = tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => result.map_err(anyhow::Error::from),
        _ = tokio::signal::ctrl_c() => {
            tracing::info!("received shutdown signal");
            Ok(())
        }
    };

    let _ = backend_health_stop.send(true);
    let _ = backend_health_task.await;
    managed_workers.shutdown();
    state.emit_backend_health_events();

    server_result
}
