use std::{fs, process::Command};

use anyhow::Context;
use serde_json::{json, Map, Value};

use aios_contracts::{
    DeviceCapabilityDescriptor, DeviceCaptureAdapterPlan as CaptureAdapterPlan,
    DeviceCaptureRequest,
};

use crate::{capture, config::Config, probe, release_grade};

#[derive(Debug, Clone)]
pub struct CapturePreview {
    pub source_backend: String,
    pub preview_object_kind: Option<String>,
    pub preview_object: Option<Value>,
    pub contains_sensitive_data: bool,
    pub notes: Vec<String>,
}

pub fn capture_preview(
    config: &Config,
    request: &DeviceCaptureRequest,
) -> anyhow::Result<CapturePreview> {
    let plan = resolve_capture_plan(config, request)?;
    let mut notes = plan.notes.clone();
    let mut preview_object = Some(execute_capture_plan(config, request, &plan)?);

    if request.modality == "screen" {
        if let Some(ui_tree_plan) = resolve_ui_tree_plan(config) {
            let ui_tree = execute_ui_tree_plan(config, &ui_tree_plan)?;
            if let Some(preview) = preview_object.as_mut() {
                ensure_object(preview).insert("ui_tree_snapshot".to_string(), ui_tree);
            }
            notes.push(format!("ui_tree_adapter_id={}", ui_tree_plan.adapter_id));
            notes.push(format!(
                "ui_tree_execution_path={}",
                ui_tree_plan.execution_path
            ));
        } else if config.ui_tree_supported {
            notes.push("ui_tree supported but no adapter source resolved".to_string());
        }
    }

    if let Some(preview) = preview_object.as_mut() {
        attach_plan_metadata(preview, &plan);
    }

    Ok(CapturePreview {
        source_backend: plan.backend.clone(),
        preview_object_kind: Some(plan.preview_object_kind.clone()),
        preview_object,
        contains_sensitive_data: contains_sensitive_data(request),
        notes,
    })
}

pub fn describe(config: &Config) -> Vec<CaptureAdapterPlan> {
    ["screen", "audio", "input", "camera"]
        .into_iter()
        .filter_map(|modality| resolve_capture_plan_for_modality(config, modality).ok())
        .collect()
}

pub fn extend_capability_notes(config: &Config, capability: &mut DeviceCapabilityDescriptor) {
    if let Ok(plan) = resolve_capture_plan_for_modality(config, &capability.modality) {
        capability
            .notes
            .push(format!("adapter_id={}", plan.adapter_id));
        capability
            .notes
            .push(format!("adapter_execution_path={}", plan.execution_path));
        capability.notes.extend(plan.notes);
    }
}

pub fn state_ui_tree_snapshot(config: &Config) -> anyhow::Result<Option<Value>> {
    let Some(plan) = state_ui_tree_adapter(config) else {
        return Ok(None);
    };
    Ok(Some(state_ui_tree_snapshot_for_adapter(config, &plan)?))
}

pub fn state_ui_tree_adapter(config: &Config) -> Option<CaptureAdapterPlan> {
    if !config.ui_tree_supported {
        return None;
    }

    let probe_result = probe::ui_tree_probe(config);
    // For state exposure, reserve "native-live" for explicit live collectors/probes.
    if let Some(result) = probe_result
        .as_ref()
        .filter(|result| result.available && result.source != "builtin-probe")
    {
        return Some(live_capture_plan(
            "ui_tree",
            "at-spi",
            "ui_tree_snapshot",
            "ui_tree.atspi-native",
            "ui_tree.atspi-probe",
            result,
        ));
    }

    if json_state_available(&config.ui_tree_state_path) {
        let mut notes = vec![format!(
            "ui_tree_state={}",
            config.ui_tree_state_path.display()
        )];
        if command_probe_gate_active(
            config.ui_tree_command.as_deref(),
            config.ui_tree_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("ui_tree_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return Some(CaptureAdapterPlan {
            modality: "ui_tree".to_string(),
            backend: "at-spi".to_string(),
            adapter_id: "ui_tree.atspi-state-file".to_string(),
            execution_path: "native-state-bridge".to_string(),
            preview_object_kind: "ui_tree_snapshot".to_string(),
            notes,
        });
    }

    if std::env::var_os("AT_SPI_BUS_ADDRESS").is_some() {
        let mut notes = vec!["at_spi_bus=true".to_string()];
        if command_probe_gate_active(
            config.ui_tree_command.as_deref(),
            config.ui_tree_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("ui_tree_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return Some(CaptureAdapterPlan {
            modality: "ui_tree".to_string(),
            backend: "at-spi".to_string(),
            adapter_id: "ui_tree.atspi-ready".to_string(),
            execution_path: "native-ready".to_string(),
            preview_object_kind: "ui_tree_snapshot".to_string(),
            notes,
        });
    }

    None
}

pub(crate) fn state_ui_tree_snapshot_for_adapter(
    config: &Config,
    plan: &CaptureAdapterPlan,
) -> anyhow::Result<Value> {
    execute_ui_tree_plan(config, plan)
}

fn resolve_capture_plan(
    config: &Config,
    request: &DeviceCaptureRequest,
) -> anyhow::Result<CaptureAdapterPlan> {
    resolve_capture_plan_for_modality(config, &request.modality)
}

fn resolve_capture_plan_for_modality(
    config: &Config,
    modality: &str,
) -> anyhow::Result<CaptureAdapterPlan> {
    match modality {
        "screen" => Ok(screen_plan(config)),
        "audio" => Ok(audio_plan(config)),
        "input" => Ok(input_plan(config)),
        "camera" => Ok(camera_plan(config)?),
        other => anyhow::bail!("unsupported capture modality: {other}"),
    }
}

