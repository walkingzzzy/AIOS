pub fn fallback_action(intent: &str) -> String {
    aios_core::intent::fallback_action(intent)
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
    fn chinese_delete_intents_require_human_confirmation() {
        assert_eq!(
            fallback_action("删除 /tmp/report.txt"),
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
