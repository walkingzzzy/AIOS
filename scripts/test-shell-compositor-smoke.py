#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "aios/shell/compositor/Cargo.toml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aios-shell-compositor-") as temp_dir:
        snapshot_path = Path(temp_dir) / "panel-snapshot.json"
        panel_action_log_path = Path(temp_dir) / "panel-action-events.jsonl"
        runtime_lock_path = Path(temp_dir) / "compositor.lock"
        runtime_ready_path = Path(temp_dir) / "compositor-ready.json"
        runtime_state_path = Path(temp_dir) / "compositor-state.json"
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
                    "placeholder_surfaces = launcher,approval-panel,notification-center",
                    f"panel_snapshot_path = {snapshot_path}",
                    f"panel_snapshot_command = {sys.executable} {command_path}",
                    f"panel_action_log_path = {panel_action_log_path}",
                    f"runtime_lock_path = {runtime_lock_path}",
                    f"runtime_ready_path = {runtime_ready_path}",
                    f"runtime_state_path = {runtime_state_path}",
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
        require("output_count" in payload, "compositor output count missing")
        require("connected_output_count" in payload, "compositor connected output count missing")
        require("primary_output_name" in payload, "compositor primary output name missing")
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
        require(
            payload["stacking_status"] == "panel-host-only(approval-panel)",
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
        require(payload["last_hit_surface_id"] is None, "compositor last hit surface id mismatch")
        require(payload["last_hit_slot_id"] is None, "compositor last hit slot id mismatch")
        require(payload["last_pointer_x"] is None, "compositor last pointer x mismatch")
        require(payload["last_pointer_y"] is None, "compositor last pointer y mismatch")
        require(payload["input_device_count"] == 0, "compositor input device count mismatch")
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


if __name__ == "__main__":
    raise SystemExit(main())
