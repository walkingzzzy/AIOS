#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
from pathlib import Path
from typing import Any


RUNTIME_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = RUNTIME_ROOT.parent
for candidate in (SHELL_ROOT, RUNTIME_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import shellctl
from panel_actions import dispatch_panel_action, select_panel_action, summarize_action_result
from shell_snapshot import add_snapshot_arguments, build_snapshot


SYSTEM_HEALTH_GET = "system.health.get"
SHELL_PANEL_SNAPSHOT_GET = "shell.panel.snapshot.get"
SHELL_PANEL_ACTION_DISPATCH = "shell.panel.action.dispatch"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS shell panel bridge socket service")
    add_snapshot_arguments(parser)
    parser.add_argument(
        "--socket-path",
        type=Path,
        default=Path(
            os.environ.get(
                "AIOS_SHELL_PANEL_BRIDGE_SOCKET",
                "/tmp/aios-shell-panel-bridge.sock",
            )
        ),
    )
    return parser.parse_args()


def response(result: dict | None = None, error: str | None = None, request_id: int | str | None = 1) -> bytes:
    if error is not None:
        payload = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": error}}
    else:
        payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


def load_profile(args: argparse.Namespace) -> dict[str, Any]:
    return shellctl.load_profile(args.profile)


def health(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args)
    return {
        "service": "shell-panel-bridge",
        "status": "ready",
        "profile_id": profile.get("profile_id"),
        "socket_path": str(args.socket_path),
    }


def snapshot_result(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args)
    return build_snapshot(profile, args)


def action_result(args: argparse.Namespace, params: dict[str, Any]) -> dict[str, Any]:
    profile = load_profile(args)
    snapshot = build_snapshot(profile, args)
    component = shellctl.normalize_component(
        params.get("component") or params.get("slot_id") or ""
    )
    if not component:
        raise RuntimeError("panel action component is required")
    action_id = params.get("action_id")
    input_kind = params.get("input_kind")
    action = select_panel_action(snapshot, component, action_id)
    payload = dispatch_panel_action(profile, args, snapshot, component, action)
    result = payload["result"]
    return {
        "component": component,
        "panel_id": params.get("panel_id"),
        "slot_id": params.get("slot_id", component),
        "action_id": action.get("action_id"),
        "input_kind": input_kind,
        "summary": summarize_action_result(component, action, result),
        "result": result,
    }


def write_tcp_transport_descriptor(socket_path: Path, host: str, port: int) -> None:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text(
        json.dumps(
            {
                "transport": "tcp",
                "service_kind": "shell-panel-bridge",
                "host": host,
                "port": port,
                "socket_path": str(socket_path),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def bind_server(socket_path: Path) -> socket.socket:
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(socket, "AF_UNIX"):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        server.listen()
        return server

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen()
    host, port = server.getsockname()
    write_tcp_transport_descriptor(socket_path, str(host), int(port))
    return server


def cleanup_socket_path(socket_path: Path) -> None:
    if socket_path.exists():
        socket_path.unlink()


def serve(args: argparse.Namespace) -> int:
    server = bind_server(args.socket_path)
    stop = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while not stop:
            try:
                server.settimeout(0.5)
                conn, _ = server.accept()
            except socket.timeout:
                continue

            with conn:
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue

                request = json.loads(data.decode("utf-8"))
                method = request.get("method")
                params = request.get("params") or {}
                request_id = request.get("id")

                try:
                    if method == SYSTEM_HEALTH_GET:
                        conn.sendall(response(health(args), request_id=request_id))
                    elif method == SHELL_PANEL_SNAPSHOT_GET:
                        conn.sendall(response(snapshot_result(args), request_id=request_id))
                    elif method == SHELL_PANEL_ACTION_DISPATCH:
                        conn.sendall(response(action_result(args, params), request_id=request_id))
                    else:
                        conn.sendall(response(error=f"unsupported method: {method}", request_id=request_id))
                except Exception as exc:  # noqa: BLE001
                    conn.sendall(response(error=str(exc), request_id=request_id))
    finally:
        server.close()
        cleanup_socket_path(args.socket_path)
    return 0


def main() -> int:
    return serve(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
