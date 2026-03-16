#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = ROOT / "out" / "tmp"
DEFAULT_OUTPUT_DIR = ROOT / "out" / "validation"
DEFAULT_PROFILE = ROOT / "aios" / "hardware" / "profiles" / "generic-x86_64-uefi.yaml"
DEFAULT_TIER1_NOMINATIONS = ROOT / "aios" / "hardware" / "tier1-nominated-machines.yaml"
HARDWARE_BOOT_EVIDENCE_EVALUATOR = ROOT / "scripts" / "evaluate-aios-hardware-boot-evidence.py"
HARDWARE_VALIDATION_RENDERER = ROOT / "scripts" / "render-aios-hardware-validation-report.py"
HARDWARE_BOOT_REPORT_SCHEMA = ROOT / "aios" / "hardware" / "schemas" / "hardware-boot-evidence-report.schema.json"
HARDWARE_VALIDATION_EVIDENCE_SCHEMA = ROOT / "aios" / "hardware" / "schemas" / "hardware-validation-evidence-index.schema.json"


def build_validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the default Tier 1 hardware evidence baseline used by the release gate"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--tier1-nominations", type=Path, default=DEFAULT_TIER1_NOMINATIONS)
    parser.add_argument("--keep-temp", action="store_true", help="Keep the synthetic boot-evidence temp directory")
    return parser.parse_args()


