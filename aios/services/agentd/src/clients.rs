use std::collections::BTreeMap;

use serde_json::{json, Value};

use aios_contracts::{
    methods, AgentIntentSubmitRequest, AgentPlan, AgentProviderExecutionResult,
    ApprovalCreateRequest, ApprovalGetRequest, ApprovalListRequest, ApprovalListResponse,
    ApprovalRecord, ApprovalResolveRequest, AuditExportRequest, AuditExportResponse,
    AuditQueryRequest, AuditQueryResponse, EpisodicMemoryAppendRequest, EpisodicMemoryRecord,
    ExecutionToken, PolicyEvaluateEnvelope, PolicyEvaluateRequest, PortalHandleRecord,
    PortalIssueHandleRequest, PortalListHandlesRequest, PortalListHandlesResponse,
    PortalLookupHandleRequest, PortalLookupHandleResponse, PortalRevokeHandleRequest,
    ProviderResolveCapabilityRequest, ProviderResolveCapabilityResponse, RuntimeInferRequest,
    RuntimeInferResponse, RuntimeRouteResolveRequest, RuntimeRouteResolveResponse,
    SemanticMemoryPutRequest, SemanticMemoryRecord, SessionCreateRequest, SessionCreateResponse,
    SessionEvidenceExportRequest, SessionEvidenceExportResponse, SessionEvidenceRequest,
    SessionEvidenceResponse, SessionListRequest, SessionListResponse, SessionRecord,
    SessionResumeRequest, SessionResumeResponse, TaskCreateRequest, TaskCreateResponse,
    TaskEventListRequest, TaskEventListResponse, TaskGetRequest, TaskListRequest, TaskListResponse,
    TaskPlanGetRequest, TaskPlanPutRequest, TaskPlanRecord, TaskRecord, TaskStateUpdateRequest,
    TokenIssueRequest, TokenVerifyRequest, TokenVerifyResponse, WorkingMemoryReadRequest,
    WorkingMemoryReadResponse, WorkingMemoryRecord, WorkingMemoryWriteRequest,
};

use crate::AppState;

pub fn create_or_resume_session(
    state: &AppState,
    request: &AgentIntentSubmitRequest,
) -> anyhow::Result<(SessionRecord, TaskRecord)> {
    if let Some(session_id) = &request.session_id {
        let resumed: SessionResumeResponse = aios_rpc::call_unix(
            &state.config.sessiond_socket,
            methods::SESSION_RESUME,
            &SessionResumeRequest {
                session_id: session_id.clone(),
            },
        )?;

        let task = create_task(
            state,
            &resumed.session.session_id,
            &request.intent,
            "planned",
        )?;
        return Ok((resumed.session, task));
    }

    let mut metadata = BTreeMap::new();
    metadata.insert("initial_intent".to_string(), json!(request.intent.clone()));

    let created: SessionCreateResponse = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::SESSION_CREATE,
        &SessionCreateRequest {
            user_id: request.user_id.clone(),
            metadata,
        },
    )?;

    Ok((created.session, created.task))
}

pub fn create_session(
    state: &AppState,
    request: &SessionCreateRequest,
) -> anyhow::Result<SessionCreateResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::SESSION_CREATE,
        request,
    )
}

pub fn resume_session(
    state: &AppState,
    request: &SessionResumeRequest,
) -> anyhow::Result<SessionResumeResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::SESSION_RESUME,
        request,
    )
}

pub fn resolve_provider_capability(
    state: &AppState,
    request: &ProviderResolveCapabilityRequest,
) -> anyhow::Result<ProviderResolveCapabilityResponse> {
    state.provider_registry.resolve_capability(request)
}

pub fn create_task(
    state: &AppState,
    session_id: &str,
    title: &str,
    task_state: &str,
) -> anyhow::Result<TaskRecord> {
    let response: TaskCreateResponse = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_CREATE,
        &TaskCreateRequest {
            session_id: session_id.to_string(),
            title: Some(title.to_string()),
            state: task_state.to_string(),
        },
    )?;

    Ok(response.task)
}

