use crate::config::Config;
use serde::Serialize;

const DEFAULT_CANVAS_WIDTH: i32 = 1280;
const DEFAULT_CANVAS_HEIGHT: i32 = 800;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Surface {
    pub surface_id: String,
    pub role: String,
    pub shell_role: String,
    pub interaction_mode: String,
    pub blocked_by: Option<String>,
    pub window_policy: String,
    pub host_interface: String,
    pub state: String,
    pub layout_zone: String,
    pub layout_anchor: String,
    pub layout_x: i32,
    pub layout_y: i32,
    pub layout_width: i32,
    pub layout_height: i32,
    pub stacking_layer: String,
    pub z_index: i32,
    pub reservation_status: String,
    pub pointer_policy: String,
    pub focus_policy: String,
    pub panel_host_status: String,
    pub panel_component: Option<String>,
    pub panel_id: Option<String>,
    pub panel_status: Option<String>,
    pub panel_tone: Option<String>,
    pub panel_primary_action_id: Option<String>,
    pub panel_action_count: u32,
    pub panel_section_count: u32,
    pub panel_error: Option<String>,
    pub embedding_status: String,
    pub embedded_surface_id: Option<String>,
    pub client_app_id: Option<String>,
    pub client_title: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SurfacePlacement {
    pub zone: &'static str,
    pub anchor: &'static str,
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

pub fn panel_slot_surfaces(config: &Config) -> Vec<Surface> {
    config
        .panel_slots
        .iter()
        .map(|surface_id| {
            let placement =
                surface_placement(surface_id, DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT);
            Surface {
                surface_id: surface_id.clone(),
                role: surface_role(surface_id).to_string(),
                shell_role: surface_shell_role(surface_id).to_string(),
                interaction_mode: surface_default_interaction_mode(surface_id).to_string(),
                blocked_by: None,
                window_policy: surface_window_policy(surface_id, &config.workspace_toplevel_mode),
                host_interface: format!("{}-panel-slot", config.desktop_host),
                state: "slot-ready".to_string(),
                layout_zone: placement.zone.to_string(),
                layout_anchor: placement.anchor.to_string(),
                layout_x: placement.x,
                layout_y: placement.y,
                layout_width: placement.width,
                layout_height: placement.height,
                stacking_layer: placement_stacking_layer(placement.zone).to_string(),
                z_index: placement_z_index(placement.zone),
                reservation_status: "panel-slot-open".to_string(),
                pointer_policy: surface_pointer_policy(surface_id).to_string(),
                focus_policy: surface_focus_policy(surface_id).to_string(),
                panel_host_status: "unbound".to_string(),
                panel_component: None,
                panel_id: None,
                panel_status: None,
                panel_tone: None,
                panel_primary_action_id: None,
                panel_action_count: 0,
                panel_section_count: 0,
                panel_error: None,
                embedding_status: "panel-slot-open".to_string(),
                embedded_surface_id: None,
                client_app_id: None,
                client_title: None,
            }
        })
        .collect()
}

pub fn placement_stacking_layer(zone: &str) -> &'static str {
    match zone {
        "main-stage" => "workspace",
        "left-dock" | "right-rail" | "bottom-right" => "panel",
        "top-strip" | "top-overlay" => "overlay",
        "floating-stack" => "floating",
        "center-modal" | "recovery-modal" => "modal",
        _ => "workspace",
    }
}

pub fn placement_z_index(zone: &str) -> i32 {
    match zone {
        "main-stage" => 100,
        "left-dock" => 120,
        "right-rail" => 130,
        "bottom-right" => 140,
        "top-strip" => 160,
        "top-overlay" => 180,
        "floating-stack" => 220,
        "center-modal" => 260,
        "recovery-modal" => 280,
        _ => 100,
    }
}

pub fn placement_contains_point(placement: &SurfacePlacement, x: f64, y: f64) -> bool {
    let left = placement.x as f64;
    let top = placement.y as f64;
    let right = (placement.x + placement.width) as f64;
    let bottom = (placement.y + placement.height) as f64;
    x >= left && x < right && y >= top && y < bottom
}

pub fn surface_contains_point(surface: &Surface, x: f64, y: f64) -> bool {
    let left = surface.layout_x as f64;
    let top = surface.layout_y as f64;
    let right = (surface.layout_x + surface.layout_width) as f64;
    let bottom = (surface.layout_y + surface.layout_height) as f64;
    x >= left && x < right && y >= top && y < bottom
}

pub fn surface_pointer_policy(surface_id: &str) -> &'static str {
    match normalize_surface_token(surface_id).as_str() {
        "captureindicators" => "passthrough",
        _ => "interactive",
    }
}

