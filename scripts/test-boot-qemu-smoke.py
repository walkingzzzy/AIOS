#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run_preflight(script: Path) -> dict:
    completed = subprocess.run(
        ["bash", str(script), "--preflight"],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout.strip() or "{}")


def main() -> int:
    image = run_preflight(ROOT / "scripts" / "build-aios-image.sh")
    qemu = run_preflight(ROOT / "scripts" / "boot-qemu.sh")
    summary = {
        "image_preflight": image,
        "qemu_preflight": qemu,
        "bootable_image_ready": image.get("status") == "ready",
        "qemu_bringup_ready": qemu.get("status") == "ready",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
