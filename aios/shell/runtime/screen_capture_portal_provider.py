#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SYSTEM_HEALTH_GET = "system.health.get"
POLICY_TOKEN_VERIFY = "policy.token.verify"
DEVICE_CAPTURE_REQUEST = "device.capture.request"
DEVICE_CAPTURE_SCREEN_READ = "device.capture.screen.read"


@dataclass
class Config:
    service_id: str
    provider_id: str
    version: str
    socket_path: Path
    policyd_socket: Path
    deviced_socket: Path


def load_config() -> Config:
    runtime_dir = Path(os.environ.get("AIOS_SCREEN_CAPTURE_PROVIDER_RUNTIME_DIR", "/run/aios/screen-provider"))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        service_id="aios-screen-capture-portal-provider",
        provider_id=os.environ.get("AIOS_SCREEN_CAPTURE_PROVIDER_ID", "shell.screen-capture.portal"),
        version="0.1.0",
        socket_path=Path(
            os.environ.get(
                "AIOS_SCREEN_CAPTURE_PROVIDER_SOCKET_PATH",
                str(runtime_dir / "screen-capture-provider.sock"),
            )
        ),
        policyd_socket=Path(
            os.environ.get(
                "AIOS_SCREEN_CAPTURE_PROVIDER_POLICYD_SOCKET",
                "/run/aios/policyd/policyd.sock",
            )
        ),
        deviced_socket=Path(
            os.environ.get(
                "AIOS_SCREEN_CAPTURE_PROVIDER_DEVICED_SOCKET",
                "/run/aios/deviced/deviced.sock",
            )
        ),
    )


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
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
        raise RuntimeError(response["error"])
    return response["result"]


def verify_token(config: Config, token: dict, handle: dict) -> None:
    if token.get("capability_id") != DEVICE_CAPTURE_SCREEN_READ:
        raise RuntimeError("execution token capability mismatch for screen capture provider")
    scope = handle_scope(handle)
    target_hash = scope_string(scope, "target_hash")
    params = {"token": token, "consume": True}
    if target_hash:
        params["target_hash"] = target_hash
    verification = rpc_call(
        config.policyd_socket,
        POLICY_TOKEN_VERIFY,
        params,
    )
    if not verification.get("valid"):
        raise RuntimeError(f"execution token rejected: {verification.get('reason')}")


def validate_handle(params: dict) -> dict:
    handle = params.get("portal_handle") or {}
    if handle.get("kind") != "screen_share_handle":
        raise RuntimeError("screen capture provider requires screen_share_handle")
    if not handle.get("target"):
        raise RuntimeError("screen capture provider requires portal target")
    return handle


def handle_scope(handle: dict) -> dict:
    scope = handle.get("scope") or {}
    return scope if isinstance(scope, dict) else {}


def scope_string(scope: dict, *keys: str) -> str | None:
    for key in keys:
        value = scope.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def scope_bool(scope: dict, *keys: str) -> bool:
    for key in keys:
        value = scope.get(key)
        if isinstance(value, bool):
            return value
    return False


def screen_request_from_handle(token: dict, handle: dict) -> dict:
    scope = handle_scope(handle)
    target = handle.get("target", "screen://current-display")
    window_ref = scope_string(scope, "window_ref", "focused_window_ref")
    if target.startswith("window://"):
        window_ref = target.split("://", 1)[1]
    source_device = scope_string(scope, "display_ref", "source_device", "monitor_ref")
    continuous = scope_bool(scope, "continuous") or scope_string(scope, "capture_mode") == "continuous"
    return {
        "modality": "screen",
        "session_id": token.get("session_id"),
        "task_id": token.get("task_id"),
        "continuous": continuous,
        "window_ref": window_ref,
        "source_device": source_device,
    }


def health(config: Config) -> dict:
    return {
        "service_id": config.service_id,
        "status": "ready",
        "version": config.version,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "socket_path": str(config.socket_path),
        "notes": [
            f"provider_id={config.provider_id}",
            f"policyd_socket={config.policyd_socket}",
            f"deviced_socket={config.deviced_socket}",
        ],
    }


def handle_screen_capture(config: Config, params: dict) -> dict:
    token = params.get("execution_token") or {}
    handle = validate_handle(params)
    verify_token(config, token, handle)
    capture_request = screen_request_from_handle(token, handle)
    capture_response = rpc_call(config.deviced_socket, DEVICE_CAPTURE_REQUEST, capture_request)
    scope = handle_scope(handle)
    notes = [
        f"session_id={token.get('session_id')}",
        f"task_id={token.get('task_id')}",
    ]
    for label, key in (
        ("portal_session_ref", "portal_session_ref"),
        ("target_hash", "target_hash"),
        ("backend", "backend"),
        ("display_ref", "display_ref"),
    ):
        value = scope.get(key)
        if value not in (None, ""):
            notes.append(f"{label}={value}")
    return {
        "provider_id": config.provider_id,
        "portal_handle": handle,
        "capture_request": capture_request,
        "capture": capture_response.get("capture"),
        "preview_object": capture_response.get("preview_object"),
        "selected_target": handle.get("target"),
        "notes": notes,
    }


def response(result: dict | None = None, error: str | None = None, request_id: int | str | None = 1) -> bytes:
    if error is not None:
        payload = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": error}}
    else:
        payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


def serve(config: Config) -> int:
    if config.socket_path.exists():
        config.socket_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(config.socket_path))
    server.listen()

    stop = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

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
                    conn.sendall(response(health(config), request_id=request_id))
                elif method == DEVICE_CAPTURE_SCREEN_READ:
                    conn.sendall(response(handle_screen_capture(config, params), request_id=request_id))
                else:
                    conn.sendall(response(error=f"unsupported method: {method}", request_id=request_id))
            except Exception as exc:  # noqa: BLE001
                conn.sendall(response(error=str(exc), request_id=request_id))

    server.close()
    if config.socket_path.exists():
        config.socket_path.unlink()
    return 0


def main() -> int:
    return serve(load_config())


if __name__ == "__main__":
    raise SystemExit(main())
