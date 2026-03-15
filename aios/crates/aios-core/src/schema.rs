use std::path::{Path, PathBuf};

use anyhow::Context;
use jsonschema::{Draft, JSONSchema};
use serde::de::DeserializeOwned;
use serde_json::Value;

pub const CURRENT_OBSERVABILITY_SCHEMA_VERSION: &str = "2026-03-13";
const INSTALLED_SCHEMA_ROOT: &str = "/usr/share/aios/schemas";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SchemaNamespace {
    Policy,
    Runtime,
    Sdk,
    Observability,
}

impl SchemaNamespace {
    fn installed_dir_name(self) -> &'static str {
        match self {
            Self::Policy => "policy",
            Self::Runtime => "runtime",
            Self::Sdk => "sdk",
            Self::Observability => "observability",
        }
    }

    fn repo_relative_dir(self) -> &'static str {
        match self {
            Self::Policy => "policy/schemas",
            Self::Runtime => "runtime/schemas",
            Self::Sdk => "sdk/schemas",
            Self::Observability => "observability/schemas",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ObservabilitySchema {
    AuditEvent,
    TraceEvent,
    DiagnosticBundle,
    HealthEvent,
    RecoveryEvidence,
    ValidationReport,
    EvidenceIndex,
    ReleaseGateReport,
    CrossServiceCorrelationReport,
    CrossServiceHealthReport,
}

impl ObservabilitySchema {
    pub fn file_name(self) -> &'static str {
        match self {
            Self::AuditEvent => "audit-event.schema.json",
            Self::TraceEvent => "trace-event.schema.json",
            Self::DiagnosticBundle => "diagnostic-bundle.schema.json",
            Self::HealthEvent => "health-event.schema.json",
            Self::RecoveryEvidence => "recovery-evidence.schema.json",
            Self::ValidationReport => "validation-report.schema.json",
            Self::EvidenceIndex => "evidence-index.schema.json",
            Self::ReleaseGateReport => "release-gate-report.schema.json",
            Self::CrossServiceCorrelationReport => "cross-service-correlation-report.schema.json",
            Self::CrossServiceHealthReport => "cross-service-health-report.schema.json",
        }
    }

    pub fn supported_versions(self) -> &'static [&'static str] {
        match self {
            Self::AuditEvent
            | Self::TraceEvent
            | Self::DiagnosticBundle
            | Self::HealthEvent
            | Self::RecoveryEvidence => &[CURRENT_OBSERVABILITY_SCHEMA_VERSION],
            Self::ValidationReport
            | Self::EvidenceIndex
            | Self::ReleaseGateReport
            | Self::CrossServiceCorrelationReport
            | Self::CrossServiceHealthReport => &[],
        }
    }
}

#[derive(Debug, Clone)]
pub struct CompiledJsonSchema {
    schema_name: String,
    schema_path: PathBuf,
    schema_root: Value,
    supported_versions: &'static [&'static str],
}

impl CompiledJsonSchema {
    pub fn schema_name(&self) -> &str {
        &self.schema_name
    }

    pub fn schema_path(&self) -> &Path {
        &self.schema_path
    }

    pub fn validate_value(&self, value: &Value) -> anyhow::Result<()> {
        self.validate_schema_version(value)?;
        let schema_root = self.schema_root.clone();
        let mut options = JSONSchema::options();
        options.with_draft(Draft::Draft202012);
        let validator = options.compile(&schema_root).map_err(|error| {
            anyhow::anyhow!(
                "failed to compile json schema {}: {}",
                self.schema_path.display(),
                error
            )
        })?;
        if let Err(errors) = validator.validate(value) {
            let details = errors
                .map(|error| format!("{error} @ {}", error.instance_path))
                .take(5)
                .collect::<Vec<_>>()
                .join("; ");
            anyhow::bail!(
                "payload failed validation against {} ({}): {}",
                self.schema_name,
                self.schema_path.display(),
                details
            );
        }
        Ok(())
    }

    fn validate_schema_version(&self, value: &Value) -> anyhow::Result<()> {
        if self.supported_versions.is_empty() {
            return Ok(());
        }

        let object = value
            .as_object()
            .with_context(|| format!("{} payload must be a JSON object", self.schema_name))?;
        let Some(schema_version) = object.get("schema_version") else {
            return Ok(());
        };
        let schema_version = schema_version.as_str().with_context(|| {
            format!(
                "{} payload schema_version must be a string",
                self.schema_name
            )
        })?;
        anyhow::ensure!(
            self.supported_versions.contains(&schema_version),
            "unsupported {} schema_version `{}` (supported: {})",
            self.schema_name,
            schema_version,
            self.supported_versions.join(", ")
        );
        Ok(())
    }
}

