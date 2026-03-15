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

from aios_cargo_bins import default_aios_bin_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS deviced readiness-matrix smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing deviced binary")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
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


def terminate(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
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
    deviced = resolve_binary("deviced", args.deviced, args.bin_dir)
    ensure_binary(deviced)

    temp_root = Path(tempfile.mkdtemp(prefix="adrm-", dir="/tmp"))
    runtime_root = temp_root / "runtime"
    state_root = temp_root / "state"
    backend_state_path = state_root / "backend-state.json"
    support_matrix_path = state_root / "ui-tree-support-matrix.json"
    pipewire_socket_path = state_root / "pipewire-0"
    input_root = state_root / "input"
    camera_root = state_root / "camera"
    input_root.mkdir(parents=True, exist_ok=True)
    camera_root.mkdir(parents=True, exist_ok=True)
    pipewire_socket_path.parent.mkdir(parents=True, exist_ok=True)
    pipewire_socket_path.write_text("ready\n")
    (input_root / "event0").write_text("keyboard\n")
    (camera_root / "video0").write_text("ready\n")

    failing_probe = "printf 'probe failed\\n' >&2; exit 7"
    env = os.environ.copy()
    env.update(
        {
            "PATH": "",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/deviced-test-session-bus",
            "AT_SPI_BUS_ADDRESS": "unix:path=/tmp/deviced-test-atspi-bus",
            "XDG_CURRENT_DESKTOP": "AIOS-SMOKE",
            "XDG_SESSION_TYPE": "wayland",
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
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(state_root / "screencast-state.json"),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(state_root / "pipewire-node.json"),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(state_root / "ui-tree-state.json"),
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "1",
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
            "AIOS_DEVICED_SCREEN_PROBE_COMMAND": failing_probe,
            "AIOS_DEVICED_AUDIO_PROBE_COMMAND": failing_probe,
            "AIOS_DEVICED_INPUT_PROBE_COMMAND": failing_probe,
            "AIOS_DEVICED_CAMERA_PROBE_COMMAND": failing_probe,
            "AIOS_DEVICED_UI_TREE_PROBE_COMMAND": failing_probe,
        }
    )

    process: subprocess.Popen | None = None
    failed = False
    try:
        process, socket_path = start_deviced(deviced, env, args.timeout)
        state = rpc_call(socket_path, "device.state.get", {}, timeout=args.timeout)

        backend_status_map = {item["modality"]: item for item in state["backend_statuses"]}
        require(
            backend_status_map["screen"]["available"] is False
            and backend_status_map["screen"]["readiness"] == "native-ready",
            "screen backend should be native-ready without live stream state",
        )
        require(
            backend_status_map["audio"]["available"] is True
            and backend_status_map["audio"]["readiness"] == "native-ready",
            "audio backend should be native-ready with PipeWire socket only",
        )
        require(
            backend_status_map["input"]["available"] is True
            and backend_status_map["input"]["readiness"] == "native-live",
            "input backend should stay native-live from enumerated devices",
        )
        require(
            backend_status_map["camera"]["available"] is True
            and backend_status_map["camera"]["readiness"] == "native-live",
            "camera backend should stay native-live from enumerated devices",
        )
        require(
            backend_status_map["ui_tree"]["available"] is False
            and backend_status_map["ui_tree"]["readiness"] == "native-ready",
            "ui_tree backend should be native-ready on AT-SPI bus only",
        )
        ui_tree_support_matrix = {item["environment_id"]: item for item in state["ui_tree_support_matrix"]}
        require(
            ui_tree_support_matrix["current-session"]["readiness"] == "native-ready",
            "ui_tree current-session support mismatch",
        )
        require(
            ui_tree_support_matrix["current-session"]["current"] is True,
            "ui_tree current-session row should be marked current",
        )
        require(
            ui_tree_support_matrix["current-session"]["desktop_environment"] == "AIOS-SMOKE",
            "ui_tree current-session desktop environment mismatch",
        )
        require(
            ui_tree_support_matrix["current-session"]["session_type"] == "wayland",
            "ui_tree current-session session type mismatch",
        )
        require(
            ui_tree_support_matrix["current-session"]["stability"] == "declared-ready",
            "ui_tree current-session stability mismatch",
        )
        require(
            ui_tree_support_matrix["atspi-live"]["available"] is True,
            "ui_tree atspi-live support should remain available with AT-SPI bus",
        )
        require(
            ui_tree_support_matrix["atspi-live"]["stability"] == "best-effort-live",
            "ui_tree atspi-live stability mismatch",
        )
        require(
            ui_tree_support_matrix["screen-ocr-fallback"]["available"] is True,
            "ui_tree OCR fallback route should always remain available",
        )
        require(
            ui_tree_support_matrix["screen-ocr-fallback"]["stability"] == "fallback-only",
            "ui_tree OCR fallback stability mismatch",
        )
        require(
            "support_matrix_path=" + str(support_matrix_path) in ui_tree_support_matrix["current-session"]["evidence"],
            "ui_tree current-session evidence missing support matrix path",
        )
        for modality in ["screen", "audio", "input", "camera", "ui_tree"]:
            require(
                "probe_readiness=probe-failed" in backend_status_map[modality]["details"],
                f"{modality} backend should preserve probe failure detail",
            )

        adapter_map = {item["modality"]: item for item in state["capture_adapters"]}
        require(
            adapter_map["screen"]["adapter_id"] == "screen.portal-ready"
            and adapter_map["screen"]["execution_path"] == "native-ready",
            "screen adapter should resolve to native-ready",
        )
        require(
            adapter_map["audio"]["adapter_id"] == "audio.pipewire-ready"
            and adapter_map["audio"]["execution_path"] == "native-ready",
            "audio adapter should resolve to native-ready",
        )
        require(
            adapter_map["input"]["adapter_id"] == "input.libinput-state-root"
            and adapter_map["input"]["execution_path"] == "native-state-bridge",
            "input adapter should resolve to native-state-bridge",
        )
        require(
            adapter_map["camera"]["adapter_id"] == "camera.v4l-state-root"
            and adapter_map["camera"]["execution_path"] == "native-state-bridge",
            "camera adapter should resolve to native-state-bridge",
        )

        screen_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "screen",
                "session_id": "matrix-session-1",
                "continuous": False,
                "window_ref": "window-1",
            },
            timeout=args.timeout,
        )
        require(screen_capture["preview_object"]["capture_mode"] == "native-ready", "screen capture mode mismatch")
        require(screen_capture["preview_object"]["adapter_id"] == "screen.portal-ready", "screen adapter mismatch")
        require(
            screen_capture["preview_object"]["adapter_execution_path"] == "native-ready",
            "screen adapter execution path mismatch",
        )
        require(screen_capture["preview_object"]["backend_ready"] is True, "screen backend_ready missing")
        require(screen_capture["preview_object"]["portal_session_bus"] is True, "screen portal bus note missing")
        require("ui_tree_snapshot" in screen_capture["preview_object"], "screen preview should attach ui_tree snapshot")
        require(
            screen_capture["preview_object"]["ui_tree_snapshot"]["adapter_id"] == "ui_tree.atspi-ready",
            "screen preview should attach native-ready ui_tree adapter",
        )
        require(
            screen_capture["preview_object"]["ui_tree_snapshot"]["capture_mode"] == "native-ready",
            "ui_tree snapshot should expose native-ready mode",
        )
        require(
            screen_capture["preview_object"]["ui_tree_snapshot"]["backend_ready"] is True,
            "ui_tree native-ready snapshot should mark backend_ready",
        )

        audio_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "audio",
                "continuous": True,
                "source_device": "default-mic",
            },
            timeout=args.timeout,
        )
        require(audio_capture["preview_object"]["capture_mode"] == "native-ready", "audio capture mode mismatch")
        require(audio_capture["preview_object"]["adapter_id"] == "audio.pipewire-ready", "audio adapter mismatch")
        require(
            audio_capture["preview_object"]["adapter_execution_path"] == "native-ready",
            "audio adapter execution path mismatch",
        )
        require(audio_capture["preview_object"]["backend_ready"] is True, "audio backend_ready missing")
        require(audio_capture["preview_object"]["backend_source"] == "pipewire-socket", "audio backend source mismatch")
        require(audio_capture["preview_object"].get("pipewire_node") is None, "audio preview should not expose missing node")

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
            input_capture["preview_object"]["capture_mode"] == "native-state-bridge",
            "input capture mode mismatch",
        )
        require(
            input_capture["preview_object"]["adapter_id"] == "input.libinput-state-root",
            "input adapter mismatch",
        )
        require(
            input_capture["preview_object"]["adapter_execution_path"] == "native-state-bridge",
            "input adapter execution path mismatch",
        )
        require(input_capture["preview_object"]["device_count"] == 1, "input device count mismatch")
        require(input_capture["preview_object"]["input_devices"] == ["event0"], "input device list mismatch")

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
        require(
            camera_capture["preview_object"]["capture_mode"] == "native-state-bridge",
            "camera capture mode mismatch",
        )
        require(
            camera_capture["preview_object"]["adapter_id"] == "camera.v4l-state-root",
            "camera adapter mismatch",
        )
        require(
            camera_capture["preview_object"]["adapter_execution_path"] == "native-state-bridge",
            "camera adapter execution path mismatch",
        )
        require(
            camera_capture["preview_object"]["device_path"].endswith("video0"),
            "camera device path mismatch",
        )

        backend_state = json.loads(backend_state_path.read_text())
        require(
            any(note == "available_backends=3" for note in backend_state["notes"]),
            "backend availability note mismatch",
        )
        adapter_paths = next((note for note in backend_state["notes"] if note.startswith("adapter_paths=")), "")
        require("screen:native-ready" in adapter_paths, "backend adapter paths missing screen native-ready")
        require("audio:native-ready" in adapter_paths, "backend adapter paths missing audio native-ready")
        require("input:native-state-bridge" in adapter_paths, "backend adapter paths missing input native-state-bridge")
        require("camera:native-state-bridge" in adapter_paths, "backend adapter paths missing camera native-state-bridge")
        backend_matrix = {item["environment_id"]: item for item in backend_state["ui_tree_support_matrix"]}
        require(
            backend_matrix["current-session"]["readiness"] == "native-ready",
            "backend-state current-session ui_tree matrix mismatch",
        )
        require(
            backend_matrix["state-bridge"]["available"] is False,
            "backend-state should report ui_tree state-bridge unavailable without state file",
        )
        require(support_matrix_path.exists(), "ui_tree support matrix artifact missing")
        support_matrix_artifact = json.loads(support_matrix_path.read_text())
        require(
            support_matrix_artifact["backend_snapshot_path"] == str(backend_state_path),
            "ui_tree support matrix artifact backend snapshot path mismatch",
        )
        artifact_rows = {item["environment_id"]: item for item in support_matrix_artifact["entries"]}
        require(
            artifact_rows["atspi-live"]["stability"] == "best-effort-live",
            "ui_tree support matrix artifact atspi stability mismatch",
        )
        require(
            "long-run collector stability evidence is still accumulating"
            in artifact_rows["atspi-live"]["limitations"],
            "ui_tree support matrix artifact limitations mismatch",
        )

        print("deviced readiness-matrix smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"deviced readiness-matrix smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        if args.keep_state or failed:
            print(f"state kept at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
