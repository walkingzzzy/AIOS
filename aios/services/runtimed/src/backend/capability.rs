use std::path::Path;

use aios_contracts::RuntimeBackendDescriptor;

#[derive(Debug, Clone)]
pub struct BackendReadiness {
    pub availability: String,
    pub activation: String,
    pub reason: String,
}

impl BackendReadiness {
    pub fn available(activation: &str, reason: impl Into<String>) -> Self {
        Self {
            availability: "available".to_string(),
            activation: activation.to_string(),
            reason: reason.into(),
        }
    }

    pub fn unavailable(availability: &str, activation: &str, reason: impl Into<String>) -> Self {
        Self {
            availability: availability.to_string(),
            activation: activation.to_string(),
            reason: reason.into(),
        }
    }

    pub fn is_available(&self) -> bool {
        self.availability == "available" || self.availability == "baseline"
    }

    pub fn descriptor(&self, backend_id: &str) -> RuntimeBackendDescriptor {
        RuntimeBackendDescriptor {
            backend_id: backend_id.to_string(),
            availability: self.availability.clone(),
            activation: self.activation.clone(),
        }
    }
}

pub fn env_truthy(name: &str) -> bool {
    std::env::var(name)
        .map(|value| {
            matches!(
                value.to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(false)
}

pub fn any_device_present(paths: &[&str]) -> bool {
    paths.iter().any(|path| Path::new(path).exists())
}

pub fn configured_command_readiness(
    backend_id: &str,
    command: Option<&str>,
) -> Option<BackendReadiness> {
    let command = command?;
    if let Some(socket_path) = command.strip_prefix("unix://") {
        let socket = Path::new(socket_path);
        return Some(if socket.exists() {
            BackendReadiness::available(
                "configured-unix-worker",
                format!("{backend_id} unix worker ready at {}", socket.display()),
            )
        } else {
            BackendReadiness::unavailable(
                "worker-socket-missing",
                "configured-unix-worker",
                format!(
                    "{backend_id} unix worker socket missing: {}",
                    socket.display()
                ),
            )
        });
    }

    Some(BackendReadiness::available(
        "configured-wrapper",
        format!("{backend_id} wrapper configured"),
    ))
}
