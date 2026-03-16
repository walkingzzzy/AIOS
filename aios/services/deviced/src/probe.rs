use std::{fs, io::ErrorKind, path::Path, process::Command};

use serde_json::{json, Value};

use crate::{config::Config, release_grade};

#[derive(Debug, Clone)]
pub struct ProbeResult {
    pub modality: String,
    pub available: bool,
    pub readiness: String,
    pub details: Vec<String>,
    pub payload: Option<Value>,
    pub source: String,
}

pub fn configured_modalities(config: &Config) -> Vec<&'static str> {
    let mut items = Vec::new();
    if config.screen_probe_command.is_some() {
        items.push("screen");
    }
    if config.audio_probe_command.is_some() {
        items.push("audio");
    }
    if config.input_probe_command.is_some() {
        items.push("input");
    }
    if config.camera_probe_command.is_some() {
        items.push("camera");
    }
    if config.ui_tree_probe_command.is_some() {
        items.push("ui_tree");
    }
    items
}

pub fn builtin_capture_probe(config: &Config, modality: &str) -> Option<ProbeResult> {
    match modality {
        "screen" => Some(finalize_probe_result(
            "screen",
            builtin_screen_probe(config),
        )),
        "audio" => Some(finalize_probe_result("audio", builtin_audio_probe(config))),
        "input" => Some(finalize_probe_result("input", builtin_input_probe(config))),
        "camera" => Some(finalize_probe_result(
            "camera",
            builtin_camera_probe(config),
        )),
        _ => None,
    }
}

pub fn capture_probe(config: &Config, modality: &str) -> Option<ProbeResult> {
    match modality {
        "screen" => Some(finalize_probe_result(
            "screen",
            config
                .screen_probe_command
                .as_deref()
                .map(|command| run_probe(config, modality, command))
                .unwrap_or_else(|| builtin_screen_probe(config)),
        )),
        "audio" => Some(finalize_probe_result(
            "audio",
            config
                .audio_probe_command
                .as_deref()
                .map(|command| run_probe(config, modality, command))
                .unwrap_or_else(|| builtin_audio_probe(config)),
        )),
        "input" => Some(finalize_probe_result(
            "input",
            config
                .input_probe_command
                .as_deref()
                .map(|command| run_probe(config, modality, command))
                .unwrap_or_else(|| builtin_input_probe(config)),
        )),
        "camera" => Some(finalize_probe_result(
            "camera",
            config
                .camera_probe_command
                .as_deref()
                .map(|command| run_probe(config, modality, command))
                .unwrap_or_else(|| builtin_camera_probe(config)),
        )),
        _ => None,
    }
}

pub fn builtin_ui_tree_probe(config: &Config) -> ProbeResult {
    finalize_probe_result("ui_tree", builtin_ui_tree_probe_result(config))
}

pub fn ui_tree_probe(config: &Config) -> Option<ProbeResult> {
    Some(finalize_probe_result(
        "ui_tree",
        config
            .ui_tree_probe_command
            .as_deref()
            .map(|command| run_probe(config, "ui_tree", command))
            .unwrap_or_else(|| builtin_ui_tree_probe_result(config)),
    ))
}

fn native_live_command<'a>(config: &'a Config, modality: &str) -> Option<&'a str> {
    match modality {
        "screen" => config.screen_live_command.as_deref(),
        "audio" => config.audio_live_command.as_deref(),
        "input" => config.input_live_command.as_deref(),
        "camera" => config.camera_live_command.as_deref(),
        _ => None,
    }
}

fn finalize_probe_result(modality: &str, mut result: ProbeResult) -> ProbeResult {
    let source = result.source.as_str();
    result.payload = release_grade::enrich_payload(
        modality,
        None,
        Some(source),
        release_grade::default_adapter_contract(Some(source)),
        result.payload,
    );
    result
}

