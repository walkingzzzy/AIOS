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

from aios_cargo_bins import default_aios_bin_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS runtimed budget and queue smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing runtimed binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(repo_root()) / name


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


def wait_for_health(socket_path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            rpc_call(socket_path, "system.health.get", {}, timeout=1.5)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def wait_for_pending(socket_path: Path, expected: int, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = rpc_call(socket_path, "runtime.queue.get", {}, timeout=timeout)
        if state.get("pending") == expected:
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for runtime.queue.get pending={expected}")


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(process: subprocess.Popen) -> str:
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


def threaded_infer(socket_path: Path, params: dict, timeout: float, sink: dict[str, dict], key: str) -> threading.Thread:
    def runner() -> None:
        sink[key] = rpc_call(socket_path, "runtime.infer.submit", params, timeout)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread


def write_runtime_profile(path: Path, *, memory_budget_mb: int, max_concurrency: int, max_parallel_models: int) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            profile_id: smoke-budget
            scope: system
            default_backend: local-cpu
            allowed_backends:
              - local-cpu
            local_model_pool:
              - model-a
              - model-b
            remote_model_pool: []
            embedding_backend: local-embedding
            rerank_backend: local-reranker
            cpu_fallback: false
            memory_budget_mb: {memory_budget_mb}
            kv_cache_budget_mb: 512
            timeout_ms: 30000
            max_concurrency: {max_concurrency}
            max_parallel_models: {max_parallel_models}
            offload_policy: manual-only
            degradation_policy: reject
            observability_level: standard
            """
        )
    )


def launch_runtimed(binary: Path, temp_root: Path, runtime_profile_text: Path) -> tuple[subprocess.Popen, Path]:
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    route_profile = state_root / "route-profile.yaml"
    shutil.copyfile(repo_root() / "aios" / "runtime" / "profiles" / "default-route-profile.yaml", route_profile)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile_text),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
        }
    )
    process = launch(binary, env)
    socket_path = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
    try:
        wait_for_socket(socket_path, 15.0)
    except Exception:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(
                f"runtimed exited before socket was ready: {output.strip() or 'no log output'}"
            ) from None
        raise
    wait_for_health(socket_path, 15.0)
    return process, socket_path


def budget_phase(binary: Path, temp_root: Path, timeout: float) -> dict:
    runtime_profile = temp_root / "budget-runtime-profile.yaml"
    write_runtime_profile(runtime_profile, memory_budget_mb=900, max_concurrency=2, max_parallel_models=1)
    process, socket_path = launch_runtimed(binary, temp_root / "bp", runtime_profile)
    failed = False

    try:
        results: dict[str, dict] = {}
        first = threaded_infer(
            socket_path,
            {
                "session_id": "session-budget",
                "task_id": "task-budget-long",
                "prompt": "Hold the cpu slot #sleep-cpu",
                "model": "model-a",
            },
            timeout,
            results,
            "first",
        )
        time.sleep(0.2)

        budget_reject = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-budget",
                "task_id": "task-budget-reject",
                "prompt": "Try a second model while model-a is active",
                "model": "model-b",
            },
            timeout=timeout,
        )
        require(budget_reject.get("rejected") is True, "budget rejection should return rejected=true")
        require(budget_reject.get("route_state") == "budget-rejected", "budget rejection route_state mismatch")

        first.join(timeout=timeout)
        require("first" in results, "long-running budget request did not complete")
        require(results["first"].get("backend_id") == "local-cpu", "budget phase should use local-cpu")

        budget_state = rpc_call(socket_path, "runtime.budget.get", {}, timeout=timeout)
        require(budget_state.get("total_requests") == 2, "budget phase should count one success and one rejection")

        rejected_events = rpc_call(
            socket_path,
            "runtime.events.get",
            {"kind": "runtime.infer.rejected", "limit": 10},
            timeout=timeout,
        )
        rejected_task_ids = {entry.get("task_id") for entry in rejected_events.get("entries", [])}
        require("task-budget-reject" in rejected_task_ids, "budget rejection event missing")

        return {
            "budget_reject_route": budget_reject.get("route_state"),
            "budget_total_requests": budget_state.get("total_requests"),
        }
    except Exception:
        failed = True
        raise
    finally:
        log_output = terminate(process)
        if failed and log_output.strip():
            print("\n--- budget phase runtimed log ---")
            print(log_output.rstrip())


def queue_phase(binary: Path, temp_root: Path, timeout: float) -> dict:
    runtime_profile = temp_root / "queue-runtime-profile.yaml"
    write_runtime_profile(runtime_profile, memory_budget_mb=2048, max_concurrency=1, max_parallel_models=2)
    process, socket_path = launch_runtimed(binary, temp_root / "qp", runtime_profile)
    failed = False

    try:
        results: dict[str, dict] = {}
        first = threaded_infer(
            socket_path,
            {
                "session_id": "session-queue",
                "task_id": "task-queue-long",
                "prompt": "Occupy the only cpu slot #sleep-cpu",
                "model": "model-a",
            },
            timeout,
            results,
            "first",
        )
        time.sleep(0.2)

        queue_reject = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-queue",
                "task_id": "task-queue-reject",
                "prompt": "This one should hit queue saturation",
                "model": "model-a",
            },
            timeout=timeout,
        )
        require(queue_reject.get("rejected") is True, "queue rejection should return rejected=true")
        require(queue_reject.get("route_state") == "queue-rejected", "queue rejection route_state mismatch")

        first.join(timeout=timeout)
        require("first" in results, "long-running queue request did not complete")
        queue_state = rpc_call(socket_path, "runtime.queue.get", {}, timeout=timeout)
        require(queue_state.get("pending") == 0, "queue phase should drain back to zero pending requests")

        rejected_events = rpc_call(
            socket_path,
            "runtime.events.get",
            {"kind": "runtime.infer.rejected", "limit": 10},
            timeout=timeout,
        )
        rejected_task_ids = {entry.get("task_id") for entry in rejected_events.get("entries", [])}
        require("task-queue-reject" in rejected_task_ids, "queue rejection event missing")

        return {
            "queue_reject_route": queue_reject.get("route_state"),
            "queue_pending_after": queue_state.get("pending"),
        }
    except Exception:
        failed = True
        raise
    finally:
        log_output = terminate(process)
        if failed and log_output.strip():
            print("\n--- queue phase runtimed log ---")
            print(log_output.rstrip())


def main() -> int:
    args = parse_args()
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    if not runtimed.exists():
        print(f"Missing runtimed binary: {runtimed}")
        raise SystemExit(2)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-runtimed-budget-", dir="/tmp" if Path("/tmp").exists() else None))
    failed = False

    try:
        budget_summary = budget_phase(runtimed, temp_root, args.timeout)
        queue_summary = queue_phase(runtimed, temp_root, args.timeout)

        print("\nRuntimed budget smoke result summary:")
        print(
            json.dumps(
                {
                    **budget_summary,
                    **queue_summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"runtimed budget smoke failed: {exc}")
        return 1
    finally:
        if args.keep_state:
            print(f"Preserved runtimed budget smoke state at: {temp_root}")
        elif not failed:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
