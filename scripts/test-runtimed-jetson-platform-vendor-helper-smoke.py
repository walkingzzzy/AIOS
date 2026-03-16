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
PLATFORM_ID = "nvidia-jetson-orin-agx"
PLATFORM_RUNTIME_SOURCE = ROOT / "aios" / "runtime" / "platforms" / PLATFORM_ID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS runtimed Jetson platform builtin vendor-helper smoke harness"
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


def wait_for_trtexec_records(path: Path, timeout: float) -> list[dict]:
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
    raise TimeoutError(f"Timed out waiting for trtexec records: {last_records}")


def wait_for_evidence(path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for evidence {path}: {last_error}")


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


def note_map(notes: list[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for note in notes:
        if "=" not in note:
            continue
        key, value = note.split("=", 1)
        mapped[key] = value
    return mapped


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("runtimed jetson platform vendor helper smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-runtimed-jetson-vendor-helper-",
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
    for script in installed_platform_dir.rglob("*.py"):
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

    engine_root = state_root / "vendor-engines"
    engine_root.mkdir(parents=True, exist_ok=True)
    (engine_root / "local-gpu.plan").write_text("fake gpu engine\n", encoding="utf-8")
    (engine_root / "local-npu.plan").write_text("fake npu engine\n", encoding="utf-8")

    trtexec_log = state_root / "fake-trtexec-records.jsonl"
    fake_trtexec = state_root / "fake_trtexec.py"
    fake_trtexec.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import json
            import os
            import sys
            from pathlib import Path


            def option_value(prefix: str) -> str | None:
                for arg in sys.argv[1:]:
                    if arg.startswith(prefix):
                        return arg.split("=", 1)[1]
                return None


            def main() -> int:
                record = {
                    "backend_id": os.environ.get("AIOS_VENDOR_WORKER_BACKEND_ID"),
                    "provider_id": os.environ.get("AIOS_VENDOR_WORKER_PROVIDER_ID"),
                    "provider_kind": os.environ.get("AIOS_VENDOR_WORKER_PROVIDER_KIND"),
                    "engine_path": os.environ.get("AIOS_VENDOR_WORKER_ENGINE_PATH"),
                    "request_task_id": os.environ.get("AIOS_RUNTIME_REQUEST_TASK_ID"),
                    "request_model": os.environ.get("AIOS_RUNTIME_REQUEST_MODEL"),
                    "args": sys.argv[1:],
                }
                log_path = Path(os.environ["AIOS_JETSON_FAKE_TRTEXEC_LOG"])
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\\n")

                times_path = option_value("--exportTimes=")
                if times_path:
                    Path(times_path).write_text(json.dumps({"latencyMs": 12.5}), encoding="utf-8")
                profile_path = option_value("--exportProfile=")
                if profile_path:
                    Path(profile_path).write_text(json.dumps({"computeMs": 9.25}), encoding="utf-8")
                print("fake trtexec completed")
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        encoding="utf-8",
    )
    os.chmod(fake_trtexec, 0o755)

    env = os.environ.copy()
    for name in [
        "AIOS_JETSON_ALLOW_REFERENCE_WORKER",
        "AIOS_JETSON_REFERENCE_WORKER_PATH",
        "AIOS_JETSON_REFERENCE_WORKER_PYTHON",
        "AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND",
        "AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND",
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
            "AIOS_JETSON_VENDOR_WORKER_PYTHON": sys.executable,
            "AIOS_JETSON_TRTEXEC_BIN": str(fake_trtexec),
            "AIOS_JETSON_VENDOR_ENGINE_ROOT": str(engine_root),
            "AIOS_JETSON_VENDOR_GPU_EXTRA_ARGS": "--dumpLayerInfo --verbose",
            "AIOS_JETSON_VENDOR_NPU_EXTRA_ARGS": "--separateProfileRun",
            "AIOS_JETSON_VENDOR_NPU_DLA_CORE": "1",
            "AIOS_JETSON_FAKE_TRTEXEC_LOG": str(trtexec_log),
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
            "Jetson builtin vendor gpu backend activation mismatch",
        )
        require(
            backend_map["local-npu"]["activation"] == "configured-unix-worker",
            "Jetson builtin vendor npu backend activation mismatch",
        )

        gpu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-vendor-helper",
                "task_id": "task-jetson-vendor-gpu",
                "prompt": "Run Jetson platform builtin vendor gpu worker",
                "model": "qwen-local-14b",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(gpu_response["backend_id"] == "local-gpu", "Jetson builtin vendor gpu response backend mismatch")
        require(
            gpu_response["route_state"] == "local-gpu-worker-v1",
            "Jetson builtin vendor gpu route mismatch",
        )
        require(
            gpu_response.get("provider_id") == "nvidia.jetson.tensorrt",
            "Jetson builtin vendor gpu provider mismatch",
        )
        require(
            gpu_response.get("runtime_service_id") == "aios-runtimed.jetson-vendor-helper",
            "Jetson builtin vendor gpu runtime_service_id mismatch",
        )
        require(
            gpu_response.get("provider_status") == "available",
            "Jetson builtin vendor gpu provider_status mismatch",
        )
        require(
            "jetson vendor nvidia.jetson.tensorrt completed task-jetson-vendor-gpu"
            in gpu_response["content"],
            "Jetson builtin vendor gpu response content mismatch",
        )
        gpu_notes = note_map(gpu_response.get("notes", []))
        require(
            gpu_notes.get("vendor_provider") == "nvidia.jetson.tensorrt",
            "Jetson builtin vendor gpu notes missing provider",
        )

        npu_response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-vendor-helper",
                "task_id": "task-jetson-vendor-npu",
                "prompt": "Run Jetson platform builtin vendor npu worker",
                "model": "qwen-local-14b",
                "preferred_backend": "local-npu",
            },
            timeout=args.timeout,
        )
        require(npu_response["backend_id"] == "local-npu", "Jetson builtin vendor npu response backend mismatch")
        require(
            npu_response["route_state"] == "local-npu-worker-v1",
            "Jetson builtin vendor npu route mismatch",
        )
        require(
            npu_response.get("provider_id") == "nvidia.jetson.dla-trtexec",
            "Jetson builtin vendor npu provider mismatch",
        )
        require(
            npu_response.get("provider_status") == "available",
            "Jetson builtin vendor npu provider_status mismatch",
        )
        require(
            "jetson vendor nvidia.jetson.dla-trtexec completed task-jetson-vendor-npu"
            in npu_response["content"],
            "Jetson builtin vendor npu response content mismatch",
        )
        npu_notes = note_map(npu_response.get("notes", []))
        require(
            npu_notes.get("vendor_dla_core") == "1",
            "Jetson builtin vendor npu notes missing dla core",
        )

        records = wait_for_trtexec_records(trtexec_log, args.timeout)
        record_map = {record["backend_id"]: record for record in records}
        require(
            any(arg == "--dumpLayerInfo" for arg in record_map["local-gpu"]["args"]),
            "fake trtexec gpu args missing extra GPU flag",
        )
        require(
            any(arg == "--verbose" for arg in record_map["local-gpu"]["args"]),
            "fake trtexec gpu args missing verbose flag",
        )
        require(
            any(arg == "--useDLACore=1" for arg in record_map["local-npu"]["args"]),
            "fake trtexec npu args missing DLA core flag",
        )
        require(
            any(arg == "--allowGPUFallback=0" for arg in record_map["local-npu"]["args"]),
            "fake trtexec npu args missing allowGPUFallback flag",
        )
        require(
            any(arg == "--separateProfileRun" for arg in record_map["local-npu"]["args"]),
            "fake trtexec npu args missing extra NPU flag",
        )

        gpu_evidence_path = Path(gpu_notes["vendor_evidence_path"])
        npu_evidence_path = Path(npu_notes["vendor_evidence_path"])
        gpu_evidence = wait_for_evidence(gpu_evidence_path, args.timeout)
        npu_evidence = wait_for_evidence(npu_evidence_path, args.timeout)
        require(
            gpu_evidence.get("provider_id") == "nvidia.jetson.tensorrt",
            "gpu evidence provider mismatch",
        )
        require(
            npu_evidence.get("provider_id") == "nvidia.jetson.dla-trtexec",
            "npu evidence provider mismatch",
        )
        require(
            npu_evidence.get("dla_core") == 1,
            "npu evidence missing dla_core",
        )
        require(
            gpu_evidence.get("latency_ms") == 12.5,
            "gpu evidence latency mismatch",
        )

        print("\nRuntimed Jetson platform builtin vendor helper smoke result summary:")
        print(
            json.dumps(
                {
                    "trtexec_records": records,
                    "gpu_response": {
                        "backend_id": gpu_response.get("backend_id"),
                        "provider_id": gpu_response.get("provider_id"),
                        "notes": gpu_response.get("notes", []),
                    },
                    "npu_response": {
                        "backend_id": npu_response.get("backend_id"),
                        "provider_id": npu_response.get("provider_id"),
                        "notes": npu_response.get("notes", []),
                    },
                    "gpu_evidence_path": str(gpu_evidence_path),
                    "npu_evidence_path": str(npu_evidence_path),
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
            print(f"kept Jetson platform builtin vendor helper smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed Jetson platform builtin vendor helper smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
