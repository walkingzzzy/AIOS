use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

use anyhow::Context;
use chrono::Utc;
use serde::Deserialize;

use aios_contracts::{
    ProviderCandidate, ProviderCapabilityDescriptor, ProviderDescriptor, ProviderDiscoverRequest,
    ProviderDiscoverResponse, ProviderGetDescriptorResponse, ProviderHealthGetResponse,
    ProviderHealthReportRequest, ProviderHealthState, ProviderRecord,
    ProviderResolveCapabilityRequest, ProviderResolveCapabilityResponse,
};

#[derive(Debug, Clone)]
pub struct RegistryConfig {
    pub state_dir: PathBuf,
    pub descriptor_dirs: Vec<PathBuf>,
}

#[derive(Debug, Clone)]
pub struct ProviderRegistry {
    config: RegistryConfig,
}

impl ProviderRegistry {
    pub fn new(config: RegistryConfig) -> anyhow::Result<Self> {
        let registry = Self { config };
        registry.ensure_dirs()?;
        Ok(registry)
    }

    pub fn register(&self, descriptor: ProviderDescriptor) -> anyhow::Result<ProviderRecord> {
        validate_descriptor(&descriptor)?;

        let now = Utc::now().to_rfc3339();
        let provider_id = descriptor.provider_id.clone();
        let record = ProviderRecord {
            provider_id: provider_id.clone(),
            descriptor,
            state: "active".to_string(),
            registered_at: now.clone(),
            updated_at: now.clone(),
            source: "dynamic".to_string(),
        };

        write_json(
            &self.dynamic_descriptor_path(&provider_id),
            &record.descriptor,
        )?;
        let health_path = self.health_path(&provider_id);
        if !health_path.exists() {
            write_json(&health_path, &default_health_state(&provider_id))?;
        }

        Ok(record)
    }

    pub fn unregister(&self, provider_id: &str) -> anyhow::Result<()> {
        let descriptor_path = self.dynamic_descriptor_path(provider_id);
        if !descriptor_path.exists() {
            anyhow::bail!("dynamic provider descriptor not found: {provider_id}");
        }

        fs::remove_file(&descriptor_path)?;
        let health_path = self.health_path(provider_id);
        if health_path.exists() {
            fs::remove_file(health_path)?;
        }

        Ok(())
    }

    pub fn discover(
        &self,
        request: &ProviderDiscoverRequest,
    ) -> anyhow::Result<ProviderDiscoverResponse> {
        let mut candidates = self
            .load_records()?
            .into_values()
            .filter(|record| matches_discovery_request(record, request))
            .map(|record| build_candidate(&record, request))
            .collect::<Vec<_>>();

        candidates.sort_by(|left, right| {
            right
                .score
                .cmp(&left.score)
                .then(left.provider_id.cmp(&right.provider_id))
        });

        Ok(ProviderDiscoverResponse { candidates })
    }

    pub fn resolve_capability(
        &self,
        request: &ProviderResolveCapabilityRequest,
    ) -> anyhow::Result<ProviderResolveCapabilityResponse> {
        let discovery = self.discover(&ProviderDiscoverRequest {
            kind: request.preferred_kind.clone(),
            capability_id: Some(request.capability_id.clone()),
            execution_location: request.preferred_execution_location.clone(),
            include_disabled: request.include_disabled,
        })?;

        let mut candidates = discovery.candidates;
        if request.require_healthy {
            candidates.retain(|candidate| {
                !candidate.disabled
                    && candidate.health_status != "disabled"
                    && candidate.health_status != "unavailable"
            });
        }

        let selected = candidates.first().cloned();
        let reason = match &selected {
            Some(candidate) => format!(
                "selected provider {} for capability {}",
                candidate.provider_id, request.capability_id
            ),
            None => format!(
                "no provider matched capability {} with current filters",
                request.capability_id
            ),
        };

        Ok(ProviderResolveCapabilityResponse {
            capability_id: request.capability_id.clone(),
            selected,
            candidates,
            reason,
        })
    }

    pub fn get_descriptor(
        &self,
        provider_id: &str,
    ) -> anyhow::Result<ProviderGetDescriptorResponse> {
        let mut records = self.load_records()?;
        let descriptor = records.remove(provider_id).map(|record| record.descriptor);

        Ok(ProviderGetDescriptorResponse { descriptor })
    }

    pub fn health_get(
        &self,
        provider_id: Option<&str>,
    ) -> anyhow::Result<ProviderHealthGetResponse> {
        let mut providers = self
            .load_records()?
            .into_values()
            .map(|record| {
                load_or_default_health(&self.health_path(&record.provider_id), &record.provider_id)
            })
            .collect::<anyhow::Result<Vec<_>>>()?;

        if let Some(provider_id) = provider_id {
            providers.retain(|provider| provider.provider_id == provider_id);
        }

        providers.sort_by(|left, right| left.provider_id.cmp(&right.provider_id));
        Ok(ProviderHealthGetResponse { providers })
    }

