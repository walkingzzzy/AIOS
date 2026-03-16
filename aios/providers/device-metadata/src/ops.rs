use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

use chrono::Utc;
use serde::Deserialize;

use aios_contracts::{
    DeviceBackendSummary, DeviceCapabilityDescriptor, DeviceCaptureAdapterPlan,
    DeviceMetadataEntry, DeviceMetadataGetRequest, DeviceMetadataGetResponse,
    DeviceMetadataReadinessSummary, DeviceStateGetResponse, UiTreeSupportMatrixEntry,
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
            "backend_overall_status={}",
            device_state.backend_summary.overall_status
        ),
        format!(
            "backend_available_status_count={}",
            device_state.backend_summary.available_status_count
        ),
        format!(
            "backend_attention_count={}",
            device_state.backend_summary.attention_count
        ),
        format!(
            "ui_tree_support_entries={}",
            device_state.ui_tree_support_matrix.len()
        ),
    ];
    if let Some(capture_mode) = &device_state.backend_summary.ui_tree_capture_mode {
        notes.push(format!("backend_ui_tree_capture_mode={capture_mode}"));
    }
    if !view.summary.unknown_modalities.is_empty() {
        notes.push(format!(
            "unknown_modalities={}",
            view.summary.unknown_modalities.join(",")
        ));
    }
    if request.include_state_notes {
        notes.extend(device_state.notes.clone());
    }
    append_release_grade_summary_notes(&mut notes, &view.entries);

    DeviceMetadataGetResponse {
        provider_id: state.config.provider_id.clone(),
        device_service_id: device_state.service_id.clone(),
        generated_at: Utc::now().to_rfc3339(),
        entries: view.entries,
        available_modalities: view.available_modalities,
        active_capture_count: view.summary.active_capture_count,
        summary: view.summary,
        backend_summary: device_state.backend_summary.clone(),
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
        backend_summary: DeviceBackendSummary {
            overall_status: "unavailable".to_string(),
            ..DeviceBackendSummary::default()
        },
        ui_tree_support_matrix: Vec::new(),
        notes: vec![
            format!("deviced_socket={}", state.config.deviced_socket.display()),
            format!(
                "requested_modalities={}",
                format_modalities_note(&requested_modalities)
            ),
            "overall_status=unavailable".to_string(),
            "backend_overall_status=unavailable".to_string(),
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
    let mut backend_details = backend
        .map(|status| status.details.clone())
        .unwrap_or_default();
    if let Some(evidence) = read_backend_evidence_metadata(backend_details.as_slice()) {
        evidence.append_backend_details(&mut backend_details);
    }

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

fn append_release_grade_summary_notes(notes: &mut Vec<String>, entries: &[DeviceMetadataEntry]) {
    let mut backend_ids = BTreeSet::new();
    let mut origins = BTreeSet::new();
    let mut stacks = BTreeSet::new();
    let mut contract_kinds = BTreeSet::new();

    for entry in entries {
        if let Some(value) =
            entry_detail_value(entry, "release_grade_backend_id=").map(str::to_string)
        {
            push_unique_note(
                notes,
                format!("release_grade_backend_id[{}]={value}", entry.modality),
            );
            backend_ids.insert(value);
        }
        if let Some(value) =
            entry_detail_value(entry, "release_grade_backend_origin=").map(str::to_string)
        {
            push_unique_note(
                notes,
                format!("release_grade_backend_origin[{}]={value}", entry.modality),
            );
            origins.insert(value);
        }
        if let Some(value) =
            entry_detail_value(entry, "release_grade_backend_stack=").map(str::to_string)
        {
            push_unique_note(
                notes,
                format!("release_grade_backend_stack[{}]={value}", entry.modality),
            );
            stacks.insert(value);
        }
        if let Some(value) =
            entry_detail_value(entry, "release_grade_contract_kind=").map(str::to_string)
        {
            push_unique_note(
                notes,
                format!("release_grade_contract_kind[{}]={value}", entry.modality),
            );
            contract_kinds.insert(value);
        }
    }

    if !backend_ids.is_empty() {
        push_unique_note(
            notes,
            format!(
                "release_grade_backend_ids={}",
                backend_ids.into_iter().collect::<Vec<_>>().join(",")
            ),
        );
    }
    if !origins.is_empty() {
        push_unique_note(
            notes,
            format!(
                "release_grade_backend_origins={}",
                origins.into_iter().collect::<Vec<_>>().join(",")
            ),
        );
    }
    if !stacks.is_empty() {
        push_unique_note(
            notes,
            format!(
                "release_grade_backend_stacks={}",
                stacks.into_iter().collect::<Vec<_>>().join(",")
            ),
        );
    }
    if !contract_kinds.is_empty() {
        push_unique_note(
            notes,
            format!(
                "release_grade_contract_kinds={}",
                contract_kinds.into_iter().collect::<Vec<_>>().join(",")
            ),
        );
    }
}

fn entry_detail_value<'a>(entry: &'a DeviceMetadataEntry, prefix: &str) -> Option<&'a str> {
    entry
        .backend_details
        .iter()
        .find_map(|detail| detail.strip_prefix(prefix))
}

