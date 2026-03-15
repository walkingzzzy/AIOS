use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
};

use chrono::{DateTime, Duration, Utc};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use aios_contracts::{ExecutionToken, TokenIssueRequest, TokenVerifyRequest, TokenVerifyResponse};

pub fn ensure_key(path: &Path) -> anyhow::Result<String> {
    if let Some(parent) = path.parent() {
        ensure_secure_parent_dir(parent)?;
    }

    if path.exists() {
        validate_key_path(path)?;
        tighten_key_permissions(path)?;

        if let Ok(existing) = fs::read_to_string(path) {
            let trimmed = existing.trim();
            if !trimmed.is_empty() {
                return Ok(trimmed.to_string());
            }
        }
    }

    let key = Uuid::new_v4().simple().to_string();
    write_key_atomic(path, &key)?;
    Ok(key)
}

pub fn key_fingerprint(signing_key: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(signing_key.as_bytes());
    let digest = hasher.finalize();
    digest[..6]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn validate_key_path(path: &Path) -> anyhow::Result<()> {
    let metadata = fs::symlink_metadata(path)?;
    let file_type = metadata.file_type();
    if file_type.is_symlink() {
        anyhow::bail!("token key path cannot be a symlink: {}", path.display());
    }
    if !file_type.is_file() {
        anyhow::bail!("token key path must be a regular file: {}", path.display());
    }

    Ok(())
}

fn ensure_secure_parent_dir(path: &Path) -> anyhow::Result<()> {
    fs::create_dir_all(path)?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }

    Ok(())
}

fn tighten_key_permissions(path: &Path) -> anyhow::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }

    Ok(())
}

fn write_key_atomic(path: &Path, key: &str) -> anyhow::Result<()> {
    let temp_path = temp_key_path(path);
    let payload = format!("{key}\n");

    let mut file = open_temp_file(&temp_path)?;
    file.write_all(payload.as_bytes())?;
    file.sync_all()?;
    drop(file);

    tighten_key_permissions(&temp_path)?;
    fs::rename(&temp_path, path)?;
    tighten_key_permissions(path)?;
    Ok(())
}

fn temp_key_path(path: &Path) -> PathBuf {
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("token.key");
    path.with_file_name(format!(".{file_name}.{}.tmp", Uuid::new_v4().simple()))
}

fn open_temp_file(path: &Path) -> anyhow::Result<fs::File> {
    let mut options = fs::OpenOptions::new();
    options.create_new(true).write(true);

    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }

    Ok(options.open(path)?)
}

pub fn issue(
    request: TokenIssueRequest,
    ttl_seconds: u64,
    signing_key: &str,
) -> anyhow::Result<ExecutionToken> {
    let expiry = Utc::now() + Duration::seconds(ttl_seconds as i64);

    let mut token = ExecutionToken {
        user_id: request.user_id,
        session_id: request.session_id,
        task_id: request.task_id,
        capability_id: request.capability_id,
        target_hash: request.target_hash,
        expiry: expiry.to_rfc3339(),
        approval_ref: request.approval_ref,
        constraints: request.constraints,
        execution_location: request.execution_location,
        taint_summary: request.taint_summary,
        signature: None,
    };

    token.signature = Some(sign(&token, signing_key)?);
    Ok(token)
}

pub fn verify(
    request: &TokenVerifyRequest,
    signing_key: &str,
) -> anyhow::Result<TokenVerifyResponse> {
    let token = &request.token;

    let Some(signature) = token.signature.as_deref() else {
        return Ok(TokenVerifyResponse {
            valid: false,
            reason: "missing token signature".to_string(),
            consumed: false,
            consume_applied: false,
        });
    };

    let expected = sign(token, signing_key)?;
    if signature != expected {
        return Ok(TokenVerifyResponse {
            valid: false,
            reason: "token signature mismatch".to_string(),
            consumed: false,
            consume_applied: false,
        });
    }

    if let Some(expected_hash) = request.target_hash.as_deref() {
        if token.target_hash.as_deref() != Some(expected_hash) {
            return Ok(TokenVerifyResponse {
                valid: false,
                reason: "target hash mismatch".to_string(),
                consumed: false,
                consume_applied: false,
            });
        }
    }

    let expiry = DateTime::parse_from_rfc3339(&token.expiry)?.with_timezone(&Utc);
    if expiry <= Utc::now() {
        return Ok(TokenVerifyResponse {
            valid: false,
            reason: "token expired".to_string(),
            consumed: false,
            consume_applied: false,
        });
    }

    Ok(TokenVerifyResponse {
        valid: true,
        reason: "token is valid".to_string(),
        consumed: false,
        consume_applied: false,
    })
}

fn sign(token: &ExecutionToken, signing_key: &str) -> anyhow::Result<String> {
    let payload = serde_json::json!({
        "user_id": token.user_id,
        "session_id": token.session_id,
        "task_id": token.task_id,
        "capability_id": token.capability_id,
        "target_hash": token.target_hash,
        "expiry": token.expiry,
        "approval_ref": token.approval_ref,
        "constraints": token.constraints,
        "execution_location": token.execution_location,
        "taint_summary": token.taint_summary,
    });

    let mut hasher = Sha256::new();
    hasher.update(signing_key.as_bytes());
    hasher.update(serde_json::to_vec(&payload)?);
    let digest = hasher.finalize();
    Ok(digest.iter().map(|byte| format!("{byte:02x}")).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TempDir {
        path: PathBuf,
    }

    impl TempDir {
        fn new() -> anyhow::Result<Self> {
            let path = std::env::temp_dir().join(format!(
                "aios-policyd-token-test-{}",
                Uuid::new_v4().simple()
            ));
            fs::create_dir_all(&path)?;
            Ok(Self { path })
        }

        fn path(&self) -> &Path {
            &self.path
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    #[test]
    fn ensure_key_creates_key_and_returns_fingerprint() -> anyhow::Result<()> {
        let temp = TempDir::new()?;
        let key_path = temp.path().join("policyd").join("token.key");

        let key = ensure_key(&key_path)?;

        assert_eq!(key.len(), 32);
        assert_eq!(key, fs::read_to_string(&key_path)?.trim());
        assert_eq!(key_fingerprint(&key).len(), 12);

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;

            let metadata = fs::metadata(&key_path)?;
            assert_eq!(metadata.permissions().mode() & 0o777, 0o600);

            let parent_metadata = fs::metadata(key_path.parent().expect("parent"))?;
            assert_eq!(parent_metadata.permissions().mode() & 0o777, 0o700);
        }

        Ok(())
    }

    #[test]
    fn ensure_key_tightens_existing_permissions() -> anyhow::Result<()> {
        let temp = TempDir::new()?;
        let key_path = temp.path().join("token.key");
        fs::write(&key_path, "existing-key\n")?;

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&key_path, fs::Permissions::from_mode(0o644))?;
        }

        let key = ensure_key(&key_path)?;
        assert_eq!(key, "existing-key");

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let metadata = fs::metadata(&key_path)?;
            assert_eq!(metadata.permissions().mode() & 0o777, 0o600);
        }

        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn ensure_key_rejects_symlink_path() -> anyhow::Result<()> {
        use std::os::unix::fs::symlink;

        let temp = TempDir::new()?;
        let real_key = temp.path().join("real.key");
        let symlink_key = temp.path().join("token.key");
        fs::write(&real_key, "linked-key\n")?;
        symlink(&real_key, &symlink_key)?;

        let error = ensure_key(&symlink_key).expect_err("symlink key path should fail");
        assert!(error
            .to_string()
            .contains("token key path cannot be a symlink"));

        Ok(())
    }
}
