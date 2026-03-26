#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SYSTEM_HEALTH_GET = "system.health.get"
POLICY_TOKEN_VERIFY = "policy.token.verify"
SHELL_WINDOW_FOCUS = "shell.window.focus"
SHELL_NOTIFICATION_OPEN = "shell.notification.open"
SHELL_OPERATOR_AUDIT_OPEN = "shell.operator-audit.open"
SHELL_REMOTE_GOVERNANCE_OPEN = "shell.remote-governance.open"
SHELL_PANEL_EVENTS_LIST = "shell.panel-events.list"


@dataclass
class Config:
    service_id: str
    provider_id: str
    version: str
    socket_path: Path
    policyd_socket: Path
    focus_state_path: Path
    notification_panel: Path
    operator_audit_panel: Path
    remote_governance_panel: Path
    agentd_socket: Path
    remote_registration_request: Path | None
    recovery_surface: Path
    updated_socket: Path
    indicator_state: Path
    backend_state: Path
    deviced_socket: Path
    panel_action_log: Path | None
    approval_fixture: Path | None
    policy_audit_log: Path
    runtime_events_log: Path
    remote_audit_log: Path
    compat_observability_log: Path
    browser_remote_registry: Path
    office_remote_registry: Path
    mcp_remote_registry: Path
    provider_registry_state_dir: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_config() -> Config:
    root = repo_root()
    runtime_dir = Path(os.environ.get("AIOS_SHELL_PROVIDER_RUNTIME_DIR", "/run/aios/shell-provider"))
    state_dir = Path(os.environ.get("AIOS_SHELL_PROVIDER_STATE_DIR", "/var/lib/aios/shell-provider"))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        service_id="aios-shell-control-provider",
        provider_id=os.environ.get("AIOS_SHELL_PROVIDER_ID", "shell.control.local"),
        version="0.1.0",
        socket_path=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_SOCKET_PATH",
                str(runtime_dir / "shell-control-provider.sock"),
            )
        ),
        policyd_socket=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_POLICYD_SOCKET",
                "/run/aios/policyd/policyd.sock",
            )
        ),
        focus_state_path=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_FOCUS_STATE_PATH",
                str(state_dir / "focus-state.json"),
            )
        ),
        notification_panel=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_NOTIFICATION_PANEL",
                str(root / "aios" / "shell" / "components" / "notification-center" / "panel.py"),
            )
        ),
        operator_audit_panel=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_OPERATOR_AUDIT_PANEL",
                str(root / "aios" / "shell" / "components" / "operator-audit" / "panel.py"),
            )
        ),
        remote_governance_panel=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_REMOTE_GOVERNANCE_PANEL",
                str(root / "aios" / "shell" / "components" / "remote-governance" / "panel.py"),
            )
        ),
        agentd_socket=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_AGENTD_SOCKET",
                os.environ.get("AIOS_COMPAT_AGENTD_SOCKET", "/run/aios/agentd/agentd.sock"),
            )
        ),
        remote_registration_request=(
            Path(value)
            if (
                value := os.environ.get("AIOS_SHELL_PROVIDER_REMOTE_REGISTRATION_REQUEST")
                or os.environ.get("AIOS_REMOTE_REGISTRATION_REQUEST")
            )
            else None
        ),
        recovery_surface=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_RECOVERY_SURFACE",
                "/var/lib/aios/updated/recovery-surface.json",
            )
        ),
        updated_socket=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_UPDATED_SOCKET",
                "/run/aios/updated/updated.sock",
            )
        ),
        indicator_state=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_INDICATOR_STATE",
                "/var/lib/aios/deviced/indicator-state.json",
            )
        ),
        backend_state=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_BACKEND_STATE",
                "/var/lib/aios/deviced/backend-state.json",
            )
        ),
        deviced_socket=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_DEVICED_SOCKET",
                "/run/aios/deviced/deviced.sock",
            )
        ),
        panel_action_log=(
            Path(value)
            if (
                value := os.environ.get("AIOS_SHELL_PROVIDER_PANEL_ACTION_LOG")
                or os.environ.get("AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH")
            )
            else None
        ),
        approval_fixture=(
            Path(value)
            if (value := os.environ.get("AIOS_SHELL_PROVIDER_APPROVAL_FIXTURE"))
            else None
        ),
        policy_audit_log=Path(
            os.environ.get("AIOS_SHELL_PROVIDER_POLICY_AUDIT_LOG", "/var/lib/aios/policyd/audit.jsonl")
        ),
        runtime_events_log=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_RUNTIME_EVENTS_LOG",
                "/var/lib/aios/runtimed/runtime-events.jsonl",
            )
        ),
        remote_audit_log=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_REMOTE_AUDIT_LOG",
                "/var/lib/aios/runtimed/remote-audit.jsonl",
            )
        ),
        compat_observability_log=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_COMPAT_OBSERVABILITY_LOG",
                "/var/lib/aios/compat/compat-observability.jsonl",
            )
        ),
        browser_remote_registry=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_BROWSER_REMOTE_REGISTRY",
                os.environ.get(
                    "AIOS_BROWSER_REMOTE_REGISTRY",
                    str(Path.home() / ".local" / "state" / "aios" / "compat-browser" / "remote-registry.json"),
                ),
            )
        ),
        office_remote_registry=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_OFFICE_REMOTE_REGISTRY",
                os.environ.get(
                    "AIOS_OFFICE_REMOTE_REGISTRY",
                    str(Path.home() / ".local" / "state" / "aios" / "compat-office" / "remote-registry.json"),
                ),
            )
        ),
        mcp_remote_registry=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_MCP_REMOTE_REGISTRY",
                os.environ.get(
                    "AIOS_MCP_BRIDGE_REMOTE_REGISTRY",
                    str(Path.home() / ".local" / "state" / "aios" / "compat-mcp-bridge" / "remote-registry.json"),
                ),
            )
        ),
        provider_registry_state_dir=Path(
            os.environ.get(
                "AIOS_SHELL_PROVIDER_PROVIDER_REGISTRY_STATE_DIR",
                os.environ.get(
                    "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR",
                    "/var/lib/aios/registry",
                ),
            )
        ),
    )


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response["result"]


