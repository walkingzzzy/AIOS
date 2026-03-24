use crate::config::Config;
use crate::panel_snapshot::{
    load_panel_snapshot, load_panel_snapshot_from_command, load_panel_snapshot_from_socket,
};
use crate::session::{PanelActionEvent, SessionState};
use serde_json::{json, Value};
use std::error::Error;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub fn mode_label(config: &Config) -> String {
    mode::mode_label(config)
}

pub fn run(config: &Config, tick_target: Option<u32>) -> Result<SessionState, Box<dyn Error>> {
    mode::run(config, tick_target)
}

pub fn probe(config: &Config) -> Result<SessionState, Box<dyn Error>> {
    mode::probe(config)
}

fn refresh_panel_host_snapshot(session: &mut SessionState, config: &Config) {
    if !should_refresh_panel_snapshot(session, config) {
        return;
    }

    if let Some(socket_path) = config.panel_bridge_socket.as_deref() {
        match load_panel_snapshot_from_socket(Path::new(socket_path)) {
            Ok(snapshot) => {
                session.apply_panel_snapshot_from(&snapshot, "socket");
                return;
            }
            Err(socket_error) => {
                if let Some(command) = config.panel_snapshot_command.as_deref() {
                    match load_panel_snapshot_from_command(command) {
                        Ok(snapshot) => {
                            session.apply_panel_snapshot_from(&snapshot, "command-fallback");
                            return;
                        }
                        Err(command_error) => {
                            if let Some(path) = config.panel_snapshot_path.as_deref() {
                                match load_panel_snapshot(Path::new(path)) {
                                    Ok(snapshot) => {
                                        session
                                            .apply_panel_snapshot_from(&snapshot, "path-fallback");
                                        return;
                                    }
                                    Err(path_error) => {
                                        session.note_panel_host_error(format!(
                                            "socket-error:{socket_error};command-error:{command_error};path-error:{path_error}"
                                        ));
                                        return;
                                    }
                                }
                            }
                            session.note_panel_host_error(format!(
                                "socket-error:{socket_error};command-error:{command_error}"
                            ));
                            return;
                        }
                    }
                }
                if let Some(path) = config.panel_snapshot_path.as_deref() {
                    match load_panel_snapshot(Path::new(path)) {
                        Ok(snapshot) => {
                            session.apply_panel_snapshot_from(&snapshot, "path-fallback");
                            return;
                        }
                        Err(path_error) => {
                            session.note_panel_host_error(format!(
                                "socket-error:{socket_error};path-error:{path_error}"
                            ));
                            return;
                        }
                    }
                }
                session.note_panel_host_error(socket_error);
                return;
            }
        }
    }

    if let Some(command) = config.panel_snapshot_command.as_deref() {
        match load_panel_snapshot_from_command(command) {
            Ok(snapshot) => {
                session.apply_panel_snapshot_from(&snapshot, "command");
                return;
            }
            Err(command_error) => {
                if let Some(path) = config.panel_snapshot_path.as_deref() {
                    match load_panel_snapshot(Path::new(path)) {
                        Ok(snapshot) => {
                            session.apply_panel_snapshot_from(&snapshot, "path-fallback");
                            return;
                        }
                        Err(path_error) => {
                            session.note_panel_host_error(format!(
                                "command-error:{command_error};path-error:{path_error}"
                            ));
                            return;
                        }
                    }
                }
                session.note_panel_host_error(command_error);
                return;
            }
        }
    }

    let Some(path) = config.panel_snapshot_path.as_deref() else {
        session.set_panel_host_disabled();
        return;
    };
    match load_panel_snapshot(Path::new(path)) {
        Ok(snapshot) => session.apply_panel_snapshot_from(&snapshot, "path"),
        Err(error) => session.note_panel_host_error(error),
    }
}

fn should_refresh_panel_snapshot(session: &SessionState, config: &Config) -> bool {
    let refresh_ticks = config.panel_snapshot_refresh_ticks.max(1);
    session.ticks == 0 || session.ticks % refresh_ticks == 0
}

fn should_redirect_to_modal(active_modal_slot: Option<&str>, hit_slot: Option<&str>) -> bool {
    match active_modal_slot {
        Some(modal_slot) => hit_slot != Some(modal_slot),
        None => false,
    }
}

fn record_panel_action_event(
    session: &mut SessionState,
    log_path: Option<&str>,
    event: PanelActionEvent,
) {
    let recorded_event = session.record_panel_action_event(event);
    if let Some(path) = log_path {
        match append_panel_action_event(Path::new(path), &recorded_event) {
            Ok(()) => session.note_panel_action_log_status("ready"),
            Err(error) => {
                session.note_panel_action_log_status(format!("write-error:{error}"));
            }
        }
    } else {
        session.note_panel_action_log_status("memory-only");
    }
}

fn append_panel_action_event(path: &Path, event: &PanelActionEvent) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    let line = serde_json::to_string(event).map_err(|error| error.to_string())?;
    writeln!(file, "{line}").map_err(|error| error.to_string())
}

pub struct MultiOutputState {
    pub outputs: Vec<OutputDescriptor>,
    pub primary_output_index: usize,
    pub layout_mode: OutputLayoutMode,
}

pub struct OutputDescriptor {
    pub output_id: String,
    pub connector_name: String,
    pub width: u32,
    pub height: u32,
    pub refresh_rate_mhz: u32,
    pub renderable: bool,
    pub position_x: i32,
    pub position_y: i32,
}

#[derive(Debug, Clone, Copy)]
pub enum OutputLayoutMode {
    Horizontal,
    Vertical,
    Mirrored,
    Custom,
}

impl MultiOutputState {
    pub fn single(output_id: String, width: u32, height: u32) -> Self {
        Self {
            outputs: vec![OutputDescriptor {
                output_id,
                connector_name: "primary".to_string(),
                width,
                height,
                refresh_rate_mhz: 60_000,
                renderable: true,
                position_x: 0,
                position_y: 0,
            }],
            primary_output_index: 0,
            layout_mode: OutputLayoutMode::Horizontal,
        }
    }

    pub fn total_render_area(&self) -> (u32, u32) {
        match self.layout_mode {
            OutputLayoutMode::Horizontal => {
                let w: u32 = self.outputs.iter().filter(|o| o.renderable).map(|o| o.width).sum();
                let h = self.outputs.iter().filter(|o| o.renderable).map(|o| o.height).max().unwrap_or(0);
                (w, h)
            }
            OutputLayoutMode::Vertical => {
                let w = self.outputs.iter().filter(|o| o.renderable).map(|o| o.width).max().unwrap_or(0);
                let h: u32 = self.outputs.iter().filter(|o| o.renderable).map(|o| o.height).sum();
                (w, h)
            }
            OutputLayoutMode::Mirrored | OutputLayoutMode::Custom => {
                let w = self.outputs.iter().filter(|o| o.renderable).map(|o| o.width).max().unwrap_or(0);
                let h = self.outputs.iter().filter(|o| o.renderable).map(|o| o.height).max().unwrap_or(0);
                (w, h)
            }
        }
    }
}

#[derive(Clone, Debug)]
struct RuntimeArtifactPaths {
    lock_path: PathBuf,
    ready_path: PathBuf,
    state_path: PathBuf,
}

struct RuntimeArtifacts {
    paths: RuntimeArtifactPaths,
    ready_published: bool,
    state_refresh_ticks: u32,
}

impl RuntimeArtifacts {
    fn acquire(config: &Config, session: &mut SessionState) -> Result<Self, Box<dyn Error>> {
        let paths = runtime_artifact_paths(config);
        session.set_runtime_artifacts(
            Some(paths.lock_path.display().to_string()),
            Some(paths.ready_path.display().to_string()),
            Some(paths.state_path.display().to_string()),
        );
        let mut runtime = Self {
            paths,
            ready_published: false,
            state_refresh_ticks: config.runtime_state_refresh_ticks.max(1),
        };
        runtime.acquire_lock(session)?;
        runtime.publish_state(session, "starting", None)?;
        Ok(runtime)
    }

    fn publish_ready(&mut self, session: &mut SessionState) -> Result<(), Box<dyn Error>> {
        write_json_file(
            &self.paths.ready_path,
            &runtime_payload(session, "ready", None, &self.paths),
        )?;
        self.ready_published = true;
        session.set_runtime_ready_status("published");
        session.set_runtime_state_status("published(ready)");
        session.set_process_boundary_status(format!("frozen(owner-pid={})", session.process_id));
        self.publish_state(session, "ready", None)
    }

    fn publish_running(&mut self, session: &mut SessionState) -> Result<(), Box<dyn Error>> {
        if !self.ready_published {
            self.publish_ready(session)?;
            return Ok(());
        }
        if session.ticks == 0 || session.ticks % self.state_refresh_ticks == 0 {
            self.publish_state(session, "running", None)?;
        }
        Ok(())
    }

    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    fn publish_failure(
        &mut self,
        session: &mut SessionState,
        error: &str,
    ) -> Result<(), Box<dyn Error>> {
        session.lifecycle_state = "failed".to_string();
        session.set_runtime_ready_status("cleared");
        session.set_runtime_lock_status("released(error)");
        session.set_runtime_state_status("published(failed)");
        session.set_process_boundary_status(format!("released(error,pid={})", session.process_id));
        let _ = remove_file_if_exists(&self.paths.ready_path);
        self.publish_state(session, "failed", Some(error))?;
        let _ = remove_file_if_exists(&self.paths.lock_path);
        Ok(())
    }

    fn finish(mut self, session: &mut SessionState) -> Result<(), Box<dyn Error>> {
        match remove_file_if_exists(&self.paths.ready_path) {
            Ok(()) => session.set_runtime_ready_status("cleared"),
            Err(error) => session.set_runtime_ready_status(format!("clear-error:{error}")),
        }
        session.set_runtime_lock_status("released");
        session.set_runtime_state_status("published(stopped)");
        session.set_process_boundary_status(format!("released(pid={})", session.process_id));
        self.publish_state(session, "stopped", None)?;
        if let Err(error) = remove_file_if_exists(&self.paths.lock_path) {
            session.set_runtime_lock_status(format!("release-error:{error}"));
        }
        Ok(())
    }

    fn acquire_lock(&mut self, session: &mut SessionState) -> Result<(), Box<dyn Error>> {
        if let Some(parent) = self.paths.lock_path.parent() {
            fs::create_dir_all(parent)?;
        }
        loop {
            match OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&self.paths.lock_path)
            {
                Ok(mut file) => {
                    let payload = json!({
                        "schema": "aios.shell.compositor.lock/v1",
                        "service_id": session.service_id,
                        "pid": session.process_id,
                        "started_at_ms": session.started_at_ms,
                        "backend_mode": session.compositor_backend,
                    });
                    file.write_all(serde_json::to_string_pretty(&payload)?.as_bytes())?;
                    file.write_all(b"\n")?;
                    session.set_runtime_lock_status("held");
                    session.set_runtime_ready_status("pending");
                    session.set_runtime_state_status("publishing");
                    session.set_process_boundary_status(format!(
                        "frozen(owner-pid={})",
                        session.process_id
                    ));
                    return Ok(());
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    if remove_stale_lock_file(&self.paths.lock_path)? {
                        continue;
                    }
                    let owner = read_lock_owner_pid(&self.paths.lock_path)
                        .map(|pid| format!("pid={pid}"))
                        .unwrap_or_else(|| "pid=unknown".to_string());
                    session.set_runtime_lock_status(format!("contended({owner})"));
                    return Err(format!(
                        "compositor-runtime-lock-contended({owner}):{}",
                        self.paths.lock_path.display()
                    )
                    .into());
                }
                Err(error) => return Err(Box::new(error)),
            }
        }
    }

    fn publish_state(
        &mut self,
        session: &mut SessionState,
        phase: &str,
        error: Option<&str>,
    ) -> Result<(), Box<dyn Error>> {
        write_json_file(
            &self.paths.state_path,
            &runtime_payload(session, phase, error, &self.paths),
        )?;
        Ok(())
    }
}

fn runtime_artifact_paths(config: &Config) -> RuntimeArtifactPaths {
    let root = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::temp_dir().join("aios-shell-compositor-runtime"));
    let service_slug = sanitize_service_id(&config.service_id);
    RuntimeArtifactPaths {
        lock_path: config
            .runtime_lock_path
            .as_ref()
            .map(PathBuf::from)
            .unwrap_or_else(|| root.join(format!("{service_slug}.lock"))),
        ready_path: config
            .runtime_ready_path
            .as_ref()
            .map(PathBuf::from)
            .unwrap_or_else(|| root.join(format!("{service_slug}.ready.json"))),
        state_path: config
            .runtime_state_path
            .as_ref()
            .map(PathBuf::from)
            .unwrap_or_else(|| root.join(format!("{service_slug}.state.json"))),
    }
}

fn sanitize_service_id(service_id: &str) -> String {
    let normalized = service_id
        .chars()
        .map(|ch| match ch {
            'a'..='z' | 'A'..='Z' | '0'..='9' | '-' | '_' => ch,
            _ => '-',
        })
        .collect::<String>();
    if normalized.is_empty() {
        "aios-shell-compositor".to_string()
    } else {
        normalized
    }
}

fn runtime_payload(
    session: &SessionState,
    phase: &str,
    error: Option<&str>,
    paths: &RuntimeArtifactPaths,
) -> Value {
    let session_value =
        serde_json::from_str::<Value>(&session.json_summary()).unwrap_or_else(|_| json!({}));
    json!({
        "schema": "aios.shell.compositor.runtime/v1",
        "phase": phase,
        "updated_at_ms": runtime_now_ms(),
        "service_id": session.service_id,
        "pid": session.process_id,
        "backend_mode": session.compositor_backend,
        "process_boundary_status": session.process_boundary_status,
        "runtime_lock_status": session.runtime_lock_status,
        "runtime_ready_status": session.runtime_ready_status,
        "runtime_state_status": session.runtime_state_status,
        "paths": {
            "lock": paths.lock_path,
            "ready": paths.ready_path,
            "state": paths.state_path,
        },
        "error": error,
        "session": session_value,
    })
}

fn write_json_file(path: &Path, value: &Value) -> Result<(), Box<dyn Error>> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, serde_json::to_string_pretty(value)? + "\n")?;
    Ok(())
}

fn remove_file_if_exists(path: &Path) -> Result<(), String> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}

fn read_lock_owner_pid(path: &Path) -> Option<u32> {
    let contents = fs::read_to_string(path).ok()?;
    let payload = serde_json::from_str::<Value>(&contents).ok()?;
    payload
        .get("pid")
        .and_then(|value| value.as_u64())
        .and_then(|value| u32::try_from(value).ok())
}

fn remove_stale_lock_file(path: &Path) -> Result<bool, Box<dyn Error>> {
    let Some(owner_pid) = read_lock_owner_pid(path) else {
        return Ok(false);
    };
    if process_is_alive(owner_pid) {
        return Ok(false);
    }
    remove_file_if_exists(path)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::Other, error))?;
    Ok(true)
}

#[cfg(unix)]
fn process_is_alive(pid: u32) -> bool {
    let result = unsafe { libc::kill(pid as libc::pid_t, 0) };
    if result == 0 {
        return true;
    }
    match std::io::Error::last_os_error().raw_os_error() {
        Some(code) if code == libc::EPERM => true,
        Some(code) if code == libc::ESRCH => false,
        _ => false,
    }
}

#[cfg(not(unix))]
fn process_is_alive(_pid: u32) -> bool {
    false
}

fn runtime_now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[cfg(target_os = "linux")]
mod mode {
    use super::*;
    use crate::panel_snapshot::dispatch_panel_action_via_socket;
    use crate::session::{ManagedWindowSummary, OutputLayoutSummary, SessionState};
    use crate::surfaces::{
        match_panel_slot, placement_contains_point, placement_z_index, surface_contains_point,
        surface_placement, SurfacePlacement,
    };
    use serde::{Deserialize, Serialize};
    use smithay::backend::{
        allocator::{
            gbm::{GbmAllocator, GbmBufferFlags, GbmDevice},
            Format as DrmFormat, Fourcc as DrmFourcc,
        },
        drm::{
            compositor::{DrmCompositor, FrameFlags, PrimaryPlaneElement},
            exporter::gbm::GbmFramebufferExporter,
            DrmDevice, DrmDeviceFd, DrmDeviceNotifier, DrmEvent, DrmNode,
        },
        egl::{EGLContext, EGLDisplay},
        input::{
            AbsolutePositionEvent, Axis, ButtonState, Device as BackendDevice,
            Event as BackendEvent, InputBackend, InputEvent, KeyState, KeyboardKeyEvent,
            PointerAxisEvent, PointerButtonEvent as BackendPointerButtonEvent, TouchEvent,
        },
        libinput::{LibinputInputBackend, LibinputSessionInterface},
        renderer::{
            element::{
                surface::{render_elements_from_surface_tree, WaylandSurfaceRenderElement},
                Kind,
            },
            gles::GlesRenderer,
            ImportDma,
            utils::{draw_render_elements, on_commit_buffer_handler},
            Color32F, Frame, Renderer,
        },
        session::{
            libseat::{LibSeatSession, LibSeatSessionNotifier},
            Event as SessionEvent, Session,
        },
        udev::UdevBackend,
        winit::{self, WinitEvent},
    };
    use smithay::delegate_compositor;
    use smithay::delegate_seat;
    use smithay::delegate_shm;
    use smithay::delegate_xdg_shell;
    use smithay::input::{
        keyboard::{FilterResult, XkbConfig},
        pointer::{
            AxisFrame, ButtonEvent as PointerButtonEvent, CursorImageStatus,
            MotionEvent as PointerMotionEvent,
        },
        touch::{
            DownEvent as TouchDownEvent, MotionEvent as TouchMotionEvent, UpEvent as TouchUpEvent,
        },
        Seat, SeatHandler, SeatState,
    };
    use smithay::output::{
        Mode as OutputMode, Output, PhysicalProperties, Scale as OutputScale, Subpixel,
    };
    use smithay::reexports::calloop::EventLoop as CalloopEventLoop;
    use smithay::reexports::drm::control::{
        connector, crtc, Device as ControlDevice, Mode as ControlMode, ResourceHandles,
    };
    use smithay::reexports::input::Libinput;
    use smithay::reexports::wayland_protocols::xdg::shell::server::xdg_toplevel;
    use smithay::reexports::wayland_server::backend::{ClientData, ClientId, DisconnectReason};
    use smithay::reexports::wayland_server::protocol::wl_buffer::WlBuffer;
    use smithay::reexports::wayland_server::protocol::wl_surface::WlSurface;
    use smithay::reexports::wayland_server::{Client, Display, ListeningSocket, Resource};
    use smithay::reexports::winit::platform::pump_events::PumpStatus;
    use smithay::utils::Transform;
    use smithay::utils::{
        DeviceFd, Logical, Physical, Point, Rectangle, Serial, Size, SERIAL_COUNTER,
    };
    use smithay::wayland::buffer::BufferHandler;
    use smithay::wayland::compositor::{
        with_states, with_surface_tree_downward, CompositorClientState, CompositorHandler,
        CompositorState, SurfaceAttributes, TraversalAction,
    };
    use smithay::wayland::shell::xdg::{
        Configure, PopupSurface, PositionerState, ToplevelSurface, XdgShellHandler, XdgShellState,
        XdgToplevelSurfaceData,
    };
    use smithay::wayland::shm::{ShmHandler, ShmState};
    use std::any::Any;
    use std::cell::RefCell;
    use std::collections::BTreeSet;
    use std::env;
    use std::ffi::OsStr;
    use std::panic::{catch_unwind, AssertUnwindSafe};
    use std::path::PathBuf;
    use std::process::Command;
    use std::rc::Rc;
    use std::sync::Arc;
    use std::time::Instant;

