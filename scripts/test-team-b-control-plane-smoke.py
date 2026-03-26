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
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


@dataclass
class ServiceProcess:
    process: subprocess.Popen
    log_path: Path
    log_handle: TextIO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS Team B control-plane smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing compiled binaries")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--system-files-provider", type=Path, help="Path to system-files-provider binary")
    parser.add_argument("--system-intent-provider", type=Path, help="Path to system-intent-provider binary")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for sockets and RPC calls")
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



def ensure_binary(path: Path, package: str) -> None:
    if path.exists():
        return
    print(f"Missing binary: {path}")
    print(f"Build it first, for example: cargo build -p {package}")
    raise SystemExit(2)


def rpc_exchange(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
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


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_exchange(socket_path, method, params, timeout)
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX")


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
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def launch(name: str, binary: Path, env: dict[str, str], log_dir: Path) -> ServiceProcess:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    log_handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return ServiceProcess(process=process, log_path=log_path, log_handle=log_handle)


def terminate(processes: list[ServiceProcess]) -> None:
    for service in processes:
        if service.process.poll() is None:
            service.process.send_signal(signal.SIGINT)
    deadline = time.time() + 5
    for service in processes:
        if service.process.poll() is not None:
            continue
        remaining = max(0.1, deadline - time.time())
        try:
            service.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            service.process.kill()
            service.process.wait(timeout=2)


def print_logs(processes: dict[str, ServiceProcess]) -> None:
    for name, service in processes.items():
        output = ""
        if service.log_path.exists():
            output = service.log_path.read_text(encoding="utf-8")
        if output.strip():
            print(f"\n--- {name} log ---")
            print(output.rstrip())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def plan_step(plan: dict, capability_id: str) -> dict | None:
    for step in plan.get("steps", []):
        if isinstance(step, dict) and step.get("capability_id") == capability_id:
            return step
    return None


def smoke_temp_root() -> Path:
    if os.name != "nt" and Path("/tmp").exists():
        return Path(tempfile.mkdtemp(prefix="tb-", dir="/tmp"))
    base = repo_root() / ".tmp" / "team-b-smoke"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="tb-", dir=base))


def step(message: str) -> None:
    print(f"[team-b-smoke] {message}", flush=True)


def require_trace_context(response: dict, service_name: str) -> None:
    trace_context = response.get("trace_context")
    require(isinstance(trace_context, dict), f"{service_name} response missing trace_context")
    require(
        isinstance(trace_context.get("trace_id"), str) and trace_context["trace_id"].startswith("trc-"),
        f"{service_name} trace_id missing or malformed",
    )
    require(
        isinstance(trace_context.get("span_id"), str) and trace_context["span_id"].startswith("spn-"),
        f"{service_name} span_id missing or malformed",
    )
    require(
        trace_context.get("origin_service") == service_name,
        f"{service_name} trace_context should identify the responding service",
    )


