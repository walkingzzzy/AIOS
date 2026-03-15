mod approval;
mod audit;
mod catalog;
mod config;
mod evaluator;
mod observability;
mod rpc;
mod taint;
mod token;
mod token_usage;

use chrono::{DateTime, Utc};

use aios_contracts::HealthResponse;
use approval::ApprovalStore;
use audit::{AuditStoreConfig, AuditWriter};
use catalog::CapabilityCatalog;
use evaluator::PolicyProfile;
use observability::ObservabilitySink;
use token_usage::TokenUsageStore;

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub started_at: DateTime<Utc>,
    pub profile: PolicyProfile,
    pub capability_catalog: CapabilityCatalog,
    pub audit_writer: AuditWriter,
    pub signing_key: String,
    pub approval_store: ApprovalStore,
    pub token_usage_store: TokenUsageStore,
}

impl AppState {
    fn health(&self) -> HealthResponse {
        let pending_approvals = self.approval_store.pending_count().unwrap_or_default();

        HealthResponse {
            service_id: self.config.service_id.clone(),
            status: "ready".to_string(),
            version: self.config.version.clone(),
            started_at: self.started_at.to_rfc3339(),
            socket_path: self.config.paths.socket_path.display().to_string(),
            notes: vec![
                format!("policy={}", self.config.policy_path.display()),
                format!(
                    "capability_catalog={}",
                    self.config.capability_catalog_path.display()
                ),
                format!(
                    "capability_catalog_entries={}",
                    self.capability_catalog.len()
                ),
                format!("audit={}", self.config.audit_log_path.display()),
                format!("audit_index={}", self.audit_writer.index_path().display()),
                format!(
                    "audit_archive_dir={}",
                    self.audit_writer.archive_dir().display()
                ),
                format!(
                    "observability_log={}",
                    self.config.observability_log_path.display()
                ),
                format!("token_key={}", self.config.token_key_path.display()),
                format!("token_usage_dir={}", self.config.token_usage_dir.display()),
                format!(
                    "token_key_fingerprint={}",
                    token::key_fingerprint(&self.signing_key)
                ),
                format!(
                    "consumed_high_risk_tokens={}",
                    self.token_usage_store.consumed_count().unwrap_or_default()
                ),
                format!("ttl_seconds={}", self.config.token_ttl_seconds),
                format!("approval_ttl_seconds={}", self.config.approval_ttl_seconds),
                format!(
                    "audit_rotate_after_bytes={}",
                    self.audit_writer.rotate_after_bytes()
                ),
                format!(
                    "audit_retention_days={}",
                    self.audit_writer.retention_days()
                ),
                format!("audit_max_archives={}", self.audit_writer.max_archives()),
                format!(
                    "audit_archived_segments={}",
                    self.audit_writer
                        .archived_segment_count()
                        .unwrap_or_default()
                ),
                format!(
                    "approval_state_dir={}",
                    self.approval_store.state_dir().display()
                ),
                format!("pending_approvals={pending_approvals}"),
            ],
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("policyd");

    let config = config::Config::load().await?;
    let profile = evaluator::PolicyProfile::load(&config.policy_path)?;
    let capability_catalog = CapabilityCatalog::load(&config.capability_catalog_path)?;
    let observability_sink = ObservabilitySink::new(config.observability_log_path.clone())?;
    let audit_writer = AuditWriter::with_store_config(
        config.audit_log_path.clone(),
        Some(observability_sink),
        AuditStoreConfig {
            index_path: config.audit_index_path.clone(),
            archive_dir: config.audit_archive_dir.clone(),
            rotate_after_bytes: config.audit_rotate_after_bytes,
            retention_days: config.audit_retention_days,
            max_archives: config.audit_max_archives,
        },
    );
    let signing_key = token::ensure_key(&config.token_key_path)?;
    let approval_store =
        ApprovalStore::new(config.paths.state_dir.clone(), config.approval_ttl_seconds)?;
    let token_usage_store = TokenUsageStore::new(config.token_usage_dir.clone())?;

    let state = AppState {
        config: config.clone(),
        started_at: Utc::now(),
        profile,
        capability_catalog,
        audit_writer,
        signing_key,
        approval_store,
        token_usage_store,
    };

    let router = rpc::build_router(state);

    tracing::info!(socket = %config.paths.socket_path.display(), "starting aios-policyd");

    tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => result?,
        _ = tokio::signal::ctrl_c() => tracing::info!("received shutdown signal"),
    }

    Ok(())
}
