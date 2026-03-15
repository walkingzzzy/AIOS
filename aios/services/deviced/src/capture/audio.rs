use chrono::Utc;
use serde_json::{json, Value};

use aios_contracts::{DeviceCapabilityDescriptor, DeviceCaptureRequest};

use crate::{config::Config, taint};

pub fn capability(config: &Config) -> DeviceCapabilityDescriptor {
    DeviceCapabilityDescriptor {
        modality: "audio".to_string(),
        available: config.audio_enabled,
        conditional: true,
        source_backend: config.audio_backend.clone(),
        notes: vec!["continuous audio capture remains approval-sensitive".to_string()],
    }
}

pub fn preview_object(_config: &Config, request: &DeviceCaptureRequest) -> Value {
    json!({
        "chunk_id": format!("chunk-{}", Utc::now().timestamp_millis()),
        "source_device": request.source_device.clone().unwrap_or_else(|| "default-microphone".to_string()),
        "timestamp": Utc::now().to_rfc3339(),
        "duration_ms": if request.continuous { 3000 } else { 1000 },
        "channel_layout": "stereo",
        "transcript_ref": Value::Null,
        "taint_summary": taint::summarize("audio", true, request.continuous)
    })
}
