use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};

use chrono::Utc;
use serde::Deserialize;

use aios_contracts::{
    DeviceBackendSummary, DeviceCapabilityDescriptor, DeviceCaptureAdapterPlan,
    DeviceMetadataEntry, DeviceMetadataGetRequest, DeviceMetadataGetResponse,
    DeviceMetadataReadinessSummary, DeviceStateGetResponse, UiTreeSupportMatrixEntry,
};

use crate::{config::Config, AppState};

const UI_TREE_MODALITY: &str = "ui_tree";
const UI_TREE_DEFAULT_BACKEND: &str = "at-spi";

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
    let mut view = build_view(device_state, request);
    let all_entries = build_entries(device_state, &[]);
    let hardware_profile = load_hardware_profile_context(&state.config, &all_entries);
    if let Ok(Some(profile_context)) = &hardware_profile {
        apply_hardware_profile_context(&mut view.entries, profile_context);
    }

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
    append_hardware_profile_notes(&mut notes, &state.config, &hardware_profile);

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
    let mut notes = vec![
        format!("deviced_socket={}", state.config.deviced_socket.display()),
        format!(
            "requested_modalities={}",
            format_modalities_note(&requested_modalities)
        ),
        "overall_status=unavailable".to_string(),
        "backend_overall_status=unavailable".to_string(),
        "device_state_source=unavailable".to_string(),
        format!("device_state_error={}", compact_note_value(error)),
    ];
    append_hardware_profile_unavailable_notes(&mut notes, &state.config);

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
        notes,
    }
}