def verify_token(config: Config, token: dict, capability_id: str) -> None:
    if token.get("capability_id") != capability_id:
        raise RuntimeError(f"execution token capability mismatch: expected {capability_id}")
    if token.get("execution_location") != "local":
        raise RuntimeError("shell control provider requires local execution tokens")

    verification = rpc_call(
        config.policyd_socket,
        POLICY_TOKEN_VERIFY,
        {"token": token},
    )
    if not verification.get("valid"):
        raise RuntimeError(f"execution token rejected: {verification.get('reason')}")


def health(config: Config) -> dict:
    return {
        "service_id": config.service_id,
        "status": "ready",
        "version": config.version,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "socket_path": str(config.socket_path),
        "notes": [
            f"provider_id={config.provider_id}",
            f"focus_state={config.focus_state_path}",
            f"notification_panel={config.notification_panel}",
            f"operator_audit_panel={config.operator_audit_panel}",
            f"remote_governance_panel={config.remote_governance_panel}",
            f"remote_registration_request={config.remote_registration_request}"
            if config.remote_registration_request is not None
            else "remote_registration_request=disabled",
            f"panel_action_log={config.panel_action_log}" if config.panel_action_log else "panel_action_log=disabled",
        ],
    }


def handle_focus(config: Config, params: dict) -> dict:
    token = params.get("execution_token") or {}
    verify_token(config, token, SHELL_WINDOW_FOCUS)

    focused_at = datetime.now(timezone.utc).isoformat()
    record = {
        "provider_id": config.provider_id,
        "status": "focused",
        "focused_target": params.get("target", "window://active"),
        "focused_at": focused_at,
        "state_path": str(config.focus_state_path),
        "notes": [
            f"session_id={token.get('session_id')}",
            f"task_id={token.get('task_id')}",
        ],
    }
    config.focus_state_path.parent.mkdir(parents=True, exist_ok=True)
    config.focus_state_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record


