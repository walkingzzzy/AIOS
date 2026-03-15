#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import (
    notification_context,
    default_browser_remote_registry,
    default_office_remote_registry,
    default_provider_registry_state_dir,
    default_compat_observability_log,
    default_panel_action_log,
    default_backend_state,
    default_deviced_socket,
    default_indicator_state,
    default_policy_socket,
    default_policy_audit_log,
    default_recovery_surface,
    default_remote_audit_log,
    default_runtime_events_log,
    default_updated_socket,
    list_approvals,
    load_backend_state,
    load_json,
    load_panel_action_events,
    operator_audit_notifications,
    load_remote_governance_summary,
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


def load_notifications(args: argparse.Namespace) -> tuple[list[dict], dict, dict, dict]:
    recovery_surface = load_recovery_surface(args.recovery_surface, args.updated_socket)
    indicator_state = load_json(args.indicator_state)
    backend_state = load_backend_state(args.backend_state, args.deviced_socket)
    panel_action_events = load_panel_action_events(args.panel_action_log)
    approvals = list_approvals(args.policy_socket, args.approval_fixture)
    audit_summary = operator_audit_notifications(
        args.policy_audit_log,
        args.runtime_events_log,
        args.remote_audit_log,
        args.compat_observability_log,
    )
    remote_governance_summary = load_remote_governance_summary(
        args.browser_remote_registry,
        args.office_remote_registry,
        args.provider_registry_state_dir,
    )
    context = notification_context(
        recovery_surface,
        indicator_state,
        approvals,
        backend_state,
        panel_action_events,
        audit_summary,
        remote_governance_summary,
    )
    return (
        context["notifications"],
        context["audit_summary"],
        context["backend_evidence_summary"],
        context["remote_governance_summary"],
    )