pub fn load_yaml_file<T>(path: &Path) -> anyhow::Result<T>
where
    T: DeserializeOwned,
{
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read yaml file {}", path.display()))?;
    serde_yaml::from_str(&text)
        .with_context(|| format!("failed to decode yaml file {}", path.display()))
}

pub fn load_json_file(path: &Path) -> anyhow::Result<Value> {
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read json file {}", path.display()))?;
    serde_json::from_str(&text)
        .with_context(|| format!("failed to decode json file {}", path.display()))
}

pub fn validate_json_schema_document(path: &Path) -> anyhow::Result<Value> {
    let value = load_json_file(path)?;
    let object = value
        .as_object()
        .with_context(|| format!("schema root must be a json object: {}", path.display()))?;

    if let Some(schema) = object.get("$schema") {
        let schema_value = schema.as_str().unwrap_or_default();
        anyhow::ensure!(
            schema_value.starts_with("http://json-schema.org/")
                || schema_value.starts_with("https://json-schema.org/"),
            "schema $schema must point to json-schema metadata: {}",
            path.display()
        );
    }

    anyhow::ensure!(
        object.contains_key("type")
            || object.contains_key("oneOf")
            || object.contains_key("anyOf")
            || object.contains_key("allOf")
            || object.contains_key("$defs")
            || object.contains_key("properties"),
        "schema document must define type/properties/composition keywords: {}",
        path.display()
    );

    if let Some(required) = object.get("required") {
        anyhow::ensure!(
            required.is_array(),
            "schema required must be an array when present: {}",
            path.display()
        );
    }

    Ok(value)
}

pub fn compile_json_schema_document(
    path: &Path,
    supported_versions: &'static [&'static str],
) -> anyhow::Result<CompiledJsonSchema> {
    let value = validate_json_schema_document(path)?;
    let schema_root = normalize_root_schema_id(value.clone(), path)?;
    let mut options = JSONSchema::options();
    options.with_draft(Draft::Draft202012);
    let validator = options.compile(&schema_root).map_err(|error| {
        anyhow::anyhow!(
            "failed to compile json schema {}: {}",
            path.display(),
            error
        )
    })?;
    drop(validator);
    Ok(CompiledJsonSchema {
        schema_name: path
            .file_name()
            .and_then(|item| item.to_str())
            .unwrap_or("schema")
            .to_string(),
        schema_path: path.to_path_buf(),
        schema_root,
        supported_versions,
    })
}

pub fn candidate_schema_dirs(namespace: SchemaNamespace) -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if namespace == SchemaNamespace::Observability {
        if let Some(dir) = std::env::var_os("AIOS_OBSERVABILITY_SCHEMA_DIR") {
            candidates.push(PathBuf::from(dir));
        }
    }

    if let Some(root) = std::env::var_os("AIOS_SCHEMA_ROOT") {
        let root = PathBuf::from(root);
        candidates.push(root.join(namespace.installed_dir_name()));
        candidates.push(root.join(namespace.repo_relative_dir()));
    }

    candidates.push(PathBuf::from(INSTALLED_SCHEMA_ROOT).join(namespace.installed_dir_name()));
    candidates.push(repo_root().join(namespace.repo_relative_dir()));
    dedupe_paths(candidates)
}

pub fn resolve_schema_path(namespace: SchemaNamespace, file_name: &str) -> anyhow::Result<PathBuf> {
    for dir in candidate_schema_dirs(namespace) {
        let candidate = dir.join(file_name);
        if candidate.exists() {
            return Ok(candidate);
        }
    }

    anyhow::bail!(
        "failed to resolve schema {} in namespace {:?}; searched: {}",
        file_name,
        namespace,
        candidate_schema_dirs(namespace)
            .into_iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>()
            .join(", ")
    );
}

pub fn compile_observability_schema(
    schema: ObservabilitySchema,
) -> anyhow::Result<CompiledJsonSchema> {
    let path = resolve_schema_path(SchemaNamespace::Observability, schema.file_name())?;
    compile_json_schema_document(&path, schema.supported_versions())
}

pub fn validate_observability_payload(
    schema: ObservabilitySchema,
    payload: &Value,
) -> anyhow::Result<()> {
    let validator = compile_observability_schema(schema)?;
    validator.validate_value(payload)
}

