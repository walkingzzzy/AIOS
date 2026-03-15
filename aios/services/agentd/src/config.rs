use std::path::PathBuf;

use aios_core::ServicePaths;

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub paths: ServicePaths,
    pub sessiond_socket: PathBuf,
    pub policyd_socket: PathBuf,
    pub runtimed_socket: PathBuf,
    pub provider_registry_state_dir: PathBuf,
    pub provider_descriptor_dirs: Vec<PathBuf>,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("agentd");
        paths.ensure_base_dirs().await?;

        let sessiond_socket = aios_core::config::env_path_or("AIOS_AGENTD_SESSIOND_SOCKET", || {
            PathBuf::from("/run/aios/sessiond/sessiond.sock")
        });

        let policyd_socket = aios_core::config::env_path_or("AIOS_AGENTD_POLICYD_SOCKET", || {
            PathBuf::from("/run/aios/policyd/policyd.sock")
        });

        let runtimed_socket = aios_core::config::env_path_or("AIOS_AGENTD_RUNTIMED_SOCKET", || {
            PathBuf::from("/run/aios/runtimed/runtimed.sock")
        });

        let provider_registry_state_dir =
            aios_core::config::env_path_or("AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR", || {
                PathBuf::from("/var/lib/aios/registry")
            });

        let provider_descriptor_dirs = std::env::var_os("AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS")
            .map(|value| std::env::split_paths(&value).collect::<Vec<_>>())
            .filter(|entries| !entries.is_empty())
            .unwrap_or_else(default_provider_descriptor_dirs);

        Ok(Self {
            service_id: "aios-agentd".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            paths,
            sessiond_socket,
            policyd_socket,
            runtimed_socket,
            provider_registry_state_dir,
            provider_descriptor_dirs,
        })
    }
}

fn default_provider_descriptor_dirs() -> Vec<PathBuf> {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut directories = vec![
        PathBuf::from("/etc/aios/providers"),
        PathBuf::from("/usr/share/aios/providers"),
        repo_root.join("sdk/providers"),
        repo_root.join("runtime/providers"),
        repo_root.join("shell/providers"),
        repo_root.join("compat/browser/providers"),
        repo_root.join("compat/office/providers"),
        repo_root.join("compat/mcp-bridge/providers"),
        repo_root.join("compat/code-sandbox/providers"),
    ];

    directories.sort();
    directories.dedup();
    directories
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_provider_dirs_include_code_sandbox_fixture() {
        let directories = default_provider_descriptor_dirs();
        assert!(directories
            .iter()
            .any(|path| path.ends_with("compat/code-sandbox/providers")));
    }
}
