use aios_contracts::ProviderResolveCapabilityRequest;

use crate::AppState;

pub fn resolve_primary_provider(
    state: &AppState,
    capability_id: &str,
) -> anyhow::Result<aios_contracts::ProviderResolveCapabilityResponse> {
    state
        .provider_registry
        .resolve_capability(&ProviderResolveCapabilityRequest {
            capability_id: capability_id.to_string(),
            preferred_kind: preferred_kind_for_capability(capability_id),
            preferred_execution_location: preferred_execution_location(capability_id),
            require_healthy: true,
            include_disabled: false,
        })
}

pub fn preferred_kind_for_capability(capability_id: &str) -> Option<String> {
    if capability_id.starts_with("runtime.") {
        return Some("runtime-provider".to_string());
    }
    if capability_id.starts_with("device.") {
        return Some("device-provider".to_string());
    }
    if capability_id.starts_with("shell.") {
        return Some("shell-provider".to_string());
    }
    if capability_id.starts_with("compat.")
        || capability_id.starts_with("browser.")
        || capability_id.starts_with("office.")
    {
        return Some("compat-provider".to_string());
    }
    if capability_id.starts_with("system.") || capability_id.starts_with("provider.") {
        return Some("system-provider".to_string());
    }

    None
}

pub fn preferred_execution_location(capability_id: &str) -> Option<String> {
    if capability_id.starts_with("device.")
        || capability_id.starts_with("compat.")
        || capability_id.starts_with("browser.")
        || capability_id.starts_with("office.")
    {
        return Some("sandbox".to_string());
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selects_preferred_kinds_by_capability_family() {
        assert_eq!(
            preferred_kind_for_capability("runtime.infer.submit"),
            Some("runtime-provider".to_string())
        );
        assert_eq!(
            preferred_kind_for_capability("device.capture.screen.read"),
            Some("device-provider".to_string())
        );
        assert_eq!(
            preferred_kind_for_capability("shell.notification.open"),
            Some("shell-provider".to_string())
        );
        assert_eq!(
            preferred_kind_for_capability("compat.office.export_pdf"),
            Some("compat-provider".to_string())
        );
        assert_eq!(
            preferred_kind_for_capability("browser.page.open"),
            Some("compat-provider".to_string())
        );
        assert_eq!(
            preferred_kind_for_capability("system.intent.execute"),
            Some("system-provider".to_string())
        );
        assert_eq!(preferred_kind_for_capability("unknown.capability"), None);
    }

    #[test]
    fn compat_and_device_capabilities_prefer_sandbox_execution() {
        assert_eq!(
            preferred_execution_location("device.capture.screen.read"),
            Some("sandbox".to_string())
        );
        assert_eq!(
            preferred_execution_location("compat.browser.navigate"),
            Some("sandbox".to_string())
        );
        assert_eq!(
            preferred_execution_location("compat.code.execute"),
            Some("sandbox".to_string())
        );
        assert_eq!(preferred_execution_location("runtime.infer.submit"), None);
    }
}
