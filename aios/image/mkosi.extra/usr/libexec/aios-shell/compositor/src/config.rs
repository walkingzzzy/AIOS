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
    pub placeholder_surfaces: Vec<String>,
    pub panel_bridge_socket: Option<String>,
    pub panel_snapshot_path: Option<String>,
    pub panel_snapshot_command: Option<String>,
    pub panel_action_command: Option<String>,
    pub panel_action_log_path: Option<String>,
    pub panel_snapshot_refresh_ticks: u32,
    pub drm_device_path: Option<String>,
    pub drm_disable_connectors: bool,
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
            placeholder_surfaces: vec![
                "launcher".to_string(),
                "task-surface".to_string(),
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
            drm_disable_connectors: false,
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
                    "socket_name" => {
                        config.socket_name = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
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
                            value.parse().unwrap_or(config.keyboard_repeat_delay_ms);
                    }
                    "keyboard_repeat_rate" => {
                        config.keyboard_repeat_rate =
                            value.parse().unwrap_or(config.keyboard_repeat_rate);
                    }
                    "placeholder_surfaces" => {
                        config.placeholder_surfaces = value
                            .split(',')
                            .map(str::trim)
                            .filter(|item| !item.is_empty())
                            .map(ToOwned::to_owned)
                            .collect();
                    }
                    "panel_bridge_socket" => {
                        config.panel_bridge_socket = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "panel_snapshot_path" => {
                        config.panel_snapshot_path = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "panel_snapshot_command" => {
                        config.panel_snapshot_command = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "panel_action_command" => {
                        config.panel_action_command = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "panel_action_log_path" => {
                        config.panel_action_log_path = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "panel_snapshot_refresh_ticks" => {
                        config.panel_snapshot_refresh_ticks =
                            value.parse().unwrap_or(config.panel_snapshot_refresh_ticks);
                    }
                    "drm_device_path" => {
                        config.drm_device_path = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "drm_disable_connectors" => {
                        config.drm_disable_connectors =
                            parse_bool(value, config.drm_disable_connectors);
                    }
                    "runtime_lock_path" => {
                        config.runtime_lock_path = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "runtime_ready_path" => {
                        config.runtime_ready_path = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "runtime_state_path" => {
                        config.runtime_state_path = if value.is_empty() {
                            None
                        } else {
                            Some(value.to_string())
                        };
                    }
                    "runtime_state_refresh_ticks" => {
                        config.runtime_state_refresh_ticks =
                            value.parse().unwrap_or(config.runtime_state_refresh_ticks);
                    }
                    "tick_ms" => {
                        config.tick_ms = value.parse().unwrap_or(config.tick_ms);
                    }
                    _ => {}
                }
            }
        }

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
            config.socket_name = if value.is_empty() { None } else { Some(value) };
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
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET") {
            config.panel_bridge_socket = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_PATH") {
            config.panel_snapshot_path = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_COMMAND") {
            config.panel_snapshot_command = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_ACTION_COMMAND") {
            config.panel_action_command = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH") {
            config.panel_action_log_path = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_REFRESH_TICKS") {
            if let Ok(parsed) = value.parse::<u32>() {
                config.panel_snapshot_refresh_ticks = parsed;
            }
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_DEVICE_PATH") {
            config.drm_device_path = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_DRM_DISABLE_CONNECTORS") {
            config.drm_disable_connectors = parse_bool(&value, config.drm_disable_connectors);
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_LOCK_PATH") {
            config.runtime_lock_path = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_READY_PATH") {
            config.runtime_ready_path = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_PATH") {
            config.runtime_state_path = if value.is_empty() { None } else { Some(value) };
        }
        if let Ok(value) = env::var("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_REFRESH_TICKS") {
            if let Ok(parsed) = value.parse::<u32>() {
                config.runtime_state_refresh_ticks = parsed;
            }
        }

        Ok(config)
    }
}

fn parse_bool(value: &str, fallback: bool) -> bool {
    match value.trim().to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => true,
        "0" | "false" | "no" | "off" => false,
        _ => fallback,
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
            "service_id = smoke\nseat_name = seat-smoke\ncompositor_backend = drm-kms\npointer_enabled = false\nkeyboard_enabled = true\ntouch_enabled = true\nkeyboard_layout = de\nkeyboard_repeat_delay_ms = 180\nkeyboard_repeat_rate = 30\nsocket_name = wayland-smoke\nplaceholder_surfaces = launcher, approval-panel\npanel_bridge_socket = /tmp/panel-bridge.sock\npanel_snapshot_path = /tmp/shell-snapshot.json\npanel_snapshot_command = python3 /tmp/shell-snapshot.py --json\npanel_action_command = python3 /tmp/panel-action.py\npanel_action_log_path = /tmp/panel-action-events.jsonl\npanel_snapshot_refresh_ticks = 8\ndrm_device_path = /dev/dri/card1\ndrm_disable_connectors = true\nruntime_lock_path = /tmp/aios-shell.lock\nruntime_ready_path = /tmp/aios-shell-ready.json\nruntime_state_path = /tmp/aios-shell-state.json\nruntime_state_refresh_ticks = 3\ntick_ms = 5\n",
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
            config.placeholder_surfaces,
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
        assert!(config.drm_disable_connectors);
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
