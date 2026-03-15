#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import default_socket, fixture_call, rpc_call


STATUS_TONES = {
    "pending": "warning",
    "approved": "positive",
    "rejected": "critical",
}


def tone_for(status: str | None) -> str:
    if not status:
        return "neutral"
    return STATUS_TONES.get(status, "neutral")


def list_approvals(socket_path: Path, fixture: Path | None, session_id: str | None, task_id: str | None, status: str | None) -> dict:
    if fixture is not None:
        args = argparse.Namespace(session_id=session_id, task_id=task_id, status=status, approval_ref=None)
        return fixture_call(fixture, "list", args)
    return rpc_call(socket_path, "approval.list", {"session_id": session_id, "task_id": task_id, "status": status})


def resolve_approval(socket_path: Path, fixture: Path | None, approval_ref: str, status: str, resolver: str, reason: str | None) -> dict:
    if fixture is not None:
        args = argparse.Namespace(approval_ref=approval_ref, status=status, resolver=resolver, reason=reason)
        return fixture_call(fixture, "resolve", args)
    return rpc_call(
        socket_path,
        "approval.resolve",
        {"approval_ref": approval_ref, "status": status, "resolver": resolver, "reason": reason},
    )


def build_summary(approvals: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    for item in approvals:
        status = item.get("status", "unknown")
        lane = item.get("approval_lane", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_lane[lane] = by_lane.get(lane, 0) + 1
    return {"total": len(approvals), "by_status": by_status, "by_lane": by_lane}


def build_model(result: dict, session_id: str | None, task_id: str | None) -> dict:
    approvals = result.get("approvals", [])
    summary = build_summary(approvals)
    focus = next((item for item in approvals if item.get("status") == "pending"), approvals[0] if approvals else None)

    approval_items = [
        {
            "approval_ref": item.get("approval_ref"),
            "label": item.get("capability_id") or item.get("approval_ref"),
            "status": item.get("status"),
            "approval_lane": item.get("approval_lane"),
            "tone": tone_for(item.get("status")),
        }
        for item in approvals
    ]
    actions = []
    if focus:
        actions.extend(
            [
                {
                    "action_id": "approve",
                    "label": "Approve",
                    "approval_ref": focus.get("approval_ref"),
                    "target_status": "approved",
                    "enabled": focus.get("status") == "pending",
                },
                {
                    "action_id": "reject",
                    "label": "Reject",
                    "approval_ref": focus.get("approval_ref"),
                    "target_status": "rejected",
                    "enabled": focus.get("status") == "pending",
                },
            ]
        )

    return {
        "component_id": "approval-panel",
        "panel_id": "approval-panel-shell",
        "panel_kind": "shell-panel-skeleton",
        "header": {
            "title": "Approval Panel",
            "subtitle": f"session {session_id or '-'} · task {task_id or '-'}",
            "status": (focus or {}).get("status", "idle"),
            "tone": tone_for((focus or {}).get("status")),
        },
        "badges": [
            {"label": "Total", "value": summary["total"], "tone": "neutral"},
            {"label": "Pending", "value": summary["by_status"].get("pending", 0), "tone": tone_for("pending")},
            {"label": "Lanes", "value": len(summary["by_lane"]), "tone": "neutral"},
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "approvals",
                "title": "Approvals",
                "items": approval_items,
                "empty_state": "No approvals found",
            },
            {
                "section_id": "lanes",
                "title": "Approval Lanes",
                "items": [
                    {"label": lane, "value": count, "tone": "neutral"}
                    for lane, count in sorted(summary["by_lane"].items())
                ],
                "empty_state": "No approval lanes",
            },
        ],
        "meta": {
            "session_id": session_id,
            "task_id": task_id,
            "focus_approval_ref": (focus or {}).get("approval_ref"),
            "approval_count": len(approvals),
            "status_summary": summary["by_status"],
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
                if section["section_id"] == "approvals":
                    lines.append(f"- {item['approval_ref']}: {item['status']} lane={item['approval_lane']} capability={item['label']}")
                else:
                    lines.append(f"- {item['label']}: {item['value']}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS approval panel skeleton")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--status")
    parser.add_argument("--approval-ref")
    parser.add_argument("--resolver", default="shell-approval-panel")
    parser.add_argument("--reason")
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.approval_ref:
            raise SystemExit("--approval-ref is required for action")
        target_status = args.status
        if not target_status:
            if args.action == "approve":
                target_status = "approved"
            elif args.action == "reject":
                target_status = "rejected"
            else:
                raise SystemExit("--status is required for custom action")
        result = resolve_approval(args.socket, args.fixture, args.approval_ref, target_status, args.resolver, args.reason)
        result["target_component"] = "task-surface" if target_status == "approved" else "approval-panel"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            result = list_approvals(args.socket, args.fixture, args.session_id, args.task_id, args.status)
            model = build_model(result, args.session_id, args.task_id)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    result = list_approvals(args.socket, args.fixture, args.session_id, args.task_id, args.status)
    model = build_model(result, args.session_id, args.task_id)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