fn configured_command_plan(
    modality: &str,
    backend: &str,
    adapter_id: &str,
    preview_object_kind: &str,
    configured_note: &str,
    capture_command: Option<&str>,
    explicit_probe_command: Option<&str>,
    probe_result: Option<&probe::ProbeResult>,
) -> Option<CaptureAdapterPlan> {
    capture_command?;
    let mut notes = vec![configured_note.to_string()];
    if explicit_probe_command.is_some() {
        let result = probe_result?;
        if !result.available {
            return None;
        }
        notes.extend(probe_notes(result));
    }

    Some(CaptureAdapterPlan {
        modality: modality.to_string(),
        backend: backend.to_string(),
        adapter_id: adapter_id.to_string(),
        execution_path: "command-adapter".to_string(),
        preview_object_kind: preview_object_kind.to_string(),
        notes,
    })
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

fn command_probe_gate_note(configured_note: &str) -> String {
    format!("{configured_note}; explicit probe unavailable, fallback path active")
}

fn resolve_ui_tree_plan(config: &Config) -> Option<CaptureAdapterPlan> {
    if !config.ui_tree_supported {
        return None;
    }

    let probe_result = probe::ui_tree_probe(config);
    if let Some(plan) = configured_command_plan(
        "ui_tree",
        "at-spi",
        "ui_tree.command",
        "ui_tree_snapshot",
        "ui_tree_command configured",
        config.ui_tree_command.as_deref(),
        config.ui_tree_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return Some(plan);
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return Some(live_capture_plan(
            "ui_tree",
            "at-spi",
            "ui_tree_snapshot",
            "ui_tree.atspi-native",
            "ui_tree.atspi-probe",
            result,
        ));
    }

    if json_state_available(&config.ui_tree_state_path) {
        let mut notes = vec![format!(
            "ui_tree_state={}",
            config.ui_tree_state_path.display()
        )];
        if command_probe_gate_active(
            config.ui_tree_command.as_deref(),
            config.ui_tree_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("ui_tree_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return Some(CaptureAdapterPlan {
            modality: "ui_tree".to_string(),
            backend: "at-spi".to_string(),
            adapter_id: "ui_tree.atspi-state-file".to_string(),
            execution_path: "native-state-bridge".to_string(),
            preview_object_kind: "ui_tree_snapshot".to_string(),
            notes,
        });
    }

    if std::env::var_os("AT_SPI_BUS_ADDRESS").is_some() {
        let mut notes = vec!["at_spi_bus=true".to_string()];
        if command_probe_gate_active(
            config.ui_tree_command.as_deref(),
            config.ui_tree_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("ui_tree_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return Some(CaptureAdapterPlan {
            modality: "ui_tree".to_string(),
            backend: "at-spi".to_string(),
            adapter_id: "ui_tree.atspi-ready".to_string(),
            execution_path: "native-ready".to_string(),
            preview_object_kind: "ui_tree_snapshot".to_string(),
            notes,
        });
    }

    None
}

fn disabled_plan(modality: &str, backend: &str, preview_object_kind: &str) -> CaptureAdapterPlan {
    CaptureAdapterPlan {
        modality: modality.to_string(),
        backend: backend.to_string(),
        adapter_id: format!("{modality}.disabled"),
        execution_path: "disabled".to_string(),
        preview_object_kind: preview_object_kind.to_string(),
        notes: vec![format!("{modality}_enabled=false")],
    }
}

fn is_formal_native_probe(result: &probe::ProbeResult) -> bool {
    result.source != "probe-command"
}

fn live_capture_plan(
    modality: &str,
    backend: &str,
    preview_object_kind: &str,
    native_adapter_id: &str,
    probe_adapter_id: &str,
    result: &probe::ProbeResult,
) -> CaptureAdapterPlan {
    let adapter_id = if is_formal_native_probe(result) {
        native_adapter_id
    } else {
        probe_adapter_id
    };
    let mut notes = probe_notes(result);
    if is_formal_native_probe(result) {
        notes.push("adapter_contract=formal-native-backend".to_string());
    } else {
        notes.push("adapter_contract=explicit-probe-command".to_string());
    }
    CaptureAdapterPlan {
        modality: modality.to_string(),
        backend: backend.to_string(),
        adapter_id: adapter_id.to_string(),
        execution_path: "native-live".to_string(),
        preview_object_kind: preview_object_kind.to_string(),
        notes,
    }
}

fn probe_notes(result: &probe::ProbeResult) -> Vec<String> {
    let mut notes = vec![
        format!("probe_source={}", result.source),
        format!("probe_readiness={}", result.readiness),
        format!("probe_modality={}", result.modality),
    ];
    if result.payload.is_some() {
        notes.push("probe_payload=true".to_string());
    }
    notes.extend(
        result
            .details
            .iter()
            .map(|detail| format!("probe_detail={detail}")),
    );
    notes
}

fn extend_with_probe_failure(notes: &mut Vec<String>, result: &probe::ProbeResult) {
    if result.available {
        return;
    }
    notes.push(format!("probe_source={}", result.source));
    notes.push(format!("probe_readiness={}", result.readiness));
    notes.push(format!("probe_modality={}", result.modality));
    notes.extend(
        result
            .details
            .iter()
            .map(|detail| format!("probe_detail={detail}")),
    );
}

fn execute_capture_plan(
    config: &Config,
    request: &DeviceCaptureRequest,
    plan: &CaptureAdapterPlan,
) -> anyhow::Result<Value> {
    match plan.execution_path.as_str() {
        "command-adapter" => {
            let command = capture_command_for(config, &plan.modality)
                .ok_or_else(|| anyhow::anyhow!("missing capture command for {}", plan.modality))?;
            run_capture_command(config, request, command)
        }
        "native-live" => {
            if let Some(value) = live_preview_for(config, request, &plan.modality)? {
                Ok(value)
            } else if let Some(value) = native_preview_for(config, request, &plan.modality)? {
                Ok(value)
            } else {
                Ok(fallback_preview_for(config, request, &plan.modality))
            }
        }
        "native-ready" => ready_preview_for(config, request, &plan.modality)?.ok_or_else(|| {
            anyhow::anyhow!(
                "missing native ready preview for resolved adapter {}",
                plan.adapter_id
            )
        }),
        "native-state-bridge" => state_bridge_preview_for(config, request, &plan.modality)?
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "missing native state preview for resolved adapter {}",
                    plan.adapter_id
                )
            }),
        "native-stub" => native_preview_for(config, request, &plan.modality)?.ok_or_else(|| {
            anyhow::anyhow!(
                "missing native preview for resolved adapter {}",
                plan.adapter_id
            )
        }),
        "builtin-preview" => Ok(fallback_preview_for(config, request, &plan.modality)),
        other => anyhow::bail!("unsupported adapter execution path: {other}"),
    }
}

fn execute_ui_tree_plan(config: &Config, plan: &CaptureAdapterPlan) -> anyhow::Result<Value> {
    let mut value = match plan.execution_path.as_str() {
        "command-adapter" => run_capture_command(
            config,
            &DeviceCaptureRequest {
                modality: "screen".to_string(),
                session_id: None,
                task_id: None,
                continuous: false,
                window_ref: None,
                source_device: None,
            },
            config
                .ui_tree_command
                .as_deref()
                .ok_or_else(|| anyhow::anyhow!("ui_tree command missing for resolved adapter"))?,
        ),
        "native-live" => {
            if let Some(value) = live_ui_tree_snapshot(config)? {
                Ok(value)
            } else if let Some(value) = native_ui_tree_snapshot(config)? {
                Ok(value)
            } else {
                anyhow::bail!(
                    "missing live ui_tree preview for resolved adapter {}",
                    plan.adapter_id
                )
            }
        }
        "native-state-bridge" => {
            let mut value = native_ui_tree_snapshot(config)?.ok_or_else(|| {
                anyhow::anyhow!(
                    "missing native ui_tree preview for resolved adapter {}",
                    plan.adapter_id
                )
            })?;
            let object = ensure_object(&mut value);
            object.insert("capture_mode".to_string(), json!("native-state-bridge"));
            object.insert(
                "adapter_execution_path".to_string(),
                json!("native-state-bridge"),
            );
            Ok(value)
        }
        "native-ready" => ready_ui_tree_snapshot(config)?.ok_or_else(|| {
            anyhow::anyhow!(
                "missing native ready ui_tree preview for resolved adapter {}",
                plan.adapter_id
            )
        }),
        "native-stub" => native_ui_tree_snapshot(config)?.ok_or_else(|| {
            anyhow::anyhow!(
                "missing native ui_tree preview for resolved adapter {}",
                plan.adapter_id
            )
        }),
        other => anyhow::bail!("unsupported ui_tree execution path: {other}"),
    }?;
    attach_plan_metadata(&mut value, plan);
    Ok(value)
}

