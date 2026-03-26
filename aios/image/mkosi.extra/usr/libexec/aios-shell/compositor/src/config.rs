use crate::surfaces::normalize_workspace_toplevel_mode;
use std::env;
use std::fs;
use std::io;
use std::path::Path;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Config {
    pub service_id: String,
    pub desktop_host: String,
    pub session_backend: String,
    pub compositor_backend: String,
    pub socket_name: Option<String>,
    pub seat_name: String,
    pub pointer_enabled: bool,
    pub keyboard_enabled: bool,
    pub touch_enabled: bool,
    pub keyboard_layout: String,
    pub keyboard_repeat_delay_ms: i32,
    pub keyboard_repeat_rate: i32,
    pub panel_slots: Vec<String>,
    pub panel_bridge_socket: Option<String>,
    pub panel_snapshot_path: Option<String>,
    pub panel_snapshot_command: Option<String>,
    pub panel_action_command: Option<String>,
    pub panel_action_log_path: Option<String>,
    pub panel_snapshot_refresh_ticks: u32,
    pub drm_device_path: Option<String>,
    pub drm_preferred_connector: Option<String>,
    pub drm_output_width: Option<i32>,
    pub drm_output_height: Option<i32>,
    pub drm_output_refresh_millihz: Option<i32>,
    pub drm_disable_connectors: bool,
    pub workspace_toplevel_mode: String,
    pub workspace_count: u32,
    pub default_workspace_index: u32,
    pub output_layout_mode: String,
    pub virtual_outputs: Vec<String>,
    pub window_state_path: Option<String>,
    pub runtime_lock_path: Option<String>,
    pub runtime_ready_path: Option<String>,
    pub runtime_state_path: Option<String>,
    pub runtime_state_refresh_ticks: u32,
    pub tick_ms: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            service_id: "aios-shell-compositor".to_string(),
            desktop_host: "gtk".to_string(),
            session_backend: "smithay-wayland-frontend".to_string(),
            compositor_backend: "winit".to_string(),
            socket_name: None,
            seat_name: "aios-shell".to_string(),
            pointer_enabled: true,
            keyboard_enabled: true,
            touch_enabled: false,
            keyboard_layout: "us".to_string(),
            keyboard_repeat_delay_ms: 200,
            keyboard_repeat_rate: 25,
            panel_slots: vec![
                "launcher".to_string(),
                "task-surface".to_string(),
                "system-assistant".to_string(),
                "ai-center".to_string(),
                "provider-settings".to_string(),
                "privacy-memory".to_string(),
                "model-library".to_string(),
                "approval-panel".to_string(),
                "portal-chooser".to_string(),
                "notification-center".to_string(),
                "recovery-surface".to_string(),
                "capture-indicators".to_string(),
                "remote-governance".to_string(),
                "device-backend-status".to_string(),
            ],
            panel_bridge_socket: None,
            panel_snapshot_path: None,
            panel_snapshot_command: None,
            panel_action_command: None,
            panel_action_log_path: None,
            panel_snapshot_refresh_ticks: 10,
            drm_device_path: None,
            drm_preferred_connector: None,
            drm_output_width: None,
            drm_output_height: None,
            drm_output_refresh_millihz: None,
            drm_disable_connectors: false,
            workspace_toplevel_mode: "maximized".to_string(),
            workspace_count: 4,
            default_workspace_index: 0,
            output_layout_mode: "horizontal".to_string(),
            virtual_outputs: Vec::new(),
            window_state_path: None,
            runtime_lock_path: None,
            runtime_ready_path: None,
            runtime_state_path: None,
            runtime_state_refresh_ticks: 1,
            tick_ms: 25,
        }
    }
}

