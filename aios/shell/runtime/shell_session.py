#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = RUNTIME_ROOT.parent
for candidate in (SHELL_ROOT, RUNTIME_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import shellctl
import shell_desktop
from shell_desktop_gtk import run_gtk_gui
from shell_profile import add_runtime_selection_arguments, build_session_plan, render_session_plan
from shell_snapshot import add_snapshot_arguments, build_snapshot, render_snapshot, write_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS shell session bootstrap")
    parser.add_argument(
        "command",
        nargs="?",
        default="plan",
        choices=["plan", "probe", "snapshot", "serve", "text", "export"],
    )
    add_snapshot_arguments(parser)
    add_runtime_selection_arguments(parser)
    return parser.parse_args()


def launch_compositor(plan: dict, args: argparse.Namespace, env: dict[str, str] | None = None) -> int:
    command = list(plan["compositor"]["launch_command"])
    if args.duration > 0:
        command.append("--once")
    if args.json:
        command.append("--emit-json")
    completed = subprocess.run(command, check=False, env=merge_env_overrides(env, plan["compositor"].get("env")))
    return completed.returncode


def probe_compositor(plan: dict, args: argparse.Namespace) -> int:
    if plan["session_backend"] != "compositor":
        print("shell session probe requires a compositor-backed profile", file=sys.stderr)
        return 1

    env = apply_panel_host_bridge_env(plan, dict(os.environ))
    env = merge_env_overrides(env, plan["compositor"].get("env")) or env
    command = [*plan["compositor"]["launch_command"], "--probe"]
    if args.json:
        command.append("--emit-json")
    completed = subprocess.run(command, check=False, env=env)
    return completed.returncode


def apply_panel_host_bridge_env(plan: dict, env: dict[str, str]) -> dict[str, str]:
    panel_host_bridge = plan.get("panel_host_bridge", {})
    if (
        panel_host_bridge.get("enabled")
        and panel_host_bridge.get("snapshot_command")
        and "AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_COMMAND" not in env
    ):
        env["AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_COMMAND"] = panel_host_bridge[
            "snapshot_command"
        ]
    if (
        panel_host_bridge.get("enabled")
        and panel_host_bridge.get("action_command")
        and "AIOS_SHELL_COMPOSITOR_PANEL_ACTION_COMMAND" not in env
    ):
        env["AIOS_SHELL_COMPOSITOR_PANEL_ACTION_COMMAND"] = panel_host_bridge[
            "action_command"
        ]
    if (
        panel_host_bridge.get("enabled")
        and panel_host_bridge.get("action_log_path")
        and "AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH" not in env
    ):
        env["AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH"] = panel_host_bridge[
            "action_log_path"
        ]
    if (
        panel_host_bridge.get("enabled")
        and panel_host_bridge.get("refresh_ticks") is not None
        and "AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_REFRESH_TICKS" not in env
    ):
        env["AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_REFRESH_TICKS"] = str(
            panel_host_bridge["refresh_ticks"]
        )
    return env


def merge_env_overrides(
    base: dict[str, str] | None,
    overrides: dict[str, str | None] | None,
) -> dict[str, str] | None:
    if base is None and not overrides:
        return None
    merged = dict(os.environ if base is None else base)
    for key, value in (overrides or {}).items():
        if value in (None, ""):
            merged.pop(key, None)
        else:
            merged[key] = str(value)
    return merged


@contextmanager
def patched_environment(overrides: dict[str, str | None]):
    previous: dict[str, str | None] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def wait_for_path(path: Path, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return path.exists()


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float = 1.5) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(str(response["error"]))
    return response["result"]


def wait_for_panel_bridge(socket_path: Path, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if socket_path.exists():
            try:
                rpc_call(socket_path, "system.health.get", {}, timeout=1.0)
                return True
            except Exception:
                time.sleep(0.05)
                continue
        time.sleep(0.05)
    return False


def choose_panel_bridge_socket_path(base_dir: Path) -> Path:
    candidate = base_dir / "pb.sock"
    if len(str(candidate)) <= 96:
        return candidate
    return Path(tempfile.gettempdir()) / f"aiospb-{os.getpid()}-{int(time.time() * 1000)}.sock"


def terminate_process(process: subprocess.Popen) -> int:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
    return process.returncode or 0


def read_process_log(path: Path, limit: int = 2400) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(content) <= limit:
        return content
    return content[-limit:]


def run_host_command(command: str, env_overrides: dict[str, str | None]) -> int:
    with patched_environment(env_overrides):
        completed = subprocess.run(["/bin/sh", "-lc", command], check=False)
    return completed.returncode


@contextmanager
def managed_panel_bridge(
    plan: dict,
    args: argparse.Namespace,
    bridge_root: Path | None = None,
):
    panel_host_bridge = plan.get("panel_host_bridge", {})
    command = panel_host_bridge.get("service_command")
    if not panel_host_bridge.get("enabled") or not command:
        yield {}
        return

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if bridge_root is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="aios-shell-panel-bridge-")
        bridge_root = Path(temp_dir.name)

    bridge_root.mkdir(parents=True, exist_ok=True)
    socket_path = choose_panel_bridge_socket_path(bridge_root)
    log_path = bridge_root / "panel-bridge-service.log"
    if socket_path.exists():
        socket_path.unlink()

    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            ["/bin/sh", "-lc", command],
            env={
                **os.environ,
                "AIOS_SHELL_PANEL_BRIDGE_SOCKET": str(socket_path),
            },
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

    try:
        if not wait_for_panel_bridge(socket_path, timeout=5.0):
            logs = read_process_log(log_path)
            terminate_process(process)
            message = f"panel bridge service unavailable at {socket_path}"
            if logs:
                message += f": {logs}"
            else:
                message += f" (log: {log_path})"
            print(
                f"{message}; falling back to command bridge",
                file=sys.stderr,
            )
            yield {}
            return

        yield {
            "AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET": str(socket_path),
        }
    finally:
        returncode = terminate_process(process)
        logs = read_process_log(log_path)
        if returncode not in (0, None) and logs:
            print(f"panel bridge service exited with code {returncode}: {logs}", file=sys.stderr)
        if temp_dir is not None:
            temp_dir.cleanup()


def run_gtk_host(
    profile: dict,
    args: argparse.Namespace,
    plan: dict,
    env_overrides: dict[str, str | None],
) -> int:
    host_runtime = plan.get("host_runtime", {})
    panel_client_command = host_runtime.get("gtk_panel_client_command")
    if panel_client_command and env_overrides.get("AIOS_SHELL_SESSION_BACKEND_ACTIVE") == "compositor":
        return run_host_command(panel_client_command, env_overrides)

    external_host_command = host_runtime.get("gtk_host_command")
    if external_host_command:
        return run_host_command(external_host_command, env_overrides)

    try:
        with patched_environment(env_overrides):
            return run_gtk_gui(profile, args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        if exc.code not in (None, 0):
            print(exc.code, file=sys.stderr)
        return 0 if exc.code in (None, 0) else 1


def fallback_from_nested_session(
    plan: dict,
    profile: dict,
    args: argparse.Namespace,
    reason: str,
) -> int:
    host_runtime = plan.get("host_runtime", {})
    if host_runtime.get("compositor_required"):
        print(f"compositor session failed: {reason}", file=sys.stderr)
        return 1

    fallback = host_runtime.get("nested_fallback", "disabled")
    if fallback == "disabled":
        print(f"compositor session failed and fallback is disabled: {reason}", file=sys.stderr)
        return 1

    print(f"compositor session fallback: {fallback} ({reason})", file=sys.stderr)
    fallback_env = {
        "AIOS_SHELL_SESSION_ENTRYPOINT": str(plan.get("entrypoint", "compatibility")),
        "AIOS_SHELL_SESSION_BACKEND_ACTIVE": "standalone-fallback",
    }
    if fallback == "standalone-tk":
        with patched_environment(fallback_env):
            return shell_desktop.run_tk_gui(profile, args)
    return run_gtk_host(profile, args, plan, fallback_env)


def launch_nested_gtk_session(plan: dict, profile: dict, args: argparse.Namespace) -> int:
    if args.json:
        raise SystemExit("JSON output is unsupported for compositor-backed GTK serve mode")

    with tempfile.TemporaryDirectory(prefix="aios-shell-session-") as temp_dir:
        runtime_dir = Path(temp_dir) / "xdg-runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        socket_name = f"aios-shell-{os.getpid()}"
        compositor_env = apply_panel_host_bridge_env(plan, {
            **os.environ,
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "AIOS_SHELL_COMPOSITOR_SOCKET_NAME": socket_name,
        })
        compositor_env = merge_env_overrides(compositor_env, plan["compositor"].get("env")) or compositor_env
        with managed_panel_bridge(plan, args, runtime_dir) as bridge_env:
            compositor = subprocess.Popen(
                plan["compositor"]["launch_command"],
                env={**compositor_env, **bridge_env},
            )
            try:
                if sys.platform.startswith("linux"):
                    socket_path = runtime_dir / socket_name
                    if not wait_for_path(socket_path, timeout=5.0):
                        if compositor.poll() is not None:
                            return fallback_from_nested_session(
                                plan,
                                profile,
                                args,
                                f"compositor exited before socket ready ({compositor.returncode})",
                            )
                        return fallback_from_nested_session(
                            plan,
                            profile,
                            args,
                            f"compositor socket not ready: {socket_path}",
                        )

                host_env = {
                    "XDG_RUNTIME_DIR": str(runtime_dir),
                    "WAYLAND_DISPLAY": socket_name,
                    "GDK_BACKEND": "wayland" if sys.platform.startswith("linux") else os.environ.get("GDK_BACKEND"),
                    "DISPLAY": None if sys.platform.startswith("linux") else os.environ.get("DISPLAY"),
                    "AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET": bridge_env.get(
                        "AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET"
                    ),
                    "AIOS_SHELL_SESSION_ENTRYPOINT": str(plan.get("entrypoint", "compatibility")),
                    "AIOS_SHELL_SESSION_BACKEND_ACTIVE": "compositor",
                }
                host_returncode = run_gtk_host(profile, args, plan, host_env)
                if host_returncode == 0:
                    return 0
                return fallback_from_nested_session(
                    plan,
                    profile,
                    args,
                    f"gtk host exited with code {host_returncode}",
                )
            finally:
                compositor_returncode = terminate_process(compositor)
                if compositor_returncode not in (0, None):
                    print(
                        f"nested compositor exited with code {compositor_returncode}",
                        file=sys.stderr,
                    )


def launch_compositor_with_bridge(plan: dict, args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="aios-shell-compositor-bridge-") as temp_dir:
        with managed_panel_bridge(plan, args, Path(temp_dir)) as bridge_env:
            env = apply_panel_host_bridge_env(plan, {**os.environ, **bridge_env})
            return launch_compositor(plan, args, env=env)


def main() -> int:
    args = parse_args()
    profile = shellctl.load_profile(args.profile)
    plan = build_session_plan(profile, args.profile, args)

    if args.command == "plan":
        if args.json:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
        else:
            print(render_session_plan(plan))
        return 0

    if args.command == "serve":
        if plan["session_backend"] == "compositor":
            if plan["desktop_host"] == "gtk":
                return launch_nested_gtk_session(plan, profile, args)
            return launch_compositor_with_bridge(plan, args)
        if plan["desktop_host"] == "gtk":
            return run_gtk_gui(profile, args)
        return shell_desktop.run_tk_gui(profile, args)

    if args.command == "probe":
        return probe_compositor(plan, args)

    snapshot = build_snapshot(profile, args)
    snapshot["session_plan"] = {
        "entrypoint": plan["entrypoint"],
        "desktop_host": plan["desktop_host"],
        "session_backend": plan["session_backend"],
        "host_runtime": plan["host_runtime"],
    }
    artifacts = write_outputs(snapshot, args)
    if args.command == "snapshot" and args.json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    elif args.command == "export":
        payload = {
            "snapshot": snapshot,
            "artifacts": artifacts,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(render_snapshot(snapshot))
            if artifacts:
                print("")
                print("artifacts:")
                for key, value in artifacts.items():
                    print(f"- {key}: {value}")
    else:
        print(render_snapshot(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