fn run_probe(config: &Config, modality: &str, command: &str) -> ProbeResult {
    let mut shell = Command::new("/bin/sh");
    shell.arg("-lc").arg(command);
    configure_probe_env(&mut shell, config, modality);

    let output = match shell.output() {
        Ok(output) => output,
        Err(error) => {
            return ProbeResult {
                modality: modality.to_string(),
                available: false,
                readiness: "probe-failed".to_string(),
                details: vec![format!("probe_error={error}")],
                payload: None,
                source: "probe-command".to_string(),
            };
        }
    };

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        let mut details = vec![exit_detail(&output.status)];
        if !stderr.is_empty() {
            details.push(format!("probe_stderr={stderr}"));
        }
        if let Some(mut result) = parse_probe_output(modality, &stdout) {
            if result.available
                || matches!(result.readiness.as_str(), "native-live" | "native-ready")
            {
                result.available = false;
                result.readiness = "probe-failed".to_string();
            }
            result.details.extend(details);
            return result;
        }
        if !stdout.is_empty() {
            details.push(format!("probe_stdout={stdout}"));
        }
        return ProbeResult {
            modality: modality.to_string(),
            available: false,
            readiness: "probe-failed".to_string(),
            details,
            payload: None,
            source: "probe-command".to_string(),
        };
    }

    if stdout.is_empty() {
        let mut details = vec!["probe_stdout=empty".to_string()];
        if !stderr.is_empty() {
            details.push(format!("probe_stderr={stderr}"));
        }
        return ProbeResult {
            modality: modality.to_string(),
            available: true,
            readiness: "native-live".to_string(),
            details,
            payload: None,
            source: "probe-command".to_string(),
        };
    }

    if let Some(mut result) = parse_probe_output(modality, &stdout) {
        if !stderr.is_empty() {
            result.details.push(format!("probe_stderr={stderr}"));
        }
        return result;
    }

    let mut details = vec!["probe_stdout=raw".to_string()];
    if !stderr.is_empty() {
        details.push(format!("probe_stderr={stderr}"));
    }
    ProbeResult {
        modality: modality.to_string(),
        available: true,
        readiness: "native-live".to_string(),
        details,
        payload: Some(json!({"raw_stdout": stdout})),
        source: "probe-command".to_string(),
    }
}

fn builtin_screen_probe(config: &Config) -> ProbeResult {
    let has_session_bus = std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some();
    let mut details = vec![format!("dbus_session_bus={has_session_bus}")];
    if let Some(command) = native_live_command(config, "screen") {
        let mut live_result = run_probe(config, "screen", command);
        live_result
            .details
            .insert(0, "screen_live_command=true".to_string());
        live_result
            .details
            .insert(1, format!("dbus_session_bus={has_session_bus}"));
        live_result.source = "builtin-screen-live-command".to_string();
        if live_result.available {
            return live_result;
        }
        details.extend(live_result.details);
        details.push(format!("screen_live_readiness={}", live_result.readiness));
    }
    let state_payload = read_json_payload(&config.screencast_state_path);
    if config.screencast_state_path.exists() {
        details.push(format!(
            "screencast_state={}",
            config.screencast_state_path.display()
        ));
    }

    let (available, readiness, payload) = if let Some(payload) = state_payload {
        (true, "native-live", Some(payload))
    } else if config.screen_backend.contains("portal") {
        if has_session_bus {
            (
                false,
                "native-ready",
                Some(json!({"dbus_session_bus": true})),
            )
        } else {
            (false, "session-unavailable", None)
        }
    } else {
        (false, "fallback-stub", None)
    };

    ProbeResult {
        modality: "screen".to_string(),
        available,
        readiness: readiness.to_string(),
        details,
        payload,
        source: "builtin-probe".to_string(),
    }
}

