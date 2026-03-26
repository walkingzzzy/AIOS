#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import (
    apply_remote_registration_request,
    default_browser_remote_registry,
    default_remote_registration_request_path,
    default_office_remote_registry,
    default_mcp_remote_registry,
    default_provider_registry_state_dir,
    load_remote_governance,
    load_remote_registration_request,
    promote_remote_registration_request,
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


def build_model(
    governance: dict,
    request_summary: dict[str, object],
    *,
    issue_only: bool,
    limit: int,
) -> dict:
    status, tone = header_status(governance)
    matched_entry_count = governance.get("matched_entry_count", 0)
    issue_count = governance.get("issue_count", 0)
    fleet_count = len(governance.get("fleet_summary", []))
    promoted_count = governance.get("control_plane_registered_count", 0)
    filtered_status_counts = governance.get("filtered_status_counts", {})
    stale_or_revoked = filtered_status_counts.get("stale", 0) + filtered_status_counts.get("revoked", 0)
    request_ready = bool(request_summary.get("ready", False))
    request_status = request_summary.get("source_status") or "missing"

    return {
        "component_id": "remote-governance",
        "panel_id": "remote-governance-panel",
        "panel_kind": "shell-panel",
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
            {
                "label": "Request",
                "value": "ready" if request_ready else request_status,
                "tone": "positive" if request_ready else tone_for("medium" if request_status == "ready" else None),
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
            {
                "action_id": "register-remote-request",
                "label": "Register Remote Request",
                "enabled": request_ready,
                "tone": "positive" if request_ready else "warning",
            },
            {
                "action_id": "promote-remote-request",
                "label": "Promote Remote Request",
                "enabled": request_ready,
                "tone": "positive" if request_ready else "warning",
            },
            {
                "action_id": "register-and-promote-request",
                "label": "Register + Promote",
                "enabled": request_ready,
                "tone": "positive" if request_ready else "warning",
            },
        ],
        "sections": [
            {
                "section_id": "request",
                "title": "Remote Registration Request",
                "items": [
                    {
                        "label": "Source Path",
                        "value": request_summary.get("source_path") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Status",
                        "value": request_status,
                        "tone": "positive" if request_ready else "warning",
                    },
                    {
                        "label": "Provider Kind",
                        "value": request_summary.get("provider_kind") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Provider Ref",
                        "value": request_summary.get("provider_ref") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Endpoint",
                        "value": request_summary.get("endpoint") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Capabilities",
                        "value": ", ".join(request_summary.get("capabilities") or []) or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Display Name",
                        "value": request_summary.get("display_name") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Control Plane ID",
                        "value": request_summary.get("control_plane_provider_id") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Errors",
                        "value": ", ".join(request_summary.get("errors") or []) or "-",
                        "tone": "warning" if request_summary.get("errors") else "neutral",
                    },
                    {
                        "label": "Warnings",
                        "value": ", ".join(request_summary.get("warnings") or []) or "-",
                        "tone": "warning" if request_summary.get("warnings") else "neutral",
                    },
                ],
                "empty_state": "No remote registration request configured",
            },
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
            "request_source_status": request_status,
            "request_source_path": request_summary.get("source_path"),
            "request_ready": request_ready,
            "request_provider_kind": request_summary.get("provider_kind"),
            "request_provider_ref": request_summary.get("provider_ref"),
            "request_endpoint": request_summary.get("endpoint"),
            "request_capabilities": request_summary.get("capabilities") or [],
            "request_errors": request_summary.get("errors") or [],
            "request_warnings": request_summary.get("warnings") or [],
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
    parser.add_argument("--mcp-remote-registry", type=Path, default=default_mcp_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--remote-registration-request", type=Path, default=default_remote_registration_request_path())
    parser.add_argument("--agent-socket", type=Path)
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
            args.mcp_remote_registry,
            args.provider_registry_state_dir,
            limit=limit,
            filters=filters,
            issue_only=issue_only,
            report_path=args.write_report,
        )
        request_summary = load_remote_registration_request(args.remote_registration_request)
        return build_model(governance, request_summary, issue_only=issue_only, limit=limit)

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
            "request_ready": model["meta"].get("request_ready", False),
            "request_source_status": model["meta"].get("request_source_status"),
            "request_provider_ref": model["meta"].get("request_provider_ref"),
            "filters": (model.get("meta") or {}).get("query", {}).get("filters", {}),
        }
        if args.action == "register-remote-request" and selected.get("enabled", False):
            request_summary = load_remote_registration_request(args.remote_registration_request)
            result.update(
                apply_remote_registration_request(
                    request_summary,
                    browser_remote_registry=args.browser_remote_registry,
                    office_remote_registry=args.office_remote_registry,
                    mcp_remote_registry=args.mcp_remote_registry,
                )
            )
        elif args.action == "promote-remote-request" and selected.get("enabled", False):
            request_summary = load_remote_registration_request(args.remote_registration_request)
            result.update(
                promote_remote_registration_request(
                    request_summary,
                    browser_remote_registry=args.browser_remote_registry,
                    office_remote_registry=args.office_remote_registry,
                    mcp_remote_registry=args.mcp_remote_registry,
                    provider_registry_state_dir=args.provider_registry_state_dir,
                    agent_socket=args.agent_socket,
                )
            )
        elif args.action == "register-and-promote-request" and selected.get("enabled", False):
            request_summary = load_remote_registration_request(args.remote_registration_request)
            registration_result = apply_remote_registration_request(
                request_summary,
                browser_remote_registry=args.browser_remote_registry,
                office_remote_registry=args.office_remote_registry,
                mcp_remote_registry=args.mcp_remote_registry,
            )
            promotion_result = promote_remote_registration_request(
                request_summary,
                browser_remote_registry=args.browser_remote_registry,
                office_remote_registry=args.office_remote_registry,
                mcp_remote_registry=args.mcp_remote_registry,
                provider_registry_state_dir=args.provider_registry_state_dir,
                agent_socket=args.agent_socket,
            )
            result.update(registration_result)
            result["registration"] = registration_result.get("registration")
            result["registration_status"] = registration_result.get("status")
            result.update(promotion_result)
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

