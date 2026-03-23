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
    parser.add_argument("--deviced-health", default="")
    parser.add_argument("--device-backend-overall-status", default="")
    parser.add_argument("--device-backend-available-count", default="")
    parser.add_argument("--device-ui-tree-support", default="")
    parser.add_argument("--device-metadata-status", default="")
    parser.add_argument("--device-metadata-backend-status", default="")
    parser.add_argument("--device-available-modalities", default="")
    parser.add_argument("--device-metadata-artifact", default="")
    parser.add_argument("--device-backend-state-artifact", default="")
    parser.add_argument("--device-release-grade-backend-ids", default="")
    parser.add_argument("--device-release-grade-backend-origins", default="")
    parser.add_argument("--device-release-grade-backend-stacks", default="")
    parser.add_argument("--device-release-grade-contract-kinds", default="")
    parser.add_argument(
        "--vendor-runtime-evidence",
        action="append",
        default=[],
        help="Optional vendor runtime evidence JSON path; may be repeated",
    )
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
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return json.loads(text)


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def sorted_join(values: set[str]) -> str:
    if not values:
        return ""
    return ",".join(sorted(values))


def note_map(notes: list[object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for note in notes:
        if not isinstance(note, str) or "=" not in note:
            continue
        key, value = note.split("=", 1)
        values[key] = value
    return values


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in (part.strip() for part in value.split(",")) if item]


def note_value(notes: list[object], prefix: str) -> str | None:
    for note in notes:
        if not isinstance(note, str):
            continue
        if note.startswith(prefix):
            return note[len(prefix) :]
    return None


def append_unique_path(paths: list[Path], seen: set[str], path_text: str | None) -> None:
    if not path_text:
        return
    candidate = str(Path(path_text))
    if candidate in seen:
        return
    seen.add(candidate)
    paths.append(Path(candidate))


def backend_evidence_paths(payload: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()

    notes = payload.get("notes")
    if isinstance(notes, list):
        for note in notes:
            if not isinstance(note, str):
                continue
            if note.startswith("backend_evidence_artifact[") and "=" in note:
                append_unique_path(paths, seen, note.split("=", 1)[1])

    statuses = payload.get("statuses")
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict):
                continue
            details = status.get("details")
            if not isinstance(details, list):
                continue
            append_unique_path(paths, seen, note_value(details, "evidence_artifact="))

    evidence_artifacts = payload.get("evidence_artifacts")
    if isinstance(evidence_artifacts, list):
        for artifact in evidence_artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_path = artifact.get("artifact_path")
            if isinstance(artifact_path, str):
                append_unique_path(paths, seen, artifact_path)

    return paths


def vendor_runtime_evidence_paths_from_payload(payload: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()

    notes = payload.get("notes")
    if isinstance(notes, list):
        for note in notes:
            if not isinstance(note, str):
                continue
            if note.startswith("vendor_evidence_path="):
                append_unique_path(paths, seen, note.split("=", 1)[1])

    statuses = payload.get("statuses")
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict):
                continue
            details = status.get("details")
            if not isinstance(details, list):
                continue
            append_unique_path(paths, seen, note_value(details, "vendor_evidence_path="))

    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key == "vendor_evidence_path" and isinstance(value, str):
                    append_unique_path(paths, seen, value)
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)

    return paths


def collect_vendor_runtime_evidence_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()

    for item in args.vendor_runtime_evidence:
        append_unique_path(paths, seen, item)

    if args.device_backend_state_artifact:
        artifact_path = Path(args.device_backend_state_artifact)
        if artifact_path.exists():
            try:
                backend_state = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                backend_state = {}
            if isinstance(backend_state, dict):
                for evidence_path in vendor_runtime_evidence_paths_from_payload(backend_state):
                    append_unique_path(paths, seen, str(evidence_path))

    return paths


def normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def profile_alignment_status(profile: dict[str, Any], device_profile: dict[str, Any]) -> str:
    report_ids = {
        value
        for value in [
            normalize_text(profile.get("id")),
            normalize_text(profile.get("canonical_hardware_profile_id")),
            normalize_text(profile.get("platform_media_id")),
        ]
        if value
    }
    runtime_ids = {
        value
        for value in [
            normalize_text(device_profile.get("hardware_profile_id")),
            normalize_text(device_profile.get("canonical_hardware_profile_id")),
            normalize_text(device_profile.get("platform_media_id")),
        ]
        if value
    }
    if not report_ids or not runtime_ids:
        return "unknown"
    return "aligned" if report_ids & runtime_ids else "mismatch"


