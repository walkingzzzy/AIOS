use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use aios_contracts::{
    DeviceBackendStatus, DeviceCaptureAdapterPlan, DeviceContinuousCollectorStatus,
    UiTreeSupportMatrixEntry,
};

use crate::{adapters, config::Config, probe};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendSnapshot {
    pub updated_at: String,
    #[serde(default)]
    pub statuses: Vec<DeviceBackendStatus>,
    #[serde(default)]
    pub adapters: Vec<DeviceCaptureAdapterPlan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ui_tree_snapshot: Option<Value>,
    #[serde(default)]
    pub continuous_collectors: Vec<DeviceContinuousCollectorStatus>,
    #[serde(default)]
    pub ui_tree_support_matrix: Vec<UiTreeSupportMatrixEntry>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct UiTreeSupportMatrixArtifact {
    generated_at: String,
    backend_snapshot_path: String,
    entries: Vec<UiTreeSupportMatrixEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct BackendEvidenceArtifact {
    generated_at: String,
    service_id: String,
    modality: String,
    backend: String,
    available: bool,
    readiness: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    source: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    adapter_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    execution_path: Option<String>,
    baseline: String,
    #[serde(default)]
    state_refs: Vec<String>,
    #[serde(default)]
    details: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    probe: Option<BackendEvidenceProbe>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    baseline_payload: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    ui_tree_snapshot: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct BackendEvidenceProbe {
    available: bool,
    readiness: String,
    source: String,
    #[serde(default)]
    details: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    payload: Option<Value>,
}

pub fn collect(config: &Config) -> Vec<DeviceBackendStatus> {
    vec![
        screen_status(config),
        audio_status(config),
        input_status(config),
        camera_status(config),
        ui_tree_status(config),
    ]
}

pub fn snapshot(config: &Config) -> anyhow::Result<BackendSnapshot> {
    let updated_at = Utc::now().to_rfc3339();
    let mut statuses = collect(config);
    let mut adapters = adapters::describe(config);
    let ui_tree_status = statuses.iter().find(|status| status.modality == "ui_tree");
    let ui_tree_adapter = adapters::state_ui_tree_adapter(config);
    let ui_tree_snapshot = match ui_tree_adapter.as_ref() {
        Some(plan) => Some(adapters::state_ui_tree_snapshot_for_adapter(config, plan)?),
        None => None,
    };
    let mut ui_tree_support_matrix = ui_tree_support_matrix(
        config,
        ui_tree_status,
        ui_tree_adapter.as_ref(),
        ui_tree_snapshot.as_ref(),
    );
    let continuous_collectors =
        crate::continuous::read_snapshot(&config.continuous_capture_state_path).unwrap_or_default();
    if let Some(plan) = ui_tree_adapter {
        adapters.push(plan);
    }
    let evidence_artifacts = persist_backend_evidence_artifacts(
        config,
        &updated_at,
        &mut statuses,
        &mut adapters,
        &mut ui_tree_support_matrix,
        ui_tree_snapshot.as_ref(),
    )?;
    let available = statuses.iter().filter(|status| status.available).count();
    let adapter_paths = adapters
        .iter()
        .map(|plan| format!("{}:{}", plan.modality, plan.execution_path))
        .collect::<Vec<_>>()
        .join(",");
    let configured_probes = probe::configured_modalities(config).join(",");
    let live_probes = adapters
        .iter()
        .filter(|plan| plan.execution_path == "native-live")
        .map(|plan| plan.modality.clone())
        .collect::<Vec<_>>()
        .join(",");
    let mut notes = vec![
        format!("available_backends={available}"),
        format!("backend_count={}", statuses.len()),
        format!("adapter_paths={adapter_paths}"),
    ];
    if !configured_probes.is_empty() {
        notes.push(format!("configured_probes={configured_probes}"));
    }
    if !live_probes.is_empty() {
        notes.push(format!("live_probes={live_probes}"));
    }
    notes.push(format!(
        "ui_tree_support_matrix_path={}",
        ui_tree_support_matrix_path(config).display()
    ));
    notes.push(format!(
        "backend_evidence_dir={}",
        config.backend_evidence_dir.display()
    ));
    notes.push(format!(
        "backend_evidence_artifact_count={}",
        evidence_artifacts.len()
    ));
    notes.extend(evidence_artifacts.into_iter().map(|(modality, path)| {
        format!("backend_evidence_artifact[{modality}]={}", path.display())
    }));
    Ok(BackendSnapshot {
        updated_at,
        notes,
        statuses,
        adapters,
        ui_tree_snapshot,
        continuous_collectors,
        ui_tree_support_matrix,
    })
}

pub fn write_snapshot(path: &Path, config: &Config) -> anyhow::Result<BackendSnapshot> {
    let snapshot = snapshot(config)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, serde_json::to_vec_pretty(&snapshot)?)?;
    write_ui_tree_support_matrix(
        &ui_tree_support_matrix_path(config),
        &snapshot.updated_at,
        path,
        &snapshot.ui_tree_support_matrix,
    )?;
    Ok(snapshot)
}

fn ui_tree_support_matrix_path(config: &Config) -> PathBuf {
    config
        .backend_state_path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("ui-tree-support-matrix.json")
}

fn write_ui_tree_support_matrix(
    path: &Path,
    generated_at: &str,
    backend_snapshot_path: &Path,
    entries: &[UiTreeSupportMatrixEntry],
) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let artifact = UiTreeSupportMatrixArtifact {
        generated_at: generated_at.to_string(),
        backend_snapshot_path: backend_snapshot_path.display().to_string(),
        entries: entries.to_vec(),
    };
    fs::write(path, serde_json::to_vec_pretty(&artifact)?)?;
    Ok(())
}

fn persist_backend_evidence_artifacts(
    config: &Config,
    generated_at: &str,
    statuses: &mut [DeviceBackendStatus],
    adapters: &mut [DeviceCaptureAdapterPlan],
    ui_tree_support_matrix: &mut [UiTreeSupportMatrixEntry],
    ui_tree_snapshot: Option<&Value>,
) -> anyhow::Result<Vec<(String, PathBuf)>> {
    fs::create_dir_all(&config.backend_evidence_dir)?;

    let adapter_lookup = adapters
        .iter()
        .map(|adapter| (adapter.modality.clone(), adapter.clone()))
        .collect::<BTreeMap<_, _>>();

    let mut artifact_paths = Vec::new();
    for status in statuses.iter_mut() {
        let adapter = adapter_lookup.get(&status.modality);
        let artifact = build_backend_evidence_artifact(
            config,
            generated_at,
            status,
            adapter,
            ui_tree_snapshot,
        )?;
        let artifact_path = backend_evidence_path(config, &status.modality);
        fs::write(&artifact_path, serde_json::to_vec_pretty(&artifact)?)?;
        status.details.push(format!(
            "evidence_artifact={}",
            artifact_path.display()
        ));
        if let Some(adapter) = adapters.iter_mut().find(|item| item.modality == status.modality) {
            adapter.notes.push(format!(
                "evidence_artifact={}",
                artifact_path.display()
            ));
        }
        artifact_paths.push((status.modality.clone(), artifact_path));
    }

    if let Some((_, path)) = artifact_paths.iter().find(|(modality, _)| modality == "ui_tree") {
        let reference = format!("backend_evidence_artifact={}", path.display());
        for row in ui_tree_support_matrix.iter_mut() {
            if !row.evidence.iter().any(|item| item == &reference) {
                row.evidence.push(reference.clone());
            }
        }
    }

    Ok(artifact_paths)
}

fn build_backend_evidence_artifact(
    config: &Config,
    generated_at: &str,
    status: &DeviceBackendStatus,
    adapter: Option<&DeviceCaptureAdapterPlan>,
    ui_tree_snapshot: Option<&Value>,
) -> anyhow::Result<BackendEvidenceArtifact> {
    let probe = probe_for_modality(config, &status.modality).map(|result| BackendEvidenceProbe {
        available: result.available,
        readiness: result.readiness,
        source: result.source,
        details: result.details,
        payload: result.payload,
    });
    let source = probe
        .as_ref()
        .map(|item| item.source.clone())
        .or_else(|| adapter.map(|item| item.adapter_id.clone()));
    let execution_path = adapter.map(|item| item.execution_path.clone());
    let baseline = match execution_path.as_deref() {
        Some("native-live") => "formal-native-helper-or-probe",
        Some("native-state-bridge") => "state-bridge-baseline",
        Some("native-ready") => "declared-native-ready",
        Some("command-adapter") => "command-adapter",
        Some(other) => other,
        None => status.readiness.as_str(),
    }
    .to_string();

    Ok(BackendEvidenceArtifact {
        generated_at: generated_at.to_string(),
        service_id: config.service_id.clone(),
        modality: status.modality.clone(),
        backend: status.backend.clone(),
        available: status.available,
        readiness: status.readiness.clone(),
        source,
        adapter_id: adapter.map(|item| item.adapter_id.clone()),
        execution_path,
        baseline,
        state_refs: state_refs_for_modality(config, &status.modality),
        details: status.details.clone(),
        probe,
        baseline_payload: baseline_payload_for_modality(config, &status.modality, ui_tree_snapshot)?,
        ui_tree_snapshot: (status.modality == "ui_tree")
            .then(|| ui_tree_snapshot.cloned())
            .flatten(),
    })
}

fn backend_evidence_path(config: &Config, modality: &str) -> PathBuf {
    config
        .backend_evidence_dir
        .join(format!("{modality}-backend-evidence.json"))
}

fn probe_for_modality(config: &Config, modality: &str) -> Option<probe::ProbeResult> {
    match modality {
        "screen" | "audio" | "input" | "camera" => probe::capture_probe(config, modality),
        "ui_tree" => probe::ui_tree_probe(config),
        _ => None,
    }
}

fn state_refs_for_modality(config: &Config, modality: &str) -> Vec<String> {
    let mut refs = Vec::new();
    match modality {
        "screen" => push_existing_ref(&mut refs, &config.screencast_state_path),
        "audio" => {
            push_existing_ref(&mut refs, &config.pipewire_socket_path);
            push_existing_ref(&mut refs, &config.pipewire_node_path);
        }
        "input" => push_existing_ref(&mut refs, &config.input_device_root),
        "camera" => push_existing_ref(&mut refs, &config.camera_device_root),
        "ui_tree" => push_existing_ref(&mut refs, &config.ui_tree_state_path),
        _ => {}
    }
    refs
}

fn push_existing_ref(refs: &mut Vec<String>, path: &Path) {
    if path.exists() {
        refs.push(path.display().to_string());
    }
}

fn baseline_payload_for_modality(
    config: &Config,
    modality: &str,
    ui_tree_snapshot: Option<&Value>,
) -> anyhow::Result<Option<Value>> {
    match modality {
        "screen" => read_json_payload(&config.screencast_state_path),
        "audio" => {
            let mut payload = serde_json::Map::new();
            if config.pipewire_socket_path.exists() {
                payload.insert(
                    "pipewire_socket".to_string(),
                    Value::String(config.pipewire_socket_path.display().to_string()),
                );
            }
            if let Some(node) = read_json_payload(&config.pipewire_node_path)? {
                payload.insert("pipewire_node".to_string(), node);
            }
            Ok((!payload.is_empty()).then_some(Value::Object(payload)))
        }
        "input" => {
            let devices = list_matching_entries(&config.input_device_root, &["event", "mouse", "kbd"])?;
            Ok((!devices.is_empty()).then_some(serde_json::json!({
                "input_root": config.input_device_root.display().to_string(),
                "input_devices": devices,
            })))
        }
        "camera" => {
            let devices = list_matching_entries(&config.camera_device_root, &["video"])?;
            Ok((!devices.is_empty()).then_some(serde_json::json!({
                "camera_root": config.camera_device_root.display().to_string(),
                "camera_devices": devices,
            })))
        }
        "ui_tree" => {
            if let Some(snapshot) = ui_tree_snapshot {
                return Ok(Some(snapshot.clone()));
            }
            read_json_payload(&config.ui_tree_state_path)
        }
        _ => Ok(None),
    }
}

fn read_json_payload(path: &Path) -> anyhow::Result<Option<Value>> {
    if !path.exists() {
        return Ok(None);
    }
    let content =
        fs::read_to_string(path).map_err(|error| anyhow::anyhow!("read {}: {error}", path.display()))?;
    let value = serde_json::from_str::<Value>(&content)
        .map_err(|error| anyhow::anyhow!("parse {}: {error}", path.display()))?;
    Ok(Some(value))
}

fn list_matching_entries(path: &Path, prefixes: &[&str]) -> anyhow::Result<Vec<String>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let mut entries = fs::read_dir(path)?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.file_name().to_string_lossy().to_string())
        .filter(|name| prefixes.iter().any(|prefix| name.starts_with(prefix)))
        .collect::<Vec<_>>();
    entries.sort();
    Ok(entries)
}

