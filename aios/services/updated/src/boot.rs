use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

use anyhow::Context;
use chrono::Utc;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BootSlotState {
    pub slot_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    pub status: String,
    pub bootable: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_booted_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_marked_good_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BootState {
    pub current_slot: String,
    pub last_good_slot: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub staged_slot: Option<String>,
    #[serde(default)]
    pub boot_success: bool,
    #[serde(default)]
    pub slots: Vec<BootSlotState>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct BootBackendConfig {
    pub backend: String,
    pub bootctl_binary: String,
    pub firmwarectl_binary: String,
    pub cmdline_path: PathBuf,
    pub entry_state_dir: PathBuf,
    pub success_marker_path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct BootControl {
    path: PathBuf,
    current_slot_hint: String,
    current_version_hint: String,
    backend: BootBackendConfig,
}

impl BootControl {
    pub fn new(
        path: PathBuf,
        current_slot_hint: String,
        current_version_hint: String,
        backend: BootBackendConfig,
    ) -> Self {
        Self {
            path,
            current_slot_hint,
            current_version_hint,
            backend,
        }
    }

    pub fn snapshot(&self) -> anyhow::Result<BootState> {
        if !self.path.exists() {
            return Ok(self.default_state());
        }

        let content = fs::read_to_string(&self.path)
            .with_context(|| format!("failed to read boot control {}", self.path.display()))?;
        let mut state = serde_json::from_str::<BootState>(&content)
            .with_context(|| format!("invalid boot control {}", self.path.display()))?;
        self.normalize(&mut state);
        Ok(state)
    }

    pub fn refresh(
        &self,
        slot_command: Option<&str>,
        success_command: Option<&str>,
    ) -> anyhow::Result<BootState> {
        let mut state = self.snapshot()?;
        state.notes.clear();
        state
            .notes
            .push(format!("boot_backend={}", self.backend.backend));

        if let Some(command) = slot_command {
            let output = command_output(command)?;
            if output.success {
                let slot = output.stdout.lines().next().unwrap_or("").trim();
                if !slot.is_empty() {
                    state.current_slot = slot.to_string();
                    state.notes.push(format!("slot_command={command}"));
                    state.notes.push(format!("current_slot={slot}"));
                }
            } else {
                state.notes.push(format!("slot_command_failed={command}"));
            }
        } else if let Some(slot) = self.detect_current_slot()? {
            state.current_slot = slot.clone();
            state.notes.push(format!("current_slot={slot}"));
        } else {
            state
                .notes
                .push("current_slot_detection_unavailable".to_string());
        }

        if let Some(command) = success_command {
            let output = command_output(command)?;
            state.boot_success = output.success;
            state.notes.push(format!("boot_success_command={command}"));
            state
                .notes
                .push(format!("boot_success={}", state.boot_success));
        } else if let Some(boot_success) = self.detect_boot_success()? {
            state.boot_success = boot_success;
            state
                .notes
                .push(format!("boot_success_marker={boot_success}"));
        }

        self.normalize(&mut state);
        self.persist(&state)?;
        Ok(state)
    }

    pub fn stage_update(&self, target_version: Option<&str>) -> anyhow::Result<BootState> {
        let mut state = self.snapshot()?;
        let target_slot = inactive_slot(&state.current_slot);
        let now = Utc::now().to_rfc3339();
        state.staged_slot = Some(target_slot.clone());
        state.boot_success = false;
        state.notes = vec![
            format!("boot_backend={}", self.backend.backend),
            format!("staged_slot={target_slot}"),
            "boot_success=false".to_string(),
        ];

        self.upsert_slot(
            &mut state,
            &target_slot,
            target_version,
            "staged",
            None,
            None,
        );
        let current_slot = state.current_slot.clone();
        self.upsert_slot(&mut state, &current_slot, None, "active", Some(now), None);
        self.normalize(&mut state);
        self.persist(&state)?;
        Ok(state)
    }

    pub fn stage_rollback(&self, target_slot: Option<&str>) -> anyhow::Result<BootState> {
        let mut state = self.snapshot()?;
        let rollback_slot = target_slot
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| state.last_good_slot.clone());
        state.staged_slot = Some(rollback_slot.clone());
        state.boot_success = false;
        state.notes = vec![
            format!("boot_backend={}", self.backend.backend),
            format!("rollback_slot={rollback_slot}"),
            "boot_success=false".to_string(),
        ];
        self.upsert_slot(
            &mut state,
            &rollback_slot,
            None,
            "rollback-target",
            None,
            None,
        );
        self.normalize(&mut state);
        self.persist(&state)?;
        Ok(state)
    }

    pub fn verify_boot(
        &self,
        slot_command: Option<&str>,
        success_command: Option<&str>,
        healthy: bool,
    ) -> anyhow::Result<BootState> {
        let mut state = self.refresh(slot_command, success_command)?;
        let now = Utc::now().to_rfc3339();

        let should_mark_good = if let Some(staged_slot) = &state.staged_slot {
            healthy && staged_slot == &state.current_slot
        } else {
            healthy && state.boot_success
        };

        if should_mark_good {
            let current_slot = state.current_slot.clone();
            state.last_good_slot = current_slot.clone();
            state.staged_slot = None;
            state.boot_success = true;
            state.notes.push(format!("boot_marked_good={current_slot}"));
            self.upsert_slot(
                &mut state,
                &current_slot,
                None,
                "active",
                Some(now.clone()),
                Some(now),
            );
            self.persist_backend_good_state(&state)?;
            self.normalize(&mut state);
            self.persist(&state)?;
        }

        Ok(state)
    }

    pub fn switch_slot(&self, target_slot: &str) -> anyhow::Result<Vec<String>> {
        let mut notes = vec![
            format!("boot_backend={}", self.backend.backend),
            format!("target_slot={target_slot}"),
        ];

        match self.backend.backend.as_str() {
            "bootctl" => {
                fs::create_dir_all(&self.backend.entry_state_dir)?;
                let entry = format!("aios-{target_slot}.conf");
                let output = Command::new(&self.backend.bootctl_binary)
                    .arg("set-oneshot")
                    .arg(&entry)
                    .output()
                    .with_context(|| {
                        format!("failed to execute {}", self.backend.firmwarectl_binary)
                    })?;
                if !output.status.success() {
                    anyhow::bail!(
                        "bootctl set-oneshot failed: {:?} {}",
                        output.status.code(),
                        String::from_utf8_lossy(&output.stderr).trim()
                    );
                }
                fs::write(
                    self.backend.entry_state_dir.join("next-entry"),
                    format!(
                        "{entry}
"
                    ),
                )?;
                fs::write(
                    self.backend.entry_state_dir.join("next-slot"),
                    format!(
                        "{target_slot}
"
                    ),
                )?;
                notes.push(format!("bootctl_entry={entry}"));
            }
            "firmware" => {
                fs::create_dir_all(&self.backend.entry_state_dir)?;
                let output = Command::new(&self.backend.firmwarectl_binary)
                    .arg("set-active")
                    .arg(target_slot)
                    .arg("--state-dir")
                    .arg(&self.backend.entry_state_dir)
                    .output()
                    .with_context(|| {
                        format!("failed to execute {}", self.backend.firmwarectl_binary)
                    })?;
                if !output.status.success() {
                    anyhow::bail!(
                        "firmwarectl set-active failed: {:?} {}",
                        output.status.code(),
                        String::from_utf8_lossy(&output.stderr).trim()
                    );
                }
                fs::write(
                    self.backend.entry_state_dir.join("next-slot"),
                    format!(
                        "{target_slot}
"
                    ),
                )?;
                notes.push(format!("firmware_pending_slot={target_slot}"));
            }
            _ => {
                fs::create_dir_all(&self.backend.entry_state_dir)?;
                fs::write(
                    self.backend.entry_state_dir.join("next-slot"),
                    format!(
                        "{target_slot}
"
                    ),
                )?;
                notes.push("boot_backend_file_switch=true".to_string());
            }
        }

        Ok(notes)
    }

    fn default_state(&self) -> BootState {
        BootState {
            current_slot: self.current_slot_hint.clone(),
            last_good_slot: self.current_slot_hint.clone(),
            staged_slot: None,
            boot_success: true,
            slots: vec![
                BootSlotState {
                    slot_id: "a".to_string(),
                    version: if self.current_slot_hint == "a" {
                        Some(self.current_version_hint.clone())
                    } else {
                        None
                    },
                    status: if self.current_slot_hint == "a" {
                        "active".to_string()
                    } else {
                        "standby".to_string()
                    },
                    bootable: true,
                    last_booted_at: None,
                    last_marked_good_at: None,
                },
                BootSlotState {
                    slot_id: "b".to_string(),
                    version: if self.current_slot_hint == "b" {
                        Some(self.current_version_hint.clone())
                    } else {
                        None
                    },
                    status: if self.current_slot_hint == "b" {
                        "active".to_string()
                    } else {
                        "standby".to_string()
                    },
                    bootable: true,
                    last_booted_at: None,
                    last_marked_good_at: None,
                },
            ],
            notes: Vec::new(),
        }
    }

    fn normalize(&self, state: &mut BootState) {
        ensure_slot(state, "a");
        ensure_slot(state, "b");
        for slot in &mut state.slots {
            if Some(slot.slot_id.as_str()) == state.staged_slot.as_deref() {
                if slot.status == "standby" {
                    slot.status = "staged".to_string();
                }
            } else if slot.slot_id == state.current_slot {
                slot.status = "active".to_string();
            } else if slot.status != "rollback-target" {
                slot.status = "standby".to_string();
            }
        }
    }

    fn upsert_slot(
        &self,
        state: &mut BootState,
        slot_id: &str,
        version: Option<&str>,
        status: &str,
        last_booted_at: Option<String>,
        last_marked_good_at: Option<String>,
    ) {
        ensure_slot(state, slot_id);
        if let Some(slot) = state.slots.iter_mut().find(|slot| slot.slot_id == slot_id) {
            if let Some(version) = version {
                slot.version = Some(version.to_string());
            }
            slot.status = status.to_string();
            if let Some(last_booted_at) = last_booted_at {
                slot.last_booted_at = Some(last_booted_at);
            }
            if let Some(last_marked_good_at) = last_marked_good_at {
                slot.last_marked_good_at = Some(last_marked_good_at);
            }
            slot.bootable = true;
        }
    }

    fn detect_current_slot(&self) -> anyhow::Result<Option<String>> {
        if let Some(slot) = parse_slot_from_cmdline(&self.backend.cmdline_path)? {
            return Ok(Some(slot));
        }
        if let Some(slot) = read_slot_hint(&self.backend.entry_state_dir.join("current-slot"))? {
            return Ok(Some(slot));
        }
        if let Some(slot) = read_slot_hint(&self.backend.entry_state_dir.join("next-slot"))? {
            return Ok(Some(slot));
        }
        if let Some(entry) = read_first_line(&self.backend.entry_state_dir.join("current-entry"))? {
            if let Some(slot) = parse_slot_hint(&entry) {
                return Ok(Some(slot));
            }
        }
        if self.backend.backend == "bootctl" {
            let output = Command::new(&self.backend.bootctl_binary)
                .arg("status")
                .output();
            if let Ok(output) = output {
                let stdout = String::from_utf8_lossy(&output.stdout);
                for line in stdout.lines() {
                    if line
                        .to_ascii_lowercase()
                        .contains("current boot loader entry")
                    {
                        if let Some(slot) = parse_slot_hint(line) {
                            return Ok(Some(slot));
                        }
                    }
                }
            }
        } else if self.backend.backend == "firmware" {
            let output = Command::new(&self.backend.firmwarectl_binary)
                .arg("status")
                .arg("--state-dir")
                .arg(&self.backend.entry_state_dir)
                .output();
            if let Ok(output) = output {
                if output.status.success() {
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    for line in stdout.lines() {
                        let normalized = line.to_ascii_lowercase();
                        if normalized.contains("current_slot")
                            || normalized.contains("booted_slot")
                            || normalized.contains("active_slot")
                            || normalized.contains("current slot")
                        {
                            if let Some(slot) = parse_slot_hint(line) {
                                return Ok(Some(slot));
                            }
                            if let Some((_, value)) = line.split_once('=') {
                                if let Some(slot) = normalize_slot(value) {
                                    return Ok(Some(slot));
                                }
                            }
                            if let Some((_, value)) = line.split_once(':') {
                                if let Some(slot) = normalize_slot(value) {
                                    return Ok(Some(slot));
                                }
                            }
                        }
                    }
                }
            }
        }
        Ok(None)
    }

    fn detect_boot_success(&self) -> anyhow::Result<Option<bool>> {
        if !self.backend.success_marker_path.exists() {
            return Ok(None);
        }
        let content = fs::read_to_string(&self.backend.success_marker_path).with_context(|| {
            format!(
                "failed to read {}",
                self.backend.success_marker_path.display()
            )
        })?;
        let normalized = content.trim().to_ascii_lowercase();
        Ok(Some(matches!(
            normalized.as_str(),
            "1" | "true" | "ok" | "ready" | "success"
        )))
    }

    fn persist_backend_good_state(&self, state: &BootState) -> anyhow::Result<()> {
        fs::create_dir_all(&self.backend.entry_state_dir)?;
        fs::write(
            self.backend.entry_state_dir.join("last-good-slot"),
            format!(
                "{}
",
                state.last_good_slot
            ),
        )?;
        fs::write(
            self.backend.entry_state_dir.join("current-slot"),
            format!(
                "{}
",
                state.current_slot
            ),
        )?;

        let next_slot = self.backend.entry_state_dir.join("next-slot");
        if next_slot.exists() {
            fs::remove_file(&next_slot)?;
        }
        let next_entry = self.backend.entry_state_dir.join("next-entry");
        if next_entry.exists() {
            fs::remove_file(&next_entry)?;
        }

        if self.backend.backend == "bootctl" {
            fs::write(
                self.backend.entry_state_dir.join("current-entry"),
                format!(
                    "aios-{}.conf
",
                    state.current_slot
                ),
            )?;
        } else if self.backend.backend == "firmware" {
            let output = Command::new(&self.backend.firmwarectl_binary)
                .arg("mark-good")
                .arg(&state.current_slot)
                .arg("--state-dir")
                .arg(&self.backend.entry_state_dir)
                .output()
                .with_context(|| {
                    format!("failed to execute {}", self.backend.firmwarectl_binary)
                })?;
            if !output.status.success() {
                anyhow::bail!(
                    "firmwarectl mark-good failed: {:?} {}",
                    output.status.code(),
                    String::from_utf8_lossy(&output.stderr).trim()
                );
            }
            fs::write(
                self.backend.entry_state_dir.join("current-entry"),
                format!(
                    "aios-{}.conf
",
                    state.current_slot
                ),
            )?;
        }
        Ok(())
    }

    fn persist(&self, state: &BootState) -> anyhow::Result<()> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&self.path, serde_json::to_vec_pretty(state)?)?;
        Ok(())
    }
}