    const MODE_LABEL_WINIT: &str = "smithay-wayland-frontend";
    const MODE_LABEL_DRM: &str = "smithay-drm-kms";
    const RENDERER_BACKEND_WINIT: &str = "winit-gles";
    const RENDERER_BACKEND_DRM: &str = "drm-kms-gbm-egl";

    const WINDOW_MOVE_GRAB_HEIGHT: i32 = 36;
    const WINDOW_RESIZE_BORDER: i32 = 12;
    const POINTER_BUTTON_RIGHT: u32 = 0x111;
    const POINTER_BUTTON_MIDDLE: u32 = 0x112;

    #[derive(Clone, Debug)]
    struct OutputSeed {
        output_id: String,
        connector_name: Option<String>,
        label: String,
        width: i32,
        height: i32,
        primary: bool,
        renderable: bool,
    }

    #[derive(Clone, Debug)]
    struct LogicalOutput {
        output_id: String,
        connector_name: Option<String>,
        label: String,
        frame: PersistedRect,
        primary: bool,
        renderable: bool,
    }

    #[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
    struct PersistedRect {
        x: i32,
        y: i32,
        width: i32,
        height: i32,
    }

    impl PersistedRect {
        fn clamp_to_bounds(&self, bounds: &PersistedRect, min_width: i32, min_height: i32) -> Self {
            let width = self.width.max(min_width).min(bounds.width.max(min_width));
            let height = self
                .height
                .max(min_height)
                .min(bounds.height.max(min_height));
            let max_x = bounds.x + bounds.width - width;
            let max_y = bounds.y + bounds.height - height;
            Self {
                x: self.x.clamp(bounds.x, max_x.max(bounds.x)),
                y: self.y.clamp(bounds.y, max_y.max(bounds.y)),
                width,
                height,
            }
        }
    }

    #[derive(Clone, Debug, Serialize, Deserialize)]
    struct PersistedWindowEntry {
        window_key: String,
        app_id: Option<String>,
        title: Option<String>,
        slot_id: Option<String>,
        output_id: Option<String>,
        workspace_index: u32,
        window_policy: String,
        rect: Option<PersistedRect>,
        #[serde(default)]
        minimized: bool,
        last_seen_at_ms: u128,
    }

    #[derive(Clone, Debug, Default, Serialize, Deserialize)]
    struct PersistedWindowManagerState {
        schema: String,
        active_workspace_index: u32,
        active_output_id: Option<String>,
        windows: Vec<PersistedWindowEntry>,
    }

    #[derive(Clone, Debug, PartialEq, Eq)]
    struct ResizeEdges {
        left: bool,
        right: bool,
        top: bool,
        bottom: bool,
    }

    #[derive(Clone, Debug)]
    enum PointerOperationKind {
        Move,
        Resize(ResizeEdges),
    }

    #[derive(Clone, Debug)]
    struct PointerOperation {
        window_key: String,
        pointer_origin: Point<f64, Logical>,
        initial_rect: PersistedRect,
        kind: PointerOperationKind,
        changed: bool,
    }

    #[derive(Clone, Debug)]
    struct ManagedWindowPlacement {
        window_key: String,
        surface_id: String,
        app_id: Option<String>,
        title: Option<String>,
        slot_id: Option<String>,
        output_id: String,
        workspace_index: u32,
        window_policy: String,
        floating: bool,
        visible: bool,
        minimized: bool,
        persisted: bool,
        interaction_state: String,
        placement: SurfacePlacement,
    }

    struct WindowManager {
        state_path: Option<PathBuf>,
        status: String,
        output_layout_mode: String,
        workspace_count: u32,
        active_workspace_index: u32,
        active_output_id: Option<String>,
        workspace_switch_count: u32,
        move_count: u32,
        resize_count: u32,
        minimize_count: u32,
        restore_count: u32,
        last_minimized_window_key: Option<String>,
        last_restored_window_key: Option<String>,
        outputs: Vec<LogicalOutput>,
        output_seeds: Vec<OutputSeed>,
        virtual_output_names: Vec<String>,
        render_all_outputs: bool,
        dirty: bool,
        pointer_operation: Option<PointerOperation>,
        state_last_modified: Option<SystemTime>,
        state_last_size: Option<u64>,
        persisted: PersistedWindowManagerState,
    }

    impl WindowManager {
        fn new(config: &Config) -> Self {
            let state_path = resolved_window_state_path(config);
            let mut manager = Self {
                state_path,
                status: "initializing".to_string(),
                output_layout_mode: config.output_layout_mode.clone(),
                workspace_count: config.workspace_count.max(1),
                active_workspace_index: config
                    .default_workspace_index
                    .min(config.workspace_count.max(1).saturating_sub(1)),
                active_output_id: None,
                workspace_switch_count: 0,
                move_count: 0,
                resize_count: 0,
                minimize_count: 0,
                restore_count: 0,
                last_minimized_window_key: None,
                last_restored_window_key: None,
                outputs: Vec::new(),
                output_seeds: Vec::new(),
                virtual_output_names: config.virtual_outputs.clone(),
                render_all_outputs: config.virtual_outputs.len() > 1,
                dirty: false,
                pointer_operation: None,
                state_last_modified: None,
                state_last_size: None,
                persisted: PersistedWindowManagerState::default(),
            };
            manager.load_state();
            manager
        }

        fn load_state(&mut self) {
            self.load_state_from_disk(false);
        }

        fn load_state_from_disk(&mut self, reloaded: bool) {
            let Some(path) = self.state_path.as_ref() else {
                self.state_last_modified = None;
                self.state_last_size = None;
                self.status = "ephemeral".to_string();
                return;
            };
            match fs::read_to_string(path) {
                Ok(contents) => {
                    self.observe_state_file();
                    match serde_json::from_str::<PersistedWindowManagerState>(&contents) {
                        Ok(state) => {
                            self.active_workspace_index = state
                                .active_workspace_index
                                .min(self.workspace_count.saturating_sub(1));
                            self.active_output_id = state.active_output_id.clone();
                            self.persisted = state;
                            self.status = format!(
                                "persistent({}={})",
                                if reloaded { "reloaded" } else { "loaded" },
                                self.persisted.windows.len()
                            );
                        }
                        Err(error) => {
                            self.persisted = PersistedWindowManagerState::default();
                            self.status = format!(
                                "persistent({}-error:{error})",
                                if reloaded { "reload" } else { "load" }
                            );
                        }
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    self.state_last_modified = None;
                    self.state_last_size = None;
                    self.persisted = PersistedWindowManagerState::default();
                    self.status = if reloaded {
                        "persistent(reload-empty)".to_string()
                    } else {
                        "persistent(empty)".to_string()
                    };
                }
                Err(error) => {
                    self.persisted = PersistedWindowManagerState::default();
                    self.status = format!(
                        "persistent({}-error:{error})",
                        if reloaded { "reload" } else { "load" }
                    );
                }
            }
        }

        fn observe_state_file(&mut self) {
            let Some(path) = self.state_path.as_ref() else {
                self.state_last_modified = None;
                self.state_last_size = None;
                return;
            };
            match fs::metadata(path) {
                Ok(metadata) => {
                    self.state_last_modified = metadata.modified().ok();
                    self.state_last_size = Some(metadata.len());
                }
                Err(_) => {
                    self.state_last_modified = None;
                    self.state_last_size = None;
                }
            }
        }

        fn reload_state_if_changed(&mut self) -> bool {
            let Some(path) = self.state_path.as_ref() else {
                return false;
            };
            let changed = match fs::metadata(path) {
                Ok(metadata) => {
                    let modified = metadata.modified().ok();
                    let size = Some(metadata.len());
                    self.state_last_modified != modified || self.state_last_size != size
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    self.state_last_modified.is_some() || self.state_last_size.is_some()
                }
                Err(error) => {
                    self.status = format!("persistent(reload-metadata-error:{error})");
                    return false;
                }
            };
            if !changed {
                return false;
            }
            self.load_state_from_disk(true);
            true
        }

        fn state_path_string(&self) -> Option<String> {
            self.state_path
                .as_ref()
                .map(|path| path.display().to_string())
        }

        fn set_output_seeds(&mut self, output_seeds: Vec<OutputSeed>) {
            self.output_seeds = output_seeds;
        }

        fn sync_outputs(&mut self, window_size: Size<i32, Physical>) {
            self.outputs = if self.virtual_output_names.len() > 1 {
                self.render_all_outputs = true;
                build_virtual_outputs(
                    &self.virtual_output_names,
                    PersistedRect {
                        x: 0,
                        y: 0,
                        width: window_size.w.max(1),
                        height: window_size.h.max(1),
                    },
                    &self.output_layout_mode,
                )
            } else if !self.output_seeds.is_empty() {
                self.render_all_outputs = false;
                build_outputs_from_seeds(&self.output_seeds, &self.output_layout_mode)
            } else {
                self.render_all_outputs = false;
                vec![LogicalOutput {
                    output_id: "display-1".to_string(),
                    connector_name: None,
                    label: "display-1".to_string(),
                    frame: PersistedRect {
                        x: 0,
                        y: 0,
                        width: window_size.w.max(1),
                        height: window_size.h.max(1),
                    },
                    primary: true,
                    renderable: true,
                }]
            };
            if self.outputs.is_empty() {
                self.outputs.push(LogicalOutput {
                    output_id: "display-1".to_string(),
                    connector_name: None,
                    label: "display-1".to_string(),
                    frame: PersistedRect {
                        x: 0,
                        y: 0,
                        width: window_size.w.max(1),
                        height: window_size.h.max(1),
                    },
                    primary: true,
                    renderable: true,
                });
            }
            if self.active_output_id.as_ref().map(|output_id| {
                self.outputs
                    .iter()
                    .any(|output| &output.output_id == output_id)
            }) != Some(true)
            {
                self.active_output_id = self
                    .outputs
                    .iter()
                    .find(|output| output.primary)
                    .map(|output| output.output_id.clone())
                    .or_else(|| self.outputs.first().map(|output| output.output_id.clone()));
            }
        }

        fn primary_output_id(&self) -> String {
            self.outputs
                .iter()
                .find(|output| output.primary)
                .or_else(|| self.outputs.first())
                .map(|output| output.output_id.clone())
                .unwrap_or_else(|| "display-1".to_string())
        }

        fn active_output_id(&self) -> Option<String> {
            self.active_output_id.clone()
        }

        fn cycle_workspace(&mut self, delta: i32) -> bool {
            if self.workspace_count <= 1 || delta == 0 {
                return false;
            }
            let workspace_count = self.workspace_count as i32;
            let next = (self.active_workspace_index as i32 + delta).rem_euclid(workspace_count);
            if next as u32 == self.active_workspace_index {
                return false;
            }
            self.active_workspace_index = next as u32;
            self.workspace_switch_count += 1;
            self.persisted.active_workspace_index = self.active_workspace_index;
            self.dirty = true;
            self.status = format!("workspace-switched({})", self.active_workspace_index + 1);
            let _ = self.save_if_dirty();
            true
        }

        fn cycle_output(&mut self, delta: i32) -> bool {
            if self.outputs.len() <= 1 || delta == 0 {
                return false;
            }
            let current_index = self
                .outputs
                .iter()
                .position(|output| {
                    Some(output.output_id.as_str()) == self.active_output_id.as_deref()
                })
                .unwrap_or(0);
            let next =
                (current_index as i32 + delta).rem_euclid(self.outputs.len() as i32) as usize;
            if next == current_index {
                return false;
            }
            self.active_output_id = Some(self.outputs[next].output_id.clone());
            self.persisted.active_output_id = self.active_output_id.clone();
            self.dirty = true;
            self.status = format!("output-switched({})", self.outputs[next].label);
            let _ = self.save_if_dirty();
            true
        }

        fn output_at_point(&self, pointer: Point<f64, Logical>) -> Option<LogicalOutput> {
            self.outputs
                .iter()
                .find(|output| {
                    pointer.x >= f64::from(output.frame.x)
                        && pointer.x <= f64::from(output.frame.x + output.frame.width)
                        && pointer.y >= f64::from(output.frame.y)
                        && pointer.y <= f64::from(output.frame.y + output.frame.height)
                })
                .cloned()
        }

        fn minimize_window(&mut self, window_key: &str) -> bool {
            let Some(entry) = self
                .persisted
                .windows
                .iter_mut()
                .find(|entry| entry.window_key == window_key)
            else {
                return false;
            };
            if entry.minimized {
                return false;
            }
            entry.minimized = true;
            self.minimize_count += 1;
            self.last_minimized_window_key = Some(window_key.to_string());
            self.dirty = true;
            self.status = format!("window-minimized({window_key})");
            let _ = self.save_if_dirty();
            true
        }

        fn restore_recent_window(&mut self) -> bool {
            let active_output = self.active_output_id.clone();
            let active_workspace_index = self.active_workspace_index;
            let entry_index = self
                .persisted
                .windows
                .iter()
                .rposition(|entry| {
                    entry.minimized
                        && entry.workspace_index == active_workspace_index
                        && (active_output.is_none()
                            || entry.output_id.as_ref() == active_output.as_ref()
                            || entry.output_id.is_none())
                })
                .or_else(|| {
                    self.persisted.windows.iter().rposition(|entry| {
                        entry.minimized && entry.workspace_index == active_workspace_index
                    })
                });
            let Some(entry_index) = entry_index else {
                return false;
            };
            let entry = &mut self.persisted.windows[entry_index];
            entry.minimized = false;
            entry.workspace_index = self.active_workspace_index;
            if let Some(active_output_id) = self.active_output_id.clone() {
                entry.output_id = Some(active_output_id);
            }
            entry.last_seen_at_ms = runtime_now_ms();
            self.restore_count += 1;
            self.last_restored_window_key = Some(entry.window_key.clone());
            self.dirty = true;
            self.status = format!("window-restored({})", entry.window_key);
            let _ = self.save_if_dirty();
            true
        }

        fn move_window_to_workspace_delta(&mut self, window_key: &str, delta: i32) -> bool {
            if self.workspace_count <= 1 || delta == 0 {
                return false;
            }
            let Some(entry) = self
                .persisted
                .windows
                .iter_mut()
                .find(|entry| entry.window_key == window_key)
            else {
                return false;
            };
            let workspace_count = self.workspace_count as i32;
            let next = (entry.workspace_index as i32 + delta).rem_euclid(workspace_count) as u32;
            if next == entry.workspace_index {
                return false;
            }
            entry.workspace_index = next;
            entry.last_seen_at_ms = runtime_now_ms();
            self.dirty = true;
            self.status = format!(
                "window-workspace-moved({window_key}->workspace-{})",
                next + 1
            );
            let _ = self.save_if_dirty();
            true
        }

        fn status_label(&self) -> String {
            self.status.clone()
        }

        fn drag_state_label(&self) -> String {
            match self.pointer_operation.as_ref() {
                Some(operation) if matches!(operation.kind, PointerOperationKind::Move) => {
                    format!("dragging({})", operation.window_key)
                }
                _ => "idle".to_string(),
            }
        }

        fn resize_state_label(&self) -> String {
            match self.pointer_operation.as_ref() {
                Some(operation) if matches!(operation.kind, PointerOperationKind::Resize(_)) => {
                    format!("resizing({})", operation.window_key)
                }
                _ => "idle".to_string(),
            }
        }

        fn output_summaries(&self) -> Vec<OutputLayoutSummary> {
            self.outputs
                .iter()
                .map(|output| OutputLayoutSummary {
                    output_id: output.output_id.clone(),
                    connector_name: output.connector_name.clone(),
                    label: output.label.clone(),
                    layout_x: output.frame.x,
                    layout_y: output.frame.y,
                    layout_width: output.frame.width,
                    layout_height: output.frame.height,
                    primary: output.primary,
                    active: Some(output.output_id.as_str()) == self.active_output_id.as_deref(),
                    renderable: output.renderable,
                })
                .collect()
        }

        fn managed_window_summaries(
            &self,
            placements: &[ManagedWindowPlacement],
        ) -> Vec<ManagedWindowSummary> {
            placements
                .iter()
                .map(|placement| ManagedWindowSummary {
                    window_key: placement.window_key.clone(),
                    surface_id: placement.surface_id.clone(),
                    app_id: placement.app_id.clone(),
                    title: placement.title.clone(),
                    slot_id: placement.slot_id.clone(),
                    output_id: placement.output_id.clone(),
                    workspace_id: format!("workspace-{}", placement.workspace_index + 1),
                    window_policy: placement.window_policy.clone(),
                    floating: placement.floating,
                    visible: placement.visible,
                    minimized: placement.minimized,
                    persisted: placement.persisted,
                    interaction_state: placement.interaction_state.clone(),
                    layout_x: placement.placement.x,
                    layout_y: placement.placement.y,
                    layout_width: placement.placement.width,
                    layout_height: placement.placement.height,
                })
                .collect()
        }

        fn place_window(
            &mut self,
            index: usize,
            metadata: &ToplevelMetadata,
            slot_id: Option<&str>,
            surface_id: String,
            window_policy: String,
        ) -> ManagedWindowPlacement {
            let window_key = managed_window_key(metadata, slot_id);
            let entry_index =
                self.ensure_window_entry(&window_key, metadata, slot_id, &window_policy);
            let floating = is_floating_window_policy(&window_policy);
            let default_output_id = self.default_output_id(slot_id, &window_policy);
            let mut output_id = self.persisted.windows[entry_index]
                .output_id
                .clone()
                .unwrap_or(default_output_id);
            if !self
                .outputs
                .iter()
                .any(|output| output.output_id == output_id)
            {
                output_id = self.primary_output_id();
                self.persisted.windows[entry_index].output_id = Some(output_id.clone());
                self.dirty = true;
            }
            let workspace_index = self.persisted.windows[entry_index]
                .workspace_index
                .min(self.workspace_count.saturating_sub(1));
            if workspace_index != self.persisted.windows[entry_index].workspace_index {
                self.persisted.windows[entry_index].workspace_index = workspace_index;
                self.dirty = true;
            }
            let output = self
                .outputs
                .iter()
                .find(|output| output.output_id == output_id)
                .cloned()
                .unwrap_or_else(|| self.outputs[0].clone());
            let minimized = self.persisted.windows[entry_index].minimized;
            let placement = if floating {
                let default_rect = placement_to_rect(&floating_window_placement_for_output(
                    index,
                    &output,
                    &window_policy,
                ));
                let rect = self.persisted.windows[entry_index]
                    .rect
                    .clone()
                    .unwrap_or(default_rect)
                    .clamp_to_bounds(&output.frame, 280, 180);
                if self.persisted.windows[entry_index].rect.as_ref() != Some(&rect) {
                    self.persisted.windows[entry_index].rect = Some(rect.clone());
                    self.dirty = true;
                }
                rect_to_placement(&rect, &window_policy)
            } else {
                placement_for_output(slot_id.unwrap_or("task-surface"), &output)
            };
            let interaction_state = match self.pointer_operation.as_ref() {
                Some(operation)
                    if operation.window_key == window_key
                        && matches!(operation.kind, PointerOperationKind::Move) =>
                {
                    "dragging".to_string()
                }
                Some(operation)
                    if operation.window_key == window_key
                        && matches!(operation.kind, PointerOperationKind::Resize(_)) =>
                {
                    "resizing".to_string()
                }
                _ if minimized => "minimized".to_string(),
                _ if floating => "floating".to_string(),
                _ => "tiled".to_string(),
            };
            ManagedWindowPlacement {
                window_key,
                surface_id,
                app_id: metadata.app_id.clone(),
                title: metadata.title.clone(),
                slot_id: slot_id.map(ToOwned::to_owned),
                output_id: output.output_id.clone(),
                workspace_index,
                window_policy,
                floating,
                visible: self.should_render_window(workspace_index, &output.output_id, minimized),
                minimized,
                persisted: self.state_path.is_some(),
                interaction_state,
                placement,
            }
        }

        fn begin_pointer_operation(
            &mut self,
            placement: &ToplevelPlacement,
            pointer: Point<f64, Logical>,
        ) -> bool {
            if !placement.visible || !is_floating_window_policy(&placement.window_policy) {
                return false;
            }
            let rect = placement_to_rect(&placement.placement);
            let kind = if let Some(edges) = detect_resize_edges(&placement.placement, pointer) {
                PointerOperationKind::Resize(edges)
            } else if is_move_grab_region(&placement.placement, pointer) {
                PointerOperationKind::Move
            } else {
                return false;
            };
            self.pointer_operation = Some(PointerOperation {
                window_key: placement.window_key.clone(),
                pointer_origin: pointer,
                initial_rect: rect,
                kind,
                changed: false,
            });
            self.status = match self.pointer_operation.as_ref().map(|item| &item.kind) {
                Some(PointerOperationKind::Move) => {
                    format!("drag-start({})", placement.window_key)
                }
                Some(PointerOperationKind::Resize(_)) => {
                    format!("resize-start({})", placement.window_key)
                }
                None => self.status.clone(),
            };
            true
        }

        fn update_pointer_operation(&mut self, pointer: Point<f64, Logical>) -> bool {
            let Some(operation) = self.pointer_operation.as_ref() else {
                return false;
            };
            let window_key = operation.window_key.clone();
            let initial_rect = operation.initial_rect.clone();
            let operation_kind = operation.kind.clone();
            let pointer_origin = operation.pointer_origin.clone();
            let Some(entry_index) = self
                .persisted
                .windows
                .iter()
                .position(|entry| entry.window_key == window_key)
            else {
                return false;
            };
            let primary_output_id = self.primary_output_id();
            let output_id = self.persisted.windows[entry_index]
                .output_id
                .clone()
                .unwrap_or(primary_output_id);
            let mut output = self
                .outputs
                .iter()
                .find(|output| output.output_id == output_id)
                .cloned()
                .unwrap_or_else(|| self.outputs[0].clone());
            let delta_x = (pointer.x - pointer_origin.x).round() as i32;
            let delta_y = (pointer.y - pointer_origin.y).round() as i32;
            let mut next_rect = initial_rect;
            let mut transferred_output: Option<LogicalOutput> = None;
            match &operation_kind {
                PointerOperationKind::Move => {
                    next_rect.x += delta_x;
                    next_rect.y += delta_y;
                    if let Some(target_output) = self.output_at_point(pointer) {
                        if target_output.output_id != output.output_id {
                            output = target_output.clone();
                            transferred_output = Some(target_output);
                        }
                    }
                }
                PointerOperationKind::Resize(edges) => {
                    if edges.left {
                        next_rect.x += delta_x;
                        next_rect.width -= delta_x;
                    }
                    if edges.right {
                        next_rect.width += delta_x;
                    }
                    if edges.top {
                        next_rect.y += delta_y;
                        next_rect.height -= delta_y;
                    }
                    if edges.bottom {
                        next_rect.height += delta_y;
                    }
                }
            }
            next_rect = next_rect.clamp_to_bounds(&output.frame, 280, 180);
            if let Some(target_output) = transferred_output.as_ref() {
                self.persisted.windows[entry_index].output_id =
                    Some(target_output.output_id.clone());
                self.active_output_id = Some(target_output.output_id.clone());
                self.persisted.active_output_id = self.active_output_id.clone();
                self.status = format!(
                    "dragging({}:output={})",
                    window_key, target_output.label
                );
                self.dirty = true;
            }
            if self.persisted.windows[entry_index].rect.as_ref() != Some(&next_rect) {
                self.persisted.windows[entry_index].rect = Some(next_rect);
                self.dirty = true;
                if let Some(operation) = self.pointer_operation.as_mut() {
                    operation.changed = true;
                }
                self.status = match &operation_kind {
                    PointerOperationKind::Move => {
                        format!("dragging({window_key})")
                    }
                    PointerOperationKind::Resize(_) => {
                        format!("resizing({window_key})")
                    }
                };
            }
            true
        }

        fn finish_pointer_operation(&mut self) -> bool {
            let Some(operation) = self.pointer_operation.take() else {
                return false;
            };
            if operation.changed {
                match operation.kind {
                    PointerOperationKind::Move => self.move_count += 1,
                    PointerOperationKind::Resize(_) => self.resize_count += 1,
                }
                let _ = self.save_if_dirty();
            }
            self.status = match operation.kind {
                PointerOperationKind::Move => format!("drag-complete({})", operation.window_key),
                PointerOperationKind::Resize(_) => {
                    format!("resize-complete({})", operation.window_key)
                }
            };
            operation.changed
        }

        fn save_if_dirty(&mut self) -> Result<(), String> {
            if !self.dirty {
                return Ok(());
            }
            let Some(path) = self.state_path.as_ref() else {
                self.status = "ephemeral".to_string();
                self.dirty = false;
                return Ok(());
            };
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).map_err(|error| error.to_string())?;
            }
            self.persisted.schema = "aios.shell.compositor.window-state/v1".to_string();
            self.persisted.active_workspace_index = self.active_workspace_index;
            self.persisted.active_output_id = self.active_output_id.clone();
            fs::write(
                path,
                serde_json::to_string_pretty(&self.persisted).map_err(|error| error.to_string())?
                    + "
",
            )
            .map_err(|error| error.to_string())?;
            self.observe_state_file();
            self.status = format!("persistent(saved={})", self.persisted.windows.len());
            self.dirty = false;
            Ok(())
        }

