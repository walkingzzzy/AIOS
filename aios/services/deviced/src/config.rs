use std::path::PathBuf;

use aios_core::ServicePaths;

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub paths: ServicePaths,
    pub capture_state_path: PathBuf,
    pub observability_log_path: PathBuf,
    pub indicator_state_path: PathBuf,
    pub backend_state_path: PathBuf,
    pub backend_evidence_dir: PathBuf,
    pub continuous_capture_state_path: PathBuf,
    pub policy_socket_path: PathBuf,
    pub approval_rpc_timeout_ms: u64,
    pub screen_backend: String,
    pub audio_backend: String,
    pub input_backend: String,
    pub camera_backend: String,
    pub screen_enabled: bool,
    pub audio_enabled: bool,
    pub input_enabled: bool,
    pub camera_enabled: bool,
    pub ui_tree_supported: bool,
    pub pipewire_socket_path: PathBuf,
    pub input_device_root: PathBuf,
    pub camera_device_root: PathBuf,
    pub screencast_state_path: PathBuf,
    pub pipewire_node_path: PathBuf,
    pub ui_tree_state_path: PathBuf,
    pub default_resolution: String,
    pub approval_mode: String,
    pub approved_sessions: Vec<String>,
    pub approved_tasks: Vec<String>,
    pub screen_capture_command: Option<String>,
    pub audio_capture_command: Option<String>,
    pub input_capture_command: Option<String>,
    pub camera_capture_command: Option<String>,
    pub ui_tree_command: Option<String>,
    pub screen_probe_command: Option<String>,
    pub audio_probe_command: Option<String>,
    pub input_probe_command: Option<String>,
    pub camera_probe_command: Option<String>,
    pub ui_tree_probe_command: Option<String>,
    pub screen_live_command: Option<String>,
    pub audio_live_command: Option<String>,
    pub input_live_command: Option<String>,
    pub camera_live_command: Option<String>,
    pub ui_tree_live_command: Option<String>,
    pub continuous_capture_interval_ms: u64,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("deviced");
        paths.ensure_base_dirs().await?;

        let capture_state_path = std::env::var_os("AIOS_DEVICED_CAPTURE_STATE_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("captures.json"));
        let observability_log_path = std::env::var_os("AIOS_DEVICED_OBSERVABILITY_LOG")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("observability.jsonl"));
        let indicator_state_path = std::env::var_os("AIOS_DEVICED_INDICATOR_STATE_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("indicator-state.json"));
        let backend_state_path = std::env::var_os("AIOS_DEVICED_BACKEND_STATE_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("backend-state.json"));
        let backend_evidence_dir = std::env::var_os("AIOS_DEVICED_BACKEND_EVIDENCE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("backend-evidence"));
        let continuous_capture_state_path =
            std::env::var_os("AIOS_DEVICED_CONTINUOUS_CAPTURE_STATE_PATH")
                .map(PathBuf::from)
                .unwrap_or_else(|| paths.state_dir.join("continuous-captures.json"));
        let policy_socket_path = std::env::var_os("AIOS_DEVICED_POLICY_SOCKET_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| ServicePaths::from_service_name("policyd").socket_path);

        let pipewire_socket_path = std::env::var_os("AIOS_DEVICED_PIPEWIRE_SOCKET_PATH")
            .map(PathBuf::from)
            .or_else(|| {
                std::env::var_os("XDG_RUNTIME_DIR")
                    .map(|value| PathBuf::from(value).join("pipewire-0"))
            })
            .unwrap_or_else(|| paths.runtime_dir.join("pipewire-0"));
        let input_device_root = std::env::var_os("AIOS_DEVICED_INPUT_DEVICE_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/dev/input"));
        let camera_device_root = std::env::var_os("AIOS_DEVICED_CAMERA_DEVICE_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/dev"));
        let screencast_state_path = std::env::var_os("AIOS_DEVICED_SCREENCAST_STATE_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("screencast-state.json"));
        let pipewire_node_path = std::env::var_os("AIOS_DEVICED_PIPEWIRE_NODE_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("pipewire-node.json"));
        let ui_tree_state_path = std::env::var_os("AIOS_DEVICED_UI_TREE_STATE_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("ui-tree-state.json"));

        Ok(Self {
            service_id: "aios-deviced".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            paths,
            capture_state_path,
            observability_log_path,
            indicator_state_path,
            backend_state_path,
            backend_evidence_dir,
            continuous_capture_state_path,
            policy_socket_path,
            approval_rpc_timeout_ms: env_u64("AIOS_DEVICED_APPROVAL_RPC_TIMEOUT_MS", 1_500),
            screen_backend: std::env::var("AIOS_DEVICED_SCREEN_BACKEND")
                .unwrap_or_else(|_| "screen-capture-portal".to_string()),
            audio_backend: std::env::var("AIOS_DEVICED_AUDIO_BACKEND")
                .unwrap_or_else(|_| "pipewire".to_string()),
            input_backend: std::env::var("AIOS_DEVICED_INPUT_BACKEND")
                .unwrap_or_else(|_| "libinput".to_string()),
            camera_backend: std::env::var("AIOS_DEVICED_CAMERA_BACKEND")
                .unwrap_or_else(|_| "pipewire-camera".to_string()),
            screen_enabled: env_flag("AIOS_DEVICED_SCREEN_ENABLED", true),
            audio_enabled: env_flag("AIOS_DEVICED_AUDIO_ENABLED", true),
            input_enabled: env_flag("AIOS_DEVICED_INPUT_ENABLED", true),
            camera_enabled: env_flag("AIOS_DEVICED_CAMERA_ENABLED", false),
            ui_tree_supported: env_flag("AIOS_DEVICED_UI_TREE_SUPPORTED", false),
            pipewire_socket_path,
            input_device_root,
            camera_device_root,
            screencast_state_path,
            pipewire_node_path,
            ui_tree_state_path,
            default_resolution: std::env::var("AIOS_DEVICED_DEFAULT_RESOLUTION")
                .unwrap_or_else(|_| "1920x1080".to_string()),
            approval_mode: std::env::var("AIOS_DEVICED_APPROVAL_MODE")
                .unwrap_or_else(|_| "metadata-only".to_string()),
            approved_sessions: env_list("AIOS_DEVICED_APPROVED_SESSION_IDS"),
            approved_tasks: env_list("AIOS_DEVICED_APPROVED_TASK_IDS"),
            screen_capture_command: std::env::var("AIOS_DEVICED_SCREEN_CAPTURE_COMMAND").ok(),
            audio_capture_command: std::env::var("AIOS_DEVICED_AUDIO_CAPTURE_COMMAND").ok(),
            input_capture_command: std::env::var("AIOS_DEVICED_INPUT_CAPTURE_COMMAND").ok(),
            camera_capture_command: std::env::var("AIOS_DEVICED_CAMERA_CAPTURE_COMMAND").ok(),
            ui_tree_command: std::env::var("AIOS_DEVICED_UI_TREE_COMMAND").ok(),
            screen_probe_command: std::env::var("AIOS_DEVICED_SCREEN_PROBE_COMMAND").ok(),
            audio_probe_command: std::env::var("AIOS_DEVICED_AUDIO_PROBE_COMMAND").ok(),
            input_probe_command: std::env::var("AIOS_DEVICED_INPUT_PROBE_COMMAND").ok(),
            camera_probe_command: std::env::var("AIOS_DEVICED_CAMERA_PROBE_COMMAND").ok(),
            ui_tree_probe_command: std::env::var("AIOS_DEVICED_UI_TREE_PROBE_COMMAND").ok(),
            screen_live_command: env_command_or_default(
                "AIOS_DEVICED_SCREEN_LIVE_COMMAND",
                "screen_portal_live.py",
            ),
            audio_live_command: env_command_or_default(
                "AIOS_DEVICED_AUDIO_LIVE_COMMAND",
                "pipewire_audio_live.py",
            ),
            input_live_command: env_command_or_default(
                "AIOS_DEVICED_INPUT_LIVE_COMMAND",
                "libinput_input_live.py",
            ),
            camera_live_command: env_command_or_default(
                "AIOS_DEVICED_CAMERA_LIVE_COMMAND",
                "camera_v4l_live.py",
            ),
            ui_tree_live_command: env_command_or_default(
                "AIOS_DEVICED_UI_TREE_LIVE_COMMAND",
                "ui_tree_atspi_snapshot.py",
            ),
            continuous_capture_interval_ms: env_u64(
                "AIOS_DEVICED_CONTINUOUS_CAPTURE_INTERVAL_MS",
                500,
            ),
        })
    }
}

fn env_flag(name: &str, default: bool) -> bool {
    std::env::var(name)
        .ok()
        .map(|value| matches!(value.as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(default)
}

fn env_u64(name: &str, default: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(default)
}

fn env_list(name: &str) -> Vec<String> {
    std::env::var(name)
        .ok()
        .map(|value| {
            value
                .split(',')
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(ToOwned::to_owned)
                .collect()
        })
        .unwrap_or_default()
}

fn env_command_or_default(name: &str, helper_script: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .or_else(|| default_helper_command(helper_script))
}

fn default_helper_command(helper_script: &str) -> Option<String> {
    let helper_path = helper_script_path(helper_script)?;
    let python = std::env::var("AIOS_DEVICED_HELPER_PYTHON")
        .unwrap_or_else(|_| "/usr/bin/python3".to_string());
    Some(format!(
        "{} {}",
        shell_escape(&python),
        shell_escape(&helper_path.display().to_string())
    ))
}

fn helper_script_path(helper_script: &str) -> Option<PathBuf> {
    let candidates = [
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("runtime")
            .join(helper_script),
        PathBuf::from("/usr/libexec/aios-deviced/runtime").join(helper_script),
    ];
    candidates.into_iter().find(|path| path.exists())
}

fn shell_escape(value: &str) -> String {
    if value
        .chars()
        .all(|char| char.is_ascii_alphanumeric() || matches!(char, '/' | '-' | '_' | '.' | ':'))
    {
        return value.to_string();
    }
    format!("'{}'", value.replace('\'', r"'\''"))
}
