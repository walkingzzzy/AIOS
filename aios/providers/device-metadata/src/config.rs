use std::path::PathBuf;

use aios_core::{config::env_path_or, ServicePaths};

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub provider_id: String,
    pub paths: ServicePaths,
    pub deviced_socket: PathBuf,
    pub agentd_socket: PathBuf,
    pub descriptor_path: PathBuf,
    pub observability_log_path: PathBuf,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("aios-device-metadata-provider");
        paths.ensure_base_dirs().await?;

        let deviced_socket = std::env::var_os("AIOS_DEVICE_METADATA_PROVIDER_DEVICED_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/deviced/deviced.sock"));

        let agentd_socket = std::env::var_os("AIOS_DEVICE_METADATA_PROVIDER_AGENTD_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/agentd/agentd.sock"));

        let descriptor_path = std::env::var_os("AIOS_DEVICE_METADATA_PROVIDER_DESCRIPTOR_PATH")
            .map(PathBuf::from)
            .unwrap_or_else(default_descriptor_path);
        let observability_log_path =
            env_path_or("AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG", || {
                paths.state_dir.join("observability.jsonl")
            });

        Ok(Self {
            service_id: "aios-device-metadata-provider".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            provider_id: std::env::var("AIOS_DEVICE_METADATA_PROVIDER_ID")
                .unwrap_or_else(|_| "device.metadata.local".to_string()),
            paths,
            deviced_socket,
            agentd_socket,
            descriptor_path,
            observability_log_path,
        })
    }
}

fn default_descriptor_path() -> PathBuf {
    let installed = PathBuf::from("/usr/share/aios/providers/device.metadata.local.json");
    if installed.exists() {
        return installed;
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../sdk/providers/device.metadata.local.json")
}
