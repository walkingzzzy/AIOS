use std::{fs, path::Path};

use chrono::Utc;
use serde::{Deserialize, Serialize};

use aios_contracts::DeviceCaptureRecord;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndicatorEntry {
    pub indicator_id: String,
    pub capture_id: String,
    pub modality: String,
    pub message: String,
    pub continuous: bool,
    pub started_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_status: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndicatorState {
    pub updated_at: String,
    #[serde(default)]
    pub active: Vec<IndicatorEntry>,
    #[serde(default)]
    pub notes: Vec<String>,
}

pub fn write_state(
    path: &Path,
    captures: &[DeviceCaptureRecord],
) -> anyhow::Result<IndicatorState> {
    let active = captures
        .iter()
        .filter(|capture| crate::capture::is_active_capture(capture))
        .filter_map(build_indicator)
        .collect::<Vec<_>>();
    let state = IndicatorState {
        updated_at: Utc::now().to_rfc3339(),
        notes: vec![format!("active_indicators={}", active.len())],
        active,
    };

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, serde_json::to_vec_pretty(&state)?)?;
    Ok(state)
}

pub fn read_state(path: &Path) -> anyhow::Result<Option<IndicatorState>> {
    if !path.exists() {
        return Ok(None);
    }

    let content = fs::read_to_string(path)?;
    Ok(Some(serde_json::from_str::<IndicatorState>(&content)?))
}

fn build_indicator(capture: &DeviceCaptureRecord) -> Option<IndicatorEntry> {
    let indicator_id = capture.indicator_id.clone()?;
    Some(IndicatorEntry {
        indicator_id,
        capture_id: capture.capture_id.clone(),
        modality: capture.modality.clone(),
        message: match capture.modality.as_str() {
            "screen" => "Screen capture active".to_string(),
            "audio" => "Microphone capture active".to_string(),
            "camera" => "Camera capture active".to_string(),
            "input" => "Input observation active".to_string(),
            _ => "Device capture active".to_string(),
        },
        continuous: capture.continuous,
        started_at: capture.started_at.clone(),
        approval_status: capture.approval_status.clone(),
    })
}
