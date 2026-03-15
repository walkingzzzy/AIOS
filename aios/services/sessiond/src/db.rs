use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

use anyhow::Context;
use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension, Row};
use serde_json::{json, Value};
use uuid::Uuid;

use aios_contracts::{
    EpisodicMemoryAppendRequest, EpisodicMemoryListRequest, EpisodicMemoryListResponse,
    EpisodicMemoryRecord, PortalHandleRecord, PortalListHandlesResponse,
    ProceduralMemoryListRequest, ProceduralMemoryListResponse, ProceduralMemoryPutRequest,
    ProceduralMemoryRecord, RecoveryRef, SemanticMemoryListRequest, SemanticMemoryListResponse,
    SemanticMemoryPutRequest, SemanticMemoryRecord, SessionCloseRequest, SessionCreateRequest,
    SessionListRequest, SessionListResponse, SessionRecord, SessionResumeRequest,
    TaskCreateRequest, TaskEventListRequest, TaskEventListResponse, TaskEventRecord,
    TaskGetRequest, TaskListRequest, TaskListResponse, TaskPlanGetRequest, TaskPlanPutRequest,
    TaskPlanRecord, TaskRecord, TaskStateUpdateRequest, WorkingMemoryReadRequest,
    WorkingMemoryReadResponse, WorkingMemoryRecord, WorkingMemoryWriteRequest,
};

use crate::{config::Config, memory::MemorySummary, observability::ObservabilitySink};

#[derive(Debug, Clone)]
pub struct Database {
    path: PathBuf,
    migrations_dir: PathBuf,
    observability_sink: Option<ObservabilitySink>,
}

impl Database {
    pub fn new(path: PathBuf, migrations_dir: PathBuf) -> Self {
        Self::new_with_observability(path, migrations_dir, None)
    }

    pub fn new_with_observability(
        path: PathBuf,
        migrations_dir: PathBuf,
        observability_sink: Option<ObservabilitySink>,
    ) -> Self {
        Self {
            path,
            migrations_dir,
            observability_sink,
        }
    }

    pub fn apply_migrations(&self) -> anyhow::Result<()> {
        let mut entries: Vec<PathBuf> = std::fs::read_dir(&self.migrations_dir)
            .with_context(|| {
                format!(
                    "failed to read migrations from {}",
                    self.migrations_dir.display()
                )
            })?
            .filter_map(|entry| entry.ok().map(|item| item.path()))
            .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("sql"))
            .collect();
        entries.sort();

        let connection = self.open_connection()?;
        for path in entries {
            let sql = std::fs::read_to_string(&path)
                .with_context(|| format!("failed to read migration {}", path.display()))?;
            connection.execute_batch(&sql)?;
        }

