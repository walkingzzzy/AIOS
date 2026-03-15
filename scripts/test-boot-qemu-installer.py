#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SUCCESS_PATTERNS = {
    "kernel": re.compile(r"Linux version .*x86_64"),
    "systemd": re.compile(r"systemd\[1\]: systemd .* running in system mode"),
    "installer": re.compile(r"AIOS_INSTALLER_REPORT status=success "),
}
FAIL_PATTERNS = [
    re.compile(r"AIOS_INSTALLER_REPORT status=failed "),
    re.compile(r"Exec format error", re.IGNORECASE),
    re.compile(r"Failed at step EXEC", re.IGNORECASE),
    re.compile(r"unable to execute", re.IGNORECASE),
    re.compile(r"Failed to start .*aios-installer\.service", re.IGNORECASE),
]
INSTALLER_CMDLINE_EXTRA = "systemd.unit=aios-installer.target root=/dev/vda2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Boot the AIOS installer image, provision a target disk, and optionally boot the installed target")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--installer-output-dir", type=Path, default=ROOT / "aios" / "image" / "installer.output")
    parser.add_argument("--system-image", type=Path, default=ROOT / "aios" / "image" / "mkosi.output" / "aios-qemu-x86_64.raw")
    parser.add_argument("--recovery-image", type=Path, default=ROOT / "aios" / "image" / "recovery.output" / "aios-qemu-x86_64-recovery.raw")
    parser.add_argument("--target-image", type=Path, default=ROOT / "out" / "qemu-installer-target.raw")
    parser.add_argument("--target-size-bytes", type=int, help="Optional explicit size for the target disk image")
    parser.add_argument("--log-path", type=Path, default=ROOT / "out" / "boot-qemu-installer.log")
    parser.add_argument("--boot-installed-target", action="store_true")
    parser.add_argument("--cross-reboot", action="store_true")
    parser.add_argument("--installed-log-path", type=Path, default=ROOT / "out" / "boot-qemu-installed-cross-reboot.log")
    return parser.parse_args()


def sanitize(line: str) -> str:
    return ANSI_ESCAPE.sub("", line).replace("\r", "").rstrip("\n")


def terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def find_ovmf_code() -> str | None:
    override = os.environ.get("AIOS_QEMU_OVMF_CODE")
    if override:
        candidate = Path(override)
        if candidate.exists():
            return str(candidate)

    for pattern in (
        "/opt/homebrew/Cellar/qemu/*/share/qemu/edk2-x86_64-code.fd",
        "/usr/local/Cellar/qemu/*/share/qemu/edk2-x86_64-code.fd",
        "/usr/share/OVMF/OVMF_CODE.fd",
        "/usr/share/OVMF/OVMF_CODE_4M.fd",
        "/usr/share/edk2/ovmf/OVMF_CODE.fd",
        "/usr/share/edk2/ovmf/OVMF_CODE_4M.fd",
        "/usr/share/qemu/OVMF.fd",
    ):
        matches = sorted(Path("/").glob(pattern.lstrip("/")))
        if matches:
            return str(matches[0])
    return None


def choose_accel() -> tuple[str, str]:
    sysname = os.uname().sysname
    machine = os.uname().machine
    if sysname == "Darwin" and machine == "arm64":
        return "tcg", "max"
    if sysname == "Darwin":
        return "hvf:tcg", "host"
    if sysname == "Linux":
        return "kvm:tcg", "host"
    return "tcg", "max"


def ensure_file(path: Path, description: str) -> None:
    if not path.exists():
        raise SystemExit(f"missing {description}: {path}")


def create_target_image(path: Path, size_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with path.open("wb") as handle:
        handle.truncate(size_bytes)


def main() -> int:
    args = parse_args()
    installer_image = args.installer_output_dir / "aios-qemu-x86_64-installer.raw"
    ensure_file(installer_image, "installer image")
    ensure_file(args.system_image, "source system image")
    recovery_image = args.recovery_image if args.recovery_image.exists() else None

    source_size = args.system_image.stat().st_size
    target_size = args.target_size_bytes or source_size
    create_target_image(args.target_image, target_size)

    accel, cpu = choose_accel()
    qemu_bin = shutil.which("qemu-system-x86_64")
    if qemu_bin is None:
        raise SystemExit("qemu-system-x86_64 is not installed")

    ovmf_code = find_ovmf_code()
    qemu_args = [
        qemu_bin,
        "-machine", f"q35,accel={accel}",
        "-cpu", cpu,
        "-m", "2048",
        "-smp", "2",
        "-display", "none",
        "-monitor", "none",
        "-serial", "stdio",
        "-drive", f"if=virtio,format=raw,file={installer_image}",
        "-drive", f"if=virtio,format=raw,readonly=on,file={args.system_image}",
        "-drive", f"if=virtio,format=raw,file={args.target_image}",
        "-nic", "user,model=virtio-net-pci",
    ]
    if recovery_image is not None:
        qemu_args.extend(["-drive", f"if=virtio,format=raw,readonly=on,file={recovery_image}"])
    if ovmf_code is not None:
        qemu_args.extend(["-drive", f"if=pflash,format=raw,readonly=on,file={ovmf_code}"])
    escaped_extra = INSTALLER_CMDLINE_EXTRA.replace(",", ",,")
    qemu_args.extend(
        [
            "-smbios",
            f"type=11,value=io.systemd.stub.kernel-cmdline-extra={escaped_extra}",
            "-smbios",
            f"type=11,value=io.systemd.boot.kernel-cmdline-extra={escaped_extra}",
        ]
    )

    proc = subprocess.Popen(
        qemu_args,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )

    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.timeout
    lines: list[str] = []
    matched: dict[str, str] = {}
    failure_line: str | None = None

    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline() if proc.stdout is not None else ""
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            clean = sanitize(line)
            if not clean:
                continue
            lines.append(clean)
            args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""))
            if failure_line is None:
                for pattern in FAIL_PATTERNS:
                    if pattern.search(clean):
                        failure_line = clean
                        break
            for key, pattern in SUCCESS_PATTERNS.items():
                if key not in matched and pattern.search(clean):
                    matched[key] = clean
            if failure_line is not None or len(matched) == len(SUCCESS_PATTERNS):
                break
    finally:
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            terminate(proc)
        if proc.stdout is not None:
            for tail in proc.stdout:
                clean = sanitize(tail)
                if clean:
                    lines.append(clean)
        args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    summary: dict[str, object] = {
        "timeout_seconds": args.timeout,
        "installer_image": str(installer_image),
        "source_image": str(args.system_image),
        "target_image": str(args.target_image),
        "recovery_image": str(recovery_image) if recovery_image else None,
        "log_path": str(args.log_path),
        "matched": matched,
        "failure_line": failure_line,
        "line_count": len(lines),
        "tail": lines[-20:],
    }

    success = failure_line is None and len(matched) == len(SUCCESS_PATTERNS)
    if success and args.boot_installed_target:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "test-qemu-cross-reboot.py"),
            "--image-path", str(args.target_image.resolve()),
            "--timeout", str(max(args.timeout, 240)),
            "--log-path", str(args.installed_log_path),
        ]
        if args.cross_reboot:
            command.append("--expect-firstboot-once")
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        summary["installed_target_cross_reboot"] = {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "log_path": str(args.installed_log_path),
        }
        success = success and completed.returncode == 0

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
