#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SHELL_ROOT = Path(__file__).resolve().parent.parent
if str(SHELL_ROOT) not in sys.path:
    sys.path.insert(0, str(SHELL_ROOT))

import shellctl


SURFACE_ORDER = [
    "launcher",
    "task-surface",
    "system-assistant",
    "ai-center",
    "provider-settings",
    "privacy-memory",
    "model-library",
    "approval-panel",
    "portal-chooser",
    "notification-center",
    "recovery-surface",
    "capture-indicators",
    "remote-governance",
    "device-backend-status",
]
OVERVIEW_TAB = "overview"
SURFACE_ORDER_INDEX = {name: index for index, name in enumerate(SURFACE_ORDER)}
ROLE_BY_COMPONENT = {
    "launcher": "dock",
    "task-surface": "workspace",
    "system-assistant": "panel",
    "ai-center": "panel",
    "provider-settings": "panel",
    "privacy-memory": "panel",
    "model-library": "panel",
    "approval-panel": "modal",
    "portal-chooser": "modal",
    "recovery-surface": "modal",
    "notification-center": "overlay",
    "capture-indicators": "status-strip",
    "remote-governance": "status-card",
    "device-backend-status": "status-card",
}
BASE_STACK_RANK = {
    "launcher": 140,
    "task-surface": 120,
    "system-assistant": 210,
    "ai-center": 200,
    "provider-settings": 203,
    "privacy-memory": 204,
    "model-library": 205,
    "approval-panel": 280,
    "portal-chooser": 320,
    "recovery-surface": 340,
    "notification-center": 220,
    "capture-indicators": 360,
    "remote-governance": 170,
    "device-backend-status": 180,
}
MODAL_COMPONENTS = {"approval-panel", "portal-chooser", "recovery-surface"}
PASSIVE_COMPONENTS = {"capture-indicators"}
MODAL_FOCUS_PRIORITY = {
    "approval-panel": 240,
    "portal-chooser": 160,
    "recovery-surface": 120,
}
BLOCKING_MODAL_STATUSES = {
    "pending",
    "blocked",
    "failed",
    "recovery-required",
}
DEGRADED_MODAL_STATUSES = {
    "attention",
    "degraded",
    "error",
    "warning",
}


def default_profile() -> Path:
    return SHELL_ROOT / "profiles" / "default-shell-profile.yaml"


def parse_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_json_payload(path: Path | None) -> tuple[dict, str | None]:
    if path is None:
        return {}, None
    if not path.exists():
        return {}, f"missing:{path}"
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return {}, str(error)
    if isinstance(payload, dict):
        return payload, None
    return {}, f"invalid-json-object:{path}"


def derive_managed_windows(window_payload: dict, runtime_session: dict) -> list[dict[str, Any]]:
    managed_windows: list[dict[str, Any]] = []
    for entry in window_payload.get("windows", []):
        if not isinstance(entry, dict):
            continue
        workspace_index = parse_int(entry.get("workspace_index"), 0)
        rect = entry.get("rect") if isinstance(entry.get("rect"), dict) else {}
        minimized = bool(entry.get("minimized"))
        managed_windows.append(
            {
                "window_key": entry.get("window_key"),
                "title": entry.get("title"),
                "app_id": entry.get("app_id"),
                "output_id": entry.get("output_id") or runtime_session.get("active_output_id") or "display-1",
                "workspace_id": f"workspace-{workspace_index + 1}",
                "window_policy": entry.get("window_policy") or "workspace-window",
                "visible": not minimized,
                "minimized": minimized,
                "layout_x": parse_int(rect.get("x"), 0),
                "layout_y": parse_int(rect.get("y"), 0),
                "layout_width": parse_int(rect.get("width"), 0),
                "layout_height": parse_int(rect.get("height"), 0),
            }
        )
    return managed_windows


def derive_release_grade_output_status(outputs: list[dict[str, Any]], renderable_output_count: int) -> str:
    if not outputs:
        return "uninitialized"
    output_count = len(outputs)
    if output_count == 1:
        return f"single-output(renderable={renderable_output_count}/{output_count})"
    if renderable_output_count >= output_count:
        return f"multi-output(renderable={renderable_output_count}/{output_count})"
    return f"multi-output(partial-renderable={renderable_output_count}/{output_count})"


