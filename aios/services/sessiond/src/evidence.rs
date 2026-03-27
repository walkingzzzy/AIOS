use std::{fs, path::Path};

use chrono::Utc;
use serde::Serialize;

use aios_contracts::{
    EpisodicMemoryListRequest, PortalListHandlesRequest, ProceduralMemoryListRequest,
    SemanticMemoryListRequest, SessionEvidenceExportRequest, SessionEvidenceExportResponse,
    SessionEvidenceRequest, SessionEvidenceResponse, TaskListRequest, WorkingMemoryReadRequest,
};

use crate::AppState;

pub fn collect(
    state: &AppState,
    request: &SessionEvidenceRequest,
) -> anyhow::Result<SessionEvidenceResponse> {
    let session = state
        .sessions
        .get(&request.session_id)?
        .ok_or_else(|| anyhow::anyhow!("session {} not found", request.session_id))?;
    let tasks = state
        .tasks
        .list(TaskListRequest {
            session_id: request.session_id.clone(),
            state: None,
            limit: Some(request.limit),
        })?
        .tasks;
    let task_events = state
        .database
        .list_session_task_events(&request.session_id, request.limit)?;
    let working_memory = state
        .memory
        .read(WorkingMemoryReadRequest {
            session_id: request.session_id.clone(),
            ref_id: None,
            limit: Some(request.limit),
        })?
        .entries;
    let episodic_memory = state
        .memory
        .list_episodic(EpisodicMemoryListRequest {
            session_id: request.session_id.clone(),
            limit: Some(request.limit),
        })?
        .entries;
    let semantic_memory = state
        .memory
        .list_semantic(SemanticMemoryListRequest {
            session_id: request.session_id.clone(),
            label: None,
            query: None,
            limit: Some(request.limit),
        })?
        .entries;
    let procedural_memory = state
        .memory
        .list_procedural(ProceduralMemoryListRequest {
            session_id: request.session_id.clone(),
            rule_name: None,
            limit: Some(request.limit),
        })?
        .entries;
    let portal_handles = state
        .portal
        .list(PortalListHandlesRequest {
            session_id: Some(request.session_id.clone()),
        })?
        .handles;
    let recovery = crate::recovery::baseline_ref(&state.database, &request.session_id)?;

    Ok(SessionEvidenceResponse {
        session,
        tasks,
        task_events,
        working_memory,
        episodic_memory,
        semantic_memory,
        procedural_memory,
        portal_handles,
        recovery,
    })
}

#[derive(Debug, Clone, Serialize)]
struct SessionEvidenceExportCounts {
    task_count: u32,
    task_event_count: u32,
    working_memory_count: u32,
    episodic_memory_count: u32,
    semantic_memory_count: u32,
    procedural_memory_count: u32,
    portal_handle_count: u32,
    resumable_task_count: u32,
    pending_task_count: u32,
}

#[derive(Debug, Clone, Serialize)]
struct SessionEvidenceExportBundle {
    export_id: String,
    created_at: String,
    service_id: String,
    session_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    counts: SessionEvidenceExportCounts,
    notes: Vec<String>,
    evidence: SessionEvidenceResponse,
}

pub fn export_bundle(
    service_id: &str,
    export_dir: &Path,
    request: &SessionEvidenceExportRequest,
    evidence: &SessionEvidenceResponse,
) -> anyhow::Result<SessionEvidenceExportResponse> {
    let created_at = Utc::now().to_rfc3339();
    let export_id = format!("session-evidence-{}", Utc::now().timestamp_millis());
    let export_path = export_dir.join(format!("{export_id}.json"));
    let counts = evidence_counts(evidence);
    let mut notes = vec![
        format!("limit={}", request.limit),
        format!("export_dir={}", export_dir.display()),
    ];
    if let Some(reason) = request.reason.as_deref() {
        notes.push(format!("reason={reason}"));
    }
    notes.push(format!("recovery_status={}", evidence.recovery.status));

    let bundle = SessionEvidenceExportBundle {
        export_id: export_id.clone(),
        created_at: created_at.clone(),
        service_id: service_id.to_string(),
        session_id: evidence.session.session_id.clone(),
        reason: request.reason.clone(),
        counts: counts.clone(),
        notes: notes.clone(),
        evidence: evidence.clone(),
    };

    if let Some(parent) = export_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&export_path, serde_json::to_vec_pretty(&bundle)?)?;

    Ok(SessionEvidenceExportResponse {
        service_id: service_id.to_string(),
        session_id: evidence.session.session_id.clone(),
        export_id,
        export_path: export_path.display().to_string(),
        created_at,
        recovery_id: Some(evidence.recovery.recovery_id.clone()),
        recovery_status: Some(evidence.recovery.status.clone()),
        task_count: counts.task_count,
        task_event_count: counts.task_event_count,
        working_memory_count: counts.working_memory_count,
        episodic_memory_count: counts.episodic_memory_count,
        semantic_memory_count: counts.semantic_memory_count,
        procedural_memory_count: counts.procedural_memory_count,
        portal_handle_count: counts.portal_handle_count,
        resumable_task_count: counts.resumable_task_count,
        pending_task_count: counts.pending_task_count,
        notes,
    })
}

fn evidence_counts(evidence: &SessionEvidenceResponse) -> SessionEvidenceExportCounts {
    SessionEvidenceExportCounts {
        task_count: count_u32(evidence.tasks.len()),
        task_event_count: count_u32(evidence.task_events.len()),
        working_memory_count: count_u32(evidence.working_memory.len()),
        episodic_memory_count: count_u32(evidence.episodic_memory.len()),
        semantic_memory_count: count_u32(evidence.semantic_memory.len()),
        procedural_memory_count: count_u32(evidence.procedural_memory.len()),
        portal_handle_count: count_u32(evidence.portal_handles.len()),
        resumable_task_count: count_u32(evidence.recovery.resumable_task_ids.len()),
        pending_task_count: count_u32(evidence.recovery.pending_task_ids.len()),
    }
}

