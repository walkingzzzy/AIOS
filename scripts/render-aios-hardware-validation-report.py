#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render AIOS hardware validation report and evidence index from evaluator output"
    )
    parser.add_argument("--profile", type=Path, help="Optional Tier 1 profile YAML/JSON")
    parser.add_argument("--evaluator-json", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--evidence-index-out", type=Path, required=True)
    parser.add_argument("--platform-media-manifest", type=Path)
    parser.add_argument("--installer-image")
    parser.add_argument("--recovery-image")
    parser.add_argument("--system-image")
    parser.add_argument("--machine-vendor", default="")
    parser.add_argument("--machine-model", default="")
    parser.add_argument("--machine-serial", default="")
    parser.add_argument("--machine-cpu-ram-storage", default="")
    parser.add_argument("--firmware-version", default="")
    parser.add_argument("--installer-report", default="")
    parser.add_argument("--vendor-firmware-hook-report", default="")
    parser.add_argument("--installer-log", default="")
    parser.add_argument("--recovery-log", default="")
    parser.add_argument("--evaluator-md", default="")
    parser.add_argument("--support-matrix", default="")
    parser.add_argument("--known-limitations", default="")
    parser.add_argument("--photo", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--operator", default="")
    parser.add_argument("--date", default=None)
    parser.add_argument(
        "--validation-status",
        choices=["pending", "passed", "failed"],
        default=None,
        help="Override derived validation status",
    )
    return parser.parse_args()


def load_profile(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    text = path.read_text()
    if not text.strip():
        return {}
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return json.loads(text)


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text())


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def final_record(evaluator: dict[str, Any]) -> dict[str, Any]:
    summaries = evaluator.get("record_summaries") or []
    if summaries:
        return summaries[-1]
    return {}


def open_issues(evaluator: dict[str, Any], notes: list[str]) -> list[str]:
    issues = [check["detail"] for check in evaluator.get("checks", []) if not check.get("passed", False)]
    issues.extend(note for note in notes if note)
    return issues


def resolved_date(raw_date: str | None) -> str:
    if raw_date:
        return raw_date
    return datetime.now(timezone.utc).date().isoformat()


def render_report(
    profile: dict[str, Any],
    evaluator: dict[str, Any],
    args: argparse.Namespace,
    status: str,
) -> str:
    final = final_record(evaluator)
    platform_id = (
        profile.get("platform_media_id")
        or profile.get("id")
        or "unknown-platform"
    )
    boot_ids = ", ".join(evaluator.get("unique_boot_ids", [])) or "-"
    issues = open_issues(evaluator, args.note)
    issue_lines = ["- None"] if not issues else [f"- {item}" for item in issues]
    report_lines = [
        f"# {platform_id} Hardware Validation Report",
        "",
        "## Machine Identity",
        "",
        f"- Vendor: {args.machine_vendor or '-'}",
        f"- Model: {args.machine_model or '-'}",
        f"- Serial / Asset Tag: {args.machine_serial or '-'}",
        f"- CPU / RAM / Storage: {args.machine_cpu_ram_storage or '-'}",
        f"- Firmware Version: {args.firmware_version or '-'}",
        "",
        "## Media and Build Inputs",
        "",
        f"- Installer image: {args.installer_image or '-'}",
        f"- Recovery image: {args.recovery_image or '-'}",
        f"- System image: {args.system_image or '-'}",
        f"- Platform media manifest: {str(args.platform_media_manifest) if args.platform_media_manifest else '-'}",
        f"- Tier1 profile: {str(args.profile) if args.profile else '-'}",
        f"- Support matrix: {args.support_matrix or '-'}",
        f"- Known limitations: {args.known_limitations or '-'}",
        "",
        "## Install Outcome",
        "",
        f"- Installer boot observed: {'yes' if args.installer_report or args.installer_log else 'pending'}",
        f"- Guided installer summary verified: {'pending' if not args.installer_report else 'see installer report'}",
        "- Target disk selected: pending",
        f"- Installer report attached: {args.installer_report or '-'}",
        f"- Vendor firmware hook report attached: {args.vendor_firmware_hook_report or '-'}",
        "",
        "## First Boot Outcome",
        "",
        f"- Firstboot completed: {'yes' if evaluator.get('passed') else 'pending'}",
        f"- Updated platform profile verified: {profile.get('updated_platform_profile', '-')}",
        f"- Boot evidence directory collected: {evaluator.get('input_dir', '-')}",
        f"- Boot IDs observed: {boot_ids}",
        "",
        "## Rollback Outcome",
        "",
        "- Rollback trigger used: pending",
        f"- Recovery media boot observed: {'pending' if not args.recovery_log else 'see recovery log'}",
        f"- Post-rollback boot observed: {'yes' if evaluator.get('passed') else 'pending'}",
        f"- Final active slot / last-good-slot: {final.get('current_slot') or '-'} / {final.get('last_good_slot') or '-'}",
        "",
        "## Attached Evidence",
        "",
        f"- Evaluator JSON: {args.evaluator_json}",
        f"- Evaluator Markdown: {args.evaluator_md or '-'}",
        f"- Installer log: {args.installer_log or '-'}",
        f"- Recovery log: {args.recovery_log or '-'}",
        f"- Photos / serial captures: {', '.join(args.photo) if args.photo else '-'}",
        "",
        "## Open Issues",
        "",
        *issue_lines,
        "",
        "## Sign-off",
        "",
        f"- Operator: {args.operator or '-'}",
        f"- Date: {resolved_date(args.date)}",
        f"- Validation status: {status}",
        "",
    ]
    return "\n".join(report_lines)


def build_evidence_index(
    profile: dict[str, Any],
    evaluator: dict[str, Any],
    args: argparse.Namespace,
    status: str,
) -> dict[str, Any]:
    final = final_record(evaluator)
    return {
        "platform_id": profile.get("platform_media_id") or profile.get("id") or "unknown-platform",
        "profile": None if args.profile is None else str(args.profile),
        "validation_status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "passed": evaluator.get("passed"),
            "record_count": evaluator.get("record_count"),
            "unique_boot_ids": evaluator.get("unique_boot_ids", []),
            "final_current_slot": final.get("current_slot"),
            "final_last_good_slot": final.get("last_good_slot"),
        },
        "artifacts": {
            "platform_media_manifest": "" if args.platform_media_manifest is None else str(args.platform_media_manifest),
            "installer_image": args.installer_image,
            "recovery_image": args.recovery_image,
            "system_image": args.system_image,
            "installer_report": args.installer_report,
            "vendor_firmware_hook_report": args.vendor_firmware_hook_report,
            "evaluator_json": str(args.evaluator_json),
            "evaluator_markdown": args.evaluator_md,
            "support_matrix": args.support_matrix,
            "known_limitations": args.known_limitations,
            "installer_log": args.installer_log,
            "recovery_log": args.recovery_log,
            "photos": args.photo,
        },
        "checks": evaluator.get("checks", []),
        "notes": open_issues(evaluator, args.note),
        "operator": args.operator,
        "date": resolved_date(args.date),
    }


def main() -> int:
    args = parse_args()
    profile = load_profile(args.profile)
    evaluator = load_json(args.evaluator_json)
    status = args.validation_status or ("passed" if evaluator.get("passed") else "failed")
    report_text = render_report(profile, evaluator, args, status)
    evidence_index = build_evidence_index(profile, evaluator, args, status)
    write_text(args.report_out, report_text)
    write_json(args.evidence_index_out, evidence_index)
    print(
        json.dumps(
            {
                "report_out": str(args.report_out),
                "evidence_index_out": str(args.evidence_index_out),
                "validation_status": status,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
