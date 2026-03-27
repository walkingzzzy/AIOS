use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub mod methods {
    pub const SYSTEM_HEALTH_GET: &str = "system.health.get";
    pub const SYSTEM_CONTRACT_GET: &str = "system.contract.get";

    pub const UPDATE_CHECK: &str = "update.check";
    pub const UPDATE_APPLY: &str = "update.apply";
    pub const UPDATE_HEALTH_GET: &str = "update.health.get";
    pub const UPDATE_ROLLBACK: &str = "update.rollback";
    pub const RECOVERY_SURFACE_GET: &str = "recovery.surface.get";
    pub const RECOVERY_BUNDLE_EXPORT: &str = "recovery.bundle.export";

    pub const DEVICE_CAPTURE_REQUEST: &str = "device.capture.request";
    pub const DEVICE_CAPTURE_STOP: &str = "device.capture.stop";
    pub const DEVICE_STATE_GET: &str = "device.state.get";
    pub const DEVICE_OBJECT_NORMALIZE: &str = "device.object.normalize";
    pub const DEVICE_RETENTION_APPLY: &str = "device.retention.apply";

    pub const SESSION_CREATE: &str = "session.create";
    pub const SESSION_LIST: &str = "session.list";
    pub const SESSION_RESUME: &str = "session.resume";
    pub const SESSION_CLOSE: &str = "session.close";
    pub const SESSION_EVIDENCE_GET: &str = "session.evidence.get";
    pub const SESSION_EVIDENCE_EXPORT: &str = "session.evidence.export";
    pub const TASK_CREATE: &str = "task.create";
    pub const TASK_GET: &str = "task.get";
    pub const TASK_LIST: &str = "task.list";
    pub const TASK_STATE_UPDATE: &str = "task.state.update";
    pub const TASK_EVENTS_LIST: &str = "task.events.list";
    pub const TASK_PLAN_PUT: &str = "task.plan.put";
    pub const TASK_PLAN_GET: &str = "task.plan.get";

    pub const MEMORY_READ: &str = "memory.read";
    pub const MEMORY_WRITE: &str = "memory.write";
    pub const MEMORY_EPISODIC_APPEND: &str = "memory.episodic.append";
    pub const MEMORY_EPISODIC_LIST: &str = "memory.episodic.list";
    pub const MEMORY_SEMANTIC_PUT: &str = "memory.semantic.put";
    pub const MEMORY_SEMANTIC_LIST: &str = "memory.semantic.list";
    pub const MEMORY_PROCEDURAL_PUT: &str = "memory.procedural.put";
    pub const MEMORY_PROCEDURAL_LIST: &str = "memory.procedural.list";

    pub const POLICY_EVALUATE: &str = "policy.evaluate";
    pub const POLICY_AUDIT_QUERY: &str = "policy.audit.query";
    pub const POLICY_AUDIT_EXPORT: &str = "policy.audit.export";
    pub const POLICY_TOKEN_ISSUE: &str = "policy.token.issue";
    pub const POLICY_TOKEN_VERIFY: &str = "policy.token.verify";

    pub const APPROVAL_CREATE: &str = "approval.create";
    pub const APPROVAL_GET: &str = "approval.get";
    pub const APPROVAL_LIST: &str = "approval.list";
    pub const APPROVAL_RESOLVE: &str = "approval.resolve";

    pub const RUNTIME_BACKEND_LIST: &str = "runtime.backend.list";
    pub const RUNTIME_ROUTE_RESOLVE: &str = "runtime.route.resolve";
    pub const RUNTIME_INFER_SUBMIT: &str = "runtime.infer.submit";
    pub const RUNTIME_EMBED_VECTORIZE: &str = "runtime.embed.vectorize";
    pub const RUNTIME_RERANK_SCORE: &str = "runtime.rerank.score";
    pub const RUNTIME_QUEUE_GET: &str = "runtime.queue.get";
    pub const RUNTIME_BUDGET_GET: &str = "runtime.budget.get";
    pub const RUNTIME_EVENTS_GET: &str = "runtime.events.get";
    pub const RUNTIME_OBSERVABILITY_EXPORT: &str = "runtime.observability.export";

    pub const PROVIDER_REGISTER: &str = "provider.register";
    pub const PROVIDER_UNREGISTER: &str = "provider.unregister";
    pub const PROVIDER_DISCOVER: &str = "provider.discover";
    pub const PROVIDER_RESOLVE_CAPABILITY: &str = "provider.resolve_capability";
    pub const PROVIDER_GET_DESCRIPTOR: &str = "provider.get_descriptor";
    pub const PROVIDER_HEALTH_GET: &str = "provider.health.get";
    pub const PROVIDER_HEALTH_REPORT: &str = "provider.health.report";
    pub const PROVIDER_DISABLE: &str = "provider.disable";
    pub const PROVIDER_ENABLE: &str = "provider.enable";

    pub const PROVIDER_FS_OPEN: &str = "provider.fs.open";
    pub const SYSTEM_FILE_BULK_DELETE: &str = "system.file.bulk_delete";
    pub const SYSTEM_INTENT_EXECUTE: &str = "system.intent.execute";
    pub const DEVICE_METADATA_GET: &str = "device.metadata.get";
    pub const SHELL_WINDOW_FOCUS: &str = "shell.window.focus";
    pub const SHELL_NOTIFICATION_OPEN: &str = "shell.notification.open";
    pub const SHELL_OPERATOR_AUDIT_OPEN: &str = "shell.operator-audit.open";
    pub const SHELL_PANEL_EVENTS_LIST: &str = "shell.panel-events.list";

    pub const PORTAL_HANDLE_ISSUE: &str = "portal.handle.issue";
    pub const PORTAL_HANDLE_LOOKUP: &str = "portal.handle.lookup";
    pub const PORTAL_HANDLE_REVOKE: &str = "portal.handle.revoke";
    pub const PORTAL_HANDLE_LIST: &str = "portal.handle.list";

    pub const AGENT_INTENT_SUBMIT: &str = "agent.intent.submit";
    pub const AGENT_TASK_GET: &str = "agent.task.get";
    pub const AGENT_TASK_LIST: &str = "agent.task.list";
    pub const AGENT_TASK_CREATE: &str = "agent.task.create";
    pub const AGENT_TASK_STATE_UPDATE: &str = "agent.task.state.update";
    pub const AGENT_TASK_EVENTS_LIST: &str = "agent.task.events.list";
    pub const AGENT_TASK_PLAN_PUT: &str = "agent.task.plan.put";
    pub const AGENT_TASK_PLAN_GET: &str = "agent.task.plan.get";
    pub const AGENT_TASK_PLAN: &str = "agent.task.plan";
    pub const AGENT_TASK_REPLAN: &str = "agent.task.replan";
    pub const AGENT_TASK_RESUME: &str = "agent.task.resume";
    pub const AGENT_SESSION_CREATE: &str = "agent.session.create";
    pub const AGENT_SESSION_LIST: &str = "agent.session.list";
    pub const AGENT_SESSION_RESUME: &str = "agent.session.resume";
    pub const AGENT_SESSION_EVIDENCE_GET: &str = "agent.session.evidence.get";
    pub const AGENT_SESSION_EVIDENCE_EXPORT: &str = "agent.session.evidence.export";
    pub const AGENT_PROVIDER_DISCOVER: &str = "agent.provider.discover";
    pub const AGENT_PROVIDER_RESOLVE_CAPABILITY: &str = "agent.provider.resolve_capability";
    pub const AGENT_PROVIDER_GET_DESCRIPTOR: &str = "agent.provider.get_descriptor";
    pub const AGENT_PROVIDER_HEALTH_GET: &str = "agent.provider.health.get";
    pub const AGENT_PROVIDER_HEALTH_REPORT: &str = "agent.provider.health.report";
    pub const AGENT_PROVIDER_DISABLE: &str = "agent.provider.disable";
    pub const AGENT_PROVIDER_ENABLE: &str = "agent.provider.enable";
    pub const AGENT_PROVIDER_REGISTER: &str = "agent.provider.register";
    pub const AGENT_PROVIDER_UNREGISTER: &str = "agent.provider.unregister";
    pub const AGENT_APPROVAL_CREATE: &str = "agent.approval.create";
    pub const AGENT_APPROVAL_GET: &str = "agent.approval.get";
    pub const AGENT_APPROVAL_LIST: &str = "agent.approval.list";
    pub const AGENT_APPROVAL_RESOLVE: &str = "agent.approval.resolve";
    pub const AGENT_PORTAL_HANDLE_ISSUE: &str = "agent.portal.handle.issue";
    pub const AGENT_PORTAL_HANDLE_REVOKE: &str = "agent.portal.handle.revoke";
    pub const AGENT_PORTAL_HANDLE_LIST: &str = "agent.portal.handle.list";
    pub const AGENT_POLICY_TOKEN_ISSUE: &str = "agent.policy.token.issue";
    pub const AGENT_POLICY_TOKEN_VERIFY: &str = "agent.policy.token.verify";
    pub const AGENT_AUDIT_QUERY: &str = "agent.audit.query";
    pub const AGENT_AUDIT_EXPORT: &str = "agent.audit.export";
}

