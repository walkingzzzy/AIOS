#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import time
from pathlib import Path


WORKER_CONTRACT = "runtime-worker-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS runtime reference accelerator worker")
    parser.add_argument("mode", choices=["stdio", "unix"])
    parser.add_argument("--backend", required=True, choices=["local-gpu", "local-npu"])
    parser.add_argument("--socket", type=Path, help="Unix socket path when mode=unix")
    return parser.parse_args()


def build_response(backend: str, request: dict) -> dict:
    prompt = request.get("prompt", "")
    if "#sleep-worker" in prompt:
        time.sleep(0.05)

    rejected = "#reject-worker" in prompt
    route_state = f"{backend}-worker-v1"
    content = "" if rejected else f"reference {backend} worker completed {request.get('task_id', 'task')}"
    reason = "worker rejected prompt directive" if rejected else "reference accelerator worker executed request"
    return {
        "worker_contract": WORKER_CONTRACT,
        "backend_id": backend,
        "route_state": route_state,
        "content": content,
        "rejected": rejected,
        "degraded": False,
        "reason": reason,
        "estimated_latency_ms": request.get("estimated_latency_ms"),
    }


def handle_payload(backend: str, payload: bytes) -> bytes:
    request = json.loads(payload.decode("utf-8") or "{}")
    request.setdefault("worker_contract", WORKER_CONTRACT)
    response = build_response(backend, request)
    return json.dumps(response, ensure_ascii=False).encode("utf-8")


def run_stdio(backend: str) -> int:
    payload = os.read(0, 1024 * 1024)
    os.write(1, handle_payload(backend, payload))
    return 0


def run_unix(backend: str, socket_path: Path) -> int:
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(16)
    try:
        while True:
            connection, _ = server.accept()
            with connection:
                payload = b""
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    payload += chunk
                connection.sendall(handle_payload(backend, payload))
    finally:
        server.close()
        if socket_path.exists():
            socket_path.unlink()


def main() -> int:
    args = parse_args()
    if args.mode == "stdio":
        return run_stdio(args.backend)
    if args.socket is None:
        raise SystemExit("--socket is required when mode=unix")
    return run_unix(args.backend, args.socket)


if __name__ == "__main__":
    raise SystemExit(main())
