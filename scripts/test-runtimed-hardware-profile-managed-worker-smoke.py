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
HARDWARE_PROFILE_ID = "nvidia-jetson-orin-agx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS runtimed hardware-profile managed-worker smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing runtimed binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Seconds to wait for sockets and RPC calls",
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


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtimed hardware profile managed worker smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-runtimed-hw-managed-",
            dir="/tmp" if Path("/tmp").exists() else None,
        )
    )
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    runtime_profile = state_root / "runtime-profile.yaml"
    route_profile = state_root / "route-profile.yaml"
    worker_launcher = state_root / "reference_worker_launcher.py"
    worker_launcher.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            from __future__ import annotations

            import os
            import sys

            REFERENCE_WORKER = {json.dumps(str(REFERENCE_WORKER))}


            def main() -> int:
                backend = os.environ["AIOS_RUNTIME_WORKER_BACKEND_ID"]
                socket_path = os.environ["AIOS_RUNTIME_WORKER_SOCKET_PATH"]
                os.execv(
                    sys.executable,
                    [
                        sys.executable,
                        REFERENCE_WORKER,
                        "unix",
                        "--backend",
                        backend,
                        "--socket",
                        socket_path,
                    ],
                )
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        )
    )
    os.chmod(worker_launcher, 0o755)
    managed_worker_template = f"{sys.executable} {worker_launcher}"
    runtime_profile.write_text(
        textwrap.dedent(
            f"""\
            profile_id: hardware-profile-managed-worker-smoke
            scope: system
            default_backend: local-gpu
            allowed_backends:
              - local-cpu
              - local-gpu
              - local-npu
            backend_worker_contract: runtime-worker-v1
            managed_worker_commands:
              local-gpu: "exit 97"
              local-npu: "exit 98"
            hardware_profile_managed_worker_commands:
              {HARDWARE_PROFILE_ID}:
                local-gpu: {json.dumps(managed_worker_template)}
                local-npu: {json.dumps(managed_worker_template)}
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
            "AIOS_RUNTIMED_HARDWARE_PROFILE_ID": HARDWARE_PROFILE_ID,
            "AIOS_RUNTIMED_MANAGED_WORKER_TIMEOUT_MS": "5000",
        }
    )
    socket_path = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
    runtimed_process = launch(runtimed, env)
    failed = False

    try:
        wait_for_path(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        notes = set(health["notes"])
        require(
            f"hardware_profile_id={HARDWARE_PROFILE_ID}" in notes,
            "runtimed health missing hardware profile id",
        )
        require(
            "managed_worker_count=2" in notes,
            "runtimed health missing managed worker count",
        )
        require(
            "managed_worker.local-gpu=ready" in notes,
            "runtimed health missing ready local-gpu managed worker",
        )
        require(
            "managed_worker.local-npu=ready" in notes,
            "runtimed health missing ready local-npu managed worker",
        )
        require(
            "managed_worker_source.local-gpu=hardware-profile" in notes,
            "local-gpu managed worker did not report hardware-profile source",
        )
        require(
            "managed_worker_source.local-npu=hardware-profile" in notes,
            "local-npu managed worker did not report hardware-profile source",
        )

        backends = rpc_call(socket_path, "runtime.backend.list", {}, timeout=args.timeout)
        backend_map = {item["backend_id"]: item for item in backends}
        require(
            backend_map["local-gpu"]["availability"] == "available",
            "hardware-profile gpu backend availability mismatch",
        )
        require(
            backend_map["local-gpu"]["activation"] == "configured-unix-worker",
            "hardware-profile gpu backend activation mismatch",
        )
        require(
            backend_map["local-npu"]["availability"] == "available",
            "hardware-profile npu backend availability mismatch",
        )
        require(
            backend_map["local-npu"]["activation"] == "configured-unix-worker",
            "hardware-profile npu backend activation mismatch",
        )

        gpu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-hardware-profile",
                "task_id": "task-hardware-profile-gpu",
                "prompt": "Run hardware profile gpu worker",
                "model": "smoke-model",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(
            gpu_response["backend_id"] == "local-gpu",
            "hardware-profile gpu response backend mismatch",
        )
        require(
            gpu_response["route_state"] == "local-gpu-worker-v1",
            "hardware-profile gpu route mismatch",
        )

        npu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-hardware-profile",
                "task_id": "task-hardware-profile-npu",
                "prompt": "Run hardware profile npu worker",
                "model": "smoke-model",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(
            npu_response["backend_id"] == "local-npu",
            "hardware-profile npu response backend mismatch",
        )
        require(
            npu_response["route_state"] == "local-npu-worker-v1",
            "hardware-profile npu route mismatch",
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
            print(f"kept hardware-profile managed worker smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed hardware-profile managed worker smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
