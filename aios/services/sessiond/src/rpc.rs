use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::Value;

use aios_contracts::{
    methods, EpisodicMemoryAppendRequest, EpisodicMemoryListRequest, PortalIssueHandleRequest,
    PortalListHandlesRequest, PortalLookupHandleRequest, PortalRevokeHandleRequest,
    ProceduralMemoryListRequest, ProceduralMemoryPutRequest, SemanticMemoryListRequest,
    SemanticMemoryPutRequest, ServiceContractResponse, SessionCloseRequest, SessionCloseResponse,
    SessionCreateRequest, SessionCreateResponse, SessionEvidenceExportRequest,
    SessionEvidenceRequest, SessionListRequest, SessionResumeRequest, SessionResumeResponse,
    TaskCreateRequest, TaskCreateResponse, TaskEventListRequest, TaskGetRequest, TaskListRequest,
    TaskPlanGetRequest, TaskPlanPutRequest, TaskStateUpdateRequest, WorkingMemoryReadRequest,
    WorkingMemoryWriteRequest,
};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::AppState;

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("sessiond");

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

    let session_state = state.clone();
    router.register_method(methods::SESSION_CREATE, move |params| {
        let request: SessionCreateRequest = parse_params(params)?;
        let initial_title = request
            .metadata
            .get("initial_intent")
            .and_then(|value| value.as_str())
            .unwrap_or("initial-session-bootstrap")
            .to_string();
        let session = session_state
            .sessions
            .create(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        let task = session_state
            .tasks
            .create(TaskCreateRequest {
                session_id: session.session_id.clone(),
                title: Some(initial_title),
                state: "planned".to_string(),
            })
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(SessionCreateResponse { session, task })
    });

    let resume_state = state.clone();
    router.register_method(methods::SESSION_RESUME, move |params| {
        let request: SessionResumeRequest = parse_params(params)?;
        let session = resume_state
            .sessions
            .resume(request)
            .map_err(internal)?
            .ok_or_else(|| RpcError::resource_not_found("session", "unknown session_id"))?;
        let recovery = crate::recovery::baseline_ref(&resume_state.database, &session.session_id)
            .map_err(internal)?;
        json(SessionResumeResponse { session, recovery })
    });

    let session_list_state = state.clone();
    router.register_method(methods::SESSION_LIST, move |params| {
        let request: SessionListRequest = parse_params(params)?;
        let sessions = session_list_state
            .sessions
            .list(request)
            .map_err(internal)?;
        json(sessions)
    });

    let close_state = state.clone();
    router.register_method(methods::SESSION_CLOSE, move |params| {
        let request: SessionCloseRequest = parse_params(params)?;
        let session = close_state
            .sessions
            .close(request)
            .map_err(internal)?
            .ok_or_else(|| RpcError::resource_not_found("session", "unknown session_id"))?;
        json(SessionCloseResponse { session })
    });

    let evidence_state = state.clone();
    router.register_method(methods::SESSION_EVIDENCE_GET, move |params| {
        let request: SessionEvidenceRequest = parse_params(params)?;
        let response = crate::evidence::collect(&evidence_state, &request)
            .map_err(internal)
            .map_err(|error| {
                if error.to_string().contains("session ")
                    && error.to_string().contains(" not found")
                {
                    RpcError::resource_not_found("session", &request.session_id)
                } else {
                    error
                }
            })?;
        json(response)
    });

    let evidence_export_state = state.clone();
    router.register_method(methods::SESSION_EVIDENCE_EXPORT, move |params| {
        let request: SessionEvidenceExportRequest = parse_params(params)?;
        let evidence = crate::evidence::collect(
            &evidence_export_state,
            &SessionEvidenceRequest {
                session_id: request.session_id.clone(),
                limit: request.limit,
            },
        )
        .map_err(internal)
        .map_err(|error| {
            if error.to_string().contains("session ") && error.to_string().contains(" not found") {
                RpcError::resource_not_found("session", &request.session_id)
            } else {
                error
            }
        })?;
        let response = crate::evidence::export_bundle(
            &evidence_export_state.config.service_id,
            &evidence_export_state.config.evidence_export_dir,
            &request,
            &evidence,
        )
        .map_err(internal)?;
        json(response)
    });

    let task_create_state = state.clone();
    router.register_method(methods::TASK_CREATE, move |params| {
        let request: TaskCreateRequest = parse_params(params)?;
        let task = task_create_state
            .tasks
            .create(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(TaskCreateResponse { task })
    });

    let task_get_state = state.clone();
    router.register_method(methods::TASK_GET, move |params| {
        let request: TaskGetRequest = parse_params(params)?;
        let task = task_get_state
            .tasks
            .get(request)
            .map_err(internal)?
            .ok_or_else(|| RpcError::resource_not_found("task", "unknown task_id"))?;
        json(task)
    });

    let task_list_state = state.clone();
    router.register_method(methods::TASK_LIST, move |params| {
        let request: TaskListRequest = parse_params(params)?;
        let tasks = task_list_state
            .tasks
            .list(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(tasks)
    });

    let task_state_update_state = state.clone();
    router.register_method(methods::TASK_STATE_UPDATE, move |params| {
        let request: TaskStateUpdateRequest = parse_params(params)?;
        let task = task_state_update_state
            .tasks
            .update_state(request)
            .map_err(internal)?
            .ok_or_else(|| RpcError::resource_not_found("task", "unknown task_id"))?;
        json(task)
    });

    let task_events_state = state.clone();
    router.register_method(methods::TASK_EVENTS_LIST, move |params| {
        let request: TaskEventListRequest = parse_params(params)?;
        let events = task_events_state
            .tasks
            .list_events(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(events)
    });

    let task_plan_put_state = state.clone();
    router.register_method(methods::TASK_PLAN_PUT, move |params| {
        let request: TaskPlanPutRequest = parse_params(params)?;
        let record = task_plan_put_state
            .plans
            .put(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(record)
    });

    let task_plan_get_state = state.clone();
    router.register_method(methods::TASK_PLAN_GET, move |params| {
        let request: TaskPlanGetRequest = parse_params(params)?;
        let record = task_plan_get_state
            .plans
            .get(request)
            .map_err(internal)?
            .ok_or_else(|| RpcError::resource_not_found("task_plan", "unknown task_id"))?;
        json(record)
    });

    let memory_write_state = state.clone();
    router.register_method(methods::MEMORY_WRITE, move |params| {
        let request: WorkingMemoryWriteRequest = parse_params(params)?;
        let record = memory_write_state
            .memory
            .write(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(record)
    });

    let memory_read_state = state.clone();
    router.register_method(methods::MEMORY_READ, move |params| {
        let request: WorkingMemoryReadRequest = parse_params(params)?;
        let response = memory_read_state
            .memory
            .read(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let episodic_append_state = state.clone();
    router.register_method(methods::MEMORY_EPISODIC_APPEND, move |params| {
        let request: EpisodicMemoryAppendRequest = parse_params(params)?;
        let record = episodic_append_state
            .memory
            .append_episodic(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(record)
    });

    let episodic_list_state = state.clone();
    router.register_method(methods::MEMORY_EPISODIC_LIST, move |params| {
        let request: EpisodicMemoryListRequest = parse_params(params)?;
        let response = episodic_list_state
            .memory
            .list_episodic(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let semantic_put_state = state.clone();
    router.register_method(methods::MEMORY_SEMANTIC_PUT, move |params| {
        let request: SemanticMemoryPutRequest = parse_params(params)?;
        let record = semantic_put_state
            .memory
            .put_semantic(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(record)
    });

    let semantic_list_state = state.clone();
    router.register_method(methods::MEMORY_SEMANTIC_LIST, move |params| {
        let request: SemanticMemoryListRequest = parse_params(params)?;
        let response = semantic_list_state
            .memory
            .list_semantic(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let procedural_put_state = state.clone();
    router.register_method(methods::MEMORY_PROCEDURAL_PUT, move |params| {
        let request: ProceduralMemoryPutRequest = parse_params(params)?;
        let record = procedural_put_state
            .memory
            .put_procedural(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(record)
    });

    let procedural_list_state = state.clone();
    router.register_method(methods::MEMORY_PROCEDURAL_LIST, move |params| {
        let request: ProceduralMemoryListRequest = parse_params(params)?;
        let response = procedural_list_state
            .memory
            .list_procedural(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let portal_issue_state = state.clone();
    router.register_method(methods::PORTAL_HANDLE_ISSUE, move |params| {
        let request: PortalIssueHandleRequest = parse_params(params)?;
        let handle = portal_issue_state
            .portal
            .issue(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(handle)
    });

    let portal_lookup_state = state.clone();
    router.register_method(methods::PORTAL_HANDLE_LOOKUP, move |params| {
        let request: PortalLookupHandleRequest = parse_params(params)?;
        let response = portal_lookup_state
            .portal
            .lookup(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let portal_revoke_state = state.clone();
    router.register_method(methods::PORTAL_HANDLE_REVOKE, move |params| {
        let request: PortalRevokeHandleRequest = parse_params(params)?;
        let response = portal_revoke_state
            .portal
            .revoke(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    let portal_list_state = state.clone();
    router.register_method(methods::PORTAL_HANDLE_LIST, move |params| {
        let request: PortalListHandlesRequest = parse_params(params)?;
        let response = portal_list_state
            .portal
            .list(request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    Arc::new(router)
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

fn internal(error: impl std::fmt::Display) -> RpcError {
    RpcError::internal_code("sessiond_internal", error.to_string())
}
