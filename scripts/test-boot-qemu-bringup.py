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
DEFAULT_IMAGE_PATH = ROOT / "aios" / "image" / "mkosi.output" / "aios-qemu-x86_64.raw"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
BASE_SUCCESS_PATTERNS = {
    "kernel": re.compile(r"Linux version .*x86_64"),
    "systemd": re.compile(r"systemd\[1\]: systemd .* running in system mode"),
    "aios_service": re.compile(r"Started .*aios-[a-z0-9-]+\.service"),
}
FIRSTBOOT_OBSERVED_PATTERN = re.compile(
    r"AIOS_FIRSTBOOT_REPORT .*machine_id_state=[a-z-]+ .*machine_id_generated=(true|false) .*random_seed_present=(true|false)"
)
FIRSTBOOT_BOOT_EVIDENCE_PATTERNS = {
    "firstboot": FIRSTBOOT_OBSERVED_PATTERN,
}
FAIL_PATTERNS = [
    re.compile(r"Exec format error", re.IGNORECASE),
    re.compile(r"Failed at step EXEC", re.IGNORECASE),
    re.compile(r"unable to execute", re.IGNORECASE),
    re.compile(r"Failed to start .*aios-[a-z0-9-]+\.service", re.IGNORECASE),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Boot the AIOS QEMU image and wait for userspace evidence"
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--expect-firstboot",
        action="store_true",
        help="Require the first-boot report in the serial log",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=ROOT / "out" / "boot-qemu-bringup.log",
        help="Path to write the captured serial log",
    )
    parser.add_argument(
        "--image-path",
        type=Path,
        help="Optional explicit disk image path to boot instead of scanning AIOS_IMAGE_OUTPUT_DIR",
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


def run_preflight(script: Path, env: dict[str, str] | None = None) -> dict[str, object] | None:
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


def ensure_boot_image(explicit_image: Path | None) -> tuple[Path | None, str | None]:
    if explicit_image is not None:
        image_path = explicit_image.resolve()
        if image_path.exists():
            return image_path, None
        return None, f"explicit image path missing: {image_path}"

    if DEFAULT_IMAGE_PATH.exists():
        return DEFAULT_IMAGE_PATH.resolve(), None

    preflight = run_preflight(ROOT / "scripts" / "build-aios-image.sh", env=bash_env())
    if preflight is None:
        return None, "usable bash runtime unavailable on this platform"
    if preflight.get("status") != "ready":
        return None, "base image build prerequisites unavailable on this host"

    completed = subprocess.run(
        bash_command(ROOT / "scripts" / "build-aios-image.sh"),
        cwd=ROOT,
        env=bash_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return None, "base image build failed"
    if not DEFAULT_IMAGE_PATH.exists():
        return None, f"base image build did not produce expected artifact: {DEFAULT_IMAGE_PATH}"
    return DEFAULT_IMAGE_PATH.resolve(), None


def choose_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def required_patterns(expect_firstboot: bool) -> dict[str, re.Pattern[str]]:
    patterns = dict(BASE_SUCCESS_PATTERNS)
    if expect_firstboot:
        patterns.update(FIRSTBOOT_BOOT_EVIDENCE_PATTERNS)
    return patterns


def main() -> int:
    args = parse_args()
    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_path, skip_reason = ensure_boot_image(args.image_path)
    except RuntimeError as exc:
        return skip(str(exc))
    if image_path is None:
        return skip(skip_reason or "boot image unavailable")

    env = bash_env()
    env["AIOS_QEMU_IMAGE_PATH"] = bash_path(image_path)
    preflight_env = dict(env)
    try:
        qemu_preflight = run_preflight(ROOT / "scripts" / "boot-qemu.sh", env=preflight_env)
    except RuntimeError as exc:
        return skip(str(exc), image_path=str(image_path))
    if qemu_preflight is None or qemu_preflight.get("status") != "ready":
        return skip(
            "qemu bringup prerequisites unavailable on this host",
            image_path=str(image_path),
            qemu_preflight=qemu_preflight,
        )

    required = required_patterns(args.expect_firstboot)
    optional = {} if args.expect_firstboot else {"firstboot": FIRSTBOOT_OBSERVED_PATTERN}

    env.setdefault("AIOS_QEMU_MEMORY_MB", "2048")
    env.setdefault("AIOS_QEMU_SMP", "2")
    env.setdefault("AIOS_QEMU_DISPLAY", "none")
    env.setdefault("AIOS_QEMU_MONITOR", "none")
    ssh_port = str(choose_free_port())
    env.setdefault("AIOS_QEMU_SERIAL", "stdio")
    env.setdefault("AIOS_QEMU_SSH_PORT", ssh_port)

    proc = subprocess.Popen(
        bash_command(ROOT / "scripts" / "boot-qemu.sh"),
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )

    deadline = time.monotonic() + args.timeout
    lines: list[str] = []
    matched: dict[str, str] = {}
    optional_matches: dict[str, str] = {}
    failure_line: str | None = None

    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline() if proc.stdout is not None else ""
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
                continue

            cleaned = sanitize(line)
            if not cleaned:
                continue
            lines.append(cleaned)

            for key, pattern in required.items():
                if key not in matched and pattern.search(cleaned):
                    matched[key] = cleaned

            for key, pattern in optional.items():
                if key not in optional_matches and pattern.search(cleaned):
                    optional_matches[key] = cleaned

            if failure_line is None:
                for pattern in FAIL_PATTERNS:
                    if pattern.search(cleaned):
                        failure_line = cleaned
                        break

            if failure_line is not None:
                break

            if len(matched) == len(required):
                break
    finally:
        terminate(proc)
        if proc.stdout is not None:
            for tail in proc.stdout:
                cleaned = sanitize(tail)
                if cleaned:
                    lines.append(cleaned)

    args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    summary = {
        "timeout_seconds": args.timeout,
        "expect_firstboot": args.expect_firstboot,
        "log_path": str(args.log_path),
        "image_path": str(image_path),
        "ssh_port": ssh_port,
        "required_patterns": sorted(required),
        "matched": matched,
        "optional_matches": optional_matches,
        "failure_line": failure_line,
        "line_count": len(lines),
        "tail": lines[-20:],
        "qemu_preflight": qemu_preflight,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if failure_line is not None:
        return 1
    return 0 if len(matched) == len(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
