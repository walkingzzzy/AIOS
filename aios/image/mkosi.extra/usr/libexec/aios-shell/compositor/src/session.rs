use crate::config::Config;
use crate::panel_snapshot::PanelSnapshot;
use crate::surfaces::{
    panel_slot_surfaces, placement_stacking_layer, placement_z_index, surface_focus_policy,
    surface_placement, surface_pointer_policy, Surface,
};
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::time::{SystemTime, UNIX_EPOCH};

const PANEL_ACTION_EVENT_HISTORY_LIMIT: usize = 16;

#[derive(Clone, Debug, Serialize)]
pub struct PanelActionEvent {
    pub sequence: u32,
    pub event_id: String,
    pub kind: String,
    pub recorded_at_ms: u128,
    pub tick: u32,
    pub slot_id: Option<String>,
    pub component: Option<String>,
    pub panel_id: Option<String>,
    pub action_id: Option<String>,
    pub input_kind: Option<String>,
    pub focus_policy: Option<String>,
    pub status: String,
    pub summary: Option<String>,
    pub error: Option<String>,
    pub payload: Option<Value>,
}

#[derive(Clone, Debug, Serialize)]
pub struct OutputLayoutSummary {
    pub output_id: String,
    pub connector_name: Option<String>,
    pub label: String,
    pub layout_x: i32,
    pub layout_y: i32,
    pub layout_width: i32,
    pub layout_height: i32,
    pub primary: bool,
    pub active: bool,
    pub renderable: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct ManagedWindowSummary {
    pub window_key: String,
    pub surface_id: String,
    pub app_id: Option<String>,
    pub title: Option<String>,
    pub slot_id: Option<String>,
    pub output_id: String,
    pub workspace_id: String,
    pub window_policy: String,
    pub floating: bool,
    pub visible: bool,
    pub minimized: bool,
    pub persisted: bool,
    pub interaction_state: String,
    pub layout_x: i32,
    pub layout_y: i32,
    pub layout_width: i32,
    pub layout_height: i32,
}

#[derive(Clone, Debug, Serialize)]
pub struct SessionState {
    pub service_id: String,
    pub runtime: String,
    pub desktop_host: String,
    pub lifecycle_state: String,
    pub started_at_ms: u128,
    pub process_id: u32,
    pub ticks: u32,
    pub socket_name: Option<String>,
    pub seat_name: Option<String>,
    pub pointer_status: String,
    pub keyboard_status: String,
    pub touch_status: String,
    pub compositor_backend: String,
    pub process_boundary_status: String,
    pub runtime_lock_path: Option<String>,
    pub runtime_ready_path: Option<String>,
    pub runtime_state_path: Option<String>,
    pub runtime_lock_status: String,
    pub runtime_ready_status: String,
    pub runtime_state_status: String,
    pub session_control_status: String,
    pub drm_device_path: Option<String>,
    pub drm_connector_name: Option<String>,
    pub drm_output_width: Option<i32>,
    pub drm_output_height: Option<i32>,
    pub drm_refresh_millihz: Option<i32>,
    pub output_count: u32,
    pub connected_output_count: u32,
    pub primary_output_name: Option<String>,
    pub output_layout_mode: String,
    pub active_output_id: Option<String>,
    pub outputs: Vec<OutputLayoutSummary>,
    pub renderable_output_count: u32,
    pub non_renderable_output_count: u32,
    pub release_grade_output_status: String,
    pub window_manager_status: String,
    pub window_state_path: Option<String>,
    pub workspace_count: u32,
    pub active_workspace_index: u32,
    pub active_workspace_id: String,
    pub workspace_switch_count: u32,
    pub managed_window_count: u32,
    pub visible_window_count: u32,
    pub floating_window_count: u32,
    pub minimized_window_count: u32,
    pub window_move_count: u32,
    pub window_resize_count: u32,
    pub window_minimize_count: u32,
    pub window_restore_count: u32,
    pub last_minimized_window_key: Option<String>,
    pub last_restored_window_key: Option<String>,
    pub workspace_window_counts: BTreeMap<String, u32>,
    pub drag_state: String,
    pub resize_state: String,
    pub managed_windows: Vec<ManagedWindowSummary>,
    pub workspace_toplevel_mode: String,
    pub modal_surface_count: u32,
    pub blocked_surface_count: u32,
    pub shell_role_counts: BTreeMap<String, u32>,
    pub interaction_mode_counts: BTreeMap<String, u32>,
    pub window_policy_counts: BTreeMap<String, u32>,
    pub panel_host_status: String,
    pub panel_host_bound_count: u32,
    pub panel_host_activation_count: u32,
    pub panel_focus_status: String,
    pub last_panel_host_slot_id: Option<String>,
    pub last_panel_host_panel_id: Option<String>,
    pub panel_action_status: String,
    pub panel_action_dispatch_count: u32,
    pub last_panel_action_slot_id: Option<String>,
    pub last_panel_action_panel_id: Option<String>,
    pub last_panel_action_id: Option<String>,
    pub last_panel_action_summary: Option<String>,
    pub last_panel_action_target_component: Option<String>,
    pub panel_action_event_count: u32,
    pub last_panel_action_event_id: Option<String>,
    pub panel_action_log_status: String,
    pub panel_action_log_path: Option<String>,
    pub panel_action_events: Vec<PanelActionEvent>,
    pub panel_snapshot_source: Option<String>,
    pub panel_snapshot_profile_id: Option<String>,
    pub panel_snapshot_surface_count: u32,
    pub panel_embedding_status: String,
    pub embedded_surface_count: u32,
    pub stacking_status: String,
    pub attention_surface_count: u32,
    pub active_modal_surface_id: Option<String>,
    pub primary_attention_surface_id: Option<String>,
    pub host_focus_status: String,
    pub pending_damage_regions: Vec<(i32, i32, i32, i32)>,
    pub damage_tracking_enabled: bool,
    pub total_damage_events: u64,
    pub last_damage_at_ms: u64,
    pub smithay_status: String,
    pub renderer_backend: String,
    pub renderer_status: String,
    pub input_backend_status: String,
    pub input_device_count: u32,
    pub input_event_count: u32,
    pub keyboard_event_count: u32,
    pub pointer_event_count: u32,
    pub touch_event_count: u32,
    pub last_input_event: Option<String>,
    pub focused_surface_id: Option<String>,
    pub topmost_surface_id: Option<String>,
    pub topmost_slot_id: Option<String>,
    pub last_hit_surface_id: Option<String>,
    pub last_hit_slot_id: Option<String>,
    pub last_pointer_x: Option<f64>,
    pub last_pointer_y: Option<f64>,
    pub rendered_frame_count: u32,
    pub client_count: u32,
    pub commit_count: u32,
    pub xdg_shell_status: String,
    pub xdg_toplevel_count: u32,
    pub xdg_popup_count: u32,
    pub surface_count: u32,
    pub surfaces: Vec<Surface>,
    #[serde(skip)]
    next_panel_action_event_sequence: u32,
}

impl SessionState {
    pub fn new(config: &Config) -> Self {
        let mut session = Self {
            service_id: config.service_id.clone(),
            runtime: config.session_backend.clone(),
            desktop_host: config.desktop_host.clone(),
            lifecycle_state: "starting".to_string(),
            started_at_ms: now_ms(),
            process_id: std::process::id(),
            ticks: 0,
            socket_name: None,
            seat_name: None,
            pointer_status: "inactive".to_string(),
            keyboard_status: "inactive".to_string(),
            touch_status: "inactive".to_string(),
            compositor_backend: config.compositor_backend.clone(),
            process_boundary_status: "unfrozen".to_string(),
            runtime_lock_path: None,
            runtime_ready_path: None,
            runtime_state_path: None,
            runtime_lock_status: "unconfigured".to_string(),
            runtime_ready_status: "unconfigured".to_string(),
            runtime_state_status: "unconfigured".to_string(),
            session_control_status: "inactive".to_string(),
            drm_device_path: None,
            drm_connector_name: None,
            drm_output_width: None,
            drm_output_height: None,
            drm_refresh_millihz: None,
            output_count: 0,
            connected_output_count: 0,
            primary_output_name: None,
            output_layout_mode: config.output_layout_mode.clone(),
            active_output_id: None,
            outputs: Vec::new(),
            renderable_output_count: 0,
            non_renderable_output_count: 0,
            release_grade_output_status: "uninitialized".to_string(),
            window_manager_status: if config.window_state_path.is_some() {
                "persistent".to_string()
            } else {
                "ephemeral".to_string()
            },
            window_state_path: config.window_state_path.clone(),
            workspace_count: config.workspace_count.max(1),
            active_workspace_index: config
                .default_workspace_index
                .min(config.workspace_count.max(1).saturating_sub(1)),
            active_workspace_id: format!(
                "workspace-{}",
                config
                    .default_workspace_index
                    .min(config.workspace_count.max(1).saturating_sub(1))
                    + 1
            ),
            workspace_switch_count: 0,
            managed_window_count: 0,
            visible_window_count: 0,
            floating_window_count: 0,
            minimized_window_count: 0,
            window_move_count: 0,
            window_resize_count: 0,
            window_minimize_count: 0,
            window_restore_count: 0,
            last_minimized_window_key: None,
            last_restored_window_key: None,
            workspace_window_counts: BTreeMap::new(),
            drag_state: "idle".to_string(),
            resize_state: "idle".to_string(),
            managed_windows: Vec::new(),
            workspace_toplevel_mode: config.workspace_toplevel_mode.clone(),
            modal_surface_count: 0,
            blocked_surface_count: 0,
            shell_role_counts: BTreeMap::new(),
            interaction_mode_counts: BTreeMap::new(),
            window_policy_counts: BTreeMap::new(),
            panel_host_status: "disabled".to_string(),
            panel_host_bound_count: 0,
            panel_host_activation_count: 0,
            panel_focus_status: "inactive".to_string(),
            last_panel_host_slot_id: None,
            last_panel_host_panel_id: None,
            panel_action_status: "idle".to_string(),
            panel_action_dispatch_count: 0,
            last_panel_action_slot_id: None,
            last_panel_action_panel_id: None,
            last_panel_action_id: None,
            last_panel_action_summary: None,
            last_panel_action_target_component: None,
            panel_action_event_count: 0,
            last_panel_action_event_id: None,
            panel_action_log_status: if config.panel_action_log_path.is_some() {
                "configured".to_string()
            } else {
                "disabled".to_string()
            },
            panel_action_log_path: config.panel_action_log_path.clone(),
            panel_action_events: Vec::new(),
            panel_snapshot_source: None,
            panel_snapshot_profile_id: None,
            panel_snapshot_surface_count: 0,
            panel_embedding_status: if config.panel_slots.is_empty() {
                "no-panel-slots".to_string()
            } else {
                format!("panel-slots-open(0/{})", config.panel_slots.len())
            },
            embedded_surface_count: 0,
            stacking_status: if config.panel_slots.is_empty() {
                "no-panel-slots".to_string()
            } else {
                "panel-slots-open".to_string()
            },
            attention_surface_count: 0,
            active_modal_surface_id: None,
            primary_attention_surface_id: None,
            host_focus_status: "pending".to_string(),
            pending_damage_regions: Vec::new(),
            damage_tracking_enabled: true,
            total_damage_events: 0,
            last_damage_at_ms: 0,
            smithay_status: "inactive".to_string(),
            renderer_backend: "inactive".to_string(),
            renderer_status: "inactive".to_string(),
            input_backend_status: "inactive".to_string(),
            input_device_count: 0,
            input_event_count: 0,
            keyboard_event_count: 0,
            pointer_event_count: 0,
            touch_event_count: 0,
            last_input_event: None,
            focused_surface_id: None,
            topmost_surface_id: None,
            topmost_slot_id: None,
            last_hit_surface_id: None,
            last_hit_slot_id: None,
            last_pointer_x: None,
            last_pointer_y: None,
            rendered_frame_count: 0,
            client_count: 0,
            commit_count: 0,
            xdg_shell_status: "inactive".to_string(),
            xdg_toplevel_count: 0,
            xdg_popup_count: 0,
            surface_count: config.panel_slots.len() as u32,
            surfaces: panel_slot_surfaces(config),
            next_panel_action_event_sequence: 0,
        };
        session.recompute_window_policy_metrics();
        session
    }

