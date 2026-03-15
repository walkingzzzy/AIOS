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
    use crate::session::SessionState;
    use crate::surfaces::{
        match_panel_slot, placement_contains_point, placement_z_index, surface_contains_point,
        surface_placement, SurfacePlacement,
    };
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
            PointerAxisEvent, PointerButtonEvent as BackendPointerButtonEvent,
            PointerMotionAbsoluteEvent, PointerMotionEvent, TouchEvent,
        },
        libinput::{LibinputInputBackend, LibinputSessionInterface},
        renderer::{
            element::{
                surface::{render_elements_from_surface_tree, WaylandSurfaceRenderElement},
                Kind,
            },
            gles::GlesRenderer,
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

    fn select_primary_drm_output(device: &DrmDevice) -> Result<DrmSelectedOutput, String> {
        let resources = device
            .resource_handles()
            .map_err(|error| format!("drm-resources-unavailable:{error}"))?;
        let mut used_crtcs = Vec::new();

        for connector_handle in resources.connectors() {
            let info = device
                .get_connector(*connector_handle, true)
                .map_err(|error| format!("drm-connector-query-failed:{error}"))?;
            if info.state() != connector::State::Connected {
                continue;
            }
            let Some(mode) = info.modes().first().copied() else {
                continue;
            };
            let Some(crtc) = select_crtc_for_connector(device, &resources, &info, &used_crtcs)
            else {
                continue;
            };
            used_crtcs.push(crtc);
            let connector_name = format!("{:?}-{}", info.interface(), info.interface_id());
            let (width, height) = mode.size();
            let physical_size_mm = info
                .size()
                .map(|(w, h)| (i32::try_from(w).unwrap_or(0), i32::try_from(h).unwrap_or(0)))
                .unwrap_or((0, 0));
            return Ok(DrmSelectedOutput {
                connector: *connector_handle,
                connector_name,
                physical_size_mm,
                subpixel: info.subpixel().into(),
                crtc,
                mode,
                output_mode: OutputMode::from(mode),
                output_size: Size::from((i32::from(width), i32::from(height))),
            });
        }

        Err("drm-output-not-available".to_string())
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
        session.set_drm_topology(
            Some(drm_path.display().to_string()),
            drm_probe.output_count,
            drm_probe.connected_output_count,
            drm_probe.primary_output_name.clone(),
        );
        let selected_output = select_primary_drm_output(&drm_device)?;

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
                configure_toplevel_for_placement(&placement.surface, &placement.placement);
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
            .map_err(|error| {
                format!("libinput-seat-assign-failed({}):{error}", config.seat_name)
            })?;
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

    fn probe_drm_outputs(device: &DrmDevice) -> Result<DrmProbe, String> {
        let resources = device
            .resource_handles()
            .map_err(|error| format!("drm-resources-unavailable:{error}"))?;
        let mut connected_output_count = 0;
        let mut active_output_count = 0;
        let mut plane_count = 0;
        let mut primary_output_name = None;
        let mut primary_output_size = None;
        let mut used_crtcs = Vec::new();

        for connector_handle in resources.connectors() {
            let info = device
                .get_connector(*connector_handle, true)
                .map_err(|error| format!("drm-connector-query-failed:{error}"))?;
            let connector_name = format!("{:?}-{}", info.interface(), info.interface_id());
            let is_connected = info.state() == connector::State::Connected;
            if is_connected {
                connected_output_count += 1;
                if primary_output_name.is_none() {
                    primary_output_name = Some(connector_name.clone());
                }
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

        Ok(DrmProbe {
            output_count: resources.connectors().len() as u32,
            connected_output_count,
            active_output_count,
            primary_output_name,
            primary_output_size,
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
                if !used_crtcs.contains(crtc) {
                    return Some(*crtc);
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
            self.session
                .surfaces
                .iter()
                .filter(|surface| {
                    surface.panel_component.is_some() && surface.focus_policy == "shell-modal"
                })
                .max_by_key(|surface| surface.z_index)
                .map(|surface| surface.surface_id.clone())
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
            let mut process = Command::new("/bin/sh");
            process.arg("-lc").arg(command);
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

            for (index, surface) in toplevels.into_iter().enumerate() {
                let metadata = toplevel_metadata(&surface);
                let slot_id = match_panel_slot(
                    &available_slots,
                    &used_slots,
                    metadata.app_id.as_deref(),
                    metadata.title.as_deref(),
                );
                let placement = match &slot_id {
                    Some(slot_id) => {
                        let placement = surface_placement(slot_id, window_size.w, window_size.h);
                        used_slots.push(slot_id.clone());
                        self.session.bind_surface_embedding(
                            slot_id,
                            surface_label(surface.wl_surface()),
                            metadata.app_id.clone(),
                            metadata.title.clone(),
                        );
                        placement
                    }
                    None => floating_window_placement(index, window_size),
                };
                let z_index = placement_z_index(placement.zone);
                placements.push(ToplevelPlacement {
                    surface,
                    slot_id,
                    sequence: index,
                    z_index,
                    placement,
                });
            }

            placements.sort_by_key(|placement| (placement.z_index, placement.sequence));
            self.session.note_stacking(
                placements
                    .last()
                    .map(|placement| surface_label(placement.surface.wl_surface())),
            );
            placements
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
                    let focus = self.pointer_focus_from_last_location(window_size);
                    if let Some(pointer) = self.seat.get_pointer() {
                        let button = PointerButtonEvent {
                            serial: SERIAL_COUNTER.next_serial(),
                            time: event.time_msec(),
                            button: event.button_code(),
                            state: event.state(),
                        };
                        pointer.button(self, &button);
                        pointer.frame(self);
                    }
                    self.session.note_pointer_input(
                        format!("pointer-button:{}", button_state_label(event.state())),
                        None,
                    );
                    if matches!(event.state(), ButtonState::Pressed) {
                        if let Some((surface, _)) = focus {
                            self.set_keyboard_focus(Some(surface));
                        } else {
                            self.activate_panel_host_slot("pointer-button");
                        }
                    }
                }
                InputEvent::PointerAxis { event } => {
                    let _ = self.pointer_focus_from_last_location(window_size);
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
                configure_toplevel_for_placement(&placement.surface, &placement.placement);
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

    fn configure_toplevel_for_placement(surface: &ToplevelSurface, placement: &SurfacePlacement) {
        let logical_size: Size<i32, Logical> = (placement.width, placement.height).into();
        surface.with_pending_state(|state| {
            state.size = Some(logical_size);
            state.bounds = Some(logical_size);
            state.states.set(xdg_toplevel::State::Activated);
        });
        let _ = surface.send_pending_configure();
    }

    fn floating_window_placement(
        index: usize,
        window_size: Size<i32, Physical>,
    ) -> SurfacePlacement {
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
