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
REFERENCE_WORKER = ROOT / "aios/services/runtimed/runtime/reference_accel_worker.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS runtimed worker-contract smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing runtimed binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
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


def start_worker(backend: str, socket_path: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            str(REFERENCE_WORKER),
            "unix",
            "--backend",
            backend,
            "--socket",
            str(socket_path),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtimed worker contract smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(tempfile.mkdtemp(prefix="aios-runtimed-workers-", dir="/tmp" if Path("/tmp").exists() else None))
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    runtime_profile = state_root / "runtime-profile.yaml"
    route_profile = state_root / "route-profile.yaml"
    gpu_socket = runtime_root / "gpu-worker.sock"
    npu_socket = runtime_root / "npu-worker.sock"
    runtime_profile.write_text(
        textwrap.dedent(
            f"""\
            profile_id: worker-contract-smoke
            scope: system
            default_backend: local-gpu
            allowed_backends:
              - local-cpu
              - local-gpu
              - local-npu
            backend_worker_contract: runtime-worker-v1
            backend_commands:
              local-gpu: unix://{gpu_socket}
              local-npu: unix://{npu_socket}
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

    gpu_worker = start_worker("local-gpu", gpu_socket)
    npu_worker = start_worker("local-npu", npu_socket)
    mismatch_worker: subprocess.Popen | None = None
    wait_for_path(gpu_socket, args.timeout)
    wait_for_path(npu_socket, args.timeout)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
        }
    )
    socket_path = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
    runtimed_process = launch(runtimed, env)
    failed = False

    try:
        wait_for_path(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        require(
            any(note == "backend_worker_contract=runtime-worker-v1" for note in health["notes"]),
            "runtimed health missing worker contract note",
        )
        require(
            any(note == "configured_wrappers=2" for note in health["notes"]),
            "runtimed health missing profile-backed wrapper count",
        )

        backends = rpc_call(socket_path, "runtime.backend.list", {}, timeout=args.timeout)
        backend_map = {item["backend_id"]: item for item in backends}
        require(backend_map["local-gpu"]["availability"] == "available", "gpu backend availability mismatch")
        require(backend_map["local-npu"]["availability"] == "available", "npu backend availability mismatch")

        gpu_route = rpc_call(
            socket_path,
            "runtime.route.resolve",
            {"preferred_backend": "local-gpu", "allow_remote": False},
            timeout=args.timeout,
        )
        require(gpu_route["selected_backend"] == "local-gpu", "gpu route resolution mismatch")

        gpu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-workers",
                "task_id": "task-gpu",
                "prompt": "Run gpu worker contract",
                "model": "smoke-model",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(gpu_response["backend_id"] == "local-gpu", "gpu response backend mismatch")
        require(gpu_response["route_state"] == "local-gpu-worker-v1", "gpu route state mismatch")
        require("reference local-gpu worker completed task-gpu" in gpu_response["content"], "gpu content mismatch")

        npu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-workers",
                "task_id": "task-npu",
                "prompt": "Run npu worker contract",
                "model": "smoke-model",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(npu_response["backend_id"] == "local-npu", "npu response backend mismatch")
        require(npu_response["route_state"] == "local-npu-worker-v1", "npu route state mismatch")
        require("reference local-npu worker completed task-npu" in npu_response["content"], "npu content mismatch")

        rejected = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-workers",
                "task_id": "task-npu-reject",
                "prompt": "Reject this prompt #reject-worker",
                "model": "smoke-model",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(rejected["backend_id"] == "local-npu", "worker rejection backend mismatch")
        require(rejected["rejected"] is True, "worker rejection flag mismatch")
        require(rejected["route_state"] == "local-npu-worker-v1", "worker rejection route mismatch")

        terminate(npu_worker)
        wait_for_path(npu_socket.parent, args.timeout)
        mismatch_worker = start_worker("local-gpu", npu_socket)
        wait_for_path(npu_socket, args.timeout)

        mismatch = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-workers",
                "task_id": "task-npu-mismatch",
                "prompt": "Run npu worker with mismatched backend",
                "model": "smoke-model",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(mismatch["backend_id"] == "local-cpu", "worker mismatch should fall back to local-cpu")
        require(
            mismatch["route_state"] == "backend-fallback-local-cpu",
            "worker mismatch should report backend fallback route state",
        )
        require(
            "worker backend mismatch" in (mismatch.get("reason") or ""),
            "worker mismatch reason missing backend mismatch detail",
        )

    except Exception:
        failed = True
        raise
    finally:
        runtimed_log = terminate(runtimed_process)
        gpu_log = terminate(gpu_worker)
        npu_log = terminate(npu_worker)
        mismatch_log = terminate(mismatch_worker)
        if failed:
            if runtimed_log.strip():
                print("\n--- runtimed log ---")
                print(runtimed_log.rstrip())
            if gpu_log.strip():
                print("\n--- gpu worker log ---")
                print(gpu_log.rstrip())
            if npu_log.strip():
                print("\n--- npu worker log ---")
                print(npu_log.rstrip())
            if mismatch_log.strip():
                print("\n--- mismatch worker log ---")
                print(mismatch_log.rstrip())
        if args.keep_state:
            print(f"kept worker contract smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed worker contract smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
