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
    parser = argparse.ArgumentParser(
        description="AIOS shell session/policy/registry flow smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing compiled binaries")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--keep-state", action="store_true")
    return parser.parse_args()


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(ROOT), name)


def ensure_binary(path: Path, package: str) -> None:
    if path.exists():
        return
    print(f"Missing binary: {path}")
    print(f"Build it first, for example: cargo build -p {package}")
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
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.5)
        except Exception as error:  # noqa: BLE001
            last_error = error
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def run_python(script: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    return completed.stdout.strip()


def load_json_output(label: str, output: str) -> dict:
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        preview = output if output else "<empty>"
        raise RuntimeError(f"{label} did not return JSON: {preview}") from error


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
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


def make_env(root: Path) -> dict[str, str]:
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    provider_dirs = [
        ROOT / "aios" / "sdk" / "providers",
        ROOT / "aios" / "runtime" / "providers",
        ROOT / "aios" / "shell" / "providers",
        ROOT / "aios" / "compat" / "browser" / "providers",
        ROOT / "aios" / "compat" / "office" / "providers",
        ROOT / "aios" / "compat" / "mcp-bridge" / "providers",
        ROOT / "aios" / "compat" / "code-sandbox" / "providers",
    ]

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
            "AIOS_POLICYD_POLICY_PATH": str(
                ROOT / "aios" / "policy" / "profiles" / "default-policy.yaml"
            ),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(
                ROOT / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"
            ),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
            "AIOS_POLICYD_APPROVAL_TTL_SECONDS": "900",
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "agentd"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "agentd"),
            "AIOS_AGENTD_SOCKET_PATH": str(runtime_root / "agentd" / "agentd.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "registry"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": os.pathsep.join(
                str(path) for path in provider_dirs
            ),
        }
    )
    return env


