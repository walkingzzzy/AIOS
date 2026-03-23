#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
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


def default_compositor_runtime_state() -> Path | None:
    value = os.environ.get("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_PATH")
    return Path(value) if value else None


def default_compositor_window_state() -> Path | None:
    value = os.environ.get("AIOS_SHELL_COMPOSITOR_WINDOW_STATE_PATH")
    return Path(value) if value else None


def parse_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_compositor_json(path: Path | None) -> tuple[dict, str | None]:
    if path is None:
        return {}, None
    payload = load_json(path)
    if payload is None:
        return {}, f"missing:{path}"
    if isinstance(payload, dict):
        return payload, None
    return {}, f"invalid-json-object:{path}"


def derive_managed_windows(window_payload: dict, runtime_session: dict) -> list[dict]:
    managed_windows: list[dict] = []
    for entry in window_payload.get("windows", []):
        if not isinstance(entry, dict):
            continue
        workspace_index = parse_int(entry.get("workspace_index"), 0)
        managed_windows.append(
            {
                "window_key": entry.get("window_key"),
                "title": entry.get("title"),
                "app_id": entry.get("app_id"),
                "output_id": entry.get("output_id") or runtime_session.get("active_output_id") or "display-1",
                "workspace_id": f"workspace-{workspace_index + 1}",
                "window_policy": entry.get("window_policy") or "workspace-window",
                "minimized": bool(entry.get("minimized")),
                "visible": not bool(entry.get("minimized")),
            }
        )
    return managed_windows


def derive_release_grade_output_status(outputs: list[dict], renderable_output_count: int) -> str:
    if not outputs:
        return "uninitialized"
    output_count = len(outputs)
    if output_count == 1:
        return f"single-output(renderable={renderable_output_count}/{output_count})"
    if renderable_output_count >= output_count:
        return f"multi-output(renderable={renderable_output_count}/{output_count})"
    return f"multi-output(partial-renderable={renderable_output_count}/{output_count})"


def load_compositor_summary(
    runtime_state_path: Path | None,
    window_state_path: Path | None,
) -> dict:
    runtime_payload, runtime_error = load_compositor_json(runtime_state_path)
    window_payload, window_error = load_compositor_json(window_state_path)
    runtime_session = runtime_payload.get("session")
    if not isinstance(runtime_session, dict):
        runtime_session = runtime_payload if isinstance(runtime_payload, dict) else {}

    runtime_managed_windows = [
        item
        for item in runtime_session.get("managed_windows", [])
        if isinstance(item, dict)
    ]
    window_managed_windows = derive_managed_windows(window_payload, runtime_session)
    managed_windows = window_managed_windows or runtime_managed_windows

    derived_workspace_counts: dict[str, int] = {}
    for window in managed_windows:
        workspace_id = str(window.get("workspace_id") or "workspace-1")
        derived_workspace_counts[workspace_id] = derived_workspace_counts.get(workspace_id, 0) + 1
    workspace_window_counts = dict(sorted(derived_workspace_counts.items()))

    active_workspace_index = parse_int(
        window_payload.get("active_workspace_index"),
        parse_int(runtime_session.get("active_workspace_index"), 0),
    )
    active_workspace_id = f"workspace-{active_workspace_index + 1}"
    outputs = [
        item
        for item in runtime_session.get("outputs", [])
        if isinstance(item, dict)
    ]
    output_count = parse_int(runtime_session.get("output_count"), len(outputs))
    renderable_output_count = parse_int(
        runtime_session.get("renderable_output_count"),
        sum(1 for item in outputs if item.get("renderable")),
    )
    non_renderable_output_count = parse_int(
        runtime_session.get("non_renderable_output_count"),
        max(output_count - renderable_output_count, 0),
    )
    errors = [error for error in (runtime_error, window_error) if error]
    data_status = "ready" if runtime_payload or window_payload else "unavailable"
    if errors and data_status == "ready":
        data_status = "partial"

    return {
        "data_status": data_status,
        "data_error": "; ".join(errors) if errors else None,
        "runtime_phase": runtime_payload.get("phase"),
        "runtime_state_status": runtime_session.get("runtime_state_status"),
        "runtime_state_path": str(runtime_state_path) if runtime_state_path else None,
        "window_state_path": str(window_state_path) if window_state_path else None,
        "window_manager_status": runtime_session.get("window_manager_status"),
        "workspace_count": parse_int(
            runtime_session.get("workspace_count"),
            max(len(workspace_window_counts), 1),
        ),
        "active_workspace_index": active_workspace_index,
        "active_workspace_id": active_workspace_id,
        "active_output_id": window_payload.get("active_output_id") or runtime_session.get("active_output_id"),
        "output_count": output_count,
        "renderable_output_count": renderable_output_count,
        "non_renderable_output_count": non_renderable_output_count,
        "release_grade_output_status": runtime_session.get("release_grade_output_status")
        or derive_release_grade_output_status(outputs, renderable_output_count),
        "managed_window_count": len(managed_windows),
        "visible_window_count": sum(1 for item in managed_windows if item.get("visible")),
        "floating_window_count": sum(1 for item in managed_windows if item.get("window_policy") and "floating" in str(item.get("window_policy"))),
        "minimized_window_count": sum(1 for item in managed_windows if item.get("minimized")),
        "window_move_count": parse_int(runtime_session.get("window_move_count"), 0),
        "window_resize_count": parse_int(runtime_session.get("window_resize_count"), 0),
        "window_minimize_count": parse_int(runtime_session.get("window_minimize_count"), 0),
        "window_restore_count": parse_int(runtime_session.get("window_restore_count"), 0),
        "last_minimized_window_key": runtime_session.get("last_minimized_window_key"),
        "last_restored_window_key": runtime_session.get("last_restored_window_key"),
        "workspace_window_counts": workspace_window_counts,
        "managed_windows": managed_windows,
        "outputs": outputs,
    }


