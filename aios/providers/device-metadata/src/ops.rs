use std::collections::{BTreeMap, BTreeSet};

use chrono::Utc;

use aios_contracts::{
    DeviceCapabilityDescriptor, DeviceCaptureAdapterPlan, DeviceMetadataEntry,
    DeviceMetadataGetRequest, DeviceMetadataGetResponse, DeviceMetadataReadinessSummary,
    DeviceStateGetResponse, UiTreeSupportMatrixEntry,
};

use crate::AppState;

pub fn get_device_metadata(
    state: &AppState,
    request: &DeviceMetadataGetRequest,
) -> DeviceMetadataGetResponse {
    match crate::clients::fetch_device_state(state) {
        Ok(device_state) => build_device_metadata_response(state, request, &device_state),
        Err(error) => build_unavailable_response(state, request, error.to_string()),
    }
}

fn build_device_metadata_response(
    state: &AppState,
    request: &DeviceMetadataGetRequest,
    device_state: &DeviceStateGetResponse,
) -> DeviceMetadataGetResponse {
    let view = build_view(device_state, request);

    let mut notes = vec![
        format!("deviced_socket={}", state.config.deviced_socket.display()),
        format!(
            "requested_modalities={}",
            format_modalities_note(&view.summary.requested_modalities)
        ),
        format!("only_available={}", request.only_available),
        format!("entry_count={}", view.entries.len()),
        format!("active_capture_count={}", view.summary.active_capture_count),
        format!(
            "continuous_collector_count={}",
            view.summary.continuous_collector_count
        ),
        format!("overall_status={}", view.summary.overall_status),
        format!(
            "ui_tree_support_entries={}",
            device_state.ui_tree_support_matrix.len()
        ),
    ];
    if !view.summary.unknown_modalities.is_empty() {
        notes.push(format!(
            "unknown_modalities={}",
            view.summary.unknown_modalities.join(",")
        ));
    }
    if request.include_state_notes {
        notes.extend(device_state.notes.clone());
    }

    DeviceMetadataGetResponse {
        provider_id: state.config.provider_id.clone(),
        device_service_id: device_state.service_id.clone(),
        generated_at: Utc::now().to_rfc3339(),
        entries: view.entries,
        available_modalities: view.available_modalities,
        active_capture_count: view.summary.active_capture_count,
        summary: view.summary,
        ui_tree_support_matrix: device_state.ui_tree_support_matrix.clone(),
        notes,
    }
}

fn build_unavailable_response(
    state: &AppState,
    request: &DeviceMetadataGetRequest,
    error: String,
) -> DeviceMetadataGetResponse {
    let requested_modalities = normalize_requested_modalities(request);
    let unavailable_modalities = requested_modalities.clone();
    let summary = DeviceMetadataReadinessSummary {
        overall_status: "unavailable".to_string(),
        requested_modalities: requested_modalities.clone(),
        available_modalities: Vec::new(),
        unavailable_modalities,
        conditional_modalities: Vec::new(),
        unknown_modalities: Vec::new(),
        active_capture_count: 0,
        continuous_collector_count: 0,
        ui_tree_available: false,
        ui_tree_snapshot_attached: false,
    };

    DeviceMetadataGetResponse {
        provider_id: state.config.provider_id.clone(),
        device_service_id: "aios-deviced".to_string(),
        generated_at: Utc::now().to_rfc3339(),
        entries: Vec::new(),
        available_modalities: Vec::new(),
        active_capture_count: 0,
        summary,
        ui_tree_support_matrix: Vec::new(),
        notes: vec![
            format!("deviced_socket={}", state.config.deviced_socket.display()),
            format!(
                "requested_modalities={}",
                format_modalities_note(&requested_modalities)
            ),
            "overall_status=unavailable".to_string(),
            "device_state_source=unavailable".to_string(),
            format!("device_state_error={}", compact_note_value(error)),
        ],
    }
}