    pub fn report_health(
        &self,
        request: &ProviderHealthReportRequest,
    ) -> anyhow::Result<ProviderHealthState> {
        ensure_provider_exists(self, &request.provider_id)?;
        if request.status.trim().is_empty() {
            anyhow::bail!("provider health status cannot be empty");
        }

        let mut health = load_or_default_health(
            &self.health_path(&request.provider_id),
            &request.provider_id,
        )?;
        health.last_checked_at = Some(Utc::now().to_rfc3339());
        health.last_error = request.last_error.clone();
        health.circuit_open = request.circuit_open;
        health.resource_pressure = request.resource_pressure.clone();
        if health.disabled {
            health.status = "disabled".to_string();
        } else {
            health.status = request.status.clone();
        }

        write_json(&self.health_path(&request.provider_id), &health)?;
        Ok(health)
    }

    pub fn disable(
        &self,
        provider_id: &str,
        reason: Option<String>,
    ) -> anyhow::Result<ProviderHealthState> {
        ensure_provider_exists(self, provider_id)?;

        let mut health = load_or_default_health(&self.health_path(provider_id), provider_id)?;
        health.status = "disabled".to_string();
        health.last_checked_at = Some(Utc::now().to_rfc3339());
        health.disabled = true;
        health.disabled_reason = reason;

        write_json(&self.health_path(provider_id), &health)?;
        Ok(health)
    }

    pub fn enable(&self, provider_id: &str) -> anyhow::Result<ProviderHealthState> {
        ensure_provider_exists(self, provider_id)?;

        let mut health = load_or_default_health(&self.health_path(provider_id), provider_id)?;
        health.status = "available".to_string();
        health.last_checked_at = Some(Utc::now().to_rfc3339());
        health.last_error = None;
        health.disabled = false;
        health.disabled_reason = None;
        health.circuit_open = false;
        health.resource_pressure = None;

        write_json(&self.health_path(provider_id), &health)?;
        Ok(health)
    }

    pub fn descriptor_dirs(&self) -> &[PathBuf] {
        &self.config.descriptor_dirs
    }

    fn ensure_dirs(&self) -> anyhow::Result<()> {
        fs::create_dir_all(self.dynamic_descriptor_dir())?;
        fs::create_dir_all(self.health_dir())?;
        Ok(())
    }

    fn load_records(&self) -> anyhow::Result<BTreeMap<String, ProviderRecord>> {
        let mut records = BTreeMap::new();

        for directory in &self.config.descriptor_dirs {
            for path in collect_descriptor_files(directory)? {
                let descriptor = load_descriptor(&path)?;
                let provider_id = descriptor.provider_id.clone();
                let timestamps = file_timestamp(&path);
                let health = load_or_default_health(&self.health_path(&provider_id), &provider_id)?;
                let state = provider_state_from_health(&health);

                records.insert(
                    provider_id.clone(),
                    ProviderRecord {
                        provider_id,
                        descriptor,
                        state,
                        registered_at: timestamps.clone(),
                        updated_at: timestamps,
                        source: format!("builtin:{}", path.display()),
                    },
                );
            }
        }

        for path in collect_descriptor_files(&self.dynamic_descriptor_dir())? {
            let descriptor = load_descriptor(&path)?;
            let provider_id = descriptor.provider_id.clone();
            let timestamps = file_timestamp(&path);
            let health = load_or_default_health(&self.health_path(&provider_id), &provider_id)?;
            let state = provider_state_from_health(&health);

            records.insert(
                provider_id.clone(),
                ProviderRecord {
                    provider_id,
                    descriptor,
                    state,
                    registered_at: timestamps.clone(),
                    updated_at: timestamps,
                    source: "dynamic".to_string(),
                },
            );
        }

        Ok(records)
    }

    fn dynamic_descriptor_dir(&self) -> PathBuf {
        self.config.state_dir.join("descriptors")
    }

    fn dynamic_descriptor_path(&self, provider_id: &str) -> PathBuf {
        self.dynamic_descriptor_dir()
            .join(format!("{provider_id}.json"))
    }

    fn health_dir(&self) -> PathBuf {
        self.config.state_dir.join("health")
    }

