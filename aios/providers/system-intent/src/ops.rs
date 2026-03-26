use aios_contracts::{
    methods, AgentPlan, AgentPlanStep, SystemIntentAction, SystemIntentRequest,
    SystemIntentResponse, TaskRecord,
};

use crate::AppState;

pub fn execute_intent(
    state: &AppState,
    request: &SystemIntentRequest,
) -> anyhow::Result<SystemIntentResponse> {
    let _permit = state
        .concurrency_budget
        .try_acquire(methods::SYSTEM_INTENT_EXECUTE)?;
    let intent = request.intent.trim();
    if intent.is_empty() {
        anyhow::bail!("intent cannot be empty");
    }

    ensure_token_context(&request.execution_token)?;
    let verification = crate::clients::verify_token(state, &request.execution_token)?;
    if !verification.valid {
        anyhow::bail!("execution token rejected: {}", verification.reason);
    }

    let task = crate::clients::fetch_task(state, &request.execution_token.task_id)?;
    if task.session_id != request.execution_token.session_id {
        anyhow::bail!(
            "task session {} does not match token session {}",
            task.session_id,
            request.execution_token.session_id
        );
    }

    let (plan_source, plan, mut notes) = match crate::clients::fetch_task_plan(state, &task.task_id)
    {
        Ok(Some(plan)) => (
            "sessiond.task.plan".to_string(),
            normalize_plan(plan, intent),
            vec![],
        ),
        Ok(None) => (
            "provider-heuristic".to_string(),
            heuristic_plan(&task, intent),
            vec!["plan_fallback=missing-task-plan".to_string()],
        ),
        Err(error) => (
            "provider-heuristic".to_string(),
            heuristic_plan(&task, intent),
            vec![format!("plan_fallback_error={}", error)],
        ),
    };

    let actions = build_actions(&plan.candidate_capabilities);
    let requires_handoff = actions
        .iter()
        .any(|action| action.requires_approval || action.kind == "manual-review");
    let status = if task.state == "rejected" {
        "rejected"
    } else if requires_handoff {
        "manual-review"
    } else {
        "planned"
    }
    .to_string();

    notes.push(format!("task_state={}", task.state));
    notes.push(format!(
        "candidate_count={}",
        plan.candidate_capabilities.len()
    ));
    notes.push(format!(
        "provider_in_flight={}",
        state.concurrency_budget.in_flight()
    ));
    if let Some(title) = task.title.as_deref() {
        notes.push(format!("task_title={title}"));
    }
    if let Some(taint_summary) = request.execution_token.taint_summary.as_deref() {
        notes.push(format!("token_taint={taint_summary}"));
    }

    Ok(SystemIntentResponse {
        provider_id: state.config.provider_id.clone(),
        session_id: request.execution_token.session_id.clone(),
        task_id: request.execution_token.task_id.clone(),
        task_state: task.state,
        status,
        intent: request.intent.clone(),
        summary: plan.summary,
        route_preference: plan.route_preference,
        next_action: plan.next_action,
        plan_source,
        candidate_capabilities: plan.candidate_capabilities,
        actions,
        requires_handoff,
        notes,
    })
}

fn ensure_token_context(token: &aios_contracts::ExecutionToken) -> anyhow::Result<()> {
    if token.capability_id != methods::SYSTEM_INTENT_EXECUTE {
        anyhow::bail!(
            "execution token capability {} does not match {}",
            token.capability_id,
            methods::SYSTEM_INTENT_EXECUTE
        );
    }
    if token.execution_location != "local" {
        anyhow::bail!("system-intent provider only supports local execution tokens");
    }
    Ok(())
}

fn normalize_plan(mut plan: AgentPlan, intent: &str) -> AgentPlan {
    if plan.summary.trim().is_empty() {
        plan.summary = summarize(intent);
    }
    if plan.candidate_capabilities.is_empty() {
        plan.candidate_capabilities = heuristic_capabilities(intent);
    }
    if plan.route_preference.trim().is_empty() {
        plan.route_preference = derive_route_preference(&plan.candidate_capabilities);
    }
    if plan.next_action.trim().is_empty() {
        plan.next_action = derive_next_action(&plan.candidate_capabilities);
    }
    if plan.steps.is_empty() {
        plan.steps = heuristic_steps(&plan.candidate_capabilities, &plan.next_action);
    }
    plan
}