    pub fn tick(&mut self) {
        self.ticks += 1;
        self.lifecycle_state = "running".to_string();
    }

    pub fn finish(&mut self) {
        self.lifecycle_state = "stopped".to_string();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_socket_name(&mut self, socket_name: Option<String>) {
        self.socket_name = socket_name;
    }

    pub fn set_seat_name(&mut self, seat_name: Option<String>) {
        self.seat_name = seat_name;
    }

    pub fn set_pointer_status<S: Into<String>>(&mut self, status: S) {
        self.pointer_status = status.into();
    }

    pub fn set_keyboard_status<S: Into<String>>(&mut self, status: S) {
        self.keyboard_status = status.into();
    }

    pub fn set_touch_status<S: Into<String>>(&mut self, status: S) {
        self.touch_status = status.into();
    }

    pub fn set_process_boundary_status<S: Into<String>>(&mut self, status: S) {
        self.process_boundary_status = status.into();
    }

    pub fn set_runtime_artifacts(
        &mut self,
        runtime_lock_path: Option<String>,
        runtime_ready_path: Option<String>,
        runtime_state_path: Option<String>,
    ) {
        self.runtime_lock_path = runtime_lock_path;
        self.runtime_ready_path = runtime_ready_path;
        self.runtime_state_path = runtime_state_path;
        self.runtime_lock_status = if self.runtime_lock_path.is_some() {
            "configured".to_string()
        } else {
            "disabled".to_string()
        };
        self.runtime_ready_status = if self.runtime_ready_path.is_some() {
            "configured".to_string()
        } else {
            "disabled".to_string()
        };
        self.runtime_state_status = if self.runtime_state_path.is_some() {
            "configured".to_string()
        } else {
            "disabled".to_string()
        };
    }

    pub fn set_runtime_lock_status<S: Into<String>>(&mut self, status: S) {
        self.runtime_lock_status = status.into();
    }

    pub fn set_runtime_ready_status<S: Into<String>>(&mut self, status: S) {
        self.runtime_ready_status = status.into();
    }

    pub fn set_runtime_state_status<S: Into<String>>(&mut self, status: S) {
        self.runtime_state_status = status.into();
    }

    pub fn set_session_control_status<S: Into<String>>(&mut self, status: S) {
        self.session_control_status = status.into();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_drm_topology(
        &mut self,
        drm_device_path: Option<String>,
        drm_connector_name: Option<String>,
        drm_output_width: Option<i32>,
        drm_output_height: Option<i32>,
        drm_refresh_millihz: Option<i32>,
        output_count: u32,
        connected_output_count: u32,
        primary_output_name: Option<String>,
    ) {
        self.drm_device_path = drm_device_path;
        self.drm_connector_name = drm_connector_name;
        self.drm_output_width = drm_output_width;
        self.drm_output_height = drm_output_height;
        self.drm_refresh_millihz = drm_refresh_millihz;
        self.output_count = output_count;
        self.connected_output_count = connected_output_count;
        self.primary_output_name = primary_output_name;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_window_state_path(&mut self, path: Option<String>) {
        self.window_state_path = path.clone();
        self.window_manager_status = if path.is_some() {
            "persistent".to_string()
        } else {
            "ephemeral".to_string()
        };
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn update_window_management(
        &mut self,
        status: String,
        output_layout_mode: String,
        active_output_id: Option<String>,
        outputs: Vec<OutputLayoutSummary>,
        workspace_count: u32,
        active_workspace_index: u32,
        workspace_switch_count: u32,
        managed_windows: Vec<ManagedWindowSummary>,
        window_move_count: u32,
        window_resize_count: u32,
        window_minimize_count: u32,
        window_restore_count: u32,
        last_minimized_window_key: Option<String>,
        last_restored_window_key: Option<String>,
        drag_state: String,
        resize_state: String,
    ) {
        self.window_manager_status = status;
        self.output_layout_mode = output_layout_mode;
        self.active_output_id = active_output_id.or_else(|| {
            outputs
                .iter()
                .find(|output| output.primary)
                .map(|output| output.output_id.clone())
                .or_else(|| outputs.first().map(|output| output.output_id.clone()))
        });
        self.outputs = outputs;
        self.renderable_output_count =
            self.outputs.iter().filter(|output| output.renderable).count() as u32;
        self.non_renderable_output_count =
            self.outputs.len() as u32 - self.renderable_output_count;
        self.release_grade_output_status = if self.outputs.is_empty() {
            "uninitialized".to_string()
        } else if self.outputs.len() == 1 {
            format!(
                "single-output(renderable={}/{})",
                self.renderable_output_count,
                self.outputs.len()
            )
        } else if self.non_renderable_output_count == 0 {
            format!(
                "multi-output(renderable={}/{})",
                self.renderable_output_count,
                self.outputs.len()
            )
        } else {
            format!(
                "multi-output(partial-renderable={}/{})",
                self.renderable_output_count,
                self.outputs.len()
            )
        };
        self.workspace_count = workspace_count.max(1);
        self.active_workspace_index =
            active_workspace_index.min(self.workspace_count.saturating_sub(1));
        self.active_workspace_id = format!("workspace-{}", self.active_workspace_index + 1);
        self.workspace_switch_count = workspace_switch_count;
        self.managed_window_count = managed_windows.len() as u32;
        self.visible_window_count = managed_windows
            .iter()
            .filter(|window| window.visible)
            .count() as u32;
        self.floating_window_count = managed_windows
            .iter()
            .filter(|window| window.floating)
            .count() as u32;
        self.minimized_window_count = managed_windows
            .iter()
            .filter(|window| window.minimized)
            .count() as u32;
        self.window_move_count = window_move_count;
        self.window_resize_count = window_resize_count;
        self.window_minimize_count = window_minimize_count;
        self.window_restore_count = window_restore_count;
        self.last_minimized_window_key = last_minimized_window_key;
        self.last_restored_window_key = last_restored_window_key;
        self.workspace_window_counts =
            managed_windows
                .iter()
                .fold(BTreeMap::new(), |mut counts, window| {
                    *counts.entry(window.workspace_id.clone()).or_insert(0) += 1;
                    counts
                });
        self.drag_state = drag_state;
        self.resize_state = resize_state;
        self.managed_windows = managed_windows;
    }

    pub fn set_panel_host_disabled(&mut self) {
        self.clear_panel_host_bindings();
        self.panel_focus_status = "inactive".to_string();
        self.last_panel_host_slot_id = None;
        self.last_panel_host_panel_id = None;
        self.panel_action_status = "idle".to_string();
        self.last_panel_action_slot_id = None;
        self.last_panel_action_panel_id = None;
        self.last_panel_action_id = None;
        self.last_panel_action_summary = None;
        self.last_panel_action_target_component = None;
        self.panel_host_status = "disabled".to_string();
        self.refresh_panel_embedding_status();
    }

    pub fn note_panel_host_error<S: Into<String>>(&mut self, status: S) {
        self.clear_panel_host_bindings();
        self.panel_focus_status = "inactive".to_string();
        self.last_panel_host_slot_id = None;
        self.last_panel_host_panel_id = None;
        self.panel_action_status = "idle".to_string();
        self.last_panel_action_slot_id = None;
        self.last_panel_action_panel_id = None;
        self.last_panel_action_id = None;
        self.last_panel_action_summary = None;
        self.last_panel_action_target_component = None;
        self.panel_host_status = status.into();
        self.refresh_panel_embedding_status();
    }

    pub fn apply_panel_snapshot_from(&mut self, snapshot: &PanelSnapshot, source: &str) {
        self.clear_panel_host_bindings();
        self.panel_snapshot_source = Some(source.to_string());
        self.panel_snapshot_profile_id = snapshot.profile_id.clone();
        self.panel_snapshot_surface_count = snapshot.surface_count;
        for panel_surface in &snapshot.surfaces {
            if let Some(surface) = self
                .surfaces
                .iter_mut()
                .find(|surface| surface.surface_id == panel_surface.component)
            {
                surface.host_interface = format!("{}-panel-host", self.desktop_host);
                surface.state = "panel-host-ready".to_string();
                surface.reservation_status = "panel-host-reserved".to_string();
                surface.panel_host_status = if panel_surface.error.is_some() {
                    "snapshot-error".to_string()
                } else {
                    "snapshot-bound".to_string()
                };
                surface.panel_component = Some(panel_surface.component.clone());
                surface.panel_id = panel_surface.panel_id.clone();
                surface.panel_status = panel_surface.status.clone();
                surface.panel_tone = panel_surface.tone.clone();
                surface.panel_primary_action_id = panel_surface.primary_action_id.clone();
                surface.panel_action_count = panel_surface.action_count;
                surface.panel_section_count = panel_surface.section_count;
                surface.panel_error = panel_surface.error.clone();
                surface.embedding_status = "panel-host-ready".to_string();
                Self::apply_panel_slot_policy(surface);
            }
        }
        self.refresh_panel_host_status();
        self.refresh_panel_embedding_status();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn sync_surface_layouts(&mut self, width: i32, height: i32) {
        for surface in &mut self.surfaces {
            let placement = surface_placement(&surface.surface_id, width, height);
            surface.layout_zone = placement.zone.to_string();
            surface.layout_anchor = placement.anchor.to_string();
            surface.layout_x = placement.x;
            surface.layout_y = placement.y;
            surface.layout_width = placement.width;
            surface.layout_height = placement.height;
            surface.stacking_layer = placement_stacking_layer(placement.zone).to_string();
            surface.z_index = placement_z_index(placement.zone);
            if surface.panel_component.is_some() {
                Self::apply_panel_slot_policy(surface);
            }
        }
        self.refresh_surface_attention_state();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn clear_surface_embeddings(&mut self) {
        for surface in &mut self.surfaces {
            surface.state = if surface.panel_component.is_some() {
                "panel-host-ready".to_string()
            } else {
                "slot-ready".to_string()
            };
            surface.reservation_status = if surface.embedded_surface_id.is_some() {
                "client-occupied".to_string()
            } else if surface.panel_component.is_some() {
                "panel-host-reserved".to_string()
            } else {
                "panel-slots-open".to_string()
            };
            surface.embedding_status = if surface.panel_component.is_some() {
                "panel-host-ready".to_string()
            } else {
                "panel-slots-open".to_string()
            };
            surface.embedded_surface_id = None;
            surface.client_app_id = None;
            surface.client_title = None;
        }
        self.refresh_panel_embedding_status();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn bind_surface_embedding(
        &mut self,
        slot_id: &str,
        embedded_surface_id: String,
        client_app_id: Option<String>,
        client_title: Option<String>,
    ) {
        if let Some(surface) = self
            .surfaces
            .iter_mut()
            .find(|surface| surface.surface_id == slot_id)
        {
            surface.state = "embedded-client".to_string();
            surface.reservation_status = "client-occupied".to_string();
            surface.embedding_status = "client-attached".to_string();
            surface.embedded_surface_id = Some(embedded_surface_id);
            surface.client_app_id = client_app_id;
            surface.client_title = client_title;
        }
        self.refresh_panel_embedding_status();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_panel_host_activation(
        &mut self,
        slot_id: &str,
        input_kind: &str,
    ) -> Option<String> {
        let (surface_id, panel_id, primary_action_id, focus_policy) = {
            let surface = self.surfaces.iter().find(|surface| {
                surface.surface_id == slot_id
                    && surface.panel_component.is_some()
                    && surface.embedded_surface_id.is_none()
                    && surface.pointer_policy != "passthrough"
            })?;
            (
                surface.surface_id.clone(),
                surface.panel_id.clone(),
                surface.panel_primary_action_id.clone(),
                surface.focus_policy.clone(),
            )
        };
        self.panel_host_activation_count += 1;
        self.last_panel_host_slot_id = Some(surface_id);
        self.last_panel_host_panel_id = panel_id;
        self.panel_focus_status = format!("{input_kind}:{focus_policy}");
        self.last_panel_action_slot_id = self.last_panel_host_slot_id.clone();
        self.last_panel_action_panel_id = self.last_panel_host_panel_id.clone();
        self.last_panel_action_id = primary_action_id;
        Some(focus_policy)
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_panel_action_result<S: Into<String>>(
        &mut self,
        status: S,
        summary: Option<String>,
    ) {
        self.panel_action_dispatch_count += 1;
        self.panel_action_status = status.into();
        self.last_panel_action_summary = summary;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_panel_action_target_component(&mut self, target_component: Option<String>) {
        self.last_panel_action_target_component = target_component;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_panel_action_log_status<S: Into<String>>(&mut self, status: S) {
        self.panel_action_log_status = status.into();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn record_panel_action_event(&mut self, mut event: PanelActionEvent) -> PanelActionEvent {
        self.next_panel_action_event_sequence += 1;
        event.sequence = self.next_panel_action_event_sequence;
        event.event_id = format!("panel-action-event-{:06}", event.sequence);
        event.recorded_at_ms = now_ms();
        self.panel_action_event_count += 1;
        self.last_panel_action_event_id = Some(event.event_id.clone());
        self.panel_action_events.push(event.clone());
        if self.panel_action_events.len() > PANEL_ACTION_EVENT_HISTORY_LIMIT {
            let overflow = self.panel_action_events.len() - PANEL_ACTION_EVENT_HISTORY_LIMIT;
            self.panel_action_events.drain(0..overflow);
        }
        event
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_stacking(
        &mut self,
        topmost_surface_id: Option<String>,
        topmost_slot_id: Option<String>,
    ) {
        self.topmost_surface_id = topmost_surface_id;
        let slot_topmost = self
            .active_modal_surface_id
            .clone()
            .or(topmost_slot_id)
            .or_else(|| self.top_active_slot_id());
        self.topmost_slot_id = slot_topmost.clone();
        if self.topmost_surface_id.is_none() {
            self.topmost_surface_id = slot_topmost.clone();
        }
        self.stacking_status = match slot_topmost.as_deref() {
            Some(surface_id)
                if self.embedded_surface_count > 0 && self.panel_host_bound_count > 0 =>
            {
                format!("hybrid-stack({surface_id})")
            }
            Some(surface_id) if self.embedded_surface_count > 0 => {
                format!("embedded-stack({surface_id})")
            }
            Some(surface_id) => format!("panel-host-stack({surface_id})"),
            None if self.surfaces.is_empty() => "no-panel-slots".to_string(),
            None if self.embedded_surface_count > 0 => format!(
                "embedded({}/{})",
                self.embedded_surface_count,
                self.surfaces.len()
            ),
            None => "panel-slots-open".to_string(),
        };
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_hit_test(
        &mut self,
        slot_id: Option<String>,
        surface_id: Option<String>,
        location: Option<(f64, f64)>,
    ) {
        self.last_hit_slot_id = slot_id;
        self.last_hit_surface_id = surface_id;
        if let Some((x, y)) = location {
            self.last_pointer_x = Some(x);
            self.last_pointer_y = Some(y);
        }
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_host_focus(&mut self, focused: bool) {
        self.host_focus_status = if focused {
            "focused".to_string()
        } else {
            "unfocused".to_string()
        };
        self.last_input_event = Some(format!("window-focus:{focused}"));
    }

    pub fn set_smithay_status<S: Into<String>>(&mut self, status: S) {
        self.smithay_status = status.into();
    }

    pub fn set_renderer_backend<S: Into<String>>(&mut self, backend: S) {
        self.renderer_backend = backend.into();
    }

    pub fn set_renderer_status<S: Into<String>>(&mut self, status: S) {
        self.renderer_status = status.into();
    }

    pub fn set_input_backend_status<S: Into<String>>(&mut self, status: S) {
        self.input_backend_status = status.into();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_input_device_count(&mut self, count: u32) {
        self.input_device_count = count;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_input_device_added<S: Into<String>>(&mut self, label: S) {
        self.input_device_count += 1;
        self.last_input_event = Some(format!("device-added:{}", label.into()));
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_input_device_removed<S: Into<String>>(&mut self, label: S) {
        self.input_device_count = self.input_device_count.saturating_sub(1);
        self.last_input_event = Some(format!("device-removed:{}", label.into()));
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_rendered_frame(&mut self) {
        self.rendered_frame_count += 1;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_client_count(&mut self, count: u32) {
        self.client_count = count;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_client_connected(&mut self) {
        self.client_count += 1;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_commit(&mut self) {
        self.commit_count += 1;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_keyboard_input<S: Into<String>>(&mut self, label: S) {
        self.input_event_count += 1;
        self.keyboard_event_count += 1;
        self.last_input_event = Some(label.into());
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_pointer_input<S: Into<String>>(&mut self, label: S, location: Option<(f64, f64)>) {
        self.input_event_count += 1;
        self.pointer_event_count += 1;
        self.last_input_event = Some(label.into());
        if let Some((x, y)) = location {
            self.last_pointer_x = Some(x);
            self.last_pointer_y = Some(y);
        }
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_touch_input<S: Into<String>>(&mut self, label: S) {
        self.input_event_count += 1;
        self.touch_event_count += 1;
        self.last_input_event = Some(label.into());
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_focused_surface_id(&mut self, surface_id: Option<String>) {
        self.focused_surface_id = surface_id;
    }

    pub fn set_xdg_shell_status<S: Into<String>>(&mut self, status: S) {
        self.xdg_shell_status = status.into();
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_xdg_toplevel_count(&mut self, count: u32) {
        self.xdg_toplevel_count = count;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_xdg_toplevel(&mut self) {
        self.xdg_toplevel_count += 1;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn set_xdg_popup_count(&mut self, count: u32) {
        self.xdg_popup_count = count;
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    pub fn note_xdg_popup(&mut self) {
        self.xdg_popup_count += 1;
    }

    pub fn json_summary(&self) -> String {
        serde_json::to_string(self).unwrap_or_else(|_| "{}".to_string())
    }

    pub fn record_damage(&mut self, x: i32, y: i32, width: i32, height: i32) {
        if self.damage_tracking_enabled {
            self.pending_damage_regions.push((x, y, width, height));
            self.total_damage_events += 1;
            self.last_damage_at_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
        }
    }

    pub fn drain_damage(&mut self) -> Vec<(i32, i32, i32, i32)> {
        std::mem::take(&mut self.pending_damage_regions)
    }

    pub fn merge_damage(&self) -> Option<(i32, i32, i32, i32)> {
        if self.pending_damage_regions.is_empty() {
            return None;
        }
        let mut min_x = i32::MAX;
        let mut min_y = i32::MAX;
        let mut max_x = i32::MIN;
        let mut max_y = i32::MIN;
        for &(x, y, w, h) in &self.pending_damage_regions {
            min_x = min_x.min(x);
            min_y = min_y.min(y);
            max_x = max_x.max(x + w);
            max_y = max_y.max(y + h);
        }
        Some((min_x, min_y, max_x - min_x, max_y - min_y))
    }
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

impl SessionState {
    fn clear_panel_host_bindings(&mut self) {
        self.panel_host_bound_count = 0;
        self.panel_snapshot_source = None;
        self.panel_snapshot_profile_id = None;
        self.panel_snapshot_surface_count = 0;
        self.last_panel_action_target_component = None;
        for surface in &mut self.surfaces {
            surface.host_interface = format!("{}-panel-slot", self.desktop_host);
            surface.reservation_status = if surface.embedded_surface_id.is_some() {
                "client-occupied".to_string()
            } else {
                "panel-slot-open".to_string()
            };
            surface.pointer_policy = surface_pointer_policy(&surface.surface_id).to_string();
            surface.focus_policy = surface_focus_policy(&surface.surface_id).to_string();
            surface.panel_host_status = "unbound".to_string();
            surface.panel_component = None;
            surface.panel_id = None;
            surface.panel_status = None;
            surface.panel_tone = None;
            surface.panel_primary_action_id = None;
            surface.panel_action_count = 0;
            surface.panel_section_count = 0;
            surface.panel_error = None;
            if surface.embedded_surface_id.is_none() {
                surface.state = "slot-ready".to_string();
                surface.embedding_status = "panel-slot-open".to_string();
                surface.z_index = placement_z_index(&surface.layout_zone);
            }
        }
    }

    fn refresh_panel_host_status(&mut self) {
        self.panel_host_bound_count = self
            .surfaces
            .iter()
            .filter(|surface| surface.panel_component.is_some())
            .count() as u32;
        self.panel_host_status = if self.panel_snapshot_surface_count == 0 {
            "snapshot-empty".to_string()
        } else if self.panel_host_bound_count == 0 {
            format!("snapshot-unmatched(0/{})", self.surfaces.len())
        } else if self.panel_host_bound_count == self.surfaces.len() as u32 {
            format!(
                "ready({}/{})",
                self.panel_host_bound_count,
                self.surfaces.len()
            )
        } else {
            format!(
                "partial({}/{})",
                self.panel_host_bound_count,
                self.surfaces.len()
            )
        };
    }

    fn refresh_panel_embedding_status(&mut self) {
        self.embedded_surface_count = self
            .surfaces
            .iter()
            .filter(|surface| surface.embedded_surface_id.is_some())
            .count() as u32;
        self.panel_embedding_status = if self.surfaces.is_empty() {
            "no-panel-slots".to_string()
        } else if self.embedded_surface_count == 0 {
            if self.panel_host_bound_count > 0 {
                format!(
                    "panel-host-ready({}/{})",
                    self.panel_host_bound_count,
                    self.surfaces.len()
                )
            } else {
                format!("panel-slots-open(0/{})", self.surfaces.len())
            }
        } else if self.embedded_surface_count == self.surfaces.len() as u32 {
            format!(
                "embedded({}/{})",
                self.embedded_surface_count,
                self.surfaces.len()
            )
        } else {
            format!(
                "partial-embedded({}/{})",
                self.embedded_surface_count,
                self.surfaces.len()
            )
        };
        self.refresh_surface_attention_state();
        if self.surfaces.is_empty() {
            self.topmost_surface_id = None;
            self.topmost_slot_id = None;
            self.stacking_status = "no-panel-slots".to_string();
            return;
        }

        let top_surface_id = self
            .active_modal_surface_id
            .clone()
            .or_else(|| self.top_active_slot_id());
        self.topmost_surface_id = top_surface_id.clone();
        self.topmost_slot_id = top_surface_id.clone();
        self.stacking_status = match top_surface_id.as_deref() {
            Some(surface_id)
                if self.embedded_surface_count > 0 && self.panel_host_bound_count > 0 =>
            {
                format!("hybrid-stack({surface_id})")
            }
            Some(surface_id) if self.embedded_surface_count > 0 => {
                format!("embedded-stack({surface_id})")
            }
            Some(surface_id) => format!("panel-host-stack({surface_id})"),
            None if self.embedded_surface_count > 0 => format!(
                "embedded({}/{})",
                self.embedded_surface_count,
                self.surfaces.len()
            ),
            None => "panel-slots-open".to_string(),
        };
    }

    fn apply_panel_slot_policy(surface: &mut Surface) {
        let base_z_index = placement_z_index(&surface.layout_zone);
        surface.z_index = base_z_index + surface_priority_boost(surface);
        if is_modal_attention_surface(surface) {
            surface.focus_policy = "shell-modal".to_string();
            surface.reservation_status = "panel-host-modal".to_string();
        } else if surface.panel_component.is_some() {
            surface.reservation_status = "panel-host-reserved".to_string();
        }
    }

    fn top_active_slot_id(&self) -> Option<String> {
        self.surfaces
            .iter()
            .filter(|surface| surface_has_active_content(surface))
            .max_by_key(|surface| surface.z_index)
            .map(|surface| surface.surface_id.clone())
    }

    fn refresh_surface_attention_state(&mut self) {
        let attention_surfaces = self
            .surfaces
            .iter()
            .filter(|surface| surface_has_active_content(surface) && is_attention_surface(surface))
            .collect::<Vec<_>>();

        self.attention_surface_count = attention_surfaces.len() as u32;
        self.active_modal_surface_id = self
            .surfaces
            .iter()
            .filter(|surface| is_engaged_modal_surface(surface))
            .max_by_key(|surface| modal_surface_priority(surface))
            .map(|surface| surface.surface_id.clone());
        self.primary_attention_surface_id = attention_surfaces
            .into_iter()
            .max_by_key(|surface| primary_attention_priority(surface))
            .map(|surface| surface.surface_id.clone())
            .or_else(|| self.active_modal_surface_id.clone());
        self.recompute_window_policy_metrics();
    }

    fn recompute_window_policy_metrics(&mut self) {
        let active_modal_surface_id = self.active_modal_surface_id.clone();
        let mut modal_surface_count = 0u32;
        let mut blocked_surface_count = 0u32;
        let mut shell_role_counts = BTreeMap::new();
        let mut interaction_mode_counts = BTreeMap::new();
        let mut window_policy_counts = BTreeMap::new();

        for surface in &mut self.surfaces {
            *shell_role_counts
                .entry(surface.shell_role.clone())
                .or_insert(0) += 1;
            *window_policy_counts
                .entry(surface.window_policy.clone())
                .or_insert(0) += 1;
            if surface_has_active_content(surface) && surface.shell_role == "modal" {
                modal_surface_count += 1;
            }

            surface.blocked_by = None;
            surface.interaction_mode = if is_passive_attention_surface(surface) {
                "passive".to_string()
            } else if active_modal_surface_id.as_deref() == Some(surface.surface_id.as_str()) {
                "modal".to_string()
            } else if surface_has_active_content(surface) && surface.shell_role == "modal" {
                "modal".to_string()
            } else if active_modal_surface_id.is_some()
                && surface_has_active_content(surface)
                && should_block_surface_by_modal(surface)
            {
                blocked_surface_count += 1;
                surface.blocked_by = active_modal_surface_id.clone();
                "blocked-by-modal".to_string()
            } else if surface.shell_role == "workspace" {
                "workspace".to_string()
            } else {
                "interactive".to_string()
            };
            *interaction_mode_counts
                .entry(surface.interaction_mode.clone())
                .or_insert(0) += 1;
        }

        self.modal_surface_count = modal_surface_count;
        self.blocked_surface_count = blocked_surface_count;
        self.shell_role_counts = shell_role_counts;
        self.interaction_mode_counts = interaction_mode_counts;
        self.window_policy_counts = window_policy_counts;
    }
}

fn surface_has_active_content(surface: &Surface) -> bool {
    surface.panel_component.is_some() || surface.embedded_surface_id.is_some()
}

fn is_modal_slot(surface: &Surface) -> bool {
    matches!(
        surface.role.as_str(),
        "approval-slot" | "chooser-slot" | "recovery-slot"
    )
}

fn is_attention_surface(surface: &Surface) -> bool {
    matches!(surface.panel_tone.as_deref(), Some("warning" | "critical"))
        || matches!(
            surface.panel_status.as_deref(),
            Some(
                "attention"
                    | "blocked"
                    | "degraded"
                    | "error"
                    | "failed"
                    | "pending"
                    | "recovery-required"
                    | "warning"
            )
        )
        || surface.panel_error.is_some()
}

fn is_modal_attention_surface(surface: &Surface) -> bool {
    is_modal_slot(surface) && is_attention_surface(surface)
}

fn is_engaged_modal_surface(surface: &Surface) -> bool {
    surface_has_active_content(surface)
        && is_modal_slot(surface)
        && (is_attention_surface(surface) || surface.embedded_surface_id.is_some())
}

fn is_passive_attention_surface(surface: &Surface) -> bool {
    surface.pointer_policy == "passthrough" || surface.focus_policy == "passive-overlay"
}

fn should_block_surface_by_modal(surface: &Surface) -> bool {
    !matches!(surface.shell_role.as_str(), "modal") && !is_passive_attention_surface(surface)
}

fn modal_surface_priority(surface: &Surface) -> (i32, i32, i32) {
    (
        match surface.role.as_str() {
            "approval-slot" => 240,
            "chooser-slot" => 160,
            "recovery-slot" => 120,
            _ => 0,
        },
        attention_status_priority(surface),
        (surface.panel_action_count.min(3) as i32) * 4,
    )
}

fn primary_attention_priority(surface: &Surface) -> (i32, i32, i32, i32) {
    (
        if is_passive_attention_surface(surface) {
            0
        } else {
            1
        },
        match surface.role.as_str() {
            "indicator-slot" => 360,
            "recovery-slot" => 340,
            "chooser-slot" => 320,
            "approval-slot" => 280,
            "notification-slot" => 220,
            "governance-slot" => 170,
            "device-health-slot" => 180,
            "launcher-slot" => 140,
            "workspace-slot" => 120,
            _ => 100,
        },
        attention_status_priority(surface),
        (surface.panel_action_count.min(3) as i32) * 4,
    )
}

fn attention_status_priority(surface: &Surface) -> i32 {
    match surface.panel_status.as_deref() {
        Some("pending" | "blocked" | "failed" | "recovery-required") => 120,
        Some("attention" | "degraded" | "error" | "warning") => 60,
        _ if is_attention_surface(surface) => 24,
        _ => 0,
    }
}

fn surface_priority_boost(surface: &Surface) -> i32 {
    let mut boost = match surface.role.as_str() {
        "approval-slot" => 240,
        "chooser-slot" => 160,
        "recovery-slot" => 120,
        "notification-slot" => 18,
        "governance-slot" => 9,
        "launcher-slot" => 8,
        "device-health-slot" => 10,
        _ => 0,
    };
    boost += match surface.panel_status.as_deref() {
        Some("pending" | "blocked" | "failed" | "recovery-required") => 120,
        Some("attention" | "degraded" | "error" | "warning") => 60,
        _ if is_attention_surface(surface) => 24,
        _ => 0,
    };
    if surface.focus_policy == "shell-modal" {
        boost += 24;
    }
    if surface.panel_action_count > 0 {
        boost += (surface.panel_action_count.min(3) as i32) * 4;
    }
    boost
}

#[cfg(test)]
mod tests {
    use super::{PanelActionEvent, SessionState};
    use crate::config::Config;

    #[test]
    fn renders_json_summary() {
        let config = Config::default();
        let session = SessionState::new(&config);
        let summary = session.json_summary();
        assert!(summary.contains("\"service_id\":\"aios-shell-compositor\""));
        assert!(summary.contains("\"process_id\":"));
        assert!(summary.contains("\"seat_name\":null"));
        assert!(summary.contains("\"pointer_status\":\"inactive\""));
        assert!(summary.contains("\"keyboard_status\":\"inactive\""));
        assert!(summary.contains("\"touch_status\":\"inactive\""));
        assert!(summary.contains("\"compositor_backend\":\"winit\""));
        assert!(summary.contains("\"process_boundary_status\":\"unfrozen\""));
        assert!(summary.contains("\"runtime_lock_path\":null"));
        assert!(summary.contains("\"runtime_ready_path\":null"));
        assert!(summary.contains("\"runtime_state_path\":null"));
        assert!(summary.contains("\"runtime_lock_status\":\"unconfigured\""));
        assert!(summary.contains("\"runtime_ready_status\":\"unconfigured\""));
        assert!(summary.contains("\"runtime_state_status\":\"unconfigured\""));
        assert!(summary.contains("\"session_control_status\":\"inactive\""));
        assert!(summary.contains("\"drm_device_path\":null"));
        assert!(summary.contains("\"output_count\":0"));
        assert!(summary.contains("\"connected_output_count\":0"));
        assert!(summary.contains("\"primary_output_name\":null"));
        assert!(summary.contains("\"panel_host_status\":\"disabled\""));
        assert!(summary.contains("\"panel_host_bound_count\":0"));
        assert!(summary.contains("\"panel_host_activation_count\":0"));
        assert!(summary.contains("\"panel_focus_status\":\"inactive\""));
        assert!(summary.contains("\"last_panel_host_slot_id\":null"));
        assert!(summary.contains("\"last_panel_host_panel_id\":null"));
        assert!(summary.contains("\"panel_action_status\":\"idle\""));
        assert!(summary.contains("\"panel_action_dispatch_count\":0"));
        assert!(summary.contains("\"last_panel_action_slot_id\":null"));
        assert!(summary.contains("\"last_panel_action_panel_id\":null"));
        assert!(summary.contains("\"last_panel_action_id\":null"));
        assert!(summary.contains("\"last_panel_action_summary\":null"));
        assert!(summary.contains("\"last_panel_action_target_component\":null"));
        assert!(summary.contains("\"panel_action_event_count\":0"));
        assert!(summary.contains("\"last_panel_action_event_id\":null"));
        assert!(summary.contains("\"panel_action_log_status\":\"disabled\""));
        assert!(summary.contains("\"panel_action_log_path\":null"));
        assert!(summary.contains("\"panel_action_events\":[]"));
        assert!(summary.contains("\"panel_snapshot_source\":null"));
        assert!(summary.contains("\"panel_snapshot_profile_id\":null"));
        assert!(summary.contains("\"panel_snapshot_surface_count\":0"));
        assert!(summary.contains(&format!(
            "\"panel_embedding_status\":\"panel-slots-open(0/{})\"",
            config.panel_slots.len()
        )));
        assert!(summary.contains("\"embedded_surface_count\":0"));
        assert!(summary.contains("\"stacking_status\":\"panel-slots-open\""));
        assert!(summary.contains("\"attention_surface_count\":0"));
        assert!(summary.contains("\"active_modal_surface_id\":null"));
        assert!(summary.contains("\"primary_attention_surface_id\":null"));
        assert!(summary.contains("\"host_focus_status\":\"pending\""));
        assert!(summary.contains("\"smithay_status\":\"inactive\""));
        assert!(summary.contains("\"renderer_backend\":\"inactive\""));
        assert!(summary.contains("\"renderer_status\":\"inactive\""));
        assert!(summary.contains("\"input_backend_status\":\"inactive\""));
        assert!(summary.contains("\"input_device_count\":0"));
        assert!(summary.contains("\"input_event_count\":0"));
        assert!(summary.contains("\"keyboard_event_count\":0"));
        assert!(summary.contains("\"pointer_event_count\":0"));
        assert!(summary.contains("\"touch_event_count\":0"));
        assert!(summary.contains("\"last_input_event\":null"));
        assert!(summary.contains("\"focused_surface_id\":null"));
        assert!(summary.contains("\"topmost_surface_id\":null"));
        assert!(summary.contains("\"last_hit_surface_id\":null"));
        assert!(summary.contains("\"last_hit_slot_id\":null"));
        assert!(summary.contains("\"last_pointer_x\":null"));
        assert!(summary.contains("\"last_pointer_y\":null"));
        assert!(summary.contains("\"xdg_shell_status\":\"inactive\""));
        assert!(summary.contains(&format!(
            "\"surface_count\":{}",
            config.panel_slots.len()
        )));
        assert!(summary.contains("\"layout_zone\":\"left-dock\""));
        assert!(summary.contains("\"stacking_layer\":\"panel\""));
        assert!(summary.contains("\"z_index\":120"));
        assert!(summary.contains("\"reservation_status\":\"panel-slot-open\""));
        assert!(summary.contains("\"pointer_policy\":\"interactive\""));
        assert!(summary.contains("\"focus_policy\":\"retain-client-focus\""));
        assert!(summary.contains("\"panel_host_status\":\"unbound\""));
        assert!(summary.contains("\"panel_component\":null"));
        assert!(summary.contains("\"panel_id\":null"));
        assert!(summary.contains("\"panel_status\":null"));
        assert!(summary.contains("\"panel_tone\":null"));
        assert!(summary.contains("\"panel_primary_action_id\":null"));
        assert!(summary.contains("\"panel_action_count\":0"));
        assert!(summary.contains("\"panel_section_count\":0"));
        assert!(summary.contains("\"panel_error\":null"));
        assert!(summary.contains("\"embedding_status\":\"panel-slot-open\""));
    }

    #[test]
    fn records_panel_host_activation_state() {
        use crate::panel_snapshot::{PanelSnapshot, PanelSurface};

        let config = Config::default();
        let mut session = SessionState::new(&config);
        session.apply_panel_snapshot_from(
            &PanelSnapshot {
                profile_id: Some("shell-compositor-smoke".to_string()),
                surface_count: 1,
                surfaces: vec![PanelSurface {
                    component: "approval-panel".to_string(),
                    panel_id: Some("approval-panel-shell".to_string()),
                    status: Some("pending".to_string()),
                    tone: Some("warning".to_string()),
                    primary_action_id: Some("approve".to_string()),
                    action_count: 2,
                    section_count: 1,
                    error: None,
                }],
            },
            "command",
        );

        let focus_policy = session.note_panel_host_activation("approval-panel", "pointer-button");
        assert_eq!(focus_policy.as_deref(), Some("shell-modal"));
        assert_eq!(session.panel_host_activation_count, 1);
        assert_eq!(session.panel_focus_status, "pointer-button:shell-modal");
        assert_eq!(session.attention_surface_count, 1);
        assert_eq!(
            session.active_modal_surface_id.as_deref(),
            Some("approval-panel")
        );
        assert_eq!(
            session.primary_attention_surface_id.as_deref(),
            Some("approval-panel")
        );
        assert_eq!(
            session.last_panel_host_slot_id.as_deref(),
            Some("approval-panel")
        );
        assert_eq!(
            session.last_panel_host_panel_id.as_deref(),
            Some("approval-panel-shell")
        );
        assert_eq!(session.last_panel_action_id.as_deref(), Some("approve"));

        session
            .note_panel_action_result("dispatch-ok", Some("Approve: status=pending".to_string()));
        assert_eq!(session.panel_action_status, "dispatch-ok");
        assert_eq!(session.panel_action_dispatch_count, 1);
        assert_eq!(
            session.last_panel_action_summary.as_deref(),
            Some("Approve: status=pending")
        );
    }

    #[test]
    fn records_panel_action_events_in_summary() {
        let config = Config::default();
        let mut session = SessionState::new(&config);
        session.record_panel_action_event(PanelActionEvent {
            sequence: 0,
            event_id: String::new(),
            kind: "panel-host.activation".to_string(),
            recorded_at_ms: 0,
            tick: 3,
            slot_id: Some("approval-panel".to_string()),
            component: Some("approval-panel".to_string()),
            panel_id: Some("approval-panel-shell".to_string()),
            action_id: Some("approve".to_string()),
            input_kind: Some("pointer-button".to_string()),
            focus_policy: Some("shell-modal".to_string()),
            status: "activated".to_string(),
            summary: Some("approval-panel activated".to_string()),
            error: None,
            payload: None,
        });
        session.record_panel_action_event(PanelActionEvent {
            sequence: 0,
            event_id: String::new(),
            kind: "panel-action.dispatch".to_string(),
            recorded_at_ms: 0,
            tick: 3,
            slot_id: Some("approval-panel".to_string()),
            component: Some("approval-panel".to_string()),
            panel_id: Some("approval-panel-shell".to_string()),
            action_id: Some("approve".to_string()),
            input_kind: Some("pointer-button".to_string()),
            focus_policy: Some("shell-modal".to_string()),
            status: "dispatch-ok(approve)".to_string(),
            summary: Some("Approve: approval-1 -> approved".to_string()),
            error: None,
            payload: Some(serde_json::json!({
                "component": "approval-panel",
                "result": {"approval_ref": "approval-1", "status": "approved"},
            })),
        });

        let summary = session.json_summary();
        assert_eq!(session.panel_action_event_count, 2);
        assert_eq!(
            session.last_panel_action_event_id.as_deref(),
            Some("panel-action-event-000002")
        );
        assert!(summary.contains("\"panel_action_event_count\":2"));
        assert!(summary.contains("\"last_panel_action_event_id\":\"panel-action-event-000002\""));
        assert!(summary.contains("\"panel-host.activation\""));
        assert!(summary.contains("\"panel-action.dispatch\""));
        assert!(summary.contains("\"approval_ref\":\"approval-1\""));
    }

    #[test]
    fn prefers_recovery_surface_over_passive_indicator_for_attention() {
        use crate::panel_snapshot::{PanelSnapshot, PanelSurface};

        let config = Config::default();
        let mut session = SessionState::new(&config);
        session.apply_panel_snapshot_from(
            &PanelSnapshot {
                profile_id: Some("shell-compositor-attention".to_string()),
                surface_count: 2,
                surfaces: vec![
                    PanelSurface {
                        component: "capture-indicators".to_string(),
                        panel_id: Some("capture-strip".to_string()),
                        status: Some("warning".to_string()),
                        tone: Some("warning".to_string()),
                        primary_action_id: Some("review-approvals".to_string()),
                        action_count: 1,
                        section_count: 1,
                        error: None,
                    },
                    PanelSurface {
                        component: "recovery-surface".to_string(),
                        panel_id: Some("recovery-surface-panel".to_string()),
                        status: Some("recovery-required".to_string()),
                        tone: Some("warning".to_string()),
                        primary_action_id: Some("rollback".to_string()),
                        action_count: 2,
                        section_count: 2,
                        error: None,
                    },
                ],
            },
            "command",
        );

        assert_eq!(session.attention_surface_count, 2);
        assert_eq!(
            session.active_modal_surface_id.as_deref(),
            Some("recovery-surface")
        );
        assert_eq!(
            session.primary_attention_surface_id.as_deref(),
            Some("recovery-surface")
        );
    }

    #[test]
    fn embedded_modal_slot_keeps_modal_stack_without_panel_snapshot() {
        let config = Config::default();
        let mut session = SessionState::new(&config);
        session.bind_surface_embedding(
            "approval-panel",
            "embedded-approval-1".to_string(),
            Some("org.example.ApprovalDialog".to_string()),
            Some("Approval Dialog".to_string()),
        );

        assert_eq!(session.embedded_surface_count, 1);
        assert_eq!(
            session.active_modal_surface_id.as_deref(),
            Some("approval-panel")
        );
        assert_eq!(
            session.primary_attention_surface_id.as_deref(),
            Some("approval-panel")
        );
        assert_eq!(
            session.topmost_surface_id.as_deref(),
            Some("approval-panel")
        );
        assert_eq!(session.stacking_status, "embedded-stack(approval-panel)");
    }

    #[test]
    fn hybrid_embedding_stack_prefers_modal_slot() {
        use crate::panel_snapshot::{PanelSnapshot, PanelSurface};

        let config = Config::default();
        let mut session = SessionState::new(&config);
        session.apply_panel_snapshot_from(
            &PanelSnapshot {
                profile_id: Some("shell-compositor-hybrid".to_string()),
                surface_count: 1,
                surfaces: vec![PanelSurface {
                    component: "approval-panel".to_string(),
                    panel_id: Some("approval-panel-shell".to_string()),
                    status: Some("pending".to_string()),
                    tone: Some("warning".to_string()),
                    primary_action_id: Some("approve".to_string()),
                    action_count: 2,
                    section_count: 1,
                    error: None,
                }],
            },
            "command",
        );
        session.bind_surface_embedding(
            "approval-panel",
            "embedded-approval-2".to_string(),
            Some("aios.shell.panel.approval".to_string()),
            Some("Approval Panel".to_string()),
        );

        assert_eq!(session.panel_host_bound_count, 1);
        assert_eq!(session.embedded_surface_count, 1);
        assert_eq!(session.stacking_status, "hybrid-stack(approval-panel)");
        assert_eq!(
            session.active_modal_surface_id.as_deref(),
            Some("approval-panel")
        );
    }

    #[test]
    fn tracks_window_policy_metrics_when_modal_surface_blocks_other_content() {
        use crate::panel_snapshot::{PanelSnapshot, PanelSurface};

        let config = Config::default();
        let mut session = SessionState::new(&config);
        session.apply_panel_snapshot_from(
            &PanelSnapshot {
                profile_id: Some("shell-compositor-policy".to_string()),
                surface_count: 3,
                surfaces: vec![
                    PanelSurface {
                        component: "launcher".to_string(),
                        panel_id: Some("launcher-panel".to_string()),
                        status: Some("active".to_string()),
                        tone: Some("positive".to_string()),
                        primary_action_id: Some("create-session".to_string()),
                        action_count: 1,
                        section_count: 1,
                        error: None,
                    },
                    PanelSurface {
                        component: "approval-panel".to_string(),
                        panel_id: Some("approval-panel-shell".to_string()),
                        status: Some("pending".to_string()),
                        tone: Some("warning".to_string()),
                        primary_action_id: Some("approve".to_string()),
                        action_count: 2,
                        section_count: 1,
                        error: None,
                    },
                    PanelSurface {
                        component: "notification-center".to_string(),
                        panel_id: Some("notification-center-panel".to_string()),
                        status: Some("info".to_string()),
                        tone: Some("neutral".to_string()),
                        primary_action_id: Some("refresh".to_string()),
                        action_count: 1,
                        section_count: 1,
                        error: None,
                    },
                ],
            },
            "command",
        );

        assert_eq!(session.modal_surface_count, 1);
        assert_eq!(session.blocked_surface_count, 2);
        assert_eq!(session.topmost_slot_id.as_deref(), Some("approval-panel"));
        assert_eq!(session.shell_role_counts.get("dock"), Some(&1));
        assert_eq!(session.window_policy_counts.get("modal-dialog"), Some(&2));
        assert_eq!(
            session.interaction_mode_counts.get("blocked-by-modal"),
            Some(&2)
        );
        let launcher = session
            .surfaces
            .iter()
            .find(|surface| surface.surface_id == "launcher")
            .unwrap();
        assert_eq!(launcher.interaction_mode, "blocked-by-modal");
        assert_eq!(launcher.blocked_by.as_deref(), Some("approval-panel"));
    }

    #[test]
    fn updates_runtime_client_metrics_in_summary() {
        let config = Config::default();
        let mut session = SessionState::new(&config);
        session.set_client_count(2);
        session.set_xdg_toplevel_count(2);
        session.set_xdg_popup_count(1);

        let summary = session.json_summary();
        assert!(summary.contains("\"client_count\":2"));
        assert!(summary.contains("\"xdg_toplevel_count\":2"));
        assert!(summary.contains("\"xdg_popup_count\":1"));
    }
}