fn builtin_audio_probe(config: &Config) -> ProbeResult {
    let mut details = vec![format!(
        "pipewire_socket={}",
        config.pipewire_socket_path.display()
    )];
    if let Some(command) = native_live_command(config, "audio") {
        let mut live_result = run_probe(config, "audio", command);
        live_result
            .details
            .insert(0, "audio_live_command=true".to_string());
        live_result.details.insert(
            1,
            format!("pipewire_socket={}", config.pipewire_socket_path.display()),
        );
        live_result.source = "builtin-audio-live-command".to_string();
        if live_result.available {
            return live_result;
        }
        details.extend(live_result.details);
        details.push(format!("audio_live_readiness={}", live_result.readiness));
    }

    for (tool, args) in [("wpctl", vec!["status"]), ("pw-cli", vec!["ls", "Node"])] {
        match run_linux_probe_command(tool, &args) {
            ToolProbeOutcome::Success { stdout } => {
                let mut live_details = vec![
                    format!("probe_tool={tool}"),
                    format!("pipewire_socket={}", config.pipewire_socket_path.display()),
                ];
                if config.pipewire_node_path.exists() {
                    live_details.push(format!(
                        "pipewire_node={}",
                        config.pipewire_node_path.display()
                    ));
                }

                let mut payload = serde_json::Map::new();
                payload.insert("probe_tool".to_string(), json!(tool));
                payload.insert(
                    "probe_excerpt".to_string(),
                    json!(clip_probe_output(&stdout)),
                );
                if config.pipewire_socket_path.exists() {
                    payload.insert(
                        "pipewire_socket".to_string(),
                        json!(config.pipewire_socket_path.display().to_string()),
                    );
                }
                if let Some(node) = read_json_payload(&config.pipewire_node_path) {
                    payload.insert("pipewire_node".to_string(), node);
                }

                return ProbeResult {
                    modality: "audio".to_string(),
                    available: true,
                    readiness: "native-live".to_string(),
                    details: live_details,
                    payload: Some(Value::Object(payload)),
                    source: "linux-tool".to_string(),
                };
            }
            ToolProbeOutcome::PermissionDenied(mut tool_details) => {
                details.append(&mut tool_details);
                return ProbeResult {
                    modality: "audio".to_string(),
                    available: false,
                    readiness: "permission-denied".to_string(),
                    details,
                    payload: None,
                    source: "linux-tool".to_string(),
                };
            }
            ToolProbeOutcome::MissingTool(mut tool_details)
            | ToolProbeOutcome::Failed(mut tool_details) => {
                details.append(&mut tool_details);
            }
        }
    }

    let socket_state = inspect_path_state(&config.pipewire_socket_path);
    let mut payload = serde_json::Map::new();
    let node_available = read_json_payload(&config.pipewire_node_path);
    let socket_present = matches!(socket_state, PathProbeState::Present);
    if socket_present {
        payload.insert(
            "pipewire_socket".to_string(),
            json!(config.pipewire_socket_path.display().to_string()),
        );
    }
    if let Some(node) = node_available {
        details.push(format!(
            "pipewire_node={}",
            config.pipewire_node_path.display()
        ));
        payload.insert("pipewire_node".to_string(), node);
    }

    let (available, readiness) = match socket_state {
        PathProbeState::Present => {
            if config.pipewire_node_path.exists() {
                (true, "native-live")
            } else {
                (true, "native-ready")
            }
        }
        PathProbeState::Missing => (false, "dependency-missing"),
        PathProbeState::PermissionDenied => (false, "permission-denied"),
        PathProbeState::Failed(detail) => {
            details.push(detail);
            (false, "probe-failed")
        }
    };

    ProbeResult {
        modality: "audio".to_string(),
        available,
        readiness: readiness.to_string(),
        details,
        payload: (!payload.is_empty()).then_some(Value::Object(payload)),
        source: "builtin-probe".to_string(),
    }
}

