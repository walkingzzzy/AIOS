#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    if os.name == "nt":
        print("container-native build smoke skipped: container-native delivery preflight is validated on Linux hosts")
        return 0

    script = ROOT / "scripts" / "build-aios-delivery-container.sh"
    dockerfile = ROOT / "docker" / "aios-delivery.Dockerfile"
    require(script.exists(), f"missing container build script: {script}")
    require(dockerfile.exists(), f"missing delivery Dockerfile: {dockerfile}")

    completed = subprocess.run(
        ["bash", str(script), "--preflight"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    require(
        payload["linux_binary_strategy"] == "container-native-linux-x86_64",
        "unexpected container-native strategy",
    )
    require(payload["dockerfile_exists"] is True, "preflight should report Dockerfile present")
    require(
        Path(payload["dockerfile"]).resolve() == dockerfile.resolve(),
        "preflight Dockerfile path mismatch",
    )
    require(payload["container_toolchain"] == "1.85.0", "unexpected container toolchain pin")
    require(payload["reuse_local_builder"] == "1", "unexpected builder reuse policy")
    require(
        payload["container_target_dir"] == "/workspace/out/aios-delivery-container-target",
        "unexpected container target dir isolation",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
