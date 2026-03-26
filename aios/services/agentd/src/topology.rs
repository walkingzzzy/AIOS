pub fn choose(intent: &str) -> String {
    aios_core::intent::topology_preference(intent)
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
    fn picks_tool_calling_for_chinese_file_or_browser_work() {
        assert_eq!(choose("打开浏览器并检查文件路径"), "tool-calling");
    }

    #[test]
    fn defaults_to_direct_for_simple_requests() {
        assert_eq!(choose("Say hello"), "direct");
    }
}