pub fn surface_focus_policy(surface_id: &str) -> &'static str {
    match normalize_surface_token(surface_id).as_str() {
        "approvalpanel" | "portalchooser" | "recoverysurface" => "shell-modal",
        "tasksurface" => "workspace-target",
        "captureindicators" => "passive-overlay",
        _ => "retain-client-focus",
    }
}

pub fn surface_role(surface_id: &str) -> &'static str {
    match normalize_surface_token(surface_id).as_str() {
        "launcher" => "launcher-slot",
        "tasksurface" => "workspace-slot",
        "approvalpanel" => "approval-slot",
        "notificationcenter" => "notification-slot",
        "portalchooser" => "chooser-slot",
        "recoverysurface" => "recovery-slot",
        "captureindicators" => "indicator-slot",
        "remotegovernance" => "governance-slot",
        "devicebackendstatus" => "device-health-slot",
        _ => "panel-host",
    }
}

pub fn surface_shell_role(surface_id: &str) -> &'static str {
    match normalize_surface_token(surface_id).as_str() {
        "launcher" => "dock",
        "tasksurface" => "workspace",
        "approvalpanel" | "portalchooser" | "recoverysurface" => "modal",
        "notificationcenter" | "captureindicators" => "overlay",
        "remotegovernance" | "devicebackendstatus" => "utility",
        _ => "floating",
    }
}

pub fn surface_default_interaction_mode(surface_id: &str) -> &'static str {
    match normalize_surface_token(surface_id).as_str() {
        "tasksurface" => "workspace",
        "approvalpanel" | "portalchooser" | "recoverysurface" => "modal",
        "captureindicators" => "passive",
        _ => "interactive",
    }
}

pub fn surface_window_policy(surface_id: &str, workspace_toplevel_mode: &str) -> String {
    let workspace_mode = normalize_workspace_toplevel_mode(workspace_toplevel_mode);
    match normalize_surface_token(surface_id).as_str() {
        "launcher" => "dock-exclusive".to_string(),
        "tasksurface" => format!("workspace-{workspace_mode}"),
        "approvalpanel" | "portalchooser" => "modal-dialog".to_string(),
        "recoverysurface" => "recovery-workflow".to_string(),
        "notificationcenter" => "overlay-floating".to_string(),
        "captureindicators" => "overlay-passive".to_string(),
        "remotegovernance" => "utility-rail".to_string(),
        "devicebackendstatus" => "utility-tray".to_string(),
        _ => "floating-utility".to_string(),
    }
}

pub fn normalize_workspace_toplevel_mode(value: &str) -> &'static str {
    match value.trim().to_ascii_lowercase().as_str() {
        "fullscreen" | "full-screen" | "full" => "fullscreen",
        _ => "maximized",
    }
}

pub fn surface_placement(
    surface_id: &str,
    canvas_width: i32,
    canvas_height: i32,
) -> SurfacePlacement {
    let width = canvas_width.max(640);
    let height = canvas_height.max(480);
    match normalize_surface_token(surface_id).as_str() {
        "launcher" => {
            let dock_width = (width / 5).clamp(240, 320);
            SurfacePlacement {
                zone: "left-dock",
                anchor: "top-left",
                x: 0,
                y: 0,
                width: dock_width,
                height,
            }
        }
        "tasksurface" => {
            let left_dock = (width / 5).clamp(240, 320);
            let right_rail = (width / 4).clamp(280, 360);
            let x = left_dock + 16;
            let y = 72;
            let slot_width = (width - left_dock - right_rail - 48).max(320);
            let slot_height = (height - 104).max(240);
            SurfacePlacement {
                zone: "main-stage",
                anchor: "center",
                x,
                y,
                width: slot_width,
                height: slot_height,
            }
        }
        "approvalpanel" => {
            let rail_width = (width / 4).clamp(280, 360);
            SurfacePlacement {
                zone: "right-rail",
                anchor: "top-right",
                x: width - rail_width,
                y: 0,
                width: rail_width,
                height,
            }
        }
        "notificationcenter" => {
            let slot_width = (width / 4).clamp(320, 400);
            let slot_height = (height / 2).clamp(240, 420);
            SurfacePlacement {
                zone: "top-overlay",
                anchor: "top-right",
                x: width - slot_width - 16,
                y: 16,
                width: slot_width,
                height: slot_height,
            }
        }
        "portalchooser" => {
            let slot_width = (width / 2).clamp(420, 620);
            let slot_height = (height / 2).clamp(280, 460);
            SurfacePlacement {
                zone: "center-modal",
                anchor: "center",
                x: (width - slot_width) / 2,
                y: (height - slot_height) / 2,
                width: slot_width,
                height: slot_height,
            }
        }
        "recoverysurface" => {
            let slot_width = (width * 3 / 4).clamp(560, 960);
            let slot_height = (height * 3 / 4).clamp(360, 680);
            SurfacePlacement {
                zone: "recovery-modal",
                anchor: "center",
                x: (width - slot_width) / 2,
                y: (height - slot_height) / 2,
                width: slot_width,
                height: slot_height,
            }
        }
        "captureindicators" => SurfacePlacement {
            zone: "top-strip",
            anchor: "top-center",
            x: (width - 320) / 2,
            y: 12,
            width: 320,
            height: 72,
        },
        "remotegovernance" => {
            let slot_width = (width / 4).clamp(280, 360);
            let slot_height = (height / 5).clamp(160, 220);
            SurfacePlacement {
                zone: "bottom-right",
                anchor: "bottom-right",
                x: width - slot_width - 16,
                y: (height - slot_height - 216).max(96),
                width: slot_width,
                height: slot_height,
            }
        }
        "devicebackendstatus" => {
            let slot_width = (width / 4).clamp(280, 360);
            SurfacePlacement {
                zone: "bottom-right",
                anchor: "bottom-right",
                x: width - slot_width - 16,
                y: height - 200,
                width: slot_width,
                height: 184,
            }
        }
        _ => SurfacePlacement {
            zone: "floating-stack",
            anchor: "top-left",
            x: 24,
            y: 24,
            width: (width / 3).clamp(240, 420),
            height: (height / 3).clamp(180, 320),
        },
    }
}

