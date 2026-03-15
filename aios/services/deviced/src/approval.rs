use std::time::Duration;

use aios_contracts::{
    methods, ApprovalListRequest, ApprovalListResponse, ApprovalRecord, DeviceCaptureRequest,
};

use crate::config::Config;

#[derive(Debug, Clone)]
pub struct ApprovalDecision {
    pub high_risk: bool,
    pub approval_required: bool,
    pub approved: bool,
    pub approval_status: String,
    pub approval_source: String,
    pub approval_ref: Option<String>,
    pub visible_indicator: bool,
    pub notes: Vec<String>,
}

pub fn evaluate(config: &Config, request: &DeviceCaptureRequest) -> ApprovalDecision {
    let high_risk = match request.modality.as_str() {
        "audio" | "camera" | "input" => true,
        "screen" => request.continuous || request.window_ref.is_none(),
        _ => request.continuous,
    };

    if config.approval_mode == "disabled" {
        return ApprovalDecision {
            high_risk,
            approval_required: false,
            approved: true,
            approval_status: "disabled".to_string(),
            approval_source: "policy-disabled".to_string(),
            approval_ref: None,
            visible_indicator: matches!(
                request.modality.as_str(),
                "screen" | "audio" | "camera" | "input"
            ),
            notes: vec!["approval enforcement disabled".to_string()],
        };
    }

    let approved_by_session = request
        .session_id
        .as_ref()
        .map(|session_id| {
            config
                .approved_sessions
                .iter()
                .any(|item| item == session_id)
        })
        .unwrap_or(false);
    let approved_by_task = request
        .task_id
        .as_ref()
        .map(|task_id| config.approved_tasks.iter().any(|item| item == task_id))
        .unwrap_or(false);
    let approval_required = high_risk;

    let mut approval_source = if approval_required {
        "unapproved".to_string()
    } else {
        "not-required".to_string()
    };
    let mut approval_ref = None;
    let mut approved_by_policyd = false;
    let mut notes = Vec::new();

    if high_risk {
        notes.push("capture classified as high-risk".to_string());
    }
    if approved_by_session {
        notes.push("approved via session allowlist".to_string());
        approval_source = "session-allowlist".to_string();
    }
    if approved_by_task {
        notes.push("approved via task allowlist".to_string());
        approval_source = "task-allowlist".to_string();
    }

    if approval_required && !approved_by_session && !approved_by_task {
        if request.session_id.is_none() && request.task_id.is_none() {
            notes.push("high-risk capture missing session/task context".to_string());
        } else if !config.policy_socket_path.exists() {
            notes.push(format!(
                "policyd_socket_unavailable={}",
                config.policy_socket_path.display()
            ));
        } else {
            match lookup_policyd_approval(config, request) {
                Ok(Some(record)) => {
                    approved_by_policyd = true;
                    approval_source = "policyd".to_string();
                    approval_ref = Some(record.approval_ref.clone());
                    notes.push(format!(
                        "approved via policyd approval_ref={}",
                        record.approval_ref
                    ));
                    notes.push(format!("approval_capability_id={}", record.capability_id));
                }
                Ok(None) => {
                    notes.push("no approved policyd approval matched capture context".to_string());
                }
                Err(error) => {
                    notes.push(format!("policyd_lookup_error={error}"));
                }
            }
        }
    }

    let approved =
        !approval_required || approved_by_session || approved_by_task || approved_by_policyd;
    let approval_status = if !approval_required {
        "not-required".to_string()
    } else if approved {
        "approved".to_string()
    } else if config.approval_mode == "enforced" {
        "denied".to_string()
    } else {
        "required".to_string()
    };

    ApprovalDecision {
        high_risk,
        approval_required,
        approved,
        approval_status,
        approval_source,
        approval_ref,
        visible_indicator: matches!(
            request.modality.as_str(),
            "screen" | "audio" | "camera" | "input"
        ),
        notes,
    }
}

fn lookup_policyd_approval(
    config: &Config,
    request: &DeviceCaptureRequest,
) -> anyhow::Result<Option<ApprovalRecord>> {
    let approvals = aios_rpc::call_unix_with_timeout::<ApprovalListRequest, ApprovalListResponse, _>(
        &config.policy_socket_path,
        methods::APPROVAL_LIST,
        &ApprovalListRequest {
            session_id: request.session_id.clone(),
            task_id: request.task_id.clone(),
            status: Some("approved".to_string()),
        },
        Duration::from_millis(config.approval_rpc_timeout_ms),
    )?;

    Ok(select_matching_approval(request, approvals.approvals))
}