fn build_view(
    device_state: &DeviceStateGetResponse,
    request: &DeviceMetadataGetRequest,
) -> DeviceMetadataView {
    let requested_modalities = normalize_requested_modalities(request);
    let known_modalities = known_modalities(device_state);

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

    if supports_ui_tree_metadata(device_state)
        && (requested_modalities.is_empty() || requested_modalities.contains(UI_TREE_MODALITY))
        && !entries
            .iter()
            .any(|entry| entry.modality == UI_TREE_MODALITY)
    {
        entries.push(build_ui_tree_entry(
            device_state,
            backend_map.get(UI_TREE_MODALITY).copied(),
            adapter_map.get(UI_TREE_MODALITY).copied(),
        ));
    }

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

fn build_ui_tree_entry(
    device_state: &DeviceStateGetResponse,
    backend: Option<&aios_contracts::DeviceBackendStatus>,
    adapter: Option<&DeviceCaptureAdapterPlan>,
) -> DeviceMetadataEntry {
    let current_support = preferred_ui_tree_support(&device_state.ui_tree_support_matrix);
    let available = current_support
        .map(|entry| entry.available)
        .or_else(|| backend.map(|status| status.available))
        .unwrap_or_else(|| current_ui_tree_available(&device_state.ui_tree_support_matrix));
    let readiness = current_support
        .map(|entry| entry.readiness.clone())
        .or_else(|| backend.map(|status| status.readiness.clone()))
        .unwrap_or_else(|| "unsupported".to_string());
    let source_backend = backend
        .map(|status| status.backend.clone())
        .or_else(|| adapter.map(|plan| plan.backend.clone()))
        .unwrap_or_else(|| UI_TREE_DEFAULT_BACKEND.to_string());
    let mut backend_details = backend
        .map(|status| status.details.clone())
        .unwrap_or_default();
    if let Some(evidence) = read_backend_evidence_metadata(backend_details.as_slice()) {
        evidence.append_backend_details(&mut backend_details);
    }
    append_ui_tree_support_matrix_details(
        &mut backend_details,
        &device_state.ui_tree_support_matrix,
        current_support,
    );

    let mut notes = vec![format!(
        "ui_tree_snapshot_attached={}",
        device_state.ui_tree_snapshot.is_some()
    )];
    if let Some(capture_mode) = &device_state.backend_summary.ui_tree_capture_mode {
        notes.push(format!("ui_tree_capture_mode={capture_mode}"));
    }
    if let Some(adapter) = adapter {
        notes.push(format!("adapter_backend={}", adapter.backend));
    }
    if let Some(current_support) = current_support {
        notes.push(format!(
            "ui_tree_current_environment_id={}",
            current_support.environment_id
        ));
        if let Some(stability) = current_support.stability.as_deref() {
            notes.push(format!("ui_tree_current_stability={stability}"));
        }
    }

    DeviceMetadataEntry {
        modality: UI_TREE_MODALITY.to_string(),
        source_backend,
        available,
        conditional: true,
        readiness,
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

fn known_modalities(device_state: &DeviceStateGetResponse) -> BTreeSet<String> {
    let mut known_modalities = device_state
        .capabilities
        .iter()
        .map(|capability| capability.modality.to_ascii_lowercase())
        .collect::<BTreeSet<_>>();
    if supports_ui_tree_metadata(device_state) {
        known_modalities.insert(UI_TREE_MODALITY.to_string());
    }
    known_modalities
}

fn supports_ui_tree_metadata(device_state: &DeviceStateGetResponse) -> bool {
    device_state
        .backend_statuses
        .iter()
        .any(|status| status.modality == UI_TREE_MODALITY)
        || device_state
            .capture_adapters
            .iter()
            .any(|adapter| adapter.modality == UI_TREE_MODALITY)
        || !device_state.ui_tree_support_matrix.is_empty()
        || device_state.ui_tree_snapshot.is_some()
}

fn preferred_ui_tree_support<'a>(
    matrix: &'a [UiTreeSupportMatrixEntry],
) -> Option<&'a UiTreeSupportMatrixEntry> {
    matrix
        .iter()
        .find(|entry| entry.current)
        .or_else(|| matrix.iter().find(|entry| entry.available))
        .or_else(|| matrix.first())
}

fn append_ui_tree_support_matrix_details(
    backend_details: &mut Vec<String>,
    matrix: &[UiTreeSupportMatrixEntry],
    current_support: Option<&UiTreeSupportMatrixEntry>,
) {
    push_unique_detail(
        backend_details,
        format!("ui_tree_support_route_count={}", matrix.len()),
    );
    push_unique_detail(
        backend_details,
        format!(
            "ui_tree_support_ready_count={}",
            matrix.iter().filter(|entry| entry.available).count()
        ),
    );

    let Some(current_support) = current_support else {
        return;
    };

    push_unique_detail(
        backend_details,
        format!(
            "ui_tree_current_environment_id={}",
            current_support.environment_id
        ),
    );
    push_unique_detail(
        backend_details,
        format!("ui_tree_current_available={}", current_support.available),
    );
    push_unique_detail(
        backend_details,
        format!("ui_tree_current_readiness={}", current_support.readiness),
    );
    if let Some(value) = current_support.desktop_environment.as_deref() {
        push_unique_detail(
            backend_details,
            format!("ui_tree_current_desktop_environment={value}"),
        );
    }
    if let Some(value) = current_support.session_type.as_deref() {
        push_unique_detail(
            backend_details,
            format!("ui_tree_current_session_type={value}"),
        );
    }
    if let Some(value) = current_support.adapter_id.as_deref() {
        push_unique_detail(
            backend_details,
            format!("ui_tree_current_adapter_id={value}"),
        );
    }
    if let Some(value) = current_support.execution_path.as_deref() {
        push_unique_detail(
            backend_details,
            format!("ui_tree_current_execution_path={value}"),
        );
    }
    if let Some(value) = current_support.stability.as_deref() {
        push_unique_detail(
            backend_details,
            format!("ui_tree_current_stability={value}"),
        );
    }
    for limitation in &current_support.limitations {
        push_unique_detail(backend_details, format!("ui_tree_limitation={limitation}"));
    }
    for evidence in &current_support.evidence {
        push_unique_detail(backend_details, format!("ui_tree_evidence={evidence}"));
    }
    for detail in &current_support.details {
        push_unique_detail(backend_details, format!("ui_tree_detail={detail}"));
    }
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

#[derive(Debug, Clone)]
struct LoadedHardwareProfile {
    path: PathBuf,
    profile: HardwareProfile,
}

#[derive(Debug, Clone, Default, Deserialize)]
struct HardwareProfile {
    id: String,
    #[serde(default)]
    platform_tier: String,
    #[serde(default)]
    gpu: String,
    #[serde(default)]
    audio: String,
    #[serde(default)]
    camera: String,
    #[serde(default)]
    canonical_hardware_profile_id: String,
    #[serde(default)]
    platform_media_id: String,
    #[serde(default)]
    runtime_profile: String,
    #[serde(default)]
    bringup_status: String,
    #[serde(default)]
    hardware_evidence_required: bool,
    #[serde(default)]
    release_track_intent: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ModalityExpectation {
    Required,
    Conditional,
}

impl ModalityExpectation {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Required => "required",
            Self::Conditional => "conditional",
        }
    }
}

#[derive(Debug, Clone)]
struct HardwareProfileContext {
    loaded: LoadedHardwareProfile,
    expectations: BTreeMap<String, ModalityExpectation>,
    required_modalities: Vec<String>,
    conditional_modalities: Vec<String>,
    available_expected_modalities: Vec<String>,
    missing_required_modalities: Vec<String>,
    missing_conditional_modalities: Vec<String>,
    validation_status: String,
}

impl HardwareProfileContext {
    fn from_loaded_profile(loaded: LoadedHardwareProfile, entries: &[DeviceMetadataEntry]) -> Self {
        let expectations = build_hardware_profile_expectations(&loaded.profile);
        let available_map = entries
            .iter()
            .map(|entry| (entry.modality.to_ascii_lowercase(), entry.available))
            .collect::<BTreeMap<_, _>>();
        let required_modalities = expected_modalities(&expectations, ModalityExpectation::Required);
        let conditional_modalities =
            expected_modalities(&expectations, ModalityExpectation::Conditional);
        let mut available_expected_modalities = Vec::new();
        let mut missing_required_modalities = Vec::new();
        let mut missing_conditional_modalities = Vec::new();

        for (modality, expectation) in &expectations {
            if available_map.get(modality).copied().unwrap_or(false) {
                available_expected_modalities.push(modality.clone());
            } else if *expectation == ModalityExpectation::Required {
                missing_required_modalities.push(modality.clone());
            } else {
                missing_conditional_modalities.push(modality.clone());
            }
        }

        let validation_status = if !missing_required_modalities.is_empty() {
            "missing-required-modalities".to_string()
        } else if !missing_conditional_modalities.is_empty() {
            "conditional-gap".to_string()
        } else {
            "matched".to_string()
        };

        Self {
            loaded,
            expectations,
            required_modalities,
            conditional_modalities,
            available_expected_modalities,
            missing_required_modalities,
            missing_conditional_modalities,
            validation_status,
        }
    }

    fn append_notes(&self, notes: &mut Vec<String>) {
        push_unique_note(
            notes,
            format!("hardware_profile_path={}", self.loaded.path.display()),
        );
        push_unique_note(notes, "hardware_profile_status=loaded".to_string());
        push_unique_note(
            notes,
            format!("hardware_profile_id={}", self.loaded.profile.id),
        );
        if !self.loaded.profile.platform_tier.is_empty() {
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_platform_tier={}",
                    self.loaded.profile.platform_tier
                ),
            );
        }
        if !self.loaded.profile.bringup_status.is_empty() {
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_bringup_status={}",
                    self.loaded.profile.bringup_status
                ),
            );
        }
        push_unique_note(
            notes,
            format!(
                "hardware_profile_canonical_id={}",
                if self.loaded.profile.canonical_hardware_profile_id.is_empty() {
                    self.loaded.profile.id.as_str()
                } else {
                    self.loaded.profile.canonical_hardware_profile_id.as_str()
                }
            ),
        );
        if !self.loaded.profile.platform_media_id.is_empty() {
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_platform_media_id={}",
                    self.loaded.profile.platform_media_id
                ),
            );
        }
        if !self.loaded.profile.runtime_profile.is_empty() {
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_runtime_profile={}",
                    self.loaded.profile.runtime_profile
                ),
            );
        }
        push_unique_note(
            notes,
            format!(
                "hardware_profile_hardware_evidence_required={}",
                self.loaded.profile.hardware_evidence_required
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_release_track_intent={}",
                self.loaded.profile.release_track_intent.join(",")
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_expected_modalities={}",
                self.expectations
                    .keys()
                    .cloned()
                    .collect::<Vec<_>>()
                    .join(",")
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_required_modalities={}",
                self.required_modalities.join(",")
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_conditional_modalities={}",
                self.conditional_modalities.join(",")
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_available_expected_modalities={}",
                self.available_expected_modalities.join(",")
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_missing_required_modalities={}",
                self.missing_required_modalities.join(",")
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_missing_conditional_modalities={}",
                self.missing_conditional_modalities.join(",")
            ),
        );
        push_unique_note(
            notes,
            format!(
                "hardware_profile_validation_status={}",
                self.validation_status
            ),
        );
    }
}

