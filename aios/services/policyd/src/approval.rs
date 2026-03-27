use std::{
    fs,
    path::{Path, PathBuf},
};

use anyhow::Context;
use chrono::{DateTime, Duration, Utc};
use serde_json::{json, Value};
use thiserror::Error;
use uuid::Uuid;

use aios_contracts::{
    ApprovalCreateRequest, ApprovalListRequest, ApprovalListResponse, ApprovalRecord,
    ApprovalResolveRequest, PolicyEvaluateRequest, TokenIssueRequest,
};

use crate::catalog::CapabilityCatalog;

#[derive(Clone)]
pub struct ApprovalStore {
    state_dir: PathBuf,
    default_ttl_seconds: u64,
}

#[derive(Debug, Error)]
pub enum ApprovalResolveError {
    #[error("unsupported approval resolution status: {status}")]
    UnsupportedStatus { status: String },
    #[error("approval {approval_ref} cannot transition from {current} to {next}")]
    InvalidTransition {
        approval_ref: String,
        current: String,
        next: String,
    },
    #[error(transparent)]
    Storage(#[from] anyhow::Error),
}

#[derive(Debug, Error)]
pub enum ApprovalScopeError {
    #[error("approval {approval_ref} context mismatch on {field}: approved={approved}, requested={requested}")]
    ContextMismatch {
        approval_ref: String,
        field: &'static str,
        approved: String,
        requested: String,
    },
    #[error(
        "approval {approval_ref} target_hash mismatch: approved={approved:?}, requested={requested:?}"
    )]
    TargetHashMismatch {
        approval_ref: String,
        approved: Option<String>,
        requested: Option<String>,
    },
    #[error("approval {approval_ref} is missing approved constraint {key}")]
    ConstraintMissing {
        approval_ref: String,
        key: String,
        approved: Value,
    },
    #[error("approval {approval_ref} does not approve constraint {key}")]
    ConstraintNotApproved {
        approval_ref: String,
        key: String,
        requested: Value,
    },
    #[error("approval {approval_ref} constraint {key} exceeds approved scope")]
    ConstraintValueMismatch {
        approval_ref: String,
        key: String,
        approved: Value,
        requested: Value,
    },
}

impl ApprovalScopeError {
    pub fn error_code(&self) -> &'static str {
        match self {
            Self::ContextMismatch { .. } => "approval_context_mismatch",
            Self::TargetHashMismatch { .. } => "approval_target_mismatch",
            Self::ConstraintMissing { .. }
            | Self::ConstraintNotApproved { .. }
            | Self::ConstraintValueMismatch { .. } => "approval_constraints_mismatch",
        }
    }

    pub fn audit_payload(&self) -> Value {
        match self {
            Self::ContextMismatch {
                field,
                approved,
                requested,
                ..
            } => json!({
                "mismatch_type": "context",
                "field": field,
                "approved": approved,
                "requested": requested,
            }),
            Self::TargetHashMismatch {
                approved,
                requested,
                ..
            } => json!({
                "mismatch_type": "target_hash",
                "approved_target_hash": approved,
                "requested_target_hash": requested,
            }),
            Self::ConstraintMissing { key, approved, .. } => json!({
                "mismatch_type": "constraints",
                "field": key,
                "approved_constraint": approved,
                "requested_constraint": Value::Null,
                "reason": "approved constraint missing from token request",
            }),
            Self::ConstraintNotApproved { key, requested, .. } => json!({
                "mismatch_type": "constraints",
                "field": key,
                "approved_constraint": Value::Null,
                "requested_constraint": requested,
                "reason": "token requested a constraint that approval did not bind",
            }),
            Self::ConstraintValueMismatch {
                key,
                approved,
                requested,
                ..
            } => json!({
                "mismatch_type": "constraints",
                "field": key,
                "approved_constraint": approved,
                "requested_constraint": requested,
                "reason": "token constraint exceeds approved scope",
            }),
        }
    }
}

