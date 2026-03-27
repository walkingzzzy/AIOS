use std::path::PathBuf;

use aios_core::ServicePaths;

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub paths: ServicePaths,
    pub database_path: PathBuf,
    pub observability_log_path: PathBuf,
    pub migrations_dir: PathBuf,
    pub portal_state_dir: PathBuf,
    pub evidence_export_dir: PathBuf,
    pub portal_default_ttl_seconds: u64,
    pub runtime_platform_env_path: PathBuf,
    pub memory_default_enabled: bool,
    pub memory_default_retention_days: u64,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("sessiond");
        paths.ensure_base_dirs().await?;

        let database_path = aios_core::config::env_path_or("AIOS_SESSIOND_DATABASE", || {
            paths.state_dir.join("sessiond.sqlite3")
        });
        let observability_log_path =
            aios_core::config::env_path_or("AIOS_SESSIOND_OBSERVABILITY_LOG", || {
                paths.state_dir.join("observability.jsonl")
            });

        let migrations_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("migrations");
        let portal_state_dir =
            aios_core::config::env_path_or("AIOS_SESSIOND_PORTAL_STATE_DIR", || {
                paths.state_dir.join("portal")
            });
        let evidence_export_dir =
            aios_core::config::env_path_or("AIOS_SESSIOND_EVIDENCE_EXPORT_DIR", || {
                paths.state_dir.join("evidence-exports")
            });
        let portal_default_ttl_seconds =
            aios_core::config::env_u64_or("AIOS_SESSIOND_PORTAL_DEFAULT_TTL_SECONDS", 300);
        let runtime_platform_env_path =
            aios_core::config::env_path_or("AIOS_SESSIOND_RUNTIME_PLATFORM_ENV", || {
                PathBuf::from("/etc/aios/runtime/platform.env")
            });
        let memory_default_enabled = parse_bool_env("AIOS_SESSIOND_MEMORY_ENABLED").unwrap_or(true);
        let memory_default_retention_days =
            aios_core::config::env_u64_or("AIOS_SESSIOND_MEMORY_RETENTION_DAYS", 30);

        Ok(Self {
            service_id: "aios-sessiond".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            paths,
            database_path,
            observability_log_path,
            migrations_dir,
            portal_state_dir,
            evidence_export_dir,
            portal_default_ttl_seconds,
            runtime_platform_env_path,
            memory_default_enabled,
            memory_default_retention_days,
        })
    }
}

fn parse_bool_env(name: &str) -> Option<bool> {
    std::env::var(name)
        .ok()
        .and_then(|value| match value.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => Some(true),
            "0" | "false" | "no" | "off" => Some(false),
            _ => None,
        })
}
