#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS deviced native-backend smoke harness")
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
        print("deviced native backend smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    deviced = resolve_binary("deviced", args.deviced, args.bin_dir)
    ensure_binary(deviced)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-deviced-native-"))
    runtime_root = temp_root / "runtime"
    state_root = temp_root / "state"
    backend_state_path = state_root / "backend-state.json"
    backend_evidence_dir = state_root / "backend-evidence"
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
                "portal_session_ref": "portal-session-1",
                "stream_node_id": 42,
                "window_ref": "window-1",
                "resolution": "1280x720",
            }
        )
    )
    pipewire_node_path.write_text(json.dumps({"node_id": 77, "channel_layout": "stereo"}))
    ui_tree_state_path.write_text(json.dumps({"snapshot_id": "tree-native-1", "focus_node": "button-1"}))

    screen_live_payload = {
        "available": True,
        "readiness": "native-live",
        "payload": {
            "release_grade_backend": "xdg-desktop-portal-screencast",
            "release_grade_backend_id": "xdg-desktop-portal-screencast",
            "release_grade_backend_origin": "os-native",
            "release_grade_backend_stack": "portal+pipewire",
            "release_grade_contract_kind": "release-grade-runtime-helper",
            "stream_node_id": 142,
            "portal_session_ref": "portal-release-1",
        },
    }
    audio_live_payload = {
        "available": True,
        "readiness": "native-live",
        "payload": {
            "release_grade_backend": "pipewire",
            "release_grade_backend_id": "pipewire",
            "release_grade_backend_origin": "os-native",
            "release_grade_backend_stack": "pipewire",
            "release_grade_contract_kind": "release-grade-runtime-helper",
            "sample_rate_hz": 48000,
        },
    }
    input_live_payload = {
        "available": True,
        "readiness": "native-live",
        "payload": {
            "release_grade_backend": "libinput",
            "release_grade_backend_id": "libinput",
            "release_grade_backend_origin": "os-native",
            "release_grade_backend_stack": "libinput",
            "release_grade_contract_kind": "release-grade-runtime-helper",
            "collector": "libinput-live",
        },
    }
    camera_live_payload = {
        "available": True,
        "readiness": "native-live",
        "payload": {
            "release_grade_backend": "v4l2",
            "release_grade_backend_id": "v4l2",
            "release_grade_backend_origin": "os-native",
            "release_grade_backend_stack": "v4l2",
            "release_grade_contract_kind": "release-grade-runtime-helper",
            "pixel_format": "MJPEG",
            "device_path": str(camera_root / "video0"),
        },
    }
    screen_live_command = (
        f"{sys.executable} -c "
        + shlex.quote(f"import json; print(json.dumps({screen_live_payload!r}))")
    )
    audio_live_command = (
        f"{sys.executable} -c "
        + shlex.quote(f"import json; print(json.dumps({audio_live_payload!r}))")
    )
    input_live_command = (
        f"{sys.executable} -c "
        + shlex.quote(f"import json; print(json.dumps({input_live_payload!r}))")
    )
    camera_live_command = (
        f"{sys.executable} -c "
        + shlex.quote(f"import json; print(json.dumps({camera_live_payload!r}))")
    )

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
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_CAMERA_ENABLED": "1",
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(ui_tree_state_path),
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "1",
            "AIOS_DEVICED_SCREEN_LIVE_COMMAND": screen_live_command,
            "AIOS_DEVICED_AUDIO_LIVE_COMMAND": audio_live_command,
            "AIOS_DEVICED_INPUT_LIVE_COMMAND": input_live_command,
            "AIOS_DEVICED_CAMERA_LIVE_COMMAND": camera_live_command,
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
        }
    )

    process: subprocess.Popen | None = None
    failed = False
    try:
        process, socket_path = start_deviced(deviced, env, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        require(
            any(note == "screen_live_command_configured=true" for note in health["notes"]),
            "screen live command health note missing",
        )
        require(
            any(note == "audio_live_command_configured=true" for note in health["notes"]),
            "audio live command health note missing",
        )
        state = rpc_call(socket_path, "device.state.get", {}, timeout=args.timeout)

        backend_status_map = {item["modality"]: item for item in state["backend_statuses"]}
        for modality in ["screen", "audio", "input", "camera", "ui_tree"]:
            require(backend_status_map[modality]["available"] is True, f"{modality} should be available")
            require(
                backend_status_map[modality]["readiness"] == "native-live",
                f"{modality} readiness should be native-live",
            )
            evidence_artifact = backend_evidence_dir / f"{modality}-backend-evidence.json"
            require(evidence_artifact.exists(), f"{modality} backend evidence artifact missing")
            require(
                any(
                    item == f"evidence_artifact={evidence_artifact}"
                    for item in backend_status_map[modality]["details"]
                ),
                f"{modality} backend status missing evidence artifact detail",
            )

        adapter_map = {item["modality"]: item for item in state["capture_adapters"]}
        require(adapter_map["screen"]["adapter_id"] == "screen.portal-native", "screen adapter mismatch")
        require(adapter_map["audio"]["adapter_id"] == "audio.pipewire-native", "audio adapter mismatch")
        require(adapter_map["input"]["adapter_id"] == "input.libinput-native", "input adapter mismatch")
        require(adapter_map["camera"]["adapter_id"] == "camera.v4l-native", "camera adapter mismatch")
        for modality in ["screen", "audio", "input", "camera"]:
            require(
                adapter_map[modality]["execution_path"] == "native-live",
                f"{modality} adapter should use native-live",
            )

        screen_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "screen",
                "session_id": "native-session-1",
                "continuous": False,
                "window_ref": "window-1",
            },
            timeout=args.timeout,
        )
        require(screen_capture["preview_object"]["capture_mode"] == "native-live", "screen capture mode mismatch")
        require(screen_capture["preview_object"]["stream_node_id"] == 142, "screen stream node missing")
        require(screen_capture["preview_object"]["adapter_id"] == "screen.portal-native", "screen adapter id mismatch")
        require(
            screen_capture["preview_object"]["release_grade_backend"] == "xdg-desktop-portal-screencast",
            "screen live backend marker missing",
        )
        require(
            screen_capture["preview_object"]["release_grade_backend_origin"] == "os-native",
            "screen live backend origin missing",
        )
        require(
            screen_capture["preview_object"]["release_grade_backend_stack"] == "portal+pipewire",
            "screen live backend stack missing",
        )
        require(
            screen_capture["preview_object"]["ui_tree_snapshot"]["adapter_id"] == "ui_tree.atspi-native",
            "ui_tree adapter id mismatch",
        )
        require(
            screen_capture["preview_object"]["adapter_contract"] == "formal-native-backend",
            "screen adapter contract mismatch",
        )

        camera_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "camera",
                "continuous": False,
                "source_device": "camera-1",
            },
            timeout=args.timeout,
        )
        require(camera_capture["preview_object"]["capture_mode"] == "native-live", "camera capture mode mismatch")
        require(camera_capture["preview_object"]["adapter_id"] == "camera.v4l-native", "camera adapter id mismatch")
        require(
            camera_capture["preview_object"]["release_grade_backend"] == "v4l2",
            "camera live backend marker missing",
        )
        require(
            camera_capture["preview_object"]["release_grade_backend_origin"] == "os-native",
            "camera live backend origin missing",
        )
        require(camera_capture["preview_object"]["device_path"].endswith("video0"), "camera device path mismatch")
        require(
            camera_capture["preview_object"]["pixel_format"] == "MJPEG",
            "camera live backend pixel format missing",
        )

        input_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "input",
                "continuous": False,
                "source_device": "keyboard-1",
            },
            timeout=args.timeout,
        )
        require(
            input_capture["preview_object"]["release_grade_backend"] == "libinput",
            "input live backend marker missing",
        )
        require(
            input_capture["preview_object"]["release_grade_backend_origin"] == "os-native",
            "input live backend origin missing",
        )
        require(
            input_capture["preview_object"]["collector"] == "libinput-live",
            "input live collector marker missing",
        )

        audio_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "audio",
                "continuous": False,
                "source_device": "default-mic",
            },
            timeout=args.timeout,
        )
        require(
            audio_capture["preview_object"]["release_grade_backend"] == "pipewire",
            "audio live backend marker missing",
        )
        require(
            audio_capture["preview_object"]["release_grade_backend_origin"] == "os-native",
            "audio live backend origin missing",
        )
        require(
            audio_capture["preview_object"]["sample_rate_hz"] == 48000,
            "audio live backend sample rate missing",
        )

        backend_state = json.loads(backend_state_path.read_text())
        require(
            any(note.startswith("available_backends=5") for note in backend_state["notes"]),
            "backend availability note mismatch",
        )
        require(
            any(note.startswith("live_probes=") for note in backend_state["notes"]),
            "backend live probe note missing",
        )
        require(
            any(note == f"backend_evidence_dir={backend_evidence_dir}" for note in backend_state["notes"]),
            "backend evidence dir note missing",
        )
        require(
            any(note.startswith("backend_evidence_artifact_count=5") for note in backend_state["notes"]),
            "backend evidence artifact count note missing",
        )
        screen_artifact = json.loads((backend_evidence_dir / "screen-backend-evidence.json").read_text())
        require(screen_artifact["baseline"] == "os-native-backend", "screen evidence baseline mismatch")
        require(
            screen_artifact.get("release_grade_backend_id") == "xdg-desktop-portal-screencast",
            "screen evidence backend id mismatch",
        )
        require(
            screen_artifact.get("release_grade_backend_origin") == "os-native",
            "screen evidence backend origin mismatch",
        )
        require(
            screen_artifact.get("release_grade_backend_stack") == "portal+pipewire",
            "screen evidence backend stack mismatch",
        )
        require(
            screen_artifact.get("contract_kind") == "release-grade-runtime-helper",
            "screen evidence contract kind mismatch",
        )
        require(
            (((screen_artifact.get("probe") or {}).get("payload") or {}).get("release_grade_backend")
             == "xdg-desktop-portal-screencast"),
            "screen evidence probe payload mismatch",
        )
        require(
            ((screen_artifact.get("baseline_payload") or {}).get("stream_node_id") == 42),
            "screen evidence baseline payload mismatch",
        )
        ui_tree_artifact = json.loads((backend_evidence_dir / "ui_tree-backend-evidence.json").read_text())
        require(ui_tree_artifact["baseline"] == "state-bridge-baseline", "ui_tree evidence baseline mismatch")
        require(
            ((ui_tree_artifact.get("ui_tree_snapshot") or {}).get("focus_node") == "button-1"),
            "ui_tree evidence snapshot mismatch",
        )

        print("deviced native-backend smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"deviced native-backend smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        if args.keep_state or failed:
            print(f"state kept at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

