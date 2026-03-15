use chrono::Utc;
use serde_json::{json, Map, Value};

use aios_contracts::{DeviceObjectNormalizeRequest, DeviceObjectNormalizeResponse};

use crate::taint;

pub fn apply(request: &DeviceObjectNormalizeRequest) -> DeviceObjectNormalizeResponse {
    let object_kind = object_kind(&request.modality).to_string();
    let taint_summary = taint::summarize(&request.modality, request.user_visible, false);

    let mut normalized = match &request.payload {
        Value::Object(map) => map.clone(),
        other => {
            let mut map = Map::new();
            map.insert("raw_payload".to_string(), other.clone());
            map
        }
    };

    let timestamp = Utc::now().to_rfc3339();
    normalized.insert("timestamp".to_string(), json!(timestamp));
    normalized.insert("taint_summary".to_string(), json!(taint_summary.clone()));
    normalized.insert(
        "source_backend".to_string(),
        json!(request
            .source_backend
            .clone()
            .unwrap_or_else(|| "synthetic".to_string())),
    );

    match request.modality.as_str() {
        "screen" => {
            normalized
                .entry("frame_id".to_string())
                .or_insert_with(|| json!(format!("frame-{}", Utc::now().timestamp_millis())));
            normalized
                .entry("resolution".to_string())
                .or_insert_with(|| json!("1920x1080"));
            normalized
                .entry("visibility_scope".to_string())
                .or_insert_with(|| {
                    json!(if request.user_visible {
                        "foreground"
                    } else {
                        "background"
                    })
                });
        }
        "audio" => {
            normalized
                .entry("chunk_id".to_string())
                .or_insert_with(|| json!(format!("chunk-{}", Utc::now().timestamp_millis())));
            normalized
                .entry("duration_ms".to_string())
                .or_insert_with(|| json!(1000));
            normalized
                .entry("channel_layout".to_string())
                .or_insert_with(|| json!("stereo"));
        }
        "input" => {
            normalized
                .entry("batch_id".to_string())
                .or_insert_with(|| json!(format!("batch-{}", Utc::now().timestamp_millis())));
            normalized
                .entry("event_types".to_string())
                .or_insert_with(|| json!(["key"]));
        }
        "camera" => {
            normalized.entry("frame_id".to_string()).or_insert_with(|| {
                json!(format!("camera-frame-{}", Utc::now().timestamp_millis()))
            });
            normalized
                .entry("source_device".to_string())
                .or_insert_with(|| json!("default-camera"));
        }
        _ => {}
    }

    let mut notes = vec![format!("normalized_as={object_kind}")];
    if request.modality == "screen" {
        if normalized.contains_key("ui_tree_snapshot") {
            notes.push("ui_tree snapshot attached to screen payload".to_string());
        } else {
            notes.push("ui_tree unsupported by default; screen_frame baseline only".to_string());
        }
    } else if request.modality == "camera" {
        notes.push("camera frames default to sensitive retention handling".to_string());
    }

    DeviceObjectNormalizeResponse {
        object_kind,
        normalized: Value::Object(normalized),
        taint_summary,
        notes,
    }
}

fn object_kind(modality: &str) -> &str {
    match modality {
        "screen" => "screen_frame",
        "audio" => "audio_chunk",
        "input" => "input_event_batch",
        "camera" => "camera_frame",
        _ => "device_object",
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn normalize_adds_screen_frame_metadata() {
        let response = apply(&DeviceObjectNormalizeRequest {
            modality: "screen".to_string(),
            payload: json!({"window_ref": "win-1"}),
            source_backend: Some("screen-capture-portal".to_string()),
            user_visible: true,
        });

        assert_eq!(response.object_kind, "screen_frame");
        assert!(response.normalized.get("frame_id").is_some());
        assert_eq!(
            response.normalized.get("visibility_scope"),
            Some(&json!("foreground"))
        );
    }

    #[test]
    fn normalize_adds_camera_frame_metadata() {
        let response = apply(&DeviceObjectNormalizeRequest {
            modality: "camera".to_string(),
            payload: json!({"device_path": "/tmp/video0"}),
            source_backend: Some("pipewire-camera".to_string()),
            user_visible: true,
        });

        assert_eq!(response.object_kind, "camera_frame");
        assert!(response.normalized.get("frame_id").is_some());
        assert_eq!(
            response.normalized.get("source_device"),
            Some(&json!("default-camera"))
        );
        assert!(response
            .notes
            .iter()
            .any(|item| item == "camera frames default to sensitive retention handling"));
    }
}
