#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path


def default_socket() -> Path:
    return Path(os.environ.get("AIOS_UPDATED_SOCKET_PATH", "/run/aios/updated/updated.sock"))


def default_surface() -> Path:
    return Path(
        os.environ.get(
            "AIOS_UPDATED_RECOVERY_SURFACE_PATH",
            "/var/lib/aios/updated/recovery-surface.json",
        )
    )


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    if not hasattr(socket, "AF_UNIX"):
        raise RuntimeError(f"unix-domain-socket-unavailable:{socket_path}")
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response["result"]


def load_surface(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_surface_or_rpc(path: Path, socket_path: Path) -> dict:
    surface = load_surface(path)
    if surface is not None:
        return surface
    return rpc_call(socket_path, "recovery.surface.get", {})


def print_status(surface: dict) -> None:
    print(f"service: {surface['service_id']}")
    print(f"overall: {surface['overall_status']}")
    print(f"deployment: {surface['deployment_status']}")
    print(f"rollback_ready: {surface['rollback_ready']}")
    if surface.get("current_slot"):
        print(f"current_slot: {surface['current_slot']}")
    if surface.get("last_good_slot"):
        print(f"last_good_slot: {surface['last_good_slot']}")
    if surface.get("staged_slot"):
        print(f"staged_slot: {surface['staged_slot']}")
    print(f"actions: {', '.join(surface.get('available_actions', []))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS recovery surface prototype")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["status", "check", "apply", "rollback", "bundle"],
    )
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--surface", type=Path, default=default_surface())
    parser.add_argument("--target-version")
    parser.add_argument("--reason")
    parser.add_argument("--recovery-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "status":
        surface = load_surface_or_rpc(args.surface, args.socket)
        if args.json:
            print(json.dumps(surface, indent=2, ensure_ascii=False))
        else:
            print_status(surface)
    elif args.command == "check":
        print(json.dumps(rpc_call(args.socket, "update.check", {}), indent=2, ensure_ascii=False))
    elif args.command == "apply":
        print(
            json.dumps(
                rpc_call(
                    args.socket,
                    "update.apply",
                    {"target_version": args.target_version, "reason": args.reason, "dry_run": False},
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
    elif args.command == "rollback":
        print(
            json.dumps(
                rpc_call(
                    args.socket,
                    "update.rollback",
                    {"recovery_id": args.recovery_id, "reason": args.reason, "dry_run": False},
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(
            json.dumps(
                rpc_call(args.socket, "recovery.bundle.export", {"reason": args.reason}),
                indent=2,
                ensure_ascii=False,
            )
        )