        fn should_render_window(
            &self,
            workspace_index: u32,
            output_id: &str,
            minimized: bool,
        ) -> bool {
            !minimized
                && workspace_index == self.active_workspace_index
                && (self.render_all_outputs
                    || Some(output_id) == self.active_output_id.as_deref()
                    || self.outputs.iter().all(|output| !output.renderable))
        }

        fn default_output_id(&self, slot_id: Option<&str>, window_policy: &str) -> String {
            if slot_id == Some("task-surface") || is_floating_window_policy(window_policy) {
                self.active_output_id
                    .clone()
                    .unwrap_or_else(|| self.primary_output_id())
            } else {
                self.primary_output_id()
            }
        }

        fn ensure_window_entry(
            &mut self,
            window_key: &str,
            metadata: &ToplevelMetadata,
            slot_id: Option<&str>,
            window_policy: &str,
        ) -> usize {
            if let Some(index) = self
                .persisted
                .windows
                .iter()
                .position(|entry| entry.window_key == window_key)
            {
                let entry = &mut self.persisted.windows[index];
                entry.app_id = metadata.app_id.clone();
                entry.title = metadata.title.clone();
                entry.slot_id = slot_id.map(ToOwned::to_owned);
                entry.window_policy = window_policy.to_string();
                entry.last_seen_at_ms = runtime_now_ms();
                return index;
            }
            self.persisted.windows.push(PersistedWindowEntry {
                window_key: window_key.to_string(),
                app_id: metadata.app_id.clone(),
                title: metadata.title.clone(),
                slot_id: slot_id.map(ToOwned::to_owned),
                output_id: None,
                workspace_index: self.active_workspace_index,
                window_policy: window_policy.to_string(),
                rect: None,
                minimized: false,
                last_seen_at_ms: runtime_now_ms(),
            });
            self.dirty = true;
            self.persisted.windows.len() - 1
        }
    }

    fn resolved_window_state_path(config: &Config) -> Option<PathBuf> {
        config
            .window_state_path
            .as_ref()
            .map(PathBuf::from)
            .or_else(|| {
                config.runtime_state_path.as_ref().map(|value| {
                    let mut path = PathBuf::from(value);
                    if let Some(stem) = path
                        .file_stem()
                        .map(|stem| stem.to_string_lossy().into_owned())
                    {
                        path.set_file_name(format!("{stem}.windows.json"));
                    } else {
                        path.push("windows.json");
                    }
                    path
                })
            })
    }

    fn build_virtual_outputs(
        output_names: &[String],
        frame: PersistedRect,
        layout_mode: &str,
    ) -> Vec<LogicalOutput> {
        let count = output_names.len().max(1) as i32;
        output_names
            .iter()
            .enumerate()
            .map(|(index, name)| {
                let index = index as i32;
                let output_frame = match layout_mode {
                    "vertical" => {
                        let height = (frame.height / count).max(1);
                        let y = frame.y + height * index;
                        let bottom = if index == count - 1 {
                            frame.y + frame.height
                        } else {
                            y + height
                        };
                        PersistedRect {
                            x: frame.x,
                            y,
                            width: frame.width,
                            height: (bottom - y).max(1),
                        }
                    }
                    "mirrored" => frame.clone(),
                    _ => {
                        let width = (frame.width / count).max(1);
                        let x = frame.x + width * index;
                        let right = if index == count - 1 {
                            frame.x + frame.width
                        } else {
                            x + width
                        };
                        PersistedRect {
                            x,
                            y: frame.y,
                            width: (right - x).max(1),
                            height: frame.height,
                        }
                    }
                };
                LogicalOutput {
                    output_id: format!("virtual-output-{}", index + 1),
                    connector_name: Some(name.clone()),
                    label: name.clone(),
                    frame: output_frame,
                    primary: index == 0,
                    renderable: true,
                }
            })
            .collect()
    }

    fn build_outputs_from_seeds(seeds: &[OutputSeed], layout_mode: &str) -> Vec<LogicalOutput> {
        let mut cursor_x = 0;
        let mut cursor_y = 0;
        seeds
            .iter()
            .enumerate()
            .map(|(index, seed)| {
                let frame = match layout_mode {
                    "vertical" => {
                        let frame = PersistedRect {
                            x: 0,
                            y: cursor_y,
                            width: seed.width.max(1),
                            height: seed.height.max(1),
                        };
                        cursor_y += seed.height.max(1);
                        frame
                    }
                    "mirrored" => PersistedRect {
                        x: 0,
                        y: 0,
                        width: seed.width.max(1),
                        height: seed.height.max(1),
                    },
                    _ => {
                        let frame = PersistedRect {
                            x: cursor_x,
                            y: 0,
                            width: seed.width.max(1),
                            height: seed.height.max(1),
                        };
                        cursor_x += seed.width.max(1);
                        frame
                    }
                };
                LogicalOutput {
                    output_id: seed.output_id.clone(),
                    connector_name: seed.connector_name.clone(),
                    label: seed.label.clone(),
                    frame,
                    primary: seed.primary || index == 0,
                    renderable: seed.renderable,
                }
            })
            .collect()
    }

    fn managed_window_key(metadata: &ToplevelMetadata, slot_id: Option<&str>) -> String {
        let raw = format!(
            "{}|{}|{}",
            metadata.app_id.as_deref().unwrap_or_default(),
            metadata.title.as_deref().unwrap_or_default(),
            slot_id.unwrap_or_default()
        );
        let sanitized = raw
            .chars()
            .map(|character| {
                if character.is_ascii_alphanumeric() {
                    character.to_ascii_lowercase()
                } else {
                    '-'
                }
            })
            .collect::<String>();
        if sanitized.trim_matches('-').is_empty() {
            "window-anonymous".to_string()
        } else {
            sanitized
                .split('-')
                .filter(|segment| !segment.is_empty())
                .collect::<Vec<_>>()
                .join("-")
        }
    }

    fn is_floating_window_policy(window_policy: &str) -> bool {
        matches!(
            window_policy,
            "floating-dialog" | "floating-utility" | "floating-workspace"
        )
    }

    fn is_minimizable_window_policy(window_policy: &str) -> bool {
        is_floating_window_policy(window_policy) || window_policy.starts_with("workspace-")
    }

    fn placement_for_output(slot_id: &str, output: &LogicalOutput) -> SurfacePlacement {
        let mut placement = surface_placement(slot_id, output.frame.width, output.frame.height);
        placement.x += output.frame.x;
        placement.y += output.frame.y;
        placement
    }

    fn floating_window_placement_for_output(
        index: usize,
        output: &LogicalOutput,
        window_policy: &str,
    ) -> SurfacePlacement {
        let size = Size::from((output.frame.width, output.frame.height));
        let mut placement = floating_window_placement(index, size, window_policy);
        placement.x += output.frame.x;
        placement.y += output.frame.y;
        placement
    }

    fn placement_to_rect(placement: &SurfacePlacement) -> PersistedRect {
        PersistedRect {
            x: placement.x,
            y: placement.y,
            width: placement.width,
            height: placement.height,
        }
    }

    fn rect_to_placement(rect: &PersistedRect, window_policy: &str) -> SurfacePlacement {
        SurfacePlacement {
            zone: if window_policy == "floating-dialog" {
                "center-modal"
            } else if window_policy == "floating-utility" {
                "right-rail"
            } else {
                "floating-stack"
            },
            anchor: if window_policy == "floating-dialog" {
                "center"
            } else if window_policy == "floating-utility" {
                "top-right"
            } else {
                "top-left"
            },
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
        }
    }

    fn detect_resize_edges(
        placement: &SurfacePlacement,
        pointer: Point<f64, Logical>,
    ) -> Option<ResizeEdges> {
        let left = pointer.x <= f64::from(placement.x + WINDOW_RESIZE_BORDER);
        let right = pointer.x >= f64::from(placement.x + placement.width - WINDOW_RESIZE_BORDER);
        let top = pointer.y <= f64::from(placement.y + WINDOW_RESIZE_BORDER);
        let bottom = pointer.y >= f64::from(placement.y + placement.height - WINDOW_RESIZE_BORDER);
        if left || right || top || bottom {
            Some(ResizeEdges {
                left,
                right,
                top,
                bottom,
            })
        } else {
            None
        }
    }

    fn is_move_grab_region(placement: &SurfacePlacement, pointer: Point<f64, Logical>) -> bool {
        pointer.y <= f64::from(placement.y + WINDOW_MOVE_GRAB_HEIGHT)
            && pointer.x >= f64::from(placement.x)
            && pointer.x <= f64::from(placement.x + placement.width)
    }

    pub fn mode_label(config: &Config) -> String {
        match normalized_compositor_backend(config) {
            "drm-kms" => MODE_LABEL_DRM.to_string(),
            _ => MODE_LABEL_WINIT.to_string(),
        }
    }

    pub fn run(config: &Config, tick_target: Option<u32>) -> Result<SessionState, Box<dyn Error>> {
        match normalized_compositor_backend(config) {
            "drm-kms" => run_drm_kms(config, tick_target),
            _ => run_nested_winit(config, tick_target),
        }
    }

    pub fn probe(config: &Config) -> Result<SessionState, Box<dyn Error>> {
        match normalized_compositor_backend(config) {
            "drm-kms" => probe_drm_kms(config),
            _ => probe_nested_winit(config),
        }
    }

    fn run_nested_winit(
        config: &Config,
        tick_target: Option<u32>,
    ) -> Result<SessionState, Box<dyn Error>> {
        let mut display: Display<App> = Display::new()?;
        let dh = display.handle();
        let compositor_state = CompositorState::new::<App>(&dh);
        let xdg_shell_state = XdgShellState::new::<App>(&dh);
        let shm_state = ShmState::new::<App>(&dh, vec![]);
        let mut seat_state = SeatState::new();
        let mut seat = seat_state.new_wl_seat(&dh, &config.seat_name);
        let mut session = SessionState::new(config);
        session.set_seat_name(Some(config.seat_name.clone()));
        if config.pointer_enabled {
            let _ = seat.add_pointer();
            session.set_pointer_status("enabled");
        } else {
            session.set_pointer_status("disabled");
        }
        if config.keyboard_enabled {
            match seat.add_keyboard(
                XkbConfig {
                    layout: config.keyboard_layout.as_str(),
                    ..XkbConfig::default()
                },
                config.keyboard_repeat_delay_ms,
                config.keyboard_repeat_rate,
            ) {
                Ok(_) => session
                    .set_keyboard_status(format!("enabled(layout={})", config.keyboard_layout)),
                Err(error) => session.set_keyboard_status(format!(
                    "init-failed(layout={}):{error}",
                    config.keyboard_layout
                )),
            }
        } else {
            session.set_keyboard_status("disabled");
        }
        if config.touch_enabled {
            let _ = seat.add_touch();
            session.set_touch_status("enabled");
        } else {
            session.set_touch_status("disabled");
        }
        session.set_input_backend_status("active(winit)");
        let window_manager = WindowManager::new(config);
        session.set_window_state_path(window_manager.state_path_string());
        let mut state = App {
            compositor_state,
            xdg_shell_state,
            shm_state,
            seat_state,
            seat,
            panel_action_command: config.panel_action_command.clone(),
            panel_bridge_socket: config.panel_bridge_socket.clone(),
            panel_action_log_path: config.panel_action_log_path.clone(),
            session,
            window_manager,
            last_toplevel_placements: Vec::new(),
        };

        let owned_runtime_dir = ensure_runtime_dir()?;
        let listener = if let Some(socket_name) = config.socket_name.as_deref() {
            ListeningSocket::bind(socket_name)?
        } else {
            ListeningSocket::bind_auto("wayland", 1..33)?
        };
        state
            .session
            .set_socket_name(listener.socket_name().map(os_str_to_string));
        state.session.set_smithay_status(MODE_LABEL_WINIT);
        state.session.set_renderer_backend(RENDERER_BACKEND_WINIT);
        state.session.set_session_control_status("nested-active");
        state.session.set_xdg_shell_status("registered");
        let mut runtime = RuntimeArtifacts::acquire(config, &mut state.session)?;
        let mut renderer = match NestedRenderer::try_new() {
            Ok(renderer) => {
                state.session.set_renderer_status("active");
                Some(renderer)
            }
            Err(reason) => {
                state
                    .session
                    .set_renderer_status(format!("winit-init-failed:{reason}"));
                None
            }
        };
        let initial_window_size = renderer
            .as_ref()
            .map(|renderer| renderer.backend.window_size())
            .unwrap_or_else(|| Size::from((1280, 800)));
        state.window_manager.sync_outputs(initial_window_size);
        state.sync_window_manager_session(&[]);

        runtime.publish_ready(&mut state.session)?;
        let run_result = (|| -> Result<(), Box<dyn Error>> {
            while tick_target
                .map(|target| state.session.ticks < target)
                .unwrap_or(true)
            {
                refresh_panel_host_snapshot(&mut state.session, config);
                let mut release_renderer = false;
                if let Some(active_renderer) = renderer.as_mut() {
                    if active_renderer.dispatch_new_events(&mut state) {
                        state.session.set_renderer_status("winit-exit-requested");
                        release_renderer = true;
                    }
                }

                while let Some(stream) = listener.accept()? {
                    display
                        .handle()
                        .insert_client(stream, Arc::new(ClientState::default()))?;
                    state.session.note_client_connected();
                }

                display.dispatch_clients(&mut state)?;
                state.sync_runtime_metrics();

                if !release_renderer {
                    if let Some(active_renderer) = renderer.as_mut() {
                        match active_renderer.render(&mut state) {
                            Ok(frame_count) => {
                                for _ in 0..frame_count {
                                    state.session.note_rendered_frame();
                                }
                            }
                            Err(reason) => {
                                state
                                    .session
                                    .set_renderer_status(format!("render-failed:{reason}"));
                                release_renderer = true;
                            }
                        }
                    }
                }

                if release_renderer {
                    renderer = None;
                }

                display.flush_clients()?;
                state.session.tick();
                runtime.publish_running(&mut state.session)?;
                thread::sleep(Duration::from_millis(config.tick_ms));
            }
            Ok(())
        })();

        if let Err(error) = run_result {
            let _ = runtime.publish_failure(&mut state.session, &error.to_string());
            drop(listener);
            drop(display);
            cleanup_runtime_dir(owned_runtime_dir);
            return Err(error);
        }

        state.session.finish();
        runtime.finish(&mut state.session)?;
        drop(listener);
        drop(display);
        cleanup_runtime_dir(owned_runtime_dir);
        Ok(state.session)
    }

    fn normalized_compositor_backend(config: &Config) -> &str {
        match config
            .compositor_backend
            .trim()
            .to_ascii_lowercase()
            .as_str()
        {
            "drm" | "drm-kms" | "kms" | "udev-drm" | "libseat-drm" => "drm-kms",
            _ => "winit",
        }
    }

    #[derive(Clone, Debug)]
    struct DrmProbe {
        output_count: u32,
        connected_output_count: u32,
        active_output_count: u32,
        primary_output_name: Option<String>,
        primary_output_size: Option<Size<i32, Physical>>,
        outputs: Vec<OutputSeed>,
        atomic_modesetting: bool,
        plane_count: u32,
    }

    #[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
    struct DrmRenderTriggers {
        commit_count: u32,
        input_event_count: u32,
        client_count: u32,
        xdg_toplevel_count: u32,
        xdg_popup_count: u32,
        panel_host_bound_count: u32,
        panel_action_event_count: u32,
        panel_snapshot_surface_count: u32,
        embedded_surface_count: u32,
    }

    impl DrmRenderTriggers {
        fn capture(session: &SessionState) -> Self {
            Self {
                commit_count: session.commit_count,
                input_event_count: session.input_event_count,
                client_count: session.client_count,
                xdg_toplevel_count: session.xdg_toplevel_count,
                xdg_popup_count: session.xdg_popup_count,
                panel_host_bound_count: session.panel_host_bound_count,
                panel_action_event_count: session.panel_action_event_count,
                panel_snapshot_surface_count: session.panel_snapshot_surface_count,
                embedded_surface_count: session.embedded_surface_count,
            }
        }
    }

    #[derive(Clone, Debug)]
    struct DrmSelectedOutput {
        connector: connector::Handle,
        connector_name: String,
        physical_size_mm: (i32, i32),
        subpixel: Subpixel,
        crtc: crtc::Handle,
        mode: ControlMode,
        output_mode: OutputMode,
        output_size: Size<i32, Physical>,
    }

    type DrmAllocator = GbmAllocator<DrmDeviceFd>;
    type DrmExporter = GbmFramebufferExporter<DrmDeviceFd>;
    type DrmPresentationCompositor = DrmCompositor<DrmAllocator, DrmExporter, (), DrmDeviceFd>;

    struct DrmDeviceContext {
        drm_node: DrmNode,
        drm_probe: DrmProbe,
        drm_device: DrmDevice,
        drm_notifier: DrmDeviceNotifier,
        gbm: GbmDevice<DrmDeviceFd>,
        renderer: GlesRenderer,
        selected_output: DrmSelectedOutput,
    }

    struct DrmPresentationRuntime {
        drm_device: DrmDevice,
        compositor: DrmPresentationCompositor,
        renderer: GlesRenderer,
        _output: Output,
        output_name: String,
        crtc: crtc::Handle,
        output_size: Size<i32, Physical>,
        refresh_millihz: i32,
        start_time: Instant,
        pageflip_pending: bool,
        needs_redraw: bool,
        last_observed_triggers: DrmRenderTriggers,
        last_presented_triggers: DrmRenderTriggers,
    }

    struct DrmRuntime {
        output_size: Size<i32, Physical>,
        output_seeds: Vec<OutputSeed>,
        drm_notifier: DrmDeviceNotifier,
        presentation: Rc<RefCell<DrmPresentationRuntime>>,
    }

    fn initialize_libseat_session(
        session: &mut SessionState,
    ) -> Result<(LibSeatSession, LibSeatSessionNotifier), String> {
        session.set_session_control_status("initializing");
        let (libseat_session, session_notifier) =
            LibSeatSession::new().map_err(|error| format!("libseat-init-failed:{error}"))?;
        session.set_session_control_status(if libseat_session.is_active() {
            "active(libseat)"
        } else {
            "inactive(libseat)"
        });
        Ok((libseat_session, session_notifier))
    }

    fn select_primary_drm_output(
        device: &DrmDevice,
        config: &Config,
    ) -> Result<DrmSelectedOutput, String> {
        let resources = device
            .resource_handles()
            .map_err(|error| format!("drm-resources-unavailable:{error}"))?;
        let mut best_candidate: Option<((i32, i32, i32, i32, i32), DrmSelectedOutput)> = None;

        for connector_handle in resources.connectors() {
            let info = device
                .get_connector(*connector_handle, true)
                .map_err(|error| format!("drm-connector-query-failed:{error}"))?;
            if info.state() != connector::State::Connected {
                continue;
            }
            let Some(crtc) = select_crtc_for_connector(device, &resources, &info, &[]) else {
                continue;
            };
            let connector_name = format!("{:?}-{}", info.interface(), info.interface_id());
            let Some((mode, output_mode, output_size, mode_rank)) =
                select_connector_mode(&info, config)
            else {
                continue;
            };
            let physical_size_mm = info
                .size()
                .map(|(w, h)| (i32::try_from(w).unwrap_or(0), i32::try_from(h).unwrap_or(0)))
                .unwrap_or((0, 0));
            let candidate = DrmSelectedOutput {
                connector: *connector_handle,
                connector_name: connector_name.clone(),
                physical_size_mm,
                subpixel: info.subpixel().into(),
                crtc,
                mode,
                output_mode,
                output_size,
            };
            let rank = (
                connector_preference_rank(
                    &connector_name,
                    config.drm_preferred_connector.as_deref(),
                ),
                mode_rank.0,
                mode_rank.1,
                mode_rank.2,
                mode_rank.3,
            );
            match &best_candidate {
                Some((best_rank, _)) if *best_rank <= rank => {}
                _ => best_candidate = Some((rank, candidate)),
            }
        }

        best_candidate
            .map(|(_, candidate)| candidate)
            .ok_or_else(|| "drm-output-not-available".to_string())
    }

    fn create_drm_output(selected_output: &DrmSelectedOutput) -> Output {
        let output = Output::new(
            selected_output.connector_name.clone(),
            PhysicalProperties {
                size: Size::from(selected_output.physical_size_mm),
                subpixel: selected_output.subpixel,
                make: "AIOS".to_string(),
                model: selected_output.connector_name.clone(),
            },
        );
        output.change_current_state(
            Some(selected_output.output_mode),
            Some(Transform::Normal),
            Some(OutputScale::Integer(1)),
            Some((0, 0).into()),
        );
        output.set_preferred(selected_output.output_mode);
        output.add_mode(selected_output.output_mode);
        output
    }

    fn initialize_drm_device_context(
        config: &Config,
        libseat_session: &mut LibSeatSession,
        session: &mut SessionState,
    ) -> Result<DrmDeviceContext, String> {
        let udev = UdevBackend::new(&config.seat_name)
            .map_err(|error| format!("udev-init-failed:{error}"))?;
        let drm_path = config
            .drm_device_path
            .as_ref()
            .map(PathBuf::from)
            .or_else(|| select_drm_device_path(&udev))
            .ok_or_else(|| "drm-device-not-found".to_string())?;
        let drm_node = DrmNode::from_path(&drm_path)
            .map_err(|error| format!("drm-node-invalid({}):{error}", drm_path.display()))?;
        let opened_fd = libseat_session
            .open(
                drm_path.as_path(),
                smithay::reexports::rustix::fs::OFlags::RDWR
                    | smithay::reexports::rustix::fs::OFlags::CLOEXEC
                    | smithay::reexports::rustix::fs::OFlags::NOCTTY,
            )
            .map_err(|error| format!("drm-open-failed({}):{error:?}", drm_path.display()))?;
        let drm_device_fd = DrmDeviceFd::new(DeviceFd::from(opened_fd));
        let (drm_device, drm_notifier) =
            DrmDevice::new(drm_device_fd.clone(), config.drm_disable_connectors).map_err(
                |error| format!("drm-device-init-failed({}):{error}", drm_path.display()),
            )?;
        let drm_probe = probe_drm_outputs(&drm_device)?;
        let selected_output = select_primary_drm_output(&drm_device, config)?;
        session.set_drm_topology(
            Some(drm_path.display().to_string()),
            Some(selected_output.connector_name.clone()),
            Some(selected_output.output_size.w),
            Some(selected_output.output_size.h),
            Some(selected_output.output_mode.refresh),
            drm_probe.output_count,
            drm_probe.connected_output_count,
            drm_probe.primary_output_name.clone(),
        );

        let gbm = GbmDevice::new(drm_device_fd.clone())
            .map_err(|error| format!("gbm-init-failed:{error}"))?;
        let egl_display = unsafe { EGLDisplay::new(gbm.clone()) }
            .map_err(|error| format!("egl-display-init-failed:{error}"))?;
        let egl_context = EGLContext::new(&egl_display)
            .map_err(|error| format!("egl-context-init-failed:{error}"))?;
        let renderer = unsafe { GlesRenderer::new(egl_context) }
            .map_err(|error| format!("gles-renderer-init-failed:{error}"))?;
        session.set_renderer_status(format!(
            "active(node={drm_node:?},outputs={},connected={},active={},atomic={},planes={},scanout=preparing,output={})",
            drm_probe.output_count,
            drm_probe.connected_output_count,
            drm_probe.active_output_count,
            drm_probe.atomic_modesetting,
            drm_probe.plane_count,
            selected_output.connector_name
        ));

        Ok(DrmDeviceContext {
            drm_node,
            drm_probe,
            drm_device,
            drm_notifier,
            gbm,
            renderer,
            selected_output,
        })
    }

    impl DrmPresentationRuntime {
        fn new(
            drm_device: DrmDevice,
            compositor: DrmPresentationCompositor,
            renderer: GlesRenderer,
            output: Output,
            selected_output: &DrmSelectedOutput,
        ) -> Self {
            Self {
                drm_device,
                compositor,
                renderer,
                _output: output,
                output_name: selected_output.connector_name.clone(),
                crtc: selected_output.crtc,
                output_size: selected_output.output_size,
                refresh_millihz: selected_output.output_mode.refresh,
                start_time: Instant::now(),
                pageflip_pending: false,
                needs_redraw: true,
                last_observed_triggers: DrmRenderTriggers::default(),
                last_presented_triggers: DrmRenderTriggers::default(),
            }
        }

        fn observe_changes(&mut self, session: &SessionState) -> DrmRenderTriggers {
            let triggers = DrmRenderTriggers::capture(session);
            if triggers != self.last_observed_triggers {
                self.last_observed_triggers = triggers;
                self.needs_redraw = true;
            }
            triggers
        }

        fn render_if_needed(
            &mut self,
            app: &mut App,
            placements: &[ToplevelPlacement],
        ) -> Result<u32, String> {
            let triggers = self.observe_changes(&app.session);
            if !self.drm_device.is_active() {
                return Ok(0);
            }
            if self.pageflip_pending || !self.needs_redraw {
                return Ok(0);
            }

            for placement in placements {
                configure_toplevel_for_placement(
                    &placement.surface,
                    &placement.placement,
                    &placement.window_policy,
                );
            }

            let elements = placements
                .iter()
                .flat_map(|placement| {
                    render_elements_from_surface_tree(
                        &mut self.renderer,
                        placement.surface.wl_surface(),
                        (placement.placement.x, placement.placement.y),
                        1.0,
                        1.0,
                        Kind::Unspecified,
                    )
                })
                .collect::<Vec<WaylandSurfaceRenderElement<GlesRenderer>>>();

            let frame_result = self
                .compositor
                .render_frame(
                    &mut self.renderer,
                    &elements,
                    Color32F::new(0.05, 0.08, 0.12, 1.0),
                    FrameFlags::DEFAULT,
                )
                .map_err(|error| format!("drm-render-frame-failed:{error}"))?;

            if frame_result.needs_sync() {
                if let PrimaryPlaneElement::Swapchain(primary) = &frame_result.primary_element {
                    let _ = primary.sync.wait();
                }
            }

            if frame_result.is_empty {
                self.needs_redraw = false;
                self.last_presented_triggers = triggers;
                app.session.set_renderer_status(format!(
                    "active(scanout-idle,output={},size={}x{},refresh={}mHz)",
                    self.output_name, self.output_size.w, self.output_size.h, self.refresh_millihz
                ));
                return Ok(0);
            }

            self.compositor
                .queue_frame(())
                .map_err(|error| format!("drm-queue-frame-failed:{error}"))?;
            self.pageflip_pending = true;
            self.needs_redraw = false;
            self.last_presented_triggers = triggers;
            app.session.set_renderer_status(format!(
                "active(scanout-pending,output={},size={}x{},refresh={}mHz,crtc={:?})",
                self.output_name,
                self.output_size.w,
                self.output_size.h,
                self.refresh_millihz,
                self.crtc
            ));

            let frame_time = self.start_time.elapsed().as_millis() as u32;
            for placement in placements {
                send_frames_surface_tree(placement.surface.wl_surface(), frame_time);
            }

            Ok(1)
        }

        fn handle_drm_event(
            &mut self,
            event: DrmEvent,
            metadata: Option<smithay::backend::drm::DrmEventMetadata>,
            app: &mut App,
        ) {
            match event {
                DrmEvent::VBlank(crtc) if crtc == self.crtc => {
                    match self.compositor.frame_submitted() {
                        Ok(Some(())) => {
                            self.pageflip_pending = false;
                            app.session.note_rendered_frame();
                            if DrmRenderTriggers::capture(&app.session)
                                != self.last_presented_triggers
                            {
                                self.needs_redraw = true;
                            }
                            let sequence = metadata
                                .map(|meta| meta.sequence.to_string())
                                .unwrap_or_else(|| "unknown".to_string());
                            app.session.set_renderer_status(format!(
                                "active(scanout,output={},frames={},last-vblank-seq={})",
                                self.output_name, app.session.rendered_frame_count, sequence
                            ));
                        }
                        Ok(None) => {
                            self.pageflip_pending = false;
                        }
                        Err(error) => {
                            self.pageflip_pending = false;
                            self.needs_redraw = true;
                            app.session
                                .set_renderer_status(format!("drm-frame-submit-failed:{error}"));
                        }
                    }
                }
                DrmEvent::VBlank(_) => {}
                DrmEvent::Error(error) => {
                    self.pageflip_pending = false;
                    self.needs_redraw = true;
                    app.session
                        .set_renderer_status(format!("drm-event-error:{error}"));
                }
            }
        }

        fn pause(&mut self, session: &mut SessionState) {
            self.drm_device.pause();
            self.pageflip_pending = false;
            self.needs_redraw = true;
            session.set_renderer_status(format!("paused(scanout,output={})", self.output_name));
        }

        fn activate(
            &mut self,
            disable_connectors: bool,
            session: &mut SessionState,
        ) -> Result<(), String> {
            self.drm_device
                .activate(disable_connectors)
                .map_err(|error| format!("drm-reactivate-failed:{error}"))?;
            self.compositor
                .reset_state()
                .map_err(|error| format!("drm-reset-state-failed:{error}"))?;
            self.pageflip_pending = false;
            self.needs_redraw = true;
            session.set_renderer_status(format!(
                "active(scanout-resume,output={},size={}x{})",
                self.output_name, self.output_size.w, self.output_size.h
            ));
            Ok(())
        }
    }

    fn initialize_drm_runtime(
        config: &Config,
        libseat_session: &mut LibSeatSession,
        session: &mut SessionState,
    ) -> Result<DrmRuntime, String> {
        let mut context = initialize_drm_device_context(config, libseat_session, session)?;
        let drm_node_label = format!("{:?}", context.drm_node);
        let output = create_drm_output(&context.selected_output);
        let renderer_formats = context
            .renderer
            .dmabuf_formats()
            .into_iter()
            .collect::<Vec<DrmFormat>>();
        if renderer_formats.is_empty() {
            return Err("drm-renderer-format-set-empty".to_string());
        }

        let allocator = GbmAllocator::new(
            context.gbm.clone(),
            GbmBufferFlags::RENDERING | GbmBufferFlags::SCANOUT,
        );
        let exporter = GbmFramebufferExporter::new(context.gbm.clone(), Some(context.drm_node));
        let surface = context
            .drm_device
            .create_surface(
                context.selected_output.crtc,
                context.selected_output.mode,
                &[context.selected_output.connector],
            )
            .map_err(|error| format!("drm-surface-init-failed:{error}"))?;
        let compositor = DrmCompositor::new(
            &output,
            surface,
            None,
            allocator,
            exporter,
            [DrmFourcc::Xrgb8888, DrmFourcc::Argb8888],
            renderer_formats,
            context.drm_device.cursor_size(),
            Some(context.gbm.clone()),
        )
        .map_err(|error| format!("drm-compositor-init-failed:{error}"))?;

        session.set_renderer_status(format!(
            "active(node={},outputs={},connected={},active={},atomic={},planes={},scanout=ready,output={},size={}x{},refresh={}mHz)",
            drm_node_label,
            context.drm_probe.output_count,
            context.drm_probe.connected_output_count,
            context.drm_probe.active_output_count,
            context.drm_probe.atomic_modesetting,
            context.drm_probe.plane_count,
            context.selected_output.connector_name,
            context.selected_output.output_size.w,
            context.selected_output.output_size.h,
            context.selected_output.output_mode.refresh
        ));

        Ok(DrmRuntime {
            output_size: context.selected_output.output_size,
            output_seeds: context.drm_probe.outputs.clone(),
            drm_notifier: context.drm_notifier,
            presentation: Rc::new(RefCell::new(DrmPresentationRuntime::new(
                context.drm_device,
                compositor,
                context.renderer,
                output,
                &context.selected_output,
            ))),
        })
    }

    fn initialize_libinput_backend(
        config: &Config,
        libseat_session: LibSeatSession,
        session: &mut SessionState,
    ) -> Result<LibinputInputBackend, String> {
        let mut libinput_context =
            Libinput::new_with_udev(LibinputSessionInterface::from(libseat_session));
        libinput_context
            .udev_assign_seat(&config.seat_name)
            .map_err(|_| format!("libinput-seat-assign-failed({})", config.seat_name))?;
        session.set_input_backend_status(format!("active(libinput,seat={})", config.seat_name));
        Ok(LibinputInputBackend::new(libinput_context))
    }

    fn run_drm_kms(
        config: &Config,
        tick_target: Option<u32>,
    ) -> Result<SessionState, Box<dyn Error>> {
        let mut display: Display<App> = Display::new()?;
        let dh = display.handle();
        let compositor_state = CompositorState::new::<App>(&dh);
        let xdg_shell_state = XdgShellState::new::<App>(&dh);
        let shm_state = ShmState::new::<App>(&dh, vec![]);
        let mut seat_state = SeatState::new();
        let mut seat = seat_state.new_wl_seat(&dh, &config.seat_name);
        let mut session = SessionState::new(config);
        session.set_seat_name(Some(config.seat_name.clone()));
        if config.pointer_enabled {
            let _ = seat.add_pointer();
            session.set_pointer_status("enabled(drm-kms)");
        } else {
            session.set_pointer_status("disabled");
        }
        if config.keyboard_enabled {
            match seat.add_keyboard(
                XkbConfig {
                    layout: config.keyboard_layout.as_str(),
                    ..XkbConfig::default()
                },
                config.keyboard_repeat_delay_ms,
                config.keyboard_repeat_rate,
            ) {
                Ok(_) => session.set_keyboard_status(format!(
                    "enabled(drm-kms,layout={})",
                    config.keyboard_layout
                )),
                Err(error) => session.set_keyboard_status(format!(
                    "init-failed(drm-kms,layout={}):{error}",
                    config.keyboard_layout
                )),
            }
        } else {
            session.set_keyboard_status("disabled");
        }
        if config.touch_enabled {
            let _ = seat.add_touch();
            session.set_touch_status("enabled(drm-kms)");
        } else {
            session.set_touch_status("disabled");
        }
        session.set_input_backend_status("initializing(libinput)");
        let window_manager = WindowManager::new(config);
        session.set_window_state_path(window_manager.state_path_string());
        let mut state = App {
            compositor_state,
            xdg_shell_state,
            shm_state,
            seat_state,
            seat,
            panel_action_command: config.panel_action_command.clone(),
            panel_bridge_socket: config.panel_bridge_socket.clone(),
            panel_action_log_path: config.panel_action_log_path.clone(),
            session,
            window_manager,
            last_toplevel_placements: Vec::new(),
        };

        let owned_runtime_dir = ensure_runtime_dir()?;
        let listener = if let Some(socket_name) = config.socket_name.as_deref() {
            ListeningSocket::bind(socket_name)?
        } else {
            ListeningSocket::bind_auto("wayland", 1..33)?
        };
        state
            .session
            .set_socket_name(listener.socket_name().map(os_str_to_string));
        state.session.set_smithay_status(MODE_LABEL_DRM);
        state.session.set_renderer_backend(RENDERER_BACKEND_DRM);
        state.session.set_xdg_shell_status("registered");
        state.session.host_focus_status = "seat-active".to_string();
        let mut runtime = RuntimeArtifacts::acquire(config, &mut state.session)?;
        let (mut libseat_session, session_notifier) =
            initialize_libseat_session(&mut state.session).map_err(|error| {
                let _ = runtime.publish_failure(&mut state.session, &error);
                Box::new(std::io::Error::new(std::io::ErrorKind::Other, error)) as Box<dyn Error>
            })?;
        let drm_runtime = initialize_drm_runtime(config, &mut libseat_session, &mut state.session)
            .map_err(|error| {
                let _ = runtime.publish_failure(&mut state.session, &error);
                Box::new(std::io::Error::new(std::io::ErrorKind::Other, error)) as Box<dyn Error>
            })?;
        let output_size = drm_runtime.output_size;
        state
            .window_manager
            .set_output_seeds(drm_runtime.output_seeds.clone());
        state.window_manager.sync_outputs(output_size);
        state.sync_window_manager_session(&[]);
        let drm_presentation = drm_runtime.presentation.clone();
        let input_backend =
            initialize_libinput_backend(config, libseat_session.clone(), &mut state.session)
                .map_err(|error| {
                    let _ = runtime.publish_failure(&mut state.session, &error);
                    Box::new(std::io::Error::new(std::io::ErrorKind::Other, error))
                        as Box<dyn Error>
                })?;
        let mut input_loop = CalloopEventLoop::<App>::try_new()?;
        let input_output_size = output_size;
        input_loop
            .handle()
            .insert_source(input_backend, move |event, _, app| {
                app.route_input_event(event, input_output_size);
            })
            .map_err(|error| {
                let message = format!("libinput-source-register-failed:{error}");
                let _ = runtime.publish_failure(&mut state.session, &message);
                Box::new(std::io::Error::new(std::io::ErrorKind::Other, message)) as Box<dyn Error>
            })?;
        let drm_event_presentation = drm_presentation.clone();
        input_loop
            .handle()
            .insert_source(drm_runtime.drm_notifier, move |event, metadata, app| {
                drm_event_presentation
                    .borrow_mut()
                    .handle_drm_event(event, metadata.take(), app);
            })
            .map_err(|error| {
                let message = format!("drm-source-register-failed:{error}");
                let _ = runtime.publish_failure(&mut state.session, &message);
                Box::new(std::io::Error::new(std::io::ErrorKind::Other, message)) as Box<dyn Error>
            })?;
        let session_presentation = drm_presentation.clone();
        let disable_connectors = config.drm_disable_connectors;
        input_loop
            .handle()
            .insert_source(session_notifier, move |event, _, app| match event {
                SessionEvent::PauseSession => {
                    session_presentation.borrow_mut().pause(&mut app.session);
                    app.session.set_session_control_status("paused(libseat)");
                    app.session.set_input_backend_status("paused(libinput)");
                }
                SessionEvent::ActivateSession => {
                    match session_presentation
                        .borrow_mut()
                        .activate(disable_connectors, &mut app.session)
                    {
                        Ok(()) => {
                            app.session.set_session_control_status("active(libseat)");
                            app.session.set_input_backend_status(format!(
                                "active(libinput,devices={})",
                                app.session.input_device_count
                            ));
                        }
                        Err(error) => {
                            app.session
                                .set_session_control_status(format!("reactivate-failed:{error}"));
                            app.session
                                .set_input_backend_status(format!("reactivate-failed:{error}"));
                            app.session.set_renderer_status(error);
                        }
                    }
                }
            })
            .map_err(|error| {
                let message = format!("libseat-source-register-failed:{error}");
                let _ = runtime.publish_failure(&mut state.session, &message);
                Box::new(std::io::Error::new(std::io::ErrorKind::Other, message)) as Box<dyn Error>
            })?;
        runtime.publish_ready(&mut state.session)?;

        let run_result = (|| -> Result<(), Box<dyn Error>> {
            while tick_target
                .map(|target| state.session.ticks < target)
                .unwrap_or(true)
            {
                refresh_panel_host_snapshot(&mut state.session, config);

                while let Some(stream) = listener.accept()? {
                    display
                        .handle()
                        .insert_client(stream, Arc::new(ClientState::default()))?;
                    state.session.note_client_connected();
                }

                input_loop.dispatch(Duration::from_millis(0), &mut state)?;
                display.dispatch_clients(&mut state)?;
                state.sync_runtime_metrics();
                let placements = state.collect_toplevel_placements(output_size);
                drm_presentation
                    .borrow_mut()
                    .render_if_needed(&mut state, &placements)
                    .map_err(|error| {
                        Box::new(std::io::Error::new(std::io::ErrorKind::Other, error))
                            as Box<dyn Error>
                    })?;
                display.flush_clients()?;
                state.session.tick();
                runtime.publish_running(&mut state.session)?;
                thread::sleep(Duration::from_millis(config.tick_ms));
            }
            Ok(())
        })();

        if let Err(error) = run_result {
            let _ = runtime.publish_failure(&mut state.session, &error.to_string());
            drop(listener);
            drop(display);
            cleanup_runtime_dir(owned_runtime_dir);
            return Err(error);
        }

        state.session.finish();
        runtime.finish(&mut state.session)?;
        drop(listener);
        drop(display);
        cleanup_runtime_dir(owned_runtime_dir);
        Ok(state.session)
    }

    fn probe_drm_kms(config: &Config) -> Result<SessionState, Box<dyn Error>> {
        let mut session = SessionState::new(config);
        session.set_seat_name(Some(config.seat_name.clone()));
        session.set_pointer_status(if config.pointer_enabled {
            "probe-configured(drm-kms)"
        } else {
            "disabled"
        });
        session.set_keyboard_status(if config.keyboard_enabled {
            format!(
                "probe-configured(drm-kms,layout={})",
                config.keyboard_layout
            )
        } else {
            "disabled".to_string()
        });
        session.set_touch_status(if config.touch_enabled {
            "probe-configured(drm-kms)"
        } else {
            "disabled"
        });
        session.set_smithay_status(MODE_LABEL_DRM);
        session.set_renderer_backend(RENDERER_BACKEND_DRM);
        session.set_xdg_shell_status("probe-pending");
        session.host_focus_status = "probe-pending".to_string();
        session.set_input_backend_status(format!(
            "probe-configured(libinput,seat={})",
            config.seat_name
        ));
        refresh_panel_host_snapshot(&mut session, config);

        match initialize_libseat_session(&mut session).and_then(|(mut libseat_session, _)| {
            initialize_drm_device_context(config, &mut libseat_session, &mut session).map(|_| ())
        }) {
            Ok(_) => {
                session.lifecycle_state = "probe-ready".to_string();
                session.set_xdg_shell_status("probe-ready");
                session.host_focus_status = "probe-ready".to_string();
            }
            Err(error) => {
                session.lifecycle_state = "probe-failed".to_string();
                session.set_renderer_status(format!("probe-failed:{error}"));
                session.set_xdg_shell_status(format!("probe-failed:{error}"));
                if matches!(
                    session.session_control_status.as_str(),
                    "inactive" | "initializing"
                ) {
                    session.set_session_control_status(format!("probe-failed:{error}"));
                }
                session.host_focus_status = "probe-failed".to_string();
            }
        }

        Ok(session)
    }

    fn probe_nested_winit(config: &Config) -> Result<SessionState, Box<dyn Error>> {
        let mut session = SessionState::new(config);
        session.set_seat_name(Some(config.seat_name.clone()));
        session.set_pointer_status(if config.pointer_enabled {
            "probe-configured"
        } else {
            "disabled"
        });
        session.set_keyboard_status(if config.keyboard_enabled {
            format!("probe-configured(layout={})", config.keyboard_layout)
        } else {
            "disabled".to_string()
        });
        session.set_touch_status(if config.touch_enabled {
            "probe-configured"
        } else {
            "disabled"
        });
        session.set_smithay_status(MODE_LABEL_WINIT);
        session.set_renderer_backend(RENDERER_BACKEND_WINIT);
        session.set_renderer_status("probe-skipped(non-drm)");
        session.set_input_backend_status("probe-configured(winit)");
        session.set_session_control_status("probe-skipped(non-drm)");
        session.set_xdg_shell_status("probe-skipped(non-drm)");
        session.host_focus_status = "probe-skipped".to_string();
        session.lifecycle_state = "probe-skipped".to_string();
        refresh_panel_host_snapshot(&mut session, config);
        Ok(session)
    }

    fn select_drm_device_path(udev: &UdevBackend) -> Option<PathBuf> {
        udev.device_list()
            .map(|(_, path)| path.to_path_buf())
            .find(|path| {
                path.file_name()
                    .map(|name| name.to_string_lossy().starts_with("card"))
                    .unwrap_or(false)
            })
            .or_else(|| {
                udev.device_list()
                    .next()
                    .map(|(_, path)| path.to_path_buf())
            })
    }

    fn connector_preference_rank(connector_name: &str, preferred: Option<&str>) -> i32 {
        let Some(preferred) = preferred else {
            return 0;
        };
        if normalized_connector_name(connector_name) == normalized_connector_name(preferred) {
            0
        } else {
            1
        }
    }

    fn select_connector_mode(
        info: &connector::Info,
        config: &Config,
    ) -> Option<(
        ControlMode,
        OutputMode,
        Size<i32, Physical>,
        (i32, i32, i32, i32),
    )> {
        info.modes()
            .iter()
            .copied()
            .map(|mode| {
                let output_mode = OutputMode::from(mode);
                let (width, height) = mode.size();
                let size = Size::from((i32::from(width), i32::from(height)));
                let rank = mode_preference_rank(size, output_mode.refresh, config);
                (mode, output_mode, size, rank)
            })
            .min_by_key(|(_, _, _, rank)| *rank)
    }

    fn mode_preference_rank(
        size: Size<i32, Physical>,
        refresh_millihz: i32,
        config: &Config,
    ) -> (i32, i32, i32, i32) {
        (
            config
                .drm_output_width
                .map(|width| (size.w - width).abs())
                .unwrap_or(0),
            config
                .drm_output_height
                .map(|height| (size.h - height).abs())
                .unwrap_or(0),
            config
                .drm_output_refresh_millihz
                .map(|refresh| (refresh_millihz - refresh).abs())
                .unwrap_or(0),
            if refresh_millihz > 0 {
                -refresh_millihz
            } else {
                0
            },
        )
    }

    fn normalized_connector_name(value: &str) -> String {
        value
            .chars()
            .filter(|character| character.is_ascii_alphanumeric())
            .flat_map(char::to_lowercase)
            .collect()
    }

    fn probe_drm_outputs(device: &DrmDevice) -> Result<DrmProbe, String> {
        let resources = device
            .resource_handles()
            .map_err(|error| format!("drm-resources-unavailable:{error}"))?;
        let mut connected_output_count = 0;
        let mut active_output_count = 0;
        let mut plane_count = 0;
        let mut primary_output_name = None;
        let mut primary_output_size = None;
        let mut outputs = Vec::new();
        let mut used_crtcs = Vec::new();

        for connector_handle in resources.connectors() {
            let info = device
                .get_connector(*connector_handle, true)
                .map_err(|error| format!("drm-connector-query-failed:{error}"))?;
            let connector_name = format!("{:?}-{}", info.interface(), info.interface_id());
            let is_connected = info.state() == connector::State::Connected;
            let size = info
                .modes()
                .first()
                .map(|mode| {
                    let (width, height) = mode.size();
                    (i32::from(width), i32::from(height))
                })
                .unwrap_or((1920, 1080));
            if is_connected {
                connected_output_count += 1;
                if primary_output_name.is_none() {
                    primary_output_name = Some(connector_name.clone());
                }
                outputs.push(OutputSeed {
                    output_id: connector_name.clone(),
                    connector_name: Some(connector_name.clone()),
                    label: connector_name.clone(),
                    width: size.0,
                    height: size.1,
                    primary: primary_output_name.as_deref() == Some(connector_name.as_str()),
                    renderable: false,
                });
            }

            let Some(mode) = info.modes().first().copied() else {
                continue;
            };
            if !is_connected {
                continue;
            }
            let Some(crtc) = select_crtc_for_connector(device, &resources, &info, &used_crtcs)
            else {
                continue;
            };
            used_crtcs.push(crtc);
            active_output_count += 1;
            let planes = device
                .planes(&crtc)
                .map_err(|error| format!("drm-plane-query-failed:{error}"))?;
            plane_count +=
                (planes.primary.len() + planes.cursor.len() + planes.overlay.len()) as u32;
            if primary_output_size.is_none() {
                let (width, height) = mode.size();
                primary_output_size = Some(Size::from((i32::from(width), i32::from(height))));
            }
        }
        if let Some(primary_name) = primary_output_name.as_deref() {
            for output in &mut outputs {
                if output.output_id == primary_name {
                    output.primary = true;
                    output.renderable = true;
                }
            }
        }
        if outputs.is_empty() {
            outputs.push(OutputSeed {
                output_id: "display-1".to_string(),
                connector_name: None,
                label: "display-1".to_string(),
                width: 1920,
                height: 1080,
                primary: true,
                renderable: true,
            });
        }

        Ok(DrmProbe {
            output_count: resources.connectors().len() as u32,
            connected_output_count,
            active_output_count,
            primary_output_name,
            primary_output_size,
            outputs,
            atomic_modesetting: device.is_atomic(),
            plane_count,
        })
    }

    fn select_crtc_for_connector(
        device: &DrmDevice,
        resources: &ResourceHandles,
        info: &connector::Info,
        used_crtcs: &[smithay::reexports::drm::control::crtc::Handle],
    ) -> Option<smithay::reexports::drm::control::crtc::Handle> {
        if let Some(encoder) = info.current_encoder() {
            if let Ok(encoder_info) = device.get_encoder(encoder) {
                if let Some(crtc) = encoder_info.crtc() {
                    if !used_crtcs.contains(&crtc) {
                        return Some(crtc);
                    }
                }
            }
        }

        for encoder in info.encoders() {
            let Ok(encoder_info) = device.get_encoder(*encoder) else {
                continue;
            };
            for crtc in resources.filter_crtcs(encoder_info.possible_crtcs()) {
                if !used_crtcs.contains(&crtc) {
                    return Some(crtc);
                }
            }
        }
        None
    }

    #[derive(Default)]
    struct ClientState {
        compositor_state: CompositorClientState,
    }

    impl ClientData for ClientState {
        fn initialized(&self, _client_id: ClientId) {}

        fn disconnected(&self, _client_id: ClientId, _reason: DisconnectReason) {}
    }

    struct App {
        compositor_state: CompositorState,
        xdg_shell_state: XdgShellState,
        shm_state: ShmState,
        seat_state: SeatState<Self>,
        seat: Seat<Self>,
        panel_action_command: Option<String>,
        panel_bridge_socket: Option<String>,
        panel_action_log_path: Option<String>,
        session: SessionState,
        window_manager: WindowManager,
        last_toplevel_placements: Vec<ToplevelPlacement>,
    }

    #[derive(Clone, Debug)]
    struct ToplevelMetadata {
        app_id: Option<String>,
        title: Option<String>,
    }

    #[derive(Clone, Debug)]
    struct ToplevelPlacement {
        surface: ToplevelSurface,
        slot_id: Option<String>,
        sequence: usize,
        z_index: i32,
        placement: SurfacePlacement,
        window_policy: String,
        window_key: String,
        output_id: String,
        visible: bool,
        persisted: bool,
        interaction_state: String,
    }

    #[derive(Clone, Debug)]
    struct PanelSlotMeta {
        component: String,
        panel_id: Option<String>,
        focus_policy: String,
        primary_action_id: Option<String>,
    }

    impl App {
        fn active_modal_slot_id(&self) -> Option<String> {
            self.session.active_modal_surface_id.clone()
        }

        fn keyboard_focus_target(&mut self, window_size: Size<i32, Physical>) -> Option<WlSurface> {
            let placements = self.collect_toplevel_placements(window_size);
            let active_modal_slot = self.active_modal_slot_id();
            if should_redirect_to_modal(
                active_modal_slot.as_deref(),
                placements
                    .last()
                    .and_then(|placement| placement.slot_id.as_deref()),
            ) {
                return None;
            }
            placements
                .last()
                .map(|placement| placement.surface.wl_surface().clone())
        }

        fn panel_slot_meta(&self, slot_id: &str) -> Option<PanelSlotMeta> {
            self.session
                .surfaces
                .iter()
                .find(|surface| surface.surface_id == slot_id)
                .map(|surface| PanelSlotMeta {
                    component: surface
                        .panel_component
                        .clone()
                        .unwrap_or_else(|| surface.surface_id.clone()),
                    panel_id: surface.panel_id.clone(),
                    focus_policy: surface.focus_policy.clone(),
                    primary_action_id: surface.panel_primary_action_id.clone(),
                })
        }

        fn slot_window_policy(&self, slot_id: &str) -> Option<String> {
            self.session
                .surfaces
                .iter()
                .find(|surface| surface.surface_id == slot_id)
                .map(|surface| surface.window_policy.clone())
        }

        fn sync_window_manager_session(&mut self, placements: &[ManagedWindowPlacement]) {
            self.session.update_window_management(
                self.window_manager.status_label(),
                self.window_manager.output_layout_mode.clone(),
                self.window_manager.active_output_id(),
                self.window_manager.output_summaries(),
                self.window_manager.workspace_count,
                self.window_manager.active_workspace_index,
                self.window_manager.workspace_switch_count,
                self.window_manager.managed_window_summaries(placements),
                self.window_manager.move_count,
                self.window_manager.resize_count,
                self.window_manager.minimize_count,
                self.window_manager.restore_count,
                self.window_manager.last_minimized_window_key.clone(),
                self.window_manager.last_restored_window_key.clone(),
                self.window_manager.drag_state_label(),
                self.window_manager.resize_state_label(),
            );
        }

        fn hit_toplevel_placement(
            &self,
            location: Point<f64, Logical>,
        ) -> Option<ToplevelPlacement> {
            self.last_toplevel_placements
                .iter()
                .rev()
                .find(|placement| {
                    placement_contains_point(&placement.placement, location.x, location.y)
                })
                .cloned()
        }

        fn maybe_cycle_workspace(&mut self, vertical_amount: f64) -> bool {
            if self.session.last_hit_slot_id.as_deref() != Some("launcher")
                || vertical_amount.abs() < 0.5
            {
                return false;
            }
            if self
                .window_manager
                .cycle_workspace(if vertical_amount > 0.0 { 1 } else { -1 })
            {
                self.set_keyboard_focus(None);
                return true;
            }
            false
        }

        fn maybe_cycle_output(&mut self, horizontal_amount: f64) -> bool {
            if horizontal_amount.abs() < 0.5 {
                return false;
            }
            if self.session.last_hit_slot_id.as_deref() != Some("task-surface") {
                return false;
            }
            self.window_manager
                .cycle_output(if horizontal_amount > 0.0 { 1 } else { -1 })
        }

        fn sync_runtime_metrics(&mut self) {
            let toplevels = self.xdg_shell_state.toplevel_surfaces();
            let popups = self.xdg_shell_state.popup_surfaces();
            let mut clients = BTreeSet::new();

            for surface in toplevels {
                if let Some(client) = surface.wl_surface().client() {
                    clients.insert(format!("{:?}", client.id()));
                }
            }
            for surface in popups {
                if let Some(client) = surface.wl_surface().client() {
                    clients.insert(format!("{:?}", client.id()));
                }
            }

            self.session.set_client_count(clients.len() as u32);
            self.session.set_xdg_toplevel_count(toplevels.len() as u32);
            self.session.set_xdg_popup_count(popups.len() as u32);
        }

        fn pointer_focus_target(
            &mut self,
            location: Point<f64, Logical>,
            window_size: Size<i32, Physical>,
        ) -> Option<(WlSurface, Point<f64, Logical>)> {
            let placements = self.collect_toplevel_placements(window_size);
            let active_modal_slot = self.active_modal_slot_id();
            let slot_hit = self.hit_test_surface_slot(location);
            let hit = placements
                .iter()
                .rev()
                .find(|placement| {
                    placement_contains_point(&placement.placement, location.x, location.y)
                })
                .cloned();
            let hit_slot = hit
                .as_ref()
                .and_then(|placement| placement.slot_id.as_deref())
                .or(slot_hit.as_deref());
            if should_redirect_to_modal(active_modal_slot.as_deref(), hit_slot) {
                self.session.note_hit_test(
                    active_modal_slot.clone(),
                    None,
                    Some((location.x, location.y)),
                );
                return None;
            }
            self.session.note_hit_test(
                hit.as_ref()
                    .and_then(|placement| placement.slot_id.clone())
                    .or(slot_hit),
                hit.as_ref()
                    .map(|placement| surface_label(placement.surface.wl_surface())),
                Some((location.x, location.y)),
            );
            hit.map(|placement| {
                (
                    placement.surface.wl_surface().clone(),
                    (placement.placement.x as f64, placement.placement.y as f64).into(),
                )
            })
        }

        fn pointer_focus_from_last_location(
            &mut self,
            window_size: Size<i32, Physical>,
        ) -> Option<(WlSurface, Point<f64, Logical>)> {
            let x = self.session.last_pointer_x?;
            let y = self.session.last_pointer_y?;
            self.pointer_focus_target((x, y).into(), window_size)
        }

        fn hit_test_surface_slot(&self, location: Point<f64, Logical>) -> Option<String> {
            self.session
                .surfaces
                .iter()
                .filter(|surface| surface.pointer_policy == "interactive")
                .filter(|surface| surface_contains_point(surface, location.x, location.y))
                .max_by_key(|surface| surface.z_index)
                .map(|surface| surface.surface_id.clone())
        }

        fn current_pointer_location(
            &self,
            window_size: Size<i32, Physical>,
        ) -> Point<f64, Logical> {
            let default_x = (window_size.w.max(1) / 2) as f64;
            let default_y = (window_size.h.max(1) / 2) as f64;
            (
                self.session.last_pointer_x.unwrap_or(default_x),
                self.session.last_pointer_y.unwrap_or(default_y),
            )
                .into()
        }

        fn clamp_pointer_location(
            &self,
            location: Point<f64, Logical>,
            window_size: Size<i32, Physical>,
        ) -> Point<f64, Logical> {
            let max_x = f64::from((window_size.w - 1).max(0));
            let max_y = f64::from((window_size.h - 1).max(0));
            (location.x.clamp(0.0, max_x), location.y.clamp(0.0, max_y)).into()
        }

        fn activate_panel_host_slot(&mut self, input_kind: &str) {
            let Some(slot_id) = self.session.last_hit_slot_id.clone() else {
                return;
            };
            let focus_policy = self
                .session
                .note_panel_host_activation(&slot_id, input_kind);
            if focus_policy.is_some() {
                if let Some(slot_meta) = self.panel_slot_meta(&slot_id) {
                    let log_path = self.panel_action_log_path.clone();
                    let tick = self.session.ticks;
                    let action_id = self
                        .session
                        .last_panel_action_id
                        .clone()
                        .or(slot_meta.primary_action_id.clone());
                    record_panel_action_event(
                        &mut self.session,
                        log_path.as_deref(),
                        PanelActionEvent {
                            sequence: 0,
                            event_id: String::new(),
                            kind: "panel-host.activation".to_string(),
                            recorded_at_ms: 0,
                            tick,
                            slot_id: Some(slot_id.clone()),
                            component: Some(slot_meta.component.clone()),
                            panel_id: slot_meta.panel_id.clone(),
                            action_id,
                            input_kind: Some(input_kind.to_string()),
                            focus_policy: Some(slot_meta.focus_policy.clone()),
                            status: "activated".to_string(),
                            summary: Some(format!(
                                "{} activated via {}",
                                slot_meta.component, input_kind
                            )),
                            error: None,
                            payload: None,
                        },
                    );
                }
            }
            match focus_policy.as_deref() {
                Some("shell-modal") | Some("workspace-target") => self.set_keyboard_focus(None),
                _ => {}
            }
            self.dispatch_panel_host_action(&slot_id, input_kind);
        }

        fn dispatch_panel_host_action(&mut self, slot_id: &str, input_kind: &str) {
            let slot_meta = self.panel_slot_meta(slot_id);
            let log_path = self.panel_action_log_path.clone();
            let tick = self.session.ticks;
            let action_id = self.session.last_panel_action_id.clone().or_else(|| {
                slot_meta
                    .as_ref()
                    .and_then(|item| item.primary_action_id.clone())
            });
            let Some(action_id) = action_id else {
                self.session.panel_action_status = "no-action".to_string();
                self.session.last_panel_action_summary = None;
                self.session.note_panel_action_target_component(None);
                record_panel_action_event(
                    &mut self.session,
                    log_path.as_deref(),
                    PanelActionEvent {
                        sequence: 0,
                        event_id: String::new(),
                        kind: "panel-action.dispatch".to_string(),
                        recorded_at_ms: 0,
                        tick,
                        slot_id: Some(slot_id.to_string()),
                        component: slot_meta.as_ref().map(|item| item.component.clone()),
                        panel_id: slot_meta.as_ref().and_then(|item| item.panel_id.clone()),
                        action_id: None,
                        input_kind: Some(input_kind.to_string()),
                        focus_policy: slot_meta.as_ref().map(|item| item.focus_policy.clone()),
                        status: "no-action".to_string(),
                        summary: None,
                        error: None,
                        payload: None,
                    },
                );
                return;
            };
            let Some(slot_meta) = slot_meta else {
                self.session.note_panel_action_result("missing-slot", None);
                self.session.note_panel_action_target_component(None);
                record_panel_action_event(
                    &mut self.session,
                    log_path.as_deref(),
                    PanelActionEvent {
                        sequence: 0,
                        event_id: String::new(),
                        kind: "panel-action.dispatch".to_string(),
                        recorded_at_ms: 0,
                        tick,
                        slot_id: Some(slot_id.to_string()),
                        component: None,
                        panel_id: None,
                        action_id: Some(action_id),
                        input_kind: Some(input_kind.to_string()),
                        focus_policy: None,
                        status: "missing-slot".to_string(),
                        summary: None,
                        error: None,
                        payload: None,
                    },
                );
                return;
            };
            let component = slot_meta.component.clone();
            let mut socket_error: Option<String> = None;
            if let Some(socket_path) = self.panel_bridge_socket.as_deref() {
                match dispatch_panel_action_via_socket(
                    Path::new(socket_path),
                    serde_json::json!({
                        "slot_id": slot_id,
                        "component": component,
                        "panel_id": slot_meta.panel_id.clone(),
                        "action_id": action_id,
                        "input_kind": input_kind,
                    }),
                ) {
                    Ok(stdout) => {
                        let summary = panel_action_summary(&stdout);
                        let status = format!("dispatch-ok({action_id})");
                        let payload = panel_action_payload(&stdout);
                        self.session.note_panel_action_target_component(
                            panel_action_target_component(payload.as_ref()),
                        );
                        self.session
                            .note_panel_action_result(status.clone(), summary.clone());
                        record_panel_action_event(
                            &mut self.session,
                            log_path.as_deref(),
                            PanelActionEvent {
                                sequence: 0,
                                event_id: String::new(),
                                kind: "panel-action.dispatch".to_string(),
                                recorded_at_ms: 0,
                                tick,
                                slot_id: Some(slot_id.to_string()),
                                component: Some(component.clone()),
                                panel_id: slot_meta.panel_id.clone(),
                                action_id: Some(action_id.clone()),
                                input_kind: Some(input_kind.to_string()),
                                focus_policy: Some(slot_meta.focus_policy.clone()),
                                status,
                                summary,
                                error: None,
                                payload,
                            },
                        );
                        return;
                    }
                    Err(error) => {
                        socket_error = Some(error);
                    }
                }
            }
            let Some(command) = self.panel_action_command.as_deref() else {
                let summary = socket_error.as_ref().map(|error| clip_string(error, 160));
                let status = if socket_error.is_some() {
                    format!("dispatch-socket-error({action_id})")
                } else {
                    "missing-command".to_string()
                };
                self.session
                    .note_panel_action_result(status.clone(), summary.clone());
                self.session.note_panel_action_target_component(None);
                record_panel_action_event(
                    &mut self.session,
                    log_path.as_deref(),
                    PanelActionEvent {
                        sequence: 0,
                        event_id: String::new(),
                        kind: "panel-action.dispatch".to_string(),
                        recorded_at_ms: 0,
                        tick,
                        slot_id: Some(slot_id.to_string()),
                        component: Some(component.clone()),
                        panel_id: slot_meta.panel_id.clone(),
                        action_id: Some(action_id.clone()),
                        input_kind: Some(input_kind.to_string()),
                        focus_policy: Some(slot_meta.focus_policy.clone()),
                        status,
                        summary: summary.clone(),
                        error: summary,
                        payload: None,
                    },
                );
                return;
            };
            let mut process = if cfg!(windows) {
                let mut process = Command::new("cmd");
                process.arg("/C").arg(command);
                process
            } else {
                let mut process = Command::new("/bin/sh");
                process.arg("-lc").arg(command);
                process
            };
            process.env("AIOS_SHELL_PANEL_SLOT_ID", slot_id);
            process.env("AIOS_SHELL_PANEL_COMPONENT", &component);
            process.env("AIOS_SHELL_PANEL_ACTION_ID", &action_id);
            process.env("AIOS_SHELL_PANEL_INPUT_KIND", input_kind);
            process.env("AIOS_SHELL_PANEL_FOCUS_POLICY", &slot_meta.focus_policy);
            if let Some(panel_id) = slot_meta.panel_id.as_deref() {
                process.env("AIOS_SHELL_PANEL_ID", panel_id);
            }
            match process.output() {
                Ok(output) if output.status.success() => {
                    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    let summary = panel_action_summary(&stdout);
                    let status = if socket_error.is_some() {
                        format!("dispatch-command-fallback({action_id})")
                    } else {
                        format!("dispatch-ok({action_id})")
                    };
                    let payload = panel_action_payload(&stdout);
                    self.session
                        .note_panel_action_target_component(panel_action_target_component(
                            payload.as_ref(),
                        ));
                    self.session
                        .note_panel_action_result(status.clone(), summary.clone());
                    record_panel_action_event(
                        &mut self.session,
                        log_path.as_deref(),
                        PanelActionEvent {
                            sequence: 0,
                            event_id: String::new(),
                            kind: "panel-action.dispatch".to_string(),
                            recorded_at_ms: 0,
                            tick,
                            slot_id: Some(slot_id.to_string()),
                            component: Some(component.clone()),
                            panel_id: slot_meta.panel_id.clone(),
                            action_id: Some(action_id.clone()),
                            input_kind: Some(input_kind.to_string()),
                            focus_policy: Some(slot_meta.focus_policy.clone()),
                            status,
                            summary,
                            error: None,
                            payload,
                        },
                    );
                }
                Ok(output) => {
                    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    let summary = summarize_command_failure(&stderr, &stdout).map(|message| {
                        if let Some(socket_error) = socket_error.as_ref() {
                            clip_string(&format!("{socket_error}; fallback:{message}"), 160)
                        } else {
                            message
                        }
                    });
                    let status = format!("dispatch-failed({action_id})");
                    let error = summary.clone();
                    let payload = panel_action_payload(&stdout);
                    self.session
                        .note_panel_action_target_component(panel_action_target_component(
                            payload.as_ref(),
                        ));
                    self.session
                        .note_panel_action_result(status.clone(), summary.clone());
                    record_panel_action_event(
                        &mut self.session,
                        log_path.as_deref(),
                        PanelActionEvent {
                            sequence: 0,
                            event_id: String::new(),
                            kind: "panel-action.dispatch".to_string(),
                            recorded_at_ms: 0,
                            tick,
                            slot_id: Some(slot_id.to_string()),
                            component: Some(component.clone()),
                            panel_id: slot_meta.panel_id.clone(),
                            action_id: Some(action_id.clone()),
                            input_kind: Some(input_kind.to_string()),
                            focus_policy: Some(slot_meta.focus_policy.clone()),
                            status,
                            summary,
                            error,
                            payload,
                        },
                    );
                }
                Err(error) => {
                    let summary = Some(if let Some(socket_error) = socket_error.as_ref() {
                        clip_string(&format!("{socket_error}; fallback:{}", error), 160)
                    } else {
                        error.to_string()
                    });
                    let status = format!("dispatch-error({action_id})");
                    self.session.note_panel_action_target_component(None);
                    self.session
                        .note_panel_action_result(status.clone(), summary.clone());
                    record_panel_action_event(
                        &mut self.session,
                        log_path.as_deref(),
                        PanelActionEvent {
                            sequence: 0,
                            event_id: String::new(),
                            kind: "panel-action.dispatch".to_string(),
                            recorded_at_ms: 0,
                            tick,
                            slot_id: Some(slot_id.to_string()),
                            component: Some(component),
                            panel_id: slot_meta.panel_id.clone(),
                            action_id: Some(action_id),
                            input_kind: Some(input_kind.to_string()),
                            focus_policy: Some(slot_meta.focus_policy.clone()),
                            status,
                            summary: summary.clone(),
                            error: summary,
                            payload: None,
                        },
                    );
                }
            }
        }

        fn set_keyboard_focus(&mut self, focus: Option<WlSurface>) {
            self.session
                .set_focused_surface_id(focus.as_ref().map(surface_label));
            if let Some(keyboard) = self.seat.get_keyboard() {
                keyboard.set_focus(self, focus, SERIAL_COUNTER.next_serial());
            }
        }

        fn collect_toplevel_placements(
            &mut self,
            window_size: Size<i32, Physical>,
        ) -> Vec<ToplevelPlacement> {
            self.window_manager.sync_outputs(window_size);
            if self.window_manager.reload_state_if_changed() {
                self.window_manager.sync_outputs(window_size);
            }
            self.session
                .sync_surface_layouts(window_size.w, window_size.h);
            self.session.clear_surface_embeddings();

            let available_slots = self
                .session
                .surfaces
                .iter()
                .map(|surface| surface.surface_id.clone())
                .collect::<Vec<_>>();
            let toplevels = self
                .xdg_shell_state
                .toplevel_surfaces()
                .iter()
                .cloned()
                .collect::<Vec<_>>();

            let mut used_slots = Vec::new();
            let mut placements = Vec::new();
            let mut managed_placements = Vec::new();

            for (index, surface) in toplevels.into_iter().enumerate() {
                let metadata = toplevel_metadata(&surface);
                let candidate_slot = match_panel_slot(
                    &available_slots,
                    &used_slots,
                    metadata.app_id.as_deref(),
                    metadata.title.as_deref(),
                );
                let window_policy = candidate_slot
                    .as_deref()
                    .and_then(|slot_id| self.slot_window_policy(slot_id))
                    .unwrap_or_else(|| toplevel_window_policy(&metadata));
                let managed = self.window_manager.place_window(
                    index,
                    &metadata,
                    candidate_slot.as_deref(),
                    surface_label(surface.wl_surface()),
                    window_policy.clone(),
                );
                if managed.visible {
                    if let Some(slot_id) = candidate_slot.as_ref() {
                        used_slots.push(slot_id.clone());
                        self.session.bind_surface_embedding(
                            slot_id,
                            managed.surface_id.clone(),
                            metadata.app_id.clone(),
                            metadata.title.clone(),
                        );
                    }
                }
                let z_index = if managed.visible {
                    placement_z_index(managed.placement.zone)
                } else {
                    -1024
                };
                managed_placements.push(managed.clone());
                placements.push(ToplevelPlacement {
                    surface,
                    slot_id: candidate_slot,
                    sequence: index,
                    z_index,
                    placement: managed.placement.clone(),
                    window_policy,
                    window_key: managed.window_key.clone(),
                    output_id: managed.output_id.clone(),
                    visible: managed.visible,
                    persisted: managed.persisted,
                    interaction_state: managed.interaction_state.clone(),
                });
            }

            self.sync_window_manager_session(&managed_placements);
            let _ = self.window_manager.save_if_dirty();
            let mut visible_placements = placements
                .into_iter()
                .filter(|placement| placement.visible)
                .collect::<Vec<_>>();
            visible_placements.sort_by_key(|placement| (placement.z_index, placement.sequence));
            self.last_toplevel_placements = visible_placements.clone();
            self.session.note_stacking(
                visible_placements
                    .last()
                    .map(|placement| surface_label(placement.surface.wl_surface())),
                visible_placements
                    .last()
                    .and_then(|placement| placement.slot_id.clone()),
            );
            visible_placements
        }

        fn route_input_event<B>(
            &mut self,
            input_event: InputEvent<B>,
            window_size: Size<i32, Physical>,
        ) where
            B: InputBackend,
        {
            match input_event {
                InputEvent::DeviceAdded { device } => {
                    self.session.note_input_device_added(format!(
                        "{}@{}",
                        device.name(),
                        device.id()
                    ));
                    self.session.set_input_backend_status(format!(
                        "active(devices={})",
                        self.session.input_device_count
                    ));
                }
                InputEvent::DeviceRemoved { device } => {
                    self.session.note_input_device_removed(format!(
                        "{}@{}",
                        device.name(),
                        device.id()
                    ));
                    self.session.set_input_backend_status(format!(
                        "active(devices={})",
                        self.session.input_device_count
                    ));
                }
                InputEvent::Keyboard { event } => {
                    if self.session.focused_surface_id.is_none() {
                        let keyboard_focus = self.keyboard_focus_target(window_size);
                        self.set_keyboard_focus(keyboard_focus);
                    }
                    if let Some(keyboard) = self.seat.get_keyboard() {
                        let _ = keyboard.input::<(), _>(
                            self,
                            event.key_code(),
                            event.state(),
                            SERIAL_COUNTER.next_serial(),
                            event.time_msec(),
                            |_, _, _| FilterResult::Forward,
                        );
                    }
                    self.session.note_keyboard_input(format!(
                        "keyboard:{}",
                        key_state_label(event.state())
                    ));
                }
                InputEvent::PointerMotion { event } => {
                    let delta = event.delta();
                    let base = self.current_pointer_location(window_size);
                    let location = self.clamp_pointer_location(
                        (base.x + delta.x, base.y + delta.y).into(),
                        window_size,
                    );
                    if self.window_manager.update_pointer_operation(location) {
                        self.session.note_pointer_input(
                            if self.window_manager.drag_state_label() != "idle" {
                                "pointer-drag"
                            } else {
                                "pointer-resize"
                            },
                            Some((location.x, location.y)),
                        );
                        return;
                    }
                    let focus = self.pointer_focus_target(location, window_size);
                    if let Some(pointer) = self.seat.get_pointer() {
                        let motion = PointerMotionEvent {
                            location,
                            serial: SERIAL_COUNTER.next_serial(),
                            time: event.time_msec(),
                        };
                        pointer.motion(self, focus.clone(), &motion);
                        pointer.frame(self);
                    }
                    self.session
                        .note_pointer_input("pointer-motion", Some((location.x, location.y)));
                    if let Some((surface, _)) = focus {
                        self.set_keyboard_focus(Some(surface));
                    }
                }
                InputEvent::PointerMotionAbsolute { event } => {
                    let location = absolute_location::<B, _>(&event, window_size);
                    if self.window_manager.update_pointer_operation(location) {
                        self.session.note_pointer_input(
                            if self.window_manager.drag_state_label() != "idle" {
                                "pointer-drag"
                            } else {
                                "pointer-resize"
                            },
                            Some((location.x, location.y)),
                        );
                        return;
                    }
                    let focus = self.pointer_focus_target(location, window_size);
                    if let Some(pointer) = self.seat.get_pointer() {
                        let motion = PointerMotionEvent {
                            location,
                            serial: SERIAL_COUNTER.next_serial(),
                            time: event.time_msec(),
                        };
                        pointer.motion(self, focus.clone(), &motion);
                        pointer.frame(self);
                    }
                    self.session
                        .note_pointer_input("pointer-motion", Some((location.x, location.y)));
                    if let Some((surface, _)) = focus {
                        self.set_keyboard_focus(Some(surface));
                    }
                }
                InputEvent::PointerButton { event } => {
                    let button_code = event.button_code();
                    let pointer_location = self.current_pointer_location(window_size);
                    let focus = self.pointer_focus_from_last_location(window_size);
                    let hit_placement =
                        self.hit_toplevel_placement(pointer_location).or_else(|| {
                            self.collect_toplevel_placements(window_size)
                                .into_iter()
                                .rev()
                                .find(|placement| {
                                    placement_contains_point(
                                        &placement.placement,
                                        pointer_location.x,
                                        pointer_location.y,
                                    )
                                })
                        });
                    let minimizing_window = matches!(event.state(), ButtonState::Pressed)
                        && button_code == POINTER_BUTTON_MIDDLE
                        && hit_placement
                            .as_ref()
                            .filter(|placement| {
                                is_minimizable_window_policy(&placement.window_policy)
                            })
                            .map(|placement| {
                                self.window_manager.minimize_window(&placement.window_key)
                            })
                            .unwrap_or(false);
                    let restoring_window = matches!(event.state(), ButtonState::Pressed)
                        && button_code == POINTER_BUTTON_MIDDLE
                        && hit_placement.is_none()
                        && self.session.last_hit_slot_id.as_deref() == Some("task-surface")
                        && self.window_manager.restore_recent_window();
                    let moving_window_workspace = matches!(event.state(), ButtonState::Pressed)
                        && button_code == POINTER_BUTTON_RIGHT
                        && hit_placement
                            .as_ref()
                            .filter(|placement| {
                                is_minimizable_window_policy(&placement.window_policy)
                            })
                            .map(|placement| {
                                self.window_manager
                                    .move_window_to_workspace_delta(&placement.window_key, 1)
                            })
                            .unwrap_or(false);
                    let finishing_grab = matches!(event.state(), ButtonState::Released)
                        && self.window_manager.pointer_operation.is_some();
                    let starting_grab = !minimizing_window
                        && !restoring_window
                        && !moving_window_workspace
                        && matches!(event.state(), ButtonState::Pressed)
                        && button_code != POINTER_BUTTON_RIGHT
                        && hit_placement
                            .as_ref()
                            .map(|placement| {
                                self.window_manager
                                    .begin_pointer_operation(placement, pointer_location)
                            })
                            .unwrap_or(false);
                    if !starting_grab
                        && !finishing_grab
                        && !minimizing_window
                        && !restoring_window
                        && !moving_window_workspace
                    {
                        if let Some(pointer) = self.seat.get_pointer() {
                            let button = PointerButtonEvent {
                                serial: SERIAL_COUNTER.next_serial(),
                                time: event.time_msec(),
                                button: button_code,
                                state: event.state(),
                            };
                            pointer.button(self, &button);
                            pointer.frame(self);
                        }
                    }
                    self.session.note_pointer_input(
                        format!("pointer-button:{}", button_state_label(event.state())),
                        None,
                    );
                    if minimizing_window || restoring_window || moving_window_workspace {
                        let _ = self.collect_toplevel_placements(window_size);
                        self.set_keyboard_focus(None);
                        return;
                    }
                    if matches!(event.state(), ButtonState::Pressed) {
                        if let Some(placement) = hit_placement.as_ref() {
                            self.set_keyboard_focus(Some(placement.surface.wl_surface().clone()));
                        }
                        if !starting_grab {
                            if let Some((surface, _)) = focus {
                                self.set_keyboard_focus(Some(surface));
                            } else {
                                self.activate_panel_host_slot("pointer-button");
                            }
                        }
                    } else if finishing_grab {
                        self.window_manager.finish_pointer_operation();
                        let _ = self.collect_toplevel_placements(window_size);
                    }
                }
                InputEvent::PointerAxis { event } => {
                    let _ = self.pointer_focus_from_last_location(window_size);
                    let horizontal_amount = event
                        .amount(Axis::Horizontal)
                        .or_else(|| {
                            event
                                .amount_v120(Axis::Horizontal)
                                .map(|value| value / 120.0)
                        })
                        .unwrap_or(0.0);
                    let vertical_amount = event
                        .amount(Axis::Vertical)
                        .or_else(|| event.amount_v120(Axis::Vertical).map(|value| value / 120.0))
                        .unwrap_or(0.0);
                    if self.maybe_cycle_workspace(vertical_amount)
                        || self.maybe_cycle_output(horizontal_amount)
                    {
                        let _ = self.collect_toplevel_placements(window_size);
                        self.session
                            .note_pointer_input("pointer-axis:window-manager", None);
                        return;
                    }
                    if let Some(pointer) = self.seat.get_pointer() {
                        let mut frame = AxisFrame::new(event.time_msec())
                            .source(event.source())
                            .relative_direction(
                                Axis::Horizontal,
                                event.relative_direction(Axis::Horizontal),
                            )
                            .relative_direction(
                                Axis::Vertical,
                                event.relative_direction(Axis::Vertical),
                            );
                        if let Some(amount) = event.amount(Axis::Horizontal) {
                            frame = frame.value(Axis::Horizontal, amount);
                        }
                        if let Some(amount) = event.amount(Axis::Vertical) {
                            frame = frame.value(Axis::Vertical, amount);
                        }
                        if let Some(v120) = event.amount_v120(Axis::Horizontal) {
                            frame = frame.v120(Axis::Horizontal, v120.round() as i32);
                        }
                        if let Some(v120) = event.amount_v120(Axis::Vertical) {
                            frame = frame.v120(Axis::Vertical, v120.round() as i32);
                        }
                        pointer.axis(self, frame);
                        pointer.frame(self);
                    }
                    self.session.note_pointer_input("pointer-axis", None);
                }
                InputEvent::TouchDown { event } => {
                    let location = absolute_location::<B, _>(&event, window_size);
                    let focus = self.pointer_focus_target(location, window_size);
                    if let Some(touch) = self.seat.get_touch() {
                        let down = TouchDownEvent {
                            slot: event.slot(),
                            location,
                            serial: SERIAL_COUNTER.next_serial(),
                            time: event.time_msec(),
                        };
                        touch.down(self, focus.clone(), &down);
                        touch.frame(self);
                    }
                    self.session.note_touch_input("touch-down");
                    if let Some((surface, _)) = focus {
                        self.set_keyboard_focus(Some(surface));
                    } else {
                        self.activate_panel_host_slot("touch-down");
                    }
                }
                InputEvent::TouchMotion { event } => {
                    let location = absolute_location::<B, _>(&event, window_size);
                    let focus = self.pointer_focus_target(location, window_size);
                    if let Some(touch) = self.seat.get_touch() {
                        let motion = TouchMotionEvent {
                            slot: event.slot(),
                            location,
                            time: event.time_msec(),
                        };
                        touch.motion(self, focus, &motion);
                        touch.frame(self);
                    }
                    self.session.note_touch_input("touch-motion");
                }
                InputEvent::TouchUp { event } => {
                    if let Some(touch) = self.seat.get_touch() {
                        let up = TouchUpEvent {
                            slot: event.slot(),
                            serial: SERIAL_COUNTER.next_serial(),
                            time: event.time_msec(),
                        };
                        touch.up(self, &up);
                        touch.frame(self);
                    }
                    self.session.note_touch_input("touch-up");
                }
                InputEvent::TouchCancel { .. } => {
                    if let Some(touch) = self.seat.get_touch() {
                        touch.cancel(self);
                    }
                    self.session.note_touch_input("touch-cancel");
                }
                InputEvent::TouchFrame { .. } => {
                    if let Some(touch) = self.seat.get_touch() {
                        touch.frame(self);
                    }
                    self.session.note_touch_input("touch-frame");
                }
                _ => {}
            }
        }
    }

    impl BufferHandler for App {
        fn buffer_destroyed(&mut self, _buffer: &WlBuffer) {}
    }

    impl CompositorHandler for App {
        fn compositor_state(&mut self) -> &mut CompositorState {
            &mut self.compositor_state
        }

        fn client_compositor_state<'a>(&self, client: &'a Client) -> &'a CompositorClientState {
            &client.get_data::<ClientState>().unwrap().compositor_state
        }

        fn commit(&mut self, surface: &WlSurface) {
            on_commit_buffer_handler::<Self>(surface);
            self.session.note_commit();
        }
    }

    impl XdgShellHandler for App {
        fn xdg_shell_state(&mut self) -> &mut XdgShellState {
            &mut self.xdg_shell_state
        }

        fn new_toplevel(&mut self, surface: ToplevelSurface) {
            let wl_surface = surface.wl_surface().clone();
            surface.with_pending_state(|state| {
                state.states.set(xdg_toplevel::State::Activated);
            });
            surface.send_configure();
            self.session.note_xdg_toplevel();
            self.set_keyboard_focus(Some(wl_surface));
        }

        fn new_popup(&mut self, surface: PopupSurface, positioner: PositionerState) {
            surface.with_pending_state(|state| {
                state.geometry = Rectangle::from_size(positioner.rect_size);
            });
            let _ = surface.send_configure();
            self.session.note_xdg_popup();
        }

        fn grab(
            &mut self,
            surface: PopupSurface,
            _seat: smithay::reexports::wayland_server::protocol::wl_seat::WlSeat,
            _serial: Serial,
        ) {
            let _ = surface.send_pending_configure();
        }

        fn ack_configure(&mut self, _surface: WlSurface, _configure: Configure) {}

        fn reposition_request(
            &mut self,
            surface: PopupSurface,
            positioner: PositionerState,
            token: u32,
        ) {
            surface.with_pending_state(|state| {
                state.geometry = Rectangle::from_size(positioner.rect_size);
                state.positioner = positioner;
            });
            surface.send_repositioned(token);
        }

        fn app_id_changed(&mut self, _surface: ToplevelSurface) {}

        fn title_changed(&mut self, _surface: ToplevelSurface) {}
    }

    impl ShmHandler for App {
        fn shm_state(&self) -> &ShmState {
            &self.shm_state
        }
    }

    impl SeatHandler for App {
        type KeyboardFocus = WlSurface;
        type PointerFocus = WlSurface;
        type TouchFocus = WlSurface;

        fn seat_state(&mut self) -> &mut SeatState<Self> {
            &mut self.seat_state
        }

        fn focus_changed(&mut self, _seat: &Seat<Self>, focused: Option<&WlSurface>) {
            self.session
                .set_focused_surface_id(focused.map(surface_label));
        }

        fn cursor_image(&mut self, _seat: &Seat<Self>, _image: CursorImageStatus) {}
    }

    impl AsMut<CompositorState> for App {
        fn as_mut(&mut self) -> &mut CompositorState {
            &mut self.compositor_state
        }
    }

    delegate_compositor!(App);
    delegate_seat!(App);
    delegate_shm!(App);
    delegate_xdg_shell!(App);

    struct NestedRenderer {
        backend: winit::WinitGraphicsBackend<GlesRenderer>,
        event_loop: winit::WinitEventLoop,
        start_time: Instant,
    }

    impl NestedRenderer {
        fn try_new() -> Result<Self, String> {
            match catch_unwind(AssertUnwindSafe(|| winit::init::<GlesRenderer>())) {
                Ok(Ok((backend, event_loop))) => Ok(Self {
                    backend,
                    event_loop,
                    start_time: Instant::now(),
                }),
                Ok(Err(err)) => Err(err.to_string()),
                Err(payload) => Err(panic_payload_message(payload)),
            }
        }

        fn dispatch_new_events(&mut self, app: &mut App) -> bool {
            let mut close_requested = false;
            let mut window_size = self.backend.window_size();
            let pump_status = self.event_loop.dispatch_new_events(|event| match event {
                WinitEvent::CloseRequested => {
                    close_requested = true;
                }
                WinitEvent::Focus(focused) => {
                    app.session.note_host_focus(focused);
                    if focused {
                        if app.session.focused_surface_id.is_none() {
                            let keyboard_focus = app.keyboard_focus_target(window_size);
                            app.set_keyboard_focus(keyboard_focus);
                        }
                    } else {
                        app.set_keyboard_focus(None);
                    }
                }
                WinitEvent::Resized { size, .. } => {
                    window_size = size;
                }
                WinitEvent::Input(input_event) => {
                    app.route_input_event(input_event, window_size);
                }
                WinitEvent::Redraw => {}
            });
            close_requested || matches!(pump_status, PumpStatus::Exit(_))
        }

        fn render(&mut self, app: &mut App) -> Result<u32, String> {
            let size = self.backend.window_size();
            if size.w == 0 || size.h == 0 {
                return Ok(0);
            }

            let damage = Rectangle::from_size(size);
            let placements = app.collect_toplevel_placements(size);
            for placement in &placements {
                configure_toplevel_for_placement(
                    &placement.surface,
                    &placement.placement,
                    &placement.window_policy,
                );
            }
            {
                let (renderer, mut framebuffer) =
                    self.backend.bind().map_err(|err| err.to_string())?;
                let elements = placements
                    .iter()
                    .flat_map(|placement| {
                        render_elements_from_surface_tree(
                            renderer,
                            placement.surface.wl_surface(),
                            (placement.placement.x, placement.placement.y),
                            1.0,
                            1.0,
                            Kind::Unspecified,
                        )
                    })
                    .collect::<Vec<WaylandSurfaceRenderElement<GlesRenderer>>>();

                let mut frame = renderer
                    .render(&mut framebuffer, size, Transform::Flipped180)
                    .map_err(|err| err.to_string())?;
                frame
                    .clear(Color32F::new(0.05, 0.08, 0.12, 1.0), &[damage])
                    .map_err(|err| err.to_string())?;
                draw_render_elements(&mut frame, 1.0, &elements, &[damage])
                    .map_err(|err| err.to_string())?;
                let _ = frame.finish().map_err(|err| err.to_string())?;
            }

            let frame_time = self.start_time.elapsed().as_millis() as u32;
            for surface in app.xdg_shell_state.toplevel_surfaces() {
                send_frames_surface_tree(surface.wl_surface(), frame_time);
            }

            self.backend
                .submit(Some(&[damage]))
                .map_err(|err| err.to_string())?;
            Ok(1)
        }
    }

    fn absolute_location<B, E>(event: &E, window_size: Size<i32, Physical>) -> Point<f64, Logical>
    where
        B: InputBackend,
        E: AbsolutePositionEvent<B>,
    {
        (
            event.x_transformed(window_size.w),
            event.y_transformed(window_size.h),
        )
            .into()
    }

    fn button_state_label(state: ButtonState) -> &'static str {
        match state {
            ButtonState::Pressed => "pressed",
            ButtonState::Released => "released",
        }
    }

    fn key_state_label(state: KeyState) -> &'static str {
        match state {
            KeyState::Pressed => "pressed",
            KeyState::Released => "released",
        }
    }

    fn configure_toplevel_for_placement(
        surface: &ToplevelSurface,
        placement: &SurfacePlacement,
        window_policy: &str,
    ) {
        let logical_size: Size<i32, Logical> = (placement.width, placement.height).into();
        surface.with_pending_state(|state| {
            state.size = Some(logical_size);
            state.bounds = Some(logical_size);
            state.states.set(xdg_toplevel::State::Activated);
            if window_policy.starts_with("workspace-fullscreen") {
                state.states.set(xdg_toplevel::State::Fullscreen);
            } else if window_policy.starts_with("workspace-maximized") {
                state.states.set(xdg_toplevel::State::Maximized);
            }
        });
        let _ = surface.send_pending_configure();
    }

    fn floating_window_placement(
        index: usize,
        window_size: Size<i32, Physical>,
        window_policy: &str,
    ) -> SurfacePlacement {
        match window_policy {
            "floating-dialog" => {
                let width = (window_size.w / 3).clamp(360, 680);
                let height = (window_size.h / 3).clamp(240, 440);
                SurfacePlacement {
                    zone: "center-modal",
                    anchor: "center",
                    x: (window_size.w - width) / 2,
                    y: (window_size.h - height) / 2,
                    width,
                    height,
                }
            }
            "floating-utility" => {
                let width = (window_size.w / 3).clamp(320, 520);
                let height = (window_size.h / 2).clamp(260, 560);
                let step_y = 28 * (index as i32);
                SurfacePlacement {
                    zone: "right-rail",
                    anchor: "top-right",
                    x: (window_size.w - width - 24).max(24),
                    y: (96 + step_y).clamp(24, (window_size.h - height - 24).max(24)),
                    width,
                    height,
                }
            }
            _ => {
                let width = (window_size.w / 2).clamp(360, 720);
                let height = (window_size.h * 3 / 5).clamp(280, 640);
                let step_x = 28 * (index as i32);
                let step_y = 22 * (index as i32);
                SurfacePlacement {
                    zone: "floating-stack",
                    anchor: "top-left",
                    x: ((window_size.w - width) / 2 + step_x)
                        .clamp(24, (window_size.w - width - 24).max(24)),
                    y: (72 + step_y).clamp(24, (window_size.h - height - 24).max(24)),
                    width,
                    height,
                }
            }
        }
    }

    fn toplevel_metadata(surface: &ToplevelSurface) -> ToplevelMetadata {
        with_states(surface.wl_surface(), |states| {
            let attributes = states
                .data_map
                .get::<XdgToplevelSurfaceData>()
                .unwrap()
                .lock()
                .unwrap();
            ToplevelMetadata {
                app_id: attributes.app_id.clone(),
                title: attributes.title.clone(),
            }
        })
    }

    fn toplevel_window_policy(metadata: &ToplevelMetadata) -> String {
        if metadata_has_token(metadata, &["dialog", "prompt", "chooser", "picker", "auth"]) {
            "floating-dialog".to_string()
        } else if metadata_has_token(
            metadata,
            &[
                "settings", "control", "status", "utility", "monitor", "audit",
            ],
        ) {
            "floating-utility".to_string()
        } else {
            "floating-workspace".to_string()
        }
    }

    fn metadata_has_token(metadata: &ToplevelMetadata, patterns: &[&str]) -> bool {
        let label = format!(
            "{} {}",
            metadata.app_id.as_deref().unwrap_or_default(),
            metadata.title.as_deref().unwrap_or_default()
        )
        .to_ascii_lowercase();
        patterns.iter().any(|pattern| label.contains(pattern))
    }

    fn surface_label(surface: &WlSurface) -> String {
        format!("wl_surface#{}", surface.id().protocol_id())
    }

    fn send_frames_surface_tree(surface: &WlSurface, time: u32) {
        with_surface_tree_downward(
            surface,
            (),
            |_, _, &()| TraversalAction::DoChildren(()),
            |_surface, states, &()| {
                for callback in states
                    .cached_state
                    .get::<SurfaceAttributes>()
                    .current()
                    .frame_callbacks
                    .drain(..)
                {
                    callback.done(time);
                }
            },
            |_, _, &()| true,
        );
    }

    fn panic_payload_message(payload: Box<dyn Any + Send>) -> String {
        match payload.downcast::<String>() {
            Ok(message) => *message,
            Err(payload) => match payload.downcast::<&'static str>() {
                Ok(message) => (*message).to_string(),
                Err(_) => "winit-init-panicked".to_string(),
            },
        }
    }

    fn ensure_runtime_dir() -> Result<Option<PathBuf>, Box<dyn Error>> {
        if env::var_os("XDG_RUNTIME_DIR").is_some() {
            return Ok(None);
        }

        let path = env::temp_dir().join(format!("aios-shell-runtime-{}", std::process::id()));
        fs::create_dir_all(&path)?;
        env::set_var("XDG_RUNTIME_DIR", &path);
        Ok(Some(path))
    }

    fn cleanup_runtime_dir(path: Option<PathBuf>) {
        if let Some(path) = path {
            let _ = fs::remove_dir_all(path);
        }
    }

    fn os_str_to_string(value: &OsStr) -> String {
        value.to_string_lossy().into_owned()
    }

    fn panel_action_summary(stdout: &str) -> Option<String> {
        if stdout.trim().is_empty() {
            return None;
        }
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(stdout) {
            if let Some(summary) = value.get("summary").and_then(|value| value.as_str()) {
                return Some(summary.to_string());
            }
            if let Some(result) = value.get("result") {
                return Some(clip_string(&result.to_string(), 160));
            }
        }
        Some(clip_string(stdout, 160))
    }

    fn panel_action_payload(stdout: &str) -> Option<serde_json::Value> {
        if stdout.trim().is_empty() {
            return None;
        }
        serde_json::from_str::<serde_json::Value>(stdout).ok()
    }

    fn panel_action_target_component(payload: Option<&serde_json::Value>) -> Option<String> {
        let payload = payload?;
        payload
            .get("target_component")
            .and_then(|value| value.as_str())
            .or_else(|| {
                payload
                    .get("result")
                    .and_then(|result| result.get("target_component"))
                    .and_then(|value| value.as_str())
            })
            .map(|value| value.to_string())
    }

    fn summarize_command_failure(stderr: &str, stdout: &str) -> Option<String> {
        let detail = if !stderr.is_empty() { stderr } else { stdout };
        if detail.is_empty() {
            None
        } else {
            Some(clip_string(detail, 160))
        }
    }

    fn clip_string(value: &str, limit: usize) -> String {
        let compact = value.split_whitespace().collect::<Vec<_>>().join(" ");
        if compact.len() <= limit {
            return compact;
        }
        format!("{}...", &compact[..limit.saturating_sub(3)])
    }
}