fn configured_command_status(
    modality: &str,
    backend: &str,
    configured_note: &str,
    capture_command: Option<&str>,
    explicit_probe_command: Option<&str>,
    probe_result: Option<&probe::ProbeResult>,
) -> Option<DeviceBackendStatus> {
    capture_command?;
    if explicit_probe_command.is_none() {
        return Some(status(
            modality,
            backend,
            true,
            "command-adapter",
            vec![configured_note.to_string()],
        ));
    }

    let result = probe_result?;
    if !result.available {
        return None;
    }

    let mut details = vec![
        configured_note.to_string(),
        format!("probe_source={}", result.source),
        format!("probe_readiness={}", result.readiness),
    ];
    details.extend(result.details.clone());
    Some(status(modality, backend, true, "command-adapter", details))
}

fn command_probe_gate_active(
    capture_command: Option<&str>,
    explicit_probe_command: Option<&str>,
    probe_result: Option<&probe::ProbeResult>,
) -> bool {
    capture_command.is_some()
        && explicit_probe_command.is_some()
        && probe_result.is_some_and(|result| !result.available)
}

fn command_probe_gate_detail(configured_note: &str) -> String {
    format!("{configured_note}; explicit probe unavailable, fallback path active")
}

fn screen_status(config: &Config) -> DeviceBackendStatus {
    if !config.screen_enabled {
        return disabled_status("screen", &config.screen_backend);
    }

    let probe_result = probe::capture_probe(config, "screen");
    let builtin_result = probe::builtin_capture_probe(config, "screen");
    if let Some(current) = configured_command_status(
        "screen",
        &config.screen_backend,
        "screen_capture_command configured",
        config.screen_capture_command.as_deref(),
        config.screen_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return current;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return probe_status("screen", &config.screen_backend, result);
    }
    let mut current = builtin_result
        .as_ref()
        .map(|result| probe_status("screen", &config.screen_backend, result))
        .unwrap_or_else(|| {
            status(
                "screen",
                &config.screen_backend,
                false,
                "fallback-stub",
                vec!["falling back to builtin preview objects".to_string()],
            )
        });
    if command_probe_gate_active(
        config.screen_capture_command.as_deref(),
        config.screen_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        current.details.push(command_probe_gate_detail(
            "screen_capture_command configured",
        ));
    }
    if let Some(result) = probe_result.as_ref() {
        apply_probe_failure(&mut current, builtin_result.as_ref(), result);
    }
    current
}

