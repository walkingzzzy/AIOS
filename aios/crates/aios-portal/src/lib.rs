use std::{
    borrow::ToOwned,
    fs,
    path::{Path, PathBuf},
};

use anyhow::Context;
use chrono::{Duration, Utc};
use serde_json::json;
use sha2::{Digest, Sha256};
use uuid::Uuid;

use aios_contracts::{
    PortalHandleRecord, PortalIssueHandleRequest, PortalListHandlesResponse,
    PortalLookupHandleRequest, PortalLookupHandleResponse, PortalRevokeHandleRequest,
};

#[derive(Debug, Clone)]
pub struct PortalConfig {
    pub state_dir: PathBuf,
    pub default_ttl_seconds: u64,
}

#[derive(Debug, Clone)]
pub struct Portal {
    config: PortalConfig,
}

#[derive(Debug, Clone)]
struct TargetDetails {
    stored_target: String,
    target_path: String,
    target_hash: String,
    display_name: String,
    target_kind: String,
    availability: String,
    canonical_target: Option<String>,
    file_extension: Option<String>,
}

impl Portal {
    pub fn new(config: PortalConfig) -> anyhow::Result<Self> {
        let portal = Self { config };
        portal.ensure_dirs()?;
        Ok(portal)
    }

    pub fn issue_handle(
        &self,
        request: &PortalIssueHandleRequest,
    ) -> anyhow::Result<PortalHandleRecord> {
        validate_request(request)?;

        let now = Utc::now();
        let expiry_seconds = request
            .expiry_seconds
            .unwrap_or(self.config.default_ttl_seconds) as i64;
        let expiry = now + Duration::seconds(expiry_seconds.max(1));

        let target_details = resolve_target_details(&request.kind, &request.target)?;
        let mut scope = request.scope.clone();
        scope
            .entry("handle_kind".to_string())
            .or_insert_with(|| json!(request.kind.clone()));
        enrich_scope(&request.kind, &target_details, &mut scope);

        let record = PortalHandleRecord {
            handle_id: format!("ph-{}", Uuid::new_v4().simple()),
            kind: request.kind.clone(),
            user_id: request.user_id.clone(),
            session_id: request.session_id.clone(),
            target: target_details.stored_target,
            scope,
            expiry: expiry.to_rfc3339(),
            revocable: request.revocable,
            issued_at: now.to_rfc3339(),
            revoked_at: None,
            revocation_reason: None,
            audit_tags: request.audit_tags.clone(),
        };

        write_json(&self.handle_path(&record.handle_id), &record)?;
        Ok(record)
    }

    pub fn lookup_handle(
        &self,
        request: &PortalLookupHandleRequest,
    ) -> anyhow::Result<PortalLookupHandleResponse> {
        let Some(mut handle) = self.load_handle(&request.handle_id)? else {
            return Ok(PortalLookupHandleResponse { handle: None });
        };

        if !matches_binding(
            &handle,
            request.session_id.as_deref(),
            request.user_id.as_deref(),
        ) {
            return Ok(PortalLookupHandleResponse { handle: None });
        }

        if is_expired(&handle) && handle.revoked_at.is_none() {
            handle.revoked_at = Some(Utc::now().to_rfc3339());
            handle.revocation_reason = Some("expired".to_string());
            write_json(&self.handle_path(&request.handle_id), &handle)?;
        }

        Ok(PortalLookupHandleResponse {
            handle: Some(handle),
        })
    }

    pub fn revoke_handle(
        &self,
        request: &PortalRevokeHandleRequest,
    ) -> anyhow::Result<PortalLookupHandleResponse> {
        let Some(mut handle) = self.load_handle(&request.handle_id)? else {
            return Ok(PortalLookupHandleResponse { handle: None });
        };

        if !matches_binding(
            &handle,
            request.session_id.as_deref(),
            request.user_id.as_deref(),
        ) {
            return Ok(PortalLookupHandleResponse { handle: None });
        }

        if !handle.revocable {
            anyhow::bail!("portal handle is not revocable: {}", request.handle_id);
        }

        if handle.revoked_at.is_none() {
            handle.revoked_at = Some(Utc::now().to_rfc3339());
            handle.revocation_reason = Some(
                request
                    .reason
                    .clone()
                    .unwrap_or_else(|| "revoked".to_string()),
            );
            write_json(&self.handle_path(&request.handle_id), &handle)?;
        }

        Ok(PortalLookupHandleResponse {
            handle: Some(handle),
        })
    }