fn count_u32(len: usize) -> u32 {
    len.try_into().unwrap_or(u32::MAX)
}

#[cfg(test)]
mod tests {
    use std::{
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use serde_json::json;

    use aios_contracts::{
        EpisodicMemoryRecord, PortalHandleRecord, ProceduralMemoryRecord, RecoveryRef,
        SemanticMemoryRecord, SessionEvidenceExportRequest, SessionEvidenceResponse, SessionRecord,
        TaskEventRecord, TaskRecord, WorkingMemoryRecord,
    };

    use super::export_bundle;

    fn temp_root(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("aios-sessiond-evidence-{name}-{stamp}"))
    }

    fn sample_evidence() -> SessionEvidenceResponse {
        SessionEvidenceResponse {
            session: SessionRecord {
                session_id: "session-1".to_string(),
                user_id: "user-1".to_string(),
                created_at: "2026-03-15T00:00:00Z".to_string(),
                last_resumed_at: None,
                status: "active".to_string(),
            },
            tasks: vec![TaskRecord {
                task_id: "task-1".to_string(),
                session_id: "session-1".to_string(),
                state: "completed".to_string(),
                title: Some("demo task".to_string()),
                created_at: "2026-03-15T00:00:00Z".to_string(),
            }],
            task_events: vec![TaskEventRecord {
                event_id: "event-1".to_string(),
                task_id: "task-1".to_string(),
                from_state: "planned".to_string(),
                to_state: "completed".to_string(),
                metadata: json!({"reason": "smoke"}),
                created_at: "2026-03-15T00:01:00Z".to_string(),
            }],
            working_memory: vec![WorkingMemoryRecord {
                ref_id: "wm-1".to_string(),
                session_id: "session-1".to_string(),
                payload: json!({"kind": "plan-summary"}),
                tags: vec!["agentd".to_string()],
                created_at: "2026-03-15T00:01:00Z".to_string(),
            }],
            episodic_memory: vec![EpisodicMemoryRecord {
                entry_id: "ep-1".to_string(),
                session_id: "session-1".to_string(),
                summary: "task completed".to_string(),
                metadata: Default::default(),
                created_at: "2026-03-15T00:01:00Z".to_string(),
            }],
            semantic_memory: vec![SemanticMemoryRecord {
                index_id: "sm-1".to_string(),
                session_id: "session-1".to_string(),
                label: "agent-plan-summary".to_string(),
                payload: json!({"task_id": "task-1"}),
                created_at: "2026-03-15T00:01:00Z".to_string(),
            }],
            procedural_memory: vec![ProceduralMemoryRecord {
                version_id: "pm-1".to_string(),
                session_id: "session-1".to_string(),
                rule_name: "delete-safe".to_string(),
                payload: json!({"allowed": true}),
                created_at: "2026-03-15T00:01:00Z".to_string(),
            }],
            portal_handles: vec![PortalHandleRecord {
                handle_id: "hdl-1".to_string(),
                kind: "file_handle".to_string(),
                user_id: "user-1".to_string(),
                session_id: "session-1".to_string(),
                target: "/tmp/demo.txt".to_string(),
                scope: Default::default(),
                expiry: "2026-03-15T00:05:00Z".to_string(),
                revocable: true,
                issued_at: "2026-03-15T00:01:00Z".to_string(),
                revoked_at: None,
                revocation_reason: None,
                audit_tags: vec!["portal-bound".to_string()],
            }],
            recovery: RecoveryRef {
                recovery_id: "rec-1".to_string(),
                session_id: "session-1".to_string(),
                status: "resume-ready".to_string(),
                updated_at: Some("2026-03-15T00:02:00Z".to_string()),
                latest_task_id: Some("task-1".to_string()),
                latest_task_state: Some("completed".to_string()),
                resumable_task_ids: vec!["task-1".to_string()],
                pending_task_ids: Vec::new(),
                approved_task_ids: Vec::new(),
                portal_handle_ids: vec!["hdl-1".to_string()],
                working_memory_refs: vec!["wm-1".to_string()],
                notes: vec!["resumable_tasks=1".to_string()],
            },
        }
    }

    #[test]
    fn export_bundle_writes_evidence_snapshot() -> anyhow::Result<()> {
        let root = temp_root("export");
        let evidence = sample_evidence();

        let response = export_bundle(
            "aios-sessiond",
            &root,
            &SessionEvidenceExportRequest {
                session_id: "session-1".to_string(),
                limit: 20,
                reason: Some("operator-export".to_string()),
            },
            &evidence,
        )?;

        assert!(PathBuf::from(&response.export_path).exists());
        let payload: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&response.export_path)?)?;
        assert_eq!(payload["counts"]["task_count"], 1);
        assert_eq!(payload["counts"]["resumable_task_count"], 1);
        assert_eq!(payload["evidence"]["session"]["session_id"], "session-1");
        assert_eq!(payload["reason"], "operator-export");
        assert_eq!(response.recovery_id.as_deref(), Some("rec-1"));
        assert_eq!(response.recovery_status.as_deref(), Some("resume-ready"));
        assert_eq!(response.resumable_task_count, 1);

        std::fs::remove_dir_all(root).ok();
        Ok(())
    }
}