impl ApprovalStore {
    pub fn new(root: PathBuf, default_ttl_seconds: u64) -> anyhow::Result<Self> {
        let state_dir = root.join("approvals");
        fs::create_dir_all(&state_dir).with_context(|| {
            format!(
                "failed to create approval state dir {}",
                state_dir.display()
            )
        })?;
        Ok(Self {
            state_dir,
            default_ttl_seconds,
        })
    }

    pub fn state_dir(&self) -> &Path {
        &self.state_dir
    }

    pub fn create(&self, request: &ApprovalCreateRequest) -> anyhow::Result<ApprovalRecord> {
        let created_at = Utc::now();
        let ttl_seconds = request
            .expires_in_seconds
            .unwrap_or(self.default_ttl_seconds);
        let record = ApprovalRecord {
            approval_ref: format!("apr-{}", Uuid::new_v4()),
            user_id: request.user_id.clone(),
            session_id: request.session_id.clone(),
            task_id: request.task_id.clone(),
            capability_id: request.capability_id.clone(),
            approval_lane: request.approval_lane.clone(),
            status: "pending".to_string(),
            execution_location: request.execution_location.clone(),
            target_hash: request.target_hash.clone(),
            constraints: request.constraints.clone(),
            taint_summary: request.taint_summary.clone(),
            reason: request.reason.clone(),
            created_at: created_at.to_rfc3339(),
            expires_at: expiry_timestamp(created_at, ttl_seconds),
            resolved_at: None,
            resolver: None,
            resolution_reason: None,
        };
        self.save(&record)?;
        Ok(record)
    }

    pub fn get(&self, approval_ref: &str) -> anyhow::Result<Option<ApprovalRecord>> {
        let path = self.record_path(approval_ref);
        if !path.exists() {
            return Ok(None);
        }
        Ok(Some(self.load_current(&path)?))
    }

    pub fn list(&self, request: &ApprovalListRequest) -> anyhow::Result<ApprovalListResponse> {
        let mut approvals = Vec::new();
        for entry in fs::read_dir(&self.state_dir)
            .with_context(|| format!("failed to read approval dir {}", self.state_dir.display()))?
        {
            let path = entry?.path();
            if path.extension().and_then(|item| item.to_str()) != Some("json") {
                continue;
            }

            let record = self.load_current(&path)?;
            if let Some(item) = &request.session_id {
                if item != &record.session_id {
                    continue;
                }
            }
            if let Some(item) = &request.task_id {
                if item != &record.task_id {
                    continue;
                }
            }
            if let Some(item) = &request.status {
                if item != &record.status {
                    continue;
                }
            }
            approvals.push(record);
        }

        approvals.sort_by(|left, right| right.created_at.cmp(&left.created_at));
        Ok(ApprovalListResponse { approvals })
    }

    pub fn resolve(
        &self,
        request: &ApprovalResolveRequest,
    ) -> Result<Option<ApprovalRecord>, ApprovalResolveError> {
        validate_resolution_status(&request.status)?;
        let Some(mut record) = self.get(&request.approval_ref)? else {
            return Ok(None);
        };
        assert_resolution_transition(&record.status, &request.status, &record.approval_ref)?;

        record.status = request.status.clone();
        record.resolver = Some(request.resolver.clone());
        record.resolved_at = Some(Utc::now().to_rfc3339());
        record.resolution_reason = request.reason.clone();
        self.save(&record)?;
        Ok(Some(record))
    }

    pub fn pending_count(&self) -> anyhow::Result<usize> {
        Ok(self
            .list(&ApprovalListRequest {
                session_id: None,
                task_id: None,
                status: Some("pending".to_string()),
            })?
            .approvals
            .len())
    }

    pub fn find_session_trust_approval(
        &self,
        request: &PolicyEvaluateRequest,
    ) -> anyhow::Result<Option<ApprovalRecord>> {
        let approvals = self.list(&ApprovalListRequest {
            session_id: Some(request.session_id.clone()),
            task_id: None,
            status: Some("approved".to_string()),
        })?;

        Ok(approvals
            .approvals
            .into_iter()
            .find(|approval| approval_matches_policy_request(approval, request)))
    }

