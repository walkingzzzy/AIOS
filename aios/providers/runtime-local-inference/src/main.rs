mod budget;
mod clients;
mod config;
mod ops;
mod rpc;

use std::time::Duration;

use chrono::{DateTime, Utc};
use serde_json::json;
use tokio::time::MissedTickBehavior;

use aios_contracts::HealthResponse;
use aios_core::{ProviderObservabilitySink, RegistrySyncStatus};

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub started_at: DateTime<Utc>,
    pub concurrency_budget: budget::ConcurrencyBudget,
    pub registry_sync: RegistrySyncStatus,
    pub observability: ProviderObservabilitySink,
}

impl AppState {
    fn health(&self) -> HealthResponse {
        let ai_readiness = self.config.load_ai_readiness_summary();
        let mut notes = vec![
            format!("provider_id={}", self.config.provider_id),
            format!("runtimed_socket={}", self.config.runtimed_socket.display()),
            format!("policyd_socket={}", self.config.policyd_socket.display()),
            format!("agentd_socket={}", self.config.agentd_socket.display()),
            format!("descriptor_path={}", self.config.descriptor_path.display()),
            format!(
                "observability_log_path={}",
                self.config.observability_log_path.display()
            ),
            format!("max_concurrency={}", self.config.max_concurrency),
            format!("embedding_backend={}", self.config.embedding_backend),
            format!("rerank_backend={}", self.config.rerank_backend),
            format!(
                "ai_readiness_path={}",
                self.config.ai_readiness_path.display()
            ),
            format!(
                "ai_onboarding_report_path={}",
                self.config.ai_onboarding_report_path.display()
            ),
            format!(
                "remote_endpoint_configured={}",
                if self.config.remote_endpoint_config().is_some() {
                    "true"
                } else {
                    "false"
                }
            ),
            format!(
                "remote_api_key_configured={}",
                if self.config.remote_api_key.is_some() {
                    "true"
                } else {
                    "false"
                }
            ),
            format!(
                "provider_enabled={}",
                if ai_readiness.provider_enabled() {
                    "true"
                } else {
                    "false"
                }
            ),
            format!(
                "route_preference={}",
                ai_readiness.effective_route_preference()
            ),
        ];
        if let Some(base_url) = self.config.remote_base_url.as_deref() {
            notes.push(format!("remote_base_url={base_url}"));
        }
        if let Some(model) = self.config.remote_model.as_deref() {
            notes.push(format!("remote_model={model}"));
        }
        if let Some(model) = self.config.remote_embedding_model.as_deref() {
            notes.push(format!("remote_embedding_model={model}"));
        }
        if let Some(model) = self.config.remote_rerank_model.as_deref() {
            notes.push(format!("remote_rerank_model={model}"));
        }
        notes.push(format!(
            "ai_readiness_state={}",
            ai_readiness.state.as_deref().unwrap_or("unknown")
        ));
        notes.push(format!(
            "ai_endpoint_ready={}",
            if ai_readiness.endpoint_configured {
                "true"
            } else {
                "false"
            }
        ));
        notes.push(format!(
            "remote_embedding_endpoint_configured={}",
            if self.config.remote_embedding_endpoint_config(None).is_some() {
                "true"
            } else {
                "false"
            }
        ));
        notes.push(format!(
            "remote_rerank_endpoint_configured={}",
            if self.config.remote_rerank_endpoint_config(None).is_some() {
                "true"
            } else {
                "false"
            }
        ));
        notes.extend(self.registry_sync.health_notes());

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

fn provider_overall_status(status: &str) -> &'static str {
    match status {
        "available" => "ready",
        "degraded" => "degraded",
        "disabled" | "unavailable" => "blocked",
        _ => "failed",
    }
}

fn emit_trace(state: &AppState, kind: &str, payload: serde_json::Value, notes: Vec<String>) {
    if let Err(error) = state.observability.append_trace(
        kind,
        Some(&state.config.paths.socket_path),
        payload,
        notes,
    ) {
        tracing::debug!(
            ?error,
            kind,
            "failed to append provider observability trace event"
        );
    }
}

fn emit_health_event(
    state: &AppState,
    source: &str,
    status: &str,
    summary: &str,
    notes: Vec<String>,
) {
    if let Err(error) = state.observability.append_health_event(
        source,
        provider_overall_status(status),
        Some(summary),
        Some(&state.config.paths.socket_path),
        notes,
    ) {
        tracing::debug!(
            ?error,
            source,
            status,
            "failed to append provider health event"
        );
    }
}

async fn self_register_with_registry(state: &AppState, attempts: usize) -> bool {
    let Some(parent) = state.config.agentd_socket.parent() else {
        return false;
    };
    if !parent.exists() {
        return false;
    }
    if !state.config.descriptor_path.exists() {
        state.registry_sync.record_descriptor_missing();
        emit_trace(
            state,
            "provider.registry.descriptor-missing",
            json!({
                "agentd_socket": state.config.agentd_socket.display().to_string(),
                "descriptor_path": state.config.descriptor_path.display().to_string(),
            }),
            vec!["registration_state=descriptor-missing".to_string()],
        );
        tracing::warn!(
            provider_id = %state.config.provider_id,
            descriptor_path = %state.config.descriptor_path.display(),
            "provider descriptor missing; skipping self-registration"
        );
        return false;
    }

    for attempt in 0..attempts {
        match crate::clients::register_provider(state) {
            Ok(_) => {
                state.registry_sync.record_startup_registration_succeeded();
                emit_trace(
                    state,
                    "provider.registry.registered",
                    json!({
                        "agentd_socket": state.config.agentd_socket.display().to_string(),
                        "descriptor_path": state.config.descriptor_path.display().to_string(),
                        "attempt": attempt + 1,
                    }),
                    vec!["registration_state=startup-registered".to_string()],
                );
                return true;
            }
            Err(error) => {
                if attempt + 1 >= attempts {
                    state
                        .registry_sync
                        .record_startup_registration_failed(error.to_string());
                    emit_trace(
                        state,
                        "provider.registry.registration-failed",
                        json!({
                            "agentd_socket": state.config.agentd_socket.display().to_string(),
                            "descriptor_path": state.config.descriptor_path.display().to_string(),
                            "attempts": attempts,
                            "error": error.to_string(),
                        }),
                        vec!["registration_state=startup-pending".to_string()],
                    );
                    tracing::warn!(
                        provider_id = %state.config.provider_id,
                        agentd_socket = %state.config.agentd_socket.display(),
                        ?error,
                        "failed to self-register provider with agentd"
                    );
                    return false;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }

    false
}

async fn report_registry_health(
    state: &AppState,
    status: &str,
    last_error: Option<String>,
    event_source: &str,
    attempts: usize,
) {
    let Some(parent) = state.config.agentd_socket.parent() else {
        return;
    };
    if !parent.exists() {
        return;
    }

    for attempt in 0..attempts {
        match crate::clients::report_provider_health(state, status, last_error.clone()) {
            Ok(_) => {
                state
                    .registry_sync
                    .record_health_report(status, last_error.clone());
                emit_health_event(
                    state,
                    event_source,
                    status,
                    "reported provider health to agentd",
                    vec![
                        format!("registry_status={status}"),
                        format!(
                            "last_error={}",
                            last_error.clone().unwrap_or_else(|| "<none>".to_string())
                        ),
                    ],
                );
                return;
            }
            Err(error) => {
                if attempt + 1 >= attempts {
                    state
                        .registry_sync
                        .record_health_sync_failure(error.to_string());
                    emit_trace(
                        state,
                        "provider.registry.health-sync-failed",
                        json!({
                            "agentd_socket": state.config.agentd_socket.display().to_string(),
                            "status": status,
                            "last_error": last_error.clone(),
                            "attempts": attempts,
                            "error": error.to_string(),
                        }),
                        vec!["health_sync=failed".to_string()],
                    );
                    tracing::warn!(
                        provider_id = %state.config.provider_id,
                        status,
                        ?error,
                        "failed to report provider health to agentd"
                    );
                    return;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
}

async fn probe_runtime_health(state: &AppState, attempts: usize) -> (String, Option<String>) {
    let ai_readiness = state.config.load_ai_readiness_summary();
    if !ai_readiness.provider_enabled() {
        return (
            "disabled".to_string(),
            Some("AI provider disabled via runtime platform env".to_string()),
        );
    }
    let remote_ready =
        state.config.remote_endpoint_config().is_some() && ai_readiness.remote_fallback_allowed();
    if ai_readiness.remote_only_preferred() && !remote_ready {
        return (
            "unavailable".to_string(),
            Some("remote-only route selected but endpoint is not configured".to_string()),
        );
    }

    for attempt in 0..attempts {
        match crate::clients::fetch_runtime_health(state) {
            Ok(_) => return ("available".to_string(), None),
            Err(error) if attempt + 1 < attempts => {
                tokio::time::sleep(Duration::from_millis(100)).await;
                if !state.config.runtimed_socket.exists() {
                    continue;
                }
                tracing::debug!(?error, "runtimed probe failed during startup, retrying");
            }
            Err(error) => {
                if ai_readiness.remote_only_preferred() && remote_ready {
                    return (
                        "available".to_string(),
                        Some("local runtime unavailable; remote endpoint configured".to_string()),
                    );
                }
                if remote_ready {
                    return (
                        "degraded".to_string(),
                        Some(format!(
                            "local runtime unavailable; remote endpoint configured: {}",
                            error
                        )),
                    );
                }
                return ("unavailable".to_string(), Some(error.to_string()));
            }
        }
    }

    if ai_readiness.remote_only_preferred() && remote_ready {
        (
            "available".to_string(),
            Some("local runtime probe exhausted; remote endpoint configured".to_string()),
        )
    } else if remote_ready {
        (
            "degraded".to_string(),
            Some("local runtime probe exhausted; remote endpoint configured".to_string()),
        )
    } else {
        (
            "unavailable".to_string(),
            Some("runtimed probe exhausted".to_string()),
        )
    }
}

async fn sync_registry_state_once(state: &AppState, registration_succeeded: &mut bool) {
    let Some(parent) = state.config.agentd_socket.parent() else {
        return;
    };
    if !parent.exists() {
        return;
    }

    if !*registration_succeeded && state.config.descriptor_path.exists() {
        match crate::clients::register_provider(state) {
            Ok(_) => {
                *registration_succeeded = true;
                state.registry_sync.record_registration_recovered();
                emit_trace(
                    state,
                    "provider.registry.recovered",
                    json!({
                        "agentd_socket": state.config.agentd_socket.display().to_string(),
                        "descriptor_path": state.config.descriptor_path.display().to_string(),
                    }),
                    vec!["registration_state=recovered".to_string()],
                );
                tracing::info!(
                    provider_id = %state.config.provider_id,
                    "registry sync recovered provider registration"
                );
            }
            Err(error) => {
                state
                    .registry_sync
                    .record_registration_retry_failed(error.to_string());
                emit_trace(
                    state,
                    "provider.registry.retry-failed",
                    json!({
                        "agentd_socket": state.config.agentd_socket.display().to_string(),
                        "descriptor_path": state.config.descriptor_path.display().to_string(),
                        "error": error.to_string(),
                    }),
                    vec!["registration_state=retrying".to_string()],
                );
                tracing::debug!(
                    provider_id = %state.config.provider_id,
                    agentd_socket = %state.config.agentd_socket.display(),
                    ?error,
                    "background provider registration retry failed"
                );
            }
        }
    }

    let (status, last_error) = probe_runtime_health(state, 1).await;
    match crate::clients::report_provider_health(state, &status, last_error.clone()) {
        Ok(_) => {
            state
                .registry_sync
                .record_health_report(&status, last_error.clone());
            emit_health_event(
                state,
                "background",
                &status,
                "reported provider health to agentd",
                vec![
                    format!("registry_status={status}"),
                    format!(
                        "last_error={}",
                        last_error.clone().unwrap_or_else(|| "<none>".to_string())
                    ),
                ],
            );
        }
        Err(error) => {
            state
                .registry_sync
                .record_health_sync_failure(error.to_string());
            emit_trace(
                state,
                "provider.registry.health-sync-failed",
                json!({
                    "agentd_socket": state.config.agentd_socket.display().to_string(),
                    "status": status,
                    "last_error": last_error.clone(),
                    "error": error.to_string(),
                }),
                vec!["health_sync=failed".to_string()],
            );
            tracing::debug!(
                provider_id = %state.config.provider_id,
                status,
                ?last_error,
                ?error,
                "background provider health sync failed"
            );
        }
    }
}

async fn run_registry_sync_loop(state: AppState, registration_succeeded: bool) {
    let mut registration_succeeded = registration_succeeded;
    let mut interval = tokio::time::interval(Duration::from_secs(1));
    interval.set_missed_tick_behavior(MissedTickBehavior::Skip);

    loop {
        interval.tick().await;
        sync_registry_state_once(&state, &mut registration_succeeded).await;
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("runtime-local-inference-provider");

    let config = config::Config::load().await?;
    let state = AppState {
        config: config.clone(),
        started_at: Utc::now(),
        concurrency_budget: budget::ConcurrencyBudget::new(config.max_concurrency),
        registry_sync: RegistrySyncStatus::new(1),
        observability: ProviderObservabilitySink::new(
            config.observability_log_path.clone(),
            config.service_id.clone(),
            config.provider_id.clone(),
        )?,
    };
    let router = rpc::build_router(state.clone());

    tracing::info!(
        socket = %config.paths.socket_path.display(),
        provider_id = %config.provider_id,
        "starting aios runtime-local-inference provider"
    );
    emit_trace(
        &state,
        "provider.runtime.started",
        json!({
            "socket_path": config.paths.socket_path.display().to_string(),
            "descriptor_path": config.descriptor_path.display().to_string(),
            "runtimed_socket": config.runtimed_socket.display().to_string(),
            "embedding_backend": config.embedding_backend.clone(),
            "rerank_backend": config.rerank_backend.clone(),
        }),
        vec!["lifecycle=startup".to_string()],
    );

    let registration_succeeded = self_register_with_registry(&state, 10).await;
    let (initial_status, initial_error) = probe_runtime_health(&state, 10).await;
    report_registry_health(&state, &initial_status, initial_error, "startup", 10).await;
    let registry_sync = tokio::spawn(run_registry_sync_loop(
        state.clone(),
        registration_succeeded,
    ));

    let serve_result = tokio::select! {
        result = aios_rpc::serve_unix(&config.paths.socket_path, router) => Some(result),
        _ = tokio::signal::ctrl_c() => None,
    };
    registry_sync.abort();

    match serve_result {
        Some(result) => {
            let last_error = result
                .as_ref()
                .err()
                .map(|error| error.to_string())
                .unwrap_or_else(|| "provider server stopped".to_string());
            report_registry_health(
                &state,
                "unavailable",
                Some(last_error.clone()),
                "background",
                3,
            )
            .await;
            emit_trace(
                &state,
                "provider.runtime.stopped",
                json!({
                    "reason": last_error,
                }),
                vec!["lifecycle=shutdown".to_string()],
            );
            result?;
        }
        None => {
            tracing::info!("received shutdown signal");
            report_registry_health(
                &state,
                "unavailable",
                Some("shutdown-signal".to_string()),
                "operator",
                3,
            )
            .await;
            emit_trace(
                &state,
                "provider.runtime.stopped",
                json!({
                    "reason": "shutdown-signal",
                }),
                vec!["lifecycle=shutdown".to_string()],
            );
        }
    }

    Ok(())
}