pub fn match_panel_slot(
    available_slots: &[String],
    used_slots: &[String],
    app_id: Option<&str>,
    title: Option<&str>,
) -> Option<String> {
    let mut candidates = Vec::new();
    if let Some(app_id) = app_id {
        candidates.push(normalize_surface_token(app_id));
    }
    if let Some(title) = title {
        candidates.push(normalize_surface_token(title));
    }

    for slot_id in available_slots {
        if used_slots.iter().any(|used| used == slot_id) {
            continue;
        }
        let slot_token = normalize_surface_token(slot_id);
        let aliases = slot_aliases(slot_id);
        if candidates.iter().any(|candidate| {
            candidate == &slot_token
                || candidate.contains(&slot_token)
                || aliases
                    .iter()
                    .any(|alias| candidate == alias || candidate.contains(alias))
        }) {
            return Some(slot_id.clone());
        }
    }

    let task_slot = available_slots
        .iter()
        .find(|slot_id| normalize_surface_token(slot_id) == "tasksurface")?;
    if used_slots.iter().any(|used| used == task_slot) {
        return None;
    }
    Some(task_slot.clone())
}

fn slot_aliases(surface_id: &str) -> &'static [&'static str] {
    match normalize_surface_token(surface_id).as_str() {
        "launcher" => &["launcherpanel", "shelllauncher"],
        "tasksurface" => &["workspace", "workspacepanel", "taskpanel"],
        "approvalpanel" => &["approvalpanelshell", "shellapprovalpanel"],
        "notificationcenter" => &["notificationcenterpanel", "notifications"],
        "portalchooser" => &["chooser", "portal"],
        "recoverysurface" => &["recovery"],
        "captureindicators" => &["capture", "indicators"],
        "remotegovernance" => &["remotegovernancepanel", "fleetgovernance", "governance"],
        "devicebackendstatus" => &["devicehealth", "backendstatus"],
        _ => &[],
    }
}