fn screen_plan(config: &Config) -> CaptureAdapterPlan {
    if !config.screen_enabled {
        return disabled_plan("screen", &config.screen_backend, "screen_frame");
    }

    let probe_result = probe::capture_probe(config, "screen");
    if let Some(plan) = configured_command_plan(
        "screen",
        &config.screen_backend,
        "screen.command",
        "screen_frame",
        "screen_capture_command configured",
        config.screen_capture_command.as_deref(),
        config.screen_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return plan;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return live_capture_plan(
            "screen",
            &config.screen_backend,
            "screen_frame",
            "screen.portal-native",
            "screen.portal-probe",
            result,
        );
    }

    if json_state_available(&config.screencast_state_path) {
        let mut notes = vec![format!(
            "screencast_state={}",
            config.screencast_state_path.display()
        )];
        if command_probe_gate_active(
            config.screen_capture_command.as_deref(),
            config.screen_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("screen_capture_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return CaptureAdapterPlan {
            modality: "screen".to_string(),
            backend: config.screen_backend.clone(),
            adapter_id: "screen.portal-state-file".to_string(),
            execution_path: "native-state-bridge".to_string(),
            preview_object_kind: "screen_frame".to_string(),
            notes,
        };
    }

    if config.screen_backend.contains("portal")
        && std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some()
    {
        let mut notes = vec!["dbus_session_bus=true".to_string()];
        if command_probe_gate_active(
            config.screen_capture_command.as_deref(),
            config.screen_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("screen_capture_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return CaptureAdapterPlan {
            modality: "screen".to_string(),
            backend: config.screen_backend.clone(),
            adapter_id: "screen.portal-ready".to_string(),
            execution_path: "native-ready".to_string(),
            preview_object_kind: "screen_frame".to_string(),
            notes,
        };
    }

    let mut notes = vec!["falling back to builtin preview".to_string()];
    if command_probe_gate_active(
        config.screen_capture_command.as_deref(),
        config.screen_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        notes.push(command_probe_gate_note("screen_capture_command configured"));
    }
    if let Some(result) = probe_result.as_ref() {
        extend_with_probe_failure(&mut notes, result);
    }
    CaptureAdapterPlan {
        modality: "screen".to_string(),
        backend: config.screen_backend.clone(),
        adapter_id: "screen.builtin-preview".to_string(),
        execution_path: "builtin-preview".to_string(),
        preview_object_kind: "screen_frame".to_string(),
        notes,
    }
}

fn audio_plan(config: &Config) -> CaptureAdapterPlan {
    if !config.audio_enabled {
        return disabled_plan("audio", &config.audio_backend, "audio_chunk");
    }

    let probe_result = probe::capture_probe(config, "audio");
    if let Some(plan) = configured_command_plan(
        "audio",
        &config.audio_backend,
        "audio.command",
        "audio_chunk",
        "audio_capture_command configured",
        config.audio_capture_command.as_deref(),
        config.audio_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return plan;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return live_capture_plan(
            "audio",
            &config.audio_backend,
            "audio_chunk",
            "audio.pipewire-native",
            "audio.pipewire-probe",
            result,
        );
    }

    if config.pipewire_socket_path.exists() {
        let mut notes = vec![format!(
            "pipewire_socket={}",
            config.pipewire_socket_path.display()
        )];
        let node_available = json_state_available(&config.pipewire_node_path);
        let adapter_id = if node_available {
            notes.push(format!(
                "pipewire_node={}",
                config.pipewire_node_path.display()
            ));
            "audio.pipewire-state-file"
        } else {
            notes.push("pipewire node missing; backend ready only".to_string());
            "audio.pipewire-ready"
        };
        let execution_path = if node_available {
            "native-state-bridge"
        } else {
            "native-ready"
        };
        if command_probe_gate_active(
            config.audio_capture_command.as_deref(),
            config.audio_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("audio_capture_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return CaptureAdapterPlan {
            modality: "audio".to_string(),
            backend: config.audio_backend.clone(),
            adapter_id: adapter_id.to_string(),
            execution_path: execution_path.to_string(),
            preview_object_kind: "audio_chunk".to_string(),
            notes,
        };
    }

    let mut notes = vec!["pipewire unavailable; using builtin preview".to_string()];
    if command_probe_gate_active(
        config.audio_capture_command.as_deref(),
        config.audio_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        notes.push(command_probe_gate_note("audio_capture_command configured"));
    }
    if let Some(result) = probe_result.as_ref() {
        extend_with_probe_failure(&mut notes, result);
    }
    CaptureAdapterPlan {
        modality: "audio".to_string(),
        backend: config.audio_backend.clone(),
        adapter_id: "audio.builtin-preview".to_string(),
        execution_path: "builtin-preview".to_string(),
        preview_object_kind: "audio_chunk".to_string(),
        notes,
    }
}

fn input_plan(config: &Config) -> CaptureAdapterPlan {
    if !config.input_enabled {
        return disabled_plan("input", &config.input_backend, "input_event_batch");
    }

    let probe_result = probe::capture_probe(config, "input");
    if let Some(plan) = configured_command_plan(
        "input",
        &config.input_backend,
        "input.command",
        "input_event_batch",
        "input_capture_command configured",
        config.input_capture_command.as_deref(),
        config.input_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return plan;
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return live_capture_plan(
            "input",
            &config.input_backend,
            "input_event_batch",
            "input.libinput-native",
            "input.libinput-probe",
            result,
        );
    }

    let input_devices = input_device_names(&config.input_device_root).unwrap_or_default();
    if !input_devices.is_empty() {
        let mut notes = vec![format!("input_root={}", config.input_device_root.display())];
        notes.push(format!("device_count={}", input_devices.len()));
        if command_probe_gate_active(
            config.input_capture_command.as_deref(),
            config.input_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("input_capture_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return CaptureAdapterPlan {
            modality: "input".to_string(),
            backend: config.input_backend.clone(),
            adapter_id: "input.libinput-state-root".to_string(),
            execution_path: "native-state-bridge".to_string(),
            preview_object_kind: "input_event_batch".to_string(),
            notes,
        };
    }

    let mut notes = vec!["input root missing; using builtin preview".to_string()];
    if command_probe_gate_active(
        config.input_capture_command.as_deref(),
        config.input_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        notes.push(command_probe_gate_note("input_capture_command configured"));
    }
    if let Some(result) = probe_result.as_ref() {
        extend_with_probe_failure(&mut notes, result);
    }
    CaptureAdapterPlan {
        modality: "input".to_string(),
        backend: config.input_backend.clone(),
        adapter_id: "input.builtin-preview".to_string(),
        execution_path: "builtin-preview".to_string(),
        preview_object_kind: "input_event_batch".to_string(),
        notes,
    }
}

fn camera_plan(config: &Config) -> anyhow::Result<CaptureAdapterPlan> {
    if !config.camera_enabled {
        return Ok(disabled_plan(
            "camera",
            &config.camera_backend,
            "camera_frame",
        ));
    }

    let probe_result = probe::capture_probe(config, "camera");
    if let Some(plan) = configured_command_plan(
        "camera",
        &config.camera_backend,
        "camera.command",
        "camera_frame",
        "camera_capture_command configured",
        config.camera_capture_command.as_deref(),
        config.camera_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        return Ok(plan);
    }
    if let Some(result) = probe_result.as_ref().filter(|result| result.available) {
        return Ok(live_capture_plan(
            "camera",
            &config.camera_backend,
            "camera_frame",
            "camera.v4l-native",
            "camera.v4l-probe",
            result,
        ));
    }

    if let Some(device_path) = first_camera_device(&config.camera_device_root)? {
        let mut notes = vec![format!("device_path={device_path}")];
        if command_probe_gate_active(
            config.camera_capture_command.as_deref(),
            config.camera_probe_command.as_deref(),
            probe_result.as_ref(),
        ) {
            notes.push(command_probe_gate_note("camera_capture_command configured"));
        }
        if let Some(result) = probe_result.as_ref() {
            extend_with_probe_failure(&mut notes, result);
        }
        return Ok(CaptureAdapterPlan {
            modality: "camera".to_string(),
            backend: config.camera_backend.clone(),
            adapter_id: "camera.v4l-state-root".to_string(),
            execution_path: "native-state-bridge".to_string(),
            preview_object_kind: "camera_frame".to_string(),
            notes,
        });
    }

    let mut notes = vec!["camera device missing or disabled; using builtin preview".to_string()];
    if command_probe_gate_active(
        config.camera_capture_command.as_deref(),
        config.camera_probe_command.as_deref(),
        probe_result.as_ref(),
    ) {
        notes.push(command_probe_gate_note("camera_capture_command configured"));
    }
    if let Some(result) = probe_result.as_ref() {
        extend_with_probe_failure(&mut notes, result);
    }
    Ok(CaptureAdapterPlan {
        modality: "camera".to_string(),
        backend: config.camera_backend.clone(),
        adapter_id: "camera.builtin-preview".to_string(),
        execution_path: "builtin-preview".to_string(),
        preview_object_kind: "camera_frame".to_string(),
        notes,
    })
}

fn capture_command_for<'a>(config: &'a Config, modality: &str) -> Option<&'a str> {
    match modality {
        "screen" => config.screen_capture_command.as_deref(),
        "audio" => config.audio_capture_command.as_deref(),
        "input" => config.input_capture_command.as_deref(),
        "camera" => config.camera_capture_command.as_deref(),
        _ => None,
    }
}

fn fallback_preview_for(config: &Config, request: &DeviceCaptureRequest, modality: &str) -> Value {
    match modality {
        "screen" => capture::screen::preview_object(config, request),
        "audio" => capture::audio::preview_object(config, request),
        "input" => capture::input::preview_object(config, request),
        "camera" => capture::camera::preview_object(config, request),
        _ => json!({"unsupported_modality": modality}),
    }
}

fn native_preview_for(
    config: &Config,
    request: &DeviceCaptureRequest,
    modality: &str,
) -> anyhow::Result<Option<Value>> {
    match modality {
        "screen" => native_screen_preview(config, request),
        "audio" => native_audio_preview(config, request),
        "input" => native_input_preview(config, request),
        "camera" => native_camera_preview(config, request),
        _ => Ok(None),
    }
}

fn live_preview_for(
    config: &Config,
    request: &DeviceCaptureRequest,
    modality: &str,
) -> anyhow::Result<Option<Value>> {
    let Some(result) = probe::capture_probe(config, modality) else {
        return Ok(None);
    };
    if !result.available {
        return Ok(None);
    }

    let mut value = native_preview_for(config, request, modality)?
        .unwrap_or_else(|| fallback_preview_for(config, request, modality));
    let object = ensure_object(&mut value);
    object.insert("capture_mode".to_string(), json!("native-live"));
    object.insert("probe_source".to_string(), json!(result.source.clone()));
    object.insert(
        "probe_readiness".to_string(),
        json!(result.readiness.clone()),
    );
    if !result.details.is_empty() {
        object.insert("probe_details".to_string(), json!(result.details.clone()));
    }
    if is_formal_native_probe(&result) {
        object.insert(
            "adapter_contract".to_string(),
            json!("formal-native-backend"),
        );
    } else {
        object.insert(
            "adapter_contract".to_string(),
            json!("explicit-probe-command"),
        );
    }
    if let Some(payload) = result.payload {
        merge_payload(object, payload);
    }
    sync_helper_contract_with_request(object, request, modality);
    Ok(Some(value))
}

fn state_bridge_preview_for(
    config: &Config,
    request: &DeviceCaptureRequest,
    modality: &str,
) -> anyhow::Result<Option<Value>> {
    let mut value = native_preview_for(config, request, modality)?;
    if let Some(preview) = value.as_mut() {
        let object = ensure_object(preview);
        object.insert("capture_mode".to_string(), json!("native-state-bridge"));
    }
    Ok(value)
}

fn ready_preview_for(
    config: &Config,
    request: &DeviceCaptureRequest,
    modality: &str,
) -> anyhow::Result<Option<Value>> {
    let mut value = native_preview_for(config, request, modality)?;
    if let Some(preview) = value.as_mut() {
        let object = ensure_object(preview);
        object.insert("capture_mode".to_string(), json!("native-ready"));
        object.insert("backend_ready".to_string(), json!(true));
    }
    Ok(value)
}

fn live_ui_tree_snapshot(config: &Config) -> anyhow::Result<Option<Value>> {
    let Some(result) = probe::ui_tree_probe(config) else {
        return Ok(None);
    };
    if !result.available {
        return Ok(None);
    }

    let mut value = native_ui_tree_snapshot(config)?.unwrap_or_else(|| {
        json!({
            "snapshot_id": format!("tree-native-{}", chrono::Utc::now().timestamp_millis()),
            "source": "at-spi",
        })
    });
    let object = ensure_object(&mut value);
    object.insert("capture_mode".to_string(), json!("native-live"));
    object.insert("probe_source".to_string(), json!(result.source.clone()));
    object.insert(
        "probe_readiness".to_string(),
        json!(result.readiness.clone()),
    );
    if !result.details.is_empty() {
        object.insert("probe_details".to_string(), json!(result.details.clone()));
    }
    if is_formal_native_probe(&result) {
        object.insert(
            "adapter_contract".to_string(),
            json!("formal-native-backend"),
        );
    } else {
        object.insert(
            "adapter_contract".to_string(),
            json!("explicit-probe-command"),
        );
    }
    if let Some(payload) = result.payload {
        merge_payload(object, payload);
    }
    Ok(Some(value))
}

fn ready_ui_tree_snapshot(config: &Config) -> anyhow::Result<Option<Value>> {
    if let Some(mut value) = native_ui_tree_snapshot(config)? {
        let object = ensure_object(&mut value);
        object.insert("capture_mode".to_string(), json!("native-ready"));
        object.insert("backend_ready".to_string(), json!(true));
        object.insert("at_spi_bus".to_string(), json!(true));
        object
            .entry("source".to_string())
            .or_insert_with(|| json!("at-spi"));
        return Ok(Some(value));
    }

    if std::env::var_os("AT_SPI_BUS_ADDRESS").is_none() {
        return Ok(None);
    }

    Ok(Some(json!({
        "snapshot_id": format!("tree-ready-{}", chrono::Utc::now().timestamp_millis()),
        "source": "at-spi",
        "capture_mode": "native-ready",
        "backend_ready": true,
        "at_spi_bus": true,
    })))
}

fn contains_sensitive_data(request: &DeviceCaptureRequest) -> bool {
    match request.modality.as_str() {
        "screen" => request.continuous,
        "audio" | "input" | "camera" => true,
        _ => false,
    }
}

fn attach_plan_metadata(preview: &mut Value, plan: &CaptureAdapterPlan) {
    let object = ensure_object(preview);
    let adapter_contract = plan
        .notes
        .iter()
        .find_map(|note| note.strip_prefix("adapter_contract="));
    let source = object
        .get("probe_source")
        .and_then(Value::as_str)
        .or_else(|| object.get("source").and_then(Value::as_str))
        .map(str::to_string);
    release_grade::enrich_object(
        &plan.modality,
        Some(plan.execution_path.as_str()),
        source.as_deref(),
        adapter_contract,
        object,
    );

    let mut adapter = Map::new();
    adapter.insert("adapter_id".to_string(), json!(plan.adapter_id));
    adapter.insert("backend".to_string(), json!(plan.backend));
    adapter.insert("execution_path".to_string(), json!(plan.execution_path));
    adapter.insert("adapter_contract".to_string(), json!(adapter_contract));
    adapter.insert("notes".to_string(), json!(plan.notes));

    for field in [
        "release_grade_backend",
        "release_grade_backend_id",
        "release_grade_backend_origin",
        "release_grade_backend_stack",
        "release_grade_contract_kind",
    ] {
        if let Some(value) = object.get(field).cloned() {
            adapter.insert(field.to_string(), value);
        }
    }

    object.insert("adapter".to_string(), Value::Object(adapter));
    object.insert("adapter_id".to_string(), json!(plan.adapter_id));
    object.insert(
        "adapter_execution_path".to_string(),
        json!(plan.execution_path),
    );
    if let Some(adapter_contract) = adapter_contract {
        object.insert("adapter_contract".to_string(), json!(adapter_contract));
    }
}

fn merge_payload(target: &mut Map<String, Value>, payload: Value) {
    match payload {
        Value::Object(items) => {
            for (key, value) in items {
                target.insert(key, value);
            }
        }
        other => {
            target.insert("probe_payload".to_string(), other);
        }
    }
}

fn sync_helper_contract_with_request(
    object: &mut Map<String, Value>,
    request: &DeviceCaptureRequest,
    modality: &str,
) {
    let request_binding = object
        .entry("request_binding".to_string())
        .or_insert_with(|| json!({}));
    let Some(binding) = request_binding.as_object_mut() else {
        return;
    };

    binding.insert("modality".to_string(), json!(modality));
    binding.insert("continuous".to_string(), json!(request.continuous));
    if let Some(session_id) = request.session_id.as_ref() {
        binding.insert("session_id".to_string(), json!(session_id));
    }
    if let Some(task_id) = request.task_id.as_ref() {
        binding.insert("task_id".to_string(), json!(task_id));
    }
    if let Some(window_ref) = request.window_ref.as_ref() {
        binding.insert("window_ref".to_string(), json!(window_ref));
    }
    if let Some(source_device) = request.source_device.as_ref() {
        binding.insert("source_device".to_string(), json!(source_device));
    }

    let session_id = binding
        .get("session_id")
        .and_then(Value::as_str)
        .unwrap_or("anonymous-session");
    let task_id = binding
        .get("task_id")
        .and_then(Value::as_str)
        .unwrap_or("ad-hoc-task");
    let request_ref = format!("{session_id}:{task_id}:{modality}");
    let adapter_hint = object
        .get("session_contract")
        .and_then(Value::as_object)
        .and_then(|contract| contract.get("adapter_hint"))
        .and_then(Value::as_str)
        .or_else(|| object.get("adapter_hint").and_then(Value::as_str))
        .map(str::to_string);

    if let Some(contract) = object
        .get_mut("session_contract")
        .and_then(Value::as_object_mut)
    {
        contract.insert("request_ref".to_string(), json!(request_ref.clone()));
        if let Some(adapter_hint) = adapter_hint.as_deref() {
            contract.insert(
                "lease_id".to_string(),
                json!(format!("{adapter_hint}:{request_ref}")),
            );
        }
    }

    if let Some(media_pipeline) = object
        .get_mut("media_pipeline")
        .and_then(Value::as_object_mut)
    {
        media_pipeline.insert("continuous".to_string(), json!(request.continuous));
    }
}

fn native_screen_preview(
    config: &Config,
    request: &DeviceCaptureRequest,
) -> anyhow::Result<Option<Value>> {
    if let Some(mut value) = read_json_value(&config.screencast_state_path)? {
        let object = ensure_object(&mut value);
        object.entry("frame_id".to_string()).or_insert_with(|| {
            json!(format!(
                "frame-native-{}",
                chrono::Utc::now().timestamp_millis()
            ))
        });
        object.entry("window_ref".to_string()).or_insert_with(|| {
            json!(request
                .window_ref
                .clone()
                .unwrap_or_else(|| "portal-window".to_string()))
        });
        object
            .entry("resolution".to_string())
            .or_insert_with(|| json!(config.default_resolution.clone()));
        object.insert("capture_mode".to_string(), json!("native-stub"));
        object.insert("backend_source".to_string(), json!("portal-state-file"));
        return Ok(Some(value));
    }

    if config.screen_backend.contains("portal")
        && std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some()
    {
        return Ok(Some(json!({
            "frame_id": format!("frame-native-{}", chrono::Utc::now().timestamp_millis()),
            "window_ref": request.window_ref.clone().unwrap_or_else(|| "portal-window".to_string()),
            "resolution": config.default_resolution,
            "capture_mode": "native-stub",
            "backend_source": "portal-session-bus",
            "portal_session_bus": true,
        })));
    }

    Ok(None)
}

fn native_audio_preview(
    config: &Config,
    request: &DeviceCaptureRequest,
) -> anyhow::Result<Option<Value>> {
    if !config.pipewire_socket_path.exists() {
        return Ok(None);
    }

    let mut value = capture::audio::preview_object(config, request);
    let object = ensure_object(&mut value);
    object.insert("capture_mode".to_string(), json!("native-stub"));
    object.insert("backend_source".to_string(), json!("pipewire-socket"));
    object.insert(
        "pipewire_socket".to_string(),
        json!(config.pipewire_socket_path.display().to_string()),
    );
    if let Some(node) = read_json_value(&config.pipewire_node_path)? {
        object.insert("pipewire_node".to_string(), node);
    }
    Ok(Some(value))
}

fn native_input_preview(
    config: &Config,
    request: &DeviceCaptureRequest,
) -> anyhow::Result<Option<Value>> {
    let devices = input_device_names(&config.input_device_root)?;
    if devices.is_empty() {
        return Ok(None);
    }

    let mut value = capture::input::preview_object(config, request);
    let object = ensure_object(&mut value);
    object.insert("capture_mode".to_string(), json!("native-stub"));
    object.insert("input_devices".to_string(), json!(devices.clone()));
    object.insert("device_count".to_string(), json!(devices.len()));
    Ok(Some(value))
}

fn native_camera_preview(
    config: &Config,
    request: &DeviceCaptureRequest,
) -> anyhow::Result<Option<Value>> {
    if !config.camera_enabled {
        return Ok(None);
    }

    let Some(device_path) = first_camera_device(&config.camera_device_root)? else {
        return Ok(None);
    };

    let mut value = capture::camera::preview_object(config, request);
    let object = ensure_object(&mut value);
    object.insert("capture_mode".to_string(), json!("native-stub"));
    object.insert("device_path".to_string(), json!(device_path));
    Ok(Some(value))
}

fn native_ui_tree_snapshot(config: &Config) -> anyhow::Result<Option<Value>> {
    if let Some(mut value) = read_json_value(&config.ui_tree_state_path)? {
        let object = ensure_object(&mut value);
        object.entry("snapshot_id".to_string()).or_insert_with(|| {
            json!(format!(
                "tree-native-{}",
                chrono::Utc::now().timestamp_millis()
            ))
        });
        object.insert("capture_mode".to_string(), json!("native-stub"));
        object.insert("adapter_id".to_string(), json!("ui_tree.atspi-state-file"));
        return Ok(Some(value));
    }

    Ok(None)
}

fn read_json_value(path: &std::path::Path) -> anyhow::Result<Option<Value>> {
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(path)
        .with_context(|| format!("failed to read backend state {}", path.display()))?;
    let value = serde_json::from_str::<Value>(&content)
        .with_context(|| format!("invalid backend state {}", path.display()))?;
    Ok(Some(value))
}

fn list_entry_names(path: &std::path::Path) -> anyhow::Result<Vec<String>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let mut items = fs::read_dir(path)?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.file_name().to_string_lossy().to_string())
        .collect::<Vec<_>>();
    items.sort();
    Ok(items)
}

