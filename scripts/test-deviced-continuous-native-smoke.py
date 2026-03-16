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

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS deviced continuous native capture smoke harness")
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
    if not path.exists():
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def wait_for_collectors(socket_path: Path, count: int, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = rpc_call(socket_path, "device.state.get", {}, timeout=1.0)
        collectors = state.get("continuous_collectors", [])
        if len(collectors) >= count and all(item.get("sample_count", 0) >= 1 for item in collectors):
            return state
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for continuous collectors to emit samples")


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("deviced continuous native smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    deviced = resolve_binary("deviced", args.deviced, args.bin_dir)
    ensure_binary(deviced)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-deviced-continuous-"))
    runtime_root = temp_root / "runtime"
    state_root = temp_root / "state"
    backend_state_path = state_root / "backend-state.json"
    continuous_state_path = state_root / "continuous-captures.json"
    pipewire_socket_path = state_root / "pipewire-0"
    input_root = state_root / "input"
    camera_root = state_root / "camera"
    screencast_state_path = state_root / "screencast-state.json"
    pipewire_node_path = state_root / "pipewire-node.json"
    ui_tree_state_path = state_root / "ui-tree-state.json"
    pipewire_socket_path.parent.mkdir(parents=True, exist_ok=True)
    input_root.mkdir(parents=True, exist_ok=True)
    camera_root.mkdir(parents=True, exist_ok=True)
    pipewire_socket_path.write_text("ready\n")
    (input_root / "event0").write_text("keyboard\n")
    (camera_root / "video0").write_text("ready\n")
    screencast_state_path.write_text(
        json.dumps(
            {
                "portal_session_ref": "session-portal-continuous",
                "stream_node_id": 101,
                "resolution": "1920x1080",
            }
        )
    )
    pipewire_node_path.write_text(
        json.dumps(
            {
                "node_id": 88,
                "channel_layout": "stereo",
            }
        )
    )
    ui_tree_state_path.write_text(json.dumps({"snapshot_id": "tree-continuous-1"}))

    env = os.environ.copy()
    env.update(
        {
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root),
            "AIOS_DEVICED_STATE_DIR": str(state_root),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "captures.json"),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(state_root / "indicator-state.json"),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(backend_state_path),
            "AIOS_DEVICED_CONTINUOUS_CAPTURE_STATE_PATH": str(continuous_state_path),
            "AIOS_DEVICED_CONTINUOUS_CAPTURE_INTERVAL_MS": "100",
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_CAMERA_ENABLED": "1",
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(ui_tree_state_path),
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "1",
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
        }
    )

    process: subprocess.Popen | None = None
    failed = False
    try:
        process = launch(deviced, env)
        socket_path = Path(env["AIOS_DEVICED_SOCKET_PATH"])
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        require(
            any(note == f"continuous_capture_state_path={continuous_state_path}" for note in health["notes"]),
            "continuous capture state health note missing",
        )

        requests = [
            {"modality": "screen", "continuous": True, "window_ref": None, "source_device": None},
            {"modality": "audio", "continuous": True, "window_ref": None, "source_device": "default-mic"},
            {"modality": "input", "continuous": True, "window_ref": None, "source_device": "keyboard-1"},
            {"modality": "camera", "continuous": True, "window_ref": None, "source_device": "camera-1"},
        ]
        capture_ids: list[str] = []
        for request in requests:
            response = rpc_call(socket_path, "device.capture.request", request, timeout=args.timeout)
            capture_ids.append(response["capture"]["capture_id"])

        state = wait_for_collectors(socket_path, 4, args.timeout)
        collectors = {item["modality"]: item for item in state["continuous_collectors"]}
        for modality in ("screen", "audio", "input", "camera"):
            require(modality in collectors, f"missing continuous collector for {modality}")
            require(
                collectors[modality]["collector_mode"] == "native-interval",
                f"{modality} collector mode mismatch",
            )
            require(
                collectors[modality]["status"] == "running",
                f"{modality} collector status mismatch",
            )
            require(
                collectors[modality]["sample_count"] >= 1,
                f"{modality} collector sample count mismatch",
            )

        require(continuous_state_path.exists(), "continuous capture state file missing")
        continuous_state = read_json(continuous_state_path)
        require(len(continuous_state["collectors"]) == 4, "continuous capture state collector count mismatch")

        refreshed_state = rpc_call(socket_path, "device.state.get", {}, timeout=args.timeout)
        backend_state = read_json(backend_state_path)
        require(
            len(backend_state["continuous_collectors"]) == len(refreshed_state["continuous_collectors"]) == 4,
            "backend state continuous collector mismatch",
        )

        for capture_id in capture_ids:
            rpc_call(
                socket_path,
                "device.capture.stop",
                {"capture_id": capture_id, "reason": "continuous-smoke-stop"},
                timeout=args.timeout,
            )

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            final_state = rpc_call(socket_path, "device.state.get", {}, timeout=1.0)
            if final_state.get("continuous_collectors") == [] and final_state.get("active_captures") == []:
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("continuous collectors did not stop cleanly")

        print("deviced continuous native smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"deviced continuous native smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        if args.keep_state or failed:
            print(f"state kept at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
