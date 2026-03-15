use aios_contracts::{DeviceRetentionApplyRequest, DeviceRetentionApplyResponse};

pub fn apply(request: &DeviceRetentionApplyRequest) -> DeviceRetentionApplyResponse {
    let retention_class = request.retention_class.clone().unwrap_or_else(|| {
        if request.contains_sensitive_data
            || request.continuous
            || requires_sensitive_retention(&request.object_kind)
        {
            "short".to_string()
        } else if request.object_kind == "screen_frame" {
            "session".to_string()
        } else {
            "ephemeral".to_string()
        }
    });

    let expires_in_seconds = match retention_class.as_str() {
        "short" => 300,
        "session" => 1800,
        _ => 60,
    };

    let mut notes = vec![format!("object_kind={}", request.object_kind)];
    if request.contains_sensitive_data {
        notes.push("contains sensitive data; using shorter retention".to_string());
    }
    if request.continuous {
        notes.push("continuous capture should be pruned aggressively".to_string());
    }
    if !request.contains_sensitive_data && requires_sensitive_retention(&request.object_kind) {
        notes.push(format!(
            "object_kind={} defaults to sensitive retention",
            request.object_kind
        ));
    }

    DeviceRetentionApplyResponse {
        object_id: request.object_id.clone(),
        retention_class,
        expires_in_seconds,
        notes,
    }
}

fn requires_sensitive_retention(object_kind: &str) -> bool {
    matches!(
        object_kind,
        "audio_chunk" | "camera_frame" | "input_event_batch"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retention_prefers_short_for_sensitive_continuous_data() {
        let response = apply(&DeviceRetentionApplyRequest {
            object_kind: "audio_chunk".to_string(),
            object_id: "obj-1".to_string(),
            retention_class: None,
            continuous: true,
            contains_sensitive_data: true,
        });

        assert_eq!(response.retention_class, "short");
        assert_eq!(response.expires_in_seconds, 300);
    }

    #[test]
    fn retention_defaults_camera_frames_to_short() {
        let response = apply(&DeviceRetentionApplyRequest {
            object_kind: "camera_frame".to_string(),
            object_id: "cam-1".to_string(),
            retention_class: None,
            continuous: false,
            contains_sensitive_data: false,
        });

        assert_eq!(response.retention_class, "short");
        assert_eq!(response.expires_in_seconds, 300);
        assert!(response
            .notes
            .iter()
            .any(|item| item == "object_kind=camera_frame defaults to sensitive retention"));
    }

    #[test]
    fn retention_defaults_audio_chunks_to_short() {
        let response = apply(&DeviceRetentionApplyRequest {
            object_kind: "audio_chunk".to_string(),
            object_id: "audio-1".to_string(),
            retention_class: None,
            continuous: false,
            contains_sensitive_data: false,
        });

        assert_eq!(response.retention_class, "short");
        assert_eq!(response.expires_in_seconds, 300);
        assert!(response
            .notes
            .iter()
            .any(|item| item == "object_kind=audio_chunk defaults to sensitive retention"));
    }

    #[test]
    fn retention_keeps_screen_frames_session_scoped() {
        let response = apply(&DeviceRetentionApplyRequest {
            object_kind: "screen_frame".to_string(),
            object_id: "screen-1".to_string(),
            retention_class: None,
            continuous: false,
            contains_sensitive_data: false,
        });

        assert_eq!(response.retention_class, "session");
        assert_eq!(response.expires_in_seconds, 1800);
    }
}
