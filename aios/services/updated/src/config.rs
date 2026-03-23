use std::path::{Path, PathBuf};

use aios_core::ServicePaths;
use serde::Deserialize;

#[derive(Debug, Clone)]
pub struct Config {
    pub service_id: String,
    pub version: String,
    pub paths: ServicePaths,
    pub deployment_state_path: PathBuf,
    pub observability_log_path: PathBuf,
    pub sysupdate_dir: PathBuf,
    pub sysupdate_definitions_dir: PathBuf,
    pub sysupdate_root: Option<PathBuf>,
    pub sysupdate_component: Option<String>,
    pub sysupdate_extra_args: Vec<String>,
    pub diagnostics_dir: PathBuf,
    pub recovery_dir: PathBuf,
    pub health_probe_path: PathBuf,
    pub recovery_surface_path: PathBuf,
    pub boot_state_path: PathBuf,
    pub boot_backend: String,
    pub bootctl_binary: String,
    pub firmwarectl_binary: String,
    pub boot_cmdline_path: PathBuf,
    pub boot_entry_state_dir: PathBuf,
    pub boot_success_marker_path: PathBuf,
    pub health_probe_command: Option<String>,
    pub sysupdate_check_command: Option<String>,
    pub sysupdate_apply_command: Option<String>,
    pub rollback_command: Option<String>,
    pub boot_slot_command: Option<String>,
    pub boot_switch_command: Option<String>,
    pub boot_success_command: Option<String>,
    pub sysupdate_binary: String,
    pub update_stack: String,
    pub current_channel: String,
    pub current_version: String,
    pub current_slot: String,
    pub target_version_hint: Option<String>,
    pub failure_injection_stage: Option<String>,
    pub failure_injection_reason: Option<String>,
    pub platform_profile_path: Option<PathBuf>,
    pub platform_profile_id: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize)]
struct PlatformProfile {
    #[serde(default)]
    profile_id: Option<String>,
    #[serde(default)]
    deployment_state_path: Option<PathBuf>,
    #[serde(default)]
    sysupdate_dir: Option<PathBuf>,
    #[serde(default)]
    sysupdate_definitions_dir: Option<PathBuf>,
    #[serde(default)]
    sysupdate_root: Option<PathBuf>,
    #[serde(default)]
    sysupdate_component: Option<String>,
    #[serde(default)]
    sysupdate_extra_args: Vec<String>,
    #[serde(default)]
    diagnostics_dir: Option<PathBuf>,
    #[serde(default)]
    recovery_dir: Option<PathBuf>,
    #[serde(default)]
    health_probe_path: Option<PathBuf>,
    #[serde(default)]
    recovery_surface_path: Option<PathBuf>,
    #[serde(default)]
    boot_state_path: Option<PathBuf>,
    #[serde(default)]
    boot_backend: Option<String>,
    #[serde(default)]
    bootctl_binary: Option<PathBuf>,
    #[serde(default)]
    firmwarectl_binary: Option<PathBuf>,
    #[serde(default)]
    boot_cmdline_path: Option<PathBuf>,
    #[serde(default)]
    boot_entry_state_dir: Option<PathBuf>,
    #[serde(default)]
    boot_success_marker_path: Option<PathBuf>,
    #[serde(default)]
    health_probe_command: Option<String>,
    #[serde(default)]
    sysupdate_check_command: Option<String>,
    #[serde(default)]
    sysupdate_apply_command: Option<String>,
    #[serde(default)]
    rollback_command: Option<String>,
    #[serde(default)]
    boot_slot_command: Option<String>,
    #[serde(default)]
    boot_switch_command: Option<String>,
    #[serde(default)]
    boot_success_command: Option<String>,
    #[serde(default)]
    sysupdate_binary: Option<PathBuf>,
    #[serde(default)]
    update_stack: Option<String>,
    #[serde(default)]
    current_channel: Option<String>,
    #[serde(default)]
    current_version: Option<String>,
    #[serde(default)]
    current_slot: Option<String>,
    #[serde(default)]
    target_version_hint: Option<String>,
    #[serde(default)]
    failure_injection_stage: Option<String>,
    #[serde(default)]
    failure_injection_reason: Option<String>,
}

#[derive(Debug, Clone)]
struct LoadedPlatformProfile {
    path: PathBuf,
    profile: PlatformProfile,
}

fn parse_extra_args(var: &str) -> Vec<String> {
    std::env::var(var)
        .map(|value| value.split_whitespace().map(ToOwned::to_owned).collect())
        .unwrap_or_default()
}

fn env_string(var: &str) -> Option<String> {
    std::env::var(var).ok()
}

fn env_path(var: &str) -> Option<PathBuf> {
    std::env::var_os(var).map(PathBuf::from)
}

fn resolve_profile_path(base: &Path, path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        base.join(path)
    }
}

