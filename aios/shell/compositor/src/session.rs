use crate::config::Config;
use crate::panel_snapshot::PanelSnapshot;
use crate::surfaces::{
    placeholder_surfaces, placement_stacking_layer, placement_z_index, surface_focus_policy,
    surface_placement, surface_pointer_policy, Surface,
};
use serde::Serialize;
use serde_json::Value;
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

#[derive(Clone, Debug)]
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
    pub output_count: u32,
    pub connected_output_count: u32,
    pub primary_output_name: Option<String>,
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
    pub surfaces: Vec<Surface>,
    next_panel_action_event_sequence: u32,
}

impl SessionState {
    pub fn new(config: &Config) -> Self {
        Self {
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
            output_count: 0,
            connected_output_count: 0,
            primary_output_name: None,
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
            panel_embedding_status: "placeholder-only".to_string(),
            embedded_surface_count: 0,
            stacking_status: "placeholder-only".to_string(),
            attention_surface_count: 0,
            active_modal_surface_id: None,
            primary_attention_surface_id: None,
            host_focus_status: "pending".to_string(),
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
            surfaces: placeholder_surfaces(config),
            next_panel_action_event_sequence: 0,
        }
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
        output_count: u32,
        connected_output_count: u32,
        primary_output_name: Option<String>,
    ) {
        self.drm_device_path = drm_device_path;
        self.output_count = output_count;
        self.connected_output_count = connected_output_count;
        self.primary_output_name = primary_output_name;
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
                "placeholder-ready".to_string()
            };
            surface.reservation_status = if surface.embedded_surface_id.is_some() {
                "client-occupied".to_string()
            } else if surface.panel_component.is_some() {
                "panel-host-reserved".to_string()
            } else {
                "placeholder-only".to_string()
            };
            surface.embedding_status = if surface.panel_component.is_some() {
                "panel-host-ready".to_string()
            } else {
                "placeholder-only".to_string()
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
    pub fn note_stacking(&mut self, topmost_surface_id: Option<String>) {
        let has_embedded_topmost = topmost_surface_id.is_some();
        self.topmost_surface_id = topmost_surface_id;
        let panel_host_topmost = if !has_embedded_topmost {
            self.top_panel_surface_id()
        } else if self.topmost_surface_id.is_some() {
            None
        } else {
            self.top_panel_surface_id()
        };
        if self.topmost_surface_id.is_none() {
            self.topmost_surface_id = panel_host_topmost.clone();
        }
        self.stacking_status = if self.embedded_surface_count == 0 {
            if let Some(surface_id) = self.topmost_surface_id.as_deref() {
                format!("panel-host-only({surface_id})")
            } else {
                "placeholder-only".to_string()
            }
        } else if self.topmost_surface_id.is_some() {
            format!("active({})", self.embedded_surface_count)
        } else {
            format!("no-topmost({})", self.embedded_surface_count)
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
        let socket_name = json_string_option(self.socket_name.as_deref());
        let seat_name = json_string_option(self.seat_name.as_deref());
        let runtime_lock_path = json_string_option(self.runtime_lock_path.as_deref());
        let runtime_ready_path = json_string_option(self.runtime_ready_path.as_deref());
        let runtime_state_path = json_string_option(self.runtime_state_path.as_deref());
        let panel_snapshot_source = json_string_option(self.panel_snapshot_source.as_deref());
        let panel_snapshot_profile_id =
            json_string_option(self.panel_snapshot_profile_id.as_deref());
        let last_panel_host_slot_id = json_string_option(self.last_panel_host_slot_id.as_deref());
        let last_panel_host_panel_id = json_string_option(self.last_panel_host_panel_id.as_deref());
        let last_panel_action_slot_id =
            json_string_option(self.last_panel_action_slot_id.as_deref());
        let last_panel_action_panel_id =
            json_string_option(self.last_panel_action_panel_id.as_deref());
        let last_panel_action_id = json_string_option(self.last_panel_action_id.as_deref());
        let last_panel_action_summary =
            json_string_option(self.last_panel_action_summary.as_deref());
        let last_panel_action_target_component =
            json_string_option(self.last_panel_action_target_component.as_deref());
        let last_panel_action_event_id =
            json_string_option(self.last_panel_action_event_id.as_deref());
        let panel_action_log_status = json_escape(&self.panel_action_log_status);
        let panel_action_log_path = json_string_option(self.panel_action_log_path.as_deref());
        let panel_action_events =
            serde_json::to_string(&self.panel_action_events).unwrap_or_else(|_| "[]".to_string());
        let last_input_event = json_string_option(self.last_input_event.as_deref());
        let focused_surface_id = json_string_option(self.focused_surface_id.as_deref());
        let topmost_surface_id = json_string_option(self.topmost_surface_id.as_deref());
        let last_hit_surface_id = json_string_option(self.last_hit_surface_id.as_deref());
        let last_hit_slot_id = json_string_option(self.last_hit_slot_id.as_deref());
        let last_pointer_x = json_number_option(self.last_pointer_x);
        let last_pointer_y = json_number_option(self.last_pointer_y);
        let active_modal_surface_id = json_string_option(self.active_modal_surface_id.as_deref());
        let primary_attention_surface_id =
            json_string_option(self.primary_attention_surface_id.as_deref());
        let drm_device_path = json_string_option(self.drm_device_path.as_deref());
        let primary_output_name = json_string_option(self.primary_output_name.as_deref());
        let surfaces = self
            .surfaces
            .iter()
            .map(|surface| {
                let embedded_surface_id = json_string_option(surface.embedded_surface_id.as_deref());
                let client_app_id = json_string_option(surface.client_app_id.as_deref());
                let client_title = json_string_option(surface.client_title.as_deref());
                let panel_component = json_string_option(surface.panel_component.as_deref());
                let panel_id = json_string_option(surface.panel_id.as_deref());
                let panel_status = json_string_option(surface.panel_status.as_deref());
                let panel_tone = json_string_option(surface.panel_tone.as_deref());
                let panel_primary_action_id =
                    json_string_option(surface.panel_primary_action_id.as_deref());
                let panel_error = json_string_option(surface.panel_error.as_deref());
                format!(
                    "{{\"surface_id\":\"{}\",\"role\":\"{}\",\"host_interface\":\"{}\",\"state\":\"{}\",\"layout_zone\":\"{}\",\"layout_anchor\":\"{}\",\"layout_x\":{},\"layout_y\":{},\"layout_width\":{},\"layout_height\":{},\"stacking_layer\":\"{}\",\"z_index\":{},\"reservation_status\":\"{}\",\"pointer_policy\":\"{}\",\"focus_policy\":\"{}\",\"panel_host_status\":\"{}\",\"panel_component\":{},\"panel_id\":{},\"panel_status\":{},\"panel_tone\":{},\"panel_primary_action_id\":{},\"panel_action_count\":{},\"panel_section_count\":{},\"panel_error\":{},\"embedding_status\":\"{}\",\"embedded_surface_id\":{},\"client_app_id\":{},\"client_title\":{}}}",
                    json_escape(&surface.surface_id),
                    json_escape(&surface.role),
                    json_escape(&surface.host_interface),
                    json_escape(&surface.state),
                    json_escape(&surface.layout_zone),
                    json_escape(&surface.layout_anchor),
                    surface.layout_x,
                    surface.layout_y,
                    surface.layout_width,
                    surface.layout_height,
                    json_escape(&surface.stacking_layer),
                    surface.z_index,
                    json_escape(&surface.reservation_status),
                    json_escape(&surface.pointer_policy),
                    json_escape(&surface.focus_policy),
                    json_escape(&surface.panel_host_status),
                    panel_component,
                    panel_id,
                    panel_status,
                    panel_tone,
                    panel_primary_action_id,
                    surface.panel_action_count,
                    surface.panel_section_count,
                    panel_error,
                    json_escape(&surface.embedding_status),
                    embedded_surface_id,
                    client_app_id,
                    client_title
                )
            })
            .collect::<Vec<_>>()
            .join(",");

        format!(
            "{{\"service_id\":\"{}\",\"runtime\":\"{}\",\"desktop_host\":\"{}\",\"lifecycle_state\":\"{}\",\"started_at_ms\":{},\"process_id\":{},\"ticks\":{},\"socket_name\":{},\"seat_name\":{},\"pointer_status\":\"{}\",\"keyboard_status\":\"{}\",\"touch_status\":\"{}\",\"compositor_backend\":\"{}\",\"process_boundary_status\":\"{}\",\"runtime_lock_path\":{},\"runtime_ready_path\":{},\"runtime_state_path\":{},\"runtime_lock_status\":\"{}\",\"runtime_ready_status\":\"{}\",\"runtime_state_status\":\"{}\",\"session_control_status\":\"{}\",\"drm_device_path\":{},\"output_count\":{},\"connected_output_count\":{},\"primary_output_name\":{},\"panel_host_status\":\"{}\",\"panel_host_bound_count\":{},\"panel_host_activation_count\":{},\"panel_focus_status\":\"{}\",\"last_panel_host_slot_id\":{},\"last_panel_host_panel_id\":{},\"panel_action_status\":\"{}\",\"panel_action_dispatch_count\":{},\"last_panel_action_slot_id\":{},\"last_panel_action_panel_id\":{},\"last_panel_action_id\":{},\"last_panel_action_summary\":{},\"last_panel_action_target_component\":{},\"panel_action_event_count\":{},\"last_panel_action_event_id\":{},\"panel_action_log_status\":\"{}\",\"panel_action_log_path\":{},\"panel_action_events\":{},\"panel_snapshot_source\":{},\"panel_snapshot_profile_id\":{},\"panel_snapshot_surface_count\":{},\"panel_embedding_status\":\"{}\",\"embedded_surface_count\":{},\"stacking_status\":\"{}\",\"attention_surface_count\":{},\"active_modal_surface_id\":{},\"primary_attention_surface_id\":{},\"host_focus_status\":\"{}\",\"smithay_status\":\"{}\",\"renderer_backend\":\"{}\",\"renderer_status\":\"{}\",\"input_backend_status\":\"{}\",\"input_device_count\":{},\"input_event_count\":{},\"keyboard_event_count\":{},\"pointer_event_count\":{},\"touch_event_count\":{},\"last_input_event\":{},\"focused_surface_id\":{},\"topmost_surface_id\":{},\"last_hit_surface_id\":{},\"last_hit_slot_id\":{},\"last_pointer_x\":{},\"last_pointer_y\":{},\"rendered_frame_count\":{},\"client_count\":{},\"commit_count\":{},\"xdg_shell_status\":\"{}\",\"xdg_toplevel_count\":{},\"xdg_popup_count\":{},\"surface_count\":{},\"surfaces\":[{}]}}",
            json_escape(&self.service_id),
            json_escape(&self.runtime),
            json_escape(&self.desktop_host),
            json_escape(&self.lifecycle_state),
            self.started_at_ms,
            self.process_id,
            self.ticks,
            socket_name,
            seat_name,
            json_escape(&self.pointer_status),
            json_escape(&self.keyboard_status),
            json_escape(&self.touch_status),
            json_escape(&self.compositor_backend),
            json_escape(&self.process_boundary_status),
            runtime_lock_path,
            runtime_ready_path,
            runtime_state_path,
            json_escape(&self.runtime_lock_status),
            json_escape(&self.runtime_ready_status),
            json_escape(&self.runtime_state_status),
            json_escape(&self.session_control_status),
            drm_device_path,
            self.output_count,
            self.connected_output_count,
            primary_output_name,
            json_escape(&self.panel_host_status),
            self.panel_host_bound_count,
            self.panel_host_activation_count,
            json_escape(&self.panel_focus_status),
            last_panel_host_slot_id,
            last_panel_host_panel_id,
            json_escape(&self.panel_action_status),
            self.panel_action_dispatch_count,
            last_panel_action_slot_id,
            last_panel_action_panel_id,
            last_panel_action_id,
            last_panel_action_summary,
            last_panel_action_target_component,
            self.panel_action_event_count,
            last_panel_action_event_id,
            panel_action_log_status,
            panel_action_log_path,
            panel_action_events,
            panel_snapshot_source,
            panel_snapshot_profile_id,
            self.panel_snapshot_surface_count,
            json_escape(&self.panel_embedding_status),
            self.embedded_surface_count,
            json_escape(&self.stacking_status),
            self.attention_surface_count,
            active_modal_surface_id,
            primary_attention_surface_id,
            json_escape(&self.host_focus_status),
            json_escape(&self.smithay_status),
            json_escape(&self.renderer_backend),
            json_escape(&self.renderer_status),
            json_escape(&self.input_backend_status),
            self.input_device_count,
            self.input_event_count,
            self.keyboard_event_count,
            self.pointer_event_count,
            self.touch_event_count,
            last_input_event,
            focused_surface_id,
            topmost_surface_id,
            last_hit_surface_id,
            last_hit_slot_id,
            last_pointer_x,
            last_pointer_y,
            self.rendered_frame_count,
            self.client_count,
            self.commit_count,
            json_escape(&self.xdg_shell_status),
            self.xdg_toplevel_count,
            self.xdg_popup_count,
            self.surfaces.len(),
            surfaces
        )
    }
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn json_escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
}

fn json_string_option(value: Option<&str>) -> String {
    match value {
        Some(value) => format!("\"{}\"", json_escape(value)),
        None => "null".to_string(),
    }
}

fn json_number_option(value: Option<f64>) -> String {
    match value {
        Some(value) if value.is_finite() => format!("{value:.3}"),
        _ => "null".to_string(),
    }
}

impl SessionState {
    fn clear_panel_host_bindings(&mut self) {
        self.panel_host_bound_count = 0;
        self.panel_snapshot_source = None;
        self.panel_snapshot_profile_id = None;
        self.panel_snapshot_surface_count = 0;
        self.last_panel_action_target_component = None;
        for surface in &mut self.surfaces {
            surface.host_interface = format!("{}-placeholder", self.desktop_host);
            surface.reservation_status = if surface.embedded_surface_id.is_some() {
                "client-occupied".to_string()
            } else {
                "placeholder-only".to_string()
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
                surface.state = "placeholder-ready".to_string();
                surface.embedding_status = "placeholder-only".to_string();
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
                "placeholder-only".to_string()
            }
        } else if self.embedded_surface_count == self.surfaces.len() as u32 {
            format!(
                "ready({}/{})",
                self.embedded_surface_count,
                self.surfaces.len()
            )
        } else {
            format!(
                "partial({}/{})",
                self.embedded_surface_count,
                self.surfaces.len()
            )
        };
        self.refresh_surface_attention_state();
        if self.embedded_surface_count == 0 {
            self.topmost_surface_id = self
                .active_modal_surface_id
                .clone()
                .or_else(|| self.top_panel_surface_id());
            self.stacking_status = if let Some(surface_id) = self.topmost_surface_id.as_deref() {
                format!("panel-host-only({surface_id})")
            } else {
                "placeholder-only".to_string()
            };
        }
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

    fn top_panel_surface_id(&self) -> Option<String> {
        self.surfaces
            .iter()
            .filter(|surface| surface.panel_component.is_some())
            .max_by_key(|surface| surface.z_index)
            .map(|surface| surface.surface_id.clone())
    }

    fn refresh_surface_attention_state(&mut self) {
        let attention_surfaces = self
            .surfaces
            .iter()
            .filter(|surface| surface.panel_component.is_some() && is_attention_surface(surface))
            .collect::<Vec<_>>();

        self.attention_surface_count = attention_surfaces.len() as u32;
        self.active_modal_surface_id = self
            .surfaces
            .iter()
            .filter(|surface| {
                surface.panel_component.is_some() && is_modal_attention_surface(surface)
            })
            .max_by_key(|surface| modal_surface_priority(surface))
            .map(|surface| surface.surface_id.clone());
        self.primary_attention_surface_id = attention_surfaces
            .into_iter()
            .max_by_key(|surface| primary_attention_priority(surface))
            .map(|surface| surface.surface_id.clone());
    }
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
    matches!(
        surface.role.as_str(),
        "approval-slot" | "chooser-slot" | "recovery-slot"
    ) && is_attention_surface(surface)
}

fn is_passive_attention_surface(surface: &Surface) -> bool {
    surface.pointer_policy == "passthrough" || surface.focus_policy == "passive-overlay"
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
        assert!(summary.contains("\"panel_embedding_status\":\"placeholder-only\""));
        assert!(summary.contains("\"embedded_surface_count\":0"));
        assert!(summary.contains("\"stacking_status\":\"placeholder-only\""));
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
        assert!(summary.contains("\"surface_count\":9"));
        assert!(summary.contains("\"layout_zone\":\"left-dock\""));
        assert!(summary.contains("\"stacking_layer\":\"panel\""));
        assert!(summary.contains("\"z_index\":120"));
        assert!(summary.contains("\"reservation_status\":\"placeholder-only\""));
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
        assert!(summary.contains("\"embedding_status\":\"placeholder-only\""));
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
