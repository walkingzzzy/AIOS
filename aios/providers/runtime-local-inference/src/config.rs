use std::path::{Path, PathBuf};

use aios_core::{config::env_path_or, ServicePaths};
use serde::Deserialize;

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub provider_id: String,
    pub paths: ServicePaths,
    pub runtimed_socket: PathBuf,
    pub policyd_socket: PathBuf,
    pub agentd_socket: PathBuf,
    pub descriptor_path: PathBuf,
    pub observability_log_path: PathBuf,
    pub max_concurrency: u32,
    pub embedding_backend: String,
    pub rerank_backend: String,
    pub ai_readiness_path: PathBuf,
    pub ai_onboarding_report_path: PathBuf,
    pub remote_base_url: Option<String>,
    pub remote_api_key: Option<String>,
    pub remote_model: Option<String>,
    pub remote_embedding_model: Option<String>,
    pub remote_rerank_model: Option<String>,
    pub remote_timeout_ms: u64,
}

#[derive(Debug, Clone, Default)]
pub struct AiReadinessSummary {
    pub source_available: bool,
    pub state: Option<String>,
    pub reason: Option<String>,
    pub next_action: Option<String>,
    pub ai_enabled: Option<bool>,
    pub ai_mode: Option<String>,
    pub route_preference: Option<String>,
    pub local_model_count: Option<u64>,
    pub endpoint_configured: bool,
}

#[derive(Debug, Clone)]
pub struct RemoteEndpointConfig {
    pub base_url: String,
    pub model: String,
    pub api_key: Option<String>,
    pub timeout_ms: u64,
}

impl RemoteEndpointConfig {
    pub fn chat_completions_url(&self) -> String {
        let normalized = self.base_url.trim_end_matches('/');
        if normalized.ends_with("/chat/completions") {
            return normalized.to_string();
        }
        if normalized.ends_with("/v1") {
            return format!("{normalized}/chat/completions");
        }
        format!("{normalized}/v1/chat/completions")
    }

    pub fn embeddings_url(&self) -> String {
        let normalized = self.base_url.trim_end_matches('/');
        if normalized.ends_with("/embeddings") {
            return normalized.to_string();
        }
        if normalized.ends_with("/v1") {
            return format!("{normalized}/embeddings");
        }
        format!("{normalized}/v1/embeddings")
    }
}

impl AiReadinessSummary {
    pub fn provider_enabled(&self) -> bool {
        self.ai_enabled.unwrap_or(true)
    }

