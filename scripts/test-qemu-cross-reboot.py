#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from queue import Empty, Queue
import re
import signal
import socket
import subprocess
import sys
import tempfile
from threading import Thread
import time
from pathlib import Path

from host_exec import bash_command, bash_path, parse_embedded_json, prepend_binary_parent_to_path, resolve_qemu_binary

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORK_ROOT = ROOT / "out" / "validation" / "qemu-cross-reboot-smoke"
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


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


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


def choose_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def resolve_monitor_dir() -> Path:
    override = os.environ.get("AIOS_QEMU_MONITOR_DIR")
    if override:
        return Path(override).expanduser()
    if unix_rpc_supported() and str(DEFAULT_WORK_ROOT).startswith("/mnt/"):
        return Path(tempfile.gettempdir()) / "aios-qemu-cross-reboot-smoke"
    return DEFAULT_WORK_ROOT


def build_monitor_endpoint() -> dict[str, object]:
    if unix_rpc_supported():
        monitor_dir = resolve_monitor_dir()
        if monitor_dir.exists():
            import shutil

            shutil.rmtree(monitor_dir, ignore_errors=True)
        monitor_dir.mkdir(parents=True, exist_ok=True)
        monitor_path = monitor_dir / "monitor.sock"
        return {
            "transport": "unix",
            "path": monitor_path,
            "monitor_dir": monitor_dir,
            "env_value": f"unix:{monitor_path},server,nowait",
            "summary": str(monitor_path),
        }

    port = choose_free_port()
    return {
        "transport": "tcp",
        "host": "127.0.0.1",
        "port": port,
        "monitor_dir": None,
        "env_value": f"tcp:127.0.0.1:{port},server,nowait",
        "summary": f"127.0.0.1:{port}",
    }


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


