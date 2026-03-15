#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPOSITOR_MANIFEST = ROOT / "aios/shell/compositor/Cargo.toml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float = 2.0) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(str(response["error"]))
    return response["result"]


def wait_for_bridge(socket_path: Path, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if socket_path.exists():
            try:
                rpc_call(socket_path, "system.health.get", {})
                return
            except Exception:
                time.sleep(0.05)
                continue
        time.sleep(0.05)
    raise TimeoutError(f"panel bridge socket not ready: {socket_path}")


def terminate(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    if process.stdout:
        return process.stdout.read().strip()
    return ""


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-panel-bridge-"))
    failed = False
    process: subprocess.Popen[str] | None = None

    try:
        launcher_fixture = temp_root / "launcher-fixture.json"
        chooser_fixture = temp_root / "chooser-fixture.json"
        profile = temp_root / "shell-profile.json"
        socket_path = temp_root / "panel-bridge.sock"
        panel_action_log = temp_root / "panel-action-events.jsonl"

        write_json(
            launcher_fixture,
            {
                "sessions": [
                    {
                        "session_id": "session-1",
                        "user_id": "user-1",
                        "created_at": "2026-03-09T00:00:00Z",
                        "status": "active",
                    }
                ],
                "tasks": [
                    {
                        "task_id": "task-1",
                        "session_id": "session-1",
                        "state": "planned",
                        "title": "prepare support handoff",
                        "created_at": "2026-03-09T00:01:00Z",
                    }
                ],
            },
        )
        write_json(
            chooser_fixture,
            {
                "request": {
                    "chooser_id": "bridge-chooser",
                    "title": "Choose Screen Share Target",
                    "status": "pending",
                    "requested_kinds": ["screen_share_handle"],
                    "selection_mode": "single",
                    "approval_status": "not-required",
                    "attempt_count": 0,
                    "max_attempts": 2,
                },
                "handles": [
                    {
                        "handle_id": "handle-file",
                        "kind": "file_handle",
                        "target": "/workspace/notes.txt",
                    },
                    {
                        "handle_id": "handle-screen",
                        "kind": "screen_share_handle",
                        "target": "screen://current-display",
                        "scope": {
                            "display_name": "Current Display",
                            "backend": "pipewire",
                        },
                    },
                ],
            },
        )
        write_json(
            profile,
            {
                "profile_id": "shell-panel-bridge-smoke",
                "desktop_host": "gtk",
                "session_backend": "compositor",
                "components": {
                    "launcher": True,
                    "portal_chooser": True,
                },
                "paths": {
                    "sessiond_socket": "/tmp/missing-sessiond.sock",
                },
                "compositor": {
                    "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                    "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                    "panel_action_log_path": str(panel_action_log),
                },
            },
        )

        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_panel_bridge_service.py"),
                "--profile",
                str(profile),
                "--socket-path",
                str(socket_path),
                "--session-id",
                "session-1",
                "--task-id",
                "task-1",
                "--launcher-fixture",
                str(launcher_fixture),
                "--chooser-fixture",
                str(chooser_fixture),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_bridge(socket_path)

        health = rpc_call(socket_path, "system.health.get", {})
        require(health["status"] == "ready", "panel bridge health mismatch")
        require(health["profile_id"] == "shell-panel-bridge-smoke", "panel bridge profile mismatch")

        snapshot = rpc_call(socket_path, "shell.panel.snapshot.get", {})
        require(snapshot["profile_id"] == "shell-panel-bridge-smoke", "panel bridge snapshot profile mismatch")
        require(snapshot["surface_count"] == 2, "panel bridge snapshot surface count mismatch")
        require(
            snapshot["summary"]["active_modal_surface"] == "portal-chooser",
            "panel bridge snapshot active modal mismatch",
        )

        action = rpc_call(
            socket_path,
            "shell.panel.action.dispatch",
            {
                "slot_id": "portal-chooser",
                "component": "portal-chooser",
                "action_id": "prefer-requested",
                "input_kind": "pointer-button",
            },
        )
        require(action["component"] == "portal-chooser", "panel bridge action component mismatch")
        require(action["action_id"] == "prefer-requested", "panel bridge action id mismatch")
        require(
            action["result"]["selected_handle_id"] == "handle-screen",
            "panel bridge action selected handle mismatch",
        )

        selected_snapshot = rpc_call(socket_path, "shell.panel.snapshot.get", {})
        chooser_surface = next(
            surface for surface in selected_snapshot["surfaces"] if surface["component"] == "portal-chooser"
        )
        require(
            chooser_surface["model"]["meta"]["selected_handle_id"] == "handle-screen",
            "panel bridge selected snapshot mismatch",
        )

        compositor_config = temp_root / "compositor.conf"
        compositor_config.write_text(
            "\n".join(
                [
                    "service_id = shell-panel-bridge-smoke",
                    "desktop_host = gtk",
                    "session_backend = smithay-wayland-frontend",
                    "seat_name = seat-bridge",
                    "pointer_enabled = true",
                    "keyboard_enabled = true",
                    "touch_enabled = false",
                    "keyboard_layout = us",
                    "placeholder_surfaces = launcher,portal-chooser",
                    f"panel_bridge_socket = {socket_path}",
                    f"panel_action_log_path = {panel_action_log}",
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
                str(COMPOSITOR_MANIFEST),
                "--",
                "--config",
                str(compositor_config),
                "--once",
                "--emit-json",
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        require(lines, "panel bridge compositor smoke produced no output")
        payload = json.loads(lines[-1])
        require(payload["panel_snapshot_source"] == "socket", "panel bridge compositor socket source mismatch")
        require(payload["panel_host_status"] == "ready(2/2)", "panel bridge compositor host status mismatch")
        require(payload["panel_snapshot_surface_count"] == 2, "panel bridge compositor surface count mismatch")

        print("shell panel bridge service smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell panel bridge service smoke failed: {error}")
        return 1
    finally:
        if process is not None:
            output = terminate(process)
            if failed and output:
                print("\n--- panel bridge log ---")
                print(output)
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
