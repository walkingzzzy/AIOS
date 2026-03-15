#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import default_socket, default_surface, load_surface_or_rpc, rpc_call


ACTION_LABELS = {
    "refresh-health": "Refresh Health",
    "check-updates": "Check Updates",
    "apply-update": "Apply Update",
    "rollback": "Rollback",
    "export-bundle": "Export Bundle",
}

STATUS_TONES = {
    "ready": "positive",
    "up-to-date": "positive",
    "idle": "neutral",
    "degraded": "warning",
    "rollback-staged": "warning",
    "blocked": "critical",
    "failed": "critical",
}


def action_label(action_id: str) -> str:
    return ACTION_LABELS.get(action_id, action_id.replace("-", " ").title())


def tone_for(status: str | None) -> str:
    if not status:
        return "neutral"
    return STATUS_TONES.get(status, "neutral")


def build_model(surface: dict) -> dict:
    overall_status = surface.get("overall_status", "unknown")
    deployment_status = surface.get("deployment_status", "unknown")
    current_slot = surface.get("current_slot")
    last_good_slot = surface.get("last_good_slot")
    staged_slot = surface.get("staged_slot")
    notes = surface.get("notes", [])
    available_actions = surface.get("available_actions", [])
    recovery_points = surface.get("recovery_points", [])
    diagnostic_bundles = surface.get("diagnostic_bundles", [])

    slot_items = []
    if current_slot:
        slot_items.append({"label": "Current Slot", "value": current_slot, "emphasis": "primary"})
    if last_good_slot:
        slot_items.append({"label": "Last Good Slot", "value": last_good_slot, "emphasis": "secondary"})
    if staged_slot:
        slot_items.append({"label": "Staged Slot", "value": staged_slot, "emphasis": "warning"})

    actions = []
    for action_id in available_actions:
        actions.append(
            {
                "action_id": action_id,
                "label": action_label(action_id),
                "enabled": True,
                "tone": tone_for(overall_status if action_id != "rollback" else deployment_status),
            }
        )

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
        "panel_kind": "shell-panel-skeleton",
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
        ],
        "actions": actions,
        "sections": sections,
        "meta": {
            "generated_at": surface.get("generated_at"),
            "action_count": len(actions),
            "note_count": len(notes),
            "recovery_point_count": len(recovery_points),
            "diagnostic_bundle_count": len(diagnostic_bundles),
            "panel_state": "interactive-skeleton",
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    badges = ", ".join(f"{badge['label']}: {badge['value']}" for badge in panel["badges"])
    lines.append(f"badges: {badges}")
    if panel["actions"]:
        lines.append("actions: " + ", ".join(action["label"] for action in panel["actions"]))
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if items:
            for item in items:
                lines.append(f"- {item['label']}: {item['value']}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def perform_action(socket_path: Path, action: str, target_version: str | None, reason: str | None, recovery_id: str | None) -> dict:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS recovery surface panel skeleton")
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
        result = perform_action(args.socket, args.action, args.target_version, args.reason, args.recovery_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            surface = load_surface_or_rpc(args.surface, args.socket)
            model = build_model(surface)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    surface = load_surface_or_rpc(args.surface, args.socket)
    model = build_model(surface)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
