#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
from functools import lru_cache
from pathlib import Path


def default_recovery_surface() -> Path:
    return Path(
        os.environ.get(
            "AIOS_UPDATED_RECOVERY_SURFACE_PATH",
            "/var/lib/aios/updated/recovery-surface.json",
        )
    )


def default_updated_socket() -> Path:
    return Path(os.environ.get("AIOS_UPDATED_SOCKET_PATH", "/run/aios/updated/updated.sock"))


def default_indicator_state() -> Path:
    return Path(
        os.environ.get(
            "AIOS_DEVICED_INDICATOR_STATE_PATH",
            "/var/lib/aios/deviced/indicator-state.json",
        )
    )


def default_backend_state() -> Path:
    return Path(
        os.environ.get(
            "AIOS_DEVICED_BACKEND_STATE_PATH",
            "/var/lib/aios/deviced/backend-state.json",
        )
    )


def default_deviced_socket() -> Path:
    return Path(os.environ.get("AIOS_DEVICED_SOCKET_PATH", "/run/aios/deviced/deviced.sock"))


def default_policy_socket() -> Path:
    return Path(os.environ.get("AIOS_POLICYD_SOCKET_PATH", "/run/aios/policyd/policyd.sock"))


def default_panel_action_log() -> Path | None:
    value = os.environ.get("AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH")
    if not value:
        return None
    return Path(value)


def default_policy_audit_log() -> Path:
    return Path(os.environ.get("AIOS_POLICYD_AUDIT_LOG", "/var/lib/aios/policyd/audit.jsonl"))


def default_runtime_events_log() -> Path:
    return Path(
        os.environ.get(
            "AIOS_RUNTIMED_EVENTS_LOG",
            "/var/lib/aios/runtimed/runtime-events.jsonl",
        )
    )


def default_remote_audit_log() -> Path:
    return Path(
        os.environ.get(
            "AIOS_RUNTIMED_REMOTE_AUDIT_LOG",
            "/var/lib/aios/runtimed/remote-audit.jsonl",
        )
    )


def default_compat_observability_log() -> Path:
    return Path(
        os.environ.get(
            "AIOS_COMPAT_OBSERVABILITY_LOG",
            "/var/lib/aios/compat/compat-observability.jsonl",
        )
    )


def load_component_module(component: str, module_name: str):
    shell_root = Path(__file__).resolve().parents[1]
    module_path = shell_root / component / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"aios_shell_{component.replace('-', '_')}_{module_name}",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def backend_helpers():
    return load_component_module("device-backend-status", "prototype")


@lru_cache(maxsize=1)
def remote_governance_helpers():
    return load_component_module("remote-governance", "prototype")


def default_browser_remote_registry() -> Path:
    return remote_governance_helpers().default_browser_remote_registry()


def default_office_remote_registry() -> Path:
    return remote_governance_helpers().default_office_remote_registry()


