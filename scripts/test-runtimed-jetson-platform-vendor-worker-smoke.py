#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
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
PLATFORM_ID = "nvidia-jetson-orin-agx"
PLATFORM_RUNTIME_SOURCE = ROOT / "aios" / "runtime" / "platforms" / PLATFORM_ID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS runtimed Jetson platform vendor-command worker smoke harness"
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


def wait_for_vendor_launch_records(path: Path, timeout: float) -> list[dict]:
    deadline = time.time() + timeout
    last_records: list[dict] = []
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            last_records = records
            backends = {record.get("backend_id") for record in records}
            if {"local-gpu", "local-npu"}.issubset(backends):
                return records
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for Jetson vendor launch records: {last_records}")


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
        print("runtimed jetson platform vendor worker smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-runtimed-jetson-vendor-platform-",
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
        source_runtime_profile.read_text(encoding="utf-8").replace(
            f"/usr/share/aios/runtime/platforms/{PLATFORM_ID}",
            str(installed_platform_dir),
        ),
        encoding="utf-8",
    )
    route_profile = state_root / "route-profile.yaml"
    shutil.copyfile(
        ROOT / "aios" / "runtime" / "profiles" / "default-route-profile.yaml",
        route_profile,
    )

    launch_log = state_root / "jetson-vendor-launches.jsonl"
    vendor_worker = state_root / "jetson_vendor_bridge_worker.py"
    vendor_worker.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import json
            import os
            import socket
            from pathlib import Path

            WORKER_CONTRACT = "runtime-worker-v1"


            def append_launch_record(path: Path, payload: dict) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\\n")


            def recv_json(connection: socket.socket) -> dict:
                payload = b""
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    payload += chunk
                return json.loads(payload.decode("utf-8") or "{}")


            def main() -> int:
                backend = os.environ["AIOS_RUNTIME_WORKER_BACKEND_ID"]
                mode = os.environ.get("AIOS_RUNTIME_WORKER_MODE", "unix")
                if mode != "unix":
                    raise SystemExit(f"unsupported vendor bridge mode: {mode}")

                socket_path = Path(os.environ["AIOS_RUNTIME_WORKER_SOCKET_PATH"])
                launch_log = Path(os.environ["AIOS_JETSON_VENDOR_BRIDGE_LOG"])
                if socket_path.exists():
                    socket_path.unlink()
                socket_path.parent.mkdir(parents=True, exist_ok=True)

                append_launch_record(
                    launch_log,
                    {
                        "kind": "jetson-vendor-command",
                        "backend_id": backend,
                        "mode": mode,
                        "socket_path": str(socket_path),
                    },
                )

                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server.bind(str(socket_path))
                server.listen(4)
                try:
                    while True:
                        connection, _ = server.accept()
                        with connection:
                            request = recv_json(connection)
                            response = {
                                "worker_contract": WORKER_CONTRACT,
                                "backend_id": backend,
                                "route_state": f"{backend}-worker-v1",
                                "content": f"jetson vendor bridge {backend} worker completed {request.get('task_id', 'task')}",
                                "rejected": False,
                                "degraded": False,
                                "reason": "jetson vendor bridge worker handled request",
                                "estimated_latency_ms": request.get("estimated_latency_ms"),
                            }
                            connection.sendall(
                                json.dumps(response, ensure_ascii=False).encode("utf-8")
                            )
                finally:
                    server.close()
                    if socket_path.exists():
                        socket_path.unlink()
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        encoding="utf-8",
    )
    os.chmod(vendor_worker, 0o755)
    vendor_command = f"{shlex.quote(sys.executable)} {shlex.quote(str(vendor_worker))}"

    env = os.environ.copy()
    for name in [
        "AIOS_JETSON_ALLOW_REFERENCE_WORKER",
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
            "AIOS_RUNTIMED_MANAGED_WORKER_TIMEOUT_MS": "5000",
            "AIOS_JETSON_ALLOW_REFERENCE_WORKER": "0",
            "AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND": vendor_command,
            "AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND": vendor_command,
            "AIOS_JETSON_VENDOR_BRIDGE_LOG": str(launch_log),
        }
    )
    socket_path = Path(env["AIOS_RUNTIMED_SOCKET_PATH"])
    runtimed_process = launch(runtimed, env)
    failed = False

    try:
        wait_for_path(socket_path, args.timeout)
        launch_records = wait_for_vendor_launch_records(launch_log, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        notes = set(health["notes"])
        require(
            f"hardware_profile_id={PLATFORM_ID}" in notes,
            "runtimed health missing Jetson hardware profile id",
        )
        require(
            "managed_worker_count=2" in notes,
            "runtimed health missing Jetson vendor managed worker count",
        )
        require(
            "managed_worker.local-gpu=ready" in notes,
            "runtimed health missing ready Jetson vendor gpu worker",
        )
        require(
            "managed_worker.local-npu=ready" in notes,
            "runtimed health missing ready Jetson vendor npu worker",
        )
        require(
            "managed_worker_source.local-gpu=hardware-profile" in notes,
            "Jetson vendor gpu worker did not report hardware-profile source",
        )
        require(
            "managed_worker_source.local-npu=hardware-profile" in notes,
            "Jetson vendor npu worker did not report hardware-profile source",
        )

        backends = rpc_call(socket_path, "runtime.backend.list", {}, timeout=args.timeout)
        backend_map = {item["backend_id"]: item for item in backends}
        require(
            backend_map["local-gpu"]["activation"] == "configured-unix-worker",
            "Jetson vendor gpu backend activation mismatch",
        )
        require(
            backend_map["local-npu"]["activation"] == "configured-unix-worker",
            "Jetson vendor npu backend activation mismatch",
        )

        gpu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-platform-vendor",
                "task_id": "task-jetson-platform-vendor-gpu",
                "prompt": "Run Jetson platform gpu vendor bridge worker",
                "model": "qwen-local-14b",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(gpu_response["backend_id"] == "local-gpu", "Jetson vendor gpu response backend mismatch")
        require(
            gpu_response["route_state"] == "local-gpu-worker-v1",
            "Jetson vendor gpu route mismatch",
        )
        require(
            "jetson vendor bridge local-gpu worker completed task-jetson-platform-vendor-gpu"
            in gpu_response["content"],
            "Jetson vendor gpu response content mismatch",
        )

        npu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-platform-vendor",
                "task_id": "task-jetson-platform-vendor-npu",
                "prompt": "Run Jetson platform npu vendor bridge worker",
                "model": "qwen-local-14b",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(npu_response["backend_id"] == "local-npu", "Jetson vendor npu response backend mismatch")
        require(
            npu_response["route_state"] == "local-npu-worker-v1",
            "Jetson vendor npu route mismatch",
        )
        require(
            "jetson vendor bridge local-npu worker completed task-jetson-platform-vendor-npu"
            in npu_response["content"],
            "Jetson vendor npu response content mismatch",
        )

        launch_record_backends = {record.get("backend_id") for record in launch_records}
        require(
            {"local-gpu", "local-npu"}.issubset(launch_record_backends),
            "Jetson vendor launch log missing gpu/npu records",
        )

        print("\nRuntimed Jetson platform vendor worker smoke result summary:")
        print(
            json.dumps(
                {
                    "launch_records": launch_records,
                    "gpu_backend": gpu_response.get("backend_id"),
                    "npu_backend": npu_response.get("backend_id"),
                    "gpu_route_state": gpu_response.get("route_state"),
                    "npu_route_state": npu_response.get("route_state"),
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
            print(f"kept Jetson platform vendor worker smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed Jetson platform vendor worker smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())