def notification_panel_command(config: Config) -> list[str]:
    command = [
        sys.executable,
        str(config.notification_panel),
        "model",
        "--json",
        "--recovery-surface",
        str(config.recovery_surface),
        "--updated-socket",
        str(config.updated_socket),
        "--indicator-state",
        str(config.indicator_state),
        "--backend-state",
        str(config.backend_state),
        "--deviced-socket",
        str(config.deviced_socket),
        "--policy-socket",
        str(config.policyd_socket),
    ]
    if config.panel_action_log is not None:
        command.extend(["--panel-action-log", str(config.panel_action_log)])
    if config.approval_fixture is not None:
        command.extend(["--approval-fixture", str(config.approval_fixture)])
    command.extend(["--policy-audit-log", str(config.policy_audit_log)])
    command.extend(["--runtime-events-log", str(config.runtime_events_log)])
    command.extend(["--remote-audit-log", str(config.remote_audit_log)])
    command.extend(["--compat-observability-log", str(config.compat_observability_log)])
    command.extend(["--browser-remote-registry", str(config.browser_remote_registry)])
    command.extend(["--office-remote-registry", str(config.office_remote_registry)])
    command.extend(["--mcp-remote-registry", str(config.mcp_remote_registry)])
    command.extend(["--provider-registry-state-dir", str(config.provider_registry_state_dir)])
    return command


def handle_notification_open(config: Config, params: dict) -> dict:
    token = params.get("execution_token") or {}
    verify_token(config, token, SHELL_NOTIFICATION_OPEN)

    completed = subprocess.run(
        notification_panel_command(config),
        check=True,
        text=True,
        capture_output=True,
    )
    model = json.loads(completed.stdout.strip() or "{}")
    notification_count = int(model.get("meta", {}).get("notification_count", 0))
    response = {
        "provider_id": config.provider_id,
        "status": "opened",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "notification_count": notification_count,
        "model": model if params.get("include_model", False) else None,
        "notes": [
            f"session_id={token.get('session_id')}",
            f"source={params.get('source') or 'provider-call'}",
        ],
    }
    return response


def operator_audit_panel_command(
    config: Config,
    *,
    params: dict,
) -> list[str]:
    issue_only = bool(params.get("issue_only", False))
    limit = panel_event_limit(params.get("limit"), default=10, maximum=32)
    command = [
        sys.executable,
        str(config.operator_audit_panel),
        "model",
        "--policy-audit-log",
        str(config.policy_audit_log),
        "--runtime-events-log",
        str(config.runtime_events_log),
        "--remote-audit-log",
        str(config.remote_audit_log),
        "--compat-observability-log",
        str(config.compat_observability_log),
        "--browser-remote-registry",
        str(config.browser_remote_registry),
        "--office-remote-registry",
        str(config.office_remote_registry),
        "--mcp-remote-registry",
        str(config.mcp_remote_registry),
        "--provider-registry-state-dir",
        str(config.provider_registry_state_dir),
        "--limit",
        str(limit),
    ]
    for flag, value in (
        ("--source", params.get("query_source")),
        ("--severity", params.get("severity")),
        ("--provider-id", params.get("provider_id")),
        ("--provider-ref", params.get("provider_ref")),
        ("--capability-id", params.get("capability_id")),
        ("--decision", params.get("decision")),
        ("--status", params.get("status")),
        ("--session-id", params.get("session_id")),
        ("--task-id", params.get("task_id")),
        ("--approval-id", params.get("approval_id")),
        ("--approval-ref", params.get("approval_ref")),
        ("--audit-id", params.get("audit_id")),
        ("--error-code", params.get("error_code")),
        ("--text", params.get("text")),
        ("--since", params.get("since")),
        ("--until", params.get("until")),
        ("--fleet-id", params.get("fleet_id")),
        ("--governance-group", params.get("governance_group")),
        ("--attestation-mode", params.get("attestation_mode")),
        ("--control-plane-status", params.get("control_plane_status")),
        ("--write-report", params.get("report_path")),
    ):
        if value not in (None, ""):
            command.extend([flag, str(value)])
    if issue_only:
        command.append("--issue-only")
    return command