#[cfg(not(target_os = "linux"))]
mod mode {
    use super::*;

    pub const MODE_LABEL: &str = "smithay-unavailable-non-linux";

    pub fn mode_label(config: &Config) -> String {
        if matches!(
            config
                .compositor_backend
                .trim()
                .to_ascii_lowercase()
                .as_str(),
            "drm" | "drm-kms" | "kms" | "udev-drm" | "libseat-drm"
        ) {
            "drm-kms-unavailable-non-linux".to_string()
        } else {
            MODE_LABEL.to_string()
        }
    }

    pub fn run(config: &Config, tick_target: Option<u32>) -> Result<SessionState, Box<dyn Error>> {
        let mut session = SessionState::new(config);
        session.set_seat_name(Some(config.seat_name.clone()));
        session.set_pointer_status(if config.pointer_enabled {
            "configured-fallback"
        } else {
            "disabled"
        });
        session.set_keyboard_status(if config.keyboard_enabled {
            format!("configured-fallback(layout={})", config.keyboard_layout)
        } else {
            "disabled".to_string()
        });
        session.set_touch_status(if config.touch_enabled {
            "configured-fallback"
        } else {
            "disabled"
        });
        let mode_label = mode_label(config);
        session.set_session_control_status("inactive(non-linux)");
        session.set_smithay_status(mode_label.clone());
        session.set_renderer_backend("none");
        session.set_renderer_status(mode_label.clone());
        session.set_input_backend_status("inactive(non-linux)");
        session.set_xdg_shell_status(mode_label.clone());
        session.host_focus_status = mode_label;
        let mut runtime = RuntimeArtifacts::acquire(config, &mut session)?;
        runtime.publish_ready(&mut session)?;
        while tick_target
            .map(|target| session.ticks < target)
            .unwrap_or(true)
        {
            refresh_panel_host_snapshot(&mut session, config);
            session.tick();
            runtime.publish_running(&mut session)?;
            thread::sleep(Duration::from_millis(config.tick_ms));
        }
        session.finish();
        runtime.finish(&mut session)?;
        Ok(session)
    }

