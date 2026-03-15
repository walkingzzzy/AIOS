use aios_contracts::{
    methods, AgentPlan, SystemIntentAction, SystemIntentRequest, SystemIntentResponse, TaskRecord,
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
    plan
}

fn heuristic_plan(task: &TaskRecord, intent: &str) -> AgentPlan {
    let candidate_capabilities = heuristic_capabilities(intent);
    AgentPlan {
        task_id: task.task_id.clone(),
        session_id: task.session_id.clone(),
        summary: task
            .title
            .clone()
            .filter(|title| !title.trim().is_empty())
            .unwrap_or_else(|| summarize(intent)),
        route_preference: derive_route_preference(&candidate_capabilities),
        next_action: derive_next_action(&candidate_capabilities),
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
    let normalized = intent.to_ascii_lowercase();
    let mut capabilities = Vec::new();

    if normalized.contains("delete") {
        push_capability(&mut capabilities, "system.file.bulk_delete");
    }
    if normalized.contains("file")
        || normalized.contains('/')
        || normalized.contains("~/")
        || normalized.contains(".txt")
        || normalized.contains(".md")
        || normalized.contains(".pdf")
    {
        push_capability(&mut capabilities, "provider.fs.open");
    }
    if normalized.contains("summarize")
        || normalized.contains("write")
        || normalized.contains("plan")
    {
        push_capability(&mut capabilities, "runtime.infer.submit");
    }
    if normalized.contains("notification") || normalized.contains("notify") {
        push_capability(&mut capabilities, "shell.notification.open");
    }
    if normalized.contains("audit")
        && (normalized.contains("operator") || normalized.contains("panel") || normalized.contains("log"))
    {
        push_capability(&mut capabilities, "shell.operator-audit.open");
    }
    if mentions_panel_event_query(&normalized) {
        push_capability(&mut capabilities, methods::SHELL_PANEL_EVENTS_LIST);
    }
    if normalized.contains("focus") {
        push_capability(&mut capabilities, "shell.window.focus");
    }
    if normalized.contains("browser")
        || normalized.contains("http://")
        || normalized.contains("https://")
    {
        push_capability(&mut capabilities, "compat.browser.navigate");
    }
    if capabilities.is_empty() {
        push_capability(&mut capabilities, methods::SYSTEM_INTENT_EXECUTE);
    }

    capabilities
}

fn push_capability(capabilities: &mut Vec<String>, capability_id: &str) {
    if !capabilities.iter().any(|item| item == capability_id) {
        capabilities.push(capability_id.to_string());
    }
}

fn mentions_panel_event_query(normalized: &str) -> bool {
    normalized.contains("panel action")
        || normalized.contains("panel actions")
        || normalized.contains("panel event")
        || normalized.contains("panel events")
        || (normalized.contains("panel")
            && (normalized.contains("event log")
                || normalized.contains("action log")
                || normalized.contains("activation log")))
}

fn derive_route_preference(candidate_capabilities: &[String]) -> String {
    if candidate_capabilities.len() == 1
        && candidate_capabilities
            .first()
            .is_some_and(|item| item == methods::SYSTEM_INTENT_EXECUTE)
    {
        "manual-guidance".to_string()
    } else {
        "tool-calling".to_string()
    }
}

fn derive_next_action(candidate_capabilities: &[String]) -> String {
    if candidate_capabilities
        .iter()
        .any(|item| item == "provider.fs.open")
    {
        return "inspect-bound-target".to_string();
    }
    if candidate_capabilities
        .iter()
        .any(|item| item == methods::SHELL_PANEL_EVENTS_LIST)
    {
        return "inspect-shell-panel-events".to_string();
    }
    if candidate_capabilities
        .iter()
        .any(|item| item.starts_with("shell."))
    {
        return "route-shell-control".to_string();
    }
    if candidate_capabilities
        .iter()
        .any(|item| item == "runtime.infer.submit")
    {
        return "invoke-runtime-preview".to_string();
    }
    if candidate_capabilities
        .iter()
        .any(|item| item == "system.file.bulk_delete")
    {
        return "request-destructive-approval".to_string();
    }

    "review-local-control-plan".to_string()
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
}
