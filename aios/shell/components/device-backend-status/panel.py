#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import default_backend_state, default_socket, load_model


IGNORE_READINESS = {
    "native-ready",
    "native-live",
    "native-state-bridge",
    "command-adapter",
    "disabled",
    "native-stub",
}
READINESS_TONES = {
    "native-ready": "positive",
    "native-live": "positive",
    "native-state-bridge": "positive",
    "command-adapter": "neutral",
    "preview-only": "warning",
    "native-stub": "warning",
    "missing-session-bus": "critical",
    "missing-pipewire-socket": "critical",
    "missing-input-root": "critical",
    "missing-camera-device": "critical",
    "missing-atspi-bus": "critical",
}


def tone_for(readiness: str | None) -> str:
    if not readiness:
        return "neutral"
    return READINESS_TONES.get(readiness, "warning")


def needs_attention(status: dict) -> bool:
    return status.get("readiness") not in IGNORE_READINESS


def normalize_model(model: dict | None, attention_only: bool) -> dict:
    base = model or {"statuses": [], "adapters": [], "notes": []}
    statuses = list(base.get("statuses", []))
    adapters = list(base.get("adapters", []))
    evidence_artifacts = list(base.get("evidence_artifacts", []))
    ui_tree_snapshot = base.get("ui_tree_snapshot")
    ui_tree_support_matrix = list(base.get("ui_tree_support_matrix", []))
    backend_summary = dict(base.get("backend_summary") or {})
    notes = list(base.get("notes", []))
    evidence_dir = base.get("evidence_dir")

    if attention_only:
        focus_modalities = {item.get("modality") for item in statuses if needs_attention(item)}
        statuses = [item for item in statuses if item.get("modality") in focus_modalities]
        adapters = [item for item in adapters if item.get("modality") in focus_modalities]
        evidence_artifacts = [
            item for item in evidence_artifacts if item.get("modality") in focus_modalities
        ]

    return {
        "updated_at": base.get("updated_at"),
        "statuses": statuses,
        "adapters": adapters,
        "evidence_artifacts": evidence_artifacts,
        "evidence_dir": evidence_dir,
        "ui_tree_snapshot": ui_tree_snapshot,
        "ui_tree_support_matrix": ui_tree_support_matrix,
        "backend_summary": backend_summary,
        "notes": notes,
    }


def derive_backend_summary(normalized: dict) -> dict:
    statuses = normalized.get("statuses", [])
    adapters = normalized.get("adapters", [])
    evidence_artifacts = normalized.get("evidence_artifacts", [])
    ui_tree_snapshot = normalized.get("ui_tree_snapshot")
    ui_tree_support_matrix = normalized.get("ui_tree_support_matrix", [])

    attention_count = sum(1 for item in statuses if needs_attention(item))
    readiness_summary: dict[str, int] = {}
    for item in statuses:
        readiness = item.get("readiness", "unknown")
        readiness_summary[readiness] = readiness_summary.get(readiness, 0) + 1

    ui_tree_capture_mode = None
    ui_tree_current_support = None
    if isinstance(ui_tree_snapshot, dict):
        ui_tree_capture_mode = ui_tree_snapshot.get("capture_mode")
    for row in ui_tree_support_matrix:
        if row.get("current"):
            ui_tree_current_support = row.get("readiness")
            break

    evidence_present_count = sum(1 for item in evidence_artifacts if item.get("artifact_present"))
    evidence_missing_count = sum(1 for item in evidence_artifacts if not item.get("artifact_present"))
    evidence_baselines = sorted(
        {
            item.get("baseline")
            for item in evidence_artifacts
            if isinstance(item.get("baseline"), str) and item.get("baseline")
        }
    )

    return {
        "overall_status": "idle" if not statuses else ("attention" if attention_count else "ready"),
        "status_count": len(statuses),
        "available_status_count": sum(1 for item in statuses if item.get("available")),
        "adapter_count": len(adapters),
        "attention_count": attention_count,
        "continuous_collector_count": 0,
        "ui_tree_support_route_count": len(ui_tree_support_matrix),
        "ui_tree_support_ready_count": sum(1 for item in ui_tree_support_matrix if item.get("available")),
        "ui_tree_snapshot_present": isinstance(ui_tree_snapshot, dict),
        "ui_tree_capture_mode": ui_tree_capture_mode,
        "ui_tree_current_support": ui_tree_current_support,
        "readiness_summary": readiness_summary,
        "evidence_artifact_count": len(evidence_artifacts),
        "evidence_present_count": evidence_present_count,
        "evidence_missing_count": evidence_missing_count,
        "evidence_baselines": evidence_baselines,
    }


