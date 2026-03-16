#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SYSTEM_HEALTH_GET = "system.health.get"
DEVICE_CAPTURE_REQUEST = "device.capture.request"


def _response(*, request_id: int | str | None, result: dict | None = None, error: str | None = None) -> bytes:
    if error is not None:
        payload = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": error}}
    else:
        payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


def _mock_transport_payload(*, capture_status: str, service_id: str) -> dict[str, Any]:
    return {
        "transport": "mock-file",
        "service_kind": "device-capture",
        "service_id": service_id,
        "capture_status": capture_status,
    }


def wait_for_socket(path: Path, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for mock socket: {path}")


def start_mock_deviced_server(
    socket_path: Path,
    *,
    capture_status: str = "capturing",
    service_id: str = "mock-deviced",
) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    if not hasattr(socket, "AF_UNIX"):
        socket_path.write_text(
            json.dumps(
                _mock_transport_payload(capture_status=capture_status, service_id=service_id),
                indent=2,
                ensure_ascii=False,
            )
        )
        thread = threading.Thread(target=stop_event.wait, daemon=True)
        thread.start()
        wait_for_socket(socket_path)
        return stop_event, thread

    def run() -> None:
        sequence = 0
        if socket_path.exists():
            socket_path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        server.listen(5)
        server.settimeout(0.1)

        try:
            while not stop_event.is_set():
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue

                with connection:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = connection.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    if not data:
                        continue

                    request = json.loads(data.decode("utf-8") or "{}")
                    request_id = request.get("id")
                    method = request.get("method")
                    params = request.get("params") or {}

                    if method == SYSTEM_HEALTH_GET:
                        connection.sendall(
                            _response(
                                request_id=request_id,
                                result={
                                    "service_id": service_id,
                                    "status": "ready",
                                    "socket_path": str(socket_path),
                                },
                            )
                        )
                        continue

                    if method == DEVICE_CAPTURE_REQUEST:
                        sequence += 1
                        capture_id = f"mock-capture-{sequence}"
                        connection.sendall(
                            _response(
                                request_id=request_id,
                                result={
                                    "capture": {
                                        "capture_id": capture_id,
                                        "modality": params.get("modality", "screen"),
                                        "status": capture_status,
                                        "continuous": bool(params.get("continuous")),
                                        "session_id": params.get("session_id"),
                                        "task_id": params.get("task_id"),
                                        "window_ref": params.get("window_ref"),
                                        "source_device": params.get("source_device"),
                                    },
                                    "preview_object": {
                                        "kind": "screen_frame",
                                        "capture_id": capture_id,
                                        "source": service_id,
                                    },
                                },
                            )
                        )
                        continue

                    connection.sendall(
                        _response(request_id=request_id, error=f"unsupported method: {method}")
                    )
        finally:
            server.close()
            if socket_path.exists():
                socket_path.unlink()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    wait_for_socket(socket_path)
    return stop_event, thread


def stop_mock_deviced_server(stop_event: threading.Event, thread: threading.Thread) -> None:
    stop_event.set()
    thread.join(timeout=2.0)


def cleanup_mock_deviced(socket_path: Path) -> None:
    if socket_path.exists() and socket_path.is_file():
        socket_path.unlink()


@contextmanager
def managed_mock_deviced(
    socket_path: Path,
    *,
    capture_status: str = "capturing",
    service_id: str = "mock-deviced",
) -> Iterator[Path]:
    stop_event, thread = start_mock_deviced_server(
        socket_path,
        capture_status=capture_status,
        service_id=service_id,
    )
    try:
        yield socket_path
    finally:
        stop_mock_deviced_server(stop_event, thread)
        cleanup_mock_deviced(socket_path)