fn build_view(
    device_state: &DeviceStateGetResponse,
    request: &DeviceMetadataGetRequest,
) -> DeviceMetadataView {
    let requested_modalities = normalize_requested_modalities(request);
    let known_modalities = device_state
        .capabilities
        .iter()
        .map(|capability| capability.modality.to_ascii_lowercase())
        .collect::<BTreeSet<_>>();

    let unknown_modalities = requested_modalities
        .iter()
        .filter(|modality| !known_modalities.contains(*modality))
        .cloned()
        .collect::<Vec<_>>();

    let effective_requested = if requested_modalities.is_empty() {
        known_modalities.iter().cloned().collect::<Vec<_>>()
    } else {
        requested_modalities.clone()
    };
    let all_entries = build_entries(device_state, &effective_requested);
    let entries = all_entries
        .iter()
        .filter(|entry| !request.only_available || entry.available)
        .cloned()
        .collect::<Vec<_>>();
    let available_modalities = all_entries
        .iter()
        .filter(|entry| entry.available)
        .map(|entry| entry.modality.clone())
        .collect::<Vec<_>>();
    let summary = build_readiness_summary(
        device_state,
        &effective_requested,
        &all_entries,
        &unknown_modalities,
    );

    DeviceMetadataView {
        entries,
        available_modalities,
        summary,
    }
}

fn build_entries(
    device_state: &DeviceStateGetResponse,
    requested_modalities: &[String],
) -> Vec<DeviceMetadataEntry> {
    let requested_modalities = requested_modalities
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();

    let backend_map = device_state
        .backend_statuses
        .iter()
        .map(|status| (status.modality.to_ascii_lowercase(), status))
        .collect::<BTreeMap<_, _>>();
    let adapter_map = device_state
        .capture_adapters
        .iter()
        .map(|adapter| (adapter.modality.to_ascii_lowercase(), adapter))
        .collect::<BTreeMap<_, _>>();

    let mut entries = device_state
        .capabilities
        .iter()
        .filter(|capability| {
            requested_modalities.is_empty()
                || requested_modalities.contains(&capability.modality.to_ascii_lowercase())
        })
        .map(|capability| {
            build_entry(
                capability,
                backend_map
                    .get(&capability.modality.to_ascii_lowercase())
                    .copied(),
                adapter_map
                    .get(&capability.modality.to_ascii_lowercase())
                    .copied(),
            )
        })
        .collect::<Vec<_>>();

    entries.sort_by(|left, right| left.modality.cmp(&right.modality));
    entries
}

fn build_entry(
    capability: &DeviceCapabilityDescriptor,
    backend: Option<&aios_contracts::DeviceBackendStatus>,
    adapter: Option<&DeviceCaptureAdapterPlan>,
) -> DeviceMetadataEntry {
    let backend_available = backend.map(|status| status.available).unwrap_or(true);
    let backend_readiness = backend
        .map(|status| status.readiness.clone())
        .unwrap_or_else(|| {
            if capability.available {
                "capability-only".to_string()
            } else {
                "unavailable".to_string()
            }
        });
    let backend_details = backend
        .map(|status| status.details.clone())
        .unwrap_or_default();

    let mut notes = capability.notes.clone();
    if let Some(adapter) = adapter {
        notes.push(format!("adapter_backend={}", adapter.backend));
    }

    DeviceMetadataEntry {
        modality: capability.modality.clone(),
        source_backend: capability.source_backend.clone(),
        available: capability.available && backend_available,
        conditional: capability.conditional,
        readiness: backend_readiness,
        backend_details,
        adapter_id: adapter.map(|item| item.adapter_id.clone()),
        adapter_execution_path: adapter.map(|item| item.execution_path.clone()),
        notes,
    }
}