def wait_for_monitor(endpoint: dict[str, object], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if endpoint["transport"] == "unix":
            if Path(endpoint["path"]).exists():
                return
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(0.5)
                try:
                    client.connect((str(endpoint["host"]), int(endpoint["port"])))
                except OSError:
                    pass
                else:
                    return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for qemu monitor: {endpoint['summary']}")


def send_monitor_command(endpoint: dict[str, object], command: str) -> None:
    if endpoint["transport"] == "unix":
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        address: object = str(endpoint["path"])
    else:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        address = (str(endpoint["host"]), int(endpoint["port"]))

    with client:
        client.settimeout(5.0)
        client.connect(address)
        try:
            client.recv(4096)
        except socket.timeout:
            pass
        client.sendall(command.encode("utf-8") + b"\n")
        time.sleep(0.1)


def start_output_pump(stream) -> tuple[Queue[str | None], Thread]:
    output_queue: Queue[str | None] = Queue()

    def pump() -> None:
        try:
            for line in stream:
                output_queue.put(sanitize(line))
        finally:
            output_queue.put(None)

    worker = Thread(target=pump, daemon=True)
    worker.start()
    return output_queue, worker


def drain_output_queue(output_queue: Queue[str | None], lines: list[str]) -> None:
    while True:
        try:
            item = output_queue.get_nowait()
        except Empty:
            return
        if item:
            lines.append(item)


def main() -> int:
    args = parse_args()
    image_path = args.image_path.resolve()
    if not image_path.exists():
        return skip("cross reboot image missing", image_path=str(image_path))

    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    endpoint = build_monitor_endpoint()

    env = bash_env()
    env["AIOS_QEMU_IMAGE_PATH"] = bash_path(image_path)
    env.setdefault("AIOS_QEMU_MEMORY_MB", "2048")
    env.setdefault("AIOS_QEMU_SMP", "2")
    env.setdefault("AIOS_QEMU_DISPLAY", "none")
    env["AIOS_QEMU_MONITOR"] = str(endpoint["env_value"])
    env.setdefault("AIOS_QEMU_SERIAL", "stdio")

    try:
        qemu_preflight = run_preflight(ROOT / "scripts" / "boot-qemu.sh", env=env)
    except RuntimeError as exc:
        return skip(str(exc), image_path=str(image_path), monitor=str(endpoint["summary"]))
    if qemu_preflight.get("status") != "ready":
        return skip(
            "qemu cross reboot prerequisites unavailable on this host",
            image_path=str(image_path),
            monitor=str(endpoint["summary"]),
            qemu_preflight=qemu_preflight,
        )

    reset_command = "sendkey ctrl-alt-delete" if args.expect_firstboot_once else "system_reset"
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
    first_cycle = {"kernel": None, "systemd": None, "service": None}
    second_cycle = {"kernel": None, "systemd": None, "service": None}
    firstboot_lines: list[str] = []
    failure_line: str | None = None
    kernel_count = 0
    reset_sent = False
    firstboot_finished = False
    first_boot_reset_deadline: float | None = None
    second_boot_settle_deadline: float | None = None
    output_queue: Queue[str | None] | None = None
    output_thread: Thread | None = None

    try:
        wait_for_monitor(endpoint, 20.0)
        if proc.stdout is None:
            raise RuntimeError("QEMU stdout pipe was not created")
        output_queue, output_thread = start_output_pump(proc.stdout)

        while time.monotonic() < deadline:
            now = time.monotonic()
            if (
                not reset_sent
                and first_boot_reset_deadline is not None
                and now >= first_boot_reset_deadline
                and all(first_cycle.values())
            ):
                send_monitor_command(endpoint, reset_command)
                reset_sent = True
                first_boot_reset_deadline = None
                continue
            if second_boot_settle_deadline is not None and now >= second_boot_settle_deadline:
                break

            timeout = 0.25
            pending_deadlines = [
                value
                for value in (
                    first_boot_reset_deadline if not reset_sent else None,
                    second_boot_settle_deadline,
                )
                if value is not None
            ]
            if pending_deadlines:
                timeout = max(0.0, min(timeout, min(pending_deadlines) - now))

            try:
                item = output_queue.get(timeout=timeout)
            except Empty:
                if proc.poll() is not None:
                    break
                continue

            if item is None:
                if proc.poll() is not None:
                    break
                continue
            if not item:
                continue

            lines.append(item)
            args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

            ignore_failures_until_reset = args.expect_firstboot_once and not reset_sent and firstboot_finished
            if failure_line is None and not ignore_failures_until_reset:
                for pattern in FAIL_PATTERNS:
                    if pattern.search(item):
                        failure_line = item
                        break

            if KERNEL_PATTERN.search(item):
                kernel_count += 1
                if kernel_count == 1 and first_cycle["kernel"] is None:
                    first_cycle["kernel"] = item
                elif kernel_count >= 2 and second_cycle["kernel"] is None:
                    second_cycle["kernel"] = item

            target_cycle = second_cycle if reset_sent else first_cycle
            if target_cycle["systemd"] is None and SYSTEMD_PATTERN.search(item):
                target_cycle["systemd"] = item
            if target_cycle["service"] is None and SERVICE_PATTERN.search(item):
                target_cycle["service"] = item

            if FIRSTBOOT_PATTERN.search(item):
                firstboot_lines.append(item)
                if args.expect_firstboot_once and len(firstboot_lines) > 1:
                    failure_line = "unexpected repeated AIOS_FIRSTBOOT_REPORT"

            if args.expect_firstboot_once and not reset_sent and FIRSTBOOT_FINISHED_PATTERN.search(item):
                firstboot_finished = True
                first_boot_reset_deadline = time.monotonic() + FIRSTBOOT_RESET_DELAY_SECONDS

            if failure_line is not None:
                break

            if not reset_sent:
                if args.expect_firstboot_once:
                    if all(first_cycle.values()) and firstboot_lines and firstboot_finished:
                        continue
                elif all(first_cycle.values()):
                    send_monitor_command(endpoint, reset_command)
                    reset_sent = True
                    continue

            if reset_sent and all(second_cycle.values()):
                if args.expect_firstboot_once:
                    if second_boot_settle_deadline is None:
                        second_boot_settle_deadline = time.monotonic() + SECOND_BOOT_SETTLE_SECONDS
                else:
                    break
    finally:
        terminate(proc)
        if output_queue is not None:
            drain_output_queue(output_queue, lines)
        if output_thread is not None:
            output_thread.join(timeout=1.0)
        args.log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    success = failure_line is None and reset_sent and all(second_cycle.values())
    if args.expect_firstboot_once:
        success = success and len(firstboot_lines) == 1

    summary = {
        "image_path": str(image_path),
        "timeout_seconds": args.timeout,
        "log_path": str(args.log_path),
        "monitor_transport": endpoint["transport"],
        "monitor_endpoint": str(endpoint["summary"]),
        "monitor_dir": str(endpoint["monitor_dir"]) if endpoint["monitor_dir"] is not None else None,
        "reset_sent": reset_sent,
        "kernel_count": kernel_count,
        "firstboot_count": len(firstboot_lines),
        "first_cycle": first_cycle,
        "second_cycle": second_cycle,
        "failure_line": failure_line,
        "tail": lines[-20:],
        "qemu_preflight": qemu_preflight,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
