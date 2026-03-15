use std::collections::BTreeMap;

use serde_json::json;

use aios_contracts::{
    methods, AgentIntentSubmitRequest, PortalHandleRecord, PortalIssueHandleRequest,
};

use crate::AppState;

pub fn maybe_issue_handle(
    state: &AppState,
    request: &AgentIntentSubmitRequest,
    session_id: &str,
    capability_id: &str,
    selected_provider_id: Option<&str>,
) -> anyhow::Result<Option<PortalHandleRecord>> {
    let Some((kind, target)) = derive_target(&request.intent, capability_id) else {
        return Ok(None);
    };

    let mut scope = BTreeMap::new();
    scope.insert("capability_id".to_string(), json!(capability_id));
    scope.insert(
        "intent_excerpt".to_string(),
        json!(summarize(&request.intent)),
    );
    scope.insert("target".to_string(), json!(target.clone()));
    if let Some(provider_id) = selected_provider_id {
        scope.insert("provider_id".to_string(), json!(provider_id));
    }

    let handle: PortalHandleRecord = aios_rpc::call_unix(
        &state.config.sessiond_socket,
        methods::PORTAL_HANDLE_ISSUE,
        &PortalIssueHandleRequest {
            kind,
            user_id: request.user_id.clone(),
            session_id: session_id.to_string(),
            target,
            scope,
            expiry_seconds: Some(300),
            revocable: true,
            audit_tags: vec!["agentd".to_string(), capability_id.to_string()],
        },
    )?;

    Ok(Some(handle))
}

pub fn target_hash(handle: &PortalHandleRecord) -> Option<String> {
    handle
        .scope
        .get("target_hash")
        .and_then(|value| value.as_str())
        .map(|value| value.to_string())
}

fn derive_target(intent: &str, capability_id: &str) -> Option<(String, String)> {
    if matches!(
        capability_id,
        "provider.fs.open" | "system.file.bulk_delete" | "compat.document.open"
    ) {
        let path = extract_primary_path(intent)?;
        let kind = if path.ends_with('/') {
            "directory_handle"
        } else {
            "file_handle"
        };
        return Some((kind.to_string(), path));
    }

    if capability_id == "compat.office.export_pdf" {
        let path = extract_export_target(intent)?;
        return Some(("export_target_handle".to_string(), path));
    }

    if capability_id == "device.capture.screen.read" {
        let target = extract_screen_target(intent);
        return Some(("screen_share_handle".to_string(), target));
    }

    None
}

fn extract_primary_path(intent: &str) -> Option<String> {
    extract_paths(intent).into_iter().next()
}

fn extract_export_target(intent: &str) -> Option<String> {
    let paths = extract_paths(intent);
    paths.last().cloned()
}

fn extract_screen_target(intent: &str) -> String {
    let normalized = intent.to_ascii_lowercase();
    if normalized.contains("window")
        || normalized.contains("app")
        || normalized.contains("focused")
        || normalized.contains("active")
    {
        return "window://focused".to_string();
    }

    if normalized.contains("display") || normalized.contains("monitor") {
        return "screen://current-display".to_string();
    }

    "screen://current-display".to_string()
}

fn extract_paths(intent: &str) -> Vec<String> {
    intent
        .split_whitespace()
        .filter_map(|token| {
            let trimmed = token.trim_matches(|char: char| {
                matches!(
                    char,
                    '"' | '\'' | ',' | '.' | ';' | '(' | ')' | '[' | ']' | '{' | '}'
                )
            });

            if trimmed.starts_with('/')
                || trimmed.starts_with("./")
                || trimmed.starts_with("../")
                || trimmed.starts_with("~/")
            {
                return Some(trimmed.to_string());
            }

            None
        })
        .collect()
}

fn summarize(intent: &str) -> String {
    let trimmed = intent.trim();
    if trimmed.len() <= 120 {
        return trimmed.to_string();
    }

    format!("{}...", &trimmed[..120])
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use serde_json::json;

    use aios_contracts::PortalHandleRecord;

    use super::*;

    #[test]
    fn derive_target_returns_file_handle_for_file_paths() {
        let target = derive_target("Open /tmp/report.txt", "provider.fs.open");
        assert_eq!(
            target,
            Some(("file_handle".to_string(), "/tmp/report.txt".to_string()))
        );
    }

    #[test]
    fn derive_target_returns_directory_handle_for_directory_paths() {
        let target = derive_target("Open /tmp/workspace/", "provider.fs.open");
        assert_eq!(
            target,
            Some((
                "directory_handle".to_string(),
                "/tmp/workspace/".to_string()
            ))
        );
    }

    #[test]
    fn derive_target_ignores_unsupported_capabilities() {
        assert_eq!(
            derive_target("Open /tmp/report.txt", "runtime.infer.submit"),
            None
        );
    }

    #[test]
    fn derive_target_returns_export_target_handle_for_export_intent() {
        let target = derive_target(
            "Export /tmp/report.docx to /tmp/report.pdf",
            "compat.office.export_pdf",
        );
        assert_eq!(
            target,
            Some((
                "export_target_handle".to_string(),
                "/tmp/report.pdf".to_string()
            ))
        );
    }

    #[test]
    fn derive_target_returns_screen_share_handle_for_screen_intent() {
        let target = derive_target(
            "Share the current screen with the reviewer",
            "device.capture.screen.read",
        );
        assert_eq!(
            target,
            Some((
                "screen_share_handle".to_string(),
                "screen://current-display".to_string()
            ))
        );
    }

    #[test]
    fn derive_target_uses_window_target_for_window_intent() {
        let target = derive_target(
            "Share the active window for support",
            "device.capture.screen.read",
        );
        assert_eq!(
            target,
            Some((
                "screen_share_handle".to_string(),
                "window://focused".to_string()
            ))
        );
    }

    #[test]
    fn extract_primary_path_handles_punctuation() {
        assert_eq!(
            extract_primary_path("Please open ('/tmp/demo.txt')."),
            Some("/tmp/demo.txt".to_string())
        );
    }

    #[test]
    fn extract_export_target_uses_last_path() {
        assert_eq!(
            extract_export_target("Export /tmp/input.docx to '/tmp/output.pdf'."),
            Some("/tmp/output.pdf".to_string())
        );
    }

    #[test]
    fn target_hash_reads_hash_from_scope() {
        let mut scope = BTreeMap::new();
        scope.insert("target_hash".to_string(), json!("sha256:abc"));
        let handle = PortalHandleRecord {
            handle_id: "hdl-1".to_string(),
            kind: "file_handle".to_string(),
            user_id: "u1".to_string(),
            session_id: "s1".to_string(),
            target: "/tmp/demo.txt".to_string(),
            scope,
            expiry: "2099-01-01T00:00:00Z".to_string(),
            revocable: true,
            issued_at: "2026-01-01T00:00:00Z".to_string(),
            revoked_at: None,
            revocation_reason: None,
            audit_tags: vec![],
        };

        assert_eq!(target_hash(&handle), Some("sha256:abc".to_string()));
    }
}
