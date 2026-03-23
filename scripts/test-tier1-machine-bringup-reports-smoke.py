#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = ROOT / "out" / "tmp"


def build_validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    evidence_index_validator = build_validator(
        ROOT / "aios" / "hardware" / "schemas" / "hardware-validation-evidence-index.schema.json"
    )

    temp_root = make_temp_dir("aios-tier1-machine-bringup-smoke-")
    output_dir = temp_root / "validation"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build-default-hardware-evidence-index.py"),
            "--output-dir",
            str(output_dir),
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

    summary_json = output_dir / "tier1-machine-bringup-summary.json"
    summary_md = output_dir / "tier1-machine-bringup-summary.md"
    require(summary_json.exists(), "missing tier1 machine bring-up summary json")
    require(summary_md.exists(), "missing tier1 machine bring-up summary markdown")

    summary = load_json(summary_json)
    reports = summary.get("machine_reports")
    require(isinstance(reports, list) and len(reports) == 2, "expected two nominated machine reports")

    by_machine = {item["machine_id"]: item for item in reports if isinstance(item, dict) and "machine_id" in item}
    require("framework-laptop-13-amd-7040" in by_machine, "missing framework nominated report")
    require("nvidia-jetson-orin-agx" in by_machine, "missing jetson nominated report")

    for machine_id, expected_platform in [
        ("framework-laptop-13-amd-7040", "generic-x86_64-uefi"),
        ("nvidia-jetson-orin-agx", "nvidia-jetson-orin-agx"),
    ]:
        item = by_machine[machine_id]
        require(item["validation_status"] == "pending", f"{machine_id} validation status mismatch")
        require(
            item["real_machine_signoff_status"] == "pending-separate-evidence",
            f"{machine_id} real-machine signoff mismatch",
        )

        report_path = Path(item["report"])
        evidence_index_path = Path(item["evidence_index"])
        device_metadata_path = Path(item["device_metadata_artifact"])
        support_matrix_path = Path(item["support_matrix"])
        known_limitations_path = Path(item["known_limitations"])
        boot_report_json = Path(item["boot_report_json"])
        boot_report_md = Path(item["boot_report_md"])

        for artifact in [
            report_path,
            evidence_index_path,
            device_metadata_path,
            support_matrix_path,
            known_limitations_path,
            boot_report_json,
            boot_report_md,
        ]:
            require(artifact.exists(), f"{machine_id} missing artifact: {artifact}")

        report_text = report_path.read_text(encoding="utf-8")
        require("- Validation status: pending" in report_text, f"{machine_id} report validation status missing")
        require(
            "- Real machine sign-off" not in report_text,
            f"{machine_id} report should keep renderer output stable without extra signoff lines",
        )

        evidence_index = load_json(evidence_index_path)
        evidence_index_validator.validate(evidence_index)
        require(
            evidence_index["baseline_kind"] == "nominated-machine-profile-baseline",
            f"{machine_id} baseline_kind mismatch",
        )
        require(
            evidence_index["real_machine_signoff_status"] == "pending-separate-evidence",
            f"{machine_id} evidence signoff mismatch",
        )
        require(
            evidence_index["validation_status"] == "pending",
            f"{machine_id} evidence validation status mismatch",
        )
        require(
            evidence_index["nominated_machine_ids"] == [machine_id],
            f"{machine_id} nominated_machine_ids mismatch",
        )
        require(
            evidence_index["nominated_machine_count"] == 1,
            f"{machine_id} nominated_machine_count mismatch",
        )
        require(
            evidence_index["device_runtime"]["device_profile"]["hardware_profile_id"] == machine_id,
            f"{machine_id} device profile id mismatch",
        )
        require(
            evidence_index["device_runtime"]["device_profile"]["platform_media_id"] == expected_platform,
            f"{machine_id} platform_media_id mismatch",
        )
        require(
            evidence_index["device_runtime"]["device_profile"]["profile_alignment_status"] == "aligned",
            f"{machine_id} profile alignment mismatch",
        )
        require(
            evidence_index["device_runtime"]["device_profile"]["validation_status"]
            == "pending-real-machine-evidence",
            f"{machine_id} device profile validation status mismatch",
        )

    summary_text = summary_md.read_text(encoding="utf-8")
    require(
        "`framework-laptop-13-amd-7040`" in summary_text and "`nvidia-jetson-orin-agx`" in summary_text,
        "summary markdown missing nominated machines",
    )

    print(
        json.dumps(
            {
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
                "machine_count": len(reports),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
