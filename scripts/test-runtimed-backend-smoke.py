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
import textwrap
import threading
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS runtimed backend wrapper smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing runtimed binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
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


def start_gpu_worker(socket_path: Path) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()

    def run() -> None:
        if socket_path.exists():
            socket_path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        server.listen(5)
        server.settimeout(0.1)

        try:
            while not stop_event.is_set():
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue

                with connection:
                    data = b""
                    while True:
                        chunk = connection.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    request = json.loads(data.decode("utf-8") or "{}")
                    prompt = request.get("prompt", "")

                    if "#fail-gpu" in prompt:
                        continue

                    if "#sleep-gpu" in prompt:
                        time.sleep(0.05)

                    payload = json.dumps(
                        {
                            "worker_contract": "runtime-worker-v1",
                            "backend_id": "local-gpu",
                            "route_state": "local-wrapper",
                            "content": f"uds worker response from local-gpu for {request.get('task_id')}",
                            "rejected": False,
                            "degraded": False,
                            "reason": "mock backend uds worker",
                            "estimated_latency_ms": request.get("estimated_latency_ms", 0),
                        }
                    ).encode("utf-8")
                    connection.sendall(payload)
        finally:
            server.close()
            if socket_path.exists():
                socket_path.unlink()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return stop_event, thread


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtimed backend smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    if not runtimed.exists():
        print(f"Missing runtimed binary: {runtimed}")
        raise SystemExit(2)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-runtimed-backend-", dir="/tmp" if Path("/tmp").exists() else None))
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    runtime_profile = state_root / "runtime-profile.yaml"
    runtime_profile.write_text(
        textwrap.dedent(
            """\
            profile_id: smoke-runtime
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
    shutil.copyfile(repo_root() / "aios" / "runtime" / "profiles" / "default-route-profile.yaml", route_profile)
    gpu_worker_socket = runtime_root / "gpu-worker.sock"
    gpu_worker_stop, gpu_worker_thread = start_gpu_worker(gpu_worker_socket)
    wait_for_socket(gpu_worker_socket, args.timeout)

    backend_script = state_root / "mock-runtime-backend.py"
    backend_script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import time
            import sys

            backend_id = sys.argv[1]
            request = json.loads(sys.stdin.read() or "{}")
            prompt = request.get("prompt", "")
            print(json.dumps({
                "route_state": "local-wrapper",
                "content": f"wrapper response from {backend_id} for {request.get('task_id')}",
                "reason": "mock backend wrapper",
                "estimated_latency_ms": request.get("estimated_latency_ms", 0),
            }))
            """
        )
    )
    backend_script.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_LOCAL_CPU_COMMAND": f"python3 {backend_script} local-cpu",
            "AIOS_RUNTIMED_LOCAL_GPU_COMMAND": f"unix://{gpu_worker_socket}",
        }
    )
    socket_path = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
    process = launch(runtimed, env)
    failed = False

    try:
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        configured_wrapper_note = next(
            (note for note in health.get("notes", []) if isinstance(note, str) and note.startswith("configured_wrappers=")),
            None,
        )
        require(configured_wrapper_note is not None, "runtimed health did not report configured wrapper count")
        configured_wrapper_count = int(configured_wrapper_note.split("=", 1)[1])
        require(configured_wrapper_count >= 2, "runtimed health wrapper count did not include cpu and gpu wrappers")

        backends = rpc_call(socket_path, "runtime.backend.list", {}, timeout=args.timeout)
        gpu_descriptor = next(item for item in backends if item.get("backend_id") == "local-gpu")
        require(gpu_descriptor.get("availability") == "available", "local-gpu descriptor did not become available")
        require(
            gpu_descriptor.get("activation") == "configured-unix-worker",
            "local-gpu activation did not expose configured unix worker",
        )

        queue_state = rpc_call(socket_path, "runtime.queue.get", {}, timeout=args.timeout)
        require(queue_state.get("pending") == 0, "runtime.queue.get reported unexpected pending count")
        require(queue_state.get("available_slots") == 2, "runtime.queue.get reported unexpected available slots")
        require(queue_state.get("saturated") is False, "runtime.queue.get unexpectedly reported a saturated queue")

        infer = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-runtime",
                "task_id": "task-runtime",
                "prompt": "Summarize the runtime backend smoke",
                "model": "smoke-model",
            },
            timeout=args.timeout,
        )
        require(infer.get("backend_id") == "local-gpu", "runtime.infer.submit did not use wrapped local-gpu backend")
        require(infer.get("route_state") == "local-wrapper", "runtime.infer.submit did not surface local-wrapper route state")
        require("uds worker response from local-gpu" in infer.get("content", ""), "runtime.infer.submit did not return uds worker content")

        budget_after_gpu = rpc_call(socket_path, "runtime.budget.get", {}, timeout=args.timeout)
        require(budget_after_gpu.get("total_requests") == 1, "runtime.budget.get did not record first request")
        require(budget_after_gpu.get("backend_request_counts", {}).get("local-gpu") == 1, "runtime budget missing local-gpu count")

        fallback = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-runtime",
                "task_id": "task-runtime-fallback",
                "prompt": "Trigger gpu wrapper failure #fail-gpu",
                "model": "smoke-model",
            },
            timeout=args.timeout,
        )
        require(fallback.get("backend_id") == "local-cpu", "runtime fallback did not use local-cpu")
        require(fallback.get("route_state") == "backend-fallback-local-cpu", "runtime fallback did not expose backend fallback route state")
        require("wrapper response from local-cpu" in fallback.get("content", ""), "runtime fallback did not return cpu wrapper content")

        timeout_fallback = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-runtime",
                "task_id": "task-runtime-timeout",
                "prompt": "Trigger timeout fallback #force-timeout #sleep-gpu",
                "model": "smoke-model",
            },
            timeout=args.timeout,
        )
        require(timeout_fallback.get("backend_id") == "local-cpu", "runtime timeout fallback did not use local-cpu")
        require(timeout_fallback.get("route_state") == "timeout-fallback-local-cpu", "runtime timeout fallback did not expose timeout fallback route state")

        budget_after_fallback = rpc_call(socket_path, "runtime.budget.get", {}, timeout=args.timeout)
        require(budget_after_fallback.get("total_requests") == 3, "runtime budget did not count all requests")
        require(budget_after_fallback.get("backend_request_counts", {}).get("local-cpu") == 2, "runtime budget missing local-cpu fallback count")
        require(budget_after_fallback.get("gpu_fallbacks") == 2, "runtime budget did not count gpu fallbacks")
        require(budget_after_fallback.get("last_backend") == "local-cpu", "runtime budget last_backend mismatch")
        require(budget_after_fallback.get("active_requests") == 0, "runtime budget active_requests should return to zero after requests complete")
        require(budget_after_fallback.get("active_models") == 0, "runtime budget active_models should return to zero after requests complete")

        runtime_events = rpc_call(socket_path, "runtime.events.get", {}, timeout=args.timeout)
        event_kinds = [entry.get("kind") for entry in runtime_events.get("entries", [])]
        require("runtime.infer.completed" in event_kinds, "runtime events did not record normal completion")
        require("runtime.infer.fallback" in event_kinds, "runtime events did not record fallback")
        require("runtime.infer.timeout" in event_kinds, "runtime events did not record timeout")

        print("\nRuntimed backend smoke result summary:")
        print(
            json.dumps(
                {
                    "backend_id": infer.get("backend_id"),
                    "route_state": infer.get("route_state"),
                    "content": infer.get("content"),
                    "gpu_transport": "unix-worker",
                    "gpu_fallback_backend": fallback.get("backend_id"),
                    "gpu_fallback_route": fallback.get("route_state"),
                    "timeout_fallback_route": timeout_fallback.get("route_state"),
                    "budget_total_requests": budget_after_fallback.get("total_requests"),
                    "budget_gpu_fallbacks": budget_after_fallback.get("gpu_fallbacks"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"runtimed backend smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        log_output = terminate(process)
        if failed and log_output.strip():
            print("\n--- runtimed log ---")
            print(log_output.rstrip())
        gpu_worker_stop.set()
        gpu_worker_thread.join(timeout=1)
        if args.keep_state:
            print(f"Preserved runtimed backend smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