    fn health_path(&self, provider_id: &str) -> PathBuf {
        self.health_dir().join(format!("{provider_id}.json"))
    }
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum CapabilityInput {
    Id(String),
    Detailed(ProviderCapabilityDescriptor),
}

#[derive(Debug, Deserialize)]
struct ProviderDescriptorInput {
    provider_id: String,
    version: String,
    kind: String,
    #[serde(default)]
    display_name: Option<String>,
    #[serde(default)]
    owner: Option<String>,
    #[serde(default)]
    worker_contract: Option<String>,
    #[serde(default)]
    result_protocol_schema_ref: Option<String>,
    #[serde(default)]
    trust_policy_modes: Vec<String>,
    capabilities: Vec<CapabilityInput>,
    #[serde(default = "default_execution_location")]
    execution_location: String,
    #[serde(default)]
    sandbox_class: Option<String>,
    #[serde(default)]
    required_permissions: Vec<String>,
    #[serde(default)]
    resource_budget: aios_contracts::ProviderResourceBudget,
    #[serde(default)]
    supported_targets: Vec<String>,
    #[serde(default)]
    input_schema_refs: Vec<String>,
    #[serde(default)]
    output_schema_refs: Vec<String>,
    #[serde(default)]
    timeout_policy: String,
    #[serde(default)]
    retry_policy: String,
    #[serde(default)]
    healthcheck: aios_contracts::ProviderHealthcheck,
    #[serde(default)]
    audit_tags: Vec<String>,
    #[serde(default)]
    taint_behavior: String,
    #[serde(default)]
    degradation_policy: String,
    #[serde(default)]
    compat_permission_manifest: Option<aios_contracts::CompatPermissionManifest>,
    #[serde(default)]
    remote_registration: Option<aios_contracts::RemoteProviderRegistration>,
}

fn default_execution_location() -> String {
    "local".to_string()
}

fn ensure_provider_exists(registry: &ProviderRegistry, provider_id: &str) -> anyhow::Result<()> {
    if registry.get_descriptor(provider_id)?.descriptor.is_none() {
        anyhow::bail!("provider not found: {provider_id}");
    }

    Ok(())
}

fn env_flag(name: &str) -> bool {
    matches!(
        std::env::var(name)
            .ok()
            .map(|value| value.trim().to_ascii_lowercase()),
        Some(value) if matches!(value.as_str(), "1" | "true" | "yes" | "on")
    )
}

fn env_csv(name: &str) -> Option<Vec<String>> {
    let raw = std::env::var(name).ok()?;
    let items = raw
        .split(',')
        .map(|item| item.trim().to_string())
        .filter(|item| !item.is_empty())
        .collect::<Vec<_>>();
    if items.is_empty() {
        None
    } else {
        Some(items)
    }
}

fn remote_registration_status(
    remote: &aios_contracts::RemoteProviderRegistration,
) -> anyhow::Result<String> {
    let current = remote
        .registration_status
        .as_deref()
        .unwrap_or("active")
        .trim()
        .to_lowercase();
    if remote.revoked_at.as_deref().is_some() || current == "revoked" {
        return Ok("revoked".to_string());
    }
    if let Some(last_heartbeat_at) = remote.last_heartbeat_at.as_deref() {
        chrono::DateTime::parse_from_rfc3339(last_heartbeat_at).with_context(|| {
            format!("invalid remote registration last_heartbeat_at: {last_heartbeat_at}")
        })?;
    }
    if let Some(ttl_seconds) = remote.heartbeat_ttl_seconds {
        if ttl_seconds > 0 {
            let heartbeat = remote
                .last_heartbeat_at
                .as_deref()
                .unwrap_or(remote.registered_at.as_str());
            let parsed = chrono::DateTime::parse_from_rfc3339(heartbeat).with_context(|| {
                format!("invalid remote registration heartbeat timestamp: {heartbeat}")
            })?;
            let ttl = ttl_seconds.min(i64::MAX as u64) as i64;
            if parsed.with_timezone(&Utc) + chrono::Duration::seconds(ttl) <= Utc::now() {
                return Ok("stale".to_string());
            }
        }
    }
    Ok(if current.is_empty() {
        "active".to_string()
    } else {
        current
    })
}

fn validate_remote_registration(
    remote: &aios_contracts::RemoteProviderRegistration,
) -> anyhow::Result<()> {
    if remote.source_provider_id.trim().is_empty() {
        anyhow::bail!("remote_registration.source_provider_id cannot be empty");
    }
    if remote.endpoint.trim().is_empty() {
        anyhow::bail!("remote_registration.endpoint cannot be empty");
    }
    if remote.target_hash.trim().is_empty() {
        anyhow::bail!("remote_registration.target_hash cannot be empty");
    }
    if remote.provider_ref.trim().is_empty() {
        anyhow::bail!("remote_registration.provider_ref cannot be empty");
    }

    let attestation = remote
        .attestation
        .as_ref()
        .context("attested_remote providers must declare remote_registration.attestation")?;
    let governance = remote
        .governance
        .as_ref()
        .context("attested_remote providers must declare remote_registration.governance")?;
    let attestation_mode = attestation.mode.trim();
    if attestation_mode.is_empty() {
        anyhow::bail!("remote_registration.attestation.mode cannot be empty");
    }
    if !matches!(attestation_mode, "bootstrap" | "verified") {
        anyhow::bail!("unsupported remote attestation mode: {attestation_mode}");
    }
    if governance.fleet_id.trim().is_empty() {
        anyhow::bail!("remote_registration.governance.fleet_id cannot be empty");
    }
    if governance.governance_group.trim().is_empty() {
        anyhow::bail!("remote_registration.governance.governance_group cannot be empty");
    }
    if attestation_mode == "verified" {
        if attestation
            .issuer
            .as_deref()
            .unwrap_or_default()
            .trim()
            .is_empty()
        {
            anyhow::bail!(
                "remote_registration.attestation.issuer is required for verified attestation"
            );
        }
        if attestation
            .subject
            .as_deref()
            .unwrap_or_default()
            .trim()
            .is_empty()
        {
            anyhow::bail!(
                "remote_registration.attestation.subject is required for verified attestation"
            );
        }
    }
    if let Some(expires_at) = attestation.expires_at.as_deref() {
        let parsed = chrono::DateTime::parse_from_rfc3339(expires_at)
            .with_context(|| format!("invalid remote attestation expires_at: {expires_at}"))?;
        if parsed.with_timezone(&Utc) <= Utc::now() {
            anyhow::bail!("remote attestation expired at {expires_at}");
        }
    }
    let status = remote_registration_status(remote)?;
    if status == "revoked" {
        anyhow::bail!("remote registration is revoked");
    }
    if status == "stale" {
        anyhow::bail!("remote registration heartbeat is stale");
    }

    if env_flag("AIOS_PROVIDER_REMOTE_REQUIRE_VERIFIED_ATTESTATION")
        && attestation_mode != "verified"
    {
        anyhow::bail!("remote provider must use verified attestation");
    }
    if let Some(allowed_fleets) = env_csv("AIOS_PROVIDER_REMOTE_ALLOWED_FLEETS") {
        if !allowed_fleets
            .iter()
            .any(|item| item == &governance.fleet_id)
        {
            anyhow::bail!(
                "remote provider fleet_id {} is not allowed by AIOS_PROVIDER_REMOTE_ALLOWED_FLEETS",
                governance.fleet_id
            );
        }
    }
    if let Some(allowed_groups) = env_csv("AIOS_PROVIDER_REMOTE_ALLOWED_GOVERNANCE_GROUPS") {
        if !allowed_groups
            .iter()
            .any(|item| item == &governance.governance_group)
        {
            anyhow::bail!(
                "remote provider governance_group {} is not allowed by AIOS_PROVIDER_REMOTE_ALLOWED_GOVERNANCE_GROUPS",
                governance.governance_group
            );
        }
    }

    Ok(())
}

fn validate_descriptor(descriptor: &ProviderDescriptor) -> anyhow::Result<()> {
    if descriptor.provider_id.trim().is_empty() {
        anyhow::bail!("provider_id cannot be empty");
    }
    if descriptor.version.trim().is_empty() {
        anyhow::bail!("version cannot be empty");
    }
    if descriptor.kind.trim().is_empty() {
        anyhow::bail!("kind cannot be empty");
    }
    if descriptor.capabilities.is_empty() {
        anyhow::bail!("provider must declare at least one capability");
    }
    if descriptor.execution_location == "attested_remote" {
        let remote = descriptor
            .remote_registration
            .as_ref()
            .context("attested_remote providers must declare remote_registration")?;
        validate_remote_registration(remote)?;
    }

    for capability in &descriptor.capabilities {
        if capability.capability_id.trim().is_empty() {
            anyhow::bail!("capability_id cannot be empty");
        }
    }

    Ok(())
}

fn matches_discovery_request(record: &ProviderRecord, request: &ProviderDiscoverRequest) -> bool {
    if !request.include_disabled && record.state == "disabled" {
        return false;
    }

    if let Some(kind) = &request.kind {
        if &record.descriptor.kind != kind {
            return false;
        }
    }

    if let Some(execution_location) = &request.execution_location {
        if &record.descriptor.execution_location != execution_location {
            return false;
        }
    }

    if let Some(capability_id) = &request.capability_id {
        return record
            .descriptor
            .capabilities
            .iter()
            .any(|capability| &capability.capability_id == capability_id);
    }

    true
}

fn build_candidate(
    record: &ProviderRecord,
    request: &ProviderDiscoverRequest,
) -> ProviderCandidate {
    let disabled = record.state == "disabled";
    let health_status = match record.state.as_str() {
        "active" => "available".to_string(),
        "disabled" => "disabled".to_string(),
        "degraded" => "degraded".to_string(),
        "unavailable" => "unavailable".to_string(),
        other => other.to_string(),
    };

    let mut score = 100;
    if record.descriptor.execution_location == "local" {
        score += 10;
    } else if record.descriptor.execution_location == "attested_remote" {
        score -= 10;
        if let Some(remote) = record.descriptor.remote_registration.as_ref() {
            if let Some(attestation) = remote.attestation.as_ref() {
                match attestation.mode.as_str() {
                    "verified" => score += 18,
                    "bootstrap" => score += 4,
                    _ => {}
                }
                if attestation.expires_at.is_some() {
                    score += 3;
                }
            }
            match remote_registration_status(remote).ok().as_deref() {
                Some("active") => score += 4,
                Some("stale") => score -= 120,
                Some("revoked") => score -= 500,
                _ => {}
            }
            if let Some(governance) = remote.governance.as_ref() {
                if governance.policy_group.is_some() {
                    score += 4;
                }
                if governance.approval_ref.is_some() {
                    score += 4;
                }
                if governance.allow_lateral_movement {
                    score -= 8;
                } else {
                    score += 2;
                }
            }
        }
    }
    if health_status == "available" {
        score += 20;
    }
    if health_status == "degraded" {
        score += 5;
    }
    if health_status == "unavailable" {
        score -= 200;
    }
    if disabled {
        score -= 1000;
    }
    if let Some(kind) = &request.kind {
        if &record.descriptor.kind == kind {
            score += 25;
        }
    }
    if let Some(execution_location) = &request.execution_location {
        if &record.descriptor.execution_location == execution_location {
            score += 25;
        }
    }

    ProviderCandidate {
        provider_id: record.provider_id.clone(),
        display_name: record.descriptor.display_name.clone(),
        kind: record.descriptor.kind.clone(),
        execution_location: record.descriptor.execution_location.clone(),
        capabilities: record
            .descriptor
            .capabilities
            .iter()
            .map(|capability| capability.capability_id.clone())
            .collect(),
        health_status,
        disabled,
        score,
        remote_registration: record.descriptor.remote_registration.clone(),
    }
}

fn default_health_state(provider_id: &str) -> ProviderHealthState {
    ProviderHealthState {
        provider_id: provider_id.to_string(),
        status: "available".to_string(),
        last_checked_at: Some(Utc::now().to_rfc3339()),
        last_error: None,
        circuit_open: false,
        resource_pressure: None,
        disabled: false,
        disabled_reason: None,
    }
}

fn load_or_default_health(path: &Path, provider_id: &str) -> anyhow::Result<ProviderHealthState> {
    if path.exists() {
        let mut last_error = None;
        for attempt in 0..5 {
            match fs::read_to_string(path) {
                Ok(content) => match serde_json::from_str::<ProviderHealthState>(&content) {
                    Ok(state) => return Ok(state),
                    Err(error) => last_error = Some(anyhow::Error::new(error)),
                },
                Err(error) => last_error = Some(anyhow::Error::new(error)),
            }

            if attempt < 4 {
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
        }

        if !path.exists() {
            return Ok(default_health_state(provider_id));
        }

        return Err(last_error.expect("health read error should be captured"))
            .with_context(|| format!("invalid provider health file {}", path.display()));
    }

    Ok(default_health_state(provider_id))
}

fn provider_state_from_health(health: &ProviderHealthState) -> String {
    if health.disabled {
        return "disabled".to_string();
    }

    match health.status.as_str() {
        "degraded" => "degraded".to_string(),
        "unavailable" => "unavailable".to_string(),
        _ => "active".to_string(),
    }
}

fn load_descriptor(path: &Path) -> anyhow::Result<ProviderDescriptor> {
    let content = fs::read_to_string(path)
        .with_context(|| format!("failed to read provider descriptor {}", path.display()))?;

    let input = match path.extension().and_then(|value| value.to_str()) {
        Some("yaml") | Some("yml") => serde_yaml::from_str::<ProviderDescriptorInput>(&content)
            .with_context(|| format!("invalid yaml descriptor {}", path.display()))?,
        _ => serde_json::from_str::<ProviderDescriptorInput>(&content)
            .with_context(|| format!("invalid json descriptor {}", path.display()))?,
    };

    let provider_id = input.provider_id;
    let descriptor = ProviderDescriptor {
        provider_id: provider_id.clone(),
        version: input.version,
        kind: input.kind,
        display_name: input.display_name.unwrap_or_else(|| provider_id.clone()),
        owner: input.owner.unwrap_or_else(|| "aios".to_string()),
        worker_contract: input.worker_contract,
        result_protocol_schema_ref: input.result_protocol_schema_ref,
        trust_policy_modes: input.trust_policy_modes,
        capabilities: input
            .capabilities
            .into_iter()
            .map(|capability| match capability {
                CapabilityInput::Id(capability_id) => ProviderCapabilityDescriptor {
                    capability_id,
                    read_only: false,
                    recoverable: false,
                    approval_required: false,
                    external_side_effect: false,
                    dynamic_code: false,
                    user_interaction_required: false,
                    supported_targets: Vec::new(),
                    input_schema_refs: Vec::new(),
                    output_schema_refs: Vec::new(),
                    audit_tags: Vec::new(),
                },
                CapabilityInput::Detailed(capability) => capability,
            })
            .collect(),
        execution_location: input.execution_location,
        sandbox_class: input.sandbox_class,
        required_permissions: input.required_permissions,
        resource_budget: input.resource_budget,
        supported_targets: input.supported_targets,
        input_schema_refs: input.input_schema_refs,
        output_schema_refs: input.output_schema_refs,
        timeout_policy: input.timeout_policy,
        retry_policy: input.retry_policy,
        healthcheck: input.healthcheck,
        audit_tags: input.audit_tags,
        taint_behavior: input.taint_behavior,
        degradation_policy: input.degradation_policy,
        compat_permission_manifest: input.compat_permission_manifest,
        remote_registration: input.remote_registration,
    };

    validate_descriptor(&descriptor)?;
    Ok(descriptor)
}

fn collect_descriptor_files(root: &Path) -> anyhow::Result<Vec<PathBuf>> {
    if !root.exists() {
        return Ok(Vec::new());
    }

    let mut directories = vec![root.to_path_buf()];
    let mut files = Vec::new();

    while let Some(directory) = directories.pop() {
        for entry in fs::read_dir(&directory)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                directories.push(path);
                continue;
            }

            if is_descriptor_file(&path) {
                files.push(path);
            }
        }
    }