fn input_device_names(path: &std::path::Path) -> anyhow::Result<Vec<String>> {
    Ok(list_entry_names(path)?
        .into_iter()
        .filter(|item| {
            item.starts_with("event") || item.starts_with("mouse") || item.starts_with("kbd")
        })
        .collect())
}

fn first_camera_device(path: &std::path::Path) -> anyhow::Result<Option<String>> {
    let mut devices = list_entry_names(path)?
        .into_iter()
        .filter(|item| item.starts_with("video"))
        .collect::<Vec<_>>();
    devices.sort();
    Ok(devices
        .first()
        .map(|device| path.join(device).display().to_string()))
}

fn json_state_available(path: &std::path::Path) -> bool {
    read_json_value(path).ok().flatten().is_some()
}

fn run_capture_command(
    config: &Config,
    request: &DeviceCaptureRequest,
    command: &str,
) -> anyhow::Result<Value> {
    let mut shell = Command::new("/bin/sh");
    shell.arg("-lc").arg(command);
    shell.env("AIOS_DEVICED_MODALITY", &request.modality);
    shell.env("AIOS_DEVICED_CONTINUOUS", request.continuous.to_string());
    shell.env(
        "AIOS_DEVICED_DEFAULT_RESOLUTION",
        &config.default_resolution,
    );
    shell.env(
        "AIOS_DEVICED_UI_TREE_SUPPORTED",
        config.ui_tree_supported.to_string(),
    );
    if let Some(session_id) = &request.session_id {
        shell.env("AIOS_DEVICED_SESSION_ID", session_id);
    }
    if let Some(task_id) = &request.task_id {
        shell.env("AIOS_DEVICED_TASK_ID", task_id);
    }
    if let Some(window_ref) = &request.window_ref {
        shell.env("AIOS_DEVICED_WINDOW_REF", window_ref);
    }
    if let Some(source_device) = &request.source_device {
        shell.env("AIOS_DEVICED_SOURCE_DEVICE", source_device);
    }

    let output = shell.output()?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stdout.is_empty() {
        return Ok(json!({"status": if output.status.success() {"ok"} else {"failed"}}));
    }

    if let Ok(value) = serde_json::from_str::<Value>(&stdout) {
        return Ok(value);
    }

    Ok(json!({"raw_stdout": stdout}))
}