fn builtin_input_probe(config: &Config) -> ProbeResult {
    let mut details = vec![format!("input_root={}", config.input_device_root.display())];
    if let Some(command) = native_live_command(config, "input") {
        let mut live_result = run_probe(config, "input", command);
        live_result
            .details
            .insert(0, "input_live_command=true".to_string());
        live_result.details.insert(
            1,
            format!("input_root={}", config.input_device_root.display()),
        );
        live_result.source = "builtin-input-live-command".to_string();
        if live_result.available {
            return live_result;
        }
        details.extend(live_result.details);
        details.push(format!("input_live_readiness={}", live_result.readiness));
    }

    match run_linux_probe_command("libinput", &["list-devices"]) {
        ToolProbeOutcome::Success { stdout } => {
            let devices = parse_libinput_devices(&stdout);
            if !devices.is_empty() {
                return ProbeResult {
                    modality: "input".to_string(),
                    available: true,
                    readiness: "native-live".to_string(),
                    details: vec![
                        "probe_tool=libinput".to_string(),
                        format!("input_root={}", config.input_device_root.display()),
                        format!("device_count={}", devices.len()),
                    ],
                    payload: Some(json!({"probe_tool": "libinput", "input_devices": devices})),
                    source: "linux-tool".to_string(),
                };
            }
            details.push("probe_tool=libinput".to_string());
            details.push("probe_tool_status=empty-device-list".to_string());
        }
        ToolProbeOutcome::PermissionDenied(mut tool_details) => {
            details.append(&mut tool_details);
            return ProbeResult {
                modality: "input".to_string(),
                available: false,
                readiness: "permission-denied".to_string(),
                details,
                payload: None,
                source: "linux-tool".to_string(),
            };
        }
        ToolProbeOutcome::MissingTool(mut tool_details)
        | ToolProbeOutcome::Failed(mut tool_details) => {
            details.append(&mut tool_details);
        }
    }

    let device_state = inspect_matching_entries(&config.input_device_root, |item| {
        item.starts_with("event") || item.starts_with("mouse") || item.starts_with("kbd")
    });
    let (available, readiness, devices) = match device_state {
        EntryProbeState::Entries(devices) => (true, "native-live", Some(devices)),
        EntryProbeState::Missing => (false, "device-missing", None),
        EntryProbeState::PermissionDenied => (false, "permission-denied", None),
        EntryProbeState::Failed(detail) => {
            details.push(detail);
            (false, "probe-failed", None)
        }
    };
    if let Some(devices) = devices.as_ref() {
        details.push(format!("device_count={}", devices.len()));
    }

    ProbeResult {
        modality: "input".to_string(),
        available,
        readiness: readiness.to_string(),
        details,
        payload: devices.map(|items| json!({"input_devices": items})),
        source: "builtin-probe".to_string(),
    }
}

fn builtin_camera_probe(config: &Config) -> ProbeResult {
    let mut details = vec![format!(
        "camera_root={}",
        config.camera_device_root.display()
    )];
    if !config.camera_enabled {
        details.push("camera_enabled=false".to_string());
    }
    if let Some(command) = native_live_command(config, "camera") {
        let mut live_result = run_probe(config, "camera", command);
        live_result
            .details
            .insert(0, "camera_live_command=true".to_string());
        live_result.details.insert(
            1,
            format!("camera_root={}", config.camera_device_root.display()),
        );
        if !config.camera_enabled {
            live_result
                .details
                .insert(2, "camera_enabled=false".to_string());
        }
        live_result.source = "builtin-camera-live-command".to_string();
        if live_result.available {
            return live_result;
        }
        details.extend(live_result.details);
        details.push(format!("camera_live_readiness={}", live_result.readiness));
    }
    match run_linux_probe_command("v4l2-ctl", &["--list-devices"]) {
        ToolProbeOutcome::Success { stdout } => {
            let devices = parse_v4l2_devices(&stdout);
            if !devices.is_empty() {
                return ProbeResult {
                    modality: "camera".to_string(),
                    available: true,
                    readiness: "native-live".to_string(),
                    details: vec![
                        "probe_tool=v4l2-ctl".to_string(),
                        format!("camera_root={}", config.camera_device_root.display()),
                        format!("device_count={}", devices.len()),
                    ],
                    payload: Some(json!({"probe_tool": "v4l2-ctl", "camera_devices": devices})),
                    source: "linux-tool".to_string(),
                };
            }
            details.push("probe_tool=v4l2-ctl".to_string());
            details.push("probe_tool_status=empty-device-list".to_string());
        }
        ToolProbeOutcome::PermissionDenied(mut tool_details) => {
            details.append(&mut tool_details);
            return ProbeResult {
                modality: "camera".to_string(),
                available: false,
                readiness: "permission-denied".to_string(),
                details,
                payload: None,
                source: "linux-tool".to_string(),
            };
        }
        ToolProbeOutcome::MissingTool(mut tool_details)
        | ToolProbeOutcome::Failed(mut tool_details) => {
            details.append(&mut tool_details);
        }
    }

    let device_state =
        inspect_matching_entries(&config.camera_device_root, |item| item.starts_with("video"));
    let (available, readiness, devices) = match device_state {
        EntryProbeState::Entries(devices) => (config.camera_enabled, "native-live", Some(devices)),
        EntryProbeState::Missing => (false, "device-missing", None),
        EntryProbeState::PermissionDenied => (false, "permission-denied", None),
        EntryProbeState::Failed(detail) => {
            details.push(detail);
            (false, "probe-failed", None)
        }
    };
    if let Some(devices) = devices.as_ref() {
        details.push(format!("device_count={}", devices.len()));
    }

    ProbeResult {
        modality: "camera".to_string(),
        available,
        readiness: if !config.camera_enabled {
            "disabled".to_string()
        } else {
            readiness.to_string()
        },
        details,
        payload: devices.map(|items| json!({"camera_devices": items})),
        source: "builtin-probe".to_string(),
    }
}

