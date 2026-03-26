#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Callable

_GTK_AVAILABLE = False
_GTK_IMPORT_ERROR: str | None = None

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    _GTK_AVAILABLE = True
except Exception as _error:
    _GTK_IMPORT_ERROR = str(_error)
    Adw = None  # type: ignore[assignment]
    Gtk = None  # type: ignore[assignment]

TONE_CSS_CLASS: dict[str, str] = {
    "positive": "success",
    "warning": "warning",
    "critical": "error",
}

ActionCallback = Callable[[dict[str, Any]], None]


def gtk_available() -> bool:
    return _GTK_AVAILABLE


def require_gtk() -> tuple[Any, Any]:
    if not _GTK_AVAILABLE:
        raise RuntimeError(
            "GTK4 renderer unavailable: install PyGObject with GTK4 and libadwaita "
            f"typelibs (import failed: {_GTK_IMPORT_ERROR})"
        )
    return Adw, Gtk


def _apply_tone(widget, tone: str | None) -> None:
    css_class = TONE_CSS_CLASS.get(tone or "")
    if css_class:
        widget.add_css_class(css_class)


def _clear_box(box) -> None:
    while True:
        child = box.get_first_child()
        if child is None:
            break
        box.remove(child)


def _build_header(
    header: dict[str, Any],
    badges: list[dict[str, Any]],
) -> Any:
    _, Gtk = require_gtk()

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

    title_label = Gtk.Label(label=header.get("title", "Panel"))
    title_label.set_xalign(0.0)
    title_label.add_css_class("title-2")

    status = header.get("status", "unknown")
    tone = header.get("tone")
    status_label = Gtk.Label(label=f"[{status}]")
    status_label.set_xalign(0.0)
    _apply_tone(status_label, tone)

    title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    title_row.append(title_label)
    title_row.append(status_label)

    subtitle = header.get("subtitle", "")
    subtitle_label = Gtk.Label(label=subtitle)
    subtitle_label.set_xalign(0.0)
    subtitle_label.set_wrap(True)
    subtitle_label.add_css_class("dim-label")

    box.append(title_row)
    box.append(subtitle_label)

    if badges:
        badge_parts = []
        for badge in badges:
            badge_parts.append(f"{badge.get('label')}: {badge.get('value')}")
        badge_label = Gtk.Label(label=" | ".join(badge_parts))
        badge_label.set_xalign(0.0)
        badge_label.set_wrap(True)
        box.append(badge_label)

    return box


def _build_actions(
    actions: list[dict[str, Any]],
    callback: ActionCallback | None,
) -> Any:
    _, Gtk = require_gtk()

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_margin_top(4)
    box.set_margin_bottom(4)

    for action in actions:
        label = action.get("label", action.get("action_id", "action"))
        button = Gtk.Button(label=label)
        button.set_sensitive(bool(action.get("enabled", True)))

        tone = action.get("tone")
        if tone == "critical":
            button.add_css_class("destructive-action")
        elif tone == "positive":
            button.add_css_class("suggested-action")

        if callback is not None:
            button.connect("clicked", _on_action_clicked, action, callback)

        box.append(button)

    return box


def _on_action_clicked(
    _button,
    action: dict[str, Any],
    callback: ActionCallback,
) -> None:
    callback(action)


def _build_section_item_label(item: dict[str, Any]) -> str:
    label = (
        item.get("label")
        or item.get("approval_ref")
        or item.get("task_id")
        or "-"
    )
    value = item.get("value")
    status = item.get("status")

    if value not in (None, ""):
        text = f"{label}: {value}"
        if status not in (None, ""):
            text += f" [{status}]"
    elif status:
        text = f"{label}: {status}"
    else:
        text = str(label)
    return text


def _build_section(
    section: dict[str, Any],
    callback: ActionCallback | None,
) -> Any:
    Adw, Gtk = require_gtk()

    group = Adw.PreferencesGroup()
    group.set_title(section.get("title", section.get("section_id", "section")))

    items = section.get("items", [])
    if not items:
        empty_row = Adw.ActionRow()
        empty_row.set_title(section.get("empty_state", "No items"))
        empty_row.add_css_class("dim-label")
        group.add(empty_row)
        return group

    for item in items:
        row_action = item.get("action") if isinstance(item.get("action"), dict) else None
        text = _build_section_item_label(item)
        tone = item.get("tone")

        row = Adw.ActionRow()
        row.set_title(text)
        _apply_tone(row, tone)

        if row_action and callback is not None:
            action_label = row_action.get(
                "label", row_action.get("action_id", "action")
            )
            action_button = Gtk.Button(label=action_label)
            action_button.set_valign(Gtk.Align.CENTER)
            action_button.set_sensitive(bool(row_action.get("enabled", True)))
            action_button.connect(
                "clicked", _on_action_clicked, row_action, callback
            )
            row.add_suffix(action_button)
            row.set_activatable_widget(action_button)

        group.add(row)

    return group


def render_panel_model_to_gtk(
    model: dict[str, Any],
    action_callback: ActionCallback | None = None,
) -> Any:
    """Build a GTK widget tree from a standard panel model dict.

    Returns a Gtk.Box containing the fully rendered panel.  The caller owns
    the returned widget and may embed it in any container.

    ``action_callback``, when provided, is invoked with the action dict
    whenever the user clicks an action button (top-level or per-item).
    """
    _, Gtk = require_gtk()

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    root.set_margin_top(12)
    root.set_margin_bottom(12)
    root.set_margin_start(12)
    root.set_margin_end(12)

    header = model.get("header") or {}
    badges = list(model.get("badges", []))
    actions = list(model.get("actions", []))
    sections = list(model.get("sections", []))

    root.append(_build_header(header, badges))

    if actions:
        root.append(_build_actions(actions, action_callback))

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_hexpand(True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

    section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    section_box.set_margin_top(4)
    for section in sections:
        section_box.append(_build_section(section, action_callback))
    scrolled.set_child(section_box)
    root.append(scrolled)

    return root


def update_panel_widget(
    container: Any,
    model: dict[str, Any],
    action_callback: ActionCallback | None = None,
) -> None:
    """Replace the contents of *container* with a fresh render of *model*.

    This is the idiomatic way to refresh a panel that was previously built
    with ``render_panel_model_to_gtk``: pass the same parent box and the
    updated model.
    """
    _clear_box(container)
    new_tree = render_panel_model_to_gtk(model, action_callback=action_callback)

    child = new_tree.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        new_tree.remove(child)
        container.append(child)
        child = next_child