fn dedupe_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut unique = Vec::new();
    for path in paths {
        if !unique.iter().any(|item: &PathBuf| item == &path) {
            unique.push(path);
        }
    }
    unique
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn normalize_root_schema_id(mut schema_root: Value, path: &Path) -> anyhow::Result<Value> {
    let Some(object) = schema_root.as_object_mut() else {
        return Ok(schema_root);
    };
    let Some(id) = object.get_mut("$id") else {
        return Ok(schema_root);
    };
    let Some(raw_id) = id.as_str() else {
        return Ok(schema_root);
    };
    if raw_id.contains("://") {
        return Ok(schema_root);
    }

    let canonical_path = path
        .canonicalize()
        .with_context(|| format!("failed to canonicalize schema path {}", path.display()))?;
    *id = Value::String(format!("file://{}", canonical_path.display()));
    Ok(schema_root)
}

#[cfg(test)]
mod tests {
    use std::path::{Path, PathBuf};

    use super::*;

    const OBSERVABILITY_SAMPLE_CASES: &[(ObservabilitySchema, &str)] = &[
        (ObservabilitySchema::AuditEvent, "audit-event.sample.json"),
        (ObservabilitySchema::TraceEvent, "trace-event.sample.json"),
        (
            ObservabilitySchema::DiagnosticBundle,
            "diagnostic-bundle.sample.json",
        ),
        (ObservabilitySchema::HealthEvent, "health-event.sample.json"),
        (
            ObservabilitySchema::RecoveryEvidence,
            "recovery-evidence.sample.json",
        ),
        (
            ObservabilitySchema::ValidationReport,
            "validation-report.sample.json",
        ),
        (
            ObservabilitySchema::EvidenceIndex,
            "evidence-index.sample.json",
        ),
        (
            ObservabilitySchema::ReleaseGateReport,
            "release-gate-report.sample.json",
        ),
        (
            ObservabilitySchema::CrossServiceCorrelationReport,
            "cross-service-correlation-report.sample.json",
        ),
        (
            ObservabilitySchema::CrossServiceHealthReport,
            "cross-service-health-report.sample.json",
        ),
    ];

    fn canonical_repo_root() -> PathBuf {
        repo_root().canonicalize().expect("repo root")
    }

    fn validate_schema_dir(root: &Path) -> anyhow::Result<()> {
        for entry in std::fs::read_dir(root)? {
            let path = entry?.path();
            if path.extension().and_then(|item| item.to_str()) != Some("json") {
                continue;
            }
            compile_json_schema_document(&path, &[])?;
        }
        Ok(())
    }

    #[test]
    fn validates_policy_runtime_sdk_and_observability_schemas() -> anyhow::Result<()> {
        let root = canonical_repo_root();
        validate_schema_dir(&root.join("policy/schemas"))?;
        validate_schema_dir(&root.join("runtime/schemas"))?;
        validate_schema_dir(&root.join("sdk/schemas"))?;
        validate_schema_dir(&root.join("observability/schemas"))?;
        Ok(())
    }

    #[test]
    fn observability_samples_match_compiled_schemas() -> anyhow::Result<()> {
        let root = canonical_repo_root();
        let samples_dir = root.join("observability/samples");
        for (schema_kind, sample_name) in OBSERVABILITY_SAMPLE_CASES {
            let validator = compile_observability_schema(*schema_kind)?;
            let sample = load_json_file(&samples_dir.join(sample_name))?;
            validator.validate_value(&sample)?;
        }
        Ok(())
    }

    #[test]
    fn observability_versioned_samples_use_current_version() -> anyhow::Result<()> {
        let root = canonical_repo_root();
        let samples_dir = root.join("observability/samples");

        for (schema_kind, sample_name) in OBSERVABILITY_SAMPLE_CASES {
            if schema_kind.supported_versions().is_empty() {
                continue;
            }

            let sample = load_json_file(&samples_dir.join(sample_name))?;
            let schema_version = sample
                .get("schema_version")
                .and_then(Value::as_str)
                .with_context(|| format!("missing schema_version in {}", sample_name))?;
            anyhow::ensure!(
                schema_version == CURRENT_OBSERVABILITY_SCHEMA_VERSION,
                "unexpected schema_version in {}: {}",
                sample_name,
                schema_version
            );
        }
        Ok(())
    }

    #[test]
    fn observability_validator_rejects_unknown_version() -> anyhow::Result<()> {
        let root = canonical_repo_root();
        let mut sample =
            load_json_file(&root.join("observability/samples/trace-event.sample.json"))?;
        sample["schema_version"] = Value::String("1999-01-01".to_string());
        let validator = compile_observability_schema(ObservabilitySchema::TraceEvent)?;
        let error = validator
            .validate_value(&sample)
            .expect_err("validator should reject unsupported schema_version");
        assert!(error
            .to_string()
            .contains("unsupported trace-event.schema.json schema_version"));
        Ok(())
    }
}