def resolve_backend_summary(normalized: dict, attention_only: bool) -> tuple[dict, str]:
    derived = derive_backend_summary(normalized)
    raw_summary = normalized.get("backend_summary")
    if attention_only:
        return derived, "filtered"
    if not isinstance(raw_summary, dict) or not raw_summary:
        return derived, "derived"

    summary = dict(derived)
    summary.update({key: value for key, value in raw_summary.items() if value is not None})
    if not isinstance(summary.get("readiness_summary"), dict):
        summary["readiness_summary"] = derived["readiness_summary"]
    if not isinstance(summary.get("evidence_baselines"), list):
        summary["evidence_baselines"] = derived["evidence_baselines"]
    return summary, "backend_summary"


def summarize_release_grade_backends(evidence_artifacts: list[dict]) -> dict:
    backend_ids: set[str] = set()
    origins: set[str] = set()
    stacks: set[str] = set()
    contract_kinds: set[str] = set()
    by_modality: dict[str, dict] = {}

    for item in evidence_artifacts:
        modality = item.get("modality")
        backend_id = item.get("release_grade_backend_id")
        origin = item.get("release_grade_backend_origin")
        stack = item.get("release_grade_backend_stack")
        contract_kind = item.get("contract_kind")
        if isinstance(backend_id, str) and backend_id:
            backend_ids.add(backend_id)
        if isinstance(origin, str) and origin:
            origins.add(origin)
        if isinstance(stack, str) and stack:
            stacks.add(stack)
        if isinstance(contract_kind, str) and contract_kind:
            contract_kinds.add(contract_kind)
        if not isinstance(modality, str) or not modality:
            continue
        if not any(
            isinstance(value, str) and value
            for value in (backend_id, origin, stack, contract_kind)
        ):
            continue
        by_modality[modality] = {
            "backend_id": backend_id,
            "origin": origin,
            "stack": stack,
            "contract_kind": contract_kind,
            "baseline": item.get("baseline"),
        }

    ordered_modalities = {key: by_modality[key] for key in sorted(by_modality)}
    return {
        "backend_ids": sorted(backend_ids),
        "origins": sorted(origins),
        "stacks": sorted(stacks),
        "contract_kinds": sorted(contract_kinds),
        "by_modality": ordered_modalities,
    }


