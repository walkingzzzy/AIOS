use std::collections::BTreeMap;
use std::path::Path;

use serde::Deserialize;

use aios_contracts::{
    RuntimeBackendDescriptor, RuntimeInferRequest, RuntimeInferResponse,
    RuntimeRouteResolveRequest, RuntimeRouteResolveResponse,
};

use crate::backend::{BackendCommands, BackendExecutionError, BackendFailureClass};

#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeProfile {
    pub profile_id: String,
    pub scope: String,
    pub default_backend: String,
    #[serde(default)]
    pub allowed_backends: Vec<String>,
    #[serde(default)]
    pub local_model_pool: Vec<String>,
    #[serde(default)]
    pub remote_model_pool: Vec<String>,
    #[serde(default)]
    pub backend_worker_contract: Option<String>,
    #[serde(default)]
    pub backend_commands: BTreeMap<String, String>,
    #[serde(default)]
    pub managed_worker_commands: BTreeMap<String, String>,
    #[serde(default)]
    pub hardware_profile_managed_worker_commands: BTreeMap<String, BTreeMap<String, String>>,
    pub embedding_backend: String,
    pub rerank_backend: String,
    pub cpu_fallback: bool,
    pub memory_budget_mb: u64,
    pub kv_cache_budget_mb: u64,
    pub timeout_ms: u64,
    pub max_concurrency: u32,
    pub max_parallel_models: u32,
    pub offload_policy: String,
    pub degradation_policy: String,
    pub observability_level: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RouteProfile {
    pub profile_id: String,
    pub default_topology: String,
    #[serde(default)]
    pub allowed_topologies: Vec<String>,
    #[serde(default)]
    pub router_stack: Vec<String>,
    pub semantic_router_enabled: bool,
    pub llm_router_enabled: bool,
    pub cost_router_enabled: bool,
    pub provider_preference: String,
    pub prefer_local: bool,
    pub prefer_structured_interface: bool,
    pub allow_gui_fallback: String,
    pub iteration_cap: u32,
    pub tool_call_cap: u32,
    pub replan_cap: u32,
    pub escalation_threshold: String,
    pub human_handoff_policy: String,
}

#[derive(Debug, Clone)]
pub struct Scheduler {
    pub runtime_profile: RuntimeProfile,
    pub route_profile: RouteProfile,
    pub backend_commands: BackendCommands,
}

impl Scheduler {
    pub fn load(
        runtime_profile_path: &Path,
        route_profile_path: &Path,
        backend_commands: BackendCommands,
    ) -> anyhow::Result<Self> {
        let runtime_profile: RuntimeProfile = aios_core::schema::load_yaml_file_validated(
            runtime_profile_path,
            aios_core::schema::SchemaNamespace::Runtime,
            "runtime-profile.schema.json",
        )?;
        let route_profile: RouteProfile = aios_core::schema::load_yaml_file_validated(
            route_profile_path,
            aios_core::schema::SchemaNamespace::Runtime,
            "route-profile.schema.json",
        )?;
        let backend_commands = merge_backend_commands(&runtime_profile, backend_commands);

        Ok(Self {
            runtime_profile,
            route_profile,
            backend_commands,
        })
    }

    pub fn backends(&self) -> Vec<RuntimeBackendDescriptor> {
        crate::backend::descriptors(
            &self.runtime_profile.allowed_backends,
            &self.backend_commands,
        )
    }