fn ensure_slot(state: &mut BootState, slot_id: &str) {
    if state.slots.iter().any(|slot| slot.slot_id == slot_id) {
        return;
    }

    state.slots.push(BootSlotState {
        slot_id: slot_id.to_string(),
        version: None,
        status: "standby".to_string(),
        bootable: true,
        last_booted_at: None,
        last_marked_good_at: None,
    });
}

fn inactive_slot(current_slot: &str) -> String {
    if current_slot == "a" {
        "b".to_string()
    } else {
        "a".to_string()
    }
}

#[derive(Debug, Clone)]
struct ShellOutput {
    success: bool,
    stdout: String,
}

fn command_output(command: &str) -> anyhow::Result<ShellOutput> {
    let output = Command::new("/bin/sh").arg("-lc").arg(command).output()?;
    Ok(ShellOutput {
        success: output.status.success(),
        stdout: String::from_utf8_lossy(&output.stdout).trim().to_string(),
    })
}

fn parse_slot_from_cmdline(path: &Path) -> anyhow::Result<Option<String>> {
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(path)
        .with_context(|| format!("failed to read cmdline {}", path.display()))?;
    for token in content.split_whitespace() {
        if let Some(slot) = token
            .strip_prefix("aios.slot=")
            .or_else(|| token.strip_prefix("rootfs_slot="))
            .or_else(|| token.strip_prefix("boot_slot="))
            .or_else(|| token.strip_prefix("slot="))
        {
            if let Some(slot) = normalize_slot(slot) {
                return Ok(Some(slot));
            }
        }
    }
    Ok(None)
}

