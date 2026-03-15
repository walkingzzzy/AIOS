use chrono::Utc;
use serde_json::{json, Value};

use aios_contracts::{DeviceCapabilityDescriptor, DeviceCaptureRequest};

use crate::{config::Config, taint};

pub fn capability(config: &Config) -> DeviceCapabilityDescriptor {
    DeviceCapabilityDescriptor {
        modality: "camera".to_string(),
        available: config.camera_enabled,
        conditional: true,
        source_backend: config.camera_backend.clone(),
        notes: vec!["camera capture remains opt-in and platform-conditional".to_string()],
    }
}

pub fn preview_object(_config: &Config, request: &DeviceCaptureRequest) -> Value {
    json!({
        "frame_id": format!("camera-frame-{}", Utc::now().timestamp_millis()),
        "source_device": request.source_device.clone().unwrap_or_else(|| "default-camera".to_string()),
        "timestamp": Utc::now().to_rfc3339(),
        "taint_summary": taint::summarize("camera", true, request.continuous)
    })
}
