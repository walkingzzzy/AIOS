#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_python(*args: str) -> str:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def main() -> int:
    temp_root = ROOT / ".tmp" / f"aios-shell-session-{uuid.uuid4().hex}"
    temp_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=False)
    previous_temp_root = os.environ.get("AIOS_SHELL_SESSION_TEMP_ROOT")
    if os.name != "nt" and Path("/tmp").exists():
        os.environ["AIOS_SHELL_SESSION_TEMP_ROOT"] = "/tmp"
    else:
        os.environ["AIOS_SHELL_SESSION_TEMP_ROOT"] = str((ROOT / ".tmp").resolve())
    try:
        marker_path = temp_root / "gtk-host-marker.json"
        fallback_marker_path = temp_root / "gtk-host-fallback-marker.json"
        fallback_tk_marker_path = temp_root / "tk-host-fallback-marker.json"
        standalone_gtk_marker_path = temp_root / "gtk-host-standalone-marker.json"
        standalone_tk_marker_path = temp_root / "tk-host-standalone-marker.json"
        panel_client_marker_path = temp_root / "gtk-panel-client-marker.json"
        host_script = temp_root / "mock-gtk-host.py"
        flaky_host_script = temp_root / "mock-gtk-host-flaky.py"
        panel_client_script = temp_root / "mock-gtk-panel-client.py"
        profile_path = temp_root / "formal-shell-profile.json"
        fallback_profile_path = temp_root / "formal-shell-profile-fallback.json"
        fallback_tk_profile_path = temp_root / "formal-shell-profile-fallback-tk.json"
        standalone_gtk_profile_path = temp_root / "standalone-gtk-shell-profile.json"
        standalone_tk_profile_path = temp_root / "standalone-tk-shell-profile.json"
        panel_client_profile_path = temp_root / "formal-shell-profile-panel-client.json"
        drm_plan_profile_path = temp_root / "formal-shell-profile-drm-plan.json"

        host_script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import os",
                    "import sys",
                    "from pathlib import Path",
                    "",
                    "marker = Path(sys.argv[1])",
                    "payload = {",
                    "    'entrypoint': os.environ.get('AIOS_SHELL_SESSION_ENTRYPOINT'),",
                    "    'active_backend': os.environ.get('AIOS_SHELL_SESSION_BACKEND_ACTIVE'),",
                    "    'desktop_host': os.environ.get('AIOS_SHELL_SESSION_DESKTOP_HOST'),",
                    "    'session_backend': os.environ.get('AIOS_SHELL_SESSION_BACKEND'),",
                    "    'host_launch_mode': os.environ.get('AIOS_SHELL_SESSION_HOST_LAUNCH_MODE'),",
                    "    'panel_clients_enabled': os.environ.get('AIOS_SHELL_SESSION_PANEL_CLIENTS_ENABLED'),",
                    "    'wayland_display': os.environ.get('WAYLAND_DISPLAY'),",
                    "    'xdg_runtime_dir': os.environ.get('XDG_RUNTIME_DIR'),",
                    "    'panel_bridge_socket': os.environ.get('AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET'),",
                    "    'panel_bridge_socket_ready': bool(os.environ.get('AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET')) and Path(os.environ['AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET']).exists(),",
                    "}",
                    "marker.write_text(json.dumps(payload, indent=2) + '\\n')",
                    "print(json.dumps(payload))",
                ]
            )
            + "\n"
        )
        host_script.chmod(0o755)
        flaky_host_script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import os",
                    "import sys",
                    "from pathlib import Path",
                    "",
                    "marker = Path(sys.argv[1])",
                    "payload = {",
                    "    'entrypoint': os.environ.get('AIOS_SHELL_SESSION_ENTRYPOINT'),",
                    "    'active_backend': os.environ.get('AIOS_SHELL_SESSION_BACKEND_ACTIVE'),",
                    "    'desktop_host': os.environ.get('AIOS_SHELL_SESSION_DESKTOP_HOST'),",
                    "    'session_backend': os.environ.get('AIOS_SHELL_SESSION_BACKEND'),",
                    "    'host_launch_mode': os.environ.get('AIOS_SHELL_SESSION_HOST_LAUNCH_MODE'),",
                    "    'panel_clients_enabled': os.environ.get('AIOS_SHELL_SESSION_PANEL_CLIENTS_ENABLED'),",
                    "    'wayland_display': os.environ.get('WAYLAND_DISPLAY'),",
                    "    'xdg_runtime_dir': os.environ.get('XDG_RUNTIME_DIR'),",
                    "    'panel_bridge_socket': os.environ.get('AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET'),",
                    "    'panel_bridge_socket_ready': bool(os.environ.get('AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET')) and Path(os.environ['AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET']).exists(),",
                    "}",
                    "marker.write_text(json.dumps(payload, indent=2) + '\\n')",
                    "if payload['active_backend'] == 'compositor':",
                    "    print(json.dumps({'failed': True, **payload}))",
                    "    raise SystemExit(9)",
                    "print(json.dumps(payload))",
                ]
            )
            + "\n"
        )
        flaky_host_script.chmod(0o755)
        panel_client_script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import os",
                    "import sys",
                    "from pathlib import Path",
                    "",
                    "marker = Path(sys.argv[1])",
                    "payload = {",
                    "    'entrypoint': os.environ.get('AIOS_SHELL_SESSION_ENTRYPOINT'),",
                    "    'active_backend': os.environ.get('AIOS_SHELL_SESSION_BACKEND_ACTIVE'),",
                    "    'desktop_host': os.environ.get('AIOS_SHELL_SESSION_DESKTOP_HOST'),",
                    "    'session_backend': os.environ.get('AIOS_SHELL_SESSION_BACKEND'),",
                    "    'host_launch_mode': os.environ.get('AIOS_SHELL_SESSION_HOST_LAUNCH_MODE'),",
                    "    'panel_clients_enabled': os.environ.get('AIOS_SHELL_SESSION_PANEL_CLIENTS_ENABLED'),",
                    "    'wayland_display': os.environ.get('WAYLAND_DISPLAY'),",
                    "    'xdg_runtime_dir': os.environ.get('XDG_RUNTIME_DIR'),",
                    "    'panel_bridge_socket': os.environ.get('AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET'),",
                    "    'panel_bridge_socket_ready': bool(os.environ.get('AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET')) and Path(os.environ['AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET']).exists(),",
                    "}",
                    "marker.write_text(json.dumps(payload, indent=2) + '\\n')",
                    "print(json.dumps(payload))",
                ]
            )
            + "\n"
        )
        panel_client_script.chmod(0o755)

        profile_path.write_text(
            json.dumps(
                {
                    "profile_id": "formal-shell-session-smoke",
                    "desktop_host": "gtk",
                    "session_backend": "compositor",
                    "session": {
                        "entrypoint": "formal",
                        "gtk_host_command": f"{sys.executable} {host_script} {marker_path}",
                        "nested_fallback": "standalone-gtk",
                        "compositor_required": False,
                    },
                    "components": {
                        "launcher": True,
                        "task_surface": True,
                        "approval_panel": True,
                        "notification_center": True,
                    },
                    "paths": {
                        "sessiond_socket": "/tmp/missing-sessiond.sock",
                        "policyd_socket": "/tmp/missing-policyd.sock",
                        "deviced_socket": "/tmp/missing-deviced.sock",
                        "updated_socket": "/tmp/missing-updated.sock",
                    },
                    "compositor": {
                        "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                        "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                        "panel_action_log_path": str((temp_root / "panel-action-events.jsonl").resolve()),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        fallback_profile_path.write_text(
            json.dumps(
                {
                    "profile_id": "formal-shell-session-fallback-smoke",
                    "desktop_host": "gtk",
                    "session_backend": "compositor",
                    "session": {
                        "entrypoint": "formal",
                        "gtk_host_command": f"{sys.executable} {flaky_host_script} {fallback_marker_path}",
                        "nested_fallback": "standalone-gtk",
                        "compositor_required": False,
                    },
                    "components": {
                        "launcher": True,
                        "task_surface": True,
                        "approval_panel": True,
                        "notification_center": True,
                    },
                    "paths": {
                        "sessiond_socket": "/tmp/missing-sessiond.sock",
                        "policyd_socket": "/tmp/missing-policyd.sock",
                        "deviced_socket": "/tmp/missing-deviced.sock",
                        "updated_socket": "/tmp/missing-updated.sock",
                    },
                    "compositor": {
                        "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                        "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                        "panel_action_log_path": str((temp_root / "panel-action-events-fallback.jsonl").resolve()),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        fallback_tk_profile_path.write_text(
            json.dumps(
                {
                    "profile_id": "formal-shell-session-fallback-tk-smoke",
                    "desktop_host": "gtk",
                    "session_backend": "compositor",
                    "session": {
                        "entrypoint": "formal",
                        "gtk_host_command": f"{sys.executable} {flaky_host_script} {fallback_marker_path}",
                        "tk_host_command": f"{sys.executable} {host_script} {fallback_tk_marker_path}",
                        "nested_fallback": "standalone-tk",
                        "compositor_required": False,
                    },
                    "components": {
                        "launcher": True,
                        "task_surface": True,
                    },
                    "paths": {
                        "sessiond_socket": "/tmp/missing-sessiond.sock",
                        "policyd_socket": "/tmp/missing-policyd.sock",
                        "deviced_socket": "/tmp/missing-deviced.sock",
                        "updated_socket": "/tmp/missing-updated.sock",
                    },
                    "compositor": {
                        "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                        "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                        "panel_action_log_path": str((temp_root / "panel-action-events-fallback-tk.jsonl").resolve()),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        standalone_gtk_profile_path.write_text(
            json.dumps(
                {
                    "profile_id": "standalone-gtk-shell-session-smoke",
                    "desktop_host": "gtk",
                    "session_backend": "standalone",
                    "session": {
                        "gtk_host_command": f"{sys.executable} {host_script} {standalone_gtk_marker_path}",
                    },
                    "components": {
                        "launcher": True,
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        standalone_tk_profile_path.write_text(
            json.dumps(
                {
                    "profile_id": "standalone-tk-shell-session-smoke",
                    "desktop_host": "tk",
                    "session_backend": "standalone",
                    "session": {
                        "tk_host_command": f"{sys.executable} {host_script} {standalone_tk_marker_path}",
                    },
                    "components": {
                        "launcher": True,
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        panel_client_profile_path.write_text(
            json.dumps(
                {
                    "profile_id": "formal-shell-session-panel-client-smoke",
                    "desktop_host": "gtk",
                    "session_backend": "compositor",
                    "session": {
                        "entrypoint": "formal",
                        "gtk_panel_client_command": f"{sys.executable} {panel_client_script} {panel_client_marker_path}",
                        "nested_fallback": "standalone-gtk",
                        "compositor_required": False,
                    },
                    "components": {
                        "launcher": True,
                        "task_surface": True,
                        "approval_panel": True,
                        "notification_center": True,
                    },
                    "paths": {
                        "sessiond_socket": "/tmp/missing-sessiond.sock",
                        "policyd_socket": "/tmp/missing-policyd.sock",
                        "deviced_socket": "/tmp/missing-deviced.sock",
                        "updated_socket": "/tmp/missing-updated.sock",
                    },
                    "compositor": {
                        "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                        "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                        "panel_action_log_path": str((temp_root / "panel-action-events-panel-client.jsonl").resolve()),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        drm_plan_profile_path.write_text(
            json.dumps(
                {
                    "profile_id": "formal-shell-session-drm-plan-smoke",
                    "desktop_host": "gtk",
                    "session_backend": "compositor",
                    "session": {
                        "entrypoint": "formal",
                        "nested_fallback": "standalone-gtk",
                        "compositor_required": False,
                    },
                    "components": {
                        "launcher": True,
                        "task_surface": True,
                    },
                    "compositor": {
                        "backend_mode": "drm-kms",
                        "drm_device_path": "/dev/dri/card7",
                        "drm_disable_connectors": True,
                        "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                        "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )

        plan_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_session.py"),
            "plan",
            "--profile",
            str(profile_path),
            "--json",
        )
        plan = json.loads(plan_output)
        require(plan["entrypoint"] == "formal", "shell session plan entrypoint mismatch")
        require(plan["desktop_host"] == "gtk", "shell session plan desktop host mismatch")
        require(plan["session_backend"] == "compositor", "shell session plan backend mismatch")
        require(
            plan["host_runtime"]["host_launch_mode"] == "external-command",
            "shell session host launch mode mismatch",
        )
        require(
            plan["host_runtime"]["panel_clients_enabled"] is False,
            "shell session explicit host command should disable panel clients",
        )
        require(
            plan["host_runtime"]["gtk_host_command"].endswith(str(marker_path)),
            "shell session host command mismatch",
        )
        require(
            plan["panel_host_bridge"]["enabled"] is True,
            "shell session should enable panel host bridge",
        )
        require(
            plan["panel_host_bridge"]["transport"] == "socket-service",
            "shell session bridge transport mismatch",
        )
        require(
            "shell_panel_bridge_service.py" in plan["panel_host_bridge"]["service_command"],
            "shell session bridge service command mismatch",
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_session.py"),
                "serve",
                "--profile",
                str(profile_path),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        require(completed.returncode == 0, "shell session serve did not exit cleanly")
        require(marker_path.exists(), "nested GTK host marker missing")

        marker = json.loads(marker_path.read_text())
        require(marker["entrypoint"] == "formal", "nested GTK host entrypoint mismatch")
        require(marker["active_backend"] == "compositor", "nested GTK host backend mismatch")
        require(marker["desktop_host"] == "gtk", "nested GTK host desktop host mismatch")
        require(marker["session_backend"] == "compositor", "nested GTK host session backend mismatch")
        require(marker["host_launch_mode"] == "external-command", "nested GTK host launch mode mismatch")
        require(marker["panel_clients_enabled"] == "false", "nested GTK host panel client flag mismatch")
        require(bool(marker["wayland_display"]), "nested GTK host missing WAYLAND_DISPLAY")
        require(bool(marker["xdg_runtime_dir"]), "nested GTK host missing XDG_RUNTIME_DIR")
        require(marker["panel_bridge_socket_ready"] is True, "nested GTK host missing panel bridge socket")

        fallback_completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_session.py"),
                "serve",
                "--profile",
                str(fallback_profile_path),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        require(
            fallback_completed.returncode == 0,
            "shell session fallback serve did not exit cleanly",
        )
        require(
            fallback_marker_path.exists(),
            "nested GTK fallback marker missing",
        )
        fallback_marker = json.loads(fallback_marker_path.read_text())
        require(
            fallback_marker["entrypoint"] == "formal",
            "nested GTK fallback entrypoint mismatch",
        )
        require(
            fallback_marker["active_backend"] == "standalone-fallback",
            "nested GTK fallback backend mismatch",
        )
        require(
            fallback_marker["desktop_host"] == "gtk",
            "nested GTK fallback desktop host mismatch",
        )
        require(
            fallback_marker["host_launch_mode"] == "external-command",
            "nested GTK fallback launch mode mismatch",
        )
        require(
            fallback_marker["panel_bridge_socket_ready"] is False,
            "standalone fallback should not rely on compositor panel bridge socket",
        )

        fallback_tk_completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_session.py"),
                "serve",
                "--profile",
                str(fallback_tk_profile_path),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        require(
            fallback_tk_completed.returncode == 0,
            "shell session fallback-tk serve did not exit cleanly",
        )
        require(fallback_tk_marker_path.exists(), "nested Tk fallback marker missing")
        fallback_tk_marker = json.loads(fallback_tk_marker_path.read_text())
        require(fallback_tk_marker["entrypoint"] == "formal", "nested Tk fallback entrypoint mismatch")
        require(
            fallback_tk_marker["active_backend"] == "standalone-fallback",
            "nested Tk fallback backend mismatch",
        )
        require(fallback_tk_marker["desktop_host"] == "tk", "nested Tk fallback desktop host mismatch")
        require(
            fallback_tk_marker["session_backend"] == "compositor",
            "nested Tk fallback session backend mismatch",
        )
        require(
            fallback_tk_marker["host_launch_mode"] == "external-command",
            "nested Tk fallback launch mode mismatch",
        )
        require(
            fallback_tk_marker["panel_bridge_socket_ready"] is False,
            "nested Tk fallback should not rely on compositor panel bridge socket",
        )

        standalone_gtk_plan_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_session.py"),
            "plan",
            "--profile",
            str(standalone_gtk_profile_path),
            "--json",
        )
        standalone_gtk_plan = json.loads(standalone_gtk_plan_output)
        require(standalone_gtk_plan["desktop_host"] == "gtk", "standalone GTK desktop host mismatch")
        require(standalone_gtk_plan["session_backend"] == "standalone", "standalone GTK backend mismatch")
        require(
            standalone_gtk_plan["host_runtime"]["host_launch_mode"] == "external-command",
            "standalone GTK launch mode mismatch",
        )
        require(
            standalone_gtk_plan["host_runtime"]["host_command"].endswith(str(standalone_gtk_marker_path)),
            "standalone GTK host command mismatch",
        )
        require(
            standalone_gtk_plan["host_runtime"]["panel_clients_enabled"] is False,
            "standalone GTK should not enable panel clients",
        )
        standalone_gtk_completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_session.py"),
                "serve",
                "--profile",
                str(standalone_gtk_profile_path),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        require(standalone_gtk_completed.returncode == 0, "standalone GTK serve did not exit cleanly")
        require(standalone_gtk_marker_path.exists(), "standalone GTK marker missing")
        standalone_gtk_marker = json.loads(standalone_gtk_marker_path.read_text())
        require(standalone_gtk_marker["entrypoint"] == "compatibility", "standalone GTK entrypoint mismatch")
        require(standalone_gtk_marker["active_backend"] == "standalone", "standalone GTK backend mismatch")
        require(standalone_gtk_marker["desktop_host"] == "gtk", "standalone GTK desktop host runtime mismatch")
        require(standalone_gtk_marker["session_backend"] == "standalone", "standalone GTK session backend mismatch")
        require(
            standalone_gtk_marker["host_launch_mode"] == "external-command",
            "standalone GTK host launch mode runtime mismatch",
        )
        require(
            standalone_gtk_marker["panel_clients_enabled"] == "false",
            "standalone GTK panel client flag mismatch",
        )
        require(not standalone_gtk_marker["wayland_display"], "standalone GTK should not get WAYLAND_DISPLAY")

        standalone_tk_plan_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_session.py"),
            "plan",
            "--profile",
            str(standalone_tk_profile_path),
            "--json",
        )
        standalone_tk_plan = json.loads(standalone_tk_plan_output)
        require(standalone_tk_plan["desktop_host"] == "tk", "standalone Tk desktop host mismatch")
        require(standalone_tk_plan["session_backend"] == "standalone", "standalone Tk backend mismatch")
        require(
            standalone_tk_plan["host_runtime"]["host_launch_mode"] == "external-command",
            "standalone Tk launch mode mismatch",
        )
        require(
            standalone_tk_plan["host_runtime"]["host_command"].endswith(str(standalone_tk_marker_path)),
            "standalone Tk host command mismatch",
        )
        standalone_tk_completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_session.py"),
                "serve",
                "--profile",
                str(standalone_tk_profile_path),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        require(standalone_tk_completed.returncode == 0, "standalone Tk serve did not exit cleanly")
        require(standalone_tk_marker_path.exists(), "standalone Tk marker missing")
        standalone_tk_marker = json.loads(standalone_tk_marker_path.read_text())
        require(standalone_tk_marker["entrypoint"] == "compatibility", "standalone Tk entrypoint mismatch")
        require(standalone_tk_marker["active_backend"] == "standalone", "standalone Tk backend mismatch")
        require(standalone_tk_marker["desktop_host"] == "tk", "standalone Tk desktop host runtime mismatch")
        require(
            standalone_tk_marker["host_launch_mode"] == "external-command",
            "standalone Tk host launch mode runtime mismatch",
        )
        require(
            standalone_tk_marker["panel_clients_enabled"] == "false",
            "standalone Tk panel client flag mismatch",
        )

        panel_client_plan_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_session.py"),
            "plan",
            "--profile",
            str(panel_client_profile_path),
            "--json",
        )
        panel_client_plan = json.loads(panel_client_plan_output)
        require(
            panel_client_plan["host_runtime"]["host_launch_mode"] == "python-gtk-panel-clients",
            "panel client session launch mode mismatch",
        )
        require(
            panel_client_plan["host_runtime"]["panel_clients_enabled"] is True,
            "panel client session should enable panel clients",
        )
        require(
            panel_client_plan["host_runtime"]["gtk_panel_client_command"].endswith(str(panel_client_marker_path)),
            "panel client session command mismatch",
        )
        drm_plan_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_session.py"),
            "plan",
            "--profile",
            str(drm_plan_profile_path),
            "--json",
        )
        drm_plan = json.loads(drm_plan_output)
        require(
            drm_plan["compositor"]["backend_mode"] == "drm-kms",
            "drm plan compositor backend mismatch",
        )
        require(
            drm_plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_BACKEND"] == "drm-kms",
            "drm plan backend env mismatch",
        )
        require(
            drm_plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_DRM_DEVICE_PATH"] == "/dev/dri/card7",
            "drm plan device env mismatch",
        )
        require(
            drm_plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_DRM_DISABLE_CONNECTORS"] == "true",
            "drm plan connector env mismatch",
        )

        panel_client_completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_session.py"),
                "serve",
                "--profile",
                str(panel_client_profile_path),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        require(
            panel_client_completed.returncode == 0,
            "panel client session serve did not exit cleanly",
        )
        require(panel_client_marker_path.exists(), "nested GTK panel client marker missing")
        panel_client_marker = json.loads(panel_client_marker_path.read_text())
        require(
            panel_client_marker["entrypoint"] == "formal",
            "nested GTK panel client entrypoint mismatch",
        )
        require(
            panel_client_marker["active_backend"] == "compositor",
            "nested GTK panel client backend mismatch",
        )
        require(
            panel_client_marker["desktop_host"] == "gtk",
            "nested GTK panel client desktop host mismatch",
        )
        require(
            panel_client_marker["host_launch_mode"] == "python-gtk-panel-clients",
            "nested GTK panel client launch mode mismatch",
        )
        require(
            panel_client_marker["panel_clients_enabled"] == "true",
            "nested GTK panel client flag mismatch",
        )
        require(
            bool(panel_client_marker["wayland_display"]),
            "nested GTK panel client missing WAYLAND_DISPLAY",
        )
        require(
            panel_client_marker["panel_bridge_socket_ready"] is True,
            "nested GTK panel client missing bridge socket",
        )

        print("shell session smoke passed")
        return 0
    finally:
        if previous_temp_root is None:
            os.environ.pop("AIOS_SHELL_SESSION_TEMP_ROOT", None)
        else:
            os.environ["AIOS_SHELL_SESSION_TEMP_ROOT"] = previous_temp_root
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
