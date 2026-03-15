use std::{
    fs::{self, File},
    io::Read,
    path::Path,
};

use serde_json::Value;

use aios_contracts::{
    ProviderFsBulkDeleteRequest, ProviderFsBulkDeleteResponse, ProviderFsEntry,
    ProviderFsOpenRequest, ProviderFsOpenResponse,
};

use crate::{scope, AppState};

pub fn open_target(
    state: &AppState,
    request: &ProviderFsOpenRequest,
) -> anyhow::Result<ProviderFsOpenResponse> {
    let _permit = state.concurrency_budget.try_acquire("provider.fs.open")?;
    let resolved = scope::resolve_open_target(state, request)?;
    let metadata = fs::symlink_metadata(&resolved.target_path)?;
    let file_type = metadata.file_type();
    let object_kind = scope::classify_file_type(&file_type).to_string();

    if file_type.is_symlink() {
        anyhow::bail!("system-files provider does not follow symlink targets");
    }

    let mut response = ProviderFsOpenResponse {
        provider_id: state.config.provider_id.clone(),
        handle: resolved.handle.clone(),
        object_kind: object_kind.clone(),
        target_path: resolved.target_path.display().to_string(),
        target_hash: resolved.target_hash,
        size_bytes: metadata.is_file().then_some(metadata.len()),
        entries: Vec::new(),
        content_preview: None,
        truncated: false,
    };

    if metadata.is_file() {
        if request.include_content {
            let max_bytes = request
                .max_bytes
                .unwrap_or(state.config.max_preview_bytes)
                .min(state.config.max_preview_bytes);
            let (content_preview, truncated) = read_preview(&resolved.target_path, max_bytes)?;
            response.content_preview = Some(content_preview);
            response.truncated = truncated;
        }
        record_open_audit(state, request, &response);
        return Ok(response);
    }

    if metadata.is_dir() {
        let max_entries = request
            .max_entries
            .unwrap_or(state.config.max_directory_entries)
            .min(state.config.max_directory_entries) as usize;
        let mut entries = fs::read_dir(&resolved.target_path)?
            .filter_map(|entry| entry.ok().map(|item| item.path()))
            .map(|path| {
                let metadata = fs::symlink_metadata(&path)?;
                Ok(ProviderFsEntry {
                    name: scope::file_name(&path),
                    path: path.display().to_string(),
                    kind: scope::classify_file_type(&metadata.file_type()).to_string(),
                })
            })
            .collect::<anyhow::Result<Vec<_>>>()?;
        entries.sort_by(|left, right| left.path.cmp(&right.path));
        response.truncated = entries.len() > max_entries;
        entries.truncate(max_entries);
        response.entries = entries;
        record_open_audit(state, request, &response);
        return Ok(response);
    }

    anyhow::bail!("system-files provider only supports file and directory targets")
}

