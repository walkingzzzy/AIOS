mod clients;
mod config;
mod execution;
mod planner;
mod portal;
mod providers;
mod recovery;
mod resolver;
mod rpc;
mod topology;

use chrono::{DateTime, Utc};

use aios_contracts::HealthResponse;
use aios_provider_registry::{ProviderRegistry, RegistryConfig};

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub provider_registry: ProviderRegistry,
    pub started_at: DateTime<Utc>,
}

impl AppState {
    fn health(&self) -> HealthResponse {
        HealthResponse {
            service_id: self.config.service_id.clone(),
            status: "ready".to_string(),
            version: self.config.version.clone(),
            started_at: self.started_at.to_rfc3339(),
            socket_path: self.config.paths.socket_path.display().to_string(),
            notes: vec![
                format!("sessiond_socket={}", self.config.sessiond_socket.display()),
                format!("policyd_socket={}", self.config.policyd_socket.display()),
                format!("runtimed_socket={}", self.config.runtimed_socket.display()),
                format!(
                    "provider_registry_state_dir={}",
                    self.config.provider_registry_state_dir.display()
                ),
                format!(
                    "provider_descriptor_dirs={}",
                    self.config
                        .provider_descriptor_dirs
                        .iter()
                        .map(|path| path.display().to_string())
                        .collect::<Vec<_>>()
                        .join(":")
                ),
                format!(
                    "system_intent_provider_socket={}",
                    self.config.system_intent_provider_socket.display()
                ),
                format!(
                    "system_files_provider_socket={}",
                    self.config.system_files_provider_socket.display()
                ),
            ],
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("agentd");

    let config = config::Config::load().await?;
    let provider_registry = ProviderRegistry::new(RegistryConfig {
        state_dir: config.provider_registry_state_dir.clone(),
        descriptor_dirs: config.provider_descriptor_dirs.clone(),
    })?;
    let state = AppState {
        config: config.clone(),
        provider_registry,
        started_at: Utc::now(),
    };

    let router = rpc::build_router(state);

    tracing::info!(socket = %config.paths.socket_path.display(), "starting aios-agentd skeleton");

    tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => result?,
        _ = tokio::signal::ctrl_c() => tracing::info!("received shutdown signal"),
    }

    Ok(())
}
