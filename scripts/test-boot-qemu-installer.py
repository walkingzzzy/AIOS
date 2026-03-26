#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from host_exec import bash_command, bash_path, parse_embedded_json, resolve_qemu_binary

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SYSTEM_IMAGE = ROOT / "aios" / "image" / "mkosi.output" / "aios-qemu-x86_64.raw"
DEFAULT_RECOVERY_IMAGE = ROOT / "aios" / "image" / "recovery.output" / "aios-qemu-x86_64-recovery.raw"
DEFAULT_INSTALLER_IMAGE = ROOT / "aios" / "image" / "installer.output" / "aios-qemu-x86_64-installer.raw"
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
    parser.add_argument("--system-image", type=Path, default=DEFAULT_SYSTEM_IMAGE)
    parser.add_argument("--recovery-image", type=Path, default=DEFAULT_RECOVERY_IMAGE)
    parser.add_argument("--target-image", type=Path, default=ROOT / "out" / "qemu-installer-target.raw")
    parser.add_argument("--target-size-bytes", type=int, help="Optional explicit size for the target disk image")
    parser.add_argument("--log-path", type=Path, default=ROOT / "out" / "boot-qemu-installer.log")
    parser.add_argument("--boot-installed-target", action="store_true")
    parser.add_argument("--cross-reboot", action="store_true")
    parser.add_argument("--installed-log-path", type=Path, default=ROOT / "out" / "boot-qemu-installed-cross-reboot.log")
    return parser.parse_args()


def sanitize(line: str) -> str:
    return ANSI_ESCAPE.sub("", line).replace("\r", "").rstrip("\n")


def skip(reason: str, **extra: object) -> int:
    payload = {"status": "skipped", "reason": reason, **extra}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def bash_env() -> dict[str, str]:
    env = os.environ.copy()
    env["AIOS_PYTHON_BIN"] = sys.executable
    return env