def load_yaml_or_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    return json.loads(text)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_command(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return
    detail = completed.stderr.strip() or completed.stdout.strip() or f"returncode={completed.returncode}"
    raise RuntimeError(f"command failed: {' '.join(command)}\n{detail}")


def synthetic_boot_record(
    *,
    boot_id: str,
    current_slot: str,
    last_good_slot: str,
    captured_at: str,
    version: str,
) -> dict[str, Any]:
    return {
        "captured_at": captured_at,
        "boot_id": boot_id,
        "cmdline": f"quiet aios.slot={current_slot}",
        "deployment_state": {
            "current_version": version,
            "status": "ready",
        },
        "boot_state": {
            "current_slot": current_slot,
            "last_good_slot": last_good_slot,
            "boot_success": True,
        },
        "bootctl_status": {
            "success": True,
            "stdout": f"Current Boot Loader Entry: aios-{current_slot}.conf",
        },
        "firmwarectl_status": {
            "success": True,
            "stdout": f"current_slot={current_slot}",
        },
        "sysupdate_list": {
            "success": True,
            "stdout": f"aios-root {version}",
        },
    }


def main() -> int:
    boot_report_validator = build_validator(HARDWARE_BOOT_REPORT_SCHEMA)
    evidence_index_validator = build_validator(HARDWARE_VALIDATION_EVIDENCE_SCHEMA)

    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    boot_report_json = output_dir / "tier1-hardware-boot-evidence-report.json"
    boot_report_md = output_dir / "tier1-hardware-boot-evidence-report.md"
    support_matrix_md = output_dir / "tier1-hardware-support-matrix.md"
    known_limitations_md = output_dir / "tier1-hardware-known-limitations.md"
    validation_report_md = output_dir / "tier1-hardware-validation-report.md"
    evidence_index_json = output_dir / "tier1-hardware-evidence-index.json"

    temp_root = make_temp_dir("aios-tier1-hardware-baseline-")
    boots_dir = temp_root / "boots"
    boots_dir.mkdir(parents=True, exist_ok=True)

    nominated_payload = load_yaml_or_json(args.tier1_nominations)
    nominated_machines = nominated_payload.get("nominated_machines", []) if isinstance(nominated_payload, dict) else []
    machine_ids = [
        str(item.get("machine_id"))
        for item in nominated_machines
        if isinstance(item, dict) and isinstance(item.get("machine_id"), str) and item.get("machine_id")
    ]

    try:
        boot_records = [
            synthetic_boot_record(
                boot_id="tier1-baseline-boot-a",
                current_slot="a",
                last_good_slot="a",
                captured_at="2026-03-14T00:00:00Z",
                version="0.1.0",
            ),
            synthetic_boot_record(
                boot_id="tier1-baseline-boot-b",
                current_slot="b",
                last_good_slot="b",
                captured_at="2026-03-14T00:05:00Z",
                version="0.2.0",
            ),
        ]
        for index, record in enumerate(boot_records, start=1):
            write_json(boots_dir / f"boot-{index}.json", record)

        run_command(
            [
                sys.executable,
                str(HARDWARE_BOOT_EVIDENCE_EVALUATOR),
                "--input-dir",
                str(boots_dir),
                "--profile",
                str(args.profile),
                "--output",
                str(boot_report_json),
                "--report-md",
                str(boot_report_md),
            ]
        )

        generated_at = datetime.now(timezone.utc).isoformat()
        write_text(
            support_matrix_md,
            "\n".join(
                [
                    "# Tier1 Hardware Baseline Support Matrix",
                    "",
                    "- Scope: release-gate synthetic baseline for nominated Tier 1 profiles",
                    f"- Generated at: {generated_at}",
                    f"- Nominated machines: {', '.join(machine_ids) if machine_ids else '-'}",
                    "- Baseline evidence exercises slot transition, boot success, bootctl, firmwarectl, and systemd-sysupdate presence.",
                    "",
                ]
            ),
        )
        write_text(
            known_limitations_md,
            "\n".join(
                [
                    "# Tier1 Hardware Baseline Known Limitations",
                    "",
                    "- This artifact is generated from synthetic boot evidence to keep the release gate machine-readable by default.",
                    "- It does not replace vendor-specific install, firstboot, rollback, or recovery sign-off on real nominated machines.",
                    f"- Nominated machines manifest: {args.tier1_nominations}",
                    "",
                ]
            ),
        )

        run_command(
            [
                sys.executable,
                str(HARDWARE_VALIDATION_RENDERER),
                "--profile",
                str(args.profile),
                "--evaluator-json",
                str(boot_report_json),
                "--report-out",
                str(validation_report_md),
                "--evidence-index-out",
                str(evidence_index_json),
                "--machine-vendor",
                "AIOS",
                "--machine-model",
                "Tier1 default release-gate baseline",
                "--machine-serial",
                "synthetic-tier1-release-gate",
                "--firmware-version",
                "baseline-synthetic",
                "--operator",
                "release-gate-default",
                "--support-matrix",
                str(support_matrix_md),
                "--known-limitations",
                str(known_limitations_md),
                "--note",
                "Synthetic Tier 1 release-gate baseline; attach real-machine sign-off separately.",
                "--note",
                f"Nominated machines manifest: {args.tier1_nominations}",
                "--validation-status",
                "passed",
            ]
        )

        evidence_index = json.loads(evidence_index_json.read_text(encoding="utf-8"))
        notes = [
            *[str(item) for item in evidence_index.get("notes", []) if isinstance(item, str) and item],
            "Synthetic Tier 1 release-gate baseline; attach real-machine sign-off separately.",
        ]
        evidence_index["baseline_kind"] = "synthetic-tier1-release-gate"
        evidence_index["validation_scope"] = "default-release-gate"
        evidence_index["real_machine_signoff_status"] = "pending-separate-evidence"
        evidence_index["nominated_machines_manifest"] = str(args.tier1_nominations)
        evidence_index["nominated_machine_ids"] = machine_ids
        evidence_index["nominated_machine_count"] = len(machine_ids)
        evidence_index["artifacts"]["boot_evidence_report"] = str(boot_report_json)
        evidence_index["artifacts"]["boot_evidence_markdown"] = str(boot_report_md)
        evidence_index["notes"] = notes
        write_json(evidence_index_json, evidence_index)

        boot_report_validator.validate(json.loads(boot_report_json.read_text(encoding="utf-8")))
        evidence_index_validator.validate(json.loads(evidence_index_json.read_text(encoding="utf-8")))

        print(
            json.dumps(
                {
                    "boot_report_json": str(boot_report_json),
                    "boot_report_md": str(boot_report_md),
                    "validation_report_md": str(validation_report_md),
                    "evidence_index_json": str(evidence_index_json),
                    "nominated_machine_count": len(machine_ids),
                    "baseline_kind": evidence_index["baseline_kind"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        if args.keep_temp:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