fn load_hardware_profile_context(
    config: &Config,
    entries: &[DeviceMetadataEntry],
) -> Result<Option<HardwareProfileContext>, String> {
    Ok(load_hardware_profile(config)?
        .map(|loaded| HardwareProfileContext::from_loaded_profile(loaded, entries)))
}

fn load_hardware_profile(config: &Config) -> Result<Option<LoadedHardwareProfile>, String> {
    let Some(path) = config.hardware_profile_path.as_ref() else {
        return Ok(None);
    };
    let payload =
        fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let profile = serde_yaml::from_str::<HardwareProfile>(&payload)
        .map_err(|error| format!("{}: {error}", path.display()))?;
    if profile.id.trim().is_empty() {
        return Err(format!("{}: hardware profile id is empty", path.display()));
    }

    Ok(Some(LoadedHardwareProfile {
        path: path.clone(),
        profile,
    }))
}

fn append_hardware_profile_notes(
    notes: &mut Vec<String>,
    config: &Config,
    result: &Result<Option<HardwareProfileContext>, String>,
) {
    match result {
        Ok(Some(context)) => context.append_notes(notes),
        Ok(None) => {}
        Err(error) => append_hardware_profile_error_notes(notes, config, error),
    }
}

fn append_hardware_profile_unavailable_notes(notes: &mut Vec<String>, config: &Config) {
    match load_hardware_profile(config) {
        Ok(Some(loaded)) => {
            let expectations = build_hardware_profile_expectations(&loaded.profile);
            push_unique_note(
                notes,
                format!("hardware_profile_path={}", loaded.path.display()),
            );
            push_unique_note(notes, "hardware_profile_status=loaded".to_string());
            push_unique_note(notes, format!("hardware_profile_id={}", loaded.profile.id));
            if !loaded.profile.platform_tier.is_empty() {
                push_unique_note(
                    notes,
                    format!(
                        "hardware_profile_platform_tier={}",
                        loaded.profile.platform_tier
                    ),
                );
            }
            if !loaded.profile.bringup_status.is_empty() {
                push_unique_note(
                    notes,
                    format!(
                        "hardware_profile_bringup_status={}",
                        loaded.profile.bringup_status
                    ),
                );
            }
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_canonical_id={}",
                    if loaded.profile.canonical_hardware_profile_id.is_empty() {
                        loaded.profile.id.as_str()
                    } else {
                        loaded.profile.canonical_hardware_profile_id.as_str()
                    }
                ),
            );
            if !loaded.profile.platform_media_id.is_empty() {
                push_unique_note(
                    notes,
                    format!(
                        "hardware_profile_platform_media_id={}",
                        loaded.profile.platform_media_id
                    ),
                );
            }
            if !loaded.profile.runtime_profile.is_empty() {
                push_unique_note(
                    notes,
                    format!(
                        "hardware_profile_runtime_profile={}",
                        loaded.profile.runtime_profile
                    ),
                );
            }
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_hardware_evidence_required={}",
                    loaded.profile.hardware_evidence_required
                ),
            );
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_release_track_intent={}",
                    loaded.profile.release_track_intent.join(",")
                ),
            );
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_expected_modalities={}",
                    expectations.keys().cloned().collect::<Vec<_>>().join(",")
                ),
            );
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_required_modalities={}",
                    expected_modalities(&expectations, ModalityExpectation::Required).join(",")
                ),
            );
            push_unique_note(
                notes,
                format!(
                    "hardware_profile_conditional_modalities={}",
                    expected_modalities(&expectations, ModalityExpectation::Conditional).join(",")
                ),
            );
            push_unique_note(
                notes,
                "hardware_profile_available_expected_modalities=".to_string(),
            );
            push_unique_note(
                notes,
                "hardware_profile_missing_required_modalities=".to_string(),
            );
            push_unique_note(
                notes,
                "hardware_profile_missing_conditional_modalities=".to_string(),
            );
            push_unique_note(
                notes,
                "hardware_profile_validation_status=device-state-unavailable".to_string(),
            );
        }
        Ok(None) => {}
        Err(error) => append_hardware_profile_error_notes(notes, config, &error),
    }
}

