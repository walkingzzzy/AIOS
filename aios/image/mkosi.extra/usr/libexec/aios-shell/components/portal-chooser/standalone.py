#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from panel import (
    build_model,
    default_sessiond_socket,
    list_handles_with_request,
    perform_action,
    render_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS portal chooser standalone host")
    parser.add_argument("command", nargs="?", default="snapshot", choices=["snapshot", "serve", "action", "export"])
    parser.add_argument("--socket", type=Path, default=default_sessiond_socket())
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--handle-fixture", type=Path)
    parser.add_argument("--policy-socket", type=Path)
    parser.add_argument("--deviced-socket", type=Path)
    parser.add_argument("--screen-provider-socket", type=Path)
    parser.add_argument("--action")
    parser.add_argument("--handle-id")
    parser.add_argument("--reason")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--output-prefix", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_state(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    handles, request = list_handles_with_request(args.socket, args.session_id, args.handle_fixture)
    model = build_model(handles, args.session_id, request)
    return handles, request, model


def snapshot_payload(args: argparse.Namespace) -> dict[str, Any]:
    _handles, _request, model = load_state(args)
    return {
        "window_title": model.get("header", {}).get("title", "Portal Chooser"),
        "selected_handle_id": model.get("meta", {}).get("detail_handle_id"),
        "detail_handle_id": model.get("meta", {}).get("detail_handle_id"),
        "status": model.get("header", {}).get("status"),
        "model": model,
        "rendered_text": render_text(model),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def export_manifest(payload: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
    model = payload.get("model") or {}
    meta = model.get("meta") or {}
    header = model.get("header") or {}
    return {
        "suite": "portal-chooser-export",
        "generated_at": utc_now(),
        "artifacts": artifacts,
        "summary": {
            "title": header.get("title"),
            "status": header.get("status"),
            "chooser_id": meta.get("chooser_id"),
            "session_id": meta.get("session_id"),
            "handle_count": meta.get("handle_count"),
            "matching_handle_count": meta.get("matching_handle_count"),
            "selectable_handle_count": meta.get("selectable_handle_count"),
            "unavailable_handle_count": meta.get("unavailable_handle_count"),
            "selected_handle_id": meta.get("selected_handle_id"),
            "confirmed_handle_id": meta.get("confirmed_handle_id"),
            "detail_handle_id": meta.get("detail_handle_id"),
            "approval_route_required": meta.get("approval_route_required"),
            "history_count": meta.get("history_count"),
        },
    }


def write_outputs(payload: dict[str, Any], output_prefix: Path | None) -> dict[str, str]:
    if output_prefix is None:
        return {}

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    text_path = output_prefix.with_suffix(".txt")
    manifest_path = output_prefix.with_suffix(".manifest.json")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    text_path.write_text(payload.get("rendered_text", "") + "\n")
    artifacts = {
        "json": str(json_path),
        "text": str(text_path),
    }
    manifest_path.write_text(json.dumps(export_manifest(payload, artifacts), indent=2, ensure_ascii=False) + "\n")
    return {
        **artifacts,
        "manifest": str(manifest_path),
    }


def run_tk_gui(args: argparse.Namespace) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as error:  # pragma: no cover
        raise SystemExit(f"tkinter unavailable: {error}")

    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("GUI display unavailable; use snapshot mode or provide DISPLAY/WAYLAND_DISPLAY")

    root = tk.Tk()
    root.geometry("1120x760")
    root.title("AIOS Portal Chooser")

    header_var = tk.StringVar(value="AIOS Portal Chooser")
    subtitle_var = tk.StringVar(value="loading")
    status_var = tk.StringVar(value="")
    message_var = tk.StringVar(value="")

    top = ttk.Frame(root, padding=12)
    top.pack(fill="x")
    ttk.Label(top, textvariable=header_var, font=("Helvetica", 18, "bold")).pack(anchor="w")
    ttk.Label(top, textvariable=subtitle_var).pack(anchor="w", pady=(4, 0))
    ttk.Label(top, textvariable=status_var).pack(anchor="w", pady=(2, 0))
    ttk.Label(top, textvariable=message_var, foreground="#1f4b99").pack(anchor="w", pady=(2, 0))

    controls = ttk.Frame(top)
    controls.pack(anchor="e", pady=(8, 0))

    body = ttk.Panedwindow(root, orient="horizontal")
    body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    left = ttk.Frame(body, padding=(0, 0, 8, 0))
    right = ttk.Frame(body)
    body.add(left, weight=2)
    body.add(right, weight=3)

    ttk.Label(left, text="Available Handles").pack(anchor="w")
    handle_list = tk.Listbox(left, exportselection=False, activestyle="dotbox")
    handle_scroll = ttk.Scrollbar(left, orient="vertical", command=handle_list.yview)
    handle_list.configure(yscrollcommand=handle_scroll.set)
    handle_list.pack(side="left", fill="both", expand=True, pady=(6, 0))
    handle_scroll.pack(side="left", fill="y", pady=(6, 0))

    detail_canvas = tk.Canvas(right, highlightthickness=0)
    detail_scroll = ttk.Scrollbar(right, orient="vertical", command=detail_canvas.yview)
    detail_container = ttk.Frame(detail_canvas, padding=(0, 0, 8, 8))
    detail_window = detail_canvas.create_window((0, 0), window=detail_container, anchor="nw")
    detail_canvas.configure(yscrollcommand=detail_scroll.set)
    detail_canvas.pack(side="left", fill="both", expand=True)
    detail_scroll.pack(side="left", fill="y")

    detail_container.bind(
        "<Configure>",
        lambda _event: detail_canvas.configure(scrollregion=detail_canvas.bbox("all")),
    )
    detail_canvas.bind(
        "<Configure>",
        lambda event: detail_canvas.itemconfigure(detail_window, width=event.width),
    )

    current_model: dict[str, Any] = {}
    current_handle_items: list[dict[str, Any]] = []
    current_handle_id: str | None = None
    refresh_job: str | None = None

    def set_message(message: str) -> None:
        message_var.set(message)

    def schedule_refresh() -> None:
        nonlocal refresh_job
        if refresh_job is not None:
            root.after_cancel(refresh_job)
        refresh_job = root.after(max(500, int(args.interval * 1000)), refresh)

    def clear_box(box: ttk.Frame) -> None:
        for child in box.winfo_children():
            child.destroy()

    def selected_handle_item() -> dict[str, Any] | None:
        if current_handle_id is None:
            return None
        return next((item for item in current_handle_items if item.get("handle_id") == current_handle_id), None)

    def show_value_section(title: str, items: list[dict[str, Any]], empty_state: str) -> None:
        frame = ttk.LabelFrame(detail_container, text=title, padding=10)
        frame.pack(fill="x", pady=(0, 12))
        if not items:
            ttk.Label(frame, text=empty_state, justify="left", anchor="w", wraplength=720).pack(fill="x")
            return
        for item in items:
            text = item.get("label", "-")
            value = item.get("value")
            status = item.get("status")
            if value not in (None, ""):
                text = f"{text}: {value}"
            if status not in (None, ""):
                text = f"{text} [{status}]"
            ttk.Label(frame, text=text, justify="left", anchor="w", wraplength=720).pack(fill="x", pady=1)

    def populate_handle_list() -> None:
        nonlocal current_handle_id
        handle_list.delete(0, "end")
        for item in current_handle_items:
            row = f"{item.get('label', '-')} ({item.get('kind', 'Unknown')}) [{item.get('status', 'available')}]"
            handle_list.insert("end", row)
        if current_handle_id is None:
            current_handle_id = current_model.get("meta", {}).get("detail_handle_id")
        if current_handle_items:
            selected_index = next(
                (index for index, item in enumerate(current_handle_items) if item.get("handle_id") == current_handle_id),
                0,
            )
            current_handle_id = current_handle_items[selected_index].get("handle_id")
            handle_list.selection_clear(0, "end")
            handle_list.selection_set(selected_index)
            handle_list.activate(selected_index)
        else:
            current_handle_id = None

    def render_details() -> None:
        clear_box(detail_container)
        header = current_model.get("header", {})
        sections = {
            section.get("section_id"): section
            for section in current_model.get("sections", [])
            if isinstance(section, dict)
        }
        ttk.Label(
            detail_container,
            text=f"{header.get('title', 'Portal Chooser')} [{header.get('status', 'unknown')}]",
            font=("Helvetica", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            detail_container,
            text=header.get("subtitle", "-"),
            justify="left",
            anchor="w",
            wraplength=760,
        ).pack(fill="x", pady=(4, 10))

        handle_item = selected_handle_item()
        selection_items = sections.get("selection-details", {}).get("items", [])
        if handle_item is not None:
            show_value_section(
                "Highlighted Handle",
                [
                    {"label": "Label", "value": handle_item.get("label")},
                    {"label": "Kind", "value": handle_item.get("kind")},
                    {"label": "State", "value": handle_item.get("status")},
                    {"label": "Target", "value": handle_item.get("value")},
                ],
                "No highlighted handle",
            )
        show_value_section(
            "Request",
            sections.get("request", {}).get("items", []),
            "No chooser request metadata",
        )
        show_value_section("Selection Details", selection_items, "No selection details")
        show_value_section(
            "Recent Events",
            sections.get("history", {}).get("items", []),
            "No chooser events recorded yet",
        )
        badges = current_model.get("badges", [])
        if badges:
            show_value_section(
                "Summary",
                [{"label": badge.get("label"), "value": badge.get("value")} for badge in badges],
                "No summary badges",
            )

    def on_handle_selected(_event=None) -> None:
        nonlocal current_handle_id
        if not handle_list.curselection():
            return
        index = int(handle_list.curselection()[0])
        if index < 0 or index >= len(current_handle_items):
            return
        current_handle_id = current_handle_items[index].get("handle_id")
        render_details()

    def run_action(action_id: str, *, handle_id: str | None = None) -> None:
        nonlocal current_handle_id
        result = perform_action(
            args.socket,
            args.session_id,
            args.handle_fixture,
            action_id,
            handle_id,
            args.reason,
        )
        target = result.get("target_component")
        suffix = f" -> {target}" if target else ""
        set_message(f"{action_id}: {result.get('status', 'unknown')}{suffix}")
        current_handle_id = result.get("confirmed_handle_id") or result.get("selected_handle_id") or current_handle_id
        refresh()

    def refresh() -> None:
        nonlocal current_model, current_handle_items, current_handle_id
        _handles, _request, current_model = load_state(args)
        current_handle_items = [
            item
            for section in current_model.get("sections", [])
            if section.get("section_id") == "handles"
            for item in section.get("items", [])
        ]
        header = current_model.get("header", {})
        header_var.set(header.get("title", "AIOS Portal Chooser"))
        subtitle_var.set(header.get("subtitle", "-"))
        status_var.set(
            f"status={header.get('status', 'unknown')} selected={current_model.get('meta', {}).get('selected_handle_id') or '-'} confirmed={current_model.get('meta', {}).get('confirmed_handle_id') or '-'}"
        )

        action_row = controls.winfo_children()
        for child in action_row:
            child.destroy()
        ttk.Button(controls, text="Refresh", command=refresh).pack(side="left")
        ttk.Button(
            controls,
            text="Select Highlighted",
            command=lambda: run_action("select-handle", handle_id=current_handle_id),
        ).pack(side="left", padx=(8, 0))
        for action in current_model.get("actions", []):
            button = ttk.Button(
                controls,
                text=action.get("label", action.get("action_id", "action")),
                command=lambda action_id=action.get("action_id"): run_action(
                    action_id,
                    handle_id=current_handle_id if action_id == "confirm-selection" else None,
                ),
            )
            if not action.get("enabled", True):
                button.state(["disabled"])
            button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Close", command=root.destroy).pack(side="left", padx=(8, 0))

        populate_handle_list()
        render_details()
        schedule_refresh()

    handle_list.bind("<<ListboxSelect>>", on_handle_selected)
    handle_list.bind("<Double-Button-1>", lambda _event: run_action("select-handle", handle_id=current_handle_id))
    refresh()
    if args.duration > 0:
        root.after(int(args.duration * 1000), root.destroy)
    root.mainloop()
    return 0


def main() -> int:
    args = parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        result = perform_action(
            args.socket,
            args.session_id,
            args.handle_fixture,
            args.action,
            args.handle_id,
            args.reason,
            task_id=args.task_id,
            user_id=args.user_id,
            policy_socket=args.policy_socket or Path("/run/aios/policyd/policyd.sock"),
            deviced_socket=args.deviced_socket or Path("/run/aios/deviced/deviced.sock"),
            screen_provider_socket=args.screen_provider_socket or Path("/run/aios/screen-provider/screen-capture-provider.sock"),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "serve":
        return run_tk_gui(args)

    payload = snapshot_payload(args)
    if args.command == "export":
        artifacts = write_outputs(payload, args.output_prefix)
        result = {
            "snapshot": payload,
            "artifacts": artifacts,
        }
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(payload["rendered_text"])
            if artifacts:
                print("")
                print("artifacts:")
                for key, value in artifacts.items():
                    print(f"- {key}: {value}")
        return 0

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload["rendered_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