fn audio_status(config: &Config) -> DeviceBackendStatus {
    if !config.audio_enabled {
        return disabled_status("audio", &config.audio_backend);
    }

    let probe_result = probe::capture_probe(config, "audio");
    let builtin_result = probe::builtin_capture_probe(config, "audio");
    if let Some(current) = configured_command_status(
        "audio",
        &config.audio_backend,
        "audio_capture_command configured",
        config.audio_capture_command.as_deref(),
        config.audio_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return current;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return probe_status("audio", &config.audio_backend, result);
    }
    let mut current = builtin_result
        .as_ref()
        .map(|result| probe_status("audio", &config.audio_backend, result))
        .unwrap_or_else(|| {
            status(
                "audio",
                &config.audio_backend,
                false,
                "fallback-stub",
                vec!["pipewire unavailable; using builtin preview".to_string()],
            )
        });
    if command_probe_gate_active(
        config.audio_capture_command.as_deref(),
        config.audio_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        current.details.push(command_probe_gate_detail(
            "audio_capture_command configured",
        ));
    }
    if let Some(result) = probe_result.as_ref() {
        apply_probe_failure(&mut current, builtin_result.as_ref(), result);
    }
    current
}

fn input_status(config: &Config) -> DeviceBackendStatus {
    if !config.input_enabled {
        return disabled_status("input", &config.input_backend);
    }

    let probe_result = probe::capture_probe(config, "input");
    let builtin_result = probe::builtin_capture_probe(config, "input");
    if let Some(current) = configured_command_status(
        "input",
        &config.input_backend,
        "input_capture_command configured",
        config.input_capture_command.as_deref(),
        config.input_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return current;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return probe_status("input", &config.input_backend, result);
    }
    let mut current = builtin_result
        .as_ref()
        .map(|result| probe_status("input", &config.input_backend, result))
        .unwrap_or_else(|| {
            status(
                "input",
                &config.input_backend,
                false,
                "fallback-stub",
                vec!["input unavailable; using builtin preview".to_string()],
            )
        });
    if command_probe_gate_active(
        config.input_capture_command.as_deref(),
        config.input_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        current.details.push(command_probe_gate_detail(
            "input_capture_command configured",
        ));
    }
    if let Some(result) = probe_result.as_ref() {
        apply_probe_failure(&mut current, builtin_result.as_ref(), result);
    }
    current
}