impl Config {
    pub fn load(path: Option<&Path>) -> io::Result<Self> {
        let mut config = Self::default();

        if let Some(path) = path {
            let contents = fs::read_to_string(path)?;
            for line in contents.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }
                let Some((raw_key, raw_value)) = line.split_once('=') else {
                    continue;
                };
                let key = raw_key.trim();
                let value = raw_value.trim();
                match key {
                    "service_id" => config.service_id = value.to_string(),
                    "desktop_host" => config.desktop_host = value.to_string(),
                    "session_backend" => config.session_backend = value.to_string(),
                    "compositor_backend" => config.compositor_backend = value.to_string(),
                    "seat_name" => config.seat_name = value.to_string(),
                    "socket_name" => config.socket_name = parse_optional_string(value),
                    "pointer_enabled" => {
                        config.pointer_enabled = parse_bool(value, config.pointer_enabled)
                    }
                    "keyboard_enabled" => {
                        config.keyboard_enabled = parse_bool(value, config.keyboard_enabled)
                    }
                    "touch_enabled" => {
                        config.touch_enabled = parse_bool(value, config.touch_enabled)
                    }
                    "keyboard_layout" => config.keyboard_layout = value.to_string(),
                    "keyboard_repeat_delay_ms" => {
                        config.keyboard_repeat_delay_ms =
                            value.parse().unwrap_or(config.keyboard_repeat_delay_ms)
                    }
                    "keyboard_repeat_rate" => {
                        config.keyboard_repeat_rate =
                            value.parse().unwrap_or(config.keyboard_repeat_rate)
                    }
                    "panel_slots" | "placeholder_surfaces" => {
                        config.panel_slots = parse_list(value)
                    }
                    "panel_bridge_socket" => {
                        config.panel_bridge_socket = parse_optional_string(value)
                    }
                    "panel_snapshot_path" => {
                        config.panel_snapshot_path = parse_optional_string(value)
                    }
                    "panel_snapshot_command" => {
                        config.panel_snapshot_command = parse_optional_string(value)
                    }
                    "panel_action_command" => {
                        config.panel_action_command = parse_optional_string(value)
                    }
                    "panel_action_log_path" => {
                        config.panel_action_log_path = parse_optional_string(value)
                    }
                    "panel_snapshot_refresh_ticks" => {
                        config.panel_snapshot_refresh_ticks =
                            value.parse().unwrap_or(config.panel_snapshot_refresh_ticks)
                    }
                    "drm_device_path" => config.drm_device_path = parse_optional_string(value),
                    "drm_preferred_connector" => {
                        config.drm_preferred_connector = parse_optional_string(value)
                    }
                    "drm_output_width" => config.drm_output_width = value.parse::<i32>().ok(),
                    "drm_output_height" => config.drm_output_height = value.parse::<i32>().ok(),
                    "drm_output_refresh_millihz" => {
                        config.drm_output_refresh_millihz = value.parse::<i32>().ok()
                    }
                    "drm_disable_connectors" => {
                        config.drm_disable_connectors =
                            parse_bool(value, config.drm_disable_connectors)
                    }
                    "workspace_toplevel_mode" => {
                        config.workspace_toplevel_mode =
                            normalize_workspace_toplevel_mode(value).to_string()
                    }
                    "workspace_count" => {
                        config.workspace_count = value.parse().unwrap_or(config.workspace_count)
                    }
                    "default_workspace_index" => {
                        config.default_workspace_index =
                            value.parse().unwrap_or(config.default_workspace_index)
                    }
                    "output_layout_mode" => {
                        config.output_layout_mode = normalize_output_layout_mode(value).to_string()
                    }
                    "virtual_outputs" => config.virtual_outputs = parse_list(value),
                    "window_state_path" => config.window_state_path = parse_optional_string(value),
                    "runtime_lock_path" => config.runtime_lock_path = parse_optional_string(value),
                    "runtime_ready_path" => {
                        config.runtime_ready_path = parse_optional_string(value)
                    }
                    "runtime_state_path" => {
                        config.runtime_state_path = parse_optional_string(value)
                    }
                    "runtime_state_refresh_ticks" => {
                        config.runtime_state_refresh_ticks =
                            value.parse().unwrap_or(config.runtime_state_refresh_ticks)
                    }
                    "tick_ms" => config.tick_ms = value.parse().unwrap_or(config.tick_ms),
                    _ => {}
                }
            }
        }

        apply_env_overrides(&mut config);
        config.workspace_count = config.workspace_count.max(1);
        config.default_workspace_index = config
            .default_workspace_index
            .min(config.workspace_count.saturating_sub(1));
        Ok(config)
    }
}