    fn record_path(&self, approval_ref: &str) -> PathBuf {
        self.state_dir.join(format!("{approval_ref}.json"))
    }

    fn load_current(&self, path: &Path) -> anyhow::Result<ApprovalRecord> {
        let mut record = self.load(path)?;
        if expire_if_needed(&mut record)? {
            self.save(&record)?;
        }
        Ok(record)
    }

    fn load(&self, path: &Path) -> anyhow::Result<ApprovalRecord> {
        let text = fs::read_to_string(path)
            .with_context(|| format!("failed to read approval record {}", path.display()))?;
        serde_json::from_str(&text)
            .with_context(|| format!("failed to decode approval record {}", path.display()))
    }

    fn save(&self, record: &ApprovalRecord) -> anyhow::Result<()> {
        let path = self.record_path(&record.approval_ref);
        let text = serde_json::to_string_pretty(record)?;
        fs::write(&path, text)
            .with_context(|| format!("failed to persist approval record {}", path.display()))
    }
}

pub fn approval_lane(
    request: &PolicyEvaluateRequest,
    catalog: &CapabilityCatalog,
    approval_default_policy: &str,
) -> String {
    let metadata = catalog.get(&request.capability_id);
    let configured_lane = metadata
        .map(|item| item.default_approval_lane.as_str())
        .filter(|lane| !lane.is_empty());

    if request.execution_location == "attested_remote" {
        return "remote-execution-review".to_string();
    }

    if request.capability_id.contains("device.capture")
        || configured_lane == Some("device-capture-review")
    {
        return "device-capture-review".to_string();
    }

    let is_high_risk = metadata
        .is_some_and(|item| item.high_risk() || item.destructive || item.approval_required)
        || request.capability_id.contains("delete")
        || request.capability_id.contains("inject");

    if is_high_risk {
        return match approval_default_policy {
            "operator-gate" => "operator-gate-review".to_string(),
            "session-trust" => "session-trust-review".to_string(),
            _ => "high-risk-side-effect-review".to_string(),
        };
    }

    configured_lane
        .unwrap_or("standard-capability-review")
        .to_string()
}

pub fn ensure_token_request_scope(
    approval: &ApprovalRecord,
    request: &TokenIssueRequest,
) -> Result<(), ApprovalScopeError> {
    match_context_field(
        approval,
        "user_id",
        approval.user_id.as_str(),
        request.user_id.as_str(),
    )?;
    match_context_field(
        approval,
        "session_id",
        approval.session_id.as_str(),
        request.session_id.as_str(),
    )?;
    match_context_field(
        approval,
        "task_id",
        approval.task_id.as_str(),
        request.task_id.as_str(),
    )?;
    match_context_field(
        approval,
        "capability_id",
        approval.capability_id.as_str(),
        request.capability_id.as_str(),
    )?;
    match_context_field(
        approval,
        "execution_location",
        approval.execution_location.as_str(),
        request.execution_location.as_str(),
    )?;

    if approval.target_hash != request.target_hash {
        return Err(ApprovalScopeError::TargetHashMismatch {
            approval_ref: approval.approval_ref.clone(),
            approved: approval.target_hash.clone(),
            requested: request.target_hash.clone(),
        });
    }

    for (key, approved_value) in &approval.constraints {
        let Some(requested_value) = request.constraints.get(key) else {
            return Err(ApprovalScopeError::ConstraintMissing {
                approval_ref: approval.approval_ref.clone(),
                key: key.clone(),
                approved: approved_value.clone(),
            });
        };
        if !constraint_within_scope(approved_value, requested_value) {
            return Err(ApprovalScopeError::ConstraintValueMismatch {
                approval_ref: approval.approval_ref.clone(),
                key: key.clone(),
                approved: approved_value.clone(),
                requested: requested_value.clone(),
            });
        }
    }

    for (key, requested_value) in &request.constraints {
        if approval.constraints.contains_key(key) {
            continue;
        }
        return Err(ApprovalScopeError::ConstraintNotApproved {
            approval_ref: approval.approval_ref.clone(),
            key: key.clone(),
            requested: requested_value.clone(),
        });
    }

    Ok(())
}

