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

ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS deviced/policyd approval smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing binaries")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(ROOT) / name


def ensure_binary(path: Path, package: str) -> None:
    if path.exists():
        return
    print(f"Missing binary: {path}")
    print(f"Build it first, for example: cargo build -p {package}")
    raise SystemExit(2)


def rpc_exchange(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
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
    return json.loads(data.decode("utf-8"))


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_exchange(socket_path, method, params, timeout)
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
    last_error = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    deadline = time.time() + 5
    for process in processes:
        if process.poll() is not None:
            continue
        remaining = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def print_logs(processes: dict[str, subprocess.Popen]) -> None:
    for name, process in processes.items():
        output = ""
        if process.stdout and process.poll() is not None:
            output = process.stdout.read()
        if output.strip():
            print(f"\n--- {name} log ---")
            print(output.rstrip())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def make_env(root: Path) -> dict[str, str]:
    run_root = root / "run"
    state_root = root / "state"
    deviced_run = run_root / "deviced"
    policyd_run = run_root / "policyd"
    deviced_state = state_root / "deviced"
    policyd_state = state_root / "policyd"
    deviced_run.mkdir(parents=True, exist_ok=True)
    policyd_run.mkdir(parents=True, exist_ok=True)
    deviced_state.mkdir(parents=True, exist_ok=True)
    policyd_state.mkdir(parents=True, exist_ok=True)

    pipewire_socket_path = deviced_state / "pipewire-0"
    pipewire_node_path = deviced_state / "pipewire-node.json"
    input_root = deviced_state / "input"
    camera_root = deviced_state / "camera"
    screencast_state_path = deviced_state / "screencast-state.json"
    ui_tree_state_path = deviced_state / "ui-tree-state.json"

    pipewire_socket_path.write_text("ready\n")
    pipewire_node_path.write_text(json.dumps({"node_id": 7, "channel_layout": "stereo"}))
    input_root.mkdir(parents=True, exist_ok=True)
    camera_root.mkdir(parents=True, exist_ok=True)
    screencast_state_path.write_text(json.dumps({"portal_session_ref": "portal-1"}))
    ui_tree_state_path.write_text(json.dumps({"snapshot_id": "tree-1"}))
    shared_observability_log = state_root / "observability.jsonl"

    env = os.environ.copy()
    env.update(
        {
            "AIOS_POLICYD_RUNTIME_DIR": str(policyd_run),
            "AIOS_POLICYD_STATE_DIR": str(policyd_state),
            "AIOS_POLICYD_SOCKET_PATH": str(policyd_run / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(ROOT / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(ROOT / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"),
            "AIOS_POLICYD_AUDIT_LOG": str(policyd_state / "audit.jsonl"),
            "AIOS_POLICYD_OBSERVABILITY_LOG": str(shared_observability_log),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(policyd_state / "token.key"),
            "AIOS_DEVICED_RUNTIME_DIR": str(deviced_run),
            "AIOS_DEVICED_STATE_DIR": str(deviced_state),
            "AIOS_DEVICED_SOCKET_PATH": str(deviced_run / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(deviced_state / "captures.json"),
            "AIOS_DEVICED_OBSERVABILITY_LOG": str(shared_observability_log),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(deviced_state / "indicator-state.json"),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(deviced_state / "backend-state.json"),
            "AIOS_DEVICED_POLICY_SOCKET_PATH": str(policyd_run / "policyd.sock"),
            "AIOS_DEVICED_APPROVAL_RPC_TIMEOUT_MS": "1000",
            "AIOS_DEVICED_APPROVAL_MODE": "enforced",
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(ui_tree_state_path),
            "AIOS_DEVICED_CAMERA_ENABLED": "false",
        }
    )
    return env


def main() -> int:
    args = parse_args()
    binaries = {
        "deviced": resolve_binary("deviced", args.deviced, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
    }
    ensure_binary(binaries["deviced"], "aios-deviced")
    ensure_binary(binaries["policyd"], "aios-policyd")

    temp_root = Path(tempfile.mkdtemp(prefix="adpa-", dir="/tmp"))
    env = make_env(temp_root)
    failed = False

    processes = {
        "policyd": launch(binaries["policyd"], env),
        "deviced": launch(binaries["deviced"], env),
    }

    try:
        policyd_socket = Path(env["AIOS_POLICYD_SOCKET_PATH"])
        deviced_socket = Path(env["AIOS_DEVICED_SOCKET_PATH"])
        wait_for_socket(policyd_socket, args.timeout)
        wait_for_socket(deviced_socket, args.timeout)
        policyd_health = wait_for_health(policyd_socket, args.timeout)
        deviced_health = wait_for_health(deviced_socket, args.timeout)
        require(policyd_health["status"] == "ready", "policyd not ready")
        require(deviced_health["status"] == "ready", "deviced not ready")
        require(
            any(note == f"policy_socket_path={policyd_socket}" for note in deviced_health["notes"]),
            "deviced health missing policy socket path",
        )

        state = rpc_call(deviced_socket, "device.state.get", {}, timeout=args.timeout)
        capture_state_path = Path(env["AIOS_DEVICED_CAPTURE_STATE_PATH"])
        require(
            any(note == f"policy_socket_path={policyd_socket}" for note in state["notes"]),
            "device.state missing policy socket path",
        )
        require(
            any(note == "policy_socket_present=true" for note in state["notes"]),
            "device.state should report policy socket present",
        )
        shared_observability_log = Path(env["AIOS_DEVICED_OBSERVABILITY_LOG"])

        denied = rpc_exchange(
            deviced_socket,
            "device.capture.request",
            {
                "modality": "audio",
                "session_id": "session-approval-1",
                "task_id": "task-approval-1",
                "continuous": True,
                "source_device": "microphone-1",
            },
            timeout=args.timeout,
        )
        require(denied.get("error") is not None, "audio capture should be denied before approval")
        require(
            "approval required for audio capture" in denied["error"]["message"],
            "missing approval denial detail",
        )

        approval = rpc_call(
            policyd_socket,
            "approval.create",
            {
                "user_id": "user-1",
                "session_id": "session-approval-1",
                "task_id": "task-approval-1",
                "capability_id": "device.capture.audio",
                "approval_lane": "device-capture-review",
                "execution_location": "local",
                "reason": "allow microphone capture",
            },
            timeout=args.timeout,
        )
        approval_ref = approval["approval_ref"]
        resolved = rpc_call(
            policyd_socket,
            "approval.resolve",
            {
                "approval_ref": approval_ref,
                "status": "approved",
                "resolver": "smoke-test",
                "reason": "approved by smoke harness",
            },
            timeout=args.timeout,
        )
        require(resolved["status"] == "approved", "approval should resolve to approved")

        capture = rpc_call(
            deviced_socket,
            "device.capture.request",
            {
                "modality": "audio",
                "session_id": "session-approval-1",
                "task_id": "task-approval-1",
                "continuous": True,
                "source_device": "microphone-1",
            },
            timeout=args.timeout,
        )
        require(capture["capture"]["approval_status"] == "approved", "capture approval status mismatch")
        require(capture["capture"].get("approval_source") == "policyd", "capture approval source mismatch")
        require(capture["capture"].get("approval_ref") == approval_ref, "capture approval ref mismatch")
        require(capture["capture"]["retention_class"] == "short", "audio retention should be short")
        require(capture["capture"].get("adapter_id") == capture["preview_object"]["adapter_id"], "capture adapter id mismatch")
        require(
            capture["capture"].get("adapter_execution_path") == capture["preview_object"]["adapter_execution_path"],
            "capture adapter path mismatch",
        )
        require(bool(capture["capture"].get("indicator_id")), "audio indicator id missing")
        require(capture["preview_object"]["source_device"] == "microphone-1", "audio source device mismatch")
        require(capture["preview_object"]["approval_context"]["approved"] is True, "approval context should be approved")
        require(capture["preview_object"]["approval_context"]["approval_source"] == "policyd", "approval source mismatch")
        require(capture["preview_object"]["approval_context"]["approval_ref"] == approval_ref, "approval ref mismatch")
        require(
            any("approved via policyd approval_ref=" in note for note in capture["preview_object"]["approval_notes"]),
            "approval notes missing policyd approval",
        )
        require(
            any("contains sensitive data" in note for note in capture["preview_object"]["retention_notes"]),
            "retention notes missing sensitive-data detail",
        )
        live_state = rpc_call(deviced_socket, "device.state.get", {}, timeout=args.timeout)
        active_capture = next(
            item for item in live_state["active_captures"] if item["capture_id"] == capture["capture"]["capture_id"]
        )
        require(active_capture.get("approval_source") == "policyd", "active capture approval source mismatch")
        require(active_capture.get("approval_ref") == approval_ref, "active capture approval ref mismatch")
        capture_state = json.loads(capture_state_path.read_text())
        persisted_capture = capture_state[capture["capture"]["capture_id"]]
        require(persisted_capture.get("approval_source") == "policyd", "persisted capture approval source mismatch")
        require(persisted_capture.get("approval_ref") == approval_ref, "persisted capture approval ref mismatch")
        require(persisted_capture.get("adapter_id") == capture["preview_object"]["adapter_id"], "persisted capture adapter id mismatch")
        require(
            persisted_capture.get("adapter_execution_path") == capture["preview_object"]["adapter_execution_path"],
            "persisted capture adapter path mismatch",
        )
        require(shared_observability_log.exists(), "shared observability log missing")
        observability_entries = [
            json.loads(line)
            for line in shared_observability_log.read_text().splitlines()
            if line.strip()
        ]
        require(
            any(entry.get("decision") == "approval-pending" for entry in observability_entries),
            "shared observability log missing mirrored policy approval audit",
        )
        require(
            any(entry.get("kind") == "device.capture.rejected" for entry in observability_entries),
            "shared observability log missing rejected device capture trace",
        )
        require(
            any(
                entry.get("kind") == "device.capture.requested"
                and entry.get("approval_id") == approval_ref
                for entry in observability_entries
            ),
            "shared observability log missing approved device capture correlation",
        )

        print("deviced policy approval smoke passed")
        return 0
    except Exception:
        failed = True
        raise
    finally:
        terminate(list(processes.values()))
        print_logs(processes)
        if failed or args.keep_state:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