        Ok(())
    }

    pub fn create_session(&self, request: &SessionCreateRequest) -> anyhow::Result<SessionRecord> {
        let connection = self.open_connection()?;
        let now = Utc::now().to_rfc3339();
        let record = SessionRecord {
            session_id: Uuid::new_v4().to_string(),
            user_id: request.user_id.clone(),
            created_at: now.clone(),
            last_resumed_at: Some(now),
            status: "active".to_string(),
        };

        connection.execute(
            "INSERT INTO sessions (session_id, user_id, metadata_json, created_at, last_resumed_at, status) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                &record.session_id,
                &record.user_id,
                serde_json::to_string(&request.metadata)?,
                &record.created_at,
                record.last_resumed_at.as_deref(),
                &record.status,
            ],
        )?;

        self.record_observability(
            "session.created",
            Some(&record.session_id),
            None,
            json!({
                "user_id": record.user_id.clone(),
                "status": record.status.clone(),
            }),
        );

        Ok(record)
    }

    pub fn resume_session(
        &self,
        request: &SessionResumeRequest,
    ) -> anyhow::Result<Option<SessionRecord>> {
        let connection = self.open_connection()?;
        let now = Utc::now().to_rfc3339();
        let updated = connection.execute(
            "UPDATE sessions SET last_resumed_at = ?2, status = 'active' WHERE session_id = ?1",
            params![&request.session_id, &now],
        )?;

        if updated == 0 {
            return Ok(None);
        }

        let session = self.fetch_session(&connection, &request.session_id)?;
        if let Some(record) = &session {
            self.record_observability(
                "session.resumed",
                Some(&record.session_id),
                None,
                json!({
                    "status": record.status.clone(),
                    "last_resumed_at": record.last_resumed_at.clone(),
                }),
            );
        }
        Ok(session)
    }

    pub fn close_session(
        &self,
        request: &SessionCloseRequest,
    ) -> anyhow::Result<Option<SessionRecord>> {
        let connection = self.open_connection()?;
        let updated = connection.execute(
            "UPDATE sessions SET status = 'closed' WHERE session_id = ?1",
            params![&request.session_id],
        )?;

        if updated == 0 {
            return Ok(None);
        }

        let session = self.fetch_session(&connection, &request.session_id)?;
        if let Some(record) = &session {
            self.record_observability(
                "session.closed",
                Some(&record.session_id),
                None,
                json!({
                    "status": record.status.clone(),
                }),
            );
        }
        Ok(session)
    }

    pub fn get_session(&self, session_id: &str) -> anyhow::Result<Option<SessionRecord>> {
        let connection = self.open_connection()?;
        self.fetch_session(&connection, session_id)
    }

    pub fn list_sessions(
        &self,
        request: &SessionListRequest,
    ) -> anyhow::Result<SessionListResponse> {
        let connection = self.open_connection()?;
        let limit = sanitize_limit(request.limit);
        let sessions = match (&request.user_id, &request.status) {
            (Some(user_id), Some(status)) => {
                let mut statement = connection.prepare(
                    "SELECT session_id, user_id, created_at, last_resumed_at, status
                     FROM sessions
                     WHERE user_id = ?1 AND status = ?2
                     ORDER BY COALESCE(last_resumed_at, created_at) DESC, created_at DESC
                     LIMIT ?3",
                )?;
                let rows = statement.query_map(params![user_id, status, limit], map_session_row)?;
                rows.collect::<Result<Vec<_>, _>>()?
            }
            (Some(user_id), None) => {
                let mut statement = connection.prepare(
                    "SELECT session_id, user_id, created_at, last_resumed_at, status
                     FROM sessions
                     WHERE user_id = ?1
                     ORDER BY COALESCE(last_resumed_at, created_at) DESC, created_at DESC
                     LIMIT ?2",
                )?;
                let rows = statement.query_map(params![user_id, limit], map_session_row)?;
                rows.collect::<Result<Vec<_>, _>>()?
            }
            (None, Some(status)) => {
                let mut statement = connection.prepare(
                    "SELECT session_id, user_id, created_at, last_resumed_at, status
                     FROM sessions
                     WHERE status = ?1
                     ORDER BY COALESCE(last_resumed_at, created_at) DESC, created_at DESC
                     LIMIT ?2",
                )?;
                let rows = statement.query_map(params![status, limit], map_session_row)?;
                rows.collect::<Result<Vec<_>, _>>()?
            }
            (None, None) => {
                let mut statement = connection.prepare(
                    "SELECT session_id, user_id, created_at, last_resumed_at, status
                     FROM sessions
                     ORDER BY COALESCE(last_resumed_at, created_at) DESC, created_at DESC
                     LIMIT ?1",
                )?;
                let rows = statement.query_map(params![limit], map_session_row)?;
                rows.collect::<Result<Vec<_>, _>>()?
            }
        };

        Ok(SessionListResponse { sessions })
    }

    pub fn create_task(&self, request: &TaskCreateRequest) -> anyhow::Result<TaskRecord> {
        let connection = self.open_connection()?;
        let task = TaskRecord {
            task_id: Uuid::new_v4().to_string(),
            session_id: request.session_id.clone(),
            state: request.state.clone(),
            title: request.title.clone(),
            created_at: Utc::now().to_rfc3339(),
        };

        connection.execute(
            "INSERT INTO tasks (task_id, session_id, title, state, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                &task.task_id,
                &task.session_id,
                task.title.as_deref(),
                &task.state,
                &task.created_at,
            ],
        )?;
        insert_task_event(&connection, &task.task_id, "created", &task.state, None)?;

        self.record_observability(
            "task.created",
            Some(&task.session_id),
            Some(&task.task_id),
            json!({
                "state": task.state.clone(),
                "title": task.title.clone(),
            }),
        );

        Ok(task)
    }

    pub fn get_task(&self, request: &TaskGetRequest) -> anyhow::Result<Option<TaskRecord>> {
        let connection = self.open_connection()?;
        self.fetch_task(&connection, &request.task_id)
    }

    pub fn list_tasks(&self, request: &TaskListRequest) -> anyhow::Result<TaskListResponse> {
        let connection = self.open_connection()?;
        let limit = sanitize_limit(request.limit);
        let tasks = if let Some(state) = &request.state {
            let mut statement = connection.prepare(
                "SELECT task_id, session_id, state, title, created_at FROM tasks WHERE session_id = ?1 AND state = ?2 ORDER BY created_at DESC LIMIT ?3",
            )?;
            let rows =
                statement.query_map(params![&request.session_id, state, limit], map_task_row)?;
            rows.collect::<Result<Vec<_>, _>>()?
        } else {
            let mut statement = connection.prepare(
                "SELECT task_id, session_id, state, title, created_at FROM tasks WHERE session_id = ?1 ORDER BY created_at DESC LIMIT ?2",
            )?;
            let rows = statement.query_map(params![&request.session_id, limit], map_task_row)?;
            rows.collect::<Result<Vec<_>, _>>()?
        };

        Ok(TaskListResponse { tasks })
    }

    pub fn update_task_state(
        &self,
        request: &TaskStateUpdateRequest,
    ) -> anyhow::Result<Option<TaskRecord>> {
        let connection = self.open_connection()?;
        let Some(task) = self.fetch_task(&connection, &request.task_id)? else {
            return Ok(None);
        };

        assert_valid_task_transition(&task.state, &request.new_state)?;
        connection.execute(
            "UPDATE tasks SET state = ?2 WHERE task_id = ?1",
            params![&request.task_id, &request.new_state],
        )?;
        insert_task_event(
            &connection,
            &request.task_id,
            &task.state,
            &request.new_state,
            request.reason.as_deref(),
        )?;
        let updated = self.fetch_task(&connection, &request.task_id)?;
        if updated.is_some() {
            self.record_observability(
                "task.state.updated",
                Some(&task.session_id),
                Some(&request.task_id),
                json!({
                    "from_state": task.state.clone(),
                    "to_state": request.new_state.clone(),
                    "reason": request.reason.clone(),
                }),
            );
        }
        Ok(updated)
    }

    pub fn list_task_events(
        &self,
        request: &TaskEventListRequest,
    ) -> anyhow::Result<TaskEventListResponse> {
        let connection = self.open_connection()?;
        let limit = sanitize_limit(Some(request.limit));
        let order = if request.reverse { "DESC" } else { "ASC" };
        let sql = format!(
            "SELECT event_id, task_id, from_state, to_state, metadata_json, created_at \
             FROM task_events WHERE task_id = ?1 ORDER BY created_at {order} LIMIT ?2"
        );
        let mut statement = connection.prepare(&sql)?;
        let rows = statement.query_map(params![&request.task_id, limit], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, String>(5)?,
            ))
        })?;
        let events = rows
            .collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .map(
                |(event_id, task_id, from_state, to_state, metadata_json, created_at)| {
                    decode_task_event(
                        &event_id,
                        &task_id,
                        &from_state,
                        &to_state,
                        metadata_json.as_deref(),
                        &created_at,
                    )
                },
            )
            .collect::<anyhow::Result<Vec<_>>>()?;

        Ok(TaskEventListResponse { events })
    }

    pub fn list_session_task_events(
        &self,
        session_id: &str,
        limit: u32,
    ) -> anyhow::Result<Vec<TaskEventRecord>> {
        let connection = self.open_connection()?;
        let limit = sanitize_limit(Some(limit));
        let mut statement = connection.prepare(
            "SELECT e.event_id, e.task_id, e.from_state, e.to_state, e.metadata_json, e.created_at \
             FROM task_events e INNER JOIN tasks t ON t.task_id = e.task_id \
             WHERE t.session_id = ?1 ORDER BY e.created_at DESC LIMIT ?2",
        )?;
        let rows = statement.query_map(params![session_id, limit], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, String>(5)?,
            ))
        })?;
        rows.collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .map(
                |(event_id, task_id, from_state, to_state, metadata_json, created_at)| {
                    decode_task_event(
                        &event_id,
                        &task_id,
                        &from_state,
                        &to_state,
                        metadata_json.as_deref(),
                        &created_at,
                    )
                },
            )
            .collect()
    }

    pub fn put_task_plan(&self, request: &TaskPlanPutRequest) -> anyhow::Result<TaskPlanRecord> {
        let connection = self.open_connection()?;
        let record = TaskPlanRecord {
            task_id: request.task_id.clone(),
            plan: request.plan.clone(),
            updated_at: Utc::now().to_rfc3339(),
        };

        connection.execute(
            "INSERT INTO task_plans (task_id, plan_json, updated_at) VALUES (?1, ?2, ?3) \
             ON CONFLICT(task_id) DO UPDATE SET plan_json = excluded.plan_json, updated_at = excluded.updated_at",
            params![
                &record.task_id,
                serde_json::to_string(&record.plan)?,
                &record.updated_at,
            ],
        )?;

        Ok(record)
    }

    pub fn get_task_plan(
        &self,
        request: &TaskPlanGetRequest,
    ) -> anyhow::Result<Option<TaskPlanRecord>> {
        let connection = self.open_connection()?;
        self.fetch_task_plan(&connection, &request.task_id)
    }

    pub fn write_working_memory(
        &self,
        request: &WorkingMemoryWriteRequest,
    ) -> anyhow::Result<WorkingMemoryRecord> {
        let connection = self.open_connection()?;
        let record = WorkingMemoryRecord {
            ref_id: request
                .ref_id
                .clone()
                .unwrap_or_else(|| format!("wm-{}", Uuid::new_v4())),
            session_id: request.session_id.clone(),
            payload: request.payload.clone(),
            tags: request.tags.clone(),
            created_at: Utc::now().to_rfc3339(),
        };

        connection.execute(
            "INSERT INTO memory_working_refs (ref_id, session_id, payload_json, created_at) VALUES (?1, ?2, ?3, ?4) \
             ON CONFLICT(ref_id) DO UPDATE SET session_id = excluded.session_id, payload_json = excluded.payload_json, created_at = excluded.created_at",
            params![
                &record.ref_id,
                &record.session_id,
                serde_json::to_string(&record)?,
                &record.created_at,
            ],
        )?;

        Ok(record)
    }

    pub fn read_working_memory(
        &self,
        request: &WorkingMemoryReadRequest,
    ) -> anyhow::Result<WorkingMemoryReadResponse> {
        let connection = self.open_connection()?;
        let entries = if let Some(ref_id) = &request.ref_id {
            match self.fetch_working_memory(&connection, ref_id)? {
                Some(record) if record.session_id == request.session_id => vec![record],
                Some(_) | None => Vec::new(),
            }
        } else {
            let limit = sanitize_limit(request.limit);
            let mut statement = connection.prepare(
                "SELECT ref_id, session_id, payload_json, created_at FROM memory_working_refs WHERE session_id = ?1 ORDER BY created_at DESC LIMIT ?2",
            )?;
            let rows = statement.query_map(params![&request.session_id, limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                ))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
                .into_iter()
                .map(|(ref_id, session_id, payload_json, created_at)| {
                    decode_working_memory(&ref_id, &session_id, &payload_json, &created_at)
                })
                .collect::<anyhow::Result<Vec<_>>>()?
        };

        Ok(WorkingMemoryReadResponse { entries })
    }

    pub fn append_episodic_memory(
        &self,
        request: &EpisodicMemoryAppendRequest,
    ) -> anyhow::Result<EpisodicMemoryRecord> {
        let connection = self.open_connection()?;
        let record = EpisodicMemoryRecord {
            entry_id: format!("ep-{}", Uuid::new_v4()),
            session_id: request.session_id.clone(),
            summary: request.summary.clone(),
            metadata: request.metadata.clone(),
            created_at: Utc::now().to_rfc3339(),
        };

        connection.execute(
            "INSERT INTO memory_episodic_entries (entry_id, session_id, summary, metadata_json, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                &record.entry_id,
                &record.session_id,
                &record.summary,
                serde_json::to_string(&record.metadata)?,
                &record.created_at,
            ],
        )?;

        Ok(record)
    }

    pub fn list_episodic_memory(
        &self,
        request: &EpisodicMemoryListRequest,
    ) -> anyhow::Result<EpisodicMemoryListResponse> {
        let connection = self.open_connection()?;
        let limit = sanitize_limit(request.limit);
        let mut statement = connection.prepare(
            "SELECT entry_id, session_id, summary, metadata_json, created_at FROM memory_episodic_entries WHERE session_id = ?1 ORDER BY created_at DESC LIMIT ?2",
        )?;
        let rows = statement.query_map(params![&request.session_id, limit], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Option<String>>(3)?,
                row.get::<_, String>(4)?,
            ))
        })?;
        let entries = rows
            .collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .map(
                |(entry_id, session_id, summary, metadata_json, created_at)| {
                    decode_episodic_memory(
                        &entry_id,
                        &session_id,
                        &summary,
                        metadata_json.as_deref(),
                        &created_at,
                    )
                },
            )
            .collect::<anyhow::Result<Vec<_>>>()?;

        Ok(EpisodicMemoryListResponse { entries })
    }

    pub fn put_semantic_memory(
        &self,
        request: &SemanticMemoryPutRequest,
    ) -> anyhow::Result<SemanticMemoryRecord> {
        let connection = self.open_connection()?;
        let record = SemanticMemoryRecord {
            index_id: format!("sem-{}", Uuid::new_v4()),
            session_id: request.session_id.clone(),
            label: request.label.clone(),
            payload: request.payload.clone(),
            created_at: Utc::now().to_rfc3339(),
        };

        connection.execute(
            "INSERT INTO memory_semantic_indexes (index_id, session_id, label, payload_json, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                &record.index_id,
                &record.session_id,
                &record.label,
                serde_json::to_string(&record.payload)?,
                &record.created_at,
            ],
        )?;

        Ok(record)
    }

    pub fn list_semantic_memory(
        &self,
        request: &SemanticMemoryListRequest,
    ) -> anyhow::Result<SemanticMemoryListResponse> {
        let connection = self.open_connection()?;
        let limit = sanitize_limit(request.limit);
        let rows = if let Some(label) = &request.label {
            let mut statement = connection.prepare(
                "SELECT index_id, session_id, label, payload_json, created_at FROM memory_semantic_indexes WHERE session_id = ?1 AND label = ?2 ORDER BY created_at DESC LIMIT ?3",
            )?;
            let rows = statement.query_map(params![&request.session_id, label, limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                ))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
        } else {
            let mut statement = connection.prepare(
                "SELECT index_id, session_id, label, payload_json, created_at FROM memory_semantic_indexes WHERE session_id = ?1 ORDER BY created_at DESC LIMIT ?2",
            )?;
            let rows = statement.query_map(params![&request.session_id, limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                ))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
        };

        let entries = rows
            .into_iter()
            .map(|(index_id, session_id, label, payload_json, created_at)| {
                decode_semantic_memory(&index_id, &session_id, &label, &payload_json, &created_at)
            })
            .collect::<anyhow::Result<Vec<_>>>()?;

        Ok(SemanticMemoryListResponse { entries })
    }

    pub fn put_procedural_memory(
        &self,
        request: &ProceduralMemoryPutRequest,
    ) -> anyhow::Result<ProceduralMemoryRecord> {
        let connection = self.open_connection()?;
        let record = ProceduralMemoryRecord {
            version_id: format!("proc-{}", Uuid::new_v4()),
            session_id: request.session_id.clone(),
            rule_name: request.rule_name.clone(),
            payload: request.payload.clone(),
            created_at: Utc::now().to_rfc3339(),
        };

        connection.execute(
            "INSERT INTO memory_procedural_versions (version_id, session_id, rule_name, payload_json, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                &record.version_id,
                &record.session_id,
                &record.rule_name,
                serde_json::to_string(&record.payload)?,
                &record.created_at,
            ],
        )?;

        Ok(record)
    }

    pub fn list_procedural_memory(
        &self,
        request: &ProceduralMemoryListRequest,
    ) -> anyhow::Result<ProceduralMemoryListResponse> {
        let connection = self.open_connection()?;
        let limit = sanitize_limit(request.limit);
        let rows = if let Some(rule_name) = &request.rule_name {
            let mut statement = connection.prepare(
                "SELECT version_id, session_id, rule_name, payload_json, created_at FROM memory_procedural_versions WHERE session_id = ?1 AND rule_name = ?2 ORDER BY created_at DESC LIMIT ?3",
            )?;
            let rows =
                statement.query_map(params![&request.session_id, rule_name, limit], |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                        row.get::<_, String>(4)?,
                    ))
                })?;
            rows.collect::<Result<Vec<_>, _>>()?
        } else {
            let mut statement = connection.prepare(
                "SELECT version_id, session_id, rule_name, payload_json, created_at FROM memory_procedural_versions WHERE session_id = ?1 ORDER BY created_at DESC LIMIT ?2",
            )?;
            let rows = statement.query_map(params![&request.session_id, limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                ))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
        };

        let entries = rows
            .into_iter()
            .map(
                |(version_id, session_id, rule_name, payload_json, created_at)| {
                    decode_procedural_memory(
                        &version_id,
                        &session_id,
                        &rule_name,
                        &payload_json,
                        &created_at,
                    )
                },
            )
            .collect::<anyhow::Result<Vec<_>>>()?;

        Ok(ProceduralMemoryListResponse { entries })
    }

    pub fn bind_portal_handle(&self, handle: &PortalHandleRecord) -> anyhow::Result<()> {
        let connection = self.open_connection()?;
        connection.execute(
            "INSERT INTO portal_handles (handle_id, session_id, kind, scope_json, expiry) VALUES (?1, ?2, ?3, ?4, ?5) \
             ON CONFLICT(handle_id) DO UPDATE SET session_id = excluded.session_id, kind = excluded.kind, scope_json = excluded.scope_json, expiry = excluded.expiry",
            params![
                &handle.handle_id,
                &handle.session_id,
                &handle.kind,
                serde_json::to_string(handle)?,
                &handle.expiry,
            ],
        )?;

        Ok(())
    }

    pub fn get_portal_handle(&self, handle_id: &str) -> anyhow::Result<Option<PortalHandleRecord>> {
        let connection = self.open_connection()?;
        self.fetch_portal_handle(&connection, handle_id)
    }

    pub fn list_portal_handles(
        &self,
        session_id: Option<&str>,
    ) -> anyhow::Result<PortalListHandlesResponse> {
        let connection = self.open_connection()?;
        let rows = if let Some(session_id) = session_id {
            let mut statement = connection.prepare(
                "SELECT handle_id, session_id, kind, scope_json, expiry FROM portal_handles WHERE session_id = ?1 ORDER BY expiry DESC",
            )?;
            let rows = statement.query_map(params![session_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                ))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
        } else {
            let mut statement = connection.prepare(
                "SELECT handle_id, session_id, kind, scope_json, expiry FROM portal_handles ORDER BY expiry DESC",
            )?;
            let rows = statement.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                ))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
        };

        let handles = rows
            .into_iter()
            .map(|(handle_id, session_id, kind, scope_json, expiry)| {
                decode_portal_handle(&handle_id, &session_id, &kind, &scope_json, &expiry)
            })
            .collect::<anyhow::Result<Vec<_>>>()?;

        Ok(PortalListHandlesResponse { handles })
    }

    pub fn portal_handle_count(&self) -> anyhow::Result<usize> {
        let connection = self.open_connection()?;
        count_rows(&connection, "portal_handles")
    }

    pub fn recovery_ref(&self, session_id: &str) -> anyhow::Result<RecoveryRef> {
        let connection = self.open_connection()?;
        let mut statement = connection.prepare(
            "SELECT recovery_id, session_id, payload_json FROM recovery_refs WHERE session_id = ?1 ORDER BY created_at DESC LIMIT 1",
        )?;

        if let Some((recovery_id, payload_json)) = statement
            .query_row(params![session_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(2)?))
            })
            .optional()?
        {
            let mut recovery: RecoveryRef = serde_json::from_str(&payload_json)?;
            recovery.recovery_id = recovery_id;
            return Ok(recovery);
        }

        let recovery = RecoveryRef {
            recovery_id: format!("recovery-{}", Uuid::new_v4()),
            session_id: session_id.to_string(),
            status: "not-generated".to_string(),
        };

        connection.execute(
            "INSERT INTO recovery_refs (recovery_id, session_id, payload_json, created_at) VALUES (?1, ?2, ?3, ?4)",
            params![
                &recovery.recovery_id,
                &recovery.session_id,
                serde_json::to_string(&recovery)?,
                Utc::now().to_rfc3339(),
            ],
        )?;

        Ok(recovery)
    }

    pub fn memory_summary(&self) -> anyhow::Result<MemorySummary> {
        let connection = self.open_connection()?;
        Ok(MemorySummary {
            working_refs: count_rows(&connection, "memory_working_refs")?,
            episodic_entries: count_rows(&connection, "memory_episodic_entries")?,
            semantic_slots: table_exists(&connection, "memory_semantic_indexes")?
                .then(|| count_rows(&connection, "memory_semantic_indexes"))
                .transpose()?
                .unwrap_or(0),
            procedural_rules: table_exists(&connection, "memory_procedural_versions")?
                .then(|| count_rows(&connection, "memory_procedural_versions"))
                .transpose()?
                .unwrap_or(0),
        })
    }

    fn open_connection(&self) -> anyhow::Result<Connection> {
        let connection = Connection::open(&self.path)
            .with_context(|| format!("failed to open sqlite database {}", self.path.display()))?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        Ok(connection)
    }

    fn record_observability(
        &self,
        kind: &str,
        session_id: Option<&str>,
        task_id: Option<&str>,
        payload: Value,
    ) {
        if let Some(sink) = &self.observability_sink {
            if let Err(error) =
                sink.append_record(kind, session_id, task_id, Some(&self.path), payload)
            {
                tracing::warn!(
                    ?error,
                    kind,
                    "failed to append sessiond observability event"
                );
            }
        }
    }

    fn fetch_session(
        &self,
        connection: &Connection,
        session_id: &str,
    ) -> anyhow::Result<Option<SessionRecord>> {
        let mut statement = connection.prepare(
            "SELECT session_id, user_id, created_at, last_resumed_at, status FROM sessions WHERE session_id = ?1",
        )?;

        statement
            .query_row(params![session_id], |row| {
                Ok(SessionRecord {
                    session_id: row.get(0)?,
                    user_id: row.get(1)?,
                    created_at: row.get(2)?,
                    last_resumed_at: row.get(3)?,
                    status: row.get(4)?,
                })
            })
            .optional()
            .map_err(Into::into)
    }

    fn fetch_task(
        &self,
        connection: &Connection,
        task_id: &str,
    ) -> anyhow::Result<Option<TaskRecord>> {
        let mut statement = connection.prepare(
            "SELECT task_id, session_id, state, title, created_at FROM tasks WHERE task_id = ?1",
        )?;

        statement
            .query_row(params![task_id], map_task_row)
            .optional()
            .map_err(Into::into)
    }

    fn fetch_task_plan(
        &self,
        connection: &Connection,
        task_id: &str,
    ) -> anyhow::Result<Option<TaskPlanRecord>> {
        let mut statement = connection
            .prepare("SELECT task_id, plan_json, updated_at FROM task_plans WHERE task_id = ?1")?;

        statement
            .query_row(params![task_id], |row| {
                Ok(TaskPlanRecord {
                    task_id: row.get(0)?,
                    plan: serde_json::from_str::<Value>(&row.get::<_, String>(1)?)
                        .unwrap_or(Value::Null),
                    updated_at: row.get(2)?,
                })
            })
            .optional()
            .map_err(Into::into)
    }

    fn fetch_working_memory(
        &self,
        connection: &Connection,
        ref_id: &str,
    ) -> anyhow::Result<Option<WorkingMemoryRecord>> {
        let mut statement = connection.prepare(
            "SELECT ref_id, session_id, payload_json, created_at FROM memory_working_refs WHERE ref_id = ?1",
        )?;

        statement
            .query_row(params![ref_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                ))
            })
            .optional()?
            .map(|(ref_id, session_id, payload_json, created_at)| {
                decode_working_memory(&ref_id, &session_id, &payload_json, &created_at)
            })
            .transpose()
    }

    fn fetch_portal_handle(
        &self,
        connection: &Connection,
        handle_id: &str,
    ) -> anyhow::Result<Option<PortalHandleRecord>> {
        let mut statement = connection.prepare(
            "SELECT handle_id, session_id, kind, scope_json, expiry FROM portal_handles WHERE handle_id = ?1",
        )?;

        statement
            .query_row(params![handle_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                ))
            })
            .optional()?
            .map(|(handle_id, session_id, kind, scope_json, expiry)| {
                decode_portal_handle(&handle_id, &session_id, &kind, &scope_json, &expiry)
            })
            .transpose()
    }
}

