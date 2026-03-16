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


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS shell control clients live smoke")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing sessiond/policyd binaries")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--provider", type=Path, help="Path to shell control provider script")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--keep-state", action="store_true")
    return parser.parse_args()


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(ROOT), name)


def resolve_provider(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return ROOT / "aios" / "shell" / "runtime" / "shell_control_provider.py"


def ensure_binaries(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing binaries for shell control clients live smoke:")
        for item in missing:
            print(f"  - {item}")
        print("Build them first, for example: cargo build -p aios-sessiond -p aios-policyd")
        raise SystemExit(2)

def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
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
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def wait_for_socket(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def make_env(root: Path) -> dict[str, str]:
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_SESSIOND_RUNTIME_DIR": str(runtime_root / "sessiond"),
            "AIOS_SESSIOND_STATE_DIR": str(state_root / "sessiond"),
            "AIOS_SESSIOND_SOCKET_PATH": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_SESSIOND_DATABASE": str(state_root / "sessiond" / "sessiond.sqlite3"),
            "AIOS_SESSIOND_PORTAL_STATE_DIR": str(state_root / "sessiond" / "portal"),
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(ROOT / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(ROOT / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
        }
    )
    return env


def launch(command: list[str] | Path, env: dict[str, str]) -> subprocess.Popen:
    argv = [str(command)] if isinstance(command, Path) else [str(item) for item in command]
    return subprocess.Popen(
        argv,
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


def run_python(script: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    return completed.stdout.strip()


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("shell control clients live smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "sessiond": resolve_binary("sessiond", args.sessiond, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "provider": resolve_provider(args.provider),
    }
    ensure_binaries(binaries)

    temp_root = Path(tempfile.mkdtemp(prefix="ascl-", dir="/tmp"))
    env = make_env(temp_root)
    failed = False
    shell_profile = temp_root / "shell-profile.yaml"
    provider_focus_state = temp_root / "state" / "shell-provider" / "focus-state.json"
    recovery_surface = temp_root / "state" / "updated" / "recovery-surface.json"
    indicator_state = temp_root / "state" / "deviced" / "indicator-state.json"
    backend_state = temp_root / "state" / "deviced" / "backend-state.json"
    panel_action_log = temp_root / "state" / "shell-provider" / "panel-action-events.jsonl"

    recovery_surface.parent.mkdir(parents=True, exist_ok=True)
    indicator_state.parent.mkdir(parents=True, exist_ok=True)
    backend_state.parent.mkdir(parents=True, exist_ok=True)
    panel_action_log.parent.mkdir(parents=True, exist_ok=True)

    recovery_surface.write_text(
        json.dumps(
            {
                "service_id": "aios-updated",
                "overall_status": "degraded",
                "deployment_status": "apply-triggered",
                "rollback_ready": True,
                "available_actions": ["check-updates", "rollback"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    indicator_state.write_text(
        json.dumps(
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
            indent=2,
            ensure_ascii=False,
        )
    )
    backend_state.write_text(
        json.dumps(
            {
                "updated_at": "2026-03-09T00:00:00Z",
                "statuses": [
                    {
                        "modality": "screen",
                        "backend": "screen-capture-portal",
                        "available": True,
                        "readiness": "native-live",
                        "details": [],
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
            },
            indent=2,
            ensure_ascii=False,
        )
    )
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

    processes = {
        "sessiond": launch(binaries["sessiond"], env),
        "policyd": launch(binaries["policyd"], env),
    }

    try:
        sessiond_socket = Path(env["AIOS_SESSIOND_SOCKET_PATH"])
        policyd_socket = Path(env["AIOS_POLICYD_SOCKET_PATH"])
        shell_profile.write_text(
            json.dumps(
                {
                    "profile_id": "shell-control-live",
                    "components": {
                        "launcher": True,
                        "task_surface": True,
                        "approval_panel": True,
                    },
                    "paths": {
                        "sessiond_socket": str(sessiond_socket),
                        "policyd_socket": str(policyd_socket),
                        "shell_control_provider_socket": str(
                            temp_root / "run" / "shell-provider" / "shell-provider.sock"
                        ),
                        "recovery_surface_model": str(recovery_surface),
                        "capture_indicator_state": str(indicator_state),
                        "device_backend_state": str(backend_state),
                        "panel_action_log_path": str(panel_action_log),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        wait_for_socket(sessiond_socket, args.timeout)
        wait_for_socket(policyd_socket, args.timeout)
        wait_for_health(sessiond_socket, args.timeout)
        wait_for_health(policyd_socket, args.timeout)

        provider_env = os.environ.copy()
        provider_env.update(
            env
        )
        provider_env.update(
            {
                "AIOS_SHELL_PROVIDER_RUNTIME_DIR": str(temp_root / "run" / "shell-provider"),
                "AIOS_SHELL_PROVIDER_STATE_DIR": str(temp_root / "state" / "shell-provider"),
                "AIOS_SHELL_PROVIDER_SOCKET_PATH": str(
                    temp_root / "run" / "shell-provider" / "shell-provider.sock"
                ),
                "AIOS_SHELL_PROVIDER_POLICYD_SOCKET": str(policyd_socket),
                "AIOS_SHELL_PROVIDER_FOCUS_STATE_PATH": str(provider_focus_state),
                "AIOS_SHELL_PROVIDER_RECOVERY_SURFACE": str(recovery_surface),
                "AIOS_SHELL_PROVIDER_INDICATOR_STATE": str(indicator_state),
                "AIOS_SHELL_PROVIDER_BACKEND_STATE": str(backend_state),
                "AIOS_SHELL_PROVIDER_PANEL_ACTION_LOG": str(panel_action_log),
                "AIOS_SHELL_PROVIDER_UPDATED_SOCKET": str(temp_root / "run" / "updated" / "updated.sock"),
                "AIOS_SHELL_PROVIDER_DEVICED_SOCKET": str(temp_root / "run" / "deviced" / "deviced.sock"),
            }
        )
        processes["provider"] = launch([sys.executable, str(binaries["provider"])], provider_env)
        provider_socket = Path(provider_env["AIOS_SHELL_PROVIDER_SOCKET_PATH"])
        wait_for_socket(provider_socket, args.timeout)
        wait_for_health(provider_socket, args.timeout)

        launcher_env = os.environ.copy()
        launcher_env.update(env)

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "component",
            "launcher",
            "create-session",
            "--user-id",
            "shell-live-user",
            "--intent",
            "open docs",
            env=launcher_env,
        )
        launch_result = json.loads(output)
        session_id = launch_result["session"]["session_id"]
        task_id = launch_result["task"]["task_id"]
        require(bool(session_id), "launcher live session id mismatch")
        require(bool(task_id), "launcher live task id mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "launcher",
            "model",
            "--session-id",
            session_id,
            "--user-id",
            "shell-live-user",
            "--intent",
            "open docs",
            env=launcher_env,
        )
        launcher_panel = json.loads(output)
        require(launcher_panel["panel_id"] == "launcher-panel", "launcher panel live mismatch")
        require(launcher_panel["meta"]["task_count"] >= 1, "launcher panel live task count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "launcher",
            "model",
            "--user-id",
            "shell-live-user",
            "--intent",
            "open docs",
            env=launcher_env,
        )
        launcher_recent_panel = json.loads(output)
        require(
            launcher_recent_panel["meta"]["resolved_session_id"] == session_id,
            "launcher live recent-session fallback mismatch",
        )
        require(
            launcher_recent_panel["meta"]["recent_session_count"] >= 1,
            "launcher live recent-session count mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "component",
            "task-surface",
            "summary",
            "--session-id",
            session_id,
            env=launcher_env,
        )
        require("total: 1" in output, "task client live summary total mismatch")
        require('"planned": 1' in output, "task client live summary state mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "task-surface",
            "model",
            "--session-id",
            session_id,
            "--task-id",
            task_id,
            env=launcher_env,
        )
        task_panel = json.loads(output)
        require(task_panel["panel_id"] == "task-panel", "task panel live mismatch")
        require(task_panel["meta"]["task_count"] >= 1, "task panel live task count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "component",
            "task-surface",
            "update",
            "--task-id",
            task_id,
            "--state",
            "approved",
            "--reason",
            "shell-live",
            env=launcher_env,
        )
        require("state: approved" in output, "task client live update mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "component",
            "approval-panel",
            "create",
            "--user-id",
            "shell-live-user",
            "--session-id",
            session_id,
            "--task-id",
            task_id,
            "--capability-id",
            "device.capture.audio",
            "--approval-lane",
            "high-risk",
            "--reason",
            "microphone request",
            env=launcher_env,
        )
        require("approval_ref:" in output, "approval client live create missing approval ref")

        approvals = rpc_call(agentd_socket, "agent.approval.list", {"session_id": session_id}, timeout=args.timeout)
        require(len(approvals["approvals"]) == 1, "approval list count mismatch after create")
        approval_ref = approvals["approvals"][0]["approval_ref"]

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "component",
            "approval-panel",
            "summary",
            "--session-id",
            session_id,
            env=launcher_env,
        )
        require("total: 1" in output, "approval client live summary total mismatch")
        require('"pending": 1' in output, "approval client live summary status mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "approval-panel",
            "model",
            "--session-id",
            session_id,
            env=launcher_env,
        )
        approval_panel = json.loads(output)
        require(approval_panel["panel_id"] == "approval-panel-shell", "approval panel live mismatch")
        require(approval_panel["meta"]["approval_count"] == 1, "approval panel live count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "control",
            "notification-open",
            "--user-id",
            "shell-live-user",
            "--session-id",
            session_id,
            "--task-id",
            "task-shell-provider-notify",
            "--source",
            "shellctl-live-smoke",
            "--include-model",
            env=launcher_env,
        )
        notification_result = json.loads(output)
        require(notification_result["status"] == "opened", "shellctl control notification-open mismatch")
        require(notification_result["notification_count"] >= 2, "shellctl control notification count mismatch")
        require(
            (notification_result.get("model") or {}).get("panel_id") == "notification-center-panel",
            "shellctl control notification panel mismatch",
        )
        require(
            ((notification_result.get("model") or {}).get("meta") or {}).get("source_summary", {}).get("shell") == 2,
            "shellctl control notification missing shell events",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "control",
            "panel-events",
            "--user-id",
            "shell-live-user",
            "--session-id",
            session_id,
            "--task-id",
            "task-shell-provider-events",
            "--component",
            "approval-panel",
            "--status-filter",
            "dispatch-failed(approve)",
            "--limit",
            "1",
            env=launcher_env,
        )
        panel_events_result = json.loads(output)
        require(panel_events_result["status"] == "ready", "shellctl control panel-events mismatch")
        require(panel_events_result["entry_count"] == 1, "shellctl control panel-events entry count mismatch")
        require(
            (panel_events_result.get("entries") or [{}])[0].get("event_id") == "panel-action-event-000002",
            "shellctl control panel-events event mismatch",
        )
        require(
            (panel_events_result.get("entries") or [{}])[0].get("payload") is None,
            "shellctl control panel-events should redact payload by default",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "control",
            "window-focus",
            "--user-id",
            "shell-live-user",
            "--session-id",
            session_id,
            "--task-id",
            "task-shell-provider-focus",
            "--target",
            "window://review",
            "--reason",
            "shellctl-live-smoke",
            env=launcher_env,
        )
        focus_result = json.loads(output)
        require(focus_result["status"] == "focused", "shellctl control window-focus mismatch")
        require(
            focus_result["focused_target"] == "window://review",
            "shellctl control window-focus target mismatch",
        )
        require(provider_focus_state.exists(), "shellctl control window-focus state file missing")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "component",
            "approval-panel",
            "resolve",
            "--approval-ref",
            approval_ref,
            "--status",
            "approved",
            "--reason",
            "ok",
            env=launcher_env,
        )
        require("status: approved" in output, "approval client live resolve mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "component",
            "approval-panel",
            "list",
            "--session-id",
            session_id,
            env=launcher_env,
        )
        require("approved" in output and approval_ref in output, "approval client live list mismatch")

        print("shell control clients live smoke passed")
        return 0
    except Exception as error:  # noqa: BLE001
        failed = True
        print(f"shell control clients live smoke failed: {error}")
        return 1
    finally:
        terminate(list(processes.values()))
        print_logs(processes)
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

