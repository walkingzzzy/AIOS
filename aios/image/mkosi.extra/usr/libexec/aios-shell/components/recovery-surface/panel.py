#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from prototype import default_socket, default_surface, load_surface, load_surface_or_rpc, rpc_call


ACTION_LABELS = {
    "refresh-health": "Refresh Health",
    "check-updates": "Check Updates",
    "apply-update": "Apply Update",
    "rollback": "Rollback",
    "export-bundle": "Export Bundle",
}

ACTION_ROUTE_REASONS = {
    "refresh-health": "health-refreshed",
    "check-updates": "update-check-requested",
    "apply-update": "update-apply-requested",
    "rollback": "rollback-issued",
    "export-bundle": "bundle-exported",
}

STATUS_TONES = {
    "ready": "positive",
    "up-to-date": "positive",
    "idle": "neutral",
    "degraded": "warning",
    "rollback-staged": "warning",
    "rollback-triggered": "warning",
    "apply-triggered": "warning",
    "staged-update": "warning",
    "ready-to-stage": "warning",
    "accepted": "positive",
    "exported": "positive",
    "observed": "neutral",
    "blocked": "critical",
    "failed": "critical",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def action_label(action_id: str) -> str:
    return ACTION_LABELS.get(action_id, action_id.replace("-", " ").title())


def tone_for(status: str | None) -> str:
    if not status:
        return "neutral"
    return STATUS_TONES.get(status, "neutral")


def normalize_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item) for item in values if str(item).strip()]


def fallback_surface(data_source_error: str | None) -> dict:
    notes = []
    if data_source_error:
        notes.append(f"data_source_error={data_source_error}")
    return {
        "generated_at": utc_now(),
        "service_id": "aios-updated",
        "overall_status": "degraded",
        "deployment_status": "source-unavailable",
        "rollback_ready": False,
        "current_slot": None,
        "last_good_slot": None,
        "staged_slot": None,
        "target_version": None,
        "notes": notes,
        "available_actions": [],
        "recovery_points": [],
        "diagnostic_bundles": [],
    }


def load_surface_with_fallback(path: Path, socket_path: Path) -> tuple[dict, str | None]:
    try:
        return load_surface_or_rpc(path, socket_path), None
    except Exception as error:
        return fallback_surface(str(error)), str(error)


def latest_recovery_id(recovery_points: list[str]) -> str | None:
    for value in reversed(recovery_points):
        name = value.rsplit("/", 1)[-1].strip()
        if name.endswith(".json"):
            name = name[:-5]
        if name:
            return name
    return None


def default_target_version(surface: dict) -> str | None:
    for key in ("target_version", "next_version", "candidate_version", "available_version"):
        value = surface.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def inferred_staged_slot(surface: dict) -> str | None:
    current_slot = str(surface.get("current_slot") or "").strip().lower()
    if current_slot == "a":
        return "b"
    if current_slot == "b":
        return "a"
    last_good_slot = str(surface.get("last_good_slot") or "").strip()
    if last_good_slot:
        return last_good_slot
    staged_slot = str(surface.get("staged_slot") or "").strip()
    return staged_slot or None


def panel_state(surface: dict, data_source_error: str | None) -> str:
    if data_source_error:
        return "fallback-empty"
    deployment_status = str(surface.get("deployment_status") or "").strip().lower()
    overall_status = str(surface.get("overall_status") or "").strip().lower()
    if deployment_status in {
        "apply-triggered",
        "staged-update",
        "rollback-triggered",
        "rollback-staged",
        "ready-to-stage",
    }:
        return "operation-pending"
    if overall_status in {"failed", "blocked"}:
        return "degraded-attention"
    return "interactive-ready"


