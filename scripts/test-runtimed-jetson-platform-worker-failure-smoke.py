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


ROOT = Path(__file__).resolve().parent.parent
PLATFORM_ID = "nvidia-jetson-orin-agx"
PLATFORM_RUNTIME_SOURCE = ROOT / "aios" / "runtime" / "platforms" / PLATFORM_ID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS runtimed Jetson platform worker failure-mode smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing runtimed binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--keep-state", action="store_true")
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


def ensure_note(notes: set[str], expected: str) -> None:
    require(expected in notes, f"missing health note: {expected}")


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtimed jetson platform worker failure smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-runtimed-jetson-platform-failure-",
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
    shutil.copyfile(
        ROOT / "aios" / "runtime" / "profiles" / "default-route-profile.yaml",
        route_profile,
    )

    env = os.environ.copy()
    for name in [
        "AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND",
        "AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND",
        "AIOS_JETSON_REFERENCE_WORKER_PATH",
        "AIOS_JETSON_REFERENCE_WORKER_PYTHON",
        "AIOS_RUNTIMED_LOCAL_GPU_WORKER_COMMAND",
        "AIOS_RUNTIMED_LOCAL_NPU_WORKER_COMMAND",
        "AIOS_RUNTIMED_LOCAL_GPU_COMMAND",
        "AIOS_RUNTIMED_LOCAL_NPU_COMMAND",
        "AIOS_RUNTIMED_DISABLE_LOCAL_GPU",
        "AIOS_RUNTIMED_DISABLE_LOCAL_NPU",
    ]:
        env.pop(name, None)
    env.update(
        {
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_HARDWARE_PROFILE_ID": PLATFORM_ID,
            "AIOS_RUNTIMED_MANAGED_WORKER_TIMEOUT_MS": "1500",
            "AIOS_JETSON_ALLOW_REFERENCE_WORKER": "0",
        }
    )
    socket_path = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
    runtimed_process = launch(runtimed, env)
    failed = False

    try:
        wait_for_path(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        notes = set(health["notes"])
        ensure_note(notes, f"hardware_profile_id={PLATFORM_ID}")
        ensure_note(notes, "managed_worker_count=0")
        ensure_note(notes, "managed_worker.local-gpu=launch-failed")
        ensure_note(notes, "managed_worker.local-npu=launch-failed")
        ensure_note(notes, "managed_worker_source.local-gpu=hardware-profile")
        ensure_note(notes, "managed_worker_source.local-npu=hardware-profile")
        ensure_note(
            notes,
            "managed_worker_detail.local-gpu=managed worker exited before socket was ready (69)",
        )
        ensure_note(
            notes,
            "managed_worker_detail.local-npu=managed worker exited before socket was ready (69)",
        )

        backends = rpc_call(socket_path, "runtime.backend.list", {}, timeout=args.timeout)
        backend_map = {item["backend_id"]: item for item in backends}
        require(
            backend_map["local-cpu"]["availability"] == "available",
            "local-cpu should remain available during Jetson bridge failure",
        )
        require(
            backend_map["local-gpu"]["availability"] != "available",
            "local-gpu should not report available when Jetson bridge is unconfigured",
        )
        require(
            backend_map["local-gpu"]["activation"] != "configured-unix-worker",
            "local-gpu should not report a configured unix worker when Jetson bridge failed",
        )
        require(
            backend_map["local-npu"]["availability"] != "available",
            "local-npu should not report available when Jetson bridge is unconfigured",
        )
        require(
            backend_map["local-npu"]["activation"] != "configured-unix-worker",
            "local-npu should not report a configured unix worker when Jetson bridge failed",
        )

        gpu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-platform-failure",
                "task_id": "task-jetson-platform-gpu-failure",
                "prompt": "Run Jetson platform gpu worker without vendor bridge",
                "model": "qwen-local-14b",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(
            gpu_response["backend_id"] == "local-cpu",
            "Jetson gpu failure path should fall back to local-cpu",
        )
        require(
            gpu_response["route_state"] == "degraded-local",
            "Jetson gpu failure path should mark degraded-local",
        )
        require(
            "local-cpu worker completed task task-jetson-platform-gpu-failure"
            in gpu_response["content"],
            "Jetson gpu failure fallback content mismatch",
        )

        npu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-platform-failure",
                "task_id": "task-jetson-platform-npu-failure",
                "prompt": "Run Jetson platform npu worker without vendor bridge",
                "model": "qwen-local-14b",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(
            npu_response["backend_id"] == "local-cpu",
            "Jetson npu failure path should fall back to local-cpu",
        )
        require(
            npu_response["route_state"] == "degraded-local",
            "Jetson npu failure path should mark degraded-local",
        )
        require(
            "local-cpu worker completed task task-jetson-platform-npu-failure"
            in npu_response["content"],
            "Jetson npu failure fallback content mismatch",
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
            print(f"kept Jetson platform worker failure smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed Jetson platform worker failure smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
