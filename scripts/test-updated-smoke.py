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

from aios_cargo_bins import default_aios_bin_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS updated smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing updated binary")
    parser.add_argument("--updated", type=Path, help="Path to updated binary")
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
    if not path.exists():
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
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception:
            time.sleep(0.1)
    raise TimeoutError("Timed out waiting for updated health")


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(process: subprocess.Popen) -> None:
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    args = parse_args()
    updated = resolve_binary("updated", args.updated, args.bin_dir)
    ensure_binary(updated)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-updated-smoke-"))
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
    check_context_path = state_root / "check-context.txt"
    apply_context_path = state_root / "apply-context.txt"
    rollback_context_path = state_root / "rollback-context.txt"
    health_context_path = state_root / "health-context.txt"
    boot_state_path = state_root / "boot-control.json"
    recovery_surface_path = state_root / "recovery-surface.json"
    observability_log_path = state_root / "observability.jsonl"

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
            "AIOS_UPDATED_DEPLOYMENT_STATE": str(state_root / "deployment-state.json"),
            "AIOS_UPDATED_OBSERVABILITY_LOG": str(observability_log_path),
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

    process = launch(updated, env)
    failed = False
    try:
        socket_path = Path(env["AIOS_UPDATED_SOCKET_PATH"])
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        print(f"updated ready: {health['status']} @ {health['socket_path']}")

        check = rpc_call(
            socket_path,
            "update.check",
            {"channel": "beta", "current_version": "1.2.3"},
            timeout=args.timeout,
        )
        require(check["status"] in {"ready-to-stage", "waiting-for-artifacts"}, "unexpected update.check status")
        require("00-aios-root.transfer" in check["artifacts"], "missing sysupdate artifact")
        require(check_context_path.read_text() == "check|beta|1.2.3|1", "check command context mismatch")
        require(recovery_surface_path.exists(), "recovery surface not written after check")

        apply_result = rpc_call(
            socket_path,
            "update.apply",
            {"target_version": "0.1.1", "reason": "smoke-stage", "dry_run": False},
            timeout=args.timeout,
        )
        require(apply_result["status"] == "accepted", "update.apply was not accepted")
        require(apply_result["deployment_status"] in {"apply-triggered", "staged-update"}, "unexpected update.apply deployment status")
        require(bool(apply_result.get("recovery_ref")), "update.apply did not return recovery_ref")
        require(
            apply_context_path.read_text().startswith("apply|0.1.1|smoke-stage|recovery-"),
            "apply command context mismatch",
        )
        require(boot_state_path.exists(), "boot control file missing after apply")
        require(recovery_surface_path.exists(), "recovery surface missing after apply")
        require(bootctl_context_path.read_text() == "set-oneshot|aios-b.conf", "bootctl apply context mismatch")
        require(next_entry_path.read_text().strip() == "aios-b.conf", "boot next-entry mismatch after apply")
        boot_state = read_json(boot_state_path)
        require(boot_state["current_slot"] == "a", "boot state current slot should remain a before reboot")
        require(boot_state.get("staged_slot") == "b", "boot state staged slot mismatch after apply")
        require(boot_state["last_good_slot"] == "a", "last good slot should remain a before verification")

        cmdline_path.write_text("quiet splash aios.slot=b\n")
        current_entry_path.write_text("aios-b.conf\n")
        boot_success_marker_path.write_text("success\n")

        health_report = rpc_call(socket_path, "update.health.get", {}, timeout=args.timeout)
        require(health_report["overall_status"] in {"ready", "idle", "degraded"}, "unexpected update.health.get status")
        require(any("probe_summary=probe ok" in note for note in health_report["notes"]), "probe summary missing from health notes")
        require(
            health_context_path.read_text() == f"health_probe|{env['AIOS_UPDATED_HEALTH_PROBE_PATH']}|{apply_result['deployment_status']}",
            "health probe command context mismatch",
        )
        verified_boot_state = read_json(boot_state_path)
        require(verified_boot_state["current_slot"] == "b", "boot verify current slot mismatch")
        require(verified_boot_state["last_good_slot"] == "b", "boot verify did not mark slot b good")
        require(verified_boot_state.get("staged_slot") is None, "staged slot should clear after successful boot verify")
        require(verified_boot_state["boot_success"] is True, "boot success flag not persisted")
        deployment_state = read_json(Path(env["AIOS_UPDATED_DEPLOYMENT_STATE"]))
        require(deployment_state["status"] == "up-to-date", "deployment status should converge after boot verify")
        require(deployment_state["current_version"] == "0.1.1", "deployment version should promote after boot verify")
        require(deployment_state.get("pending_action") is None, "pending action should clear after boot verify")
        require(deployment_state.get("active_recovery_id") is None, "active recovery id should clear after boot verify")
        recovery_surface = read_json(recovery_surface_path)
        require(recovery_surface["current_slot"] == "b", "recovery surface current slot mismatch")
        require("rollback" in recovery_surface["available_actions"], "recovery surface should advertise rollback")

        recovery_surface_rpc = rpc_call(socket_path, "recovery.surface.get", {}, timeout=args.timeout)
        require(recovery_surface_rpc["deployment_status"] == recovery_surface["deployment_status"], "recovery surface rpc deployment mismatch")
        require(recovery_surface_rpc.get("current_slot") == "b", "recovery surface rpc current slot mismatch")
        require(recovery_surface_rpc.get("last_good_slot") == "b", "recovery surface rpc last good slot mismatch")
        require("rollback" in recovery_surface_rpc["available_actions"], "recovery surface rpc should advertise rollback")

        bundle = rpc_call(
            socket_path,
            "recovery.bundle.export",
            {"reason": "smoke-export"},
            timeout=args.timeout,
        )
        require(Path(bundle["bundle_path"]).exists(), "diagnostic bundle was not written")

        rollback = rpc_call(
            socket_path,
            "update.rollback",
            {
                "recovery_id": apply_result["recovery_ref"],
                "reason": "smoke-rollback",
                "dry_run": False,
            },
            timeout=args.timeout,
        )
        require(rollback["status"] == "accepted", "unexpected update.rollback status")
        require(bool(rollback.get("rollback_target")), "rollback target missing")
        require(
            rollback_context_path.read_text() == f"rollback|{apply_result['recovery_ref']}|smoke-rollback",
            "rollback command context mismatch",
        )
        require(bootctl_context_path.read_text() == "set-oneshot|aios-a.conf", "bootctl rollback context mismatch")
        require(next_entry_path.read_text().strip() == "aios-a.conf", "boot next-entry mismatch after rollback")
        rollback_boot_state = read_json(boot_state_path)
        require(rollback_boot_state["current_slot"] == "b", "rollback should still report pre-reboot slot")
        require(rollback_boot_state.get("staged_slot") == "a", "rollback should stage slot a before reboot")

        cmdline_path.write_text("quiet splash aios.slot=a\n")
        current_entry_path.write_text("aios-a.conf\n")
        boot_success_marker_path.write_text("success\n")
        post_rollback_health = rpc_call(socket_path, "update.health.get", {}, timeout=args.timeout)
        require(post_rollback_health["overall_status"] in {"ready", "idle", "degraded"}, "unexpected rollback health status")
        final_boot_state = read_json(boot_state_path)
        require(final_boot_state["current_slot"] == "a", "rollback boot state current slot mismatch")
        require(final_boot_state["last_good_slot"] == "a", "rollback did not restore slot a as last good")
        require(final_boot_state.get("staged_slot") is None, "rollback should clear staged slot after verification")
        final_deployment_state = read_json(Path(env["AIOS_UPDATED_DEPLOYMENT_STATE"]))
        require(final_deployment_state["status"] == "up-to-date", "deployment status should converge after rollback verify")
        require(final_deployment_state["current_version"] == "1.2.3", "deployment version should restore after rollback verify")
        require(final_deployment_state.get("pending_action") is None, "pending action should clear after rollback verify")
        require(final_deployment_state.get("active_recovery_id") is None, "active recovery id should clear after rollback verify")
        require(observability_log_path.exists(), "updated observability log missing")
        observability_entries = [
            json.loads(line)
            for line in observability_log_path.read_text().splitlines()
            if line.strip()
        ]
        kinds = {entry.get("kind") for entry in observability_entries}
        require("update.check.completed" in kinds, "observability log missing update.check event")
        require("update.apply.completed" in kinds, "observability log missing update.apply event")
        require("update.health.reported" in kinds, "observability log missing update.health event")
        require("recovery.surface.reported" in kinds, "observability log missing recovery surface event")
        require("recovery.bundle.exported" in kinds, "observability log missing recovery bundle event")
        require("update.rollback.completed" in kinds, "observability log missing update.rollback event")
        require(
            any(entry.get("update_id") == apply_result["recovery_ref"] for entry in observability_entries),
            "observability log missing recovery-linked update_id",
        )

        print("updated smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"updated smoke failed: {error}")
        return 1
    finally:
        terminate(process)
        if process.stdout:
            output = process.stdout.read()
            if output.strip():
                print("\n--- updated log ---")
                print(output.rstrip())
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
