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
        str(item)
        for item in root.iterdir()
        if item.name.startswith("video")
    )


def probe_devices() -> tuple[str | None, list[str], str | None]:
    try:
        completed = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None, [], None
    devices = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().startswith("/dev/video")
    ]
    excerpt = " ".join(completed.stdout.split())[:240]
    return "v4l2-ctl", devices, excerpt


def main() -> int:
    camera_root = Path(os.environ.get("AIOS_DEVICED_CAMERA_DEVICE_ROOT", "/dev"))
    devices = enumerate_devices(camera_root)
    tool, live_devices, excerpt = probe_devices()
    if live_devices:
        devices = live_devices
    backend_origin = "os-native" if live_devices else "state-enumeration"
    payload = {
        "release_grade_backend": "v4l2",
        "release_grade_backend_id": "v4l2",
        "release_grade_backend_origin": backend_origin,
        "release_grade_backend_stack": "v4l2",
        "release_grade_contract_kind": "release-grade-runtime-helper",
        "adapter_hint": "camera.v4l-native",
        "camera_devices": devices,
    }
    if devices:
        payload["device_path"] = str(devices[0])
    if tool:
        payload["probe_tool"] = tool
    if excerpt:
        payload["probe_excerpt"] = excerpt
    payload = apply_helper_contract(
        payload,
        modality="camera",
        release_grade_backend="v4l2",
        release_grade_backend_id="v4l2",
        release_grade_backend_origin=backend_origin,
        release_grade_backend_stack="v4l2",
        adapter_hint="camera.v4l-native",
        collector="camera.v4l-live",
        transport=build_transport(
            "v4l2",
            endpoint=str(camera_root),
            stream_ref=str(payload.get("device_path")) if payload.get("device_path") else None,
            details={"device_count": len(devices)},
        ),
        evidence=build_evidence(
            state_ref=str(camera_root),
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
            f"camera_root={camera_root}",
            f"device_count={len(devices)}",
        ],
        "payload": payload if devices else None,
        "source": "deviced-runtime-helper",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