    pub fn resolve(&self, request: &RuntimeRouteResolveRequest) -> RuntimeRouteResolveResponse {
        let requested_backend = request
            .preferred_backend
            .clone()
            .filter(|backend| {
                self.runtime_profile
                    .allowed_backends
                    .iter()
                    .any(|item| item == backend)
            })
            .unwrap_or_else(|| self.runtime_profile.default_backend.clone());

        let selected_backend =
            self.ensure_executable_backend(&requested_backend, request.allow_remote);
        let selected_readiness =
            crate::backend::readiness(&selected_backend, &self.backend_commands);
        let selected_is_executable = selected_readiness
            .as_ref()
            .map(|readiness| readiness.is_available())
            .unwrap_or(false);
        let degraded = selected_backend != self.runtime_profile.default_backend
            || selected_backend != requested_backend;
        let route_state = match selected_backend.as_str() {
            "local-cpu" if !selected_is_executable => "setup-pending",
            "attested-remote" if !selected_is_executable => "remote-disabled",
            _ if !selected_is_executable => "capability-rejected",
            "attested-remote" => {
                if degraded {
                    "degraded-remote"
                } else {
                    "attested-remote"
                }
            }
            "local-cpu" if self.backend_commands.local_cpu.is_none() => {
                if degraded {
                    "degraded-local"
                } else {
                    "local-worker"
                }
            }
            _ if degraded => "degraded-local",
            _ if self
                .backend_commands
                .for_backend(&selected_backend)
                .is_some() =>
            {
                "local-wrapper"
            }
            _ => "local",
        }
        .to_string();

        let reason = if !selected_is_executable {
            let readiness_reason = selected_readiness
                .map(|readiness| readiness.reason)
                .unwrap_or_else(|| "selected backend is not executable".to_string());
            if selected_backend != requested_backend {
                format!(
                    "selected {} instead of requested {} but backend is not executable: {}",
                    selected_backend, requested_backend, readiness_reason
                )
            } else {
                format!(
                    "selected {} but backend is not executable: {}",
                    selected_backend, readiness_reason
                )
            }
        } else if selected_backend != requested_backend {
            let fallback_reason =
                self.non_executable_backend_reason(&requested_backend, request.allow_remote);
            format!(
                "selected {} instead of requested {} because {}",
                selected_backend, requested_backend, fallback_reason
            )
        } else if degraded {
            format!(
                "selected {} instead of default {}",
                selected_backend, self.runtime_profile.default_backend
            )
        } else {
            format!(
                "using {} with topology {}",
                selected_backend, self.route_profile.default_topology
            )
        };

        RuntimeRouteResolveResponse {
            selected_backend,
            route_state,
            degraded,
            reason,
        }
    }

    pub fn infer(&self, request: &RuntimeInferRequest) -> RuntimeInferResponse {
        let route = self.resolve(&RuntimeRouteResolveRequest {
            preferred_backend: request.preferred_backend.clone(),
            allow_remote: true,
        });
        self.infer_on_route(request, &route)
    }

    pub fn infer_on_route(
        &self,
        request: &RuntimeInferRequest,
        route: &RuntimeRouteResolveResponse,
    ) -> RuntimeInferResponse {
        let estimated_latency_ms = self.estimate_latency_ms(request);

        if estimated_latency_ms > self.runtime_profile.timeout_ms {
            if self.runtime_profile.cpu_fallback
                && route.selected_backend != "local-cpu"
                && self.backend_is_executable("local-cpu", true)
            {
                return self.fallback_response(
                    request,
                    "local-cpu",
                    estimated_latency_ms,
                    "timeout-fallback-local-cpu",
                    format!(
                        "estimated latency {}ms exceeded timeout {}ms; downgraded to local-cpu",
                        estimated_latency_ms, self.runtime_profile.timeout_ms
                    ),
                    Vec::new(),
                );
            }

            return RuntimeInferResponse {
                backend_id: route.selected_backend.clone(),
                route_state: "timeout-rejected".to_string(),
                content: String::new(),
                degraded: route.degraded,
                rejected: true,
                reason: Some(format!(
                    "estimated latency {}ms exceeded timeout {}ms",
                    estimated_latency_ms, self.runtime_profile.timeout_ms
                )),
                estimated_latency_ms: Some(estimated_latency_ms),
                provider_id: None,
                runtime_service_id: None,
                provider_status: None,
                queue_saturated: None,
                runtime_budget: None,
                notes: Vec::new(),
            };
        }

        match crate::backend::execute(
            &route.selected_backend,
            request,
            estimated_latency_ms,
            self.runtime_profile.timeout_ms,
            &self.backend_commands,
        ) {
            Ok(mut response) => {
                response.degraded |= route.degraded;
                if route.degraded
                    && matches!(
                        response.route_state.as_str(),
                        "local" | "local-wrapper" | "local-worker"
                    )
                {
                    response.route_state = route.route_state.clone();
                }
                if response.reason.is_none() {
                    response.reason = Some(format!("estimated latency {}ms", estimated_latency_ms));
                }
                response
            }
            Err(error) => self.handle_backend_failure(request, route, estimated_latency_ms, error),
        }
    }

