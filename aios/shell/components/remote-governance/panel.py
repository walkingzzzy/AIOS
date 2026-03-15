#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import (
    default_browser_remote_registry,
    default_office_remote_registry,
    default_provider_registry_state_dir,
    load_remote_governance,
)


SEVERITY_TONES = {
    "critical": "critical",
    "high": "warning",
    "medium": "warning",
    "info": "neutral",
}


def tone_for(severity: str | None) -> str:
    if not severity:
        return "neutral"
    return SEVERITY_TONES.get(severity, "neutral")


def header_status(governance: dict) -> tuple[str, str]:
    issues = governance.get("issues", [])
    if any(item.get("severity") == "critical" for item in issues):
        return "critical", "critical"
    if governance.get("issue_count", 0):
        return "attention", "warning"
    if governance.get("matched_entry_count", 0):
        return "ready", "positive"
    return "idle", "neutral"


def build_model(governance: dict, *, issue_only: bool, limit: int) -> dict:
    status, tone = header_status(governance)
    matched_entry_count = governance.get("matched_entry_count", 0)
    issue_count = governance.get("issue_count", 0)
    fleet_count = len(governance.get("fleet_summary", []))
    promoted_count = governance.get("control_plane_registered_count", 0)
    filtered_status_counts = governance.get("filtered_status_counts", {})
    stale_or_revoked = filtered_status_counts.get("stale", 0) + filtered_status_counts.get("revoked", 0)

    return {
        "component_id": "remote-governance",
        "panel_id": "remote-governance-panel",
        "panel_kind": "shell-panel-skeleton",
        "header": {
            "title": "Compat Remote Governance",
            "subtitle": f"{matched_entry_count} matched · {issue_count} issues · {fleet_count} fleets",
            "status": status,
            "tone": tone,
        },
        "badges": [
            {"label": "Matched", "value": matched_entry_count, "tone": "neutral"},
            {"label": "Issues", "value": issue_count, "tone": "warning" if issue_count else "neutral"},
            {"label": "Fleets", "value": fleet_count, "tone": "neutral"},
            {
                "label": "Promoted",
                "value": promoted_count,
                "tone": "positive" if promoted_count else "neutral",
            },
            {
                "label": "Stale/Revoked",
                "value": stale_or_revoked,
                "tone": "warning" if stale_or_revoked else "neutral",
            },
        ],
        "actions": [
            {"action_id": "refresh", "label": "Refresh Governance", "enabled": True, "tone": "neutral"},
            {
                "action_id": "focus-issues",
                "label": "Focus Issues",
                "enabled": issue_count > 0,
                "tone": "warning",
            },
        ],
        "sections": [
            {
                "section_id": "issues",
                "title": "Governance Issues",
                "items": [
                    {
                        "label": item.get("provider_ref") or item.get("provider_id") or "remote",
                        "value": item.get("title") or "issue",
                        "detail": item.get("detail"),
                        "source": item.get("source"),
                        "severity": item.get("severity"),
                        "tone": tone_for(item.get("severity")),
                    }
                    for item in governance.get("issues", [])
                ],
                "empty_state": "No governance issues",
            },
            {
                "section_id": "entries",
                "title": "Remote Registrations",
                "items": [
                    {
                        "label": item.get("provider_ref") or item.get("control_plane_provider_id") or "remote",
                        "value": item.get("registration_status") or "unknown",
                        "source": item.get("source"),
                        "fleet_id": item.get("fleet_id"),
                        "governance_group": item.get("governance_group"),
                        "control_plane_provider_id": item.get("control_plane_provider_id"),
                        "control_plane_status": item.get("control_plane_health_status"),
                        "attestation_mode": item.get("attestation_mode"),
                        "issue_count": item.get("issue_count", 0),
                        "issue_severity": item.get("issue_severity"),
                        "descriptor_only": item.get("descriptor_only", False),
                        "tone": tone_for(item.get("issue_severity")) if item.get("issue_count") else "neutral",
                    }
                    for item in governance.get("entries", [])
                ],
                "empty_state": "No remote registrations matched",
            },
            {
                "section_id": "fleets",
                "title": "Fleet Summary",
                "items": [
                    {
                        "label": item.get("fleet_id", "unassigned"),
                        "value": f"{item.get('entry_count', 0)} remotes",
                        "issue_count": item.get("issue_count", 0),
                        "status_counts": item.get("status_counts", {}),
                        "sources": item.get("sources", []),
                        "tone": "warning" if item.get("issue_count", 0) else "neutral",
                    }
                    for item in governance.get("fleet_summary", [])
                ],
                "empty_state": "No fleet metadata",
            },
            {
                "section_id": "artifacts",
                "title": "Artifact Paths",
                "items": [
                    {"label": key, "value": value, "tone": "neutral"}
                    for key, value in (governance.get("artifact_paths") or {}).items()
                ],
                "empty_state": "No governance artifacts",
            },
        ],
        "meta": {
            "generated_at": governance.get("generated_at"),
            "entry_count": governance.get("entry_count", 0),
            "matched_entry_count": matched_entry_count,
            "issue_count": issue_count,
            "fleet_count": fleet_count,
            "source_counts": governance.get("source_counts", {}),
            "filtered_source_counts": governance.get("filtered_source_counts", {}),
            "status_counts": governance.get("status_counts", {}),
            "filtered_status_counts": filtered_status_counts,
            "fleet_ids": governance.get("fleet_ids", []),
            "governance_groups": governance.get("governance_groups", []),
            "attestation_modes": governance.get("attestation_modes", []),
            "control_plane_provider_ids": governance.get("control_plane_provider_ids", []),
            "control_plane_registered_count": promoted_count,
            "issue_only": issue_only,
            "limit": limit,
            "query": governance.get("query", {}),
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    lines.append("badges: " + ", ".join(f"{item['label']}: {item['value']}" for item in panel["badges"]))
    if panel["actions"]:
        lines.append(
            "actions: "
            + ", ".join(action["label"] for action in panel["actions"] if action.get("enabled", True))
        )
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if not items:
            lines.append(f"- {section['empty_state']}")
            continue
        for item in items:
            if section["section_id"] == "issues":
                lines.append(
                    f"- {item['label']} ({item.get('source') or '-'}) [{item.get('severity') or '-'}]: "
                    f"{item['value']} :: {item.get('detail') or '-'}"
                )
            elif section["section_id"] == "entries":
                lines.append(
                    f"- {item['label']} ({item.get('source') or '-'}) [{item['value']}] "
                    f"fleet={item.get('fleet_id') or '-'} "
                    f"group={item.get('governance_group') or '-'} "
                    f"control_plane={item.get('control_plane_provider_id') or '-'} "
                    f"health={item.get('control_plane_status') or '-'} "
                    f"attestation={item.get('attestation_mode') or '-'} "
                    f"issues={item.get('issue_count', 0)}"
                )
            elif section["section_id"] == "fleets":
                lines.append(
                    f"- {item['label']}: {item['value']} "
                    f"issues={item.get('issue_count', 0)} "
                    f"status={json.dumps(item.get('status_counts', {}), ensure_ascii=False, sort_keys=True)}"
                )
            else:
                lines.append(f"- {item['label']}: {item['value']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS compat remote governance panel")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--issue-only", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--source")
    parser.add_argument("--severity")
    parser.add_argument("--fleet-id")
    parser.add_argument("--governance-group")
    parser.add_argument("--status")
    parser.add_argument("--provider-ref")
    parser.add_argument("--provider-id")
    parser.add_argument("--attestation-mode")
    parser.add_argument("--control-plane-status")
    parser.add_argument("--approval-ref")
    parser.add_argument("--text")
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
        "fleet_id": args.fleet_id,
        "governance_group": args.governance_group,
        "status": args.status,
        "provider_ref": args.provider_ref,
        "provider_id": args.provider_id,
        "attestation_mode": args.attestation_mode,
        "control_plane_status": args.control_plane_status,
        "approval_ref": args.approval_ref,
        "text": args.text,
    }

    def current_model(issue_only: bool) -> dict:
        governance = load_remote_governance(
            args.browser_remote_registry,
            args.office_remote_registry,
            args.provider_registry_state_dir,
            limit=limit,
            filters=filters,
            issue_only=issue_only,
            report_path=args.write_report,
        )
        return build_model(governance, issue_only=issue_only, limit=limit)

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        issue_only = args.issue_only or args.action == "focus-issues"
        model = current_model(issue_only)
        selected = next((item for item in model["actions"] if item["action_id"] == args.action), None)
        if selected is None:
            raise SystemExit(f"unknown action: {args.action}")
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "target_component": "remote-governance",
            "issue_only": issue_only,
            "entry_count": model["meta"]["entry_count"],
            "matched_entry_count": model["meta"]["matched_entry_count"],
            "issue_count": model["meta"]["issue_count"],
            "fleet_count": model["meta"]["fleet_count"],
            "filters": (model.get("meta") or {}).get("query", {}).get("filters", {}),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            model = current_model(args.issue_only)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    model = current_model(args.issue_only)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
