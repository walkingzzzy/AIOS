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


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS portal chooser live screen-capture chain smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing deviced and policyd binaries")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--provider", type=Path, help="Path to screen capture provider script")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--user-id", default="portal-capture-user", help="User id for smoke requests")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(ROOT) / name


def resolve_provider(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return ROOT / "aios" / "shell" / "runtime" / "screen_capture_portal_provider.py"


def ensure_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing files for portal capture chain smoke:")
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


def run_python(script: Path, *args: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def make_runtime_env(temp_root: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
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
                "portal_session_ref": "portal-session-chooser-live",
                "stream_node_id": 42,
                "window_ref": "window-portal-live",
                "resolution": "1280x720",
            }
        )
    )
    pipewire_node_path.write_text(json.dumps({"node_id": 77, "channel_layout": "stereo"}))
    ui_tree_state_path.write_text(
        json.dumps({"snapshot_id": "tree-portal-live-1", "focus_node": "button-1"})
    )

    policyd_env = os.environ.copy()
    policyd_env.update(
        {
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(ROOT / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(
                ROOT / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"
            ),
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
            "AIOS_DEVICED_SCREEN_PROBE_COMMAND": (
                "python3 -c 'import json; print(json.dumps({"
                "\"available\": True, "
                "\"readiness\": \"native-live\", "
                "\"payload\": {\"probe_frame\": True, \"probe_source_name\": \"portal-capture-chain\"}"
                "}))'"
            ),
        }
    )
    provider_env = os.environ.copy()
    provider_env.update(
        {
            "AIOS_SCREEN_CAPTURE_PROVIDER_RUNTIME_DIR": str(runtime_root / "screen-provider"),
            "AIOS_SCREEN_CAPTURE_PROVIDER_SOCKET_PATH": str(
                runtime_root / "screen-provider" / "screen-provider.sock"
            ),
            "AIOS_SCREEN_CAPTURE_PROVIDER_POLICYD_SOCKET": str(
                runtime_root / "policyd" / "policyd.sock"
            ),
            "AIOS_SCREEN_CAPTURE_PROVIDER_DEVICED_SOCKET": str(
                runtime_root / "deviced" / "deviced.sock"
            ),
        }
    )
    return policyd_env, deviced_env, provider_env


def main() -> int:
    args = parse_args()
    paths = {
        "deviced": resolve_binary("deviced", args.deviced, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "provider": resolve_provider(args.provider),
    }
    ensure_paths(paths)

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-portal-capture-chain-",
            dir="/tmp" if Path("/tmp").exists() else None,
        )
    )
    policyd_env, deviced_env, provider_env = make_runtime_env(temp_root)
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
        require(
            provider_health.get("service_id") == "aios-screen-capture-portal-provider",
            "unexpected screen provider health payload",
        )

        approval_eval = rpc_call(
            sockets["policyd"],
            "policy.evaluate",
            {
                "user_id": args.user_id,
                "session_id": "session-live",
                "task_id": "task-live",
                "capability_id": "device.capture.screen.read",
                "execution_location": "local",
                "target_hash": "screen-hash-live-1",
                "constraints": {
                    "window_ref": "window-live-1",
                    "display_ref": "display-live-1",
                    "portal_session_ref": "portal-session-chooser-live",
                    "continuous": True,
                },
                "intent": "Share the current screen",
            },
            timeout=args.timeout,
        )
        approval_ref = approval_eval.get("approval_ref")
        require(bool(approval_ref), "portal capture chain approval_ref missing")
        approval_resolution = rpc_call(
            sockets["policyd"],
            "approval.resolve",
            {
                "approval_ref": approval_ref,
                "status": "approved",
                "resolver": "portal-capture-chain-smoke",
                "reason": "approved for chooser capture chain smoke",
            },
            timeout=args.timeout,
        )
        require(
            approval_resolution.get("status") == "approved",
            "portal capture chain approval was not approved",
        )

        chooser_fixture = temp_root / "chooser-fixture.json"
        chooser_fixture_direct = temp_root / "chooser-fixture-direct.json"
        profile = temp_root / "shell-profile.json"
        base_payload = {
            "request": {
                "chooser_id": "chooser-live-capture",
                "title": "Choose Screen Share Target",
                "status": "selected",
                "requested_kinds": ["screen_share_handle"],
                "selection_mode": "single",
                "approval_status": "approved",
                "approval_ref": approval_ref,
                "selected_handle_id": "handle-screen",
                "capability_id": "device.capture.screen.read",
                "attempt_count": 0,
                "max_attempts": 3,
            },
            "handles": [
                {
                    "handle_id": "handle-screen",
                    "kind": "screen_share_handle",
                    "target": "screen://current-display",
                    "scope": {
                        "display_name": "Current Display",
                        "backend": "pipewire",
                        "display_ref": "display-live-1",
                        "window_ref": "window-live-1",
                        "portal_session_ref": "portal-session-chooser-live",
                        "continuous": True,
                        "target_hash": "screen-hash-live-1",
                    },
                }
            ],
        }
        write_json(chooser_fixture, base_payload)
        write_json(chooser_fixture_direct, json.loads(json.dumps(base_payload)))
        write_json(
            profile,
            {
                "profile_id": "portal-capture-chain-smoke",
                "components": {
                    "portal_chooser": True,
                },
                "paths": {
                    "sessiond_socket": "/tmp/missing-sessiond.sock",
                    "policyd_socket": str(sockets["policyd"]),
                    "deviced_socket": str(sockets["deviced"]),
                    "screen_capture_provider_socket": str(sockets["provider"]),
                },
            },
        )

        shellctl_confirm = json.loads(
            run_python(
                ROOT / "aios/shell/shellctl.py",
                "--profile",
                str(profile),
                "--json",
                "panel",
                "--allow-disabled",
                "portal-chooser",
                "action",
                "--session-id",
                "session-live",
                "--task-id",
                "task-live",
                "--user-id",
                args.user_id,
                "--handle-fixture",
                str(chooser_fixture),
                "--action",
                "confirm-selection",
            )
        )
        require(shellctl_confirm["status"] == "confirmed", "shellctl chooser confirm should succeed")
        require(
            shellctl_confirm["target_component"] == "task-surface",
            "shellctl chooser confirm route mismatch",
        )
        require(
            shellctl_confirm["capture_transport"] == "screen-provider",
            "shellctl chooser should prefer screen provider transport",
        )
        require(
            shellctl_confirm["capture_status"] == "capturing",
            "shellctl chooser live capture status mismatch",
        )
        require(bool(shellctl_confirm["capture_id"]), "shellctl chooser live capture_id missing")
        require(
            (shellctl_confirm["capture_request"] or {}).get("window_ref") == "window-live-1",
            "shellctl chooser live capture window_ref mismatch",
        )
        require(
            (shellctl_confirm["capture_request"] or {}).get("source_device") == "display-live-1",
            "shellctl chooser live capture source_device mismatch",
        )
        fixture_request = json.loads(chooser_fixture.read_text()).get("request") or {}
        require(
            fixture_request.get("capture_transport") == "screen-provider",
            "chooser fixture should persist provider transport",
        )
        require(
            fixture_request.get("capture_status") == "capturing",
            "chooser fixture should persist capture status",
        )

        direct_confirm = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-live-direct",
                "--task-id",
                "task-live-direct",
                "--user-id",
                args.user_id,
                "--handle-fixture",
                str(chooser_fixture_direct),
                "--policy-socket",
                str(sockets["policyd"]),
                "--deviced-socket",
                str(sockets["deviced"]),
                "--screen-provider-socket",
                str(temp_root / "missing-provider.sock"),
                "--action",
                "confirm-selection",
            )
        )
        require(direct_confirm["status"] == "confirmed", "direct chooser confirm should succeed")
        require(
            direct_confirm["capture_transport"] == "deviced-direct",
            "chooser confirm should fall back to direct deviced transport",
        )
        require(
            direct_confirm["capture_status"] == "capturing",
            "direct chooser capture status mismatch",
        )

        print("portal capture chain smoke passed")
        print(
            json.dumps(
                {
                    "provider_transport": shellctl_confirm["capture_transport"],
                    "provider_capture_id": shellctl_confirm["capture_id"],
                    "direct_transport": direct_confirm["capture_transport"],
                    "direct_capture_id": direct_confirm["capture_id"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:  # noqa: BLE001
        failed = True
        print(f"portal capture chain smoke failed: {error}", file=sys.stderr)
        return 1
    finally:
        terminate(list(processes.values()))
        if failed:
            print_logs(processes)
            print(f"state kept at: {temp_root}", file=sys.stderr)
        elif args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
