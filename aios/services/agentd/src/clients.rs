use std::collections::BTreeMap;

use serde_json::{json, Value};

use aios_contracts::{
    methods, AgentIntentSubmitRequest, AgentPlan, EpisodicMemoryAppendRequest,
    EpisodicMemoryRecord, ExecutionToken, PolicyEvaluateEnvelope, PolicyEvaluateRequest,
    ProviderResolveCapabilityResponse, RuntimeInferRequest, RuntimeInferResponse,
    RuntimeRouteResolveRequest, RuntimeRouteResolveResponse, SemanticMemoryPutRequest,
    SemanticMemoryRecord, SessionCreateRequest, SessionCreateResponse, SessionRecord,
    SessionResumeRequest, SessionResumeResponse, TaskCreateRequest, TaskCreateResponse,
    TaskListRequest, TaskListResponse, TaskPlanPutRequest, TaskPlanRecord, TaskRecord,
    TaskStateUpdateRequest, TokenIssueRequest, WorkingMemoryRecord, WorkingMemoryWriteRequest,
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

pub fn persist_working_memory(
    state: &AppState,
    session_id: &str,
    intent: &str,
    plan: &AgentPlan,
    provider_resolution: Option<&ProviderResolveCapabilityResponse>,
    route: Option<&RuntimeRouteResolveResponse>,
    portal_handle_id: Option<&str>,
    task_state: &str,
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
            }),
        },
    )
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

    let token: ExecutionToken = aios_rpc::call_unix(
        &state.config.policyd_socket,
        methods::POLICY_TOKEN_ISSUE,
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