    fn handle_backend_failure(
        &self,
        request: &RuntimeInferRequest,
        route: &RuntimeRouteResolveResponse,
        estimated_latency_ms: u64,
        error: BackendExecutionError,
    ) -> RuntimeInferResponse {
        if self.runtime_profile.cpu_fallback
            && route.selected_backend != "local-cpu"
            && error.fallback_backend == Some("local-cpu")
            && self.backend_is_executable("local-cpu", true)
        {
            let route_state = match error.class {
                BackendFailureClass::Timeout => "timeout-fallback-local-cpu",
                _ => "backend-fallback-local-cpu",
            };

            return self.fallback_response(
                request,
                "local-cpu",
                estimated_latency_ms,
                route_state,
                error.reason,
                error.notes,
            );
        }

        let route_state = match error.class {
            BackendFailureClass::Timeout => "timeout-rejected".to_string(),
            BackendFailureClass::Unavailable if error.route_state == "remote-disabled" => {
                "capability-rejected".to_string()
            }
            _ => error.route_state,
        };

        RuntimeInferResponse {
            backend_id: route.selected_backend.clone(),
            route_state,
            content: String::new(),
            degraded: route.degraded,
            rejected: true,
            reason: Some(error.reason),
            estimated_latency_ms: Some(estimated_latency_ms),
            provider_id: None,
            runtime_service_id: None,
            provider_status: None,
            queue_saturated: None,
            runtime_budget: None,
            notes: error.notes,
        }
    }

    fn ensure_executable_backend(&self, requested_backend: &str, allow_remote: bool) -> String {
        if self.backend_is_executable(requested_backend, allow_remote) {
            return requested_backend.to_string();
        }

        if self.runtime_profile.cpu_fallback
            && requested_backend != "local-cpu"
            && self.is_backend_allowed("local-cpu")
            && self.backend_is_executable("local-cpu", allow_remote)
        {
            return "local-cpu".to_string();
        }

        if let Some(backend_id) =
            self.first_alternate_executable_backend(requested_backend, allow_remote)
        {
            return backend_id;
        }

        self.first_allowed_backend_for_policy(allow_remote)
            .or_else(|| {
                self.backend_allowed_under_policy(requested_backend, allow_remote)
                    .then(|| requested_backend.to_string())
            })
            .unwrap_or_else(|| self.runtime_profile.default_backend.clone())
    }

    fn first_alternate_executable_backend(
        &self,
        requested_backend: &str,
        allow_remote: bool,
    ) -> Option<String> {
        let mut candidates = Vec::new();
        if self.runtime_profile.default_backend != requested_backend
            && self.runtime_profile.default_backend != "local-cpu"
        {
            candidates.push(self.runtime_profile.default_backend.as_str());
        }
        for backend_id in &self.runtime_profile.allowed_backends {
            let backend_id = backend_id.as_str();
            if backend_id == requested_backend
                || backend_id == "local-cpu"
                || candidates.contains(&backend_id)
            {
                continue;
            }
            candidates.push(backend_id);
        }

        candidates
            .into_iter()
            .find(|backend_id| self.backend_is_executable(backend_id, allow_remote))
            .map(str::to_string)
    }

    fn first_allowed_backend_for_policy(&self, allow_remote: bool) -> Option<String> {
        if self.backend_is_executable(&self.runtime_profile.default_backend, allow_remote) {
            return Some(self.runtime_profile.default_backend.clone());
        }

        self.runtime_profile
            .allowed_backends
            .iter()
            .find(|backend_id| self.backend_is_executable(backend_id, allow_remote))
            .cloned()
    }

    fn backend_is_executable(&self, backend_id: &str, allow_remote: bool) -> bool {
        if !self.backend_allowed_under_policy(backend_id, allow_remote) {
            return false;
        }

        crate::backend::readiness(backend_id, &self.backend_commands)
            .map(|readiness| readiness.is_available())
            .unwrap_or(false)
    }

    fn backend_allowed_under_policy(&self, backend_id: &str, allow_remote: bool) -> bool {
        self.is_backend_allowed(backend_id) && (allow_remote || backend_id != "attested-remote")
    }

    fn is_backend_allowed(&self, backend_id: &str) -> bool {
        self.runtime_profile
            .allowed_backends
            .iter()
            .any(|item| item == backend_id)
    }

    fn non_executable_backend_reason(&self, backend_id: &str, allow_remote: bool) -> String {
        if !self.is_backend_allowed(backend_id) {
            return format!("{} is not allowed by runtime profile", backend_id);
        }
        if backend_id == "attested-remote" && !allow_remote {
            return "attested-remote is disallowed for this request".to_string();
        }

        crate::backend::readiness(backend_id, &self.backend_commands)
            .map(|readiness| readiness.reason)
            .unwrap_or_else(|| "requested backend is not executable".to_string())
    }