    pub fn list_handles(
        &self,
        session_id: Option<&str>,
    ) -> anyhow::Result<PortalListHandlesResponse> {
        let mut handles = collect_handle_files(&self.handle_dir())?
            .into_iter()
            .map(|path| load_handle(&path))
            .collect::<anyhow::Result<Vec<_>>>()?;

        for handle in &mut handles {
            if is_expired(handle) && handle.revoked_at.is_none() {
                handle.revoked_at = Some(Utc::now().to_rfc3339());
                handle.revocation_reason = Some("expired".to_string());
                write_json(&self.handle_path(&handle.handle_id), handle)?;
            }
        }

        if let Some(session_id) = session_id {
            handles.retain(|handle| handle.session_id == session_id);
        }

        handles.sort_by(|left, right| left.handle_id.cmp(&right.handle_id));
        Ok(PortalListHandlesResponse { handles })
    }

    pub fn state_dir(&self) -> &Path {
        &self.config.state_dir
    }

    fn ensure_dirs(&self) -> anyhow::Result<()> {
        fs::create_dir_all(self.handle_dir())?;
        Ok(())
    }

    fn handle_dir(&self) -> PathBuf {
        self.config.state_dir.join("handles")
    }

    fn handle_path(&self, handle_id: &str) -> PathBuf {
        self.handle_dir().join(format!("{handle_id}.json"))
    }

    fn load_handle(&self, handle_id: &str) -> anyhow::Result<Option<PortalHandleRecord>> {
        let path = self.handle_path(handle_id);
        if !path.exists() {
            return Ok(None);
        }

        Ok(Some(load_handle(&path)?))
    }
}

fn validate_request(request: &PortalIssueHandleRequest) -> anyhow::Result<()> {
    if request.user_id.trim().is_empty() {
        anyhow::bail!("user_id cannot be empty");
    }
    if request.session_id.trim().is_empty() {
        anyhow::bail!("session_id cannot be empty");
    }
    if request.target.trim().is_empty() {
        anyhow::bail!("target cannot be empty");
    }
    if !matches!(
        request.kind.as_str(),
        "file_handle"
            | "directory_handle"
            | "window_handle"
            | "screen_share_handle"
            | "export_target_handle"
            | "contact_ref"
            | "remote_account_ref"
    ) {
        anyhow::bail!("unsupported portal handle kind: {}", request.kind);
    }

    Ok(())
}

fn enrich_scope(
    kind: &str,
    details: &TargetDetails,
    scope: &mut std::collections::BTreeMap<String, serde_json::Value>,
) {
    scope
        .entry("stored_target".to_string())
        .or_insert_with(|| json!(details.stored_target));
    scope
        .entry("target_path".to_string())
        .or_insert_with(|| json!(details.target_path));
    scope
        .entry("target_hash".to_string())
        .or_insert_with(|| json!(details.target_hash));
    scope
        .entry("handle_kind".to_string())
        .or_insert_with(|| json!(kind));
    scope
        .entry("display_name".to_string())
        .or_insert_with(|| json!(details.display_name));
    scope
        .entry("target_kind".to_string())
        .or_insert_with(|| json!(details.target_kind));
    scope
        .entry("availability".to_string())
        .or_insert_with(|| json!(details.availability));
    scope
        .entry("target_exists".to_string())
        .or_insert_with(|| json!(details.availability == "available"));
    if let Some(file_extension) = &details.file_extension {
        scope
            .entry("target_extension".to_string())
            .or_insert_with(|| json!(file_extension));
    }
    if let Some(parent) = Path::new(&details.stored_target)
        .parent()
        .and_then(|value| value.to_str())
    {
        if !parent.is_empty() {
            scope
                .entry("target_parent".to_string())
                .or_insert_with(|| json!(parent));
        }
    }
    if let Some(canonical_target) = &details.canonical_target {
        scope
            .entry("canonical_target".to_string())
            .or_insert_with(|| json!(canonical_target));
    }
}

