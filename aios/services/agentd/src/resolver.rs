pub fn candidate_capabilities(intent: &str) -> Vec<String> {
    let normalized = intent.to_ascii_lowercase();
    let mut capabilities = Vec::new();

    let mentions_web = normalized.contains("http://")
        || normalized.contains("https://")
        || normalized.contains("www.")
        || normalized.contains("browser")
        || normalized.contains("website")
        || normalized.contains("web page")
        || normalized.contains("webpage")
        || normalized.contains("url");
    let mentions_web_extract = normalized.contains("extract")
        || normalized.contains("scrape")
        || normalized.contains("selector")
        || (mentions_web && normalized.contains("title"));
    let mentions_code_subject = normalized.contains("python")
        || normalized.contains("script")
        || normalized.contains("sandbox")
        || normalized.contains("code");
    let mentions_code_action = normalized.contains("run")
        || normalized.contains("execute")
        || normalized.contains("sandbox");
    let mentions_path = !mentions_web
        && (normalized.contains("/")
            || normalized.contains("~/")
            || normalized.contains("../")
            || normalized.contains("./")
            || normalized.contains(".txt")
            || normalized.contains(".md")
            || normalized.contains(".pdf")
            || normalized.contains(".doc")
            || normalized.contains(".docx")
            || normalized.contains(".odt"));
    let mentions_panel_events = mentions_panel_event_query(&normalized);

    if normalized.contains("screen") {
        push_capability(&mut capabilities, "device.capture.screen.read");
    }

    if mentions_web {
        push_capability(&mut capabilities, "compat.browser.navigate");
    }

    if mentions_web && mentions_web_extract {
        push_capability(&mut capabilities, "compat.browser.extract");
    }

    if normalized.contains("notification") || normalized.contains("notify") {
        push_capability(&mut capabilities, "shell.notification.open");
    }

    if normalized.contains("audit")
        && (normalized.contains("operator") || normalized.contains("panel") || normalized.contains("log"))
    {
        push_capability(&mut capabilities, "shell.operator-audit.open");
    }

    if mentions_panel_events {
        push_capability(&mut capabilities, "shell.panel-events.list");
    }

    if normalized.contains("focus")
        && (normalized.contains("window") || normalized.contains("workspace"))
    {
        push_capability(&mut capabilities, "shell.window.focus");
    }

    if normalized.contains("export") || normalized.contains("pdf") {
        push_capability(&mut capabilities, "compat.office.export_pdf");
    }

    if normalized.contains("document")
        || normalized.contains(".doc")
        || normalized.contains(".docx")
        || normalized.contains(".odt")
    {
        push_capability(&mut capabilities, "compat.document.open");
    }

    if mentions_code_subject && mentions_code_action {
        push_capability(&mut capabilities, "compat.code.execute");
    }

    if normalized.contains("delete") {
        push_capability(&mut capabilities, "system.file.bulk_delete");
    }

    if normalized.contains("file") || mentions_path {
        push_capability(&mut capabilities, "provider.fs.open");
    }

    if normalized.contains("summarize")
        || normalized.contains("write")
        || normalized.contains("plan")
    {
        push_capability(&mut capabilities, "runtime.infer.submit");
    }

    if capabilities.is_empty() {
        push_capability(&mut capabilities, "system.intent.execute");
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_multiple_capabilities_from_single_intent() {
        let capabilities = candidate_capabilities("Open the file, summarize it, then delete it");

        assert!(capabilities.iter().any(|item| item == "provider.fs.open"));
        assert!(capabilities
            .iter()
            .any(|item| item == "runtime.infer.submit"));
        assert!(capabilities
            .iter()
            .any(|item| item == "system.file.bulk_delete"));
    }

    #[test]
    fn falls_back_to_generic_intent_execution() {
        let capabilities = candidate_capabilities("Just help me think");
        assert_eq!(capabilities, vec!["system.intent.execute".to_string()]);
    }

    #[test]
    fn detects_export_pdf_as_primary_compat_capability() {
        let capabilities = candidate_capabilities("Export /tmp/report.docx to /tmp/report.pdf");

        assert_eq!(
            capabilities.first(),
            Some(&"compat.office.export_pdf".to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == "compat.document.open"));
    }

    #[test]
    fn detects_shell_capabilities_from_notification_and_focus_intents() {
        let capabilities =
            candidate_capabilities("Open the notification center and focus the active window");

        assert!(capabilities
            .iter()
            .any(|item| item == "shell.notification.open"));
        assert!(capabilities.iter().any(|item| item == "shell.window.focus"));
    }

    #[test]
    fn detects_panel_event_queries_as_shell_capability() {
        let capabilities =
            candidate_capabilities("List the panel action log for the approval panel");

        assert!(capabilities
            .iter()
            .any(|item| item == "shell.panel-events.list"));
    }

    #[test]
    fn detects_operator_audit_panel_queries() {
        let capabilities =
            candidate_capabilities("Open the operator audit log panel for recent remote failures");

        assert!(capabilities
            .iter()
            .any(|item| item == "shell.operator-audit.open"));
    }

    #[test]
    fn detects_browser_capabilities_from_url_intents() {
        let capabilities =
            candidate_capabilities("Open https://example.com in the browser and extract the title");

        assert_eq!(
            capabilities.first(),
            Some(&"compat.browser.navigate".to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == "compat.browser.extract"));
        assert!(!capabilities.iter().any(|item| item == "provider.fs.open"));
    }

    #[test]
    fn detects_code_sandbox_capability_for_python_execution() {
        let capabilities = candidate_capabilities("Run this Python script in the sandbox");

        assert_eq!(
            capabilities.first(),
            Some(&"compat.code.execute".to_string())
        );
    }
}
