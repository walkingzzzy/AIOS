use std::{
    ffi::OsStr,
    path::{Path, PathBuf},
};

use chrono::Utc;
use sha2::{Digest, Sha256};

use aios_contracts::{
    methods, ExecutionToken, PortalHandleRecord, ProviderFsBulkDeleteRequest, ProviderFsOpenRequest,
};

use crate::{clients, AppState};

#[derive(Debug, Clone)]
pub struct ResolvedTarget {
    pub handle: PortalHandleRecord,
    pub target_path: PathBuf,
    pub target_hash: String,
}

pub fn resolve_open_target(
    state: &AppState,
    request: &ProviderFsOpenRequest,
) -> anyhow::Result<ResolvedTarget> {
    resolve_target(
        state,
        &request.handle_id,
        &request.execution_token,
        methods::PROVIDER_FS_OPEN,
        &["file_handle", "directory_handle"],
        false,
    )
}

pub fn resolve_delete_target(
    state: &AppState,
    request: &ProviderFsBulkDeleteRequest,
) -> anyhow::Result<ResolvedTarget> {
    resolve_target(
        state,
        &request.handle_id,
        &request.execution_token,
        methods::SYSTEM_FILE_BULK_DELETE,
        &["file_handle", "directory_handle"],
        !request.dry_run,
    )
}

fn resolve_target(
    state: &AppState,
    handle_id: &str,
    token: &ExecutionToken,
    capability_id: &str,
    allowed_kinds: &[&str],
    consume: bool,
) -> anyhow::Result<ResolvedTarget> {
    let handle = clients::lookup_handle(state, handle_id, token)?;
    ensure_handle_available(&handle)?;
    ensure_handle_kind(&handle, allowed_kinds)?;
    ensure_token_context(token, &handle, capability_id)?;

    let target_hash = target_hash(&handle);
    let verification = clients::verify_token(state, token, &target_hash, consume)?;
    if !verification.valid {
        anyhow::bail!("execution token rejected: {}", verification.reason);
    }

    Ok(ResolvedTarget {
        target_path: expand_target(&handle.target)?,
        handle,
        target_hash,
    })
}

fn ensure_handle_available(handle: &PortalHandleRecord) -> anyhow::Result<()> {
    if let Some(revoked_at) = &handle.revoked_at {
        anyhow::bail!(
            "portal handle {} is revoked at {} ({})",
            handle.handle_id,
            revoked_at,
            handle
                .revocation_reason
                .clone()
                .unwrap_or_else(|| "unknown reason".to_string())
        );
    }

    let expiry = chrono::DateTime::parse_from_rfc3339(&handle.expiry)?.with_timezone(&Utc);
    if expiry <= Utc::now() {
        anyhow::bail!("portal handle {} is expired", handle.handle_id);
    }

    Ok(())
}

fn ensure_handle_kind(handle: &PortalHandleRecord, allowed_kinds: &[&str]) -> anyhow::Result<()> {
    if allowed_kinds.iter().any(|kind| *kind == handle.kind) {
        return Ok(());
    }

    anyhow::bail!(
        "portal handle {} kind {} is unsupported for this operation",
        handle.handle_id,
        handle.kind
    )
}

fn ensure_token_context(
    token: &ExecutionToken,
    handle: &PortalHandleRecord,
    capability_id: &str,
) -> anyhow::Result<()> {
    if token.user_id != handle.user_id {
        anyhow::bail!("execution token user does not match portal handle user");
    }
    if token.session_id != handle.session_id {
        anyhow::bail!("execution token session does not match portal handle session");
    }
    if token.capability_id != capability_id {
        anyhow::bail!(
            "execution token capability {} does not match {}",
            token.capability_id,
            capability_id
        );
    }
    if token.execution_location != "local" {
        anyhow::bail!("system-files provider only supports local execution tokens");
    }

    Ok(())
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

    anyhow::bail!(
        "system-files provider requires an absolute or ~/ target path, got {}",
        target
    )
}