fn select_matching_approval(
    request: &DeviceCaptureRequest,
    approvals: Vec<ApprovalRecord>,
) -> Option<ApprovalRecord> {
    approvals
        .into_iter()
        .filter(|record| approval_match_score(record, request) > 0)
        .max_by_key(|record| approval_match_score(record, request))
}

fn approval_match_score(record: &ApprovalRecord, request: &DeviceCaptureRequest) -> usize {
    if record.status != "approved" {
        return 0;
    }

    let exact_capability = capture_capability_id(request);
    let generic_capability = "device.capture";
    let device_capture_lane = "device-capture-review";

    let matches_device_capture = record.capability_id == exact_capability
        || record.capability_id == generic_capability
        || record.capability_id.contains(generic_capability)
        || record.approval_lane == device_capture_lane;
    if !matches_device_capture {
        return 0;
    }

    let mut score = 0;
    if record.task_id == request.task_id.clone().unwrap_or_default() {
        score += 4;
    }
    if record.session_id == request.session_id.clone().unwrap_or_default() {
        score += 2;
    }
    if record.capability_id == exact_capability {
        score += 8;
    } else if record.capability_id == generic_capability {
        score += 6;
    } else if record.capability_id.contains(generic_capability) {
        score += 3;
    }
    if record.approval_lane == device_capture_lane {
        score += 5;
    }
    score
}

fn capture_capability_id(request: &DeviceCaptureRequest) -> String {
    format!("device.capture.{}", request.modality)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn approval_record(
        approval_ref: &str,
        session_id: &str,
        task_id: &str,
        capability_id: &str,
        approval_lane: &str,
        status: &str,
    ) -> ApprovalRecord {
        ApprovalRecord {
            approval_ref: approval_ref.to_string(),
            user_id: "user-1".to_string(),
            session_id: session_id.to_string(),
            task_id: task_id.to_string(),
            capability_id: capability_id.to_string(),
            approval_lane: approval_lane.to_string(),
            status: status.to_string(),
            execution_location: "local".to_string(),
            target_hash: None,
            constraints: std::collections::BTreeMap::new(),
            taint_summary: None,
            reason: None,
            created_at: "2026-03-09T00:00:00Z".to_string(),
            expires_at: Some("2026-03-09T00:15:00Z".to_string()),
            resolved_at: Some("2026-03-09T00:01:00Z".to_string()),
            resolver: Some("tester".to_string()),
            resolution_reason: None,
        }
    }

    fn request(modality: &str) -> DeviceCaptureRequest {
        DeviceCaptureRequest {
            modality: modality.to_string(),
            session_id: Some("session-1".to_string()),
            task_id: Some("task-1".to_string()),
            continuous: true,
            window_ref: None,
            source_device: None,
        }
    }

    #[test]
    fn prefers_exact_capability_match() {
        let request = request("audio");
        let approvals = vec![
            approval_record(
                "apr-generic",
                "session-1",
                "task-1",
                "device.capture",
                "device-capture-review",
                "approved",
            ),
            approval_record(
                "apr-audio",
                "session-1",
                "task-1",
                "device.capture.audio",
                "device-capture-review",
                "approved",
            ),
        ];

        let selected = select_matching_approval(&request, approvals).expect("selected approval");
        assert_eq!(selected.approval_ref, "apr-audio");
    }

    #[test]
    fn accepts_device_capture_lane_with_broad_capability() {
        let request = request("screen");
        let approvals = vec![approval_record(
            "apr-lane",
            "session-1",
            "task-1",
            "policy.evaluate",
            "device-capture-review",
            "approved",
        )];

        let selected = select_matching_approval(&request, approvals).expect("selected approval");
        assert_eq!(selected.approval_ref, "apr-lane");
    }

    #[test]
    fn ignores_unrelated_approvals() {
        let request = request("input");
        let approvals = vec![approval_record(
            "apr-other",
            "session-1",
            "task-1",
            "system.file.delete",
            "high-risk-side-effect-review",
            "approved",
        )];

        assert!(select_matching_approval(&request, approvals).is_none());
    }
}
