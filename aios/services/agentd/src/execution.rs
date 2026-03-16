use serde_json::{json, Value};

use aios_contracts::{
    methods, AgentProviderExecutionResult, ExecutionToken, PortalHandleRecord,
    ProviderFsBulkDeleteRequest, ProviderFsBulkDeleteResponse, ProviderFsOpenRequest,
    ProviderResolveCapabilityResponse, SystemIntentRequest,
};

use crate::AppState;

const DEFAULT_MAX_PREVIEW_BYTES: u64 = 4096;
const DEFAULT_MAX_DIRECTORY_ENTRIES: u32 = 32;

pub fn maybe_execute_first_party_provider(
    state: &AppState,
    intent: &str,
    provider_resolution: &ProviderResolveCapabilityResponse,
    execution_token: Option<&ExecutionToken>,
    portal_handle: Option<&PortalHandleRecord>,
) -> Option<AgentProviderExecutionResult> {
    let selected = provider_resolution.selected.as_ref()?;
    let provider_id = selected.provider_id.as_str();
    let capability_id = provider_resolution.capability_id.as_str();

    match (provider_id, capability_id) {
        ("system.intent.local", methods::SYSTEM_INTENT_EXECUTE) => {
            Some(execute_system_intent(state, intent, execution_token))
        }
        ("system.files.local", methods::PROVIDER_FS_OPEN) => Some(execute_provider_fs_open(
            state,
            execution_token,
            portal_handle,
        )),
        _ => None,
    }
}

pub fn resume_approved_provider_execution(
    state: &AppState,
    provider_resolution: &ProviderResolveCapabilityResponse,
    execution_token: &ExecutionToken,
    portal_handle: &PortalHandleRecord,
) -> Option<AgentProviderExecutionResult> {
    let selected = provider_resolution.selected.as_ref()?;
    let provider_id = selected.provider_id.as_str();
    let capability_id = provider_resolution.capability_id.as_str();

    match (provider_id, capability_id) {
        ("system.files.local", methods::SYSTEM_FILE_BULK_DELETE) => Some(
            execute_provider_fs_bulk_delete(state, execution_token, portal_handle),
        ),
        _ => None,
    }
}

fn execute_system_intent(
    state: &AppState,
    intent: &str,
    execution_token: Option<&ExecutionToken>,
) -> AgentProviderExecutionResult {
    let provider_id = "system.intent.local";
    let capability_id = methods::SYSTEM_INTENT_EXECUTE;
    let mut notes = vec!["provider_rpc=system.intent.execute".to_string()];
    let Some(token) = execution_token else {
        return deferred_execution(
            provider_id,
            capability_id,
            "execution token missing for system.intent.execute",
            notes,
        );
    };

    let socket_path = &state.config.system_intent_provider_socket;
    notes.push(format!("provider_socket={}", socket_path.display()));
    if !socket_path.exists() {
        return deferred_execution(
            provider_id,
            capability_id,
            format!("provider socket unavailable: {}", socket_path.display()),
            notes,
        );
    }

    let request = SystemIntentRequest {
        execution_token: token.clone(),
        intent: intent.to_string(),
    };

    let response: anyhow::Result<aios_contracts::SystemIntentResponse> =
        aios_rpc::call_unix(socket_path, methods::SYSTEM_INTENT_EXECUTE, &request);
    match response {
        Ok(response) => {
            notes.push(format!("plan_source={}", response.plan_source.as_str()));
            notes.push(format!("requires_handoff={}", response.requires_handoff));
            completed_execution(
                provider_id,
                capability_id,
                serialize_result(&response),
                notes,
            )
        }
        Err(error) => failed_execution(provider_id, capability_id, error.to_string(), notes),
    }
}

