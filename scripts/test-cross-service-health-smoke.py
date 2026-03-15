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

import yaml

from aios_cargo_bins import default_aios_bin_dir


ROOT = Path(__file__).resolve().parent.parent
BUILD_REPORT_SCRIPT = ROOT / "scripts" / "build-cross-service-health-report.py"
SHELL_CONTROL_PROVIDER = ROOT / "aios" / "shell" / "runtime" / "shell_control_provider.py"
SCREEN_CAPTURE_PROVIDER = ROOT / "aios" / "shell" / "runtime" / "screen_capture_portal_provider.py"
BROWSER_PROVIDER = ROOT / "aios" / "compat" / "browser" / "runtime" / "browser_provider.py"
OFFICE_PROVIDER = ROOT / "aios" / "compat" / "office" / "runtime" / "office_provider.py"
CODE_SANDBOX_PROVIDER = ROOT / "aios" / "compat" / "code-sandbox" / "runtime" / "aios_sandbox_executor.py"
UI_TREE_COLLECTOR = ROOT / "aios" / "services" / "deviced" / "runtime" / "ui_tree_atspi_snapshot.py"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "cross-service-health-report"
DEFAULT_DELIVERY_MANIFEST = ROOT / "out" / "aios-system-delivery" / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS cross-service health exporter smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing compiled service binaries")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument("--updated", type=Path, help="Path to updated binary")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for sockets and probes")
    parser.add_argument(
        "--delivery-manifest",
        type=Path,
        default=DEFAULT_DELIVERY_MANIFEST,
        help="Path to the delivery manifest consumed by the exporter",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help="Output prefix for the generated report artifacts",
    )
    parser.add_argument("--keep-state", action="store_true", help="Keep the temp runtime/state directory on success")
    return parser.parse_args()


def repo_root() -> Path:
    return ROOT


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(repo_root()) / name


def ensure_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing files for cross-service health smoke:")
        for item in missing:
            print(f"  - {item}")
        raise SystemExit(2)