fn read_slot_hint(path: &Path) -> anyhow::Result<Option<String>> {
    Ok(read_first_line(path)?.and_then(|line| parse_slot_hint(&line)))
}

fn read_first_line(path: &Path) -> anyhow::Result<Option<String>> {
    if !path.exists() {
        return Ok(None);
    }
    let content =
        fs::read_to_string(path).with_context(|| format!("failed to read {}", path.display()))?;
    Ok(content
        .lines()
        .next()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(ToOwned::to_owned))
}

fn parse_slot_hint(value: &str) -> Option<String> {
    let normalized = value.trim().to_ascii_lowercase();
    if let Some(slot) = normalize_slot(&normalized) {
        return Some(slot);
    }
    for pattern in [
        "slot-a", "slot_a", "slot=a", "slot:a", "aios-a", "aios_a", "-a.conf",
    ] {
        if normalized.contains(pattern) {
            return Some("a".to_string());
        }
    }
    for pattern in [
        "slot-b", "slot_b", "slot=b", "slot:b", "aios-b", "aios_b", "-b.conf",
    ] {
        if normalized.contains(pattern) {
            return Some("b".to_string());
        }
    }
    None
}

fn normalize_slot(value: &str) -> Option<String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "a" | "_a" | "slot-a" | "slot_a" => Some("a".to_string()),
        "b" | "_b" | "slot-b" | "slot_b" => Some("b".to_string()),
        _ => None,
    }
}
