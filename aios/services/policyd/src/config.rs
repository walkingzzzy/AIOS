use std::path::PathBuf;

use aios_core::ServicePaths;

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub paths: ServicePaths,
    pub policy_path: PathBuf,
    pub capability_catalog_path: PathBuf,
    pub audit_log_path: PathBuf,
    pub audit_index_path: PathBuf,
    pub audit_archive_dir: PathBuf,
    pub observability_log_path: PathBuf,
    pub token_key_path: PathBuf,
    pub token_usage_dir: PathBuf,
    pub token_ttl_seconds: u64,
    pub approval_ttl_seconds: u64,
    pub audit_rotate_after_bytes: u64,
    pub audit_retention_days: u64,
    pub audit_max_archives: usize,
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("policyd");
        paths.ensure_base_dirs().await?;

        let policy_path = aios_core::config::env_path_or("AIOS_POLICYD_POLICY_PATH", || {
            PathBuf::from("/etc/aios/policy/default-policy.yaml")
        });

        let capability_catalog_path =
            aios_core::config::env_path_or("AIOS_POLICYD_CAPABILITY_CATALOG_PATH", || {
                PathBuf::from("/etc/aios/policy/default-capability-catalog.yaml")
            });

        let audit_log_path = aios_core::config::env_path_or("AIOS_POLICYD_AUDIT_LOG", || {
            paths.state_dir.join("audit.jsonl")
        });
        let audit_index_path =
            aios_core::config::env_path_or("AIOS_POLICYD_AUDIT_INDEX_PATH", || {
                paths.state_dir.join("audit-index.json")
            });
        let audit_archive_dir =
            aios_core::config::env_path_or("AIOS_POLICYD_AUDIT_ARCHIVE_DIR", || {
                paths.state_dir.join("audit-archive")
            });
        let observability_log_path =
            aios_core::config::env_path_or("AIOS_POLICYD_OBSERVABILITY_LOG", || {
                paths.state_dir.join("observability.jsonl")
            });

        let token_key_path = aios_core::config::env_path_or("AIOS_POLICYD_TOKEN_KEY_PATH", || {
            paths.state_dir.join("token.key")
        });
        let token_usage_dir =
            aios_core::config::env_path_or("AIOS_POLICYD_TOKEN_USAGE_DIR", || {
                paths.state_dir.join("token-usage")
            });

        let token_ttl_seconds =
            aios_core::config::env_u64_or("AIOS_POLICYD_TOKEN_TTL_SECONDS", 300);

        let approval_ttl_seconds =
            aios_core::config::env_u64_or("AIOS_POLICYD_APPROVAL_TTL_SECONDS", 900);
        let audit_rotate_after_bytes =
            aios_core::config::env_u64_or("AIOS_POLICYD_AUDIT_ROTATE_AFTER_BYTES", 256 * 1024);
        let audit_retention_days =
            aios_core::config::env_u64_or("AIOS_POLICYD_AUDIT_RETENTION_DAYS", 30);
        let audit_max_archives =
            aios_core::config::env_u64_or("AIOS_POLICYD_AUDIT_MAX_ARCHIVES", 32) as usize;

        Ok(Self {
            service_id: "aios-policyd".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            paths,
            policy_path,
            capability_catalog_path,
            audit_log_path,
            audit_index_path,
            audit_archive_dir,
            observability_log_path,
            token_key_path,
            token_usage_dir,
            token_ttl_seconds,
            approval_ttl_seconds,
            audit_rotate_after_bytes,
            audit_retention_days,
            audit_max_archives,
        })
    }
}