pub fn target_hash(handle: &PortalHandleRecord) -> String {
    handle
        .scope
        .get("target_hash")
        .and_then(|value| value.as_str())
        .map(|value| value.to_string())
        .unwrap_or_else(|| hash_target(&handle.target))
}

pub fn dangerous_target(path: &Path) -> bool {
    let Some(path_text) = path.to_str() else {
        return true;
    };

    if [
        "/",
        "/Users",
        "/System",
        "/Applications",
        "/Library",
        "/usr",
        "/bin",
        "/sbin",
        "/etc",
        "/var",
    ]
    .iter()
    .any(|candidate| *candidate == path_text)
    {
        return true;
    }

    std::env::var_os("HOME")
        .map(PathBuf::from)
        .is_some_and(|home| home == path)
}

pub fn classify_file_type(file_type: &std::fs::FileType) -> &'static str {
    if file_type.is_file() {
        return "file";
    }
    if file_type.is_dir() {
        return "directory";
    }
    if file_type.is_symlink() {
        return "symlink";
    }
    "other"
}

pub fn file_name(path: &Path) -> String {
    path.file_name()
        .unwrap_or_else(|| OsStr::new(""))
        .to_string_lossy()
        .into_owned()
}

fn hash_target(target: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(target.as_bytes());
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use std::{
        collections::BTreeMap,
        path::PathBuf,
        sync::{Mutex, OnceLock},
    };

    use serde_json::json;

    use super::*;

    fn handle() -> PortalHandleRecord {
        let mut scope = BTreeMap::new();
        scope.insert("target_hash".to_string(), json!("abc123"));

        PortalHandleRecord {
            handle_id: "ph-1".to_string(),
            kind: "file_handle".to_string(),
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            target: "/tmp/demo.txt".to_string(),
            scope,
            expiry: "2099-01-01T00:00:00Z".to_string(),
            revocable: true,
            issued_at: "2026-01-01T00:00:00Z".to_string(),
            revoked_at: None,
            revocation_reason: None,
            audit_tags: vec![],
        }
    }

    fn home_env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    fn token(capability_id: &str) -> ExecutionToken {
        ExecutionToken {
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: capability_id.to_string(),
            target_hash: Some("abc123".to_string()),
            expiry: "2099-01-01T00:00:00Z".to_string(),
            approval_ref: None,
            constraints: BTreeMap::new(),
            execution_location: "local".to_string(),
            taint_summary: None,
            signature: Some("sig".to_string()),
        }
    }

    #[test]
    fn target_hash_prefers_scope_value() {
        assert_eq!(target_hash(&handle()), "abc123".to_string());
    }

    #[test]
    fn dangerous_target_rejects_root_and_home() {
        let _guard = home_env_lock().lock().expect("lock HOME env");
        let previous_home = std::env::var_os("HOME");

        assert!(dangerous_target(Path::new("/")));
        std::env::set_var("HOME", "/tmp/home-scope-test");
        assert!(dangerous_target(Path::new("/tmp/home-scope-test")));
        assert!(!dangerous_target(Path::new(
            "/tmp/home-scope-test/docs/report.txt"
        )));

        match previous_home {
            Some(value) => std::env::set_var("HOME", value),
            None => std::env::remove_var("HOME"),
        }
    }

    #[test]
    fn ensure_token_context_rejects_capability_mismatch() {
        let error = ensure_token_context(
            &token(methods::SYSTEM_FILE_BULK_DELETE),
            &handle(),
            methods::PROVIDER_FS_OPEN,
        )
        .expect_err("capability mismatch should fail");
        assert!(error.to_string().contains("does not match"));
    }

    #[test]
    fn expand_target_supports_home_paths() {
        let _guard = home_env_lock().lock().expect("lock HOME env");
        let previous_home = std::env::var_os("HOME");

        std::env::set_var("HOME", "/tmp/home-scope-expand");
        assert_eq!(
            expand_target("~/notes.txt").expect("expand target"),
            PathBuf::from("/tmp/home-scope-expand/notes.txt")
        );

        match previous_home {
            Some(value) => std::env::set_var("HOME", value),
            None => std::env::remove_var("HOME"),
        }
    }
}
