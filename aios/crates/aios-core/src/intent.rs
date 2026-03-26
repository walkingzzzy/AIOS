use aios_contracts::methods;

#[derive(Debug, Default)]
struct IntentSignals {
    has_explicit_target: bool,
    mentions_screen: bool,
    mentions_web: bool,
    mentions_web_extract: bool,
    mentions_code_execution: bool,
    mentions_file_target: bool,
    mentions_document: bool,
    mentions_export_pdf: bool,
    mentions_delete: bool,
    mentions_runtime: bool,
    mentions_notification: bool,
    mentions_operator_audit: bool,
    mentions_panel_events: bool,
    mentions_focus: bool,
    mentions_meta_request: bool,
}

pub fn candidate_capabilities(intent: &str) -> Vec<String> {
    let signals = analyze_intent(intent);
    let mut capabilities = Vec::new();
    let suppress_surface_routes = should_suppress_surface_routes(&signals);

    if signals.mentions_delete && !suppress_surface_routes {
        push_capability(&mut capabilities, methods::SYSTEM_FILE_BULK_DELETE);
    }
    if signals.mentions_code_execution && !suppress_surface_routes {
        push_capability(&mut capabilities, "compat.code.execute");
    }
    if signals.mentions_screen && !suppress_surface_routes {
        push_capability(&mut capabilities, "device.capture.screen.read");
    }
    if signals.mentions_web && !suppress_surface_routes {
        push_capability(&mut capabilities, "compat.browser.navigate");
    }
    if signals.mentions_web && signals.mentions_web_extract && !suppress_surface_routes {
        push_capability(&mut capabilities, "compat.browser.extract");
    }
    if signals.mentions_export_pdf && !suppress_surface_routes {
        push_capability(&mut capabilities, "compat.office.export_pdf");
    }
    if signals.mentions_document && !suppress_surface_routes {
        push_capability(&mut capabilities, "compat.document.open");
    }
    if signals.mentions_file_target && !suppress_surface_routes {
        push_capability(&mut capabilities, methods::PROVIDER_FS_OPEN);
    }
    if signals.mentions_runtime {
        push_capability(&mut capabilities, methods::RUNTIME_INFER_SUBMIT);
    }
    if signals.mentions_notification && !suppress_surface_routes {
        push_capability(&mut capabilities, methods::SHELL_NOTIFICATION_OPEN);
    }
    if signals.mentions_operator_audit {
        push_capability(&mut capabilities, methods::SHELL_OPERATOR_AUDIT_OPEN);
    }
    if signals.mentions_panel_events {
        push_capability(&mut capabilities, methods::SHELL_PANEL_EVENTS_LIST);
    }
    if signals.mentions_focus && !suppress_surface_routes {
        push_capability(&mut capabilities, methods::SHELL_WINDOW_FOCUS);
    }
    if capabilities.is_empty() {
        push_capability(&mut capabilities, methods::SYSTEM_INTENT_EXECUTE);
    }
    capabilities.sort_by_key(|capability_id| capability_priority(capability_id));

    capabilities
}

pub fn topology_preference(intent: &str) -> String {
    let normalized = intent.to_lowercase();

    if contains_any(
        &normalized,
        &["plan", "multi-step", "计划", "分步", "多步骤"],
    ) {
        return "plan-execute".to_string();
    }

    let signals = analyze_intent(intent);
    if !should_suppress_surface_routes(&signals)
        && (signals.mentions_file_target
            || signals.mentions_web
            || signals.mentions_screen
            || signals.mentions_code_execution
            || signals.mentions_export_pdf
            || signals.mentions_document
            || signals.mentions_notification
            || signals.mentions_focus)
    {
        return "tool-calling".to_string();
    }

    "direct".to_string()
}

pub fn fallback_action(intent: &str) -> String {
    let normalized = intent.to_lowercase();
    if contains_any(&normalized, &["delete", "删除", "移除"]) {
        return "request-human-confirmation".to_string();
    }

    "retry-with-lower-risk-route".to_string()
}

