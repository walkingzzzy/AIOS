#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import (
    FILTER_FIELDS,
    default_browser_remote_registry,
    default_compat_observability_log,
    default_office_remote_registry,
    default_policy_audit_log,
    default_provider_registry_state_dir,
    default_remote_audit_log,
    default_runtime_events_log,
    load_operator_audit,
)


SEVERITY_TONES = {
    "critical": "critical",
    "high": "critical",
    "medium": "warning",
    "info": "neutral",
}


def tone_for(severity: str | None) -> str:
    if not severity:
        return "neutral"
    return SEVERITY_TONES.get(severity, "neutral")


def active_filters(audit: dict) -> dict[str, object]:
    query = audit.get("query") if isinstance(audit.get("query"), dict) else {}
    filters = query.get("filters")
    if not isinstance(filters, dict):
        return {}
    return {
        str(key): value
        for key, value in filters.items()
        if isinstance(key, str) and key in FILTER_FIELDS and value not in (None, "")
    }


def build_model(audit: dict, *, issue_only: bool, limit: int) -> dict:
    issues = list(audit.get("issues", []))
    recent_records = list(audit.get("recent_records", []))
    remote_governance = audit.get("remote_governance") or {}
    governance_issues = list(audit.get("governance_issues", []))
    filters = active_filters(audit)
    if issue_only:
        recent_records = issues
    status = "ready"
    if audit.get("issue_count", 0):
        status = "attention"
        if any(item.get("severity") in {"high", "critical"} for item in issues):
            status = "critical"

    actions = [
        {"action_id": "refresh", "label": "Refresh Audit", "enabled": True, "tone": "neutral"},
        {
            "action_id": "focus-issues",
            "label": "Focus Issues",
            "enabled": audit.get("issue_count", 0) > 0,
            "tone": "warning",
        },
        {
            "action_id": "show-all-records",
            "label": "Show All Records",
            "enabled": issue_only,
            "tone": "neutral",
        },
        {
            "action_id": "inspect-remote-governance",
            "label": "Inspect Governance",
            "enabled": remote_governance.get("matched_entry_count", 0) > 0
            or remote_governance.get("issue_count", 0) > 0,
            "tone": "warning" if remote_governance.get("issue_count", 0) else "neutral",
        },
    ]

    filter_items = [
        {"label": key, "value": str(value), "tone": "neutral"}
        for key, value in sorted(filters.items())
    ]

    return {
        "component_id": "operator-audit",
        "panel_id": "operator-audit-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Operator Audit",
            "subtitle": (
                f"{audit.get('matched_record_count', audit.get('record_count', 0))} matched · "
                f"{audit.get('issue_count', 0)} issues · "
                f"{len(audit.get('task_ids', []))} tasks"
            ),
            "status": status,
            "tone": "critical" if status == "critical" else ("warning" if status == "attention" else "neutral"),
        },
        "badges": [
            {
                "label": "Matched",
                "value": audit.get("matched_record_count", audit.get("record_count", 0)),
                "tone": "neutral",
            },
            {
                "label": "Issues",
                "value": audit.get("issue_count", 0),
                "tone": "warning" if audit.get("issue_count", 0) else "neutral",
            },
            {"label": "Sources", "value": len(audit.get("source_counts", {})), "tone": "neutral"},
            {"label": "Tasks", "value": len(audit.get("task_ids", [])), "tone": "neutral"},
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "issues",
                "title": "Issues",
                "items": [
                    {
                        "label": item.get("title", "issue"),
                        "value": item.get("detail", "-"),
                        "source": item.get("source", "unknown"),
                        "severity": item.get("severity", "info"),
                        "timestamp": item.get("timestamp", ""),
                        "tone": tone_for(item.get("severity")),
                    }
                    for item in issues[:limit]
                ],
                "empty_state": "No audit issues",
            },
            {
                "section_id": "query",
                "title": "Query",
                "items": [
                    {
                        "label": "Report",
                        "value": (audit.get("query") or {}).get("report_path") or "not-written",
                        "tone": "neutral" if (audit.get("query") or {}).get("report_path") else "warning",
                    },
                    {
                        "label": "Latest",
                        "value": (audit.get("query") or {}).get("latest_timestamp") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Oldest",
                        "value": (audit.get("query") or {}).get("oldest_timestamp") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Providers",
                        "value": len(audit.get("provider_ids", [])),
                        "tone": "neutral",
                    },
                    {
                        "label": "Capabilities",
                        "value": len(audit.get("capability_ids", [])),
                        "tone": "neutral",
                    },
                ]
                + filter_items,
                "empty_state": "No active query filters",
            },
            {
                "section_id": "recent-records",
                "title": "Recent Records" if not issue_only else "Focused Issues",
                "items": [
                    {
                        "label": item.get("title", "record"),
                        "value": item.get("detail", "-"),
                        "source": item.get("source", "unknown"),
                        "timestamp": item.get("timestamp", ""),
                        "tone": tone_for(item.get("severity")),
                    }
                    for item in recent_records[:limit]
                ],
                "empty_state": "No operator audit records",
            },
            {
                "section_id": "remote-governance",
                "title": "Remote Governance",
                "items": [
                    {
                        "label": "Matched",
                        "value": remote_governance.get("matched_entry_count", 0),
                        "tone": "neutral",
                    },
                    {
                        "label": "Issues",
                        "value": remote_governance.get("issue_count", 0),
                        "tone": "warning" if remote_governance.get("issue_count", 0) else "neutral",
                    },
                    {
                        "label": "Fleets",
                        "value": remote_governance.get("fleet_count", 0),
                        "tone": "neutral",
                    },
                    {
                        "label": "Statuses",
                        "value": json.dumps(
                            remote_governance.get("filtered_status_counts") or {},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No remote governance records",
            },
            {
                "section_id": "remote-governance-issues",
                "title": "Remote Governance Issues",
                "items": [
                    {
                        "label": item.get("title", "issue"),
                        "value": item.get("detail", "-"),
                        "source": item.get("source", "governance"),
                        "severity": item.get("severity", "info"),
                        "timestamp": item.get("timestamp", ""),
                        "tone": tone_for(item.get("severity")),
                    }
                    for item in governance_issues[:limit]
                ],
                "empty_state": "No remote governance issues",
            },
            {
                "section_id": "sources",
                "title": "Source Coverage",
                "items": [
                    {
                        "label": source,
                        "value": f"{(audit.get('filtered_source_counts') or {}).get(source, 0)} matched / {count} total",
                        "issues": (audit.get("issue_source_counts") or {}).get(source, 0),
                        "tone": "warning"
                        if (audit.get("issue_source_counts") or {}).get(source, 0)
                        else "neutral",
                    }
                    for source, count in sorted((audit.get("source_counts") or {}).items())
                ],
                "empty_state": "No audit sources",
            },
            {
                "section_id": "tasks",
                "title": "Correlated Tasks",
                "items": [
                    {"label": task_id, "value": "observed", "tone": "neutral"}
                    for task_id in audit.get("task_ids", [])
                ],
                "empty_state": "No correlated tasks",
            },
            {
                "section_id": "artifacts",
                "title": "Artifact Paths",
                "items": [
                    {
                        "label": key,
                        "value": value or "missing",
                        "tone": "neutral" if value else "warning",
                    }
                    for key, value in sorted((audit.get("artifact_paths") or {}).items())
                ],
                "empty_state": "No artifact paths",
            },
        ],
        "meta": {
            "record_count": audit.get("record_count", 0),
            "matched_record_count": audit.get("matched_record_count", audit.get("record_count", 0)),
            "issue_count": audit.get("issue_count", 0),
            "task_count": len(audit.get("task_ids", [])),
            "source_counts": audit.get("source_counts", {}),
            "filtered_source_counts": audit.get("filtered_source_counts", {}),
            "issue_source_counts": audit.get("issue_source_counts", {}),
            "artifact_paths": audit.get("artifact_paths", {}),
            "filters": filters,
            "provider_ids": audit.get("provider_ids", []),
            "capability_ids": audit.get("capability_ids", []),
            "remote_governance_entry_count": remote_governance.get("entry_count", 0),
            "remote_governance_matched_entry_count": remote_governance.get("matched_entry_count", 0),
            "remote_governance_issue_count": remote_governance.get("issue_count", 0),
            "remote_governance_fleet_count": remote_governance.get("fleet_count", 0),
            "remote_governance_source_counts": remote_governance.get("source_counts", {}),
            "remote_governance_filtered_source_counts": remote_governance.get("filtered_source_counts", {}),
            "remote_governance_status_counts": remote_governance.get("status_counts", {}),
            "remote_governance_filtered_status_counts": remote_governance.get("filtered_status_counts", {}),
            "remote_governance_fleet_ids": remote_governance.get("fleet_ids", []),
            "remote_governance_artifact_paths": remote_governance.get("artifact_paths", {}),
            "query": audit.get("query", {}),
            "issue_only": issue_only,
            "limit": limit,
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
        if not items:
            lines.append(f"- {section['empty_state']}")
            continue
        for item in items:
            suffix = f" ({item['source']})" if item.get("source") else ""
            lines.append(f"- {item['label']}{suffix}: {item['value']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS operator audit panel")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--policy-audit-log", type=Path, default=default_policy_audit_log())
    parser.add_argument("--runtime-events-log", type=Path, default=default_runtime_events_log())
    parser.add_argument("--remote-audit-log", type=Path, default=default_remote_audit_log())
    parser.add_argument(
        "--compat-observability-log",
        type=Path,
        default=default_compat_observability_log(),
    )
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--issue-only", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--source")
    parser.add_argument("--severity")
    parser.add_argument("--provider-id")
    parser.add_argument("--provider-ref")
    parser.add_argument("--capability-id")
    parser.add_argument("--decision")
    parser.add_argument("--status")
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--approval-id")
    parser.add_argument("--approval-ref")
    parser.add_argument("--audit-id")
    parser.add_argument("--error-code")
    parser.add_argument("--text")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--fleet-id")
    parser.add_argument("--governance-group")
    parser.add_argument("--attestation-mode")
    parser.add_argument("--control-plane-status")
    parser.add_argument("--write-report", type=Path)
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    limit = max(1, min(args.limit, 32))
    filters = {
        "source": args.source,
        "severity": args.severity,
        "provider_id": args.provider_id,
        "provider_ref": args.provider_ref,
        "capability_id": args.capability_id,
        "decision": args.decision,
        "status": args.status,
        "session_id": args.session_id,
        "task_id": args.task_id,
        "approval_id": args.approval_id,
        "approval_ref": args.approval_ref,
        "audit_id": args.audit_id,
        "error_code": args.error_code,
        "text": args.text,
        "since": args.since,
        "until": args.until,
        "fleet_id": args.fleet_id,
        "governance_group": args.governance_group,
        "attestation_mode": args.attestation_mode,
        "control_plane_status": args.control_plane_status,
    }

    def governance_filters_for_meta(model_meta: dict) -> dict[str, object]:
        filters = dict(model_meta.get("filters") or {})
        governance_filters: dict[str, object] = {}
        source = filters.get("source")
        if source in {"browser", "office", "compat"}:
            governance_filters["source"] = source
        for key in (
            "fleet_id",
            "governance_group",
            "provider_ref",
            "provider_id",
            "attestation_mode",
            "control_plane_status",
            "text",
            "status",
            "approval_ref",
        ):
            value = filters.get(key)
            if value not in (None, ""):
                governance_filters[key] = value
        if "approval_ref" not in governance_filters:
            approval_value = filters.get("approval_id")
            if approval_value not in (None, ""):
                governance_filters["approval_ref"] = approval_value
        return governance_filters

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        audit = load_operator_audit(
            args.policy_audit_log,
            args.runtime_events_log,
            args.remote_audit_log,
            args.compat_observability_log,
            browser_remote_registry=args.browser_remote_registry,
            office_remote_registry=args.office_remote_registry,
            provider_registry_state_dir=args.provider_registry_state_dir,
            limit=limit,
            filters=filters,
            report_path=args.write_report,
        )
        model = build_model(audit, issue_only=args.issue_only, limit=limit)
        selected = next((item for item in model["actions"] if item["action_id"] == args.action), None)
        if selected is None:
            raise SystemExit(f"unknown action: {args.action}")
        target_component = "remote-governance" if args.action == "inspect-remote-governance" else "operator-audit"
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "target_component": target_component,
            "issue_only": True if args.action == "focus-issues" and selected.get("enabled") else False,
            "issue_count": model["meta"]["issue_count"],
            "record_count": model["meta"]["record_count"],
            "matched_record_count": model["meta"]["matched_record_count"],
            "filters": model["meta"]["filters"],
            "remote_governance_filters": governance_filters_for_meta(model["meta"]),
            "remote_governance_issue_count": model["meta"]["remote_governance_issue_count"],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            audit = load_operator_audit(
                args.policy_audit_log,
                args.runtime_events_log,
                args.remote_audit_log,
                args.compat_observability_log,
                browser_remote_registry=args.browser_remote_registry,
                office_remote_registry=args.office_remote_registry,
                provider_registry_state_dir=args.provider_registry_state_dir,
                limit=limit,
                filters=filters,
                report_path=args.write_report,
            )
            model = build_model(audit, issue_only=args.issue_only, limit=limit)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    audit = load_operator_audit(
        args.policy_audit_log,
        args.runtime_events_log,
        args.remote_audit_log,
        args.compat_observability_log,
        browser_remote_registry=args.browser_remote_registry,
        office_remote_registry=args.office_remote_registry,
        provider_registry_state_dir=args.provider_registry_state_dir,
        limit=limit,
        filters=filters,
        report_path=args.write_report,
    )
    model = build_model(audit, issue_only=args.issue_only, limit=limit)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

