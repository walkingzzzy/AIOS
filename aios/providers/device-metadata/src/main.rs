mod clients;
mod config;
mod ops;
mod rpc;

use std::time::Duration;

use chrono::{DateTime, Utc};
use serde_json::json;
use tokio::time::MissedTickBehavior;

use aios_contracts::{DeviceMetadataGetRequest, HealthResponse};
use aios_core::{ProviderObservabilitySink, RegistrySyncStatus};

#[derive(Clone)]
pub struct AppState {
    pub config: config::Config,
    pub started_at: DateTime<Utc>,
    pub registry_sync: RegistrySyncStatus,
    pub observability: ProviderObservabilitySink,
}

impl AppState {
    fn health(&self) -> HealthResponse {
        let metadata = crate::ops::get_device_metadata(self, &DeviceMetadataGetRequest::default());
        let dependency_unavailable = metadata
            .notes
            .iter()
            .any(|note| note == "device_state_source=unavailable");

        let mut notes = vec![
            format!("provider_id={}", self.config.provider_id),
            format!("deviced_socket={}", self.config.deviced_socket.display()),
            format!("agentd_socket={}", self.config.agentd_socket.display()),
            format!("descriptor_path={}", self.config.descriptor_path.display()),
            format!(
                "observability_log_path={}",
                self.config.observability_log_path.display()
            ),
            format!(
                "hardware_profile_path={}",
                self.config
                    .hardware_profile_path
                    .as_ref()
                    .map(|path| path.display().to_string())
                    .unwrap_or_else(|| "<none>".to_string())
            ),
            format!("device_overall_status={}", metadata.summary.overall_status),
            format!(
                "device_backend_overall_status={}",
                metadata.backend_summary.overall_status
            ),
            format!(
                "device_backend_available_status_count={}",
                metadata.backend_summary.available_status_count
            ),
            format!(
                "device_backend_attention_count={}",
                metadata.backend_summary.attention_count
            ),
            format!(
                "device_available_modalities={}",
                format_modalities_note(&metadata.summary.available_modalities)
            ),
            format!(
                "device_unavailable_modalities={}",
                format_modalities_note(&metadata.summary.unavailable_modalities)
            ),
            format!(
                "device_continuous_collector_count={}",
                metadata.summary.continuous_collector_count
            ),
            format!("ui_tree_available={}", metadata.summary.ui_tree_available),
            format!(
                "ui_tree_support_entries={}",
                metadata.ui_tree_support_matrix.len()
            ),
        ];
        if let Some(capture_mode) = &metadata.backend_summary.ui_tree_capture_mode {
            notes.push(format!(
                "device_backend_ui_tree_capture_mode={capture_mode}"
            ));
        }
        for (metadata_key, health_key) in [
            (
                "release_grade_backend_ids",
                "device_release_grade_backend_ids",
            ),
            (
                "release_grade_backend_origins",
                "device_release_grade_backend_origins",
            ),
            (
                "release_grade_backend_stacks",
                "device_release_grade_backend_stacks",
            ),
            (
                "release_grade_contract_kinds",
                "device_release_grade_contract_kinds",
            ),
            ("hardware_profile_id", "device_hardware_profile_id"),
            (
                "hardware_profile_validation_status",
                "device_hardware_profile_validation_status",
            ),
            (
                "hardware_profile_required_modalities",
                "device_hardware_profile_required_modalities",
            ),
            (
                "hardware_profile_missing_required_modalities",
                "device_hardware_profile_missing_required_modalities",
            ),
            (
                "hardware_profile_missing_conditional_modalities",
                "device_hardware_profile_missing_conditional_modalities",
            ),
        ] {
            if let Some(value) = metadata
                .notes
                .iter()
                .find_map(|note| note.strip_prefix(&format!("{metadata_key}=")))
            {
                notes.push(format!("{health_key}={value}"));
            }
        }
        notes.extend(self.registry_sync.health_notes());

        if dependency_unavailable {
            notes.push("deviced_status=unavailable".to_string());
            if let Some(error) = metadata
                .notes
                .iter()
                .find_map(|note| note.strip_prefix("device_state_error="))
            {
                notes.push(format!("deviced_probe_error={error}"));
            }
        } else {
            notes.push("deviced_status=available".to_string());
        }

        HealthResponse {
            service_id: self.config.service_id.clone(),
            status: if dependency_unavailable {
                "degraded".to_string()
            } else {
                "ready".to_string()
            },
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
        match crate::clients::register_provider(state).await {
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
                        descriptor_path = %state.config.descriptor_path.display(),
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
        match crate::clients::report_provider_health(state, status, last_error.clone()).await {
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
                        agentd_socket = %state.config.agentd_socket.display(),
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

async fn probe_deviced_health(state: &AppState, attempts: usize) -> (String, Option<String>) {
    for attempt in 0..attempts {
        match crate::clients::fetch_device_state_async(state).await {
            Ok(_) => return ("available".to_string(), None),
            Err(error) if attempt + 1 < attempts => {
                tokio::time::sleep(Duration::from_millis(100)).await;
                if !state.config.deviced_socket.exists() {
                    continue;
                }
                tracing::debug!(?error, "deviced probe failed during startup, retrying");
            }
            Err(error) => return ("unavailable".to_string(), Some(error.to_string())),
        }
    }

    (
        "unavailable".to_string(),
        Some("deviced probe exhausted".to_string()),
    )
}

async fn sync_registry_state_once(state: &AppState, registration_succeeded: &mut bool) {
    let Some(parent) = state.config.agentd_socket.parent() else {
        return;
    };
    if !parent.exists() {
        return;
    }

    if !*registration_succeeded && state.config.descriptor_path.exists() {
        match crate::clients::register_provider(state).await {
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

    let (status, last_error) = probe_deviced_health(state, 1).await;
    match crate::clients::report_provider_health(state, &status, last_error.clone()).await {
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

fn format_modalities_note(modalities: &[String]) -> String {
    if modalities.is_empty() {
        "<none>".to_string()
    } else {
        modalities.join(",")
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    aios_core::logging::init("device-metadata-provider");

    let config = config::Config::load().await?;
    let state = AppState {
        config: config.clone(),
        started_at: Utc::now(),
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
        "starting aios device-metadata provider"
    );
    emit_trace(
        &state,
        "provider.runtime.started",
        json!({
            "socket_path": config.paths.socket_path.display().to_string(),
            "descriptor_path": config.descriptor_path.display().to_string(),
            "deviced_socket": config.deviced_socket.display().to_string(),
        }),
        vec!["lifecycle=startup".to_string()],
    );

    let registration_succeeded = self_register_with_registry(&state, 10).await;
    let (initial_status, initial_error) = probe_deviced_health(&state, 10).await;
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