    fn fallback_response(
        &self,
        request: &RuntimeInferRequest,
        backend_id: &str,
        estimated_latency_ms: u64,
        route_state: &str,
        reason: String,
        failure_notes: Vec<String>,
    ) -> RuntimeInferResponse {
        match crate::backend::execute(
            backend_id,
            request,
            estimated_latency_ms,
            self.runtime_profile.timeout_ms,
            &self.backend_commands,
        ) {
            Ok(mut response) => {
                response.degraded = true;
                response.route_state = route_state.to_string();
                response.reason = Some(reason);
                response.notes.extend(failure_notes);
                return response;
            }
            Err(error) => RuntimeInferResponse {
                backend_id: backend_id.to_string(),
                route_state: "fallback-failed".to_string(),
                content: String::new(),
                degraded: true,
                rejected: true,
                reason: Some(format!(
                    "{}; fallback execution also failed: {}",
                    reason, error.reason
                )),
                estimated_latency_ms: Some(estimated_latency_ms),
                provider_id: None,
                runtime_service_id: None,
                provider_status: None,
                queue_saturated: None,
                runtime_budget: None,
                notes: failure_notes,
            },
        }
    }

    fn estimate_latency_ms(&self, request: &RuntimeInferRequest) -> u64 {
        if request.prompt.contains("#force-timeout") {
            return self.runtime_profile.timeout_ms + 1;
        }

        let prompt_cost = (request.prompt.chars().count() as u64).saturating_mul(4);
        let model_cost = request
            .model
            .as_ref()
            .map(|model| model.chars().count() as u64 * 3)
            .unwrap_or(0);

        60 + prompt_cost + model_cost
    }
}

