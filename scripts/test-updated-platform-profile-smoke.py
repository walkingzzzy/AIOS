#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from aios_cargo_bins import cargo_target_bin_dir, default_aios_bin_dir, detect_host_target

ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS updated platform-profile smoke harness")
    parser.add_argument("--bin-dir", type=Path)
    parser.add_argument("--updated", type=Path)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args()


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(ROOT) / name


def ensure_binary(path: Path) -> None:
    command = ["cargo", "build"]
    host_target = detect_host_target(ROOT / "aios")
    if host_target and path.parent == cargo_target_bin_dir(ROOT, host_target):
        command.extend(["--target", host_target])
    command.extend(["-p", "aios-updated"])
    subprocess.run(command, cwd=ROOT / "aios", check=True)
    if not path.exists():
        raise SystemExit(f"missing binary after build: {path}")


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
        raise RuntimeError(response["error"])
    return response["result"]


def wait_for_socket(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for socket {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
        except Exception:
            time.sleep(0.1)
    raise TimeoutError("timed out waiting for health")


def terminate(process: subprocess.Popen[str]) -> None:
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


def main() -> int:
    args = parse_args()
    updated = resolve_binary("updated", args.updated, args.bin_dir)
    ensure_binary(updated)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-upd-", dir="/tmp"))
    runtime_root = temp_root / "r"
    state_root = temp_root / "s"
    boot_dir = state_root / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)
    (boot_dir / "current-slot").write_text("a\n")
    (boot_dir / "current-entry").write_text("aios-a.conf\n")
    cmdline_path = state_root / "cmdline"
    cmdline_path.write_text("quiet splash aios.slot=a\n")
    boot_success_marker = state_root / "boot-success"
    boot_success_marker.write_text("success\n")
    recovery_surface_path = state_root / "recovery-surface.json"
    boot_state_path = state_root / "boot-control.json"

    bootctl_context = state_root / "bootctl-context.txt"
    sysupdate_context = state_root / "sysupdate-context.txt"
    fake_bootctl = state_root / "fake-bootctl.sh"
    fake_sysupdate = state_root / "fake-systemd-sysupdate.sh"
    profile_sysupdate_dir = ROOT / "aios" / "services" / "updated" / "platforms" / "generic-x86_64-uefi" / "share" / "sysupdate.d"
    health_probe = ROOT / "aios" / "services" / "updated" / "platforms" / "generic-x86_64-uefi" / "libexec" / "health-probe.sh"
    fake_bootctl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "context=\"$AIOS_UPDATED_TEST_BOOTCTL_CONTEXT\"\n"
        "case \"${1:-}\" in\n"
        "  status)\n"
        "    printf 'Current Boot Loader Entry: aios-a.conf\\n'\n"
        "    ;;\n"
        "  set-oneshot)\n"
        "    printf '%s|%s' \"$1\" \"$2\" > \"$context\"\n"
        "    ;;\n"
        "  *)\n"
        "    printf 'unsupported bootctl verb: %s\\n' \"${1:-}\" >&2\n"
        "    exit 1\n"
        "    ;;\n"
        "esac\n"
    )
    fake_bootctl.chmod(0o755)
    fake_sysupdate.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$AIOS_UPDATED_TEST_SYSUPDATE_CONTEXT\"\n"
        "last=''\n"
        "for arg in \"$@\"; do\n"
        "  last=\"$arg\"\n"
        "done\n"
        "case \"$last\" in\n"
        "  check-new) printf 'version 0.2.0\\n' ;;\n"
        "  list) printf 'aios-root 0.2.0\\n' ;;\n"
        "  update) printf 'updated 0.2.0\\n' ;;\n"
        "  *) printf 'unsupported %s\\n' \"$last\" >&2; exit 9 ;;\n"
        "esac\n"
    )
    fake_sysupdate.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_UPDATED_RUNTIME_DIR": str(runtime_root),
            "AIOS_UPDATED_STATE_DIR": str(state_root),
            "AIOS_UPDATED_SOCKET_PATH": str(runtime_root / "u.sock"),
            "AIOS_UPDATED_DEPLOYMENT_STATE": str(state_root / "deployment-state.json"),
            "AIOS_UPDATED_DIAGNOSTICS_DIR": str(state_root / "diagnostics"),
            "AIOS_UPDATED_RECOVERY_DIR": str(state_root / "recovery"),
            "AIOS_UPDATED_RECOVERY_SURFACE_PATH": str(recovery_surface_path),
            "AIOS_UPDATED_BOOT_STATE_PATH": str(boot_state_path),
            "AIOS_UPDATED_BOOT_ENTRY_STATE_DIR": str(boot_dir),
            "AIOS_UPDATED_BOOT_CMDLINE_PATH": str(cmdline_path),
            "AIOS_UPDATED_BOOT_SUCCESS_MARKER_PATH": str(boot_success_marker),
            "AIOS_UPDATED_SYSUPDATE_DIR": str(profile_sysupdate_dir),
            "AIOS_UPDATED_PLATFORM_PROFILE": str(ROOT / "aios" / "services" / "updated" / "platforms" / "generic-x86_64-uefi" / "share" / "profile.yaml"),
            "AIOS_UPDATED_HEALTH_PROBE_COMMAND": str(health_probe),
            "AIOS_UPDATED_SYSUPDATE_BIN": str(ROOT / "aios" / "services" / "updated" / "platforms" / "generic-x86_64-uefi" / "libexec" / "systemd-sysupdate-bridge.sh"),
            "AIOS_UPDATED_SYSUPDATE_DEFINITIONS_DIR": str(profile_sysupdate_dir),
            "AIOS_PLATFORM_SYSUPDATE_BIN": str(fake_sysupdate),
            "AIOS_UPDATED_FIRMWARECTL_BIN": str(ROOT / "aios" / "services" / "updated" / "platforms" / "generic-x86_64-uefi" / "libexec" / "firmwarectl-bridge.sh"),
            "AIOS_PLATFORM_BOOTCTL_BIN": str(fake_bootctl),
            "AIOS_UPDATED_TEST_BOOTCTL_CONTEXT": str(bootctl_context),
            "AIOS_UPDATED_TEST_SYSUPDATE_CONTEXT": str(sysupdate_context),
        }
    )

    process = subprocess.Popen([str(updated)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        socket_path = Path(env["AIOS_UPDATED_SOCKET_PATH"])
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        notes = health.get("notes", [])
        require(any("platform_profile_id=generic-x86_64-uefi" in note for note in notes), "missing platform profile id in health notes")
        require(any("boot_backend=firmware" in note for note in notes), "expected firmware backend from profile")
        require(any("probe_overall_status=healthy" in note for note in notes), "missing probe status in health notes")
        require(any("probe_summary=platform delivery backend ready" in note for note in notes), "missing probe summary in health notes")

        check = rpc_call(socket_path, "update.check", {"channel": "stable", "current_version": "0.1.0"}, timeout=args.timeout)
        require(check["status"] in {"ready-to-stage", "waiting-for-artifacts"}, "unexpected update.check status")
        apply_result = rpc_call(socket_path, "update.apply", {"target_version": "0.2.0", "reason": "platform-smoke", "dry_run": False}, timeout=args.timeout)
        require(apply_result["status"] == "accepted", "update.apply was not accepted")
        health_report = rpc_call(socket_path, "update.health.get", {}, timeout=args.timeout)
        require(health_report["overall_status"] == "degraded", "expected staged update health to degrade until reboot verification")
        require(any("probe_summary=update staged and awaiting reboot verification" in note for note in health_report["notes"]), "staged update probe summary missing from update health")
        require(bootctl_context.read_text() == "set-oneshot|aios-b.conf", "firmware bridge did not drive bootctl set-oneshot")
        sysupdate_log = sysupdate_context.read_text().splitlines()
        require(any("slot-b" in line and line.endswith("update") for line in sysupdate_log), "sysupdate bridge did not select slot-b definitions for update")
        boot_state = json.loads(boot_state_path.read_text())
        require(boot_state.get("staged_slot") == "b", "boot state did not stage slot b")
        print(json.dumps({"health": health, "check": check, "apply": apply_result, "update_health": health_report, "sysupdate_log": sysupdate_log}, indent=2, ensure_ascii=False))
        return 0
    finally:
        terminate(process)


if __name__ == "__main__":
    raise SystemExit(main())