fn ensure_object(value: &mut Value) -> &mut Map<String, Value> {
    if !value.is_object() {
        let original = value.clone();
        *value = json!({"raw_payload": original});
    }

    value.as_object_mut().expect("value converted to object")
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    struct EnvVarGuard {
        key: &'static str,
        previous: Option<OsString>,
    }

    impl EnvVarGuard {
        fn set(key: &'static str, value: &str) -> Self {
            let previous = std::env::var_os(key);
            std::env::set_var(key, value);
            Self { key, previous }
        }

        fn unset(key: &'static str) -> Self {
            let previous = std::env::var_os(key);
            std::env::remove_var(key);
            Self { key, previous }
        }
    }

    impl Drop for EnvVarGuard {
        fn drop(&mut self) {
            if let Some(value) = self.previous.as_ref() {
                std::env::set_var(self.key, value);
            } else {
                std::env::remove_var(self.key);
            }
        }
    }

    fn probe_shell_supported() -> bool {
        std::path::Path::new("/bin/sh").exists()
    }

    fn config() -> Config {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        let unique = TEST_COUNTER.fetch_add(1, Ordering::Relaxed);
        let state_root =
            std::env::temp_dir().join(format!("aios-deviced-adapters-test-{stamp}-{unique}"));
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
            camera_enabled: false,
            ui_tree_supported: false,
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
    fn probe_selects_native_live_adapter() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _dbus = EnvVarGuard::unset("DBUS_SESSION_BUS_ADDRESS");
        let _atspi = EnvVarGuard::unset("AT_SPI_BUS_ADDRESS");
        if !probe_shell_supported() {
            return;
        }
        let mut config = config();
        config.screen_probe_command = Some(
            r#"printf '%s\n' '{"available":true,"readiness":"native-live","payload":{"probe_frame":true}}'"#
                .to_string(),
        );

        let plan = describe(&config)
            .into_iter()
            .find(|item| item.modality == "screen")
            .expect("screen plan present");

        assert_eq!(plan.adapter_id, "screen.portal-probe");
        assert_eq!(plan.execution_path, "native-live");
        assert!(plan.notes.iter().any(|item| item == "probe_payload=true"));

        cleanup(&config);
    }

    #[test]
    fn live_command_selects_formal_native_adapter() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _dbus = EnvVarGuard::unset("DBUS_SESSION_BUS_ADDRESS");
        let _atspi = EnvVarGuard::unset("AT_SPI_BUS_ADDRESS");
        if !probe_shell_supported() {
            return;
        }
        let mut config = config();
        config.screen_live_command = Some(
            r#"printf '%s\n' '{"available":true,"readiness":"native-live","payload":{"release_grade_backend":"xdg-desktop-portal-screencast","release_grade_backend_id":"xdg-desktop-portal-screencast","release_grade_backend_origin":"os-native","release_grade_backend_stack":"portal+pipewire","release_grade_contract_kind":"release-grade-runtime-helper","stream_node_id":108}}'"#
                .to_string(),
        );

        let plan = describe(&config)
            .into_iter()
            .find(|item| item.modality == "screen")
            .expect("screen plan present");

        assert_eq!(plan.adapter_id, "screen.portal-native");
        assert_eq!(plan.execution_path, "native-live");
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "probe_source=builtin-screen-live-command"));
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "adapter_contract=formal-native-backend"));

        let preview = capture_preview(
            &config,
            &DeviceCaptureRequest {
                modality: "screen".to_string(),
                session_id: Some("session-live".to_string()),
                task_id: None,
                continuous: false,
                window_ref: Some("window-live".to_string()),
                source_device: None,
            },
        )
        .expect("capture preview");

        let preview_object = preview.preview_object.expect("preview object");
        assert_eq!(
            preview_object
                .get("release_grade_backend")
                .and_then(Value::as_str),
            Some("xdg-desktop-portal-screencast")
        );
        assert_eq!(
            preview_object
                .get("adapter_contract")
                .and_then(Value::as_str),
            Some("formal-native-backend")
        );

        cleanup(&config);
    }

    #[test]
    fn live_helper_contract_is_rebound_to_capture_request_context() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _dbus = EnvVarGuard::unset("DBUS_SESSION_BUS_ADDRESS");
        let _atspi = EnvVarGuard::unset("AT_SPI_BUS_ADDRESS");
        if !probe_shell_supported() {
            return;
        }
        let mut config = config();
        config.screen_live_command = Some(
            r#"printf '%s\n' '{"available":true,"readiness":"native-live","payload":{"release_grade_backend":"xdg-desktop-portal-screencast","release_grade_backend_id":"xdg-desktop-portal-screencast","release_grade_backend_origin":"os-native","release_grade_backend_stack":"portal+pipewire","release_grade_contract_kind":"release-grade-runtime-helper","adapter_hint":"screen.portal-native","request_binding":{"modality":"screen","session_id":"anonymous-session","task_id":"ad-hoc-task","continuous":false},"session_contract":{"contract_kind":"release-grade-runtime-helper","adapter_hint":"screen.portal-native","request_ref":"anonymous-session:ad-hoc-task:screen","lease_id":"screen.portal-native:anonymous-session:ad-hoc-task:screen"},"media_pipeline":{"collector":"screen.portal-live","continuous":false}}}'"#
                .to_string(),
        );

        let preview = capture_preview(
            &config,
            &DeviceCaptureRequest {
                modality: "screen".to_string(),
                session_id: Some("session-live".to_string()),
                task_id: Some("task-live".to_string()),
                continuous: true,
                window_ref: Some("window-live".to_string()),
                source_device: None,
            },
        )
        .expect("capture preview");

        let preview_object = preview.preview_object.expect("preview object");
        assert_eq!(
            preview_object
                .get("request_binding")
                .and_then(Value::as_object)
                .and_then(|binding| binding.get("session_id"))
                .and_then(Value::as_str),
            Some("session-live")
        );
        assert_eq!(
            preview_object
                .get("request_binding")
                .and_then(Value::as_object)
                .and_then(|binding| binding.get("task_id"))
                .and_then(Value::as_str),
            Some("task-live")
        );
        assert_eq!(
            preview_object
                .get("session_contract")
                .and_then(Value::as_object)
                .and_then(|contract| contract.get("request_ref"))
                .and_then(Value::as_str),
            Some("session-live:task-live:screen")
        );
        assert_eq!(
            preview_object
                .get("session_contract")
                .and_then(Value::as_object)
                .and_then(|contract| contract.get("lease_id"))
                .and_then(Value::as_str),
            Some("screen.portal-native:session-live:task-live:screen")
        );
        assert_eq!(
            preview_object
                .get("media_pipeline")
                .and_then(Value::as_object)
                .and_then(|pipeline| pipeline.get("continuous"))
                .and_then(Value::as_bool),
            Some(true)
        );

        cleanup(&config);
    }

    #[test]
    fn probe_payload_is_merged_into_preview() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _dbus = EnvVarGuard::unset("DBUS_SESSION_BUS_ADDRESS");
        let _atspi = EnvVarGuard::unset("AT_SPI_BUS_ADDRESS");
        if !probe_shell_supported() {
            return;
        }
        let mut config = config();
        config.screen_probe_command = Some(
            r#"printf '%s\n' '{"available":true,"readiness":"native-live","payload":{"probe_frame":true,"probe_resolution":"1024x768"}}'"#
                .to_string(),
        );

        let preview = capture_preview(
            &config,
            &DeviceCaptureRequest {
                modality: "screen".to_string(),
                session_id: Some("session-1".to_string()),
                task_id: None,
                continuous: false,
                window_ref: Some("window-1".to_string()),
                source_device: None,
            },
        )
        .expect("capture preview");

        let preview_object = preview.preview_object.expect("preview object");
        assert_eq!(
            preview_object.get("probe_frame").and_then(Value::as_bool),
            Some(true)
        );
        assert_eq!(
            preview_object
                .get("probe_resolution")
                .and_then(Value::as_str),
            Some("1024x768")
        );
        assert_eq!(
            preview_object
                .get("adapter_execution_path")
                .and_then(Value::as_str),
            Some("native-live")
        );

        cleanup(&config);
    }

    #[test]
    fn failed_probe_falls_back_to_state_stub() {
        let mut config = config();
        fs::create_dir_all(config.screencast_state_path.parent().expect("state dir"))
            .expect("create state dir");
        fs::write(
            &config.screencast_state_path,
            serde_json::to_vec(&json!({"stream_node_id": 7, "window_ref": "window-1"}))
                .expect("encode state"),
        )
        .expect("write screencast state");
        config.screen_probe_command = Some("printf 'probe failed\n' >&2; exit 7".to_string());

        let plan = describe(&config)
            .into_iter()
            .find(|item| item.modality == "screen")
            .expect("screen plan present");

        assert_eq!(plan.adapter_id, "screen.portal-state-file");
        assert_eq!(plan.execution_path, "native-state-bridge");
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "probe_readiness=probe-failed"));
        assert!(plan
            .notes
            .iter()
            .any(|item| item.starts_with("probe_detail=")));

        cleanup(&config);
    }

    #[test]
    fn state_root_preview_uses_native_state_bridge_mode() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _dbus = EnvVarGuard::unset("DBUS_SESSION_BUS_ADDRESS");
        let _atspi = EnvVarGuard::unset("AT_SPI_BUS_ADDRESS");
        let mut config = config();
        config.screen_probe_command = Some("printf 'probe failed\\n' >&2; exit 7".to_string());
        fs::create_dir_all(config.screencast_state_path.parent().expect("state dir"))
            .expect("create state dir");
        fs::write(
            &config.screencast_state_path,
            serde_json::to_vec(&json!({"stream_node_id": 7, "window_ref": "window-1"}))
                .expect("encode state"),
        )
        .expect("write state file");

        let preview = capture_preview(
            &config,
            &DeviceCaptureRequest {
                modality: "screen".to_string(),
                session_id: Some("session-1".to_string()),
                task_id: None,
                continuous: false,
                window_ref: Some("window-1".to_string()),
                source_device: None,
            },
        )
        .expect("capture preview should succeed");

        let preview_object = preview.preview_object.expect("preview object present");
        assert_eq!(
            preview_object.get("capture_mode").and_then(Value::as_str),
            Some("native-state-bridge")
        );
        assert_eq!(
            preview_object
                .get("adapter_execution_path")
                .and_then(Value::as_str),
            Some("native-state-bridge")
        );
        assert_eq!(
            preview_object
                .get("release_grade_backend_id")
                .and_then(Value::as_str),
            Some("xdg-desktop-portal-screencast")
        );
        assert_eq!(
            preview_object
                .get("release_grade_backend_origin")
                .and_then(Value::as_str),
            Some("state-bridge")
        );

        cleanup(&config);
    }

    #[test]
    fn screen_bus_only_uses_native_ready_mode() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _env = EnvVarGuard::set("DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/dbus-test-bus");

        let mut config = config();
        config.screen_probe_command = Some("printf 'probe failed\n' >&2; exit 7".to_string());

        let plan = describe(&config)
            .into_iter()
            .find(|item| item.modality == "screen")
            .expect("screen plan present");
        assert_eq!(plan.adapter_id, "screen.portal-ready");
        assert_eq!(plan.execution_path, "native-ready");
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "dbus_session_bus=true"));
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "probe_readiness=probe-failed"));

        let preview = capture_preview(
            &config,
            &DeviceCaptureRequest {
                modality: "screen".to_string(),
                session_id: Some("session-1".to_string()),
                task_id: None,
                continuous: false,
                window_ref: Some("window-1".to_string()),
                source_device: None,
            },
        )
        .expect("screen ready preview should succeed");

        let preview_object = preview.preview_object.expect("preview object present");
        assert_eq!(
            preview_object.get("capture_mode").and_then(Value::as_str),
            Some("native-ready")
        );
        assert_eq!(
            preview_object
                .get("adapter_execution_path")
                .and_then(Value::as_str),
            Some("native-ready")
        );
        assert_eq!(
            preview_object.get("adapter_id").and_then(Value::as_str),
            Some("screen.portal-ready")
        );
        assert_eq!(
            preview_object
                .get("portal_session_bus")
                .and_then(Value::as_bool),
            Some(true)
        );
        assert_eq!(
            preview_object.get("backend_ready").and_then(Value::as_bool),
            Some(true)
        );
        assert_eq!(
            preview_object
                .get("release_grade_backend_origin")
                .and_then(Value::as_str),
            Some("declared-ready")
        );
        assert_eq!(
            preview_object
                .get("release_grade_backend_stack")
                .and_then(Value::as_str),
            Some("portal+pipewire")
        );

        cleanup(&config);
    }

    #[test]
    fn audio_socket_only_uses_native_ready_mode() {
        let mut config = config();
        config.audio_probe_command = Some("printf 'probe failed\n' >&2; exit 7".to_string());
        fs::create_dir_all(config.pipewire_socket_path.parent().expect("pipewire dir"))
            .expect("create pipewire dir");
        fs::write(&config.pipewire_socket_path, b"ready\n").expect("write pipewire socket");

        let plan = describe(&config)
            .into_iter()
            .find(|item| item.modality == "audio")
            .expect("audio plan present");
        assert_eq!(plan.adapter_id, "audio.pipewire-ready");
        assert_eq!(plan.execution_path, "native-ready");
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "pipewire node missing; backend ready only"));
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "probe_readiness=probe-failed"));

        let preview = capture_preview(
            &config,
            &DeviceCaptureRequest {
                modality: "audio".to_string(),
                session_id: None,
                task_id: None,
                continuous: true,
                window_ref: None,
                source_device: Some("mic-1".to_string()),
            },
        )
        .expect("audio ready preview should succeed");

        let preview_object = preview.preview_object.expect("preview object present");
        assert_eq!(
            preview_object.get("capture_mode").and_then(Value::as_str),
            Some("native-ready")
        );
        assert_eq!(
            preview_object
                .get("adapter_execution_path")
                .and_then(Value::as_str),
            Some("native-ready")
        );
        assert_eq!(
            preview_object.get("adapter_id").and_then(Value::as_str),
            Some("audio.pipewire-ready")
        );
        assert_eq!(
            preview_object.get("backend_source").and_then(Value::as_str),
            Some("pipewire-socket")
        );
        assert_eq!(
            preview_object.get("backend_ready").and_then(Value::as_bool),
            Some(true)
        );
        assert!(preview_object.get("pipewire_node").is_none());

        cleanup(&config);
    }

    #[test]
    fn explicit_probe_failure_blocks_command_adapter_plan_shortcut() {
        let mut config = config();
        config.camera_enabled = true;
        config.ui_tree_supported = true;
        fs::create_dir_all(config.screencast_state_path.parent().expect("state dir"))
            .expect("create state dir");
        fs::write(&config.screencast_state_path, b"{}").expect("write screencast state");
        fs::create_dir_all(config.pipewire_socket_path.parent().expect("pipewire dir"))
            .expect("create pipewire dir");
        fs::write(&config.pipewire_socket_path, b"ready\n").expect("write pipewire socket");
        fs::write(&config.pipewire_node_path, b"{}").expect("write pipewire node");
        fs::create_dir_all(&config.input_device_root).expect("create input root");
        fs::write(config.input_device_root.join("event0"), b"keyboard\n")
            .expect("write input device");
        fs::create_dir_all(&config.camera_device_root).expect("create camera root");
        fs::write(config.camera_device_root.join("video0"), b"ready\n")
            .expect("write camera device");
        fs::create_dir_all(config.ui_tree_state_path.parent().expect("ui tree dir"))
            .expect("create ui tree dir");
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

        let plans = describe(&config);
        for modality in ["screen", "audio", "input", "camera"] {
            let plan = plans
                .iter()
                .find(|item| item.modality == modality)
                .unwrap_or_else(|| panic!("missing plan for {modality}"));
            assert_ne!(
                plan.execution_path, "command-adapter",
                "{modality} should not short-circuit to command-adapter"
            );
            assert!(
                plan.notes
                    .iter()
                    .any(|item| item.contains("explicit probe unavailable")),
                "{modality} should record the probe gate note: {:?}",
                plan.notes
            );
            assert!(
                plan.notes
                    .iter()
                    .any(|item| item == "probe_readiness=probe-failed"),
                "{modality} should keep probe failure detail"
            );
        }

        let ui_tree_plan = resolve_ui_tree_plan(&config).expect("ui_tree plan");
        assert_ne!(ui_tree_plan.execution_path, "command-adapter");
        assert!(ui_tree_plan
            .notes
            .iter()
            .any(|item| item.contains("explicit probe unavailable")));
        assert!(ui_tree_plan
            .notes
            .iter()
            .any(|item| item == "probe_readiness=probe-failed"));

        cleanup(&config);
    }

    #[test]
    fn camera_state_root_uses_native_state_bridge_mode() {
        let mut config = config();
        config.camera_enabled = true;
        config.camera_probe_command = Some("printf 'probe failed\\n' >&2; exit 7".to_string());
        fs::create_dir_all(&config.camera_device_root).expect("create camera root");
        fs::write(config.camera_device_root.join("video0"), b"ready\n")
            .expect("write camera device");

        let plan = describe(&config)
            .into_iter()
            .find(|item| item.modality == "camera")
            .expect("camera plan present");
        assert_eq!(plan.adapter_id, "camera.v4l-state-root");
        assert_eq!(plan.execution_path, "native-state-bridge");
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "probe_readiness=probe-failed"));

        let preview = capture_preview(
            &config,
            &DeviceCaptureRequest {
                modality: "camera".to_string(),
                session_id: None,
                task_id: None,
                continuous: false,
                window_ref: None,
                source_device: Some("camera-1".to_string()),
            },
        )
        .expect("camera preview should succeed");

        let preview_object = preview.preview_object.expect("preview object present");
        let expected_path = config
            .camera_device_root
            .join("video0")
            .display()
            .to_string();
        assert_eq!(
            preview_object.get("capture_mode").and_then(Value::as_str),
            Some("native-state-bridge")
        );
        assert_eq!(
            preview_object
                .get("adapter_execution_path")
                .and_then(Value::as_str),
            Some("native-state-bridge")
        );
        assert_eq!(
            preview_object.get("adapter_id").and_then(Value::as_str),
            Some("camera.v4l-state-root")
        );
        assert_eq!(
            preview_object.get("device_path").and_then(Value::as_str),
            Some(expected_path.as_str())
        );

        cleanup(&config);
    }

    #[test]
    fn ui_tree_state_file_uses_native_state_bridge_mode() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _dbus = EnvVarGuard::unset("DBUS_SESSION_BUS_ADDRESS");
        let _atspi = EnvVarGuard::unset("AT_SPI_BUS_ADDRESS");
        let mut config = config();
        config.ui_tree_supported = true;
        config.ui_tree_probe_command = Some("printf 'probe failed\n' >&2; exit 7".to_string());
        fs::create_dir_all(config.ui_tree_state_path.parent().expect("state dir"))
            .expect("create state dir");
        fs::write(
            &config.ui_tree_state_path,
            serde_json::to_vec(&json!({"snapshot_id": "tree-state-1", "focus_node": "node-1"}))
                .expect("encode ui tree state"),
        )
        .expect("write ui tree state");

        let plan = resolve_ui_tree_plan(&config).expect("ui_tree plan present");
        assert_eq!(plan.adapter_id, "ui_tree.atspi-state-file");
        assert_eq!(plan.execution_path, "native-state-bridge");
        assert!(plan
            .notes
            .iter()
            .any(|item| item == "probe_readiness=probe-failed"));

        let snapshot = execute_ui_tree_plan(&config, &plan).expect("ui_tree snapshot present");
        assert_eq!(
            snapshot.get("snapshot_id").and_then(Value::as_str),
            Some("tree-state-1")
        );
        assert_eq!(
            snapshot.get("capture_mode").and_then(Value::as_str),
            Some("native-state-bridge")
        );
        assert_eq!(
            snapshot
                .get("adapter_execution_path")
                .and_then(Value::as_str),
            Some("native-state-bridge")
        );
        assert_eq!(
            snapshot.get("adapter_id").and_then(Value::as_str),
            Some("ui_tree.atspi-state-file")
        );
        assert_eq!(
            snapshot
                .get("adapter")
                .and_then(|item| item.get("backend"))
                .and_then(Value::as_str),
            Some("at-spi")
        );
        assert_eq!(
            snapshot
                .get("release_grade_backend_origin")
                .and_then(Value::as_str),
            Some("state-bridge")
        );

        cleanup(&config);
    }

    #[test]
    fn ui_tree_bus_only_uses_native_ready_mode() {
        let _guard = crate::TEST_ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let _env = EnvVarGuard::set("AT_SPI_BUS_ADDRESS", "unix:path=/tmp/atspi-test-bus");

        let mut config = config();
        config.ui_tree_supported = true;

        let plan = resolve_ui_tree_plan(&config).expect("ui_tree plan present");
        assert_eq!(plan.adapter_id, "ui_tree.atspi-ready");
        assert_eq!(plan.execution_path, "native-ready");
        assert!(plan.notes.iter().any(|item| item == "at_spi_bus=true"));

        let snapshot = execute_ui_tree_plan(&config, &plan).expect("ui_tree snapshot present");
        assert_eq!(
            snapshot.get("capture_mode").and_then(Value::as_str),
            Some("native-ready")
        );
        assert_eq!(
            snapshot.get("adapter_id").and_then(Value::as_str),
            Some("ui_tree.atspi-ready")
        );
        assert_eq!(
            snapshot.get("backend_ready").and_then(Value::as_bool),
            Some(true)
        );
        assert_eq!(
            snapshot.get("at_spi_bus").and_then(Value::as_bool),
            Some(true)
        );
        assert_eq!(
            snapshot
                .get("release_grade_backend_id")
                .and_then(Value::as_str),
            Some("at-spi")
        );
        assert_eq!(
            snapshot
                .get("release_grade_backend_origin")
                .and_then(Value::as_str),
            Some("declared-ready")
        );

        cleanup(&config);
    }
}
