pub fn fallback_action(intent: &str) -> String {
    if intent.to_ascii_lowercase().contains("delete") {
        return "request-human-confirmation".to_string();
    }

    "retry-with-lower-risk-route".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn delete_intents_require_human_confirmation() {
        assert_eq!(
            fallback_action("Delete /tmp/report.txt"),
            "request-human-confirmation"
        );
    }

    #[test]
    fn low_risk_intents_prefer_retry() {
        assert_eq!(
            fallback_action("Summarize this draft"),
            "retry-with-lower-risk-route"
        );
    }
}