pub fn list_tasks(
    state: &AppState,
    session_id: &str,
    state_filter: Option<&str>,
    limit: Option<u32>,
) -> anyhow::Result<Vec<TaskRecord>> {
    let response: TaskListResponse = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_LIST,
        &TaskListRequest {
            session_id: session_id.to_string(),
            state: state_filter.map(str::to_string),
            limit,
        },
    )?;

    Ok(response.tasks)
}

pub fn get_task(state: &AppState, task_id: &str) -> anyhow::Result<TaskRecord> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_GET,
        &TaskGetRequest {
            task_id: task_id.to_string(),
        },
    )
}

pub fn update_task_state(
    state: &AppState,
    task_id: &str,
    new_state: &str,
    reason: Option<&str>,
) -> anyhow::Result<TaskRecord> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_STATE_UPDATE,
        &TaskStateUpdateRequest {
            task_id: task_id.to_string(),
            new_state: new_state.to_string(),
            reason: reason.map(str::to_string),
        },
    )
}

pub fn persist_task_plan(
    state: &AppState,
    task_id: &str,
    plan: &AgentPlan,
) -> anyhow::Result<TaskPlanRecord> {
    let plan_value: Value = serde_json::to_value(plan)?;
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_PLAN_PUT,
        &TaskPlanPutRequest {
            task_id: task_id.to_string(),
            plan: plan_value,
        },
    )
}

pub fn persist_task_plan_request(
    state: &AppState,
    request: &TaskPlanPutRequest,
) -> anyhow::Result<TaskPlanRecord> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_PLAN_PUT,
        request,
    )
}

pub fn get_task_plan_record(state: &AppState, task_id: &str) -> anyhow::Result<TaskPlanRecord> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_PLAN_GET,
        &TaskPlanGetRequest {
            task_id: task_id.to_string(),
        },
    )
}

pub fn get_task_plan(state: &AppState, task_id: &str) -> anyhow::Result<AgentPlan> {
    let record = get_task_plan_record(state, task_id)?;
    Ok(serde_json::from_value(record.plan)?)
}

pub fn try_get_task_plan(state: &AppState, task_id: &str) -> anyhow::Result<Option<AgentPlan>> {
    match get_task_plan(state, task_id) {
        Ok(plan) => Ok(Some(plan)),
        Err(error) if is_resource_not_found(&error) => Ok(None),
        Err(error) => Err(error),
    }
}

pub fn list_task_events(
    state: &AppState,
    task_id: &str,
    limit: u32,
    reverse: bool,
) -> anyhow::Result<TaskEventListResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_EVENTS_LIST,
        &TaskEventListRequest {
            task_id: task_id.to_string(),
            limit,
            reverse,
        },
    )
}

pub fn read_working_memory_ref(
    state: &AppState,
    session_id: &str,
    ref_id: &str,
) -> anyhow::Result<Option<WorkingMemoryRecord>> {
    let response: WorkingMemoryReadResponse = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::MEMORY_READ,
        &WorkingMemoryReadRequest {
            session_id: session_id.to_string(),
            ref_id: Some(ref_id.to_string()),
            limit: Some(1),
        },
    )?;

    Ok(response.entries.into_iter().next())
}

pub fn lookup_portal_handle(
    state: &AppState,
    handle_id: &str,
    session_id: &str,
    user_id: &str,
) -> anyhow::Result<Option<PortalHandleRecord>> {
    let response: PortalLookupHandleResponse = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::PORTAL_HANDLE_LOOKUP,
        &PortalLookupHandleRequest {
            handle_id: handle_id.to_string(),
            session_id: Some(session_id.to_string()),
            user_id: Some(user_id.to_string()),
        },
    )?;

    Ok(response.handle)
}

pub fn create_task_request(
    state: &AppState,
    request: &TaskCreateRequest,
) -> anyhow::Result<TaskCreateResponse> {
    aios_rpc::call_unix(&state.config.sessiond_socket, methods::TASK_CREATE, request)
}

