#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="aios-hardware-validation-report-"))
    profile_path = temp_root / "tier1-profile.yaml"
    evaluator_path = temp_root / "evaluator.json"
    report_out = temp_root / "hardware-validation-report.md"
    evidence_index_out = temp_root / "hardware-validation-evidence.json"
    support_matrix_path = temp_root / "support-matrix.md"
    known_limitations_path = temp_root / "known-limitations.md"

    profile_path.write_text(
        "\n".join(
            [
                "id: generic-x86_64-uefi-tier1",
                "platform_media_id: generic-x86_64-uefi",
                "updated_platform_profile: /usr/share/aios/updated/platforms/generic-x86_64-uefi/profile.yaml",
                "",
            ]
        )
    )
    support_matrix_path.write_text("# Support Matrix\n\n- GPU: optional\n")
    known_limitations_path.write_text("# Known Limitations\n\n- Hardware evidence pending\n")
    evaluator_path.write_text(
        json.dumps(
            {
                "passed": True,
                "record_count": 2,
                "unique_boot_ids": ["boot-a", "boot-b"],
                "input_dir": "/var/lib/aios/hardware-evidence/boots",
                "checks": [
                    {"name": "minimum_boots", "passed": True, "detail": "observed 2 unique boot ids"},
                    {"name": "slot_transition", "passed": True, "detail": "first=a last=b expected=a->b"},
                ],
                "record_summaries": [
                    {
                        "path": "/tmp/boot-a.json",
                        "boot_id": "boot-a",
                        "current_slot": "a",
                        "last_good_slot": "a",
                    },
                    {
                        "path": "/tmp/boot-b.json",
                        "boot_id": "boot-b",
                        "current_slot": "b",
                        "last_good_slot": "b",
                    },
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "render-aios-hardware-validation-report.py"),
            "--profile",
            str(profile_path),
            "--evaluator-json",
            str(evaluator_path),
            "--report-out",
            str(report_out),
            "--evidence-index-out",
            str(evidence_index_out),
            "--machine-vendor",
            "Generic",
            "--machine-model",
            "x86_64 devkit",
            "--machine-serial",
            "serial-1",
            "--firmware-version",
            "FW-1.2.3",
            "--operator",
            "codex",
            "--installer-image",
            "installer.raw",
            "--recovery-image",
            "recovery.raw",
            "--system-image",
            "system.raw",
            "--support-matrix",
            str(support_matrix_path),
            "--known-limitations",
            str(known_limitations_path),
            "--photo",
            "photo-1.jpg",
            "--note",
            "No open issues",
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

    report_text = report_out.read_text()
    require("# generic-x86_64-uefi Hardware Validation Report" in report_text, "report title mismatch")
    require("- Vendor: Generic" in report_text, "report vendor mismatch")
    require("- Boot IDs observed: boot-a, boot-b" in report_text, "report boot ids mismatch")
    require("- Final active slot / last-good-slot: b / b" in report_text, "report final slot mismatch")
    require("- Validation status: passed" in report_text, "report validation status mismatch")
    require(f"- Support matrix: {support_matrix_path}" in report_text, "report support matrix mismatch")
    require(f"- Known limitations: {known_limitations_path}" in report_text, "report known limitations mismatch")

    evidence_index = json.loads(evidence_index_out.read_text())
    require(evidence_index["platform_id"] == "generic-x86_64-uefi", "evidence index platform mismatch")
    require(evidence_index["validation_status"] == "passed", "evidence index status mismatch")
    require(evidence_index["summary"]["final_current_slot"] == "b", "evidence index final current slot mismatch")
    require(evidence_index["artifacts"]["photos"] == ["photo-1.jpg"], "evidence index photos mismatch")
    require(evidence_index["artifacts"]["support_matrix"] == str(support_matrix_path), "evidence index support matrix mismatch")
    require(evidence_index["artifacts"]["known_limitations"] == str(known_limitations_path), "evidence index known limitations mismatch")
    require(evidence_index["operator"] == "codex", "evidence index operator mismatch")
    print(json.dumps({"report_out": str(report_out), "evidence_index_out": str(evidence_index_out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