def build_model(
    notifications: list[dict],
    audit_summary: dict,
    backend_evidence_summary: dict,
    remote_governance_summary: dict,
) -> dict:
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
        {
            "action_id": "inspect-operator-audit",
            "label": "Inspect Operator Audit",
            "enabled": bool(audit_summary.get("issue_count")),
            "tone": "warning",
        },
        {
            "action_id": "inspect-remote-governance",
            "label": "Inspect Remote Governance",
            "enabled": bool(
                remote_governance_summary.get("matched_entry_count")
                or remote_governance_summary.get("issue_count")
            ),
            "tone": "warning" if remote_governance_summary.get("issue_count") else "neutral",
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
            {
                "section_id": "operator-audit",
                "title": "Operator Audit",
                "items": [
                    {"label": "Records", "value": audit_summary.get("record_count", 0), "tone": "neutral"},
                    {
                        "label": "Issues",
                        "value": audit_summary.get("issue_count", 0),
                        "tone": "warning" if audit_summary.get("issue_count", 0) else "neutral",
                    },
                    {
                        "label": "Tasks",
                        "value": len(audit_summary.get("task_ids", [])),
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No operator audit records",
            },
            {
                "section_id": "operator-audit-sources",
                "title": "Operator Audit Sources",
                "items": [
                    {"label": source, "value": count, "tone": "neutral"}
                    for source, count in sorted((audit_summary.get("source_counts") or {}).items())
                ],
                "empty_state": "No audit sources",
            },
            {
                "section_id": "device-backend-evidence",
                "title": "Device Backend Evidence",
                "items": [
                    {
                        "label": "Ready",
                        "value": backend_evidence_summary.get("present_count", 0),
                        "tone": "positive" if backend_evidence_summary.get("present_count", 0) else "neutral",
                    },
                    {
                        "label": "Missing",
                        "value": backend_evidence_summary.get("missing_count", 0),
                        "tone": "warning" if backend_evidence_summary.get("missing_count", 0) else "neutral",
                    },
                    {
                        "label": "Baselines",
                        "value": ", ".join(backend_evidence_summary.get("baselines", [])) or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Evidence Dir",
                        "value": backend_evidence_summary.get("evidence_dir") or "missing",
                        "tone": "neutral" if backend_evidence_summary.get("evidence_dir") else "warning",
                    },
                ],
                "empty_state": "No backend evidence summary",
            },
            {
                "section_id": "remote-governance",
                "title": "Remote Governance",
                "items": [
                    {
                        "label": "Matched",
                        "value": remote_governance_summary.get("matched_entry_count", 0),
                        "tone": "neutral",
                    },
                    {
                        "label": "Issues",
                        "value": remote_governance_summary.get("issue_count", 0),
                        "tone": "warning" if remote_governance_summary.get("issue_count", 0) else "neutral",
                    },
                    {
                        "label": "Fleets",
                        "value": remote_governance_summary.get("fleet_count", 0),
                        "tone": "neutral",
                    },
                    {
                        "label": "Sources",
                        "value": ", ".join(
                            f"{source}:{count}"
                            for source, count in sorted((remote_governance_summary.get("source_counts") or {}).items())
                        )
                        or "-",
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No remote governance summary",
            },
            {
                "section_id": "remote-governance-issues",
                "title": "Remote Governance Issues",
                "items": [
                    {
                        "label": item.get("provider_ref") or item.get("provider_id") or "remote",
                        "value": item.get("title") or "issue",
                        "detail": item.get("detail") or "-",
                        "tone": tone_for(item.get("severity")),
                    }
                    for item in remote_governance_summary.get("issues", [])
                ],
                "empty_state": "No remote governance issues",
            },
        ],
        "meta": {
            "notification_count": summary["total"],
            "source_summary": summary["by_source"],
            "severity_summary": summary["by_severity"],
            "kind_summary": summary["by_kind"],
            "operator_audit_record_count": audit_summary.get("record_count", 0),
            "operator_audit_issue_count": audit_summary.get("issue_count", 0),
            "operator_audit_task_count": len(audit_summary.get("task_ids", [])),
            "operator_audit_source_counts": audit_summary.get("source_counts", {}),
            "operator_audit_artifact_paths": audit_summary.get("artifact_paths", {}),
            "backend_evidence_artifact_count": backend_evidence_summary.get("artifact_count", 0),
            "backend_evidence_present_count": backend_evidence_summary.get("present_count", 0),
            "backend_evidence_missing_count": backend_evidence_summary.get("missing_count", 0),
            "backend_evidence_baselines": backend_evidence_summary.get("baselines", []),
            "backend_evidence_dir": backend_evidence_summary.get("evidence_dir"),
            "remote_governance_entry_count": remote_governance_summary.get("entry_count", 0),
            "remote_governance_matched_entry_count": remote_governance_summary.get("matched_entry_count", 0),
            "remote_governance_issue_count": remote_governance_summary.get("issue_count", 0),
            "remote_governance_fleet_count": remote_governance_summary.get("fleet_count", 0),
            "remote_governance_source_counts": remote_governance_summary.get("source_counts", {}),
            "remote_governance_status_counts": remote_governance_summary.get("status_counts", {}),
            "remote_governance_artifact_paths": remote_governance_summary.get("artifact_paths", {}),
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
    parser.add_argument("--policy-audit-log", type=Path, default=default_policy_audit_log())
    parser.add_argument("--runtime-events-log", type=Path, default=default_runtime_events_log())
    parser.add_argument("--remote-audit-log", type=Path, default=default_remote_audit_log())
    parser.add_argument("--compat-observability-log", type=Path, default=default_compat_observability_log())
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        notifications, audit_summary, backend_evidence_summary, remote_governance_summary = load_notifications(args)
        model = build_model(
            notifications,
            audit_summary,
            backend_evidence_summary,
            remote_governance_summary,
        )
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
        elif args.action == "inspect-operator-audit" and selected.get("enabled", False):
            target_component = "operator-audit"
        elif args.action == "inspect-remote-governance" and selected.get("enabled", False):
            target_component = "remote-governance"
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "notification_count": model["meta"]["notification_count"],
            "status": model["header"]["status"],
            "target_component": target_component,
            "operator_audit_issue_count": model["meta"]["operator_audit_issue_count"],
            "remote_governance_issue_count": model["meta"]["remote_governance_issue_count"],
            "backend_evidence_present_count": model["meta"]["backend_evidence_present_count"],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            notifications, audit_summary, backend_evidence_summary, remote_governance_summary = load_notifications(args)
            model = build_model(
                notifications,
                audit_summary,
                backend_evidence_summary,
                remote_governance_summary,
            )
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    notifications, audit_summary, backend_evidence_summary, remote_governance_summary = load_notifications(args)
    model = build_model(
        notifications,
        audit_summary,
        backend_evidence_summary,
        remote_governance_summary,
    )
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
