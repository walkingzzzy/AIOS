use std::collections::BTreeMap;
use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::Value;

use aios_contracts::{
    methods, AgentIntentSubmissionResponse, AgentIntentSubmitRequest, AgentPlan, AgentPlanRequest,
    AgentProviderExecutionResult, AgentTaskGetRequest, AgentTaskGetResponse,
    AgentTaskResumeRequest, AgentTaskResumeResponse, ApprovalCreateRequest, ApprovalGetRequest,
    ApprovalListRequest, ApprovalResolveRequest, AuditExportRequest, AuditQueryRequest,
    PortalIssueHandleRequest, PortalListHandlesRequest, PortalRevokeHandleRequest,
    ProviderDisableRequest, ProviderDiscoverRequest, ProviderEnableRequest,
    ProviderGetDescriptorRequest, ProviderHealthGetRequest, ProviderHealthReportRequest,
    ProviderRegisterRequest, ProviderResolveCapabilityRequest, ProviderUnregisterRequest,
    ServiceContractResponse, SessionCreateRequest, SessionEvidenceExportRequest,
    SessionEvidenceRequest, SessionListRequest, SessionResumeRequest, SessionResumeResponse,
    TaskCreateRequest, TaskEventListRequest, TaskListRequest, TaskPlanGetRequest,
    TaskPlanPutRequest, TaskRecord, TaskStateUpdateRequest, TokenIssueRequest, TokenVerifyRequest,
};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::AppState;

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("agentd");

    let health_state = state.clone();
    router.register_method(methods::SYSTEM_HEALTH_GET, move |_| {
        json(health_state.health())
    });

    let contract_state = state.clone();
    router.register_method(methods::SYSTEM_CONTRACT_GET, move |_| {
        json(ServiceContractResponse {
            service_id: contract_state.config.service_id.clone(),
            contract: aios_contracts::shared_contract_manifest(),
        })
    });

    let provider_register_state = state.clone();
    router.register_method(methods::PROVIDER_REGISTER, move |params| {
        let request: ProviderRegisterRequest = parse_params(params)?;
        let record = provider_register_state
            .provider_registry
            .register(request.descriptor)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(record)
    });

    let provider_unregister_state = state.clone();
    router.register_method(methods::PROVIDER_UNREGISTER, move |params| {
        let request: ProviderUnregisterRequest = parse_params(params)?;
        provider_unregister_state
            .provider_registry
            .unregister(&request.provider_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(serde_json::json!({
            "provider_id": request.provider_id,
            "unregistered": true,
        }))
    });

    let provider_discover_state = state.clone();
    router.register_method(methods::PROVIDER_DISCOVER, move |params| {
        let request: ProviderDiscoverRequest = parse_params(params)?;
        let response = provider_discover_state
            .provider_registry
            .discover(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let provider_resolve_state = state.clone();
    router.register_method(methods::PROVIDER_RESOLVE_CAPABILITY, move |params| {
        let request: ProviderResolveCapabilityRequest = parse_params(params)?;
        let response = provider_resolve_state
            .provider_registry
            .resolve_capability(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let provider_descriptor_state = state.clone();
    router.register_method(methods::PROVIDER_GET_DESCRIPTOR, move |params| {
        let request: ProviderGetDescriptorRequest = parse_params(params)?;
        let response = provider_descriptor_state
            .provider_registry
            .get_descriptor(&request.provider_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let provider_health_state = state.clone();
    router.register_method(methods::PROVIDER_HEALTH_GET, move |params| {
        let request: ProviderHealthGetRequest = parse_params(params)?;
        let response = provider_health_state
            .provider_registry
            .health_get(request.provider_id.as_deref())
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let provider_health_report_state = state.clone();
    router.register_method(methods::PROVIDER_HEALTH_REPORT, move |params| {
        let request: ProviderHealthReportRequest = parse_params(params)?;
        let response = provider_health_report_state
            .provider_registry
            .report_health(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let provider_disable_state = state.clone();
    router.register_method(methods::PROVIDER_DISABLE, move |params| {
        let request: ProviderDisableRequest = parse_params(params)?;
        let response = provider_disable_state
            .provider_registry
            .disable(&request.provider_id, request.reason)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let provider_enable_state = state.clone();
    router.register_method(methods::PROVIDER_ENABLE, move |params| {
        let request: ProviderEnableRequest = parse_params(params)?;
        let response = provider_enable_state
            .provider_registry
            .enable(&request.provider_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_session_create_state = state.clone();
    router.register_method(methods::AGENT_SESSION_CREATE, move |params| {
        let request: SessionCreateRequest = parse_params(params)?;
        let response = crate::clients::create_session(&agent_session_create_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_session_resume_state = state.clone();
    router.register_method(methods::AGENT_SESSION_RESUME, move |params| {
        let request: SessionResumeRequest = parse_params(params)?;
        let response: SessionResumeResponse =
            crate::clients::resume_session(&agent_session_resume_state, &request)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_discover_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_DISCOVER, move |params| {
        let request: ProviderDiscoverRequest = parse_params(params)?;
        let response = agent_provider_discover_state
            .provider_registry
            .discover(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_resolve_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_RESOLVE_CAPABILITY, move |params| {
        let request: ProviderResolveCapabilityRequest = parse_params(params)?;
        let response =
            crate::clients::resolve_provider_capability(&agent_provider_resolve_state, &request)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_descriptor_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_GET_DESCRIPTOR, move |params| {
        let request: ProviderGetDescriptorRequest = parse_params(params)?;
        let response = agent_provider_descriptor_state
            .provider_registry
            .get_descriptor(&request.provider_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_health_get_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_HEALTH_GET, move |params| {
        let request: ProviderHealthGetRequest = parse_params(params)?;
        let response = agent_provider_health_get_state
            .provider_registry
            .health_get(request.provider_id.as_deref())
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_health_report_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_HEALTH_REPORT, move |params| {
        let request: ProviderHealthReportRequest = parse_params(params)?;
        let response = agent_provider_health_report_state
            .provider_registry
            .report_health(&request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_disable_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_DISABLE, move |params| {
        let request: ProviderDisableRequest = parse_params(params)?;
        let response = agent_provider_disable_state
            .provider_registry
            .disable(&request.provider_id, request.reason)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_enable_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_ENABLE, move |params| {
        let request: ProviderEnableRequest = parse_params(params)?;
        let response = agent_provider_enable_state
            .provider_registry
            .enable(&request.provider_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_register_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_REGISTER, move |params| {
        let request: ProviderRegisterRequest = parse_params(params)?;
        let response = agent_provider_register_state
            .provider_registry
            .register(request.descriptor)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_provider_unregister_state = state.clone();
    router.register_method(methods::AGENT_PROVIDER_UNREGISTER, move |params| {
        let request: ProviderUnregisterRequest = parse_params(params)?;
        agent_provider_unregister_state
            .provider_registry
            .unregister(&request.provider_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(serde_json::json!({
            "provider_id": request.provider_id,
            "unregistered": true,
        }))
    });

    let agent_task_get_state = state.clone();
    router.register_method(methods::AGENT_TASK_GET, move |params| {
        let request: AgentTaskGetRequest = parse_params(params)?;
        let response = build_agent_task_get_response(&agent_task_get_state, &request)?;
        json(response)
    });

    let agent_task_list_state = state.clone();
    router.register_method(methods::AGENT_TASK_LIST, move |params| {
        let request: TaskListRequest = parse_params(params)?;
        let tasks = crate::clients::list_tasks(
            &agent_task_list_state,
            &request.session_id,
            request.state.as_deref(),
            request.limit,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(aios_contracts::TaskListResponse { tasks })
    });

    let agent_task_create_state = state.clone();
    router.register_method(methods::AGENT_TASK_CREATE, move |params| {
        let request: TaskCreateRequest = parse_params(params)?;
        let response = crate::clients::create_task_request(&agent_task_create_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_task_update_state = state.clone();
    router.register_method(methods::AGENT_TASK_STATE_UPDATE, move |params| {
        let request: TaskStateUpdateRequest = parse_params(params)?;
        let response =
            crate::clients::update_task_state_request(&agent_task_update_state, &request)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_task_events_state = state.clone();
    router.register_method(methods::AGENT_TASK_EVENTS_LIST, move |params| {
        let request: TaskEventListRequest = parse_params(params)?;
        let response = crate::clients::list_task_events(
            &agent_task_events_state,
            &request.task_id,
            request.limit,
            request.reverse,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_task_plan_put_state = state.clone();
    router.register_method(methods::AGENT_TASK_PLAN_PUT, move |params| {
        let request: TaskPlanPutRequest = parse_params(params)?;
        let response =
            crate::clients::persist_task_plan_request(&agent_task_plan_put_state, &request)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_task_plan_state = state.clone();
    router.register_method(methods::AGENT_TASK_PLAN_GET, move |params| {
        let request: TaskPlanGetRequest = parse_params(params)?;
        let response =
            crate::clients::get_task_plan_record(&agent_task_plan_state, &request.task_id)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_session_list_state = state.clone();
    router.register_method(methods::AGENT_SESSION_LIST, move |params| {
        let request: SessionListRequest = parse_params(params)?;
        let response = crate::clients::list_sessions(&agent_session_list_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_session_evidence_state = state.clone();
    router.register_method(methods::AGENT_SESSION_EVIDENCE_GET, move |params| {
        let request: SessionEvidenceRequest = parse_params(params)?;
        let response =
            crate::clients::get_session_evidence(&agent_session_evidence_state, &request)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_session_evidence_export_state = state.clone();
    router.register_method(methods::AGENT_SESSION_EVIDENCE_EXPORT, move |params| {
        let request: SessionEvidenceExportRequest = parse_params(params)?;
        let response =
            crate::clients::export_session_evidence(&agent_session_evidence_export_state, &request)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_approval_create_state = state.clone();
    router.register_method(methods::AGENT_APPROVAL_CREATE, move |params| {
        let request: ApprovalCreateRequest = parse_params(params)?;
        let response = crate::clients::create_approval(&agent_approval_create_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_approval_get_state = state.clone();
    router.register_method(methods::AGENT_APPROVAL_GET, move |params| {
        let request: ApprovalGetRequest = parse_params(params)?;
        let response =
            crate::clients::get_approval(&agent_approval_get_state, &request.approval_ref)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_approval_list_state = state.clone();
    router.register_method(methods::AGENT_APPROVAL_LIST, move |params| {
        let request: ApprovalListRequest = parse_params(params)?;
        let response = crate::clients::list_approvals_request(&agent_approval_list_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_approval_resolve_state = state.clone();
    router.register_method(methods::AGENT_APPROVAL_RESOLVE, move |params| {
        let request: ApprovalResolveRequest = parse_params(params)?;
        let response = crate::clients::resolve_approval(&agent_approval_resolve_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_portal_issue_state = state.clone();
    router.register_method(methods::AGENT_PORTAL_HANDLE_ISSUE, move |params| {
        let request: PortalIssueHandleRequest = parse_params(params)?;
        let response = crate::clients::issue_portal_handle(&agent_portal_issue_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_portal_revoke_state = state.clone();
    router.register_method(methods::AGENT_PORTAL_HANDLE_REVOKE, move |params| {
        let request: PortalRevokeHandleRequest = parse_params(params)?;
        let response = crate::clients::revoke_portal_handle(&agent_portal_revoke_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_portal_list_state = state.clone();
    router.register_method(methods::AGENT_PORTAL_HANDLE_LIST, move |params| {
        let request: PortalListHandlesRequest = parse_params(params)?;
        let response = crate::clients::list_portal_handles(&agent_portal_list_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_policy_token_issue_state = state.clone();
    router.register_method(methods::AGENT_POLICY_TOKEN_ISSUE, move |params| {
        let request: TokenIssueRequest = parse_params(params)?;
        let response = crate::clients::issue_execution_token_request(
            &agent_policy_token_issue_state,
            &request,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_policy_token_verify_state = state.clone();
    router.register_method(methods::AGENT_POLICY_TOKEN_VERIFY, move |params| {
        let request: TokenVerifyRequest = parse_params(params)?;
        let response = crate::clients::verify_execution_token_request(
            &agent_policy_token_verify_state,
            &request,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_audit_query_state = state.clone();
    router.register_method(methods::AGENT_AUDIT_QUERY, move |params| {
        let request: AuditQueryRequest = parse_params(params)?;
        let response = crate::clients::query_audit(&agent_audit_query_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let agent_audit_export_state = state.clone();
    router.register_method(methods::AGENT_AUDIT_EXPORT, move |params| {
        let request: AuditExportRequest = parse_params(params)?;
        let response = crate::clients::export_audit(&agent_audit_export_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });
    let submit_state = state.clone();
    router.register_method(methods::AGENT_INTENT_SUBMIT, move |params| {
        let request: AgentIntentSubmitRequest = parse_params(params)?;
        if request.intent.trim().is_empty() {
            return Err(RpcError::invalid_params_code(
                "intent_empty",
                "intent cannot be empty",
            ));
        }

        let (session, mut task) = crate::clients::create_or_resume_session(&submit_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let plan = crate::planner::plan_for_task(
            session.session_id.clone(),
            task.task_id.clone(),
            request.intent.clone(),
        );
        crate::clients::persist_task_plan(&submit_state, &task.task_id, &plan)
            .map_err(|error| RpcError::Internal(error.to_string()))?;

        let primary_capability = plan
            .candidate_capabilities
            .first()
            .cloned()
            .unwrap_or_else(|| "system.intent.execute".to_string());
        let provider_resolution =
            crate::providers::resolve_primary_provider(&submit_state, &primary_capability)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        let selected_provider_id = provider_resolution
            .selected
            .as_ref()
            .map(|candidate| candidate.provider_id.as_str());
        let portal_handle = crate::portal::maybe_issue_handle(
            &submit_state,
            &request,
            &session.session_id,
            &primary_capability,
            selected_provider_id,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        let execution_location = provider_resolution
            .selected
            .as_ref()
            .map(|candidate| candidate.execution_location.clone())
            .unwrap_or_else(|| "local".to_string());
        let policy = crate::clients::evaluate_primary_capability(
            &submit_state,
            &request.user_id,
            &session.session_id,
            &task.task_id,
            &request.intent,
            &primary_capability,
            &execution_location,
            portal_handle.as_ref().and_then(crate::portal::target_hash),
            BTreeMap::new(),
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;

        if policy.decision.decision == "denied" {
            task = crate::clients::update_task_state(
                &submit_state,
                &task.task_id,
                "rejected",
                Some("policy-denied"),
            )
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        } else if policy.decision.decision == "allowed" && provider_resolution.selected.is_some() {
            task = crate::clients::update_task_state(
                &submit_state,
                &task.task_id,
                "approved",
                Some("policy-allowed-provider-resolved"),
            )
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        }

        let execution_token =
            if policy.decision.decision == "allowed" && provider_resolution.selected.is_some() {
                crate::clients::issue_execution_token(
                    &submit_state,
                    &request.user_id,
                    &session.session_id,
                    &task.task_id,
                    &primary_capability,
                    portal_handle.as_ref().and_then(crate::portal::target_hash),
                    &execution_location,
                    &policy,
                )
                .map_err(|error| RpcError::Internal(error.to_string()))?
            } else {
                None
            };
        let route = crate::clients::resolve_route(&submit_state, Some("local-cpu".to_string()))
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let runtime_preview = if plan
            .candidate_capabilities
            .iter()
            .any(|item| item == "runtime.infer.submit")
            && policy.decision.decision == "allowed"
            && provider_resolution.selected.is_some()
        {
            Some(
                crate::clients::preview_runtime(
                    &submit_state,
                    &session.session_id,
                    &task.task_id,
                    &request.intent,
                )
                .map_err(|error| RpcError::Internal(error.to_string()))?,
            )
        } else {
            None
        };
        crate::clients::persist_working_memory(
            &submit_state,
            &session.session_id,
            &request.intent,
            &plan,
            Some(&provider_resolution),
            Some(&route),
            portal_handle
                .as_ref()
                .map(|handle| handle.handle_id.as_str()),
            &task.state,
            Some(&policy),
            execution_token.as_ref(),
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::append_episodic_memory(
            &submit_state,
            &session.session_id,
            &task.task_id,
            &request.intent,
            &plan,
            &task.state,
            portal_handle
                .as_ref()
                .map(|handle| handle.handle_id.as_str()),
            Some(&policy),
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::persist_semantic_memory(
            &submit_state,
            &session.session_id,
            &task.task_id,
            &request.intent,
            &primary_capability,
            Some(&provider_resolution),
            Some(&route),
            Some(&policy),
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;

        let provider_execution =
            if policy.decision.decision == "allowed" && provider_resolution.selected.is_some() {
                crate::execution::maybe_execute_first_party_provider(
                    &submit_state,
                    &request.intent,
                    &provider_resolution,
                    execution_token.as_ref(),
                    portal_handle.as_ref(),
                )
            } else {
                None
            };

        if let Some(outcome) = provider_execution.as_ref() {
            match outcome.status.as_str() {
                "completed" => {
                    task = crate::clients::update_task_state(
                        &submit_state,
                        &task.task_id,
                        "executing",
                        Some("agent.provider-execution-started"),
                    )
                    .map_err(|error| RpcError::Internal(error.to_string()))?;
                    task = crate::clients::update_task_state(
                        &submit_state,
                        &task.task_id,
                        "completed",
                        Some("agent.provider-execution-completed"),
                    )
                    .map_err(|error| RpcError::Internal(error.to_string()))?;
                }
                "failed" => {
                    task = crate::clients::update_task_state(
                        &submit_state,
                        &task.task_id,
                        "failed",
                        Some("agent.provider-execution-failed"),
                    )
                    .map_err(|error| RpcError::Internal(error.to_string()))?;
                }
                _ => {}
            }
            crate::clients::persist_provider_execution_outcome(
                &submit_state,
                &session.session_id,
                &task.task_id,
                outcome,
            )
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        }

        json(AgentIntentSubmissionResponse {
            session,
            task,
            plan,
            policy,
            route,
            provider_resolution: Some(provider_resolution),
            portal_handle,
            execution_token,
            runtime_preview,
            provider_execution,
        })
    });

    let plan_state = state.clone();
    router.register_method(methods::AGENT_TASK_PLAN, move |params| {
        let request: AgentPlanRequest = parse_params(params)?;
        if request.intent.trim().is_empty() {
            return Err(RpcError::invalid_params_code(
                "intent_empty",
                "intent cannot be empty",
            ));
        }

        let session_id = request.session_id;
        let intent = request.intent;
        let task = crate::clients::create_task(&plan_state, &session_id, &intent, "planned")
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let plan =
            crate::planner::plan_for_task(session_id.clone(), task.task_id.clone(), intent.clone());
        crate::clients::persist_task_plan(&plan_state, &plan.task_id, &plan)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let primary_capability = plan
            .candidate_capabilities
            .first()
            .cloned()
            .unwrap_or_else(|| "system.intent.execute".to_string());
        let provider_resolution =
            crate::providers::resolve_primary_provider(&plan_state, &primary_capability)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::persist_working_memory(
            &plan_state,
            &session_id,
            &intent,
            &plan,
            Some(&provider_resolution),
            None,
            None,
            &task.state,
            None,
            None,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::append_episodic_memory(
            &plan_state,
            &session_id,
            &task.task_id,
            &intent,
            &plan,
            &task.state,
            None,
            None,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::persist_semantic_memory(
            &plan_state,
            &session_id,
            &task.task_id,
            &intent,
            &primary_capability,
            Some(&provider_resolution),
            None,
            None,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(plan)
    });

    let replan_state = state.clone();
    router.register_method(methods::AGENT_TASK_REPLAN, move |params| {
        let request: AgentPlanRequest = parse_params(params)?;
        if request.intent.trim().is_empty() {
            return Err(RpcError::invalid_params_code(
                "intent_empty",
                "intent cannot be empty",
            ));
        }

        let session_id = request.session_id;
        let intent = request.intent;
        let session_tasks = crate::clients::list_tasks(&replan_state, &session_id, None, Some(20))
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let basis_task = select_replan_basis(&session_tasks);
        let basis_task_id = basis_task.as_ref().map(|task| task.task_id.clone());
        let basis_task_state = basis_task.as_ref().map(|task| task.state.clone());
        let basis_task_marked_replanned = if let Some(task) = basis_task.as_ref() {
            if can_mark_task_replanned(&task.state) {
                crate::clients::update_task_state(
                    &replan_state,
                    &task.task_id,
                    "replanned",
                    Some("agent.replan-basis"),
                )
                .map_err(|error| RpcError::Internal(error.to_string()))?;
                true
            } else {
                false
            }
        } else {
            false
        };

        let task = crate::clients::create_task(&replan_state, &session_id, &intent, "planned")
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let plan =
            crate::planner::plan_for_task(session_id.clone(), task.task_id.clone(), intent.clone());
        crate::clients::persist_task_plan(&replan_state, &plan.task_id, &plan)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let primary_capability = plan
            .candidate_capabilities
            .first()
            .cloned()
            .unwrap_or_else(|| "system.intent.execute".to_string());
        let provider_resolution =
            crate::providers::resolve_primary_provider(&replan_state, &primary_capability)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::persist_working_memory(
            &replan_state,
            &session_id,
            &intent,
            &plan,
            Some(&provider_resolution),
            None,
            None,
            &task.state,
            None,
            None,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::append_episodic_memory(
            &replan_state,
            &session_id,
            &task.task_id,
            &intent,
            &plan,
            &task.state,
            None,
            None,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        crate::clients::persist_semantic_memory(
            &replan_state,
            &session_id,
            &task.task_id,
            &intent,
            &primary_capability,
            Some(&provider_resolution),
            None,
            None,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(serde_json::json!({
            "plan": plan,
            "task_state": task.state,
            "fallback": replan_fallback_label(basis_task.as_ref()),
            "basis_task_id": basis_task_id,
            "basis_task_state": basis_task_state,
            "basis_task_marked_replanned": basis_task_marked_replanned,
            "session_task_count": session_tasks.len(),
        }))
    });

    let resume_state = state.clone();
    router.register_method(methods::AGENT_TASK_RESUME, move |params| {
        let request: AgentTaskResumeRequest = parse_params(params)?;
        let mut task = crate::clients::get_task(&resume_state, &request.task_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        if !can_resume_task(&task.state) {
            return Err(RpcError::precondition_failed(
                "task_not_resumable",
                format!(
                    "task {} cannot resume from state {}",
                    task.task_id, task.state
                ),
            ));
        }

        let plan = crate::clients::get_task_plan(&resume_state, &request.task_id)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let primary_capability = plan
            .candidate_capabilities
            .first()
            .cloned()
            .unwrap_or_else(|| "system.intent.execute".to_string());
        if primary_capability != methods::SYSTEM_FILE_BULK_DELETE {
            return Err(RpcError::precondition_failed(
                "resume_unsupported_capability",
                format!(
                    "capability {} is not resumable in agentd",
                    primary_capability
                ),
            ));
        }

        let approval = resolve_resume_approval(&resume_state, &request, &task.task_id)?;
        if approval.capability_id != primary_capability {
            return Err(RpcError::conflict(
                "approval_capability_mismatch",
                format!(
                    "approval {} binds capability {}, expected {}",
                    approval.approval_ref, approval.capability_id, primary_capability
                ),
            ));
        }

        let provider_resolution =
            crate::providers::resolve_primary_provider(&resume_state, &primary_capability)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        let selected_provider = provider_resolution.selected.as_ref().ok_or_else(|| {
            RpcError::precondition_failed(
                "provider_not_resolved",
                format!("no provider selected for capability {}", primary_capability),
            )
        })?;
        if selected_provider.execution_location != approval.execution_location {
            return Err(RpcError::conflict(
                "approval_execution_location_mismatch",
                format!(
                    "approval {} allows {}, but provider resolved to {}",
                    approval.approval_ref,
                    approval.execution_location,
                    selected_provider.execution_location
                ),
            ));
        }

        let working_memory = crate::clients::read_working_memory_ref(
            &resume_state,
            &task.session_id,
            &format!("wm-plan-{}", task.task_id),
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;
        let handle_id = working_memory
            .as_ref()
            .and_then(|record| working_memory_portal_handle_id(&record.payload))
            .ok_or_else(|| {
                RpcError::precondition_failed(
                    "portal_handle_missing",
                    format!(
                        "task {} is missing portal_handle_id in working memory",
                        task.task_id
                    ),
                )
            })?;
        let portal_handle = crate::clients::lookup_portal_handle(
            &resume_state,
            handle_id,
            &task.session_id,
            &approval.user_id,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?
        .ok_or_else(|| RpcError::resource_not_found("portal_handle", handle_id))?;

        let execution_token =
            crate::clients::issue_approval_execution_token(&resume_state, &approval)
                .map_err(|error| RpcError::Internal(error.to_string()))?;
        let provider_execution = crate::execution::resume_approved_provider_execution(
            &resume_state,
            &provider_resolution,
            &execution_token,
            &portal_handle,
        )
        .ok_or_else(|| {
            RpcError::precondition_failed(
                "resume_execution_unsupported",
                format!(
                    "provider {} cannot resume {}",
                    selected_provider.provider_id, primary_capability
                ),
            )
        })?;

        if task.state != "approved" {
            task = crate::clients::update_task_state(
                &resume_state,
                &task.task_id,
                "approved",
                Some("agent.resume-approval-validated"),
            )
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        }

        match provider_execution.status.as_str() {
            "completed" => {
                task = crate::clients::update_task_state(
                    &resume_state,
                    &task.task_id,
                    "executing",
                    Some("agent.resume-provider-execution-started"),
                )
                .map_err(|error| RpcError::Internal(error.to_string()))?;
                task = crate::clients::update_task_state(
                    &resume_state,
                    &task.task_id,
                    "completed",
                    Some("agent.resume-provider-execution-completed"),
                )
                .map_err(|error| RpcError::Internal(error.to_string()))?;
            }
            "failed" => {
                task = crate::clients::update_task_state(
                    &resume_state,
                    &task.task_id,
                    "failed",
                    Some("agent.resume-provider-execution-failed"),
                )
                .map_err(|error| RpcError::Internal(error.to_string()))?;
            }
            _ => {}
        }

        crate::clients::persist_provider_execution_outcome(
            &resume_state,
            &task.session_id,
            &task.task_id,
            &provider_execution,
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;

        json(AgentTaskResumeResponse {
            task,
            plan,
            approval,
            provider_resolution,
            portal_handle,
            execution_token,
            provider_execution: Some(provider_execution),
        })
    });

    Arc::new(router)
}

fn select_replan_basis(tasks: &[TaskRecord]) -> Option<TaskRecord> {
    tasks.first().cloned()
}

fn can_mark_task_replanned(state: &str) -> bool {
    matches!(state, "planned" | "failed")
}

fn replan_fallback_label(basis_task: Option<&TaskRecord>) -> &'static str {
    if basis_task.is_some() {
        "replanned-from-existing-session"
    } else {
        "planned-without-basis-task"
    }
}

fn can_resume_task(state: &str) -> bool {
    matches!(state, "planned" | "approved" | "failed")
}

fn resolve_resume_approval(
    state: &AppState,
    request: &AgentTaskResumeRequest,
    task_id: &str,
) -> Result<aios_contracts::ApprovalRecord, RpcError> {
    let approval = if let Some(approval_ref) = request.approval_ref.as_deref() {
        crate::clients::get_approval(state, approval_ref)
            .map_err(|error| RpcError::Internal(error.to_string()))?
    } else {
        let approvals = crate::clients::list_approvals(state, task_id, Some("approved"))
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        match approvals.len() {
            0 => {
                return Err(RpcError::precondition_failed(
                    "approval_missing",
                    format!("task {} has no approved approval to resume", task_id),
                ));
            }
            1 => approvals.into_iter().next().expect("single approval"),
            _ => {
                return Err(RpcError::conflict(
                    "approval_ambiguous",
                    format!(
                        "task {} has multiple approved approvals; specify approval_ref",
                        task_id
                    ),
                ));
            }
        }
    };

    if approval.task_id != task_id {
        return Err(RpcError::conflict(
            "approval_task_mismatch",
            format!(
                "approval {} does not belong to task {}",
                approval.approval_ref, task_id
            ),
        ));
    }
    if approval.status != "approved" {
        return Err(RpcError::precondition_failed(
            "approval_not_approved",
            format!("approval {} is {}", approval.approval_ref, approval.status),
        ));
    }

    Ok(approval)
}

fn working_memory_portal_handle_id(payload: &Value) -> Option<&str> {
    payload.get("portal_handle_id").and_then(Value::as_str)
}

fn build_agent_task_get_response(
    state: &AppState,
    request: &AgentTaskGetRequest,
) -> Result<AgentTaskGetResponse, RpcError> {
    let task = crate::clients::get_task(state, &request.task_id)
        .map_err(|error| RpcError::Internal(error.to_string()))?;
    let mut notes = Vec::new();

    let plan = match crate::clients::try_get_task_plan(state, &request.task_id) {
        Ok(plan) => plan,
        Err(error) => {
            notes.push(format!("task_plan_unavailable={error}"));
            None
        }
    };

    let events = match crate::clients::list_task_events(
        state,
        &request.task_id,
        request.event_limit,
        true,
    ) {
        Ok(response) => response.events,
        Err(error) => {
            notes.push(format!("task_events_unavailable={error}"));
            Vec::new()
        }
    };

    let approvals = match crate::clients::list_approvals(state, &request.task_id, None) {
        Ok(approvals) => approvals,
        Err(error) => {
            notes.push(format!("approvals_unavailable={error}"));
            Vec::new()
        }
    };

    let plan_summary = match crate::clients::read_working_memory_ref(
        state,
        &task.session_id,
        &format!("wm-plan-{}", task.task_id),
    ) {
        Ok(record) => record,
        Err(error) => {
            notes.push(format!("plan_summary_unavailable={error}"));
            None
        }
    };
    let portal_handle_id = plan_summary
        .as_ref()
        .and_then(|record| working_memory_portal_handle_id(&record.payload))
        .map(str::to_string);

    let portal_handle = if let Some(handle_id) = portal_handle_id.as_deref() {
        match crate::clients::list_portal_handles(
            state,
            &PortalListHandlesRequest {
                session_id: Some(task.session_id.clone()),
            },
        ) {
            Ok(response) => response
                .handles
                .into_iter()
                .find(|item| item.handle_id == handle_id),
            Err(error) => {
                notes.push(format!("portal_handles_unavailable={error}"));
                None
            }
        }
    } else {
        None
    };

    let provider_resolution = if let Some(capability_id) = primary_capability(plan.as_ref()) {
        match crate::providers::resolve_primary_provider(state, capability_id) {
            Ok(response) => Some(response),
            Err(error) => {
                notes.push(format!("provider_resolution_unavailable={error}"));
                None
            }
        }
    } else {
        None
    };

    let provider_execution = match crate::clients::read_working_memory_ref(
        state,
        &task.session_id,
        &format!("wm-provider-execution-{}", task.task_id),
    ) {
        Ok(Some(record)) => provider_execution_from_payload(&record.payload),
        Ok(None) => None,
        Err(error) => {
            notes.push(format!("provider_execution_unavailable={error}"));
            None
        }
    };

    Ok(AgentTaskGetResponse {
        task,
        plan,
        events,
        approvals,
        portal_handle_id,
        portal_handle,
        provider_resolution,
        route: plan_summary
            .as_ref()
            .and_then(|record| working_memory_value(&record.payload, "route")),
        policy: plan_summary
            .as_ref()
            .and_then(|record| working_memory_value(&record.payload, "policy")),
        execution_token: plan_summary
            .as_ref()
            .and_then(|record| working_memory_value(&record.payload, "execution_token")),
        provider_execution,
        notes,
    })
}

fn primary_capability(plan: Option<&AgentPlan>) -> Option<&str> {
    plan.and_then(|item| item.candidate_capabilities.first().map(String::as_str))
}

fn working_memory_value(payload: &Value, key: &str) -> Option<Value> {
    payload.get(key).filter(|value| !value.is_null()).cloned()
}

fn provider_execution_from_payload(payload: &Value) -> Option<AgentProviderExecutionResult> {
    let provider_id = payload.get("provider_id")?.as_str()?.to_string();
    let capability_id = payload.get("capability_id")?.as_str()?.to_string();
    let status = payload.get("status")?.as_str()?.to_string();
    let task_state = payload.get("task_state")?.as_str()?.to_string();
    let result = payload.get("result").cloned().unwrap_or(Value::Null);
    let notes = payload
        .get("notes")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    Some(AgentProviderExecutionResult {
        provider_id,
        capability_id,
        status,
        task_state,
        result,
        notes,
    })
}
fn parse_params<T>(params: Option<Value>) -> Result<T, RpcError>
where
    T: DeserializeOwned,
{
    serde_json::from_value(params.unwrap_or(Value::Null))
        .map_err(|error| RpcError::invalid_params_code("invalid_json_params", error.to_string()))
}

fn json<T>(value: T) -> RpcResult
where
    T: Serialize,
{
    serde_json::to_value(value).map_err(|error| {
        RpcError::internal_code("response_serialization_failed", error.to_string())
    })
}

#[cfg(test)]
mod tests {
    use aios_contracts::TaskRecord;
    use serde_json::json;

    use super::*;

    fn task(task_id: &str, state: &str) -> TaskRecord {
        TaskRecord {
            task_id: task_id.to_string(),
            session_id: "session-1".to_string(),
            state: state.to_string(),
            title: Some("task".to_string()),
            created_at: "2026-01-01T00:00:00Z".to_string(),
        }
    }

    #[test]
    fn select_replan_basis_uses_latest_task() {
        let tasks = vec![
            task("task-newest", "approved"),
            task("task-older", "failed"),
        ];
        let selected = select_replan_basis(&tasks).expect("basis task");
        assert_eq!(selected.task_id, "task-newest");
    }

    #[test]
    fn only_planned_or_failed_tasks_can_be_marked_replanned() {
        assert!(can_mark_task_replanned("planned"));
        assert!(can_mark_task_replanned("failed"));
        assert!(!can_mark_task_replanned("approved"));
        assert!(!can_mark_task_replanned("completed"));
    }

    #[test]
    fn fallback_label_reflects_basis_presence() {
        assert_eq!(
            replan_fallback_label(Some(&task("task-1", "planned"))),
            "replanned-from-existing-session"
        );
        assert_eq!(replan_fallback_label(None), "planned-without-basis-task");
    }

    #[test]
    fn only_planned_approved_or_failed_tasks_can_resume() {
        assert!(can_resume_task("planned"));
        assert!(can_resume_task("approved"));
        assert!(can_resume_task("failed"));
        assert!(!can_resume_task("completed"));
        assert!(!can_resume_task("rejected"));
    }

    #[test]
    fn working_memory_portal_handle_id_reads_handle_id_from_payload() {
        let payload = json!({
            "portal_handle_id": "hdl-1",
            "task_id": "task-1",
        });

        assert_eq!(working_memory_portal_handle_id(&payload), Some("hdl-1"));
    }

    #[test]
    fn working_memory_value_returns_non_null_field() {
        let payload = json!({
            "route": {"selected_backend": "local-cpu"},
            "policy": null,
        });

        assert_eq!(
            working_memory_value(&payload, "route"),
            Some(json!({"selected_backend": "local-cpu"}))
        );
        assert_eq!(working_memory_value(&payload, "policy"), None);
    }

    #[test]
    fn provider_execution_from_payload_decodes_summary() {
        let payload = json!({
            "provider_id": "system.files.local",
            "capability_id": "system.file.bulk_delete",
            "status": "completed",
            "task_state": "completed",
            "result": {"status": "deleted"},
            "notes": ["provider_rpc=system.file.bulk_delete"],
        });

        let execution =
            provider_execution_from_payload(&payload).expect("provider execution summary");
        assert_eq!(execution.provider_id, "system.files.local");
        assert_eq!(execution.capability_id, "system.file.bulk_delete");
        assert_eq!(execution.status, "completed");
        assert_eq!(execution.result["status"], "deleted");
        assert_eq!(
            execution.notes,
            vec!["provider_rpc=system.file.bulk_delete".to_string()]
        );
    }
}
