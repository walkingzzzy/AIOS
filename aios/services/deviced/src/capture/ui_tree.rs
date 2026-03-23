use aios_contracts::DeviceCapabilityDescriptor;

use crate::config::Config;

pub fn capability(config: &Config) -> DeviceCapabilityDescriptor {
    let mut notes = vec!["ui_tree access is desktop- and permission-conditional".to_string()];
    if config.ui_tree_live_command.is_some() {
        notes.push("ui_tree_live_command_configured=true".to_string());
    }
    if config.ui_tree_state_path.exists() {
        notes.push(format!(
            "ui_tree_state={}",
            config.ui_tree_state_path.display()
        ));
    }

    DeviceCapabilityDescriptor {
        modality: "ui_tree".to_string(),
        available: config.ui_tree_supported,
        conditional: true,
        source_backend: "at-spi".to_string(),
        notes,
    }
}
