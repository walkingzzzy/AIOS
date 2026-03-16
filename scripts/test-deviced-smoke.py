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


UI_TREE_COLLECTOR = (
    Path(__file__).resolve().parent.parent
    / "aios/services/deviced/runtime/ui_tree_atspi_snapshot.py"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS deviced smoke harness")
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


def start_deviced(binary: Path, env: dict[str, str], timeout: float) -> tuple[subprocess.Popen, Path, dict]:
    process = launch(binary, env)
    socket_path = Path(env["AIOS_DEVICED_SOCKET_PATH"])
    wait_for_socket(socket_path, timeout)
    health = wait_for_health(socket_path, timeout)
    print(f"deviced ready: {health['status']} @ {health['socket_path']}")
    return process, socket_path, health


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("deviced smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    deviced = resolve_binary("deviced", args.deviced, args.bin_dir)
    ensure_binary(deviced)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-deviced-smoke-"))
    runtime_root = temp_root / "runtime"
    state_root = temp_root / "state"
    backend_state_path = state_root / "backend-state.json"
    pipewire_socket_path = state_root / "pipewire-0"
    input_root = state_root / "input"
    camera_root = state_root / "camera"
    screencast_state_path = state_root / "screencast-state.json"
    pipewire_node_path = state_root / "pipewire-node.json"
    ui_tree_state_path = state_root / "ui-tree-state.json"
    ui_tree_fixture_path = state_root / "ui-tree-live-fixture.json"
    observability_log_path = state_root / "observability.jsonl"
    pipewire_socket_path.parent.mkdir(parents=True, exist_ok=True)
    input_root.mkdir(parents=True, exist_ok=True)
    camera_root.mkdir(parents=True, exist_ok=True)
    pipewire_socket_path.write_text("ready\n")
    (input_root / "event0").write_text("keyboard\n")
    (camera_root / "video0").write_text("ready\n")
    screencast_state_path.write_text(
        json.dumps(
            {
                "portal_session_ref": "session-portal-1",
                "stream_node_id": 42,
                "window_ref": "window-1",
                "resolution": "1280x720",
            }
        )
    )
    pipewire_node_path.write_text(
        json.dumps(
            {
                "node_id": 77,
                "channel_layout": "stereo",
            }
        )
    )
    ui_tree_state_path.write_text(
        json.dumps(
            {
                "snapshot_id": "tree-native-1",
                "focus_node": "button-1",
            }
        )
    )
    ui_tree_fixture_path.write_text(
        json.dumps(
            {
                "snapshot_id": "tree-live-1",
                "applications": [
                    {
                        "node_id": "desktop-0/app-0",
                        "name": "AIOS Shell",
                        "role": "application",
                        "states": ["active"],
                        "children": [
                            {
                                "node_id": "desktop-0/app-0/0",
                                "name": "Approve",
                                "role": "push button",
                                "states": ["focused"],
                            }
                        ],
                    }
                ],
            }
        )
    )

    env = os.environ.copy()
    env.update(
        {
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root),
            "AIOS_DEVICED_STATE_DIR": str(state_root),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "captures.json"),
            "AIOS_DEVICED_OBSERVABILITY_LOG": str(observability_log_path),
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
            "AIOS_DEVICED_UI_TREE_LIVE_COMMAND": (
                f"{sys.executable} {UI_TREE_COLLECTOR} --fixture {ui_tree_fixture_path} --json"
            ),
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
            "AIOS_DEVICED_SCREEN_PROBE_COMMAND": "python3 -c 'import json; print(json.dumps({\"available\": True, \"readiness\": \"native-live\", \"payload\": {\"probe_frame\": True, \"probe_source_name\": \"screen-smoke\"}}))'",
            "AIOS_DEVICED_CAMERA_PROBE_COMMAND": "printf 'probe failed\\n' >&2; exit 7",
        }
    )

    process: subprocess.Popen | None = None
    failed = False
    try:
        indicator_state_path = Path(env["AIOS_DEVICED_INDICATOR_STATE_PATH"])
        backend_state_path = Path(env["AIOS_DEVICED_BACKEND_STATE_PATH"])
        capture_state_path = Path(env["AIOS_DEVICED_CAPTURE_STATE_PATH"])
        process, socket_path, health = start_deviced(deviced, env, args.timeout)
        require(
            any(note == f"backend_state_path={backend_state_path}" for note in health["notes"]),
            "backend state health note missing",
        )
        require(
            any(note == "screen_probe_command_configured=true" for note in health["notes"]),
            "screen probe health note missing",
        )
        require(
            any(note == "ui_tree_live_command_configured=true" for note in health["notes"]),
            "ui_tree live command health note missing",
        )

        state = rpc_call(socket_path, "device.state.get", {}, timeout=args.timeout)
        require(any(item["modality"] == "screen" for item in state["capabilities"]), "screen capability missing")
        require(any(item["modality"] == "screen" for item in state["capture_adapters"]), "screen adapter missing from rpc state")
        screen_capability = next(item for item in state["capabilities"] if item["modality"] == "screen")
        require(any(note == "adapter_id=screen.portal-probe" for note in screen_capability["notes"]), "screen capability adapter note missing")
        require(any(note == "approval_mode=metadata-only" for note in state["notes"]), "approval mode note missing")
        require(any(note.startswith("available_backends=") for note in state["notes"]), "backend availability note missing")
        require(any(note == f"backend_state_path={backend_state_path}" for note in state["notes"]), "backend state note missing")
        require(backend_state_path.exists(), "backend state file missing")
        backend_state = read_json(backend_state_path)
        backend_state_map = {item["modality"]: item for item in backend_state["statuses"]}
        require(backend_state_map["screen"]["readiness"] == "native-live", "backend snapshot screen mismatch")
        require(backend_state_map["audio"]["readiness"] == "native-live", "backend snapshot audio mismatch")
        require(backend_state_map["camera"]["readiness"] == "native-live", "backend snapshot camera mismatch")
        require(backend_state_map["ui_tree"]["readiness"] == "native-live", "backend snapshot ui_tree mismatch")
        adapter_map = {item["modality"]: item for item in backend_state["adapters"]}
        require(adapter_map["screen"]["execution_path"] == "native-live", "backend snapshot screen adapter path mismatch")
        require(adapter_map["screen"]["adapter_id"] == "screen.portal-probe", "backend snapshot screen adapter mismatch")
        require(adapter_map["audio"]["adapter_id"] == "audio.pipewire-native", "backend snapshot audio adapter mismatch")
        require(adapter_map["camera"]["execution_path"] == "native-state-bridge", "backend snapshot camera adapter path mismatch")
        require(adapter_map["camera"]["adapter_id"] == "camera.v4l-state-root", "backend snapshot camera adapter mismatch")
        configured_probes = next((note for note in backend_state["notes"] if note.startswith("configured_probes=")), "")
        require("screen" in configured_probes and "camera" in configured_probes, "backend snapshot configured probe note missing camera")
        screen_backend = next(item for item in state["backend_statuses"] if item["modality"] == "screen")
        audio_backend = next(item for item in state["backend_statuses"] if item["modality"] == "audio")
        input_backend = next(item for item in state["backend_statuses"] if item["modality"] == "input")
        camera_backend = next(item for item in state["backend_statuses"] if item["modality"] == "camera")
        ui_tree_backend = next(item for item in state["backend_statuses"] if item["modality"] == "ui_tree")
        require(screen_backend["readiness"] == "native-live", "screen backend readiness mismatch")
        require(audio_backend["readiness"] == "native-live", "audio backend readiness mismatch")
        require(input_backend["available"] is True, "input backend should be available")
        require(input_backend["readiness"] == "native-live", "input backend readiness mismatch")
        require(camera_backend["available"] is True, "camera backend should be available")
        require(camera_backend["readiness"] == "native-live", "camera backend readiness mismatch")
        require(ui_tree_backend["readiness"] == "native-live", "ui_tree backend readiness mismatch")
        require("collector=fixture" in ui_tree_backend["details"], "ui_tree backend collector detail missing")
        require(state["ui_tree_snapshot"]["snapshot_id"] == "tree-live-1", "device state ui_tree snapshot missing")
        require(
            state["ui_tree_snapshot"]["capture_mode"] == "native-live",
            "device state ui_tree capture mode mismatch",
        )
        require(
            state["ui_tree_snapshot"]["adapter_id"] == "ui_tree.atspi-native",
            "device state ui_tree adapter mismatch",
        )
        require(
            state["ui_tree_snapshot"]["focus_node"] == "desktop-0/app-0/0",
            "device state ui_tree focus mismatch",
        )

        screen_capture = rpc_call(
            socket_path,
            "device.capture.request",
            {
                "modality": "screen",
                "session_id": "session-1",
                "continuous": False,
                "window_ref": "window-1",
            },
            timeout=args.timeout,
        )
        require(screen_capture["capture"]["modality"] == "screen", "screen capture modality mismatch")
        require(screen_capture["preview_object"]["window_ref"] == "window-1", "screen preview window_ref mismatch")
        require(screen_capture["preview_object"]["capture_mode"] == "native-live", "screen native live missing")
        require(screen_capture["preview_object"]["stream_node_id"] == 42, "screen native stream id missing")
        require(screen_capture["preview_object"]["probe_frame"] is True, "screen probe payload missing")
        require(screen_capture["preview_object"]["probe_source_name"] == "screen-smoke", "screen probe source payload missing")
        require(screen_capture["preview_object"]["adapter_id"] == "screen.portal-probe", "screen adapter id missing")
        require(screen_capture["preview_object"]["adapter_execution_path"] == "native-live", "screen adapter path missing")
        require("ui_tree_adapter_id=ui_tree.atspi-native" in screen_capture["preview_object"]["adapter_notes"], "screen adapter notes missing ui_tree note")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["snapshot_id"] == "tree-live-1", "ui_tree snapshot missing")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["adapter_id"] == "ui_tree.atspi-native", "ui_tree snapshot adapter id missing")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["adapter_execution_path"] == "native-live", "ui_tree snapshot adapter path missing")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["adapter"]["backend"] == "at-spi", "ui_tree snapshot backend missing")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["adapter_contract"] == "formal-native-backend", "ui_tree snapshot adapter contract missing")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["collector"] == "fixture", "ui_tree snapshot collector mismatch")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["application_count"] == 1, "ui_tree snapshot application count mismatch")
        require(screen_capture["preview_object"]["ui_tree_snapshot"]["focus_node"] == "desktop-0/app-0/0", "ui_tree snapshot focus mismatch")
        require(screen_capture["capture"]["approval_status"] == "not-required", "screen approval metadata mismatch")
        require(
            screen_capture["capture"].get("approval_source")
            == screen_capture["preview_object"]["approval_context"]["approval_source"],
            "screen approval source mismatch",
        )
        require(screen_capture["capture"]["retention_class"] == "session", "screen retention metadata missing")
        require(screen_capture["capture"].get("adapter_id") == screen_capture["preview_object"]["adapter_id"], "screen capture adapter id mismatch")
        require(
            screen_capture["capture"].get("adapter_execution_path") == screen_capture["preview_object"]["adapter_execution_path"],
            "screen capture adapter path mismatch",
        )
        require(bool(screen_capture["capture"].get("indicator_id")), "screen indicator metadata missing")

        normalized = rpc_call(
            socket_path,
            "device.object.normalize",
            {
                "modality": "screen",
                "payload": screen_capture["preview_object"],
                "source_backend": "screen-capture-portal",
                "user_visible": True,
            },
            timeout=args.timeout,
        )
        require(normalized["object_kind"] == "screen_frame", "normalize object kind mismatch")
        require(normalized["normalized"]["ui_tree_snapshot"]["snapshot_id"] == "tree-live-1", "ui_tree snapshot missing after normalize")

        retention = rpc_call(
            socket_path,
            "device.retention.apply",
            {
                "object_kind": "screen_frame",
                "object_id": normalized["normalized"]["frame_id"],
                "continuous": False,
                "contains_sensitive_data": False,
            },
            timeout=args.timeout,
        )
        require(retention["retention_class"] == "session", "retention class mismatch")

        require(indicator_state_path.exists(), "indicator state file missing after screen capture")
        indicator_state = read_json(indicator_state_path)
        require(len(indicator_state["active"]) == 1, "screen capture should create one visible indicator")
        require(indicator_state["active"][0]["approval_status"] == "not-required", "screen indicator approval mismatch")

        stop_screen = rpc_call(
            socket_path,
            "device.capture.stop",
            {"capture_id": screen_capture["capture"]["capture_id"], "reason": "screen-done"},
            timeout=args.timeout,
        )
        require(stop_screen["capture"]["status"] == "stopped", "screen capture stop status mismatch")
        require(stop_screen["capture"]["stopped_reason"] == "screen-done", "screen capture stop reason mismatch")
        indicator_state = read_json(indicator_state_path)
        require(indicator_state["active"] == [], "screen stop should clear indicators")

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
        require(input_capture["capture"]["modality"] == "input", "input capture modality mismatch")
        require(input_capture["preview_object"]["capture_mode"] == "native-live", "input native live missing")
        require(input_capture["preview_object"]["adapter_id"] == "input.libinput-native", "input adapter id mismatch")
        require(input_capture["preview_object"]["adapter_contract"] == "formal-native-backend", "input adapter contract mismatch")
        require(input_capture["preview_object"]["adapter_execution_path"] == "native-live", "input adapter path mismatch")

        stop_input = rpc_call(
            socket_path,
            "device.capture.stop",
            {"capture_id": input_capture["capture"]["capture_id"], "reason": "input-done"},
            timeout=args.timeout,
        )
        require(stop_input["capture"]["status"] == "stopped", "input capture stop status mismatch")
        require(stop_input["capture"]["stopped_reason"] == "input-done", "input capture stop reason mismatch")
        indicator_state = read_json(indicator_state_path)
        require(indicator_state["active"] == [], "input stop should clear indicators")

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
        require(camera_capture["capture"]["modality"] == "camera", "camera capture modality mismatch")
        require(camera_capture["capture"]["approval_required"] is True, "camera capture should require approval")
        require(camera_capture["capture"]["approval_status"] == "required", "camera capture approval status mismatch")
        require(camera_capture["capture"].get("approval_source") == "unapproved", "camera capture approval source mismatch")
        require(camera_capture["capture"]["tainted"] is True, "camera capture should be tainted")
        require(camera_capture["capture"]["retention_class"] == "short", "camera capture retention should be short")
        require(camera_capture["capture"]["retention_ttl_seconds"] == 300, "camera capture retention ttl mismatch")
        require(camera_capture["capture"].get("adapter_id") == camera_capture["preview_object"]["adapter_id"], "camera capture adapter id mismatch")
        require(
            camera_capture["capture"].get("adapter_execution_path") == camera_capture["preview_object"]["adapter_execution_path"],
            "camera capture adapter path mismatch",
        )
        require(camera_capture["preview_object"]["capture_mode"] == "native-state-bridge", "camera state bridge mode missing")
        require(camera_capture["preview_object"]["adapter_id"] == "camera.v4l-state-root", "camera adapter id mismatch")
        require(camera_capture["preview_object"]["adapter_execution_path"] == "native-state-bridge", "camera adapter path mismatch")
        require(camera_capture["preview_object"]["source_device"] == "camera-1", "camera preview source device mismatch")
        require(camera_capture["preview_object"]["device_path"].endswith("video0"), "camera preview device path mismatch")
        require(camera_capture["preview_object"]["approval_context"]["high_risk"] is True, "camera approval context missing high-risk flag")
        require(camera_capture["preview_object"]["retention_context"]["retention_class"] == "short", "camera retention context mismatch")
        require(
            any("high-risk capture missing session/task context" in note for note in camera_capture["preview_object"]["approval_notes"]),
            "camera approval notes missing missing-context detail",
        )
        require(
            any("contains sensitive data" in note for note in camera_capture["preview_object"]["retention_notes"]),
            "camera retention notes missing sensitive-data detail",
        )
        indicator_state = read_json(indicator_state_path)
        require(len(indicator_state["active"]) == 1, "camera capture should create one visible indicator")
        require(indicator_state["active"][0]["modality"] == "camera", "camera indicator modality mismatch")
        require(indicator_state["active"][0]["approval_status"] == "required", "camera indicator approval mismatch")

        normalized_camera = rpc_call(
            socket_path,
            "device.object.normalize",
            {
                "modality": "camera",
                "payload": camera_capture["preview_object"],
                "source_backend": "pipewire-camera",
                "user_visible": True,
            },
            timeout=args.timeout,
        )
        require(normalized_camera["object_kind"] == "camera_frame", "camera normalize object kind mismatch")
        require(normalized_camera["normalized"]["source_device"] == "camera-1", "camera normalize source device mismatch")
        require(
            any(note == "camera frames default to sensitive retention handling" for note in normalized_camera["notes"]),
            "camera normalize notes missing sensitive-retention note",
        )

        camera_retention = rpc_call(
            socket_path,
            "device.retention.apply",
            {
                "object_kind": "camera_frame",
                "object_id": normalized_camera["normalized"]["frame_id"],
                "continuous": False,
                "contains_sensitive_data": False,
            },
            timeout=args.timeout,
        )
        require(camera_retention["retention_class"] == "short", "camera direct retention should default short")
        require(camera_retention["expires_in_seconds"] == 300, "camera direct retention ttl mismatch")
        require(
            any(note == "object_kind=camera_frame defaults to sensitive retention" for note in camera_retention["notes"]),
            "camera direct retention notes missing object-kind default",
        )

        stop_camera = rpc_call(
            socket_path,
            "device.capture.stop",
            {"capture_id": camera_capture["capture"]["capture_id"], "reason": "camera-done"},
            timeout=args.timeout,
        )
        require(stop_camera["capture"]["status"] == "stopped", "camera capture stop status mismatch")
        require(stop_camera["capture"]["stopped_reason"] == "camera-done", "camera capture stop reason mismatch")
        indicator_state = read_json(indicator_state_path)
        require(indicator_state["active"] == [], "camera stop should clear indicators")

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
        require(audio_capture["capture"]["approval_required"] is True, "audio capture should require approval")
        require(audio_capture["capture"]["approval_status"] == "required", "audio capture approval status mismatch")
        require(audio_capture["capture"].get("approval_source") == "unapproved", "audio capture approval source mismatch")
        require(audio_capture["capture"]["tainted"] is True, "audio capture should be tainted")
        require(audio_capture["capture"]["retention_class"] == "short", "audio capture retention should be short")
        require(audio_capture["capture"]["retention_ttl_seconds"] == 300, "audio capture retention ttl mismatch")
        require(audio_capture["capture"].get("adapter_id") == audio_capture["preview_object"]["adapter_id"], "audio capture adapter id mismatch")
        require(
            audio_capture["capture"].get("adapter_execution_path") == audio_capture["preview_object"]["adapter_execution_path"],
            "audio capture adapter path mismatch",
        )
        require(audio_capture["preview_object"]["capture_mode"] == "native-live", "audio native live missing")
        require(audio_capture["preview_object"]["pipewire_node"]["node_id"] == 77, "audio pipewire node missing")
        require(audio_capture["preview_object"]["adapter_id"] == "audio.pipewire-native", "audio adapter id missing")
        require(audio_capture["preview_object"]["adapter_contract"] == "formal-native-backend", "audio adapter contract missing")
        indicator_state = read_json(indicator_state_path)
        require(len(indicator_state["active"]) == 1, "audio capture should create one visible indicator")
        require(indicator_state["active"][0]["approval_status"] == "required", "audio indicator approval mismatch")
        require(capture_state_path.exists(), "capture state file missing before restart")

        terminate(process)
        process = None
        process, socket_path, health = start_deviced(deviced, env, args.timeout)
        require(
            any(note == "startup_interrupted_captures=1" for note in health["notes"]),
            "startup recovery health note missing",
        )
        indicator_state = read_json(indicator_state_path)
        require(indicator_state["active"] == [], "restart should clear interrupted indicators")

        recovered_state = rpc_call(socket_path, "device.state.get", {}, timeout=args.timeout)
        require(recovered_state["active_captures"] == [], "interrupted captures should not remain active after restart")
        require(
            any(note == "startup_interrupted_captures=1" for note in recovered_state["notes"]),
            "startup recovery state note missing",
        )
        capture_state = read_json(capture_state_path)
        recovered_audio = capture_state[audio_capture["capture"]["capture_id"]]
        require(recovered_audio["status"] == "interrupted", "audio capture should be interrupted after restart")
        require(bool(recovered_audio.get("stopped_at")), "interrupted capture should record stopped_at")
        require(
            recovered_audio.get("stopped_reason") == "startup-reconciliation-interrupted",
            "interrupted capture should record stopped_reason",
        )
        require(recovered_audio.get("approval_source") == "unapproved", "interrupted audio approval source mismatch")
        require(recovered_audio.get("adapter_id") == "audio.pipewire-native", "interrupted audio adapter id mismatch")
        require(recovered_audio.get("adapter_execution_path") == "native-live", "interrupted audio adapter path mismatch")

        stop_audio = rpc_call(
            socket_path,
            "device.capture.stop",
            {"capture_id": audio_capture["capture"]["capture_id"], "reason": "audio-cleanup"},
            timeout=args.timeout,
        )
        require(stop_audio["capture"]["status"] == "stopped", "interrupted audio stop status mismatch")
        require(stop_audio["capture"]["stopped_reason"] == "audio-cleanup", "interrupted audio stop reason mismatch")
        require(indicator_state_path.exists(), "indicator state file missing")
        indicator_state = read_json(indicator_state_path)
        require(indicator_state["active"] == [], "audio cleanup should keep indicators cleared")

        final_state = rpc_call(socket_path, "device.state.get", {}, timeout=args.timeout)
        require(final_state["active_captures"] == [], "active captures not cleared")
        require(any(note == "active_indicators=0" for note in final_state["notes"]), "final indicator note mismatch")
        backend_state = read_json(backend_state_path)
        require(any(note.startswith("backend_count=") for note in backend_state["notes"]), "backend snapshot note missing")
        require(any(note.startswith("adapter_paths=") for note in backend_state["notes"]), "backend adapter paths note missing")
        require(observability_log_path.exists(), "deviced observability log missing")
        observability_entries = [
            json.loads(line)
            for line in observability_log_path.read_text().splitlines()
            if line.strip()
        ]
        kinds = {entry.get("kind") for entry in observability_entries}
        require("device.state.reported" in kinds, "observability log missing device.state event")
        require("device.capture.requested" in kinds, "observability log missing capture request event")
        require("device.capture.stopped" in kinds, "observability log missing capture stop event")
        require(
            any(entry.get("provider_id") == "screen-capture-portal" for entry in observability_entries),
            "observability log missing screen provider correlation",
        )

        print("deviced smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"deviced smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        if process is not None and process.stdout:
            output = process.stdout.read()
            if output.strip():
                print("\n--- deviced log ---")
                print(output.rstrip())
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
