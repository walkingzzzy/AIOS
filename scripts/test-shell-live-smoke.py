#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
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
AIOS_ROOT = ROOT / "aios"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS live shell smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing updated/deviced binaries")
    parser.add_argument("--updated", type=Path, help="Path to updated binary")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
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


def run_python(script: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    return completed.stdout.strip()


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
    raise TimeoutError(f"Timed out waiting for health: {socket_path}")


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    if process.stdout:
        return process.stdout.read().strip()
    return ""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def setup_updated_env(base: Path) -> tuple[dict[str, str], dict[str, Path]]:
    runtime_root = base / "runtime"
    state_root = base / "state"
    sysupdate_dir = base / "sysupdate"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    sysupdate_dir.mkdir(parents=True, exist_ok=True)
    (sysupdate_dir / "00-aios-root.transfer").write_text("transfer\n")

    boot_dir = state_root / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)
    cmdline_path = boot_dir / "cmdline"
    current_entry_path = boot_dir / "current-entry"
    boot_success_marker_path = state_root / "boot-success"
    fake_bootctl_path = state_root / "fake-bootctl.sh"
    bootctl_context_path = state_root / "bootctl-context.txt"
    health_context_path = state_root / "health-context.txt"
    apply_context_path = state_root / "apply-context.txt"
    rollback_context_path = state_root / "rollback-context.txt"
    recovery_surface_path = state_root / "recovery-surface.json"
    boot_state_path = state_root / "boot-control.json"
    updated_socket = runtime_root / "updated.sock"

    cmdline_path.write_text("quiet splash aios.slot=a\n")
    current_entry_path.write_text("aios-a.conf\n")
    boot_success_marker_path.write_text("success\n")
    fake_bootctl_path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "context=\"$AIOS_UPDATED_TEST_BOOTCTL_CONTEXT\"\n"
        "boot_dir=\"$AIOS_UPDATED_TEST_BOOT_DIR\"\n"
        "case \"${1:-}\" in\n"
        "  status)\n"
        "    entry=aios-a.conf\n"
        "    if [ -f \"$boot_dir/current-entry\" ]; then\n"
        "      entry=$(head -n 1 \"$boot_dir/current-entry\")\n"
        "    fi\n"
        "    printf '%s\\n' \"Current Boot Loader Entry: $entry\"\n"
        "    ;;\n"
        "  set-oneshot)\n"
        "    printf '%s' \"$1|$2\" > \"$context\"\n"
        "    ;;\n"
        "  *)\n"
        "    printf 'unsupported bootctl verb: %s\\n' \"${1:-}\" >&2\n"
        "    exit 1\n"
        "    ;;\n"
        "esac\n"
    )
    fake_bootctl_path.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_UPDATED_RUNTIME_DIR": str(runtime_root),
            "AIOS_UPDATED_STATE_DIR": str(state_root),
            "AIOS_UPDATED_SOCKET_PATH": str(updated_socket),
            "AIOS_UPDATED_DEPLOYMENT_STATE": str(state_root / "deployment-state.json"),
            "AIOS_UPDATED_DIAGNOSTICS_DIR": str(state_root / "diagnostics"),
            "AIOS_UPDATED_RECOVERY_DIR": str(state_root / "recovery"),
            "AIOS_UPDATED_SYSUPDATE_DIR": str(sysupdate_dir),
            "AIOS_UPDATED_HEALTH_PROBE_PATH": str(state_root / "health-probe.json"),
            "AIOS_UPDATED_RECOVERY_SURFACE_PATH": str(recovery_surface_path),
            "AIOS_UPDATED_BOOT_STATE_PATH": str(boot_state_path),
            "AIOS_UPDATED_BOOT_BACKEND": "bootctl",
            "AIOS_UPDATED_BOOTCTL_BIN": str(fake_bootctl_path),
            "AIOS_UPDATED_BOOT_CMDLINE_PATH": str(cmdline_path),
            "AIOS_UPDATED_BOOT_ENTRY_STATE_DIR": str(boot_dir),
            "AIOS_UPDATED_BOOT_SUCCESS_MARKER_PATH": str(boot_success_marker_path),
            "AIOS_UPDATED_CURRENT_SLOT": "a",
            "AIOS_UPDATED_HEALTH_PROBE_COMMAND": (
                f"printf '%s' \"$AIOS_UPDATED_OPERATION|$AIOS_UPDATED_HEALTH_PROBE_PATH|$AIOS_UPDATED_DEPLOYMENT_STATUS\" > {shlex.quote(str(health_context_path))} && "
                "printf '%s' '{\"overall_status\":\"healthy\",\"summary\":\"probe ok\"}'"
            ),
            "AIOS_UPDATED_SYSUPDATE_CHECK_COMMAND": "printf 'sysupdate check ok'",
            "AIOS_UPDATED_SYSUPDATE_APPLY_COMMAND": (
                f"printf '%s' \"$AIOS_UPDATED_OPERATION|$AIOS_UPDATED_REQUEST_TARGET_VERSION|$AIOS_UPDATED_REQUEST_REASON|$AIOS_UPDATED_RECOVERY_ID\" > {shlex.quote(str(apply_context_path))} && "
                "printf 'sysupdate apply ok'"
            ),
            "AIOS_UPDATED_ROLLBACK_COMMAND": (
                f"printf '%s' \"$AIOS_UPDATED_OPERATION|$AIOS_UPDATED_ROLLBACK_TARGET|$AIOS_UPDATED_REQUEST_REASON\" > {shlex.quote(str(rollback_context_path))} && "
                "printf 'rollback ok'"
            ),
            "AIOS_UPDATED_TARGET_VERSION": "0.1.1",
            "AIOS_UPDATED_TEST_BOOTCTL_CONTEXT": str(bootctl_context_path),
            "AIOS_UPDATED_TEST_BOOT_DIR": str(boot_dir),
        }
    )
    paths = {
        "socket": updated_socket,
        "recovery_surface": recovery_surface_path,
        "boot_state": boot_state_path,
        "apply_context": apply_context_path,
    }
    return env, paths