pub async fn bootstrap(
    config: &Config,
    observability_sink: Option<ObservabilitySink>,
) -> anyhow::Result<Database> {
    config.paths.ensure_base_dirs().await?;

    if let Some(parent) = config.database_path.parent() {
        tokio::fs::create_dir_all(parent).await?;
    }

    let database = Database::new_with_observability(
        config.database_path.clone(),
        config.migrations_dir.clone(),
        observability_sink,
    );
    database.apply_migrations()?;

    tracing::info!(
        database = %config.database_path.display(),
        migrations = %config.migrations_dir.display(),
        "sessiond storage layout prepared"
    );

    Ok(database)
}

fn map_task_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<TaskRecord> {
    Ok(TaskRecord {
        task_id: row.get(0)?,
        session_id: row.get(1)?,
        state: row.get(2)?,
        title: row.get(3)?,
        created_at: row.get(4)?,
    })
}

fn insert_task_event(
    connection: &Connection,
    task_id: &str,
    from_state: &str,
    to_state: &str,
    reason: Option<&str>,
) -> anyhow::Result<()> {
    connection.execute(
        "INSERT INTO task_events (event_id, task_id, from_state, to_state, metadata_json, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            format!("evt-{}", Uuid::new_v4()),
            task_id,
            from_state,
            to_state,
            serde_json::to_string(&json!({ "reason": reason }))?,
            Utc::now().to_rfc3339(),
        ],
    )?;
    Ok(())
}

