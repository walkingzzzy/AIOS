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
import tempfile
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS updated cross-restart smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing updated binary")
    parser.add_argument("--updated", type=Path, help="Path to updated binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(ROOT), name)


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


def ensure_binary(path: Path) -> None:
    if path.exists():
        return
    print(f"Missing binary: updated={path}")
    print("Build it first, for example: cargo build -p aios-updated")
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
    last_error = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for updated health: {last_error}")


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
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


def write_boot_state(cmdline_path: Path, current_entry_path: Path, marker_path: Path, slot: str) -> None:
    cmdline_path.write_text(f"quiet splash aios.slot={slot}\n")
    current_entry_path.write_text(f"aios-{slot}.conf\n")
    marker_path.write_text("success\n")


def print_log(name: str, process: subprocess.Popen | None) -> None:
    if process is None or process.stdout is None:
        return
    output = process.stdout.read()
    if output.strip():
        print(f"\n--- {name} log ---")
        print(output.rstrip())


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("updated restart smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    updated = resolve_binary("updated", args.updated, args.bin_dir)
    ensure_binary(updated)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-updated-restart-"))
    runtime_root = temp_root / "runtime"
    state_root = temp_root / "state"
    sysupdate_dir = temp_root / "sysupdate"
    sysupdate_dir.mkdir(parents=True, exist_ok=True)
    (sysupdate_dir / "00-aios-root.transfer").write_text("transfer\n")

    boot_dir = state_root / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)
    cmdline_path = boot_dir / "cmdline"
    current_entry_path = boot_dir / "current-entry"
    next_entry_path = boot_dir / "next-entry"
    bootctl_context_path = state_root / "bootctl-context.txt"
    boot_success_marker_path = state_root / "boot-success"
    fake_bootctl_path = state_root / "fake-bootctl.sh"
    health_context_path = state_root / "health-context.txt"
    apply_context_path = state_root / "apply-context.txt"
    rollback_context_path = state_root / "rollback-context.txt"
    boot_state_path = state_root / "boot-control.json"
    recovery_surface_path = state_root / "recovery-surface.json"
    deployment_state_path = state_root / "deployment-state.json"

    write_boot_state(cmdline_path, current_entry_path, boot_success_marker_path, "a")
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

    failed = False
    process: subprocess.Popen | None = None
    try:
        socket_path = Path(env["AIOS_UPDATED_SOCKET_PATH"])

        process = launch(updated, env)
        wait_for_socket(socket_path, args.timeout)
        wait_for_health(socket_path, args.timeout)

        apply_result = rpc_call(
            socket_path,
            "update.apply",
            {"target_version": "0.1.1", "reason": "restart-stage", "dry_run": False},
            timeout=args.timeout,
        )
        require(apply_result["status"] == "accepted", "update.apply should be accepted")
        require(bootctl_context_path.read_text() == "set-oneshot|aios-b.conf", "bootctl apply context mismatch")
        staged_boot = read_json(boot_state_path)
        require(staged_boot["current_slot"] == "a", "current slot should remain a before reboot")
        require(staged_boot.get("staged_slot") == "b", "staged slot should be b before reboot")
        require(next_entry_path.read_text().strip() == "aios-b.conf", "next entry mismatch before reboot")
        terminate(process)
        print_log("updated stage", process)
        process = None

        write_boot_state(cmdline_path, current_entry_path, boot_success_marker_path, "b")
        process = launch(updated, env)
        wait_for_socket(socket_path, args.timeout)
        wait_for_health(socket_path, args.timeout)
        require(recovery_surface_path.exists(), "recovery surface should be synced during startup")
        restarted_surface = read_json(recovery_surface_path)
        restarted_boot = read_json(boot_state_path)
        restarted_deployment = read_json(deployment_state_path)
        require(restarted_boot["current_slot"] == "b", "startup sync should detect slot b")
        require(restarted_boot["last_good_slot"] == "b", "startup sync should mark slot b good")
        require(restarted_boot.get("staged_slot") is None, "startup sync should clear staged slot after successful boot")
        require(restarted_boot["boot_success"] is True, "startup sync should persist boot success")
        require(restarted_deployment["status"] == "up-to-date", "startup sync should converge deployment status")
        require(restarted_deployment["current_version"] == "0.1.1", "startup sync should promote deployment version")
        require(restarted_deployment.get("pending_action") is None, "startup sync should clear pending action")
        require(restarted_deployment.get("active_recovery_id") is None, "startup sync should clear active recovery id")
        require(restarted_surface.get("current_slot") == "b", "startup recovery surface current slot mismatch")
        require(restarted_surface.get("last_good_slot") == "b", "startup recovery surface last_good mismatch")
        require("rollback" in restarted_surface["available_actions"], "startup recovery surface should advertise rollback")
        require(
            health_context_path.read_text().startswith(f"health_probe|{env['AIOS_UPDATED_HEALTH_PROBE_PATH']}|"),
            "startup health probe context missing",
        )

        rollback = rpc_call(
            socket_path,
            "update.rollback",
            {"recovery_id": apply_result["recovery_ref"], "reason": "restart-rollback", "dry_run": False},
            timeout=args.timeout,
        )
        require(rollback["status"] == "accepted", "update.rollback should be accepted")
        require(bootctl_context_path.read_text() == "set-oneshot|aios-a.conf", "bootctl rollback context mismatch")
        rollback_boot = read_json(boot_state_path)
        require(rollback_boot["current_slot"] == "b", "rollback should still report slot b before reboot")
        require(rollback_boot.get("staged_slot") == "a", "rollback should stage slot a before reboot")
        terminate(process)
        print_log("updated rollback", process)
        process = None

        write_boot_state(cmdline_path, current_entry_path, boot_success_marker_path, "a")
        process = launch(updated, env)
        wait_for_socket(socket_path, args.timeout)
        wait_for_health(socket_path, args.timeout)
        final_surface = read_json(recovery_surface_path)
        final_boot = read_json(boot_state_path)
        final_deployment = read_json(deployment_state_path)
        final_recovery_record = read_json(Path(state_root / "recovery" / f"{apply_result['recovery_ref']}.json"))
        require(final_boot["current_slot"] == "a", "final startup sync should detect slot a")
        require(final_boot["last_good_slot"] == "a", "final startup sync should mark slot a good")
        require(final_boot.get("staged_slot") is None, "final startup sync should clear staged slot")
        require(final_deployment["status"] == "up-to-date", "final startup sync should converge deployment status")
        require(final_deployment["current_version"] == "0.1.0", "final startup sync should restore deployment version")
        require(final_deployment.get("pending_action") is None, "final startup sync should clear pending action")
        require(final_deployment.get("active_recovery_id") is None, "final startup sync should clear active recovery id")
        require(final_recovery_record["status"] == "rolled-back", "recovery point should be marked rolled-back")
        require(final_surface.get("current_slot") == "a", "final recovery surface current slot mismatch")
        require(final_surface.get("last_good_slot") == "a", "final recovery surface last_good mismatch")

        print("updated restart smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"updated restart smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        print_log("updated final", process)
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