def load_compositor_window_manager(profile: dict) -> dict[str, Any]:
    compositor = profile.get("compositor", {}) or {}
    runtime_state_path = None
    if compositor.get("runtime_state_path"):
        runtime_state_path = Path(str(compositor["runtime_state_path"]))
    window_state_path = None
    if compositor.get("window_state_path"):
        window_state_path = Path(str(compositor["window_state_path"]))

    runtime_payload, runtime_error = load_json_payload(runtime_state_path)
    window_payload, window_error = load_json_payload(window_state_path)
    runtime_session = runtime_payload.get("session")
    if not isinstance(runtime_session, dict):
        runtime_session = runtime_payload if isinstance(runtime_payload, dict) else {}

    runtime_managed_windows = [
        item
        for item in runtime_session.get("managed_windows", [])
        if isinstance(item, dict)
    ]
    window_managed_windows = derive_managed_windows(window_payload, runtime_session)
    managed_windows = window_managed_windows or runtime_managed_windows

    derived_counts: dict[str, int] = {}
    for window in managed_windows:
        workspace_id = str(window.get("workspace_id") or "workspace-1")
        derived_counts[workspace_id] = derived_counts.get(workspace_id, 0) + 1
    workspace_window_counts = dict(sorted(derived_counts.items()))

    outputs = [
        item
        for item in runtime_session.get("outputs", [])
        if isinstance(item, dict)
    ]
    output_count = parse_int(runtime_session.get("output_count"), len(outputs))
    renderable_output_count = parse_int(
        runtime_session.get("renderable_output_count"),
        sum(1 for item in outputs if item.get("renderable")),
    )
    non_renderable_output_count = parse_int(
        runtime_session.get("non_renderable_output_count"),
        max(output_count - renderable_output_count, 0),
    )
    active_workspace_index = parse_int(window_payload.get("active_workspace_index"), 0)
    if window_payload.get("active_workspace_index") in (None, ""):
        active_workspace_index = parse_int(runtime_session.get("active_workspace_index"), 0)

    data_status = "ready" if runtime_payload or window_payload else "unavailable"
    errors = [error for error in (runtime_error, window_error) if error]
    if errors and data_status == "ready":
        data_status = "partial"

    return {
        "data_status": data_status,
        "data_error": "; ".join(errors) if errors else None,
        "runtime_phase": runtime_payload.get("phase"),
        "runtime_state_status": runtime_session.get("runtime_state_status"),
        "runtime_state_path": str(runtime_state_path) if runtime_state_path else None,
        "window_state_path": str(window_state_path) if window_state_path else None,
        "window_manager_status": runtime_session.get("window_manager_status"),
        "workspace_count": parse_int(runtime_session.get("workspace_count"), max(len(workspace_window_counts), 1)),
        "active_workspace_index": active_workspace_index,
        "active_workspace_id": f"workspace-{active_workspace_index + 1}",
        "active_output_id": window_payload.get("active_output_id") or runtime_session.get("active_output_id"),
        "output_count": output_count,
        "renderable_output_count": renderable_output_count,
        "non_renderable_output_count": non_renderable_output_count,
        "release_grade_output_status": runtime_session.get("release_grade_output_status")
        or derive_release_grade_output_status(outputs, renderable_output_count),
        "managed_window_count": len(managed_windows),
        "visible_window_count": sum(1 for item in managed_windows if item.get("visible")),
        "floating_window_count": sum(1 for item in managed_windows if item.get("window_policy") and "floating" in str(item.get("window_policy"))),
        "minimized_window_count": sum(1 for item in managed_windows if item.get("minimized")),
        "window_move_count": parse_int(runtime_session.get("window_move_count"), 0),
        "window_resize_count": parse_int(runtime_session.get("window_resize_count"), 0),
        "window_minimize_count": parse_int(runtime_session.get("window_minimize_count"), 0),
        "window_restore_count": parse_int(runtime_session.get("window_restore_count"), 0),
        "last_minimized_window_key": runtime_session.get("last_minimized_window_key"),
        "last_restored_window_key": runtime_session.get("last_restored_window_key"),
        "workspace_window_counts": workspace_window_counts,
        "managed_windows": managed_windows,
        "outputs": outputs,
    }


