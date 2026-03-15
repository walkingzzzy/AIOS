#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import default_indicator_path, load_state


APPROVAL_TONES = {
    "approved": "positive",
    "not-required": "neutral",
    "required": "warning",
    "pending": "warning",
    "denied": "critical",
    "disabled": "neutral",
}


def tone_for(status: str | None) -> str:
    if not status:
        return "neutral"
    return APPROVAL_TONES.get(status, "neutral")


def needs_attention(item: dict) -> bool:
    return (item.get("approval_status") or "").lower() in {"required", "pending", "denied"}


def build_model(state: dict | None) -> dict:
    active = [] if state is None else list(state.get("active", []))
    notes = [] if state is None else list(state.get("notes", []))
    modality_count = len({item.get("modality") for item in active if item.get("modality")})
    attention_count = sum(1 for item in active if needs_attention(item))
    status = "idle"
    if active:
        status = "attention" if attention_count else "active"

    return {
        "component_id": "capture-indicators",
        "panel_id": "capture-indicators-panel",
        "panel_kind": "shell-panel-skeleton",
        "header": {
            "title": "Capture Indicators",
            "subtitle": f"{len(active)} active captures · {modality_count} modalities",
            "status": status,
            "tone": "warning" if attention_count else ("positive" if active else "neutral"),
        },
        "badges": [
            {"label": "Active", "value": len(active), "tone": "neutral"},
            {"label": "Modalities", "value": modality_count, "tone": "neutral"},
            {
                "label": "Attention",
                "value": attention_count,
                "tone": "warning" if attention_count else "neutral",
            },
        ],
        "actions": [
            {"action_id": "refresh", "label": "Refresh Indicators", "enabled": True, "tone": "neutral"},
            {
                "action_id": "review-approvals",
                "label": "Review Approvals",
                "enabled": attention_count > 0,
                "tone": "warning",
            },
        ],
        "sections": [
            {
                "section_id": "active",
                "title": "Active Indicators",
                "items": [
                    {
                        "indicator_id": item.get("indicator_id"),
                        "label": item.get("message", item.get("modality", "capture")),
                        "modality": item.get("modality"),
                        "approval_status": item.get("approval_status"),
                        "continuous": item.get("continuous", False),
                        "started_at": item.get("started_at"),
                        "tone": tone_for(item.get("approval_status")),
                    }
                    for item in active
                ],
                "empty_state": "No active capture indicators",
            },
            {
                "section_id": "notes",
                "title": "State Notes",
                "items": [
                    {"label": f"note-{index + 1}", "value": note, "tone": "neutral"}
                    for index, note in enumerate(notes)
                ],
                "empty_state": "No state notes",
            },
        ],
        "meta": {
            "updated_at": None if state is None else state.get("updated_at"),
            "active_count": len(active),
            "attention_count": attention_count,
            "modality_count": modality_count,
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
                if section["section_id"] == "active":
                    lines.append(
                        f"- {item['modality']}: {item['label']} approval={item.get('approval_status') or 'n/a'} continuous={str(item['continuous']).lower()}"
                    )
                else:
                    lines.append(f"- {item['label']}: {item['value']}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS capture indicators panel skeleton")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--path", type=Path, default=default_indicator_path())
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        state = load_state(args.path)
        model = build_model(state)
        selected = next((item for item in model["actions"] if item["action_id"] == args.action), None)
        if selected is None:
            raise SystemExit(f"unknown action: {args.action}")
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "active_count": model["meta"]["active_count"],
            "attention_count": model["meta"]["attention_count"],
            "target_component": (
                "approval-panel"
                if args.action == "review-approvals" and selected.get("enabled", False)
                else None
            ),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            model = build_model(load_state(args.path))
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    model = build_model(load_state(args.path))
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