def write_shell_profile(path: Path, env: dict[str, str]) -> None:
    path.write_text(
        json.dumps(
            {
                "profile_id": "shell-control-plane-live",
                "desktop_host": "tk",
                "session_backend": "standalone",
                "components": {
                    "launcher": True,
                    "task_surface": True,
                    "approval_panel": True,
                    "notification_center": False,
                    "recovery_surface": False,
                    "capture_indicators": False,
                    "portal_chooser": False,
                    "device_backend_status": False,
                },
                "paths": {
                    "agentd_socket": env["AIOS_AGENTD_SOCKET_PATH"],
                    "sessiond_socket": env["AIOS_SESSIOND_SOCKET_PATH"],
                    "policyd_socket": env["AIOS_POLICYD_SOCKET_PATH"],
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("shell session/policy/registry flow smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "sessiond": resolve_binary("sessiond", args.sessiond, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
    }
    ensure_binary(binaries["sessiond"], "aios-sessiond")
    ensure_binary(binaries["policyd"], "aios-policyd")
    ensure_binary(binaries["agentd"], "aios-agentd")

    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-cp-", dir="/tmp"))
    env = make_env(temp_root)
    shell_profile = temp_root / "shell-profile.json"
    write_shell_profile(shell_profile, env)

    failed = False
    processes: dict[str, subprocess.Popen] = {}
    try:
        for name in ("sessiond", "policyd", "agentd"):
            processes[name] = launch(binaries[name], env)

        sessiond_socket = Path(env["AIOS_SESSIOND_SOCKET_PATH"])
        policyd_socket = Path(env["AIOS_POLICYD_SOCKET_PATH"])
        agentd_socket = Path(env["AIOS_AGENTD_SOCKET_PATH"])

        for socket_path in (sessiond_socket, policyd_socket, agentd_socket):
            wait_for_socket(socket_path, args.timeout)
            wait_for_health(socket_path, args.timeout)

        session = rpc_call(
            agentd_socket,
            "agent.session.create",
            {"user_id": "shell-live-user", "metadata": {"source": "shell-flow-smoke"}},
            timeout=args.timeout,
        )["session"]
        session_id = session["session_id"]

        provider_resolution = rpc_call(
            agentd_socket,
            "agent.provider.resolve_capability",
            {
                "capability_id": "provider.fs.open",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            (provider_resolution.get("selected") or {}).get("provider_id")
            == "system.files.local",
            "provider registry did not resolve provider.fs.open to system.files.local",
        )

        plan = rpc_call(
            agentd_socket,
            "agent.task.plan",
            {"session_id": session_id, "intent": "Open /tmp/report.txt"},
            timeout=args.timeout,
        )
        task_id = plan["task_id"]
        require(
            plan.get("candidate_capabilities", [None])[0] == "provider.fs.open",
            "agent task plan lost provider.fs.open primary capability",
        )

        evaluation = rpc_call(
            policyd_socket,
            "policy.evaluate",
            {
                "user_id": "shell-live-user",
                "session_id": session_id,
                "task_id": task_id,
                "capability_id": "system.file.bulk_delete",
                "execution_location": "local",
                "intent": "Delete /tmp/report.txt",
            },
            timeout=args.timeout,
        )
        approval_ref = evaluation.get("approval_ref")
        require(bool(approval_ref), "policy.evaluate did not produce approval_ref")

        task_panel = load_json_output(
            "task panel",
            run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
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
                env=env,
            ),
        )
        require(task_panel["panel_id"] == "task-panel", "task panel id mismatch")
        require(
            task_panel["meta"]["primary_capability"] == "provider.fs.open",
            "task panel primary capability mismatch",
        )
        require(
            task_panel["meta"]["provider_selected_id"] == "system.files.local",
            "task panel provider selection mismatch",
        )
        require(
            task_panel["meta"]["provider_candidate_count"] >= 1,
            "task panel provider candidates missing",
        )
        require(
            task_panel["meta"]["task_event_count"] >= 1,
            "task panel event history missing",
        )
        require(
            task_panel["meta"]["plan_route_preference"] == "tool-calling",
            "task panel route preference mismatch",
        )

        approved_task = load_json_output(
            "task approve action",
            run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
                "--profile",
                str(shell_profile),
                "--json",
                "panel",
                "task-surface",
                "action",
                "--task-id",
                task_id,
                "--action",
                "approve-task",
                env=env,
            ),
        )
        require(
            approved_task["state"] == "approved",
            "task surface approve action did not update sessiond state",
        )
        require(
            approved_task["target_component"] == "task-surface",
            "task surface approve action route mismatch",
        )

        started_task = load_json_output(
            "task start action",
            run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
                "--profile",
                str(shell_profile),
                "--json",
                "panel",
                "task-surface",
                "action",
                "--task-id",
                task_id,
                "--action",
                "start-task",
                env=env,
            ),
        )
        require(
            started_task["state"] == "executing",
            "task surface start action did not use executing state",
        )

        approval_panel = load_json_output(
            "approval panel",
            run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
                "--profile",
                str(shell_profile),
                "--json",
                "panel",
                "approval-panel",
                "model",
                "--session-id",
                session_id,
                "--task-id",
                task_id,
                env=env,
            ),
        )
        require(
            approval_panel["meta"]["approval_count"] == 1,
            "approval panel missing pending approval",
        )
        require(
            approval_panel["meta"]["focus_approval_ref"] == approval_ref,
            "approval panel focus approval mismatch",
        )

        snapshot = load_json_output(
            "shell snapshot",
            run_python(
                ROOT / "aios" / "shell" / "runtime" / "shell_desktop.py",
                "snapshot",
                "--profile",
                str(shell_profile),
                "--session-id",
                session_id,
                "--task-id",
                task_id,
                "--surface",
                "task-surface",
                "--surface",
                "approval-panel",
                "--json",
                env=env,
            ),
        )
        require(snapshot["surface_count"] == 2, "shell snapshot surface count mismatch")
        component_names = snapshot["summary"]["component_names"]
        require("task-surface" in component_names, "snapshot missing task-surface")
        require("approval-panel" in component_names, "snapshot missing approval-panel")

        print(
            json.dumps(
                {
                    "profile": str(shell_profile),
                    "session_id": session_id,
                    "task_id": task_id,
                    "approval_ref": approval_ref,
                    "provider_id": task_panel["meta"]["provider_selected_id"],
                    "snapshot_surfaces": component_names,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:  # noqa: BLE001
        failed = True
        print(f"shell session/policy/registry flow smoke failed: {error}", file=sys.stderr)
        print_logs(processes)
        return 1
    finally:
        terminate(list(processes.values()))
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