fn push_unique_note(notes: &mut Vec<String>, note: String) {
    if !notes.iter().any(|item| item == &note) {
        notes.push(note);
    }
}

fn read_backend_evidence_metadata(details: &[String]) -> Option<ReleaseGradeBackendEvidence> {
    let artifact_path = backend_evidence_artifact_path(details)?;
    let payload = fs::read_to_string(artifact_path).ok()?;
    serde_json::from_str::<BackendEvidenceArtifact>(&payload)
        .ok()
        .map(ReleaseGradeBackendEvidence::from_artifact)
}

fn backend_evidence_artifact_path(details: &[String]) -> Option<&Path> {
    details
        .iter()
        .find_map(|detail| detail.strip_prefix("evidence_artifact="))
        .map(Path::new)
}

#[derive(Debug, Clone, Default, Deserialize)]
struct BackendEvidenceArtifact {
    #[serde(default)]
    baseline: String,
    #[serde(default)]
    source: Option<String>,
    #[serde(default)]
    release_grade_backend_id: Option<String>,
    #[serde(default)]
    release_grade_backend_origin: Option<String>,
    #[serde(default)]
    release_grade_backend_stack: Option<String>,
    #[serde(default)]
    contract_kind: Option<String>,
}

#[derive(Debug, Clone, Default)]
struct ReleaseGradeBackendEvidence {
    release_grade_backend_id: Option<String>,
    release_grade_backend_origin: Option<String>,
    release_grade_backend_stack: Option<String>,
    release_grade_contract_kind: Option<String>,
    baseline: Option<String>,
    source: Option<String>,
}

impl ReleaseGradeBackendEvidence {
    fn from_artifact(artifact: BackendEvidenceArtifact) -> Self {
        Self {
            release_grade_backend_id: artifact.release_grade_backend_id,
            release_grade_backend_origin: artifact.release_grade_backend_origin,
            release_grade_backend_stack: artifact.release_grade_backend_stack,
            release_grade_contract_kind: artifact.contract_kind,
            baseline: (!artifact.baseline.is_empty()).then_some(artifact.baseline),
            source: artifact.source,
        }
    }

    fn append_backend_details(&self, backend_details: &mut Vec<String>) {
        self.append_value(
            backend_details,
            "release_grade_backend_id",
            self.release_grade_backend_id.as_deref(),
        );
        self.append_value(
            backend_details,
            "release_grade_backend_origin",
            self.release_grade_backend_origin.as_deref(),
        );
        self.append_value(
            backend_details,
            "release_grade_backend_stack",
            self.release_grade_backend_stack.as_deref(),
        );
        self.append_value(
            backend_details,
            "release_grade_contract_kind",
            self.release_grade_contract_kind.as_deref(),
        );
        self.append_value(
            backend_details,
            "backend_baseline",
            self.baseline.as_deref(),
        );
        self.append_value(
            backend_details,
            "backend_evidence_source",
            self.source.as_deref(),
        );
    }