def rpc_call(socket_path: Path, method: str, params: dict[str, object], timeout: float) -> dict:
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
            return rpc_call(socket_path, "system.health.get", {}, timeout=min(timeout, 1.5))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def wait_for_update_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "update.health.get", {}, timeout=min(timeout, 1.5))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for update.health.get on {socket_path}: {last_error}")


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
        try:
            process.wait(timeout=max(0.1, deadline - time.time()))
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


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def make_control_plane_env(root: Path) -> dict[str, str]:
    run_root = root / "run"
    state_root = root / "state"
    run_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    provider_dirs = [
        ROOT / "aios" / "sdk" / "providers",
        ROOT / "aios" / "runtime" / "providers",
        ROOT / "aios" / "shell" / "providers",
        ROOT / "aios" / "compat" / "browser" / "providers",
        ROOT / "aios" / "compat" / "office" / "providers",
        ROOT / "aios" / "compat" / "mcp-bridge" / "providers",
        ROOT / "aios" / "compat" / "code-sandbox" / "providers",
    ]

    env = os.environ.copy()
    env.update(
        {
            "AIOS_AGENTD_RUNTIME_DIR": str(run_root / "agentd"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "agentd"),
            "AIOS_AGENTD_SOCKET_PATH": str(run_root / "agentd" / "agentd.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(run_root / "sessiond" / "sessiond.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(run_root / "runtimed" / "runtimed.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "registry"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": os.pathsep.join(str(path) for path in provider_dirs),
            "AIOS_SESSIOND_RUNTIME_DIR": str(run_root / "sessiond"),
            "AIOS_SESSIOND_STATE_DIR": str(state_root / "sessiond"),
            "AIOS_SESSIOND_SOCKET_PATH": str(run_root / "sessiond" / "sessiond.sock"),
            "AIOS_SESSIOND_DATABASE": str(state_root / "sessiond" / "sessiond.sqlite3"),
            "AIOS_SESSIOND_OBSERVABILITY_LOG": str(state_root / "runtimed" / "observability.jsonl"),
            "AIOS_POLICYD_RUNTIME_DIR": str(run_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(ROOT / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(
                ROOT / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"
            ),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_OBSERVABILITY_LOG": str(state_root / "runtimed" / "observability.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
            "AIOS_POLICYD_APPROVAL_TTL_SECONDS": "900",
            "AIOS_RUNTIMED_RUNTIME_DIR": str(run_root / "runtimed"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "runtimed"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(run_root / "runtimed" / "runtimed.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(ROOT / "aios" / "runtime" / "profiles" / "default-runtime-profile.yaml"),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(ROOT / "aios" / "runtime" / "profiles" / "default-route-profile.yaml"),
            "AIOS_RUNTIMED_POLICYD_SOCKET": str(run_root / "policyd" / "policyd.sock"),
            "AIOS_RUNTIMED_REMOTE_AUDIT_LOG": str(state_root / "runtimed" / "remote-audit.jsonl"),
            "AIOS_RUNTIMED_OBSERVABILITY_LOG": str(state_root / "runtimed" / "observability.jsonl"),
        }
    )
    return env


def make_deviced_env(root: Path, control_env: dict[str, str]) -> dict[str, str]:
    runtime_root = root / "run" / "deviced"
    state_root = root / "state" / "deviced"
    shared_observability_log = root / "state" / "runtimed" / "observability.jsonl"
    backend_state_path = state_root / "backend-state.json"
    pipewire_socket_path = state_root / "pipewire-0"
    input_root = state_root / "input"
    camera_root = state_root / "camera"
    screencast_state_path = state_root / "screencast-state.json"
    pipewire_node_path = state_root / "pipewire-node.json"
    ui_tree_state_path = state_root / "ui-tree-state.json"
    ui_tree_fixture_path = state_root / "ui-tree-live-fixture.json"

    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    input_root.mkdir(parents=True, exist_ok=True)
    camera_root.mkdir(parents=True, exist_ok=True)
    pipewire_socket_path.write_text("ready\n")
    (input_root / "event0").write_text("keyboard\n")
    (camera_root / "video0").write_text("ready\n")
    write_json(
        screencast_state_path,
        {
            "portal_session_ref": "session-portal-1",
            "stream_node_id": 42,
            "window_ref": "window-1",
            "resolution": "1280x720",
        },
    )
    write_json(
        pipewire_node_path,
        {
            "node_id": 77,
            "channel_layout": "stereo",
        },
    )
    write_json(
        ui_tree_state_path,
        {
            "snapshot_id": "tree-native-1",
            "focus_node": "button-1",
        },
    )
    write_json(
        ui_tree_fixture_path,
        {
            "snapshot_id": "tree-live-1",
            "applications": [
                {
                    "node_id": "desktop-0/app-0",
                    "name": "AIOS Shell",
                    "role": "application",
                    "states": ["active"],
                }
            ],
        },
    )

    env = os.environ.copy()
    env.update(
        {
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root),
            "AIOS_DEVICED_STATE_DIR": str(state_root),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "captures.json"),
            "AIOS_DEVICED_OBSERVABILITY_LOG": str(shared_observability_log),
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
            "AIOS_DEVICED_POLICY_SOCKET_PATH": control_env["AIOS_POLICYD_SOCKET_PATH"],
            "AIOS_DEVICED_SCREEN_PROBE_COMMAND": (
                "python3 -c 'import json; print(json.dumps({\"available\": True, "
                "\"readiness\": \"native-live\", \"payload\": {\"probe_frame\": True}}))'"
            ),
            "AIOS_DEVICED_CAMERA_PROBE_COMMAND": "printf 'probe failed\\n' >&2; exit 7",
        }
    )
    return env


def make_updated_env(root: Path) -> tuple[dict[str, str], dict[str, Path]]:
    runtime_root = root / "run" / "updated"
    state_root = root / "state" / "updated"
    shared_observability_log = root / "state" / "runtimed" / "observability.jsonl"
    sysupdate_dir = root / "sysupdate"
    boot_dir = state_root / "boot"
    health_probe_path = state_root / "health-probe.json"
    recovery_surface_path = state_root / "recovery-surface.json"
    boot_state_path = state_root / "boot-control.json"
    deployment_state_path = state_root / "deployment-state.json"

    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    sysupdate_dir.mkdir(parents=True, exist_ok=True)
    boot_dir.mkdir(parents=True, exist_ok=True)
    (sysupdate_dir / "00-aios-root.transfer").write_text("transfer\n")

    cmdline_path = boot_dir / "cmdline"
    current_entry_path = boot_dir / "current-entry"
    next_entry_path = boot_dir / "next-entry"
    bootctl_context_path = state_root / "bootctl-context.txt"
    boot_success_marker_path = state_root / "boot-success"
    fake_bootctl_path = state_root / "fake-bootctl.sh"
    check_context_path = state_root / "check-context.txt"
    apply_context_path = state_root / "apply-context.txt"
    rollback_context_path = state_root / "rollback-context.txt"
    health_context_path = state_root / "health-context.txt"

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
            "AIOS_UPDATED_SOCKET_PATH": str(runtime_root / "updated.sock"),
            "AIOS_UPDATED_DEPLOYMENT_STATE": str(deployment_state_path),
            "AIOS_UPDATED_OBSERVABILITY_LOG": str(shared_observability_log),
            "AIOS_UPDATED_DIAGNOSTICS_DIR": str(state_root / "diagnostics"),
            "AIOS_UPDATED_RECOVERY_DIR": str(state_root / "recovery"),
            "AIOS_UPDATED_SYSUPDATE_DIR": str(sysupdate_dir),
            "AIOS_UPDATED_HEALTH_PROBE_PATH": str(health_probe_path),
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
            "AIOS_UPDATED_SYSUPDATE_CHECK_COMMAND": (
                f"printf '%s' \"$AIOS_UPDATED_OPERATION|$AIOS_UPDATED_REQUEST_CHANNEL|$AIOS_UPDATED_REQUEST_CURRENT_VERSION|$AIOS_UPDATED_ARTIFACT_COUNT\" > {shlex.quote(str(check_context_path))} && "
                "printf 'sysupdate check ok'"
            ),
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
    return env, {
        "health_probe_path": health_probe_path,
        "recovery_surface_path": recovery_surface_path,
        "boot_state_path": boot_state_path,
        "deployment_state_path": deployment_state_path,
        "next_entry_path": next_entry_path,
        "health_context_path": health_context_path,
    }


def make_shell_control_env(
    root: Path,
    control_env: dict[str, str],
    deviced_env: dict[str, str],
    updated_env: dict[str, str],
    updated_paths: dict[str, Path],
) -> dict[str, str]:
    runtime_root = root / "run" / "shell-provider"
    state_root = root / "state" / "shell-provider"
    panel_action_log = state_root / "panel-action-events.jsonl"
    focus_state = state_root / "focus-state.json"
    approval_fixture = state_root / "approvals.json"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    approval_fixture.write_text(json.dumps({"approvals": []}, indent=2, ensure_ascii=False) + "\n")
    panel_action_log.write_text("")

    env = os.environ.copy()
    env.update(
        {
            "AIOS_SHELL_PROVIDER_RUNTIME_DIR": str(runtime_root),
            "AIOS_SHELL_PROVIDER_STATE_DIR": str(state_root),
            "AIOS_SHELL_PROVIDER_SOCKET_PATH": str(runtime_root / "shell-control-provider.sock"),
            "AIOS_SHELL_PROVIDER_POLICYD_SOCKET": control_env["AIOS_POLICYD_SOCKET_PATH"],
            "AIOS_SHELL_PROVIDER_FOCUS_STATE_PATH": str(focus_state),
            "AIOS_SHELL_PROVIDER_RECOVERY_SURFACE": str(updated_paths["recovery_surface_path"]),
            "AIOS_SHELL_PROVIDER_UPDATED_SOCKET": updated_env["AIOS_UPDATED_SOCKET_PATH"],
            "AIOS_SHELL_PROVIDER_INDICATOR_STATE": deviced_env["AIOS_DEVICED_INDICATOR_STATE_PATH"],
            "AIOS_SHELL_PROVIDER_BACKEND_STATE": deviced_env["AIOS_DEVICED_BACKEND_STATE_PATH"],
            "AIOS_SHELL_PROVIDER_DEVICED_SOCKET": deviced_env["AIOS_DEVICED_SOCKET_PATH"],
            "AIOS_SHELL_PROVIDER_PANEL_ACTION_LOG": str(panel_action_log),
            "AIOS_SHELL_PROVIDER_APPROVAL_FIXTURE": str(approval_fixture),
        }
    )
    return env


def make_screen_capture_env(
    root: Path,
    control_env: dict[str, str],
    deviced_env: dict[str, str],
) -> dict[str, str]:
    runtime_root = root / "run" / "screen-provider"
    runtime_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "AIOS_SCREEN_CAPTURE_PROVIDER_RUNTIME_DIR": str(runtime_root),
            "AIOS_SCREEN_CAPTURE_PROVIDER_SOCKET_PATH": str(runtime_root / "screen-capture-provider.sock"),
            "AIOS_SCREEN_CAPTURE_PROVIDER_POLICYD_SOCKET": control_env["AIOS_POLICYD_SOCKET_PATH"],
            "AIOS_SCREEN_CAPTURE_PROVIDER_DEVICED_SOCKET": deviced_env["AIOS_DEVICED_SOCKET_PATH"],
        }
    )
    return env


def build_spec(
    spec_path: Path,
    control_env: dict[str, str],
    deviced_env: dict[str, str],
    updated_env: dict[str, str],
    updated_paths: dict[str, Path],
    shell_env: dict[str, str],
    screen_env: dict[str, str],
    delivery_manifest: Path,
    hardware_validation_index: Path,
) -> None:
    sources = [
        {
            "source_id": "sessiond",
            "kind": "rpc-service",
            "component_kind": "service",
            "service_id": "aios-sessiond",
            "socket_path": control_env["AIOS_SESSIOND_SOCKET_PATH"],
            "summary": "Service health export for aios-sessiond",
        },
        {
            "source_id": "policyd",
            "kind": "rpc-service",
            "component_kind": "service",
            "service_id": "aios-policyd",
            "socket_path": control_env["AIOS_POLICYD_SOCKET_PATH"],
            "summary": "Service health export for aios-policyd",
        },
        {
            "source_id": "runtimed",
            "kind": "rpc-service",
            "component_kind": "runtime",
            "service_id": "aios-runtimed",
            "socket_path": control_env["AIOS_RUNTIMED_SOCKET_PATH"],
            "summary": "Runtime health export for aios-runtimed",
        },
        {
            "source_id": "agentd",
            "kind": "rpc-service",
            "component_kind": "service",
            "service_id": "aios-agentd",
            "socket_path": control_env["AIOS_AGENTD_SOCKET_PATH"],
            "summary": "Service health export for aios-agentd",
        },
        {
            "source_id": "provider-registry",
            "kind": "provider-registry",
            "component_kind": "provider",
            "service_id": "aios-agentd",
            "socket_path": control_env["AIOS_AGENTD_SOCKET_PATH"],
            "provider_ids": [
                "system.files.local",
                "system.intent.local",
                "device.metadata.local",
                "runtime.local.inference",
                "shell.control.local",
                "shell.screen-capture.portal",
                "compat.browser.automation.local",
                "compat.office.document.local",
                "compat.mcp.bridge.local",
                "compat.code.sandbox.local",
            ],
            "summary": "Provider registry health export",
        },
        {
            "source_id": "deviced",
            "kind": "rpc-service",
            "component_kind": "device",
            "service_id": "aios-deviced",
            "socket_path": deviced_env["AIOS_DEVICED_SOCKET_PATH"],
            "summary": "Device health export for aios-deviced",
        },
        {
            "source_id": "updated",
            "kind": "rpc-update",
            "component_kind": "update",
            "service_id": "aios-updated",
            "socket_path": updated_env["AIOS_UPDATED_SOCKET_PATH"],
            "probe_path": str(updated_paths["health_probe_path"]),
            "artifact_path": str(updated_paths["health_probe_path"]),
            "boot_id": "boot-smoke",
            "update_id": "update-smoke",
            "summary": "Update health export for aios-updated",
        },
        {
            "source_id": "shell-control-provider",
            "kind": "rpc-service",
            "component_kind": "shell",
            "service_id": "aios-shell-control-provider",
            "socket_path": shell_env["AIOS_SHELL_PROVIDER_SOCKET_PATH"],
            "summary": "Shell control provider health export",
        },
        {
            "source_id": "screen-capture-provider",
            "kind": "rpc-service",
            "component_kind": "shell",
            "service_id": "aios-screen-capture-portal-provider",
            "socket_path": screen_env["AIOS_SCREEN_CAPTURE_PROVIDER_SOCKET_PATH"],
            "summary": "Shell screen capture provider health export",
        },
        {
            "source_id": "browser-compat-provider",
            "kind": "command-health",
            "component_kind": "provider",
            "service_id": "aios-browser-automation-provider",
            "provider_id": "compat.browser.automation.local",
            "command": [sys.executable, str(BROWSER_PROVIDER), "health"],
            "summary": "Compat browser provider health export",
        },
        {
            "source_id": "office-compat-provider",
            "kind": "command-health",
            "component_kind": "provider",
            "service_id": "aios-office-document-provider",
            "provider_id": "compat.office.document.local",
            "command": [sys.executable, str(OFFICE_PROVIDER), "health"],
            "summary": "Compat office provider health export",
        },
        {
            "source_id": "code-sandbox-provider",
            "kind": "command-health",
            "component_kind": "provider",
            "service_id": "aios-code-sandbox-provider",
            "provider_id": "compat.code.sandbox.local",
            "command": [sys.executable, str(CODE_SANDBOX_PROVIDER), "health"],
            "summary": "Compat code sandbox provider health export",
        },
        {
            "source_id": "delivery-bundle",
            "kind": "delivery-artifact",
            "component_kind": "platform",
            "service_id": "aios-system-delivery",
            "manifest_path": str(delivery_manifest),
            "summary": "Delivery manifest health export",
        },
        {
            "source_id": "hardware-validation",
            "kind": "evidence-index",
            "component_kind": "hardware",
            "service_id": "aios-hardware-validation",
            "index_path": str(hardware_validation_index),
            "summary": "Hardware validation evidence index export",
        },
    ]
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(yaml.safe_dump({"sources": sources}, sort_keys=False, allow_unicode=False))


def main() -> int:
    args = parse_args()
    binaries = {
        "sessiond": resolve_binary("sessiond", args.sessiond, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "runtimed": resolve_binary("runtimed", args.runtimed, args.bin_dir),
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
        "deviced": resolve_binary("deviced", args.deviced, args.bin_dir),
        "updated": resolve_binary("updated", args.updated, args.bin_dir),
        "build-report": BUILD_REPORT_SCRIPT,
        "shell-provider": SHELL_CONTROL_PROVIDER,
        "screen-provider": SCREEN_CAPTURE_PROVIDER,
        "browser-provider": BROWSER_PROVIDER,
        "office-provider": OFFICE_PROVIDER,
        "code-sandbox-provider": CODE_SANDBOX_PROVIDER,
        "delivery-manifest": args.delivery_manifest,
    }
    ensure_paths(binaries)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-cross-service-health-", dir="/tmp" if Path("/tmp").exists() else None))
    control_env = make_control_plane_env(temp_root)
    deviced_env = make_deviced_env(temp_root, control_env)
    updated_env, updated_paths = make_updated_env(temp_root)
    shell_env = make_shell_control_env(temp_root, control_env, deviced_env, updated_env, updated_paths)
    screen_env = make_screen_capture_env(temp_root, control_env, deviced_env)

    processes = {
        "sessiond": launch([str(binaries["sessiond"])], control_env),
        "policyd": launch([str(binaries["policyd"])], control_env),
        "runtimed": launch([str(binaries["runtimed"])], control_env),
        "agentd": launch([str(binaries["agentd"])], control_env),
        "deviced": launch([str(binaries["deviced"])], deviced_env),
        "updated": launch([str(binaries["updated"])], updated_env),
    }
    failed = False

    try:
        for name, socket_path in [
            ("sessiond", Path(control_env["AIOS_SESSIOND_SOCKET_PATH"])),
            ("policyd", Path(control_env["AIOS_POLICYD_SOCKET_PATH"])),
            ("runtimed", Path(control_env["AIOS_RUNTIMED_SOCKET_PATH"])),
            ("agentd", Path(control_env["AIOS_AGENTD_SOCKET_PATH"])),
            ("deviced", Path(deviced_env["AIOS_DEVICED_SOCKET_PATH"])),
            ("updated", Path(updated_env["AIOS_UPDATED_SOCKET_PATH"])),
        ]:
            wait_for_socket(socket_path, args.timeout)
            health = wait_for_health(socket_path, args.timeout)
            require(health.get("status") in {"ready", "idle", "degraded"}, f"{name} returned unexpected status {health}")

        device_state = rpc_call(Path(deviced_env["AIOS_DEVICED_SOCKET_PATH"]), "device.state.get", {}, args.timeout)
        require(device_state.get("service_id") == "aios-deviced", "device.state.get did not return aios-deviced")
        update_health = wait_for_update_health(Path(updated_env["AIOS_UPDATED_SOCKET_PATH"]), args.timeout)
        require(update_health.get("overall_status") in {"ready", "idle", "degraded"}, "updated health probe did not converge")
        shared_observability_log = Path(control_env["AIOS_RUNTIMED_OBSERVABILITY_LOG"])
        require(shared_observability_log.exists(), "shared observability log missing before provider bootstrap")
        shared_entries = [
            json.loads(line)
            for line in shared_observability_log.read_text().splitlines()
            if line.strip()
        ]
        require(
            any(
                entry.get("source") == "aios-updated"
                and entry.get("kind") == "update.health.reported"
                for entry in shared_entries
            ),
            "shared observability log missing updated health trace",
        )
        require(
            any(
                entry.get("source") == "aios-deviced"
                and entry.get("kind") == "device.state.reported"
                for entry in shared_entries
            ),
            "shared observability log missing deviced state trace",
        )

        processes["shell-provider"] = launch([sys.executable, str(SHELL_CONTROL_PROVIDER)], shell_env)
        processes["screen-provider"] = launch([sys.executable, str(SCREEN_CAPTURE_PROVIDER)], screen_env)

        for name, socket_path in [
            ("shell-provider", Path(shell_env["AIOS_SHELL_PROVIDER_SOCKET_PATH"])),
            ("screen-provider", Path(screen_env["AIOS_SCREEN_CAPTURE_PROVIDER_SOCKET_PATH"])),
        ]:
            wait_for_socket(socket_path, args.timeout)
            health = wait_for_health(socket_path, args.timeout)
            require(health.get("status") == "ready", f"{name} health is not ready: {health}")

        spec_path = temp_root / "cross-service-health-spec.yaml"
        hardware_validation_index = temp_root / "state" / "hardware-validation" / "evidence-index.json"
        write_json(
            hardware_validation_index,
            {
                "platform_id": "generic-x86_64-uefi",
                "index_id": "hardware-validation-generic-x86_64-uefi",
                "validation_kind": "hardware-validation",
                "validation_status": "passed",
                "generated_at": "2026-03-14T00:00:00Z",
                "summary": {
                    "final_current_slot": "b",
                },
                "artifacts": {
                    "report": "hardware-validation-report.md",
                },
            },
        )
        build_spec(
            spec_path,
            control_env,
            deviced_env,
            updated_env,
            updated_paths,
            shell_env,
            screen_env,
            args.delivery_manifest,
            hardware_validation_index,
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(BUILD_REPORT_SCRIPT),
                "--spec",
                str(spec_path),
                "--output-prefix",
                str(args.output_prefix),
                "--timeout",
                str(min(args.timeout, 8.0)),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.stdout.strip():
            print(completed.stdout.rstrip())
        if completed.stderr.strip():
            print(completed.stderr.rstrip())
        require(completed.returncode == 0, "cross-service health report builder returned non-zero")

        report_path = args.output_prefix.with_suffix(".json")
        events_path = (
            args.output_prefix.parent
            / args.output_prefix.name.replace("-report", "-events")
        ).with_suffix(".jsonl")
        report = json.loads(report_path.read_text())
        require(report["overall_status"] == "passed", "cross-service health report did not pass")
        required_checks = {
            "sessiond",
            "policyd",
            "runtimed",
            "agentd",
            "provider-registry",
            "deviced",
            "updated",
            "shell-control-provider",
            "screen-capture-provider",
            "browser-compat-provider",
            "office-compat-provider",
            "code-sandbox-provider",
            "delivery-bundle",
            "hardware-validation",
        }
        check_ids = {item["check_id"] for item in report.get("checks", [])}
        require(not (required_checks - check_ids), f"missing exporter checks: {sorted(required_checks - check_ids)}")
        require(report["summary"]["source_count"] == 14, f"unexpected source_count: {report['summary']['source_count']}")
        require(report["summary"]["event_count"] == 23, f"unexpected event_count: {report['summary']['event_count']}")
        require(
            set(report["summary"]["component_kinds"]) >= {"service", "runtime", "device", "update", "shell", "provider", "platform", "hardware"},
            "component kind coverage missing from summary",
        )
        service_ids = {item["service_id"] for item in report.get("events", [])}
        require(
            {
                "aios-sessiond",
                "aios-policyd",
                "aios-runtimed",
                "aios-agentd",
                "aios-deviced",
                "aios-updated",
                "aios-system-delivery",
                "aios-hardware-validation",
            } <= service_ids,
            "missing core service ids in health events",
        )
        require(events_path.exists(), "cross-service health events jsonl missing")
        require(any(event.get("provider_id") == "runtime.local.inference" for event in report["events"]), "provider registry event missing runtime.local.inference")
        require(any(event.get("service_id") == "aios-system-delivery" for event in report["events"]), "delivery event missing")
        require(
            any(
                event.get("service_id") == "aios-hardware-validation"
                and event.get("component_kind") == "hardware"
                and event.get("artifact_path") == str(hardware_validation_index)
                for event in report["events"]
            ),
            "hardware validation event missing",
        )
        require(
            any(event.get("service_id") == "aios-updated" and event.get("artifact_path") == str(updated_paths["health_probe_path"]) for event in report["events"]),
            "updated event missing health probe artifact path",
        )

        print(
            json.dumps(
                {
                    "overall_status": report["overall_status"],
                    "report": str(report_path),
                    "events": str(events_path),
                    "source_count": report["summary"]["source_count"],
                    "event_count": report["summary"]["event_count"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as error:
        failed = True
        print(f"cross-service health smoke failed: {error}")
        return 1
    finally:
        terminate(list(processes.values()))
        print_logs(processes)
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
