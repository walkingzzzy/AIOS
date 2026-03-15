use serde::Deserialize;
use std::fs;
use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::process::Command;
use std::time::Duration;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PanelSnapshot {
    pub profile_id: Option<String>,
    pub surface_count: u32,
    pub surfaces: Vec<PanelSurface>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PanelSurface {
    pub component: String,
    pub panel_id: Option<String>,
    pub status: Option<String>,
    pub tone: Option<String>,
    pub primary_action_id: Option<String>,
    pub action_count: u32,
    pub section_count: u32,
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawSnapshot {
    profile_id: Option<String>,
    surface_count: Option<u32>,
    surfaces: Option<Vec<RawSurface>>,
}

#[derive(Debug, Deserialize)]
struct RawSurface {
    component: Option<String>,
    panel_id: Option<String>,
    status: Option<String>,
    tone: Option<String>,
    error: Option<String>,
    model: Option<RawModel>,
}

#[derive(Debug, Deserialize)]
struct RawModel {
    panel_id: Option<String>,
    actions: Option<Vec<RawAction>>,
    sections: Option<Vec<serde_json::Value>>,
    header: Option<RawHeader>,
}

#[derive(Debug, Deserialize)]
struct RawAction {
    action_id: Option<String>,
    enabled: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct RawHeader {
    status: Option<String>,
    tone: Option<String>,
}

pub fn load_panel_snapshot(path: &Path) -> Result<PanelSnapshot, String> {
    let contents = fs::read_to_string(path)
        .map_err(|error| format!("read-panel-snapshot:{}:{error}", path.display()))?;
    parse_panel_snapshot(&format!("path:{}", path.display()), &contents)
}

pub fn load_panel_snapshot_from_command(command: &str) -> Result<PanelSnapshot, String> {
    let output = Command::new("/bin/sh")
        .arg("-lc")
        .arg(command)
        .output()
        .map_err(|error| format!("exec-panel-snapshot-command:{error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let mut status = format!("panel-snapshot-command-failed:{:?}", output.status.code());
        if !stderr.is_empty() {
            status.push_str(&format!(":stderr={stderr}"));
        }
        if !stdout.is_empty() {
            status.push_str(&format!(":stdout={stdout}"));
        }
        return Err(status);
    }
    let contents = String::from_utf8_lossy(&output.stdout).to_string();
    parse_panel_snapshot("command", &contents)
}

pub fn load_panel_snapshot_from_socket(path: &Path) -> Result<PanelSnapshot, String> {
    let contents = call_panel_bridge(path, "shell.panel.snapshot.get", serde_json::json!({}))?;
    parse_panel_snapshot(&format!("socket:{}", path.display()), &contents)
}

#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub fn dispatch_panel_action_via_socket(
    path: &Path,
    params: serde_json::Value,
) -> Result<String, String> {
    call_panel_bridge(path, "shell.panel.action.dispatch", params)
}

fn call_panel_bridge(
    path: &Path,
    method: &str,
    params: serde_json::Value,
) -> Result<String, String> {
    let mut stream = UnixStream::connect(path)
        .map_err(|error| format!("connect-panel-bridge:{}:{error}", path.display()))?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    let request = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    });
    let payload = serde_json::to_vec(&request)
        .map_err(|error| format!("encode-panel-bridge-request:{}:{error}", path.display()))?;
    stream
        .write_all(&payload)
        .map_err(|error| format!("write-panel-bridge-request:{}:{error}", path.display()))?;
    stream
        .write_all(b"\n")
        .map_err(|error| format!("write-panel-bridge-request:{}:{error}", path.display()))?;

    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("read-panel-bridge-response:{}:{error}", path.display()))?;
    let value = serde_json::from_str::<serde_json::Value>(&response)
        .map_err(|error| format!("parse-panel-bridge-response:{}:{error}", path.display()))?;
    if let Some(error) = value.get("error") {
        let message = error
            .get("message")
            .and_then(|value| value.as_str())
            .unwrap_or("unknown panel bridge error");
        return Err(format!(
            "panel-bridge-response-error:{}:{}",
            path.display(),
            message
        ));
    }
    let result = value
        .get("result")
        .cloned()
        .unwrap_or_else(|| serde_json::Value::Null);
    serde_json::to_string(&result)
        .map_err(|error| format!("encode-panel-bridge-result:{}:{error}", path.display()))
}

fn parse_panel_snapshot(source: &str, contents: &str) -> Result<PanelSnapshot, String> {
    let raw: RawSnapshot = parse_raw_snapshot(source, contents)?;
    let surfaces = raw
        .surfaces
        .unwrap_or_default()
        .into_iter()
        .filter_map(normalize_surface)
        .collect::<Vec<_>>();
    Ok(PanelSnapshot {
        profile_id: raw.profile_id,
        surface_count: raw.surface_count.unwrap_or(surfaces.len() as u32),
        surfaces,
    })
}

fn parse_raw_snapshot(source: &str, contents: &str) -> Result<RawSnapshot, String> {
    let value = serde_json::from_str::<serde_json::Value>(contents)
        .or_else(|_| parse_last_json_line(contents))
        .map_err(|error| format!("parse-panel-snapshot:{source}:{error}"))?;
    let raw_value = value.get("snapshot").cloned().unwrap_or(value);
    serde_json::from_value(raw_value)
        .map_err(|error| format!("decode-panel-snapshot:{source}:{error}"))
}

