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
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(repo_root()), name)


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


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


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        process.send_signal(signal.SIGINT)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("deviced runtime helpers smoke skipped: unix rpc transport unsupported on this platform")
        return 0
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
            screen_capture["preview_object"]["release_grade_backend"]
            == "xdg-desktop-portal-screencast",
            "screen runtime helper backend mismatch",
        )
        require(
            screen_capture["preview_object"]["release_grade_backend_origin"]
            == "runtime-helper",
            "screen runtime helper origin mismatch",
        )
        require(
            screen_capture["preview_object"]["release_grade_backend_stack"]
            == "portal+pipewire",
            "screen runtime helper stack mismatch",
        )
        require(
            audio_capture["preview_object"]["release_grade_backend"] == "pipewire",
            "audio runtime helper backend mismatch",
        )
        require(
            audio_capture["preview_object"]["release_grade_backend_origin"] == "os-native",
            "audio runtime helper origin mismatch",
        )
        require(
            input_capture["preview_object"]["release_grade_backend"] == "libinput",
            "input runtime helper backend mismatch",
        )
        require(
            input_capture["preview_object"]["release_grade_backend_origin"]
            == "state-enumeration",
            "input runtime helper origin mismatch",
        )
        require(
            input_capture["preview_object"]["collector"] == "libinput-live",
            "input runtime helper collector mismatch",
        )
        require(
            camera_capture["preview_object"]["release_grade_backend"] == "v4l2",
            "camera runtime helper backend mismatch",
        )
        require(
            camera_capture["preview_object"]["release_grade_backend_origin"]
            == "state-enumeration",
            "camera runtime helper origin mismatch",
        )
        require(
            screen_capture["preview_object"]["session_contract"]["contract_kind"]
            == "release-grade-runtime-helper",
            "screen helper should expose runtime helper contract",
        )
        require(
            screen_capture["preview_object"]["release_grade_contract_kind"]
            == "release-grade-runtime-helper",
            "screen helper contract kind mismatch",
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
                    "screen_origin": screen_capture["preview_object"]["release_grade_backend_origin"],
                    "screen_contract": screen_capture["preview_object"]["session_contract"]["contract_kind"],
                    "audio_backend": audio_capture["preview_object"]["release_grade_backend"],
                    "audio_origin": audio_capture["preview_object"]["release_grade_backend_origin"],
                    "audio_transport": audio_capture["preview_object"]["transport"]["kind"],
                    "input_backend": input_capture["preview_object"]["release_grade_backend"],
                    "input_origin": input_capture["preview_object"]["release_grade_backend_origin"],
                    "input_collector": input_capture["preview_object"]["collector"],
                    "input_evidence": input_capture["preview_object"]["evidence"]["state_ref"],
                    "camera_backend": camera_capture["preview_object"]["release_grade_backend"],
                    "camera_origin": camera_capture["preview_object"]["release_grade_backend_origin"],
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
            stop_process(process)
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

