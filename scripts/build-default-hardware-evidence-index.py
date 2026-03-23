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
DEFAULT_MACHINE_REPORT_DIR = "tier1-machine-bringup"


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


def platform_profile_path(platform_media_id: str | None) -> Path | None:
    if not platform_media_id:
        return None
    candidate = ROOT / "aios" / "image" / "platforms" / platform_media_id / "profile.yaml"
    if candidate.exists():
        return candidate
    return None


def join_csv(values: list[str]) -> str:
    return ",".join(values)


def append_arg(arguments: list[str], name: str, value: str | None) -> None:
    if value is None:
        return
    text = value.strip()
    if not text:
        return
    arguments.extend([f"--{name}", text])


def machine_cpu_ram_storage(profile: dict[str, Any]) -> str:
    parts = []
    for key in ("arch", "gpu", "npu"):
        value = profile.get(key)
        if isinstance(value, str) and value:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def release_track_intent(nomination: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    raw = nomination.get("release_track_intent")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    raw = profile.get("release_track_intent")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    return []


def modality_expectations(profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    required = ["screen", "input"]
    conditional = ["ui_tree"]
    for field in ("audio", "camera"):
        value = profile.get(field)
        if value == "required":
            required.append(field)
        elif value == "optional":
            conditional.append(field)
    return required, conditional


def build_device_metadata_payload(
    profile_path: Path,
    profile: dict[str, Any],
    nomination: dict[str, Any],
) -> dict[str, Any]:
    required_modalities, conditional_modalities = modality_expectations(profile)
    runtime_profile = nomination.get("runtime_profile") or profile.get("runtime_profile") or ""
    platform_media_id = (
        nomination.get("platform_media_id")
        or profile.get("platform_media_id")
        or profile.get("canonical_hardware_profile_id")
        or profile.get("id")
        or ""
    )
    canonical_hardware_profile_id = (
        nomination.get("canonical_hardware_profile_id")
        or profile.get("canonical_hardware_profile_id")
        or platform_media_id
    )
    evidence_status = nomination.get("evidence_status") or profile.get("bringup_status") or "pending-real-machine-evidence"
    release_tracks = release_track_intent(nomination, profile)
    notes = [
        f"hardware_profile_id={profile.get('id', '')}",
        f"hardware_profile_path={profile_path}",
        f"hardware_profile_canonical_id={canonical_hardware_profile_id}",
        f"hardware_profile_platform_media_id={platform_media_id}",
        f"hardware_profile_platform_tier={profile.get('platform_tier', '')}",
        f"hardware_profile_bringup_status={evidence_status}",
        f"hardware_profile_runtime_profile={runtime_profile}",
        f"hardware_profile_hardware_evidence_required={str(bool(profile.get('hardware_evidence_required', True))).lower()}",
        "hardware_profile_validation_status=pending-real-machine-evidence",
        f"hardware_profile_required_modalities={join_csv(required_modalities)}",
        f"hardware_profile_conditional_modalities={join_csv(conditional_modalities)}",
        "hardware_profile_available_expected_modalities=",
        f"hardware_profile_missing_required_modalities={join_csv(required_modalities)}",
        f"hardware_profile_missing_conditional_modalities={join_csv(conditional_modalities)}",
        f"hardware_profile_release_track_intent={join_csv(release_tracks)}",
    ]
    return {
        "provider_id": "device.metadata.local",
        "summary": {
            "overall_status": "pending-real-machine-evidence",
            "available_modalities": [],
        },
        "backend_summary": {
            "overall_status": "pending-real-machine-evidence",
        },
        "notes": notes,
    }


def render_machine_support_matrix(
    machine_id: str,
    nomination: dict[str, Any],
    profile: dict[str, Any],
    platform_profile: Path | None,
    generated_at: str,
) -> str:
    required_modalities, conditional_modalities = modality_expectations(profile)
    return "\n".join(
        [
            f"# {machine_id} Tier1 Bring-up Support Matrix",
            "",
            f"- Generated at: {generated_at}",
            f"- Machine ID: {machine_id}",
            f"- Profile path: {nomination.get('profile_path', '-')}",
            f"- Platform media ID: {nomination.get('platform_media_id') or profile.get('platform_media_id') or '-'}",
            f"- Platform media profile: {platform_profile or '-'}",
            f"- Updated platform profile: {nomination.get('updated_platform_profile') or profile.get('updated_platform_profile') or '-'}",
            f"- Runtime profile: {nomination.get('runtime_profile') or profile.get('runtime_profile') or '-'}",
            f"- Evidence status: {nomination.get('evidence_status') or profile.get('bringup_status') or '-'}",
            f"- Required modalities: {join_csv(required_modalities) or '-'}",
            f"- Conditional modalities: {join_csv(conditional_modalities) or '-'}",
            "",
        ]
    )


def render_machine_known_limitations(
    machine_id: str,
    nomination: dict[str, Any],
    profile: dict[str, Any],
) -> str:
    lines = [
        f"# {machine_id} Tier1 Bring-up Known Limitations",
        "",
        "- This report records the nominated-machine baseline, not real-machine sign-off.",
        "- Real install, firstboot, update, rollback, and recovery evidence must be attached separately.",
        f"- Current evidence status: {nomination.get('evidence_status') or profile.get('bringup_status') or 'pending-real-machine-evidence'}",
    ]
    for note in nomination.get("notes") or []:
        lines.append(f"- {note}")
    for note in profile.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def build_boot_records() -> list[dict[str, Any]]:
    return [
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


def write_boot_records(boots_dir: Path) -> None:
    boots_dir.mkdir(parents=True, exist_ok=True)
    for index, record in enumerate(build_boot_records(), start=1):
        write_json(boots_dir / f"boot-{index}.json", record)


def machine_report_paths(output_dir: Path, machine_id: str) -> dict[str, Path]:
    machine_root = output_dir / DEFAULT_MACHINE_REPORT_DIR / machine_id
    return {
        "root": machine_root,
        "boots_dir": machine_root / "boots",
        "boot_report_json": machine_root / "hardware-boot-evidence-report.json",
        "boot_report_md": machine_root / "hardware-boot-evidence-report.md",
        "support_matrix_md": machine_root / "support-matrix.md",
        "known_limitations_md": machine_root / "known-limitations.md",
        "device_metadata_json": machine_root / "device-metadata.json",
        "validation_report_md": machine_root / "hardware-validation-report.md",
        "evidence_index_json": machine_root / "hardware-validation-evidence.json",
    }


def build_machine_report(
    *,
    output_dir: Path,
    nomination: dict[str, Any],
    boot_report_validator: Draft202012Validator,
    evidence_index_validator: Draft202012Validator,
    tier1_nominations_path: Path,
) -> dict[str, Any]:
    machine_id = str(nomination.get("machine_id"))
    profile_path = ROOT / str(nomination.get("profile_path"))
    profile = load_yaml_or_json(profile_path)
    paths = machine_report_paths(output_dir, machine_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    platform_profile = platform_profile_path(
        str(nomination.get("platform_media_id") or profile.get("platform_media_id") or "")
    )

    write_boot_records(paths["boots_dir"])
    run_command(
        [
            sys.executable,
            str(HARDWARE_BOOT_EVIDENCE_EVALUATOR),
            "--input-dir",
            str(paths["boots_dir"]),
            "--profile",
            str(profile_path),
            "--output",
            str(paths["boot_report_json"]),
            "--report-md",
            str(paths["boot_report_md"]),
        ]
    )

    write_text(
        paths["support_matrix_md"],
        render_machine_support_matrix(machine_id, nomination, profile, platform_profile, generated_at),
    )
    write_text(
        paths["known_limitations_md"],
        render_machine_known_limitations(machine_id, nomination, profile),
    )
    write_json(
        paths["device_metadata_json"],
        build_device_metadata_payload(profile_path, profile, nomination),
    )

    command = [
        sys.executable,
        str(HARDWARE_VALIDATION_RENDERER),
        "--profile",
        str(profile_path),
        "--evaluator-json",
        str(paths["boot_report_json"]),
        "--report-out",
        str(paths["validation_report_md"]),
        "--evidence-index-out",
        str(paths["evidence_index_json"]),
        "--machine-vendor",
        str(profile.get("vendor_id", "unknown")),
        "--machine-model",
        str(profile.get("model", machine_id)),
        "--machine-serial",
        f"baseline-{machine_id}",
        "--firmware-version",
        "baseline-synthetic",
        "--support-matrix",
        str(paths["support_matrix_md"]),
        "--known-limitations",
        str(paths["known_limitations_md"]),
        "--device-metadata-artifact",
        str(paths["device_metadata_json"]),
        "--operator",
        "tier1-machine-baseline",
        "--note",
        "Nominated machine bring-up report recorded from profile baseline; attach real-machine sign-off separately.",
        "--note",
        f"Nominated machines manifest: {tier1_nominations_path}",
        "--validation-status",
        "pending",
    ]
    append_arg(command, "machine-cpu-ram-storage", machine_cpu_ram_storage(profile))
    append_arg(command, "platform-media-manifest", None if platform_profile is None else str(platform_profile))
    run_command(command)

    boot_report = json.loads(paths["boot_report_json"].read_text(encoding="utf-8"))
    evidence_index = json.loads(paths["evidence_index_json"].read_text(encoding="utf-8"))
    evidence_index["baseline_kind"] = "nominated-machine-profile-baseline"
    evidence_index["validation_scope"] = "tier1-machine-report"
    evidence_index["real_machine_signoff_status"] = "pending-separate-evidence"
    evidence_index["nominated_machines_manifest"] = str(tier1_nominations_path)
    evidence_index["nominated_machine_ids"] = [machine_id]
    evidence_index["nominated_machine_count"] = 1
    write_json(paths["evidence_index_json"], evidence_index)

    boot_report_validator.validate(boot_report)
    evidence_index_validator.validate(json.loads(paths["evidence_index_json"].read_text(encoding="utf-8")))

    return {
        "machine_id": machine_id,
        "profile": str(profile_path),
        "platform_media_id": nomination.get("platform_media_id") or profile.get("platform_media_id"),
        "validation_status": "pending",
        "real_machine_signoff_status": "pending-separate-evidence",
        "report": str(paths["validation_report_md"]),
        "evidence_index": str(paths["evidence_index_json"]),
        "support_matrix": str(paths["support_matrix_md"]),
        "known_limitations": str(paths["known_limitations_md"]),
        "boot_report_json": str(paths["boot_report_json"]),
        "boot_report_md": str(paths["boot_report_md"]),
        "device_metadata_artifact": str(paths["device_metadata_json"]),
    }


def render_machine_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Tier1 Machine Bring-up Summary",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Source nominations: `{report['nominations_path']}`",
        f"- Report count: `{len(report['machine_reports'])}`",
        "",
        "| Machine | Validation | Real-machine sign-off | Report | Evidence index |",
        "|---------|------------|-----------------------|--------|----------------|",
    ]
    for item in report["machine_reports"]:
        lines.append(
            f"| `{item['machine_id']}` | `{item['validation_status']}` | "
            f"`{item['real_machine_signoff_status']}` | `{item['report']}` | `{item['evidence_index']}` |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- These reports close the repo-level bring-up report deliverable for each nominated machine.",
            "- They do not replace real-machine install, update, rollback, or recovery evidence.",
            "",
        ]
    )
    return "\n".join(lines)


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
    machine_summary_json = output_dir / "tier1-machine-bringup-summary.json"
    machine_summary_md = output_dir / "tier1-machine-bringup-summary.md"

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
        write_boot_records(boots_dir)

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

        machine_reports = [
            build_machine_report(
                output_dir=output_dir,
                nomination=nomination,
                boot_report_validator=boot_report_validator,
                evidence_index_validator=evidence_index_validator,
                tier1_nominations_path=args.tier1_nominations,
            )
            for nomination in nominated_machines
            if isinstance(nomination, dict) and nomination.get("machine_id") and nomination.get("profile_path")
        ]

        machine_summary = {
            "generated_at": generated_at,
            "nominations_path": str(args.tier1_nominations),
            "machine_reports": machine_reports,
        }
        write_json(machine_summary_json, machine_summary)
        write_text(machine_summary_md, render_machine_summary(machine_summary))

        print(
            json.dumps(
                {
                    "boot_report_json": str(boot_report_json),
                    "boot_report_md": str(boot_report_md),
                    "validation_report_md": str(validation_report_md),
                    "evidence_index_json": str(evidence_index_json),
                    "machine_summary_json": str(machine_summary_json),
                    "machine_summary_md": str(machine_summary_md),
                    "machine_report_count": len(machine_reports),
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