fn builtin_ui_tree_probe_result(config: &Config) -> ProbeResult {
    let has_at_spi_bus = std::env::var_os("AT_SPI_BUS_ADDRESS").is_some();
    let mut details = vec![format!("at_spi_bus={has_at_spi_bus}")];
    if !config.ui_tree_supported {
        return ProbeResult {
            modality: "ui_tree".to_string(),
            available: false,
            readiness: "unsupported".to_string(),
            details,
            payload: None,
            source: "builtin-probe".to_string(),
        };
    }

    if let Some(command) = config.ui_tree_live_command.as_deref() {
        let mut live_result = run_probe(config, "ui_tree", command);
        live_result
            .details
            .insert(0, "ui_tree_live_command=true".to_string());
        live_result
            .details
            .insert(1, format!("at_spi_bus={has_at_spi_bus}"));
        live_result.source = "builtin-ui-tree-live-command".to_string();
        if live_result.available {
            return live_result;
        }
        details.extend(live_result.details);
        details.push(format!("ui_tree_live_readiness={}", live_result.readiness));
    }

    let state_payload = read_json_payload(&config.ui_tree_state_path);
    if config.ui_tree_state_path.exists() {
        details.push(format!(
            "ui_tree_state={}",
            config.ui_tree_state_path.display()
        ));
    }

    let (available, readiness, payload) = if let Some(payload) = state_payload {
        (true, "native-live", Some(payload))
    } else if has_at_spi_bus {
        (false, "native-ready", Some(json!({"at_spi_bus": true})))
    } else {
        (false, "session-unavailable", None)
    };

    ProbeResult {
        modality: "ui_tree".to_string(),
        available,
        readiness: readiness.to_string(),
        details,
        payload,
        source: "builtin-probe".to_string(),
    }
}

enum ToolProbeOutcome {
    Success { stdout: String },
    MissingTool(Vec<String>),
    PermissionDenied(Vec<String>),
    Failed(Vec<String>),
}

enum PathProbeState {
    Present,
    Missing,
    PermissionDenied,
    Failed(String),
}

enum EntryProbeState {
    Entries(Vec<String>),
    Missing,
    PermissionDenied,
    Failed(String),
}

fn run_linux_probe_command(tool: &str, args: &[&str]) -> ToolProbeOutcome {
    let output = match Command::new(tool).args(args).output() {
        Ok(output) => output,
        Err(error) => {
            return match error.kind() {
                ErrorKind::NotFound => ToolProbeOutcome::MissingTool(vec![
                    format!("probe_tool={tool}"),
                    "probe_tool_status=missing-tool".to_string(),
                ]),
                ErrorKind::PermissionDenied => ToolProbeOutcome::PermissionDenied(vec![
                    format!("probe_tool={tool}"),
                    "probe_tool_status=permission-denied".to_string(),
                    format!("probe_error={error}"),
                ]),
                _ => ToolProbeOutcome::Failed(vec![
                    format!("probe_tool={tool}"),
                    "probe_tool_status=failed".to_string(),
                    format!("probe_error={error}"),
                ]),
            };
        }
    };

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if output.status.success() {
        if stdout.is_empty() {
            return ToolProbeOutcome::Failed(vec![
                format!("probe_tool={tool}"),
                "probe_tool_status=empty-stdout".to_string(),
            ]);
        }
        return ToolProbeOutcome::Success { stdout };
    }

    let mut details = vec![format!("probe_tool={tool}")];
    if is_permission_error(&stderr) || is_permission_error(&stdout) {
        details.push("probe_tool_status=permission-denied".to_string());
        details.push(exit_detail(&output.status));
        if !stderr.is_empty() {
            details.push(format!("probe_stderr={stderr}"));
        }
        if !stdout.is_empty() {
            details.push(format!("probe_stdout={stdout}"));
        }
        return ToolProbeOutcome::PermissionDenied(details);
    }

    details.push("probe_tool_status=failed".to_string());
    details.push(exit_detail(&output.status));
    if !stderr.is_empty() {
        details.push(format!("probe_stderr={stderr}"));
    }
    if !stdout.is_empty() {
        details.push(format!("probe_stdout={stdout}"));
    }
    ToolProbeOutcome::Failed(details)
}