fn build_readiness_summary(
    device_state: &DeviceStateGetResponse,
    requested_modalities: &[String],
    entries: &[DeviceMetadataEntry],
    unknown_modalities: &[String],
) -> DeviceMetadataReadinessSummary {
    let available_modalities = entries
        .iter()
        .filter(|entry| entry.available)
        .map(|entry| entry.modality.clone())
        .collect::<BTreeSet<_>>();
    let conditional_modalities = entries
        .iter()
        .filter(|entry| entry.conditional)
        .map(|entry| entry.modality.clone())
        .collect::<BTreeSet<_>>();
    let mut unavailable_modalities = entries
        .iter()
        .filter(|entry| !entry.available)
        .map(|entry| entry.modality.clone())
        .collect::<BTreeSet<_>>();
    unavailable_modalities.extend(unknown_modalities.iter().cloned());

    let overall_status = if entries.is_empty() && unavailable_modalities.is_empty() {
        "unavailable".to_string()
    } else if unavailable_modalities.is_empty() {
        "ready".to_string()
    } else if available_modalities.is_empty() {
        "unavailable".to_string()
    } else {
        "degraded".to_string()
    };

    DeviceMetadataReadinessSummary {
        overall_status,
        requested_modalities: requested_modalities.to_vec(),
        available_modalities: available_modalities.into_iter().collect(),
        unavailable_modalities: unavailable_modalities.into_iter().collect(),
        conditional_modalities: conditional_modalities.into_iter().collect(),
        unknown_modalities: unknown_modalities.to_vec(),
        active_capture_count: device_state.active_captures.len() as u32,
        continuous_collector_count: device_state.continuous_collectors.len() as u32,
        ui_tree_available: current_ui_tree_available(&device_state.ui_tree_support_matrix),
        ui_tree_snapshot_attached: device_state.ui_tree_snapshot.is_some(),
    }
}

fn current_ui_tree_available(matrix: &[UiTreeSupportMatrixEntry]) -> bool {
    matrix
        .iter()
        .find(|entry| entry.current)
        .map(|entry| entry.available)
        .unwrap_or_else(|| matrix.iter().any(|entry| entry.available))
}