fn parse_last_json_line(contents: &str) -> Result<serde_json::Value, serde_json::Error> {
    let mut last_error = None;
    for line in contents
        .lines()
        .rev()
        .filter(|line| !line.trim().is_empty())
    {
        match serde_json::from_str::<serde_json::Value>(line) {
            Ok(value) => return Ok(value),
            Err(error) => last_error = Some(error),
        }
    }
    serde_json::from_str::<serde_json::Value>(contents).map_err(|error| last_error.unwrap_or(error))
}

fn normalize_surface(surface: RawSurface) -> Option<PanelSurface> {
    let component = surface.component?;
    let model = surface.model;
    let panel_id = surface
        .panel_id
        .or_else(|| model.as_ref().and_then(|model| model.panel_id.clone()));
    let status = surface.status.or_else(|| {
        model
            .as_ref()
            .and_then(|model| model.header.as_ref()?.status.clone())
    });
    let tone = surface.tone.or_else(|| {
        model
            .as_ref()
            .and_then(|model| model.header.as_ref()?.tone.clone())
    });
    let action_count = model
        .as_ref()
        .and_then(|model| model.actions.as_ref())
        .map(|actions| actions.len() as u32)
        .unwrap_or(0);
    let primary_action_id = model
        .as_ref()
        .and_then(|model| model.actions.as_ref())
        .and_then(|actions| {
            actions
                .iter()
                .find(|action| action.enabled != Some(false) && action.action_id.is_some())
                .or_else(|| actions.iter().find(|action| action.action_id.is_some()))
        })
        .and_then(|action| action.action_id.clone());
    let section_count = model
        .as_ref()
        .and_then(|model| model.sections.as_ref())
        .map(|sections| sections.len() as u32)
        .unwrap_or(0);
    Some(PanelSurface {
        component,
        panel_id,
        status,
        tone,
        primary_action_id,
        action_count,
        section_count,
        error: surface.error,
    })
}

#[cfg(test)]
mod tests {
    use super::{load_panel_snapshot, parse_panel_snapshot};
    use std::fs;

    #[test]
    fn loads_snapshot_surface_metadata() {
        let dir = std::env::temp_dir().join(format!(
            "aios-shell-compositor-panel-snapshot-{}",
            std::process::id()
        ));
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("snapshot.json");
        fs::write(
            &path,
            r#"{
  "profile_id": "shell-compositor-smoke",
  "surface_count": 2,
  "surfaces": [
    {
      "component": "launcher",
      "status": "active",
      "tone": "positive",
      "panel_id": "launcher-panel",
      "model": {
        "actions": [{"action_id": "create-session"}],
        "sections": [{"section_id": "session"}]
      }
    },
    {
      "component": "approval-panel",
      "model": {
        "panel_id": "approval-panel-shell",
        "header": {"status": "pending", "tone": "warning"},
        "actions": [{"action_id": "approve"}, {"action_id": "reject"}],
        "sections": [{"section_id": "approvals"}, {"section_id": "lanes"}]
      }
    }
  ]
}"#,
        )
        .unwrap();

        let snapshot = load_panel_snapshot(&path).unwrap();
        assert_eq!(
            snapshot.profile_id.as_deref(),
            Some("shell-compositor-smoke")
        );
        assert_eq!(snapshot.surface_count, 2);
        assert_eq!(snapshot.surfaces.len(), 2);
        assert_eq!(snapshot.surfaces[0].component, "launcher");
        assert_eq!(
            snapshot.surfaces[0].primary_action_id.as_deref(),
            Some("create-session")
        );
        assert_eq!(snapshot.surfaces[0].action_count, 1);
        assert_eq!(
            snapshot.surfaces[1].panel_id.as_deref(),
            Some("approval-panel-shell")
        );
        assert_eq!(snapshot.surfaces[1].status.as_deref(), Some("pending"));
        assert_eq!(snapshot.surfaces[1].section_count, 2);

        fs::remove_file(path).unwrap();
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn loads_export_payload_snapshot() {
        let snapshot = parse_panel_snapshot(
            "command",
            r#"{
  "snapshot": {
    "profile_id": "shell-session-export",
    "surface_count": 1,
    "surfaces": [
      {
        "component": "notification-center",
        "model": {
          "header": {"status": "info", "tone": "neutral"},
          "actions": [{"action_id": "refresh"}]
        }
      }
    ]
  },
  "artifacts": {
    "json": "/tmp/snapshot.json"
  }
}"#,
        )
        .unwrap();
        assert_eq!(snapshot.profile_id.as_deref(), Some("shell-session-export"));
        assert_eq!(snapshot.surface_count, 1);
        assert_eq!(snapshot.surfaces[0].component, "notification-center");
        assert_eq!(
            snapshot.surfaces[0].primary_action_id.as_deref(),
            Some("refresh")
        );
        assert_eq!(snapshot.surfaces[0].action_count, 1);
    }
}
