#!/usr/bin/env python3
"""Bridge module for launching any AIOS shell component panel in GTK4 mode.

Usage as a script::

    python shell_panel_clients_integration.py \\
        --component notification-center \\
        --profile /path/to/profile.yaml \\
        --interval 3.0

Usage as a library::

    from shell_panel_clients_integration import launch_component_gtk

    launch_component_gtk("launcher", profile_path=Path("..."))
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = RUNTIME_ROOT.parent
for _candidate in (SHELL_ROOT, RUNTIME_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import shellctl
from shell_panel_gtk_renderer import (
    gtk_available,
    require_gtk,
    update_panel_widget,
)


def _require_display() -> None:
    if sys.platform.startswith("linux") and not os.environ.get(
        "DISPLAY"
    ) and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit(
            "GUI display unavailable; set DISPLAY or WAYLAND_DISPLAY"
        )


def load_panel_model(
    profile: dict[str, Any],
    component: str,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    panel_args = ["model", "--json", *(extra_args or [])]
    result = shellctl.run_panel(profile, component, panel_args, expect_json=True)
    if isinstance(result, dict):
        return result
    return {}


def _dispatch_action(
    profile: dict[str, Any],
    component: str,
    action: dict[str, Any],
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    action_id = action.get("action_id")
    if not action_id:
        return {}
    command = ["action", "--action", action_id, *(extra_args or [])]
    try:
        result = shellctl.run_panel(
            profile, component, command, expect_json=True
        )
    except subprocess.CalledProcessError:
        return {}
    return result if isinstance(result, dict) else {}


def launch_component_gtk(
    component: str,
    profile_path: Path | None = None,
    interval: float = 2.0,
    duration: float = 0.0,
    extra_args: list[str] | None = None,
) -> int:
    if not gtk_available():
        raise SystemExit(
            "GTK4 renderer is not available; install PyGObject with GTK4 and "
            "libadwaita typelibs"
        )
    _require_display()

    Adw, Gtk = require_gtk()
    from gi.repository import GLib

    resolved_profile_path = profile_path or shellctl.DEFAULT_PROFILE
    profile = shellctl.load_profile(resolved_profile_path)
    component = shellctl.normalize_component(component)
    app_id = f"aios.shell.integration.{component.replace('-', '.')}"

    class IntegrationApp(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id=app_id, flags=0)
            self.window: Any = None
            self.panel_box: Any = None

        def do_activate(self) -> None:
            if self.window is None:
                self.window = Adw.ApplicationWindow(application=self)
                self.window.set_title(f"AIOS · {component}")
                self.window.set_default_size(520, 640)

                self.panel_box = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL, spacing=0
                )
                self.window.set_content(self.panel_box)

            self.window.present()
            self._refresh()
            GLib.timeout_add(max(500, int(interval * 1000)), self._on_tick)
            if duration > 0:
                GLib.timeout_add(
                    int(duration * 1000), self._on_duration_done
                )

        def _on_tick(self) -> bool:
            self._refresh()
            return True

        def _on_duration_done(self) -> bool:
            self.quit()
            return False

        def _on_action(self, action: dict[str, Any]) -> None:
            _dispatch_action(profile, component, action, extra_args)
            self._refresh()

        def _refresh(self) -> None:
            try:
                model = load_panel_model(profile, component, extra_args)
            except Exception:
                model = {
                    "header": {
                        "title": component,
                        "status": "error",
                        "subtitle": "Failed to load panel model",
                        "tone": "critical",
                    },
                    "badges": [],
                    "actions": [],
                    "sections": [],
                }
            update_panel_widget(
                self.panel_box, model, action_callback=self._on_action
            )

    app = IntegrationApp()
    return app.run([])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch an AIOS shell component panel in GTK4"
    )
    parser.add_argument(
        "--component",
        required=True,
        help="Shell component name (e.g. launcher, notification-center)",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=shellctl.DEFAULT_PROFILE,
    )
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Extra arguments forwarded to the panel entrypoint",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    extra = list(args.extra)
    if extra and extra[0] == "--":
        extra = extra[1:]
    return launch_component_gtk(
        component=args.component,
        profile_path=args.profile,
        interval=args.interval,
        duration=args.duration,
        extra_args=extra or None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