fn assert_valid_task_transition(from: &str, to: &str) -> anyhow::Result<()> {
    if from == to {
        return Ok(());
    }

    let allowed = match from {
        "planned" => matches!(
            to,
            "approved" | "executing" | "cancelled" | "rejected" | "failed" | "replanned"
        ),
        "approved" => matches!(to, "executing" | "cancelled" | "failed"),
        "executing" => matches!(to, "completed" | "failed" | "cancelled"),
        "failed" => matches!(to, "replanned" | "cancelled"),
        "replanned" => matches!(to, "approved" | "executing" | "cancelled" | "failed"),
        "completed" | "cancelled" | "rejected" => false,
        _ => false,
    };

    if !allowed {
        anyhow::bail!("invalid task state transition: {from} -> {to}");
    }

    Ok(())
}

fn sanitize_limit(limit: Option<u32>) -> u32 {
    limit.unwrap_or(50).min(200).max(1)
}

fn map_session_row(row: &Row<'_>) -> rusqlite::Result<SessionRecord> {
    Ok(SessionRecord {
        session_id: row.get(0)?,
        user_id: row.get(1)?,
        created_at: row.get(2)?,
        last_resumed_at: row.get(3)?,
        status: row.get(4)?,
    })
}

fn count_rows(connection: &Connection, table: &str) -> anyhow::Result<usize> {
    let sql = format!("SELECT COUNT(*) FROM {table}");
    Ok(connection.query_row(&sql, [], |row| row.get::<_, i64>(0))? as usize)
}