    pub fn probe(config: &Config) -> Result<SessionState, Box<dyn Error>> {
        let mut session = SessionState::new(config);
        session.set_seat_name(Some(config.seat_name.clone()));
        session.set_pointer_status(if config.pointer_enabled {
            "configured-fallback"
        } else {
            "disabled"
        });
        session.set_keyboard_status(if config.keyboard_enabled {
            format!("configured-fallback(layout={})", config.keyboard_layout)
        } else {
            "disabled".to_string()
        });
        session.set_touch_status(if config.touch_enabled {
            "configured-fallback"
        } else {
            "disabled"
        });
        let mode_label = mode_label(config);
        session.lifecycle_state = "probe-unavailable".to_string();
        session.set_session_control_status("inactive(non-linux)");
        session.set_smithay_status(mode_label.clone());
        session.set_renderer_backend("none");
        session.set_renderer_status(mode_label.clone());
        session.set_input_backend_status("inactive(non-linux)");
        session.set_xdg_shell_status(mode_label.clone());
        session.host_focus_status = mode_label;
        refresh_panel_host_snapshot(&mut session, config);
        Ok(session)
    }
}

#[cfg(test)]
mod tests {
    use super::{append_panel_action_event, record_panel_action_event, should_redirect_to_modal};
    use crate::config::Config;
    use crate::session::{PanelActionEvent, SessionState};
    use serde_json::json;
    use std::fs;

