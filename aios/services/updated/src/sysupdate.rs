use std::{path::PathBuf, process::Command};

#[derive(Debug, Clone)]
pub struct BackendConfig {
    pub binary: String,
    pub definitions_dir: PathBuf,
    pub root: Option<PathBuf>,
    pub component: Option<String>,
    pub extra_args: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct SysupdateCheck {
    pub available: Option<bool>,
    pub next_version: Option<String>,
    pub notes: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct SysupdateApply {
    pub success: bool,
    pub notes: Vec<String>,
}

pub fn check(
    config: &BackendConfig,
    environment: &[(String, String)],
) -> anyhow::Result<SysupdateCheck> {
    let mut notes = Vec::new();
    let check_output = run(config, "check-new", environment)?;
    notes.extend(notes_for(
        "systemd_sysupdate_check",
        &rendered_command(config, "check-new"),
        &check_output,
    ));

    let available = if check_output.success {
        Some(true)
    } else if check_output.exit_code == Some(1) {
        Some(false)
    } else {
        None
    };

    let mut next_version = first_version_like_line(&check_output.stdout);
    let list_output = run(config, "list", environment)?;
    notes.extend(notes_for(
        "systemd_sysupdate_list",
        &rendered_command(config, "list"),
        &list_output,
    ));
    if next_version.is_none() {
        next_version = first_version_like_line(&list_output.stdout);
    }

    Ok(SysupdateCheck {
        available,
        next_version,
        notes,
    })
}

pub fn apply(
    config: &BackendConfig,
    environment: &[(String, String)],
) -> anyhow::Result<SysupdateApply> {
    let output = run(config, "update", environment)?;
    Ok(SysupdateApply {
        success: output.success,
        notes: notes_for(
            "systemd_sysupdate_apply",
            &rendered_command(config, "update"),
            &output,
        ),
    })
}

#[derive(Debug, Clone)]
struct ShellOutput {
    success: bool,
    exit_code: Option<i32>,
    stdout: String,
    stderr: String,
}

fn run(
    config: &BackendConfig,
    subcommand: &str,
    environment: &[(String, String)],
) -> anyhow::Result<ShellOutput> {
    let mut command = Command::new(&config.binary);
    push_backend_args(&mut command, config);
    command.arg(subcommand);
    for (key, value) in environment {
        command.env(key, value);
    }
    let output = command.output()?;
    Ok(ShellOutput {
        success: output.status.success(),
        exit_code: output.status.code(),
        stdout: String::from_utf8_lossy(&output.stdout).trim().to_string(),
        stderr: String::from_utf8_lossy(&output.stderr).trim().to_string(),
    })
}

fn push_backend_args(command: &mut Command, config: &BackendConfig) {
    command.arg("--definitions").arg(&config.definitions_dir);
    if let Some(root) = &config.root {
        command.arg("--root").arg(root);
    }
    if let Some(component) = &config.component {
        command.arg("--component").arg(component);
    }
    command.args(&config.extra_args);
}

fn rendered_command(config: &BackendConfig, subcommand: &str) -> String {
    let mut parts = vec![config.binary.clone()];
    parts.push("--definitions".to_string());
    parts.push(config.definitions_dir.display().to_string());
    if let Some(root) = &config.root {
        parts.push("--root".to_string());
        parts.push(root.display().to_string());
    }
    if let Some(component) = &config.component {
        parts.push("--component".to_string());
        parts.push(component.clone());
    }
    parts.extend(config.extra_args.iter().cloned());
    parts.push(subcommand.to_string());
    parts.join(" ")
}

fn notes_for(prefix: &str, command: &str, output: &ShellOutput) -> Vec<String> {
    let mut notes = vec![
        format!("{prefix}_command={command}"),
        format!("{prefix}_success={}", output.success),
        format!("{prefix}_exit_code={:?}", output.exit_code),
    ];
    if !output.stdout.is_empty() {
        notes.push(format!("{prefix}_stdout={}", truncate(&output.stdout)));
    }
    if !output.stderr.is_empty() {
        notes.push(format!("{prefix}_stderr={}", truncate(&output.stderr)));
    }
    notes
}

fn first_version_like_line(stdout: &str) -> Option<String> {
    stdout
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .find_map(|line| {
            line.split_whitespace()
                .rev()
                .find(|token| token.chars().any(|ch| ch.is_ascii_digit()))
                .map(ToOwned::to_owned)
                .or_else(|| Some(line.to_string()))
        })
}

fn truncate(value: &str) -> String {
    const MAX_LEN: usize = 160;
    if value.chars().count() <= MAX_LEN {
        return value.to_string();
    }

    let truncated = value.chars().take(MAX_LEN).collect::<String>();
    format!("{truncated}...")
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::{
        fs,
        os::unix::fs::PermissionsExt,
        path::Path,
        time::{SystemTime, UNIX_EPOCH},
    };

    fn temp_dir(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time before epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("aios-updated-{name}-{stamp}"));
        fs::create_dir_all(&path).expect("create temp dir");
        path
    }

    fn fake_backend_script(path: &Path, context_path: &Path) {
        let script = format!(
            r#"#!/bin/sh
set -eu
printf '%s
' "$*" >> "{}"
last=''
for arg in "$@"; do
  last="$arg"
done
case "$last" in
  check-new)
    printf 'version 0.2.0
'
    ;;
  list)
    printf 'aios-root 0.2.0
'
    ;;
  update)
    printf 'updated 0.2.0
'
    ;;
  *)
    printf 'unsupported %s