def add_snapshot_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", type=Path, default=default_profile())
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--intent", default="shell-desktop")
    parser.add_argument("--title")
    parser.add_argument("--task-state", default="planned")
    parser.add_argument("--task-state-filter")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--launcher-fixture", type=Path)
    parser.add_argument("--task-fixture", type=Path)
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--chooser-fixture", type=Path)
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--surface", action="append", dest="surfaces", help="Only include matching shell surface(s)")
    parser.add_argument("--status-filter", help="Only include surfaces with this header status")
    parser.add_argument("--tone-filter", help="Only include surfaces with this header tone")
    parser.add_argument("--output-prefix", type=Path, help="Write snapshot JSON/TXT artifacts using this prefix")
    parser.add_argument("--json", action="store_true")


def panel_context_args(args: argparse.Namespace, component: str) -> list[str] | None:
    command: list[str] = []
    if component == "launcher":
        if args.launcher_fixture is not None:
            command.extend(["--fixture", str(args.launcher_fixture)])
        if args.session_id:
            command.extend(["--session-id", args.session_id])
        command.extend(["--user-id", args.user_id, "--intent", args.intent, "--state", args.task_state])
        if args.title:
            command.extend(["--title", args.title])
        return command

    if component == "task-surface":
        if args.task_fixture is None and not args.session_id:
            return None
        if args.task_fixture is not None:
            command.extend(["--fixture", str(args.task_fixture)])
        if args.session_id:
            command.extend(["--session-id", args.session_id])
        if args.task_id:
            command.extend(["--task-id", args.task_id])
        if args.task_state_filter:
            command.extend(["--state", args.task_state_filter])
        if args.limit is not None:
            command.extend(["--limit", str(args.limit)])
        return command

    if component == "system-assistant":
        if args.launcher_fixture is not None:
            command.extend(["--fixture", str(args.launcher_fixture)])
        if args.task_fixture is not None:
            command.extend(["--task-fixture", str(args.task_fixture)])
        if args.approval_fixture is not None:
            command.extend(["--approval-fixture", str(args.approval_fixture)])
        if args.session_id:
            command.extend(["--session-id", args.session_id])
        if args.user_id:
            command.extend(["--user-id", args.user_id])
        if args.task_state:
            command.extend(["--task-state", args.task_state])
        return command

    if component == "ai-center":
        return command

    if component == "provider-settings":
        return command

    if component == "privacy-memory":
        return command

    if component == "model-library":
        return command

    if component == "approval-panel":
        if args.approval_fixture is not None:
            command.extend(["--fixture", str(args.approval_fixture)])
        if args.session_id:
            command.extend(["--session-id", args.session_id])
        if args.task_id:
            command.extend(["--task-id", args.task_id])
        return command

    if component == "portal-chooser":
        if args.chooser_fixture is None and not args.session_id:
            return None
        if args.chooser_fixture is not None:
            command.extend(["--handle-fixture", str(args.chooser_fixture)])
        if args.session_id:
            command.extend(["--session-id", args.session_id])
        if args.task_id:
            command.extend(["--task-id", args.task_id])
        if args.user_id:
            command.extend(["--user-id", args.user_id])
        return command

    if component == "notification-center":
        if args.approval_fixture is not None:
            command.extend(["--approval-fixture", str(args.approval_fixture)])
        return command

    if component in {
        "recovery-surface",
        "capture-indicators",
        "remote-governance",
        "device-backend-status",
    }:
        return command

    return None


def build_panel_args(args: argparse.Namespace, component: str) -> list[str] | None:
    context_args = panel_context_args(args, component)
    if context_args is None:
        return None
    return ["model", "--json", *context_args]


def enabled_components(profile: dict, include_disabled: bool) -> list[str]:
    enabled: list[str] = []
    for component in SURFACE_ORDER:
        if include_disabled or shellctl.component_enabled(profile, component):
            enabled.append(component)
    return enabled


