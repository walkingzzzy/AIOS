use std::sync::Arc;
use std::collections::BTreeMap;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::Value;

use aios_contracts::{
    methods, AgentIntentSubmissionResponse, AgentIntentSubmitRequest, AgentPlanRequest,
    ProviderDisableRequest, ProviderDiscoverRequest, ProviderEnableRequest,
    ProviderGetDescriptorRequest, ProviderHealthGetRequest, ProviderHealthReportRequest,
    ProviderRegisterRequest, ProviderResolveCapabilityRequest, ProviderUnregisterRequest,
    ServiceContractResponse, TaskRecord,
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
        )
        .map_err(|error| RpcError::Internal(error.to_string()))?;

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
}