' "$last" >&2
    exit 9
    ;;
esac
"#,
            context_path.display()
        );
        fs::write(path, script).expect("write fake backend script");
        let mut perms = fs::metadata(path).expect("metadata").permissions();
        perms.set_mode(0o755);
        fs::set_permissions(path, perms).expect("set mode");
    }

    #[test]
    fn check_passes_structured_backend_arguments() {
        let temp = temp_dir("sysupdate-check");
        let context_path = temp.join("context.log");
        let binary_path = temp.join("fake-systemd-sysupdate.sh");
        let definitions_dir = temp.join("definitions");
        let sysroot = temp.join("sysroot");
        fs::create_dir_all(&definitions_dir).expect("definitions dir");
        fs::create_dir_all(&sysroot).expect("sysroot");
        fake_backend_script(&binary_path, &context_path);

        let config = BackendConfig {
            binary: binary_path.display().to_string(),
            definitions_dir: definitions_dir.clone(),
            root: Some(sysroot.clone()),
            component: Some("aios-root".to_string()),
            extra_args: vec!["--verify=false".to_string()],
        };

        let result = check(
            &config,
            &[("AIOS_UPDATED_OPERATION".to_string(), "check".to_string())],
        )
        .expect("sysupdate check succeeds");
        assert_eq!(result.available, Some(true));
        assert_eq!(result.next_version.as_deref(), Some("0.2.0"));

        let context = fs::read_to_string(&context_path).expect("read context");
        assert!(context.contains("--definitions"));
        assert!(context.contains(&definitions_dir.display().to_string()));
        assert!(context.contains("--root"));
        assert!(context.contains(&sysroot.display().to_string()));
        assert!(context.contains("--component aios-root"));
        assert!(context.contains("--verify=false check-new"));
        assert!(context.contains("--verify=false list"));
    }

    #[test]
    fn apply_runs_update_subcommand() {
        let temp = temp_dir("sysupdate-apply");
        let context_path = temp.join("context.log");
        let binary_path = temp.join("fake-systemd-sysupdate.sh");
        let definitions_dir = temp.join("definitions");
        fs::create_dir_all(&definitions_dir).expect("definitions dir");
        fake_backend_script(&binary_path, &context_path);

        let config = BackendConfig {
            binary: binary_path.display().to_string(),
            definitions_dir,
            root: None,
            component: None,
            extra_args: Vec::new(),
        };

        let result = apply(&config, &[]).expect("sysupdate apply succeeds");
        assert!(result.success);
        let context = fs::read_to_string(&context_path).expect("read context");
        assert!(context.contains("update"));
    }
}
