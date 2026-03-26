#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from host_exec import bash_command, bash_path, parse_embedded_json, prepend_binary_parent_to_path, resolve_qemu_binary

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECOVERY_IMAGE = ROOT / "aios" / "image" / "recovery.output" / "aios-qemu-x86_64-recovery.raw"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SUCCESS_PATTERNS = {
    'kernel': re.compile(r'Linux version .*x86_64'),
    'systemd': re.compile(r'systemd\[1\]: systemd .* running in system mode'),
    'recovery_mode': re.compile(r'AIOS recovery mode'),
    'recovery_surface': re.compile(r'recovery_surface: .*'),
}
FAIL_PATTERNS = [
    re.compile(r'Failed to start aios-recovery-shell\.service', re.IGNORECASE),
    re.compile(r'Exec format error', re.IGNORECASE),
    re.compile(r'Failed at step EXEC', re.IGNORECASE),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Boot the AIOS recovery image in QEMU and wait for recovery-mode evidence'
    )
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument(
        '--log-path',
        type=Path,
        default=ROOT / 'out' / 'boot-qemu-recovery.log',
        help='Path to write the captured serial log',
    )
    return parser.parse_args()


def skip(reason: str, **extra: object) -> int:
    payload = {"status": "skipped", "reason": reason, **extra}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def bash_env() -> dict[str, str]:
    env = os.environ.copy()
    env["AIOS_PYTHON_BIN"] = sys.executable
    prepend_binary_parent_to_path(env, resolve_qemu_binary())
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


def ensure_recovery_image() -> tuple[Path | None, str | None]:
    if DEFAULT_RECOVERY_IMAGE.exists():
        return DEFAULT_RECOVERY_IMAGE.resolve(), None

    preflight = run_preflight(ROOT / "scripts" / "build-aios-recovery-image.sh", env=bash_env())
    if preflight.get("status") != "ready":
        return None, "recovery image build prerequisites unavailable on this host"

    completed = subprocess.run(
        bash_command(ROOT / "scripts" / "build-aios-recovery-image.sh"),
        cwd=ROOT,
        env=bash_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return None, "recovery image build failed"
    if not DEFAULT_RECOVERY_IMAGE.exists():
        return None, f"recovery image build did not produce expected artifact: {DEFAULT_RECOVERY_IMAGE}"
    return DEFAULT_RECOVERY_IMAGE.resolve(), None


def choose_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def sanitize(line: str) -> str:
    return ANSI_ESCAPE.sub('', line).replace('\r', '').rstrip('\n')


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


def main() -> int:
    args = parse_args()
    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_path, skip_reason = ensure_recovery_image()
    except RuntimeError as exc:
        return skip(str(exc))
    if image_path is None:
        return skip(skip_reason or "recovery image unavailable")

    env = bash_env()
    env.setdefault('AIOS_QEMU_MEMORY_MB', '2048')
    env.setdefault('AIOS_QEMU_SMP', '2')
    env.setdefault('AIOS_QEMU_DISPLAY', 'none')
    env.setdefault('AIOS_QEMU_MONITOR', 'none')
    env.setdefault('AIOS_QEMU_SERIAL', 'stdio')
    env.setdefault('AIOS_QEMU_SSH_PORT', str(choose_free_port()))
    env['AIOS_QEMU_IMAGE_PATH'] = bash_path(image_path)
    env.setdefault('AIOS_QEMU_KERNEL_CMDLINE_EXTRA', 'systemd.unit=aios-recovery.target')
    try:
        qemu_preflight = run_preflight(ROOT / "scripts" / "boot-qemu.sh", env=env)
    except RuntimeError as exc:
        return skip(str(exc), image_path=str(image_path))
    if qemu_preflight.get("status") != "ready":
        return skip(
            "qemu recovery bringup prerequisites unavailable on this host",
            image_path=str(image_path),
            qemu_preflight=qemu_preflight,
        )

    proc = subprocess.Popen(
        bash_command(ROOT / 'scripts' / 'boot-qemu.sh'),
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors='replace',
        bufsize=1,
    )

    deadline = time.monotonic() + args.timeout
    lines: list[str] = []
    matched: dict[str, str] = {}
    failure_line: str | None = None

    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline() if proc.stdout is not None else ''
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue

            clean = sanitize(line)
            if not clean:
                continue
            lines.append(clean)
            args.log_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

            if failure_line is None:
                for pattern in FAIL_PATTERNS:
                    if pattern.search(clean):
                        failure_line = clean
                        break

            for key, pattern in SUCCESS_PATTERNS.items():
                if key not in matched and pattern.search(clean):
                    matched[key] = clean

            if failure_line is None and len(matched) == len(SUCCESS_PATTERNS):
                break
    finally:
        terminate(proc)

    success = failure_line is None and len(matched) == len(SUCCESS_PATTERNS)
    result = {
        'timeout_seconds': args.timeout,
        'log_path': str(args.log_path),
        'image_path': str(image_path),
        'required_patterns': sorted(SUCCESS_PATTERNS.keys()),
        'matched': matched,
        'failure_line': failure_line,
        'line_count': len(lines),
        'tail': lines[-20:],
        'qemu_preflight': qemu_preflight,
    }
    print(json.dumps(result, indent=2))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
