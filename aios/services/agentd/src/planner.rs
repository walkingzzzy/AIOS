use aios_contracts::{methods, AgentPlan, AgentPlanStep};

#[cfg(test)]
use aios_contracts::{AgentIntentSubmitRequest, AgentPlanRequest};
#[cfg(test)]
use uuid::Uuid;

#[cfg(test)]
pub fn plan_intent(request: AgentIntentSubmitRequest) -> AgentPlan {
    let session_id = request
        .session_id
        .unwrap_or_else(|| format!("unbound-{}", request.user_id));

    build_plan(session_id, Uuid::new_v4().to_string(), request.intent)
}

#[cfg(test)]
pub fn plan_task(request: AgentPlanRequest) -> AgentPlan {
    build_plan(
        request.session_id,
        Uuid::new_v4().to_string(),
        request.intent,
    )
}

pub fn plan_for_task(session_id: String, task_id: String, intent: String) -> AgentPlan {
    build_plan(session_id, task_id, intent)
}

fn build_plan(session_id: String, task_id: String, intent: String) -> AgentPlan {
    let candidate_capabilities = crate::resolver::candidate_capabilities(&intent);
    let route_preference = crate::topology::choose(&intent);
    let next_action = aios_core::intent::next_action(&candidate_capabilities);
    let fallback_action = crate::recovery::fallback_action(&intent);
    let steps = build_steps(&intent, &candidate_capabilities, &fallback_action);

    AgentPlan {
        task_id,
        session_id,
        summary: summarize(&intent),
        route_preference,
        candidate_capabilities,
        next_action,
        steps,
    }
}

fn build_steps(
    intent: &str,
    candidate_capabilities: &[String],
    next_action: &str,
) -> Vec<AgentPlanStep> {
    let skip_provider_fs_open = candidate_capabilities
        .iter()
        .any(|item| item == "compat.document.open");
    let mut indexed = candidate_capabilities
        .iter()
        .enumerate()
        .filter(|(_, capability_id)| {
            !(skip_provider_fs_open && capability_id.as_str() == "provider.fs.open")
        })
        .collect::<Vec<_>>();
    indexed.sort_by_key(|(index, capability_id)| (step_priority(capability_id), *index));

    indexed
        .into_iter()
        .enumerate()
        .map(|(order, (_, capability_id))| {
            build_step(intent, capability_id, order == 0, next_action)
        })
        .collect()
}
fn build_step(
    intent: &str,
    capability_id: &str,
    is_first: bool,
    next_action: &str,
) -> AgentPlanStep {
    let portal_kind = crate::portal::requested_handle_kind(intent, capability_id);
    let requires_portal_handle = portal_kind.is_some();
    let requires_approval = matches!(
        capability_id,
        methods::SYSTEM_FILE_BULK_DELETE | "device.capture.screen.read" | "compat.code.execute"
    );

    AgentPlanStep {
        step: step_label(capability_id),
        capability_id: capability_id.to_string(),
        status: if is_first {
            "ready".to_string()
        } else {
            "planned".to_string()
        },
        provider_kind: crate::providers::preferred_kind_for_capability(capability_id),
        execution_location: crate::providers::preferred_execution_location(capability_id),
        requires_approval,
        requires_portal_handle,
        portal_kind,
        recovery_action: Some(step_recovery_action(
            capability_id,
            requires_approval,
            requires_portal_handle,
            next_action,
        )),
    }
}

fn step_priority(capability_id: &str) -> u8 {
    match capability_id {
        "provider.fs.open" => 10,
        "compat.document.open" => 20,
        "compat.browser.navigate" => 30,
        "compat.browser.extract" => 40,
        methods::RUNTIME_INFER_SUBMIT => 50,
        methods::SYSTEM_INTENT_EXECUTE => 60,
        "shell.notification.open" => 70,
        methods::SHELL_PANEL_EVENTS_LIST => 72,
        "shell.operator-audit.open" => 74,
        "shell.window.focus" => 76,
        "compat.office.export_pdf" => 80,
        "device.capture.screen.read" => 90,
        "compat.code.execute" => 95,
        methods::SYSTEM_FILE_BULK_DELETE => 100,
        _ => 110,
    }
}

