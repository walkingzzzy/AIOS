use std::path::PathBuf;

use aios_core::ServicePaths;
use anyhow::Context;

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
    pub audit_export_dir: PathBuf,
    pub observability_log_path: PathBuf,
    pub token_key_path: PathBuf,
    pub token_usage_dir: PathBuf,
    pub token_ttl_seconds: u64,
    pub approval_ttl_seconds: u64,
    pub audit_rotate_after_bytes: u64,
    pub audit_retention_days: u64,
    pub audit_max_archives: usize,
    pub runtime_platform_env_path: PathBuf,
    pub approval_default_policy: String,
    pub remote_prompt_level: String,
}

#[derive(Debug, Clone)]
pub struct RuntimePolicySettings {
    pub approval_default_policy: String,
    pub remote_prompt_level: String,
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
        let audit_export_dir =
            aios_core::config::env_path_or("AIOS_POLICYD_AUDIT_EXPORT_DIR", || {
                paths.state_dir.join("audit-exports")
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
        let runtime_platform_env_path =
            aios_core::config::env_path_or("AIOS_POLICYD_RUNTIME_PLATFORM_ENV", || {
                PathBuf::from("/etc/aios/runtime/platform.env")
            });
        let approval_default_policy = normalize_approval_default_policy(
            aios_core::config::env_optional_string("AIOS_POLICYD_APPROVAL_DEFAULT_POLICY")
                .as_deref(),
        );
        let remote_prompt_level = normalize_remote_prompt_level(
            aios_core::config::env_optional_string("AIOS_POLICYD_REMOTE_PROMPT_LEVEL").as_deref(),
        );

        Ok(Self {
            service_id: "aios-policyd".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            paths,
            policy_path,
            capability_catalog_path,
            audit_log_path,
            audit_index_path,
            audit_archive_dir,
            audit_export_dir,
            observability_log_path,
            token_key_path,
            token_usage_dir,
            token_ttl_seconds,
            approval_ttl_seconds,
            audit_rotate_after_bytes,
            audit_retention_days,
            audit_max_archives,
            runtime_platform_env_path,
            approval_default_policy,
            remote_prompt_level,
        })
    }

    pub fn runtime_policy_settings(&self) -> anyhow::Result<RuntimePolicySettings> {
        let mut settings = RuntimePolicySettings {
            approval_default_policy: self.approval_default_policy.clone(),
            remote_prompt_level: self.remote_prompt_level.clone(),
        };

        let env_values = load_runtime_platform_env(&self.runtime_platform_env_path)?;
        if let Some(value) = env_values.get("AIOS_RUNTIMED_APPROVAL_DEFAULT_POLICY") {
            settings.approval_default_policy = normalize_approval_default_policy(Some(value));
        }
        if let Some(value) = env_values.get("AIOS_RUNTIMED_REMOTE_PROMPT_LEVEL") {
            settings.remote_prompt_level = normalize_remote_prompt_level(Some(value));
        }

        if let Some(value) =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_APPROVAL_DEFAULT_POLICY")
        {
            settings.approval_default_policy = normalize_approval_default_policy(Some(&value));
        }
        if let Some(value) =
            aios_core::config::env_optional_string("AIOS_RUNTIMED_REMOTE_PROMPT_LEVEL")
        {
            settings.remote_prompt_level = normalize_remote_prompt_level(Some(&value));
        }

        Ok(settings)
    }
}

fn load_runtime_platform_env(
    path: &PathBuf,
) -> anyhow::Result<std::collections::BTreeMap<String, String>> {
    if !path.exists() {
        return Ok(std::collections::BTreeMap::new());
    }

    let contents = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read runtime platform env {}", path.display()))?;
    let mut values = std::collections::BTreeMap::new();
    for raw_line in contents.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') || !line.contains('=') {
            continue;
        }
        let (key, value) = line.split_once('=').unwrap_or_default();
        values.insert(key.trim().to_string(), value.trim().to_string());
    }

    Ok(values)
}

fn normalize_approval_default_policy(value: Option<&str>) -> String {
    match value
        .unwrap_or("prompt-required")
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "session-trust" => "session-trust".to_string(),
        "operator-gate" => "operator-gate".to_string(),
        _ => "prompt-required".to_string(),
    }
}

fn normalize_remote_prompt_level(value: Option<&str>) -> String {
    match value.unwrap_or("full").trim().to_ascii_lowercase().as_str() {
        "summary" => "summary".to_string(),
        "minimal" => "minimal".to_string(),
        _ => "full".to_string(),
    }
}
