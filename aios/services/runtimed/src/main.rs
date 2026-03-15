mod backend;
mod budget;
mod config;
mod events;
mod events_persistence;
mod managed_workers;
mod observability;
mod queue;
mod remote_audit;
mod remote_security;
mod rpc;
mod scheduler;

use chrono::{DateTime, Utc};

use aios_contracts::HealthResponse;
use budget::BudgetState;
use events::EventStore;
use managed_workers::ManagedWorkerSummary;
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
    pub managed_workers: ManagedWorkerSummary,
}

impl AppState {
    fn health(&self) -> HealthResponse {
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

    let router = rpc::build_router(state);

    tracing::info!(socket = %config.paths.socket_path.display(), "starting aios-runtimed");

    tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => result?,
        _ = tokio::signal::ctrl_c() => tracing::info!("received shutdown signal"),
    }

    managed_workers.shutdown();

    Ok(())
}
