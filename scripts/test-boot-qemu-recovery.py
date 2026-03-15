#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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

    env = os.environ.copy()
    env.setdefault('AIOS_QEMU_MEMORY_MB', '2048')
    env.setdefault('AIOS_QEMU_SMP', '2')
    env.setdefault('AIOS_QEMU_DISPLAY', 'none')
    env.setdefault('AIOS_QEMU_MONITOR', 'none')
    env.setdefault('AIOS_QEMU_SERIAL', 'stdio')
    env.setdefault('AIOS_QEMU_SSH_PORT', str(choose_free_port()))
    env.setdefault('AIOS_IMAGE_OUTPUT_DIR', str(ROOT / 'aios' / 'image' / 'recovery.output'))
    env.setdefault('AIOS_QEMU_KERNEL_CMDLINE_EXTRA', 'systemd.unit=aios-recovery.target')

    proc = subprocess.Popen(
        ['bash', str(ROOT / 'scripts' / 'boot-qemu.sh')],
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
            args.log_path.write_text('\n'.join(lines) + '\n')

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
        'required_patterns': sorted(SUCCESS_PATTERNS.keys()),
        'matched': matched,
        'failure_line': failure_line,
        'line_count': len(lines),
        'tail': lines[-20:],
    }
    print(json.dumps(result, indent=2))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