fn resolve_profile_path_option(base: Option<&Path>, value: Option<&PathBuf>) -> Option<PathBuf> {
    value.map(|path| {
        if let Some(base) = base {
            resolve_profile_path(base, path)
        } else {
            path.clone()
        }
    })
}

fn resolve_profile_string_path(base: Option<&Path>, value: Option<&PathBuf>) -> Option<String> {
    resolve_profile_path_option(base, value).map(|path| path.display().to_string())
}

fn load_platform_profile() -> anyhow::Result<Option<LoadedPlatformProfile>> {
    let Some(profile_path) = env_path("AIOS_UPDATED_PLATFORM_PROFILE") else {
        return Ok(None);
    };

    let content = std::fs::read_to_string(&profile_path)?;
    let profile = serde_yaml::from_str::<PlatformProfile>(&content)?;
    Ok(Some(LoadedPlatformProfile {
        path: profile_path,
        profile,
    }))
}

impl Config {
    pub async fn load() -> anyhow::Result<Self> {
        let paths = ServicePaths::from_service_name("updated");
        paths.ensure_base_dirs().await?;

        let loaded_profile = load_platform_profile()?;
        let profile = loaded_profile.as_ref().map(|loaded| &loaded.profile);
        let profile_base = loaded_profile
            .as_ref()
            .and_then(|loaded| loaded.path.parent().map(Path::to_path_buf));
        let profile_base = profile_base.as_deref();

        let diagnostics_dir = env_path("AIOS_UPDATED_DIAGNOSTICS_DIR")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.diagnostics_dir.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("diagnostics"));
        let recovery_dir = env_path("AIOS_UPDATED_RECOVERY_DIR")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.recovery_dir.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("recovery"));
        tokio::fs::create_dir_all(&diagnostics_dir).await?;
        tokio::fs::create_dir_all(&recovery_dir).await?;

        let deployment_state_path = env_path("AIOS_UPDATED_DEPLOYMENT_STATE")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.deployment_state_path.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("deployment-state.json"));
        let observability_log_path = env_path("AIOS_UPDATED_OBSERVABILITY_LOG")
            .unwrap_or_else(|| paths.state_dir.join("observability.jsonl"));

        let health_probe_path = env_path("AIOS_UPDATED_HEALTH_PROBE_PATH")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.health_probe_path.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("health-probe.json"));
        let recovery_surface_path = env_path("AIOS_UPDATED_RECOVERY_SURFACE_PATH")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.recovery_surface_path.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("recovery-surface.json"));
        let boot_state_path = env_path("AIOS_UPDATED_BOOT_STATE_PATH")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.boot_state_path.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("boot-control.json"));
        let boot_entry_state_dir = env_path("AIOS_UPDATED_BOOT_ENTRY_STATE_DIR")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.boot_entry_state_dir.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("boot"));
        let boot_cmdline_path = env_path("AIOS_UPDATED_BOOT_CMDLINE_PATH")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.boot_cmdline_path.as_ref()),
                )
            })
            .unwrap_or_else(|| PathBuf::from("/proc/cmdline"));
        let boot_success_marker_path = env_path("AIOS_UPDATED_BOOT_SUCCESS_MARKER_PATH")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.boot_success_marker_path.as_ref()),
                )
            })
            .unwrap_or_else(|| paths.state_dir.join("boot-success"));

        let health_probe_command = env_string("AIOS_UPDATED_HEALTH_PROBE_COMMAND")
            .or_else(|| profile.and_then(|value| value.health_probe_command.clone()));
        let sysupdate_check_command = env_string("AIOS_UPDATED_SYSUPDATE_CHECK_COMMAND")
            .or_else(|| profile.and_then(|value| value.sysupdate_check_command.clone()));
        let sysupdate_apply_command = env_string("AIOS_UPDATED_SYSUPDATE_APPLY_COMMAND")
            .or_else(|| profile.and_then(|value| value.sysupdate_apply_command.clone()));
        let rollback_command = env_string("AIOS_UPDATED_ROLLBACK_COMMAND")
            .or_else(|| profile.and_then(|value| value.rollback_command.clone()));
        let boot_slot_command = env_string("AIOS_UPDATED_BOOT_SLOT_COMMAND")
            .or_else(|| profile.and_then(|value| value.boot_slot_command.clone()));
        let boot_switch_command = env_string("AIOS_UPDATED_BOOT_SWITCH_COMMAND")
            .or_else(|| profile.and_then(|value| value.boot_switch_command.clone()));
        let boot_success_command = env_string("AIOS_UPDATED_BOOT_SUCCESS_COMMAND")
            .or_else(|| profile.and_then(|value| value.boot_success_command.clone()));

        let sysupdate_dir = env_path("AIOS_UPDATED_SYSUPDATE_DIR")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.sysupdate_dir.as_ref()),
                )
            })
            .unwrap_or_else(|| PathBuf::from("/etc/systemd/sysupdate.d"));
        let sysupdate_definitions_dir = env_path("AIOS_UPDATED_SYSUPDATE_DEFINITIONS_DIR")
            .or_else(|| {
                resolve_profile_path_option(
                    profile_base,
                    profile.and_then(|value| value.sysupdate_definitions_dir.as_ref()),
                )
            })
            .unwrap_or_else(|| sysupdate_dir.clone());
        let sysupdate_root = env_path("AIOS_UPDATED_SYSROOT").or_else(|| {
            resolve_profile_path_option(
                profile_base,
                profile.and_then(|value| value.sysupdate_root.as_ref()),
            )
        });
        let sysupdate_component = env_string("AIOS_UPDATED_SYSUPDATE_COMPONENT")
            .or_else(|| profile.and_then(|value| value.sysupdate_component.clone()));
        let sysupdate_extra_args =
            if std::env::var_os("AIOS_UPDATED_SYSUPDATE_EXTRA_ARGS").is_some() {
                parse_extra_args("AIOS_UPDATED_SYSUPDATE_EXTRA_ARGS")
            } else {
                profile
                    .map(|value| value.sysupdate_extra_args.clone())
                    .unwrap_or_default()
            };

        let sysupdate_binary = env_string("AIOS_UPDATED_SYSUPDATE_BIN")
            .or_else(|| {
                resolve_profile_string_path(
                    profile_base,
                    profile.and_then(|value| value.sysupdate_binary.as_ref()),
                )
            })
            .unwrap_or_else(|| "systemd-sysupdate".to_string());
        let update_stack = env_string("AIOS_UPDATED_UPDATE_STACK")
            .or_else(|| profile.and_then(|value| value.update_stack.clone()))
            .unwrap_or_else(|| "systemd-sysupdate".to_string());
        let current_channel = env_string("AIOS_UPDATED_CHANNEL")
            .or_else(|| profile.and_then(|value| value.current_channel.clone()))
            .unwrap_or_else(|| "stable".to_string());
        let current_version = env_string("AIOS_UPDATED_CURRENT_VERSION")
            .or_else(|| profile.and_then(|value| value.current_version.clone()))
            .unwrap_or_else(|| env!("CARGO_PKG_VERSION").to_string());
        let current_slot = env_string("AIOS_UPDATED_CURRENT_SLOT")
            .or_else(|| profile.and_then(|value| value.current_slot.clone()))
            .unwrap_or_else(|| "a".to_string());
        let target_version_hint = env_string("AIOS_UPDATED_TARGET_VERSION")
            .or_else(|| profile.and_then(|value| value.target_version_hint.clone()));
        let failure_injection_stage = env_string("AIOS_UPDATED_FAILURE_INJECTION_STAGE")
            .or_else(|| profile.and_then(|value| value.failure_injection_stage.clone()));
        let failure_injection_reason = env_string("AIOS_UPDATED_FAILURE_INJECTION_REASON")
            .or_else(|| profile.and_then(|value| value.failure_injection_reason.clone()));
        let boot_backend = env_string("AIOS_UPDATED_BOOT_BACKEND")
            .or_else(|| profile.and_then(|value| value.boot_backend.clone()))
            .unwrap_or_else(|| "state-file".to_string());
        let bootctl_binary = env_string("AIOS_UPDATED_BOOTCTL_BIN")
            .or_else(|| {
                resolve_profile_string_path(
                    profile_base,
                    profile.and_then(|value| value.bootctl_binary.as_ref()),
                )
            })
            .unwrap_or_else(|| "bootctl".to_string());
        let firmwarectl_binary = env_string("AIOS_UPDATED_FIRMWARECTL_BIN")
            .or_else(|| {
                resolve_profile_string_path(
                    profile_base,
                    profile.and_then(|value| value.firmwarectl_binary.as_ref()),
                )
            })
            .unwrap_or_else(|| "firmwarectl".to_string());

        Ok(Self {
            service_id: "aios-updated".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            paths,
            deployment_state_path,
            observability_log_path,
            sysupdate_dir,
            sysupdate_definitions_dir,
            sysupdate_root,
            sysupdate_component,
            sysupdate_extra_args,
            diagnostics_dir,
            recovery_dir,
            health_probe_path,
            recovery_surface_path,
            boot_state_path,
            boot_backend,
            bootctl_binary,
            firmwarectl_binary,
            boot_cmdline_path,
            boot_entry_state_dir,
            boot_success_marker_path,
            health_probe_command,
            sysupdate_check_command,
            sysupdate_apply_command,
            rollback_command,
            boot_slot_command,
            boot_switch_command,
            boot_success_command,
            sysupdate_binary,
            update_stack,
            current_channel,
            current_version,
            current_slot,
            target_version_hint,
            failure_injection_stage,
            failure_injection_reason,
            platform_profile_path: loaded_profile.as_ref().map(|loaded| loaded.path.clone()),
            platform_profile_id: profile.and_then(|value| value.profile_id.clone()),
        })
    }
}
