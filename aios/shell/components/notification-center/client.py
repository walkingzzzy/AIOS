#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from prototype import (
    notification_context,
    default_browser_remote_registry,
    default_mcp_remote_registry,
    default_office_remote_registry,
    default_provider_registry_state_dir,
    default_compat_observability_log,
    default_panel_action_log,
    default_backend_state,
    default_deviced_socket,
    default_agent_socket,
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
    load_remote_governance_summary,
    load_recovery_surface,
    operator_audit_notifications,
    print_notifications,
)


def build_summary(
    notifications: list[dict],
    *,
    audit_summary: dict | None = None,
    backend_evidence_summary: dict | None = None,
    remote_governance_summary: dict | None = None,
) -> dict:
    by_severity: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for item in notifications:
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        by_source[item["source"]] = by_source.get(item["source"], 0) + 1
    return {
        "total": len(notifications),
        "by_severity": by_severity,
        "by_source": by_source,
        "operator_audit_issue_count": (audit_summary or {}).get("issue_count", 0),
        "backend_evidence_present_count": (backend_evidence_summary or {}).get("present_count", 0),
        "backend_evidence_missing_count": (backend_evidence_summary or {}).get("missing_count", 0),
        "backend_evidence_backend_ids": (backend_evidence_summary or {}).get("backend_ids", []),
        "remote_governance_issue_count": (remote_governance_summary or {}).get("issue_count", 0),
        "remote_governance_matched_entry_count": (remote_governance_summary or {}).get("matched_entry_count", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS notification center shell client")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "summary"])
    parser.add_argument("--recovery-surface", type=Path, default=default_recovery_surface())
    parser.add_argument("--updated-socket", type=Path, default=default_updated_socket())
    parser.add_argument("--indicator-state", type=Path, default=default_indicator_state())
    parser.add_argument("--backend-state", type=Path, default=default_backend_state())
    parser.add_argument("--deviced-socket", type=Path, default=default_deviced_socket())
    parser.add_argument("--policy-socket", type=Path, default=default_policy_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--compositor-runtime-state", type=Path)
    parser.add_argument("--compositor-window-state", type=Path)
    parser.add_argument("--ai-readiness", type=Path)
    parser.add_argument("--ai-onboarding-report", type=Path)
    parser.add_argument("--runtime-platform-env", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model-registry", type=Path)
    parser.add_argument("--panel-action-log", type=Path, default=default_panel_action_log())
    parser.add_argument("--policy-audit-log", type=Path, default=default_policy_audit_log())
    parser.add_argument("--runtime-events-log", type=Path, default=default_runtime_events_log())
    parser.add_argument("--remote-audit-log", type=Path, default=default_remote_audit_log())
    parser.add_argument("--compat-observability-log", type=Path, default=default_compat_observability_log())
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--mcp-remote-registry", type=Path, default=default_mcp_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    recovery_surface = load_recovery_surface(args.recovery_surface, args.updated_socket)
    indicator_state = load_json(args.indicator_state)
    backend_state = load_backend_state(args.backend_state, args.deviced_socket)
    panel_action_events = load_panel_action_events(args.panel_action_log)
    approvals = list_approvals(args.agent_socket, args.approval_fixture)
    audit_summary = operator_audit_notifications(
        args.policy_audit_log,
        args.runtime_events_log,
        args.remote_audit_log,
        args.compat_observability_log,
    )
    remote_governance_summary = load_remote_governance_summary(
        args.browser_remote_registry,
        args.office_remote_registry,
        args.mcp_remote_registry,
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
    notifications = context["notifications"]
    backend_evidence_summary = context["backend_evidence_summary"]

    if args.command == "summary":
        summary = build_summary(
            notifications,
            audit_summary=audit_summary,
            backend_evidence_summary=backend_evidence_summary,
            remote_governance_summary=remote_governance_summary,
        )
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"total: {summary['total']}")
            print(f"by_severity: {json.dumps(summary['by_severity'], ensure_ascii=False, sort_keys=True)}")
            print(f"by_source: {json.dumps(summary['by_source'], ensure_ascii=False, sort_keys=True)}")
            print(f"operator_audit_issue_count: {summary['operator_audit_issue_count']}")
            print(f"backend_evidence_present_count: {summary['backend_evidence_present_count']}")
            print(f"backend_evidence_backend_ids: {json.dumps(summary['backend_evidence_backend_ids'], ensure_ascii=False)}")
            print(f"remote_governance_issue_count: {summary['remote_governance_issue_count']}")
        return 0

    if args.json:
        print(json.dumps({"notifications": notifications}, indent=2, ensure_ascii=False))
    else:
        print_notifications(notifications)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