def build_model(model: dict | None, attention_only: bool) -> dict:
    normalized = normalize_model(model, attention_only)
    statuses = normalized.get("statuses", [])
    adapters = normalized.get("adapters", [])
    evidence_artifacts = normalized.get("evidence_artifacts", [])
    ui_tree_snapshot = normalized.get("ui_tree_snapshot")
    ui_tree_support_matrix = normalized.get("ui_tree_support_matrix", [])
    notes = normalized.get("notes", [])
    backend_summary, summary_source = resolve_backend_summary(normalized, attention_only)
    release_grade_summary = summarize_release_grade_backends(evidence_artifacts)
    attention_count = int(backend_summary.get("attention_count") or 0)

    ui_tree_capture_mode = backend_summary.get("ui_tree_capture_mode")
    ui_tree_focus = None
    ui_tree_application_count = 0
    ui_tree_badge_tone = "neutral"
    ui_tree_items: list[dict] = []
    if isinstance(ui_tree_snapshot, dict):
        ui_tree_focus = ui_tree_snapshot.get("focus_name") or ui_tree_snapshot.get("focus_node")
        ui_tree_application_count = int(ui_tree_snapshot.get("application_count") or 0)
        if ui_tree_capture_mode in {"native-live", "native-ready", "native-state-bridge"}:
            ui_tree_badge_tone = "positive"
        elif ui_tree_capture_mode:
            ui_tree_badge_tone = "warning"
        ui_tree_items = [
            {
                "label": "snapshot_id",
                "value": ui_tree_snapshot.get("snapshot_id", "-"),
                "tone": "neutral",
            },
            {
                "label": "capture_mode",
                "value": ui_tree_capture_mode or "unknown",
                "tone": ui_tree_badge_tone,
            },
            {
                "label": "applications",
                "value": ui_tree_application_count,
                "tone": "neutral",
            },
            {
                "label": "focus",
                "value": ui_tree_focus or "-",
                "tone": "neutral",
            },
        ]
        if ui_tree_snapshot.get("adapter_id"):
            ui_tree_items.append(
                {
                    "label": "adapter_id",
                    "value": ui_tree_snapshot["adapter_id"],
                    "tone": "neutral",
                }
            )
        if ui_tree_snapshot.get("collector"):
            ui_tree_items.append(
                {
                    "label": "collector",
                    "value": ui_tree_snapshot["collector"],
                    "tone": "neutral",
                }
            )

    status_count = int(backend_summary.get("status_count") or 0)
    adapter_count = int(backend_summary.get("adapter_count") or 0)
    available_status_count = int(backend_summary.get("available_status_count") or 0)
    ui_tree_support_ready_count = int(backend_summary.get("ui_tree_support_ready_count") or 0)
    evidence_artifact_count = int(backend_summary.get("evidence_artifact_count") or 0)
    evidence_present_count = int(backend_summary.get("evidence_present_count") or 0)
    evidence_missing_count = int(backend_summary.get("evidence_missing_count") or 0)
    evidence_baselines = list(backend_summary.get("evidence_baselines") or [])
    status = backend_summary.get("overall_status") or "idle"

    actions = [
        {"action_id": "refresh", "label": "Refresh Backends", "enabled": True, "tone": "neutral"},
        {
            "action_id": "focus-attention",
            "label": "Focus Attention",
            "enabled": attention_count > 0,
            "tone": "warning",
        },
    ]

    return {
        "component_id": "device-backend-status",
        "panel_id": "device-backend-status-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Device Backend Status",
            "subtitle": f"{status_count} backend statuses · {adapter_count} adapters",
            "status": status,
            "tone": "warning" if attention_count else ("positive" if status_count else "neutral"),
        },
        "badges": [
            {"label": "Statuses", "value": status_count, "tone": "neutral"},
            {"label": "Available", "value": available_status_count, "tone": "positive" if available_status_count else "neutral"},
            {"label": "Adapters", "value": adapter_count, "tone": "neutral"},
            {
                "label": "Attention",
                "value": attention_count,
                "tone": "warning" if attention_count else "neutral",
            },
            {
                "label": "UI Tree",
                "value": ui_tree_capture_mode or "unavailable",
                "tone": ui_tree_badge_tone if ui_tree_capture_mode else "neutral",
            },
            {
                "label": "UI Tree Routes",
                "value": ui_tree_support_ready_count,
                "tone": "positive" if ui_tree_support_ready_count else "neutral",
            },
            {
                "label": "Evidence",
                "value": evidence_present_count,
                "tone": "positive" if evidence_present_count else "neutral",
            },
            {
                "label": "Release-Grade",
                "value": len(release_grade_summary["backend_ids"]),
                "tone": "positive" if release_grade_summary["backend_ids"] else "neutral",
            },
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "statuses",
                "title": "Backend Readiness",
                "items": [
                    {
                        "label": item.get("modality", "unknown"),
                        "value": item.get("backend", "unknown"),
                        "readiness": item.get("readiness"),
                        "available": item.get("available"),
                        "details": item.get("details", []),
                        "tone": tone_for(item.get("readiness")),
                    }
                    for item in statuses
                ],
                "empty_state": "No backend statuses",
            },
            {
                "section_id": "adapters",
                "title": "Capture Adapters",
                "items": [
                    {
                        "label": item.get("modality", "unknown"),
                        "value": item.get("adapter_id", "unknown"),
                        "execution_path": item.get("execution_path"),
                        "backend": item.get("backend"),
                        "tone": "neutral",
                    }
                    for item in adapters
                ],
                "empty_state": "No capture adapters",
            },
            {
                "section_id": "backend-evidence",
                "title": "Backend Evidence",
                "items": [
                    {
                        "label": item.get("modality", "unknown"),
                        "value": item.get("release_grade_backend_id")
                        or item.get("baseline")
                        or "unknown",
                        "baseline": item.get("baseline"),
                        "artifact_path": item.get("artifact_path"),
                        "artifact_present": item.get("artifact_present"),
                        "execution_path": item.get("execution_path"),
                        "source": item.get("source"),
                        "readiness": item.get("readiness"),
                        "backend_origin": item.get("release_grade_backend_origin"),
                        "backend_stack": item.get("release_grade_backend_stack"),
                        "contract_kind": item.get("contract_kind"),
                        "state_refs": item.get("state_refs", []),
                        "tone": (
                            "positive"
                            if item.get("artifact_present")
                            and (item.get("release_grade_backend_id") or item.get("baseline"))
                            else "warning"
                        ),
                    }
                    for item in evidence_artifacts
                ],
                "empty_state": "No backend evidence artifacts",
            },
            {
                "section_id": "release-grade-summary",
                "title": "Release-Grade Summary",
                "items": [
                    {
                        "label": "Backend IDs",
                        "value": ", ".join(release_grade_summary["backend_ids"]) or "-",
                        "tone": "positive" if release_grade_summary["backend_ids"] else "neutral",
                    },
                    {
                        "label": "Origins",
                        "value": ", ".join(release_grade_summary["origins"]) or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Stacks",
                        "value": ", ".join(release_grade_summary["stacks"]) or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Contracts",
                        "value": ", ".join(release_grade_summary["contract_kinds"]) or "-",
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No release-grade backend metadata",
            },
            {
                "section_id": "ui-tree",
                "title": "UI Tree Snapshot",
                "items": ui_tree_items,
                "empty_state": "No ui_tree snapshot",
            },
            {
                "section_id": "ui-tree-support",
                "title": "UI Tree Support Matrix",
                "items": [
                    {
                        "label": item.get("environment_id", "unknown"),
                        "value": item.get("readiness", "unknown"),
                        "available": item.get("available"),
                        "current": item.get("current"),
                        "details": item.get("details", []),
                        "tone": "positive" if item.get("available") else "warning",
                    }
                    for item in ui_tree_support_matrix
                ],
                "empty_state": "No ui_tree support routes",
            },
            {
                "section_id": "notes",
                "title": "Operational Notes",
                "items": [
                    {"label": f"note-{index + 1}", "value": note, "tone": "neutral"}
                    for index, note in enumerate(notes)
                ],
                "empty_state": "No operational notes",
            },
        ],
        "meta": {
            "updated_at": normalized.get("updated_at"),
            "summary_source": summary_source,
            "attention_count": attention_count,
            "status_count": status_count,
            "available_status_count": available_status_count,
            "adapter_count": adapter_count,
            "evidence_artifact_count": evidence_artifact_count,
            "evidence_present_count": evidence_present_count,
            "evidence_missing_count": evidence_missing_count,
            "evidence_dir": normalized.get("evidence_dir"),
            "evidence_baselines": evidence_baselines,
            "release_grade_backend_ids": release_grade_summary["backend_ids"],
            "release_grade_backend_origins": release_grade_summary["origins"],
            "release_grade_backend_stacks": release_grade_summary["stacks"],
            "release_grade_contract_kinds": release_grade_summary["contract_kinds"],
            "release_grade_backends": release_grade_summary["by_modality"],
            "readiness_summary": backend_summary.get("readiness_summary", {}),
            "attention_only": attention_only,
            "ui_tree_available": bool(backend_summary.get("ui_tree_snapshot_present")),
            "ui_tree_capture_mode": ui_tree_capture_mode,
            "ui_tree_focus": ui_tree_focus,
            "ui_tree_application_count": ui_tree_application_count,
            "ui_tree_support_route_count": int(backend_summary.get("ui_tree_support_route_count") or 0),
            "ui_tree_support_ready_count": ui_tree_support_ready_count,
            "ui_tree_current_support": backend_summary.get("ui_tree_current_support"),
            "continuous_collector_count": int(backend_summary.get("continuous_collector_count") or 0),
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    lines.append("badges: " + ", ".join(f"{item['label']}: {item['value']}" for item in panel["badges"]))
    if panel["actions"]:
        lines.append("actions: " + ", ".join(action["label"] for action in panel["actions"] if action.get("enabled", True)))
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if items:
            for item in items:
                if section["section_id"] == "statuses":
                    detail_suffix = ""
                    if item.get("details"):
                        detail_suffix = f" details={','.join(item['details'])}"
                    lines.append(
                        f"- {item['label']}: {item['value']} [{item.get('readiness')}] available={item.get('available')}{detail_suffix}"
                    )
                elif section["section_id"] == "adapters":
                    lines.append(
                        f"- {item['label']}: {item['value']} path={item.get('execution_path') or '-'} backend={item.get('backend') or '-'}"
                    )
                elif section["section_id"] == "backend-evidence":
                    state_refs = ",".join(item.get("state_refs", []))
                    lines.append(
                        f"- {item['label']}: {item['value']} "
                        f"baseline={item.get('baseline') or '-'} "
                        f"origin={item.get('backend_origin') or '-'} "
                        f"stack={item.get('backend_stack') or '-'} "
                        f"contract={item.get('contract_kind') or '-'} "
                        f"path={item.get('artifact_path') or '-'} "
                        f"present={item.get('artifact_present')} "
                        f"source={item.get('source') or '-'} "
                        f"state_refs={state_refs or '-'}"
                    )
                elif section["section_id"] == "ui-tree":
                    lines.append(f"- {item['label']}: {item['value']}")
                elif section["section_id"] == "ui-tree-support":
                    detail_suffix = ""
                    if item.get("details"):
                        detail_suffix = f" details={','.join(item['details'])}"
                    lines.append(
                        f"- {item['label']}: {item['value']} available={item.get('available')} current={item.get('current')}{detail_suffix}"
                    )
                else:
                    lines.append(f"- {item['label']}: {item['value']}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS device backend status panel")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--path", type=Path, default=default_backend_state())
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--attention-only", action="store_true")
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        attention_only = args.attention_only or args.action == "focus-attention"
        model = build_model(load_model(args.path, args.fixture, args.socket), attention_only)
        selected = next((item for item in model["actions"] if item["action_id"] == args.action), None)
        if selected is None:
            raise SystemExit(f"unknown action: {args.action}")
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "status": model["header"]["status"],
            "attention_count": model["meta"]["attention_count"],
            "attention_only": attention_only,
            "status_count": model["meta"]["status_count"],
            "adapter_count": model["meta"]["adapter_count"],
            "readiness_summary": model["meta"]["readiness_summary"],
            "release_grade_backend_ids": model["meta"]["release_grade_backend_ids"],
            "release_grade_contract_kinds": model["meta"]["release_grade_contract_kinds"],
            "ui_tree_capture_mode": model["meta"]["ui_tree_capture_mode"],
            "ui_tree_current_support": model["meta"]["ui_tree_current_support"],
            "route_reason": "attention-focus" if args.action == "focus-attention" else "refresh",
            "target_component": "device-backend-status",
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            model = build_model(load_model(args.path, args.fixture, args.socket), args.attention_only)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    model = build_model(load_model(args.path, args.fixture, args.socket), args.attention_only)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