def derive_device_profile_summary(profile: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    summary = {
        "metadata_artifact": normalize_text(args.device_metadata_artifact),
        "hardware_profile_id": None,
        "hardware_profile_path": None,
        "canonical_hardware_profile_id": None,
        "platform_media_id": None,
        "platform_tier": None,
        "bringup_status": None,
        "runtime_profile": None,
        "hardware_evidence_required": None,
        "validation_status": None,
        "required_modalities": [],
        "conditional_modalities": [],
        "available_expected_modalities": [],
        "missing_required_modalities": [],
        "missing_conditional_modalities": [],
        "release_track_intent": [],
        "profile_alignment_status": "unknown",
    }
    artifact_path = summary["metadata_artifact"]
    if artifact_path is None:
        return summary
    path = Path(artifact_path)
    if not path.exists():
        summary["metadata_artifact"] = str(path)
        return summary
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        summary["metadata_artifact"] = str(path)
        return summary
    if not isinstance(payload, dict):
        summary["metadata_artifact"] = str(path)
        return summary

    notes = note_map(payload.get("notes") or [])
    summary.update(
        {
            "metadata_artifact": str(path),
            "hardware_profile_id": normalize_text(notes.get("hardware_profile_id")),
            "hardware_profile_path": normalize_text(notes.get("hardware_profile_path")),
            "canonical_hardware_profile_id": normalize_text(notes.get("hardware_profile_canonical_id")),
            "platform_media_id": normalize_text(notes.get("hardware_profile_platform_media_id")),
            "platform_tier": normalize_text(notes.get("hardware_profile_platform_tier")),
            "bringup_status": normalize_text(notes.get("hardware_profile_bringup_status")),
            "runtime_profile": normalize_text(notes.get("hardware_profile_runtime_profile")),
            "validation_status": normalize_text(notes.get("hardware_profile_validation_status")),
            "required_modalities": split_csv(notes.get("hardware_profile_required_modalities")),
            "conditional_modalities": split_csv(notes.get("hardware_profile_conditional_modalities")),
            "available_expected_modalities": split_csv(notes.get("hardware_profile_available_expected_modalities")),
            "missing_required_modalities": split_csv(notes.get("hardware_profile_missing_required_modalities")),
            "missing_conditional_modalities": split_csv(notes.get("hardware_profile_missing_conditional_modalities")),
            "release_track_intent": split_csv(notes.get("hardware_profile_release_track_intent")),
        }
    )
    hardware_evidence_required = normalize_text(notes.get("hardware_profile_hardware_evidence_required"))
    if hardware_evidence_required is not None:
        summary["hardware_evidence_required"] = hardware_evidence_required == "true"
    summary["profile_alignment_status"] = profile_alignment_status(profile, summary)
    return summary


def derive_release_grade_summary(args: argparse.Namespace) -> dict[str, str]:
    backend_ids: set[str] = set()
    origins: set[str] = set()
    stacks: set[str] = set()
    contract_kinds: set[str] = set()

    if args.device_backend_state_artifact:
        artifact_path = Path(args.device_backend_state_artifact)
        if artifact_path.exists():
            try:
                backend_state = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                backend_state = {}
            if isinstance(backend_state, dict):
                for evidence_path in backend_evidence_paths(backend_state):
                    if not evidence_path.exists():
                        continue
                    try:
                        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if not isinstance(evidence_payload, dict):
                        continue
                    backend_id = evidence_payload.get("release_grade_backend_id") or evidence_payload.get(
                        "release_grade_backend"
                    )
                    origin = evidence_payload.get("release_grade_backend_origin")
                    stack = evidence_payload.get("release_grade_backend_stack")
                    contract_kind = evidence_payload.get("release_grade_contract_kind") or evidence_payload.get(
                        "contract_kind"
                    )
                    if isinstance(backend_id, str) and backend_id:
                        backend_ids.add(backend_id)
                    if isinstance(origin, str) and origin:
                        origins.add(origin)
                    if isinstance(stack, str) and stack:
                        stacks.add(stack)
                    if isinstance(contract_kind, str) and contract_kind:
                        contract_kinds.add(contract_kind)

    return {
        "backend_ids": args.device_release_grade_backend_ids or sorted_join(backend_ids),
        "origins": args.device_release_grade_backend_origins or sorted_join(origins),
        "stacks": args.device_release_grade_backend_stacks or sorted_join(stacks),
        "contract_kinds": args.device_release_grade_contract_kinds or sorted_join(contract_kinds),
    }


def summarize_vendor_runtime_evidence(args: argparse.Namespace) -> dict[str, Any]:
    provider_ids: set[str] = set()
    runtime_service_ids: set[str] = set()
    provider_statuses: set[str] = set()
    provider_kinds: set[str] = set()
    backend_ids: set[str] = set()
    runtime_binaries: set[str] = set()
    engine_paths: set[str] = set()
    contract_kinds: set[str] = set()
    loaded_paths: list[str] = []
    issues: list[str] = []

    for evidence_path in collect_vendor_runtime_evidence_paths(args):
        if not evidence_path.exists():
            issues.append(f"vendor runtime evidence missing: {evidence_path}")
            continue
        try:
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"vendor runtime evidence unreadable: {evidence_path} ({exc})")
            continue
        if not isinstance(payload, dict):
            issues.append(f"vendor runtime evidence payload is not an object: {evidence_path}")
            continue
        loaded_paths.append(str(evidence_path))
        for value, target in [
            (payload.get("provider_id"), provider_ids),
            (payload.get("runtime_service_id"), runtime_service_ids),
            (payload.get("provider_status"), provider_statuses),
            (payload.get("provider_kind"), provider_kinds),
            (payload.get("backend_id"), backend_ids),
            (payload.get("runtime_binary"), runtime_binaries),
            (payload.get("engine_path"), engine_paths),
            (payload.get("contract_kind"), contract_kinds),
        ]:
            if isinstance(value, str) and value:
                target.add(value)

    declared_paths = collect_vendor_runtime_evidence_paths(args)
    if not declared_paths:
        signoff_status = "not-attached"
    elif issues:
        signoff_status = "incomplete"
    else:
        signoff_status = "evidence-attached"

    return {
        "signoff_status": signoff_status,
        "evidence_count": len(loaded_paths),
        "evidence_paths": loaded_paths,
        "provider_ids": sorted(provider_ids),
        "runtime_service_ids": sorted(runtime_service_ids),
        "provider_statuses": sorted(provider_statuses),
        "provider_kinds": sorted(provider_kinds),
        "backend_ids": sorted(backend_ids),
        "runtime_binaries": sorted(runtime_binaries),
        "engine_paths": sorted(engine_paths),
        "contract_kinds": sorted(contract_kinds),
        "issues": issues,
    }


