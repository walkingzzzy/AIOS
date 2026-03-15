#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import (
    build_notifications,
    default_panel_action_log,
    default_backend_state,
    default_deviced_socket,
    default_indicator_state,
    default_policy_socket,
    default_recovery_surface,
    default_updated_socket,
    list_approvals,
    load_backend_state,
    load_json,
    load_panel_action_events,
    load_recovery_surface,
)


SEVERITY_TONES = {
    "high": "critical",
    "medium": "warning",
    "info": "neutral",
}

SEVERITY_RANK = {
    "idle": 0,
    "info": 1,
    "medium": 2,
    "high": 3,
}


def tone_for(severity: str | None) -> str:
    if not severity:
        return "neutral"
    return SEVERITY_TONES.get(severity, "neutral")


def summarize(notifications: list[dict]) -> dict:
    by_severity: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for item in notifications:
        severity = item.get("severity", "info")
        source = item.get("source", "unknown")
        kind = item.get("kind", "unknown")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "total": len(notifications),
        "by_severity": by_severity,
        "by_source": by_source,
        "by_kind": by_kind,
    }


def overall_severity(notifications: list[dict]) -> str:
    status = "idle"
    for item in notifications:
        candidate = item.get("severity", "info")
        if SEVERITY_RANK.get(candidate, 0) > SEVERITY_RANK.get(status, 0):
            status = candidate
    return status


def load_notifications(args: argparse.Namespace) -> list[dict]:
    recovery_surface = load_recovery_surface(args.recovery_surface, args.updated_socket)
    indicator_state = load_json(args.indicator_state)
    backend_state = load_backend_state(args.backend_state, args.deviced_socket)
    panel_action_events = load_panel_action_events(args.panel_action_log)
    approvals = list_approvals(args.policy_socket, args.approval_fixture)
    return build_notifications(
        recovery_surface,
        indicator_state,
        approvals,
        backend_state,
        panel_action_events,
    )


def build_model(notifications: list[dict]) -> dict:
    summary = summarize(notifications)
    status = overall_severity(notifications)
    actions = [
        {
            "action_id": "refresh",
            "label": "Refresh Feed",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "review-approvals",
            "label": "Review Approvals",
            "enabled": any(item.get("kind") == "approval-pending" for item in notifications),
            "tone": "critical",
        },
        {
            "action_id": "open-recovery",
            "label": "Open Recovery",
            "enabled": any(item.get("source") == "updated" for item in notifications),
            "tone": "warning",
        },
        {
            "action_id": "inspect-device-health",
            "label": "Inspect Device Health",
            "enabled": any(item.get("source") == "deviced" for item in notifications),
            "tone": "warning",
        },
    ]

    return {
        "component_id": "notification-center",
        "panel_id": "notification-center-panel",
        "panel_kind": "shell-panel-skeleton",
        "header": {
            "title": "Notification Center",
            "subtitle": f"{summary['total']} notifications · {len(summary['by_source'])} sources",
            "status": status,
            "tone": tone_for(status),
        },
        "badges": [
            {"label": "Total", "value": summary["total"], "tone": "neutral"},
            {
                "label": "High",
                "value": summary["by_severity"].get("high", 0),
                "tone": tone_for("high") if summary["by_severity"].get("high", 0) else "neutral",
            },
            {"label": "Sources", "value": len(summary["by_source"]), "tone": "neutral"},
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "notifications",
                "title": "Notifications",
                "items": [
                    {
                        "label": item.get("title", "notification"),
                        "value": item.get("detail", "-"),
                        "source": item.get("source", "unknown"),
                        "severity": item.get("severity", "info"),
                        "kind": item.get("kind", "unknown"),
                        "tone": tone_for(item.get("severity")),
                    }
                    for item in notifications
                ],
                "empty_state": "No notifications",
            },
            {
                "section_id": "sources",
                "title": "Sources",
                "items": [
                    {"label": source, "value": count, "tone": "neutral"}
                    for source, count in sorted(summary["by_source"].items())
                ],
                "empty_state": "No sources",
            },
            {
                "section_id": "severity-mix",
                "title": "Severity Mix",
                "items": [
                    {"label": severity, "value": count, "tone": tone_for(severity)}
                    for severity, count in sorted(summary["by_severity"].items())
                ],
                "empty_state": "No severities",
            },
        ],
        "meta": {
            "notification_count": summary["total"],
            "source_summary": summary["by_source"],
            "severity_summary": summary["by_severity"],
            "kind_summary": summary["by_kind"],
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
                if section["section_id"] == "notifications":
                    lines.append(
                        f"- [{item['severity']}] {item['label']} ({item['source']}) :: {item['value']}"
                    )
                else:
                    lines.append(f"- {item['label']}: {item['value']}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS notification center panel skeleton")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--recovery-surface", type=Path, default=default_recovery_surface())
    parser.add_argument("--updated-socket", type=Path, default=default_updated_socket())
    parser.add_argument("--indicator-state", type=Path, default=default_indicator_state())
    parser.add_argument("--backend-state", type=Path, default=default_backend_state())
    parser.add_argument("--deviced-socket", type=Path, default=default_deviced_socket())
    parser.add_argument("--policy-socket", type=Path, default=default_policy_socket())
    parser.add_argument("--panel-action-log", type=Path, default=default_panel_action_log())
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        notifications = load_notifications(args)
        model = build_model(notifications)
        selected = next((item for item in model["actions"] if item["action_id"] == args.action), None)
        if selected is None:
            raise SystemExit(f"unknown action: {args.action}")
        target_component = None
        if args.action == "review-approvals" and selected.get("enabled", False):
            target_component = "approval-panel"
        elif args.action == "open-recovery" and selected.get("enabled", False):
            target_component = "recovery-surface"
        elif args.action == "inspect-device-health" and selected.get("enabled", False):
            target_component = "device-backend-status"
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "notification_count": model["meta"]["notification_count"],
            "status": model["header"]["status"],
            "target_component": target_component,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            notifications = load_notifications(args)
            model = build_model(notifications)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    notifications = load_notifications(args)
    model = build_model(notifications)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