pub fn control_plane_route_preference(candidate_capabilities: &[String]) -> String {
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

pub fn next_action(candidate_capabilities: &[String]) -> String {
    match candidate_capabilities.first().map(String::as_str) {
        Some(methods::SYSTEM_FILE_BULK_DELETE) => "request-destructive-approval".to_string(),
        Some("compat.code.execute") => "request-sandbox-approval".to_string(),
        Some("device.capture.screen.read") => "request-screen-capture-approval".to_string(),
        Some("compat.browser.navigate") => "open-browser-target".to_string(),
        Some("compat.browser.extract") => "extract-browser-content".to_string(),
        Some("compat.office.export_pdf") => "export-document-target".to_string(),
        Some("compat.document.open") => "open-compat-document".to_string(),
        Some(methods::PROVIDER_FS_OPEN) => "inspect-bound-target".to_string(),
        Some(methods::SHELL_PANEL_EVENTS_LIST) => "inspect-shell-panel-events".to_string(),
        Some(capability_id) if capability_id.starts_with("shell.") => {
            "route-shell-control".to_string()
        }
        Some(methods::RUNTIME_INFER_SUBMIT) => "invoke-runtime-preview".to_string(),
        _ => "review-local-control-plan".to_string(),
    }
}

fn analyze_intent(intent: &str) -> IntentSignals {
    let normalized = intent.to_lowercase();
    let has_url = contains_any(
        &normalized,
        &["http://", "https://", "www."],
    );
    let mentions_navigation_action = contains_any(
        &normalized,
        &[
            "open", "visit", "navigate", "browse", "go to", "launch", "打开", "访问", "前往",
            "浏览", "启动",
        ],
    );
    let mentions_extract_action = contains_any(
        &normalized,
        &[
            "extract", "scrape", "selector", "title", "提取", "抓取", "抽取", "标题",
        ],
    );
    let mentions_web_surface = contains_any(
        &normalized,
        &[
            "browser",
            "website",
            "web page",
            "webpage",
            "url",
            "浏览器",
            "网页",
            "网站",
            "网址",
            "链接",
        ],
    );
    let mentions_web = has_url || (mentions_web_surface && (mentions_navigation_action || mentions_extract_action));
    let mentions_path = !has_url
        && contains_any(
            &normalized,
            &[
                "/", "\\", "~/", "../", "./", ".txt", ".md", ".pdf", ".doc", ".docx", ".odt",
                ".json", ".yaml", ".yml", ".log", ".csv",
            ],
        );
    let mentions_document = contains_any(
        &normalized,
        &["document", ".doc", ".docx", ".odt", "word", "文档"],
    );
    let mentions_file_object = contains_any(
        &normalized,
        &[
            "file",
            "files",
            "folder",
            "directory",
            "path",
            "文件",
            "文件夹",
            "目录",
            "路径",
        ],
    ) || mentions_document;
    let mentions_file_action = contains_any(
        &normalized,
        &[
            "open",
            "read",
            "inspect",
            "view",
            "review",
            "summarize",
            "summary",
            "translate",
            "analyze",
            "analyse",
            "rewrite",
            "write",
            "edit",
            "export",
            "delete",
            "remove",
            "list",
            "打开",
            "读取",
            "检查",
            "查看",
            "审阅",
            "总结",
            "摘要",
            "翻译",
            "分析",
            "改写",
            "撰写",
            "编辑",
            "导出",
            "删除",
            "移除",
            "列出",
        ],
    );
    let mentions_file_target = mentions_path
        || (mentions_file_object && mentions_file_action)
        || mentions_document;
    let mentions_delete_action = contains_any(
        &normalized,
        &[
            "delete", "remove", "erase", "purge", "wipe", "删除", "移除", "清理", "清空",
        ],
    );
    let mentions_recycle_bin = contains_any(
        &normalized,
        &["recycle bin", "trash", "回收站", "垃圾桶"],
    );
    let mentions_meta_request = contains_any(
        &normalized,
        &[
            "how to",
            "how do",
            "what is",
            "why",
            "explain",
            "describe",
            "guide",
            "docs",
            "documentation",
            "tutorial",
            "如何",
            "怎么",
            "为什么",
            "介绍",
            "说明",
            "文档",
            "教程",
        ],
    );

    IntentSignals {
        has_explicit_target: has_url || mentions_path,
        mentions_screen: contains_any(&normalized, &["screen", "screenshot", "屏幕", "截图"])
            && contains_any(
                &normalized,
                &[
                    "capture",
                    "share",
                    "screenshot",
                    "read",
                    "inspect",
                    "捕获",
                    "共享",
                    "截图",
                    "读取",
                    "检查",
                ],
            ),
        mentions_web,
        mentions_web_extract: mentions_web && mentions_extract_action,
        mentions_code_execution: contains_any(
            &normalized,
            &[
                "python", "script", "code", "sandbox", "脚本", "代码", "沙箱",
            ],
        ) && contains_any(
            &normalized,
            &["run", "execute", "launch", "运行", "执行", "启动"],
        ),
        mentions_file_target,
        mentions_document,
        mentions_export_pdf: contains_any(
            &normalized,
            &["export", "pdf", "导出", "转换为pdf", "转成pdf"],
        ),
        mentions_delete: mentions_delete_action && (mentions_file_target || mentions_recycle_bin),
        mentions_runtime: contains_any(
            &normalized,
            &[
                "summarize",
                "summary",
                "write",
                "rewrite",
                "draft",
                "plan",
                "analyze",
                "analyse",
                "explain",
                "translate",
                "review",
                "总结",
                "摘要",
                "概括",
                "写",
                "撰写",
                "改写",
                "计划",
                "规划",
                "分析",
                "解释",
                "翻译",
                "审阅",
                "how to",
                "how do",
                "what is",
                "why",
                "guide",
                "docs",
                "documentation",
                "tutorial",
                "如何",
                "怎么",
                "为什么",
                "介绍",
                "说明",
                "文档",
                "教程",
            ],
        ),
        mentions_notification: contains_any(
            &normalized,
            &["notification", "notify", "提醒", "通知", "消息提醒"],
        ),
        mentions_operator_audit: contains_any(
            &normalized,
            &["audit", "审计", "operator audit", "操作审计"],
        ) && contains_any(
            &normalized,
            &["operator", "panel", "log", "操作", "面板", "日志"],
        ),
        mentions_panel_events: mentions_panel_event_query(&normalized),
        mentions_focus: contains_any(
            &normalized,
            &[
                "focus window",
                "focus workspace",
                "bring to front",
                "focus",
                "聚焦窗口",
                "切换窗口",
                "置前",
                "聚焦",
            ],
        ),
        mentions_meta_request,
    }
}

fn push_capability(capabilities: &mut Vec<String>, capability_id: &str) {
    if !capabilities.iter().any(|item| item == capability_id) {
        capabilities.push(capability_id.to_string());
    }
}

fn contains_any(haystack: &str, patterns: &[&str]) -> bool {
    patterns.iter().any(|pattern| haystack.contains(pattern))
}

fn should_suppress_surface_routes(signals: &IntentSignals) -> bool {
    signals.mentions_meta_request
        && !signals.has_explicit_target
        && !signals.mentions_operator_audit
        && !signals.mentions_panel_events
}

fn mentions_panel_event_query(normalized: &str) -> bool {
    contains_any(
        normalized,
        &[
            "panel action",
            "panel actions",
            "panel event",
            "panel events",
            "面板事件",
            "面板日志",
            "操作日志",
            "激活日志",
        ],
    ) || (normalized.contains("panel")
        && contains_any(normalized, &["event log", "action log", "activation log"]))
}

fn capability_priority(capability_id: &str) -> u8 {
    match capability_id {
        methods::SYSTEM_FILE_BULK_DELETE => 5,
        "compat.code.execute" => 10,
        "device.capture.screen.read" => 20,
        "compat.browser.navigate" => 30,
        "compat.browser.extract" => 35,
        "compat.office.export_pdf" => 40,
        "compat.document.open" => 45,
        methods::PROVIDER_FS_OPEN => 50,
        methods::RUNTIME_INFER_SUBMIT => 60,
        methods::SHELL_PANEL_EVENTS_LIST => 70,
        methods::SHELL_OPERATOR_AUDIT_OPEN => 72,
        methods::SHELL_NOTIFICATION_OPEN => 74,
        methods::SHELL_WINDOW_FOCUS => 76,
        methods::SYSTEM_INTENT_EXECUTE => 100,
        _ => 110,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn falls_back_to_generic_intent_execution() {
        let capabilities = candidate_capabilities("Just help me think");
        assert_eq!(
            capabilities,
            vec![methods::SYSTEM_INTENT_EXECUTE.to_string()]
        );
    }

    #[test]
    fn detects_multiple_capabilities_from_single_intent() {
        let capabilities = candidate_capabilities("Open the file, summarize it, then delete it");

        assert_eq!(
            capabilities.first(),
            Some(&methods::SYSTEM_FILE_BULK_DELETE.to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == methods::PROVIDER_FS_OPEN));
        assert!(capabilities
            .iter()
            .any(|item| item == methods::RUNTIME_INFER_SUBMIT));
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
            .any(|item| item == methods::SHELL_NOTIFICATION_OPEN));
        assert!(capabilities
            .iter()
            .any(|item| item == methods::SHELL_WINDOW_FOCUS));
    }

    #[test]
    fn detects_panel_event_queries_as_shell_capability() {
        let capabilities =
            candidate_capabilities("List the panel action log for the approval panel");

        assert!(capabilities
            .iter()
            .any(|item| item == methods::SHELL_PANEL_EVENTS_LIST));
    }

    #[test]
    fn detects_operator_audit_panel_queries() {
        let capabilities =
            candidate_capabilities("Open the operator audit log panel for recent remote failures");

        assert!(capabilities
            .iter()
            .any(|item| item == methods::SHELL_OPERATOR_AUDIT_OPEN));
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
        assert!(!capabilities
            .iter()
            .any(|item| item == methods::PROVIDER_FS_OPEN));
    }

    #[test]
    fn detects_code_sandbox_capability_for_python_execution() {
        let capabilities = candidate_capabilities("Run this Python script in the sandbox");

        assert_eq!(
            capabilities.first(),
            Some(&"compat.code.execute".to_string())
        );
    }

    #[test]
    fn detects_chinese_file_summary_intent() {
        let capabilities = candidate_capabilities("打开 /tmp/报告.md 并总结重点");

        assert_eq!(
            capabilities.first(),
            Some(&methods::PROVIDER_FS_OPEN.to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == methods::RUNTIME_INFER_SUBMIT));
    }

    #[test]
    fn detects_chinese_delete_intent() {
        let capabilities = candidate_capabilities("删除 /tmp/danger.txt 并清空回收站");

        assert_eq!(
            capabilities.first(),
            Some(&methods::SYSTEM_FILE_BULK_DELETE.to_string())
        );
        assert!(capabilities
            .iter()
            .any(|item| item == methods::PROVIDER_FS_OPEN));
    }

    #[test]
    fn detects_chinese_browser_extract_intent() {
        let capabilities = candidate_capabilities("用浏览器打开 https://example.com 并提取标题");

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
    fn picks_plan_execute_for_multistep_requests() {
        assert_eq!(
            topology_preference("Create a multi-step plan for migration"),
            "plan-execute"
        );
    }

    #[test]
    fn picks_tool_calling_for_chinese_file_or_browser_work() {
        assert_eq!(
            topology_preference("打开浏览器并检查文件路径"),
            "tool-calling"
        );
    }

    #[test]
    fn browser_provider_explanation_prefers_direct_topology() {
        assert_eq!(
            topology_preference("Explain the browser provider health state"),
            "direct"
        );
    }

    #[test]
    fn delete_intents_require_human_confirmation() {
        assert_eq!(
            fallback_action("删除 /tmp/report.txt"),
            "request-human-confirmation"
        );
    }

    #[test]
    fn capability_next_action_prefers_primary_capability() {
        let capabilities = vec![
            methods::PROVIDER_FS_OPEN.to_string(),
            methods::RUNTIME_INFER_SUBMIT.to_string(),
        ];
        assert_eq!(next_action(&capabilities), "inspect-bound-target");
    }

    #[test]
    fn control_plane_route_prefers_manual_guidance_for_generic_intent() {
        let capabilities = vec![methods::SYSTEM_INTENT_EXECUTE.to_string()];
        assert_eq!(
            control_plane_route_preference(&capabilities),
            "manual-guidance"
        );
    }

    #[test]
    fn browser_provider_explanation_does_not_trigger_navigation_route() {
        let capabilities = candidate_capabilities("Explain the browser provider health state");

        assert_eq!(
            capabilities.first(),
            Some(&methods::RUNTIME_INFER_SUBMIT.to_string())
        );
        assert!(!capabilities
            .iter()
            .any(|item| item == "compat.browser.navigate"));
    }

    #[test]
    fn delete_audit_log_review_does_not_trigger_file_delete() {
        let capabilities = candidate_capabilities("Review the delete audit log for recent failures");

        assert!(!capabilities
            .iter()
            .any(|item| item == methods::SYSTEM_FILE_BULK_DELETE));
        assert!(capabilities
            .iter()
            .any(|item| item == methods::SHELL_OPERATOR_AUDIT_OPEN));
        assert!(capabilities
            .iter()
            .any(|item| item == methods::RUNTIME_INFER_SUBMIT));
    }

    #[test]
    fn sandbox_explanation_does_not_trigger_code_execution() {
        let capabilities = candidate_capabilities("Explain the Python sandbox approval model");

        assert_eq!(
            capabilities.first(),
            Some(&methods::RUNTIME_INFER_SUBMIT.to_string())
        );
        assert!(!capabilities
            .iter()
            .any(|item| item == "compat.code.execute"));
    }
}