fn append_hardware_profile_error_notes(notes: &mut Vec<String>, config: &Config, error: &str) {
    let Some(path) = config.hardware_profile_path.as_ref() else {
        return;
    };
    push_unique_note(notes, format!("hardware_profile_path={}", path.display()));
    push_unique_note(notes, "hardware_profile_status=error".to_string());
    push_unique_note(
        notes,
        format!("hardware_profile_error={}", compact_note_value(error)),
    );
}

fn build_hardware_profile_expectations(
    profile: &HardwareProfile,
) -> BTreeMap<String, ModalityExpectation> {
    let mut expectations = BTreeMap::new();
    if let Some(display_expectation) = classify_profile_requirement(&profile.gpu) {
        expectations.insert("screen".to_string(), display_expectation);
        expectations.insert("input".to_string(), display_expectation);
        expectations.insert(UI_TREE_MODALITY.to_string(), display_expectation);
    }
    if let Some(expectation) = classify_profile_requirement(&profile.audio) {
        expectations.insert("audio".to_string(), expectation);
    }
    if let Some(expectation) = classify_profile_requirement(&profile.camera) {
        expectations.insert("camera".to_string(), expectation);
    }
    expectations
}

fn classify_profile_requirement(value: &str) -> Option<ModalityExpectation> {
    match value.trim().to_ascii_lowercase().as_str() {
        "" | "none" | "absent" | "disabled" | "unsupported" | "headless" | "false" => None,
        "required" | "integrated" | "builtin" | "dedicated" | "discrete" | "present" | "yes"
        | "true" => Some(ModalityExpectation::Required),
        _ => Some(ModalityExpectation::Conditional),
    }
}