def compositor_notifications(summary: dict) -> list[dict]:
    notifications: list[dict] = []
    if summary.get("data_status") in {"partial", "unavailable"} and (
        summary.get("runtime_state_path") or summary.get("window_state_path")
    ):
        notifications.append(
            {
                "title": "Compositor state unavailable",
                "detail": summary.get("data_error") or "window manager state not published",
                "source": "compositor",
                "severity": "medium",
                "kind": "window-manager-unavailable",
            }
        )
    if summary.get("managed_window_count", 0):
        notifications.append(
            {
                "title": "Workspace windows managed",
                "detail": (
                    f"{summary.get('managed_window_count', 0)} windows · "
                    f"{summary.get('workspace_count', 1)} workspaces · "
                    f"active {summary.get('active_workspace_id') or 'workspace-1'}"
                ),
                "source": "compositor",
                "severity": "info",
                "kind": "window-manager-summary",
            }
        )
    if summary.get("minimized_window_count", 0):
        notifications.append(
            {
                "title": "Minimized windows available",
                "detail": f"{summary.get('minimized_window_count', 0)} windows can be restored from task surface",
                "source": "compositor",
                "severity": "medium",
                "kind": "window-manager-minimized",
            }
        )
    return notifications


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


def load_notifications(args: argparse.Namespace) -> tuple[list[dict], dict, dict, dict, dict]:
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
    compositor_summary = load_compositor_summary(
        args.compositor_runtime_state,
        args.compositor_window_state,
    )
    notifications = list(context["notifications"])
    notifications.extend(compositor_notifications(compositor_summary))
    return (
        notifications,
        context["audit_summary"],
        context["backend_evidence_summary"],
        context["remote_governance_summary"],
        compositor_summary,
    )