def render_report(
    profile: dict[str, Any],
    evaluator: dict[str, Any],
    args: argparse.Namespace,
    status: str,
) -> str:
    final = final_record(evaluator)
    release_grade_summary = derive_release_grade_summary(args)
    vendor_runtime = summarize_vendor_runtime_evidence(args)
    device_profile = derive_device_profile_summary(profile, args)
    platform_id = profile.get("platform_media_id") or profile.get("id") or "unknown-platform"
    boot_ids = ", ".join(evaluator.get("unique_boot_ids", [])) or "-"
    issues = open_issues(evaluator, args.note) + vendor_runtime["issues"]
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
        "## Device And Multimodal Validation",
        "",
        f"- deviced health: {args.deviced_health or '-'}",
        f"- device.state.get overall backend status: {args.device_backend_overall_status or '-'}",
        f"- device.state.get available backend count: {args.device_backend_available_count or '-'}",
        f"- device.state.get ui_tree current support: {args.device_ui_tree_support or '-'}",
        f"- device.metadata.get readiness status: {args.device_metadata_status or '-'}",
        f"- device.metadata.get backend overall status: {args.device_metadata_backend_status or '-'}",
        f"- device.metadata.get available modalities: {args.device_available_modalities or '-'}",
        f"- device.metadata artifact attached: {args.device_metadata_artifact or '-'}",
        f"- release-grade backend ids: {release_grade_summary['backend_ids'] or '-'}",
        f"- release-grade backend origins: {release_grade_summary['origins'] or '-'}",
        f"- release-grade backend stacks: {release_grade_summary['stacks'] or '-'}",
        f"- release-grade contract kinds: {release_grade_summary['contract_kinds'] or '-'}",
        f"- backend-state artifact attached: {args.device_backend_state_artifact or '-'}",
        f"- vendor runtime sign-off status: {vendor_runtime['signoff_status']}",
        f"- vendor runtime provider ids: {','.join(vendor_runtime['provider_ids']) or '-'}",
        f"- vendor runtime service ids: {','.join(vendor_runtime['runtime_service_ids']) or '-'}",
        f"- vendor runtime statuses: {','.join(vendor_runtime['provider_statuses']) or '-'}",
        f"- vendor runtime kinds: {','.join(vendor_runtime['provider_kinds']) or '-'}",
        f"- vendor runtime backend ids: {','.join(vendor_runtime['backend_ids']) or '-'}",
        f"- vendor runtime evidence count: {vendor_runtime['evidence_count']}",
        f"- vendor runtime evidence attached: {','.join(vendor_runtime['evidence_paths']) or '-'}",
        "",
        "## Device Profile Alignment",
        "",
        f"- Report profile id: {profile.get('id', '-')}",
        f"- Report platform media id: {profile.get('platform_media_id', '-')}",
        f"- Runtime hardware profile id: {device_profile['hardware_profile_id'] or '-'}",
        f"- Runtime hardware profile path: {device_profile['hardware_profile_path'] or '-'}",
        f"- Runtime canonical hardware profile id: {device_profile['canonical_hardware_profile_id'] or '-'}",
        f"- Runtime platform media id: {device_profile['platform_media_id'] or '-'}",
        f"- Runtime platform tier: {device_profile['platform_tier'] or '-'}",
        f"- Runtime bring-up status: {device_profile['bringup_status'] or '-'}",
        f"- Runtime profile alignment: {device_profile['profile_alignment_status']}",
        f"- Runtime validation status: {device_profile['validation_status'] or '-'}",
        f"- Runtime hardware evidence required: {'yes' if device_profile['hardware_evidence_required'] is True else 'no' if device_profile['hardware_evidence_required'] is False else '-'}",
        f"- Runtime required modalities: {','.join(device_profile['required_modalities']) or '-'}",
        f"- Runtime conditional modalities: {','.join(device_profile['conditional_modalities']) or '-'}",
        f"- Runtime available expected modalities: {','.join(device_profile['available_expected_modalities']) or '-'}",
        f"- Runtime missing required modalities: {','.join(device_profile['missing_required_modalities']) or '-'}",
        f"- Runtime missing conditional modalities: {','.join(device_profile['missing_conditional_modalities']) or '-'}",
        f"- Runtime release track intent: {','.join(device_profile['release_track_intent']) or '-'}",
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
        f"- Vendor runtime evidence: {', '.join(vendor_runtime['evidence_paths']) or '-'}",
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
    release_grade_summary = derive_release_grade_summary(args)
    vendor_runtime = summarize_vendor_runtime_evidence(args)
    device_profile = derive_device_profile_summary(profile, args)
    notes = open_issues(evaluator, args.note) + vendor_runtime["issues"]
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
            "device_metadata_artifact": args.device_metadata_artifact,
            "device_backend_state_artifact": args.device_backend_state_artifact,
            "vendor_runtime_evidence": vendor_runtime["evidence_paths"],
            "photos": args.photo,
        },
        "device_runtime": {
            "backend_state_artifact": args.device_backend_state_artifact or None,
            "device_profile": device_profile,
            "release_grade_backends": {
                "backend_ids": release_grade_summary["backend_ids"],
                "origins": release_grade_summary["origins"],
                "stacks": release_grade_summary["stacks"],
                "contract_kinds": release_grade_summary["contract_kinds"],
            },
            "vendor_runtime": {
                "vendor_runtime_signoff_status": vendor_runtime["signoff_status"],
                "evidence_count": vendor_runtime["evidence_count"],
                "evidence_paths": vendor_runtime["evidence_paths"],
                "provider_ids": vendor_runtime["provider_ids"],
                "runtime_service_ids": vendor_runtime["runtime_service_ids"],
                "provider_statuses": vendor_runtime["provider_statuses"],
                "provider_kinds": vendor_runtime["provider_kinds"],
                "backend_ids": vendor_runtime["backend_ids"],
                "runtime_binaries": vendor_runtime["runtime_binaries"],
                "engine_paths": vendor_runtime["engine_paths"],
                "contract_kinds": vendor_runtime["contract_kinds"],
                "issues": vendor_runtime["issues"],
            },
        },
        "checks": evaluator.get("checks", []),
        "notes": notes,
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