def handle_operator_audit_open(config: Config, params: dict) -> dict:
    token = params.get("execution_token") or {}
    verify_token(config, token, SHELL_OPERATOR_AUDIT_OPEN)

    issue_only = bool(params.get("issue_only", False))
    limit = panel_event_limit(params.get("limit"), default=10, maximum=32)
    completed = subprocess.run(
        operator_audit_panel_command(config, params=params),
        check=True,
        text=True,
        capture_output=True,
    )
    model = json.loads(completed.stdout.strip() or "{}")
    response = {
        "provider_id": config.provider_id,
        "status": "opened",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "issue_count": int((model.get("meta") or {}).get("issue_count", 0)),
        "record_count": int((model.get("meta") or {}).get("record_count", 0)),
        "matched_record_count": int((model.get("meta") or {}).get("matched_record_count", 0)),
        "task_count": int((model.get("meta") or {}).get("task_count", 0)),
        "remote_governance_issue_count": int((model.get("meta") or {}).get("remote_governance_issue_count", 0)),
        "remote_governance_matched_entry_count": int(
            (model.get("meta") or {}).get("remote_governance_matched_entry_count", 0)
        ),
        "issue_only": issue_only,
        "filters": (model.get("meta") or {}).get("filters", {}),
        "report_path": ((model.get("meta") or {}).get("query") or {}).get("report_path"),
        "model": model if params.get("include_model", False) else None,
        "notes": [
            f"session_id={token.get('session_id')}",
            f"source={params.get('source') or 'provider-call'}",
        ],
    }
    return response


def remote_governance_panel_command(
    config: Config,
    *,
    params: dict,
) -> list[str]:
    issue_only = bool(params.get("issue_only", False))
    limit = panel_event_limit(params.get("limit"), default=10, maximum=32)
    command = [
        sys.executable,
        str(config.remote_governance_panel),
        "model",
        "--browser-remote-registry",
        str(config.browser_remote_registry),
        "--office-remote-registry",
        str(config.office_remote_registry),
        "--mcp-remote-registry",
        str(config.mcp_remote_registry),
        "--provider-registry-state-dir",
        str(config.provider_registry_state_dir),
        "--limit",
        str(limit),
        "--agent-socket",
        str(config.agentd_socket),
    ]
    if config.remote_registration_request is not None:
        command.extend(
            [
                "--remote-registration-request",
                str(config.remote_registration_request),
            ]
        )
    for flag, value in (
        ("--source", params.get("query_source")),
        ("--severity", params.get("severity")),
        ("--fleet-id", params.get("fleet_id")),
        ("--governance-group", params.get("governance_group")),
        ("--status", params.get("status")),
        ("--provider-ref", params.get("provider_ref")),
        ("--provider-id", params.get("provider_id")),
        ("--attestation-mode", params.get("attestation_mode")),
        ("--control-plane-status", params.get("control_plane_status")),
        ("--approval-ref", params.get("approval_ref")),
        ("--text", params.get("text")),
        ("--write-report", params.get("report_path")),
    ):
        if value not in (None, ""):
            command.extend([flag, str(value)])
    if issue_only:
        command.append("--issue-only")
    return command


def handle_remote_governance_open(config: Config, params: dict) -> dict:
    token = params.get("execution_token") or {}
    verify_token(config, token, SHELL_REMOTE_GOVERNANCE_OPEN)

    issue_only = bool(params.get("issue_only", False))
    completed = subprocess.run(
        remote_governance_panel_command(config, params=params),
        check=True,
        text=True,
        capture_output=True,
    )
    model = json.loads(completed.stdout.strip() or "{}")
    meta = model.get("meta") or {}
    response = {
        "provider_id": config.provider_id,
        "status": "opened",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": int(meta.get("entry_count", 0)),
        "matched_entry_count": int(meta.get("matched_entry_count", 0)),
        "issue_count": int(meta.get("issue_count", 0)),
        "fleet_count": int(meta.get("fleet_count", 0)),
        "issue_only": issue_only,
        "filters": (meta.get("query") or {}).get("filters", {}),
        "report_path": (meta.get("query") or {}).get("report_path"),
        "model": model if params.get("include_model", False) else None,
        "notes": [
            f"session_id={token.get('session_id')}",
            f"source={params.get('source') or 'provider-call'}",
        ],
    }
    return response


def panel_event_filters(params: dict) -> dict[str, str]:
    filters: dict[str, str] = {}
    for key in ("kind", "component", "slot_id", "panel_id", "action_id", "status_filter"):
        value = params.get(key)
        if value not in (None, ""):
            filters[key] = str(value)
    return filters


def panel_event_limit(value: object, *, default: int = 8, maximum: int = 32) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return default
    if limit < 1:
        return default
    return min(limit, maximum)