def default_provider_registry_state_dir() -> Path:
    return remote_governance_helpers().default_provider_registry_state_dir()


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_jsonl(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    records: list[dict] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response["result"]


def list_approvals(socket_path: Path | None, fixture: Path | None) -> list[dict]:
    if fixture is not None:
        payload = load_json(fixture) or {"approvals": []}
        return payload.get("approvals", [])
    if socket_path is None:
        return []
    try:
        response = rpc_call(socket_path, "approval.list", {})
    except Exception:
        return []
    return response.get("approvals", [])


def load_recovery_surface(path: Path, socket_path: Path | None) -> dict | None:
    surface = load_json(path)
    if surface is not None:
        return surface
    if socket_path is None or not socket_path.exists():
        return None
    try:
        return rpc_call(socket_path, "recovery.surface.get", {})
    except Exception:
        return None


def load_backend_state(path: Path, socket_path: Path | None) -> dict | None:
    state = load_json(path)
    if state is not None:
        return backend_helpers().attach_evidence_artifacts(state)
    if socket_path is None or not socket_path.exists():
        return None
    try:
        response = rpc_call(socket_path, "device.state.get", {})
    except Exception:
        return None
    state = {
        "statuses": response.get("backend_statuses", []),
        "adapters": response.get("capture_adapters", []),
        "notes": response.get("notes", []),
    }
    return backend_helpers().attach_evidence_artifacts(state)


def summarize_backend_evidence(backend_state: dict | None) -> dict:
    artifacts = []
    evidence_dir = None
    if isinstance(backend_state, dict):
        artifacts = [
            item for item in backend_state.get("evidence_artifacts", [])
            if isinstance(item, dict)
        ]
        evidence_dir = backend_state.get("evidence_dir")
    baselines = sorted(
        {
            item.get("baseline")
            for item in artifacts
            if isinstance(item.get("baseline"), str) and item.get("baseline")
        }
    )
    summary_items = [
        {
            "modality": item.get("modality"),
            "artifact_path": item.get("artifact_path"),
            "artifact_present": bool(item.get("artifact_present")),
            "baseline": item.get("baseline"),
            "execution_path": item.get("execution_path"),
            "source": item.get("source"),
        }
        for item in artifacts[:6]
    ]
    return {
        "artifact_count": len(artifacts),
        "present_count": sum(1 for item in artifacts if item.get("artifact_present")),
        "missing_count": sum(1 for item in artifacts if not item.get("artifact_present")),
        "baselines": baselines,
        "evidence_dir": evidence_dir,
        "artifacts": summary_items,
    }


def severity_for_backend(status: dict) -> str:
    readiness = status.get("readiness")
    if readiness in {"missing-session-bus", "missing-pipewire-socket", "missing-input-root", "missing-camera-device", "missing-atspi-bus"}:
        return "high"
    if readiness in {"preview-only", "native-stub", "native-state-bridge"}:
        return "info"
    if readiness == "native-live":
        return "info"
    return "medium"


def include_backend_status(status: dict) -> bool:
    readiness = status.get("readiness")
    if readiness in {"native-ready", "native-live", "native-state-bridge", "command-adapter", "disabled"}:
        return False
    if readiness == "native-stub":
        return False
    return True


def load_panel_action_events(path: Path | None, limit: int = 6) -> list[dict]:
    if path is None or not path.exists():
        return []

    entries: list[dict] = []
    lines = path.read_text().splitlines()
    for raw_line in lines[-64:]:
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        if value.get("kind") != "panel-action.dispatch":
            continue
        entries.append(value)
    return entries[-limit:]


def load_remote_governance_summary(
    browser_remote_registry: Path,
    office_remote_registry: Path,
    provider_registry_state_dir: Path,
) -> dict:
    try:
        payload = remote_governance_helpers().load_remote_governance(
            browser_remote_registry,
            office_remote_registry,
            provider_registry_state_dir,
            limit=6,
        )
    except Exception:
        return {
            "entry_count": 0,
            "matched_entry_count": 0,
            "issue_count": 0,
            "fleet_count": 0,
            "source_counts": {},
            "status_counts": {},
            "artifact_paths": {
                "browser_remote_registry": str(browser_remote_registry),
                "office_remote_registry": str(office_remote_registry),
                "provider_registry_state_dir": str(provider_registry_state_dir),
            },
            "issues": [],
        }
    return {
        "entry_count": payload.get("entry_count", 0),
        "matched_entry_count": payload.get("matched_entry_count", 0),
        "issue_count": payload.get("issue_count", 0),
        "fleet_count": len(payload.get("fleet_summary", [])),
        "source_counts": payload.get("filtered_source_counts") or payload.get("source_counts", {}),
        "status_counts": payload.get("filtered_status_counts") or payload.get("status_counts", {}),
        "artifact_paths": payload.get("artifact_paths", {}),
        "issues": [
            {
                "title": item.get("title"),
                "detail": item.get("detail"),
                "severity": item.get("severity"),
                "provider_ref": item.get("provider_ref"),
                "provider_id": item.get("provider_id"),
                "source": item.get("source"),
            }
            for item in payload.get("issues", [])[:4]
            if isinstance(item, dict)
        ],
    }


def severity_for_panel_action(event: dict) -> str:
    status = str(event.get("status") or "")
    if (
        status.startswith("dispatch-error(")
        or status.startswith("dispatch-failed(")
        or status in {"missing-command", "missing-slot"}
    ):
        return "high"
    if status == "no-action":
        return "medium"
    return "info"


def panel_action_kind(event: dict) -> str:
    severity = severity_for_panel_action(event)
    return "panel-action-error" if severity == "high" else "panel-action"


def panel_action_title(event: dict) -> str:
    component = event.get("component") or event.get("slot_id") or "panel-slot"
    action_id = event.get("action_id") or "unknown"
    severity = severity_for_panel_action(event)
    if severity == "high":
        return f"Panel action failed: {component}::{action_id}"
    if severity == "medium":
        return f"Panel action needs attention: {component}::{action_id}"
    return f"Panel action completed: {component}::{action_id}"


def panel_action_detail(event: dict) -> str:
    summary = event.get("summary")
    if summary not in (None, ""):
        return str(summary)
    error = event.get("error")
    if error not in (None, ""):
        return str(error)
    status = event.get("status")
    if status not in (None, ""):
        return str(status)
    return "panel action event recorded"


def operator_audit_notifications(
    policy_audit_log: Path | None,
    runtime_events_log: Path | None,
    remote_audit_log: Path | None,
    compat_observability_log: Path | None,
    limit: int = 6,
) -> dict:
    records = {
        "policy": load_jsonl(policy_audit_log),
        "runtime": load_jsonl(runtime_events_log),
        "remote": load_jsonl(remote_audit_log),
        "compat": load_jsonl(compat_observability_log),
    }
    notifications: list[dict] = []
    task_ids: set[str] = set()

    for entry in records["policy"][-48:]:
        decision = str(entry.get("decision") or "")
        if decision not in {"denied", "needs-approval", "approval-scope-mismatch", "approval-pending"}:
            continue
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            task_ids.add(task_id)
        notifications.append(
            {
                "source": "operator-audit",
                "severity": "high" if decision in {"denied", "approval-scope-mismatch"} else "medium",
                "kind": "audit-policy",
                "title": f"Policy audit: {decision}",
                "detail": f"capability={entry.get('capability_id') or '-'} task={entry.get('task_id') or '-'}",
            }
        )

    for entry in records["runtime"][-48:]:
        kind = str(entry.get("kind") or "")
        if kind not in {"runtime.infer.timeout", "runtime.infer.fallback"}:
            continue
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            task_ids.add(task_id)
        notifications.append(
            {
                "source": "operator-audit",
                "severity": "medium" if kind.endswith("timeout") else "info",
                "kind": "audit-runtime",
                "title": f"Runtime event: {kind}",
                "detail": f"task={entry.get('task_id') or '-'} backend={entry.get('backend_id') or '-'}",
            }
        )

    for entry in records["remote"][-48:]:
        status = str(entry.get("status") or "")
        if status in {"ok", "completed", "ready"}:
            continue
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            task_ids.add(task_id)
        notifications.append(
            {
                "source": "operator-audit",
                "severity": "high" if status in {"error", "failed"} else "medium",
                "kind": "audit-remote",
                "title": f"Remote audit: {status or 'attention'}",
                "detail": f"provider={entry.get('provider_id') or '-'} task={entry.get('task_id') or '-'}",
            }
        )

    for entry in records["compat"][-48:]:
        result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
        error_code = result.get("error_code")
        decision = str(entry.get("decision") or "")
        if error_code in (None, "") and decision not in {"denied", "needs-approval"}:
            continue
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            task_ids.add(task_id)
        notifications.append(
            {
                "source": "operator-audit",
                "severity": "medium" if error_code else "high",
                "kind": "audit-compat",
                "title": f"Compat audit: {error_code or decision}",
                "detail": f"provider={entry.get('provider_id') or '-'} task={entry.get('task_id') or '-'}",
            }
        )

    source_counts = {
        source: len(items)
        for source, items in records.items()
        if items
    }
    return {
        "record_count": sum(len(items) for items in records.values()),
        "issue_count": len(notifications),
        "task_ids": sorted(task_ids),
        "source_counts": source_counts,
        "notifications": notifications[-limit:],
        "artifact_paths": {
            "policy_audit_log": str(policy_audit_log) if policy_audit_log is not None and policy_audit_log.exists() else None,
            "runtime_events_log": str(runtime_events_log) if runtime_events_log is not None and runtime_events_log.exists() else None,
            "remote_audit_log": str(remote_audit_log) if remote_audit_log is not None and remote_audit_log.exists() else None,
            "compat_observability_log": str(compat_observability_log) if compat_observability_log is not None and compat_observability_log.exists() else None,
        },
    }


def build_notifications(
    recovery_surface: dict | None,
    indicator_state: dict | None,
    approvals: list[dict],
    backend_state: dict | None,
    panel_action_events: list[dict] | None = None,
    audit_summary: dict | None = None,
) -> list[dict]:
    notifications: list[dict] = []

    if recovery_surface is not None:
        overall_status = recovery_surface.get("overall_status")
        deployment_status = recovery_surface.get("deployment_status")
        rollback_ready = recovery_surface.get("rollback_ready", False)
        if overall_status in {"degraded", "blocked"}:
            notifications.append(
                {
                    "source": "updated",
                    "severity": "high" if overall_status == "blocked" else "medium",
                    "kind": "recovery-status",
                    "title": f"System update health is {overall_status}",
                    "detail": f"deployment={deployment_status}",
                }
            )
        elif deployment_status not in {None, "idle", "up-to-date"}:
            notifications.append(
                {
                    "source": "updated",
                    "severity": "info",
                    "kind": "deployment-status",
                    "title": f"Deployment state: {deployment_status}",
                    "detail": f"rollback_ready={rollback_ready}",
                }
            )
        if rollback_ready:
            notifications.append(
                {
                    "source": "updated",
                    "severity": "info",
                    "kind": "rollback-ready",
                    "title": "Recovery rollback is available",
                    "detail": ", ".join(recovery_surface.get("available_actions", [])),
                }
            )

    if indicator_state is not None:
        for item in indicator_state.get("active", []):
            notifications.append(
                {
                    "source": "deviced",
                    "severity": "medium",
                    "kind": "capture-active",
                    "title": item.get("message", "Device capture active"),
                    "detail": f"modality={item.get('modality')} approval={item.get('approval_status') or 'n/a'}",
                }
            )

    if backend_state is not None:
        adapter_map = {
            item.get("modality"): item for item in backend_state.get("adapters", []) if item.get("modality")
        }
        for status in backend_state.get("statuses", []):
            if not include_backend_status(status):
                continue
            modality = status.get("modality", "unknown")
            adapter = adapter_map.get(modality)
            adapter_detail = ""
            if adapter is not None:
                adapter_detail = f" adapter={adapter.get('adapter_id')} path={adapter.get('execution_path')}"
            notifications.append(
                {
                    "source": "deviced",
                    "severity": severity_for_backend(status),
                    "kind": "backend-status",
                    "title": f"Backend attention: {modality} is {status.get('readiness')}",
                    "detail": f"backend={status.get('backend')}{adapter_detail}",
                }
            )

    for event in panel_action_events or []:
        notifications.append(
            {
                "source": "shell",
                "severity": severity_for_panel_action(event),
                "kind": panel_action_kind(event),
                "title": panel_action_title(event),
                "detail": panel_action_detail(event),
            }
        )

    for item in (audit_summary or {}).get("notifications", []):
        notifications.append(item)

    pending_approvals = [item for item in approvals if item.get("status") in {"pending", "required"}]
    for item in pending_approvals:
        notifications.append(
            {
                "source": "policyd",
                "severity": "high",
                "kind": "approval-pending",
                "title": f"Approval pending: {item.get('capability_id')}",
                "detail": f"approval_ref={item.get('approval_ref')} task={item.get('task_id')}",
            }
        )

    return notifications


def notification_context(
    recovery_surface: dict | None,
    indicator_state: dict | None,
    approvals: list[dict],
    backend_state: dict | None,
    panel_action_events: list[dict] | None,
    audit_summary: dict | None,
    remote_governance_summary: dict | None,
) -> dict:
    notifications = build_notifications(
        recovery_surface,
        indicator_state,
        approvals,
        backend_state,
        panel_action_events,
        audit_summary,
    )
    return {
        "notifications": notifications,
        "audit_summary": audit_summary or {},
        "backend_evidence_summary": summarize_backend_evidence(backend_state),
        "remote_governance_summary": remote_governance_summary or {},
    }


def print_notifications(items: list[dict]) -> None:
    if not items:
        print("no notifications")
        return
    for item in items:
        print(f"- [{item['severity']}] {item['title']} ({item['source']}) :: {item['detail']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS notification center prototype")
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
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

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
    notifications = build_notifications(
        recovery_surface,
        indicator_state,
        approvals,
        backend_state,
        panel_action_events,
        audit_summary,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "notifications": notifications,
                    "operator_audit": audit_summary,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print_notifications(notifications)