fn heuristic_plan(task: &TaskRecord, intent: &str) -> AgentPlan {
    let candidate_capabilities = heuristic_capabilities(intent);
    let next_action = derive_next_action(&candidate_capabilities);
    AgentPlan {
        task_id: task.task_id.clone(),
        session_id: task.session_id.clone(),
        summary: task
            .title
            .clone()
            .filter(|title| !title.trim().is_empty())
            .unwrap_or_else(|| summarize(intent)),
        route_preference: derive_route_preference(&candidate_capabilities),
        next_action: next_action.clone(),
        steps: heuristic_steps(&candidate_capabilities, &next_action),
        candidate_capabilities,
    }
}

fn summarize(intent: &str) -> String {
    let trimmed = intent.trim();
    if trimmed.chars().count() <= 96 {
        return trimmed.to_string();
    }

    format!("{}...", trimmed.chars().take(96).collect::<String>())
}

fn heuristic_capabilities(intent: &str) -> Vec<String> {
    aios_core::intent::candidate_capabilities(intent)
}

fn derive_route_preference(candidate_capabilities: &[String]) -> String {
    aios_core::intent::control_plane_route_preference(candidate_capabilities)
}

fn derive_next_action(candidate_capabilities: &[String]) -> String {
    aios_core::intent::next_action(candidate_capabilities)
}

fn heuristic_steps(candidate_capabilities: &[String], next_action: &str) -> Vec<AgentPlanStep> {
    candidate_capabilities
        .iter()
        .enumerate()
        .map(|(index, capability_id)| AgentPlanStep {
            step: capability_id.replace('.', "-"),
            capability_id: capability_id.clone(),
            status: if index == 0 {
                "ready".to_string()
            } else {
                "planned".to_string()
            },
            provider_kind: None,
            execution_location: None,
            requires_approval: matches!(
                capability_id.as_str(),
                methods::SYSTEM_FILE_BULK_DELETE
                    | "compat.code.execute"
                    | "device.capture.screen.read"
            ),
            requires_portal_handle: matches!(
                capability_id.as_str(),
                "provider.fs.open"
                    | methods::SYSTEM_FILE_BULK_DELETE
                    | "compat.document.open"
                    | "device.capture.screen.read"
            ),
            portal_kind: match capability_id.as_str() {
                "provider.fs.open" | methods::SYSTEM_FILE_BULK_DELETE | "compat.document.open" => {
                    Some("file_handle".to_string())
                }
                "device.capture.screen.read" => Some("screen_share_handle".to_string()),
                _ => None,
            },
            recovery_action: Some(next_action.to_string()),
        })
        .collect()
}

fn build_actions(candidate_capabilities: &[String]) -> Vec<SystemIntentAction> {
    if candidate_capabilities.is_empty() {
        return vec![manual_review_action("no candidate capability resolved")];
    }

    candidate_capabilities
        .iter()
        .enumerate()
        .map(|(index, capability_id)| action_for_capability(index, capability_id))
        .collect()
}

fn action_for_capability(index: usize, capability_id: &str) -> SystemIntentAction {
    let action_id = format!(
        "intent-action-{}-{}",
        index + 1,
        capability_id.replace('.', "-")
    );

    match capability_id {
        methods::SYSTEM_INTENT_EXECUTE => SystemIntentAction {
            action_id,
            kind: "control-plan".to_string(),
            capability_id: Some(capability_id.to_string()),
            description:
                "Keep the request on the local control plane and refine the next specific capability."
                    .to_string(),
            requires_approval: false,
        },
        "provider.fs.open" => SystemIntentAction {
            action_id,
            kind: "provider-call".to_string(),
            capability_id: Some(capability_id.to_string()),
            description:
                "Open the referenced file or directory through the filesystem provider before continuing."
                    .to_string(),
            requires_approval: false,
        },
        "runtime.infer.submit" => SystemIntentAction {
            action_id,
            kind: "runtime-preview".to_string(),
            capability_id: Some(capability_id.to_string()),
            description:
                "Forward the prompt to the local runtime provider for a structured model response."
                    .to_string(),
            requires_approval: false,
        },
        "system.file.bulk_delete" => SystemIntentAction {
            action_id,
            kind: "manual-review".to_string(),
            capability_id: Some(capability_id.to_string()),
            description:
                "Deletion remains approval-gated; require an explicit reviewed execution path first."
                    .to_string(),
            requires_approval: true,
        },
        "compat.code.execute" => SystemIntentAction {
            action_id,
            kind: "manual-review".to_string(),
            capability_id: Some(capability_id.to_string()),
            description:
                "Code execution must stay approval-gated before handing off to the sandbox provider."
                    .to_string(),
            requires_approval: true,
        },
        "device.capture.screen.read" => SystemIntentAction {
            action_id,
            kind: "manual-review".to_string(),
            capability_id: Some(capability_id.to_string()),
            description:
                "Screen capture remains approval-gated before requesting sensitive device access."
                    .to_string(),
            requires_approval: true,
        },
        capability_id if capability_id.starts_with("shell.") => SystemIntentAction {
            action_id,
            kind: "shell-control".to_string(),
            capability_id: Some(capability_id.to_string()),
            description: "Route the request through a shell control provider.".to_string(),
            requires_approval: false,
        },
        capability_id if capability_id.starts_with("compat.") => SystemIntentAction {
            action_id,
            kind: "compat-bridge".to_string(),
            capability_id: Some(capability_id.to_string()),
            description: "Route the request through a compat bridge provider.".to_string(),
            requires_approval: false,
        },
        _ => manual_review_action(capability_id),
    }
}

