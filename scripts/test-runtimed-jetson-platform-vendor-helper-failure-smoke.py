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
        description="AIOS runtimed Jetson platform vendor-helper failure smoke harness"
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


def wait_for_json(path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for JSON file {path}: {last_error}")


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
        print("runtimed jetson platform vendor helper failure smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    runtimed = resolve_binary("runtimed", args.runtimed, args.bin_dir)
    ensure_binary(runtimed, "aios-runtimed")

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-runtimed-jetson-vendor-helper-failure-",
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
    fake_trtexec = state_root / "fake_trtexec_failure.py"
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
                backend_id = os.environ.get("AIOS_VENDOR_WORKER_BACKEND_ID")
                record = {
                    "backend_id": backend_id,
                    "provider_id": os.environ.get("AIOS_VENDOR_WORKER_PROVIDER_ID"),
                    "provider_kind": os.environ.get("AIOS_VENDOR_WORKER_PROVIDER_KIND"),
                    "engine_path": os.environ.get("AIOS_VENDOR_WORKER_ENGINE_PATH"),
                    "request_task_id": os.environ.get("AIOS_RUNTIME_REQUEST_TASK_ID"),
                    "args": sys.argv[1:],
                }
                log_path = Path(os.environ["AIOS_JETSON_FAKE_TRTEXEC_LOG"])
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\\n")

                if backend_id == "local-gpu":
                    print("simulated jetson vendor gpu failure", file=sys.stderr)
                    return 7

                times_path = option_value("--exportTimes=")
                if times_path:
                    Path(times_path).write_text(json.dumps({"latencyMs": 8.5}), encoding="utf-8")
                profile_path = option_value("--exportProfile=")
                if profile_path:
                    Path(profile_path).write_text(json.dumps({"computeMs": 6.0}), encoding="utf-8")
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
            "managed_worker.local-gpu=ready" in notes,
            "runtimed health missing ready Jetson vendor gpu worker",
        )

        response = rpc_call(
            socket_path,
            "runtime.infer.submit",
            {
                "session_id": "session-jetson-vendor-helper-failure",
                "task_id": "task-jetson-vendor-gpu-failure",
                "prompt": "Run Jetson vendor gpu worker and trigger a vendor failure",
                "model": "qwen-local-14b",
                "preferred_backend": "local-gpu",
            },
            timeout=args.timeout,
        )
        require(response["backend_id"] == "local-cpu", "vendor failure should fall back to local-cpu")
        require(
            response["route_state"] == "backend-fallback-local-cpu",
            "vendor failure should report backend fallback route state",
        )
        require(response.get("degraded") is True, "vendor failure fallback should be degraded")
        require(
            "jetson vendor runtime trtexec failed" in (response.get("reason") or ""),
            "vendor failure reason missing structured worker failure message",
        )
        notes_map = note_map(response.get("notes", []))
        evidence_path = Path(notes_map["vendor_evidence_path"])
        require(
            notes_map.get("vendor_error_path") == str(evidence_path),
            "vendor error path note should match evidence path",
        )
        evidence = wait_for_json(evidence_path, args.timeout)
        require(evidence.get("backend_id") == "local-gpu", "vendor error evidence backend mismatch")
        require(
            evidence.get("provider_id") == "nvidia.jetson.tensorrt",
            "vendor error evidence provider mismatch",
        )
        require(
            evidence.get("provider_status") == "error",
            "vendor error evidence status mismatch",
        )
        require(
            evidence.get("error_class") == "command-failed",
            "vendor error evidence class mismatch",
        )
        require(
            "returncode=7" in str(evidence.get("error") or ""),
            "vendor error evidence missing subprocess return code",
        )

        fallback_events = rpc_call(
            socket_path,
            "runtime.events.get",
            {
                "task_id": "task-jetson-vendor-gpu-failure",
                "kind": "runtime.infer.fallback",
                "payload_equals": {"backend_id": "local-cpu"},
                "limit": 10,
            },
            timeout=args.timeout,
        )
        require(
            len(fallback_events.get("entries", [])) >= 1,
            "vendor failure fallback event missing",
        )
        fallback_payload = fallback_events["entries"][0].get("payload", {})
        require(
            fallback_payload.get("artifact_path") == str(evidence_path),
            "fallback event artifact_path mismatch",
        )

        export_response = rpc_call(
            socket_path,
            "runtime.observability.export",
            {
                "task_id": "task-jetson-vendor-gpu-failure",
                "kind": "runtime.infer.fallback",
                "payload_equals": {
                    "backend_id": "local-cpu",
                    "artifact_path": str(evidence_path),
                },
                "limit": 10,
                "reverse": False,
                "reason": "vendor-helper-failure-smoke",
            },
            timeout=args.timeout,
        )
        export_path = Path(export_response["export_path"])
        export_manifest = wait_for_json(export_path, args.timeout)
        require(
            str(evidence_path) in export_manifest["correlation"]["artifact_paths"],
            "runtime export missing vendor evidence artifact path",
        )
        exported_runtime_events_path = Path(export_manifest["exported_artifacts"]["runtime_events_path"])
        exported_runtime_events = [
            json.loads(line)
            for line in exported_runtime_events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        require(
            any(
                item.get("payload", {}).get("artifact_path") == str(evidence_path)
                for item in exported_runtime_events
            ),
            "runtime export missing fallback artifact in exported runtime events",
        )

        print("\nRuntimed Jetson platform vendor helper failure smoke result summary:")
        print(
            json.dumps(
                {
                    "response": {
                        "backend_id": response.get("backend_id"),
                        "route_state": response.get("route_state"),
                        "reason": response.get("reason"),
                        "notes": response.get("notes", []),
                    },
                    "evidence_path": str(evidence_path),
                    "fallback_event_artifact_path": fallback_payload.get("artifact_path"),
                    "export_path": str(export_path),
                    "export_artifact_paths": export_manifest["correlation"]["artifact_paths"],
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
            print(f"kept Jetson platform vendor helper failure smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    print("runtimed Jetson platform vendor helper failure smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

