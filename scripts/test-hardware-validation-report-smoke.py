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
    schema = json.loads(path.read_text())
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


def main() -> int:
    evidence_index_validator = build_validator(
        ROOT / "aios" / "hardware" / "schemas" / "hardware-validation-evidence-index.schema.json"
    )

    temp_root = make_temp_dir("aios-hardware-validation-report-")
    profile_path = temp_root / "tier1-profile.yaml"
    evaluator_path = temp_root / "evaluator.json"
    report_out = temp_root / "hardware-validation-report.md"
    evidence_index_out = temp_root / "hardware-validation-evidence.json"
    support_matrix_path = temp_root / "support-matrix.md"
    known_limitations_path = temp_root / "known-limitations.md"
    device_metadata_path = temp_root / "device-metadata.json"
    vendor_runtime_evidence = temp_root / "vendor-runtime-evidence.json"

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
    backend_evidence_dir = temp_root / "backend-evidence"
    backend_evidence_dir.mkdir(parents=True, exist_ok=True)
    screen_evidence = backend_evidence_dir / "screen-backend-evidence.json"
    screen_evidence.write_text(
        json.dumps(
            {
                "modality": "screen",
                "release_grade_backend_id": "xdg-desktop-portal-screencast",
                "release_grade_backend_origin": "os-native",
                "release_grade_backend_stack": "portal+pipewire",
                "release_grade_contract_kind": "release-grade-runtime-helper",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    audio_evidence = backend_evidence_dir / "audio-backend-evidence.json"
    audio_evidence.write_text(
        json.dumps(
            {
                "modality": "audio",
                "release_grade_backend_id": "pipewire",
                "release_grade_backend_origin": "os-native",
                "release_grade_backend_stack": "pipewire",
                "contract_kind": "release-grade-runtime-helper",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    backend_state_path = temp_root / "backend-state.json"
    vendor_runtime_evidence.write_text(
        json.dumps(
            {
                "backend_id": "local-gpu",
                "provider_id": "nvidia.jetson.tensorrt",
                "provider_kind": "trtexec",
                "provider_status": "available",
                "runtime_service_id": "aios-runtimed.jetson-vendor-helper",
                "contract_kind": "vendor-runtime-evidence-v1",
                "engine_path": "/var/lib/aios/runtime/vendor-engines/local-gpu.plan",
                "runtime_binary": "/usr/bin/trtexec",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    backend_state_path.write_text(
        json.dumps(
            {
                "notes": [
                    f"backend_evidence_artifact[screen]={screen_evidence}",
                    f"backend_evidence_artifact[audio]={audio_evidence}",
                ],
                "statuses": [
                    {
                        "modality": "screen",
                        "details": [f"evidence_artifact={screen_evidence}"],
                    },
                    {
                        "modality": "audio",
                        "details": [f"evidence_artifact={audio_evidence}"],
                    },
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    device_metadata_path.write_text(
        json.dumps(
            {
                "provider_id": "device.metadata.local",
                "notes": [
                    "hardware_profile_id=framework-laptop-13-amd-7040",
                    "hardware_profile_path=/usr/share/aios/hardware/profiles/framework-laptop-13-amd-7040.yaml",
                    "hardware_profile_canonical_id=generic-x86_64-uefi",
                    "hardware_profile_platform_media_id=generic-x86_64-uefi",
                    "hardware_profile_platform_tier=tier1",
                    "hardware_profile_bringup_status=nominated-formal-tier1",
                    "hardware_profile_runtime_profile=/etc/aios/runtime/default-runtime-profile.yaml",
                    "hardware_profile_hardware_evidence_required=true",
                    "hardware_profile_validation_status=matched",
                    "hardware_profile_required_modalities=audio,camera,input,screen,ui_tree",
                    "hardware_profile_conditional_modalities=",
                    "hardware_profile_available_expected_modalities=audio,camera,input,screen,ui_tree",
                    "hardware_profile_missing_required_modalities=",
                    "hardware_profile_missing_conditional_modalities=",
                    "hardware_profile_release_track_intent=developer-preview,product-preview",
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
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
            "--deviced-health",
            "ready",
            "--device-backend-overall-status",
            "ready",
            "--device-backend-available-count",
            "5",
            "--device-ui-tree-support",
            "native-live",
            "--device-metadata-status",
            "ready",
            "--device-metadata-backend-status",
            "ready",
            "--device-available-modalities",
            "audio,camera,input,screen,ui_tree",
            "--device-metadata-artifact",
            str(device_metadata_path),
            "--device-backend-state-artifact",
            str(backend_state_path),
            "--vendor-runtime-evidence",
            str(vendor_runtime_evidence),
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
    require("## Device And Multimodal Validation" in report_text, "report device validation section missing")
    require("- deviced health: ready" in report_text, "report deviced health mismatch")
    require("- device.state.get overall backend status: ready" in report_text, "report device backend overall status mismatch")
    require("- device.state.get available backend count: 5" in report_text, "report device backend count mismatch")
    require("- device.state.get ui_tree current support: native-live" in report_text, "report device ui_tree support mismatch")
    require("- device.metadata.get readiness status: ready" in report_text, "report device metadata status mismatch")
    require("- device.metadata.get backend overall status: ready" in report_text, "report device metadata backend status mismatch")
    require(
        "- device.metadata.get available modalities: audio,camera,input,screen,ui_tree" in report_text,
        "report device metadata modalities mismatch",
    )
    require(
        f"- device.metadata artifact attached: {device_metadata_path}" in report_text,
        "report device metadata artifact mismatch",
    )
    require(
        "- release-grade backend ids: pipewire,xdg-desktop-portal-screencast" in report_text,
        "report release-grade backend ids mismatch",
    )
    require(
        "- release-grade backend origins: os-native" in report_text,
        "report release-grade backend origins mismatch",
    )
    require(
        "- release-grade backend stacks: pipewire,portal+pipewire" in report_text,
        "report release-grade backend stacks mismatch",
    )
    require(
        "- release-grade contract kinds: release-grade-runtime-helper" in report_text,
        "report release-grade contract kinds mismatch",
    )
    require(
        f"- backend-state artifact attached: {backend_state_path}" in report_text,
        "report backend-state artifact mismatch",
    )
    require(
        "- vendor runtime sign-off status: evidence-attached" in report_text,
        "report vendor runtime sign-off status mismatch",
    )
    require(
        "- vendor runtime provider ids: nvidia.jetson.tensorrt" in report_text,
        "report vendor runtime provider ids mismatch",
    )
    require(
        "- vendor runtime service ids: aios-runtimed.jetson-vendor-helper" in report_text,
        "report vendor runtime service ids mismatch",
    )
    require(
        f"- vendor runtime evidence attached: {vendor_runtime_evidence}" in report_text,
        "report vendor runtime evidence path mismatch",
    )
    require("## Device Profile Alignment" in report_text, "report device profile alignment section missing")
    require(
        "- Runtime hardware profile id: framework-laptop-13-amd-7040" in report_text,
        "report runtime hardware profile id mismatch",
    )
    require(
        "- Runtime canonical hardware profile id: generic-x86_64-uefi" in report_text,
        "report runtime canonical hardware profile id mismatch",
    )
    require(
        "- Runtime profile alignment: aligned" in report_text,
        "report runtime profile alignment mismatch",
    )
    require(
        "- Runtime validation status: matched" in report_text,
        "report runtime validation status mismatch",
    )
    require(
        "- Runtime required modalities: audio,camera,input,screen,ui_tree" in report_text,
        "report runtime required modalities mismatch",
    )

    evidence_index = json.loads(evidence_index_out.read_text())
    evidence_index_validator.validate(evidence_index)
    require(evidence_index["platform_id"] == "generic-x86_64-uefi", "evidence index platform mismatch")
    require(evidence_index["validation_status"] == "passed", "evidence index status mismatch")
    require(evidence_index["summary"]["final_current_slot"] == "b", "evidence index final current slot mismatch")
    require(evidence_index["artifacts"]["photos"] == ["photo-1.jpg"], "evidence index photos mismatch")
    require(evidence_index["artifacts"]["support_matrix"] == str(support_matrix_path), "evidence index support matrix mismatch")
    require(evidence_index["artifacts"]["known_limitations"] == str(known_limitations_path), "evidence index known limitations mismatch")
    require(evidence_index["artifacts"]["device_metadata_artifact"] == str(device_metadata_path), "evidence index device metadata artifact mismatch")
    require(evidence_index["artifacts"]["device_backend_state_artifact"] == str(backend_state_path), "evidence index backend-state artifact mismatch")
    require(evidence_index["artifacts"]["vendor_runtime_evidence"] == [str(vendor_runtime_evidence)], "evidence index vendor runtime evidence mismatch")
    require(evidence_index["device_runtime"]["device_profile"]["hardware_profile_id"] == "framework-laptop-13-amd-7040", "evidence index device profile id mismatch")
    require(evidence_index["device_runtime"]["device_profile"]["profile_alignment_status"] == "aligned", "evidence index device profile alignment mismatch")
    require(evidence_index["device_runtime"]["device_profile"]["required_modalities"] == ["audio", "camera", "input", "screen", "ui_tree"], "evidence index device profile required modalities mismatch")
    require(evidence_index["device_runtime"]["vendor_runtime"]["vendor_runtime_signoff_status"] == "evidence-attached", "evidence index vendor runtime signoff mismatch")
    require(evidence_index["device_runtime"]["vendor_runtime"]["provider_ids"] == ["nvidia.jetson.tensorrt"], "evidence index vendor runtime provider ids mismatch")
    require(evidence_index["operator"] == "codex", "evidence index operator mismatch")
    print(json.dumps({"report_out": str(report_out), "evidence_index_out": str(evidence_index_out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
