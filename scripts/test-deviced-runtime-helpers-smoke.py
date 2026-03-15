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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS deviced runtime-helper smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing deviced binary")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--keep-state", action="store_true")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(repo_root()) / name


def ensure_binary(path: Path) -> None:
    if path.exists():
        return
    raise SystemExit(f"missing binary: {path}")


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
    raise TimeoutError(f"timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception:
            time.sleep(0.1)
    raise TimeoutError("timed out waiting for deviced health")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    args = parse_args()
    deviced = resolve_binary("deviced", args.deviced, args.bin_dir)
    ensure_binary(deviced)

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-devh-",
            dir="/tmp" if Path("/tmp").exists() else None,
        )
    )
    runtime_root = temp_root / "runtime"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    backend_state_path = state_root / "backend-state.json"
    pipewire_socket_path = state_root / "pipewire-0"
    input_root = state_root / "input"
    camera_root = state_root / "camera"
    screencast_state_path = state_root / "screencast-state.json"
    pipewire_node_path = state_root / "pipewire-node.json"
    indicator_state_path = state_root / "indicator-state.json"
    pipewire_socket_path.write_text("ready\n", encoding="utf-8")
    input_root.mkdir(parents=True, exist_ok=True)
    (input_root / "event0").write_text("keyboard\n", encoding="utf-8")
    camera_root.mkdir(parents=True, exist_ok=True)
    (camera_root / "video0").write_text("ready\n", encoding="utf-8")
    screencast_state_path.write_text(
        json.dumps(
            {
                "portal_session_ref": "portal-helper-1",
                "stream_node_id": 420,
                "resolution": "1280x720",
            }
        ),
        encoding="utf-8",
    )
    pipewire_node_path.write_text(
        json.dumps({"node_id": 77, "channel_layout": "stereo"}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    env.update(
        {
            "PATH": "",
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root),
            "AIOS_DEVICED_STATE_DIR": str(state_root),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "captures.json"),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(indicator_state_path),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(backend_state_path),
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_CAMERA_ENABLED": "1",
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "0",
            "AIOS_DEVICED_HELPER_PYTHON": sys.executable,
        }
    )

    process = subprocess.Popen(
        [str(deviced)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    failed = False
    try:
        socket_path = Path(env["AIOS_DEVICED_SOCKET_PATH"])
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        require(
            any(note == "screen_live_command_configured=true" for note in health["notes"]),
            "screen helper command should be configured by default",
        )
        require(
            any(note == "audio_live_command_configured=true" for note in health["notes"]),
            "audio helper command should be configured by default",
        )
        require(
            any(note == "input_live_command_configured=true" for note in health["notes"]),
            "input helper command should be configured by default",
        )
        require(
            any(note == "camera_live_command_configured=true" for note in health["notes"]),
            "camera helper command should be configured by default",
        )

        screen_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "screen",
                "session_id": "session-1",
                "task_id": "task-screen",
                "continuous": False,
                "window_ref": "window-1",
            },
            timeout=args.timeout,
        )
        audio_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "audio",
                "session_id": "session-1",
                "task_id": "task-audio",
                "continuous": False,
                "source_device": "default-mic",
            },
            timeout=args.timeout,
        )
        input_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "input",
                "session_id": "session-1",
                "task_id": "task-input",
                "continuous": False,
                "source_device": "keyboard-1",
            },
            timeout=args.timeout,
        )
        camera_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "camera",
                "session_id": "session-1",
                "task_id": "task-camera",
                "continuous": False,
                "source_device": "camera-1",
            },
            timeout=args.timeout,
        )

        require(
            screen_capture["preview_object"]["release_grade_backend"] == "portal-screen-helper",
            "screen runtime helper marker mismatch",
        )
        require(
            audio_capture["preview_object"]["release_grade_backend"] == "pipewire-audio-helper",
            "audio runtime helper marker mismatch",
        )
        require(
            input_capture["preview_object"]["collector"] == "libinput-live",
            "input runtime helper collector mismatch",
        )
        require(
            camera_capture["preview_object"]["release_grade_backend"] == "camera-v4l-helper",
            "camera runtime helper marker mismatch",
        )
        require(
            screen_capture["preview_object"]["session_contract"]["contract_kind"]
            == "release-grade-native-helper",
            "screen helper should expose session contract",
        )
        require(
            screen_capture["preview_object"]["request_binding"]["task_id"] == "task-screen",
            "screen helper request binding mismatch",
        )
        require(
            screen_capture["preview_object"]["transport"]["kind"] == "portal+pipewire",
            "screen helper transport mismatch",
        )
        require(
            audio_capture["preview_object"]["transport"]["kind"] == "pipewire",
            "audio helper transport mismatch",
        )
        require(
            audio_capture["preview_object"]["request_binding"]["task_id"] == "task-audio",
            "audio helper request binding mismatch",
        )
        require(
            input_capture["preview_object"]["evidence"]["state_ref"] == str(input_root),
            "input helper evidence state_ref mismatch",
        )
        require(
            input_capture["preview_object"]["media_pipeline"]["collector"] == "libinput-live",
            "input helper media pipeline collector mismatch",
        )
        require(
            camera_capture["preview_object"]["transport"]["stream_ref"]
            == str(camera_root / "video0"),
            "camera helper transport stream ref mismatch",
        )
        require(
            camera_capture["preview_object"]["request_binding"]["task_id"] == "task-camera",
            "camera helper request binding mismatch",
        )

        backend_state = json.loads(backend_state_path.read_text(encoding="utf-8"))
        backend_statuses = {item["modality"]: item for item in backend_state["statuses"]}
        for modality in ("screen", "audio", "input", "camera"):
            require(
                backend_statuses[modality]["readiness"] == "native-live",
                f"{modality} helper should report native-live",
            )

        print(
            json.dumps(
                {
                    "screen_backend": screen_capture["preview_object"]["release_grade_backend"],
                    "screen_contract": screen_capture["preview_object"]["session_contract"]["contract_kind"],
                    "audio_backend": audio_capture["preview_object"]["release_grade_backend"],
                    "audio_transport": audio_capture["preview_object"]["transport"]["kind"],
                    "input_collector": input_capture["preview_object"]["collector"],
                    "input_evidence": input_capture["preview_object"]["evidence"]["state_ref"],
                    "camera_backend": camera_capture["preview_object"]["release_grade_backend"],
                    "camera_stream_ref": camera_capture["preview_object"]["transport"]["stream_ref"],
                    "backend_state_path": str(backend_state_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception:
        failed = True
        raise
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        preserve_state = failed or args.keep_state
        if preserve_state:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