fn apply_env_overrides(config: &mut Config) {
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_SERVICE_ID") {
        config.service_id = value;
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DESKTOP_HOST") {
        config.desktop_host = value;
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_SESSION_BACKEND") {
        config.session_backend = value;
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_BACKEND") {
        config.compositor_backend = value;
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_SEAT_NAME") {
        config.seat_name = value;
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_SOCKET_NAME") {
        config.socket_name = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_POINTER_ENABLED") {
        config.pointer_enabled = parse_bool(&value, config.pointer_enabled);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_KEYBOARD_ENABLED") {
        config.keyboard_enabled = parse_bool(&value, config.keyboard_enabled);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_TOUCH_ENABLED") {
        config.touch_enabled = parse_bool(&value, config.touch_enabled);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_KEYBOARD_LAYOUT") {
        config.keyboard_layout = value;
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_KEYBOARD_REPEAT_DELAY_MS") {
        if let Ok(parsed) = value.parse::<i32>() {
            config.keyboard_repeat_delay_ms = parsed;
        }
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_KEYBOARD_REPEAT_RATE") {
        if let Ok(parsed) = value.parse::<i32>() {
            config.keyboard_repeat_rate = parsed;
        }
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_TICK_MS") {
        if let Ok(parsed) = value.parse::<u64>() {
            config.tick_ms = parsed;
        }
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_SLOTS") {
        config.panel_slots = parse_list(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET") {
        config.panel_bridge_socket = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_PATH") {
        config.panel_snapshot_path = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_COMMAND") {
        config.panel_snapshot_command = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_ACTION_COMMAND") {
        config.panel_action_command = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH") {
        config.panel_action_log_path = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_REFRESH_TICKS") {
        if let Ok(parsed) = value.parse::<u32>() {
            config.panel_snapshot_refresh_ticks = parsed;
        }
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_DEVICE_PATH") {
        config.drm_device_path = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_PREFERRED_CONNECTOR") {
        config.drm_preferred_connector = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_OUTPUT_WIDTH") {
        config.drm_output_width = value.parse::<i32>().ok();
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_OUTPUT_HEIGHT") {
        config.drm_output_height = value.parse::<i32>().ok();
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_OUTPUT_REFRESH_MILLIHZ") {
        config.drm_output_refresh_millihz = value.parse::<i32>().ok();
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_DISABLE_CONNECTORS") {
        config.drm_disable_connectors = parse_bool(&value, config.drm_disable_connectors);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_WORKSPACE_TOPLEVEL_MODE") {
        config.workspace_toplevel_mode = normalize_workspace_toplevel_mode(&value).to_string();
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_WORKSPACE_COUNT") {
        if let Ok(parsed) = value.parse::<u32>() {
            config.workspace_count = parsed;
        }
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DEFAULT_WORKSPACE_INDEX") {
        if let Ok(parsed) = value.parse::<u32>() {
            config.default_workspace_index = parsed;
        }
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_OUTPUT_LAYOUT_MODE") {
        config.output_layout_mode = normalize_output_layout_mode(&value).to_string();
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_VIRTUAL_OUTPUTS") {
        config.virtual_outputs = parse_list(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_WINDOW_STATE_PATH") {
        config.window_state_path = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_LOCK_PATH") {
        config.runtime_lock_path = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_READY_PATH") {
        config.runtime_ready_path = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_PATH") {
        config.runtime_state_path = parse_optional_string(&value);
    }
    if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_REFRESH_TICKS") {
        if let Ok(parsed) = value.parse::<u32>() {
            config.runtime_state_refresh_ticks = parsed;
        }
    }
}

fn parse_bool(value: &str, fallback: bool) -> bool {
    match value.trim().to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => true,
        "0" | "false" | "no" | "off" => false,
        _ => fallback,
    }
}

fn parse_optional_string(value: &str) -> Option<String> {
    if value.trim().is_empty() {
        None
    } else {
        Some(value.trim().to_string())
    }
}

fn parse_list(value: &str) -> Vec<String> {
    value
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn normalize_output_layout_mode(value: &str) -> &'static str {
    match value.trim().to_ascii_lowercase().as_str() {
        "vertical" | "stacked" => "vertical",
        "mirrored" | "mirror" => "mirrored",
        _ => "horizontal",
    }
}

#[cfg(test)]
mod tests {
    use super::Config;
    use std::fs;

