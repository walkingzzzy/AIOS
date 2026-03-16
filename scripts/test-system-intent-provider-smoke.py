#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS system intent provider smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing sessiond/policyd/agentd/system-intent-provider binaries")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--provider", type=Path, help="Path to system-intent-provider binary")
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


def ensure_binaries(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing binaries for system intent provider smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print("Build them first, for example: cargo build -p aios-sessiond -p aios-policyd -p aios-agentd -p aios-system-intent-provider")
        raise SystemExit(2)


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_response(socket_path, method, params, timeout)
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def rpc_response(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
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
    return json.loads(data.decode("utf-8"))


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


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
            return rpc_call(socket_path, "system.health.get", {}, timeout=min(timeout, 1.5))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def wait_for_provider_health(socket_path: Path, provider_id: str, expected_status: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_seen = None
    while time.time() < deadline:
        result = rpc_call(
            socket_path,
            "agent.provider.health.get",
            {"provider_id": provider_id},
            timeout=min(timeout, 1.5),
        )
        providers = result.get("providers", [])
        if providers:
            last_seen = providers[0]
            if providers[0].get("status") == expected_status and providers[0].get("last_checked_at"):
                return providers[0]
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for provider health={expected_status}: {last_seen}")


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
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    provider_dirs = [
        repo / "aios" / "sdk" / "providers",
        repo / "aios" / "runtime" / "providers",
        repo / "aios" / "shell" / "providers",
        repo / "aios" / "compat" / "browser" / "providers",
        repo / "aios" / "compat" / "office" / "providers",
        repo / "aios" / "compat" / "mcp-bridge" / "providers",
        repo / "aios" / "compat" / "code-sandbox" / "providers",
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
            "AIOS_POLICYD_POLICY_PATH": str(repo / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(repo / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "agentd"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "agentd"),
            "AIOS_AGENTD_SOCKET_PATH": str(runtime_root / "agentd" / "agentd.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "registry"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": os.pathsep.join(str(path) for path in provider_dirs),
            "AIOS_SYSTEM_INTENT_PROVIDER_RUNTIME_DIR": str(runtime_root / "system-intent-provider"),
            "AIOS_SYSTEM_INTENT_PROVIDER_STATE_DIR": str(state_root / "system-intent-provider"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH": str(runtime_root / "system-intent-provider" / "system-intent-provider.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SESSIOND_SOCKET": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_AGENTD_SOCKET": str(runtime_root / "agentd" / "agentd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_DESCRIPTOR_PATH": str(repo / "aios" / "sdk" / "providers" / "system-intent.local.json"),
            "AIOS_SYSTEM_INTENT_PROVIDER_MAX_CONCURRENCY": "2",
        }
    )
    return env


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("system intent provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "sessiond": resolve_binary("sessiond", args.sessiond, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
        "provider": resolve_binary("system-intent-provider", args.provider, args.bin_dir),
    }
    ensure_binaries(binaries)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-system-intent-provider-", dir="/tmp" if Path("/tmp").exists() else None))
    env = make_env(temp_root)
    processes: dict[str, subprocess.Popen] = {}
    failed = False

    try:
        for name in ["sessiond", "policyd", "agentd", "provider"]:
            processes[name] = launch(binaries[name], env)

        sockets = {
            "sessiond": Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            "policyd": Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            "agentd": Path(env["AIOS_AGENTD_SOCKET_PATH"]),
            "provider": Path(env["AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH"]),
        }

        for name, socket_path in sockets.items():
            wait_for_socket(socket_path, args.timeout)
            health = wait_for_health(socket_path, args.timeout)
            print(f"{name} ready: {health['status']} @ {health['socket_path']}")

        provider_health = wait_for_provider_health(
            sockets["agentd"],
            "system.intent.local",
            "available",
            args.timeout,
        )
        require(provider_health.get("status") == "available", "system.intent.local did not report available health")

        intent = "Open /tmp/report.md, summarize the findings, then decide whether manual review is needed"
        session_result = rpc_call(
            sockets["agentd"],
            "agent.session.create",
            {"user_id": "system-intent-smoke", "metadata": {"initial_intent": intent}},
            timeout=args.timeout,
        )
        session_id = session_result["session"]["session_id"]
        task_id = session_result["task"]["task_id"]

        plan = {
            "task_id": task_id,
            "session_id": session_id,
            "summary": "Review local report and decide next action",
            "route_preference": "tool-calling",
            "candidate_capabilities": ["provider.fs.open", "runtime.infer.submit"],
            "next_action": "inspect-bound-target",
        }
        rpc_call(
            sockets["agentd"],
            "agent.task.plan.put",
            {"task_id": task_id, "plan": plan},
            timeout=args.timeout,
        )

        token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "system-intent-smoke",
                "session_id": session_id,
                "task_id": task_id,
                "capability_id": "system.intent.execute",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=args.timeout,
        )

        response = rpc_call(
            sockets["provider"],
            "system.intent.execute",
            {"execution_token": token, "intent": intent},
            timeout=args.timeout,
        )

        require(response.get("provider_id") == "system.intent.local", "system intent response provider_id mismatch")
        require(response.get("session_id") == session_id, "system intent response session_id mismatch")
        require(response.get("task_id") == task_id, "system intent response task_id mismatch")
        require(response.get("plan_source") == "sessiond.task.plan", "system intent provider did not consume sessiond task plan")
        require(response.get("route_preference") == "tool-calling", "system intent provider route preference mismatch")
        require(response.get("next_action") == "inspect-bound-target", "system intent provider next_action mismatch")
        require(response.get("status") == "planned", "system intent provider should stay in planned status")
        require("provider.fs.open" in response.get("candidate_capabilities", []), "system intent provider lost provider.fs.open capability")
        require("runtime.infer.submit" in response.get("candidate_capabilities", []), "system intent provider lost runtime.infer.submit capability")

        actions = response.get("actions", [])
        action_caps = {item.get("capability_id") for item in actions}
        require("provider.fs.open" in action_caps, "system intent provider did not map filesystem action")
        require("runtime.infer.submit" in action_caps, "system intent provider did not map runtime action")
        require(response.get("requires_handoff") is False, "system intent provider should not require handoff for read-only plan")

        notes = response.get("notes", [])
        require(any(note == "task_state=planned" for note in notes), "system intent notes missing task state")
        require(any(note == "candidate_count=2" for note in notes), "system intent notes missing candidate count")

        heuristic_intent = "Open /tmp/notes.txt and summarize the result locally"
        heuristic_session = rpc_call(
            sockets["agentd"],
            "agent.session.create",
            {"user_id": "system-intent-smoke", "metadata": {"initial_intent": heuristic_intent}},
            timeout=args.timeout,
        )
        heuristic_session_id = heuristic_session["session"]["session_id"]
        heuristic_task_id = heuristic_session["task"]["task_id"]
        heuristic_token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "system-intent-smoke",
                "session_id": heuristic_session_id,
                "task_id": heuristic_task_id,
                "capability_id": "system.intent.execute",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=args.timeout,
        )
        heuristic_response = rpc_call(
            sockets["provider"],
            "system.intent.execute",
            {"execution_token": heuristic_token, "intent": heuristic_intent},
            timeout=args.timeout,
        )
        require(heuristic_response.get("plan_source") == "provider-heuristic", "system intent provider did not fall back to heuristic planning without task.plan")
        require("provider.fs.open" in heuristic_response.get("candidate_capabilities", []), "heuristic system intent response lost provider.fs.open capability")
        require("runtime.infer.submit" in heuristic_response.get("candidate_capabilities", []), "heuristic system intent response lost runtime.infer.submit capability")

        wrong_token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "system-intent-smoke",
                "session_id": session_id,
                "task_id": task_id,
                "capability_id": "runtime.infer.submit",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=args.timeout,
        )
        invalid_response = rpc_response(
            sockets["provider"],
            "system.intent.execute",
            {"execution_token": wrong_token, "intent": intent},
            timeout=args.timeout,
        )
        invalid_error = (invalid_response.get("error") or {}).get("message", "")
        require("execution token capability" in invalid_error, "system intent provider did not reject invalid capability token")

        empty_response = rpc_response(
            sockets["provider"],
            "system.intent.execute",
            {"execution_token": token, "intent": "   "},
            timeout=args.timeout,
        )
        empty_error = (empty_response.get("error") or {}).get("message", "")
        require("intent cannot be empty" in empty_error, "system intent provider did not reject empty intents")

        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "task_id": task_id,
                    "status": response.get("status"),
                    "plan_source": response.get("plan_source"),
                    "heuristic_plan_source": heuristic_response.get("plan_source"),
                    "route_preference": response.get("route_preference"),
                    "next_action": response.get("next_action"),
                    "actions": actions,
                    "invalid_error": invalid_error,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"system intent provider smoke failed: {exc}")
        return 1
    finally:
        terminate(list(processes.values()))
        if failed:
            print_logs(processes)
        if args.keep_state:
            print(f"Preserved system intent provider smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