fn inspect_path_state(path: &Path) -> PathProbeState {
    match fs::metadata(path) {
        Ok(_) => PathProbeState::Present,
        Err(error) => match error.kind() {
            ErrorKind::NotFound => PathProbeState::Missing,
            ErrorKind::PermissionDenied => PathProbeState::PermissionDenied,
            _ => PathProbeState::Failed(format!("probe_error={error}")),
        },
    }
}

fn inspect_matching_entries<F>(path: &Path, matcher: F) -> EntryProbeState
where
    F: Fn(&str) -> bool,
{
    if path.is_file() {
        let Some(name) = path.file_name().and_then(|item| item.to_str()) else {
            return EntryProbeState::Missing;
        };
        return if matcher(name) {
            EntryProbeState::Entries(vec![name.to_string()])
        } else {
            EntryProbeState::Missing
        };
    }

    match fs::read_dir(path) {
        Ok(entries) => {
            let mut items = entries
                .filter_map(|entry| entry.ok())
                .map(|entry| entry.file_name().to_string_lossy().to_string())
                .filter(|item| matcher(item))
                .collect::<Vec<_>>();
            items.sort();
            if items.is_empty() {
                EntryProbeState::Missing
            } else {
                EntryProbeState::Entries(items)
            }
        }
        Err(error) => match error.kind() {
            ErrorKind::NotFound => EntryProbeState::Missing,
            ErrorKind::PermissionDenied => EntryProbeState::PermissionDenied,
            _ => EntryProbeState::Failed(format!("probe_error={error}")),
        },
    }
}

fn is_permission_error(value: &str) -> bool {
    let lowercase = value.to_ascii_lowercase();
    lowercase.contains("permission denied")
        || lowercase.contains("not permitted")
        || lowercase.contains("access denied")
}

fn clip_probe_output(output: &str) -> String {
    let mut clipped = output.lines().take(8).collect::<Vec<_>>().join("\n");
    if clipped.chars().count() > 512 {
        clipped = clipped.chars().take(512).collect();
    }
    clipped
}

