#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
KERNEL_PATTERN = re.compile(r"Linux version .*x86_64")
SYSTEMD_PATTERN = re.compile(r"systemd\[1\]: systemd .* running in system mode")
SERVICE_PATTERN = re.compile(r"Started .*aios-[a-z0-9-]+\.service")
FIRSTBOOT_PATTERN = re.compile(r"AIOS_FIRSTBOOT_REPORT ")
FIRSTBOOT_FINISHED_PATTERN = re.compile(r"Finished aios-firstboot\.service")
FAIL_PATTERNS = [
    re.compile(r"Exec format error", re.IGNORECASE),
    re.compile(r"Failed at step EXEC", re.IGNORECASE),
    re.compile(r"unable to execute", re.IGNORECASE),
]
FIRSTBOOT_RESET_DELAY_SECONDS = 8.0
SECOND_BOOT_SETTLE_SECONDS = 8.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Boot a QEMU image, trigger a real VM reset, and require the second boot")
    parser.add_argument("--image-path", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--log-path", type=Path, default=ROOT / "out" / "boot-qemu-cross-reboot.log")
    parser.add_argument("--expect-firstboot-once", action="store_true")
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


def wait_for_monitor(socket_path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for monitor socket: {socket_path}")


def send_monitor_command(socket_path: Path, command: str) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5.0)
        client.connect(str(socket_path))
        client.recv(4096)
        client.sendall(command.encode("utf-8") + b"\n")
        time.sleep(0.1)


def read_available_lines(
    stream,
    buffer: str,
) -> tuple[list[str], str, bool]:
    chunk = os.read(stream.fileno(), 4096)
    if not chunk:
        return [], buffer, True

    buffer += chunk.decode("utf-8", errors="replace")
    parts = buffer.split("\n")
    complete = [sanitize(line) for line in parts[:-1]]
    return complete, parts[-1], False


def main() -> int:
    args = parse_args()
    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    monitor_dir = Path(tempfile.mkdtemp(prefix="aios-qemu-monitor-"))
    monitor_path = monitor_dir / "monitor.sock"

    env = os.environ.copy()
    env["AIOS_QEMU_IMAGE_PATH"] = str(args.image_path.resolve())
    env.setdefault("AIOS_QEMU_MEMORY_MB", "2048")
    env.setdefault("AIOS_QEMU_SMP", "2")
    env.setdefault("AIOS_QEMU_DISPLAY", "none")
    env["AIOS_QEMU_MONITOR"] = f"unix:{monitor_path},server,nowait"
    env.setdefault("AIOS_QEMU_SERIAL", "stdio")

    reset_command = "sendkey ctrl-alt-delete" if args.expect_firstboot_once else "system_reset"

    proc = subprocess.Popen(
        ["bash", str(ROOT / "scripts" / "boot-qemu.sh")],
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
    first_cycle = {"kernel": None, "systemd": None, "service": None}
    second_cycle = {"kernel": None, "systemd": None, "service": None}
    firstboot_lines: list[str] = []
    failure_line: str | None = None
    kernel_count = 0
    reset_sent = False
    firstboot_finished = False
    first_boot_reset_deadline: float | None = None
    second_boot_settle_deadline: float | None = None
    selector: selectors.BaseSelector | None = None
    stdout_buffer = ""
    stdout_closed = False

    try:
        wait_for_monitor(monitor_path, 20)
        if proc.stdout is None:
            raise RuntimeError("QEMU stdout pipe was not created")
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)

        while time.monotonic() < deadline:
            now = time.monotonic()
            if not reset_sent and first_boot_reset_deadline is not None and now >= first_boot_reset_deadline and all(first_cycle.values()):
                send_monitor_command(monitor_path, reset_command)
                reset_sent = True
                first_boot_reset_deadline = None
                continue
            if second_boot_settle_deadline is not None and now >= second_boot_settle_deadline:
                break

            timeout = 0.25
            pending_deadlines = [d for d in (first_boot_reset_deadline if not reset_sent else None, second_boot_settle_deadline) if d is not None]
            if pending_deadlines:
                timeout = max(0.0, min(timeout, min(pending_deadlines) - now))

            events = selector.select(timeout)
            if not events:
                if stdout_buffer:
                    cleaned = sanitize(stdout_buffer)
                    if cleaned:
                        lines.append(cleaned)
                        args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""))
                    stdout_buffer = ""
                if proc.poll() is not None:
                    break
                continue

            ready_lines, stdout_buffer, stdout_closed = read_available_lines(
                proc.stdout, stdout_buffer
            )
            if stdout_closed:
                if stdout_buffer:
                    cleaned = sanitize(stdout_buffer)
                    if cleaned:
                        lines.append(cleaned)
                    stdout_buffer = ""
                if proc.poll() is not None:
                    break
                continue

            for cleaned in ready_lines:
                if not cleaned:
                    continue
                lines.append(cleaned)
                args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""))

                ignore_failures_until_reset = (
                    args.expect_firstboot_once and not reset_sent and firstboot_finished
                )
                if failure_line is None and not ignore_failures_until_reset:
                    for pattern in FAIL_PATTERNS:
                        if pattern.search(cleaned):
                            failure_line = cleaned
                            break

                if KERNEL_PATTERN.search(cleaned):
                    kernel_count += 1
                    if kernel_count == 1 and first_cycle["kernel"] is None:
                        first_cycle["kernel"] = cleaned
                    elif kernel_count >= 2 and second_cycle["kernel"] is None:
                        second_cycle["kernel"] = cleaned
                target_cycle = second_cycle if reset_sent else first_cycle
                if target_cycle["systemd"] is None and SYSTEMD_PATTERN.search(cleaned):
                    target_cycle["systemd"] = cleaned
                if target_cycle["service"] is None and SERVICE_PATTERN.search(cleaned):
                    target_cycle["service"] = cleaned
                if FIRSTBOOT_PATTERN.search(cleaned):
                    firstboot_lines.append(cleaned)
                    if args.expect_firstboot_once and len(firstboot_lines) > 1:
                        failure_line = "unexpected repeated AIOS_FIRSTBOOT_REPORT"
                if (
                    args.expect_firstboot_once
                    and not reset_sent
                    and FIRSTBOOT_FINISHED_PATTERN.search(cleaned)
                ):
                    firstboot_finished = True
                    first_boot_reset_deadline = time.monotonic() + FIRSTBOOT_RESET_DELAY_SECONDS

                if failure_line is not None:
                    break

                if not reset_sent:
                    if args.expect_firstboot_once:
                        if all(first_cycle.values()) and firstboot_lines and firstboot_finished:
                            continue
                    elif all(first_cycle.values()):
                        send_monitor_command(monitor_path, reset_command)
                        reset_sent = True
                        continue

                if reset_sent and all(second_cycle.values()):
                    if args.expect_firstboot_once:
                        if second_boot_settle_deadline is None:
                            second_boot_settle_deadline = (
                                time.monotonic() + SECOND_BOOT_SETTLE_SECONDS
                            )
                    else:
                        break

            if failure_line is not None:
                break
    finally:
        if selector is not None:
            selector.close()
        terminate(proc)
        if proc.stdout is not None:
            if stdout_buffer:
                cleaned = sanitize(stdout_buffer)
                if cleaned:
                    lines.append(cleaned)
                stdout_buffer = ""
            for tail in proc.stdout:
                cleaned = sanitize(tail)
                if cleaned:
                    lines.append(cleaned)
        args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    success = failure_line is None and reset_sent and all(second_cycle.values())
    if args.expect_firstboot_once:
        success = success and len(firstboot_lines) == 1

    summary = {
        "image_path": str(args.image_path.resolve()),
        "timeout_seconds": args.timeout,
        "log_path": str(args.log_path),
        "reset_sent": reset_sent,
        "kernel_count": kernel_count,
        "firstboot_count": len(firstboot_lines),
        "first_cycle": first_cycle,
        "second_cycle": second_cycle,
        "failure_line": failure_line,
        "tail": lines[-20:],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