    pub fn effective_route_preference(&self) -> &'static str {
        match self.route_preference.as_deref() {
            Some("remote-first") => "remote-first",
            Some("remote-only") => "remote-only",
            Some("local-first") => "local-first",
            _ => match self.ai_mode.as_deref() {
                Some("cloud") => "remote-only",
                _ => "local-first",
            },
        }
    }

    pub fn remote_only_preferred(&self) -> bool {
        self.effective_route_preference() == "remote-only"
            || matches!(
                self.state.as_deref(),
                Some("cloud-ready") | Some("hybrid-remote-only")
            )
    }

    pub fn remote_first_preferred(&self) -> bool {
        matches!(
            self.effective_route_preference(),
            "remote-first" | "remote-only"
        )
    }

    pub fn remote_fallback_allowed(&self) -> bool {
        self.provider_enabled() && self.endpoint_configured
    }

    pub fn remote_route_state(&self) -> &'static str {
        match self.state.as_deref() {
            Some("hybrid-remote-only") => "hybrid-remote-only",
            Some("cloud-ready") => "cloud-ready",
            Some("hybrid-ready") => "hybrid-ready",
            Some("local-ready") => "local-ready",
            Some("setup-pending") => "setup-pending",
            Some("not-ready") => "not-ready",
            Some("disabled") => "disabled",
            _ => "cloud-ready",
        }
    }
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("aios-runtime-local-inference-provider");
        paths.ensure_base_dirs().await?;

        let runtimed_socket =
            std::env::var_os("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_RUNTIMED_SOCKET")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("/run/aios/runtimed/runtimed.sock"));
        let policyd_socket =
            std::env::var_os("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_POLICYD_SOCKET")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("/run/aios/policyd/policyd.sock"));
        let agentd_socket = std::env::var_os("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_AGENTD_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/run/aios/agentd/agentd.sock"));
        let descriptor_path =
            std::env::var_os("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_DESCRIPTOR_PATH")
                .map(PathBuf::from)
                .unwrap_or_else(default_descriptor_path);
        let observability_log_path = env_path_or(
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG",
            || paths.state_dir.join("observability.jsonl"),
        );
        let max_concurrency =
            std::env::var("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_MAX_CONCURRENCY")
                .ok()
                .and_then(|value| value.parse::<u32>().ok())
                .unwrap_or(2);
        let embedding_backend =
            std::env::var("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_EMBEDDING_BACKEND")
                .unwrap_or_else(|_| "local-embedding".to_string());
        let rerank_backend = std::env::var("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_RERANK_BACKEND")
            .unwrap_or_else(|_| "local-reranker".to_string());
        let ai_readiness_path = env_path_or(
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_AI_READINESS_PATH",
            || PathBuf::from("/var/lib/aios/runtime/ai-readiness.json"),
        );
        let ai_onboarding_report_path = env_path_or(
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_AI_ONBOARDING_REPORT_PATH",
            || PathBuf::from("/var/lib/aios/onboarding/ai-onboarding-report.json"),
        );
        let onboarding_report = load_onboarding_report(&ai_onboarding_report_path);
        let remote_base_url = first_non_empty_env(&[
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_BASE_URL",
            "AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL",
            "OPENAI_BASE_URL",
        ])
        .or_else(|| {
            onboarding_report
                .as_ref()
                .and_then(|report| trim_non_empty(report.endpoint_base_url.as_deref()))
        });
        let remote_model = first_non_empty_env(&[
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_MODEL",
            "AIOS_RUNTIMED_AI_ENDPOINT_MODEL",
        ])
        .or_else(|| {
            onboarding_report
                .as_ref()
                .and_then(|report| trim_non_empty(report.endpoint_model.as_deref()))
        });
        let remote_embedding_model = first_non_empty_env(&[
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_EMBEDDING_MODEL",
            "AIOS_RUNTIMED_AI_ENDPOINT_EMBEDDING_MODEL",
        ])
        .or_else(|| remote_model.clone());
        let remote_rerank_model = first_non_empty_env(&[
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_RERANK_MODEL",
            "AIOS_RUNTIMED_AI_ENDPOINT_RERANK_MODEL",
        ])
        .or_else(|| remote_embedding_model.clone())
        .or_else(|| remote_model.clone());
        let remote_api_key = first_non_empty_env(&[
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_API_KEY",
            "AIOS_RUNTIMED_AI_ENDPOINT_API_KEY",
            "OPENAI_API_KEY",
        ]);
        let remote_timeout_ms =
            std::env::var("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_REMOTE_TIMEOUT_MS")
                .ok()
                .and_then(|value| value.parse::<u64>().ok())
                .unwrap_or(30_000);

        Ok(Self {
            service_id: "aios-runtime-local-inference-provider".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            provider_id: std::env::var("AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_ID")
                .unwrap_or_else(|_| "runtime.local.inference".to_string()),
            paths,
            runtimed_socket,
            policyd_socket,
            agentd_socket,
            descriptor_path,
            observability_log_path,
            max_concurrency,
            embedding_backend,
            rerank_backend,
            ai_readiness_path,
            ai_onboarding_report_path,
            remote_base_url,
            remote_api_key,
            remote_model,
            remote_embedding_model,
            remote_rerank_model,
            remote_timeout_ms,
        })
    }

    pub fn load_ai_readiness_summary(&self) -> AiReadinessSummary {
        let readiness_payload = load_ai_readiness_payload(&self.ai_readiness_path);
        let report_payload = load_onboarding_report(&self.ai_onboarding_report_path);
        let state = readiness_payload
            .as_ref()
            .and_then(|payload| trim_non_empty(payload.state.as_deref()))
            .or_else(|| {
                report_payload
                    .as_ref()
                    .and_then(|payload| trim_non_empty(payload.readiness_state.as_deref()))
            });
        let reason = readiness_payload
            .as_ref()
            .and_then(|payload| trim_non_empty(payload.reason.as_deref()))
            .or_else(|| {
                report_payload
                    .as_ref()
                    .and_then(|payload| trim_non_empty(payload.readiness_reason.as_deref()))
            });
        let next_action = readiness_payload
            .as_ref()
            .and_then(|payload| trim_non_empty(payload.next_action.as_deref()))
            .or_else(|| {
                report_payload
                    .as_ref()
                    .and_then(|payload| trim_non_empty(payload.next_action.as_deref()))
            });
        let ai_enabled_env = env_bool("AIOS_RUNTIMED_AI_ENABLED");
        let ai_mode_env = first_non_empty_env(&["AIOS_RUNTIMED_AI_MODE"]);
        let route_preference_env = first_non_empty_env(&["AIOS_RUNTIMED_AI_ROUTE_PREFERENCE"]);
        let endpoint_configured = readiness_payload
            .as_ref()
            .and_then(|payload| payload.endpoint_configured)
            .or_else(|| {
                report_payload
                    .as_ref()
                    .and_then(|payload| payload.endpoint_configured)
            })
            .unwrap_or(false)
            || self.remote_endpoint_config().is_some();

        AiReadinessSummary {
            source_available: readiness_payload.is_some() || report_payload.is_some(),
            state,
            reason,
            next_action,
            ai_enabled: readiness_payload
                .as_ref()
                .and_then(|payload| payload.ai_enabled)
                .or_else(|| {
                    report_payload
                        .as_ref()
                        .and_then(|payload| payload.ai_enabled)
                })
                .or(ai_enabled_env),
            ai_mode: readiness_payload
                .as_ref()
                .and_then(|payload| trim_non_empty(payload.ai_mode.as_deref()))
                .or_else(|| {
                    report_payload
                        .as_ref()
                        .and_then(|payload| trim_non_empty(payload.ai_mode.as_deref()))
                })
                .or(ai_mode_env.clone()),
            route_preference: normalize_route_preference(
                route_preference_env,
                readiness_payload
                    .as_ref()
                    .and_then(|payload| trim_non_empty(payload.ai_mode.as_deref()))
                    .or_else(|| {
                        report_payload
                            .as_ref()
                            .and_then(|payload| trim_non_empty(payload.ai_mode.as_deref()))
                    })
                    .or(ai_mode_env),
            ),
            local_model_count: readiness_payload
                .as_ref()
                .and_then(|payload| payload.local_model_count)
                .or_else(|| {
                    report_payload
                        .as_ref()
                        .and_then(|payload| payload.local_model_count)
                }),
            endpoint_configured,
        }
    }

    pub fn remote_endpoint_config(&self) -> Option<RemoteEndpointConfig> {
        let base_url = trim_non_empty(self.remote_base_url.as_deref())?;
        let model = trim_non_empty(self.remote_model.as_deref())?;
        Some(RemoteEndpointConfig {
            base_url,
            model,
            api_key: trim_non_empty(self.remote_api_key.as_deref()),
            timeout_ms: self.remote_timeout_ms,
        })
    }

    pub fn remote_embedding_endpoint_config(
        &self,
        requested_model: Option<&str>,
    ) -> Option<RemoteEndpointConfig> {
        let base_url = trim_non_empty(self.remote_base_url.as_deref())?;
        let model = trim_non_empty(requested_model)
            .or_else(|| trim_non_empty(self.remote_embedding_model.as_deref()))
            .or_else(|| trim_non_empty(self.remote_model.as_deref()))?;
        Some(RemoteEndpointConfig {
            base_url,
            model,
            api_key: trim_non_empty(self.remote_api_key.as_deref()),
            timeout_ms: self.remote_timeout_ms,
        })
    }

    pub fn remote_rerank_endpoint_config(
        &self,
        requested_model: Option<&str>,
    ) -> Option<RemoteEndpointConfig> {
        let base_url = trim_non_empty(self.remote_base_url.as_deref())?;
        let model = trim_non_empty(requested_model)
            .or_else(|| trim_non_empty(self.remote_rerank_model.as_deref()))
            .or_else(|| trim_non_empty(self.remote_embedding_model.as_deref()))
            .or_else(|| trim_non_empty(self.remote_model.as_deref()))?;
        Some(RemoteEndpointConfig {
            base_url,
            model,
            api_key: trim_non_empty(self.remote_api_key.as_deref()),
            timeout_ms: self.remote_timeout_ms,
        })
    }
}