fn step_label(capability_id: &str) -> String {
    match capability_id {
        "provider.fs.open" => "inspect-bound-target".to_string(),
        methods::RUNTIME_INFER_SUBMIT => "invoke-runtime-preview".to_string(),
        methods::SYSTEM_FILE_BULK_DELETE => "execute-approved-delete".to_string(),
        methods::SYSTEM_INTENT_EXECUTE => "refine-local-intent".to_string(),
        "compat.document.open" => "open-compat-document".to_string(),
        "compat.office.export_pdf" => "export-document-target".to_string(),
        "compat.browser.navigate" => "open-browser-target".to_string(),
        "compat.browser.extract" => "extract-browser-content".to_string(),
        "shell.notification.open" => "open-notification-surface".to_string(),
        methods::SHELL_PANEL_EVENTS_LIST => "inspect-shell-panel-events".to_string(),
        "shell.operator-audit.open" => "open-operator-audit".to_string(),
        "shell.window.focus" => "focus-shell-window".to_string(),
        "device.capture.screen.read" => "capture-screen-context".to_string(),
        "compat.code.execute" => "execute-compat-code".to_string(),
        _ => capability_id.replace('.', "-"),
    }
}

fn step_recovery_action(
    capability_id: &str,
    requires_approval: bool,
    requires_portal_handle: bool,
    next_action: &str,
) -> String {
    if requires_approval {
        return "wait-for-approval".to_string();
    }
    if requires_portal_handle {
        return "reuse-portal-handle".to_string();
    }
    if capability_id == methods::RUNTIME_INFER_SUBMIT {
        return "reuse-runtime-route".to_string();
    }

    next_action.to_string()
}

fn summarize(intent: &str) -> String {
    let trimmed = intent.trim();

    if trimmed.len() <= 96 {
        return trimmed.to_string();
    }

    format!("{}...", &trimmed[..96])
}

#[cfg(test)]
mod tests {
    use aios_contracts::{AgentIntentSubmitRequest, AgentPlanRequest};

    use super::*;

    #[test]
    fn plan_intent_uses_unbound_session_when_missing() {
        let plan = plan_intent(AgentIntentSubmitRequest {
            user_id: "tester".to_string(),
            session_id: None,
            intent: "Summarize this plan locally".to_string(),
        });

        assert_eq!(plan.session_id, "unbound-tester");
        assert!(plan.task_id.len() > 8);
        assert!(plan
            .candidate_capabilities
            .iter()
            .any(|item| item == "runtime.infer.submit"));
        assert_eq!(plan.steps.len(), 1);
        assert_eq!(plan.steps[0].status, "ready");
    }

    #[test]
    fn plan_task_preserves_session_and_truncates_summary() {
        let intent = "A".repeat(140);
        let plan = plan_task(AgentPlanRequest {
            session_id: "session-1".to_string(),
            intent,
        });

        assert_eq!(plan.session_id, "session-1");
        assert!(plan.summary.ends_with("..."));
        assert!(plan.summary.len() <= 99);
    }

    #[test]
    fn plan_for_task_keeps_explicit_task_id() {
        let plan = plan_for_task(
            "session-2".to_string(),
            "task-42".to_string(),
            "Open /tmp/report.txt and summarize it".to_string(),
        );

        assert_eq!(plan.task_id, "task-42");
        assert_eq!(plan.route_preference, "tool-calling");
        assert_eq!(plan.next_action, "inspect-bound-target");
        assert_eq!(plan.steps[0].capability_id, "provider.fs.open");
        assert_eq!(plan.steps[1].capability_id, "runtime.infer.submit");
        assert!(plan.steps[0].requires_portal_handle);
    }

    #[test]
    fn multi_step_plan_prioritizes_low_risk_read_before_delete() {
        let plan = plan_for_task(
            "session-3".to_string(),
            "task-99".to_string(),
            "Open /tmp/report.txt, summarize it, then delete it".to_string(),
        );

        let ordered = plan
            .steps
            .iter()
            .map(|step| step.capability_id.as_str())
            .collect::<Vec<_>>();
        assert_eq!(
            ordered,
            vec![
                "provider.fs.open",
                "runtime.infer.submit",
                "system.file.bulk_delete",
            ]
        );
        assert!(plan.steps[2].requires_approval);
        assert_eq!(plan.next_action, "request-destructive-approval");
        assert_eq!(
            plan.steps[0].recovery_action.as_deref(),
            Some("reuse-portal-handle")
        );
    }

    #[test]
    fn export_plan_opens_document_before_export_target() {
        let plan = plan_for_task(
            "session-4".to_string(),
            "task-100".to_string(),
            "Export /tmp/report.docx to /tmp/report.pdf".to_string(),
        );

        let ordered = plan
            .steps
            .iter()
            .map(|step| step.capability_id.as_str())
            .collect::<Vec<_>>();
        assert_eq!(
            ordered,
            vec!["compat.document.open", "compat.office.export_pdf"]
        );
        assert_eq!(plan.next_action, "export-document-target");
        assert_eq!(
            plan.steps[1].portal_kind.as_deref(),
            Some("export_target_handle")
        );
    }
}
