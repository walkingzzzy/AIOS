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
    pub observability_log_path: PathBuf,
    pub max_concurrency: u32,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("aios-system-intent-provider");
        paths.ensure_base_dirs().await?;

        let sessiond_socket = std::env::var_os("AIOS_SYSTEM_INTENT_PROVIDER_SESSIOND_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/sessiond/sessiond.sock"));
        let policyd_socket = std::env::var_os("AIOS_SYSTEM_INTENT_PROVIDER_POLICYD_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/policyd/policyd.sock"));
        let agentd_socket = std::env::var_os("AIOS_SYSTEM_INTENT_PROVIDER_AGENTD_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/agentd/agentd.sock"));
        let descriptor_path = std::env::var_os("AIOS_SYSTEM_INTENT_PROVIDER_DESCRIPTOR_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(default_descriptor_path);
        let observability_log_path = env_path_or(
            "AIOS_SYSTEM_INTENT_PROVIDER_OBSERVABILITY_LOG",
            || paths.state_dir.join("observability.jsonl"),
        );
        let max_concurrency = std::env::var("AIOS_SYSTEM_INTENT_PROVIDER_MAX_CONCURRENCY")
            .ok()
            .and_then(|value| value.parse::<u32>().ok())
            .unwrap_or(8);

        Ok(Self {
            service_id: "aios-system-intent-provider".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            provider_id: std::env::var("AIOS_SYSTEM_INTENT_PROVIDER_ID")
                .unwrap_or_else(|_| "system.intent.local".to_string()),
            paths,
            sessiond_socket,
            policyd_socket,
            agentd_socket,
            descriptor_path,
            observability_log_path,
            max_concurrency,
        })
    }
}

fn default_descriptor_path() -> PathBuf {
    let installed = PathBuf::from("/usr/share/aios/providers/system-intent.local.json");
    if installed.exists() {
        return installed;
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../sdk/providers/system-intent.local.json")
}