    #[test]
    fn loads_config_file() {
        let dir = std::env::temp_dir().join(format!(
            "aios-shell-compositor-config-{}",
            std::process::id()
        ));
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("config.conf");
        fs::write(
            &path,
            "service_id = smoke\nseat_name = seat-smoke\ncompositor_backend = drm-kms\npointer_enabled = false\nkeyboard_enabled = true\ntouch_enabled = true\nkeyboard_layout = de\nkeyboard_repeat_delay_ms = 180\nkeyboard_repeat_rate = 30\nsocket_name = wayland-smoke\npanel_slots = launcher, approval-panel\npanel_bridge_socket = /tmp/panel-bridge.sock\npanel_snapshot_path = /tmp/shell-snapshot.json\npanel_snapshot_command = python3 /tmp/shell-snapshot.py --json\npanel_action_command = python3 /tmp/panel-action.py\npanel_action_log_path = /tmp/panel-action-events.jsonl\npanel_snapshot_refresh_ticks = 8\ndrm_device_path = /dev/dri/card1\ndrm_preferred_connector = HDMI-A-1\ndrm_output_width = 1920\ndrm_output_height = 1080\ndrm_output_refresh_millihz = 60000\ndrm_disable_connectors = true\nworkspace_toplevel_mode = fullscreen\nworkspace_count = 6\ndefault_workspace_index = 2\noutput_layout_mode = vertical\nvirtual_outputs = left-display,right-display\nwindow_state_path = /tmp/aios-shell-windows.json\nruntime_lock_path = /tmp/aios-shell.lock\nruntime_ready_path = /tmp/aios-shell-ready.json\nruntime_state_path = /tmp/aios-shell-state.json\nruntime_state_refresh_ticks = 3\ntick_ms = 5\n",
        )
        .unwrap();

        let config = Config::load(Some(&path)).unwrap();
        assert_eq!(config.service_id, "smoke");
        assert_eq!(config.seat_name, "seat-smoke");
        assert_eq!(config.compositor_backend, "drm-kms");
        assert!(!config.pointer_enabled);
        assert!(config.keyboard_enabled);
        assert!(config.touch_enabled);
        assert_eq!(config.keyboard_layout, "de");
        assert_eq!(config.keyboard_repeat_delay_ms, 180);
        assert_eq!(config.keyboard_repeat_rate, 30);
        assert_eq!(config.socket_name, Some("wayland-smoke".to_string()));
        assert_eq!(
            config.panel_slots,
            vec!["launcher".to_string(), "approval-panel".to_string()]
        );
        assert_eq!(
            config.panel_bridge_socket,
            Some("/tmp/panel-bridge.sock".to_string())
        );
        assert_eq!(
            config.panel_snapshot_path,
            Some("/tmp/shell-snapshot.json".to_string())
        );
        assert_eq!(
            config.panel_snapshot_command,
            Some("python3 /tmp/shell-snapshot.py --json".to_string())
        );
        assert_eq!(
            config.panel_action_command,
            Some("python3 /tmp/panel-action.py".to_string())
        );
        assert_eq!(
            config.panel_action_log_path,
            Some("/tmp/panel-action-events.jsonl".to_string())
        );
        assert_eq!(config.panel_snapshot_refresh_ticks, 8);
        assert_eq!(config.drm_device_path, Some("/dev/dri/card1".to_string()));
        assert_eq!(config.drm_preferred_connector, Some("HDMI-A-1".to_string()));
        assert_eq!(config.drm_output_width, Some(1920));
        assert_eq!(config.drm_output_height, Some(1080));
        assert_eq!(config.drm_output_refresh_millihz, Some(60000));
        assert!(config.drm_disable_connectors);
        assert_eq!(config.workspace_toplevel_mode, "fullscreen");
        assert_eq!(config.workspace_count, 6);
        assert_eq!(config.default_workspace_index, 2);
        assert_eq!(config.output_layout_mode, "vertical");
        assert_eq!(
            config.virtual_outputs,
            vec!["left-display".to_string(), "right-display".to_string()]
        );
        assert_eq!(
            config.window_state_path,
            Some("/tmp/aios-shell-windows.json".to_string())
        );
        assert_eq!(
            config.runtime_lock_path,
            Some("/tmp/aios-shell.lock".to_string())
        );
        assert_eq!(
            config.runtime_ready_path,
            Some("/tmp/aios-shell-ready.json".to_string())
        );
        assert_eq!(
            config.runtime_state_path,
            Some("/tmp/aios-shell-state.json".to_string())
        );
        assert_eq!(config.runtime_state_refresh_ticks, 3);
        assert_eq!(config.tick_ms, 5);

        fs::remove_file(path).unwrap();
        fs::remove_dir_all(dir).unwrap();
    }
}