def run_preflight(script: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    completed = subprocess.run(
        bash_command(script, "--preflight"),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"preflight failed: {script}")
    payload = parse_embedded_json(completed.stdout)
    if payload is None:
        raise RuntimeError(f"failed to parse preflight json from {script}")
    return payload


def run_build_script(script: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(
        bash_command(script),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise RuntimeError(f"build failed: {script.name}")


def build_env_for_system_image(image_path: Path) -> dict[str, str]:
    env = bash_env()
    env["AIOS_IMAGE_OUTPUT_DIR_OVERRIDE"] = bash_path(image_path.parent)
    return env


def build_env_for_recovery_image(image_path: Path) -> dict[str, str]:
    env = bash_env()
    env["AIOS_RECOVERY_IMAGE_OUTPUT_DIR"] = bash_path(image_path.parent)
    return env


def build_env_for_installer_image(output_dir: Path) -> dict[str, str]:
    env = bash_env()
    env["AIOS_INSTALLER_IMAGE_OUTPUT_DIR"] = bash_path(output_dir)
    return env


def ensure_system_image(image_path: Path) -> tuple[Path | None, str | None, dict[str, object] | None]:
    resolved = image_path.resolve()
    if resolved.exists():
        return resolved, None, None
    preflight = run_preflight(ROOT / "scripts" / "build-aios-image.sh", env=build_env_for_system_image(resolved))
    if preflight.get("status") != "ready":
        return None, "system image build prerequisites unavailable on this host", preflight
    run_build_script(ROOT / "scripts" / "build-aios-image.sh", build_env_for_system_image(resolved))
    if not resolved.exists():
        raise RuntimeError(f"system image build did not produce expected artifact: {resolved}")
    return resolved, None, preflight


def ensure_recovery_image(image_path: Path) -> tuple[Path | None, str | None, dict[str, object] | None]:
    resolved = image_path.resolve()
    if resolved.exists():
        return resolved, None, None
    preflight = run_preflight(ROOT / "scripts" / "build-aios-recovery-image.sh", env=build_env_for_recovery_image(resolved))
    if preflight.get("status") != "ready":
        return None, "recovery image build prerequisites unavailable on this host", preflight
    run_build_script(ROOT / "scripts" / "build-aios-recovery-image.sh", build_env_for_recovery_image(resolved))
    if not resolved.exists():
        raise RuntimeError(f"recovery image build did not produce expected artifact: {resolved}")
    return resolved, None, preflight


def ensure_installer_image(image_path: Path, output_dir: Path) -> tuple[Path | None, str | None, dict[str, object] | None]:
    resolved = image_path.resolve()
    if resolved.exists():
        return resolved, None, None
    preflight = run_preflight(
        ROOT / "scripts" / "build-aios-installer-image.sh",
        env=build_env_for_installer_image(output_dir.resolve()),
    )
    if preflight.get("status") != "ready":
        return None, "installer image build prerequisites unavailable on this host", preflight
    run_build_script(
        ROOT / "scripts" / "build-aios-installer-image.sh",
        build_env_for_installer_image(output_dir.resolve()),
    )
    if not resolved.exists():
        raise RuntimeError(f"installer image build did not produce expected artifact: {resolved}")
    return resolved, None, preflight


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


def find_ovmf_code(qemu_bin: Path | None) -> str | None:
    override = os.environ.get("AIOS_QEMU_OVMF_CODE")
    if override:
        candidate = Path(override)
        if candidate.exists():
            return str(candidate)

    if qemu_bin is not None:
        relative_candidates = [
            qemu_bin.parent / "share" / "edk2-x86_64-code.fd",
            qemu_bin.parent / "share" / "OVMF.fd",
            qemu_bin.parent.parent / "share" / "qemu" / "edk2-x86_64-code.fd",
            qemu_bin.parent.parent / "share" / "qemu" / "OVMF.fd",
        ]
        for candidate in relative_candidates:
            if candidate.exists():
                return str(candidate)

    search_roots = [Path("/")]
    if os.name == "nt":
        for env_name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
            program_root = os.environ.get(env_name)
            if program_root:
                search_roots.append(Path(program_root))

    patterns = (
        "opt/homebrew/Cellar/qemu/*/share/qemu/edk2-x86_64-code.fd",
        "usr/local/Cellar/qemu/*/share/qemu/edk2-x86_64-code.fd",
        "usr/share/OVMF/OVMF_CODE.fd",
        "usr/share/OVMF/OVMF_CODE_4M.fd",
        "usr/share/edk2/ovmf/OVMF_CODE.fd",
        "usr/share/edk2/ovmf/OVMF_CODE_4M.fd",
        "usr/share/qemu/OVMF.fd",
        "qemu/share/edk2-x86_64-code.fd",
        "QEMU/share/edk2-x86_64-code.fd",
        "qemu/share/OVMF.fd",
        "QEMU/share/OVMF.fd",
    )
    for root in search_roots:
        for pattern in patterns:
            matches = sorted(root.glob(pattern))
            if matches:
                return str(matches[0])
    return None


def choose_accel() -> tuple[str, str]:
    sysname = platform.system()
    machine = platform.machine().lower()
    default_accel = "tcg"
    default_cpu = "max"
    if sysname == "Darwin" and machine == "arm64":
        default_accel, default_cpu = "tcg", "max"
    elif sysname == "Darwin":
        default_accel, default_cpu = "hvf:tcg", "host"
    elif sysname == "Linux":
        default_accel, default_cpu = "kvm:tcg", "host"
    return (
        os.environ.get("AIOS_QEMU_ACCEL", default_accel),
        os.environ.get("AIOS_QEMU_CPU", default_cpu),
    )


def create_target_image(path: Path, size_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with path.open("wb") as handle:
        handle.truncate(size_bytes)


def main() -> int:
    args = parse_args()
    installer_image_path = (args.installer_output_dir / DEFAULT_INSTALLER_IMAGE.name).resolve()
    system_preflight: dict[str, object] | None = None
    recovery_preflight: dict[str, object] | None = None
    installer_preflight: dict[str, object] | None = None

    try:
        system_image, skip_reason, system_preflight = ensure_system_image(args.system_image)
        if system_image is None:
            return skip(skip_reason or "system image unavailable", build_preflight=system_preflight)

        recovery_image, recovery_skip_reason, recovery_preflight = ensure_recovery_image(args.recovery_image)
        if recovery_image is None:
            return skip(
                recovery_skip_reason or "recovery image unavailable",
                system_image=str(system_image),
                build_preflight=recovery_preflight,
            )

        installer_image, installer_skip_reason, installer_preflight = ensure_installer_image(
            installer_image_path,
            args.installer_output_dir,
        )
        if installer_image is None:
            return skip(
                installer_skip_reason or "installer image unavailable",
                system_image=str(system_image),
                recovery_image=str(recovery_image) if recovery_image else None,
                build_preflight=installer_preflight,
            )
    except RuntimeError as exc:
        raise SystemExit(str(exc))

    source_size = system_image.stat().st_size
    target_size = args.target_size_bytes or source_size
    create_target_image(args.target_image, target_size)

    accel, cpu = choose_accel()
    qemu_bin = resolve_qemu_binary()
    if qemu_bin is None:
        return skip(
            "qemu-system-x86_64 is not installed on this host",
            installer_image=str(installer_image),
            system_image=str(system_image),
            recovery_image=str(recovery_image),
        )

    ovmf_code = find_ovmf_code(qemu_bin)
    if ovmf_code is None:
        return skip(
            "OVMF firmware image unavailable for installer media boot",
            qemu_binary=str(qemu_bin),
            installer_image=str(installer_image),
        )

    qemu_args = [
        str(qemu_bin),
        "-machine",
        f"q35,accel={accel}",
        "-cpu",
        cpu,
        "-m",
        "2048",
        "-smp",
        "2",
        "-display",
        "none",
        "-monitor",
        "none",
        "-serial",
        "stdio",
        "-drive",
        f"if=virtio,format=raw,file={installer_image}",
        "-drive",
        f"if=virtio,format=raw,readonly=on,file={system_image}",
        "-drive",
        f"if=virtio,format=raw,file={args.target_image.resolve()}",
        "-drive",
        f"if=virtio,format=raw,readonly=on,file={recovery_image}",
        "-drive",
        f"if=pflash,format=raw,readonly=on,file={ovmf_code}",
        "-nic",
        "user,model=virtio-net-pci",
    ]
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
            args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
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
        args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    summary: dict[str, object] = {
        "timeout_seconds": args.timeout,
        "installer_image": str(installer_image),
        "source_image": str(system_image),
        "target_image": str(args.target_image.resolve()),
        "recovery_image": str(recovery_image),
        "log_path": str(args.log_path),
        "matched": matched,
        "failure_line": failure_line,
        "line_count": len(lines),
        "tail": lines[-20:],
        "qemu_binary": str(qemu_bin),
        "ovmf_code": str(ovmf_code),
        "system_image_preflight": system_preflight,
        "recovery_image_preflight": recovery_preflight,
        "installer_image_preflight": installer_preflight,
    }

    success = failure_line is None and len(matched) == len(SUCCESS_PATTERNS)
    if success and args.boot_installed_target:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "test-qemu-cross-reboot.py"),
            "--image-path",
            str(args.target_image.resolve()),
            "--timeout",
            str(max(args.timeout, 240)),
            "--log-path",
            str(args.installed_log_path),
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
