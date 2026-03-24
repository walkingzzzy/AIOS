#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "aios/shell/compositor/Cargo.toml"
TEMP_ROOT_DIR = ROOT / "out" / "tmp"


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    temp_dir = make_temp_dir("aios-shell-compositor-")
    failed = False
    try:
        snapshot_path = temp_dir / "panel-snapshot.json"
        panel_action_log_path = Path(temp_dir) / "panel-action-events.jsonl"
        runtime_lock_path = Path(temp_dir) / "compositor.lock"
        runtime_ready_path = Path(temp_dir) / "compositor-ready.json"
        runtime_state_path = Path(temp_dir) / "compositor-state.json"
        window_state_path = Path(temp_dir) / "compositor-windows.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "profile_id": "shell-compositor-fallback",
                    "surface_count": 1,
                    "surfaces": [
                        {
                            "component": "launcher",
                            "panel_id": "fallback-launcher",
                            "status": "stale",
                            "tone": "warning",
                            "model": {"actions": [{"action_id": "noop"}]},
                        },
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        command_path = Path(temp_dir) / "panel-snapshot-command.py"
        command_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    'payload = {"snapshot": {"profile_id": "shell-compositor-smoke", "surface_count": 3, "surfaces": [',
                    '    {"component": "launcher", "panel_id": "launcher-panel", "status": "active", "tone": "positive", "model": {"actions": [{"action_id": "create-session"}], "sections": [{"section_id": "session"}]}},',
                    '    {"component": "approval-panel", "model": {"panel_id": "approval-panel-shell", "header": {"status": "pending", "tone": "warning"}, "actions": [{"action_id": "approve"}, {"action_id": "reject"}], "sections": [{"section_id": "approvals"}, {"section_id": "lanes"}]}},',
                    '    {"component": "notification-center", "panel_id": "notification-center-panel", "status": "info", "tone": "neutral", "model": {"actions": [{"action_id": "refresh"}], "sections": [{"section_id": "notifications"}]}}',
                    ']}, "artifacts": {"json": "/tmp/shell-compositor-smoke.json"}}',
                    "print(json.dumps(payload))",
                ]
            )
            + "\n"
        )
        config_path = Path(temp_dir) / "compositor.conf"
        config_path.write_text(
            "\n".join(
                [
                    "service_id = shell-compositor-smoke",
                    "desktop_host = gtk",
                    "session_backend = smithay-wayland-frontend",
                    "seat_name = seat-smoke",
                    "pointer_enabled = true",
                    "keyboard_enabled = true",
                    "touch_enabled = true",
                    "keyboard_layout = us",
                    "panel_slots = launcher,approval-panel,notification-center",
                    f"panel_snapshot_path = {snapshot_path}",
                    f"panel_snapshot_command = {sys.executable} {command_path}",
                    f"panel_action_log_path = {panel_action_log_path}",
                    f"runtime_lock_path = {runtime_lock_path}",
                    f"runtime_ready_path = {runtime_ready_path}",
                    f"runtime_state_path = {runtime_state_path}",
                    f"window_state_path = {window_state_path}",
                    "workspace_count = 4",
                    "default_workspace_index = 0",
                    "output_layout_mode = horizontal",
                    "runtime_state_refresh_ticks = 1",
                    "panel_snapshot_refresh_ticks = 1",
                    "tick_ms = 1",
                ]
            )
            + "\n"
        )

        completed = subprocess.run(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                str(MANIFEST),
                "--",
                "--config",
                str(config_path),
                "--once",
                "--emit-json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        require(stdout_lines, "compositor smoke produced no output")
        require(
            "starting shell compositor" in stdout_lines[0],
            "compositor smoke missing startup log",
        )

        payload = json.loads(stdout_lines[-1])
        require(payload["service_id"] == "shell-compositor-smoke", "compositor service_id mismatch")
        require(payload["runtime"] == "smithay-wayland-frontend", "compositor runtime mismatch")
        require(payload["desktop_host"] == "gtk", "compositor desktop host mismatch")
        require(payload["lifecycle_state"] == "stopped", "compositor lifecycle state mismatch")
        require(payload["ticks"] == 1, "compositor tick count mismatch")
        require(payload["surface_count"] == 3, "compositor surface count mismatch")
        require(payload["seat_name"] == "seat-smoke", "compositor seat_name mismatch")
        require(payload["runtime_lock_path"] == str(runtime_lock_path), "compositor runtime lock path mismatch")
        require(payload["runtime_ready_path"] == str(runtime_ready_path), "compositor runtime ready path mismatch")
        require(payload["runtime_state_path"] == str(runtime_state_path), "compositor runtime state path mismatch")
        require(payload["runtime_lock_status"] == "released", "compositor runtime lock status mismatch")
        require(payload["runtime_ready_status"] == "cleared", "compositor runtime ready status mismatch")
        require(
            payload["runtime_state_status"] == "published(stopped)",
            "compositor runtime state status mismatch",
        )
        require(
            payload["process_boundary_status"].startswith("released(pid="),
            "compositor process boundary status mismatch",
        )
        require("pointer_status" in payload, "compositor pointer status missing")
        require("keyboard_status" in payload, "compositor keyboard status missing")
        require("touch_status" in payload, "compositor touch status missing")
        require("compositor_backend" in payload, "compositor backend missing")
        require("process_boundary_status" in payload, "compositor process boundary status missing")
        require("runtime_lock_path" in payload, "compositor runtime lock path missing")
        require("runtime_ready_path" in payload, "compositor runtime ready path missing")
        require("runtime_state_path" in payload, "compositor runtime state path missing")
        require("runtime_lock_status" in payload, "compositor runtime lock status missing")
        require("runtime_ready_status" in payload, "compositor runtime ready status missing")
        require("runtime_state_status" in payload, "compositor runtime state status missing")
        require("session_control_status" in payload, "compositor session control status missing")
        require("drm_device_path" in payload, "compositor drm device path missing")
        require("drm_connector_name" in payload, "compositor drm connector name missing")
        require("drm_output_width" in payload, "compositor drm output width missing")
        require("drm_output_height" in payload, "compositor drm output height missing")
        require("drm_refresh_millihz" in payload, "compositor drm refresh missing")
        require("output_count" in payload, "compositor output count missing")
        require("connected_output_count" in payload, "compositor connected output count missing")
        require("primary_output_name" in payload, "compositor primary output name missing")
        require("renderable_output_count" in payload, "compositor renderable output count missing")
        require("non_renderable_output_count" in payload, "compositor non-renderable output count missing")
        require("release_grade_output_status" in payload, "compositor release-grade output status missing")
        require("workspace_toplevel_mode" in payload, "compositor workspace toplevel mode missing")
        require("workspace_count" in payload, "compositor workspace count missing")
        require("active_workspace_index" in payload, "compositor active workspace index missing")
        require("active_workspace_id" in payload, "compositor active workspace id missing")
        require("workspace_switch_count" in payload, "compositor workspace switch count missing")
        require("output_layout_mode" in payload, "compositor output layout mode missing")
        require("window_manager_status" in payload, "compositor window manager status missing")
        require("window_state_path" in payload, "compositor window state path missing")
        require("managed_window_count" in payload, "compositor managed window count missing")
        require("visible_window_count" in payload, "compositor visible window count missing")
        require("floating_window_count" in payload, "compositor floating window count missing")
        require("minimized_window_count" in payload, "compositor minimized window count missing")
        require("window_move_count" in payload, "compositor window move count missing")
        require("window_resize_count" in payload, "compositor window resize count missing")
        require("window_minimize_count" in payload, "compositor window minimize count missing")
        require("window_restore_count" in payload, "compositor window restore count missing")
        require("last_minimized_window_key" in payload, "compositor last minimized window key missing")
        require("last_restored_window_key" in payload, "compositor last restored window key missing")
        require("workspace_window_counts" in payload, "compositor workspace window counts missing")
        require("drag_state" in payload, "compositor drag state missing")
        require("resize_state" in payload, "compositor resize state missing")
        require("outputs" in payload, "compositor outputs missing")
        require("managed_windows" in payload, "compositor managed windows missing")
        require("modal_surface_count" in payload, "compositor modal surface count missing")
        require("blocked_surface_count" in payload, "compositor blocked surface count missing")
        require("shell_role_counts" in payload, "compositor shell role counts missing")
        require("interaction_mode_counts" in payload, "compositor interaction mode counts missing")
        require("window_policy_counts" in payload, "compositor window policy counts missing")
        require("panel_host_status" in payload, "compositor panel host status missing")
        require("panel_host_bound_count" in payload, "compositor panel host bound count missing")
        require("panel_host_activation_count" in payload, "compositor panel host activation count missing")
        require("panel_focus_status" in payload, "compositor panel focus status missing")
        require("last_panel_host_slot_id" in payload, "compositor last panel host slot id missing")
        require("last_panel_host_panel_id" in payload, "compositor last panel host panel id missing")
        require("panel_action_status" in payload, "compositor panel action status missing")
        require("panel_action_dispatch_count" in payload, "compositor panel action dispatch count missing")
        require("last_panel_action_slot_id" in payload, "compositor last panel action slot id missing")
        require("last_panel_action_panel_id" in payload, "compositor last panel action panel id missing")
        require("last_panel_action_id" in payload, "compositor last panel action id missing")
        require("last_panel_action_summary" in payload, "compositor last panel action summary missing")
        require(
            "last_panel_action_target_component" in payload,
            "compositor last panel action target component missing",
        )
        require("panel_action_event_count" in payload, "compositor panel action event count missing")
        require("last_panel_action_event_id" in payload, "compositor last panel action event id missing")
        require("panel_action_log_status" in payload, "compositor panel action log status missing")
        require("panel_action_log_path" in payload, "compositor panel action log path missing")
        require("panel_action_events" in payload, "compositor panel action events missing")
        require("panel_snapshot_source" in payload, "compositor panel snapshot source missing")
        require("panel_snapshot_profile_id" in payload, "compositor panel snapshot profile id missing")
        require("panel_snapshot_surface_count" in payload, "compositor panel snapshot surface count missing")
        require("panel_embedding_status" in payload, "compositor panel embedding status missing")
        require("embedded_surface_count" in payload, "compositor embedded surface count missing")
        require("stacking_status" in payload, "compositor stacking status missing")
        require("attention_surface_count" in payload, "compositor attention surface count missing")
        require("active_modal_surface_id" in payload, "compositor active modal surface missing")
        require(
            "primary_attention_surface_id" in payload,
            "compositor primary attention surface missing",
        )
        require("host_focus_status" in payload, "compositor host focus status missing")
        require("smithay_status" in payload, "compositor smithay status missing")
        require("renderer_backend" in payload, "compositor renderer backend missing")
        require("renderer_status" in payload, "compositor renderer status missing")
        require("input_backend_status" in payload, "compositor input backend status missing")
        require("input_device_count" in payload, "compositor input device count missing")
        require("input_event_count" in payload, "compositor input event count missing")
        require("keyboard_event_count" in payload, "compositor keyboard event count missing")
        require("pointer_event_count" in payload, "compositor pointer event count missing")
        require("touch_event_count" in payload, "compositor touch event count missing")
        require("last_input_event" in payload, "compositor last input event missing")
        require("focused_surface_id" in payload, "compositor focused surface id missing")
        require("topmost_surface_id" in payload, "compositor topmost surface id missing")
        require("topmost_slot_id" in payload, "compositor topmost slot id missing")
        require("last_hit_surface_id" in payload, "compositor last hit surface id missing")
        require("last_hit_slot_id" in payload, "compositor last hit slot id missing")
        require("last_pointer_x" in payload, "compositor last pointer x missing")
        require("last_pointer_y" in payload, "compositor last pointer y missing")
        require("rendered_frame_count" in payload, "compositor rendered frame count missing")
        require("xdg_shell_status" in payload, "compositor xdg shell status missing")
        require(payload["xdg_toplevel_count"] == 0, "compositor xdg toplevel count mismatch")
        require(payload["xdg_popup_count"] == 0, "compositor xdg popup count mismatch")
        require(payload["input_event_count"] == 0, "compositor input event count mismatch")
        require(payload["keyboard_event_count"] == 0, "compositor keyboard event count mismatch")
        require(payload["pointer_event_count"] == 0, "compositor pointer event count mismatch")
        require(payload["touch_event_count"] == 0, "compositor touch event count mismatch")
        require(payload["compositor_backend"] == "winit", "compositor backend mismatch")
        require(payload["panel_host_status"] == "ready(3/3)", "compositor panel host status mismatch")
        require(payload["panel_host_bound_count"] == 3, "compositor panel host bound count mismatch")
        require(payload["panel_host_activation_count"] == 0, "compositor panel host activation count mismatch")
        require(payload["panel_focus_status"] == "inactive", "compositor panel focus status mismatch")
        require(payload["last_panel_host_slot_id"] is None, "compositor last panel host slot id mismatch")
        require(payload["last_panel_host_panel_id"] is None, "compositor last panel host panel id mismatch")
        require(payload["panel_action_status"] == "idle", "compositor panel action status mismatch")
        require(payload["panel_action_dispatch_count"] == 0, "compositor panel action dispatch count mismatch")
        require(payload["last_panel_action_slot_id"] is None, "compositor last panel action slot id mismatch")
        require(payload["last_panel_action_panel_id"] is None, "compositor last panel action panel id mismatch")
        require(payload["last_panel_action_id"] is None, "compositor last panel action id mismatch")
        require(payload["last_panel_action_summary"] is None, "compositor last panel action summary mismatch")
        require(
            payload["last_panel_action_target_component"] is None,
            "compositor last panel action target mismatch",
        )
        require(payload["panel_action_event_count"] == 0, "compositor panel action event count mismatch")
        require(payload["last_panel_action_event_id"] is None, "compositor last panel action event id mismatch")
        require(payload["panel_action_log_status"] == "configured", "compositor panel action log status mismatch")
        require(payload["panel_action_log_path"] == str(panel_action_log_path), "compositor panel action log path mismatch")
        require(payload["panel_action_events"] == [], "compositor panel action events mismatch")
        require(payload["panel_snapshot_source"] == "command", "compositor panel snapshot source mismatch")
        require(payload["panel_snapshot_profile_id"] == "shell-compositor-smoke", "compositor panel snapshot profile id mismatch")
        require(payload["panel_snapshot_surface_count"] == 3, "compositor panel snapshot surface count mismatch")
        require(payload["panel_embedding_status"] == "panel-host-ready(3/3)", "compositor panel embedding status mismatch")
        require(payload["embedded_surface_count"] == 0, "compositor embedded surface count mismatch")
        require(payload["workspace_toplevel_mode"] == "maximized", "compositor workspace toplevel mode mismatch")
        require(payload["workspace_count"] == 4, "compositor workspace count mismatch")
        require(payload["active_workspace_index"] == 0, "compositor active workspace index mismatch")
        require(payload["active_workspace_id"] == "workspace-1", "compositor active workspace id mismatch")
        require(payload["workspace_switch_count"] == 0, "compositor workspace switch count mismatch")
        require(payload["output_layout_mode"] == "horizontal", "compositor output layout mode mismatch")
        require(payload["renderable_output_count"] == 1, "compositor renderable output count mismatch")
        require(payload["non_renderable_output_count"] == 0, "compositor non-renderable output count mismatch")
        require(
            payload["release_grade_output_status"] == "single-output(renderable=1/1)",
            "compositor release-grade output status mismatch",
        )
        require(payload["window_state_path"] == str(window_state_path), "compositor window state path mismatch")
        require(payload["managed_window_count"] == 0, "compositor managed window count mismatch")
        require(payload["visible_window_count"] == 0, "compositor visible window count mismatch")
        require(payload["floating_window_count"] == 0, "compositor floating window count mismatch")
        require(payload["minimized_window_count"] == 0, "compositor minimized window count mismatch")
        require(payload["window_move_count"] == 0, "compositor window move count mismatch")
        require(payload["window_resize_count"] == 0, "compositor window resize count mismatch")
        require(payload["window_minimize_count"] == 0, "compositor window minimize count mismatch")
        require(payload["window_restore_count"] == 0, "compositor window restore count mismatch")
        require(payload["last_minimized_window_key"] is None, "compositor last minimized window key mismatch")
        require(payload["last_restored_window_key"] is None, "compositor last restored window key mismatch")
        require(payload["workspace_window_counts"] == {}, "compositor workspace window counts mismatch")
        require(payload["drag_state"] == "idle", "compositor drag state mismatch")
        require(payload["resize_state"] == "idle", "compositor resize state mismatch")
        require(len(payload["outputs"]) == 1, "compositor outputs mismatch")
        require(payload["outputs"][0]["output_id"] == "display-1", "compositor primary output id mismatch")
        require(payload["outputs"][0]["primary"] is True, "compositor primary output flag mismatch")
        require(payload["outputs"][0]["renderable"] is True, "compositor renderable output flag mismatch")
        require(payload["managed_windows"] == [], "compositor managed windows mismatch")
        require(
            payload["window_manager_status"].startswith("persistent"),
            "compositor window manager status mismatch",
        )
        require(payload["modal_surface_count"] == 1, "compositor modal surface count mismatch")
        require(payload["blocked_surface_count"] == 2, "compositor blocked surface count mismatch")
        require(payload["shell_role_counts"]["dock"] == 1, "compositor dock role count mismatch")
        require(payload["shell_role_counts"]["modal"] == 1, "compositor modal role count mismatch")
        require(
            payload["interaction_mode_counts"]["blocked-by-modal"] == 2,
            "compositor blocked interaction count mismatch",
        )
        require(
            payload["window_policy_counts"]["modal-dialog"] == 1,
            "compositor modal window policy mismatch",
        )
        require(
            payload["stacking_status"] == "panel-host-stack(approval-panel)",
            "compositor stacking status mismatch",
        )
        require(payload["attention_surface_count"] == 1, "compositor attention surface count mismatch")
        require(
            payload["active_modal_surface_id"] == "approval-panel",
            "compositor active modal surface mismatch",
        )
        require(
            payload["primary_attention_surface_id"] == "approval-panel",
            "compositor primary attention surface mismatch",
        )
        require(payload["focused_surface_id"] is None, "compositor focused surface id mismatch")
        require(
            payload["topmost_surface_id"] == "approval-panel",
            "compositor topmost surface id mismatch",
        )
        require(payload["topmost_slot_id"] == "approval-panel", "compositor topmost slot id mismatch")
        require(payload["last_hit_surface_id"] is None, "compositor last hit surface id mismatch")
        require(payload["last_hit_slot_id"] is None, "compositor last hit slot id mismatch")
        require(payload["last_pointer_x"] is None, "compositor last pointer x mismatch")
        require(payload["last_pointer_y"] is None, "compositor last pointer y mismatch")
        require(payload["input_device_count"] == 0, "compositor input device count mismatch")
        surfaces = {surface["surface_id"]: surface for surface in payload["surfaces"]}
        require(surfaces["launcher"]["shell_role"] == "dock", "compositor launcher shell role mismatch")
        require(
            surfaces["approval-panel"]["interaction_mode"] == "modal",
            "compositor approval interaction mode mismatch",
        )
        require(
            surfaces["approval-panel"]["window_policy"] == "modal-dialog",
            "compositor approval window policy mismatch",
        )
        require(
            surfaces["notification-center"]["blocked_by"] == "approval-panel",
            "compositor notification blocked_by mismatch",
        )
        require(runtime_state_path.exists(), "compositor runtime state file missing")
        runtime_state = json.loads(runtime_state_path.read_text())
        require(runtime_state["phase"] == "stopped", "compositor runtime state phase mismatch")
        require(
            runtime_state["paths"]["lock"] == str(runtime_lock_path),
            "compositor runtime state lock path mismatch",
        )
        require(
            runtime_state["paths"]["ready"] == str(runtime_ready_path),
            "compositor runtime state ready path mismatch",
        )
        require(
            runtime_state["paths"]["state"] == str(runtime_state_path),
            "compositor runtime state state path mismatch",
        )
        require(
            runtime_state["session"]["runtime_lock_status"] == "released",
            "compositor runtime state lock status mismatch",
        )
        require(
            runtime_state["session"]["runtime_ready_status"] == "cleared",
            "compositor runtime state ready status mismatch",
        )
        require(
            runtime_state["session"]["runtime_state_status"] == "published(stopped)",
            "compositor runtime state status mismatch",
        )
        require(not runtime_lock_path.exists(), "compositor runtime lock should be cleaned up")
        require(not runtime_ready_path.exists(), "compositor runtime ready file should be cleaned up")
        if sys.platform.startswith("linux"):
            require(payload["smithay_status"] == "smithay-wayland-frontend", "linux smithay status mismatch")
            require(payload["renderer_backend"] == "winit-gles", "linux renderer backend mismatch")
            require(payload["session_control_status"] == "nested-active", "linux session control status mismatch")
            require(payload["renderer_status"] != "inactive", "linux renderer status mismatch")
            require(payload["xdg_shell_status"] == "registered", "linux xdg shell status mismatch")
            require(payload["socket_name"] is not None, "linux smithay socket missing")
            require(payload["pointer_status"] == "enabled", "linux pointer status mismatch")
            require(payload["keyboard_status"].startswith("enabled("), "linux keyboard status mismatch")
            require(payload["touch_status"] == "enabled", "linux touch status mismatch")
            require(payload["input_backend_status"] == "active(winit)", "linux input backend status mismatch")
            require(
                payload["host_focus_status"] in {"pending", "focused", "unfocused"},
                "linux host focus status mismatch",
            )
            require(
                payload["last_input_event"] is None
                or payload["last_input_event"].startswith("window-focus:"),
                "linux last input event mismatch",
            )
        else:
            require(
                payload["smithay_status"] == "smithay-unavailable-non-linux",
                "non-linux smithay fallback status mismatch",
            )
            require(
                payload["session_control_status"] == "inactive(non-linux)",
                "non-linux session control status mismatch",
            )
            require(payload["renderer_backend"] == "none", "non-linux renderer backend mismatch")
            require(
                payload["renderer_status"] == "smithay-unavailable-non-linux",
                "non-linux renderer fallback status mismatch",
            )
            require(
                payload["xdg_shell_status"] == "smithay-unavailable-non-linux",
                "non-linux xdg shell fallback status mismatch",
            )
            require(payload["pointer_status"] == "configured-fallback", "non-linux pointer status mismatch")
            require(
                payload["keyboard_status"].startswith("configured-fallback("),
                "non-linux keyboard status mismatch",
            )
            require(payload["touch_status"] == "configured-fallback", "non-linux touch status mismatch")
            require(
                payload["input_backend_status"] == "inactive(non-linux)",
                "non-linux input backend status mismatch",
            )
            require(
                payload["host_focus_status"] == "smithay-unavailable-non-linux",
                "non-linux host focus status mismatch",
            )
            require(payload["last_input_event"] is None, "non-linux last input event mismatch")
            drm_config_path = Path(temp_dir) / "compositor-drm.conf"
            drm_config_path.write_text(
                "\n".join(
                    [
                        "service_id = shell-compositor-drm-smoke",
                        "desktop_host = gtk",
                        "session_backend = smithay-wayland-frontend",
                        "compositor_backend = drm-kms",
                        "seat_name = seat-smoke",
                        f"panel_snapshot_path = {snapshot_path}",
                        f"panel_snapshot_command = {sys.executable} {command_path}",
                        "panel_snapshot_refresh_ticks = 1",
                        "tick_ms = 1",
                    ]
                )
                + "\n"
            )
            drm_completed = subprocess.run(
                [
                    "cargo",
                    "run",
                    "--quiet",
                    "--manifest-path",
                    str(MANIFEST),
                    "--",
                    "--config",
                    str(drm_config_path),
                    "--once",
                    "--emit-json",
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            drm_stdout_lines = [line for line in drm_completed.stdout.splitlines() if line.strip()]
            require(drm_stdout_lines, "drm compositor smoke produced no output")
            drm_payload = json.loads(drm_stdout_lines[-1])
            require(drm_payload["compositor_backend"] == "drm-kms", "drm compositor backend mismatch")
            require(
                drm_payload["smithay_status"] == "drm-kms-unavailable-non-linux",
                "drm compositor non-linux status mismatch",
            )
            require(
                drm_payload["renderer_status"] == "drm-kms-unavailable-non-linux",
                "drm compositor non-linux renderer status mismatch",
            )
        require(
            [item["surface_id"] for item in payload["surfaces"]] == ["launcher", "approval-panel", "notification-center"],
            "compositor surface ordering mismatch",
        )
        expected_focus_policy = {
            "launcher": "retain-client-focus",
            "approval-panel": "shell-modal",
            "notification-center": "retain-client-focus",
        }
        expected_reservation_status = {
            "launcher": "panel-host-reserved",
            "approval-panel": "panel-host-modal",
            "notification-center": "panel-host-reserved",
        }
        expected_primary_action = {
            "launcher": "create-session",
            "approval-panel": "approve",
            "notification-center": "refresh",
        }
        for item in payload["surfaces"]:
            require("layout_zone" in item, "compositor surface layout zone missing")
            require("layout_anchor" in item, "compositor surface layout anchor missing")
            require("layout_x" in item, "compositor surface layout x missing")
            require("layout_y" in item, "compositor surface layout y missing")
            require("layout_width" in item, "compositor surface layout width missing")
            require("layout_height" in item, "compositor surface layout height missing")
            require("stacking_layer" in item, "compositor surface stacking layer missing")
            require("z_index" in item, "compositor surface z_index missing")
            require("reservation_status" in item, "compositor surface reservation status missing")
            require("pointer_policy" in item, "compositor surface pointer policy missing")
            require("focus_policy" in item, "compositor surface focus policy missing")
            require("panel_host_status" in item, "compositor surface panel host status missing")
            require("panel_component" in item, "compositor surface panel component missing")
            require("panel_id" in item, "compositor surface panel id missing")
            require("panel_status" in item, "compositor surface panel status missing")
            require("panel_tone" in item, "compositor surface panel tone missing")
            require("panel_primary_action_id" in item, "compositor surface panel primary action id missing")
            require("panel_action_count" in item, "compositor surface panel action count missing")
            require("panel_section_count" in item, "compositor surface panel section count missing")
            require("panel_error" in item, "compositor surface panel error missing")
            require("embedding_status" in item, "compositor surface embedding status missing")
            require("embedded_surface_id" in item, "compositor surface embedded surface id missing")
            require("client_app_id" in item, "compositor surface client app id missing")
            require("client_title" in item, "compositor surface client title missing")
            require(item["panel_host_status"] == "snapshot-bound", "compositor surface panel host status mismatch")
            require(item["panel_component"] == item["surface_id"], "compositor surface panel component mismatch")
            require(
                item["reservation_status"] == expected_reservation_status[item["surface_id"]],
                "compositor surface reservation status mismatch",
            )
            require(item["pointer_policy"] == "interactive", "compositor surface pointer policy mismatch")
            require(item["focus_policy"] == expected_focus_policy[item["surface_id"]], "compositor surface focus policy mismatch")
            require(item["panel_primary_action_id"] == expected_primary_action[item["surface_id"]], "compositor surface primary action mismatch")
            require(item["embedding_status"] == "panel-host-ready", "compositor surface embedding status mismatch")
            require(item["embedded_surface_id"] is None, "compositor surface embedded surface id mismatch")
            require(item["client_app_id"] is None, "compositor surface client app id mismatch")
            require(item["client_title"] is None, "compositor surface client title mismatch")
            require(item["panel_error"] is None, "compositor surface panel error mismatch")

        print("shell compositor smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell compositor smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_dir}")
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