fn parse_libinput_devices(stdout: &str) -> Vec<String> {
    stdout
        .lines()
        .filter_map(|line| line.trim().strip_prefix("Device:"))
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn parse_v4l2_devices(stdout: &str) -> Vec<String> {
    stdout
        .lines()
        .map(str::trim_end)
        .filter(|line| !line.trim().is_empty())
        .filter(|line| !line.starts_with('\t') && !line.starts_with('/'))
        .map(|line| line.trim().trim_end_matches(':').to_string())
        .filter(|item| !item.is_empty())
        .collect()
}

fn read_json_payload(path: &std::path::Path) -> Option<Value> {
    let content = fs::read_to_string(path).ok()?;
    serde_json::from_str::<Value>(&content).ok()
}

fn configure_probe_env(shell: &mut Command, config: &Config, modality: &str) {
    shell.env("AIOS_DEVICED_PROBE", "1");
    shell.env("AIOS_DEVICED_MODALITY", modality);
    shell.env("AIOS_DEVICED_PROBE_MODALITY", modality);
    shell.env("AIOS_DEVICED_SERVICE_ID", &config.service_id);
    shell.env(
        "AIOS_DEVICED_DEFAULT_RESOLUTION",
        &config.default_resolution,
    );
    shell.env(
        "AIOS_DEVICED_UI_TREE_SUPPORTED",
        config.ui_tree_supported.to_string(),
    );
    shell.env("AIOS_DEVICED_SCREEN_BACKEND", &config.screen_backend);
    shell.env("AIOS_DEVICED_AUDIO_BACKEND", &config.audio_backend);
    shell.env("AIOS_DEVICED_INPUT_BACKEND", &config.input_backend);
    shell.env("AIOS_DEVICED_CAMERA_BACKEND", &config.camera_backend);
    shell.env(
        "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH",
        config.pipewire_socket_path.display().to_string(),
    );
    shell.env(
        "AIOS_DEVICED_INPUT_DEVICE_ROOT",
        config.input_device_root.display().to_string(),
    );
    shell.env(
        "AIOS_DEVICED_CAMERA_DEVICE_ROOT",
        config.camera_device_root.display().to_string(),
    );
    shell.env(
        "AIOS_DEVICED_SCREENCAST_STATE_PATH",
        config.screencast_state_path.display().to_string(),
    );
    shell.env(
        "AIOS_DEVICED_PIPEWIRE_NODE_PATH",
        config.pipewire_node_path.display().to_string(),
    );
    shell.env(
        "AIOS_DEVICED_UI_TREE_STATE_PATH",
        config.ui_tree_state_path.display().to_string(),
    );
}

fn parse_probe_output(modality: &str, stdout: &str) -> Option<ProbeResult> {
    let value = serde_json::from_str::<Value>(stdout).ok()?;
    if let Some(object) = value.as_object() {
        let is_envelope = object.contains_key("available")
            || object.contains_key("readiness")
            || object.contains_key("details")
            || object.contains_key("payload")
            || object.contains_key("source");
        if is_envelope {
            let available = object
                .get("available")
                .and_then(Value::as_bool)
                .unwrap_or(true);
            let readiness = object
                .get("readiness")
                .and_then(Value::as_str)
                .map(ToString::to_string)
                .unwrap_or_else(|| {
                    if available {
                        "native-live".to_string()
                    } else {
                        "probe-failed".to_string()
                    }
                });
            let details = object
                .get("details")
                .map(value_to_details)
                .unwrap_or_default();
            let payload = object.get("payload").cloned();
            let source = object
                .get("source")
                .and_then(Value::as_str)
                .unwrap_or("probe-command")
                .to_string();
            return Some(ProbeResult {
                modality: modality.to_string(),
                available,
                readiness,
                details,
                payload,
                source,
            });
        }
    }

    Some(ProbeResult {
        modality: modality.to_string(),
        available: true,
        readiness: "native-live".to_string(),
        details: vec!["probe_payload=json".to_string()],
        payload: Some(value),
        source: "probe-command".to_string(),
    })
}

fn value_to_details(value: &Value) -> Vec<String> {
    match value {
        Value::Array(items) => items.iter().map(detail_item_to_string).collect(),
        Value::String(item) => vec![item.clone()],
        _ => vec![detail_item_to_string(value)],
    }
}

fn detail_item_to_string(value: &Value) -> String {
    match value {
        Value::String(item) => item.clone(),
        _ => value.to_string(),
    }
}

fn exit_detail(status: &std::process::ExitStatus) -> String {
    match status.code() {
        Some(code) => format!("probe_exit_code={code}"),
        None => "probe_exit=signal".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_libinput_devices_extracts_named_devices() {
        let parsed = parse_libinput_devices(
            "Device: Test Keyboard\nKernel: /dev/input/event0\n\nDevice: Test Mouse\nKernel: /dev/input/event1\n",
        );

        assert_eq!(
            parsed,
            vec!["Test Keyboard".to_string(), "Test Mouse".to_string()]
        );
    }

    #[test]
    fn parse_v4l2_devices_extracts_device_blocks() {
        let parsed = parse_v4l2_devices(
            "HD Webcam C270 (usb-0000:00:14.0-5):\n\t/dev/video0\n\nVirtual Camera:\n\t/dev/video1\n",
        );

        assert_eq!(
            parsed,
            vec![
                "HD Webcam C270 (usb-0000:00:14.0-5)".to_string(),
                "Virtual Camera".to_string()
            ]
        );
    }
}
