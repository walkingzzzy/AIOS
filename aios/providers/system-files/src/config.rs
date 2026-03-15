use std::path::PathBuf;

use aios_core::{config::env_path_or, ServicePaths};

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub provider_id: String,
    pub paths: ServicePaths,
    pub sessiond_socket: PathBuf,
    pub policyd_socket: PathBuf,
    pub agentd_socket: PathBuf,
    pub descriptor_path: PathBuf,
    pub audit_log_path: PathBuf,
    pub observability_log_path: PathBuf,
    pub max_preview_bytes: u64,
    pub max_directory_entries: u32,
    pub max_concurrency: u32,
    pub max_delete_affected_paths: u32,
    pub test_startup_reserve_ms: u64,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("aios-system-files-provider");
        paths.ensure_base_dirs().await?;

        let sessiond_socket = std::env::var_os("AIOS_SYSTEM_FILES_PROVIDER_SESSIOND_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/sessiond/sessiond.sock"));

        let policyd_socket = std::env::var_os("AIOS_SYSTEM_FILES_PROVIDER_POLICYD_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/policyd/policyd.sock"));

        let audit_log_path = std::env::var_os("AIOS_SYSTEM_FILES_PROVIDER_AUDIT_LOG")
            .map(PathBuf::from)
            .unwrap_or_else(|| paths.state_dir.join("audit.jsonl"));
        let observability_log_path = env_path_or(
            "AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG",
            || paths.state_dir.join("observability.jsonl"),
        );

        let agentd_socket = std::env::var_os("AIOS_SYSTEM_FILES_PROVIDER_AGENTD_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/agentd/agentd.sock"));

        let descriptor_path = std::env::var_os("AIOS_SYSTEM_FILES_PROVIDER_DESCRIPTOR_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(default_descriptor_path);

        Ok(Self {
            service_id: "aios-system-files-provider".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            provider_id: std::env::var("AIOS_SYSTEM_FILES_PROVIDER_ID")
                .unwrap_or_else(|_| "system.files.local".to_string()),
            paths,
            sessiond_socket,
            policyd_socket,
            agentd_socket,
            descriptor_path,
            audit_log_path,
            observability_log_path,
            max_preview_bytes: read_u64_env("AIOS_SYSTEM_FILES_PROVIDER_MAX_PREVIEW_BYTES", 4096),
            max_directory_entries: read_u32_env(
                "AIOS_SYSTEM_FILES_PROVIDER_MAX_DIRECTORY_ENTRIES",
                64,
            ),
            max_concurrency: read_u32_env("AIOS_SYSTEM_FILES_PROVIDER_MAX_CONCURRENCY", 2),
            max_delete_affected_paths: read_u32_env(
                "AIOS_SYSTEM_FILES_PROVIDER_MAX_DELETE_AFFECTED_PATHS",
                64,
            ),
            test_startup_reserve_ms: read_u64_env(
                "AIOS_SYSTEM_FILES_PROVIDER_TEST_STARTUP_RESERVE_MS",
                0,
            ),
        })
    }
}

fn read_u64_env(name: &str, default_value: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(default_value)
}

fn read_u32_env(name: &str, default_value: u32) -> u32 {
    std::env::var(name)
        .ok()
        .and_then(|value| value.parse::<u32>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(default_value)
}

fn default_descriptor_path() -> PathBuf {
    let installed = PathBuf::from("/usr/share/aios/providers/system-files.local.json");
    if installed.exists() {
        return installed;
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../sdk/providers/system-files.local.json")
}
