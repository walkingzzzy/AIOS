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

from aios_cargo_bins import default_aios_bin_dir


ROOT = Path(__file__).resolve().parent.parent
PLATFORM_ID = "nvidia-jetson-orin-agx"
PLATFORM_RUNTIME_SOURCE = ROOT / "aios" / "runtime" / "platforms" / PLATFORM_ID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS runtimed Jetson platform worker-bridge smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing runtimed binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--keep-state", action="store_true")
    return parser.parse_args()


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(ROOT) / name


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
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-runtimed-jetson-platform-",
            dir="/tmp" if Path("/tmp").exists() else None,
        )
    )
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    installed_root = temp_root / "installed-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    installed_platform_dir = (
        installed_root
        / "usr"
        / "share"
        / "aios"
        / "runtime"
        / "platforms"
        / PLATFORM_ID
    )
    shutil.copytree(PLATFORM_RUNTIME_SOURCE, installed_platform_dir)
    for script in installed_platform_dir.rglob("*.sh"):
        script.chmod(script.stat().st_mode | 0o111)

    source_runtime_profile = PLATFORM_RUNTIME_SOURCE / "default-runtime-profile.yaml"
    runtime_profile = state_root / "runtime-profile.yaml"
    runtime_profile.write_text(
        source_runtime_profile.read_text().replace(
            f"/usr/share/aios/runtime/platforms/{PLATFORM_ID}",
            str(installed_platform_dir),
        )
    )
    route_profile = state_root / "route-profile.yaml"
    shutil.copyfile(ROOT / "aios" / "runtime" / "profiles" / "default-route-profile.yaml", route_profile)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_HARDWARE_PROFILE_ID": PLATFORM_ID,
            "AIOS_RUNTIMED_MANAGED_WORKER_TIMEOUT_MS": "5000",
            "AIOS_JETSON_ALLOW_REFERENCE_WORKER": "1",
            "AIOS_JETSON_REFERENCE_WORKER_PYTHON": sys.executable,
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
            f"hardware_profile_id={PLATFORM_ID}" in notes,
            "runtimed health missing Jetson hardware profile id",
        )
        require(
            "managed_worker.local-gpu=ready" in notes,
            "runtimed health missing ready Jetson gpu worker",
        )
        require(
            "managed_worker.local-npu=ready" in notes,
            "runtimed health missing ready Jetson npu worker",
        )
        require(
            "managed_worker_source.local-gpu=hardware-profile" in notes,
            "Jetson gpu worker did not report hardware-profile source",
        )
        require(
            "managed_worker_source.local-npu=hardware-profile" in notes,
            "Jetson npu worker did not report hardware-profile source",
        )

        backends = rpc_call(socket_path, "runtime.backend.list", {}, timeout=args.timeout)
        backend_map = {item["backend_id"]: item for item in backends}
        require(
            backend_map["local-gpu"]["activation"] == "configured-unix-worker",
            "Jetson gpu backend activation mismatch",
        )
        require(
            backend_map["local-npu"]["activation"] == "configured-unix-worker",
            "Jetson npu backend activation mismatch",
        )

        gpu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-platform",
                "task_id": "task-jetson-platform-gpu",
                "prompt": "Run Jetson platform gpu worker",
                "model": "qwen-local-14b",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(gpu_response["backend_id"] == "local-gpu", "Jetson gpu response backend mismatch")
        require(
            gpu_response["route_state"] == "local-gpu-worker-v1",
            "Jetson gpu route mismatch",
        )
        require(
            "jetson reference local-gpu worker completed" in gpu_response["content"],
            "Jetson gpu response content mismatch",
        )

        npu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-platform",
                "task_id": "task-jetson-platform-npu",
                "prompt": "Run Jetson platform npu worker",
                "model": "qwen-local-14b",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(npu_response["backend_id"] == "local-npu", "Jetson npu response backend mismatch")
        require(
            npu_response["route_state"] == "local-npu-worker-v1",
            "Jetson npu route mismatch",
        )
        require(
            "jetson reference local-npu worker completed" in npu_response["content"],
            "Jetson npu response content mismatch",
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
            print(f"kept Jetson platform worker smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed Jetson platform worker smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