pub const SHARED_CONTRACT_VERSION: &str = "1.0.0";
pub const SHARED_COMPATIBILITY_EPOCH: &str = "2026-Q1";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractMethodRecord {
    pub method: String,
    pub stability: String,
    pub introduced_in: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractSchemaRecord {
    pub schema_ref: String,
    pub stability: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractManifest {
    pub contract_version: String,
    pub compatibility_epoch: String,
    pub methods: Vec<ContractMethodRecord>,
    pub schemas: Vec<ContractSchemaRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceContractResponse {
    pub service_id: String,
    pub contract: ContractManifest,
}

pub fn shared_contract_manifest() -> ContractManifest {
    let introduced_in = SHARED_CONTRACT_VERSION.to_string();
    let methods = vec![
        methods::SYSTEM_HEALTH_GET,
        methods::SYSTEM_CONTRACT_GET,
        methods::SESSION_CREATE,
        methods::SESSION_LIST,
        methods::SESSION_RESUME,
        methods::SESSION_CLOSE,
        methods::SESSION_EVIDENCE_GET,
        methods::SESSION_EVIDENCE_EXPORT,
        methods::TASK_CREATE,
        methods::TASK_GET,
        methods::TASK_LIST,
        methods::TASK_STATE_UPDATE,
        methods::TASK_EVENTS_LIST,
        methods::TASK_PLAN_PUT,
        methods::TASK_PLAN_GET,
        methods::MEMORY_READ,
        methods::MEMORY_WRITE,
        methods::MEMORY_EPISODIC_APPEND,
        methods::MEMORY_EPISODIC_LIST,
        methods::MEMORY_SEMANTIC_PUT,
        methods::MEMORY_SEMANTIC_LIST,
        methods::MEMORY_PROCEDURAL_PUT,
        methods::MEMORY_PROCEDURAL_LIST,
        methods::POLICY_EVALUATE,
        methods::POLICY_AUDIT_QUERY,
        methods::POLICY_AUDIT_EXPORT,
        methods::POLICY_TOKEN_ISSUE,
        methods::POLICY_TOKEN_VERIFY,
        methods::APPROVAL_CREATE,
        methods::APPROVAL_GET,
        methods::APPROVAL_LIST,
        methods::APPROVAL_RESOLVE,
        methods::RUNTIME_BACKEND_LIST,
        methods::RUNTIME_ROUTE_RESOLVE,
        methods::RUNTIME_INFER_SUBMIT,
        methods::RUNTIME_EMBED_VECTORIZE,
        methods::RUNTIME_RERANK_SCORE,
        methods::RUNTIME_QUEUE_GET,
        methods::RUNTIME_BUDGET_GET,
        methods::RUNTIME_EVENTS_GET,
        methods::RUNTIME_OBSERVABILITY_EXPORT,
        methods::PROVIDER_DISCOVER,
        methods::PROVIDER_RESOLVE_CAPABILITY,
        methods::PROVIDER_GET_DESCRIPTOR,
        methods::PROVIDER_HEALTH_GET,
        methods::AGENT_INTENT_SUBMIT,
        methods::AGENT_TASK_GET,
        methods::AGENT_TASK_LIST,
        methods::AGENT_TASK_CREATE,
        methods::AGENT_TASK_STATE_UPDATE,
        methods::AGENT_TASK_EVENTS_LIST,
        methods::AGENT_TASK_PLAN_PUT,
        methods::AGENT_TASK_PLAN_GET,
        methods::AGENT_TASK_PLAN,
        methods::AGENT_TASK_REPLAN,
        methods::AGENT_TASK_RESUME,
        methods::AGENT_SESSION_CREATE,
        methods::AGENT_SESSION_LIST,
        methods::AGENT_SESSION_RESUME,
        methods::AGENT_SESSION_EVIDENCE_GET,
        methods::AGENT_SESSION_EVIDENCE_EXPORT,
        methods::AGENT_PROVIDER_DISCOVER,
        methods::AGENT_PROVIDER_RESOLVE_CAPABILITY,
        methods::AGENT_PROVIDER_GET_DESCRIPTOR,
        methods::AGENT_PROVIDER_HEALTH_GET,
        methods::AGENT_PROVIDER_HEALTH_REPORT,
        methods::AGENT_PROVIDER_DISABLE,
        methods::AGENT_PROVIDER_ENABLE,
        methods::AGENT_PROVIDER_REGISTER,
        methods::AGENT_PROVIDER_UNREGISTER,
        methods::AGENT_APPROVAL_CREATE,
        methods::AGENT_APPROVAL_GET,
        methods::AGENT_APPROVAL_LIST,
        methods::AGENT_APPROVAL_RESOLVE,
        methods::AGENT_PORTAL_HANDLE_ISSUE,
        methods::AGENT_PORTAL_HANDLE_REVOKE,
        methods::AGENT_PORTAL_HANDLE_LIST,
        methods::AGENT_POLICY_TOKEN_ISSUE,
        methods::AGENT_POLICY_TOKEN_VERIFY,
        methods::AGENT_AUDIT_QUERY,
        methods::AGENT_AUDIT_EXPORT,
    ]
    .into_iter()
    .map(|method| ContractMethodRecord {
        method: method.to_string(),
        stability: "frozen".to_string(),
        introduced_in: introduced_in.clone(),
    })
    .collect::<Vec<_>>();

    let schemas = vec![
        "aios/policy/schemas/execution-token.schema.json",
        "aios/runtime/schemas/runtime-profile.schema.json",
        "aios/runtime/schemas/route-profile.schema.json",
        "aios/observability/schemas/audit-event.schema.json",
        "aios/observability/schemas/trace-event.schema.json",
    ]
    .into_iter()
    .map(|schema_ref| ContractSchemaRecord {
        schema_ref: schema_ref.to_string(),
        stability: "frozen".to_string(),
    })
    .collect::<Vec<_>>();

    ContractManifest {
        contract_version: SHARED_CONTRACT_VERSION.to_string(),
        compatibility_epoch: SHARED_COMPATIBILITY_EPOCH.to_string(),
        methods,
        schemas,
    }
}

fn default_execution_location() -> String {
    "local".to_string()
}

fn default_compat_permission_schema_version() -> String {
    "1.0.0".to_string()
}

fn default_task_state() -> String {
    "planned".to_string()
}

fn default_approval_status() -> String {
    "pending".to_string()
}

fn default_provider_health_status() -> String {
    "available".to_string()
}

fn default_query_limit() -> u32 {
    50
}

fn default_query_reverse() -> bool {
    true
}

fn default_true() -> bool {
    true
}

fn default_runtime_backend_health_state() -> String {
    "unknown".to_string()
}
fn default_portal_revocable() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthResponse {
    pub service_id: String,
    pub status: String,
    pub version: String,
    pub started_at: String,
    pub socket_path: String,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UpdateCheckRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub channel: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub current_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateCheckResponse {
    pub service_id: String,
    pub update_stack: String,
    pub configured_channel: String,
    pub current_version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub next_version: Option<String>,
    pub status: String,
    #[serde(default)]
    pub artifacts: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UpdateApplyRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_version: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default)]
    pub dry_run: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateApplyResponse {
    pub service_id: String,
    pub status: String,
    pub deployment_status: String,
    pub dry_run: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_version: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery_ref: Option<String>,
    #[serde(default)]
    pub staged_artifacts: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UpdateHealthGetRequest {}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateHealthGetResponse {
    pub service_id: String,
    pub overall_status: String,
    pub rollback_ready: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_check_at: Option<String>,
    #[serde(default)]
    pub recovery_points: Vec<String>,
    #[serde(default)]
    pub diagnostic_bundles: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UpdateRollbackRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default)]
    pub dry_run: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateRollbackResponse {
    pub service_id: String,
    pub status: String,
    pub deployment_status: String,
    pub dry_run: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rollback_target: Option<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RecoverySurfaceGetRequest {}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecoverySurfaceGetResponse {
    pub service_id: String,
    pub generated_at: String,
    pub deployment_status: String,
    pub overall_status: String,
    pub rollback_ready: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub current_slot: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_good_slot: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub staged_slot: Option<String>,
    #[serde(default)]
    pub recovery_points: Vec<String>,
    #[serde(default)]
    pub diagnostic_bundles: Vec<String>,
    #[serde(default)]
    pub available_actions: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RecoveryBundleExportRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecoveryBundleExportResponse {
    pub service_id: String,
    pub bundle_id: String,
    pub bundle_path: String,
    pub created_at: String,
    pub deployment_status: String,
    #[serde(default)]
    pub recovery_points: Vec<String>,
    #[serde(default)]
    pub diagnostic_bundles: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCapabilityDescriptor {
    pub modality: String,
    pub available: bool,
    pub conditional: bool,
    pub source_backend: String,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DeviceStateGetRequest {}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCaptureRecord {
    pub capture_id: String,
    pub modality: String,
    pub status: String,
    pub continuous: bool,
    pub started_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stopped_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stopped_reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    pub taint_summary: String,
    #[serde(default)]
    pub tainted: bool,
    pub source_backend: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preview_object_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adapter_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adapter_execution_path: Option<String>,
    #[serde(default)]
    pub approval_required: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_source: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub indicator_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub retention_class: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub retention_ttl_seconds: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceBackendStatus {
    pub modality: String,
    pub backend: String,
    pub available: bool,
    pub readiness: String,
    #[serde(default)]
    pub details: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceBackendSummary {
    pub overall_status: String,
    #[serde(default)]
    pub status_count: u32,
    #[serde(default)]
    pub available_status_count: u32,
    #[serde(default)]
    pub adapter_count: u32,
    #[serde(default)]
    pub attention_count: u32,
    #[serde(default)]
    pub continuous_collector_count: u32,
    #[serde(default)]
    pub ui_tree_support_route_count: u32,
    #[serde(default)]
    pub ui_tree_support_ready_count: u32,
    #[serde(default)]
    pub ui_tree_snapshot_present: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ui_tree_capture_mode: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ui_tree_current_support: Option<String>,
    #[serde(default)]
    pub readiness_summary: BTreeMap<String, u32>,
    #[serde(default)]
    pub evidence_artifact_count: u32,
    #[serde(default)]
    pub evidence_present_count: u32,
    #[serde(default)]
    pub evidence_missing_count: u32,
    #[serde(default)]
    pub evidence_baselines: Vec<String>,
}

impl Default for DeviceBackendSummary {
    fn default() -> Self {
        Self {
            overall_status: "unknown".to_string(),
            status_count: 0,
            available_status_count: 0,
            adapter_count: 0,
            attention_count: 0,
            continuous_collector_count: 0,
            ui_tree_support_route_count: 0,
            ui_tree_support_ready_count: 0,
            ui_tree_snapshot_present: false,
            ui_tree_capture_mode: None,
            ui_tree_current_support: None,
            readiness_summary: BTreeMap::new(),
            evidence_artifact_count: 0,
            evidence_present_count: 0,
            evidence_missing_count: 0,
            evidence_baselines: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UiTreeSupportMatrixEntry {
    pub environment_id: String,
    pub available: bool,
    pub readiness: String,
    #[serde(default)]
    pub current: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub desktop_environment: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_type: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adapter_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_path: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stability: Option<String>,
    #[serde(default)]
    pub limitations: Vec<String>,
    #[serde(default)]
    pub evidence: Vec<String>,
    #[serde(default)]
    pub details: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCaptureAdapterPlan {
    pub modality: String,
    pub backend: String,
    pub adapter_id: String,
    pub execution_path: String,
    pub preview_object_kind: String,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceContinuousCollectorStatus {
    pub capture_id: String,
    pub modality: String,
    pub backend: String,
    pub collector_mode: String,
    pub status: String,
    pub updated_at: String,
    #[serde(default)]
    pub sample_count: u64,
    #[serde(default)]
    pub details: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceStateGetResponse {
    pub service_id: String,
    #[serde(default)]
    pub capabilities: Vec<DeviceCapabilityDescriptor>,
    #[serde(default)]
    pub active_captures: Vec<DeviceCaptureRecord>,
    #[serde(default)]
    pub backend_statuses: Vec<DeviceBackendStatus>,
    #[serde(default)]
    pub capture_adapters: Vec<DeviceCaptureAdapterPlan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ui_tree_snapshot: Option<Value>,
    #[serde(default)]
    pub continuous_collectors: Vec<DeviceContinuousCollectorStatus>,
    #[serde(default)]
    pub backend_summary: DeviceBackendSummary,
    #[serde(default)]
    pub ui_tree_support_matrix: Vec<UiTreeSupportMatrixEntry>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCaptureRequest {
    pub modality: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    #[serde(default)]
    pub continuous: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub window_ref: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_device: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCaptureResponse {
    pub capture: DeviceCaptureRecord,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preview_object: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCaptureStopRequest {
    pub capture_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCaptureStopResponse {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capture: Option<DeviceCaptureRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceObjectNormalizeRequest {
    pub modality: String,
    pub payload: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_backend: Option<String>,
    #[serde(default)]
    pub user_visible: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceObjectNormalizeResponse {
    pub object_kind: String,
    pub normalized: Value,
    pub taint_summary: String,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceRetentionApplyRequest {
    pub object_kind: String,
    pub object_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub retention_class: Option<String>,
    #[serde(default)]
    pub continuous: bool,
    #[serde(default)]
    pub contains_sensitive_data: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceRetentionApplyResponse {
    pub object_id: String,
    pub retention_class: String,
    pub expires_in_seconds: u64,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionCreateRequest {
    pub user_id: String,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionResumeRequest {
    pub session_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionCloseRequest {
    pub session_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionListRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionEvidenceRequest {
    pub session_id: String,
    #[serde(default = "default_query_limit")]
    pub limit: u32,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionEvidenceExportRequest {
    pub session_id: String,
    #[serde(default = "default_query_limit")]
    pub limit: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionRecord {
    pub session_id: String,
    pub user_id: String,
    pub created_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_resumed_at: Option<String>,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecoveryRef {
    pub recovery_id: String,
    pub session_id: String,
    pub status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub latest_task_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub latest_task_state: Option<String>,
    #[serde(default)]
    pub resumable_task_ids: Vec<String>,
    #[serde(default)]
    pub pending_task_ids: Vec<String>,
    #[serde(default)]
    pub approved_task_ids: Vec<String>,
    #[serde(default)]
    pub portal_handle_ids: Vec<String>,
    #[serde(default)]
    pub working_memory_refs: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskCreateRequest {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default = "default_task_state")]
    pub state: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskGetRequest {
    pub task_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskListRequest {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub state: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskStateUpdateRequest {
    pub task_id: String,
    pub new_state: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskEventListRequest {
    pub task_id: String,
    #[serde(default = "default_query_limit")]
    pub limit: u32,
    #[serde(default = "default_query_reverse")]
    pub reverse: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskRecord {
    pub task_id: String,
    pub session_id: String,
    pub state: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionCreateResponse {
    pub session: SessionRecord,
    pub task: TaskRecord,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionListResponse {
    pub sessions: Vec<SessionRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionResumeResponse {
    pub session: SessionRecord,
    pub recovery: RecoveryRef,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionCloseResponse {
    pub session: SessionRecord,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionEvidenceResponse {
    pub session: SessionRecord,
    pub tasks: Vec<TaskRecord>,
    pub task_events: Vec<TaskEventRecord>,
    pub working_memory: Vec<WorkingMemoryRecord>,
    pub episodic_memory: Vec<EpisodicMemoryRecord>,
    pub semantic_memory: Vec<SemanticMemoryRecord>,
    pub procedural_memory: Vec<ProceduralMemoryRecord>,
    pub portal_handles: Vec<PortalHandleRecord>,
    pub recovery: RecoveryRef,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionEvidenceExportResponse {
    pub service_id: String,
    pub session_id: String,
    pub export_id: String,
    pub export_path: String,
    pub created_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery_status: Option<String>,
    pub task_count: u32,
    pub task_event_count: u32,
    pub working_memory_count: u32,
    pub episodic_memory_count: u32,
    pub semantic_memory_count: u32,
    pub procedural_memory_count: u32,
    pub portal_handle_count: u32,
    #[serde(default)]
    pub resumable_task_count: u32,
    #[serde(default)]
    pub pending_task_count: u32,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskCreateResponse {
    pub task: TaskRecord,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskListResponse {
    pub tasks: Vec<TaskRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskEventRecord {
    pub event_id: String,
    pub task_id: String,
    pub from_state: String,
    pub to_state: String,
    pub metadata: Value,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskEventListResponse {
    pub events: Vec<TaskEventRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskPlanPutRequest {
    pub task_id: String,
    pub plan: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskPlanGetRequest {
    pub task_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskPlanRecord {
    pub task_id: String,
    pub plan: Value,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyEvaluateRequest {
    pub user_id: String,
    pub session_id: String,
    pub task_id: String,
    pub capability_id: String,
    #[serde(default = "default_execution_location")]
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_hash: Option<String>,
    #[serde(default)]
    pub constraints: BTreeMap<String, Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub intent: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_summary: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyEvaluateResponse {
    pub decision: String,
    pub requires_approval: bool,
    pub reason: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_summary: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyEvaluateEnvelope {
    pub decision: PolicyEvaluateResponse,
    pub approval_lane: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_hint: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalCreateRequest {
    pub user_id: String,
    pub session_id: String,
    pub task_id: String,
    pub capability_id: String,
    pub approval_lane: String,
    #[serde(default = "default_execution_location")]
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_hash: Option<String>,
    #[serde(default)]
    pub constraints: BTreeMap<String, Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_summary: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_in_seconds: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalGetRequest {
    pub approval_ref: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalListRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalResolveRequest {
    pub approval_ref: String,
    pub status: String,
    pub resolver: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalRecord {
    pub approval_ref: String,
    pub user_id: String,
    pub session_id: String,
    pub task_id: String,
    pub capability_id: String,
    pub approval_lane: String,
    #[serde(default = "default_approval_status")]
    pub status: String,
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_hash: Option<String>,
    #[serde(default)]
    pub constraints: BTreeMap<String, Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_summary: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    pub created_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolved_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolver: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolution_reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalListResponse {
    pub approvals: Vec<ApprovalRecord>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AuditQueryRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capability_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decision: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_location: Option<String>,
    #[serde(default = "default_query_limit")]
    pub limit: u32,
    #[serde(default = "default_query_reverse")]
    pub reverse: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditRecord {
    pub audit_id: String,
    pub timestamp: String,
    pub user_id: String,
    pub session_id: String,
    pub task_id: String,
    pub capability_id: String,
    pub decision: String,
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub route_state: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_summary: Option<String>,
    pub result: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditQueryResponse {
    #[serde(default)]
    pub entries: Vec<AuditRecord>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditExportRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capability_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub decision: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_location: Option<String>,
    #[serde(default = "default_query_limit")]
    pub limit: u32,
    #[serde(default = "default_query_reverse")]
    pub reverse: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditExportResponse {
    pub service_id: String,
    pub export_id: String,
    pub export_path: String,
    pub created_at: String,
    pub entry_count: u32,
    #[serde(default)]
    pub session_count: u32,
    #[serde(default)]
    pub task_count: u32,
    #[serde(default)]
    pub approval_ref_count: u32,
    #[serde(default)]
    pub decision_count: u32,
    pub active_segment_path: String,
    pub index_path: String,
    pub archive_dir: String,
    pub archived_segment_count: u32,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceEventRecord {
    pub event_id: String,
    pub timestamp: String,
    pub source: String,
    pub kind: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    pub payload: Value,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TraceQueryRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub payload_equals: BTreeMap<String, Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub payload_contains: Option<String>,
    #[serde(default = "default_query_limit")]
    pub limit: u32,
    #[serde(default = "default_query_reverse")]
    pub reverse: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TraceQueryResponse {
    #[serde(default)]
    pub entries: Vec<TraceEventRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeObservabilityExportRequest {
    #[serde(flatten)]
    pub query: TraceQueryRequest,
    #[serde(default = "default_true")]
    pub include_runtime_events: bool,
    #[serde(default = "default_true")]
    pub include_observability: bool,
    #[serde(default = "default_true")]
    pub include_remote_audit: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

impl Default for RuntimeObservabilityExportRequest {
    fn default() -> Self {
        Self {
            query: TraceQueryRequest::default(),
            include_runtime_events: true,
            include_observability: true,
            include_remote_audit: true,
            reason: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeObservabilityExportResponse {
    pub service_id: String,
    pub export_id: String,
    pub export_path: String,
    pub created_at: String,
    pub runtime_event_count: u32,
    pub observability_count: u32,
    pub remote_audit_count: u32,
    pub backend_count: u32,
    #[serde(default)]
    pub correlated_session_count: u32,
    #[serde(default)]
    pub correlated_task_count: u32,
    #[serde(default)]
    pub artifact_count: u32,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenIssueRequest {
    pub user_id: String,
    pub session_id: String,
    pub task_id: String,
    pub capability_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
    #[serde(default)]
    pub constraints: BTreeMap<String, Value>,
    #[serde(default = "default_execution_location")]
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_summary: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionToken {
    pub user_id: String,
    pub session_id: String,
    pub task_id: String,
    pub capability_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_hash: Option<String>,
    pub expiry: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
    #[serde(default)]
    pub constraints: BTreeMap<String, Value>,
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub taint_summary: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenVerifyRequest {
    pub token: ExecutionToken,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_hash: Option<String>,
    #[serde(default)]
    pub consume: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenVerifyResponse {
    pub valid: bool,
    pub reason: String,
    #[serde(default)]
    pub consumed: bool,
    #[serde(default)]
    pub consume_applied: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeBackendDescriptor {
    pub backend_id: String,
    pub availability: String,
    pub activation: String,
    #[serde(default = "default_runtime_backend_health_state")]
    pub health_state: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub reason: String,
    #[serde(default)]
    pub managed: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback_backend: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub worker_contract: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub worker_state: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub command_source: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub socket_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeBackendEventPayload {
    pub event_phase: String,
    pub backend_id: String,
    pub resolved_backend: String,
    pub route_state: String,
    #[serde(default)]
    pub degraded: bool,
    #[serde(default)]
    pub rejected: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub requested_backend: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback_backend: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub estimated_latency_ms: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pending_queue: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub active_requests: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub queue_saturated: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_service_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub artifact_path: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRouteResolveRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preferred_backend: Option<String>,
    #[serde(default)]
    pub allow_remote: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRouteResolveResponse {
    pub selected_backend: String,
    pub route_state: String,
    pub degraded: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeInferRequest {
    pub session_id: String,
    pub task_id: String,
    pub prompt: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_token: Option<ExecutionToken>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preferred_backend: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeInferResponse {
    pub backend_id: String,
    pub route_state: String,
    pub content: String,
    pub degraded: bool,
    #[serde(default)]
    pub rejected: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub estimated_latency_ms: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_service_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub queue_saturated: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_budget: Option<RuntimeBudgetResponse>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeEmbedRequest {
    pub session_id: String,
    pub task_id: String,
    #[serde(default)]
    pub inputs: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_token: Option<ExecutionToken>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preferred_backend: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeEmbeddingRecord {
    pub input_index: usize,
    pub vector: Vec<f32>,
    #[serde(default)]
    pub text_length: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeEmbedResponse {
    pub backend_id: String,
    pub route_state: String,
    #[serde(default)]
    pub vector_dimension: u32,
    #[serde(default)]
    pub embeddings: Vec<RuntimeEmbeddingRecord>,
    #[serde(default)]
    pub degraded: bool,
    #[serde(default)]
    pub rejected: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_service_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub queue_saturated: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_budget: Option<RuntimeBudgetResponse>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRerankRequest {
    pub session_id: String,
    pub task_id: String,
    pub query: String,
    #[serde(default)]
    pub documents: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub top_k: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_token: Option<ExecutionToken>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preferred_backend: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRerankResult {
    pub document_index: usize,
    pub score: f32,
    pub document: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRerankResponse {
    pub backend_id: String,
    pub route_state: String,
    #[serde(default)]
    pub results: Vec<RuntimeRerankResult>,
    #[serde(default)]
    pub degraded: bool,
    #[serde(default)]
    pub rejected: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_service_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub queue_saturated: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_budget: Option<RuntimeBudgetResponse>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeQueueResponse {
    pub pending: usize,
    pub max_concurrency: u32,
    #[serde(default)]
    pub available_slots: u32,
    #[serde(default)]
    pub saturated: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeBudgetResponse {
    pub memory_budget_mb: u64,
    pub kv_cache_budget_mb: u64,
    pub max_concurrency: u32,
    pub max_parallel_models: u32,
    pub timeout_ms: u64,
    #[serde(default)]
    pub total_requests: u64,
    #[serde(default)]
    pub gpu_fallbacks: u64,
    #[serde(default)]
    pub active_requests: u32,
    #[serde(default)]
    pub active_models: u32,
    #[serde(default)]
    pub active_estimated_memory_mb: u64,
    #[serde(default)]
    pub active_estimated_kv_cache_mb: u64,
    #[serde(default)]
    pub backend_request_counts: BTreeMap<String, u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_backend: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_route_state: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderCapabilityDescriptor {
    pub capability_id: String,
    #[serde(default)]
    pub read_only: bool,
    #[serde(default)]
    pub recoverable: bool,
    #[serde(default)]
    pub approval_required: bool,
    #[serde(default)]
    pub external_side_effect: bool,
    #[serde(default)]
    pub dynamic_code: bool,
    #[serde(default)]
    pub user_interaction_required: bool,
    #[serde(default)]
    pub supported_targets: Vec<String>,
    #[serde(default)]
    pub input_schema_refs: Vec<String>,
    #[serde(default)]
    pub output_schema_refs: Vec<String>,
    #[serde(default)]
    pub audit_tags: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ProviderResourceBudget {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_memory_mb: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_cpu_percent: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_concurrency: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_requests_per_minute: Option<u32>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ProviderHealthcheck {
    #[serde(default)]
    pub kind: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub endpoint: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub interval_seconds: Option<u64>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CompatPermissionCapability {
    #[serde(default)]
    pub capability_id: String,
    #[serde(default)]
    pub permission_scopes: Vec<String>,
    #[serde(default)]
    pub approval_required: bool,
    #[serde(default)]
    pub dynamic_code: bool,
    #[serde(default)]
    pub user_interaction_required: bool,
    #[serde(default)]
    pub network_access: String,
    #[serde(default)]
    pub subprocess_access: String,
    #[serde(default)]
    pub filesystem_access: String,
    #[serde(default)]
    pub target_binding: String,
    #[serde(default)]
    pub audit_tags: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CompatPermissionBudget {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_timeout_seconds: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_memory_mb: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_cpu_seconds: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_concurrency: Option<u32>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CompatPermissionManifest {
    #[serde(default = "default_compat_permission_schema_version")]
    pub schema_version: String,
    #[serde(default)]
    pub provider_id: String,
    #[serde(default = "default_execution_location")]
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sandbox_class: Option<String>,
    #[serde(default)]
    pub required_permissions: Vec<String>,
    #[serde(default)]
    pub resource_budget: CompatPermissionBudget,
    #[serde(default)]
    pub capabilities: Vec<CompatPermissionCapability>,
    #[serde(default)]
    pub audit_tags: Vec<String>,
    #[serde(default)]
    pub taint_behavior: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RemoteProviderAttestation {
    #[serde(default)]
    pub mode: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub issuer: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub subject: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub issued_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub evidence_ref: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub digest: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RemoteProviderGovernance {
    #[serde(default)]
    pub fleet_id: String,
    #[serde(default)]
    pub governance_group: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub policy_group: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub registered_by: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
    #[serde(default)]
    pub allow_lateral_movement: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RemoteProviderRegistration {
    #[serde(default)]
    pub source_provider_id: String,
    #[serde(default)]
    pub provider_ref: String,
    #[serde(default)]
    pub endpoint: String,
    #[serde(default)]
    pub auth_mode: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub auth_header_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub auth_secret_env: Option<String>,
    #[serde(default)]
    pub target_hash: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
    #[serde(default)]
    pub registered_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub display_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub control_plane_provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub registration_status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_heartbeat_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub heartbeat_ttl_seconds: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revoked_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revocation_reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attestation: Option<RemoteProviderAttestation>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub governance: Option<RemoteProviderGovernance>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderDescriptor {
    pub provider_id: String,
    pub version: String,
    pub kind: String,
    pub display_name: String,
    pub owner: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub worker_contract: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result_protocol_schema_ref: Option<String>,
    #[serde(default)]
    pub trust_policy_modes: Vec<String>,
    pub capabilities: Vec<ProviderCapabilityDescriptor>,
    #[serde(default = "default_execution_location")]
    pub execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sandbox_class: Option<String>,
    #[serde(default)]
    pub required_permissions: Vec<String>,
    #[serde(default)]
    pub resource_budget: ProviderResourceBudget,
    #[serde(default)]
    pub supported_targets: Vec<String>,
    #[serde(default)]
    pub input_schema_refs: Vec<String>,
    #[serde(default)]
    pub output_schema_refs: Vec<String>,
    #[serde(default)]
    pub timeout_policy: String,
    #[serde(default)]
    pub retry_policy: String,
    #[serde(default)]
    pub healthcheck: ProviderHealthcheck,
    #[serde(default)]
    pub audit_tags: Vec<String>,
    #[serde(default)]
    pub taint_behavior: String,
    #[serde(default)]
    pub degradation_policy: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub compat_permission_manifest: Option<CompatPermissionManifest>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub remote_registration: Option<RemoteProviderRegistration>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderRecord {
    pub provider_id: String,
    pub descriptor: ProviderDescriptor,
    pub state: String,
    pub registered_at: String,
    pub updated_at: String,
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderHealthState {
    pub provider_id: String,
    #[serde(default = "default_provider_health_status")]
    pub status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_checked_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_error: Option<String>,
    #[serde(default)]
    pub circuit_open: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resource_pressure: Option<String>,
    #[serde(default)]
    pub disabled: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub disabled_reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderCandidate {
    pub provider_id: String,
    pub display_name: String,
    pub kind: String,
    pub execution_location: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
    pub health_status: String,
    pub disabled: bool,
    pub score: i32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub remote_registration: Option<RemoteProviderRegistration>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderRegisterRequest {
    pub descriptor: ProviderDescriptor,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderUnregisterRequest {
    pub provider_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderDiscoverRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capability_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_location: Option<String>,
    #[serde(default)]
    pub include_disabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderDiscoverResponse {
    pub candidates: Vec<ProviderCandidate>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderResolveCapabilityRequest {
    pub capability_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preferred_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preferred_execution_location: Option<String>,
    #[serde(default)]
    pub require_healthy: bool,
    #[serde(default)]
    pub include_disabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderResolveCapabilityResponse {
    pub capability_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub selected: Option<ProviderCandidate>,
    #[serde(default)]
    pub candidates: Vec<ProviderCandidate>,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderGetDescriptorRequest {
    pub provider_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderGetDescriptorResponse {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor: Option<ProviderDescriptor>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderHealthGetRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderHealthGetResponse {
    pub providers: Vec<ProviderHealthState>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderHealthReportRequest {
    pub provider_id: String,
    pub status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_error: Option<String>,
    #[serde(default)]
    pub circuit_open: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resource_pressure: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderDisableRequest {
    pub provider_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderEnableRequest {
    pub provider_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkingMemoryWriteRequest {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ref_id: Option<String>,
    pub payload: Value,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkingMemoryReadRequest {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ref_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkingMemoryRecord {
    pub ref_id: String,
    pub session_id: String,
    pub payload: Value,
    #[serde(default)]
    pub tags: Vec<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkingMemoryReadResponse {
    pub entries: Vec<WorkingMemoryRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodicMemoryAppendRequest {
    pub session_id: String,
    pub summary: String,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodicMemoryListRequest {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodicMemoryRecord {
    pub entry_id: String,
    pub session_id: String,
    pub summary: String,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodicMemoryListResponse {
    pub entries: Vec<EpisodicMemoryRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticMemoryPutRequest {
    pub session_id: String,
    pub label: String,
    pub payload: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticMemoryListRequest {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub query: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticMemoryRecord {
    pub index_id: String,
    pub session_id: String,
    pub label: String,
    pub payload: Value,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticMemoryListResponse {
    pub entries: Vec<SemanticMemoryRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProceduralMemoryPutRequest {
    pub session_id: String,
    pub rule_name: String,
    pub payload: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProceduralMemoryListRequest {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rule_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProceduralMemoryRecord {
    pub version_id: String,
    pub session_id: String,
    pub rule_name: String,
    pub payload: Value,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProceduralMemoryListResponse {
    pub entries: Vec<ProceduralMemoryRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortalIssueHandleRequest {
    pub kind: String,
    pub user_id: String,
    pub session_id: String,
    pub target: String,
    #[serde(default)]
    pub scope: BTreeMap<String, Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expiry_seconds: Option<u64>,
    #[serde(default = "default_portal_revocable")]
    pub revocable: bool,
    #[serde(default)]
    pub audit_tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortalLookupHandleRequest {
    pub handle_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortalRevokeHandleRequest {
    pub handle_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortalListHandlesRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortalHandleRecord {
    pub handle_id: String,
    pub kind: String,
    pub user_id: String,
    pub session_id: String,
    pub target: String,
    #[serde(default)]
    pub scope: BTreeMap<String, Value>,
    pub expiry: String,
    pub revocable: bool,
    pub issued_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revoked_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub revocation_reason: Option<String>,
    #[serde(default)]
    pub audit_tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortalLookupHandleResponse {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub handle: Option<PortalHandleRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortalListHandlesResponse {
    pub handles: Vec<PortalHandleRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderFsOpenRequest {
    pub handle_id: String,
    pub execution_token: ExecutionToken,
    #[serde(default)]
    pub include_content: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_bytes: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_entries: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderFsEntry {
    pub name: String,
    pub path: String,
    pub kind: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderFsOpenResponse {
    pub provider_id: String,
    pub handle: PortalHandleRecord,
    pub object_kind: String,
    pub target_path: String,
    pub target_hash: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub size_bytes: Option<u64>,
    #[serde(default)]
    pub entries: Vec<ProviderFsEntry>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content_preview: Option<String>,
    #[serde(default)]
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderFsBulkDeleteRequest {
    pub handle_id: String,
    pub execution_token: ExecutionToken,
    #[serde(default)]
    pub recursive: bool,
    #[serde(default)]
    pub dry_run: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderFsBulkDeleteResponse {
    pub provider_id: String,
    pub handle: PortalHandleRecord,
    pub target_path: String,
    pub dry_run: bool,
    pub status: String,
    #[serde(default)]
    pub affected_paths: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DeviceMetadataGetRequest {
    #[serde(default)]
    pub modalities: Vec<String>,
    #[serde(default)]
    pub only_available: bool,
    #[serde(default)]
    pub include_state_notes: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceMetadataEntry {
    pub modality: String,
    pub source_backend: String,
    pub available: bool,
    pub conditional: bool,
    pub readiness: String,
    #[serde(default)]
    pub backend_details: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adapter_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adapter_execution_path: Option<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceMetadataReadinessSummary {
    pub overall_status: String,
    #[serde(default)]
    pub requested_modalities: Vec<String>,
    #[serde(default)]
    pub available_modalities: Vec<String>,
    #[serde(default)]
    pub unavailable_modalities: Vec<String>,
    #[serde(default)]
    pub conditional_modalities: Vec<String>,
    #[serde(default)]
    pub unknown_modalities: Vec<String>,
    #[serde(default)]
    pub active_capture_count: u32,
    #[serde(default)]
    pub continuous_collector_count: u32,
    #[serde(default)]
    pub ui_tree_available: bool,
    #[serde(default)]
    pub ui_tree_snapshot_attached: bool,
}

impl Default for DeviceMetadataReadinessSummary {
    fn default() -> Self {
        Self {
            overall_status: "unknown".to_string(),
            requested_modalities: Vec::new(),
            available_modalities: Vec::new(),
            unavailable_modalities: Vec::new(),
            conditional_modalities: Vec::new(),
            unknown_modalities: Vec::new(),
            active_capture_count: 0,
            continuous_collector_count: 0,
            ui_tree_available: false,
            ui_tree_snapshot_attached: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceMetadataGetResponse {
    pub provider_id: String,
    pub device_service_id: String,
    pub generated_at: String,
    #[serde(default)]
    pub entries: Vec<DeviceMetadataEntry>,
    #[serde(default)]
    pub available_modalities: Vec<String>,
    #[serde(default)]
    pub active_capture_count: u32,
    #[serde(default)]
    pub summary: DeviceMetadataReadinessSummary,
    #[serde(default)]
    pub backend_summary: DeviceBackendSummary,
    #[serde(default)]
    pub ui_tree_support_matrix: Vec<UiTreeSupportMatrixEntry>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellWindowFocusRequest {
    pub execution_token: ExecutionToken,
    pub target: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellWindowFocusResponse {
    pub provider_id: String,
    pub status: String,
    pub focused_target: String,
    pub focused_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub state_path: Option<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellNotificationOpenRequest {
    pub execution_token: ExecutionToken,
    #[serde(default)]
    pub include_model: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellNotificationOpenResponse {
    pub provider_id: String,
    pub status: String,
    pub opened_at: String,
    pub notification_count: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<Value>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemIntentRequest {
    pub execution_token: ExecutionToken,
    pub intent: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemIntentAction {
    pub action_id: String,
    pub kind: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capability_id: Option<String>,
    pub description: String,
    #[serde(default)]
    pub requires_approval: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemIntentResponse {
    pub provider_id: String,
    pub session_id: String,
    pub task_id: String,
    pub task_state: String,
    pub status: String,
    pub intent: String,
    pub summary: String,
    pub route_preference: String,
    pub next_action: String,
    pub plan_source: String,
    #[serde(default)]
    pub candidate_capabilities: Vec<String>,
    #[serde(default)]
    pub actions: Vec<SystemIntentAction>,
    #[serde(default)]
    pub requires_handoff: bool,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentIntentSubmitRequest {
    pub user_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    pub intent: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentPlanRequest {
    pub session_id: String,
    pub intent: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTaskGetRequest {
    pub task_id: String,
    #[serde(default = "default_query_limit")]
    pub event_limit: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentPlan {
    pub task_id: String,
    pub session_id: String,
    pub summary: String,
    pub route_preference: String,
    pub candidate_capabilities: Vec<String>,
    pub next_action: String,
    #[serde(default)]
    pub steps: Vec<AgentPlanStep>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentPlanStep {
    pub step: String,
    pub capability_id: String,
    pub status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_location: Option<String>,
    #[serde(default)]
    pub requires_approval: bool,
    #[serde(default)]
    pub requires_portal_handle: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub portal_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery_action: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTaskResumeRequest {
    pub task_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentProviderExecutionResult {
    pub provider_id: String,
    pub capability_id: String,
    pub status: String,
    pub task_state: String,
    pub result: Value,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentApprovalSummary {
    pub required: bool,
    pub approval_status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_lane: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capability_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_location: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentChooserRequest {
    pub chooser_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub subtitle: Option<String>,
    pub status: String,
    #[serde(default)]
    pub requested_kinds: Vec<String>,
    pub selection_mode: String,
    pub approval_status: String,
    #[serde(default)]
    pub attempt_count: u32,
    #[serde(default)]
    pub max_attempts: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_ref: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capability_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub portal_handle_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<String>,
    #[serde(default)]
    pub audit_tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentIntentSubmissionResponse {
    pub session: SessionRecord,
    pub task: TaskRecord,
    pub plan: AgentPlan,
    pub policy: PolicyEvaluateEnvelope,
    pub route: RuntimeRouteResolveResponse,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_resolution: Option<ProviderResolveCapabilityResponse>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub portal_handle: Option<PortalHandleRecord>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_token: Option<ExecutionToken>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_preview: Option<RuntimeInferResponse>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_execution: Option<AgentProviderExecutionResult>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_summary: Option<AgentApprovalSummary>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub chooser_request: Option<AgentChooserRequest>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery: Option<RecoveryRef>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTaskGetResponse {
    pub task: TaskRecord,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub plan: Option<AgentPlan>,
    #[serde(default)]
    pub events: Vec<TaskEventRecord>,
    #[serde(default)]
    pub approvals: Vec<ApprovalRecord>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub portal_handle_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub portal_handle: Option<PortalHandleRecord>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_resolution: Option<ProviderResolveCapabilityResponse>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub route: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub policy: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_token: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_execution: Option<AgentProviderExecutionResult>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_summary: Option<AgentApprovalSummary>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub chooser_request: Option<AgentChooserRequest>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery: Option<RecoveryRef>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTaskResumeResponse {
    pub task: TaskRecord,
    pub plan: AgentPlan,
    pub approval: ApprovalRecord,
    pub provider_resolution: ProviderResolveCapabilityResponse,
    pub portal_handle: PortalHandleRecord,
    pub execution_token: ExecutionToken,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_execution: Option<AgentProviderExecutionResult>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_summary: Option<AgentApprovalSummary>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub chooser_request: Option<AgentChooserRequest>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recovery: Option<RecoveryRef>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::collections::BTreeMap;

    #[test]
    fn shared_contract_manifest_exposes_frozen_methods_and_schemas() {
        let manifest = shared_contract_manifest();
        assert_eq!(manifest.contract_version, SHARED_CONTRACT_VERSION);
        assert_eq!(manifest.compatibility_epoch, SHARED_COMPATIBILITY_EPOCH);
        assert!(manifest
            .methods
            .iter()
            .any(|item| item.method == methods::SYSTEM_CONTRACT_GET));
        assert!(manifest
            .methods
            .iter()
            .any(|item| item.method == methods::SESSION_EVIDENCE_GET));
        assert!(manifest
            .schemas
            .iter()
            .any(|item| { item.schema_ref == "aios/policy/schemas/execution-token.schema.json" }));
    }

    #[test]
    fn runtime_backend_descriptor_defaults_new_health_fields_when_omitted() {
        let descriptor: RuntimeBackendDescriptor = serde_json::from_value(serde_json::json!({
            "backend_id": "local-cpu",
            "availability": "available",
            "activation": "built-in"
        }))
        .expect("descriptor should deserialize");

        assert_eq!(descriptor.health_state, "unknown");
        assert!(descriptor.reason.is_empty());
        assert!(!descriptor.managed);
        assert!(descriptor.fallback_backend.is_none());
    }

    #[test]
    fn runtime_backend_event_payload_serializes_stable_runtime_fields() {
        let payload = RuntimeBackendEventPayload {
            event_phase: "fallback".to_string(),
            backend_id: "local-cpu".to_string(),
            resolved_backend: "local-gpu".to_string(),
            route_state: "backend-fallback-local-cpu".to_string(),
            degraded: true,
            rejected: false,
            requested_backend: Some("local-gpu".to_string()),
            fallback_backend: Some("local-cpu".to_string()),
            reason: Some("gpu worker unavailable".to_string()),
            model: Some("smoke-model".to_string()),
            estimated_latency_ms: Some(42),
            pending_queue: Some(1),
            active_requests: Some(2),
            queue_saturated: Some(false),
            provider_id: Some("nvidia.jetson.tensorrt".to_string()),
            runtime_service_id: Some("aios-runtimed.jetson-vendor-helper".to_string()),
            provider_status: Some("available".to_string()),
            artifact_path: Some("/var/lib/aios/runtimed/vendor-execution.json".to_string()),
        };

        let value = serde_json::to_value(&payload).expect("payload should serialize");
        assert_eq!(value["event_phase"], "fallback");
        assert_eq!(value["backend_id"], "local-cpu");
        assert_eq!(value["resolved_backend"], "local-gpu");
        assert_eq!(value["fallback_backend"], "local-cpu");
        assert_eq!(value["pending_queue"], 1);
        assert_eq!(value["provider_id"], "nvidia.jetson.tensorrt");
        assert_eq!(
            value["artifact_path"],
            "/var/lib/aios/runtimed/vendor-execution.json"
        );
    }

    #[test]
    fn device_state_response_preserves_frozen_backend_summary_shape() {
        let response = DeviceStateGetResponse {
            service_id: "aios-deviced".to_string(),
            capabilities: vec![DeviceCapabilityDescriptor {
                modality: "screen".to_string(),
                available: true,
                conditional: false,
                source_backend: "screen-capture-portal".to_string(),
                notes: vec!["screen-capability".to_string()],
            }],
            active_captures: Vec::new(),
            backend_statuses: vec![DeviceBackendStatus {
                modality: "screen".to_string(),
                backend: "screen-capture-portal".to_string(),
                available: true,
                readiness: "native-live".to_string(),
                details: vec!["probe_source=builtin".to_string()],
            }],
            capture_adapters: vec![DeviceCaptureAdapterPlan {
                modality: "screen".to_string(),
                backend: "screen-capture-portal".to_string(),
                adapter_id: "screen.portal-native".to_string(),
                execution_path: "native-live".to_string(),
                preview_object_kind: "screen_frame".to_string(),
                notes: vec!["adapter_contract=formal-native-backend".to_string()],
            }],
            ui_tree_snapshot: Some(json!({
                "snapshot_id": "tree-1",
                "capture_mode": "native-live",
                "focus_node": "desktop-0/app-0/0",
            })),
            continuous_collectors: vec![DeviceContinuousCollectorStatus {
                capture_id: "capture-1".to_string(),
                modality: "audio".to_string(),
                backend: "pipewire-audio".to_string(),
                collector_mode: "continuous".to_string(),
                status: "running".to_string(),
                updated_at: "2026-03-16T00:00:00Z".to_string(),
                sample_count: 4,
                details: vec!["sample_rate=48000".to_string()],
            }],
            backend_summary: DeviceBackendSummary {
                overall_status: "ready".to_string(),
                status_count: 5,
                available_status_count: 5,
                adapter_count: 5,
                attention_count: 0,
                continuous_collector_count: 1,
                ui_tree_support_route_count: 3,
                ui_tree_support_ready_count: 2,
                ui_tree_snapshot_present: true,
                ui_tree_capture_mode: Some("native-live".to_string()),
                ui_tree_current_support: Some("native-live".to_string()),
                readiness_summary: BTreeMap::from([("native-live".to_string(), 5)]),
                evidence_artifact_count: 5,
                evidence_present_count: 5,
                evidence_missing_count: 0,
                evidence_baselines: vec!["os-native-backend".to_string()],
            },
            ui_tree_support_matrix: vec![UiTreeSupportMatrixEntry {
                environment_id: "atspi-live".to_string(),
                available: true,
                readiness: "native-live".to_string(),
                current: true,
                desktop_environment: Some("gnome".to_string()),
                session_type: Some("wayland".to_string()),
                adapter_id: Some("ui_tree.atspi-native".to_string()),
                execution_path: Some("native-live".to_string()),
                stability: Some("best-effort-live".to_string()),
                limitations: vec!["desktop-dependent".to_string()],
                evidence: vec!["support_matrix_path=/tmp/ui-tree-support-matrix.json".to_string()],
                details: vec!["desktop=gnome".to_string()],
            }],
            notes: vec!["backend_overall_status=ready".to_string()],
        };

        let value =
            serde_json::to_value(&response).expect("device state response should serialize");
        assert_eq!(value["backend_summary"]["overall_status"], "ready");
        assert_eq!(value["backend_summary"]["available_status_count"], 5);
        assert_eq!(
            value["backend_summary"]["ui_tree_capture_mode"],
            "native-live"
        );
        assert_eq!(
            value["backend_summary"]["readiness_summary"]["native-live"],
            5
        );
        assert_eq!(
            value["ui_tree_support_matrix"][0]["environment_id"],
            "atspi-live"
        );
        assert_eq!(
            value["ui_tree_support_matrix"][0]["adapter_id"],
            "ui_tree.atspi-native"
        );
    }

    #[test]
    fn device_response_compatibility_defaults_new_backend_summary_fields_when_omitted() {
        let state: DeviceStateGetResponse = serde_json::from_value(json!({
            "service_id": "aios-deviced"
        }))
        .expect("device state response should deserialize with omitted optional fields");
        assert_eq!(state.backend_summary.overall_status, "unknown");
        assert!(state.ui_tree_support_matrix.is_empty());

        let metadata: DeviceMetadataGetResponse = serde_json::from_value(json!({
            "provider_id": "device.metadata.local",
            "device_service_id": "aios-deviced",
            "generated_at": "2026-03-16T00:00:00Z"
        }))
        .expect("device metadata response should deserialize with omitted optional fields");
        assert_eq!(metadata.backend_summary.overall_status, "unknown");
        assert!(metadata.ui_tree_support_matrix.is_empty());
    }

    #[test]
    fn device_metadata_response_preserves_frozen_backend_summary_shape() {
        let response = DeviceMetadataGetResponse {
            provider_id: "device.metadata.local".to_string(),
            device_service_id: "aios-deviced".to_string(),
            generated_at: "2026-03-16T00:00:00Z".to_string(),
            entries: vec![DeviceMetadataEntry {
                modality: "screen".to_string(),
                source_backend: "screen-capture-portal".to_string(),
                available: true,
                conditional: false,
                readiness: "native-live".to_string(),
                backend_details: vec!["probe_source=builtin".to_string()],
                adapter_id: Some("screen.portal-native".to_string()),
                adapter_execution_path: Some("native-live".to_string()),
                notes: vec!["adapter_contract=formal-native-backend".to_string()],
            }],
            available_modalities: vec!["screen".to_string()],
            active_capture_count: 1,
            summary: DeviceMetadataReadinessSummary {
                overall_status: "ready".to_string(),
                requested_modalities: vec!["screen".to_string()],
                available_modalities: vec!["screen".to_string()],
                unavailable_modalities: Vec::new(),
                conditional_modalities: Vec::new(),
                unknown_modalities: Vec::new(),
                active_capture_count: 1,
                continuous_collector_count: 0,
                ui_tree_available: true,
                ui_tree_snapshot_attached: true,
            },
            backend_summary: DeviceBackendSummary {
                overall_status: "ready".to_string(),
                status_count: 5,
                available_status_count: 5,
                adapter_count: 5,
                attention_count: 0,
                continuous_collector_count: 1,
                ui_tree_support_route_count: 3,
                ui_tree_support_ready_count: 2,
                ui_tree_snapshot_present: true,
                ui_tree_capture_mode: Some("native-live".to_string()),
                ui_tree_current_support: Some("native-live".to_string()),
                readiness_summary: BTreeMap::from([("native-live".to_string(), 5)]),
                evidence_artifact_count: 5,
                evidence_present_count: 5,
                evidence_missing_count: 0,
                evidence_baselines: vec!["os-native-backend".to_string()],
            },
            ui_tree_support_matrix: vec![UiTreeSupportMatrixEntry {
                environment_id: "atspi-live".to_string(),
                available: true,
                readiness: "native-live".to_string(),
                current: true,
                desktop_environment: Some("gnome".to_string()),
                session_type: Some("wayland".to_string()),
                adapter_id: Some("ui_tree.atspi-native".to_string()),
                execution_path: Some("native-live".to_string()),
                stability: Some("best-effort-live".to_string()),
                limitations: vec!["desktop-dependent".to_string()],
                evidence: vec!["support_matrix_path=/tmp/ui-tree-support-matrix.json".to_string()],
                details: vec!["desktop=gnome".to_string()],
            }],
            notes: vec!["backend_overall_status=ready".to_string()],
        };

        let value =
            serde_json::to_value(&response).expect("device metadata response should serialize");
        assert_eq!(value["summary"]["overall_status"], "ready");
        assert_eq!(value["backend_summary"]["overall_status"], "ready");
        assert_eq!(
            value["backend_summary"]["ui_tree_capture_mode"],
            "native-live"
        );
        assert_eq!(
            value["ui_tree_support_matrix"][0]["environment_id"],
            "atspi-live"
        );
    }
}