fn expected_modalities(
    expectations: &BTreeMap<String, ModalityExpectation>,
    expected_kind: ModalityExpectation,
) -> Vec<String> {
    expectations
        .iter()
        .filter_map(|(modality, expectation)| {
            (*expectation == expected_kind).then_some(modality.clone())
        })
        .collect()
}

fn apply_hardware_profile_context(
    entries: &mut [DeviceMetadataEntry],
    context: &HardwareProfileContext,
) {
    for entry in entries {
        let modality = entry.modality.to_ascii_lowercase();
        let Some(expectation) = context.expectations.get(&modality) else {
            continue;
        };
        push_unique_detail(
            &mut entry.backend_details,
            format!("hardware_profile_id={}", context.loaded.profile.id),
        );
        push_unique_detail(
            &mut entry.backend_details,
            format!("hardware_profile_expectation={}", expectation.as_str()),
        );
        if !context.loaded.profile.platform_tier.is_empty() {
            push_unique_detail(
                &mut entry.backend_details,
                format!(
                    "hardware_profile_platform_tier={}",
                    context.loaded.profile.platform_tier
                ),
            );
        }
        push_unique_note(
            &mut entry.notes,
            format!("hardware_profile_path={}", context.loaded.path.display()),
        );
        push_unique_note(
            &mut entry.notes,
            format!(
                "hardware_profile_validation_status={}",
                context.validation_status
            ),
        );
        if !context.loaded.profile.bringup_status.is_empty() {
            push_unique_note(
                &mut entry.notes,
                format!(
                    "hardware_profile_bringup_status={}",
                    context.loaded.profile.bringup_status
                ),
            );
        }
    }
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

fn push_unique_detail(details: &mut Vec<String>, detail: String) {
    if !details.iter().any(|item| item == &detail) {
        details.push(detail);
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
            hardware_profile_path: None,
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

    fn state_with_ui_tree_backend() -> DeviceStateGetResponse {
        let mut device_state = state();
        device_state.backend_statuses.push(DeviceBackendStatus {
            modality: "ui_tree".to_string(),
            backend: "at-spi".to_string(),
            available: true,
            readiness: "native-live".to_string(),
            details: vec!["probe_source=builtin-probe".to_string()],
        });
        device_state
            .capture_adapters
            .push(DeviceCaptureAdapterPlan {
                modality: "ui_tree".to_string(),
                backend: "at-spi".to_string(),
                adapter_id: "ui_tree.atspi-native".to_string(),
                execution_path: "native-live".to_string(),
                preview_object_kind: "ui_tree_snapshot".to_string(),
                notes: vec![],
            });
        device_state
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

    fn write_hardware_profile(
        root: &std::path::Path,
        file_name: &str,
        content: &str,
    ) -> std::path::PathBuf {
        fs::create_dir_all(root).expect("create hardware profile dir");
        let path = root.join(file_name);
        fs::write(&path, content).expect("write hardware profile");
        path
    }

    #[test]
    fn build_entries_combines_capability_backend_and_adapter_state() {
        let entries = build_entries(&state(), &["screen".to_string(), "camera".to_string()]);

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
    fn build_entries_adds_ui_tree_entry_from_support_matrix() {
        let entries = build_entries(&state_with_ui_tree_backend(), &["ui_tree".to_string()]);

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].modality, "ui_tree");
        assert_eq!(entries[0].source_backend, "at-spi");
        assert!(entries[0].available);
        assert!(entries[0].conditional);
        assert_eq!(entries[0].readiness, "native-live");
        assert_eq!(
            entries[0].adapter_id.as_deref(),
            Some("ui_tree.atspi-native")
        );
        assert!(
            entries[0]
                .backend_details
                .iter()
                .any(|item| item == "ui_tree_current_environment_id=atspi-live"),
            "ui_tree metadata entry should expose current support row"
        );
        assert!(
            entries[0]
                .notes
                .iter()
                .any(|item| item == "ui_tree_snapshot_attached=true"),
            "ui_tree metadata entry should expose snapshot attachment state"
        );
    }

    #[test]
    fn build_view_treats_requested_ui_tree_as_known_modality() {
        let view = build_view(
            &state_with_ui_tree_backend(),
            &DeviceMetadataGetRequest {
                modalities: vec!["ui_tree".to_string()],
                only_available: false,
                include_state_notes: false,
            },
        );

        assert!(view.summary.unknown_modalities.is_empty());
        assert_eq!(
            view.summary.available_modalities,
            vec!["ui_tree".to_string()]
        );
        assert_eq!(view.entries.len(), 1);
        assert_eq!(view.entries[0].modality, "ui_tree");
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
    fn build_device_metadata_response_adds_hardware_profile_notes_and_entry_details() {
        let mut app = app_state();
        let profile_root = app
            .config
            .deviced_socket
            .parent()
            .expect("deviced socket parent");
        let profile_path = write_hardware_profile(
            profile_root,
            "framework-laptop-13-amd-7040.yaml",
            r#"id: framework-laptop-13-amd-7040
platform_tier: tier1
gpu: integrated
audio: required
camera: required
canonical_hardware_profile_id: generic-x86_64-uefi
platform_media_id: generic-x86_64-uefi
runtime_profile: /etc/aios/runtime/default-runtime-profile.yaml
bringup_status: nominated-formal-tier1
hardware_evidence_required: true
release_track_intent:
  - developer-preview
  - product-preview
"#,
        );
        app.config.hardware_profile_path = Some(profile_path.clone());

        let mut device_state = state_with_ui_tree_backend();
        device_state.capabilities.push(DeviceCapabilityDescriptor {
            modality: "input".to_string(),
            available: true,
            conditional: false,
            source_backend: "libinput".to_string(),
            notes: vec!["input-capability".to_string()],
        });
        device_state.backend_statuses.push(DeviceBackendStatus {
            modality: "input".to_string(),
            backend: "libinput".to_string(),
            available: true,
            readiness: "native-live".to_string(),
            details: vec!["devices=keyboard,mouse".to_string()],
        });
        device_state
            .capture_adapters
            .push(DeviceCaptureAdapterPlan {
                modality: "input".to_string(),
                backend: "libinput".to_string(),
                adapter_id: "input.libinput-native".to_string(),
                execution_path: "native-live".to_string(),
                preview_object_kind: "input_event".to_string(),
                notes: vec![],
            });

        let response = build_device_metadata_response(
            &app,
            &DeviceMetadataGetRequest {
                modalities: vec![
                    "screen".to_string(),
                    "input".to_string(),
                    "camera".to_string(),
                    "ui_tree".to_string(),
                ],
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
        let ui_tree_entry = response
            .entries
            .iter()
            .find(|entry| entry.modality == "ui_tree")
            .expect("ui_tree entry");

        assert!(
            screen_entry
                .backend_details
                .iter()
                .any(|item| item == "hardware_profile_id=framework-laptop-13-amd-7040"),
            "screen entry should expose hardware profile id"
        );
        assert!(
            screen_entry
                .backend_details
                .iter()
                .any(|item| item == "hardware_profile_expectation=required"),
            "screen entry should expose hardware profile expectation"
        );
        assert!(
            screen_entry.notes.iter().any(
                |item| item == "hardware_profile_validation_status=missing-required-modalities"
            ),
            "screen entry should expose hardware profile validation status"
        );
        assert!(
            ui_tree_entry
                .backend_details
                .iter()
                .any(|item| item == "hardware_profile_expectation=required"),
            "ui_tree entry should expose required expectation from the hardware profile"
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == &format!("hardware_profile_path={}", profile_path.display())),
            "metadata response should expose hardware profile path"
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "hardware_profile_id=framework-laptop-13-amd-7040"),
            "metadata response should expose hardware profile id"
        );
        assert!(
            response.notes.iter().any(|note| note
                == "hardware_profile_required_modalities=audio,camera,input,screen,ui_tree"),
            "metadata response should expose required hardware profile modalities"
        );
        assert!(
            response
                .notes
                .iter()
                .any(|note| note == "hardware_profile_missing_required_modalities=audio,camera"),
            "metadata response should expose missing required modalities"
        );
        assert!(
            response.notes.iter().any(
                |note| note == "hardware_profile_validation_status=missing-required-modalities"
            ),
            "metadata response should expose hardware profile validation status"
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
