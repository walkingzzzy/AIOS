#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORM_ID = "nvidia-jetson-orin-agx"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed = value.strip()
        if len(parsed) >= 2 and parsed[0] == parsed[-1] == '"':
            parsed = parsed[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        values[key.strip()] = parsed
    return values


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="aios-vendor-fw-"))
    system_image = temp_root / "system.raw"
    installer_image = temp_root / "installer.raw"
    recovery_image = temp_root / "recovery.raw"
    for path, payload in (
        (system_image, b"system-image"),
        (installer_image, b"installer-image"),
        (recovery_image, b"recovery-image"),
    ):
        path.write_bytes(payload)

    output_dir = temp_root / "platform-media"
    state_dir = temp_root / "boot-state"
    report_dir = temp_root / "installer-report"
    sysroot = temp_root / "sysroot"
    context_log = temp_root / "nvbootctrl-context.log"
    fake_nvbootctrl = write_executable(
        temp_root / "fake-nvbootctrl.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        "state_dir=\"$AIOS_UPDATED_TEST_NVBOOTCTRL_STATE_DIR\"\n"
        "context=\"$AIOS_UPDATED_TEST_NVBOOTCTRL_CONTEXT\"\n"
        "mkdir -p \"$state_dir\"\n"
        "verb=\"${1:-}\"\n"
        "shift || true\n"
        "case \"$verb\" in\n"
        "  get-current-slot)\n"
        "    if [ -f \"$state_dir/tool-current-slot\" ]; then cat \"$state_dir/tool-current-slot\"; else printf '0\\n'; fi\n"
        "    ;;\n"
        "  dump-slots-info)\n"
        "    printf 'slot: 0, status: bootable\\nslot: 1, status: bootable\\n'\n"
        "    ;;\n"
        "  set-active-boot-slot)\n"
        "    printf 'set-active-boot-slot %s\\n' \"$1\" >> \"$context\"\n"
        "    printf '%s\\n' \"$1\" > \"$state_dir/tool-next-slot\"\n"
        "    ;;\n"
        "  mark-boot-successful)\n"
        "    printf 'mark-boot-successful\\n' >> \"$context\"\n"
        "    ;;\n"
        "  *)\n"
        "    printf 'unsupported verb: %s\\n' \"$verb\" >&2\n"
        "    exit 1\n"
        "    ;;\n"
        "esac\n",
    )

    build_completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build-aios-platform-media.py"),
            "--platform",
            PLATFORM_ID,
            "--platform-profile",
            str(ROOT / "aios" / "image" / "platforms" / PLATFORM_ID / "profile.yaml"),
            "--output-dir",
            str(output_dir),
            "--system-image",
            str(system_image),
            "--installer-image",
            str(installer_image),
            "--recovery-image",
            str(recovery_image),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    manifest = json.loads((output_dir / "platform-media-manifest.json").read_text())
    installer_env = load_env(
        output_dir / "config" / "installer-overlay" / "etc" / "aios" / "installer" / "aios-installer.env"
    )
    require(manifest["platform_id"] == PLATFORM_ID, "vendor platform id mismatch")
    require(
        installer_env.get("AIOS_INSTALLER_VENDOR_ID") == "nvidia",
        "installer env missing vendor id",
    )
    require(
        installer_env.get("AIOS_INSTALLER_PLATFORM_PROFILE")
        == "/usr/share/aios/updated/platforms/nvidia-jetson-orin-agx/profile.yaml",
        "installer env missing updated platform profile",
    )
    require(
        installer_env.get("AIOS_INSTALLER_GUIDED_MODE") == "interactive",
        "installer env missing guided mode",
    )

    pre_hook = ROOT / "aios" / "image" / "platforms" / PLATFORM_ID / "hooks" / "pre-install.sh"
    post_hook = ROOT / "aios" / "image" / "platforms" / PLATFORM_ID / "hooks" / "post-install.sh"
    hook_env = {
        **os.environ,
        "AIOS_NVIDIA_NVBOOTCTRL_BIN": str(fake_nvbootctrl),
        "AIOS_UPDATED_TEST_NVBOOTCTRL_STATE_DIR": str(state_dir),
        "AIOS_UPDATED_TEST_NVBOOTCTRL_CONTEXT": str(context_log),
        "AIOS_INSTALLER_REPORT_DIR": str(report_dir),
        "AIOS_INSTALLER_VENDOR_ID": "nvidia",
        "AIOS_INSTALLER_HARDWARE_PROFILE_ID": PLATFORM_ID,
        "AIOS_INSTALLER_INSTALL_ID": "vendor-smoke-001",
        "AIOS_INSTALLER_INSTALL_SLOT": "b",
    }
    subprocess.run(["bash", str(pre_hook)], cwd=ROOT, env=hook_env, check=True)
    subprocess.run(
        ["bash", str(post_hook)],
        cwd=ROOT,
        env={**hook_env, "AIOS_INSTALLER_SYSROOT": str(sysroot)},
        check=True,
    )
    pre_report = json.loads((report_dir / "hook-reports" / "nvidia-pre-install.json").read_text())
    post_report = json.loads((sysroot / "etc" / "aios" / "installer" / "nvidia-firmware-hook-report.json").read_text())
    require(pre_report["vendor_id"] == "nvidia", "pre-install report vendor mismatch")
    require(post_report["install_slot"] == "b", "post-install report slot mismatch")

    bridge = ROOT / "aios" / "services" / "updated" / "platforms" / PLATFORM_ID / "libexec" / "firmwarectl-bridge.sh"
    bridge_env = {
        **os.environ,
        "AIOS_NVIDIA_NVBOOTCTRL_BIN": str(fake_nvbootctrl),
        "AIOS_UPDATED_TEST_NVBOOTCTRL_STATE_DIR": str(state_dir),
        "AIOS_UPDATED_TEST_NVBOOTCTRL_CONTEXT": str(context_log),
    }
    status = subprocess.run(
        ["bash", str(bridge), "status", "--state-dir", str(state_dir)],
        cwd=ROOT,
        env=bridge_env,
        text=True,
        capture_output=True,
        check=True,
    )
    require("backend=nvidia-nvbootctrl-adapter" in status.stdout, "status missing adapter backend")
    subprocess.run(
        ["bash", str(bridge), "set-active", "b", "--state-dir", str(state_dir)],
        cwd=ROOT,
        env=bridge_env,
        check=True,
    )
    subprocess.run(
        ["bash", str(bridge), "mark-good", "b", "--state-dir", str(state_dir)],
        cwd=ROOT,
        env=bridge_env,
        check=True,
    )

    context_lines = context_log.read_text().splitlines()
    require(
        "set-active-boot-slot 1" in context_lines,
        "vendor bridge did not stage slot b via nvbootctrl",
    )
    require("mark-boot-successful" in context_lines, "vendor bridge did not mark boot successful")
    require(
        (state_dir / "last-good-slot").read_text().strip() == "b",
        "vendor bridge should persist last-good-slot=b",
    )

    print(
        json.dumps(
            {
                "platform_manifest": manifest["platform_id"],
                "pre_report_path": str(report_dir / "hook-reports" / "nvidia-pre-install.json"),
                "post_report_path": str(sysroot / "etc" / "aios" / "installer" / "nvidia-firmware-hook-report.json"),
                "bridge_status": status.stdout.strip().splitlines(),
                "nvbootctrl_context": context_lines,
                "build_stdout_lines": len(build_completed.stdout.splitlines()),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
