use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

use chrono::Utc;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use aios_contracts::ExecutionToken;

#[derive(Debug, Clone)]
pub struct TokenUsageStore {
    dir: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TokenUsageRecord {
    consumed_at: String,
    capability_id: String,
    user_id: String,
    session_id: String,
    task_id: String,
    execution_location: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    target_hash: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    approval_ref: Option<String>,
    token_signature: String,
}

#[derive(Debug, Clone)]
pub struct TokenConsumeResult {
    pub consumed: bool,
}

impl TokenUsageStore {
    pub fn new(dir: PathBuf) -> anyhow::Result<Self> {
        ensure_secure_dir(&dir)?;
        Ok(Self { dir })
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }

    pub fn is_consumed(&self, token: &ExecutionToken) -> anyhow::Result<bool> {
        Ok(self.record_path(token)?.exists())
    }

    pub fn consume(&self, token: &ExecutionToken) -> anyhow::Result<TokenConsumeResult> {
        let path = self.record_path(token)?;
        let signature = token
            .signature
            .as_deref()
            .ok_or_else(|| anyhow::anyhow!("token signature missing"))?;

        let payload = serde_json::to_vec_pretty(&TokenUsageRecord {
            consumed_at: Utc::now().to_rfc3339(),
            capability_id: token.capability_id.clone(),
            user_id: token.user_id.clone(),
            session_id: token.session_id.clone(),
            task_id: token.task_id.clone(),
            execution_location: token.execution_location.clone(),
            target_hash: token.target_hash.clone(),
            approval_ref: token.approval_ref.clone(),
            token_signature: signature.to_string(),
        })?;

        match open_record_file(&path) {
            Ok(mut file) => {
                file.write_all(&payload)?;
                file.write_all(b"\n")?;
                file.sync_all()?;
                tighten_file_permissions(&path)?;
                Ok(TokenConsumeResult { consumed: true })
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                Ok(TokenConsumeResult { consumed: false })
            }
            Err(error) => Err(error.into()),
        }
    }

    pub fn consumed_count(&self) -> anyhow::Result<usize> {
        if !self.dir.exists() {
            return Ok(0);
        }
        Ok(fs::read_dir(&self.dir)?
            .filter_map(Result::ok)
            .filter(|entry| {
                entry
                    .path()
                    .extension()
                    .and_then(|value| value.to_str())
                    .is_some_and(|value| value == "json")
            })
            .count())
    }

    fn record_path(&self, token: &ExecutionToken) -> anyhow::Result<PathBuf> {
        let signature = token
            .signature
            .as_deref()
            .ok_or_else(|| anyhow::anyhow!("token signature missing"))?;
        let mut hasher = Sha256::new();
        hasher.update(signature.as_bytes());
        let digest = hasher.finalize();
        Ok(self
            .dir
            .join(format!("{}.json", hex_digest(&digest))))
    }
}

fn hex_digest(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn open_record_file(path: &Path) -> std::io::Result<fs::File> {
    let mut options = OpenOptions::new();
    options.create_new(true).write(true);

    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }

    options.open(path)
}

fn ensure_secure_dir(path: &Path) -> anyhow::Result<()> {
    fs::create_dir_all(path)?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }

    Ok(())
}

fn tighten_file_permissions(path: &Path) -> anyhow::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }

    Ok(())
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
                "aios-policyd-token-usage-test-{}",
                uuid::Uuid::new_v4().simple()
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

    fn token(signature: &str) -> ExecutionToken {
        ExecutionToken {
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: "system.file.bulk_delete".to_string(),
            target_hash: Some("sha256:abc".to_string()),
            expiry: "2099-01-01T00:00:00Z".to_string(),
            approval_ref: Some("approval-1".to_string()),
            constraints: Default::default(),
            execution_location: "local".to_string(),
            taint_summary: None,
            signature: Some(signature.to_string()),
        }
    }

    #[test]
    fn consume_records_first_use_and_rejects_reuse() -> anyhow::Result<()> {
        let temp = TempDir::new()?;
        let store = TokenUsageStore::new(temp.path().join("usage"))?;
        let token = token("sig-1");

        assert!(!store.is_consumed(&token)?);
        assert!(store.consume(&token)?.consumed);
        assert!(store.is_consumed(&token)?);
        assert!(!store.consume(&token)?.consumed);
        assert_eq!(store.consumed_count()?, 1);
        Ok(())
    }
}
