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
import textwrap
import threading
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS runtime local inference provider smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing policyd/agentd/runtimed/runtime-local-inference-provider binaries")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--provider", type=Path, help="Path to runtime-local-inference-provider binary")
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
        print("Missing binaries for runtime local inference provider smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print("Build them first, for example: cargo build -p aios-policyd -p aios-agentd -p aios-runtimed -p aios-runtime-local-inference-provider")
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


def wait_for_file(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for file: {path}")


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


def note_map(health: dict) -> dict[str, str]:
    notes: dict[str, str] = {}
    for note in health.get("notes", []):
        if isinstance(note, str) and "=" in note:
            key, value = note.split("=", 1)
            notes[key] = value
    return notes



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

    runtime_profile = state_root / "runtime-profile.yaml"
    runtime_profile.write_text(
        textwrap.dedent(
            """\
            profile_id: provider-smoke-runtime
            scope: system
            default_backend: local-gpu
            allowed_backends:
              - local-cpu
              - local-gpu
            local_model_pool:
              - smoke-model
            remote_model_pool: []
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
    shutil.copyfile(repo / "aios" / "runtime" / "profiles" / "default-route-profile.yaml", route_profile)

    hold_started = state_root / "mock-runtime-backend.hold-started"
    hold_release = state_root / "mock-runtime-backend.hold-release"
    backend_script = state_root / "mock-runtime-backend.py"
    backend_script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import sys
            import time
            from pathlib import Path

            backend_id = sys.argv[1]
            request = json.loads(sys.stdin.read() or "{{}}")
            counter_path = Path({str(state_root / 'mock-runtime-backend.count')!r})
            hold_started = Path({str(hold_started)!r})
            hold_release = Path({str(hold_release)!r})

            try:
                call_count = int(counter_path.read_text())
            except Exception:
                call_count = 0
            call_count += 1
            counter_path.write_text(str(call_count))

            if backend_id == "local-gpu" and call_count == 2:
                hold_started.write_text(request.get("task_id", "hold-started"))
                deadline = time.time() + 5.0
                while time.time() < deadline and not hold_release.exists():
                    time.sleep(0.05)

            print(json.dumps({{
                "route_state": "local-wrapper",
                "content": f"wrapper response from {{backend_id}} for {{request.get('task_id')}}",
                "reason": "mock runtime provider backend",
                "estimated_latency_ms": request.get("estimated_latency_ms", 0),
            }}))
            """
        )
    )
    backend_script.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
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
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_LOCAL_CPU_COMMAND": f"python3 {backend_script} local-cpu",
            "AIOS_RUNTIMED_LOCAL_GPU_COMMAND": f"python3 {backend_script} local-gpu",
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_RUNTIME_DIR": str(runtime_root / "rli"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_STATE_DIR": str(state_root / "rli"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_SOCKET_PATH": str(runtime_root / "rli" / "rli.sock"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_RUNTIMED_SOCKET": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_AGENTD_SOCKET": str(runtime_root / "agentd" / "agentd.sock"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_DESCRIPTOR_PATH": str(repo / "aios" / "runtime" / "providers" / "runtime.local-inference.json"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_MAX_CONCURRENCY": "1",
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG": str(state_root / "rli" / "observability.jsonl"),
        }
    )
    return env


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtime local inference provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
        "runtimed": resolve_binary("runtimed", args.runtimed, args.bin_dir),
        "provider": resolve_binary("runtime-local-inference-provider", args.provider, args.bin_dir),
    }
    ensure_binaries(binaries)

    temp_root = Path(
        tempfile.mkdtemp(prefix="aios-rli-", dir="/tmp" if Path("/tmp").exists() else None)
    )
    hold_started = temp_root / "state" / "mock-runtime-backend.hold-started"
    hold_release = temp_root / "state" / "mock-runtime-backend.hold-release"
    env = make_env(temp_root)
    provider_observability_log = Path(env["AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG"])
    processes: dict[str, subprocess.Popen] = {}
    failed = False

    try:
        for name in ["policyd", "agentd", "runtimed", "provider"]:
            processes[name] = launch(binaries[name], env)

        sockets = {
            "policyd": Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            "agentd": Path(env["AIOS_AGENTD_SOCKET_PATH"]),
            "runtimed": Path(env["AIOS_RUNTIMED_SOCKET_PATH"]),
            "provider": Path(env["AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_SOCKET_PATH"]),
        }

        for name, socket_path in sockets.items():
            wait_for_socket(socket_path, args.timeout)
            health = wait_for_health(socket_path, args.timeout)
            print(f"{name} ready: {health['status']} @ {health['socket_path']}")
            if name == "provider":
                notes = note_map(health)
                require(
                    notes.get("embedding_backend") == "local-embedding",
                    "runtime local inference provider health missing embedding backend",
                )
                require(
                    notes.get("rerank_backend") == "local-reranker",
                    "runtime local inference provider health missing rerank backend",
                )

        provider_health = wait_for_provider_health(
            sockets["agentd"],
            "runtime.local.inference",
            "available",
            args.timeout,
        )
        require(provider_health.get("status") == "available", "runtime.local.inference did not report available health")

        token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "runtime-provider-smoke",
                "session_id": "session-runtime-provider",
                "task_id": "task-runtime-provider",
                "capability_id": "runtime.infer.submit",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=args.timeout,
        )

        response = rpc_call(
            sockets["provider"],
            "runtime.infer.submit",
            {
                "session_id": "session-runtime-provider",
                "task_id": "task-runtime-provider",
                "prompt": "Summarize provider fleet readiness",
                "model": "smoke-model",
                "preferred_backend": "local-gpu",
                "execution_token": token,
            },
            timeout=args.timeout,
        )

        require(response.get("backend_id") == "local-gpu", "runtime local inference provider did not preserve local-gpu backend")
        require(response.get("route_state") == "local-wrapper", "runtime local inference provider route_state mismatch")
        require("wrapper response from local-gpu" in response.get("content", ""), "runtime local inference provider did not return runtimed wrapper content")
        require(response.get("provider_id") == "runtime.local.inference", "runtime local inference provider_id mismatch")
        require(response.get("runtime_service_id") == "aios-runtimed", "runtime local inference provider did not expose runtime service id")
        require(response.get("provider_status") == "available", "runtime local inference provider status mismatch")
        require(response.get("queue_saturated") is False, "runtime local inference provider incorrectly reported queue saturation")
        require(isinstance(response.get("runtime_budget"), dict), "runtime local inference provider did not attach runtime budget")
        require(any(note == "provider_max_concurrency=1" for note in response.get("notes", [])), "runtime local inference notes missing provider concurrency")

        embed_token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "runtime-provider-smoke",
                "session_id": "session-runtime-provider",
                "task_id": "task-runtime-provider",
                "capability_id": "runtime.embed.vectorize",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=args.timeout,
        )
        embed_response = rpc_call(
            sockets["provider"],
            "runtime.embed.vectorize",
            {
                "session_id": "session-runtime-provider",
                "task_id": "task-runtime-provider",
                "inputs": [
                    "device readiness summary",
                    "provider registry health status",
                ],
                "model": "smoke-embedding-model",
                "execution_token": embed_token,
            },
            timeout=args.timeout,
        )
        require(embed_response.get("backend_id") == "local-embedding", "runtime embedding backend mismatch")
        require(embed_response.get("route_state") == "provider-local-embedding", "runtime embedding route_state mismatch")
        require(embed_response.get("vector_dimension") == 8, "runtime embedding dimension mismatch")
        require(len(embed_response.get("embeddings", [])) == 2, "runtime embedding record count mismatch")
        require(
            len((embed_response.get("embeddings") or [])[0].get("vector", [])) == 8,
            "runtime embedding vector length mismatch",
        )
        require(embed_response.get("provider_id") == "runtime.local.inference", "runtime embedding provider_id mismatch")
        require(
            any(note == "provider_operation=embedding" for note in embed_response.get("notes", [])),
            "runtime embedding notes missing formal operation marker",
        )

        rerank_token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "runtime-provider-smoke",
                "session_id": "session-runtime-provider",
                "task_id": "task-runtime-provider",
                "capability_id": "runtime.rerank.score",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=args.timeout,
        )
        rerank_response = rpc_call(
            sockets["provider"],
            "runtime.rerank.score",
            {
                "session_id": "session-runtime-provider",
                "task_id": "task-runtime-provider",
                "query": "provider health summary",
                "documents": [
                    "provider health summary with audit notes",
                    "screen capture backend readiness matrix",
                    "shell notification center updates",
                ],
                "top_k": 2,
                "model": "smoke-rerank-model",
                "execution_token": rerank_token,
            },
            timeout=args.timeout,
        )
        require(rerank_response.get("backend_id") == "local-reranker", "runtime rerank backend mismatch")
        require(rerank_response.get("route_state") == "provider-local-rerank", "runtime rerank route_state mismatch")
        require(len(rerank_response.get("results", [])) == 2, "runtime rerank top_k mismatch")
        require(
            (rerank_response.get("results") or [])[0].get("document_index") == 0,
            "runtime rerank did not keep most relevant document first",
        )
        require(rerank_response.get("provider_id") == "runtime.local.inference", "runtime rerank provider_id mismatch")
        require(
            any(note == "provider_operation=rerank" for note in rerank_response.get("notes", [])),
            "runtime rerank notes missing formal operation marker",
        )

        wait_for_file(provider_observability_log, args.timeout)
        observability_entries = [
            json.loads(line)
            for line in provider_observability_log.read_text().splitlines()
            if line.strip()
        ]
        observability_kinds = {entry.get("kind") for entry in observability_entries}
        require(
            "provider.runtime.infer.result" in observability_kinds,
            "provider observability log missing infer result trace",
        )
        require(
            "provider.runtime.embed.result" in observability_kinds,
            "provider observability log missing embedding trace",
        )
        require(
            "provider.runtime.rerank.result" in observability_kinds,
            "provider observability log missing rerank trace",
        )
        embed_trace = next(
            entry
            for entry in observability_entries
            if entry.get("kind") == "provider.runtime.embed.result"
            and entry.get("payload", {}).get("task_id") == "task-runtime-provider"
        )
        require(
            embed_trace.get("payload", {}).get("route_state") == "provider-local-embedding",
            "provider embedding trace route_state mismatch",
        )
        rerank_trace = next(
            entry
            for entry in observability_entries
            if entry.get("kind") == "provider.runtime.rerank.result"
            and entry.get("payload", {}).get("task_id") == "task-runtime-provider"
        )
        require(
            rerank_trace.get("payload", {}).get("route_state") == "provider-local-rerank",
            "provider rerank trace route_state mismatch",
        )

        invalid_response = rpc_response(
            sockets["provider"],
            "runtime.infer.submit",
            {
                "session_id": "wrong-session",
                "task_id": "task-runtime-provider",
                "prompt": "Invalid token context",
                "model": "smoke-model",
                "execution_token": token,
            },
            timeout=args.timeout,
        )
        invalid_error = (invalid_response.get("error") or {}).get("message", "")
        require("request session_id wrong-session does not match token session_id session-runtime-provider" in invalid_error, "runtime local inference provider did not reject mismatched session context")

        hold_result: dict[str, object] = {}

        def hold_request() -> None:
            try:
                hold_result["response"] = rpc_call(
                    sockets["provider"],
                    "runtime.infer.submit",
                    {
                        "session_id": "session-runtime-provider",
                        "task_id": "task-runtime-provider",
                        "prompt": "Hold the gpu route #hold-gpu",
                        "model": "smoke-model",
                        "preferred_backend": "local-gpu",
                        "execution_token": token,
                    },
                    timeout=args.timeout + 2,
                )
            except Exception as exc:  # noqa: BLE001
                hold_result["error"] = str(exc)

        hold_thread = threading.Thread(target=hold_request, daemon=True)
        hold_thread.start()
        wait_for_file(hold_started, args.timeout)

        deadline = time.time() + args.timeout
        budget_error = ""
        while time.time() < deadline:
            budget_response = rpc_response(
                sockets["provider"],
                "runtime.infer.submit",
                {
                    "session_id": "session-runtime-provider",
                    "task_id": "task-runtime-provider",
                    "prompt": "Second request while first is running",
                    "model": "smoke-model",
                    "preferred_backend": "local-gpu",
                    "execution_token": token,
                },
                timeout=args.timeout,
            )
            budget_error = (budget_response.get("error") or {}).get("message", "")
            if "provider concurrency budget exhausted" in budget_error:
                break
            if "response" in hold_result or "error" in hold_result:
                break
            time.sleep(0.05)
        require("provider concurrency budget exhausted" in budget_error, "runtime local inference provider did not surface provider budget exhaustion")

        hold_release.write_text("release")
        hold_thread.join(timeout=args.timeout + 2)
        require("error" not in hold_result, f"held runtime request failed unexpectedly: {hold_result.get('error')}")
        require(
            isinstance(hold_result.get("response"), dict)
            and hold_result["response"].get("backend_id") == "local-gpu",
            "held runtime request did not finish successfully",
        )

        if processes["runtimed"].poll() is None:
            processes["runtimed"].send_signal(signal.SIGINT)
            processes["runtimed"].wait(timeout=5)

        unavailable = rpc_call(
            sockets["provider"],
            "runtime.infer.submit",
            {
                "session_id": "session-runtime-provider",
                "task_id": "task-runtime-provider",
                "prompt": "Retry after runtimed shutdown",
                "model": "smoke-model",
                "execution_token": token,
            },
            timeout=args.timeout,
        )

        require(unavailable.get("rejected") is True, "runtime local inference provider should reject when runtimed is down")
        require(unavailable.get("route_state") == "runtime-unavailable", "runtime local inference provider did not classify runtimed outage")
        require(unavailable.get("provider_status") == "degraded", "runtime local inference provider did not expose degraded provider status")
        require(unavailable.get("provider_id") == "runtime.local.inference", "runtime local inference outage response provider_id mismatch")

        degraded_health = wait_for_provider_health(
            sockets["agentd"],
            "runtime.local.inference",
            "unavailable",
            args.timeout,
        )
        require(degraded_health.get("status") == "unavailable", "runtime local inference provider health was not downgraded after runtimed outage")

        print(
            json.dumps(
                {
                    "backend_id": response.get("backend_id"),
                    "route_state": response.get("route_state"),
                    "provider_status": response.get("provider_status"),
                    "runtime_budget_total_requests": response.get("runtime_budget", {}).get("total_requests"),
                    "embedding_backend_id": embed_response.get("backend_id"),
                    "embedding_dimension": embed_response.get("vector_dimension"),
                    "rerank_backend_id": rerank_response.get("backend_id"),
                    "rerank_top_document_index": (rerank_response.get("results") or [{}])[0].get("document_index"),
                    "invalid_error": invalid_error,
                    "budget_error": budget_error,
                    "outage_route_state": unavailable.get("route_state"),
                    "outage_provider_status": unavailable.get("provider_status"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"runtime local inference provider smoke failed: {exc}")
        return 1
    finally:
        terminate(list(processes.values()))
        if failed:
            print_logs(processes)
        if args.keep_state:
            print(f"Preserved runtime local inference provider smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

