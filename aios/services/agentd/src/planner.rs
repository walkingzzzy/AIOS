use aios_contracts::AgentPlan;

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
    let next_action = crate::recovery::fallback_action(&intent);

    AgentPlan {
        task_id,
        session_id,
        summary: summarize(&intent),
        route_preference,
        candidate_capabilities,
        next_action,
    }
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
        assert!(plan
            .candidate_capabilities
            .iter()
            .any(|item| item == "provider.fs.open"));
    }
}