fn camera_status(config: &Config) -> DeviceBackendStatus {
    if !config.camera_enabled {
        return disabled_status("camera", &config.camera_backend);
    }

    let probe_result = probe::capture_probe(config, "camera");
    let builtin_result = probe::builtin_capture_probe(config, "camera");
    if let Some(current) = configured_command_status(
        "camera",
        &config.camera_backend,
        "camera_capture_command configured",
        config.camera_capture_command.as_deref(),
        config.camera_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return current;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return probe_status("camera", &config.camera_backend, result);
    }
    let mut current = builtin_result
        .as_ref()
        .map(|result| probe_status("camera", &config.camera_backend, result))
        .unwrap_or_else(|| {
            status(
                "camera",
                &config.camera_backend,
                false,
                "fallback-stub",
                vec!["camera unavailable; using builtin preview".to_string()],
            )
        });
    if command_probe_gate_active(
        config.camera_capture_command.as_deref(),
        config.camera_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        current.details.push(command_probe_gate_detail(
            "camera_capture_command configured",
        ));
    }
    if let Some(result) = probe_result.as_ref() {
        apply_probe_failure(&mut current, builtin_result.as_ref(), result);
    }
    current
}

fn ui_tree_status(config: &Config) -> DeviceBackendStatus {
    if !config.ui_tree_supported {
        return status(
            "ui_tree",
            "at-spi",
            false,
            "unsupported",
            vec!["ui_tree capability disabled".to_string()],
        );
    }

    let probe_result = probe::ui_tree_probe(config);
    let builtin_result = Some(probe::builtin_ui_tree_probe(config));
    if let Some(current) = configured_command_status(
        "ui_tree",
        "at-spi",
        "ui_tree_command configured",
        config.ui_tree_command.as_deref(),
        config.ui_tree_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return current;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return probe_status("ui_tree", "at-spi", result);
    }
    let mut current = builtin_result
        .as_ref()
        .map(|result| probe_status("ui_tree", "at-spi", result))
        .unwrap_or_else(|| {
            status(
                "ui_tree",
                "at-spi",
                false,
                "unsupported",
                vec!["ui_tree capability disabled".to_string()],
            )
        });
    if command_probe_gate_active(
        config.ui_tree_command.as_deref(),
        config.ui_tree_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        current
            .details
            .push(command_probe_gate_detail("ui_tree_command configured"));
    }
    if let Some(result) = probe_result.as_ref() {
        apply_probe_failure(&mut current, builtin_result.as_ref(), result);
    }
    current
}

fn disabled_status(modality: &str, backend: &str) -> DeviceBackendStatus {
    status(
        modality,
        backend,
        false,
        "disabled",
        vec![format!("{modality}_enabled=false")],
    )
}

fn probe_status(modality: &str, backend: &str, result: &probe::ProbeResult) -> DeviceBackendStatus {
    let mut details = vec![format!("probe_source={}", result.source)];
    details.extend(result.details.clone());
    status(
        modality,
        backend,
        result.available,
        &result.readiness,
        details,
    )
}