pub fn update_task_state_request(
    state: &AppState,
    request: &TaskStateUpdateRequest,
) -> anyhow::Result<TaskRecord> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::TASK_STATE_UPDATE,
        request,
    )
}

pub fn list_sessions(
    state: &AppState,
    request: &SessionListRequest,
) -> anyhow::Result<SessionListResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::SESSION_LIST,
        request,
    )
}

pub fn create_approval(
    state: &AppState,
    request: &ApprovalCreateRequest,
) -> anyhow::Result<ApprovalRecord> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::APPROVAL_CREATE,
        request,
    )
}

pub fn get_approval(state: &AppState, approval_ref: &str) -> anyhow::Result<ApprovalRecord> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::APPROVAL_GET,
        &ApprovalGetRequest {
            approval_ref: approval_ref.to_string(),
        },
    )
}

pub fn list_approvals(
    state: &AppState,
    task_id: &str,
    status: Option<&str>,
) -> anyhow::Result<Vec<ApprovalRecord>> {
    let response: ApprovalListResponse = aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::APPROVAL_LIST,
        &ApprovalListRequest {
            session_id: None,
            task_id: Some(task_id.to_string()),
            status: status.map(str::to_string),
        },
    )?;

    Ok(response.approvals)
}

pub fn resolve_approval(
    state: &AppState,
    request: &ApprovalResolveRequest,
) -> anyhow::Result<ApprovalRecord> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::APPROVAL_RESOLVE,
        request,
    )
}

pub fn list_approvals_request(
    state: &AppState,
    request: &ApprovalListRequest,
) -> anyhow::Result<ApprovalListResponse> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::APPROVAL_LIST,
        request,
    )
}

pub fn get_session_evidence(
    state: &AppState,
    request: &SessionEvidenceRequest,
) -> anyhow::Result<SessionEvidenceResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::SESSION_EVIDENCE_GET,
        request,
    )
}

pub fn export_session_evidence(
    state: &AppState,
    request: &SessionEvidenceExportRequest,
) -> anyhow::Result<SessionEvidenceExportResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::SESSION_EVIDENCE_EXPORT,
        request,
    )
}

pub fn issue_portal_handle(
    state: &AppState,
    request: &PortalIssueHandleRequest,
) -> anyhow::Result<PortalHandleRecord> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::PORTAL_HANDLE_ISSUE,
        request,
    )
}

pub fn revoke_portal_handle(
    state: &AppState,
    request: &PortalRevokeHandleRequest,
) -> anyhow::Result<PortalLookupHandleResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::PORTAL_HANDLE_REVOKE,
        request,
    )
}

pub fn list_portal_handles(
    state: &AppState,
    request: &PortalListHandlesRequest,
) -> anyhow::Result<PortalListHandlesResponse> {
    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::PORTAL_HANDLE_LIST,
        request,
    )
}

pub fn query_audit(
    state: &AppState,
    request: &AuditQueryRequest,
) -> anyhow::Result<AuditQueryResponse> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_AUDIT_QUERY,
        request,
    )
}

pub fn export_audit(
    state: &AppState,
    request: &AuditExportRequest,
) -> anyhow::Result<AuditExportResponse> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_AUDIT_EXPORT,
        request,
    )
}