fn match_context_field(
    approval: &ApprovalRecord,
    field: &'static str,
    approved: &str,
    requested: &str,
) -> Result<(), ApprovalScopeError> {
    if approved == requested {
        return Ok(());
    }

    Err(ApprovalScopeError::ContextMismatch {
        approval_ref: approval.approval_ref.clone(),
        field,
        approved: approved.to_string(),
        requested: requested.to_string(),
    })
}

fn approval_matches_policy_request(
    approval: &ApprovalRecord,
    request: &PolicyEvaluateRequest,
) -> bool {
    if approval.status != "approved"
        || approval.user_id != request.user_id
        || approval.session_id != request.session_id
        || approval.capability_id != request.capability_id
        || approval.execution_location != request.execution_location
        || approval.target_hash != request.target_hash
    {
        return false;
    }

    for (key, approved_value) in &approval.constraints {
        let Some(requested_value) = request.constraints.get(key) else {
            return false;
        };
        if !constraint_within_scope(approved_value, requested_value) {
            return false;
        }
    }

    request
        .constraints
        .keys()
        .all(|key| approval.constraints.contains_key(key))
}

fn constraint_within_scope(approved: &Value, requested: &Value) -> bool {
    match (approved, requested) {
        (Value::Number(approved), Value::Number(requested)) => {
            match (approved.as_f64(), requested.as_f64()) {
                (Some(approved), Some(requested)) => requested <= approved,
                _ => false,
            }
        }
        _ => approved == requested,
    }
}

fn expiry_timestamp(created_at: DateTime<Utc>, ttl_seconds: u64) -> Option<String> {
    Some((created_at + Duration::seconds(ttl_seconds as i64)).to_rfc3339())
}

fn expire_if_needed(record: &mut ApprovalRecord) -> anyhow::Result<bool> {
    if record.status != "pending" {
        return Ok(false);
    }

    let Some(expires_at) = record.expires_at.as_deref() else {
        return Ok(false);
    };
    let expires_at = DateTime::parse_from_rfc3339(expires_at)
        .with_context(|| {
            format!(
                "failed to parse approval expiry for {}",
                record.approval_ref
            )
        })?
        .with_timezone(&Utc);
    if expires_at > Utc::now() {
        return Ok(false);
    }

    record.status = "timed-out".to_string();
    record.resolved_at = Some(expires_at.to_rfc3339());
    record.resolver = Some("system-timeout".to_string());
    if record.resolution_reason.is_none() {
        record.resolution_reason = Some("approval expired before resolution".to_string());
    }
    Ok(true)
}

fn validate_resolution_status(status: &str) -> Result<(), ApprovalResolveError> {
    if matches!(status, "approved" | "rejected" | "revoked") {
        return Ok(());
    }

    Err(ApprovalResolveError::UnsupportedStatus {
        status: status.to_string(),
    })
}

