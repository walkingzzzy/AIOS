#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def main() -> int:
    if os.name == "nt":
        print("installer ux smoke skipped: guided installer shell flow is validated on Linux hosts")
        return 0

    temp_root = Path(tempfile.mkdtemp(prefix="aios-installer-ux-"))
    env_file = temp_root / "aios-installer.env"
    report_dir = temp_root / "reports"
    hooks_dir = temp_root / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_hook = write_executable(hooks_dir / "pre-install.sh", "#!/bin/sh\nexit 0\n")
    post_hook = write_executable(hooks_dir / "post-install.sh", "#!/bin/sh\nexit 0\n")
    env_file.write_text(
        "\n".join(
            [
                "AIOS_INSTALLER_SOURCE_IMAGE_FILE=/usr/share/aios/installer/payload/aios-system.raw",
                "AIOS_INSTALLER_TARGET_DISK=/dev/nvme0n1",
                "AIOS_INSTALLER_RECOVERY_DISK=/dev/sdb",
                "AIOS_INSTALLER_PLATFORM_ID=nvidia-jetson-orin-agx",
                'AIOS_INSTALLER_PLATFORM_LABEL="NVIDIA Jetson AGX Orin Devkit"',
                "AIOS_INSTALLER_PLATFORM_PROFILE=/usr/share/aios/updated/platforms/nvidia-jetson-orin-agx/profile.yaml",
                "AIOS_INSTALLER_INSTALL_SOURCE=installer-media:embedded-payload",
                "AIOS_INSTALLER_INSTALL_SLOT=b",
                "AIOS_INSTALLER_BOOT_BACKEND=firmware",
                "AIOS_INSTALLER_GUIDED_MODE=interactive",
                "AIOS_INSTALLER_GUIDED_AUTO_CONFIRM_SECONDS=0",
                "AIOS_INSTALLER_AI_ENABLED=1",
                "AIOS_INSTALLER_AI_MODE=hybrid",
                "AIOS_INSTALLER_AI_PRIVACY_PROFILE=balanced",
                "AIOS_INSTALLER_AI_AUTO_PULL_DEFAULT_MODEL=1",
                "AIOS_INSTALLER_AI_AUTO_MODEL_SOURCE=ollama-library",
                "AIOS_INSTALLER_AI_AUTO_MODEL_ID=qwen2.5:7b-instruct",
                "AIOS_INSTALLER_AI_ENDPOINT_BASE_URL=http://127.0.0.1:11434/v1",
                "AIOS_INSTALLER_AI_ENDPOINT_MODEL=qwen2.5:7b-instruct",
                "AIOS_INSTALLER_VENDOR_ID=nvidia",
                "AIOS_INSTALLER_HARDWARE_PROFILE_ID=nvidia-jetson-orin-agx",
                f"AIOS_INSTALLER_PRE_INSTALL_HOOK={pre_hook}",
                f"AIOS_INSTALLER_POST_INSTALL_HOOK={post_hook}",
            ]
        )
        + "\n"
    )

    completed = subprocess.run(
        ["bash", str(ROOT / "aios" / "image" / "installer" / "aios-installer-guided.sh")],
        cwd=ROOT,
        env={
            **os.environ,
            "AIOS_INSTALLER_ENV_FILE": str(env_file),
            "AIOS_INSTALLER_REPORT_DIR": str(report_dir),
            "AIOS_INSTALLER_GUIDED_DRY_RUN": "1",
        },
        text=True,
        capture_output=True,
        check=True,
    )

    session_path = report_dir / "guided-session.json"
    summary_path = report_dir / "guided-summary.txt"
    require(session_path.exists(), f"missing guided session file: {session_path}")
    require(summary_path.exists(), f"missing guided summary file: {summary_path}")
    session = json.loads(session_path.read_text())
    summary = summary_path.read_text()

    require(session["platform_id"] == "nvidia-jetson-orin-agx", "platform_id mismatch")
    require(session["target_disk"] == "/dev/nvme0n1", "target disk mismatch")
    require(session["install_slot"] == "b", "install slot mismatch")
    require(session["guided_mode"] == "interactive", "guided mode mismatch")
    require(session["ai_config"]["enabled"] is True, "guided session ai enabled mismatch")
    require(session["ai_config"]["mode"] == "hybrid", "guided session ai mode mismatch")
    require(
        session["ai_config"]["endpoint_base_url"] == "http://127.0.0.1:11434/v1",
        "guided session ai endpoint mismatch",
    )
    require(
        session["pre_install_hook"]["status"] == "ready",
        "pre-install hook should be marked ready",
    )
    require(
        session["post_install_hook"]["status"] == "ready",
        "post-install hook should be marked ready",
    )
    require(
        "Platform ID    : nvidia-jetson-orin-agx" in summary,
        "summary missing platform id",
    )
    require("Target Disk    : /dev/nvme0n1" in summary, "summary missing target disk")
    require("Vendor ID      : nvidia" in summary, "summary missing vendor id")
    require("AI Enabled     : yes" in summary, "summary missing ai enabled flag")
    require("AI Mode        : hybrid" in summary, "summary missing ai mode")
    require(
        "AI Endpoint    : http://127.0.0.1:11434/v1" in summary,
        "summary missing ai endpoint",
    )
    require(
        completed.stdout.strip().endswith("dry-run complete; installer runner not invoked"),
        "guided script should complete in dry-run mode",
    )

    print(
        json.dumps(
            {
                "session_path": str(session_path),
                "summary_path": str(summary_path),
                "platform_id": session["platform_id"],
                "target_disk": session["target_disk"],
                "guided_mode": session["guided_mode"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
