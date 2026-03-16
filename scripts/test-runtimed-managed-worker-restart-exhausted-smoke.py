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
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS runtimed managed-worker restart exhaustion smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing runtimed binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for sockets, restart transitions and RPC calls",
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help="Keep temp runtime/state directory on success",
    )
    return parser.parse_args()


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(ROOT), name)


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


def ensure_binary(path: Path, package: str) -> None:
    if path.exists():
        return
    print(f"Missing binary: {path}")
    print(f"Build it first, for example: cargo build -p {package}")
    raise SystemExit(2)


def wait_for_path(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for path: {path}")


def wait_for_file(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for file: {path}")


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


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def wait_for_backend_descriptor(
    socket_path: Path,
    backend_id: str,
    timeout: float,
    predicate,
) -> dict:
    deadline = time.time() + timeout
    last_descriptor: dict | None = None
    while time.time() < deadline:
        descriptors = rpc_call(socket_path, "runtime.backend.list", {}, timeout=1.0)
        descriptor = next(item for item in descriptors if item.get("backend_id") == backend_id)
        last_descriptor = descriptor
        if predicate(descriptor):
            return descriptor
        time.sleep(0.1)
    raise TimeoutError(
        f"Timed out waiting for backend descriptor {backend_id}: {last_descriptor}"
    )


def wait_for_backend_health_events(socket_path: Path, timeout: float) -> list[dict]:
    deadline = time.time() + timeout
    last_entries: list[dict] = []
    while time.time() < deadline:
        response = rpc_call(
            socket_path,
            "runtime.events.get",
            {"kind": "runtime.backend.health", "limit": 32, "reverse": False},
            timeout=1.0,
        )
        entries = [
            entry
            for entry in response.get("entries", [])
            if entry.get("payload", {}).get("backend_id") == "local-gpu"
        ]
        last_entries = entries
        has_restarting = any(
            entry.get("payload", {}).get("worker_state") == "restarting"
            for entry in entries
        )
        has_exhausted = any(
            entry.get("payload", {}).get("worker_state") == "restart-exhausted"
            and "attempt 2/2" in (entry.get("payload", {}).get("detail") or "")
            for entry in entries
        )
        if has_restarting and has_exhausted:
            return entries
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for backend health exhaustion events: {last_entries}")


def wait_for_observability_exhausted_entries(path: Path, timeout: float) -> list[dict]:
    deadline = time.time() + timeout
    last_entries: list[dict] = []
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            entries = [
                json.loads(line)
                for line in path.read_text().splitlines()
                if line.strip()
            ]
            filtered = [
                entry
                for entry in entries
                if entry.get("kind") == "runtime.backend.health"
                and entry.get("backend_id") == "local-gpu"
            ]
            last_entries = filtered
            has_restarting = any(
                entry.get("worker_state") == "restarting" for entry in filtered
            )
            has_exhausted = any(
                entry.get("worker_state") == "restart-exhausted"
                and "attempt 2/2" in (entry.get("payload", {}).get("detail") or "")
                for entry in filtered
            )
            if has_restarting and has_exhausted:
                return filtered
        time.sleep(0.1)
    raise TimeoutError(
        f"Timed out waiting for observability exhaustion entries: {last_entries}"
    )


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


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtimed managed worker restart exhausted smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-runtimed-restart-exhausted-",
            dir="/tmp" if Path("/tmp").exists() else None,
        )
    )
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    launch_counter = state_root / "restart-count.txt"
    worker_script = state_root / "restart_exhausted_worker.py"
    worker_script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import json
            import os
            import socket
            from pathlib import Path

            WORKER_CONTRACT = "runtime-worker-v1"


            def next_launch_count(path: Path) -> int:
                count = int(path.read_text().strip()) if path.exists() else 0
                count += 1
                path.write_text(str(count))
                return count


            def main() -> int:
                backend = os.environ["AIOS_RUNTIME_WORKER_BACKEND_ID"]
                socket_path = Path(os.environ["AIOS_RUNTIME_WORKER_SOCKET_PATH"])
                counter_path = Path(os.environ["AIOS_RESTART_EXHAUSTED_COUNT_FILE"])
                launch_count = next_launch_count(counter_path)
                if launch_count > 1:
                    return 23

                if socket_path.exists():
                    socket_path.unlink()
                socket_path.parent.mkdir(parents=True, exist_ok=True)

                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server.bind(str(socket_path))
                server.listen(1)
                try:
                    connection, _ = server.accept()
                    with connection:
                        payload = b""
                        while True:
                            chunk = connection.recv(65536)
                            if not chunk:
                                break
                            payload += chunk
                        request = json.loads(payload.decode("utf-8") or "{}")
                        response = {
                            "worker_contract": WORKER_CONTRACT,
                            "backend_id": backend,
                            "route_state": f"{backend}-worker-v1",
                            "content": f"restart exhausted worker handled {request.get('task_id', 'task')}",
                            "rejected": False,
                            "degraded": False,
                            "reason": "managed worker handled one request before restart exhaustion",
                            "estimated_latency_ms": request.get("estimated_latency_ms"),
                        }
                        connection.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))
                finally:
                    server.close()
                    if socket_path.exists():
                        socket_path.unlink()
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        )
    )
    os.chmod(worker_script, 0o755)

    runtime_profile = state_root / "runtime-profile.yaml"
    route_profile = state_root / "route-profile.yaml"
    managed_worker_command = f"{sys.executable} {worker_script}"
    runtime_profile.write_text(
        textwrap.dedent(
            f"""\
            profile_id: managed-worker-restart-exhausted-smoke
            scope: system
            default_backend: local-gpu
            allowed_backends:
              - local-cpu
              - local-gpu
            backend_worker_contract: runtime-worker-v1
            managed_worker_commands:
              local-gpu: {json.dumps(managed_worker_command)}
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
    shutil.copyfile(ROOT / "aios/runtime/profiles/default-route-profile.yaml", route_profile)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_OBSERVABILITY_LOG": str(state_root / "runtimed" / "observability.jsonl"),
            "AIOS_RUNTIMED_MANAGED_WORKER_TIMEOUT_MS": "1200",
            "AIOS_RUNTIMED_MANAGED_WORKER_RESTART_BACKOFF_MS": "150",
            "AIOS_RUNTIMED_MANAGED_WORKER_RESTART_LIMIT": "2",
            "AIOS_RUNTIMED_BACKEND_HEALTH_POLL_MS": "100",
            "AIOS_RESTART_EXHAUSTED_COUNT_FILE": str(launch_counter),
        }
    )
    socket_path = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
    observability_log = Path(env["AIOS_RUNTIMED_OBSERVABILITY_LOG"])
    runtimed_process = launch(runtimed, env)
    failed = False

    try:
        wait_for_path(socket_path, args.timeout)
        initial_health = wait_for_health(socket_path, args.timeout)
        require(
            any(note == "managed_worker.local-gpu=ready" for note in initial_health["notes"]),
            "runtimed health missing initial ready local-gpu managed worker",
        )

        first_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-restart-exhausted",
                "task_id": "task-restart-exhausted-1",
                "prompt": "Trigger managed worker restart exhaustion",
                "model": "smoke-model",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(
            first_response.get("backend_id") == "local-gpu",
            "first exhaustion response backend mismatch",
        )
        require(
            first_response.get("route_state") == "local-gpu-worker-v1",
            "first exhaustion route mismatch",
        )

        exhausted_descriptor = wait_for_backend_descriptor(
            socket_path,
            "local-gpu",
            args.timeout,
            lambda item: item.get("health_state") == "unavailable"
            and item.get("worker_state") == "restart-exhausted"
            and "attempt 2/2" in (item.get("detail") or ""),
        )
        exhausted_health = wait_for_health(socket_path, args.timeout)
        require(
            any(note == "managed_worker_count=0" for note in exhausted_health["notes"]),
            "runtimed health missing exhausted managed worker count",
        )
        require(
            any(note == "managed_worker.local-gpu=restart-exhausted" for note in exhausted_health["notes"]),
            "runtimed health missing restart-exhausted local-gpu state",
        )
        require(
            any(
                note.startswith("managed_worker_detail.local-gpu=") and "attempt 2/2" in note
                for note in exhausted_health["notes"]
            ),
            "runtimed health missing restart exhaustion detail for local-gpu managed worker",
        )

        backend_health_entries = wait_for_backend_health_events(socket_path, args.timeout)
        require(
            any(entry.get("payload", {}).get("worker_state") == "restarting" for entry in backend_health_entries),
            "runtime.backend.health missing restarting transition before exhaustion",
        )
        require(
            any(
                entry.get("payload", {}).get("worker_state") == "restart-exhausted"
                and "attempt 2/2" in (entry.get("payload", {}).get("detail") or "")
                for entry in backend_health_entries
            ),
            "runtime.backend.health missing restart-exhausted transition",
        )

        wait_for_file(observability_log, args.timeout)
        observability_entries = wait_for_observability_exhausted_entries(observability_log, args.timeout)
        require(
            any(entry.get("worker_state") == "restarting" for entry in observability_entries),
            "observability missing restarting transition before exhaustion",
        )
        require(
            any(
                entry.get("worker_state") == "restart-exhausted"
                and "attempt 2/2" in (entry.get("payload", {}).get("detail") or "")
                for entry in observability_entries
            ),
            "observability missing restart-exhausted transition",
        )

        second_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-restart-exhausted",
                "task_id": "task-restart-exhausted-2",
                "prompt": "Confirm managed worker fallback after exhaustion",
                "model": "smoke-model",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(
            second_response.get("backend_id") == "local-cpu",
            "exhausted managed worker should fall back to local-cpu",
        )
        require(
            second_response.get("route_state") == "degraded-local",
            "exhausted managed worker should route through degraded-local fallback",
        )
        require(
            "local-cpu worker completed task task-restart-exhausted-2"
            in second_response.get("content", ""),
            "exhausted managed worker fallback content mismatch",
        )

        print("\nRuntimed managed worker restart exhaustion smoke result summary:")
        print(
            json.dumps(
                {
                    "exhausted_availability": exhausted_descriptor.get("availability"),
                    "exhausted_activation": exhausted_descriptor.get("activation"),
                    "exhausted_detail": exhausted_descriptor.get("detail"),
                    "first_response_backend": first_response.get("backend_id"),
                    "second_response_backend": second_response.get("backend_id"),
                    "launch_count": launch_counter.read_text().strip() if launch_counter.exists() else "0",
                    "backend_health_event_count": len(backend_health_entries),
                    "observability_event_count": len(observability_entries),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception:
        failed = True
        raise
    finally:
        runtimed_log = terminate(runtimed_process)
        if failed and runtimed_log.strip():
            print("\n--- runtimed log ---")
            print(runtimed_log.rstrip())
        if args.keep_state:
            print(f"kept managed worker restart exhaustion smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed managed worker restart exhaustion smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())