use serde_json::{json, Map, Value};

pub fn default_backend_id(modality: &str) -> Option<&'static str> {
    match modality {
        "screen" => Some("xdg-desktop-portal-screencast"),
        "audio" => Some("pipewire"),
        "input" => Some("libinput"),
        "camera" => Some("v4l2"),
        "ui_tree" => Some("at-spi"),
        _ => None,
    }
}

pub fn default_backend_stack(modality: &str) -> Option<&'static str> {
    match modality {
        "screen" => Some("portal+pipewire"),
        "audio" => Some("pipewire"),
        "input" => Some("libinput"),
        "camera" => Some("v4l2"),
        "ui_tree" => Some("at-spi"),
        _ => None,
    }
}

pub fn infer_origin(source: Option<&str>, execution_path: Option<&str>) -> Option<&'static str> {
    match execution_path {
        Some("native-state-bridge") => return Some("state-bridge"),
        Some("native-ready") => return Some("declared-ready"),
        Some("command-adapter") => return Some("command-adapter"),
        _ => {}
    }

    match source {
        Some("linux-tool") => Some("os-native"),
        Some(source) if source.starts_with("builtin-") => Some("runtime-helper"),
        Some("probe-command") | Some("deviced-runtime-helper") => Some("runtime-helper"),
        Some("builtin-probe") if execution_path == Some("native-live") => Some("state-enumeration"),
        _ => None,
    }
}

pub fn default_adapter_contract(source: Option<&str>) -> Option<&'static str> {
    match source {
        Some("probe-command") => Some("explicit-probe-command"),
        Some(_) => Some("formal-native-backend"),
        None => None,
    }
}

pub fn enrich_payload(
    modality: &str,
    execution_path: Option<&str>,
    source: Option<&str>,
    adapter_contract: Option<&str>,
    payload: Option<Value>,
) -> Option<Value> {
    match payload {
        Some(Value::Object(mut object)) => {
            enrich_object(
                modality,
                execution_path,
                source,
                adapter_contract,
                &mut object,
            );
            Some(Value::Object(object))
        }
        other => other,
    }
}

pub fn enrich_object(
    modality: &str,
    execution_path: Option<&str>,
    source: Option<&str>,
    adapter_contract: Option<&str>,
    object: &mut Map<String, Value>,
) {
    let should_enrich = source.is_some()
        || matches!(
            execution_path,
            Some("native-live") | Some("native-ready") | Some("native-state-bridge")
        );
    if !should_enrich {
        return;
    }

    if !object.contains_key("release_grade_backend") {
        if let Some(value) = object
            .get("release_grade_backend_id")
            .cloned()
            .or_else(|| default_backend_id(modality).map(|id| json!(id)))
        {
            object.insert("release_grade_backend".to_string(), value);
        }
    }

    if !object.contains_key("release_grade_backend_id") {
        if let Some(value) = object
            .get("release_grade_backend")
            .cloned()
            .or_else(|| default_backend_id(modality).map(|id| json!(id)))
        {
            object.insert("release_grade_backend_id".to_string(), value);
        }
    }

    if !object.contains_key("release_grade_backend_stack") {
        if let Some(stack) = default_backend_stack(modality) {
            object.insert("release_grade_backend_stack".to_string(), json!(stack));
        }
    }

    if !object.contains_key("release_grade_backend_origin") {
        if let Some(origin) = infer_origin(source, execution_path) {
            object.insert("release_grade_backend_origin".to_string(), json!(origin));
        }
    }

    if !object.contains_key("release_grade_contract_kind") {
        if let Some(value) = payload_contract_kind(object)
            .or_else(|| adapter_contract.map(str::to_string))
            .or_else(|| default_adapter_contract(source).map(str::to_string))
        {
            object.insert("release_grade_contract_kind".to_string(), json!(value));
        }
    }
}

fn payload_contract_kind(object: &Map<String, Value>) -> Option<String> {
    object
        .get("session_contract")
        .and_then(Value::as_object)
        .and_then(|contract| contract.get("contract_kind"))
        .and_then(Value::as_str)
        .map(str::to_string)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn enrich_object_adds_defaults_for_ready_state() {
        let mut object = Map::new();
        object.insert("backend_ready".to_string(), json!(true));

        enrich_object(
            "screen",
            Some("native-ready"),
            None,
            Some("formal-native-backend"),
            &mut object,
        );

        assert_eq!(
            object
                .get("release_grade_backend_id")
                .and_then(Value::as_str),
            Some("xdg-desktop-portal-screencast")
        );
        assert_eq!(
            object
                .get("release_grade_backend_origin")
                .and_then(Value::as_str),
            Some("declared-ready")
        );
        assert_eq!(
            object
                .get("release_grade_contract_kind")
                .and_then(Value::as_str),
            Some("formal-native-backend")
        );
    }

    #[test]
    fn infer_origin_prefers_state_bridge_execution_path() {
        assert_eq!(
            infer_origin(Some("builtin-probe"), Some("native-state-bridge")),
            Some("state-bridge")
        );
    }

    #[test]
    fn enrich_payload_preserves_existing_contract_kind() {
        let payload = enrich_payload(
            "screen",
            None,
            Some("builtin-screen-live-command"),
            Some("formal-native-backend"),
            Some(json!({
                "release_grade_contract_kind": "release-grade-runtime-helper",
                "stream_node_id": 7,
            })),
        )
        .expect("payload");

        assert_eq!(
            payload
                .get("release_grade_contract_kind")
                .and_then(Value::as_str),
            Some("release-grade-runtime-helper")
        );
        assert_eq!(
            payload
                .get("release_grade_backend_origin")
                .and_then(Value::as_str),
            Some("runtime-helper")
        );
    }
}