fn merge_backend_commands(
    runtime_profile: &RuntimeProfile,
    mut commands: BackendCommands,
) -> BackendCommands {
    if commands.local_cpu.is_none() {
        commands.local_cpu = runtime_profile.backend_commands.get("local-cpu").cloned();
    }
    if commands.local_gpu.is_none() {
        commands.local_gpu = runtime_profile.backend_commands.get("local-gpu").cloned();
    }
    if commands.local_npu.is_none() {
        commands.local_npu = runtime_profile.backend_commands.get("local-npu").cloned();
    }
    if commands.attested_remote.is_none() {
        commands.attested_remote = runtime_profile
            .backend_commands
            .get("attested-remote")
            .cloned();
    }
    commands
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    fn scheduler() -> Scheduler {
        Scheduler {
            runtime_profile: RuntimeProfile {
                profile_id: "default-local".to_string(),
                scope: "system".to_string(),
                default_backend: "local-gpu".to_string(),
                allowed_backends: vec![
                    "local-cpu".to_string(),
                    "local-gpu".to_string(),
                    "attested-remote".to_string(),
                ],
                local_model_pool: vec![],
                remote_model_pool: vec![],
                backend_worker_contract: Some("runtime-worker-v1".to_string()),
                backend_commands: BTreeMap::new(),
                managed_worker_commands: BTreeMap::new(),
                hardware_profile_managed_worker_commands: BTreeMap::new(),
                embedding_backend: "embed".to_string(),
                rerank_backend: "rerank".to_string(),
                cpu_fallback: true,
                memory_budget_mb: 1024,
                kv_cache_budget_mb: 256,
                timeout_ms: 30_000,
                max_concurrency: 2,
                max_parallel_models: 1,
                offload_policy: "manual-only".to_string(),
                degradation_policy: "fallback-local-cpu".to_string(),
                observability_level: "standard".to_string(),
            },
            route_profile: RouteProfile {
                profile_id: "default-route".to_string(),
                default_topology: "tool-calling".to_string(),
                allowed_topologies: vec![],
                router_stack: vec![],
                semantic_router_enabled: true,
                llm_router_enabled: true,
                cost_router_enabled: true,
                provider_preference: "structured-first".to_string(),
                prefer_local: true,
                prefer_structured_interface: true,
                allow_gui_fallback: "manual-only".to_string(),
                iteration_cap: 8,
                tool_call_cap: 12,
                replan_cap: 2,
                escalation_threshold: "high".to_string(),
                human_handoff_policy: "required".to_string(),
            },
            backend_commands: BackendCommands::default(),
        }
    }

    fn temp_profile_dir(name: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time")
            .as_nanos();
        std::env::temp_dir().join(format!("aios-runtimed-{name}-{suffix}"))
    }

    fn write_profiles(
        runtime_profile: &str,
        route_profile: &str,
    ) -> anyhow::Result<(PathBuf, PathBuf, PathBuf)> {
        let root = temp_profile_dir("profiles");
        fs::create_dir_all(&root)?;
        let runtime_profile_path = root.join("runtime-profile.yaml");
        let route_profile_path = root.join("route-profile.yaml");
        fs::write(&runtime_profile_path, runtime_profile)?;
        fs::write(&route_profile_path, route_profile)?;
        Ok((root, runtime_profile_path, route_profile_path))
    }

    #[test]
    fn resolve_falls_back_to_cpu_when_optional_backend_is_unavailable() {
        let response = scheduler().resolve(&RuntimeRouteResolveRequest {
            preferred_backend: Some("local-gpu".to_string()),
            allow_remote: false,
        });
        assert_eq!(response.selected_backend, "local-cpu");
        assert!(response.degraded);
    }

    #[test]
    fn resolve_blocks_remote_when_allow_remote_is_false() {
        let mut scheduler = scheduler();
        scheduler.runtime_profile.default_backend = "attested-remote".to_string();
        scheduler.backend_commands.attested_remote =
            Some("http://127.0.0.1:8081/infer".to_string());

        let response = scheduler.resolve(&RuntimeRouteResolveRequest {
            preferred_backend: None,
            allow_remote: false,
        });
        assert_eq!(response.selected_backend, "local-cpu");
        assert!(response.reason.contains("attested-remote is disallowed"));
    }

    #[test]
    fn resolve_uses_alternate_local_backend_when_cpu_fallback_is_disabled() {
        let mut scheduler = scheduler();
        scheduler.runtime_profile.cpu_fallback = false;
        scheduler.runtime_profile.allowed_backends =
            vec!["local-gpu".to_string(), "local-npu".to_string()];
        scheduler.backend_commands.local_npu = Some("echo configured".to_string());

        let response = scheduler.resolve(&RuntimeRouteResolveRequest {
            preferred_backend: Some("local-gpu".to_string()),
            allow_remote: false,
        });

        assert_eq!(response.selected_backend, "local-npu");
        assert!(response.degraded);
        assert!(response.reason.contains("no supported gpu device detected"));
    }

    #[test]
    fn resolve_uses_local_backend_when_remote_is_blocked_and_cpu_fallback_is_disabled() {
        let mut scheduler = scheduler();
        scheduler.runtime_profile.cpu_fallback = false;
        scheduler.runtime_profile.default_backend = "attested-remote".to_string();
        scheduler.runtime_profile.allowed_backends =
            vec!["attested-remote".to_string(), "local-gpu".to_string()];
        scheduler.backend_commands.attested_remote =
            Some("http://127.0.0.1:8081/infer".to_string());
        scheduler.backend_commands.local_gpu = Some("echo configured".to_string());

        let response = scheduler.resolve(&RuntimeRouteResolveRequest {
            preferred_backend: None,
            allow_remote: false,
        });

        assert_eq!(response.selected_backend, "local-gpu");
        assert!(response.degraded);
        assert!(response.reason.contains("attested-remote is disallowed"));
    }

    #[test]
    fn timeout_fallback_uses_cpu_route_state() {
        let mut scheduler = scheduler();
        scheduler.backend_commands.local_gpu = Some("echo configured".to_string());
        let response = scheduler.infer(&RuntimeInferRequest {
            session_id: "session".to_string(),
            task_id: "task".to_string(),
            prompt: "force fallback #force-timeout".to_string(),
            model: Some("smoke-model".to_string()),
            execution_token: None,
            preferred_backend: None,
        });
        assert_eq!(response.backend_id, "local-cpu");
        assert_eq!(response.route_state, "timeout-fallback-local-cpu");
        assert!(response.degraded);
    }

    #[test]
    fn infer_uses_inline_local_cpu_worker_when_gpu_is_not_available() {
        let response = scheduler().infer(&RuntimeInferRequest {
            session_id: "session".to_string(),
            task_id: "task-inline".to_string(),
            prompt: "Summarize runtime status".to_string(),
            model: Some("smoke-model".to_string()),
            execution_token: None,
            preferred_backend: None,
        });

        assert_eq!(response.backend_id, "local-cpu");
        assert_eq!(response.route_state, "degraded-local");
        assert!(response.degraded);
        assert!(response
            .content
            .contains("local-cpu worker completed task task-inline"));
        assert_eq!(
            response.reason.as_deref(),
            Some("local-cpu built-in worker executed request")
        );
    }

    #[test]
    fn resolve_falls_back_to_cpu_when_gpu_unix_worker_socket_is_missing() {
        let mut scheduler = scheduler();
        scheduler.backend_commands.local_gpu =
            Some("unix:///tmp/aios-runtimed-missing-gpu.sock".to_string());

        let response = scheduler.resolve(&RuntimeRouteResolveRequest {
            preferred_backend: Some("local-gpu".to_string()),
            allow_remote: false,
        });

        assert_eq!(response.selected_backend, "local-cpu");
        assert!(response.degraded);
    }

    #[test]
    fn load_rejects_runtime_profile_with_invalid_offload_policy() {
        let runtime_profile = r#"
profile_id: default-local
scope: system
default_backend: local-cpu
allowed_backends:
  - local-cpu
local_model_pool:
  - qwen-local-14b
remote_model_pool:
  - gpt-4.1
embedding_backend: local-embedding
rerank_backend: local-reranker
cpu_fallback: true
memory_budget_mb: 6144
kv_cache_budget_mb: 2048
timeout_ms: 30000
max_concurrency: 4
max_parallel_models: 2
offload_policy: invalid-policy
degradation_policy: fallback-local-cpu
observability_level: standard
"#;
        let route_profile = r#"
profile_id: default-route
default_topology: tool-calling
allowed_topologies:
  - direct
  - tool-calling
router_stack:
  - rule
semantic_router_enabled: true
llm_router_enabled: true
cost_router_enabled: true
provider_preference: structured-first
prefer_local: true
prefer_structured_interface: true
allow_gui_fallback: manual-only
iteration_cap: 8
tool_call_cap: 12
replan_cap: 2
escalation_threshold: high-risk-or-low-confidence
human_handoff_policy: required-on-ambiguous-high-risk
"#;
        let (root, runtime_profile_path, route_profile_path) =
            write_profiles(runtime_profile, route_profile).expect("write test profiles");

        let error = Scheduler::load(
            &runtime_profile_path,
            &route_profile_path,
            BackendCommands::default(),
        )
        .expect_err("invalid runtime profile should be rejected");

        let error_text = error.to_string();
        assert!(error_text.contains("failed schema validation"));
        assert!(error_text.contains("runtime-profile.schema.json"));
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn load_rejects_route_profile_with_invalid_topology() {
        let runtime_profile = r#"
profile_id: default-local
scope: system
default_backend: local-cpu
allowed_backends:
  - local-cpu
local_model_pool:
  - qwen-local-14b
remote_model_pool:
  - gpt-4.1
embedding_backend: local-embedding
rerank_backend: local-reranker
cpu_fallback: true
memory_budget_mb: 6144
kv_cache_budget_mb: 2048
timeout_ms: 30000
max_concurrency: 4
max_parallel_models: 2
offload_policy: manual-only
degradation_policy: fallback-local-cpu
observability_level: standard
"#;
        let route_profile = r#"
profile_id: default-route
default_topology: invalid-topology
allowed_topologies:
  - direct
  - tool-calling
router_stack:
  - rule
semantic_router_enabled: true
llm_router_enabled: true
cost_router_enabled: true
provider_preference: structured-first
prefer_local: true
prefer_structured_interface: true
allow_gui_fallback: manual-only
iteration_cap: 8
tool_call_cap: 12
replan_cap: 2
escalation_threshold: high-risk-or-low-confidence
human_handoff_policy: required-on-ambiguous-high-risk
"#;
        let (root, runtime_profile_path, route_profile_path) =
            write_profiles(runtime_profile, route_profile).expect("write test profiles");

        let error = Scheduler::load(
            &runtime_profile_path,
            &route_profile_path,
            BackendCommands::default(),
        )
        .expect_err("invalid route profile should be rejected");

        let error_text = error.to_string();
        assert!(error_text.contains("failed schema validation"));
        assert!(error_text.contains("route-profile.schema.json"));
        fs::remove_dir_all(root).ok();
    }
}
