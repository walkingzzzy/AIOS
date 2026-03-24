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
    parser = argparse.ArgumentParser(description="AIOS screen capture provider smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing deviced and policyd binaries")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--provider", type=Path, help="Path to screen capture provider script")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--user-id", default="screen-provider-user", help="User id for smoke requests")
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


def resolve_provider(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return repo_root() / "aios" / "shell" / "runtime" / "screen_capture_portal_provider.py"


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"

def ensure_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing files for screen capture provider smoke harness:")
        for item in missing:
            print(f"  - {item}")
        raise SystemExit(2)


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


def wait_for_socket(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.5)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def launch(command: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        command,
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


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("screen capture provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    paths = {
        "deviced": resolve_binary("deviced", args.deviced, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "provider": resolve_provider(args.provider),
    }
    ensure_paths(paths)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-screen-provider-", dir="/tmp" if Path("/tmp").exists() else None))
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    backend_state_path = state_root / "deviced" / "backend-state.json"
    pipewire_socket_path = state_root / "deviced" / "pipewire-0"
    input_root = state_root / "deviced" / "input"
    camera_root = state_root / "deviced" / "camera"
    screencast_state_path = state_root / "deviced" / "screencast-state.json"
    pipewire_node_path = state_root / "deviced" / "pipewire-node.json"
    ui_tree_state_path = state_root / "deviced" / "ui-tree-state.json"
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
                "window_ref": "focused",
                "resolution": "1280x720",
            }
        )
    )
    pipewire_node_path.write_text(json.dumps({"node_id": 77, "channel_layout": "stereo"}))
    ui_tree_state_path.write_text(json.dumps({"snapshot_id": "tree-native-1", "focus_node": "button-1"}))

    policyd_env = os.environ.copy()
    policyd_env.update(
        {
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(repo_root() / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(repo_root() / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
        }
    )
    deviced_env = os.environ.copy()
    deviced_env.update(
        {
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root / "deviced"),
            "AIOS_DEVICED_STATE_DIR": str(state_root / "deviced"),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced" / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "deviced" / "captures.json"),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(state_root / "deviced" / "indicator-state.json"),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(backend_state_path),
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(ui_tree_state_path),
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "1",
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
            "AIOS_DEVICED_POLICY_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_DEVICED_SCREEN_PROBE_COMMAND": "python3 -c 'import json; print(json.dumps({\"available\": True, \"readiness\": \"native-live\", \"payload\": {\"probe_frame\": True, \"probe_source_name\": \"screen-provider-smoke\"}}))'",
        }
    )
    provider_env = os.environ.copy()
    provider_env.update(
        {
            "AIOS_SCREEN_CAPTURE_PROVIDER_RUNTIME_DIR": str(runtime_root / "screen-provider"),
            "AIOS_SCREEN_CAPTURE_PROVIDER_SOCKET_PATH": str(runtime_root / "screen-provider" / "screen-provider.sock"),
            "AIOS_SCREEN_CAPTURE_PROVIDER_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_SCREEN_CAPTURE_PROVIDER_DEVICED_SOCKET": str(runtime_root / "deviced" / "deviced.sock"),
        }
    )

    sockets = {
        "policyd": Path(policyd_env["AIOS_POLICYD_SOCKET_PATH"]),
        "deviced": Path(deviced_env["AIOS_DEVICED_SOCKET_PATH"]),
        "provider": Path(provider_env["AIOS_SCREEN_CAPTURE_PROVIDER_SOCKET_PATH"]),
    }
    processes: dict[str, subprocess.Popen] = {}
    failed = False

    try:
        processes["policyd"] = launch([str(paths["policyd"])], policyd_env)
        wait_for_socket(sockets["policyd"], args.timeout)
        wait_for_health(sockets["policyd"], args.timeout)

        processes["deviced"] = launch([str(paths["deviced"])], deviced_env)
        wait_for_socket(sockets["deviced"], args.timeout)
        wait_for_health(sockets["deviced"], args.timeout)

        processes["provider"] = launch([sys.executable, str(paths["provider"])], provider_env)
        wait_for_socket(sockets["provider"], args.timeout)
        provider_health = wait_for_health(sockets["provider"], args.timeout)
        require(provider_health.get("service_id") == "aios-screen-capture-portal-provider", "unexpected screen provider health payload")

        approval_eval = rpc_call(
            sockets["policyd"],
            "policy.evaluate",
            {
                "user_id": args.user_id,
                "session_id": "session-screen",
                "task_id": "task-screen",
                "capability_id": "device.capture.screen.read",
                "execution_location": "sandbox",
                "target_hash": "screen-smoke-hash",
                "constraints": {
                    "window_ref": "window-scope-1",
                    "display_ref": "display-3",
                    "portal_session_ref": "portal-session-77",
                    "continuous": True,
                },
                "intent": "Share the current screen",
            },
            timeout=args.timeout,
        )
        approval_ref = approval_eval.get("approval_ref")
        require(approval_eval.get("decision", {}).get("decision") == "needs-approval", "screen capture policy did not require approval")
        require(bool(approval_ref), "screen capture approval_ref missing")

        resolved = rpc_call(
            sockets["policyd"],
            "approval.resolve",
            {
                "approval_ref": approval_ref,
                "status": "approved",
                "resolver": "screen-provider-smoke",
                "reason": "approved for provider smoke",
            },
            timeout=args.timeout,
        )
        require(resolved.get("status") == "approved", "screen capture approval was not approved")

        token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": args.user_id,
                "session_id": "session-screen",
                "task_id": "task-screen",
                "capability_id": "device.capture.screen.read",
                "approval_ref": approval_ref,
                "target_hash": "screen-smoke-hash",
                "constraints": {
                    "window_ref": "window-scope-1",
                    "display_ref": "display-3",
                    "portal_session_ref": "portal-session-77",
                    "continuous": True,
                },
                "execution_location": "sandbox",
            },
            timeout=args.timeout,
        )

        result = rpc_call(
            sockets["provider"],
            "device.capture.screen.read",
            {
                "execution_token": token,
                "portal_handle": {
                    "handle_id": "ph-screen",
                    "kind": "screen_share_handle",
                    "session_id": "session-screen",
                    "target": "screen://current-display",
                    "scope": {
                        "target": "screen://current-display",
                        "target_path": "screen://current-display",
                        "target_hash": "screen-smoke-hash",
                        "portal_session_ref": "portal-session-77",
                        "backend": "pipewire",
                        "display_ref": "display-3",
                        "window_ref": "window-scope-1",
                        "continuous": True,
                    },
                    "issued_at": "2026-03-09T00:00:00Z",
                    "expires_at": "2026-03-09T01:00:00Z",
                },
            },
            timeout=args.timeout,
        )

        capture = result.get("capture") or {}
        capture_request = result.get("capture_request") or {}
        require(capture.get("modality") == "screen", "screen provider capture modality mismatch")
        require(capture.get("source_backend") in {"screen-capture-portal", "screen-capture"}, "screen provider source backend mismatch")
        require(capture.get("continuous") is True, "screen provider continuous flag mismatch")
        preview = result.get("preview_object") or {}
        require(capture.get("preview_object_kind") == "screen_frame", "screen provider preview kind mismatch")
        require(bool(preview.get("frame_id")), "screen provider preview frame missing")
        require(result.get("selected_target") == "screen://current-display", "screen provider target mismatch")
        require(capture_request.get("continuous") is True, "screen provider request continuous mismatch")
        require(capture_request.get("window_ref") == "window-scope-1", "screen provider window_ref mismatch")
        require(capture_request.get("source_device") == "display-3", "screen provider source_device mismatch")
        require(
            "portal_session_ref=portal-session-77" in (result.get("notes") or []),
            "screen provider portal session note mismatch",
        )
        require(
            "target_hash=screen-smoke-hash" in (result.get("notes") or []),
            "screen provider target hash note mismatch",
        )
        try:
            rpc_call(
                sockets["provider"],
                "device.capture.screen.read",
                {
                    "execution_token": token,
                    "portal_handle": {
                        "handle_id": "ph-screen",
                        "kind": "screen_share_handle",
                        "session_id": "session-screen",
                        "target": "screen://current-display",
                        "scope": {
                            "target": "screen://current-display",
                            "target_path": "screen://current-display",
                            "target_hash": "screen-smoke-hash",
                        },
                        "issued_at": "2026-03-09T00:00:00Z",
                        "expires_at": "2026-03-09T01:00:00Z",
                    },
                },
                timeout=args.timeout,
            )
            raise RuntimeError("screen provider unexpectedly accepted a consumed token")
        except RuntimeError as error:
            require(
                "already consumed" in str(error),
                "screen provider should reject consumed tokens",
            )

        print("\nScreen capture provider smoke result summary:")
        print(
            json.dumps(
                {
                    "provider_id": result.get("provider_id"),
                    "capture_id": capture.get("capture_id"),
                    "source_backend": capture.get("source_backend"),
                    "preview_kind": capture.get("preview_object_kind"),
                    "selected_target": result.get("selected_target"),
                    "continuous": capture_request.get("continuous"),
                    "window_ref": capture_request.get("window_ref"),
                    "source_device": capture_request.get("source_device"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"screen capture provider smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        terminate(list(processes.values()))
        if failed:
            print_logs(processes)
        if args.keep_state:
            print(f"Preserved screen capture provider smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