fn decode_working_memory(
    ref_id: &str,
    session_id: &str,
    payload_json: &str,
    created_at: &str,
) -> anyhow::Result<WorkingMemoryRecord> {
    if let Ok(record) = serde_json::from_str::<WorkingMemoryRecord>(payload_json) {
        return Ok(record);
    }

    Ok(WorkingMemoryRecord {
        ref_id: ref_id.to_string(),
        session_id: session_id.to_string(),
        payload: serde_json::from_str::<Value>(payload_json).unwrap_or(Value::Null),
        tags: Vec::new(),
        created_at: created_at.to_string(),
    })
}

fn decode_episodic_memory(
    entry_id: &str,
    session_id: &str,
    summary: &str,
    metadata_json: Option<&str>,
    created_at: &str,
) -> anyhow::Result<EpisodicMemoryRecord> {
    let metadata = metadata_json
        .map(|item| serde_json::from_str::<BTreeMap<String, Value>>(item).unwrap_or_default())
        .unwrap_or_default();

    Ok(EpisodicMemoryRecord {
        entry_id: entry_id.to_string(),
        session_id: session_id.to_string(),
        summary: summary.to_string(),
        metadata,
        created_at: created_at.to_string(),
    })
}

fn decode_procedural_memory(
    version_id: &str,
    session_id: &str,
    rule_name: &str,
    payload_json: &str,
    created_at: &str,
) -> anyhow::Result<ProceduralMemoryRecord> {
    Ok(ProceduralMemoryRecord {
        version_id: version_id.to_string(),
        session_id: session_id.to_string(),
        rule_name: rule_name.to_string(),
        payload: serde_json::from_str::<Value>(payload_json).unwrap_or(Value::Null),
        created_at: created_at.to_string(),
    })
}

