pub fn choose(intent: &str) -> String {
    let normalized = intent.to_ascii_lowercase();

    if normalized.contains("plan") || normalized.contains("multi-step") {
        return "plan-execute".to_string();
    }

    if normalized.contains("open") || normalized.contains("file") || normalized.contains("browser")
    {
        return "tool-calling".to_string();
    }

    "direct".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn picks_plan_execute_for_multistep_requests() {
        assert_eq!(
            choose("Create a multi-step plan for migration"),
            "plan-execute"
        );
    }

    #[test]
    fn picks_tool_calling_for_file_or_browser_work() {
        assert_eq!(choose("Open the browser and file chooser"), "tool-calling");
    }

    #[test]
    fn defaults_to_direct_for_simple_requests() {
        assert_eq!(choose("Say hello"), "direct");
    }
}
