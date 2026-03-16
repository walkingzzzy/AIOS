mod config;
mod db;
mod evidence;
mod memory;
mod observability;
mod plan;
mod portal;
mod recovery;
mod rpc;
mod session;
mod task;

use chrono::{DateTime, Utc};

use aios_contracts::HealthResponse;
use aios_portal::{Portal, PortalConfig};
use db::Database;
use memory::WorkingMemoryStore;
use observability::ObservabilitySink;
use plan::TaskPlanStore;
use portal::PortalStore;
use session::SessionStore;
use task::TaskStore;

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub started_at: DateTime<Utc>,
    pub database: Database,
    pub sessions: SessionStore,
    pub tasks: TaskStore,
    pub plans: TaskPlanStore,
    pub memory: WorkingMemoryStore,
    pub portal: PortalStore,
}

impl AppState {
    fn new(config: config::Config, database: Database) -> anyhow::Result<Self> {
        let portal_runtime = Portal::new(PortalConfig {
            state_dir: config.portal_state_dir.clone(),
            default_ttl_seconds: config.portal_default_ttl_seconds,
        })?;

        Ok(Self {
            config,
            started_at: Utc::now(),
            sessions: SessionStore::new(database.clone()),
            tasks: TaskStore::new(database.clone()),
            plans: TaskPlanStore::new(database.clone()),
            memory: WorkingMemoryStore::new(database.clone()),
            portal: PortalStore::new(database.clone(), portal_runtime),
            database,
        })
    }

    fn health(&self) -> HealthResponse {
        let memory_summary = self.database.memory_summary().unwrap_or_default();
        let portal_handle_count = self.database.portal_handle_count().unwrap_or_default();

        HealthResponse {
            service_id: self.config.service_id.clone(),
            status: "ready".to_string(),
            version: self.config.version.clone(),
            started_at: self.started_at.to_rfc3339(),
            socket_path: self.config.paths.socket_path.display().to_string(),
            notes: vec![
                format!("database={}", self.config.database_path.display()),
                format!(
                    "migrations={}",
                    db::migrations_dir(&self.config.migrations_dir).display()
                ),
                format!(
                    "observability_log={}",
                    self.config.observability_log_path.display()
                ),
                format!(
                    "memory=working:{} episodic:{} semantic:{} procedural:{}",
                    memory_summary.working_refs,
                    memory_summary.episodic_entries,
                    memory_summary.semantic_slots,
                    memory_summary.procedural_rules,
                ),
                format!("portal_handles={portal_handle_count}"),
                format!(
                    "portal_state_dir={}",
                    self.config.portal_state_dir.display()
                ),
                format!(
                    "evidence_export_dir={}",
                    self.config.evidence_export_dir.display()
                ),
            ],
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("sessiond");

    let config = config::Config::load().await?;
    let observability_sink = ObservabilitySink::new(config.observability_log_path.clone())?;
    let database = db::bootstrap(&config, Some(observability_sink)).await?;

    let state = AppState::new(config.clone(), database)?;
    let router = rpc::build_router(state);

    tracing::info!(socket = %config.paths.socket_path.display(), "starting aios-sessiond");

    tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => result?,
        _ = tokio::signal::ctrl_c() => tracing::info!("received shutdown signal"),
    }

    Ok(())
}
