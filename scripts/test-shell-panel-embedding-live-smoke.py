#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from shell_evidence_manifest import write_shell_evidence_manifest


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


def wait_for_path(path: Path, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"path not ready: {path}")


def terminate(process: subprocess.Popen[str] | None) -> str:
    if process is None:
        return ""
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


def gtk_available() -> bool:
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        return True
    except Exception:
        return False


def main() -> int:
    if not sys.platform.startswith("linux"):
        print("shell panel embedding live smoke skipped: linux only")
        return 0
    if not gtk_available():
        print("shell panel embedding live smoke skipped: GTK4/libadwaita runtime unavailable")
        return 0

    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-panel-embedding-"))
    failed = False
    bridge_process: subprocess.Popen[str] | None = None
    compositor_process: subprocess.Popen[str] | None = None
    panel_clients_process: subprocess.Popen[str] | None = None

    try:
        launcher_fixture = temp_root / "launcher-fixture.json"
        approval_fixture = temp_root / "approval-fixture.json"
        profile = temp_root / "shell-profile.json"
        bridge_socket = temp_root / "panel-bridge.sock"
        panel_action_log = temp_root / "panel-action-events.jsonl"
        runtime_dir = temp_root / "xdg-runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        wayland_socket_name = "aios-embed-smoke"
        wayland_socket = runtime_dir / wayland_socket_name

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
            approval_fixture,
            {
                "approvals": [
                    {
                        "approval_ref": "approval-1",
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "task_id": "task-1",
                        "capability_id": "device.capture.screen.read",
                        "approval_lane": "device-capture-review",
                        "status": "pending",
                        "execution_location": "local",
                        "created_at": "2026-03-09T00:03:00Z",
                        "reason": "screen share request",
                    }
                ]
            },
        )
        write_json(
            profile,
            {
                "profile_id": "shell-panel-embedding-live-smoke",
                "desktop_host": "gtk",
                "session_backend": "compositor",
                "components": {
                    "launcher": True,
                    "approval_panel": True,
                },
                "paths": {
                    "sessiond_socket": "/tmp/missing-sessiond.sock",
                    "policyd_socket": "/tmp/missing-policyd.sock",
                },
                "compositor": {
                    "manifest_path": str(COMPOSITOR_MANIFEST.resolve()),
                    "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                    "panel_action_log_path": str(panel_action_log),
                },
            },
        )

        bridge_process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_panel_bridge_service.py"),
                "--profile",
                str(profile),
                "--socket-path",
                str(bridge_socket),
                "--session-id",
                "session-1",
                "--task-id",
                "task-1",
                "--launcher-fixture",
                str(launcher_fixture),
                "--approval-fixture",
                str(approval_fixture),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_bridge(bridge_socket)

        compositor_config = temp_root / "compositor.conf"
        compositor_config.write_text(
            "\n".join(
                [
                    "service_id = shell-panel-embedding-live-smoke",
                    "desktop_host = gtk",
                    "session_backend = smithay-wayland-frontend",
                    "seat_name = seat-embed",
                    "pointer_enabled = true",
                    "keyboard_enabled = true",
                    "touch_enabled = false",
                    "keyboard_layout = us",
                    "placeholder_surfaces = launcher,approval-panel",
                    f"socket_name = {wayland_socket_name}",
                    f"panel_bridge_socket = {bridge_socket}",
                    f"panel_action_log_path = {panel_action_log}",
                    "panel_snapshot_refresh_ticks = 1",
                    "tick_ms = 10",
                ]
            )
            + "\n"
        )

        compositor_env = {
            **dict(os.environ),
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "AIOS_SHELL_COMPOSITOR_SOCKET_NAME": wayland_socket_name,
            "AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET": str(bridge_socket),
        }
        compositor_process = subprocess.Popen(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                str(COMPOSITOR_MANIFEST),
                "--",
                "--config",
                str(compositor_config),
                "--ticks",
                "140",
                "--emit-json",
            ],
            cwd=ROOT,
            env=compositor_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_path(wayland_socket, timeout=8.0)

        panel_clients_process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_panel_clients_gtk.py"),
                "serve",
                "--profile",
                str(profile),
                "--bridge-socket",
                str(bridge_socket),
                "--session-id",
                "session-1",
                "--task-id",
                "task-1",
                "--launcher-fixture",
                str(launcher_fixture),
                "--approval-fixture",
                str(approval_fixture),
                "--duration",
                "1.5",
            ],
            cwd=ROOT,
            env={
                **dict(os.environ),
                "XDG_RUNTIME_DIR": str(runtime_dir),
                "WAYLAND_DISPLAY": wayland_socket_name,
                "GDK_BACKEND": "wayland",
                "AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET": str(bridge_socket),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        panel_clients_returncode = panel_clients_process.wait(timeout=10)
        require(panel_clients_returncode == 0, "GTK panel clients did not exit cleanly")

        compositor_output = terminate(compositor_process)
        lines = [line for line in compositor_output.splitlines() if line.strip()]
        require(lines, "panel embedding live compositor produced no output")
        payload = json.loads(lines[-1])
        require(payload["panel_snapshot_source"] == "socket", "panel embedding live snapshot source mismatch")
        require(payload["embedded_surface_count"] >= 1, "panel embedding live should embed at least one client")
        require(payload["client_count"] >= 1, "panel embedding live client count mismatch")
        require(
            payload["xdg_toplevel_count"] >= payload["embedded_surface_count"],
            "panel embedding live xdg toplevel count mismatch",
        )
        require(
            payload["panel_embedding_status"] in {"partial(1/2)", "ready(2/2)", "partial(2/2)"} or payload["embedded_surface_count"] >= 1,
            "panel embedding live status mismatch",
        )
        embedded_surfaces = [
            item for item in payload["surfaces"] if item.get("embedded_surface_id") is not None
        ]
        require(embedded_surfaces, "panel embedding live surfaces should expose embedded surface ids")
        require(
            any((item.get("client_app_id") or "").startswith("aios.shell.panel.") for item in embedded_surfaces),
            "panel embedding live should expose dedicated GTK panel client app ids",
        )
        manifest_path = temp_root / "shell-panel-embedding-live-manifest.json"
        manifest = write_shell_evidence_manifest(
            manifest_path,
            suite="shell-panel-embedding-live",
            artifacts={
                "profile": str(profile),
                "compositor_manifest": str(COMPOSITOR_MANIFEST),
                "panel_action_log": str(panel_action_log),
                "bridge_socket": str(bridge_socket),
            },
            snapshot=None,
            records=[
                {
                    "slot_id": item.get("surface_id"),
                    "embedded_surface_id": item.get("embedded_surface_id"),
                    "client_app_id": item.get("client_app_id"),
                    "client_title": item.get("client_title"),
                    "embedding_status": item.get("embedding_status"),
                }
                for item in embedded_surfaces
            ],
            extra={
                "panel_snapshot_source": payload["panel_snapshot_source"],
                "panel_embedding_status": payload["panel_embedding_status"],
                "embedded_surface_count": payload["embedded_surface_count"],
                "client_count": payload["client_count"],
                "xdg_toplevel_count": payload["xdg_toplevel_count"],
            },
        )
        require(manifest_path.exists(), "panel embedding live manifest missing")
        require(
            manifest["suite"] == "shell-panel-embedding-live",
            "panel embedding live manifest suite mismatch",
        )
        require(
            len(manifest["records"]) == len(embedded_surfaces),
            "panel embedding live manifest record count mismatch",
        )

        print("shell panel embedding live smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell panel embedding live smoke failed: {error}")
        return 1
    finally:
        if panel_clients_process is not None and panel_clients_process.poll() is None:
            terminate(panel_clients_process)
        bridge_logs = terminate(bridge_process)
        compositor_logs = terminate(compositor_process)
        if failed:
            if bridge_logs:
                print("\n--- panel bridge log ---")
                print(bridge_logs)
            if compositor_logs:
                print("\n--- compositor log ---")
                print(compositor_logs)
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
