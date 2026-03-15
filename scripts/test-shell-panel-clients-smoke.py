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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_python(script: Path, *args: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


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


def terminate(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-panel-clients-"))
    failed = False
    process: subprocess.Popen[str] | None = None

    try:
        launcher_fixture = temp_root / "launcher-fixture.json"
        chooser_fixture = temp_root / "chooser-fixture.json"
        profile = temp_root / "shell-profile.json"
        socket_path = temp_root / "panel-bridge.sock"

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
                    "chooser_id": "panel-clients-chooser",
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
                        },
                    },
                ],
            },
        )
        write_json(
            profile,
            {
                "profile_id": "shell-panel-clients-smoke",
                "desktop_host": "gtk",
                "session_backend": "compositor",
                "components": {
                    "launcher": True,
                    "portal_chooser": True,
                },
                "paths": {
                    "sessiond_socket": "/tmp/missing-sessiond.sock",
                },
            },
        )

        local_snapshot = json.loads(
            run_python(
                ROOT / "aios/shell/runtime/shell_panel_clients_gtk.py",
                "snapshot",
                "--profile",
                str(profile),
                "--session-id",
                "session-1",
                "--task-id",
                "task-1",
                "--launcher-fixture",
                str(launcher_fixture),
                "--chooser-fixture",
                str(chooser_fixture),
            )
        )
        require(local_snapshot["source"] == "local", "panel clients local snapshot source mismatch")
        require(
            local_snapshot["spawn_strategy"] == "process-per-component",
            "panel clients local spawn strategy mismatch",
        )
        require(local_snapshot["window_count"] == 2, "panel clients local window count mismatch")
        components = {item["component"] for item in local_snapshot["windows"]}
        require(components == {"launcher", "portal-chooser"}, "panel clients local components mismatch")
        chooser_window = next(item for item in local_snapshot["windows"] if item["component"] == "portal-chooser")
        require(chooser_window["window_title"] == "portal-chooser", "panel clients chooser title mismatch")
        require(chooser_window["selected_handle_id"] is None, "panel clients chooser selected handle mismatch")

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

        rpc_call(
            socket_path,
            "shell.panel.action.dispatch",
            {
                "slot_id": "portal-chooser",
                "component": "portal-chooser",
                "action_id": "prefer-requested",
                "input_kind": "pointer-button",
            },
        )

        bridge_snapshot = json.loads(
            run_python(
                ROOT / "aios/shell/runtime/shell_panel_clients_gtk.py",
                "snapshot",
                "--profile",
                str(profile),
                "--bridge-socket",
                str(socket_path),
                "--session-id",
                "session-1",
                "--task-id",
                "task-1",
                "--launcher-fixture",
                str(launcher_fixture),
                "--chooser-fixture",
                str(chooser_fixture),
            )
        )
        require(bridge_snapshot["source"] == "bridge", "panel clients bridge snapshot source mismatch")
        require(
            bridge_snapshot["spawn_strategy"] == "process-per-component",
            "panel clients bridge spawn strategy mismatch",
        )
        chooser_window = next(item for item in bridge_snapshot["windows"] if item["component"] == "portal-chooser")
        require(
            chooser_window["selected_handle_id"] == "handle-screen",
            "panel clients bridge chooser selection mismatch",
        )

        print("shell panel clients smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell panel clients smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