pub fn bulk_delete(
    state: &AppState,
    request: &ProviderFsBulkDeleteRequest,
) -> anyhow::Result<ProviderFsBulkDeleteResponse> {
    let _permit = state
        .concurrency_budget
        .try_acquire("system.file.bulk_delete")?;
    let resolved = scope::resolve_delete_target(state, request)?;

    let response = if scope::dangerous_target(&resolved.target_path) {
        ProviderFsBulkDeleteResponse {
            provider_id: state.config.provider_id.clone(),
            handle: resolved.handle,
            target_path: resolved.target_path.display().to_string(),
            dry_run: request.dry_run,
            status: "skipped".to_string(),
            affected_paths: Vec::new(),
            reason: Some("dangerous target path".to_string()),
        }
    } else {
        let metadata = match fs::symlink_metadata(&resolved.target_path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let response = ProviderFsBulkDeleteResponse {
                    provider_id: state.config.provider_id.clone(),
                    handle: resolved.handle,
                    target_path: resolved.target_path.display().to_string(),
                    dry_run: request.dry_run,
                    status: "skipped".to_string(),
                    affected_paths: Vec::new(),
                    reason: Some("target path does not exist".to_string()),
                };
                record_delete_audit(state, request, &response);
                return Ok(response);
            }
            Err(error) => return Err(error.into()),
        };

        if metadata.file_type().is_symlink() {
            ProviderFsBulkDeleteResponse {
                provider_id: state.config.provider_id.clone(),
                handle: resolved.handle,
                target_path: resolved.target_path.display().to_string(),
                dry_run: request.dry_run,
                status: "skipped".to_string(),
                affected_paths: Vec::new(),
                reason: Some("symlink targets are not deletable".to_string()),
            }
        } else if metadata.is_dir() && !request.recursive {
            ProviderFsBulkDeleteResponse {
                provider_id: state.config.provider_id.clone(),
                handle: resolved.handle,
                target_path: resolved.target_path.display().to_string(),
                dry_run: request.dry_run,
                status: "skipped".to_string(),
                affected_paths: vec![resolved.target_path.display().to_string()],
                reason: Some("directory deletion requires recursive=true".to_string()),
            }
        } else {
            let affected_paths = collect_affected_paths(
                &resolved.target_path,
                request.recursive,
                state.config.max_delete_affected_paths as usize + 1,
            )?;

            if let Some(response) =
                enforce_delete_constraints(state, request, &resolved, &metadata, &affected_paths)
            {
                response
            } else if request.dry_run {
                ProviderFsBulkDeleteResponse {
                    provider_id: state.config.provider_id.clone(),
                    handle: resolved.handle,
                    target_path: resolved.target_path.display().to_string(),
                    dry_run: true,
                    status: "would-delete".to_string(),
                    affected_paths,
                    reason: None,
                }
            } else {
                if metadata.is_dir() {
                    fs::remove_dir_all(&resolved.target_path)?;
                } else {
                    fs::remove_file(&resolved.target_path)?;
                }

                ProviderFsBulkDeleteResponse {
                    provider_id: state.config.provider_id.clone(),
                    handle: resolved.handle,
                    target_path: resolved.target_path.display().to_string(),
                    dry_run: false,
                    status: "deleted".to_string(),
                    affected_paths,
                    reason: None,
                }
            }
        }
    };

    record_delete_audit(state, request, &response);
    Ok(response)
}

fn enforce_delete_constraints(
    state: &AppState,
    request: &ProviderFsBulkDeleteRequest,
    resolved: &scope::ResolvedTarget,
    metadata: &fs::Metadata,
    affected_paths: &[String],
) -> Option<ProviderFsBulkDeleteResponse> {
    if request.execution_token.approval_ref.is_none() {
        return Some(skip_delete_response(
            state,
            request,
            resolved,
            Vec::new(),
            "delete execution token must include approval_ref",
        ));
    }

    if metadata.is_dir()
        && !constraint_flag(
            &request.execution_token.constraints,
            "allow_directory_delete",
        )
    {
        return Some(skip_delete_response(
            state,
            request,
            resolved,
            vec![resolved.target_path.display().to_string()],
            "directory deletion requires allow_directory_delete=true constraint",
        ));
    }

    if request.recursive
        && !constraint_flag(&request.execution_token.constraints, "allow_recursive")
    {
        return Some(skip_delete_response(
            state,
            request,
            resolved,
            vec![resolved.target_path.display().to_string()],
            "recursive deletion requires allow_recursive=true constraint",
        ));
    }

    let max_allowed = constraint_u64(&request.execution_token.constraints, "max_affected_paths")
        .unwrap_or(state.config.max_delete_affected_paths as u64)
        .min(state.config.max_delete_affected_paths as u64);
    if affected_paths.len() as u64 > max_allowed {
        return Some(skip_delete_response(
            state,
            request,
            resolved,
            affected_paths.to_vec(),
            &format!(
                "delete scope exceeds max_affected_paths constraint: affected={} max={} ",
                affected_paths.len(),
                max_allowed
            )
            .trim()
            .to_string(),
        ));
    }

    None
}