fn normalize_surface_token(value: &str) -> String {
    value
        .chars()
        .filter(|character| character.is_ascii_alphanumeric())
        .flat_map(char::to_lowercase)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::{
        match_panel_slot, normalize_workspace_toplevel_mode, panel_slot_surfaces,
        placement_contains_point, placement_stacking_layer, placement_z_index,
        surface_contains_point, surface_focus_policy, surface_placement, surface_pointer_policy,
        surface_window_policy,
    };
    use crate::config::Config;

    #[test]
    fn maps_panel_slot_surfaces() {
        let mut config = Config::default();
        config.panel_slots = vec!["launcher".to_string(), "task-surface".to_string()];

        let surfaces = panel_slot_surfaces(&config);
        assert_eq!(surfaces.len(), 2);
        assert_eq!(surfaces[0].surface_id, "launcher");
        assert_eq!(surfaces[0].role, "launcher-slot");
        assert_eq!(surfaces[0].shell_role, "dock");
        assert_eq!(surfaces[0].interaction_mode, "interactive");
        assert_eq!(surfaces[0].blocked_by, None);
        assert_eq!(surfaces[0].window_policy, "dock-exclusive");
        assert_eq!(surfaces[0].host_interface, "gtk-panel-slot");
        assert_eq!(surfaces[0].layout_zone, "left-dock");
        assert_eq!(surfaces[0].stacking_layer, "panel");
        assert_eq!(surfaces[0].z_index, 120);
        assert_eq!(surfaces[0].reservation_status, "panel-slot-open");
        assert_eq!(surfaces[0].pointer_policy, "interactive");
        assert_eq!(surfaces[0].focus_policy, "retain-client-focus");
        assert_eq!(surfaces[0].panel_host_status, "unbound");
        assert_eq!(surfaces[0].panel_primary_action_id, None);
        assert_eq!(surfaces[0].embedding_status, "panel-slot-open");
        assert_eq!(surfaces[1].role, "workspace-slot");
        assert_eq!(surfaces[1].shell_role, "workspace");
        assert_eq!(surfaces[1].window_policy, "workspace-maximized");
    }

    #[test]
    fn resolves_workspace_window_policy_from_config() {
        let mut config = Config::default();
        config.workspace_toplevel_mode = "fullscreen".to_string();
        let surfaces = panel_slot_surfaces(&config);
        let workspace = surfaces
            .iter()
            .find(|surface| surface.surface_id == "task-surface")
            .unwrap();
        assert_eq!(workspace.window_policy, "workspace-fullscreen");
        assert_eq!(
            surface_window_policy("task-surface", "maximized"),
            "workspace-maximized"
        );
        assert_eq!(
            surface_window_policy("task-surface", "fullscreen"),
            "workspace-fullscreen"
        );
        assert_eq!(
            normalize_workspace_toplevel_mode("full-screen"),
            "fullscreen"
        );
        assert_eq!(normalize_workspace_toplevel_mode("unknown"), "maximized");
    }

    #[test]
    fn matches_panel_slot_from_app_id() {
        let slot = match_panel_slot(
            &[
                "launcher".to_string(),
                "task-surface".to_string(),
                "approval-panel".to_string(),
            ],
            &[],
            Some("approval-panel-shell"),
            None,
        );
        assert_eq!(slot, Some("approval-panel".to_string()));
    }

    #[test]
    fn matches_panel_slot_from_process_per_component_app_id() {
        let slot = match_panel_slot(
            &[
                "launcher".to_string(),
                "approval-panel".to_string(),
                "portal-chooser".to_string(),
            ],
            &[],
            Some("aios.shell.panel.portal.chooser"),
            None,
        );
        assert_eq!(slot, Some("portal-chooser".to_string()));
    }

    #[test]
    fn matches_remote_governance_slot_aliases() {
        let slot = match_panel_slot(
            &[
                "remote-governance".to_string(),
                "device-backend-status".to_string(),
            ],
            &[],
            Some("aios.shell.panel.fleet-governance"),
            None,
        );
        assert_eq!(slot, Some("remote-governance".to_string()));
    }

    #[test]
    fn falls_back_to_task_surface_for_generic_client() {
        let slot = match_panel_slot(
            &["launcher".to_string(), "task-surface".to_string()],
            &[],
            Some("org.example.Editor"),
            Some("Notes"),
        );
        assert_eq!(slot, Some("task-surface".to_string()));
    }

    #[test]
    fn computes_notification_overlay_placement() {
        let placement = surface_placement("notification-center", 1440, 900);
        assert_eq!(placement.zone, "top-overlay");
        assert_eq!(placement.anchor, "top-right");
        assert!(placement.x > 900);
        assert!(placement.y < 32);
    }

    #[test]
    fn reports_modal_stacking_above_workspace() {
        assert_eq!(placement_stacking_layer("center-modal"), "modal");
        assert!(placement_z_index("center-modal") > placement_z_index("main-stage"));
        assert!(placement_z_index("top-overlay") > placement_z_index("right-rail"));
    }

    #[test]
    fn hit_tests_surface_placement() {
        let placement = surface_placement("task-surface", 1280, 800);
        assert!(placement_contains_point(&placement, 400.0, 240.0));
        assert!(!placement_contains_point(&placement, 8.0, 8.0));
        let surfaces = panel_slot_surfaces(&Config::default());
        let launcher = surfaces
            .iter()
            .find(|surface| surface.surface_id == "launcher")
            .unwrap();
        assert!(surface_contains_point(launcher, 8.0, 8.0));
        assert!(!surface_contains_point(launcher, 800.0, 8.0));
    }

    #[test]
    fn assigns_focus_and_pointer_policy_by_slot() {
        assert_eq!(surface_pointer_policy("capture-indicators"), "passthrough");
        assert_eq!(surface_focus_policy("approval-panel"), "shell-modal");
        assert_eq!(surface_focus_policy("task-surface"), "workspace-target");
        assert_eq!(surface_focus_policy("launcher"), "retain-client-focus");
    }
}