    files.sort();
    Ok(files)
}

fn is_descriptor_file(path: &Path) -> bool {
    matches!(
        path.extension().and_then(|value| value.to_str()),
        Some("json") | Some("yaml") | Some("yml")
    )
}

fn file_timestamp(path: &Path) -> String {
    fs::metadata(path)
        .ok()
        .and_then(|metadata| metadata.modified().ok())
        .map(chrono::DateTime::<Utc>::from)
        .unwrap_or_else(Utc::now)
        .to_rfc3339()
}

fn write_json<T>(path: &Path, value: &T) -> anyhow::Result<()>
where
    T: serde::Serialize,
{
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    fs::write(path, serde_json::to_vec_pretty(value)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::{fs, path::PathBuf};

    use super::*;
    use aios_contracts::{
        ProviderCapabilityDescriptor, ProviderDescriptor, RemoteProviderAttestation,
        RemoteProviderGovernance, RemoteProviderRegistration,
    };

    fn temp_root() -> PathBuf {
        let nanos = Utc::now().timestamp_nanos_opt().unwrap_or_default();
        let root = std::env::temp_dir().join(format!(
            "aios-provider-registry-test-{}-{}",
            std::process::id(),
            nanos
        ));
        fs::create_dir_all(&root).expect("create temp root");
        root
    }

    fn write_descriptor(root: &Path, provider_id: &str) {
        let providers_dir = root.join("providers");
        fs::create_dir_all(&providers_dir).expect("create provider dir");
        fs::write(
            providers_dir.join(format!("{}.json", provider_id)),
            format!(
                r#"{{
  "provider_id": "{}",
  "version": "0.1.0",
  "kind": "system-provider",
  "display_name": "{}",
  "owner": "aios",
  "capabilities": [{{ "capability_id": "provider.fs.open" }}],
  "execution_location": "local"
}}"#,
                provider_id, provider_id
            ),
        )
        .expect("write descriptor");
    }

    fn remote_descriptor(
        provider_id: &str,
        attestation_mode: &str,
        expires_at: Option<&str>,
    ) -> ProviderDescriptor {
        let now = Utc::now().to_rfc3339();
        ProviderDescriptor {
            provider_id: provider_id.to_string(),
            version: "0.1.0".to_string(),
            kind: "compat-provider".to_string(),
            display_name: provider_id.to_string(),
            owner: "aios-tests".to_string(),
            worker_contract: None,
            result_protocol_schema_ref: None,
            trust_policy_modes: vec!["registered-remote".to_string()],
            capabilities: vec![ProviderCapabilityDescriptor {
                capability_id: "compat.browser.navigate".to_string(),
                read_only: true,
                recoverable: true,
                approval_required: false,
                external_side_effect: false,
                dynamic_code: false,
                user_interaction_required: false,
                supported_targets: vec!["registered-remote".to_string()],
                input_schema_refs: Vec::new(),
                output_schema_refs: Vec::new(),
                audit_tags: vec!["remote".to_string()],
            }],
            execution_location: "attested_remote".to_string(),
            sandbox_class: None,
            required_permissions: Vec::new(),
            resource_budget: aios_contracts::ProviderResourceBudget::default(),
            supported_targets: vec!["registered-remote".to_string()],
            input_schema_refs: Vec::new(),
            output_schema_refs: Vec::new(),
            timeout_policy: "bounded-5s".to_string(),
            retry_policy: "no-retry".to_string(),
            healthcheck: aios_contracts::ProviderHealthcheck::default(),
            audit_tags: vec!["remote".to_string()],
            taint_behavior: "input-propagates".to_string(),
            degradation_policy: "fallback-to-local".to_string(),
            compat_permission_manifest: None,
            remote_registration: Some(RemoteProviderRegistration {
                source_provider_id: "compat.browser.automation.local".to_string(),
                provider_ref: "browser.remote.worker".to_string(),
                endpoint: "https://browser.remote.example/bridge".to_string(),
                auth_mode: "bearer".to_string(),
                auth_header_name: None,
                auth_secret_env: Some("BROWSER_REMOTE_SECRET".to_string()),
                target_hash: "sha256:test-remote".to_string(),
                capabilities: vec!["compat.browser.navigate".to_string()],
                registered_at: now.clone(),
                display_name: Some("Remote Browser Worker".to_string()),
                control_plane_provider_id: Some(provider_id.to_string()),
                registration_status: Some("active".to_string()),
                last_heartbeat_at: Some(now.clone()),
                heartbeat_ttl_seconds: Some(3600),
                revoked_at: None,
                revocation_reason: None,
                attestation: Some(RemoteProviderAttestation {
                    mode: attestation_mode.to_string(),
                    issuer: Some("aios-attestor".to_string()),
                    subject: Some("browser.remote.worker".to_string()),
                    issued_at: Some(now),
                    expires_at: expires_at.map(str::to_string),
                    evidence_ref: Some("evidence://remote/browser".to_string()),
                    digest: Some("sha256:attestation".to_string()),
                    status: Some("trusted".to_string()),
                }),
                governance: Some(RemoteProviderGovernance {
                    fleet_id: "fleet-alpha".to_string(),
                    governance_group: "operator-audit".to_string(),
                    policy_group: Some("remote-browser".to_string()),
                    registered_by: Some("shell-provider-smoke".to_string()),
                    approval_ref: Some("approval-remote-1".to_string()),
                    allow_lateral_movement: false,
                }),
            }),
        }
    }

    #[test]
    fn report_health_marks_builtin_provider_unavailable() -> anyhow::Result<()> {
        let root = temp_root();
        write_descriptor(&root, "system.files.local");

        let registry = ProviderRegistry::new(RegistryConfig {
            state_dir: root.join("state"),
            descriptor_dirs: vec![root.join("providers")],
        })?;

        let health = registry.report_health(&ProviderHealthReportRequest {
            provider_id: "system.files.local".to_string(),
            status: "unavailable".to_string(),
            last_error: Some("provider stopped".to_string()),
            circuit_open: false,
            resource_pressure: None,
        })?;
        assert_eq!(health.status, "unavailable");

        let resolution = registry.resolve_capability(&ProviderResolveCapabilityRequest {
            capability_id: "provider.fs.open".to_string(),
            preferred_kind: None,
            preferred_execution_location: Some("local".to_string()),
            require_healthy: true,
            include_disabled: false,
        })?;
        assert!(resolution.selected.is_none());

        fs::remove_dir_all(&root)?;
        Ok(())
    }

    #[test]
    fn report_health_preserves_disabled_provider_state() -> anyhow::Result<()> {
        let root = temp_root();
        write_descriptor(&root, "system.files.local");

        let registry = ProviderRegistry::new(RegistryConfig {
            state_dir: root.join("state"),
            descriptor_dirs: vec![root.join("providers")],
        })?;

        registry.disable("system.files.local", Some("operator-disabled".to_string()))?;
        let health = registry.report_health(&ProviderHealthReportRequest {
            provider_id: "system.files.local".to_string(),
            status: "available".to_string(),
            last_error: None,
            circuit_open: false,
            resource_pressure: None,
        })?;
        assert!(health.disabled);
        assert_eq!(health.status, "disabled");

        fs::remove_dir_all(&root)?;
        Ok(())
    }

    #[test]
    fn register_preserves_existing_disabled_health_state() -> anyhow::Result<()> {
        let root = temp_root();
        write_descriptor(&root, "system.files.local");

        let registry = ProviderRegistry::new(RegistryConfig {
            state_dir: root.join("state"),
            descriptor_dirs: vec![root.join("providers")],
        })?;

        registry.disable("system.files.local", Some("operator-disabled".to_string()))?;
        let descriptor = load_descriptor(&root.join("providers").join("system.files.local.json"))?;
        registry.register(descriptor)?;

        let health = registry.health_get(Some("system.files.local"))?;
        let provider = health.providers.first().expect("provider health");
        assert!(provider.disabled);
        assert_eq!(provider.status, "disabled");

        fs::remove_dir_all(&root)?;
        Ok(())
    }

    #[test]
    fn load_or_default_health_retries_transient_invalid_json() -> anyhow::Result<()> {
        let root = temp_root();
        let path = root
            .join("state")
            .join("registry")
            .join("health")
            .join("system.files.local.json");
        fs::create_dir_all(path.parent().expect("health dir"))?;
        fs::write(&path, "{")?;

        let writer_path = path.clone();
        let writer = std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_millis(15));
            fs::write(
                &writer_path,
                serde_json::to_vec_pretty(&default_health_state("system.files.local"))
                    .expect("serialize health"),
            )
            .expect("rewrite health");
        });

        let health = load_or_default_health(&path, "system.files.local")?;
        writer.join().expect("writer thread");

        assert_eq!(health.provider_id, "system.files.local");
        assert_eq!(health.status, "available");

        fs::remove_dir_all(&root)?;
        Ok(())
    }

    #[test]
    fn register_rejects_expired_attested_remote_descriptor() {
        let root = temp_root();
        let registry = ProviderRegistry::new(RegistryConfig {
            state_dir: root.join("state"),
            descriptor_dirs: vec![root.join("providers")],
        })
        .expect("registry");

        let error = registry
            .register(remote_descriptor(
                "compat.browser.remote.expired",
                "verified",
                Some("2020-01-01T00:00:00Z"),
            ))
            .expect_err("expired attestation should be rejected");
        assert!(error.to_string().contains("remote attestation expired"));

        fs::remove_dir_all(&root).expect("cleanup");
    }

    #[test]
    fn register_rejects_stale_attested_remote_descriptor() {
        let root = temp_root();
        let registry = ProviderRegistry::new(RegistryConfig {
            state_dir: root.join("state"),
            descriptor_dirs: vec![root.join("providers")],
        })
        .expect("registry");

        let mut descriptor = remote_descriptor(
            "compat.browser.remote.stale",
            "verified",
            Some("2030-01-01T00:00:00Z"),
        );
        if let Some(remote) = descriptor.remote_registration.as_mut() {
            remote.last_heartbeat_at = Some("2020-01-01T00:00:00Z".to_string());
            remote.heartbeat_ttl_seconds = Some(60);
        }
        let error = registry
            .register(descriptor)
            .expect_err("stale remote registration should be rejected");
        assert!(error.to_string().contains("heartbeat is stale"));

        fs::remove_dir_all(&root).expect("cleanup");
    }

    #[test]
    fn verified_attested_remote_scores_above_bootstrap_remote() -> anyhow::Result<()> {
        let root = temp_root();
        let registry = ProviderRegistry::new(RegistryConfig {
            state_dir: root.join("state"),
            descriptor_dirs: vec![root.join("providers")],
        })?;

        registry.register(remote_descriptor(
            "compat.browser.remote.bootstrap",
            "bootstrap",
            None,
        ))?;
        registry.register(remote_descriptor(
            "compat.browser.remote.verified",
            "verified",
            Some("2030-01-01T00:00:00Z"),
        ))?;

        let discovery = registry.discover(&ProviderDiscoverRequest {
            kind: None,
            capability_id: Some("compat.browser.navigate".to_string()),
            execution_location: Some("attested_remote".to_string()),
            include_disabled: false,
        })?;
        assert_eq!(discovery.candidates.len(), 2);
        assert_eq!(
            discovery.candidates[0].provider_id,
            "compat.browser.remote.verified"
        );
        assert!(
            discovery.candidates[0].score > discovery.candidates[1].score,
            "verified remote should score above bootstrap remote"
        );

        fs::remove_dir_all(&root)?;
        Ok(())
    }
}
