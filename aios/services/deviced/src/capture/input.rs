use chrono::Utc;
use serde_json::{json, Value};

use aios_contracts::{DeviceCapabilityDescriptor, DeviceCaptureRequest};

use crate::{config::Config, taint};

pub fn capability(config: &Config) -> DeviceCapabilityDescriptor {
    DeviceCapabilityDescriptor {
        modality: "input".to_string(),
        available: config.input_enabled,
        conditional: true,
        source_backend: config.input_backend.clone(),
        notes: vec!["input capture is read-only and distinct from input injection".to_string()],
    }
}

pub fn preview_object(_config: &Config, request: &DeviceCaptureRequest) -> Value {
    let now = Utc::now().to_rfc3339();
    json!({
        "batch_id": format!("batch-{}", Utc::now().timestamp_millis()),
        "source_device": request.source_device.clone().unwrap_or_else(|| "keyboard".to_string()),
        "timestamp_range": { "start": now, "end": Utc::now().to_rfc3339() },
        "event_types": ["key"],
        "window_ref": request.window_ref.clone().unwrap_or_else(|| "foreground-window".to_string()),
        "focus_ref": "focused-element",
        "taint_summary": taint::summarize("input", true, request.continuous)
    })
}