def make_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    run_root = root / "run"
    state_root = root / "state"
    shared_observability_log = state_root / "runtimed" / "observability.jsonl"
    run_root.mkdir(parents=True, exist_ok=True)
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
            "AIOS_AGENTD_RUNTIME_DIR": str(run_root / "agentd"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "agentd"),
            "AIOS_AGENTD_SOCKET_PATH": str(run_root / "agentd" / "agentd.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(run_root / "sessiond" / "sessiond.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(run_root / "runtimed" / "runtimed.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "registry"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": os.pathsep.join(str(path) for path in provider_dirs),
            "AIOS_AGENTD_SYSTEM_FILES_PROVIDER_SOCKET": str(run_root / "system-files-provider" / "system-files-provider.sock"),
            "AIOS_AGENTD_SYSTEM_INTENT_PROVIDER_SOCKET": str(run_root / "system-intent-provider" / "system-intent-provider.sock"),
            "AIOS_SESSIOND_RUNTIME_DIR": str(run_root / "sessiond"),
            "AIOS_SESSIOND_STATE_DIR": str(state_root / "sessiond"),
            "AIOS_SESSIOND_SOCKET_PATH": str(run_root / "sessiond" / "sessiond.sock"),
            "AIOS_SESSIOND_DATABASE": str(state_root / "sessiond" / "sessiond.sqlite3"),
            "AIOS_SESSIOND_OBSERVABILITY_LOG": str(shared_observability_log),
            "AIOS_POLICYD_RUNTIME_DIR": str(run_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(repo / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(repo / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_OBSERVABILITY_LOG": str(shared_observability_log),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
            "AIOS_POLICYD_APPROVAL_TTL_SECONDS": "900",
            "AIOS_RUNTIMED_RUNTIME_DIR": str(run_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(run_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(repo / "aios" / "runtime" / "profiles" / "default-runtime-profile.yaml"),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(repo / "aios" / "runtime" / "profiles" / "default-route-profile.yaml"),
            "AIOS_RUNTIMED_POLICYD_SOCKET": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_RUNTIMED_REMOTE_AUDIT_LOG": str(state_root / "runtimed" / "remote-audit.jsonl"),
            "AIOS_RUNTIMED_OBSERVABILITY_LOG": str(shared_observability_log),
            "AIOS_SYSTEM_FILES_PROVIDER_RUNTIME_DIR": str(run_root / "system-files-provider"),
            "AIOS_SYSTEM_FILES_PROVIDER_STATE_DIR": str(state_root / "system-files-provider"),
            "AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH": str(run_root / "system-files-provider" / "system-files-provider.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_AGENTD_SOCKET": str(run_root / "agentd" / "agentd.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_SESSIOND_SOCKET": str(run_root / "sessiond" / "sessiond.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_POLICYD_SOCKET": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_DESCRIPTOR_PATH": str(repo / "aios" / "sdk" / "providers" / "system-files.local.json"),
            "AIOS_SYSTEM_FILES_PROVIDER_AUDIT_LOG": str(state_root / "system-files-provider" / "audit.jsonl"),
            "AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG": str(shared_observability_log),
            "AIOS_SYSTEM_INTENT_PROVIDER_RUNTIME_DIR": str(run_root / "system-intent-provider"),
            "AIOS_SYSTEM_INTENT_PROVIDER_STATE_DIR": str(state_root / "system-intent-provider"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH": str(run_root / "system-intent-provider" / "system-intent-provider.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_AGENTD_SOCKET": str(run_root / "agentd" / "agentd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SESSIOND_SOCKET": str(run_root / "sessiond" / "sessiond.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_POLICYD_SOCKET": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_DESCRIPTOR_PATH": str(repo / "aios" / "sdk" / "providers" / "system-intent.local.json"),
            "AIOS_SYSTEM_INTENT_PROVIDER_OBSERVABILITY_LOG": str(shared_observability_log),
        }
    )
    return env


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("team-b control-plane smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "sessiond": resolve_binary("sessiond", args.sessiond, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "runtimed": resolve_binary("runtimed", args.runtimed, args.bin_dir),
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
        "system-files-provider": resolve_binary("system-files-provider", args.system_files_provider, args.bin_dir),
        "system-intent-provider": resolve_binary("system-intent-provider", args.system_intent_provider, args.bin_dir),
    }
    ensure_binary(binaries["sessiond"], "aios-sessiond")
    ensure_binary(binaries["policyd"], "aios-policyd")
    ensure_binary(binaries["runtimed"], "aios-runtimed")
    ensure_binary(binaries["agentd"], "aios-agentd")
    ensure_binary(binaries["system-files-provider"], "aios-system-files-provider")
    ensure_binary(binaries["system-intent-provider"], "aios-system-intent-provider")

    temp_root = smoke_temp_root()
    env = make_env(temp_root)
    failed = False
    log_dir = temp_root / "logs"

    processes = {
        "sessiond": launch("sessiond", binaries["sessiond"], env, log_dir),
        "policyd": launch("policyd", binaries["policyd"], env, log_dir),
        "runtimed": launch("runtimed", binaries["runtimed"], env, log_dir),
        "system-files-provider": launch("system-files-provider", binaries["system-files-provider"], env, log_dir),
        "system-intent-provider": launch("system-intent-provider", binaries["system-intent-provider"], env, log_dir),
        "agentd": launch("agentd", binaries["agentd"], env, log_dir),
    }

    try:
        sessiond_socket = Path(env["AIOS_SESSIOND_SOCKET_PATH"])
        policyd_socket = Path(env["AIOS_POLICYD_SOCKET_PATH"])
        runtimed_socket = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
        agentd_socket = Path(env["AIOS_AGENTD_SOCKET_PATH"])
        system_files_provider_socket = Path(env["AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH"])
        system_intent_provider_socket = Path(env["AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH"])

        for service_name, socket_path in [
            ("sessiond", sessiond_socket),
            ("policyd", policyd_socket),
            ("runtimed", runtimed_socket),
            ("system-files-provider", system_files_provider_socket),
            ("system-intent-provider", system_intent_provider_socket),
            ("agentd", agentd_socket),
        ]:
            wait_for_socket(socket_path, args.timeout)
            health = wait_for_health(socket_path, args.timeout)
            require(health["status"] == "ready", f"service not ready: {socket_path}")
            require_trace_context(
                rpc_exchange(socket_path, "system.health.get", {}, timeout=args.timeout),
                service_name,
            )

        step("all services healthy")
        contract_response = rpc_exchange(agentd_socket, "system.contract.get", {}, timeout=args.timeout)
        require_trace_context(contract_response, "agentd")
        contract = contract_response["result"]
        require(contract["contract"]["contract_version"] == "1.0.0", "contract version should be frozen")
        require(
            any(item["method"] == "system.contract.get" for item in contract["contract"]["methods"]),
            "contract manifest should include system.contract.get",
        )

        invalid_intent = rpc_exchange(
            agentd_socket,
            "agent.intent.submit",
            {"user_id": "user-team-b", "session_id": None, "intent": "   "},
            timeout=args.timeout,
        )
        require(invalid_intent.get("error") is not None, "empty intent should return rpc error")
        require(
            invalid_intent["error"].get("data", {}).get("error_code") == "intent_empty",
            "empty intent should return structured error code",
        )

        step("submit low-risk intent")
        allowed = rpc_call(
            agentd_socket,
            "agent.intent.submit",
            {
                "user_id": "user-team-b",
                "session_id": None,
                "intent": "请在本地总结当前计划",
            },
            timeout=args.timeout,
        )
        session_id = allowed["session"]["session_id"]
        allowed_task_id = allowed["task"]["task_id"]
        require(allowed["policy"]["decision"]["decision"] == "allowed", "summarize intent should be allowed")
        require(allowed["task"]["state"] == "approved", "allowed task should move to approved")
        require(allowed["runtime_preview"]["backend_id"] == "local-cpu", "runtime preview should use local cpu")
        require(plan_step(allowed["plan"], "runtime.infer.submit") is not None, "allowed plan should expose runtime step")
        require(plan_step(allowed["plan"], "runtime.infer.submit")["status"] == "completed", "allowed runtime step should be completed")
        require(allowed["plan"]["next_action"] == "invoke-runtime-preview", "allowed plan next_action mismatch")
        require(allowed.get("approval_summary") is None, "low-risk summarize intent should not expose approval summary")
        require((allowed.get("recovery") or {}).get("session_id") == session_id, "allowed response should include recovery summary")

        task_events = rpc_call(
            agentd_socket,
            "agent.task.events.list",
            {
                "task_id": allowed_task_id,
                "limit": 10,
                "reverse": True,
            },
            timeout=args.timeout,
        )["events"]
        require(any(event["to_state"] == "approved" for event in task_events), "task events missing approved transition")

        semantic_entries = rpc_call(
            sessiond_socket,
            "memory.semantic.list",
            {
                "session_id": session_id,
                "label": "agent-plan-summary",
                "limit": 10,
            },
            timeout=args.timeout,
        )["entries"]
        require(len(semantic_entries) >= 1, "semantic memory should contain agent plan summary")
        require(
            semantic_entries[0]["payload"].get("primary_capability") == "runtime.infer.submit",
            "semantic memory should store runtime primary capability",
        )
        evidence = rpc_call(
            agentd_socket,
            "agent.session.evidence.get",
            {
                "session_id": session_id,
                "limit": 20,
            },
            timeout=args.timeout,
        )
        require(len(evidence["tasks"]) >= 1, "session evidence should include tasks")
        require(len(evidence["semantic_memory"]) >= 1, "session evidence should include semantic memory")
        require(evidence["recovery"]["session_id"] == session_id, "session evidence should include recovery ref")

        runtime_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {
                "session_id": session_id,
                "task_id": allowed_task_id,
                "limit": 10,
                "reverse": True,
            },
            timeout=args.timeout,
        )["entries"]
        require(any(event["kind"] == "runtime.infer.completed" for event in runtime_events), "runtime events missing completion entry")

        step("low-risk intent completed")
        danger_path = temp_root / "team-b-danger.txt"
        danger_path.write_text("team-b control-plane approval target\n")

        step("submit approval-gated delete intent")
        needs_approval = rpc_call(
            agentd_socket,
            "agent.intent.submit",
            {
                "user_id": "user-team-b",
                "session_id": session_id,
                "intent": f"删除 {danger_path} 并清空回收站",
            },
            timeout=args.timeout,
        )
        approval_task_id = needs_approval["task"]["task_id"]
        require(
            needs_approval["policy"]["decision"]["decision"] == "needs-approval",
            "delete intent should require approval",
        )
        approval_ref = needs_approval["policy"].get("approval_ref")
        require(bool(approval_ref), "approval_ref should be present for high-risk intent")
        approval_target_hash = ((needs_approval.get("portal_handle") or {}).get("scope") or {}).get("target_hash")
        require(bool(approval_target_hash), "high-risk approval flow should bind portal target_hash")
        require(
            needs_approval["plan"].get("next_action") == "request-destructive-approval",
            "delete plan next_action mismatch",
        )
        delete_step = plan_step(needs_approval["plan"], "system.file.bulk_delete")
        require(delete_step is not None, "delete intent should expose destructive step in plan")
        require(delete_step["requires_approval"] is True, "delete step should be marked approval-gated")
        require((needs_approval.get("approval_summary") or {}).get("approval_ref") == approval_ref, "submit response should expose approval summary ref")
        require((needs_approval.get("approval_summary") or {}).get("approval_status") == "pending", "submit response should expose pending approval status")
        require((needs_approval.get("chooser_request") or {}).get("approval_ref") == approval_ref, "submit response should expose chooser approval ref")
        require((needs_approval.get("chooser_request") or {}).get("portal_handle_id") == needs_approval["portal_handle"]["handle_id"], "submit response should bind chooser to portal handle")

        approvals = rpc_call(
            agentd_socket,
            "agent.approval.list",
            {
                "session_id": session_id,
                "task_id": approval_task_id,
                "status": "pending",
            },
            timeout=args.timeout,
        )["approvals"]
        require(any(item["approval_ref"] == approval_ref for item in approvals), "pending approval not found")

        step("resolve approval")
        approved = rpc_call(
            agentd_socket,
            "agent.approval.resolve",
            {
                "approval_ref": approval_ref,
                "status": "approved",
                "resolver": "team-b-smoke",
                "reason": "user confirmed destructive action",
            },
            timeout=args.timeout,
        )
        require(approved["status"] == "approved", "approval should resolve to approved")

        step("resume approved task")
        resumed = rpc_call(
            agentd_socket,
            "agent.task.resume",
            {
                "task_id": approval_task_id,
                "approval_ref": approval_ref,
            },
            timeout=args.timeout,
        )
        require(resumed["task"]["state"] == "completed", "agent.task.resume should complete the approved task")
        require(
            resumed["execution_token"].get("approval_ref") == approval_ref,
            "agent.task.resume should issue an approval-bound execution token",
        )
        require(
            resumed["provider_execution"]["status"] == "completed",
            "agent.task.resume should execute the provider successfully",
        )
        require(
            resumed["provider_execution"]["result"].get("status") == "deleted",
            "agent.task.resume should delete the approved target",
        )
        require((resumed.get("approval_summary") or {}).get("approval_status") == "approved", "agent.task.resume should expose approved summary")
        require((resumed.get("recovery") or {}).get("session_id") == session_id, "agent.task.resume should expose recovery summary")
        require(not danger_path.exists(), "agent.task.resume should remove the approved target")

        step("resume completed")
        agent_task_detail = rpc_call(
            agentd_socket,
            "agent.task.get",
            {"task_id": approval_task_id, "event_limit": 10},
            timeout=args.timeout,
        )
        require(agent_task_detail["task"]["task_id"] == approval_task_id, "agent.task.get should return the requested task")
        require(
            agent_task_detail.get("plan", {}).get("candidate_capabilities", [None])[0] == "system.file.bulk_delete",
            "agent.task.get should include the primary delete capability",
        )
        require(
            any(item.get("approval_ref") == approval_ref for item in agent_task_detail.get("approvals", [])),
            "agent.task.get should include task approvals",
        )
        require(
            (agent_task_detail.get("provider_execution") or {}).get("status") == "completed",
            "agent.task.get should expose provider execution outcome",
        )
        require((agent_task_detail.get("approval_summary") or {}).get("approval_ref") == approval_ref, "agent.task.get should expose approval summary")
        require((agent_task_detail.get("chooser_request") or {}).get("portal_handle_id") == needs_approval["portal_handle"]["handle_id"], "agent.task.get should expose chooser portal binding")
        require((agent_task_detail.get("recovery") or {}).get("session_id") == session_id, "agent.task.get should expose recovery summary")

        agent_task_list = rpc_call(
            agentd_socket,
            "agent.task.list",
            {"session_id": session_id, "limit": 20},
            timeout=args.timeout,
        )
        require(
            any(item["task_id"] == approval_task_id for item in agent_task_list.get("tasks", [])),
            "agent.task.list should include the approved task",
        )

        agent_task_events = rpc_call(
            agentd_socket,
            "agent.task.events.list",
            {"task_id": approval_task_id, "limit": 10, "reverse": True},
            timeout=args.timeout,
        )
        require(
            any(event["to_state"] == "completed" for event in agent_task_events.get("events", [])),
            "agent.task.events.list should include completed transition",
        )

        agent_task_plan = rpc_call(
            agentd_socket,
            "agent.task.plan.get",
            {"task_id": approval_task_id},
            timeout=args.timeout,
        )
        require(agent_task_plan["task_id"] == approval_task_id, "agent.task.plan.get should return the task plan")
        require(
            agent_task_plan.get("next_action") == "request-destructive-approval",
            "agent.task.plan.get should retain destructive next_action",
        )

        agent_session_evidence = rpc_call(
            agentd_socket,
            "agent.session.evidence.get",
            {"session_id": session_id, "limit": 20},
            timeout=args.timeout,
        )
        require(
            any(item["task_id"] == approval_task_id for item in agent_session_evidence.get("tasks", [])),
            "agent.session.evidence.get should include the resumed task",
        )

        agent_session_export = rpc_call(
            agentd_socket,
            "agent.session.evidence.export",
            {"session_id": session_id, "limit": 20, "reason": "team-b-smoke"},
            timeout=args.timeout,
        )
        session_export_path = Path(agent_session_export["export_path"])
        require(session_export_path.exists(), "agent.session.evidence.export should write an export bundle")
        session_export_payload = json.loads(session_export_path.read_text())
        require(
            session_export_payload["counts"]["task_count"] >= 2,
            "agent.session.evidence.export should retain task counts",
        )
        require(
            any(item["task_id"] == approval_task_id for item in session_export_payload["evidence"].get("tasks", [])),
            "agent.session.evidence.export should retain the resumed task",
        )
        require(agent_session_export.get("recovery_status"), "agent.session.evidence.export should expose recovery status summary")
        require(agent_session_export.get("resumable_task_count", 0) >= 1, "agent.session.evidence.export should expose resumable task count")
        require(session_export_payload["counts"].get("resumable_task_count", 0) >= 1, "session export payload should retain resumable task count")


        agent_approval = rpc_call(
            agentd_socket,
            "agent.approval.get",
            {"approval_ref": approval_ref},
            timeout=args.timeout,
        )
        require(agent_approval["status"] == "approved", "agent.approval.get should expose approval status")

        agent_approval_list = rpc_call(
            agentd_socket,
            "agent.approval.list",
            {"session_id": session_id, "task_id": approval_task_id},
            timeout=args.timeout,
        )
        require(
            any(item["approval_ref"] == approval_ref for item in agent_approval_list.get("approvals", [])),
            "agent.approval.list should include the approved record",
        )

        agent_portal_handles = rpc_call(
            agentd_socket,
            "agent.portal.handle.list",
            {"session_id": session_id},
            timeout=args.timeout,
        )
        require(
            any(
                item["handle_id"] == needs_approval["portal_handle"]["handle_id"]
                for item in agent_portal_handles.get("handles", [])
            ),
            "agent.portal.handle.list should include the destructive task handle",
        )

        agent_audit = rpc_call(
            agentd_socket,
            "agent.audit.query",
            {"session_id": session_id, "task_id": approval_task_id, "limit": 10, "reverse": True},
            timeout=args.timeout,
        )
        require(
            any(item["decision"] == "approval-approved" for item in agent_audit.get("entries", [])),
            "agent.audit.query should expose approval-approved audit entries",
        )

        agent_audit_export = rpc_call(
            agentd_socket,
            "agent.audit.export",
            {"session_id": session_id, "task_id": approval_task_id, "limit": 10, "reverse": True, "reason": "team-b-smoke"},
            timeout=args.timeout,
        )
        audit_export_path = Path(agent_audit_export["export_path"])
        require(audit_export_path.exists(), "agent.audit.export should write an export bundle")
        audit_export_payload = json.loads(audit_export_path.read_text())
        require(
            any(item["decision"] == "approval-approved" for item in audit_export_payload.get("entries", [])),
            "agent.audit.export should retain approval-approved audit entries",
        )
        require(
            audit_export_payload["audit_store"]["active_segment_path"] == env["AIOS_POLICYD_AUDIT_LOG"],
            "agent.audit.export should retain policyd active segment path",
        )
        require(agent_audit_export.get("approval_ref_count", 0) >= 1, "agent.audit.export should expose approval ref count")
        require(agent_audit_export.get("decision_count", 0) >= 1, "agent.audit.export should expose decision count")


        token = rpc_call(
            agentd_socket,
            "agent.policy.token.issue",
            {
                "user_id": "user-team-b",
                "session_id": session_id,
                "task_id": approval_task_id,
                "capability_id": needs_approval["plan"]["candidate_capabilities"][0],
                "target_hash": approval_target_hash,
                "approval_ref": approval_ref,
                "constraints": {},
                "execution_location": needs_approval["provider_resolution"]["selected"]["execution_location"],
                "taint_summary": needs_approval["policy"]["taint_hint"],
            },
            timeout=args.timeout,
        )
        verified = rpc_call(
            agentd_socket,
            "agent.policy.token.verify",
            {"token": token, "target_hash": approval_target_hash},
            timeout=args.timeout,
        )
        require(verified["valid"] is True, "issued token should verify")
        consumed = rpc_call(
            agentd_socket,
            "agent.policy.token.verify",
            {"token": token, "target_hash": approval_target_hash, "consume": True},
            timeout=args.timeout,
        )
        require(consumed["valid"] is True, "high-risk token should verify and consume once")
        require(consumed["consumed"] is True, "high-risk token should report consumed=true")

        reused = rpc_call(
            agentd_socket,
            "agent.policy.token.verify",
            {"token": token, "target_hash": approval_target_hash, "consume": True},
            timeout=args.timeout,
        )
        require(reused["valid"] is False, "consumed high-risk token should not verify twice")
        require(
            "already consumed" in reused["reason"],
            "reused high-risk token should explain reuse rejection",
        )

        audit_entries = rpc_call(
            agentd_socket,
            "agent.audit.query",
            {
                "session_id": session_id,
                "task_id": approval_task_id,
                "limit": 10,
                "reverse": True,
            },
            timeout=args.timeout,
        )["entries"]
        decisions = {entry["decision"] for entry in audit_entries}
        require("approval-pending" in decisions, "audit missing approval-pending")
        require("approval-approved" in decisions, "audit missing approval-approved")
        require("token-issued" in decisions, "audit missing token-issued")
        require("token-consumed" in decisions, "audit missing token-consumed")
        require("token-reused" in decisions, "audit missing token-reused")

        observability_log = Path(env["AIOS_RUNTIMED_OBSERVABILITY_LOG"])
        require(observability_log.exists(), "shared observability log was not written")
        observability_entries = [
            json.loads(line)
            for line in observability_log.read_text().splitlines()
            if line.strip()
        ]
        require(
            any(entry.get("kind") == "runtime.infer.completed" for entry in observability_entries),
            "shared observability log missing runtime completion trace",
        )
        require(
            any(
                entry.get("source") == "aios-sessiond"
                and entry.get("kind") == "task.state.updated"
                for entry in observability_entries
            ),
            "shared observability log missing sessiond task lifecycle trace",
        )
        require(
            any(entry.get("decision") == "approval-pending" for entry in observability_entries),
            "shared observability log missing mirrored policy audit",
        )
        require(
            any(entry.get("artifact_path") == env["AIOS_POLICYD_AUDIT_LOG"] for entry in observability_entries if entry.get("decision")),
            "mirrored policy audit should retain audit artifact path",
        )

        runtime_export = rpc_call(
            runtimed_socket,
            "runtime.observability.export",
            {
                "session_id": session_id,
                "limit": 50,
                "reverse": False,
                "reason": "team-b-control-plane-smoke",
            },
            timeout=args.timeout,
        )
        runtime_export_path = Path(runtime_export["export_path"])
        require(runtime_export_path.exists(), "runtime.observability.export should write an export bundle")
        runtime_export_payload = json.loads(runtime_export_path.read_text())
        require(
            runtime_export_payload["counts"].get("runtime_event_count", 0) >= 1,
            "runtime.observability.export should retain runtime events",
        )
        require(
            allowed_task_id in runtime_export_payload["correlation"].get("task_ids", []),
            "runtime.observability.export should correlate the runtime task",
        )

        print("team-b control plane smoke passed")
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"team-b control plane smoke failed: {exc}")
        return 1
    finally:
        terminate(list(processes.values()))
        for service in processes.values():
            service.log_handle.close()
        print_logs(processes)
        if failed or args.keep_state:
            print(f"state retained at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())