    fn append_value(&self, backend_details: &mut Vec<String>, key: &str, value: Option<&str>) {
        let Some(value) = value else {
            return;
        };
        let item = format!("{key}={value}");
        if !backend_details.iter().any(|detail| detail == &item) {
            backend_details.push(item);
        }
    }
}

#[cfg(test)]
mod tests {
    use std::{
        fs,
        sync::atomic::{AtomicU64, Ordering},
    };

    use chrono::Utc;
    use serde_json::json;

    use super::*;
    use aios_contracts::{
        DeviceBackendStatus, DeviceBackendSummary, DeviceCapabilityDescriptor,
        DeviceCaptureAdapterPlan, DeviceContinuousCollectorStatus,
    };
    use aios_core::{ProviderObservabilitySink, RegistrySyncStatus, ServicePaths};

    use crate::{config::Config, AppState};

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    fn app_state() -> AppState {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time before unix epoch")
            .as_nanos();
        let unique = TEST_COUNTER.fetch_add(1, Ordering::Relaxed);
        let root =
            std::env::temp_dir().join(format!("aios-device-metadata-ops-test-{stamp}-{unique}"));
        let observability_log_path = root.join("observability.jsonl");
        let config = Config {
            service_id: "aios-device-metadata-provider".to_string(),
            version: "0.1.0".to_string(),
            provider_id: "device.metadata.local".to_string(),
            paths: ServicePaths::from_service_name("device-metadata-ops-test"),
            deviced_socket: root.join("deviced.sock"),
            agentd_socket: root.join("agentd.sock"),
            descriptor_path: root.join("device.metadata.local.json"),
            observability_log_path: observability_log_path.clone(),
        };
        AppState {
            config,
            started_at: Utc::now(),
            registry_sync: RegistrySyncStatus::new(1),
            observability: ProviderObservabilitySink::new(
                observability_log_path,
                "aios-device-metadata-provider",
                "device.metadata.local",
            )
            .expect("provider observability sink"),
        }
    }

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
            backend_summary: DeviceBackendSummary {
                overall_status: "attention".to_string(),
                status_count: 2,
                available_status_count: 1,
                adapter_count: 2,
                attention_count: 1,
                continuous_collector_count: 1,
                ui_tree_support_route_count: 2,
                ui_tree_support_ready_count: 2,
                ui_tree_snapshot_present: true,
                ui_tree_capture_mode: Some("native-live".to_string()),
                ui_tree_current_support: Some("native-live".to_string()),
                readiness_summary: BTreeMap::from([
                    ("missing-camera-devices".to_string(), 1),
                    ("native-live".to_string(), 1),
                ]),
                evidence_artifact_count: 2,
                evidence_present_count: 2,
                evidence_missing_count: 0,
                evidence_baselines: vec![
                    "os-native-backend".to_string(),
                    "state-bridge-baseline".to_string(),
                ],
            },
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