fn resolve_target_details(kind: &str, target: &str) -> anyhow::Result<TargetDetails> {
    match kind {
        "file_handle" | "directory_handle" => resolve_filesystem_target(kind, target),
        "export_target_handle" => {
            let path = expand_target(target)?;
            let path_text = path.display().to_string();
            Ok(TargetDetails {
                stored_target: path_text.clone(),
                target_path: path_text.clone(),
                target_hash: hash_target(&path_text),
                display_name: display_name(&path),
                target_kind: "export_target".to_string(),
                availability: "available".to_string(),
                canonical_target: None,
                file_extension: path
                    .extension()
                    .and_then(|value| value.to_str())
                    .map(ToOwned::to_owned),
            })
        }
        _ => Ok(TargetDetails {
            stored_target: target.to_string(),
            target_path: target.to_string(),
            target_hash: hash_target(target),
            display_name: target.to_string(),
            target_kind: kind.to_string(),
            availability: "available".to_string(),
            canonical_target: None,
            file_extension: None,
        }),
    }
}

fn resolve_filesystem_target(kind: &str, target: &str) -> anyhow::Result<TargetDetails> {
    let path = expand_target(target)?;
    let metadata = fs::symlink_metadata(&path)
        .with_context(|| format!("portal target does not exist: {}", path.display()))?;
    let file_type = metadata.file_type();
    if file_type.is_symlink() {
        anyhow::bail!(
            "portal handle targets cannot be symlinks: {}",
            path.display()
        );
    }
    if kind == "file_handle" && !file_type.is_file() {
        anyhow::bail!(
            "file_handle target is not a regular file: {}",
            path.display()
        );
    }
    if kind == "directory_handle" && !file_type.is_dir() {
        anyhow::bail!(
            "directory_handle target is not a directory: {}",
            path.display()
        );
    }

    let canonical = path.canonicalize().unwrap_or_else(|_| path.clone());
    let canonical_text = canonical.display().to_string();
    let path_text = path.display().to_string();
    Ok(TargetDetails {
        stored_target: path_text.clone(),
        target_path: path_text,
        target_hash: hash_target(&canonical_text),
        display_name: display_name(&path),
        target_kind: if file_type.is_dir() {
            "directory".to_string()
        } else {
            "file".to_string()
        },
        availability: "available".to_string(),
        canonical_target: Some(canonical_text),
        file_extension: path
            .extension()
            .and_then(|value| value.to_str())
            .map(ToOwned::to_owned),
    })
}

fn expand_target(target: &str) -> anyhow::Result<PathBuf> {
    if target.starts_with("~/") {
        let Some(home) = std::env::var_os("HOME") else {
            anyhow::bail!("HOME is not set; cannot resolve portal target {}", target);
        };
        return Ok(PathBuf::from(home).join(target.trim_start_matches("~/")));
    }

    let path = PathBuf::from(target);
    if path.is_absolute() {
        return Ok(path);
    }

    std::env::current_dir()
        .map(|current_dir| current_dir.join(path))
        .with_context(|| format!("failed to resolve portal target {}", target))
}

fn display_name(path: &Path) -> String {
    path.file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .unwrap_or_else(|| path.display().to_string())
}

fn load_handle(path: &Path) -> anyhow::Result<PortalHandleRecord> {
    let content = fs::read_to_string(path)
        .with_context(|| format!("failed to read portal handle {}", path.display()))?;
    serde_json::from_str(&content)
        .with_context(|| format!("invalid portal handle {}", path.display()))
}

fn collect_handle_files(root: &Path) -> anyhow::Result<Vec<PathBuf>> {
    if !root.exists() {
        return Ok(Vec::new());
    }

    let mut files = fs::read_dir(root)?
        .filter_map(|entry| entry.ok().map(|item| item.path()))
        .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    files.sort();
    Ok(files)
}

fn is_expired(handle: &PortalHandleRecord) -> bool {
    chrono::DateTime::parse_from_rfc3339(&handle.expiry)
        .map(|expiry| expiry.with_timezone(&Utc) <= Utc::now())
        .unwrap_or(false)
}