def setup_deviced_env(base: Path) -> tuple[dict[str, str], dict[str, Path]]:
    runtime_root = base / "runtime"
    state_root = base / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    backend_state_path = state_root / "backend-state.json"
    indicator_state_path = state_root / "indicator-state.json"
    pipewire_socket_path = state_root / "pipewire-0"
    input_root = state_root / "input"
    camera_root = state_root / "camera"
    screencast_state_path = state_root / "screencast-state.json"
    pipewire_node_path = state_root / "pipewire-node.json"
    ui_tree_state_path = state_root / "ui-tree-state.json"
    deviced_socket = runtime_root / "deviced.sock"

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

    env = os.environ.copy()
    env.update(
        {
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root),
            "AIOS_DEVICED_STATE_DIR": str(state_root),
            "AIOS_DEVICED_SOCKET_PATH": str(deviced_socket),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "captures.json"),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(indicator_state_path),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(backend_state_path),
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(ui_tree_state_path),
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "1",
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
            "AIOS_DEVICED_SCREEN_PROBE_COMMAND": f"{shlex.quote(sys.executable)} -c 'import json; print(json.dumps({{\"available\": True, \"readiness\": \"native-live\", \"payload\": {{\"probe_frame\": True, \"probe_source_name\": \"shell-live\"}}}}))'",
        }
    )
    paths = {
        "socket": deviced_socket,
        "indicator_state": indicator_state_path,
        "backend_state": backend_state_path,
    }
    return env, paths


