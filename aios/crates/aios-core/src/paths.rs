use std::{env, path::PathBuf};

#[derive(Debug, Clone)]
pub struct ServicePaths {
    pub state_dir: PathBuf,
    pub runtime_dir: PathBuf,
    pub socket_path: PathBuf,
}

impl ServicePaths {
    pub fn from_service_name(service_name: &str) -> Self {
        let normalized = service_name.trim_start_matches("aios-");
        let env_prefix = format!("AIOS_{}", normalized.replace('-', "_").to_ascii_uppercase());

        let state_dir = env::var_os(format!("{env_prefix}_STATE_DIR"))
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(format!("/var/lib/aios/{normalized}")));

        let runtime_dir = env::var_os(format!("{env_prefix}_RUNTIME_DIR"))
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(format!("/run/aios/{normalized}")));

        let socket_path = env::var_os(format!("{env_prefix}_SOCKET_PATH"))
            .map(PathBuf::from)
            .unwrap_or_else(|| runtime_dir.join(format!("{normalized}.sock")));

        Self {
            state_dir,
            runtime_dir,
            socket_path,
        }
    }

    pub async fn ensure_base_dirs(&self) -> anyhow::Result<()> {
        tokio::fs::create_dir_all(&self.state_dir).await?;
        tokio::fs::create_dir_all(&self.runtime_dir).await?;
        Ok(())
    }
}
