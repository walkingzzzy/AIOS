#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


RUNTIME_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = RUNTIME_ROOT.parent
for candidate in (SHELL_ROOT, RUNTIME_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import shellctl
from panel_actions import (
    clip_text,
    dispatch_panel_action,
    process_error_text,
    summarize_action_result,
)
from shell_snapshot import build_snapshot, render_panel_text, write_outputs


def next_surface_from_action_result(current_surface: str, result: dict[str, Any]) -> str:
    target_component = result.get("target_component")
    if isinstance(target_component, str) and target_component.strip():
        return target_component.strip()
    return current_surface


def require_gtk_runtime():
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, GLib, Gtk
    except Exception as error:  # pragma: no cover
        raise SystemExit(
            "GTK host unavailable: install PyGObject with GTK4 and libadwaita typelibs "
            f"(import failed: {error})"
        )
    return Adw, GLib, Gtk


def run_gtk_gui(profile: dict[str, Any], args) -> int:
    Adw, GLib, Gtk = require_gtk_runtime()

    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("GUI display unavailable; use snapshot/text mode or provide DISPLAY/WAYLAND_DISPLAY")

    class ShellDesktopGtkApp(Adw.Application):
        def __init__(self) -> None:
            super().__init__(application_id="aios.shell.desktop", flags=0)
            self.window = None
            self.summary_label = None
            self.artifact_label = None
            self.surface_list = None
            self.detail_box = None
            self.action_box = None
            self.section_box = None
            self.current_snapshot: dict[str, Any] = {}
            self.selected_surface = "overview"
            self.rows: dict[str, Any] = {}
            self.row_names: dict[Any, str] = {}
            self.toast_overlay = None

        def do_activate(self) -> None:  # pragma: no cover
            if self.window is None:
                self.window = Adw.ApplicationWindow(application=self)
                self.window.set_title("AIOS Shell Desktop")
                self.window.set_default_size(1280, 860)

                self.toast_overlay = Adw.ToastOverlay()
                root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
                root.set_margin_top(16)
                root.set_margin_bottom(16)
                root.set_margin_start(16)
                root.set_margin_end(16)

                header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                title = Gtk.Label(label="AIOS Shell Desktop")
                title.set_xalign(0.0)
                title.add_css_class("title-1")
                self.summary_label = Gtk.Label(label="loading")
                self.summary_label.set_xalign(0.0)
                self.artifact_label = Gtk.Label(label="")
                self.artifact_label.set_xalign(0.0)
                header_box.append(title)
                header_box.append(self.summary_label)
                header_box.append(self.artifact_label)

                button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                refresh_button = Gtk.Button(label="Refresh")
                refresh_button.connect("clicked", lambda *_args: self.refresh())
                save_button = Gtk.Button(label="Save Snapshot")
                save_button.connect("clicked", lambda *_args: self.save_now())
                close_button = Gtk.Button(label="Close")
                close_button.connect("clicked", lambda *_args: self.quit())
                button_row.append(refresh_button)
                button_row.append(save_button)
                button_row.append(close_button)

                body = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
                body.set_wide_handle(True)
                body.set_position(320)

                self.surface_list = Gtk.ListBox()
                self.surface_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
                self.surface_list.connect("row-selected", self.on_row_selected)
                left_scroll = Gtk.ScrolledWindow()
                left_scroll.set_child(self.surface_list)
                left_scroll.set_min_content_width(280)

                detail_scroll = Gtk.ScrolledWindow()
                self.detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
                self.detail_box.set_margin_top(8)
                self.detail_box.set_margin_bottom(8)
                self.detail_box.set_margin_start(8)
                self.detail_box.set_margin_end(8)
                detail_scroll.set_child(self.detail_box)

                body.set_start_child(left_scroll)
                body.set_end_child(detail_scroll)

                root.append(header_box)
                root.append(button_row)
                root.append(body)
                self.toast_overlay.set_child(root)
                self.window.set_content(self.toast_overlay)

            self.window.present()
            self.refresh()
            GLib.timeout_add(max(500, int(args.interval * 1000)), self.on_timeout)
            if args.duration > 0:
                GLib.timeout_add(int(args.duration * 1000), self.on_duration_complete)

        def on_duration_complete(self) -> bool:
            self.quit()
            return False

        def on_timeout(self) -> bool:
            self.refresh()
            return True

        def toast(self, message: str) -> None:
            toast = Adw.Toast.new(message)
            self.toast_overlay.add_toast(toast)

        def clear_box(self, box) -> None:
            while True:
                child = box.get_first_child()
                if child is None:
                    break
                box.remove(child)

        def rebuild_surface_list(self, snapshot: dict[str, Any]) -> None:
            self.rows = {}
            self.row_names = {}
            self.clear_box(self.surface_list)

            stack_order = snapshot.get("summary", {}).get("stack_order", [])
            surfaces = list(snapshot.get("surfaces", []))
            surfaces.sort(
                key=lambda surface: (
                    stack_order.index(surface["component"])
                    if surface["component"] in stack_order
                    else len(stack_order)
                )
            )
            names = ["overview", *[surface["component"] for surface in surfaces]]
            for name in names:
                row = Gtk.ListBoxRow()
                row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row_box.set_margin_top(8)
                row_box.set_margin_bottom(8)
                row_box.set_margin_start(8)
                row_box.set_margin_end(8)
                title = Gtk.Label(label=name)
                title.set_xalign(0.0)
                title.add_css_class("heading")
                row_box.append(title)
                row.set_child(row_box)
                self.rows[name] = row
                self.row_names[row] = name
                self.surface_list.append(row)

            if self.selected_surface not in self.rows:
                self.selected_surface = "overview"
            self.surface_list.select_row(self.rows[self.selected_surface])

        def on_row_selected(self, _listbox, row) -> None:
            if row is None:
                return
            self.selected_surface = self.row_names.get(row, "overview")
            self.render_selected_surface()

        def refresh(self) -> None:
            snapshot = build_snapshot(profile, args)
            self.current_snapshot = snapshot
            artifacts = write_outputs(snapshot, args)
            self.rebuild_surface_list(snapshot)

            summary = snapshot.get("summary", {})
            self.summary_label.set_label(
                f"visible={summary.get('visible_surface_count', snapshot['surface_count'])} "
                f"total={summary.get('total_surface_count', 0)} "
                f"skipped={summary.get('skipped_count', 0)} "
                f"errors={summary.get('error_count', 0)}"
            )
            if artifacts:
                self.artifact_label.set_label(
                    "artifacts: " + ", ".join(f"{key}={value}" for key, value in artifacts.items())
                )
            else:
                self.artifact_label.set_label("")
            self.render_selected_surface()

        def render_selected_surface(self) -> None:
            self.clear_box(self.detail_box)

            if self.selected_surface == "overview":
                overview = Gtk.TextView()
                overview.set_editable(False)
                overview.set_cursor_visible(False)
                overview.get_buffer().set_text(render_panel_text(
                    {
                        "header": {"title": "Overview", "status": "ready", "subtitle": "Resolved shell session"},
                        "sections": [
                            {
                                "title": "Snapshot",
                                "items": [
                                    {"label": "profile_id", "value": self.current_snapshot.get("profile_id")},
                                    {"label": "generated_at", "value": self.current_snapshot.get("generated_at")},
                                    {"label": "surface_count", "value": self.current_snapshot.get("surface_count", 0)},
                                    {
                                        "label": "active_modal_surface",
                                        "value": self.current_snapshot.get("summary", {}).get("active_modal_surface") or "-",
                                    },
                                    {
                                        "label": "primary_attention_surface",
                                        "value": self.current_snapshot.get("summary", {}).get("primary_attention_surface") or "-",
                                    },
                                    {
                                        "label": "stack_order",
                                        "value": " > ".join(self.current_snapshot.get("summary", {}).get("stack_order", [])) or "-",
                                    },
                                ],
                            }
                        ],
                    }
                ))
                self.detail_box.append(overview)
                return

            surface = next(
                (item for item in self.current_snapshot.get("surfaces", []) if item["component"] == self.selected_surface),
                None,
            )
            if surface is None:
                self.detail_box.append(Gtk.Label(label="Surface missing"))
                return

            model = surface.get("model") or {}
            header = model.get("header", {})

            title = Gtk.Label(label=f"{header.get('title', surface['component'])} [{header.get('status', 'unknown')}]")
            title.set_xalign(0.0)
            title.add_css_class("title-2")
            subtitle = Gtk.Label(label=header.get("subtitle", ""))
            subtitle.set_xalign(0.0)
            subtitle.set_wrap(True)
            badges = Gtk.Label(
                label=" | ".join(
                    f"{item.get('label')}: {item.get('value')}" for item in model.get("badges", [])
                )
            )
            badges.set_xalign(0.0)
            badges.set_wrap(True)
            policy = Gtk.Label(
                label=(
                    f"role={surface.get('shell_role', '-')}"
                    f" focus={surface.get('focus_policy', '-')}"
                    f" interaction={surface.get('interaction_mode', '-')}"
                    f" stack_rank={surface.get('stack_rank', '-')}"
                ),
            )
            policy.set_xalign(0.0)
            policy.set_wrap(True)
            blocked_by = surface.get("blocked_by")
            if blocked_by:
                policy.set_label(policy.get_label() + f" blocked_by={blocked_by}")

            self.detail_box.append(title)
            self.detail_box.append(subtitle)
            self.detail_box.append(badges)
            self.detail_box.append(policy)

            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            for action in model.get("actions", []):
                button = Gtk.Button(label=action.get("label", action.get("action_id", "action")))
                button.set_sensitive(bool(action.get("enabled", True)))
                button.connect("clicked", self.on_action_clicked, action)
                actions.append(button)
            self.detail_box.append(actions)

            for section in model.get("sections", []):
                frame = Gtk.Frame(label=section.get("title", section.get("section_id", "section")))
                body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                body.set_margin_top(8)
                body.set_margin_bottom(8)
                body.set_margin_start(8)
                body.set_margin_end(8)
                items = section.get("items", [])
                if items:
                    for item in items:
                        label = item.get("label") or item.get("approval_ref") or item.get("task_id") or "-"
                        status = item.get("status")
                        if item.get("value") not in (None, ""):
                            text = f"{label}: {item.get('value')}"
                            if status not in (None, ""):
                                text += f" [{status}]"
                        elif status:
                            text = f"{label}: {status}"
                        else:
                            text = label

                        row_action = item.get("action") if isinstance(item.get("action"), dict) else None
                        if row_action:
                            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                            row_label = Gtk.Label(label=text)
                            row_label.set_xalign(0.0)
                            row_label.set_wrap(True)
                            row_label.set_hexpand(True)
                            row_action_button = Gtk.Button(
                                label=row_action.get("label", row_action.get("action_id", "action"))
                            )
                            row_action_button.set_sensitive(bool(row_action.get("enabled", True)))
                            row_action_button.connect("clicked", self.on_action_clicked, row_action)
                            row_box.append(row_label)
                            row_box.append(row_action_button)
                            body.append(row_box)
                            continue

                        row_label = Gtk.Label(label=text)
                        row_label.set_xalign(0.0)
                        row_label.set_wrap(True)
                        body.append(row_label)
                else:
                    empty = Gtk.Label(label=section.get("empty_state", "No items"))
                    empty.set_xalign(0.0)
                    empty.set_wrap(True)
                    body.append(empty)
                frame.set_child(body)
                self.detail_box.append(frame)

            if surface.get("error"):
                error_label = Gtk.Label(label=surface["error"])
                error_label.set_xalign(0.0)
                error_label.set_wrap(True)
                self.detail_box.append(error_label)

        def on_action_clicked(self, _button, action: dict[str, Any]) -> None:
            label = action.get("label", action.get("action_id", "action"))
            try:
                payload = dispatch_panel_action(profile, args, self.current_snapshot, self.selected_surface, action)
            except subprocess.CalledProcessError as error:
                self.toast(f"{label} failed: {clip_text(process_error_text(error))}")
                return
            except Exception as error:
                self.toast(f"{label} failed: {clip_text(str(error))}")
                return

            next_surface = next_surface_from_action_result(self.selected_surface, payload["result"])
            self.toast(summarize_action_result(self.selected_surface, action, payload["result"]))
            self.selected_surface = next_surface
            self.refresh()

        def save_now(self) -> None:
            if not self.current_snapshot:
                return
            if args.output_prefix is None:
                self.toast("Set --output-prefix to persist the current snapshot")
                return
            artifacts = write_outputs(self.current_snapshot, args)
            if artifacts:
                self.artifact_label.set_label(
                    "artifacts: " + ", ".join(f"{key}={value}" for key, value in artifacts.items())
                )
                self.toast("Snapshot exported")

    app = ShellDesktopGtkApp()
    return app.run([])
