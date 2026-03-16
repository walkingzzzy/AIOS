#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = ROOT / "out" / "tmp"


def build_validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def write_script(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def emit_skip(reason: str) -> None:
    print(json.dumps({"status": "skipped", "reason": reason}, indent=2, ensure_ascii=False))


def main() -> int:
    if sys.platform == "win32":
        emit_skip("Windows 环境不支持直接执行 POSIX shell 启动证据采集脚本")
        return 0

    boot_report_validator = build_validator(
        ROOT / "aios" / "hardware" / "schemas" / "hardware-boot-evidence-report.schema.json"
    )
    evidence_index_validator = build_validator(
        ROOT / "aios" / "hardware" / "schemas" / "hardware-validation-evidence-index.schema.json"
    )

    temp_root = make_temp_dir("aios-hardware-evidence-smoke-")
    output_dir = temp_root / "boots"
    profile_path = temp_root / "tier1-profile.yaml"
    boot_id_path = temp_root / "boot_id"
    cmdline_path = temp_root / "cmdline"
    deployment_path = temp_root / "deployment.json"
    boot_state_path = temp_root / "boot-state.json"
    boot_dir = temp_root / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)

    fake_bootctl = temp_root / "fake-bootctl.sh"
    fake_firmwarectl = temp_root / "fake-firmwarectl.sh"
    fake_sysupdate = temp_root / "fake-systemd-sysupdate.sh"
    write_script(fake_bootctl, "#!/bin/sh\nprintf 'Current Boot Loader Entry: aios-b.conf\\n'")
    write_script(fake_firmwarectl, "#!/bin/sh\nprintf 'current_slot=b\\n'")
    write_script(fake_sysupdate, "#!/bin/sh\nprintf 'aios-root 0.2.0\\n'")

    collector = ROOT / "aios" / "hardware" / "evidence" / "aios-boot-evidence.sh"
    env = os.environ.copy()
    env.update(
        {
            "AIOS_BOOT_EVIDENCE_OUTPUT_DIR": str(output_dir),
            "AIOS_BOOT_EVIDENCE_BOOT_ID_PATH": str(boot_id_path),
            "AIOS_BOOT_EVIDENCE_CMDLINE_PATH": str(cmdline_path),
            "AIOS_BOOT_EVIDENCE_DEPLOYMENT_STATE_PATH": str(deployment_path),
            "AIOS_BOOT_EVIDENCE_BOOT_STATE_PATH": str(boot_state_path),
            "AIOS_BOOT_EVIDENCE_BOOT_ENTRY_STATE_DIR": str(boot_dir),
            "AIOS_BOOT_EVIDENCE_BOOTCTL_BIN": str(fake_bootctl),
            "AIOS_BOOT_EVIDENCE_FIRMWARECTL_BIN": str(fake_firmwarectl),
            "AIOS_BOOT_EVIDENCE_SYSUPDATE_BIN": str(fake_sysupdate),
            "AIOS_BOOT_EVIDENCE_SYSUPDATE_DEFINITIONS_DIR": str(temp_root / "sysupdate.d"),
        }
    )

    boot_id_path.write_text("boot-a\n")
    cmdline_path.write_text("quiet aios.slot=a\n")
    write_json(deployment_path, {"current_version": "0.1.0", "status": "idle"})
    write_json(boot_state_path, {"current_slot": "a", "last_good_slot": "a", "boot_success": True})
    subprocess.run([str(collector)], cwd=ROOT, env=env, check=True, capture_output=True, text=True)

    boot_id_path.write_text("boot-b\n")
    cmdline_path.write_text("quiet aios.slot=b\n")
    write_json(deployment_path, {"current_version": "0.2.0", "status": "ready"})
    write_json(boot_state_path, {"current_slot": "b", "last_good_slot": "b", "boot_success": True})
    subprocess.run([str(collector)], cwd=ROOT, env=env, check=True, capture_output=True, text=True)

    profile_path.write_text(
        "\n".join(
            [
                "id: smoke-tier1",
                "boot_evidence_expectations:",
                "  min_boots: 2",
                "  require_boot_success: true",
                "  require_deployment_state: true",
                "  require_boot_state: true",
                "  require_bootctl_status: true",
                "  require_firmware_status: true",
                "  require_sysupdate_listing: true",
                "  expect_slot_transition: a:b",
                "  expect_last_good_slot: b",
                "",
            ]
        )
    )

    report_path = temp_root / "report.json"
    report_md_path = temp_root / "report.md"
    evidence_index_path = temp_root / "evidence-index.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate-aios-hardware-boot-evidence.py"),
            "--input-dir",
            str(output_dir),
            "--profile",
            str(profile_path),
            "--output",
            str(report_path),
            "--report-md",
            str(report_md_path),
            "--evidence-index-out",
            str(evidence_index_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr)
        raise SystemExit(completed.returncode)

    report = json.loads(report_path.read_text())
    boot_report_validator.validate(report)
    require(report["passed"] is True, "evidence report should pass")
    require(len(report["unique_boot_ids"]) == 2, "expected two unique boot ids")
    require(report["resolved_expectations"]["require_bootctl_status"] is True, "profile expectations not applied")
    require(report_md_path.exists(), "missing markdown report")
    require("## Checks" in report_md_path.read_text(), "markdown report missing checks section")
    evidence_index = json.loads(evidence_index_path.read_text())
    evidence_index_validator.validate(evidence_index)
    require(evidence_index["validation_status"] == "passed", "evidence index status mismatch")
    require(len(evidence_index["records"]) == 2, "evidence index record count mismatch")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
