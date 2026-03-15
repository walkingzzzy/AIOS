use std::{collections::BTreeMap, path::Path};

use serde::Deserialize;

#[derive(Debug, Clone)]
pub struct CapabilityCatalog {
    capabilities: BTreeMap<String, CapabilityMetadata>,
}

#[derive(Debug, Clone, Deserialize)]
struct CapabilityCatalogFile {
    #[serde(default)]
    capabilities: Vec<CapabilityMetadata>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CapabilityMetadata {
    pub capability_id: String,
    #[serde(default = "default_capability_version")]
    pub version: String,
    #[serde(default = "default_risk_tier")]
    pub risk_tier: String,
    #[serde(default)]
    pub approval_required: bool,
    #[serde(default)]
    pub prompt_injection_sensitive: bool,
    #[serde(default)]
    pub destructive: bool,
    #[serde(default)]
    pub user_interaction_required: bool,
    #[serde(default)]
    pub default_approval_lane: String,
    #[serde(default)]
    pub taint_tags: Vec<String>,
    #[serde(default)]
    pub supersedes: Option<String>,
    #[serde(default)]
    pub migration_note: Option<String>,
}

impl CapabilityCatalog {
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        let file: CapabilityCatalogFile = aios_core::schema::load_yaml_file(path)?;
        let mut capabilities = BTreeMap::new();
        for capability in file.capabilities {
            capabilities.insert(capability.capability_id.clone(), capability);
        }
        Ok(Self { capabilities })
    }

    pub fn get(&self, capability_id: &str) -> Option<&CapabilityMetadata> {
        self.capabilities.get(capability_id)
    }

    pub fn len(&self) -> usize {
        self.capabilities.len()
    }
}

impl CapabilityMetadata {
    pub fn high_risk(&self) -> bool {
        matches!(self.risk_tier.as_str(), "high" | "critical")
    }
}

fn default_risk_tier() -> String {
    "medium".to_string()
}

fn default_capability_version() -> String {
    "1.0.0".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_catalog_and_indexes_capabilities() -> anyhow::Result<()> {
        let path = std::env::temp_dir().join(format!(
            "aios-policy-catalog-{}.yaml",
            uuid::Uuid::new_v4().simple()
        ));
        std::fs::write(
            &path,
            r#"capabilities:
  - capability_id: runtime.infer.submit
    version: 2.1.0
    risk_tier: low
    prompt_injection_sensitive: true
    migration_note: keep request contract aligned with runtime-worker-v1
    taint_tags: [prompt]
"#,
        )?;

        let catalog = CapabilityCatalog::load(&path)?;
        let entry = catalog.get("runtime.infer.submit").expect("catalog entry");
        assert_eq!(catalog.len(), 1);
        assert_eq!(entry.version, "2.1.0");
        assert_eq!(entry.risk_tier, "low");
        assert!(entry.prompt_injection_sensitive);
        assert_eq!(
            entry.migration_note.as_deref(),
            Some("keep request contract aligned with runtime-worker-v1")
        );

        let _ = std::fs::remove_file(path);
        Ok(())
    }
}