fn apply_probe_failure(
    status: &mut DeviceBackendStatus,
    builtin_result: Option<&probe::ProbeResult>,
    result: &probe::ProbeResult,
) {
    if result.available {
        return;
    }
    if builtin_result.is_some_and(|builtin| same_probe_result(builtin, result)) {
        return;
    }
    status
        .details
        .push(format!("probe_source={}", result.source));
    status
        .details
        .push(format!("probe_readiness={}", result.readiness));
    status.details.extend(result.details.clone());
}

fn status(
    modality: &str,
    backend: &str,
    available: bool,
    readiness: &str,
    details: Vec<String>,
) -> DeviceBackendStatus {
    DeviceBackendStatus {
        modality: modality.to_string(),
        backend: backend.to_string(),
        available,
        readiness: readiness.to_string(),
        details,
    }
}

fn same_probe_result(left: &probe::ProbeResult, right: &probe::ProbeResult) -> bool {
    left.available == right.available
        && left.readiness == right.readiness
        && left.source == right.source
        && left.details == right.details
}

fn ui_tree_support_matrix(
    config: &Config,
    current_status: Option<&DeviceBackendStatus>,
    current_adapter: Option<&DeviceCaptureAdapterPlan>,
    ui_tree_snapshot: Option<&Value>,
) -> Vec<UiTreeSupportMatrixEntry> {
    let desktop_environment = std::env::var("XDG_CURRENT_DESKTOP")
        .ok()
        .or_else(|| std::env::var("DESKTOP_SESSION").ok())
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "unknown".to_string());
    let session_type = std::env::var("XDG_SESSION_TYPE")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| {
            if std::env::var_os("WAYLAND_DISPLAY").is_some() {
                "wayland".to_string()
            } else if std::env::var_os("DISPLAY").is_some() {
                "x11".to_string()
            } else {
                "headless".to_string()
            }
        });
    let current_readiness = current_status
        .map(|status| status.readiness.clone())
        .unwrap_or_else(|| "unsupported".to_string());
    let current_available = current_status.is_some_and(|status| status.available)
        || matches!(
            current_readiness.as_str(),
            "native-live" | "native-ready" | "native-state-bridge" | "command-adapter"
        );

    let probe_result = probe::ui_tree_probe(config);
    let atspi_available = probe_result.as_ref().is_some_and(|result| result.available)
        || std::env::var_os("AT_SPI_BUS_ADDRESS").is_some();
    let atspi_readiness = if probe_result.as_ref().is_some_and(|result| result.available) {
        "native-live"
    } else if std::env::var_os("AT_SPI_BUS_ADDRESS").is_some() {
        "native-ready"
    } else {
        "missing-atspi-bus"
    };
    let state_bridge_available = current_adapter
        .is_some_and(|plan| plan.execution_path == "native-state-bridge")
        || ui_tree_snapshot
            .and_then(Value::as_object)
            .and_then(|object| object.get("capture_mode"))
            .and_then(Value::as_str)
            .is_some_and(|mode| mode == "native-state-bridge");

    let mut current_details = vec![
        format!("desktop_environment={desktop_environment}"),
        format!("session_type={session_type}"),
        format!(
            "dbus_session_bus={}",
            std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some()
        ),
        format!(
            "at_spi_bus={}",
            std::env::var_os("AT_SPI_BUS_ADDRESS").is_some()
        ),
    ];
    if let Some(status) = current_status {
        current_details.extend(status.details.clone());
    }
    if let Some(plan) = current_adapter {
        current_details.push(format!("adapter_id={}", plan.adapter_id));
        current_details.push(format!("adapter_execution_path={}", plan.execution_path));
    }

    let mut atspi_details = vec![
        format!(
            "ui_tree_live_command_configured={}",
            config.ui_tree_live_command.is_some()
        ),
        format!(
            "at_spi_bus={}",
            std::env::var_os("AT_SPI_BUS_ADDRESS").is_some()
        ),
    ];
    if let Some(result) = probe_result {
        atspi_details.push(format!("probe_source={}", result.source));
        atspi_details.push(format!("probe_readiness={}", result.readiness));
        atspi_details.extend(result.details);
    }
    let support_matrix_path = ui_tree_support_matrix_path(config).display().to_string();
    let current_execution_path = current_adapter.map(|plan| plan.execution_path.as_str());

    vec![
        UiTreeSupportMatrixEntry {
            environment_id: "current-session".to_string(),
            available: current_available,
            readiness: current_readiness,
            current: true,
            desktop_environment: Some(desktop_environment.clone()),
            session_type: Some(session_type.clone()),
            adapter_id: current_adapter.map(|plan| plan.adapter_id.clone()),
            execution_path: current_adapter.map(|plan| plan.execution_path.clone()),
            stability: Some(
                match current_execution_path {
                    Some("native-live") => "best-effort-live",
                    Some("native-state-bridge") => "state-bridge",
                    Some("native-ready") | Some("command-adapter") => "declared-ready",
                    _ if current_available => "environment-dependent",
                    _ => "declared-limited",
                }
                .to_string(),
            ),
            limitations: if current_available {
                Vec::new()
            } else {
                vec![
                    "current session still lacks a fully-qualified live ui_tree collector"
                        .to_string(),
                ]
            },
            evidence: vec![
                format!("backend_state_path={}", config.backend_state_path.display()),
                format!("support_matrix_path={support_matrix_path}"),
            ],
            details: current_details,
        },
        UiTreeSupportMatrixEntry {
            environment_id: "atspi-live".to_string(),
            available: atspi_available,
            readiness: atspi_readiness.to_string(),
            current: false,
            desktop_environment: Some(desktop_environment.clone()),
            session_type: Some(session_type.clone()),
            adapter_id: Some("ui_tree.atspi-native".to_string()),
            execution_path: Some(if atspi_available {
                "native-live".to_string()
            } else if std::env::var_os("AT_SPI_BUS_ADDRESS").is_some() {
                "native-ready".to_string()
            } else {
                "native-live".to_string()
            }),
            stability: Some("best-effort-live".to_string()),
            limitations: vec![
                "requires AT-SPI availability".to_string(),
                "long-run collector stability evidence is still accumulating".to_string(),
            ],
            evidence: vec![
                format!(
                    "ui_tree_live_command_configured={}",
                    config.ui_tree_live_command.is_some()
                ),
                format!("support_matrix_path={support_matrix_path}"),
            ],
            details: atspi_details,
        },
        UiTreeSupportMatrixEntry {
            environment_id: "state-bridge".to_string(),
            available: state_bridge_available,
            readiness: if state_bridge_available {
                "native-state-bridge".to_string()
            } else {
                "missing-state-file".to_string()
            },
            current: false,
            desktop_environment: Some(desktop_environment.clone()),
            session_type: Some(session_type.clone()),
            adapter_id: Some("ui_tree.state-bridge".to_string()),
            execution_path: Some("native-state-bridge".to_string()),
            stability: Some("state-bridge".to_string()),
            limitations: if state_bridge_available {
                vec!["snapshot can lag live focus state".to_string()]
            } else {
                vec!["state bridge requires a ui_tree state file producer".to_string()]
            },
            evidence: vec![
                format!("ui_tree_state_path={}", config.ui_tree_state_path.display()),
                format!("support_matrix_path={support_matrix_path}"),
            ],
            details: vec![format!(
                "ui_tree_state_path={}",
                config.ui_tree_state_path.display()
            )],
        },
        UiTreeSupportMatrixEntry {
            environment_id: "screen-ocr-fallback".to_string(),
            available: true,
            readiness: "screen-frame+ocr".to_string(),
            current: false,
            desktop_environment: Some(desktop_environment),
            session_type: Some(session_type),
            adapter_id: Some("screen.ocr-fallback".to_string()),
            execution_path: Some("screen-frame+ocr".to_string()),
            stability: Some("fallback-only".to_string()),
            limitations: vec![
                "OCR fallback does not provide a structured accessibility tree".to_string(),
                "accuracy depends on frame quality".to_string(),
            ],
            evidence: vec![
                "fallback_path=screen_frame+ocr".to_string(),
                format!("support_matrix_path={support_matrix_path}"),
            ],
            details: vec!["fallback_path=screen_frame+ocr".to_string()],
        },
    ]
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    fn config() -> Config {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        let unique = TEST_COUNTER.fetch_add(1, Ordering::Relaxed);
        let state_root =
            std::env::temp_dir().join(format!("aios-deviced-backend-test-{stamp}-{unique}"));
        Config {
            service_id: "aios-deviced".to_string(),
            version: "0.1.0".to_string(),
            paths: aios_core::ServicePaths::from_service_name("deviced-test"),
            capture_state_path: state_root.join("captures.json"),
            observability_log_path: state_root.join("observability.jsonl"),
            indicator_state_path: state_root.join("indicator-state.json"),
            backend_state_path: state_root.join("backend-state.json"),
            backend_evidence_dir: state_root.join("backend-evidence"),
            continuous_capture_state_path: state_root.join("continuous-captures.json"),
            policy_socket_path: state_root.join("policyd.sock"),
            approval_rpc_timeout_ms: 500,
            screen_backend: "screen-capture-portal".to_string(),
            audio_backend: "pipewire".to_string(),
            input_backend: "libinput".to_string(),
            camera_backend: "pipewire-camera".to_string(),
            screen_enabled: true,
            audio_enabled: true,
            input_enabled: true,
            camera_enabled: true,
            ui_tree_supported: true,
            pipewire_socket_path: state_root.join("pipewire-0"),
            input_device_root: state_root.join("input"),
            camera_device_root: state_root.join("camera"),
            screencast_state_path: state_root.join("screencast-state.json"),
            pipewire_node_path: state_root.join("pipewire-node.json"),
            ui_tree_state_path: state_root.join("ui-tree-state.json"),
            default_resolution: "1920x1080".to_string(),
            approval_mode: "metadata-only".to_string(),
            approved_sessions: Vec::new(),
            approved_tasks: Vec::new(),
            screen_capture_command: None,
            audio_capture_command: None,
            input_capture_command: None,
            camera_capture_command: None,
            ui_tree_command: None,
            screen_probe_command: None,
            audio_probe_command: None,
            input_probe_command: None,
            camera_probe_command: None,
            ui_tree_probe_command: None,
            screen_live_command: None,
            audio_live_command: None,
            input_live_command: None,
            camera_live_command: None,
            ui_tree_live_command: None,
            continuous_capture_interval_ms: 500,
        }
    }

    fn cleanup(config: &Config) {
        if let Some(parent) = config.capture_state_path.parent() {
            fs::remove_dir_all(parent).ok();
        }
    }

    #[test]
    fn state_backed_backends_report_native_live_readiness() {
        let mut config = config();
        let state_dir = config
            .screencast_state_path
            .parent()
            .expect("state dir")
            .to_path_buf();
        fs::create_dir_all(&state_dir).expect("create state dir");
        fs::write(&config.screencast_state_path, b"{}").expect("write screencast state");
        fs::write(&config.pipewire_socket_path, b"ready\n").expect("write pipewire socket");
        fs::write(&config.pipewire_node_path, b"{}").expect("write pipewire node");
        fs::create_dir_all(&config.input_device_root).expect("create input root");
        fs::write(config.input_device_root.join("event0"), b"keyboard\n")
            .expect("write input device");
        fs::create_dir_all(&config.camera_device_root).expect("create camera root");
        fs::write(config.camera_device_root.join("video0"), b"ready\n")
            .expect("write camera device");
        fs::write(&config.ui_tree_state_path, b"{}").expect("write ui tree state");

        let failing_probe = Some("printf 'probe failed\\n' >&2; exit 7".to_string());
        config.screen_probe_command = failing_probe.clone();
        config.audio_probe_command = failing_probe.clone();
        config.input_probe_command = failing_probe.clone();
        config.camera_probe_command = failing_probe.clone();
        config.ui_tree_probe_command = failing_probe;

        let statuses = collect(&config);
        for modality in ["screen", "audio", "input", "camera", "ui_tree"] {
            let status = statuses
                .iter()
                .find(|item| item.modality == modality)
                .unwrap_or_else(|| panic!("missing status for {modality}"));
            assert!(status.available, "{modality} should remain available");
            assert_eq!(status.readiness, "native-live");
            assert!(
                status
                    .details
                    .iter()
                    .any(|item| item == "probe_readiness=probe-failed"),
                "{modality} should preserve probe failure details"
            );
        }

        cleanup(&config);
    }

    #[test]
    fn snapshot_includes_ui_tree_state_bridge_payload() {
        let config = config();
        let state_dir = config
            .screencast_state_path
            .parent()
            .expect("state dir")
            .to_path_buf();
        fs::create_dir_all(&state_dir).expect("create state dir");
        fs::write(
            &config.ui_tree_state_path,
            br#"{"snapshot_id":"tree-native-1","focus_node":"button-1"}"#,
        )
        .expect("write ui tree state");

        let snapshot = snapshot(&config).expect("snapshot");
        let ui_tree_adapter = snapshot
            .adapters
            .iter()
            .find(|item| item.modality == "ui_tree")
            .expect("ui_tree adapter");
        assert_eq!(ui_tree_adapter.adapter_id, "ui_tree.atspi-state-file");
        assert_eq!(ui_tree_adapter.execution_path, "native-state-bridge");
        assert!(
            snapshot
                .notes
                .iter()
                .any(|item| item.contains("ui_tree:native-state-bridge")),
            "adapter paths should include ui_tree state bridge"
        );

        let ui_tree_snapshot = snapshot.ui_tree_snapshot.expect("ui_tree snapshot");
        assert_eq!(
            ui_tree_snapshot
                .get("snapshot_id")
                .and_then(serde_json::Value::as_str),
            Some("tree-native-1")
        );
        assert_eq!(
            ui_tree_snapshot
                .get("capture_mode")
                .and_then(serde_json::Value::as_str),
            Some("native-state-bridge")
        );
        assert_eq!(
            ui_tree_snapshot
                .get("adapter_id")
                .and_then(serde_json::Value::as_str),
            Some("ui_tree.atspi-state-file")
        );
        assert!(
            snapshot
                .ui_tree_support_matrix
                .iter()
                .any(|item| item.environment_id == "state-bridge" && item.available),
            "ui_tree support matrix should report state-bridge availability"
        );
        assert!(
            snapshot
                .ui_tree_support_matrix
                .iter()
                .any(|item| item.environment_id == "screen-ocr-fallback" && item.available),
            "ui_tree support matrix should retain OCR fallback"
        );

        cleanup(&config);
    }

    #[test]
    fn snapshot_persists_backend_evidence_artifacts() {
        let mut config = config();
        let state_dir = config
            .screencast_state_path
            .parent()
            .expect("state dir")
            .to_path_buf();
        fs::create_dir_all(&state_dir).expect("create state dir");
        fs::write(
            &config.screencast_state_path,
            br#"{"portal_session_ref":"portal-session-1","stream_node_id":42}"#,
        )
        .expect("write screencast state");
        fs::write(&config.pipewire_socket_path, b"ready\n").expect("write pipewire socket");
        fs::write(&config.pipewire_node_path, br#"{"node_id":77}"#)
            .expect("write pipewire node");
        fs::create_dir_all(&config.input_device_root).expect("create input root");
        fs::write(config.input_device_root.join("event0"), b"keyboard\n")
            .expect("write input device");
        fs::create_dir_all(&config.camera_device_root).expect("create camera root");
        fs::write(config.camera_device_root.join("video0"), b"ready\n")
            .expect("write camera device");
        fs::write(
            &config.ui_tree_state_path,
            br#"{"snapshot_id":"tree-native-1","focus_node":"button-1"}"#,
        )
        .expect("write ui tree state");

        config.screen_live_command = Some(
            "printf '{\"available\":true,\"readiness\":\"native-live\",\"payload\":{\"release_grade_backend\":\"portal-live-helper\"},\"source\":\"deviced-runtime-helper\"}'\n"
                .to_string(),
        );
        config.audio_live_command = Some(
            "printf '{\"available\":true,\"readiness\":\"native-live\",\"payload\":{\"release_grade_backend\":\"pipewire-live-helper\"},\"source\":\"deviced-runtime-helper\"}'\n"
                .to_string(),
        );
        config.input_live_command = Some(
            "printf '{\"available\":true,\"readiness\":\"native-live\",\"payload\":{\"release_grade_backend\":\"libinput-live-helper\"},\"source\":\"deviced-runtime-helper\"}'\n"
                .to_string(),
        );
        config.camera_live_command = Some(
            "printf '{\"available\":true,\"readiness\":\"native-live\",\"payload\":{\"release_grade_backend\":\"camera-live-helper\"},\"source\":\"deviced-runtime-helper\"}'\n"
                .to_string(),
        );

        let snapshot = snapshot(&config).expect("snapshot");
        let screen_status = snapshot
            .statuses
            .iter()
            .find(|item| item.modality == "screen")
            .expect("screen status");
        let screen_artifact_path = config
            .backend_evidence_dir
            .join("screen-backend-evidence.json");
        assert!(
            screen_artifact_path.exists(),
            "screen backend evidence artifact should be written"
        );
        assert!(
            screen_status
                .details
                .iter()
                .any(|item| item == &format!("evidence_artifact={}", screen_artifact_path.display())),
            "screen status should expose backend evidence artifact path"
        );
        let screen_artifact: Value = serde_json::from_slice(
            &fs::read(&screen_artifact_path).expect("read screen evidence artifact"),
        )
        .expect("parse screen evidence artifact");
        assert_eq!(
            screen_artifact.get("baseline").and_then(Value::as_str),
            Some("formal-native-helper-or-probe")
        );
        assert_eq!(
            screen_artifact
                .get("probe")
                .and_then(Value::as_object)
                .and_then(|probe| probe.get("payload"))
                .and_then(Value::as_object)
                .and_then(|payload| payload.get("release_grade_backend"))
                .and_then(Value::as_str),
            Some("portal-live-helper")
        );
        assert_eq!(
            screen_artifact
                .get("baseline_payload")
                .and_then(Value::as_object)
                .and_then(|payload| payload.get("stream_node_id"))
                .and_then(Value::as_u64),
            Some(42)
        );
        assert!(
            snapshot
                .notes
                .iter()
                .any(|item| item == &format!("backend_evidence_dir={}", config.backend_evidence_dir.display())),
            "snapshot notes should expose backend evidence dir"
        );

        cleanup(&config);
    }

    #[test]
    fn explicit_probe_failure_blocks_command_adapter_status_shortcut() {
        let mut config = config();
        let state_dir = config
            .screencast_state_path
            .parent()
            .expect("state dir")
            .to_path_buf();
        fs::create_dir_all(&state_dir).expect("create state dir");
        fs::write(&config.screencast_state_path, b"{}").expect("write screencast state");
        fs::write(&config.pipewire_socket_path, b"ready\n").expect("write pipewire socket");
        fs::write(&config.pipewire_node_path, b"{}").expect("write pipewire node");
        fs::create_dir_all(&config.input_device_root).expect("create input root");
        fs::write(config.input_device_root.join("event0"), b"keyboard\n")
            .expect("write input device");
        fs::create_dir_all(&config.camera_device_root).expect("create camera root");
        fs::write(config.camera_device_root.join("video0"), b"ready\n")
            .expect("write camera device");
        fs::write(&config.ui_tree_state_path, b"{}").expect("write ui tree state");

        let configured_command = Some("printf '{\"ok\":true}'\n".to_string());
        config.screen_capture_command = configured_command.clone();
        config.audio_capture_command = configured_command.clone();
        config.input_capture_command = configured_command.clone();
        config.camera_capture_command = configured_command.clone();
        config.ui_tree_command = configured_command;

        let failing_probe = Some("printf 'probe failed\\n' >&2; exit 7".to_string());
        config.screen_probe_command = failing_probe.clone();
        config.audio_probe_command = failing_probe.clone();
        config.input_probe_command = failing_probe.clone();
        config.camera_probe_command = failing_probe.clone();
        config.ui_tree_probe_command = failing_probe;

        let statuses = collect(&config);
        for modality in ["screen", "audio", "input", "camera", "ui_tree"] {
            let status = statuses
                .iter()
                .find(|item| item.modality == modality)
                .unwrap_or_else(|| panic!("missing status for {modality}"));
            assert_ne!(
                status.readiness, "command-adapter",
                "{modality} should not short-circuit to command-adapter"
            );
            assert!(
                status
                    .details
                    .iter()
                    .any(|item| item.contains("explicit probe unavailable")),
                "{modality} should record why the command adapter was gated"
            );
            assert!(
                status
                    .details
                    .iter()
                    .any(|item| item == "probe_readiness=probe-failed"),
                "{modality} should keep probe failure detail"
            );
        }

        cleanup(&config);
    }
}