def panel_event_matches(entry: dict, filters: dict[str, str]) -> bool:
    if "kind" in filters and entry.get("kind") != filters["kind"]:
        return False
    if "component" in filters and entry.get("component") != filters["component"]:
        return False
    if "slot_id" in filters and entry.get("slot_id") != filters["slot_id"]:
        return False
    if "panel_id" in filters and entry.get("panel_id") != filters["panel_id"]:
        return False
    if "action_id" in filters and entry.get("action_id") != filters["action_id"]:
        return False
    if "status_filter" in filters and entry.get("status") != filters["status_filter"]:
        return False
    return True


def handle_panel_events_list(config: Config, params: dict) -> dict:
    token = params.get("execution_token") or {}
    verify_token(config, token, SHELL_PANEL_EVENTS_LIST)

    filters = panel_event_filters(params)
    limit = panel_event_limit(params.get("limit"))
    include_payload = bool(params.get("include_payload", False))
    response_payload = {
        "provider_id": config.provider_id,
        "status": "ready",
        "panel_action_log_path": str(config.panel_action_log) if config.panel_action_log else None,
        "entry_count": 0,
        "matched_entry_count": 0,
        "entries": [],
        "applied_filters": {
            **filters,
            "limit": limit,
            "include_payload": include_payload,
        },
        "notes": [
            f"session_id={token.get('session_id')}",
            "ordering=recent-first",
        ],
    }

    if config.panel_action_log is None:
        response_payload["status"] = "disabled"
        response_payload["notes"].append("panel_action_log=disabled")
        return response_payload

    if not config.panel_action_log.exists():
        response_payload["status"] = "missing"
        response_payload["notes"].append("panel_action_log=missing")
        return response_payload

    try:
        lines = config.panel_action_log.read_text().splitlines()
    except OSError as exc:
        raise RuntimeError(f"failed to read panel action log: {exc}") from exc

    ignored_entries = 0
    entries: list[dict] = []
    matched_entry_count = 0
    for raw_line in reversed(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            ignored_entries += 1
            continue
        if not isinstance(value, dict):
            ignored_entries += 1
            continue
        if not panel_event_matches(value, filters):
            continue
        matched_entry_count += 1
        if len(entries) >= limit:
            continue
        entry = dict(value)
        if not include_payload:
            entry["payload"] = None
        entries.append(entry)

    response_payload["entry_count"] = len(entries)
    response_payload["matched_entry_count"] = matched_entry_count
    response_payload["entries"] = entries
    if ignored_entries:
        response_payload["notes"].append(f"ignored_entries={ignored_entries}")
    return response_payload


def response(result: dict | None = None, error: str | None = None, request_id: int | str | None = 1) -> bytes:
    if error is not None:
        payload = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": error}}
    else:
        payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


def serve(config: Config) -> int:
    if config.socket_path.exists():
        config.socket_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(config.socket_path))
    server.listen()

    stop = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not stop:
        try:
            server.settimeout(0.5)
            conn, _ = server.accept()
        except socket.timeout:
            continue

        with conn:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            if not data:
                continue

            request = json.loads(data.decode("utf-8"))
            method = request.get("method")
            params = request.get("params") or {}
            request_id = request.get("id")

            try:
                if method == SYSTEM_HEALTH_GET:
                    conn.sendall(response(health(config), request_id=request_id))
                elif method == SHELL_WINDOW_FOCUS:
                    conn.sendall(response(handle_focus(config, params), request_id=request_id))
                elif method == SHELL_NOTIFICATION_OPEN:
                    conn.sendall(response(handle_notification_open(config, params), request_id=request_id))
                elif method == SHELL_OPERATOR_AUDIT_OPEN:
                    conn.sendall(response(handle_operator_audit_open(config, params), request_id=request_id))
                elif method == SHELL_REMOTE_GOVERNANCE_OPEN:
                    conn.sendall(response(handle_remote_governance_open(config, params), request_id=request_id))
                elif method == SHELL_PANEL_EVENTS_LIST:
                    conn.sendall(response(handle_panel_events_list(config, params), request_id=request_id))
                else:
                    conn.sendall(response(error=f"unsupported method: {method}", request_id=request_id))
            except Exception as exc:  # noqa: BLE001
                conn.sendall(response(error=str(exc), request_id=request_id))

    server.close()
    if config.socket_path.exists():
        config.socket_path.unlink()
    return 0


def main() -> int:
    return serve(load_config())


if __name__ == "__main__":
    raise SystemExit(main())
