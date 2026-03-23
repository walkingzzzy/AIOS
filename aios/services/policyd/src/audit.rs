use anyhow::Context;
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, BufWriter, Write},
    path::{Path, PathBuf},
};

use aios_contracts::{
    ApprovalRecord, AuditExportRequest, AuditExportResponse, AuditQueryRequest, AuditQueryResponse,
    AuditRecord, ExecutionToken, PolicyEvaluateRequest, PolicyEvaluateResponse, TokenIssueRequest,
    TokenVerifyRequest, TokenVerifyResponse,
};
use aios_core::schema::CURRENT_OBSERVABILITY_SCHEMA_VERSION;

use crate::observability::ObservabilitySink;

#[derive(Debug, Clone)]
pub struct AuditStoreConfig {
    pub index_path: PathBuf,
    pub archive_dir: PathBuf,
    pub rotate_after_bytes: u64,
    pub retention_days: u64,
    pub max_archives: usize,
}

impl AuditStoreConfig {
    pub fn for_active_log(path: &Path) -> Self {
        let parent = path
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| PathBuf::from("."));
        let stem = path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("audit");

        Self {
            index_path: parent.join(format!("{stem}-index.json")),
            archive_dir: parent.join(format!("{stem}-archive")),
            rotate_after_bytes: 256 * 1024,
            retention_days: 30,
            max_archives: 32,
        }
    }
}

