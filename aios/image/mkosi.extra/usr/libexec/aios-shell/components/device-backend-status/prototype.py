#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path


def default_backend_state() -> Path:
    return Path(
        os.environ.get(
            "AIOS_DEVICED_BACKEND_STATE_PATH",
            "/var/lib/aios/deviced/backend-state.json",
        )
    )


def default_socket() -> Path:
    return Path(os.environ.get("AIOS_DEVICED_SOCKET_PATH", "/run/aios/deviced/deviced.sock"))


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
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


def load_model(path: Path, fixture: Path | None, socket_path: Path) -> dict | None:
    source = fixture or path
    if source.exists():
        return json.loads(source.read_text())
    if socket_path.exists():
        state = rpc_call(socket_path, "device.state.get", {})
        return {
            "updated_at": None,
            "statuses": state.get("backend_statuses", []),
            "adapters": state.get("capture_adapters", []),
            "ui_tree_snapshot": state.get("ui_tree_snapshot"),
            "ui_tree_support_matrix": state.get("ui_tree_support_matrix", []),
            "notes": state.get("notes", []),
        }
    return None


def render(model: dict | None) -> str:
    if model is None:
        return "no device backend state"

    lines: list[str] = []
    updated_at = model.get("updated_at")
    if updated_at:
        lines.append(f"updated_at: {updated_at}")
    for status in model.get("statuses", []):
        details = ", ".join(status.get("details", []))
        line = (
            f"- {status['modality']}: {status['backend']} "
            f"[{status['readiness']}] available={status['available']}"
        )
        if details:
            line = f"{line} details={details}"
        lines.append(line)
    for adapter in model.get("adapters", []):
        lines.append(
            f"adapter: {adapter['modality']} -> {adapter['adapter_id']} [{adapter['execution_path']}]"
        )
    ui_tree_snapshot = model.get("ui_tree_snapshot")
    if isinstance(ui_tree_snapshot, dict):
        focus = ui_tree_snapshot.get("focus_name") or ui_tree_snapshot.get("focus_node") or "-"
        lines.append(
            "ui_tree: "
            f"{ui_tree_snapshot.get('snapshot_id', '-')} "
            f"[{ui_tree_snapshot.get('capture_mode', 'unknown')}] "
            f"applications={ui_tree_snapshot.get('application_count', 0)} "
            f"focus={focus}"
        )
    for row in model.get("ui_tree_support_matrix", []):
        lines.append(
            "ui_tree_matrix: "
            f"{row.get('environment_id', '-')} "
            f"[{row.get('readiness', 'unknown')}] "
            f"available={row.get('available')}"
        )
    for note in model.get("notes", []):
        lines.append(f"note: {note}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS device backend status prototype")
    parser.add_argument("--path", type=Path, default=default_backend_state())
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    print(render(load_model(args.path, args.fixture, args.socket)))
