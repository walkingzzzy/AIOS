#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS runtimed events, token, and remote-audit smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing compiled binaries")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
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


def wait_for_file(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for file: {path}")


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


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(process: subprocess.Popen | None) -> str:
    if process is None:
        return ""
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    return process.stdout.read() if process.stdout else ""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class RemoteHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
        prompt = payload.get("prompt", "")

        if "#fail-remote" in prompt:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "21")
            self.end_headers()
            self.wfile.write(b"remote backend offline")
            return

        response = json.dumps(
            {
                "route_state": "attested-remote",
                "content": f"remote response for {payload.get('task_id')}",
                "reason": "remote http worker",
                "estimated_latency_ms": payload.get("estimated_latency_ms", 0),
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return


def issue_remote_token(
    policyd_socket: Path,
    *,
    user_id: str,
    session_id: str,
    task_id: str,
    target_hash: str | None,
    timeout: float,
) -> dict:
    return rpc_call(
        policyd_socket,
        "policy.token.issue",
        {
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": "runtime.infer.submit",
            "target_hash": target_hash,
            "approval_ref": None,
            "constraints": {},
            "execution_location": "attested_remote",
            "taint_summary": None,
        },
        timeout=timeout,
    )


def remote_target_hash(command: str) -> str:
    return hashlib.sha256(command.strip().encode("utf-8")).hexdigest()


def submit_missing_token_request(runtimed_socket: Path, task_id: str, timeout: float) -> dict:
    return rpc_call(
        runtimed_socket,
        "runtime.infer.submit",
        {
            "session_id": "session-events",
            "task_id": task_id,
            "prompt": "Use the remote backend without a token",
            "model": "smoke-model",
            "preferred_backend": "attested-remote",
        },
        timeout=timeout,
    )


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtimed events smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    policyd = resolve_binary("policyd", args.policyd, args.bin_dir)
    if not runtimed.exists():
        print(f"Missing runtimed binary: {runtimed}")
        raise SystemExit(2)
    if not policyd.exists():
        print(f"Missing policyd binary: {policyd}")
        raise SystemExit(2)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-runtimed-events-", dir="/tmp" if Path("/tmp").exists() else None))
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    runtime_profile = state_root / "runtime-profile.yaml"
    runtime_profile.write_text(
        textwrap.dedent(
            """\
            profile_id: smoke-events
            scope: system
            default_backend: attested-remote
            allowed_backends:
              - local-cpu
              - attested-remote
            local_model_pool:
              - smoke-model
            remote_model_pool:
              - smoke-model
            embedding_backend: local-embedding
            rerank_backend: local-reranker
            cpu_fallback: true
            memory_budget_mb: 2048
            kv_cache_budget_mb: 512
            timeout_ms: 30000
            max_concurrency: 2
            max_parallel_models: 1
            offload_policy: manual-only
            degradation_policy: fallback-local-cpu
            observability_level: standard
            """
        )
    )
    route_profile = state_root / "route-profile.yaml"
    shutil.copyfile(repo_root() / "aios" / "runtime" / "profiles" / "default-route-profile.yaml", route_profile)

    policy_profile = state_root / "policy.yaml"
    policy_profile.write_text(
        textwrap.dedent(
            """\
            profile_id: smoke-policy
            require_approval: []
            deny: []
            remote_offload_default: allowed
            taint_mode: strict
            """
        )
    )
    capability_catalog = repo_root() / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), RemoteHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    endpoint = f"http://127.0.0.1:{httpd.server_port}/infer"
    endpoint_target_hash = remote_target_hash(endpoint)

    policyd_env = os.environ.copy()
    policyd_env.update(
        {
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(policy_profile),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(capability_catalog),
        }
    )
    policyd_socket = Path(policyd_env["AIOS_POLICYD_SOCKET_PATH"])
    policyd_process = launch(policyd, policyd_env)

    runtimed_env = os.environ.copy()
    runtimed_env.update(
        {
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_ATTESTED_REMOTE_COMMAND": endpoint,
            "AIOS_RUNTIMED_POLICYD_SOCKET": str(policyd_socket),
            "AIOS_RUNTIMED_OBSERVABILITY_LOG": str(state_root / "runtimed" / "observability.jsonl"),
        }
    )
    runtimed_socket = Path(runtimed_env["AIOS_RUNTIMED_SOCKET_PATH"])
    remote_audit_log = Path(runtimed_env["AIOS_RUNTIMED_STATE_DIR"]) / "attested-remote-audit.jsonl"
    observability_log = Path(runtimed_env["AIOS_RUNTIMED_OBSERVABILITY_LOG"])
    runtimed_process = None
    failed = False

    try:
        wait_for_socket(policyd_socket, args.timeout)
        wait_for_health(policyd_socket, args.timeout)

        runtimed_process = launch(runtimed, runtimed_env)
        wait_for_socket(runtimed_socket, args.timeout)
        wait_for_health(runtimed_socket, args.timeout)

        backends = rpc_call(runtimed_socket, "runtime.backend.list", {}, timeout=args.timeout)
        remote_descriptor = next(item for item in backends if item.get("backend_id") == "attested-remote")
        require(remote_descriptor.get("availability") == "available", "attested-remote should be available")
        require(remote_descriptor.get("activation") == "configured-remote-endpoint", "attested-remote activation mismatch")

        backend_health_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {"kind": "runtime.backend.health", "limit": 10, "reverse": False},
            timeout=args.timeout,
        )
        backend_health_entries = backend_health_events.get("entries", [])
        require(
            len(backend_health_entries) == len(backends),
            "runtime backend health event count mismatch",
        )
        backend_health_by_backend = {
            entry.get("payload", {}).get("backend_id"): entry.get("payload", {})
            for entry in backend_health_entries
        }
        for backend in backends:
            backend_payload = backend_health_by_backend.get(backend.get("backend_id"))
            require(backend_payload is not None, f"missing backend health event for {backend.get('backend_id')}")
            require(
                backend_payload.get("availability") == backend.get("availability"),
                f"backend availability mismatch for {backend.get('backend_id')}",
            )
            require(
                backend_payload.get("activation") == backend.get("activation"),
                f"backend activation mismatch for {backend.get('backend_id')}",
            )
            require(
                backend_payload.get("health_state") == backend.get("health_state"),
                f"backend health_state mismatch for {backend.get('backend_id')}",
            )
        missing_token = submit_missing_token_request(
            runtimed_socket,
            "task-remote-missing-token",
            args.timeout,
        )
        require(missing_token.get("rejected") is True, "missing-token request should be rejected")
        require(missing_token.get("route_state") == "remote-token-required", "missing-token route_state mismatch")

        remote_token = issue_remote_token(
            policyd_socket,
            user_id="user-events",
            session_id="session-events",
            task_id="task-remote",
            target_hash=endpoint_target_hash,
            timeout=args.timeout,
        )
        remote_response = rpc_call(
            runtimed_socket,
            "runtime.infer.submit",
            {
                "session_id": "session-events",
                "task_id": "task-remote",
                "prompt": "Use the remote backend",
                "model": "smoke-model",
                "preferred_backend": "attested-remote",
                "execution_token": remote_token,
            },
            timeout=args.timeout,
        )
        require(remote_response.get("backend_id") == "attested-remote", "remote request should use attested-remote")
        require(remote_response.get("route_state") == "attested-remote", "remote route_state mismatch")
        require("remote response for task-remote" in remote_response.get("content", ""), "remote response content mismatch")

        wrong_hash_token = issue_remote_token(
            policyd_socket,
            user_id="user-events",
            session_id="session-events",
            task_id="task-remote-wrong-hash",
            target_hash="wrong-target-hash",
            timeout=args.timeout,
        )
        wrong_hash_response = rpc_call(
            runtimed_socket,
            "runtime.infer.submit",
            {
                "session_id": "session-events",
                "task_id": "task-remote-wrong-hash",
                "prompt": "Use the remote backend with the wrong target hash",
                "model": "smoke-model",
                "preferred_backend": "attested-remote",
                "execution_token": wrong_hash_token,
            },
            timeout=args.timeout,
        )
        require(wrong_hash_response.get("rejected") is True, "wrong-hash request should be rejected")
        require(wrong_hash_response.get("route_state") == "remote-token-invalid", "wrong-hash route_state mismatch")
        require(
            "target_hash" in (wrong_hash_response.get("reason") or ""),
            "wrong-hash rejection reason should mention target_hash",
        )

        fallback_token = issue_remote_token(
            policyd_socket,
            user_id="user-events",
            session_id="session-events",
            task_id="task-remote-fallback",
            target_hash=endpoint_target_hash,
            timeout=args.timeout,
        )
        fallback_response = rpc_call(
            runtimed_socket,
            "runtime.infer.submit",
            {
                "session_id": "session-events",
                "task_id": "task-remote-fallback",
                "prompt": "Force remote failure #fail-remote",
                "model": "smoke-model",
                "preferred_backend": "attested-remote",
                "execution_token": fallback_token,
            },
            timeout=args.timeout,
        )
        require(fallback_response.get("backend_id") == "local-cpu", "remote failure should fall back to local-cpu")
        require(fallback_response.get("route_state") == "backend-fallback-local-cpu", "remote fallback route_state mismatch")
        require("local-cpu worker completed task task-remote-fallback" in fallback_response.get("content", ""), "fallback content mismatch")

        ordered_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {"task_id": "task-remote", "reverse": False, "limit": 10},
            timeout=args.timeout,
        )
        ordered_kinds = [entry.get("kind") for entry in ordered_events.get("entries", [])]
        require(
            ordered_kinds[:3] == [
                "runtime.infer.submit",
                "runtime.infer.admitted",
                "runtime.infer.started",
            ],
            "ordered event prefix mismatch",
        )
        require("runtime.infer.completed" in ordered_kinds, "remote completed event missing")

        rejected_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {"task_id": "task-remote-missing-token", "limit": 10},
            timeout=args.timeout,
        )
        rejected_kinds = [entry.get("kind") for entry in rejected_events.get("entries", [])]
        require("runtime.infer.rejected" in rejected_kinds, "missing-token rejected event missing")

        wrong_hash_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {"task_id": "task-remote-wrong-hash", "limit": 10},
            timeout=args.timeout,
        )
        wrong_hash_kinds = [entry.get("kind") for entry in wrong_hash_events.get("entries", [])]
        require("runtime.infer.rejected" in wrong_hash_kinds, "wrong-hash rejected event missing")

        fallback_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {
                "task_id": "task-remote-fallback",
                "kind": "runtime.infer.fallback",
                "source": "aios-runtimed",
                "payload_equals": {
                    "backend_id": "local-cpu",
                    "resolved_backend": "attested-remote",
                },
                "payload_contains": "LOCAL-CPU",
                "limit": 10,
                "reverse": False,
            },
            timeout=args.timeout,
        )
        fallback_kinds = [entry.get("kind") for entry in fallback_events.get("entries", [])]
        require("runtime.infer.fallback" in fallback_kinds, "fallback event missing")

        degraded_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {
                "task_id": "task-remote-fallback",
                "kind": "runtime.infer.degraded",
                "payload_equals": {"backend_id": "local-cpu"},
                "limit": 10,
                "reverse": False,
            },
            timeout=args.timeout,
        )
        require(
            len(degraded_events.get("entries", [])) >= 1,
            "degraded event missing",
        )

        history_task_ids: list[str] = []
        for index in range(70):
            task_id = f"task-history-{index:02d}"
            history_task_ids.append(task_id)
            history_response = submit_missing_token_request(
                runtimed_socket,
                task_id,
                args.timeout,
            )
            require(history_response.get("rejected") is True, f"history request {task_id} should be rejected")
            require(
                history_response.get("route_state") == "remote-token-required",
                f"history request {task_id} route_state mismatch",
            )

        require(remote_audit_log.exists(), "attested-remote audit log was not created")
        audit_lines = [json.loads(line) for line in remote_audit_log.read_text().splitlines() if line.strip()]
        statuses = {entry.get("status") for entry in audit_lines}
        task_ids = {entry.get("task_id") for entry in audit_lines}
        require("error" in statuses, "remote audit missing authorization error entry")
        require("completed" in statuses, "remote audit missing completed entry")
        require("fallback" in statuses, "remote audit missing fallback entry")
        require("task-remote" in task_ids, "remote audit missing task-remote entry")
        require("task-remote-wrong-hash" in task_ids, "remote audit missing task-remote-wrong-hash entry")
        require("task-remote-fallback" in task_ids, "remote audit missing task-remote-fallback entry")
        require("task-remote-missing-token" in task_ids, "remote audit missing missing-token entry")

        wait_for_file(observability_log, args.timeout)
        observability_entries = [
            json.loads(line)
            for line in observability_log.read_text().splitlines()
            if line.strip()
        ]
        backend_observability_entry = next(
            entry
            for entry in observability_entries
            if entry.get("kind") == "runtime.backend.health"
            and entry.get("backend_id") == "attested-remote"
        )
        require(
            backend_observability_entry.get("health_state") == remote_descriptor.get("health_state"),
            "observability backend health_state mismatch",
        )
        fallback_observability_entry = next(
            entry
            for entry in observability_entries
            if entry.get("kind") == "runtime.infer.fallback"
            and entry.get("task_id") == "task-remote-fallback"
        )
        require(
            fallback_observability_entry.get("backend_id") == "local-cpu",
            "observability fallback backend mismatch",
        )
        require(
            fallback_observability_entry.get("resolved_backend") == "attested-remote",
            "observability resolved_backend mismatch",
        )
        require(
            fallback_observability_entry.get("route_state") == "backend-fallback-local-cpu",
            "observability fallback route_state mismatch",
        )

        export_response = rpc_call(
            runtimed_socket,
            "runtime.observability.export",
            {
                "session_id": "session-events",
                "task_id": "task-remote-fallback",
                "kind": "runtime.infer.fallback",
                "payload_equals": {
                    "backend_id": "local-cpu",
                    "resolved_backend": "attested-remote",
                },
                "limit": 10,
                "reverse": False,
                "reason": "events-smoke-export",
            },
            timeout=args.timeout,
        )
        export_path = Path(export_response["export_path"])
        wait_for_file(export_path, args.timeout)
        export_payload = json.loads(export_path.read_text())
        require(export_payload["counts"]["runtime_event_count"] >= 1, "runtime export missing runtime events")
        require(export_payload["counts"]["observability_count"] >= 1, "runtime export missing observability entries")
        require(
            "task-remote-fallback" in export_payload["correlation"]["task_ids"],
            "runtime export missing fallback task correlation",
        )
        require(
            "fallback" in export_payload["correlation"]["remote_audit_statuses"],
            "runtime export missing remote audit fallback correlation",
        )
        exported_runtime_events_path = Path(export_payload["exported_artifacts"]["runtime_events_path"])
        wait_for_file(exported_runtime_events_path, args.timeout)
        exported_runtime_events = [
            json.loads(line)
            for line in exported_runtime_events_path.read_text().splitlines()
            if line.strip()
        ]
        require(
            any(item.get("kind") == "runtime.infer.fallback" for item in exported_runtime_events),
            "runtime export JSONL missing fallback event",
        )

        first_runtimed_log = terminate(runtimed_process)
        runtimed_process = None

        restarted = launch(runtimed, runtimed_env)
        runtimed_process = restarted
        wait_for_socket(runtimed_socket, args.timeout)
        wait_for_health(runtimed_socket, args.timeout)

        persisted_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {"session_id": "session-events", "kind": "runtime.infer.completed", "limit": 10},
            timeout=args.timeout,
        )
        persisted_task_ids = {entry.get("task_id") for entry in persisted_events.get("entries", [])}
        require("task-remote" in persisted_task_ids, "persisted completed event for remote task missing after restart")
        require("task-remote-fallback" in persisted_task_ids, "persisted completed event for fallback task missing after restart")

        oldest_history_events = rpc_call(
            runtimed_socket,
            "runtime.events.get",
            {"task_id": history_task_ids[0], "kind": "runtime.infer.rejected", "limit": 10},
            timeout=args.timeout,
        )
        oldest_history_kinds = [entry.get("kind") for entry in oldest_history_events.get("entries", [])]
        require(
            "runtime.infer.rejected" in oldest_history_kinds,
            "oldest persisted history event missing after ring buffer rollover and restart",
        )

        print("\nRuntimed events smoke result summary:")
        print(
            json.dumps(
                {
                    "missing_token_route": missing_token.get("route_state"),
                    "remote_backend": remote_response.get("backend_id"),
                    "remote_route": remote_response.get("route_state"),
                    "wrong_target_route": wrong_hash_response.get("route_state"),
                    "fallback_backend": fallback_response.get("backend_id"),
                    "fallback_route": fallback_response.get("route_state"),
                    "remote_audit_statuses": sorted(status for status in statuses if status),
                    "export_path": str(export_path),
                    "export_counts": export_payload.get("counts", {}),
                    "history_oldest_task": history_task_ids[0],
                    "history_reject_count": len(history_task_ids),
                    "persisted_completed_tasks": sorted(task_id for task_id in persisted_task_ids if task_id),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if first_runtimed_log.strip():
            print("\n--- first runtimed log excerpt ---")
            print(first_runtimed_log.rstrip())
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"runtimed events smoke failed: {exc}")
        return 1
    finally:
        runtimed_log = terminate(runtimed_process)
        policyd_log = terminate(policyd_process)
        if failed:
            if runtimed_log.strip():
                print("\n--- runtimed log ---")
                print(runtimed_log.rstrip())
            if policyd_log.strip():
                print("\n--- policyd log ---")
                print(policyd_log.rstrip())
        httpd.shutdown()
        httpd.server_close()
        if args.keep_state:
            print(f"Preserved runtimed events smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())


