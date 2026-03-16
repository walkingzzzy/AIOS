#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from helper_contract import apply_helper_contract, build_evidence, build_transport


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def probe_excerpt() -> tuple[str | None, str | None]:
    for command in (["wpctl", "status"], ["pw-cli", "ls", "Node"]):
        try:
            completed = subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        excerpt = " ".join(completed.stdout.split())[:240]
        return command[0], excerpt
    return None, None


def main() -> int:
    socket_path = Path(
        os.environ.get("AIOS_DEVICED_PIPEWIRE_SOCKET_PATH", "/run/user/1000/pipewire-0")
    )
    node_path = Path(
        os.environ.get("AIOS_DEVICED_PIPEWIRE_NODE_PATH", "/var/lib/aios/deviced/pipewire-node.json")
    )
    payload: dict[str, object] = {
        "release_grade_backend": "pipewire",
        "release_grade_backend_id": "pipewire",
        "release_grade_backend_origin": "os-native",
        "release_grade_backend_stack": "pipewire",
        "release_grade_contract_kind": "release-grade-runtime-helper",
        "adapter_hint": "audio.pipewire-native",
        "pipewire_socket": str(socket_path),
    }
    node = read_json(node_path)
    if node:
        payload["pipewire_node"] = node
    tool, excerpt = probe_excerpt()
    if tool:
        payload["probe_tool"] = tool
        payload["probe_excerpt"] = excerpt
    payload = apply_helper_contract(
        payload,
        modality="audio",
        release_grade_backend="pipewire",
        release_grade_backend_id="pipewire",
        release_grade_backend_origin="os-native",
        release_grade_backend_stack="pipewire",
        adapter_hint="audio.pipewire-native",
        collector="audio.pipewire-live",
        transport=build_transport(
            "pipewire",
            endpoint=str(socket_path),
            stream_ref=(
                f"pipewire-node:{node.get('node_id')}"
                if isinstance(node, dict) and node.get("node_id") is not None
                else None
            ),
            details={"socket_present": socket_path.exists()},
        ),
        evidence=build_evidence(
            state_ref=str(node_path) if node_path.exists() else None,
            probe_tool=tool,
            probe_excerpt=excerpt,
            details={
                "pipewire_socket": str(socket_path),
                "socket_present": socket_path.exists(),
            },
        ),
    )

    result = {
        "available": socket_path.exists(),
        "readiness": "native-live" if socket_path.exists() else "dependency-missing",
        "details": [
            f"pipewire_socket={socket_path}",
            f"pipewire_node={node_path}" if node_path.exists() else f"pipewire_node_missing={node_path}",
        ],
        "payload": payload if socket_path.exists() else None,
        "source": "deviced-runtime-helper",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