fn normalize_requested_modalities(request: &DeviceMetadataGetRequest) -> Vec<String> {
    request
        .modalities
        .iter()
        .map(|item| item.trim().to_ascii_lowercase())
        .filter(|item| !item.is_empty())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn format_modalities_note(modalities: &[String]) -> String {
    if modalities.is_empty() {
        "<all>".to_string()
    } else {
        modalities.join(",")
    }
}

fn compact_note_value(value: impl AsRef<str>) -> String {
    let mut compact = value.as_ref().replace('\n', " ");
    if compact.len() > 160 {
        compact.truncate(157);
        compact.push_str("...");
    }
    compact
}

struct DeviceMetadataView {
    entries: Vec<DeviceMetadataEntry>,
    available_modalities: Vec<String>,
    summary: DeviceMetadataReadinessSummary,
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use aios_contracts::{
        DeviceBackendStatus, DeviceCapabilityDescriptor, DeviceCaptureAdapterPlan,
        DeviceContinuousCollectorStatus,
    };

    fn state() -> DeviceStateGetResponse {
        DeviceStateGetResponse {
            service_id: "aios-deviced".to_string(),
            capabilities: vec![
                DeviceCapabilityDescriptor {
                    modality: "screen".to_string(),
                    available: true,
                    conditional: false,
                    source_backend: "screen-capture-portal".to_string(),
                    notes: vec!["screen-capability".to_string()],
                },
                DeviceCapabilityDescriptor {
                    modality: "camera".to_string(),
                    available: true,
                    conditional: true,
                    source_backend: "pipewire-camera".to_string(),
                    notes: vec!["camera-capability".to_string()],
                },
            ],
            active_captures: vec![],
            backend_statuses: vec![
                DeviceBackendStatus {
                    modality: "screen".to_string(),
                    backend: "screen-capture-portal".to_string(),
                    available: true,
                    readiness: "native-live".to_string(),
                    details: vec!["probe_source=builtin".to_string()],
                },
                DeviceBackendStatus {
                    modality: "camera".to_string(),
                    backend: "pipewire-camera".to_string(),
                    available: false,
                    readiness: "missing-camera-devices".to_string(),
                    details: vec!["device_count=0".to_string()],
                },
            ],
            capture_adapters: vec![
                DeviceCaptureAdapterPlan {
                    modality: "screen".to_string(),
                    backend: "screen-capture-portal".to_string(),
                    adapter_id: "screen.portal-probe".to_string(),
                    execution_path: "native-live".to_string(),
                    preview_object_kind: "screen_frame".to_string(),
                    notes: vec![],
                },
                DeviceCaptureAdapterPlan {
                    modality: "camera".to_string(),
                    backend: "pipewire-camera".to_string(),
                    adapter_id: "camera.v4l-state-root".to_string(),
                    execution_path: "native-state-bridge".to_string(),
                    preview_object_kind: "camera_frame".to_string(),
                    notes: vec![],
                },
            ],
            ui_tree_snapshot: Some(json!({
                "snapshot_id": "tree-1",
                "capture_mode": "native-live",
                "focus_node": "screen-1",
            })),
            continuous_collectors: vec![DeviceContinuousCollectorStatus {
                capture_id: "cap-1".to_string(),
                modality: "audio".to_string(),
                backend: "pipewire-audio".to_string(),
                collector_mode: "continuous".to_string(),
                status: "running".to_string(),
                updated_at: "2026-03-13T00:00:00Z".to_string(),
                sample_count: 4,
                details: vec!["sample_rate=16000".to_string()],
            }],
            ui_tree_support_matrix: vec![
                UiTreeSupportMatrixEntry {
                    environment_id: "atspi-live".to_string(),
                    available: true,
                    readiness: "native-live".to_string(),
                    current: true,
                    desktop_environment: Some("gnome".to_string()),
                    session_type: Some("wayland".to_string()),
                    adapter_id: Some("ui_tree.atspi-probe".to_string()),
                    execution_path: Some("native-live".to_string()),
                    stability: Some("desktop-dependent".to_string()),
                    limitations: Vec::new(),
                    evidence: Vec::new(),
                    details: vec!["desktop=gnome".to_string()],
                },
                UiTreeSupportMatrixEntry {
                    environment_id: "screen-ocr-fallback".to_string(),
                    available: true,
                    readiness: "fallback".to_string(),
                    current: false,
                    desktop_environment: Some("gnome".to_string()),
                    session_type: Some("wayland".to_string()),
                    adapter_id: Some("screen.ocr-fallback".to_string()),
                    execution_path: Some("screen-frame+ocr".to_string()),
                    stability: Some("fallback".to_string()),
                    limitations: Vec::new(),
                    evidence: Vec::new(),
                    details: vec!["always_on".to_string()],
                },
            ],
            notes: vec![format!("metadata={}", json!({"ok": true}))],
        }
    }

    #[test]
    fn build_entries_combines_capability_backend_and_adapter_state() {
        let entries = build_entries(&state(), &[]);

        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].modality, "camera");
        assert!(!entries[0].available);
        assert_eq!(
            entries[0].adapter_execution_path.as_deref(),
            Some("native-state-bridge")
        );
        assert_eq!(entries[1].modality, "screen");
        assert!(entries[1].available);
        assert_eq!(
            entries[1].adapter_id.as_deref(),
            Some("screen.portal-probe")
        );
    }

    #[test]
    fn build_entries_filters_to_available_modalities() {
        let entries = build_entries(&state(), &["screen".to_string(), "camera".to_string()]);

        let filtered = entries
            .into_iter()
            .filter(|entry| entry.available)
            .collect::<Vec<_>>();

        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].modality, "screen");
    }

    #[test]
    fn build_readiness_summary_tracks_unknown_and_ui_tree_state() {
        let entries = build_entries(
            &state(),
            &[
                "screen".to_string(),
                "camera".to_string(),
                "lidar".to_string(),
            ],
        );
        let summary = build_readiness_summary(
            &state(),
            &[
                "screen".to_string(),
                "camera".to_string(),
                "lidar".to_string(),
            ],
            &entries,
            &["lidar".to_string()],
        );

        assert_eq!(summary.overall_status, "degraded");
        assert_eq!(summary.available_modalities, vec!["screen".to_string()]);
        assert_eq!(
            summary.unavailable_modalities,
            vec!["camera".to_string(), "lidar".to_string()]
        );
        assert_eq!(summary.conditional_modalities, vec!["camera".to_string()]);
        assert_eq!(summary.unknown_modalities, vec!["lidar".to_string()]);
        assert_eq!(summary.continuous_collector_count, 1);
        assert!(summary.ui_tree_available);
        assert!(summary.ui_tree_snapshot_attached);
    }
}