fn execute_provider_fs_open(
    state: &AppState,
    execution_token: Option<&ExecutionToken>,
    portal_handle: Option<&PortalHandleRecord>,
) -> AgentProviderExecutionResult {
    let provider_id = "system.files.local";
    let capability_id = methods::PROVIDER_FS_OPEN;
    let Some(token) = execution_token else {
        return deferred_execution(
            provider_id,
            capability_id,
            "execution token missing for provider.fs.open",
            vec!["provider_rpc=provider.fs.open".to_string()],
        );
    };
    let Some(handle) = portal_handle else {
        return failed_execution(
            provider_id,
            capability_id,
            "provider.fs.open requires a portal handle",
            vec!["provider_rpc=provider.fs.open".to_string()],
        );
    };

    let mut notes = vec![
        "provider_rpc=provider.fs.open".to_string(),
        format!("portal_handle_kind={}", handle.kind),
        format!("portal_handle_id={}", handle.handle_id),
    ];
    let socket_path = &state.config.system_files_provider_socket;
    notes.push(format!("provider_socket={}", socket_path.display()));
    if !socket_path.exists() {
        return deferred_execution(
            provider_id,
            capability_id,
            format!("provider socket unavailable: {}", socket_path.display()),
            notes,
        );
    }

    let request = build_fs_open_request(handle, token);
    notes.push(format!(
        "content_preview_requested={}",
        request.include_content
    ));

    let response: anyhow::Result<aios_contracts::ProviderFsOpenResponse> =
        aios_rpc::call_unix(socket_path, methods::PROVIDER_FS_OPEN, &request);
    match response {
        Ok(response) => {
            notes.push(format!("object_kind={}", response.object_kind.as_str()));
            notes.push(format!("truncated={}", response.truncated));
            completed_execution(
                provider_id,
                capability_id,
                serialize_result(&response),
                notes,
            )
        }
        Err(error) => failed_execution(provider_id, capability_id, error.to_string(), notes),
    }
}

fn execute_provider_fs_bulk_delete(
    state: &AppState,
    execution_token: &ExecutionToken,
    portal_handle: &PortalHandleRecord,
) -> AgentProviderExecutionResult {
    let provider_id = "system.files.local";
    let capability_id = methods::SYSTEM_FILE_BULK_DELETE;
    let recursive = portal_handle.kind == "directory_handle"
        && constraint_flag(&execution_token.constraints, "allow_recursive");
    let mut notes = vec![
        "provider_rpc=system.file.bulk_delete".to_string(),
        format!("portal_handle_kind={}", portal_handle.kind),
        format!("portal_handle_id={}", portal_handle.handle_id),
        format!("recursive={recursive}"),
    ];
    let socket_path = &state.config.system_files_provider_socket;
    notes.push(format!("provider_socket={}", socket_path.display()));
    if !socket_path.exists() {
        return deferred_execution(
            provider_id,
            capability_id,
            format!("provider socket unavailable: {}", socket_path.display()),
            notes,
        );
    }

    let request = ProviderFsBulkDeleteRequest {
        handle_id: portal_handle.handle_id.clone(),
        execution_token: execution_token.clone(),
        recursive,
        dry_run: false,
    };

    let response: anyhow::Result<ProviderFsBulkDeleteResponse> =
        aios_rpc::call_unix(socket_path, methods::SYSTEM_FILE_BULK_DELETE, &request);
    match response {
        Ok(response) => {
            notes.push(format!("provider_status={}", response.status));
            if let Some(reason) = response.reason.as_deref() {
                notes.push(format!("provider_reason={reason}"));
            }
            if delete_response_completed(&response) {
                completed_execution(
                    provider_id,
                    capability_id,
                    serialize_result(&response),
                    notes,
                )
            } else {
                failed_execution_with_result(
                    provider_id,
                    capability_id,
                    serialize_result(&response),
                    notes,
                )
            }
        }
        Err(error) => failed_execution(provider_id, capability_id, error.to_string(), notes),
    }
}

fn build_fs_open_request(
    handle: &PortalHandleRecord,
    execution_token: &ExecutionToken,
) -> ProviderFsOpenRequest {
    ProviderFsOpenRequest {
        handle_id: handle.handle_id.clone(),
        execution_token: execution_token.clone(),
        include_content: handle.kind == "file_handle",
        max_bytes: (handle.kind == "file_handle").then_some(DEFAULT_MAX_PREVIEW_BYTES),
        max_entries: (handle.kind == "directory_handle").then_some(DEFAULT_MAX_DIRECTORY_ENTRIES),
    }
}

fn constraint_flag(constraints: &std::collections::BTreeMap<String, Value>, key: &str) -> bool {
    constraints
        .get(key)
        .and_then(Value::as_bool)
        .unwrap_or(false)
}

fn delete_response_completed(response: &ProviderFsBulkDeleteResponse) -> bool {
    matches!(response.status.as_str(), "deleted" | "would-delete")
        || (response.status == "skipped"
            && response.reason.as_deref() == Some("target path does not exist"))
}

fn serialize_result<T>(value: &T) -> Value
where
    T: serde::Serialize,
{
    serde_json::to_value(value).unwrap_or_else(|error| {
        json!({
            "serialization_error": error.to_string(),
        })
    })
}

fn completed_execution(
    provider_id: &str,
    capability_id: &str,
    result: Value,
    notes: Vec<String>,
) -> AgentProviderExecutionResult {
    AgentProviderExecutionResult {
        provider_id: provider_id.to_string(),
        capability_id: capability_id.to_string(),
        status: "completed".to_string(),
        task_state: "completed".to_string(),
        result,
        notes,
    }
}

