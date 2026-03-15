use chrono::Utc;
use serde_json::{json, Value};

use aios_contracts::{DeviceCapabilityDescriptor, DeviceCaptureRequest};

use crate::{config::Config, taint};

pub fn capability(config: &Config) -> DeviceCapabilityDescriptor {
    let mut notes = vec![format!("default_resolution={}", config.default_resolution)];
    if !config.ui_tree_supported {
        notes.push("ui_tree not enabled; screen_frame baseline only".to_string());
    }

    DeviceCapabilityDescriptor {
        modality: "screen".to_string(),
        available: config.screen_enabled,
        conditional: true,
        source_backend: config.screen_backend.clone(),
        notes,
    }
}

pub fn preview_object(config: &Config, request: &DeviceCaptureRequest) -> Value {
    json!({
        "frame_id": format!("frame-{}", Utc::now().timestamp_millis()),
        "window_ref": request.window_ref.clone().unwrap_or_else(|| "foreground-window".to_string()),
        "workspace_ref": "workspace-1",
        "timestamp": Utc::now().to_rfc3339(),
        "resolution": config.default_resolution.clone(),
        "visibility_scope": "foreground",
        "taint_summary": taint::summarize("screen", true, request.continuous)
    })
}