def main() -> int:
    args = parse_args()
    updated = resolve_binary("updated", args.updated, args.bin_dir)
    deviced = resolve_binary("deviced", args.deviced, args.bin_dir)
    ensure_binary(updated, "aios-updated")
    ensure_binary(deviced, "aios-deviced")

    temp_root = Path(tempfile.mkdtemp(prefix="asl-", dir="/tmp"))
    updated_root = temp_root / "updated"
    deviced_root = temp_root / "deviced"
    panel_action_log_path = temp_root / "panel-action-events.jsonl"
    missing_surface = temp_root / "missing-recovery-surface.json"
    missing_backend = temp_root / "missing-backend-state.json"
    shell_profile = temp_root / "shell-profile.yaml"

    updated_env, updated_paths = setup_updated_env(updated_root)
    deviced_env, deviced_paths = setup_deviced_env(deviced_root)
    shell_profile.write_text(
        json.dumps(
            {
                "profile_id": "shell-live-smoke",
                "desktop_host": "tk",
                "session_backend": "standalone",
                "components": {
                    "notification_center": True,
                    "recovery_surface": True,
                    "capture_indicators": True,
                    "device_backend_status": True,
                },
                "paths": {
                    "updated_socket": str(updated_paths["socket"]),
                    "recovery_surface_model": str(updated_paths["recovery_surface"]),
                    "capture_indicator_state": str(deviced_paths["indicator_state"]),
                    "device_backend_state": str(deviced_paths["backend_state"]),
                    "deviced_socket": str(deviced_paths["socket"]),
                    "policyd_socket": "/tmp/missing-policyd.sock",
                },
                "compositor": {
                    "manifest_path": "../compositor/Cargo.toml",
                    "config_path": "../compositor/default-compositor.conf",
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    updated_process = launch(updated, updated_env)
    deviced_process = launch(deviced, deviced_env)
    failed = False

    try:
        wait_for_socket(updated_paths["socket"], args.timeout)
        wait_for_socket(deviced_paths["socket"], args.timeout)
        wait_for_health(updated_paths["socket"], args.timeout)
        wait_for_health(deviced_paths["socket"], args.timeout)

        apply_result = rpc_call(
            updated_paths["socket"],
            "update.apply",
            {"target_version": "0.1.1", "reason": "shell-live-smoke", "dry_run": False},
            timeout=args.timeout,
        )
        require(apply_result["status"] == "accepted", "update.apply was not accepted")
        require(updated_paths["recovery_surface"].exists(), "recovery surface missing after apply")
        require(updated_paths["boot_state"].exists(), "boot state missing after apply")
        require(
            updated_paths["apply_context"].read_text().startswith("apply|0.1.1|shell-live-smoke|recovery-"),
            "updated apply context mismatch",
        )

        screen_capture = rpc_call(
            deviced_paths["socket"],
            "device.capture.request",
            {
                "modality": "screen",
                "session_id": "session-1",
                "continuous": False,
                "window_ref": "window-1",
            },
            timeout=args.timeout,
        )
        require(screen_capture["capture"]["status"] == "sampled", "screen capture not sampled")
        require(deviced_paths["indicator_state"].exists(), "indicator state missing after capture")
        require(deviced_paths["backend_state"].exists(), "backend state missing after capture")

        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/prototype.py",
            "status",
            "--surface",
            str(updated_paths["recovery_surface"]),
            "--socket",
            str(updated_paths["socket"]),
        )
        require("deployment: apply-triggered" in output, "recovery surface missing deployment state")
        require("staged_slot: b" in output, "recovery surface missing staged slot")

        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/prototype.py",
            "status",
            "--surface",
            str(missing_surface),
            "--socket",
            str(updated_paths["socket"]),
        )
        require("service: aios-updated" in output, "recovery rpc fallback missing service id")
        require("rollback_ready: True" in output, "recovery rpc fallback missing rollback readiness")
        require("deployment: apply-triggered" in output, "recovery rpc fallback missing deployment state")
        require("staged_slot: b" in output, "recovery rpc fallback missing staged slot")

        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/client.py",
            "summary",
            "--surface",
            str(missing_surface),
            "--socket",
            str(updated_paths["socket"]),
        )
        require("deployment: apply-triggered" in output, "recovery client fallback missing deployment state")
        require("action_count:" in output, "recovery client summary missing action count")

        output = run_python(
            ROOT / "aios/shell/components/device-backend-status/prototype.py",
            "--path",
            str(missing_backend),
            "--socket",
            str(deviced_paths["socket"]),
        )
        require("screen-capture-portal [native-live]" in output, "backend status rpc fallback missing screen status")
        require("adapter: screen -> screen.portal-probe [native-live]" in output, "backend status rpc fallback missing adapter")

        output = run_python(
            ROOT / "aios/shell/components/device-backend-status/client.py",
            "status",
            "--path",
            str(missing_backend),
            "--socket",
            str(deviced_paths["socket"]),
        )
        require("screen-capture-portal [native-live]" in output, "backend client rpc fallback missing screen status")
        require("adapter: screen -> screen.portal-probe [native-live]" in output, "backend client rpc fallback missing adapter")

        output = run_python(
            ROOT / "aios/shell/components/capture-indicators/prototype.py",
            "--path",
            str(deviced_paths["indicator_state"]),
        )
        require("screen: Screen capture active [not-required]" in output, "capture indicators live output mismatch")

        output = run_python(
            ROOT / "aios/shell/components/capture-indicators/client.py",
            "status",
            "--path",
            str(deviced_paths["indicator_state"]),
        )
        require("screen: Screen capture active [not-required]" in output, "capture client live output mismatch")

        output = run_python(
            ROOT / "aios/shell/components/notification-center/prototype.py",
            "--recovery-surface",
            str(updated_paths["recovery_surface"]),
            "--indicator-state",
            str(deviced_paths["indicator_state"]),
            "--backend-state",
            str(deviced_paths["backend_state"]),
            "--updated-socket",
            str(updated_paths["socket"]),
            "--deviced-socket",
            str(deviced_paths["socket"]),
        )
        require("Deployment state: apply-triggered" in output, "notification center missing deployment item")
        require("Recovery rollback is available" in output, "notification center missing rollback item")
        require("Screen capture active" in output, "notification center missing capture item")
        require("Backend attention: screen" not in output, "notification center should ignore native-live backend")

        output = run_python(
            ROOT / "aios/shell/components/notification-center/client.py",
            "summary",
            "--recovery-surface",
            str(updated_paths["recovery_surface"]),
            "--indicator-state",
            str(deviced_paths["indicator_state"]),
            "--backend-state",
            str(deviced_paths["backend_state"]),
            "--updated-socket",
            str(updated_paths["socket"]),
            "--deviced-socket",
            str(deviced_paths["socket"]),
        )
        require("total:" in output, "notification client summary missing total")
        require('"updated"' in output, "notification client summary missing updated source")

        backend_state = read_json(deviced_paths["backend_state"])
        require(any(item["modality"] == "screen" for item in backend_state.get("adapters", [])), "backend state missing screen adapter")

        output = run_python(
            ROOT / "aios/shell/runtime/shell_session.py",
            "plan",
            "--profile",
            str(shell_profile),
            "--json",
        )
        session_plan = json.loads(output)
        require(session_plan["entrypoint"] == "compatibility", "shell live session plan entrypoint mismatch")
        require(session_plan["desktop_host"] == "tk", "shell live session plan host mismatch")
        require(session_plan["session_backend"] == "standalone", "shell live session plan backend mismatch")
        require(
            session_plan["host_runtime"]["nested_fallback"] == "disabled",
            "shell live standalone fallback mismatch",
        )
        require(
            session_plan["panel_host_bridge"]["enabled"] is False,
            "shell live standalone plan should not enable panel host bridge",
        )
        require(
            session_plan["panel_host_bridge"]["snapshot_command"] is None,
            "shell live standalone plan should not expose panel snapshot command",
        )

        output = run_python(
            ROOT / "aios/shell/runtime/shell_session.py",
            "plan",
            "--profile",
            str(shell_profile),
            "--json",
            env={
                **os.environ,
                "AIOS_SHELL_DESKTOP_HOST": "gtk",
                "AIOS_SHELL_SESSION_BACKEND": "compositor",
                "AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH": str(panel_action_log_path),
            },
        )
        override_plan = json.loads(output)
        require(override_plan["entrypoint"] == "formal", "shell live compositor entrypoint mismatch")
        require(override_plan["desktop_host"] == "gtk", "shell live env desktop host override mismatch")
        require(override_plan["session_backend"] == "compositor", "shell live env session backend override mismatch")
        require(
            override_plan["host_runtime"]["host_launch_mode"] == "python-gtk-panel-clients",
            "shell live compositor launch mode mismatch",
        )
        require(
            "shell_panel_clients_gtk.py" in override_plan["host_runtime"]["gtk_panel_client_command"],
            "shell live compositor panel client command mismatch",
        )
        require(
            override_plan["host_runtime"]["panel_clients_enabled"] is True,
            "shell live compositor panel clients should be enabled",
        )
        require(
            override_plan["host_runtime"]["nested_fallback"] == "standalone-gtk",
            "shell live compositor fallback mismatch",
        )
        require(
            override_plan["panel_host_bridge"]["enabled"] is True,
            "shell live compositor plan should enable panel host bridge",
        )
        require(
            override_plan["panel_host_bridge"]["transport"] == "socket-service",
            "shell live compositor bridge transport mismatch",
        )
        require(
            "shell_panel_bridge_service.py" in override_plan["panel_host_bridge"]["service_command"],
            "shell live compositor bridge service command mismatch",
        )
        require(
            "shell_panel_host_bridge.py" in override_plan["panel_host_bridge"]["action_command"],
            "shell live compositor plan action command mismatch",
        )
        require(
            override_plan["panel_host_bridge"]["refresh_ticks"] == 10,
            "shell live compositor plan refresh ticks mismatch",
        )
        require(
            "shell_session.py snapshot" in override_plan["panel_host_bridge"]["snapshot_command"],
            "shell live compositor plan snapshot command mismatch",
        )
        require(
            f"--profile {shell_profile.resolve()}" in override_plan["panel_host_bridge"]["snapshot_command"],
            "shell live compositor plan profile flag missing",
        )
        require(
            f"--profile {shell_profile.resolve()}" in override_plan["panel_host_bridge"]["action_command"],
            "shell live compositor plan action profile flag missing",
        )
        require(
            override_plan["panel_host_bridge"]["action_log_path"] == str(panel_action_log_path.resolve()),
            "shell live compositor plan action log path mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/runtime/shell_panel_host_bridge.py",
            "--profile",
            str(shell_profile),
            "--component",
            "device-backend-status",
            "--json",
        )
        panel_bridge = json.loads(output)
        require(panel_bridge["component"] == "device-backend-status", "panel host bridge component mismatch")
        require(panel_bridge["action_id"] == "refresh", "panel host bridge action mismatch")
        require("status=ready" in panel_bridge["summary"], "panel host bridge summary mismatch")
        require(panel_bridge["result"]["action"] == "refresh", "panel host bridge result action mismatch")
        require(panel_bridge["result"]["status"] == "ready", "panel host bridge result status mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "status",
        )
        shellctl_status = json.loads(output)
        require(
            shellctl_status["components"]["recovery-surface"]["deployment_status"] == "apply-triggered",
            "shellctl status missing recovery deployment",
        )
        require(
            shellctl_status["components"]["notification-center"]["total"] >= 2,
            "shellctl status missing notifications",
        )
        require(
            len(shellctl_status["components"]["capture-indicators"]["active"]) == 1,
            "shellctl status missing indicator state",
        )
        require(
            shellctl_status["components"]["device-backend-status"]["ui_tree_snapshot"]["snapshot_id"]
            == "tree-native-1",
            "shellctl status missing ui_tree snapshot",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "notification-center",
            "model",
        )
        notification_panel = json.loads(output)
        require(notification_panel["panel_id"] == "notification-center-panel", "shell live notification panel id mismatch")
        require(notification_panel["meta"]["notification_count"] >= 2, "shell live notification panel count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "capture-indicators",
            "model",
        )
        capture_panel = json.loads(output)
        require(capture_panel["panel_id"] == "capture-indicators-panel", "shell live capture panel id mismatch")
        require(capture_panel["meta"]["active_count"] == 1, "shell live capture panel active count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "device-backend-status",
            "model",
        )
        backend_panel = json.loads(output)
        require(backend_panel["panel_id"] == "device-backend-status-panel", "shell live backend panel id mismatch")
        require(backend_panel["meta"]["status_count"] >= 1, "shell live backend panel status count mismatch")
        require(backend_panel["meta"]["ui_tree_available"] is True, "shell live backend panel missing ui_tree snapshot")
        require(
            backend_panel["meta"]["ui_tree_capture_mode"] == "native-state-bridge",
            "shell live backend panel ui_tree capture mode mismatch",
        )
        require(
            backend_panel["meta"]["ui_tree_focus"] == "button-1",
            "shell live backend panel ui_tree focus mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(shell_profile),
            "--json",
            "panel",
            "recovery-surface",
            "model",
        )
        recovery_panel = json.loads(output)
        require(recovery_panel["panel_id"] == "recovery-panel", "shell live recovery panel id mismatch")
        require(recovery_panel["header"]["status"] in {"ready", "idle", "degraded"}, "shell live recovery panel status mismatch")
        require(recovery_panel["meta"]["action_count"] >= 2, "shell live recovery panel action count mismatch")

        print("shell live smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell live smoke failed: {error}")
        return 1
    finally:
        updated_log = terminate(updated_process)
        deviced_log = terminate(deviced_process)
        if updated_log:
            print("\n--- updated log ---")
            print(updated_log)
        if deviced_log:
            print("\n--- deviced log ---")
            print(deviced_log)
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
