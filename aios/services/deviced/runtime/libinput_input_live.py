#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from helper_contract import apply_helper_contract, build_evidence, build_transport


def enumerate_devices(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(
        item.name
        for item in root.iterdir()
        if item.name.startswith(("event", "mouse", "kbd"))
    )


def probe_excerpt() -> tuple[str | None, list[str], str | None]:
    try:
        completed = subprocess.run(
            ["libinput", "list-devices"],
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None, [], None
    devices = [
        line.split(":", 1)[1].strip()
        for line in completed.stdout.splitlines()
        if line.startswith("Device:")
    ]
    excerpt = " ".join(completed.stdout.split())[:240]
    return "libinput", devices, excerpt


def main() -> int:
    input_root = Path(os.environ.get("AIOS_DEVICED_INPUT_DEVICE_ROOT", "/dev/input"))
    devices = enumerate_devices(input_root)
    tool, live_devices, excerpt = probe_excerpt()
    if live_devices:
        devices = live_devices
    backend_origin = "os-native" if live_devices else "state-enumeration"
    payload = {
        "release_grade_backend": "libinput",
        "release_grade_backend_id": "libinput",
        "release_grade_backend_origin": backend_origin,
        "release_grade_backend_stack": "libinput",
        "release_grade_contract_kind": "release-grade-runtime-helper",
        "adapter_hint": "input.libinput-native",
        "collector": "libinput-live",
        "input_devices": devices,
    }
    if tool:
        payload["probe_tool"] = tool
    if excerpt:
        payload["probe_excerpt"] = excerpt
    payload = apply_helper_contract(
        payload,
        modality="input",
        release_grade_backend="libinput",
        release_grade_backend_id="libinput",
        release_grade_backend_origin=backend_origin,
        release_grade_backend_stack="libinput",
        adapter_hint="input.libinput-native",
        collector="libinput-live",
        transport=build_transport(
            "libinput",
            endpoint=str(input_root),
            details={"device_count": len(devices)},
        ),
        evidence=build_evidence(
            state_ref=str(input_root),
            probe_tool=tool,
            probe_excerpt=excerpt,
            details={
                "device_count": len(devices),
                "backend_origin": backend_origin,
            },
        ),
    )
    result = {
        "available": bool(devices),
        "readiness": "native-live" if devices else "device-missing",
        "details": [
            f"input_root={input_root}",
            f"device_count={len(devices)}",
        ],
        "payload": payload if devices else None,
        "source": "deviced-runtime-helper",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