def normalize_requested_surfaces(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        normalized.append(shellctl.normalize_component(value))
    return normalized


def component_order(component: str) -> int:
    return SURFACE_ORDER_INDEX.get(component, len(SURFACE_ORDER))


def shell_role(component: str) -> str:
    return ROLE_BY_COMPONENT.get(component, "panel")


def enabled_action_count(surface: dict[str, Any]) -> int:
    model = surface.get("model") or {}
    return len([item for item in model.get("actions", []) if item.get("enabled", True)])


def surface_is_attention(surface: dict[str, Any]) -> bool:
    if surface.get("error"):
        return True

    tone = (surface.get("tone") or "").strip().lower()
    if tone in {"warning", "critical"}:
        return True

    status = (surface.get("status") or "").strip().lower()
    return status in {
        "attention",
        "blocked",
        "degraded",
        "error",
        "failed",
        "pending",
        "recovery-required",
        "warning",
    }


def choose_active_modal_surface(surfaces: list[dict[str, Any]]) -> str | None:
    modal_surfaces = [surface for surface in surfaces if surface.get("component") in MODAL_COMPONENTS]
    if not modal_surfaces:
        return None

    def modal_focus_priority(surface: dict[str, Any]) -> int:
        component = surface.get("component", "")
        status = (surface.get("status") or "").strip().lower()
        priority = MODAL_FOCUS_PRIORITY.get(component, 0)
        if status in BLOCKING_MODAL_STATUSES:
            priority += 120
        elif status in DEGRADED_MODAL_STATUSES:
            priority += 60
        elif surface_is_attention(surface):
            priority += 24
        priority += min(enabled_action_count(surface), 3) * 4
        return priority

    ranked = sorted(
        modal_surfaces,
        key=lambda surface: (
            -modal_focus_priority(surface),
            component_order(surface.get("component", "")),
        ),
    )
    chosen = ranked[0]
    if surface_is_attention(chosen) or enabled_action_count(chosen) > 0:
        return chosen.get("component")
    return None


def choose_primary_attention_surface(surfaces: list[dict[str, Any]]) -> str | None:
    attention_surfaces = [surface for surface in surfaces if surface_is_attention(surface)]
    if not attention_surfaces:
        return None
    ranked = sorted(
        attention_surfaces,
        key=lambda surface: (
            1 if surface.get("component") in PASSIVE_COMPONENTS else 0,
            -(BASE_STACK_RANK.get(surface.get("component", ""), 100)),
            component_order(surface.get("component", "")),
        ),
    )
    return ranked[0].get("component")


def annotate_visible_surfaces(
    surfaces: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    active_modal_surface = choose_active_modal_surface(surfaces)
    primary_attention_surface = choose_primary_attention_surface(surfaces)
    annotated: list[dict[str, Any]] = []

    for surface in surfaces:
        component = surface.get("component", "")
        role = shell_role(component)
        stack_rank = BASE_STACK_RANK.get(component, 100)
        attention = surface_is_attention(surface)
        action_count = enabled_action_count(surface)

        if attention:
            stack_rank += 24
        if action_count:
            stack_rank += min(action_count, 3) * 4
        if component == active_modal_surface:
            stack_rank += 120
        elif component in MODAL_COMPONENTS:
            stack_rank += 24
        elif component == "notification-center":
            stack_rank += 16

        if component in PASSIVE_COMPONENTS:
            interaction_mode = "passive"
        elif component == active_modal_surface:
            interaction_mode = "modal"
        elif active_modal_surface and role in {"dock", "workspace", "overlay", "panel"}:
            interaction_mode = "blocked-by-modal"
        elif role == "workspace":
            interaction_mode = "workspace"
        else:
            interaction_mode = "interactive"

        blocked_by = None
        if interaction_mode == "blocked-by-modal":
            blocked_by = active_modal_surface

        annotated.append(
            {
                **surface,
                "shell_role": role,
                "focus_policy": (
                    "shell-modal"
                    if component in MODAL_COMPONENTS
                    else (
                        "workspace-target"
                        if component == "task-surface"
                        else (
                            "passive-overlay"
                            if component in PASSIVE_COMPONENTS
                            else "retain-client-focus"
                        )
                    )
                ),
                "interaction_mode": interaction_mode,
                "blocked_by": blocked_by,
                "stack_rank": stack_rank,
                "attention": attention,
                "enabled_action_count": action_count,
            }
        )

    stack_order = [
        surface.get("component", "")
        for surface in sorted(
            annotated,
            key=lambda surface: (-surface["stack_rank"], component_order(surface.get("component", ""))),
        )
    ]

    return annotated, {
        "active_modal_surface": active_modal_surface,
        "primary_attention_surface": primary_attention_surface,
        "stack_order": stack_order,
        "workspace_surface": "task-surface" if any(item.get("component") == "task-surface" for item in annotated) else None,
    }


def render_panel_text(panel: dict) -> str:
    header = panel.get("header", {})
    lines = [
        f"{header.get('title', panel.get('panel_id', 'panel'))} [{header.get('status', 'unknown')}]",
        header.get("subtitle", "-"),
    ]
    badges = panel.get("badges", [])
    if badges:
        lines.append("badges: " + ", ".join(f"{item.get('label')}: {item.get('value')}" for item in badges))
    actions = [item.get("label") for item in panel.get("actions", []) if item.get("enabled", True)]
    if actions:
        lines.append("actions: " + ", ".join(actions))
    for section in panel.get("sections", []):
        lines.append(f"[{section.get('title', section.get('section_id', 'section'))}]")
        items = section.get("items", [])
        if not items:
            lines.append(f"- {section.get('empty_state', 'No items')}")
            continue
        for item in items:
            if "value" in item and item.get("value") not in (None, ""):
                line = f"- {item.get('label', item.get('approval_ref', item.get('task_id', '-')))}: {item.get('value')}"
                if item.get("status") not in (None, ""):
                    line += f" [{item.get('status')}]"
                lines.append(line)
            elif "status" in item:
                lines.append(f"- {item.get('label', item.get('approval_ref', item.get('task_id', '-')))}: {item.get('status')}")
            else:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)


def apply_surface_filters(surfaces: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    requested_surfaces = set(normalize_requested_surfaces(args.surfaces))
    filtered: list[dict[str, Any]] = []
    for surface in surfaces:
        if requested_surfaces and surface["component"] not in requested_surfaces:
            continue
        if args.status_filter and surface.get("status") != args.status_filter:
            continue
        if args.tone_filter and surface.get("tone") != args.tone_filter:
            continue
        filtered.append(surface)
    return filtered


def build_summary(
    all_surfaces: list[dict[str, Any]],
    visible_surfaces: list[dict[str, Any]],
    skipped: list[dict[str, str]],
    args: argparse.Namespace,
    shell_layout: dict[str, Any],
    compositor_window_manager: dict[str, Any],
) -> dict[str, Any]:
    status_counts = Counter(surface.get("status", "unknown") for surface in visible_surfaces)
    tone_counts = Counter(surface.get("tone", "neutral") for surface in visible_surfaces)
    focus_policy_counts = Counter(surface.get("focus_policy", "unknown") for surface in visible_surfaces)
    interaction_mode_counts = Counter(surface.get("interaction_mode", "unknown") for surface in visible_surfaces)
    action_count = 0
    error_count = 0
    panel_ids: list[str] = []
    attention_components: list[str] = []
    blocked_components: list[str] = []
    component_roles: dict[str, str] = {}
    for surface in visible_surfaces:
        panel_ids.append(surface.get("panel_id") or surface["component"])
        component_roles[surface["component"]] = surface.get("shell_role", "panel")
        if surface.get("error"):
            error_count += 1
        if surface.get("attention"):
            attention_components.append(surface["component"])
        if surface.get("blocked_by"):
            blocked_components.append(surface["component"])
        model = surface.get("model") or {}
        actions = [item for item in model.get("actions", []) if item.get("enabled", True)]
        action_count += len(actions)

    requested_surfaces = normalize_requested_surfaces(args.surfaces)
    return {
        "total_surface_count": len(all_surfaces),
        "visible_surface_count": len(visible_surfaces),
        "skipped_count": len(skipped),
        "error_count": error_count,
        "action_count": action_count,
        "status_counts": dict(sorted(status_counts.items())),
        "tone_counts": dict(sorted(tone_counts.items())),
        "focus_policy_counts": dict(sorted(focus_policy_counts.items())),
        "interaction_mode_counts": dict(sorted(interaction_mode_counts.items())),
        "component_names": [surface["component"] for surface in visible_surfaces],
        "component_roles": component_roles,
        "panel_ids": panel_ids,
        "modal_surface_count": len([surface for surface in visible_surfaces if surface.get("component") in MODAL_COMPONENTS]),
        "attention_surface_count": len(attention_components),
        "blocked_surface_count": len(blocked_components),
        "attention_components": attention_components,
        "blocked_components": blocked_components,
        "active_modal_surface": shell_layout.get("active_modal_surface"),
        "primary_attention_surface": shell_layout.get("primary_attention_surface"),
        "workspace_surface": shell_layout.get("workspace_surface"),
        "stack_order": shell_layout.get("stack_order", []),
        "top_stack_surface": (shell_layout.get("stack_order") or [None])[0],
        "window_manager_status": compositor_window_manager.get("window_manager_status"),
        "compositor_data_status": compositor_window_manager.get("data_status"),
        "compositor_data_error": compositor_window_manager.get("data_error"),
        "runtime_phase": compositor_window_manager.get("runtime_phase"),
        "runtime_state_status": compositor_window_manager.get("runtime_state_status"),
        "runtime_state_path": compositor_window_manager.get("runtime_state_path"),
        "window_state_path": compositor_window_manager.get("window_state_path"),
        "workspace_count": compositor_window_manager.get("workspace_count", 1),
        "active_workspace_index": compositor_window_manager.get("active_workspace_index", 0),
        "active_workspace_id": compositor_window_manager.get("active_workspace_id"),
        "active_output_id": compositor_window_manager.get("active_output_id"),
        "managed_window_count": compositor_window_manager.get("managed_window_count", 0),
        "visible_window_count": compositor_window_manager.get("visible_window_count", 0),
        "floating_window_count": compositor_window_manager.get("floating_window_count", 0),
        "minimized_window_count": compositor_window_manager.get("minimized_window_count", 0),
        "window_move_count": compositor_window_manager.get("window_move_count", 0),
        "window_resize_count": compositor_window_manager.get("window_resize_count", 0),
        "window_minimize_count": compositor_window_manager.get("window_minimize_count", 0),
        "window_restore_count": compositor_window_manager.get("window_restore_count", 0),
        "last_minimized_window_key": compositor_window_manager.get("last_minimized_window_key"),
        "last_restored_window_key": compositor_window_manager.get("last_restored_window_key"),
        "workspace_window_counts": compositor_window_manager.get("workspace_window_counts", {}),
        "applied_filters": {
            "components": requested_surfaces,
            "status": args.status_filter,
            "tone": args.tone_filter,
        },
    }


def build_snapshot(profile: dict, args: argparse.Namespace) -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for component in enabled_components(profile, args.include_disabled):
        panel_args = build_panel_args(args, component)
        if panel_args is None:
            skipped.append({"component": component, "reason": "missing-context"})
            continue
        try:
            model = shellctl.run_panel(profile, component, panel_args, expect_json=True)
            surfaces.append(
                {
                    "component": component,
                    "panel_id": model.get("panel_id"),
                    "status": model.get("header", {}).get("status", "unknown"),
                    "tone": model.get("header", {}).get("tone", "neutral"),
                    "model": model,
                }
            )
        except subprocess.CalledProcessError as error:
            surfaces.append(
                {
                    "component": component,
                    "panel_id": component,
                    "status": "error",
                    "tone": "critical",
                    "error": error.stderr.strip() or error.stdout.strip() or str(error),
                }
            )

    visible_surfaces = apply_surface_filters(surfaces, args)
    visible_surfaces, shell_layout = annotate_visible_surfaces(visible_surfaces)
    compositor_window_manager = load_compositor_window_manager(profile)
    summary = build_summary(
        surfaces,
        visible_surfaces,
        skipped,
        args,
        shell_layout,
        compositor_window_manager,
    )
    return {
        "profile_id": profile.get("profile_id", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": args.session_id,
        "task_id": args.task_id,
        "surface_count": len(visible_surfaces),
        "total_surface_count": len(surfaces),
        "surfaces": visible_surfaces,
        "skipped": skipped,
        "window_manager": compositor_window_manager,
        "summary": summary,
    }


def render_overview(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("summary", {})
    lines = [
        f"profile_id: {snapshot.get('profile_id', 'unknown')}",
        f"generated_at: {snapshot.get('generated_at')}",
        f"visible_surfaces: {summary.get('visible_surface_count', snapshot.get('surface_count', 0))}",
        f"total_surfaces: {summary.get('total_surface_count', snapshot.get('total_surface_count', 0))}",
        f"skipped: {summary.get('skipped_count', len(snapshot.get('skipped', [])))}",
        f"errors: {summary.get('error_count', 0)}",
        f"actions: {summary.get('action_count', 0)}",
    ]
    if snapshot.get("session_id"):
        lines.append(f"session_id: {snapshot['session_id']}")
    if snapshot.get("task_id"):
        lines.append(f"task_id: {snapshot['task_id']}")

    applied_filters = summary.get("applied_filters", {})
    if any(value for value in applied_filters.values()):
        lines.append(
            "filters: "
            + ", ".join(
                f"{key}={value}"
                for key, value in applied_filters.items()
                if value not in (None, [], "")
            )
        )

    status_counts = summary.get("status_counts", {})
    if status_counts:
        lines.append("status_counts: " + ", ".join(f"{key}={value}" for key, value in status_counts.items()))
    tone_counts = summary.get("tone_counts", {})
    if tone_counts:
        lines.append("tone_counts: " + ", ".join(f"{key}={value}" for key, value in tone_counts.items()))
    focus_policy_counts = summary.get("focus_policy_counts", {})
    if focus_policy_counts:
        lines.append(
            "focus_policy_counts: "
            + ", ".join(f"{key}={value}" for key, value in focus_policy_counts.items())
        )
    interaction_mode_counts = summary.get("interaction_mode_counts", {})
    if interaction_mode_counts:
        lines.append(
            "interaction_mode_counts: "
            + ", ".join(f"{key}={value}" for key, value in interaction_mode_counts.items())
        )
    if summary.get("attention_components"):
        lines.append("attention_components: " + ", ".join(summary["attention_components"]))
    if summary.get("blocked_components"):
        lines.append("blocked_components: " + ", ".join(summary["blocked_components"]))
    if summary.get("active_modal_surface"):
        lines.append(f"active_modal_surface: {summary['active_modal_surface']}")
    if summary.get("primary_attention_surface"):
        lines.append(f"primary_attention_surface: {summary['primary_attention_surface']}")
    if summary.get("workspace_surface"):
        lines.append(f"workspace_surface: {summary['workspace_surface']}")
    if summary.get("top_stack_surface"):
        lines.append(f"top_stack_surface: {summary['top_stack_surface']}")
    if summary.get("window_manager_status"):
        lines.append(f"window_manager_status: {summary['window_manager_status']}")
    if summary.get("active_workspace_id"):
        lines.append(f"active_workspace_id: {summary['active_workspace_id']}")
    if summary.get("active_output_id"):
        lines.append(f"active_output_id: {summary['active_output_id']}")
    lines.append(f"managed_windows: {summary.get('managed_window_count', 0)}")
    lines.append(f"minimized_windows: {summary.get('minimized_window_count', 0)}")
    if summary.get("workspace_window_counts"):
        lines.append(
            "workspace_window_counts: "
            + ", ".join(
                f"{key}={value}" for key, value in sorted(summary["workspace_window_counts"].items())
            )
        )
    stack_order = summary.get("stack_order", [])
    if stack_order:
        lines.append("stack_order: " + " > ".join(stack_order))

    skipped = snapshot.get("skipped", [])
    if skipped:
        lines.append("skipped_components: " + ", ".join(f"{item['component']}({item['reason']})" for item in skipped))
    return "\n".join(lines)


def render_snapshot(snapshot: dict[str, Any]) -> str:
    lines = [
        f"AIOS Shell Desktop [{snapshot.get('profile_id', 'unknown')}]",
        f"generated_at: {snapshot.get('generated_at')}",
        f"surface_count: {snapshot.get('surface_count', 0)}",
        f"total_surface_count: {snapshot.get('total_surface_count', snapshot.get('surface_count', 0))}",
    ]
    if snapshot.get("session_id"):
        lines.append(f"session_id: {snapshot['session_id']}")
    if snapshot.get("task_id"):
        lines.append(f"task_id: {snapshot['task_id']}")
    lines.append("")
    lines.append("## overview")
    lines.append(render_overview(snapshot))
    skipped = snapshot.get("skipped", [])
    if skipped:
        lines.append("")
        lines.append("skipped: " + ", ".join(f"{item['component']}({item['reason']})" for item in skipped))
    for surface in snapshot.get("surfaces", []):
        lines.append("")
        lines.append(f"## {surface.get('component')} [{surface.get('status', 'unknown')}]")
        if surface.get("error"):
            lines.append(surface["error"])
        else:
            lines.append(render_panel_text(surface["model"]))
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], args: argparse.Namespace) -> dict[str, str]:
    if args.output_prefix is None:
        return {}

    output_prefix = args.output_prefix.expanduser().resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    text_path = output_prefix.with_suffix(".txt")
    json_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text_path.write_text(render_snapshot(snapshot) + "\n", encoding="utf-8")
    return {
        "json": str(json_path),
        "text": str(text_path),
    }