#[derive(Debug, Clone)]
pub struct AuditWriter {
    path: PathBuf,
    index_path: PathBuf,
    archive_dir: PathBuf,
    rotate_after_bytes: u64,
    retention_days: u64,
    max_archives: usize,
    observability_sink: Option<ObservabilitySink>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AuditStoreIndex {
    schema_version: String,
    generated_at: String,
    active_log: String,
    index_path: String,
    archive_dir: String,
    rotate_after_bytes: u64,
    retention_days: u64,
    max_archives: usize,
    active_segment: AuditSegmentMetadata,
    #[serde(default)]
    archived_segments: Vec<AuditSegmentMetadata>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AuditSegmentMetadata {
    segment_id: String,
    path: String,
    status: String,
    created_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    rotated_at: Option<String>,
    record_count: u64,
    size_bytes: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    first_timestamp: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    last_timestamp: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    first_audit_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    last_audit_id: Option<String>,
}

impl AuditSegmentMetadata {
    fn empty(segment_id: String, path: PathBuf, status: &str, created_at: String) -> Self {
        Self {
            segment_id,
            path: path.display().to_string(),
            status: status.to_string(),
            created_at,
            rotated_at: None,
            record_count: 0,
            size_bytes: 0,
            first_timestamp: None,
            last_timestamp: None,
            first_audit_id: None,
            last_audit_id: None,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct AuditExportStoreMetadata {
    active_segment_path: String,
    index_path: String,
    archive_dir: String,
    archived_segment_count: u32,
}

#[derive(Debug, Clone, Serialize)]
struct AuditExportBundle {
    export_id: String,
    created_at: String,
    service_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    filters: AuditQueryRequest,
    notes: Vec<String>,
    audit_store: AuditExportStoreMetadata,
    entries: Vec<AuditRecord>,
}

impl AuditWriter {
    pub fn new(path: PathBuf, observability_sink: Option<ObservabilitySink>) -> Self {
        let config = AuditStoreConfig::for_active_log(&path);
        Self::with_store_config(path, observability_sink, config)
    }

    pub fn with_store_config(
        path: PathBuf,
        observability_sink: Option<ObservabilitySink>,
        config: AuditStoreConfig,
    ) -> Self {
        Self {
            path,
            index_path: config.index_path,
            archive_dir: config.archive_dir,
            rotate_after_bytes: config.rotate_after_bytes,
            retention_days: config.retention_days,
            max_archives: config.max_archives,
            observability_sink,
        }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn index_path(&self) -> &Path {
        &self.index_path
    }

    pub fn archive_dir(&self) -> &Path {
        &self.archive_dir
    }

    pub fn rotate_after_bytes(&self) -> u64 {
        self.rotate_after_bytes
    }

    pub fn retention_days(&self) -> u64 {
        self.retention_days
    }

    pub fn max_archives(&self) -> usize {
        self.max_archives
    }

    pub fn archived_segment_count(&self) -> anyhow::Result<usize> {
        Ok(self.load_index()?.archived_segments.len())
    }

    pub fn append_evaluation(
        &self,
        request: &PolicyEvaluateRequest,
        response: &PolicyEvaluateResponse,
        approval_lane: &str,
        approval_id: Option<&str>,
    ) -> anyhow::Result<()> {
        let mut payload = json!({
            "audit_id": format!("audit-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": Utc::now().to_rfc3339(),
            "generated_at": Utc::now().to_rfc3339(),
            "user_id": request.user_id,
            "session_id": request.session_id,
            "task_id": request.task_id,
            "capability_id": request.capability_id,
            "decision": response.decision,
            "execution_location": request.execution_location,
            "route_state": approval_lane,
            "taint_summary": response.taint_summary,
            "result": {
                "reason": response.reason,
                "target_hash": request.target_hash,
                "constraints": request.constraints,
            },
        });
        if let Some(item) = approval_id {
            payload["approval_id"] = Value::String(item.to_string());
        }
        self.append_json(payload)
    }

    pub fn append_token(&self, token: &ExecutionToken) -> anyhow::Result<()> {
        let mut payload = json!({
            "audit_id": format!("token-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": Utc::now().to_rfc3339(),
            "generated_at": Utc::now().to_rfc3339(),
            "user_id": token.user_id,
            "session_id": token.session_id,
            "task_id": token.task_id,
            "capability_id": token.capability_id,
            "decision": "token-issued",
            "execution_location": token.execution_location,
            "taint_summary": token.taint_summary,
            "result": token,
        });
        if let Some(item) = token.approval_ref.as_deref() {
            payload["approval_id"] = Value::String(item.to_string());
        }
        self.append_json(payload)
    }

    pub fn append_token_verify(
        &self,
        request: &TokenVerifyRequest,
        response: &TokenVerifyResponse,
    ) -> anyhow::Result<()> {
        let decision = if response.valid && response.consumed {
            "token-consumed"
        } else if response.valid {
            "token-valid"
        } else if response.consume_applied {
            "token-reused"
        } else {
            "token-invalid"
        };
        let mut payload = json!({
            "audit_id": format!("verify-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": Utc::now().to_rfc3339(),
            "generated_at": Utc::now().to_rfc3339(),
            "user_id": request.token.user_id,
            "session_id": request.token.session_id,
            "task_id": request.token.task_id,
            "capability_id": request.token.capability_id,
            "decision": decision,
            "execution_location": request.token.execution_location,
            "taint_summary": request.token.taint_summary,
            "result": {
                "reason": response.reason,
                "consume_requested": request.consume,
                "consume_applied": response.consume_applied,
                "consumed": response.consumed,
            },
        });
        if let Some(item) = request.token.approval_ref.as_deref() {
            payload["approval_id"] = Value::String(item.to_string());
        }
        self.append_json(payload)
    }

    pub fn append_approval_created(&self, approval: &ApprovalRecord) -> anyhow::Result<()> {
        self.append_json(json!({
            "audit_id": format!("approval-{}", approval.approval_ref),
            "timestamp": Utc::now().to_rfc3339(),
            "generated_at": Utc::now().to_rfc3339(),
            "user_id": approval.user_id,
            "session_id": approval.session_id,
            "task_id": approval.task_id,
            "approval_id": approval.approval_ref,
            "capability_id": approval.capability_id,
            "decision": "approval-pending",
            "execution_location": approval.execution_location,
            "route_state": approval.approval_lane,
            "taint_summary": approval.taint_summary,
            "result": {
                "approval_ref": approval.approval_ref,
                "status": approval.status,
                "reason": approval.reason,
                "expires_at": approval.expires_at,
                "target_hash": approval.target_hash,
                "constraints": approval.constraints,
            },
        }))
    }

    pub fn append_approval_resolved(&self, approval: &ApprovalRecord) -> anyhow::Result<()> {
        self.append_json(json!({
            "audit_id": format!("approval-{}-{}", approval.status, approval.approval_ref),
            "timestamp": Utc::now().to_rfc3339(),
            "generated_at": Utc::now().to_rfc3339(),
            "user_id": approval.user_id,
            "session_id": approval.session_id,
            "task_id": approval.task_id,
            "approval_id": approval.approval_ref,
            "capability_id": approval.capability_id,
            "decision": format!("approval-{}", approval.status),
            "execution_location": approval.execution_location,
            "route_state": approval.approval_lane,
            "taint_summary": approval.taint_summary,
            "result": {
                "approval_ref": approval.approval_ref,
                "status": approval.status,
                "resolver": approval.resolver,
                "resolved_at": approval.resolved_at,
                "resolution_reason": approval.resolution_reason,
                "expires_at": approval.expires_at,
                "target_hash": approval.target_hash,
                "constraints": approval.constraints,
            },
        }))
    }

    pub fn append_approval_scope_mismatch(
        &self,
        request: &TokenIssueRequest,
        approval: &ApprovalRecord,
        mismatch: &crate::approval::ApprovalScopeError,
    ) -> anyhow::Result<()> {
        self.append_json(json!({
            "audit_id": format!("approval-scope-mismatch-{}", Utc::now().timestamp_nanos_opt().unwrap_or_default()),
            "timestamp": Utc::now().to_rfc3339(),
            "generated_at": Utc::now().to_rfc3339(),
            "user_id": request.user_id,
            "session_id": request.session_id,
            "task_id": request.task_id,
            "approval_id": approval.approval_ref,
            "capability_id": request.capability_id,
            "decision": "approval-scope-mismatch",
            "execution_location": request.execution_location,
            "taint_summary": request.taint_summary,
            "result": {
                "approval_ref": approval.approval_ref,
                "reason": mismatch.to_string(),
                "requested_target_hash": request.target_hash,
                "requested_constraints": request.constraints,
                "approved_target_hash": approval.target_hash,
                "approved_constraints": approval.constraints,
                "scope_mismatch": mismatch.audit_payload(),
            },
        }))
    }

    pub fn query(&self, request: &AuditQueryRequest) -> anyhow::Result<AuditQueryResponse> {
        let mut entries = Vec::new();
        for path in self.segment_paths()? {
            if !path.exists() {
                continue;
            }

            let file = File::open(&path)?;
            for line in BufReader::new(file).lines() {
                let line = line?;
                if line.trim().is_empty() {
                    continue;
                }

                let entry = serde_json::from_str::<AuditRecord>(&line)
                    .with_context(|| format!("failed to decode audit record {}", path.display()))?;
                if !matches_request(&entry, request) {
                    continue;
                }
                entries.push(entry);
            }
        }

        if request.reverse {
            entries.reverse();
        }

        entries.truncate(request.limit.max(1) as usize);
        Ok(AuditQueryResponse { entries })
    }

    pub fn export(
        &self,
        service_id: &str,
        export_dir: &Path,
        request: &AuditExportRequest,
    ) -> anyhow::Result<AuditExportResponse> {
        let query = audit_query_from_export_request(request);
        let entries = self.query(&query)?.entries;
        let index = self.load_index()?;
        let created_at = Utc::now().to_rfc3339();
        let export_id = format!("audit-export-{}", Utc::now().timestamp_millis());
        let export_path = export_dir.join(format!("{export_id}.json"));
        let mut notes = vec![
            format!("limit={}", request.limit),
            format!("reverse={}", request.reverse),
            format!("export_dir={}", export_dir.display()),
        ];
        if let Some(reason) = request.reason.as_deref() {
            notes.push(format!("reason={reason}"));
        }

        let audit_store = AuditExportStoreMetadata {
            active_segment_path: index.active_segment.path.clone(),
            index_path: self.index_path.display().to_string(),
            archive_dir: self.archive_dir.display().to_string(),
            archived_segment_count: count_u32(index.archived_segments.len()),
        };
        let bundle = AuditExportBundle {
            export_id: export_id.clone(),
            created_at: created_at.clone(),
            service_id: service_id.to_string(),
            reason: request.reason.clone(),
            filters: query,
            notes: notes.clone(),
            audit_store: audit_store.clone(),
            entries: entries.clone(),
        };

        if let Some(parent) = export_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&export_path, serde_json::to_vec_pretty(&bundle)?)?;

        let session_count = count_u32(
            entries
                .iter()
                .map(|entry| entry.session_id.clone())
                .collect::<BTreeSet<_>>()
                .len(),
        );
        let task_count = count_u32(
            entries
                .iter()
                .map(|entry| entry.task_id.clone())
                .collect::<BTreeSet<_>>()
                .len(),
        );
        let approval_ref_count = count_u32(
            entries
                .iter()
                .filter_map(audit_approval_ref)
                .collect::<BTreeSet<_>>()
                .len(),
        );
        let decision_count = count_u32(
            entries
                .iter()
                .map(|entry| entry.decision.clone())
                .collect::<BTreeSet<_>>()
                .len(),
        );

        Ok(AuditExportResponse {
            service_id: service_id.to_string(),
            export_id,
            export_path: export_path.display().to_string(),
            created_at,
            entry_count: count_u32(entries.len()),
            session_count,
            task_count,
            approval_ref_count,
            decision_count,
            active_segment_path: audit_store.active_segment_path,
            index_path: audit_store.index_path,
            archive_dir: audit_store.archive_dir,
            archived_segment_count: audit_store.archived_segment_count,
            notes,
        })
    }

    fn append_json(&self, mut payload: Value) -> anyhow::Result<()> {
        let object = payload
            .as_object_mut()
            .context("audit payload must be a JSON object")?;
        let nullable_keys = object
            .iter()
            .filter_map(|(key, value)| {
                if value.is_null() && key != "result" {
                    Some(key.clone())
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        for key in nullable_keys {
            object.remove(&key);
        }
        object
            .entry("schema_version".to_string())
            .or_insert(Value::String(
                CURRENT_OBSERVABILITY_SCHEMA_VERSION.to_string(),
            ));
        object
            .entry("artifact_path".to_string())
            .or_insert(Value::String(self.path.display().to_string()));
        if !object.contains_key("generated_at") {
            if let Some(timestamp) = object.get("timestamp").cloned() {
                object.insert("generated_at".to_string(), timestamp);
            }
        }

        let mut index = self.load_index()?;
        let line = serde_json::to_string(&payload)?;
        if self.should_rotate(line.len() as u64 + 1)? {
            self.rotate_active_segment(&mut index)?;
        }

        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }
        if let Some(parent) = self.index_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::create_dir_all(&self.archive_dir)?;

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        writeln!(file, "{line}")?;
        file.flush()?;

        Self::touch_segment_metadata(&mut index.active_segment, &payload);
        index.active_segment.size_bytes = fs::metadata(&self.path)?.len();
        index.generated_at = Utc::now().to_rfc3339();
        index.active_log = self.path.display().to_string();
        index.index_path = self.index_path.display().to_string();
        index.archive_dir = self.archive_dir.display().to_string();
        index.rotate_after_bytes = self.rotate_after_bytes;
        index.retention_days = self.retention_days;
        index.max_archives = self.max_archives;
        self.enforce_retention(&mut index)?;
        self.save_index(&index)?;

        if let Some(sink) = &self.observability_sink {
            if let Err(error) = sink.append_record(&payload) {
                tracing::warn!(
                    ?error,
                    "failed to mirror policyd audit into observability sink"
                );
            }
        }
        Ok(())
    }

    fn should_rotate(&self, incoming_bytes: u64) -> anyhow::Result<bool> {
        if self.rotate_after_bytes == 0 || !self.path.exists() {
            return Ok(false);
        }

        let current_size = fs::metadata(&self.path)?.len();
        Ok(current_size > 0
            && current_size.saturating_add(incoming_bytes) > self.rotate_after_bytes)
    }

    fn rotate_active_segment(&self, index: &mut AuditStoreIndex) -> anyhow::Result<()> {
        if !self.path.exists() || fs::metadata(&self.path)?.len() == 0 {
            return Ok(());
        }

        fs::create_dir_all(&self.archive_dir)?;
        let rotation_time = Utc::now();
        let segment_id = format!(
            "audit-segment-{}",
            rotation_time.timestamp_nanos_opt().unwrap_or_default()
        );
        let archive_path = self.archive_dir.join(format!("{segment_id}.jsonl"));

        let reader =
            BufReader::new(File::open(&self.path).with_context(|| {
                format!("failed to open active audit log {}", self.path.display())
            })?);
        let mut writer = BufWriter::new(File::create(&archive_path).with_context(|| {
            format!(
                "failed to create archive audit segment {}",
                archive_path.display()
            )
        })?);
        let mut archived_segment = AuditSegmentMetadata::empty(
            segment_id,
            archive_path.clone(),
            "archived",
            index.active_segment.created_at.clone(),
        );
        archived_segment.rotated_at = Some(rotation_time.to_rfc3339());

        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }

            let mut value: Value = serde_json::from_str(&line).with_context(|| {
                format!(
                    "failed to decode active audit record during rotation {}",
                    self.path.display()
                )
            })?;
            if let Some(object) = value.as_object_mut() {
                object.insert(
                    "artifact_path".to_string(),
                    Value::String(archive_path.display().to_string()),
                );
            }
            let archived_line = serde_json::to_string(&value)?;
            writeln!(writer, "{archived_line}")?;
            Self::touch_segment_metadata(&mut archived_segment, &value);
        }
        writer.flush()?;
        archived_segment.size_bytes = fs::metadata(&archive_path)?.len();
        index.archived_segments.push(archived_segment);

        fs::remove_file(&self.path)?;
        index.active_segment = AuditSegmentMetadata::empty(
            "active".to_string(),
            self.path.clone(),
            "active",
            rotation_time.to_rfc3339(),
        );
        index.generated_at = rotation_time.to_rfc3339();
        self.enforce_retention(index)?;
        self.save_index(index)?;
        Ok(())
    }

    fn segment_paths(&self) -> anyhow::Result<Vec<PathBuf>> {
        if !self.index_path.exists() {
            return Ok(if self.path.exists() {
                vec![self.path.clone()]
            } else {
                Vec::new()
            });
        }

        let index = self.load_index()?;
        let mut paths = index
            .archived_segments
            .into_iter()
            .map(|segment| PathBuf::from(segment.path))
            .collect::<Vec<_>>();
        paths.push(PathBuf::from(index.active_segment.path));
        Ok(paths)
    }

    fn load_index(&self) -> anyhow::Result<AuditStoreIndex> {
        if !self.index_path.exists() {
            return self.build_default_index();
        }

        let text = fs::read_to_string(&self.index_path)
            .with_context(|| format!("failed to read audit index {}", self.index_path.display()))?;
        let mut index = serde_json::from_str::<AuditStoreIndex>(&text).with_context(|| {
            format!("failed to decode audit index {}", self.index_path.display())
        })?;
        index.active_log = self.path.display().to_string();
        index.index_path = self.index_path.display().to_string();
        index.archive_dir = self.archive_dir.display().to_string();
        index.rotate_after_bytes = self.rotate_after_bytes;
        index.retention_days = self.retention_days;
        index.max_archives = self.max_archives;
        index.active_segment.path = self.path.display().to_string();
        index.active_segment.status = "active".to_string();
        Ok(index)
    }

    fn build_default_index(&self) -> anyhow::Result<AuditStoreIndex> {
        let now = Utc::now().to_rfc3339();
        Ok(AuditStoreIndex {
            schema_version: CURRENT_OBSERVABILITY_SCHEMA_VERSION.to_string(),
            generated_at: now.clone(),
            active_log: self.path.display().to_string(),
            index_path: self.index_path.display().to_string(),
            archive_dir: self.archive_dir.display().to_string(),
            rotate_after_bytes: self.rotate_after_bytes,
            retention_days: self.retention_days,
            max_archives: self.max_archives,
            active_segment: self.scan_segment(
                &self.path,
                "active".to_string(),
                "active",
                now,
                None,
            )?,
            archived_segments: Vec::new(),
        })
    }

    fn scan_segment(
        &self,
        path: &Path,
        segment_id: String,
        status: &str,
        created_at: String,
        rotated_at: Option<String>,
    ) -> anyhow::Result<AuditSegmentMetadata> {
        let mut metadata =
            AuditSegmentMetadata::empty(segment_id, path.to_path_buf(), status, created_at);
        metadata.rotated_at = rotated_at;
        if !path.exists() {
            return Ok(metadata);
        }

        let file = File::open(path)
            .with_context(|| format!("failed to open audit segment {}", path.display()))?;
        for line in BufReader::new(file).lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }

            let value = serde_json::from_str::<Value>(&line).with_context(|| {
                format!("failed to decode audit segment record {}", path.display())
            })?;
            Self::touch_segment_metadata(&mut metadata, &value);
        }
        metadata.size_bytes = fs::metadata(path)?.len();
        Ok(metadata)
    }

    fn enforce_retention(&self, index: &mut AuditStoreIndex) -> anyhow::Result<()> {
        if self.retention_days > 0 {
            let cutoff = Utc::now() - Duration::days(self.retention_days as i64);
            let mut retained = Vec::with_capacity(index.archived_segments.len());
            for segment in index.archived_segments.drain(..) {
                let is_expired = segment_reference_time(&segment)
                    .map(|timestamp| timestamp < cutoff)
                    .unwrap_or(false);
                if is_expired {
                    remove_file_if_exists(Path::new(&segment.path))?;
                    continue;
                }
                retained.push(segment);
            }
            index.archived_segments = retained;
        }

        if self.max_archives > 0 && index.archived_segments.len() > self.max_archives {
            let remove_count = index.archived_segments.len() - self.max_archives;
            for segment in index.archived_segments.drain(0..remove_count) {
                remove_file_if_exists(Path::new(&segment.path))?;
            }
        }

        Ok(())
    }

    fn save_index(&self, index: &AuditStoreIndex) -> anyhow::Result<()> {
        if let Some(parent) = self.index_path.parent() {
            fs::create_dir_all(parent)?;
        }
        let text = serde_json::to_string_pretty(index)?;
        fs::write(&self.index_path, text).with_context(|| {
            format!(
                "failed to persist audit index {}",
                self.index_path.display()
            )
        })
    }

    fn touch_segment_metadata(metadata: &mut AuditSegmentMetadata, payload: &Value) {
        metadata.record_count += 1;
        if let Some(timestamp) = payload.get("timestamp").and_then(|value| value.as_str()) {
            if metadata.first_timestamp.is_none() {
                metadata.first_timestamp = Some(timestamp.to_string());
            }
            metadata.last_timestamp = Some(timestamp.to_string());
        }
        if let Some(audit_id) = payload.get("audit_id").and_then(|value| value.as_str()) {
            if metadata.first_audit_id.is_none() {
                metadata.first_audit_id = Some(audit_id.to_string());
            }
            metadata.last_audit_id = Some(audit_id.to_string());
        }
    }
}

fn matches_request(entry: &AuditRecord, request: &AuditQueryRequest) -> bool {
    if let Some(user_id) = &request.user_id {
        if &entry.user_id != user_id {
            return false;
        }
    }
    if let Some(session_id) = &request.session_id {
        if &entry.session_id != session_id {
            return false;
        }
    }
    if let Some(task_id) = &request.task_id {
        if &entry.task_id != task_id {
            return false;
        }
    }
    if let Some(capability_id) = &request.capability_id {
        if &entry.capability_id != capability_id {
            return false;
        }
    }
    if let Some(decision) = &request.decision {
        if &entry.decision != decision {
            return false;
        }
    }
    if let Some(execution_location) = &request.execution_location {
        if &entry.execution_location != execution_location {
            return false;
        }
    }

    true
}

fn audit_query_from_export_request(request: &AuditExportRequest) -> AuditQueryRequest {
    AuditQueryRequest {
        user_id: request.user_id.clone(),
        session_id: request.session_id.clone(),
        task_id: request.task_id.clone(),
        capability_id: request.capability_id.clone(),
        decision: request.decision.clone(),
        execution_location: request.execution_location.clone(),
        limit: request.limit,
        reverse: request.reverse,
    }
}

fn audit_approval_ref(entry: &AuditRecord) -> Option<String> {
    entry
        .result
        .get("approval_ref")
        .and_then(Value::as_str)
        .map(str::to_string)
}
fn count_u32(len: usize) -> u32 {
    len.try_into().unwrap_or(u32::MAX)
}

fn segment_reference_time(segment: &AuditSegmentMetadata) -> Option<DateTime<Utc>> {
    [
        segment.last_timestamp.as_deref(),
        segment.rotated_at.as_deref(),
        Some(segment.created_at.as_str()),
    ]
    .into_iter()
    .flatten()
    .find_map(|value| {
        DateTime::parse_from_rfc3339(value)
            .ok()
            .map(|timestamp| timestamp.with_timezone(&Utc))
    })
}

fn remove_file_if_exists(path: &Path) -> anyhow::Result<()> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    fn store_config(
        root: &Path,
        rotate_after_bytes: u64,
        retention_days: u64,
        max_archives: usize,
    ) -> AuditStoreConfig {
        AuditStoreConfig {
            index_path: root.join("audit-index.json"),
            archive_dir: root.join("audit-archive"),
            rotate_after_bytes,
            retention_days,
            max_archives,
        }
    }

    #[test]
    fn query_filters_and_reverses_entries() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-audit-query-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("audit.jsonl");
        let writer = AuditWriter::new(path.clone(), None);

        writer.append_json(json!({
            "audit_id": "audit-1",
            "timestamp": "2026-03-09T00:00:00Z",
            "user_id": "u1",
            "session_id": "s1",
            "task_id": "t1",
            "capability_id": "shell.notification.open",
            "decision": "allowed",
            "execution_location": "local",
            "route_state": "direct",
            "taint_summary": null,
            "result": "ok"
        }))?;
        writer.append_json(json!({
            "audit_id": "audit-2",
            "timestamp": "2026-03-09T00:01:00Z",
            "user_id": "u1",
            "session_id": "s1",
            "task_id": "t2",
            "capability_id": "system.file.bulk_delete",
            "decision": "denied",
            "execution_location": "sandbox",
            "route_state": "high-risk",
            "taint_summary": "prompt-injection-suspected",
            "result": "blocked"
        }))?;

        let response = writer.query(&AuditQueryRequest {
            user_id: Some("u1".to_string()),
            decision: Some("denied".to_string()),
            limit: 10,
            reverse: true,
            ..AuditQueryRequest::default()
        })?;

        assert_eq!(response.entries.len(), 1);
        assert_eq!(response.entries[0].audit_id, "audit-2");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn approval_audit_entries_capture_pending_and_resolved_states() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-approval-audit-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("audit.jsonl");
        let writer = AuditWriter::new(path, None);
        let approval = ApprovalRecord {
            approval_ref: "apr-1".to_string(),
            user_id: "u1".to_string(),
            session_id: "s1".to_string(),
            task_id: "t1".to_string(),
            capability_id: "system.file.bulk_delete".to_string(),
            approval_lane: "high-risk-side-effect-review".to_string(),
            status: "approved".to_string(),
            execution_location: "local".to_string(),
            target_hash: Some("sha256:audit".to_string()),
            constraints: std::collections::BTreeMap::from([
                ("allow_directory_delete".to_string(), json!(true)),
                ("max_affected_paths".to_string(), json!(8)),
            ]),
            taint_summary: Some("high-risk".to_string()),
            reason: Some("requires approval".to_string()),
            created_at: "2026-03-13T00:00:00Z".to_string(),
            expires_at: Some("2026-03-13T00:15:00Z".to_string()),
            resolved_at: Some("2026-03-13T00:01:00Z".to_string()),
            resolver: Some("reviewer".to_string()),
            resolution_reason: Some("approved".to_string()),
        };

        writer.append_approval_created(&approval)?;
        writer.append_approval_resolved(&approval)?;

        let response = writer.query(&AuditQueryRequest {
            task_id: Some("t1".to_string()),
            limit: 10,
            reverse: true,
            ..AuditQueryRequest::default()
        })?;
        assert_eq!(response.entries.len(), 2);
        assert_eq!(response.entries[0].decision, "approval-approved");
        assert_eq!(response.entries[1].decision, "approval-pending");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn audit_writer_mirrors_schema_valid_records_to_observability_sink() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-audit-observability-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let audit_path = root.join("audit.jsonl");
        let observability_path = root.join("observability.jsonl");
        let sink = ObservabilitySink::new(observability_path.clone())?;
        let writer = AuditWriter::new(audit_path.clone(), Some(sink));

        writer.append_json(json!({
            "audit_id": "audit-1",
            "timestamp": "2026-03-09T00:00:00Z",
            "user_id": "u1",
            "session_id": "s1",
            "task_id": "t1",
            "approval_id": "apr-1",
            "capability_id": "system.file.bulk_delete",
            "decision": "approval-pending",
            "execution_location": "local",
            "taint_summary": null,
            "result": {"approval_ref": "apr-1"}
        }))?;

        let entry: Value = serde_json::from_str(
            fs::read_to_string(&observability_path)?
                .lines()
                .next()
                .expect("entry"),
        )?;
        assert_eq!(
            entry["schema_version"],
            CURRENT_OBSERVABILITY_SCHEMA_VERSION
        );
        assert_eq!(entry["artifact_path"], audit_path.display().to_string());
        assert_eq!(entry["decision"], "approval-pending");
        assert!(entry.get("taint_summary").is_none());

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn audit_store_rotates_and_queries_archived_segments() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-audit-rotation-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("audit.jsonl");
        let writer =
            AuditWriter::with_store_config(path.clone(), None, store_config(&root, 220, 30, 8));

        writer.append_json(json!({
            "audit_id": "audit-1",
            "timestamp": "2026-03-09T00:00:00Z",
            "user_id": "u1",
            "session_id": "s1",
            "task_id": "t1",
            "capability_id": "system.file.bulk_delete",
            "decision": "approval-pending",
            "execution_location": "local",
            "result": {"summary": "first record with enough content to trigger rotation"}
        }))?;
        writer.append_json(json!({
            "audit_id": "audit-2",
            "timestamp": "2026-03-09T00:01:00Z",
            "user_id": "u1",
            "session_id": "s1",
            "task_id": "t1",
            "capability_id": "system.file.bulk_delete",
            "decision": "approval-approved",
            "execution_location": "local",
            "result": {"summary": "second record should land in a fresh active segment"}
        }))?;

        assert_eq!(writer.archived_segment_count()?, 1);

        let index: Value = serde_json::from_str(&fs::read_to_string(writer.index_path())?)?;
        let archived_path = index["archived_segments"][0]["path"]
            .as_str()
            .expect("archived path");
        assert!(Path::new(archived_path).exists());

        let archived_entry: Value = serde_json::from_str(
            fs::read_to_string(archived_path)?
                .lines()
                .next()
                .expect("archived entry"),
        )?;
        assert_eq!(archived_entry["artifact_path"], archived_path);

        let response = writer.query(&AuditQueryRequest {
            session_id: Some("s1".to_string()),
            limit: 10,
            reverse: false,
            ..AuditQueryRequest::default()
        })?;
        assert_eq!(response.entries.len(), 2);
        assert_eq!(response.entries[0].audit_id, "audit-1");
        assert_eq!(response.entries[1].audit_id, "audit-2");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn audit_export_writes_bundle_file_with_store_metadata() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-audit-export-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("audit.jsonl");
        let writer =
            AuditWriter::with_store_config(path.clone(), None, store_config(&root, 0, 30, 4));

        writer.append_json(json!({
            "audit_id": "audit-export-1",
            "timestamp": "2026-03-09T00:00:00Z",
            "user_id": "u1",
            "session_id": "s1",
            "task_id": "t1",
            "capability_id": "system.file.bulk_delete",
            "decision": "approval-pending",
            "execution_location": "local",
            "result": {"summary": "export me", "approval_ref": "apr-export-1"}
        }))?;

        let export_dir = root.join("exports");
        let response = writer.export(
            "aios-policyd",
            &export_dir,
            &AuditExportRequest {
                user_id: None,
                session_id: Some("s1".to_string()),
                task_id: None,
                capability_id: None,
                decision: None,
                execution_location: None,
                limit: 10,
                reverse: true,
                reason: Some("operator-export".to_string()),
            },
        )?;

        assert!(Path::new(&response.export_path).exists());
        assert_eq!(response.entry_count, 1);
        assert_eq!(response.session_count, 1);
        assert_eq!(response.task_count, 1);
        assert_eq!(response.approval_ref_count, 1);
        assert_eq!(response.decision_count, 1);
        assert_eq!(response.session_count, 1);
        assert_eq!(response.task_count, 1);
        assert_eq!(response.approval_ref_count, 1);
        assert_eq!(response.decision_count, 1);
        assert_eq!(response.active_segment_path, path.display().to_string());
        let payload: Value = serde_json::from_str(&fs::read_to_string(&response.export_path)?)?;
        assert_eq!(payload["entries"][0]["audit_id"], "audit-export-1");
        assert_eq!(payload["reason"], "operator-export");
        assert_eq!(
            payload["audit_store"]["active_segment_path"],
            path.display().to_string()
        );

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn audit_store_retention_prunes_old_archives() -> anyhow::Result<()> {
        let root = std::env::temp_dir().join(format!(
            "aios-audit-retention-{}",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        fs::create_dir_all(&root)?;
        let path = root.join("audit.jsonl");
        let writer =
            AuditWriter::with_store_config(path.clone(), None, store_config(&root, 0, 0, 1));

        fs::create_dir_all(writer.archive_dir())?;
        let archived_one = writer.archive_dir().join("segment-1.jsonl");
        let archived_two = writer.archive_dir().join("segment-2.jsonl");
        fs::write(
            &archived_one,
            "{\"audit_id\":\"audit-1\",\"timestamp\":\"2026-03-08T00:00:00Z\",\"user_id\":\"u1\",\"session_id\":\"s1\",\"task_id\":\"t1\",\"capability_id\":\"system.file.bulk_delete\",\"decision\":\"approval-pending\",\"execution_location\":\"local\",\"result\":\"ok\"}\n",
        )?;
        fs::write(
            &archived_two,
            "{\"audit_id\":\"audit-2\",\"timestamp\":\"2026-03-09T00:00:00Z\",\"user_id\":\"u1\",\"session_id\":\"s1\",\"task_id\":\"t1\",\"capability_id\":\"system.file.bulk_delete\",\"decision\":\"approval-approved\",\"execution_location\":\"local\",\"result\":\"ok\"}\n",
        )?;

        let mut index = AuditStoreIndex {
            schema_version: CURRENT_OBSERVABILITY_SCHEMA_VERSION.to_string(),
            generated_at: "2026-03-10T00:00:00Z".to_string(),
            active_log: writer.path().display().to_string(),
            index_path: writer.index_path().display().to_string(),
            archive_dir: writer.archive_dir().display().to_string(),
            rotate_after_bytes: writer.rotate_after_bytes(),
            retention_days: writer.retention_days(),
            max_archives: writer.max_archives(),
            active_segment: AuditSegmentMetadata::empty(
                "active".to_string(),
                writer.path().to_path_buf(),
                "active",
                "2026-03-10T00:00:00Z".to_string(),
            ),
            archived_segments: vec![
                writer.scan_segment(
                    &archived_one,
                    "segment-1".to_string(),
                    "archived",
                    "2026-03-08T00:00:00Z".to_string(),
                    Some("2026-03-08T00:00:00Z".to_string()),
                )?,
                writer.scan_segment(
                    &archived_two,
                    "segment-2".to_string(),
                    "archived",
                    "2026-03-09T00:00:00Z".to_string(),
                    Some("2026-03-09T00:00:00Z".to_string()),
                )?,
            ],
        };

        writer.enforce_retention(&mut index)?;
        writer.save_index(&index)?;

        assert_eq!(index.archived_segments.len(), 1);
        assert!(!archived_one.exists());
        assert!(archived_two.exists());

        let _ = fs::remove_dir_all(root);
        Ok(())
    }
}