def write_surface(path: Path, surface: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(surface, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_action_list(surface: dict, *action_ids: str) -> None:
    actions = normalize_string_list(surface.get("available_actions"))
    for action_id in action_ids:
        if action_id not in actions:
            actions.append(action_id)
    surface["available_actions"] = actions


def append_note(surface: dict, note: str) -> None:
    notes = normalize_string_list(surface.get("notes"))
    notes.append(note)
    surface["notes"] = notes


def action_tone(action_id: str, surface: dict, enabled: bool) -> str:
    if not enabled:
        return "neutral"
    if action_id in {"apply-update", "rollback"}:
        return tone_for(surface.get("deployment_status"))
    return tone_for(surface.get("overall_status"))


def build_actions(surface: dict, data_source_error: str | None) -> list[dict]:
    if data_source_error:
        return []

    recovery_points = normalize_string_list(surface.get("recovery_points"))
    diagnostic_bundles = normalize_string_list(surface.get("diagnostic_bundles"))
    rollback_default_recovery_id = latest_recovery_id(recovery_points)
    target_version = default_target_version(surface)

    actions = []
    for action_id in normalize_string_list(surface.get("available_actions")):
        enabled = True
        action = {
            "action_id": action_id,
            "label": action_label(action_id),
            "enabled": True,
            "tone": "neutral",
        }
        if action_id == "apply-update":
            enabled = target_version is not None
            if target_version is not None:
                action["target_version"] = target_version
            action["reason"] = "recovery-panel-apply"
        elif action_id == "rollback":
            enabled = bool(surface.get("rollback_ready")) or rollback_default_recovery_id is not None
            if rollback_default_recovery_id is not None:
                action["recovery_id"] = rollback_default_recovery_id
            action["reason"] = "recovery-panel-rollback"
        elif action_id == "export-bundle":
            action["reason"] = "recovery-panel-export"
            if diagnostic_bundles:
                action["bundle_count"] = len(diagnostic_bundles)
        elif action_id == "check-updates":
            action["reason"] = "recovery-panel-check"
        elif action_id == "refresh-health":
            action["reason"] = "recovery-panel-refresh"

        action["enabled"] = enabled
        action["tone"] = action_tone(action_id, surface, enabled)
        actions.append(action)
    return actions


def build_model(surface: dict, data_source_error: str | None = None) -> dict:
    overall_status = surface.get("overall_status", "unknown")
    deployment_status = surface.get("deployment_status", "unknown")
    current_slot = surface.get("current_slot")
    last_good_slot = surface.get("last_good_slot")
    staged_slot = surface.get("staged_slot")
    notes = normalize_string_list(surface.get("notes"))
    recovery_points = normalize_string_list(surface.get("recovery_points"))
    diagnostic_bundles = normalize_string_list(surface.get("diagnostic_bundles"))
    actions = build_actions(surface, data_source_error)

    slot_items = []
    if current_slot:
        slot_items.append({"label": "Current Slot", "value": current_slot, "emphasis": "primary"})
    if last_good_slot:
        slot_items.append({"label": "Last Good Slot", "value": last_good_slot, "emphasis": "secondary"})
    if staged_slot:
        slot_items.append({"label": "Staged Slot", "value": staged_slot, "emphasis": "warning"})

    sections = [
        {
            "section_id": "slots",
            "title": "Boot Slots",
            "items": slot_items,
            "empty_state": "No boot slot information",
        },
        {
            "section_id": "recovery-points",
            "title": "Recovery Points",
            "items": [
                {"label": item.replace(".json", ""), "value": item, "emphasis": "secondary"}
                for item in recovery_points
            ],
            "empty_state": "No recovery points exported",
        },
        {
            "section_id": "diagnostics",
            "title": "Diagnostic Bundles",
            "items": [
                {"label": item.replace(".json", ""), "value": item, "emphasis": "secondary"}
                for item in diagnostic_bundles
            ],
            "empty_state": "No diagnostic bundles exported",
        },
        {
            "section_id": "notes",
            "title": "Operational Notes",
            "items": [
                {"label": f"note-{index + 1}", "value": note, "emphasis": "secondary"}
                for index, note in enumerate(notes)
            ],
            "empty_state": "No operational notes",
        },
    ]

    return {
        "component_id": "recovery-surface",
        "panel_id": "recovery-panel",
        "panel_kind": "shell-panel",
        "service_id": surface.get("service_id"),
        "header": {
            "title": "Recovery Panel",
            "subtitle": f"{surface.get('service_id', 'unknown')} · deployment {deployment_status}",
            "status": overall_status,
            "tone": tone_for(overall_status),
        },
        "badges": [
            {
                "label": "Overall",
                "value": overall_status,
                "tone": tone_for(overall_status),
            },
            {
                "label": "Deployment",
                "value": deployment_status,
                "tone": tone_for(deployment_status),
            },
            {
                "label": "Rollback Ready",
                "value": str(surface.get("rollback_ready", False)).lower(),
                "tone": "positive" if surface.get("rollback_ready", False) else "neutral",
            },
            {
                "label": "Recovery Points",
                "value": len(recovery_points),
                "tone": "neutral",
            },
            {
                "label": "Bundles",
                "value": len(diagnostic_bundles),
                "tone": "neutral",
            },
        ],
        "actions": actions,
        "sections": sections,
        "meta": {
            "generated_at": surface.get("generated_at"),
            "action_count": len(actions),
            "available_action_ids": [item.get("action_id") for item in actions],
            "note_count": len(notes),
            "recovery_point_count": len(recovery_points),
            "diagnostic_bundle_count": len(diagnostic_bundles),
            "latest_recovery_id": latest_recovery_id(recovery_points),
            "default_target_version": default_target_version(surface),
            "panel_state": panel_state(surface, data_source_error),
            "data_source_status": "ready" if data_source_error is None else "fallback-empty",
            "data_source_error": data_source_error,
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    badges = ", ".join(f"{badge['label']}: {badge['value']}" for badge in panel["badges"])
    lines.append(f"badges: {badges}")
    meta = panel.get("meta") or {}
    if meta.get("data_source_status") != "ready":
        lines.append(f"source: {meta.get('data_source_status')}")
        if meta.get("data_source_error"):
            lines.append(f"source_error: {meta['data_source_error']}")
    if panel["actions"]:
        lines.append(
            "actions: " + ", ".join(action["label"] for action in panel["actions"] if action.get("enabled", True))
        )
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if items:
            for item in items:
                lines.append(f"- {item['label']}: {item['value']}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def perform_rpc_action(
    socket_path: Path,
    action: str,
    target_version: str | None,
    reason: str | None,
    recovery_id: str | None,
) -> dict:
    if action == "refresh-health":
        return rpc_call(socket_path, "update.health.get", {})
    if action == "check-updates":
        return rpc_call(socket_path, "update.check", {})
    if action == "apply-update":
        return rpc_call(
            socket_path,
            "update.apply",
            {"target_version": target_version, "reason": reason, "dry_run": False},
        )
    if action == "rollback":
        return rpc_call(
            socket_path,
            "update.rollback",
            {"recovery_id": recovery_id, "reason": reason, "dry_run": False},
        )
    if action == "export-bundle":
        return rpc_call(socket_path, "recovery.bundle.export", {"reason": reason})
    raise SystemExit(f"unsupported panel action: {action}")


def next_bundle_name(existing_bundles: list[str]) -> str:
    known = set(existing_bundles)
    index = len(existing_bundles) + 1
    while True:
        candidate = f"bundle-{index}.json"
        if candidate not in known:
            return candidate
        index += 1


def simulate_surface_action(
    surface_path: Path,
    surface: dict,
    action: str,
    target_version: str | None,
    reason: str | None,
    recovery_id: str | None,
) -> tuple[dict, dict]:
    updated = json.loads(json.dumps(surface, ensure_ascii=False))
    updated.setdefault("service_id", "aios-updated")
    updated["generated_at"] = utc_now()
    updated.setdefault("overall_status", "idle")
    updated.setdefault("deployment_status", "idle")
    updated.setdefault("rollback_ready", False)
    updated.setdefault("available_actions", [])
    updated.setdefault("recovery_points", [])
    updated.setdefault("diagnostic_bundles", [])
    updated.setdefault("notes", [])

    result: dict[str, object] = {}

    if action == "refresh-health":
        result = {"status": "observed"}
    elif action == "check-updates":
        append_note(updated, f"update_check_requested_at={utc_now()}")
        result = {
            "status": "checked",
            "deployment_status": updated.get("deployment_status"),
            "artifacts": [],
        }
    elif action == "apply-update":
        applied_target_version = target_version or default_target_version(updated) or "surface-staged-version"
        inferred_recovery_id = recovery_id or latest_recovery_id(normalize_string_list(updated.get("recovery_points"))) or f"recovery-{len(normalize_string_list(updated.get('recovery_points'))) + 1:03d}"
        recovery_point_name = inferred_recovery_id if inferred_recovery_id.endswith(".json") else f"{inferred_recovery_id}.json"
        recovery_points = normalize_string_list(updated.get("recovery_points"))
        if recovery_point_name not in recovery_points:
            recovery_points.append(recovery_point_name)
        updated["recovery_points"] = recovery_points
        updated["target_version"] = applied_target_version
        updated["overall_status"] = "degraded"
        updated["deployment_status"] = "apply-triggered"
        updated["rollback_ready"] = True
        updated["staged_slot"] = inferred_staged_slot(updated)
        ensure_action_list(updated, "refresh-health", "rollback", "export-bundle")
        append_note(updated, f"apply_requested={applied_target_version}")
        append_note(updated, f"recovery_ref={inferred_recovery_id}")
        result = {
            "status": "accepted",
            "deployment_status": updated.get("deployment_status"),
            "recovery_ref": inferred_recovery_id,
            "target_version": applied_target_version,
        }
    elif action == "rollback":
        inferred_recovery_id = recovery_id or latest_recovery_id(normalize_string_list(updated.get("recovery_points"))) or "recovery-latest"
        rollback_target = str(updated.get("last_good_slot") or inferred_staged_slot(updated) or updated.get("current_slot") or "a")
        updated["overall_status"] = "degraded"
        updated["deployment_status"] = "rollback-triggered"
        updated["rollback_ready"] = True
        updated["staged_slot"] = rollback_target
        ensure_action_list(updated, "refresh-health", "rollback", "export-bundle")
        append_note(updated, f"rollback_requested={inferred_recovery_id}")
        result = {
            "status": "accepted",
            "deployment_status": updated.get("deployment_status"),
            "recovery_ref": inferred_recovery_id,
            "rollback_target": rollback_target,
        }
    elif action == "export-bundle":
        bundles = normalize_string_list(updated.get("diagnostic_bundles"))
        bundle_name = next_bundle_name(bundles)
        bundle_path = surface_path.parent / bundle_name
        bundle_payload = {
            "generated_at": utc_now(),
            "service_id": updated.get("service_id", "aios-updated"),
            "overall_status": updated.get("overall_status"),
            "deployment_status": updated.get("deployment_status"),
            "rollback_ready": updated.get("rollback_ready", False),
            "reason": reason,
            "source": "recovery-surface",
        }
        bundle_path.write_text(json.dumps(bundle_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        bundles.append(bundle_name)
        updated["diagnostic_bundles"] = bundles
        ensure_action_list(updated, "refresh-health", "export-bundle")
        append_note(updated, f"bundle_exported={bundle_name}")
        result = {
            "status": "exported",
            "bundle_path": str(bundle_path),
            "bundle_name": bundle_name,
        }
    else:
        raise SystemExit(f"unsupported panel action: {action}")

    if action != "refresh-health":
        write_surface(surface_path, updated)

    return updated, result


def standardize_action_result(
    action: str,
    surface: dict,
    payload: dict,
    *,
    data_source_mode: str,
    reason: str | None,
    data_source_error: str | None,
) -> dict:
    recovery_points = normalize_string_list(surface.get("recovery_points"))
    diagnostic_bundles = normalize_string_list(surface.get("diagnostic_bundles"))
    result = {
        "action": action,
        "status": payload.get("status") or surface.get("overall_status") or "unknown",
        "target_component": "recovery-surface",
        "route_reason": ACTION_ROUTE_REASONS.get(action, action),
        "overall_status": surface.get("overall_status"),
        "deployment_status": surface.get("deployment_status"),
        "rollback_ready": bool(surface.get("rollback_ready", False)),
        "current_slot": surface.get("current_slot"),
        "last_good_slot": surface.get("last_good_slot"),
        "staged_slot": surface.get("staged_slot"),
        "recovery_point_count": len(recovery_points),
        "diagnostic_bundle_count": len(diagnostic_bundles),
        "latest_recovery_id": latest_recovery_id(recovery_points),
        "panel_state": panel_state(surface, None),
        "data_source_mode": data_source_mode,
        "data_source_error": data_source_error,
        "reason": reason,
    }
    for key in (
        "deployment_status",
        "recovery_ref",
        "rollback_target",
        "bundle_path",
        "bundle_name",
        "target_version",
        "artifacts",
        "notes",
        "summary",
    ):
        if payload.get(key) not in (None, "", []):
            result[key] = payload[key]
    return result


def perform_action(
    socket_path: Path,
    surface_path: Path,
    action: str,
    target_version: str | None,
    reason: str | None,
    recovery_id: str | None,
) -> dict:
    try:
        payload = perform_rpc_action(socket_path, action, target_version, reason, recovery_id)
        surface, refresh_error = load_surface_with_fallback(surface_path, socket_path)
        return standardize_action_result(
            action,
            surface,
            payload,
            data_source_mode="rpc",
            reason=reason,
            data_source_error=refresh_error,
        )
    except Exception as error:
        surface = load_surface(surface_path)
        if surface is None:
            raise
        updated_surface, payload = simulate_surface_action(
            surface_path,
            surface,
            action,
            target_version,
            reason,
            recovery_id,
        )
        return standardize_action_result(
            action,
            updated_surface,
            payload,
            data_source_mode="surface-file-fallback",
            reason=reason,
            data_source_error=str(error),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS recovery surface panel")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--surface", type=Path, default=default_surface())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--action")
    parser.add_argument("--target-version")
    parser.add_argument("--reason")
    parser.add_argument("--recovery-id")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action command")
        result = perform_action(args.socket, args.surface, args.action, args.target_version, args.reason, args.recovery_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            surface, data_source_error = load_surface_with_fallback(args.surface, args.socket)
            model = build_model(surface, data_source_error)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    surface, data_source_error = load_surface_with_fallback(args.surface, args.socket)
    model = build_model(surface, data_source_error)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