fn manual_review_action(reason: &str) -> SystemIntentAction {
    SystemIntentAction {
        action_id: "intent-action-manual-review".to_string(),
        kind: "manual-review".to_string(),
        capability_id: None,
        description: format!("Review the intent manually before execution: {reason}"),
        requires_approval: true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn heuristic_capabilities_fall_back_to_system_intent_execute() {
        let capabilities = heuristic_capabilities("Just help me think through this");
        assert_eq!(
            capabilities,
            vec![methods::SYSTEM_INTENT_EXECUTE.to_string()]
        );
    }

    #[test]
    fn build_actions_marks_delete_as_manual_review() {
        let actions = build_actions(&[
            "provider.fs.open".to_string(),
            "system.file.bulk_delete".to_string(),
        ]);

        assert_eq!(actions.len(), 2);
        assert!(!actions[0].requires_approval);
        assert!(actions[1].requires_approval);
        assert_eq!(actions[1].kind, "manual-review");
    }

    #[test]
    fn heuristic_capabilities_detect_panel_event_queries() {
        let capabilities =
            heuristic_capabilities("Inspect the panel action log for the notification center");

        assert!(capabilities
            .iter()
            .any(|item| item == methods::SHELL_PANEL_EVENTS_LIST));
        assert_eq!(
            derive_next_action(&capabilities),
            "inspect-shell-panel-events"
        );
    }

    #[test]
    fn heuristic_capabilities_support_chinese_file_summary_intents() {
        let capabilities = heuristic_capabilities("打开 /tmp/报告.md 并总结重点");

        assert_eq!(
            capabilities.first(),
            Some(&methods::PROVIDER_FS_OPEN.to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == methods::RUNTIME_INFER_SUBMIT));
        assert_eq!(derive_next_action(&capabilities), "inspect-bound-target");
    }

    #[test]
    fn destructive_intents_prioritize_delete_and_require_approval() {
        let capabilities = heuristic_capabilities("Delete /tmp/danger.txt after review");

        assert_eq!(
            capabilities.first(),
            Some(&methods::SYSTEM_FILE_BULK_DELETE.to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == methods::PROVIDER_FS_OPEN));
        assert_eq!(
            derive_next_action(&capabilities),
            "request-destructive-approval"
        );

        let actions = build_actions(&capabilities);
        assert!(actions.iter().any(|item| {
            item.capability_id.as_deref() == Some(methods::SYSTEM_FILE_BULK_DELETE)
                && item.requires_approval
        }));
    }

    #[test]
    fn chinese_browser_extract_intent_avoids_filesystem_fallback() {
        let capabilities = heuristic_capabilities("用浏览器打开 https://example.com 并提取标题");

        assert_eq!(
            capabilities.first(),
            Some(&"compat.browser.navigate".to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == "compat.browser.extract"));
        assert!(!capabilities
            .iter()
            .any(|item| item == methods::PROVIDER_FS_OPEN));
    }

    #[test]
    fn chinese_code_execution_intent_is_approval_gated() {
        let capabilities = heuristic_capabilities("在沙箱里运行这个 Python 脚本");

        assert_eq!(
            capabilities.first(),
            Some(&"compat.code.execute".to_string())
        );
        assert_eq!(
            derive_next_action(&capabilities),
            "request-sandbox-approval"
        );

        let actions = build_actions(&capabilities);
        assert_eq!(actions.len(), 1);
        assert!(actions[0].requires_approval);
    }

    #[test]
    fn heuristic_steps_keep_sensitive_capabilities_approval_gated() {
        let steps = heuristic_steps(
            &[
                "compat.code.execute".to_string(),
                "device.capture.screen.read".to_string(),
            ],
            "request-approval",
        );

        assert_eq!(steps.len(), 2);
        assert!(steps[0].requires_approval);
        assert!(!steps[0].requires_portal_handle);
        assert!(steps[1].requires_approval);
        assert!(steps[1].requires_portal_handle);
        assert_eq!(
            steps[1].portal_kind.as_deref(),
            Some("screen_share_handle")
        );
    }
}