fn hash_target(target: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(target.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn matches_binding(
    handle: &PortalHandleRecord,
    session_id: Option<&str>,
    user_id: Option<&str>,
) -> bool {
    if let Some(session_id) = session_id {
        if handle.session_id != session_id {
            return false;
        }
    }
    if let Some(user_id) = user_id {
        if handle.user_id != user_id {
            return false;
        }
    }

    true
}

fn write_json<T>(path: &Path, value: &T) -> anyhow::Result<()>
where
    T: serde::Serialize,
{
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    fs::write(path, serde_json::to_vec_pretty(value)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{load_handle, write_json, Portal, PortalConfig};
    use aios_contracts::{
        PortalIssueHandleRequest, PortalLookupHandleRequest, PortalRevokeHandleRequest,
    };
    use chrono::Utc;
    use serde_json::json;

    fn temp_state_dir(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "aios-portal-{name}-{}-{}",
            std::process::id(),
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn issue_request(
        session_id: &str,
        kind: &str,
        target: &str,
        revocable: bool,
    ) -> PortalIssueHandleRequest {
        PortalIssueHandleRequest {
            kind: kind.to_string(),
            user_id: "user-1".to_string(),
            session_id: session_id.to_string(),
            target: target.to_string(),
            scope: std::collections::BTreeMap::from([
                ("display_name".to_string(), json!(target)),
                ("backend".to_string(), json!("test-backend")),
            ]),
            expiry_seconds: Some(60),
            revocable,
            audit_tags: vec!["portal".to_string(), kind.to_string()],
        }
    }

    #[test]
    fn issues_looks_up_and_filters_handles_by_session() {
        let state_dir = temp_state_dir("issue-list");
        let portal = Portal::new(PortalConfig {
            state_dir: state_dir.clone(),
            default_ttl_seconds: 60,
        })
        .unwrap();

        let first = portal
            .issue_handle(&issue_request(
                "session-a",
                "screen_share_handle",
                "display-1",
                true,
            ))
            .unwrap();
        let second = portal
            .issue_handle(&issue_request(
                "session-b",
                "export_target_handle",
                "/tmp/report.pdf",
                true,
            ))
            .unwrap();

        let looked_up = portal
            .lookup_handle(&PortalLookupHandleRequest {
                handle_id: first.handle_id.clone(),
                session_id: Some("session-a".to_string()),
                user_id: Some("user-1".to_string()),
            })
            .unwrap()
            .handle
            .unwrap();
        assert_eq!(looked_up.session_id, "session-a");
        assert_eq!(looked_up.scope.get("backend"), Some(&json!("test-backend")));

        let session_a = portal.list_handles(Some("session-a")).unwrap();
        assert_eq!(session_a.handles.len(), 1);
        assert_eq!(session_a.handles[0].handle_id, first.handle_id);

        let all = portal.list_handles(None).unwrap();
        assert_eq!(all.handles.len(), 2);
        assert!(all
            .handles
            .iter()
            .any(|handle| handle.handle_id == second.handle_id));

        std::fs::remove_dir_all(state_dir).unwrap();
    }

    #[test]
    fn list_marks_expired_handles_revoked() {
        let state_dir = temp_state_dir("expiry");
        let portal = Portal::new(PortalConfig {
            state_dir: state_dir.clone(),
            default_ttl_seconds: 60,
        })
        .unwrap();
        let target = state_dir.join("report.txt");
        std::fs::write(&target, "report").unwrap();

        let handle = portal
            .issue_handle(&issue_request(
                "session-a",
                "file_handle",
                &target.display().to_string(),
                true,
            ))
            .unwrap();
        let path = state_dir
            .join("handles")
            .join(format!("{}.json", handle.handle_id));
        let mut record = load_handle(&path).unwrap();
        record.expiry = "2000-01-01T00:00:00+00:00".to_string();
        write_json(&path, &record).unwrap();

        let listed = portal.list_handles(Some("session-a")).unwrap();
        assert_eq!(listed.handles.len(), 1);
        assert!(listed.handles[0].revoked_at.is_some());
        assert_eq!(
            listed.handles[0].revocation_reason.as_deref(),
            Some("expired")
        );

        std::fs::remove_dir_all(state_dir).unwrap();
    }

    #[test]
    fn refuses_to_revoke_non_revocable_handle() {
        let state_dir = temp_state_dir("non-revocable");
        let portal = Portal::new(PortalConfig {
            state_dir: state_dir.clone(),
            default_ttl_seconds: 60,
        })
        .unwrap();
        let target = state_dir.join("export");
        std::fs::create_dir_all(&target).unwrap();

        let handle = portal
            .issue_handle(&issue_request(
                "session-a",
                "directory_handle",
                &target.display().to_string(),
                false,
            ))
            .unwrap();

        let error = portal
            .revoke_handle(&PortalRevokeHandleRequest {
                handle_id: handle.handle_id.clone(),
                session_id: Some("session-a".to_string()),
                user_id: Some("user-1".to_string()),
                reason: Some("user-request".to_string()),
            })
            .unwrap_err();
        assert!(error.to_string().contains("not revocable"));

        std::fs::remove_dir_all(state_dir).unwrap();
    }

    #[test]
    fn file_and_directory_handles_enrich_scope_metadata() {
        let state_dir = temp_state_dir("scope-metadata");
        let portal = Portal::new(PortalConfig {
            state_dir: state_dir.clone(),
            default_ttl_seconds: 60,
        })
        .unwrap();
        let reports_dir = state_dir.join("reports");
        std::fs::create_dir_all(&reports_dir).unwrap();
        let file_target = reports_dir.join("final.md");
        std::fs::write(&file_target, "# demo").unwrap();
        let directory_target = reports_dir.join("archive");
        std::fs::create_dir_all(&directory_target).unwrap();

        let file_handle = portal
            .issue_handle(&PortalIssueHandleRequest {
                kind: "file_handle".to_string(),
                user_id: "user-1".to_string(),
                session_id: "session-a".to_string(),
                target: file_target.display().to_string(),
                scope: std::collections::BTreeMap::new(),
                expiry_seconds: Some(60),
                revocable: true,
                audit_tags: vec!["portal".to_string(), "file_handle".to_string()],
            })
            .unwrap();
        assert_eq!(
            file_handle.scope.get("display_name"),
            Some(&json!("final.md"))
        );
        assert_eq!(
            file_handle.scope.get("target_parent"),
            Some(&json!(reports_dir.display().to_string()))
        );
        assert_eq!(file_handle.scope.get("target_kind"), Some(&json!("file")));
        assert_eq!(
            file_handle.scope.get("availability"),
            Some(&json!("available"))
        );
        assert_eq!(
            file_handle.scope.get("handle_kind"),
            Some(&json!("file_handle"))
        );
        assert!(file_handle.scope.contains_key("target_hash"));

        let directory_handle = portal
            .issue_handle(&PortalIssueHandleRequest {
                kind: "directory_handle".to_string(),
                user_id: "user-1".to_string(),
                session_id: "session-a".to_string(),
                target: directory_target.display().to_string(),
                scope: std::collections::BTreeMap::new(),
                expiry_seconds: Some(60),
                revocable: true,
                audit_tags: vec!["portal".to_string(), "directory_handle".to_string()],
            })
            .unwrap();
        assert_eq!(
            directory_handle.scope.get("display_name"),
            Some(&json!("archive"))
        );
        assert_eq!(
            directory_handle.scope.get("target_parent"),
            Some(&json!(reports_dir.display().to_string()))
        );
        assert_eq!(
            directory_handle.scope.get("target_kind"),
            Some(&json!("directory"))
        );

        std::fs::remove_dir_all(state_dir).unwrap();
    }

    #[test]
    fn lookup_and_revoke_respect_session_binding() {
        let state_dir = temp_state_dir("binding");
        let portal = Portal::new(PortalConfig {
            state_dir: state_dir.clone(),
            default_ttl_seconds: 60,
        })
        .unwrap();
        let target = state_dir.join("report.txt");
        std::fs::write(&target, "report").unwrap();

        let handle = portal
            .issue_handle(&issue_request(
                "session-a",
                "file_handle",
                &target.display().to_string(),
                true,
            ))
            .unwrap();

        let denied_lookup = portal
            .lookup_handle(&PortalLookupHandleRequest {
                handle_id: handle.handle_id.clone(),
                session_id: Some("session-b".to_string()),
                user_id: Some("user-1".to_string()),
            })
            .unwrap();
        assert!(denied_lookup.handle.is_none());

        let denied_revoke = portal
            .revoke_handle(&PortalRevokeHandleRequest {
                handle_id: handle.handle_id.clone(),
                session_id: Some("session-b".to_string()),
                user_id: Some("user-1".to_string()),
                reason: Some("deny".to_string()),
            })
            .unwrap();
        assert!(denied_revoke.handle.is_none());

        let allowed_lookup = portal
            .lookup_handle(&PortalLookupHandleRequest {
                handle_id: handle.handle_id,
                session_id: Some("session-a".to_string()),
                user_id: Some("user-1".to_string()),
            })
            .unwrap();
        assert!(allowed_lookup.handle.is_some());

        std::fs::remove_dir_all(state_dir).unwrap();
    }
}