pub fn persist_working_memory(
    state: &AppState,
    session_id: &str,
    intent: &str,
    plan: &AgentPlan,
    provider_resolution: Option<&ProviderResolveCapabilityResponse>,
    route: Option<&RuntimeRouteResolveResponse>,
    portal_handle_id: Option<&str>,
    task_state: &str,
    policy: Option<&PolicyEvaluateEnvelope>,
    execution_token: Option<&ExecutionToken>,
) -> anyhow::Result<WorkingMemoryRecord> {
    let provider_summary = provider_resolution.map(|resolution| {
        json!({
            "capability_id": resolution.capability_id.clone(),
            "selected_provider_id": resolution
                .selected
                .as_ref()
                .map(|candidate| candidate.provider_id.clone()),
            "selected_execution_location": resolution
                .selected
                .as_ref()
                .map(|candidate| candidate.execution_location.clone()),
            "candidate_provider_ids": resolution
                .candidates
                .iter()
                .map(|candidate| candidate.provider_id.clone())
                .collect::<Vec<_>>(),
            "reason": resolution.reason.clone(),
        })
    });
    let route_summary = route.map(|item| {
        json!({
            "selected_backend": item.selected_backend.clone(),
            "route_state": item.route_state.clone(),
            "degraded": item.degraded,
            "reason": item.reason.clone(),
        })
    });

    let mut tags = vec![
        "agentd".to_string(),
        "working-memory".to_string(),
        "plan-summary".to_string(),
        format!("task-state:{task_state}"),
    ];
    if provider_resolution
        .and_then(|resolution| resolution.selected.as_ref())
        .is_some()
    {
        tags.push("provider-resolved".to_string());
    }
    if portal_handle_id.is_some() {
        tags.push("portal-bound".to_string());
    }
    if let Some(policy) = policy {
        tags.push(format!("policy:{}", policy.decision.decision));
        if policy.decision.requires_approval {
            tags.push("approval-required".to_string());
        }
    }
    if execution_token.is_some() {
        tags.push("token-issued".to_string());
    }

    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::MEMORY_WRITE,
        &WorkingMemoryWriteRequest {
            session_id: session_id.to_string(),
            ref_id: Some(format!("wm-plan-{}", plan.task_id.as_str())),
            payload: json!({
                "kind": "agent-plan",
                "source": "agentd",
                "task_id": plan.task_id.clone(),
                "intent": intent,
                "summary": plan.summary.clone(),
                "route_preference": plan.route_preference.clone(),
                "candidate_capabilities": plan.candidate_capabilities.clone(),
                "next_action": plan.next_action.clone(),
                "task_state": task_state,
                "provider_resolution": provider_summary,
                "route": route_summary,
                "portal_handle_id": portal_handle_id,
                "policy": policy_summary(policy),
                "execution_token": execution_token_summary(execution_token),
            }),
            tags,
        },
    )
}

pub fn append_episodic_memory(
    state: &AppState,
    session_id: &str,
    task_id: &str,
    intent: &str,
    plan: &AgentPlan,
    task_state: &str,
    portal_handle_id: Option<&str>,
    policy: Option<&PolicyEvaluateEnvelope>,
) -> anyhow::Result<EpisodicMemoryRecord> {
    let mut metadata = BTreeMap::new();
    metadata.insert("task_id".to_string(), json!(task_id));
    metadata.insert("intent".to_string(), json!(intent));
    metadata.insert(
        "route_preference".to_string(),
        json!(plan.route_preference.clone()),
    );
    metadata.insert(
        "candidate_capabilities".to_string(),
        json!(plan.candidate_capabilities.clone()),
    );
    metadata.insert("task_state".to_string(), json!(task_state));
    if let Some(handle_id) = portal_handle_id {
        metadata.insert("portal_handle_id".to_string(), json!(handle_id));
    }
    if let Some(policy) = policy {
        metadata.insert(
            "policy_decision".to_string(),
            json!(policy.decision.decision),
        );
        metadata.insert(
            "requires_approval".to_string(),
            json!(policy.decision.requires_approval),
        );
        metadata.insert(
            "approval_lane".to_string(),
            json!(policy.approval_lane.clone()),
        );
        if let Some(approval_ref) = policy.approval_ref.as_deref() {
            metadata.insert("approval_ref".to_string(), json!(approval_ref));
        }
    }

    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::MEMORY_EPISODIC_APPEND,
        &EpisodicMemoryAppendRequest {
            session_id: session_id.to_string(),
            summary: plan.summary.clone(),
            metadata,
        },
    )
}

