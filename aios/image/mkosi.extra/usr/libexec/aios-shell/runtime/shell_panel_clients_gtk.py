#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


RUNTIME_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = RUNTIME_ROOT.parent
for candidate in (SHELL_ROOT, RUNTIME_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from panel_actions import dispatch_panel_action
from shell_snapshot import add_snapshot_arguments, build_snapshot
import shellctl


BRIDGE_METHOD_HEALTH = "system.health.get"
BRIDGE_METHOD_SNAPSHOT = "shell.panel.snapshot.get"
BRIDGE_METHOD_ACTION = "shell.panel.action.dispatch"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS standalone GTK panel clients")
    parser.add_argument("command", nargs="?", default="serve", choices=["snapshot", "serve"])
    parser.add_argument("--component")
    add_snapshot_arguments(parser)
    parser.add_argument(
        "--bridge-socket",
        type=Path,
        default=Path(
            os.environ.get(
                "AIOS_SHELL_COMPOSITOR_PANEL_BRIDGE_SOCKET",
                "/tmp/aios-shell-panel-bridge.sock",
            )
        ),
    )
    parser.add_argument(
        "--respawn-limit",
        type=int,
        default=max(0, int(os.environ.get("AIOS_SHELL_PANEL_CLIENT_RESPAWN_LIMIT", "2"))),
    )
    parser.add_argument(
        "--respawn-backoff",
        type=float,
        default=max(0.0, float(os.environ.get("AIOS_SHELL_PANEL_CLIENT_RESPAWN_BACKOFF", "0.25"))),
    )
    return parser.parse_args()


def require_gtk_runtime():
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, GLib, Gtk
    except Exception as error:  # pragma: no cover
        raise SystemExit(
            "GTK panel clients unavailable: install PyGObject with GTK4 and libadwaita typelibs "
            f"(import failed: {error})"
        )
    return Adw, GLib, Gtk


def load_bridge_transport(socket_path: Path) -> dict | None:
    if not socket_path.exists() or not socket_path.is_file():
        return None
    try:
        payload = json.loads(socket_path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("transport") not in {"tcp", "mock-file"}:
        return None
    return payload


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float = 2.0) -> dict:
    transport = load_bridge_transport(socket_path)
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    if transport is not None and transport.get("transport") == "tcp":
        host = str(transport.get("host") or "127.0.0.1")
        port = int(transport.get("port") or 0)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect((host, port))
            client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(65536)
                if not chunk:
                    break
                data += chunk
    else:
        if not hasattr(socket, "AF_UNIX"):
            raise RuntimeError(f"unix-domain-socket-unavailable:{socket_path}")
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


def bridge_available(socket_path: Path) -> bool:
    if not socket_path.exists():
        return False
    try:
        rpc_call(socket_path, BRIDGE_METHOD_HEALTH, {})
        return True
    except Exception:
        return False


def load_snapshot(profile: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if bridge_available(args.bridge_socket):
        return rpc_call(args.bridge_socket, BRIDGE_METHOD_SNAPSHOT, {}), "bridge"
    return build_snapshot(profile, args), "local"


def window_title_token(surface: dict[str, Any]) -> str:
    return str(surface.get("component") or "panel")


def display_title(surface: dict[str, Any]) -> str:
    model = surface.get("model") or {}
    header = model.get("header") or {}
    return str(header.get("title") or surface.get("component") or "Panel")


def window_specs(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for surface in snapshot.get("surfaces", []):
        model = surface.get("model") or {}
        header = model.get("header") or {}
        meta = model.get("meta") or {}
        specs.append(
            {
                "component": surface.get("component"),
                "panel_id": model.get("panel_id") or surface.get("panel_id"),
                "window_title": window_title_token(surface),
                "display_title": display_title(surface),
                "subtitle": header.get("subtitle"),
                "status": header.get("status"),
                "tone": header.get("tone"),
                "layout_width": surface.get("layout_width", 420),
                "layout_height": surface.get("layout_height", 320),
                "focus_policy": surface.get("focus_policy"),
                "pointer_policy": surface.get("pointer_policy"),
                "action_count": len(model.get("actions", [])),
                "section_count": len(model.get("sections", [])),
                "selected_handle_id": meta.get("selected_handle_id"),
                "confirmed_handle_id": meta.get("confirmed_handle_id"),
                "detail_handle_id": meta.get("detail_handle_id"),
                "model": model,
            }
        )
    return specs


def snapshot_payload(profile: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    snapshot, source = load_snapshot(profile, args)
    return {
        "source": source,
        "spawn_strategy": "process-per-component",
        "window_count": len(snapshot.get("surfaces", [])),
        "bridge_socket": str(args.bridge_socket) if bridge_available(args.bridge_socket) else None,
        "windows": window_specs(snapshot),
    }


def dispatch_action(
    profile: dict[str, Any],
    args: argparse.Namespace,
    snapshot: dict[str, Any],
    component: str,
    action: dict[str, Any],
) -> dict[str, Any]:
    if bridge_available(args.bridge_socket):
        model = (next(
            (surface.get("model") or {} for surface in snapshot.get("surfaces", []) if surface.get("component") == component),
            {},
        ))
        return rpc_call(
            args.bridge_socket,
            BRIDGE_METHOD_ACTION,
            {
                "slot_id": component,
                "component": component,
                "panel_id": model.get("panel_id"),
                "action_id": action.get("action_id"),
                "input_kind": "gtk-button",
            },
        )
    payload = dispatch_panel_action(profile, args, snapshot, component, action)
    return payload["result"]


def component_snapshot(profile: dict[str, Any], args: argparse.Namespace, component: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    snapshot, source = load_snapshot(profile, args)
    surface = next(
        (item for item in snapshot.get("surfaces", []) if item.get("component") == component),
        None,
    )
    if surface is None:
        return snapshot, {
            "component": component,
            "panel_id": component,
            "window_title": component,
            "display_title": component,
            "subtitle": "Surface not available",
            "status": "missing",
            "tone": "warning",
            "layout_width": 420,
            "layout_height": 280,
            "focus_policy": "retain-client-focus",
            "pointer_policy": "interactive",
            "action_count": 0,
            "section_count": 0,
            "selected_handle_id": None,
            "confirmed_handle_id": None,
            "detail_handle_id": None,
            "model": {
                "header": {
                    "title": component,
                    "status": "missing",
                    "subtitle": "Waiting for surface snapshot",
                },
                "actions": [],
                "sections": [],
                "badges": [],
                "meta": {"component": component},
            },
        }, source
    return snapshot, next(item for item in window_specs(snapshot) if item.get("component") == component), source


def snapshot_context_args(args: argparse.Namespace) -> list[str]:
    command = ["--profile", str(args.profile)]
    string_fields = [
        ("session_id", "--session-id"),
        ("task_id", "--task-id"),
        ("user_id", "--user-id"),
        ("intent", "--intent"),
        ("title", "--title"),
        ("task_state", "--task-state"),
        ("task_state_filter", "--task-state-filter"),
        ("status_filter", "--status-filter"),
        ("tone_filter", "--tone-filter"),
    ]
    for field_name, flag in string_fields:
        value = getattr(args, field_name, None)
        if value not in (None, ""):
            command.extend([flag, str(value)])
    if getattr(args, "limit", None) is not None:
        command.extend(["--limit", str(args.limit)])
    for field_name, flag in (
        ("launcher_fixture", "--launcher-fixture"),
        ("task_fixture", "--task-fixture"),
        ("approval_fixture", "--approval-fixture"),
        ("chooser_fixture", "--chooser-fixture"),
        ("output_prefix", "--output-prefix"),
    ):
        value = getattr(args, field_name, None)
        if value is not None:
            command.extend([flag, str(Path(value).expanduser().resolve())])
    if getattr(args, "include_disabled", False):
        command.append("--include-disabled")
    if getattr(args, "interval", None) is not None:
        command.extend(["--interval", str(args.interval)])
    if getattr(args, "duration", None) is not None:
        command.extend(["--duration", str(args.duration)])
    for surface in getattr(args, "surfaces", []) or []:
        if surface not in (None, ""):
            command.extend(["--surface", str(surface)])
    command.extend(["--bridge-socket", str(args.bridge_socket)])
    return command


def component_log_path(log_root: Path, component: str) -> Path:
    safe_name = "".join(
        character if character.isascii() and character.isalnum() else "-"
        for character in component
    ).strip("-")
    return log_root / f"{safe_name or 'panel'}.log"


def read_log_excerpt(path: Path, limit: int = 2400) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(content) <= limit:
        return content
    return content[-limit:]


def spawn_component_process(
    child_base: list[str],
    component: str,
    log_root: Path,
    attempt: int,
) -> tuple[subprocess.Popen[str], Path]:
    log_path = component_log_path(log_root, f"{component}-attempt-{attempt}")
    env = dict(os.environ)
    env["AIOS_SHELL_PANEL_COMPONENT"] = component
    env["AIOS_SHELL_PANEL_RESPAWN_ATTEMPT"] = str(attempt)
    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [*child_base, "--component", component],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
    return process, log_path


def supervise_panel_clients(profile: dict[str, Any], args: argparse.Namespace) -> int:
    snapshot, _source = load_snapshot(profile, args)
    components = [
        str(surface.get("component"))
        for surface in snapshot.get("surfaces", [])
        if isinstance(surface.get("component"), str)
    ]
    if not components:
        return 0

    child_base = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        *snapshot_context_args(args),
    ]

    processes: list[tuple[str, subprocess.Popen[str], Path]] = []
    restart_counts: dict[str, int] = {component: 0 for component in components}
    stop = False
    success = False
    log_root = Path(tempfile.mkdtemp(prefix="aios-shell-panel-clients-logs-"))

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    previous_sigint = signal.signal(signal.SIGINT, handle_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, handle_signal)
    try:
        for component in components:
            process, log_path = spawn_component_process(child_base, component, log_root, attempt=0)
            processes.append((component, process, log_path))

        while processes and not stop:
            remaining: list[tuple[str, subprocess.Popen[str], Path]] = []
            for component, process, log_path in processes:
                returncode = process.poll()
                if returncode is None:
                    remaining.append((component, process, log_path))
                    continue
                if returncode != 0:
                    restart_count = restart_counts.get(component, 0)
                    if not stop and restart_count < args.respawn_limit:
                        next_attempt = restart_count + 1
                        restart_counts[component] = next_attempt
                        time.sleep(args.respawn_backoff)
                        respawned_process, respawned_log_path = spawn_component_process(
                            child_base,
                            component,
                            log_root,
                            attempt=next_attempt,
                        )
                        print(
                            f"panel client restarted: component={component} attempt={next_attempt}",
                            file=sys.stderr,
                        )
                        remaining.append((component, respawned_process, respawned_log_path))
                        continue
                    logs = read_log_excerpt(log_path)
                    message = f"panel client exited with code {returncode}: {component}"
                    if logs:
                        message += f": {logs}"
                    else:
                        message += f" (log: {log_path})"
                    raise RuntimeError(message)
            processes = remaining
            if processes:
                time.sleep(0.05)

        for _component, process, _log_path in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        success = True
        return 0
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        if success:
            shutil.rmtree(log_root, ignore_errors=True)
        else:
            for _component, process, _log_path in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            print(f"panel client logs kept at: {log_root}", file=sys.stderr)


def run_component_client(profile: dict[str, Any], args: argparse.Namespace, component: str) -> int:
    Adw, GLib, Gtk = require_gtk_runtime()

    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("GUI display unavailable; use snapshot mode or provide DISPLAY/WAYLAND_DISPLAY")

    application_id = f"aios.shell.panel.{component.replace('-', '.')}"

    class PanelClientsApp(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id=application_id, flags=0)
            self.snapshot: dict[str, Any] = {}
            self.window = None
            self.body_box = None
            self.header_label = None
            self.subtitle_label = None
            self.profile = profile

        def do_activate(self) -> None:  # pragma: no cover
            if self.window is None:
                self.window = Adw.ApplicationWindow(application=self)
                root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                root.set_margin_top(12)
                root.set_margin_bottom(12)
                root.set_margin_start(12)
                root.set_margin_end(12)

                self.header_label = Gtk.Label(label=component)
                self.header_label.set_xalign(0.0)
                self.header_label.add_css_class("title-3")
                self.subtitle_label = Gtk.Label(label="")
                self.subtitle_label.set_xalign(0.0)
                self.subtitle_label.set_wrap(True)
                self.body_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                root.append(self.header_label)
                root.append(self.subtitle_label)
                root.append(self.body_box)
                self.window.set_content(root)
                self.window.present()
            self.refresh()
            GLib.timeout_add(max(500, int(args.interval * 1000)), self.on_timeout)
            if args.duration > 0:
                GLib.timeout_add(int(args.duration * 1000), self.on_duration_complete)

        def on_timeout(self) -> bool:
            self.refresh()
            return True

        def on_duration_complete(self) -> bool:
            self.quit()
            return False

        def refresh(self) -> None:
            self.snapshot, spec, _source = component_snapshot(self.profile, args, component)
            self.render_component(spec)

        def render_component(self, spec: dict[str, Any]) -> None:
            model = spec["model"] or {}
            header = model.get("header") or {}
            self.window.set_title(spec["window_title"])
            self.window.set_default_size(int(spec["layout_width"]), int(spec["layout_height"]))
            self.header_label.set_label(spec["display_title"])
            self.subtitle_label.set_label(
                f"{header.get('status', 'unknown')} | focus={spec.get('focus_policy', '-')} | pointer={spec.get('pointer_policy', '-')}"
            )

            body = self.body_box
            while True:
                child = body.get_first_child()
                if child is None:
                    break
                body.remove(child)

            badges = model.get("badges", [])
            if badges:
                badge_label = Gtk.Label(
                    label=" | ".join(f"{item.get('label')}: {item.get('value')}" for item in badges)
                )
                badge_label.set_xalign(0.0)
                badge_label.set_wrap(True)
                body.append(badge_label)

            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            for action in model.get("actions", []):
                button = Gtk.Button(label=action.get("label", action.get("action_id", "action")))
                button.set_sensitive(bool(action.get("enabled", True)))
                button.connect("clicked", self.on_action_clicked, action)
                actions.append(button)
            body.append(actions)

            for section in model.get("sections", []):
                frame = Gtk.Frame(label=section.get("title", section.get("section_id", "section")))
                section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                section_box.set_margin_top(8)
                section_box.set_margin_bottom(8)
                section_box.set_margin_start(8)
                section_box.set_margin_end(8)
                items = section.get("items", [])
                if not items:
                    placeholder = Gtk.Label(label="No entries")
                    placeholder.set_xalign(0.0)
                    section_box.append(placeholder)
                else:
                    for item in items:
                        label = Gtk.Label(
                            label=f"{item.get('label', '-')}: {item.get('value', '-')}",
                        )
                        label.set_xalign(0.0)
                        label.set_wrap(True)
                        section_box.append(label)
                frame.set_child(section_box)
                body.append(frame)

        def on_action_clicked(self, _button, action: dict[str, Any]) -> None:
            try:
                dispatch_action(self.profile, args, self.snapshot, component, action)
            except Exception as error:  # pragma: no cover
                print(f"panel action failed for {component}: {error}", file=sys.stderr)
            self.refresh()

    app = PanelClientsApp()
    return app.run([])


def main() -> int:
    args = parse_args()
    profile = shellctl.load_profile(args.profile)
    if args.command == "snapshot":
        print(json.dumps(snapshot_payload(profile, args), indent=2, ensure_ascii=False))
        return 0
    if args.component:
        return run_component_client(profile, args, args.component)
    return supervise_panel_clients(profile, args)


if __name__ == "__main__":
    raise SystemExit(main())

