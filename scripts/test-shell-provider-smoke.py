#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS shell control provider smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing policyd binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--provider", type=Path, help="Path to shell control provider script")
    parser.add_argument("--user-id", default="shell-provider-user", help="User id for smoke calls")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(repo_root()), name)


def resolve_provider(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return repo_root() / "aios" / "shell" / "runtime" / "shell_control_provider.py"


def ensure_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing files for shell provider smoke harness:")
        for item in missing:
            print(f"  - {item}")
        raise SystemExit(2)

def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
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
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def wait_for_socket(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.5)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def launch(command: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    deadline = time.time() + 5
    for process in processes:
        if process.poll() is not None:
            continue
        remaining = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def print_logs(processes: dict[str, subprocess.Popen]) -> None:
    for name, process in processes.items():
        output = ""
        if process.stdout and process.poll() is not None:
            output = process.stdout.read()
        if output.strip():
            print(f"\n--- {name} log ---")
            print(output.rstrip())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def issue_token(
    policyd_socket: Path,
    *,
    user_id: str,
    session_id: str,
    task_id: str,
    capability_id: str,
    timeout: float,
) -> dict:
    return rpc_call(
        policyd_socket,
        "policy.token.issue",
        {
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "execution_location": "local",
            "constraints": {},
        },
        timeout=timeout,
    )


def write_fixture(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def write_jsonl_record(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("shell provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "provider": resolve_provider(args.provider),
    }
    ensure_paths(binaries)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-provider-", dir="/tmp" if Path("/tmp").exists() else None))
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    recovery_surface = state_root / "updated" / "recovery-surface.json"
    indicator_state = state_root / "deviced" / "indicator-state.json"
    backend_state = state_root / "deviced" / "backend-state.json"
    backend_evidence_dir = state_root / "deviced" / "backend-evidence"
    approval_fixture = state_root / "policyd" / "approvals.json"
    focus_state = state_root / "shell-provider" / "focus-state.json"
    panel_action_log = state_root / "shell-provider" / "panel-action-events.jsonl"
    policy_audit_log = state_root / "shell-provider" / "operator-policy-audit.jsonl"
    runtime_events_log = state_root / "runtimed" / "runtime-events.jsonl"
    remote_audit_log = state_root / "runtimed" / "remote-audit.jsonl"
    compat_observability_log = state_root / "compat" / "compat-observability.jsonl"
    browser_remote_registry = state_root / "compat" / "browser-remote-registry.json"
    office_remote_registry = state_root / "compat" / "office-remote-registry.json"
    provider_registry_state_dir = state_root / "registry"

    backend_evidence_dir.mkdir(parents=True, exist_ok=True)
    screen_evidence = backend_evidence_dir / "screen-backend-evidence.json"
    write_fixture(
        screen_evidence,
        {
            "modality": "screen",
            "baseline": "os-native-backend",
            "execution_path": "native-live",
            "source": "provider-smoke",
            "release_grade_backend_id": "xdg-desktop-portal-screencast",
            "release_grade_backend_origin": "os-native",
            "release_grade_backend_stack": "portal+pipewire",
            "contract_kind": "release-grade-runtime-helper",
            "state_refs": ["/tmp/provider-screen-state.json"],
        },
    )

    write_fixture(
        recovery_surface,
        {
            "service_id": "aios-updated",
            "overall_status": "degraded",
            "deployment_status": "apply-triggered",
            "rollback_ready": True,
            "available_actions": ["check-updates", "rollback"],
        },
    )
    write_fixture(
        indicator_state,
        {
            "updated_at": "2026-03-09T00:00:00Z",
            "active": [
                {
                    "indicator_id": "indicator-1",
                    "capture_id": "cap-1",
                    "modality": "screen",
                    "message": "Screen capture active",
                    "continuous": False,
                    "started_at": "2026-03-09T00:00:00Z",
                    "approval_status": "approved",
                }
            ],
        },
    )
    write_fixture(
        backend_state,
        {
            "updated_at": "2026-03-09T00:00:00Z",
            "statuses": [
                {
                    "modality": "screen",
                    "backend": "screen-capture-portal",
                    "available": True,
                    "readiness": "native-live",
                    "details": [f"evidence_artifact={screen_evidence}"],
                }
            ],
            "adapters": [
                {
                    "modality": "screen",
                    "backend": "screen-capture-portal",
                    "adapter_id": "screen.portal-live",
                    "execution_path": "native-live",
                    "preview_object_kind": "screen_frame",
                    "notes": [],
                }
            ],
            "notes": [
                f"backend_evidence_dir={backend_evidence_dir}",
                "backend_evidence_artifact_count=1",
                f"backend_evidence_artifact[screen]={screen_evidence}",
            ],
        },
    )
    write_fixture(
        approval_fixture,
        {
            "approvals": [
                {
                    "approval_ref": "approval-1",
                    "user_id": args.user_id,
                    "session_id": "session-shell",
                    "task_id": "task-notify",
                    "capability_id": "device.capture.screen.read",
                    "approval_lane": "device-capture-review",
                    "status": "pending",
                    "execution_location": "local",
                    "created_at": "2026-03-09T00:00:00Z",
                    "reason": "screen share",
                }
            ]
        },
    )
    panel_action_log.parent.mkdir(parents=True, exist_ok=True)
    panel_action_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "sequence": 1,
                        "event_id": "panel-action-event-000001",
                        "kind": "panel-action.dispatch",
                        "recorded_at_ms": 1,
                        "tick": 1,
                        "slot_id": "notification-center",
                        "component": "notification-center",
                        "panel_id": "notification-center-panel",
                        "action_id": "refresh",
                        "input_kind": "pointer-button",
                        "focus_policy": "retain-client-focus",
                        "status": "dispatch-ok(refresh)",
                        "summary": "Refresh Feed: status=ready",
                        "error": None,
                        "payload": {"result": {"status": "ready"}},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "sequence": 2,
                        "event_id": "panel-action-event-000002",
                        "kind": "panel-action.dispatch",
                        "recorded_at_ms": 2,
                        "tick": 2,
                        "slot_id": "approval-panel",
                        "component": "approval-panel",
                        "panel_id": "approval-panel-shell",
                        "action_id": "approve",
                        "input_kind": "pointer-button",
                        "focus_policy": "shell-modal",
                        "status": "dispatch-failed(approve)",
                        "summary": "approval callback failed",
                        "error": "approval callback failed",
                        "payload": {"result": {"status": "failed"}},
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n"
    )
    write_jsonl_record(
        policy_audit_log,
        {
            "audit_id": "audit-1",
            "timestamp": "2026-03-09T00:00:00Z",
            "user_id": args.user_id,
            "session_id": "session-shell",
            "task_id": "task-audit-1",
            "capability_id": "compat.browser.navigate",
            "decision": "denied",
        },
    )
    write_jsonl_record(
        runtime_events_log,
        {
            "event_id": "runtime-1",
            "kind": "runtime.infer.timeout",
            "task_id": "task-audit-2",
            "backend_id": "remote-gpu",
        },
    )
    write_jsonl_record(
        remote_audit_log,
        {
            "audit_id": "remote-1",
            "status": "error",
            "provider_id": "compat.browser.remote.worker",
            "task_id": "task-audit-3",
        },
    )
    write_jsonl_record(
        compat_observability_log,
        {
            "audit_id": "compat-1",
            "decision": "allowed",
            "provider_id": "compat.office.document.local",
            "task_id": "task-audit-4",
            "result": {"error_code": "office_remote_pdf_missing"},
        },
    )
    write_fixture(
        browser_remote_registry,
        {
            "schema_version": "1.0.0",
            "entries": [
                {
                    "provider_ref": "browser.remote.worker",
                    "endpoint": "https://browser.remote.example/bridge",
                    "control_plane_provider_id": "compat.browser.remote.worker",
                    "registration_status": "active",
                    "last_heartbeat_at": "2026-03-09T00:05:00Z",
                    "heartbeat_ttl_seconds": 3600,
                    "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                    "governance": {"fleet_id": "fleet-browser", "governance_group": "operator-audit"}
                }
            ],
        },
    )
    write_fixture(
        office_remote_registry,
        {
            "schema_version": "1.0.0",
            "entries": [
                {
                    "provider_ref": "office.remote.worker",
                    "endpoint": "https://office.remote.example/bridge",
                    "control_plane_provider_id": "compat.office.remote.worker",
                    "registration_status": "active",
                    "last_heartbeat_at": "2020-01-01T00:00:00Z",
                    "heartbeat_ttl_seconds": 60,
                    "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                    "governance": {"fleet_id": "fleet-office", "governance_group": "operator-audit"}
                }
            ],
        },
    )
    write_fixture(
        provider_registry_state_dir / "descriptors" / "compat.browser.remote.worker.json",
        {
            "provider_id": "compat.browser.remote.worker",
            "display_name": "Browser Remote Worker",
            "kind": "compat-provider",
            "execution_location": "attested_remote",
            "remote_registration": {
                "source_provider_id": "compat.browser.automation.local",
                "provider_ref": "browser.remote.worker",
                "endpoint": "https://browser.remote.example/bridge",
                "registration_status": "active",
                "last_heartbeat_at": "2026-03-09T00:05:00Z",
                "heartbeat_ttl_seconds": 3600,
                "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                "governance": {"fleet_id": "fleet-browser", "governance_group": "operator-audit"}
            },
        },
    )
    write_fixture(
        provider_registry_state_dir / "health" / "compat.browser.remote.worker.json",
        {"provider_id": "compat.browser.remote.worker", "status": "available", "disabled": False},
    )
    write_fixture(
        provider_registry_state_dir / "descriptors" / "compat.office.remote.worker.json",
        {
            "provider_id": "compat.office.remote.worker",
            "display_name": "Office Remote Worker",
            "kind": "compat-provider",
            "execution_location": "attested_remote",
            "remote_registration": {
                "source_provider_id": "compat.office.document.local",
                "provider_ref": "office.remote.worker",
                "endpoint": "https://office.remote.example/bridge",
                "registration_status": "active",
                "last_heartbeat_at": "2026-03-09T00:00:00Z",
                "heartbeat_ttl_seconds": 3600,
                "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                "governance": {"fleet_id": "fleet-office", "governance_group": "operator-audit"}
            },
        },
    )
    write_fixture(
        provider_registry_state_dir / "health" / "compat.office.remote.worker.json",
        {"provider_id": "compat.office.remote.worker", "status": "unavailable", "disabled": False, "last_error": "bridge offline"},
    )

    policyd_env = os.environ.copy()
    policyd_env.update(
        {
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(repo_root() / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(repo_root() / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
        }
    )
    provider_env = os.environ.copy()
    provider_env.update(
        {
            "AIOS_SHELL_PROVIDER_RUNTIME_DIR": str(runtime_root / "shell-provider"),
            "AIOS_SHELL_PROVIDER_STATE_DIR": str(state_root / "shell-provider"),
            "AIOS_SHELL_PROVIDER_SOCKET_PATH": str(runtime_root / "shell-provider" / "shell-provider.sock"),
            "AIOS_SHELL_PROVIDER_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_SHELL_PROVIDER_FOCUS_STATE_PATH": str(focus_state),
            "AIOS_SHELL_PROVIDER_RECOVERY_SURFACE": str(recovery_surface),
            "AIOS_SHELL_PROVIDER_INDICATOR_STATE": str(indicator_state),
            "AIOS_SHELL_PROVIDER_BACKEND_STATE": str(backend_state),
            "AIOS_SHELL_PROVIDER_PANEL_ACTION_LOG": str(panel_action_log),
            "AIOS_SHELL_PROVIDER_APPROVAL_FIXTURE": str(approval_fixture),
            "AIOS_SHELL_PROVIDER_UPDATED_SOCKET": str(runtime_root / "updated" / "updated.sock"),
            "AIOS_SHELL_PROVIDER_DEVICED_SOCKET": str(runtime_root / "deviced" / "deviced.sock"),
            "AIOS_SHELL_PROVIDER_POLICY_AUDIT_LOG": str(policy_audit_log),
            "AIOS_SHELL_PROVIDER_RUNTIME_EVENTS_LOG": str(runtime_events_log),
            "AIOS_SHELL_PROVIDER_REMOTE_AUDIT_LOG": str(remote_audit_log),
            "AIOS_SHELL_PROVIDER_COMPAT_OBSERVABILITY_LOG": str(compat_observability_log),
            "AIOS_SHELL_PROVIDER_BROWSER_REMOTE_REGISTRY": str(browser_remote_registry),
            "AIOS_SHELL_PROVIDER_OFFICE_REMOTE_REGISTRY": str(office_remote_registry),
            "AIOS_SHELL_PROVIDER_PROVIDER_REGISTRY_STATE_DIR": str(provider_registry_state_dir),
        }
    )

    sockets = {
        "policyd": Path(policyd_env["AIOS_POLICYD_SOCKET_PATH"]),
        "provider": Path(provider_env["AIOS_SHELL_PROVIDER_SOCKET_PATH"]),
    }
    processes: dict[str, subprocess.Popen] = {}
    failed = False

    try:
        processes["policyd"] = launch([str(binaries["policyd"])], policyd_env)
        wait_for_socket(sockets["policyd"], args.timeout)
        wait_for_health(sockets["policyd"], args.timeout)

        processes["provider"] = launch([sys.executable, str(binaries["provider"])], provider_env)
        wait_for_socket(sockets["provider"], args.timeout)
        provider_health = wait_for_health(sockets["provider"], args.timeout)
        require(provider_health.get("service_id") == "aios-shell-control-provider", "unexpected shell provider health payload")

        notification_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id="session-shell",
            task_id="task-notify",
            capability_id="shell.notification.open",
            timeout=args.timeout,
        )
        notification_result = rpc_call(
            sockets["provider"],
            "shell.notification.open",
            {
                "execution_token": notification_token,
                "include_model": True,
                "source": "shell-provider-smoke",
            },
            timeout=args.timeout,
        )
        require(notification_result.get("status") == "opened", "shell.notification.open did not succeed")
        require(notification_result.get("notification_count", 0) >= 2, "shell.notification.open did not build notification model")
        require((notification_result.get("model") or {}).get("panel_id") == "notification-center-panel", "shell.notification.open returned an unexpected panel model")
        require(
            ((notification_result.get("model") or {}).get("meta") or {}).get("source_summary", {}).get("shell") == 2,
            "shell.notification.open did not include shell panel action events",
        )
        require(
            ((notification_result.get("model") or {}).get("meta") or {}).get("backend_evidence_present_count") == 1,
            "shell.notification.open did not include backend evidence summary",
        )
        require(
            "xdg-desktop-portal-screencast" in (((notification_result.get("model") or {}).get("meta") or {}).get("backend_evidence_backend_ids") or []),
            "shell.notification.open did not expose release-grade backend ids",
        )
        require(
            ((notification_result.get("model") or {}).get("meta") or {}).get("remote_governance_issue_count", 0) >= 2,
            "shell.notification.open did not include remote governance summary",
        )
        require(
            "panel_action_log=" in "\n".join(provider_health.get("notes", [])),
            "shell provider health missing panel action log note",
        )

        operator_audit_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id="session-shell",
            task_id="task-operator-audit",
            capability_id="shell.operator-audit.open",
            timeout=args.timeout,
        )
        operator_audit_result = rpc_call(
            sockets["provider"],
            "shell.operator-audit.open",
            {
                "execution_token": operator_audit_token,
                "include_model": True,
                "issue_only": True,
                "limit": 8,
                "source": "shell-provider-smoke",
                "provider_id": "compat.office.document.local",
                "task_id": "task-audit-4",
                "report_path": str(state_root / "shell-provider" / "operator-audit-report.json"),
            },
            timeout=args.timeout,
        )
        require(operator_audit_result.get("status") == "opened", "shell.operator-audit.open did not succeed")
        require(operator_audit_result.get("issue_count") == 1, "shell.operator-audit.open issue count mismatch")
        require(operator_audit_result.get("record_count") == 6, "shell.operator-audit.open record count mismatch")
        require(
            operator_audit_result.get("matched_record_count") == 1,
            "shell.operator-audit.open matched record count mismatch",
        )
        require(
            (operator_audit_result.get("filters") or {}).get("provider_id") == "compat.office.document.local",
            "shell.operator-audit.open provider filter mismatch",
        )
        require(
            operator_audit_result.get("report_path") == str(state_root / "shell-provider" / "operator-audit-report.json"),
            "shell.operator-audit.open report path mismatch",
        )
        require(
            (operator_audit_result.get("model") or {}).get("panel_id") == "operator-audit-panel",
            "shell.operator-audit.open returned an unexpected panel model",
        )
        require(
            ((operator_audit_result.get("model") or {}).get("meta") or {}).get("task_count") == 1,
            "shell.operator-audit.open filtered task count mismatch",
        )

        operator_audit_governance_report = state_root / "shell-provider" / "operator-audit-governance-report.json"
        operator_audit_governance_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id="session-shell",
            task_id="task-operator-audit-governance",
            capability_id="shell.operator-audit.open",
            timeout=args.timeout,
        )
        operator_audit_governance_result = rpc_call(
            sockets["provider"],
            "shell.operator-audit.open",
            {
                "execution_token": operator_audit_governance_token,
                "include_model": True,
                "issue_only": True,
                "limit": 8,
                "source": "shell-provider-smoke",
                "fleet_id": "fleet-office",
                "report_path": str(operator_audit_governance_report),
            },
            timeout=args.timeout,
        )
        require(
            operator_audit_governance_result.get("status") == "opened",
            "shell.operator-audit.open governance query did not succeed",
        )
        require(
            operator_audit_governance_result.get("matched_record_count") == 1,
            "shell.operator-audit.open governance matched record count mismatch",
        )
        require(
            operator_audit_governance_result.get("remote_governance_issue_count", 0) >= 2,
            "shell.operator-audit.open governance issue count mismatch",
        )
        require(
            (operator_audit_governance_result.get("filters") or {}).get("fleet_id") == "fleet-office",
            "shell.operator-audit.open governance fleet filter mismatch",
        )
        require(
            operator_audit_governance_result.get("report_path") == str(operator_audit_governance_report),
            "shell.operator-audit.open governance report path mismatch",
        )
        require(operator_audit_governance_report.exists(), "shell.operator-audit.open governance report missing")
        require(
            ((operator_audit_governance_result.get("model") or {}).get("meta") or {}).get(
                "remote_governance_matched_entry_count"
            )
            == 1,
            "shell.operator-audit.open governance model matched entry count mismatch",
        )

        remote_governance_report = state_root / "shell-provider" / "remote-governance-report.json"
        remote_governance_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id="session-shell",
            task_id="task-remote-governance",
            capability_id="shell.remote-governance.open",
            timeout=args.timeout,
        )
        remote_governance_result = rpc_call(
            sockets["provider"],
            "shell.remote-governance.open",
            {
                "execution_token": remote_governance_token,
                "include_model": True,
                "issue_only": True,
                "limit": 8,
                "source": "shell-provider-smoke",
                "fleet_id": "fleet-office",
                "report_path": str(remote_governance_report),
            },
            timeout=args.timeout,
        )
        require(remote_governance_result.get("status") == "opened", "shell.remote-governance.open did not succeed")
        require(remote_governance_result.get("entry_count") == 2, "shell.remote-governance.open entry count mismatch")
        require(
            remote_governance_result.get("matched_entry_count") == 1,
            "shell.remote-governance.open matched entry count mismatch",
        )
        require(remote_governance_result.get("issue_count", 0) >= 2, "shell.remote-governance.open issue count mismatch")
        require(remote_governance_result.get("fleet_count") == 1, "shell.remote-governance.open fleet count mismatch")
        require(remote_governance_result.get("issue_only") is True, "shell.remote-governance.open issue_only mismatch")
        require(
            (remote_governance_result.get("filters") or {}).get("fleet_id") == "fleet-office",
            "shell.remote-governance.open fleet filter mismatch",
        )
        require(
            remote_governance_result.get("report_path") == str(remote_governance_report),
            "shell.remote-governance.open report path mismatch",
        )
        require(remote_governance_report.exists(), "shell.remote-governance.open did not write report")
        require(
            (remote_governance_result.get("model") or {}).get("panel_id") == "remote-governance-panel",
            "shell.remote-governance.open returned an unexpected panel model",
        )
        require(
            ((remote_governance_result.get("model") or {}).get("meta") or {}).get("matched_entry_count") == 1,
            "shell.remote-governance.open model matched entry count mismatch",
        )

        panel_events_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id="session-shell",
            task_id="task-panel-events",
            capability_id="shell.panel-events.list",
            timeout=args.timeout,
        )
        panel_events_result = rpc_call(
            sockets["provider"],
            "shell.panel-events.list",
            {
                "execution_token": panel_events_token,
                "limit": 1,
                "component": "approval-panel",
                "status_filter": "dispatch-failed(approve)",
                "include_payload": False,
            },
            timeout=args.timeout,
        )
        require(panel_events_result.get("status") == "ready", "shell.panel-events.list did not succeed")
        require(panel_events_result.get("entry_count") == 1, "shell.panel-events.list did not apply limit/filter")
        require(
            panel_events_result.get("matched_entry_count") == 1,
            "shell.panel-events.list matched entry count mismatch",
        )
        panel_event_entries = panel_events_result.get("entries") or []
        require(len(panel_event_entries) == 1, "shell.panel-events.list returned unexpected entries")
        require(
            panel_event_entries[0].get("component") == "approval-panel",
            "shell.panel-events.list did not preserve component filter",
        )
        require(
            panel_event_entries[0].get("payload") is None,
            "shell.panel-events.list should redact payload unless requested",
        )

        focus_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id="session-shell",
            task_id="task-focus",
            capability_id="shell.window.focus",
            timeout=args.timeout,
        )
        focus_result = rpc_call(
            sockets["provider"],
            "shell.window.focus",
            {
                "execution_token": focus_token,
                "target": "window://review",
                "reason": "smoke-focus",
            },
            timeout=args.timeout,
        )
        require(focus_result.get("status") == "focused", "shell.window.focus did not succeed")
        require(focus_result.get("focused_target") == "window://review", "shell.window.focus did not preserve focus target")
        require(focus_state.exists(), "shell.window.focus did not persist focus state")
        persisted_focus = json.loads(focus_state.read_text())
        require(persisted_focus.get("focused_target") == "window://review", "persisted focus state target mismatch")

        print("\nShell provider smoke result summary:")
        print(
            json.dumps(
                {
                    "provider_id": provider_health["notes"][0].split("=", 1)[1],
                    "notification_count": notification_result.get("notification_count"),
                    "notification_panel_id": (notification_result.get("model") or {}).get("panel_id"),
                    "operator_audit_issue_count": operator_audit_result.get("issue_count"),
                    "operator_audit_panel_id": (operator_audit_result.get("model") or {}).get("panel_id"),
                    "remote_governance_issue_count": remote_governance_result.get("issue_count"),
                    "remote_governance_panel_id": (remote_governance_result.get("model") or {}).get("panel_id"),
                    "remote_governance_report_path": str(remote_governance_report),
                    "panel_event_status": panel_events_result.get("status"),
                    "panel_event_id": panel_event_entries[0].get("event_id"),
                    "focus_target": focus_result.get("focused_target"),
                    "focus_state_path": str(focus_state),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"shell provider smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        terminate(list(processes.values()))
        if failed:
            print_logs(processes)
        if args.keep_state:
            print(f"Preserved shell provider smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())