    #[test]
    fn appends_panel_action_events_to_jsonl() {
        let temp_dir = std::env::temp_dir().join(format!(
            "aios-shell-panel-action-log-{}",
            std::process::id()
        ));
        fs::create_dir_all(&temp_dir).unwrap();
        let path = temp_dir.join("panel-action-events.jsonl");
        let _ = fs::remove_file(&path);

        append_panel_action_event(
            &path,
            &PanelActionEvent {
                sequence: 2,
                event_id: "panel-action-event-000002".to_string(),
                kind: "panel-action.dispatch".to_string(),
                recorded_at_ms: 42,
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
                payload: Some(json!({"result": {"approval_ref": "approval-1"}})),
            },
        )
        .unwrap();

        let contents = fs::read_to_string(&path).unwrap();
        assert!(contents.contains("\"event_id\":\"panel-action-event-000002\""));
        assert!(contents.contains("\"kind\":\"panel-action.dispatch\""));
        assert!(contents.contains("\"approval_ref\":\"approval-1\""));

        fs::remove_file(path).unwrap();
        fs::remove_dir_all(temp_dir).unwrap();
    }

    #[test]
    fn record_panel_action_event_marks_memory_only_without_log_path() {
        let config = Config::default();
        let mut session = SessionState::new(&config);
        record_panel_action_event(
            &mut session,
            None,
            PanelActionEvent {
                sequence: 0,
                event_id: String::new(),
                kind: "panel-host.activation".to_string(),
                recorded_at_ms: 0,
                tick: 1,
                slot_id: Some("launcher".to_string()),
                component: Some("launcher".to_string()),
                panel_id: Some("launcher-panel".to_string()),
                action_id: Some("create-session".to_string()),
                input_kind: Some("pointer-button".to_string()),
                focus_policy: Some("retain-client-focus".to_string()),
                status: "activated".to_string(),
                summary: Some("launcher activated via pointer-button".to_string()),
                error: None,
                payload: None,
            },
        );

        assert_eq!(session.panel_action_event_count, 1);
        assert_eq!(session.panel_action_log_status, "memory-only");
        assert_eq!(
            session.last_panel_action_event_id.as_deref(),
            Some("panel-action-event-000001")
        );
    }

    #[test]
    fn modal_focus_redirect_blocks_non_modal_hits() {
        assert!(should_redirect_to_modal(
            Some("approval-panel"),
            Some("task-surface")
        ));
        assert!(should_redirect_to_modal(Some("approval-panel"), None));
        assert!(!should_redirect_to_modal(
            Some("approval-panel"),
            Some("approval-panel")
        ));
        assert!(!should_redirect_to_modal(None, Some("task-surface")));
    }
}