pub fn persist_semantic_memory(
    state: &AppState,
    session_id: &str,
    task_id: &str,
    intent: &str,
    primary_capability: &str,
    provider_resolution: Option<&ProviderResolveCapabilityResponse>,
    route: Option<&RuntimeRouteResolveResponse>,
    policy: Option<&PolicyEvaluateEnvelope>,
) -> anyhow::Result<SemanticMemoryRecord> {
    let provider_id = provider_resolution
        .and_then(|resolution| resolution.selected.as_ref())
        .map(|candidate| candidate.provider_id.clone());
    let execution_location = provider_resolution
        .and_then(|resolution| resolution.selected.as_ref())
        .map(|candidate| candidate.execution_location.clone());

    aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::MEMORY_SEMANTIC_PUT,
        &SemanticMemoryPutRequest {
            session_id: session_id.to_string(),
            label: "agent-plan-summary".to_string(),
            payload: json!({
                "task_id": task_id,
                "intent_summary": intent.chars().take(96).collect::<String>(),
                "primary_capability": primary_capability,
                "provider_id": provider_id,
                "execution_location": execution_location,
                "route_state": route.map(|item| item.route_state.clone()),
                "selected_backend": route.map(|item| item.selected_backend.clone()),
                "policy_decision": policy.map(|item| item.decision.decision.clone()),
                "requires_approval": policy.map(|item| item.decision.requires_approval),
                "approval_ref": policy.and_then(|item| item.approval_ref.clone()),
            }),
        },
    )
}

pub fn persist_provider_execution_outcome(
    state: &AppState,
    session_id: &str,
    task_id: &str,
    outcome: &AgentProviderExecutionResult,
) -> anyhow::Result<()> {
    let _: WorkingMemoryRecord = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::MEMORY_WRITE,
        &WorkingMemoryWriteRequest {
            session_id: session_id.to_string(),
            ref_id: Some(format!("wm-provider-execution-{task_id}")),
            payload: json!({
                "kind": "provider-execution",
                "source": "agentd",
                "task_id": task_id,
                "provider_id": outcome.provider_id.clone(),
                "capability_id": outcome.capability_id.clone(),
                "status": outcome.status.clone(),
                "task_state": outcome.task_state.clone(),
                "result": outcome.result.clone(),
                "notes": outcome.notes.clone(),
            }),
            tags: vec![
                "agentd".to_string(),
                "provider-execution".to_string(),
                format!("status:{}", outcome.status),
                format!("task-state:{}", outcome.task_state),
            ],
        },
    )?;

    let _: EpisodicMemoryRecord = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::MEMORY_EPISODIC_APPEND,
        &EpisodicMemoryAppendRequest {
            session_id: session_id.to_string(),
            summary: format!(
                "{} via {} {}",
                outcome.capability_id, outcome.provider_id, outcome.status
            ),
            metadata: BTreeMap::from([
                ("task_id".to_string(), json!(task_id)),
                (
                    "provider_id".to_string(),
                    json!(outcome.provider_id.clone()),
                ),
                (
                    "capability_id".to_string(),
                    json!(outcome.capability_id.clone()),
                ),
                ("status".to_string(), json!(outcome.status.clone())),
                ("task_state".to_string(), json!(outcome.task_state.clone())),
            ]),
        },
    )?;

    let _: SemanticMemoryRecord = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::MEMORY_SEMANTIC_PUT,
        &SemanticMemoryPutRequest {
            session_id: session_id.to_string(),
            label: "agent-provider-execution".to_string(),
            payload: json!({
                "task_id": task_id,
                "provider_id": outcome.provider_id.clone(),
                "capability_id": outcome.capability_id.clone(),
                "status": outcome.status.clone(),
                "task_state": outcome.task_state.clone(),
            }),
        },
    )?;

    Ok(())
}

pub fn evaluate_primary_capability(
    state: &AppState,
    user_id: &str,
    session_id: &str,
    task_id: &str,
    intent: &str,
    capability_id: &str,
    execution_location: &str,
    target_hash: Option<String>,
    constraints: BTreeMap<String, Value>,
) -> anyhow::Result<PolicyEvaluateEnvelope> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_EVALUATE,
        &PolicyEvaluateRequest {
            user_id: user_id.to_string(),
            session_id: session_id.to_string(),
            task_id: task_id.to_string(),
            capability_id: capability_id.to_string(),
            execution_location: execution_location.to_string(),
            target_hash,
            constraints,
            intent: Some(intent.to_string()),
            taint_summary: None,
        },
    )
}