fn decode_semantic_memory(
    index_id: &str,
    session_id: &str,
    label: &str,
    payload_json: &str,
    created_at: &str,
) -> anyhow::Result<SemanticMemoryRecord> {
    Ok(SemanticMemoryRecord {
        index_id: index_id.to_string(),
        session_id: session_id.to_string(),
        label: label.to_string(),
        payload: serde_json::from_str::<Value>(payload_json).unwrap_or(Value::Null),
        created_at: created_at.to_string(),
    })
}

fn decode_task_event(
    event_id: &str,
    task_id: &str,
    from_state: &str,
    to_state: &str,
    metadata_json: Option<&str>,
    created_at: &str,
) -> anyhow::Result<TaskEventRecord> {
    let metadata = metadata_json
        .and_then(|item| serde_json::from_str::<Value>(item).ok())
        .unwrap_or(Value::Null);

    Ok(TaskEventRecord {
        event_id: event_id.to_string(),
        task_id: task_id.to_string(),
        from_state: from_state.to_string(),
        to_state: to_state.to_string(),
        metadata,
        created_at: created_at.to_string(),
    })
}

fn decode_portal_handle(
    handle_id: &str,
    session_id: &str,
    kind: &str,
    scope_json: &str,
    expiry: &str,
) -> anyhow::Result<PortalHandleRecord> {
    if let Ok(record) = serde_json::from_str::<PortalHandleRecord>(scope_json) {
        return Ok(record);
    }

    let scope = serde_json::from_str::<BTreeMap<String, Value>>(scope_json).unwrap_or_default();
    Ok(PortalHandleRecord {
        handle_id: handle_id.to_string(),
        kind: kind.to_string(),
        user_id: scope
            .get("user_id")
            .and_then(Value::as_str)
            .unwrap_or("unknown-user")
            .to_string(),
        session_id: session_id.to_string(),
        target: scope
            .get("target_path")
            .or_else(|| scope.get("target"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        scope,
        expiry: expiry.to_string(),
        revocable: true,
        issued_at: expiry.to_string(),
        revoked_at: None,
        revocation_reason: None,
        audit_tags: Vec::new(),
    })
}

fn table_exists(connection: &Connection, table: &str) -> anyhow::Result<bool> {
    Ok(connection.query_row(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?1",
        params![table],
        |row| row.get::<_, i64>(0),
    )? > 0)
}

pub fn migrations_dir(path: &Path) -> &Path {
    path
}

#[cfg(test)]
mod tests {
    use std::{collections::BTreeMap, path::PathBuf};

    use serde_json::{json, Value};
    use uuid::Uuid;

    use super::*;

    fn test_database() -> (Database, PathBuf) {
        let root = std::env::temp_dir().join(format!("aios-sessiond-test-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&root).expect("create temp root");
        let database_path = root.join("sessiond.sqlite3");
        let migrations_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("migrations");
        let database = Database::new(database_path, migrations_dir);
        database.apply_migrations().expect("apply migrations");
        (database, root)
    }

    #[test]
    fn task_state_updates_are_mirrored_to_observability_sink() {
        let root =
            std::env::temp_dir().join(format!("aios-sessiond-observability-db-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&root).expect("create temp root");
        let database_path = root.join("sessiond.sqlite3");
        let observability_path = root.join("observability.jsonl");
        let migrations_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("migrations");
        let sink =
            ObservabilitySink::new(observability_path.clone()).expect("create observability sink");
        let database =
            Database::new_with_observability(database_path.clone(), migrations_dir, Some(sink));
        database.apply_migrations().expect("apply migrations");

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "trace-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");
        let task = database
            .create_task(&TaskCreateRequest {
                session_id: session.session_id.clone(),
                title: Some("Trace task".to_string()),
                state: "planned".to_string(),
            })
            .expect("create task");
        database
            .update_task_state(&TaskStateUpdateRequest {
                task_id: task.task_id.clone(),
                new_state: "approved".to_string(),
                reason: Some("trace transition".to_string()),
            })
            .expect("update task state")
            .expect("task exists");

        let records = std::fs::read_to_string(&observability_path).expect("read observability");
        assert!(records.contains("\"kind\":\"session.created\""));
        assert!(records.contains("\"kind\":\"task.created\""));
        assert!(records.contains("\"kind\":\"task.state.updated\""));
        assert!(records.contains(&database_path.display().to_string()));

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn session_list_orders_by_recent_activity_and_filters() {
        let (database, root) = test_database();

        let first = database
            .create_session(&SessionCreateRequest {
                user_id: "launcher-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create first session");
        std::thread::sleep(std::time::Duration::from_millis(2));
        let second = database
            .create_session(&SessionCreateRequest {
                user_id: "other-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create second session");
        database
            .close_session(&SessionCloseRequest {
                session_id: second.session_id.clone(),
            })
            .expect("close second session")
            .expect("second session exists");
        database
            .resume_session(&SessionResumeRequest {
                session_id: first.session_id.clone(),
            })
            .expect("resume first session")
            .expect("first session exists");

        let listed = database
            .list_sessions(&SessionListRequest {
                user_id: None,
                status: None,
                limit: Some(10),
            })
            .expect("list sessions");
        assert_eq!(listed.sessions.len(), 2);
        assert_eq!(listed.sessions[0].session_id, first.session_id);

        let active_filtered = database
            .list_sessions(&SessionListRequest {
                user_id: Some("launcher-user".to_string()),
                status: Some("active".to_string()),
                limit: Some(10),
            })
            .expect("list filtered sessions");
        assert_eq!(active_filtered.sessions.len(), 1);
        assert_eq!(active_filtered.sessions[0].session_id, first.session_id);

        let closed_filtered = database
            .list_sessions(&SessionListRequest {
                user_id: None,
                status: Some("closed".to_string()),
                limit: Some(10),
            })
            .expect("list closed sessions");
        assert_eq!(closed_filtered.sessions.len(), 1);
        assert_eq!(closed_filtered.sessions[0].session_id, second.session_id);

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn task_lifecycle_roundtrip_persists_and_filters() {
        let (database, root) = test_database();

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "test-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");

        let task = database
            .create_task(&TaskCreateRequest {
                session_id: session.session_id.clone(),
                title: Some("Draft plan".to_string()),
                state: "planned".to_string(),
            })
            .expect("create task");

        let listed = database
            .list_tasks(&TaskListRequest {
                session_id: session.session_id.clone(),
                state: None,
                limit: Some(10),
            })
            .expect("list tasks");
        assert_eq!(listed.tasks.len(), 1);
        assert_eq!(listed.tasks[0].task_id, task.task_id);

        let updated = database
            .update_task_state(&TaskStateUpdateRequest {
                task_id: task.task_id.clone(),
                new_state: "approved".to_string(),
                reason: Some("unit-test".to_string()),
            })
            .expect("update task state")
            .expect("task exists");
        assert_eq!(updated.state, "approved");

        let filtered = database
            .list_tasks(&TaskListRequest {
                session_id: session.session_id,
                state: Some("approved".to_string()),
                limit: Some(10),
            })
            .expect("filter tasks");
        assert_eq!(filtered.tasks.len(), 1);
        assert_eq!(filtered.tasks[0].task_id, task.task_id);

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn working_and_episodic_memory_roundtrip() {
        let (database, root) = test_database();

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "memory-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");

        let working = database
            .write_working_memory(&WorkingMemoryWriteRequest {
                session_id: session.session_id.clone(),
                ref_id: Some("wm-test".to_string()),
                payload: json!({"kind": "plan", "task_id": "task-1"}),
                tags: vec!["unit-test".to_string()],
            })
            .expect("write working memory");
        assert_eq!(working.ref_id, "wm-test");

        let working_list = database
            .read_working_memory(&WorkingMemoryReadRequest {
                session_id: session.session_id.clone(),
                ref_id: None,
                limit: Some(10),
            })
            .expect("read working memory");
        assert_eq!(working_list.entries.len(), 1);
        assert_eq!(working_list.entries[0].ref_id, "wm-test");

        let mut metadata = BTreeMap::new();
        metadata.insert("task_id".to_string(), json!("task-1"));
        metadata.insert("task_state".to_string(), json!("approved"));
        let episodic = database
            .append_episodic_memory(&EpisodicMemoryAppendRequest {
                session_id: session.session_id.clone(),
                summary: "approved plan stored".to_string(),
                metadata,
            })
            .expect("append episodic memory");
        assert!(episodic.entry_id.starts_with("ep-"));

        let episodic_list = database
            .list_episodic_memory(&EpisodicMemoryListRequest {
                session_id: session.session_id.clone(),
                limit: Some(10),
            })
            .expect("list episodic memory");
        assert_eq!(episodic_list.entries.len(), 1);
        assert_eq!(episodic_list.entries[0].summary, "approved plan stored");
        assert_eq!(
            episodic_list.entries[0]
                .metadata
                .get("task_id")
                .and_then(Value::as_str),
            Some("task-1")
        );

        let summary = database.memory_summary().expect("memory summary");
        assert_eq!(summary.working_refs, 1);
        assert_eq!(summary.episodic_entries, 1);

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn task_events_are_recorded_and_invalid_transitions_fail() {
        let (database, root) = test_database();

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "events-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");

        let task = database
            .create_task(&TaskCreateRequest {
                session_id: session.session_id,
                title: Some("Review report".to_string()),
                state: "planned".to_string(),
            })
            .expect("create task");

        database
            .update_task_state(&TaskStateUpdateRequest {
                task_id: task.task_id.clone(),
                new_state: "approved".to_string(),
                reason: Some("reviewed".to_string()),
            })
            .expect("approve task");

        let connection = database.open_connection().expect("open connection");
        let event_count = connection
            .query_row(
                "SELECT COUNT(*) FROM task_events WHERE task_id = ?1",
                params![&task.task_id],
                |row| row.get::<_, i64>(0),
            )
            .expect("count task events");
        assert_eq!(event_count, 2);

        let invalid = database.update_task_state(&TaskStateUpdateRequest {
            task_id: task.task_id,
            new_state: "planned".to_string(),
            reason: Some("invalid rollback".to_string()),
        });
        assert!(invalid.is_err());

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn semantic_memory_roundtrip_filters_by_label() {
        let (database, root) = test_database();

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "semantic-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");

        let first = database
            .put_semantic_memory(&SemanticMemoryPutRequest {
                session_id: session.session_id.clone(),
                label: "plan-summary".to_string(),
                payload: json!({"summary": "Summarize project plan", "capability": "runtime.infer.submit"}),
            })
            .expect("put semantic memory");
        assert!(first.index_id.starts_with("sem-"));

        database
            .put_semantic_memory(&SemanticMemoryPutRequest {
                session_id: session.session_id.clone(),
                label: "provider-resolution".to_string(),
                payload: json!({"provider_id": "runtime.local.inference"}),
            })
            .expect("put second semantic memory");

        let all = database
            .list_semantic_memory(&SemanticMemoryListRequest {
                session_id: session.session_id.clone(),
                label: None,
                limit: Some(10),
            })
            .expect("list all semantic memory");
        assert_eq!(all.entries.len(), 2);

        let filtered = database
            .list_semantic_memory(&SemanticMemoryListRequest {
                session_id: session.session_id,
                label: Some("plan-summary".to_string()),
                limit: Some(10),
            })
            .expect("list filtered semantic memory");
        assert_eq!(filtered.entries.len(), 1);
        assert_eq!(filtered.entries[0].label, "plan-summary");
        assert_eq!(
            filtered.entries[0]
                .payload
                .get("capability")
                .and_then(Value::as_str),
            Some("runtime.infer.submit")
        );

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn task_event_query_returns_latest_events_with_metadata() {
        let (database, root) = test_database();

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "events-query-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");

        let task = database
            .create_task(&TaskCreateRequest {
                session_id: session.session_id,
                title: Some("Approval flow".to_string()),
                state: "planned".to_string(),
            })
            .expect("create task");

        database
            .update_task_state(&TaskStateUpdateRequest {
                task_id: task.task_id.clone(),
                new_state: "approved".to_string(),
                reason: Some("user approved".to_string()),
            })
            .expect("approve task");
        database
            .update_task_state(&TaskStateUpdateRequest {
                task_id: task.task_id.clone(),
                new_state: "executing".to_string(),
                reason: Some("worker admitted".to_string()),
            })
            .expect("start task");

        let latest = database
            .list_task_events(&TaskEventListRequest {
                task_id: task.task_id.clone(),
                limit: 2,
                reverse: true,
            })
            .expect("list latest task events");
        assert_eq!(latest.events.len(), 2);
        assert_eq!(latest.events[0].to_state, "executing");
        assert_eq!(latest.events[1].to_state, "approved");
        assert_eq!(
            latest.events[0]
                .metadata
                .get("reason")
                .and_then(Value::as_str),
            Some("worker admitted")
        );

        let oldest = database
            .list_task_events(&TaskEventListRequest {
                task_id: task.task_id,
                limit: 1,
                reverse: false,
            })
            .expect("list oldest task event");
        assert_eq!(oldest.events.len(), 1);
        assert_eq!(oldest.events[0].from_state, "created");
        assert_eq!(oldest.events[0].to_state, "planned");

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn portal_handles_and_recovery_refs_roundtrip() {
        let (database, root) = test_database();

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "portal-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");

        let mut scope = BTreeMap::new();
        scope.insert("target".to_string(), json!("/tmp/report.txt"));
        scope.insert("user_id".to_string(), json!("portal-user"));
        let handle = PortalHandleRecord {
            handle_id: "hdl-test".to_string(),
            kind: "file_handle".to_string(),
            user_id: "portal-user".to_string(),
            session_id: session.session_id.clone(),
            target: "/tmp/report.txt".to_string(),
            scope,
            expiry: "2099-01-01T00:00:00Z".to_string(),
            revocable: true,
            issued_at: "2026-01-01T00:00:00Z".to_string(),
            revoked_at: None,
            revocation_reason: None,
            audit_tags: vec!["unit-test".to_string()],
        };
        database
            .bind_portal_handle(&handle)
            .expect("bind portal handle");

        let loaded = database
            .get_portal_handle("hdl-test")
            .expect("get portal handle")
            .expect("portal handle exists");
        assert_eq!(loaded.target, "/tmp/report.txt");

        let listed = database
            .list_portal_handles(Some(&session.session_id))
            .expect("list portal handles");
        assert_eq!(listed.handles.len(), 1);
        assert_eq!(listed.handles[0].handle_id, "hdl-test");

        let first_recovery = database
            .recovery_ref(&session.session_id)
            .expect("first recovery ref");
        let second_recovery = database
            .recovery_ref(&session.session_id)
            .expect("second recovery ref");
        assert_eq!(first_recovery.recovery_id, second_recovery.recovery_id);

        std::fs::remove_dir_all(root).ok();
    }

    #[test]
    fn procedural_memory_versions_are_append_only() {
        let (database, root) = test_database();

        let session = database
            .create_session(&SessionCreateRequest {
                user_id: "proc-user".to_string(),
                metadata: BTreeMap::new(),
            })
            .expect("create session");

        let first = database
            .put_procedural_memory(&ProceduralMemoryPutRequest {
                session_id: session.session_id.clone(),
                rule_name: "agent.plan.default".to_string(),
                payload: json!({"topology": "direct"}),
            })
            .expect("put first procedural memory");
        let second = database
            .put_procedural_memory(&ProceduralMemoryPutRequest {
                session_id: session.session_id.clone(),
                rule_name: "agent.plan.default".to_string(),
                payload: json!({"topology": "plan-execute"}),
            })
            .expect("put second procedural memory");
        assert_ne!(first.version_id, second.version_id);

        let listed = database
            .list_procedural_memory(&ProceduralMemoryListRequest {
                session_id: session.session_id,
                rule_name: Some("agent.plan.default".to_string()),
                limit: Some(10),
            })
            .expect("list procedural memory");
        assert_eq!(listed.entries.len(), 2);
        assert!(listed
            .entries
            .iter()
            .any(|item| item.version_id == first.version_id));
        assert!(listed
            .entries
            .iter()
            .any(|item| item.version_id == second.version_id));

        let summary = database.memory_summary().expect("memory summary");
        assert_eq!(summary.procedural_rules, 2);

        std::fs::remove_dir_all(root).ok();
    }
}