    fn write_backend_evidence(
        root: &std::path::Path,
        modality: &str,
        payload: serde_json::Value,
    ) -> std::path::PathBuf {
        fs::create_dir_all(root).expect("create evidence dir");
        let path = root.join(format!("{modality}-backend-evidence.json"));
        fs::write(
            &path,
            serde_json::to_vec_pretty(&payload).expect("serialize evidence payload"),
        )
        .expect("write evidence artifact");
        path
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
    #[test]
    fn build_device_metadata_response_preserves_backend_summary() {
        let app = app_state();
        let response = build_device_metadata_response(
            &app,
            &DeviceMetadataGetRequest {
                modalities: vec!["screen".to_string(), "camera".to_string()],
                only_available: false,
                include_state_notes: false,
            },
            &state(),
        );

        assert_eq!(response.backend_summary.overall_status, "attention");
        assert_eq!(response.backend_summary.available_status_count, 1);
        assert_eq!(response.backend_summary.attention_count, 1);
        assert_eq!(
            response.backend_summary.ui_tree_capture_mode.as_deref(),
            Some("native-live")
        );
        assert_eq!(
            response
                .backend_summary
                .readiness_summary
                .get("missing-camera-devices"),
            Some(&1)
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "backend_overall_status=attention"),
            "metadata notes should expose backend overall status"
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "backend_attention_count=1"),
            "metadata notes should expose backend attention count"
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "backend_ui_tree_capture_mode=native-live"),
            "metadata notes should expose backend ui_tree capture mode"
        );
    }

    #[test]
    fn build_device_metadata_response_adds_release_grade_backend_details_and_notes() {
        let app = app_state();
        let evidence_root = app
            .config
            .deviced_socket
            .parent()
            .expect("deviced socket parent");
        let screen_evidence = write_backend_evidence(
            evidence_root,
            "screen",
            json!({
                "baseline": "os-native-backend",
                "source": "deviced-runtime-helper",
                "release_grade_backend_id": "xdg-desktop-portal-screencast",
                "release_grade_backend_origin": "os-native",
                "release_grade_backend_stack": "portal+pipewire",
                "contract_kind": "release-grade-runtime-helper"
            }),
        );

        let mut device_state = state();
        let screen_backend = device_state
            .backend_statuses
            .iter_mut()
            .find(|status| status.modality == "screen")
            .expect("screen backend status");
        screen_backend
            .details
            .push(format!("evidence_artifact={}", screen_evidence.display()));

        let response = build_device_metadata_response(
            &app,
            &DeviceMetadataGetRequest {
                modalities: vec!["screen".to_string()],
                only_available: false,
                include_state_notes: false,
            },
            &device_state,
        );

        let screen_entry = response
            .entries
            .iter()
            .find(|entry| entry.modality == "screen")
            .expect("screen entry");
        assert!(
            screen_entry
                .backend_details
                .iter()
                .any(|item| item == "release_grade_backend_id=xdg-desktop-portal-screencast"),
            "screen entry should expose release-grade backend id"
        );
        assert!(
            screen_entry
                .backend_details
                .iter()
                .any(|item| item == "release_grade_backend_origin=os-native"),
            "screen entry should expose release-grade backend origin"
        );
        assert!(
            screen_entry
                .backend_details
                .iter()
                .any(|item| item == "release_grade_backend_stack=portal+pipewire"),
            "screen entry should expose release-grade backend stack"
        );
        assert!(
            screen_entry
                .backend_details
                .iter()
                .any(|item| item == "release_grade_contract_kind=release-grade-runtime-helper"),
            "screen entry should expose release-grade contract kind"
        );
        assert!(
            response.notes.iter().any(
                |note| note == "release_grade_backend_id[screen]=xdg-desktop-portal-screencast"
            ),
            "metadata response should expose screen release-grade backend id"
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "release_grade_backend_ids=xdg-desktop-portal-screencast"),
            "metadata response should expose aggregated release-grade backend ids"
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "release_grade_contract_kinds=release-grade-runtime-helper"),
            "metadata response should expose aggregated release-grade contract kinds"
        );
    }

    #[test]
    fn build_unavailable_response_sets_backend_summary_unavailable() {
        let app = app_state();
        let response = build_unavailable_response(
            &app,
            &DeviceMetadataGetRequest {
                modalities: vec!["screen".to_string(), "camera".to_string()],
                only_available: false,
                include_state_notes: false,
            },
            "deviced offline".to_string(),
        );

        assert_eq!(response.summary.overall_status, "unavailable");
        assert_eq!(response.backend_summary.overall_status, "unavailable");
        assert_eq!(response.backend_summary.available_status_count, 0);
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "backend_overall_status=unavailable"),
            "metadata outage notes should expose backend overall status"
        );
    }
}