def build_model(
    notifications: list[dict],
    audit_summary: dict,
    backend_evidence_summary: dict,
    remote_governance_summary: dict,
    compositor_summary: dict,
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
        {
            "action_id": "inspect-window-manager",
            "label": "Inspect Windows",
            "enabled": bool(
                compositor_summary.get("managed_window_count")
                or compositor_summary.get("minimized_window_count")
                or compositor_summary.get("data_status") != "unavailable"
            ),
            "tone": "warning" if compositor_summary.get("minimized_window_count") else "neutral",
        },
    ]

    return {
        "component_id": "notification-center",
        "panel_id": "notification-center-panel",
        "panel_kind": "shell-panel",
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
            {"label": "Windows", "value": compositor_summary.get("managed_window_count", 0), "tone": "neutral"},
            {
                "label": "Minimized",
                "value": compositor_summary.get("minimized_window_count", 0),
                "tone": "warning" if compositor_summary.get("minimized_window_count", 0) else "neutral",
            },
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
                        "label": "Backend IDs",
                        "value": ", ".join(backend_evidence_summary.get("backend_ids", [])) or "-",
                        "tone": "positive" if backend_evidence_summary.get("backend_ids") else "neutral",
                    },
                    {
                        "label": "Origins",
                        "value": ", ".join(backend_evidence_summary.get("origins", [])) or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Stacks",
                        "value": ", ".join(backend_evidence_summary.get("stacks", [])) or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Contracts",
                        "value": ", ".join(backend_evidence_summary.get("contract_kinds", [])) or "-",
                        "tone": "neutral",
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
            {
                "section_id": "window-manager",
                "title": "Window Manager",
                "items": [
                    {"label": "Status", "value": compositor_summary.get("window_manager_status") or compositor_summary.get("data_status"), "tone": "warning" if compositor_summary.get("data_status") != "ready" else "neutral"},
                    {"label": "Runtime Phase", "value": compositor_summary.get("runtime_phase") or "unknown", "tone": "neutral"},
                    {"label": "Workspace", "value": compositor_summary.get("active_workspace_id") or "workspace-1", "tone": "positive"},
                    {"label": "Output", "value": compositor_summary.get("active_output_id") or "-", "tone": "neutral"},
                    {"label": "Renderable Outputs", "value": compositor_summary.get("renderable_output_count", 0), "tone": "positive" if compositor_summary.get("renderable_output_count", 0) else "neutral"},
                    {"label": "Output Status", "value": compositor_summary.get("release_grade_output_status") or "uninitialized", "tone": "neutral"},
                    {"label": "Managed", "value": compositor_summary.get("managed_window_count", 0), "tone": "neutral"},
                    {"label": "Minimized", "value": compositor_summary.get("minimized_window_count", 0), "tone": "warning" if compositor_summary.get("minimized_window_count", 0) else "neutral"},
                    {"label": "Workspace Count", "value": compositor_summary.get("workspace_count", 1), "tone": "neutral"},
                    {"label": "Workspace Mix", "value": ", ".join(f"{key}:{value}" for key, value in sorted((compositor_summary.get("workspace_window_counts") or {}).items())) or "-", "tone": "neutral"},
                    {"label": "Last Minimized", "value": compositor_summary.get("last_minimized_window_key") or "-", "tone": "warning" if compositor_summary.get("last_minimized_window_key") else "neutral"},
                    {"label": "Last Restored", "value": compositor_summary.get("last_restored_window_key") or "-", "tone": "positive" if compositor_summary.get("last_restored_window_key") else "neutral"},
                ],
                "empty_state": "No compositor window manager summary",
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
            "backend_evidence_backend_ids": backend_evidence_summary.get("backend_ids", []),
            "backend_evidence_origins": backend_evidence_summary.get("origins", []),
            "backend_evidence_stacks": backend_evidence_summary.get("stacks", []),
            "backend_evidence_contract_kinds": backend_evidence_summary.get("contract_kinds", []),
            "backend_evidence_dir": backend_evidence_summary.get("evidence_dir"),
            "remote_governance_entry_count": remote_governance_summary.get("entry_count", 0),
            "remote_governance_matched_entry_count": remote_governance_summary.get("matched_entry_count", 0),
            "remote_governance_issue_count": remote_governance_summary.get("issue_count", 0),
            "remote_governance_fleet_count": remote_governance_summary.get("fleet_count", 0),
            "remote_governance_source_counts": remote_governance_summary.get("source_counts", {}),
            "remote_governance_status_counts": remote_governance_summary.get("status_counts", {}),
            "remote_governance_artifact_paths": remote_governance_summary.get("artifact_paths", {}),
            "compositor_data_status": compositor_summary.get("data_status"),
            "compositor_data_error": compositor_summary.get("data_error"),
            "compositor_runtime_phase": compositor_summary.get("runtime_phase"),
            "compositor_runtime_state_status": compositor_summary.get("runtime_state_status"),
            "compositor_runtime_state_path": compositor_summary.get("runtime_state_path"),
            "compositor_window_state_path": compositor_summary.get("window_state_path"),
            "compositor_window_manager_status": compositor_summary.get("window_manager_status"),
            "compositor_workspace_count": compositor_summary.get("workspace_count", 1),
            "compositor_active_workspace_id": compositor_summary.get("active_workspace_id"),
            "compositor_active_output_id": compositor_summary.get("active_output_id"),
            "compositor_output_count": compositor_summary.get("output_count", 0),
            "compositor_renderable_output_count": compositor_summary.get("renderable_output_count", 0),
            "compositor_non_renderable_output_count": compositor_summary.get("non_renderable_output_count", 0),
            "compositor_release_grade_output_status": compositor_summary.get("release_grade_output_status"),
            "compositor_managed_window_count": compositor_summary.get("managed_window_count", 0),
            "compositor_visible_window_count": compositor_summary.get("visible_window_count", 0),
            "compositor_floating_window_count": compositor_summary.get("floating_window_count", 0),
            "compositor_minimized_window_count": compositor_summary.get("minimized_window_count", 0),
            "compositor_window_move_count": compositor_summary.get("window_move_count", 0),
            "compositor_window_resize_count": compositor_summary.get("window_resize_count", 0),
            "compositor_window_minimize_count": compositor_summary.get("window_minimize_count", 0),
            "compositor_window_restore_count": compositor_summary.get("window_restore_count", 0),
            "compositor_last_minimized_window_key": compositor_summary.get("last_minimized_window_key"),
            "compositor_last_restored_window_key": compositor_summary.get("last_restored_window_key"),
            "compositor_workspace_window_counts": compositor_summary.get("workspace_window_counts", {}),
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
    parser = argparse.ArgumentParser(description="AIOS notification center panel")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--recovery-surface", type=Path, default=default_recovery_surface())
    parser.add_argument("--updated-socket", type=Path, default=default_updated_socket())
    parser.add_argument("--indicator-state", type=Path, default=default_indicator_state())
    parser.add_argument("--backend-state", type=Path, default=default_backend_state())
    parser.add_argument("--deviced-socket", type=Path, default=default_deviced_socket())
    parser.add_argument("--policy-socket", type=Path, default=default_policy_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
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
    parser.add_argument("--compositor-runtime-state", type=Path, default=default_compositor_runtime_state())
    parser.add_argument("--compositor-window-state", type=Path, default=default_compositor_window_state())
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        notifications, audit_summary, backend_evidence_summary, remote_governance_summary, compositor_summary = load_notifications(args)
        model = build_model(
            notifications,
            audit_summary,
            backend_evidence_summary,
            remote_governance_summary,
            compositor_summary,
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
        elif args.action == "inspect-window-manager" and selected.get("enabled", False):
            target_component = "task-surface"
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "notification_count": model["meta"]["notification_count"],
            "status": model["header"]["status"],
            "target_component": target_component,
            "operator_audit_issue_count": model["meta"]["operator_audit_issue_count"],
            "remote_governance_issue_count": model["meta"]["remote_governance_issue_count"],
            "backend_evidence_present_count": model["meta"]["backend_evidence_present_count"],
            "backend_evidence_backend_ids": model["meta"]["backend_evidence_backend_ids"],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            notifications, audit_summary, backend_evidence_summary, remote_governance_summary, compositor_summary = load_notifications(args)
            model = build_model(
                notifications,
                audit_summary,
                backend_evidence_summary,
                remote_governance_summary,
                compositor_summary,
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

    notifications, audit_summary, backend_evidence_summary, remote_governance_summary, compositor_summary = load_notifications(args)
    model = build_model(
        notifications,
        audit_summary,
        backend_evidence_summary,
        remote_governance_summary,
        compositor_summary,
    )
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