fn skip_delete_response(
    state: &AppState,
    request: &ProviderFsBulkDeleteRequest,
    resolved: &scope::ResolvedTarget,
    affected_paths: Vec<String>,
    reason: &str,
) -> ProviderFsBulkDeleteResponse {
    ProviderFsBulkDeleteResponse {
        provider_id: state.config.provider_id.clone(),
        handle: resolved.handle.clone(),
        target_path: resolved.target_path.display().to_string(),
        dry_run: request.dry_run,
        status: "skipped".to_string(),
        affected_paths,
        reason: Some(reason.to_string()),
    }
}

fn constraint_flag(constraints: &std::collections::BTreeMap<String, Value>, key: &str) -> bool {
    constraints
        .get(key)
        .and_then(Value::as_bool)
        .unwrap_or(false)
}

fn constraint_u64(
    constraints: &std::collections::BTreeMap<String, Value>,
    key: &str,
) -> Option<u64> {
    constraints.get(key).and_then(Value::as_u64)
}

fn record_open_audit(
    state: &AppState,
    request: &ProviderFsOpenRequest,
    response: &ProviderFsOpenResponse,
) {
    if let Err(error) = state
        .audit_writer
        .append_open(&request.execution_token, response)
    {
        tracing::warn!(?error, "failed to append provider open audit entry");
    }
}

fn record_delete_audit(
    state: &AppState,
    request: &ProviderFsBulkDeleteRequest,
    response: &ProviderFsBulkDeleteResponse,
) {
    if let Err(error) = state
        .audit_writer
        .append_delete(&request.execution_token, response)
    {
        tracing::warn!(?error, "failed to append provider delete audit entry");
    }
}

fn read_preview(path: &Path, max_bytes: u64) -> anyhow::Result<(String, bool)> {
    let mut file = File::open(path)?;
    let mut buffer = vec![0_u8; max_bytes as usize];
    let bytes_read = file.read(&mut buffer)?;
    buffer.truncate(bytes_read);
    let metadata_len = file.metadata()?.len();
    Ok((
        String::from_utf8_lossy(&buffer).into_owned(),
        metadata_len > bytes_read as u64,
    ))
}

fn collect_affected_paths(
    path: &Path,
    recursive: bool,
    limit: usize,
) -> anyhow::Result<Vec<String>> {
    let mut affected_paths = Vec::new();
    collect_path(path, recursive, limit, &mut affected_paths)?;
    Ok(affected_paths)
}

fn collect_path(
    path: &Path,
    recursive: bool,
    limit: usize,
    output: &mut Vec<String>,
) -> anyhow::Result<()> {
    if output.len() >= limit {
        return Ok(());
    }

    output.push(path.display().to_string());

    let metadata = fs::symlink_metadata(path)?;
    if metadata.is_dir() && recursive {
        let mut entries = fs::read_dir(path)?
            .filter_map(|entry| entry.ok().map(|item| item.path()))
            .collect::<Vec<_>>();
        entries.sort();
        for entry in entries {
            collect_path(&entry, true, limit, output)?;
            if output.len() >= limit {
                break;
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use std::{fs, path::PathBuf};

    use uuid::Uuid;

    use super::*;

    fn temp_root() -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "aios-system-files-provider-test-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&root).expect("create temp root");
        root
    }

    #[test]
    fn collect_affected_paths_includes_children_when_recursive() {
        let root = temp_root();
        let child = root.join("child.txt");
        fs::write(&child, "demo").expect("write child");

        let paths = collect_affected_paths(&root, true, 32).expect("collect paths");
        assert!(paths.iter().any(|path| path == &root.display().to_string()));
        assert!(paths
            .iter()
            .any(|path| path == &child.display().to_string()));

        fs::remove_dir_all(&root).expect("cleanup temp root");
    }

    #[test]
    fn read_preview_reports_truncation() {
        let root = temp_root();
        let file = root.join("preview.txt");
        fs::write(&file, "1234567890").expect("write preview file");

        let (preview, truncated) = read_preview(&file, 4).expect("read preview");
        assert_eq!(preview, "1234".to_string());
        assert!(truncated);

        fs::remove_dir_all(&root).expect("cleanup temp root");
    }
}