pub fn issue_execution_token_request(
    state: &AppState,
    request: &TokenIssueRequest,
) -> anyhow::Result<ExecutionToken> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_TOKEN_ISSUE,
        request,
    )
}

pub fn verify_execution_token_request(
    state: &AppState,
    request: &TokenVerifyRequest,
) -> anyhow::Result<TokenVerifyResponse> {
    aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_TOKEN_VERIFY,
        request,
    )
}

pub fn issue_execution_token(
    state: &AppState,
    user_id: &str,
    session_id: &str,
    task_id: &str,
    capability_id: &str,
    target_hash: Option<String>,
    execution_location: &str,
    policy: &PolicyEvaluateEnvelope,
) -> anyhow::Result<Option<ExecutionToken>> {
    if policy.decision.decision != "allowed" {
        return Ok(None);
    }

    let token = issue_execution_token_request(
        state,
        &TokenIssueRequest {
            user_id: user_id.to_string(),
            session_id: session_id.to_string(),
            task_id: task_id.to_string(),
            capability_id: capability_id.to_string(),
            target_hash,
            approval_ref: None,
            constraints: BTreeMap::new(),
            execution_location: execution_location.to_string(),
            taint_summary: policy.taint_hint.clone(),
        },
    )?;

    Ok(Some(token))
}

pub fn issue_approval_execution_token(
    state: &AppState,
    approval: &ApprovalRecord,
) -> anyhow::Result<ExecutionToken> {
    issue_execution_token_request(
        state,
        &TokenIssueRequest {
            user_id: approval.user_id.clone(),
            session_id: approval.session_id.clone(),
            task_id: approval.task_id.clone(),
            capability_id: approval.capability_id.clone(),
            target_hash: approval.target_hash.clone(),
            approval_ref: Some(approval.approval_ref.clone()),
            constraints: approval.constraints.clone(),
            execution_location: approval.execution_location.clone(),
            taint_summary: approval.taint_summary.clone(),
        },
    )
}

pub fn resolve_route(
    state: &AppState,
    preferred_backend: Option<String>,
) -> anyhow::Result<RuntimeRouteResolveResponse> {
    aios_rpc::call_unix(
        &state.config.runtimed_socket,
        methods::RUNTIME_ROUTE_RESOLVE,
        &RuntimeRouteResolveRequest {
            preferred_backend,
            allow_remote: false,
        },
    )
}

pub fn preview_runtime(
    state: &AppState,
    session_id: &str,
    task_id: &str,
    prompt: &str,
) -> anyhow::Result<RuntimeInferResponse> {
    aios_rpc::call_unix(
        &state.config.runtimed_socket,
        methods::RUNTIME_INFER_SUBMIT,
        &RuntimeInferRequest {
            session_id: session_id.to_string(),
            task_id: task_id.to_string(),
            prompt: prompt.to_string(),
            model: None,
            execution_token: None,
            preferred_backend: None,
        },
    )
}

fn policy_summary(policy: Option<&PolicyEvaluateEnvelope>) -> Option<Value> {
    policy.map(|item| {
        json!({
            "decision": item.decision.decision.clone(),
            "requires_approval": item.decision.requires_approval,
            "reason": item.decision.reason.clone(),
            "approval_lane": item.approval_lane.clone(),
            "approval_ref": item.approval_ref.clone(),
            "taint_hint": item.taint_hint.clone(),
        })
    })
}

fn execution_token_summary(execution_token: Option<&ExecutionToken>) -> Option<Value> {
    execution_token.map(|token| {
        json!({
            "capability_id": token.capability_id.clone(),
            "execution_location": token.execution_location.clone(),
            "approval_ref": token.approval_ref.clone(),
            "has_target_hash": token.target_hash.is_some(),
            "constraint_keys": token.constraints.keys().cloned().collect::<Vec<_>>(),
        })
    })
}

fn is_resource_not_found(error: &anyhow::Error) -> bool {
    error.to_string().contains("[resource_not_found]")
}