fn deferred_execution(
    provider_id: &str,
    capability_id: &str,
    reason: impl Into<String>,
    mut notes: Vec<String>,
) -> AgentProviderExecutionResult {
    let reason = reason.into();
    notes.push(format!("deferred_reason={reason}"));
    AgentProviderExecutionResult {
        provider_id: provider_id.to_string(),
        capability_id: capability_id.to_string(),
        status: "deferred".to_string(),
        task_state: "approved".to_string(),
        result: json!({
            "reason": reason,
        }),
        notes,
    }
}

fn failed_execution(
    provider_id: &str,
    capability_id: &str,
    error: impl Into<String>,
    mut notes: Vec<String>,
) -> AgentProviderExecutionResult {
    let error = error.into();
    notes.push(format!("provider_error={error}"));
    AgentProviderExecutionResult {
        provider_id: provider_id.to_string(),
        capability_id: capability_id.to_string(),
        status: "failed".to_string(),
        task_state: "failed".to_string(),
        result: json!({
            "error": error,
        }),
        notes,
    }
}

fn failed_execution_with_result(
    provider_id: &str,
    capability_id: &str,
    result: Value,
    mut notes: Vec<String>,
) -> AgentProviderExecutionResult {
    notes.push("provider_error=provider returned non-terminal status".to_string());
    AgentProviderExecutionResult {
        provider_id: provider_id.to_string(),
        capability_id: capability_id.to_string(),
        status: "failed".to_string(),
        task_state: "failed".to_string(),
        result,
        notes,
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;

    fn token() -> ExecutionToken {
        ExecutionToken {
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: methods::PROVIDER_FS_OPEN.to_string(),
            target_hash: Some("sha256:abc".to_string()),
            expiry: "2099-01-01T00:00:00Z".to_string(),
            approval_ref: None,
            constraints: Default::default(),
            execution_location: "local".to_string(),
            taint_summary: None,
            signature: Some("sig".to_string()),
        }
    }

    fn handle(kind: &str) -> PortalHandleRecord {
        PortalHandleRecord {
            handle_id: "hdl-1".to_string(),
            kind: kind.to_string(),
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            target: "/tmp/demo".to_string(),
            scope: BTreeMap::new(),
            expiry: "2099-01-01T00:00:00Z".to_string(),
            revocable: true,
            issued_at: "2026-01-01T00:00:00Z".to_string(),
            revoked_at: None,
            revocation_reason: None,
            audit_tags: vec![],
        }
    }

    #[test]
    fn build_fs_open_request_includes_content_for_file_handles() {
        let request = build_fs_open_request(&handle("file_handle"), &token());

        assert!(request.include_content);
        assert_eq!(request.max_bytes, Some(DEFAULT_MAX_PREVIEW_BYTES));
        assert_eq!(request.max_entries, None);
    }

    #[test]
    fn build_fs_open_request_uses_entry_budget_for_directory_handles() {
        let request = build_fs_open_request(&handle("directory_handle"), &token());

        assert!(!request.include_content);
        assert_eq!(request.max_bytes, None);
        assert_eq!(request.max_entries, Some(DEFAULT_MAX_DIRECTORY_ENTRIES));
    }

    #[test]
    fn deferred_execution_preserves_approved_task_state() {
        let result = deferred_execution(
            "system.intent.local",
            methods::SYSTEM_INTENT_EXECUTE,
            "provider socket unavailable",
            vec![],
        );

        assert_eq!(result.status, "deferred");
        assert_eq!(result.task_state, "approved");
        assert_eq!(result.result["reason"], "provider socket unavailable");
    }

    #[test]
    fn delete_response_treats_missing_target_as_completed_noop() {
        let response = ProviderFsBulkDeleteResponse {
            provider_id: "system.files.local".to_string(),
            handle: handle("file_handle"),
            target_path: "/tmp/demo.txt".to_string(),
            dry_run: false,
            status: "skipped".to_string(),
            affected_paths: vec![],
            reason: Some("target path does not exist".to_string()),
        };

        assert!(delete_response_completed(&response));
    }

    #[test]
    fn delete_response_rejects_other_skipped_statuses() {
        let response = ProviderFsBulkDeleteResponse {
            provider_id: "system.files.local".to_string(),
            handle: handle("directory_handle"),
            target_path: "/tmp/workspace".to_string(),
            dry_run: false,
            status: "skipped".to_string(),
            affected_paths: vec!["/tmp/workspace".to_string()],
            reason: Some("dangerous target path".to_string()),
        };

        assert!(!delete_response_completed(&response));
    }
}