fn assert_resolution_transition(
    current: &str,
    next: &str,
    approval_ref: &str,
) -> Result<(), ApprovalResolveError> {
    let allowed = matches!(
        (current, next),
        ("pending", "approved" | "rejected" | "revoked") | ("approved", "revoked")
    );
    if allowed {
        return Ok(());
    }

    Err(ApprovalResolveError::InvalidTransition {
        approval_ref: approval_ref.to_string(),
        current: current.to_string(),
        next: next.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;

    struct TempDir {
        path: PathBuf,
    }

    impl TempDir {
        fn new() -> anyhow::Result<Self> {
            let path = std::env::temp_dir().join(format!(
                "aios-approval-store-test-{}",
                Uuid::new_v4().simple()
            ));
            fs::create_dir_all(&path)?;
            Ok(Self { path })
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn store(default_ttl_seconds: u64) -> anyhow::Result<(ApprovalStore, TempDir)> {
        let temp = TempDir::new()?;
        Ok((
            ApprovalStore::new(temp.path.clone(), default_ttl_seconds)?,
            temp,
        ))
    }

    fn create_request() -> ApprovalCreateRequest {
        ApprovalCreateRequest {
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: "system.file.bulk_delete".to_string(),
            approval_lane: "high-risk-side-effect-review".to_string(),
            execution_location: "local".to_string(),
            target_hash: Some("sha256:approval-target".to_string()),
            constraints: BTreeMap::from([
                ("allow_directory_delete".to_string(), json!(true)),
                ("allow_recursive".to_string(), json!(true)),
                ("max_affected_paths".to_string(), json!(8)),
            ]),
            taint_summary: Some("high-risk".to_string()),
            reason: Some("requires approval".to_string()),
            expires_in_seconds: None,
        }
    }

    #[test]
    fn create_uses_default_ttl_when_not_overridden() -> anyhow::Result<()> {
        let (store, _temp) = store(900)?;
        let record = store.create(&create_request())?;

        assert_eq!(record.status, "pending");
        assert!(record.expires_at.is_some());
        assert!(record.resolution_reason.is_none());
        Ok(())
    }

    #[test]
    fn get_marks_expired_pending_approvals_as_timed_out() -> anyhow::Result<()> {
        let (store, _temp) = store(1)?;
        let mut request = create_request();
        request.expires_in_seconds = Some(0);

        let created = store.create(&request)?;
        let loaded = store
            .get(&created.approval_ref)?
            .expect("approval should exist");

        assert_eq!(loaded.status, "timed-out");
        assert_eq!(loaded.resolver.as_deref(), Some("system-timeout"));
        assert_eq!(
            loaded.resolution_reason.as_deref(),
            Some("approval expired before resolution")
        );
        Ok(())
    }

    #[test]
    fn approved_approvals_can_be_revoked() -> anyhow::Result<()> {
        let (store, _temp) = store(900)?;
        let created = store.create(&create_request())?;

        let approved = store
            .resolve(&ApprovalResolveRequest {
                approval_ref: created.approval_ref.clone(),
                status: "approved".to_string(),
                resolver: "reviewer-1".to_string(),
                reason: Some("looks safe".to_string()),
            })?
            .expect("approval should resolve");
        assert_eq!(approved.status, "approved");
        assert_eq!(approved.resolution_reason.as_deref(), Some("looks safe"));

        let revoked = store
            .resolve(&ApprovalResolveRequest {
                approval_ref: created.approval_ref,
                status: "revoked".to_string(),
                resolver: "reviewer-2".to_string(),
                reason: Some("context changed".to_string()),
            })?
            .expect("approval should revoke");
        assert_eq!(revoked.status, "revoked");
        assert_eq!(revoked.resolver.as_deref(), Some("reviewer-2"));
        assert_eq!(
            revoked.resolution_reason.as_deref(),
            Some("context changed")
        );
        Ok(())
    }

    #[test]
    fn invalid_resolution_status_returns_typed_error() -> anyhow::Result<()> {
        let (store, _temp) = store(900)?;
        let created = store.create(&create_request())?;

        let error = store
            .resolve(&ApprovalResolveRequest {
                approval_ref: created.approval_ref,
                status: "timed-out".to_string(),
                resolver: "reviewer-1".to_string(),
                reason: None,
            })
            .expect_err("unsupported status should fail");

        assert!(matches!(
            error,
            ApprovalResolveError::UnsupportedStatus { .. }
        ));
        Ok(())
    }

    #[test]
    fn rejected_approvals_cannot_transition_back_to_approved() -> anyhow::Result<()> {
        let (store, _temp) = store(900)?;
        let created = store.create(&create_request())?;

        let rejected = store
            .resolve(&ApprovalResolveRequest {
                approval_ref: created.approval_ref.clone(),
                status: "rejected".to_string(),
                resolver: "reviewer-1".to_string(),
                reason: Some("unsafe".to_string()),
            })?
            .expect("approval should reject");
        assert_eq!(rejected.status, "rejected");

        let error = store
            .resolve(&ApprovalResolveRequest {
                approval_ref: created.approval_ref,
                status: "approved".to_string(),
                resolver: "reviewer-2".to_string(),
                reason: Some("retry".to_string()),
            })
            .expect_err("rejected approval should not re-approve");

        assert!(matches!(
            error,
            ApprovalResolveError::InvalidTransition { .. }
        ));
        Ok(())
    }

    #[test]
    fn token_scope_enforces_target_hash_and_constraint_bounds() {
        let approval = ApprovalRecord {
            approval_ref: "apr-scope".to_string(),
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: "system.file.bulk_delete".to_string(),
            approval_lane: "high-risk-side-effect-review".to_string(),
            status: "approved".to_string(),
            execution_location: "local".to_string(),
            target_hash: Some("sha256:approval-target".to_string()),
            constraints: BTreeMap::from([
                ("allow_directory_delete".to_string(), json!(true)),
                ("allow_recursive".to_string(), json!(true)),
                ("max_affected_paths".to_string(), json!(8)),
            ]),
            taint_summary: None,
            reason: Some("scoped approval".to_string()),
            created_at: "2026-03-14T00:00:00Z".to_string(),
            expires_at: Some("2026-03-14T00:15:00Z".to_string()),
            resolved_at: Some("2026-03-14T00:01:00Z".to_string()),
            resolver: Some("reviewer-1".to_string()),
            resolution_reason: Some("approved".to_string()),
        };

        let narrowed = TokenIssueRequest {
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: "system.file.bulk_delete".to_string(),
            target_hash: Some("sha256:approval-target".to_string()),
            approval_ref: Some("apr-scope".to_string()),
            constraints: BTreeMap::from([
                ("allow_directory_delete".to_string(), json!(true)),
                ("allow_recursive".to_string(), json!(true)),
                ("max_affected_paths".to_string(), json!(4)),
            ]),
            execution_location: "local".to_string(),
            taint_summary: None,
        };
        assert!(ensure_token_request_scope(&approval, &narrowed).is_ok());

        let missing_constraint = TokenIssueRequest {
            constraints: BTreeMap::from([
                ("allow_directory_delete".to_string(), json!(true)),
                ("max_affected_paths".to_string(), json!(4)),
            ]),
            ..narrowed.clone()
        };
        assert!(matches!(
            ensure_token_request_scope(&approval, &missing_constraint),
            Err(ApprovalScopeError::ConstraintMissing { .. })
        ));

        let broader_constraint = TokenIssueRequest {
            constraints: BTreeMap::from([
                ("allow_directory_delete".to_string(), json!(true)),
                ("allow_recursive".to_string(), json!(true)),
                ("max_affected_paths".to_string(), json!(16)),
            ]),
            ..narrowed.clone()
        };
        assert!(matches!(
            ensure_token_request_scope(&approval, &broader_constraint),
            Err(ApprovalScopeError::ConstraintValueMismatch { .. })
        ));

        let extra_constraint = TokenIssueRequest {
            constraints: BTreeMap::from([
                ("allow_directory_delete".to_string(), json!(true)),
                ("allow_recursive".to_string(), json!(true)),
                ("max_affected_paths".to_string(), json!(4)),
                ("delete_mode".to_string(), json!("force")),
            ]),
            ..narrowed.clone()
        };
        assert!(matches!(
            ensure_token_request_scope(&approval, &extra_constraint),
            Err(ApprovalScopeError::ConstraintNotApproved { .. })
        ));

        let wrong_target = TokenIssueRequest {
            target_hash: Some("sha256:other".to_string()),
            ..narrowed
        };
        assert!(matches!(
            ensure_token_request_scope(&approval, &wrong_target),
            Err(ApprovalScopeError::TargetHashMismatch { .. })
        ));
    }
}
