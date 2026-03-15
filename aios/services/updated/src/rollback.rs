use crate::deployment::DeploymentState;

pub fn rollback_ready(state: &DeploymentState, recovery_points: &[String]) -> bool {
    state.rollback_ready || !recovery_points.is_empty() || state.status == "ready-to-stage"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rollback_is_ready_when_recovery_points_exist() {
        let state = DeploymentState {
            service_id: "aios-updated".to_string(),
            update_stack: "systemd-sysupdate".to_string(),
            current_channel: "stable".to_string(),
            current_version: "0.1.0".to_string(),
            next_version: None,
            status: "idle".to_string(),
            rollback_ready: false,
            last_check_at: None,
            active_recovery_id: None,
            pending_action: None,
            notes: Vec::new(),
        };

        assert!(rollback_ready(&state, &["recovery-001.json".to_string()]));
    }
}
