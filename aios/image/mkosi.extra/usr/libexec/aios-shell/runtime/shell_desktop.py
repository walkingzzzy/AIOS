#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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
from shell_profile import add_runtime_selection_arguments, build_session_plan
from shell_snapshot import (
    OVERVIEW_TAB,
    add_snapshot_arguments,
    build_snapshot,
    render_overview,
    render_snapshot,
    write_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS shell desktop host")
    parser.add_argument("command", nargs="?", default="snapshot", choices=["snapshot", "serve", "text", "export"])
    add_snapshot_arguments(parser)
    add_runtime_selection_arguments(parser)
    return parser.parse_args()


def next_surface_from_action_result(current_surface: str, result: dict[str, Any]) -> str:
    target_component = result.get("target_component")
    if isinstance(target_component, str) and target_component.strip():
        return target_component.strip()
    return current_surface


def ordered_snapshot_surfaces(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    stack_order = snapshot.get("summary", {}).get("stack_order", [])
    surfaces = list(snapshot.get("surfaces", []))
    surfaces.sort(
        key=lambda surface: (
            stack_order.index(surface["component"])
            if surface["component"] in stack_order
            else len(stack_order)
        )
    )
    return surfaces


def find_snapshot_surface(snapshot: dict[str, Any], component: str) -> dict[str, Any] | None:
    return next(
        (item for item in snapshot.get("surfaces", []) if item.get("component") == component),
        None,
    )


def run_tk_gui(profile: dict[str, Any], args: argparse.Namespace) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as error:  # pragma: no cover
        raise SystemExit(f"tkinter unavailable: {error}")

    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("GUI display unavailable; use snapshot/text mode or provide DISPLAY/WAYLAND_DISPLAY")

    root = tk.Tk()
    root.title("AIOS Shell Desktop")
    root.geometry("1280x860")

    header_var = tk.StringVar(value="AIOS Shell Desktop")
    summary_var = tk.StringVar(value="loading")
    artifact_var = tk.StringVar(value="")
    message_var = tk.StringVar(value="")

    top = ttk.Frame(root, padding=12)
    top.pack(fill="x")
    ttk.Label(top, textvariable=header_var, font=("Helvetica", 18, "bold")).pack(anchor="w")
    ttk.Label(top, textvariable=summary_var).pack(anchor="w", pady=(4, 0))
    ttk.Label(top, textvariable=artifact_var).pack(anchor="w", pady=(2, 0))
    ttk.Label(top, textvariable=message_var, foreground="#1f4b99").pack(anchor="w", pady=(2, 0))

    body = ttk.Panedwindow(root, orient="horizontal")
    body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    left = ttk.Frame(body, padding=(0, 0, 8, 0))
    right = ttk.Frame(body)
    body.add(left, weight=1)
    body.add(right, weight=4)

    ttk.Label(left, text="Surfaces").pack(anchor="w")
    surface_list = tk.Listbox(left, exportselection=False, activestyle="dotbox")
    surface_scroll = ttk.Scrollbar(left, orient="vertical", command=surface_list.yview)
    surface_list.configure(yscrollcommand=surface_scroll.set)
    surface_list.pack(side="left", fill="both", expand=True, pady=(6, 0))
    surface_scroll.pack(side="left", fill="y", pady=(6, 0))

    detail_canvas = tk.Canvas(right, highlightthickness=0)
    detail_scroll = ttk.Scrollbar(right, orient="vertical", command=detail_canvas.yview)
    detail_container = ttk.Frame(detail_canvas, padding=(0, 0, 8, 8))
    detail_window = detail_canvas.create_window((0, 0), window=detail_container, anchor="nw")
    detail_canvas.configure(yscrollcommand=detail_scroll.set)
    detail_canvas.pack(side="left", fill="both", expand=True)
    detail_scroll.pack(side="left", fill="y")

    def on_detail_container_configure(_event=None) -> None:
        detail_canvas.configure(scrollregion=detail_canvas.bbox("all"))

    def on_detail_canvas_configure(event) -> None:
        detail_canvas.itemconfigure(detail_window, width=event.width)

    detail_container.bind("<Configure>", on_detail_container_configure)
    detail_canvas.bind("<Configure>", on_detail_canvas_configure)

    current_snapshot: dict[str, Any] = {}
    ordered_names: list[str] = []
    selected_surface = OVERVIEW_TAB
    refresh_job: str | None = None

    def show_message(message: str) -> None:
        message_var.set(message)

    def clear_box(box: ttk.Frame) -> None:
        for child in box.winfo_children():
            child.destroy()

    def reset_detail_scroll() -> None:
        detail_canvas.yview_moveto(0.0)

    def schedule_refresh() -> None:
        nonlocal refresh_job
        if refresh_job is not None:
            root.after_cancel(refresh_job)
        refresh_job = root.after(max(500, int(args.interval * 1000)), refresh)

    def create_readonly_text(parent: ttk.Frame, content: str, height: int = 12) -> tk.Text:
        widget = tk.Text(parent, wrap="word", height=height, relief="flat", borderwidth=0)
        widget.insert("1.0", content)
        widget.configure(state="disabled")
        return widget

    def make_wrapped_label(parent: ttk.Frame, text: str, *, style: str | None = None) -> ttk.Label:
        label = ttk.Label(parent, text=text, justify="left", anchor="w", wraplength=820)
        if style:
            label.configure(style=style)
        label.pack(fill="x", anchor="w")
        return label

    def populate_surface_list() -> None:
        nonlocal ordered_names, selected_surface
        ordered_names = [OVERVIEW_TAB]
        ordered_names.extend(surface["component"] for surface in ordered_snapshot_surfaces(current_snapshot))
        surface_list.delete(0, "end")
        for name in ordered_names:
            surface_list.insert("end", name)
        if selected_surface not in ordered_names:
            selected_surface = OVERVIEW_TAB
        if selected_surface in ordered_names:
            index = ordered_names.index(selected_surface)
            surface_list.selection_clear(0, "end")
            surface_list.selection_set(index)
            surface_list.activate(index)

    def current_surface_model() -> dict[str, Any] | None:
        return find_snapshot_surface(current_snapshot, selected_surface)

    def render_overview_surface() -> None:
        title = ttk.Label(detail_container, text="Overview", font=("Helvetica", 16, "bold"))
        title.pack(anchor="w")
        make_wrapped_label(
            detail_container,
            "Resolved shell session snapshot, stack order, modal state, and artifact summary.",
        )
        overview = create_readonly_text(detail_container, render_overview(current_snapshot), height=18)
        overview.pack(fill="both", expand=True, pady=(10, 0))

    def render_surface_details(surface: dict[str, Any]) -> None:
        model = surface.get("model") or {}
        header = model.get("header", {})

        title = ttk.Label(
            detail_container,
            text=f"{header.get('title', surface['component'])} [{header.get('status', 'unknown')}]",
            font=("Helvetica", 16, "bold"),
        )
        title.pack(anchor="w")
        make_wrapped_label(detail_container, header.get("subtitle", "-"))

        badges = model.get("badges", [])
        if badges:
            make_wrapped_label(
                detail_container,
                " | ".join(f"{item.get('label')}: {item.get('value')}" for item in badges),
            )

        policy_parts = [
            f"role={surface.get('shell_role', '-')}",
            f"focus={surface.get('focus_policy', '-')}",
            f"interaction={surface.get('interaction_mode', '-')}",
            f"stack_rank={surface.get('stack_rank', '-')}",
        ]
        if surface.get("blocked_by"):
            policy_parts.append(f"blocked_by={surface['blocked_by']}")
        make_wrapped_label(detail_container, " ".join(policy_parts))

        actions = model.get("actions", [])
        if actions:
            action_row = ttk.Frame(detail_container)
            action_row.pack(fill="x", pady=(10, 0))
            for action in actions:
                button = ttk.Button(
                    action_row,
                    text=action.get("label", action.get("action_id", "action")),
                    command=lambda item=action: on_action_clicked(item, selected_surface),
                )
                if not action.get("enabled", True):
                    button.state(["disabled"])
                button.pack(side="left", padx=(0, 8))

        for section in model.get("sections", []):
            frame = ttk.LabelFrame(
                detail_container,
                text=section.get("title", section.get("section_id", "section")),
                padding=10,
            )
            frame.pack(fill="x", pady=(12, 0))

            items = section.get("items", [])
            if not items:
                make_wrapped_label(frame, section.get("empty_state", "No items"))
                continue

            for item in items:
                label = item.get("label") or item.get("approval_ref") or item.get("task_id") or "-"
                status = item.get("status")
                if item.get("value") not in (None, ""):
                    row_text = f"{label}: {item.get('value')}"
                    if status not in (None, ""):
                        row_text += f" [{status}]"
                elif status not in (None, ""):
                    row_text = f"{label}: {status}"
                else:
                    row_text = label

                row_action = item.get("action") if isinstance(item.get("action"), dict) else None
                if row_action:
                    row = ttk.Frame(frame)
                    row.pack(fill="x", pady=2)
                    row_label = ttk.Label(row, text=row_text, justify="left", anchor="w", wraplength=720)
                    row_label.pack(side="left", fill="x", expand=True)
                    button = ttk.Button(
                        row,
                        text=row_action.get("label", row_action.get("action_id", "action")),
                        command=lambda action=row_action: on_action_clicked(action, selected_surface),
                    )
                    if not row_action.get("enabled", True):
                        button.state(["disabled"])
                    button.pack(side="right", padx=(8, 0))
                else:
                    make_wrapped_label(frame, row_text)

        if surface.get("error"):
            frame = ttk.LabelFrame(detail_container, text="Error", padding=10)
            frame.pack(fill="x", pady=(12, 0))
            make_wrapped_label(frame, surface["error"])

    def render_selected_surface() -> None:
        clear_box(detail_container)
        if selected_surface == OVERVIEW_TAB:
            render_overview_surface()
        else:
            surface = current_surface_model()
            if surface is None:
                make_wrapped_label(detail_container, "Surface missing")
            else:
                render_surface_details(surface)
        on_detail_container_configure()
        reset_detail_scroll()

    def on_surface_selected(_event=None) -> None:
        nonlocal selected_surface
        if not surface_list.curselection():
            return
        index = int(surface_list.curselection()[0])
        if index < 0 or index >= len(ordered_names):
            return
        selected_surface = ordered_names[index]
        render_selected_surface()

    def on_action_clicked(action: dict[str, Any], component: str) -> None:
        nonlocal selected_surface
        label = action.get("label", action.get("action_id", "action"))
        try:
            payload = dispatch_panel_action(profile, args, current_snapshot, component, action)
        except Exception as error:
            if isinstance(error, SystemExit):  # pragma: no cover
                raise
            detail = process_error_text(error) if hasattr(error, "stderr") else str(error)
            show_message(f"{label} failed: {clip_text(detail)}")
            return

        next_surface = next_surface_from_action_result(component, payload["result"])
        show_message(summarize_action_result(component, action, payload["result"]))
        selected_surface = next_surface
        refresh()

    def refresh() -> None:
        nonlocal current_snapshot
        snapshot = build_snapshot(profile, args)
        current_snapshot = snapshot
        artifacts = write_outputs(snapshot, args)

        header_var.set(f"AIOS Shell Desktop [{snapshot['profile_id']}]")
        summary = snapshot.get("summary", {})
        summary_var.set(
            f"visible={summary.get('visible_surface_count', snapshot['surface_count'])} total={summary.get('total_surface_count', 0)} skipped={summary.get('skipped_count', 0)} errors={summary.get('error_count', 0)} generated_at={snapshot['generated_at']}"
        )
        if artifacts:
            artifact_var.set("artifacts: " + ", ".join(f"{key}={value}" for key, value in artifacts.items()))
        else:
            artifact_var.set("")
        populate_surface_list()
        render_selected_surface()
        schedule_refresh()

    def save_now() -> None:
        if not current_snapshot:
            return
        if args.output_prefix is None:
            artifact_var.set("artifacts: set --output-prefix to persist snapshot")
            return
        artifacts = write_outputs(current_snapshot, args)
        artifact_var.set("artifacts: " + ", ".join(f"{key}={value}" for key, value in artifacts.items()))
        show_message("Snapshot exported")

    controls = ttk.Frame(top)
    controls.pack(anchor="e", pady=(8, 0))
    ttk.Button(controls, text="Refresh Now", command=refresh).pack(side="left")
    ttk.Button(controls, text="Save Snapshot", command=save_now).pack(side="left", padx=(8, 0))
    ttk.Button(controls, text="Close", command=root.destroy).pack(side="left", padx=(8, 0))
    surface_list.bind("<<ListboxSelect>>", on_surface_selected)

    refresh()
    if args.duration > 0:
        root.after(int(args.duration * 1000), root.destroy)
    root.mainloop()
    return 0


def run_gtk_gui(profile: dict[str, Any], args: argparse.Namespace) -> int:
    from shell_desktop_gtk import run_gtk_gui as launch_gtk_host

    return launch_gtk_host(profile, args)


def main() -> int:
    args = parse_args()
    profile = shellctl.load_profile(args.profile)
    plan = build_session_plan(profile, args.profile, args)

    if args.command == "serve":
        if plan["session_backend"] == "compositor":
            raise SystemExit(
                "shell_desktop.py is the compatibility desktop host; use shell_session.py serve --session-backend compositor"
            )
        if plan["desktop_host"] == "gtk":
            return run_gtk_gui(profile, args)
        return run_tk_gui(profile, args)

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