fn default_descriptor_path() -> PathBuf {
    let installed = PathBuf::from("/usr/share/aios/providers/runtime.local-inference.json");
    if installed.exists() {
        return installed;
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../runtime/providers/runtime.local-inference.json")
}

fn first_non_empty_env(keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| {
        std::env::var(key)
            .ok()
            .and_then(|value| trim_non_empty(Some(&value)))
    })
}

fn env_bool(key: &str) -> Option<bool> {
    std::env::var(key)
        .ok()
        .map(|value| match value.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => true,
            "0" | "false" | "no" | "off" => false,
            _ => true,
        })
}

fn trim_non_empty(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn normalize_route_preference(
    route_preference: Option<String>,
    ai_mode: Option<String>,
) -> Option<String> {
    let ai_mode = ai_mode.unwrap_or_else(|| "hybrid".to_string());
    let normalized = route_preference
        .as_deref()
        .map(str::trim)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let candidate = match normalized.as_str() {
        "remote-first" => "remote-first",
        "remote-only" => "remote-only",
        "local-first" => "local-first",
        _ if ai_mode == "cloud" => "remote-only",
        _ => "local-first",
    };
    Some(
        if ai_mode == "cloud" {
            "remote-only"
        } else if ai_mode == "local" {
            "local-first"
        } else {
            candidate
        }
        .to_string(),
    )
}

fn load_json_file<T>(path: &Path) -> Option<T>
where
    T: for<'de> Deserialize<'de>,
{
    let content = std::fs::read_to_string(path).ok()?;
    serde_json::from_str::<T>(&content).ok()
}

fn load_onboarding_report(path: &Path) -> Option<AiOnboardingReport> {
    load_json_file(path)
}

fn load_ai_readiness_payload(path: &Path) -> Option<AiReadinessPayload> {
    load_json_file(path)
}

#[derive(Debug, Clone, Deserialize)]
struct AiReadinessPayload {
    #[serde(default)]
    state: Option<String>,
    #[serde(default)]
    reason: Option<String>,
    #[serde(default)]
    next_action: Option<String>,
    #[serde(default)]
    ai_enabled: Option<bool>,
    #[serde(default)]
    ai_mode: Option<String>,
    #[serde(default)]
    local_model_count: Option<u64>,
    #[serde(default)]
    endpoint_configured: Option<bool>,
}

#[derive(Debug, Clone, Deserialize)]
struct AiOnboardingReport {
    #[serde(default)]
    ai_enabled: Option<bool>,
    #[serde(default)]
    ai_mode: Option<String>,
    #[serde(default)]
    local_model_count: Option<u64>,
    #[serde(default)]
    endpoint_configured: Option<bool>,
    #[serde(default)]
    endpoint_base_url: Option<String>,
    #[serde(default)]
    endpoint_model: Option<String>,
    #[serde(default)]
    readiness_state: Option<String>,
    #[serde(default)]
    readiness_reason: Option<String>,
    #[serde(default)]
    next_action: Option<String>,
}
