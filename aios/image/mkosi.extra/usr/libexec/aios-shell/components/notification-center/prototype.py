#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
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


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


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
        return state
    if socket_path is None or not socket_path.exists():
        return None
    try:
        response = rpc_call(socket_path, "device.state.get", {})
    except Exception:
        return None
    return {
        "statuses": response.get("backend_statuses", []),
        "adapters": response.get("capture_adapters", []),
        "notes": response.get("notes", []),
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


def build_notifications(
    recovery_surface: dict | None,
    indicator_state: dict | None,
    approvals: list[dict],
    backend_state: dict | None,
    panel_action_events: list[dict] | None = None,
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
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    recovery_surface = load_recovery_surface(args.recovery_surface, args.updated_socket)
    indicator_state = load_json(args.indicator_state)
    backend_state = load_backend_state(args.backend_state, args.deviced_socket)
    panel_action_events = load_panel_action_events(args.panel_action_log)
    approvals = list_approvals(args.policy_socket, args.approval_fixture)
    notifications = build_notifications(
        recovery_surface,
        indicator_state,
        approvals,
        backend_state,
        panel_action_events,
    )

    if args.json:
        print(json.dumps({"notifications": notifications}, indent=2, ensure_ascii=False))
    else:
        print_notifications(notifications)
