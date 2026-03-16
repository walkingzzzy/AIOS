#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS deviced probe-failure smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing deviced binary")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
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


def ensure_binary(path: Path) -> None:
    if path.exists():
        return
    print(f"Missing binary: deviced={path}")
    print("Build it first, for example: cargo build -p aios-deviced")
    raise SystemExit(2)


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
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
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception:
            time.sleep(0.1)
    raise TimeoutError("Timed out waiting for deviced health")


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        process.send_signal(signal.SIGINT)


def terminate(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        stop_process(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def start_deviced(binary: Path, env: dict[str, str], timeout: float) -> tuple[subprocess.Popen, Path]:
    process = launch(binary, env)
    socket_path = Path(env["AIOS_DEVICED_SOCKET_PATH"])
    wait_for_socket(socket_path, timeout)
    health = wait_for_health(socket_path, timeout)
    require(health["status"] == "ready", "deviced did not become ready")
    return process, socket_path


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("deviced probe failure smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    deviced = resolve_binary("deviced", args.deviced, args.bin_dir)
    ensure_binary(deviced)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-deviced-failures-"))
    runtime_root = temp_root / "runtime"
    state_root = temp_root / "state"
    backend_state_path = state_root / "backend-state.json"
    input_root = state_root / "input"
    camera_root = state_root / "camera"
    input_root.mkdir(parents=True, exist_ok=True)
    camera_root.mkdir(parents=True, exist_ok=True)
    (input_root / "event0").write_text("keyboard\n")
    os.chmod(input_root, 0)

    env = os.environ.copy()
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    env.pop("AT_SPI_BUS_ADDRESS", None)
    env.update(
        {
            "PATH": "",
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root),
            "AIOS_DEVICED_STATE_DIR": str(state_root),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "captures.json"),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(state_root / "indicator-state.json"),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(backend_state_path),
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(state_root / "pipewire-0"),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_CAMERA_ENABLED": "1",
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(state_root / "screencast-state.json"),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(state_root / "pipewire-node.json"),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(state_root / "ui-tree-state.json"),
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "1",
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
        }
    )

    process: subprocess.Popen | None = None
    failed = False
    try:
        process, socket_path = start_deviced(deviced, env, args.timeout)
        state = rpc_call(socket_path, "device.state.get", {}, timeout=args.timeout)

        backend_status_map = {item["modality"]: item for item in state["backend_statuses"]}
        require(
            backend_status_map["screen"]["readiness"] == "session-unavailable",
            "screen readiness should be session-unavailable",
        )
        require(
            backend_status_map["audio"]["readiness"] == "dependency-missing",
            "audio readiness should be dependency-missing",
        )
        require(
            backend_status_map["input"]["readiness"] == "permission-denied",
            "input readiness should be permission-denied",
        )
        require(
            backend_status_map["camera"]["readiness"] == "device-missing",
            "camera readiness should be device-missing",
        )
        require(
            backend_status_map["ui_tree"]["readiness"] == "session-unavailable",
            "ui_tree readiness should be session-unavailable",
        )
        for modality in ["screen", "audio", "input", "camera", "ui_tree"]:
            require(backend_status_map[modality]["available"] is False, f"{modality} should be unavailable")

        adapter_map = {item["modality"]: item for item in state["capture_adapters"]}
        for modality in ["screen", "audio", "input", "camera"]:
            require(
                adapter_map[modality]["execution_path"] == "builtin-preview",
                f"{modality} should fall back to builtin-preview",
            )

        screen_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "screen",
                "session_id": "failure-session-1",
                "continuous": False,
                "window_ref": "window-1",
            },
            timeout=args.timeout,
        )
        require(screen_capture["preview_object"]["adapter_execution_path"] == "builtin-preview", "screen fallback path mismatch")
        require(
            "ui_tree supported but no adapter source resolved" in screen_capture["preview_object"]["adapter_notes"],
            "screen preview should report missing ui_tree adapter",
        )

        backend_state = json.loads(backend_state_path.read_text())
        require(
            any(note.startswith("available_backends=0") for note in backend_state["notes"]),
            "backend availability note mismatch",
        )

        print("deviced probe-failure smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"deviced probe-failure smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        if input_root.exists():
            os.chmod(input_root, stat.S_IRWXU)
        if args.keep_state or failed:
            print(f"state kept at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
