#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from prototype import default_agent_socket, default_socket, fixture_call, load_fixture, rpc_call


STATUS_TONES = {
    "idle": "neutral",
    "active": "positive",
    "paused": "warning",
    "planned": "neutral",
    "approved": "positive",
    "in_progress": "warning",
    "completed": "positive",
    "failed": "critical",
}

SESSION_LIST_LIMIT = 6
SUGGESTED_INTENTS = [
    "open docs",
    "review approvals",
    "inspect device health",
]
WINDOW_ACTION_IDS = {
    "activate-next-workspace",
    "activate-previous-workspace",
    "focus-window",
    "minimize-window",
    "move-window-next-workspace",
    "restore-recent-window",
    "restore-window",
    "send-window-active-output",
}
TASK_SURFACE_PANEL = Path(__file__).resolve().parent.parent / "task-surface" / "panel.py"


def tone_for(status: str | None) -> str:
    if not status:
        return "neutral"
    return STATUS_TONES.get(status, "neutral")


def sort_sessions(sessions: list[dict]) -> list[dict]:
    return sorted(
        sessions,
        key=lambda item: (
            item.get("last_resumed_at") or item.get("created_at") or "",
            item.get("created_at") or "",
        ),
        reverse=True,
    )


def sort_tasks(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda item: item.get("created_at") or "", reverse=True)


def unique_intents(intent: str) -> list[str]:
    ordered = [intent, *SUGGESTED_INTENTS]
    unique: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique[:4]


def restore_point_at(session: dict | None) -> str | None:
    if not session:
        return None
    return session.get("last_resumed_at") or session.get("created_at")



def default_compositor_runtime_state() -> Path | None:
    value = os.environ.get("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_PATH")
    return Path(value) if value else None


def default_compositor_window_state() -> Path | None:
    value = os.environ.get("AIOS_SHELL_COMPOSITOR_WINDOW_STATE_PATH")
    return Path(value) if value else None


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


def derive_managed_windows(window_payload: dict, runtime_session: dict) -> list[dict]:
    managed_windows: list[dict] = []
    for entry in window_payload.get("windows", []):
        if not isinstance(entry, dict):
            continue
        rect = entry.get("rect") if isinstance(entry.get("rect"), dict) else {}
        workspace_index = parse_int(entry.get("workspace_index"), 0)
        workspace_id = f"workspace-{workspace_index + 1}"
        output_id = entry.get("output_id") or runtime_session.get("active_output_id") or "display-1"
        window_policy = str(entry.get("window_policy") or "workspace-window")
        minimized = bool(entry.get("minimized"))
        managed_windows.append(
            {
                "window_key": entry.get("window_key"),
                "surface_id": entry.get("slot_id") or entry.get("window_key"),
                "app_id": entry.get("app_id"),
                "title": entry.get("title"),
                "slot_id": entry.get("slot_id"),
                "output_id": output_id,
                "workspace_id": workspace_id,
                "window_policy": window_policy,
                "floating": "floating" in window_policy,
                "visible": not minimized,
                "minimized": minimized,
                "persisted": True,
                "interaction_state": "minimized" if minimized else "persisted",
                "layout_x": parse_int(rect.get("x"), 0),
                "layout_y": parse_int(rect.get("y"), 0),
                "layout_width": parse_int(rect.get("width"), 0),
                "layout_height": parse_int(rect.get("height"), 0),
            }
        )
    return managed_windows


def workspace_id_from_index(index: int) -> str:
    return f"workspace-{max(index, 0) + 1}"


def derive_release_grade_output_status(outputs: list[dict], renderable_output_count: int) -> str:
    if not outputs:
        return "uninitialized"
    output_count = len(outputs)
    if output_count == 1:
        return f"single-output(renderable={renderable_output_count}/{output_count})"
    if renderable_output_count >= output_count:
        return f"multi-output(renderable={renderable_output_count}/{output_count})"
    return f"multi-output(partial-renderable={renderable_output_count}/{output_count})"


def load_compositor_summary(
    runtime_state_path: Path | None,
    window_state_path: Path | None,
) -> dict:
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

    derived_workspace_counts: dict[str, int] = {}
    for window in managed_windows:
        workspace_id = str(window.get("workspace_id") or "workspace-1")
        derived_workspace_counts[workspace_id] = derived_workspace_counts.get(workspace_id, 0) + 1
    workspace_window_counts = dict(sorted(derived_workspace_counts.items()))

    active_workspace_index = parse_int(
        window_payload.get("active_workspace_index"),
        parse_int(runtime_session.get("active_workspace_index"), 0),
    )
    active_workspace_id = workspace_id_from_index(active_workspace_index)
    workspace_count = max(
        1,
        parse_int(
            runtime_session.get("workspace_count"),
            max(len(workspace_window_counts), active_workspace_index + 1, 1),
        ),
    )
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
    errors = [error for error in (runtime_error, window_error) if error]
    data_status = "ready" if runtime_payload or window_payload else "unavailable"
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
        "workspace_count": workspace_count,
        "active_workspace_index": active_workspace_index,
        "active_workspace_id": active_workspace_id,
        "active_output_id": window_payload.get("active_output_id") or runtime_session.get("active_output_id"),
        "output_count": output_count,
        "renderable_output_count": renderable_output_count,
        "non_renderable_output_count": non_renderable_output_count,
        "release_grade_output_status": runtime_session.get("release_grade_output_status")
        or derive_release_grade_output_status(outputs, renderable_output_count),
        "managed_window_count": len(managed_windows),
        "visible_window_count": sum(1 for item in managed_windows if item.get("visible")),
        "floating_window_count": sum(1 for item in managed_windows if item.get("floating")),
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


def load_fixture_state(path: Path, session_id: str | None) -> dict:
    payload = load_fixture(path)
    sessions = sort_sessions(list(payload.get("sessions", [])))
    all_tasks = sort_tasks(list(payload.get("tasks", [])))
    focus_session = None
    if session_id:
        focus_session = next((item for item in sessions if item.get("session_id") == session_id), None)
    elif sessions:
        focus_session = sessions[0]
    focus_tasks = all_tasks
    if focus_session is not None:
        focus_tasks = [item for item in all_tasks if item.get("session_id") == focus_session.get("session_id")]
    recovery = None
    if focus_session is not None:
        recovery = {
            "recovery_id": f"recovery-{focus_session.get('session_id')}",
            "session_id": focus_session.get("session_id"),
            "status": "baseline",
        }
    return {
        "sessions": sessions,
        "tasks": focus_tasks,
        "all_tasks": all_tasks,
        "focus_session": focus_session,
        "recovery": recovery,
        "session_count": len(sessions),
        "task_count_total": len(all_tasks),
        "data_source_status": "ready",
        "data_source_error": None,
    }


def load_live_state(agent_socket_path: Path, session_id: str | None) -> dict:
    sessions: list[dict] = []
    focus_session = None
    recovery = None
    tasks: list[dict] = []
    errors: list[str] = []

    try:
        sessions_result = rpc_call(
            agent_socket_path,
            "agent.session.list",
            {"limit": SESSION_LIST_LIMIT},
        )
        sessions = sort_sessions(list(sessions_result.get("sessions", [])))
    except Exception as error:
        sessions = []
        errors.append(str(error))

    focus_session_id = session_id or ((sessions[0] if sessions else {}).get("session_id"))
    if focus_session_id:
        try:
            evidence = rpc_call(
                agent_socket_path,
                "agent.session.evidence.get",
                {"session_id": focus_session_id, "limit": 20},
            )
            focus_session = evidence.get("session")
            recovery = evidence.get("recovery")
            tasks = sort_tasks(list(evidence.get("tasks", [])))
        except Exception as error:
            focus_session = next(
                (item for item in sessions if item.get("session_id") == focus_session_id),
                None,
            )
            recovery = None
            tasks = []
            errors.append(str(error))

    if focus_session is not None and not any(
        item.get("session_id") == focus_session.get("session_id") for item in sessions
    ):
        sessions = sort_sessions([focus_session, *sessions])

    if errors:
        data_source_status = "partial" if sessions or focus_session is not None or tasks else "fallback-empty"
        data_source_error = "; ".join(errors)
    else:
        data_source_status = "ready"
        data_source_error = None

    return {
        "sessions": sessions,
        "tasks": tasks,
        "all_tasks": tasks,
        "focus_session": focus_session,
        "recovery": recovery,
        "session_count": len(sessions),
        "task_count_total": len(tasks),
        "data_source_status": data_source_status,
        "data_source_error": data_source_error,
    }


def load_state(agent_socket_path: Path, fixture: Path | None, session_id: str | None) -> dict:
    if fixture is not None:
        return load_fixture_state(fixture, session_id)
    return load_live_state(agent_socket_path, session_id)


def build_model(
    state: dict,
    requested_session_id: str | None,
    user_id: str,
    intent: str,
    title: str | None,
    task_state: str,
    compositor_summary: dict,
) -> dict:
    sessions = list(state.get("sessions", []))
    tasks = list(state.get("tasks", []))
    all_tasks = list(state.get("all_tasks", tasks))
    focus_session = state.get("focus_session")
    recovery = state.get("recovery")
    focus_task = tasks[0] if tasks else None
    resolved_session_id = (focus_session or {}).get("session_id")
    restore_available = focus_session is not None
    restore_point = restore_point_at(focus_session)
    restore_target_component = "task-surface" if restore_available else None
    recovery_status = (recovery or {}).get("status")
    task_counts_by_session: dict[str, int] = {}
    for item in all_tasks:
        session_key = item.get("session_id")
        if not session_key:
            continue
        task_counts_by_session[session_key] = task_counts_by_session.get(session_key, 0) + 1

    recent_sessions = []
    for item in sessions[:SESSION_LIST_LIMIT]:
        session_key = item.get("session_id")
        session_state = item.get("status", "unknown")
        task_count = task_counts_by_session.get(session_key, 0)
        last_activity = item.get("last_resumed_at") or item.get("created_at") or "-"
        recent_sessions.append(
            {
                "label": session_key or "unknown-session",
                "value": f"{session_state} · tasks={task_count} · {last_activity}",
                "tone": tone_for(session_state),
                "action": {
                    "action_id": "resume-session",
                    "label": "Resume",
                    "enabled": bool(session_key),
                    "session_id": session_key,
                },
            }
        )

    suggestion_items = []
    for suggestion in unique_intents(intent):
        action_id = "create-task" if resolved_session_id else "create-session"
        suggestion_items.append(
            {
                "label": suggestion,
                "value": "append to active session" if resolved_session_id else "start a new session",
                "tone": "neutral",
                "action": {
                    "action_id": action_id,
                    "label": "Launch",
                    "enabled": True,
                    "session_id": resolved_session_id,
                    "title": suggestion,
                    "intent": suggestion,
                    "target_state": task_state,
                },
            }
        )

    active_workspace_id = compositor_summary.get("active_workspace_id")
    active_output_id = compositor_summary.get("active_output_id")
    active_workspace_windows = [
        item
        for item in compositor_summary.get("managed_windows", [])
        if item.get("workspace_id") == active_workspace_id and not item.get("minimized")
    ]
    minimized_windows = [
        item for item in compositor_summary.get("managed_windows", []) if item.get("minimized")
    ]

    actions = [
        {
            "action_id": "create-session",
            "label": "Create Session",
            "enabled": True,
            "tone": "positive",
        },
        {
            "action_id": "resume-session",
            "label": "Resume Session",
            "enabled": focus_session is not None,
            "tone": tone_for((focus_session or {}).get("status")),
            "session_id": resolved_session_id,
        },
        {
            "action_id": "create-task",
            "label": "Create Task",
            "enabled": focus_session is not None,
            "tone": tone_for(task_state),
            "session_id": resolved_session_id,
            "target_state": task_state,
        },
    ]
    if compositor_summary.get("window_state_path"):
        actions.extend(
            [
                {
                    "action_id": "restore-recent-window",
                    "label": "Restore Window",
                    "enabled": compositor_summary.get("minimized_window_count", 0) > 0,
                    "tone": "positive",
                    "workspace_id": active_workspace_id,
                    "output_id": active_output_id,
                },
                {
                    "action_id": "activate-next-workspace",
                    "label": "Next Workspace",
                    "enabled": compositor_summary.get("workspace_count", 1) > 1,
                    "tone": "neutral",
                    "workspace_id": active_workspace_id,
                    "output_id": active_output_id,
                },
            ]
        )

    active_workspace_window_items = [
        {
            "label": item.get("title") or item.get("app_id") or item.get("window_key") or "window",
            "value": " · ".join(
                part
                for part in (
                    item.get("window_policy") or "workspace-window",
                    item.get("output_id") or "display-1",
                    item.get("window_key") or "",
                )
                if part
            ),
            "tone": "neutral",
            "action": {
                "action_id": "focus-window",
                "label": "Focus",
                "enabled": bool(item.get("window_key")) and bool(compositor_summary.get("window_state_path")),
                "window_key": item.get("window_key"),
                "workspace_id": item.get("workspace_id"),
                "output_id": item.get("output_id"),
            },
        }
        for item in active_workspace_windows
    ]
    minimized_window_items = [
        {
            "label": item.get("title") or item.get("app_id") or item.get("window_key") or "window",
            "value": " · ".join(
                part
                for part in (
                    item.get("workspace_id") or "workspace-1",
                    item.get("output_id") or "display-1",
                    item.get("window_key") or "",
                )
                if part
            ),
            "tone": "warning",
            "action": {
                "action_id": "restore-window",
                "label": "Restore",
                "enabled": bool(item.get("window_key")) and bool(compositor_summary.get("window_state_path")),
                "window_key": item.get("window_key"),
                "workspace_id": item.get("workspace_id") or active_workspace_id,
                "output_id": active_output_id or item.get("output_id"),
            },
        }
        for item in minimized_windows
    ]
    window_overview_items = [
        {
            "label": "window_manager_status",
            "value": compositor_summary.get("window_manager_status") or compositor_summary.get("data_status") or "unavailable",
            "tone": "warning" if compositor_summary.get("data_status") != "ready" else "neutral",
        },
        {
            "label": "active_workspace",
            "value": active_workspace_id or "workspace-1",
            "tone": "positive" if active_workspace_id else "neutral",
        },
        {
            "label": "active_output",
            "value": active_output_id or "-",
            "tone": "neutral",
        },
        {
            "label": "renderable_outputs",
            "value": compositor_summary.get("renderable_output_count", 0),
            "tone": "positive" if compositor_summary.get("renderable_output_count", 0) else "neutral",
        },
        {
            "label": "output_status",
            "value": compositor_summary.get("release_grade_output_status") or "uninitialized",
            "tone": "neutral",
        },
        {
            "label": "managed_windows",
            "value": compositor_summary.get("managed_window_count", 0),
            "tone": "neutral",
        },
        {
            "label": "minimized_windows",
            "value": compositor_summary.get("minimized_window_count", 0),
            "tone": "warning" if compositor_summary.get("minimized_window_count", 0) else "neutral",
        },
    ]

    return {
        "component_id": "launcher",
        "panel_id": "launcher-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Launcher Panel",
            "subtitle": f"user {user_id} · intent {intent}",
            "status": (focus_session or {}).get("status", "idle"),
            "tone": tone_for((focus_session or {}).get("status", "idle")),
        },
        "badges": [
            {"label": "Sessions", "value": state.get("session_count", len(sessions)), "tone": "neutral"},
            {"label": "Tasks", "value": len(tasks), "tone": "neutral"},
            {"label": "Focus", "value": resolved_session_id or "none", "tone": tone_for((focus_session or {}).get("status"))},
            {"label": "Workspace", "value": active_workspace_id or "-", "tone": "positive" if active_workspace_id else "neutral"},
            {"label": "Minimized", "value": compositor_summary.get("minimized_window_count", 0), "tone": "warning" if compositor_summary.get("minimized_window_count", 0) else "neutral"},
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "suggestions",
                "title": "Suggested Launches",
                "items": suggestion_items,
                "empty_state": "No suggested launches",
            },
            {
                "section_id": "launch-request",
                "title": "Launch Request",
                "items": [
                    {"label": "user_id", "value": user_id, "tone": "neutral"},
                    {"label": "intent", "value": intent, "tone": "neutral"},
                    {"label": "task_title", "value": title or intent, "tone": "neutral"},
                    {"label": "task_state", "value": task_state, "tone": tone_for(task_state)},
                ],
                "empty_state": "No launch request",
            },
            {
                "section_id": "recent-sessions",
                "title": "Recent Sessions",
                "items": recent_sessions,
                "empty_state": "No recent sessions",
            },
            {
                "section_id": "restore",
                "title": "Session Restore",
                "items": [] if focus_session is None else [
                    {"label": "session_id", "value": resolved_session_id, "tone": "neutral"},
                    {
                        "label": "restore_ready",
                        "value": "ready" if restore_available else "unavailable",
                        "tone": "positive" if restore_available else "neutral",
                    },
                    {
                        "label": "restore_point_at",
                        "value": restore_point or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "recovery_id",
                        "value": (recovery or {}).get("recovery_id") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "recovery_status",
                        "value": recovery_status or "-",
                        "tone": tone_for(recovery_status),
                    },
                    {
                        "label": "target_surface",
                        "value": restore_target_component or "-",
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No restorable session selected",
            },
            {
                "section_id": "session",
                "title": "Session",
                "items": [] if focus_session is None else [
                    {"label": "session_id", "value": focus_session.get("session_id"), "tone": "neutral"},
                    {"label": "user_id", "value": focus_session.get("user_id"), "tone": "neutral"},
                    {"label": "status", "value": focus_session.get("status"), "tone": tone_for(focus_session.get("status"))},
                    {"label": "created_at", "value": focus_session.get("created_at", "-") , "tone": "neutral"},
                ],
                "empty_state": "No active session selected",
            },
            {
                "section_id": "recovery",
                "title": "Recovery",
                "items": [] if recovery is None else [
                    {"label": "recovery_id", "value": recovery.get("recovery_id"), "tone": "neutral"},
                    {"label": "status", "value": recovery.get("status"), "tone": tone_for(recovery.get("status"))},
                ],
                "empty_state": "No recovery context",
            },
            {
                "section_id": "tasks",
                "title": "Session Tasks",
                "items": [
                    {
                        "label": item.get("title") or item.get("task_id"),
                        "value": item.get("state"),
                        "task_id": item.get("task_id"),
                        "tone": tone_for(item.get("state")),
                    }
                    for item in tasks
                ],
                "empty_state": "No tasks in session",
            },
            {
                "section_id": "window-overview",
                "title": "Window Restore",
                "items": window_overview_items,
                "empty_state": "No compositor window manager summary",
            },
            {
                "section_id": "active-workspace-windows",
                "title": "Active Workspace Windows",
                "items": active_workspace_window_items,
                "empty_state": "No visible windows in the active workspace",
            },
            {
                "section_id": "minimized-windows",
                "title": "Minimized Windows",
                "items": minimized_window_items,
                "empty_state": "No minimized windows",
            },
        ],
        "meta": {
            "requested_session_id": requested_session_id,
            "resolved_session_id": resolved_session_id,
            "focus_task_id": (focus_task or {}).get("task_id"),
            "session_count": state.get("session_count", len(sessions)),
            "recent_session_count": len(recent_sessions),
            "suggestion_count": len(suggestion_items),
            "task_count": len(tasks),
            "task_count_total": state.get("task_count_total", len(tasks)),
            "restore_available": restore_available,
            "restore_session_id": resolved_session_id,
            "restore_point_at": restore_point,
            "restore_target_component": restore_target_component,
            "restore_recovery_id": (recovery or {}).get("recovery_id"),
            "restore_recovery_status": recovery_status,
            "restore_task_count": len(tasks),
            "focus_session_status": (focus_session or {}).get("status"),
            "focus_session_last_resumed_at": (focus_session or {}).get("last_resumed_at"),
            "data_source_status": state.get("data_source_status", "ready"),
            "data_source_error": state.get("data_source_error"),
            "compositor_data_status": compositor_summary.get("data_status"),
            "compositor_data_error": compositor_summary.get("data_error"),
            "compositor_runtime_phase": compositor_summary.get("runtime_phase"),
            "compositor_runtime_state_status": compositor_summary.get("runtime_state_status"),
            "compositor_runtime_state_path": compositor_summary.get("runtime_state_path"),
            "compositor_window_state_path": compositor_summary.get("window_state_path"),
            "compositor_window_manager_status": compositor_summary.get("window_manager_status"),
            "workspace_count": compositor_summary.get("workspace_count", 1),
            "active_workspace_index": compositor_summary.get("active_workspace_index", 0),
            "active_workspace_id": active_workspace_id,
            "active_output_id": active_output_id,
            "output_count": compositor_summary.get("output_count", 0),
            "renderable_output_count": compositor_summary.get("renderable_output_count", 0),
            "non_renderable_output_count": compositor_summary.get("non_renderable_output_count", 0),
            "release_grade_output_status": compositor_summary.get("release_grade_output_status"),
            "managed_window_count": compositor_summary.get("managed_window_count", 0),
            "visible_window_count": compositor_summary.get("visible_window_count", 0),
            "floating_window_count": compositor_summary.get("floating_window_count", 0),
            "minimized_window_count": compositor_summary.get("minimized_window_count", 0),
            "window_move_count": compositor_summary.get("window_move_count", 0),
            "window_resize_count": compositor_summary.get("window_resize_count", 0),
            "window_minimize_count": compositor_summary.get("window_minimize_count", 0),
            "window_restore_count": compositor_summary.get("window_restore_count", 0),
            "last_minimized_window_key": compositor_summary.get("last_minimized_window_key"),
            "last_restored_window_key": compositor_summary.get("last_restored_window_key"),
            "workspace_window_counts": compositor_summary.get("workspace_window_counts", {}),
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    lines.append("badges: " + ", ".join(f"{item['label']}: {item['value']}" for item in panel["badges"]))
    meta = panel.get("meta") or {}
    if meta.get("data_source_status") != "ready":
        lines.append(f"source: {meta.get('data_source_status')}")
        if meta.get("data_source_error"):
            lines.append(f"source_error: {meta['data_source_error']}")
    if panel["actions"]:
        lines.append("actions: " + ", ".join(action["label"] for action in panel["actions"] if action.get("enabled", True)))
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if items:
            for item in items:
                action = item.get("action") if isinstance(item.get("action"), dict) else None
                action_suffix = f" -> {action.get('label')}" if action else ""
                if section["section_id"] == "tasks":
                    lines.append(f"- {item.get('task_id')}: {item['label']} [{item['value']}]{action_suffix}")
                else:
                    lines.append(f"- {item['label']}: {item['value']}{action_suffix}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def resolve_action_session_id(args: argparse.Namespace) -> str | None:
    if args.session_id:
        return args.session_id
    if args.fixture is not None:
        state = load_fixture_state(args.fixture, None)
        focus_session = state.get("focus_session") or {}
        return focus_session.get("session_id")
    try:
        sessions = rpc_call(args.agent_socket, "agent.session.list", {"limit": 1}).get("sessions", [])
    except Exception:
        return None
    if sessions:
        return sessions[0].get("session_id")
    return None



def dispatch_window_action(args: argparse.Namespace) -> dict:
    command = [sys.executable, str(TASK_SURFACE_PANEL), "action", "--action", args.action]
    if args.compositor_runtime_state is not None:
        command.extend(["--compositor-runtime-state", str(args.compositor_runtime_state)])
    if args.compositor_window_state is not None:
        command.extend(["--compositor-window-state", str(args.compositor_window_state)])
    if args.window_key:
        command.extend(["--window-key", args.window_key])
    if args.workspace_id:
        command.extend(["--workspace-id", args.workspace_id])
    if args.output_id:
        command.extend(["--output-id", args.output_id])
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return json.loads(completed.stdout.strip() or "{}")


def run_action(args: argparse.Namespace) -> dict:
    if args.action in WINDOW_ACTION_IDS:
        return dispatch_window_action(args)

    if args.action == "create-session":
        action_args = argparse.Namespace(
            user_id=args.user_id,
            intent=args.intent,
            session_id=None,
            title=args.title,
            state=args.state,
        )
        if args.fixture is not None:
            result = fixture_call(args.fixture, "create-session", action_args)
        else:
            result = rpc_call(args.agent_socket, "agent.session.create", {"user_id": args.user_id, "metadata": {"initial_intent": args.intent}})
        return {
            **result,
            "target_component": "task-surface",
        }

    session_id = resolve_action_session_id(args)
    if not session_id:
        raise SystemExit("--session-id is required for this action")

    if args.action == "resume-session":
        action_args = argparse.Namespace(session_id=session_id)
        if args.fixture is not None:
            result = fixture_call(args.fixture, "resume", action_args)
        else:
            result = rpc_call(args.agent_socket, "agent.session.resume", {"session_id": session_id})
        session = result.get("session") or {}
        recovery = result.get("recovery") or {}
        return {
            **result,
            "target_component": "task-surface",
            "restore_available": bool(session.get("session_id")),
            "resumed_session_id": session.get("session_id"),
            "session_status": session.get("status"),
            "restore_point_at": session.get("last_resumed_at") or session.get("created_at"),
            "recovery_id": recovery.get("recovery_id"),
            "recovery_status": recovery.get("status"),
            "restore_status": recovery.get("status")
            or session.get("status")
            or ("ready" if session.get("session_id") else "unavailable"),
        }

    if args.action == "create-task":
        action_args = argparse.Namespace(session_id=session_id, title=args.title or args.intent, state=args.state)
        if args.fixture is not None:
            result = fixture_call(args.fixture, "create-task", action_args)
        else:
            result = rpc_call(args.agent_socket, "agent.task.create", {"session_id": session_id, "title": args.title or args.intent, "state": args.state})
        return {
            **result,
            "target_component": "task-surface",
        }

    raise SystemExit(f"unknown action: {args.action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS launcher panel")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--intent", default="shell-launcher")
    parser.add_argument("--title")
    parser.add_argument("--state", default="planned")
    parser.add_argument("--action")
    parser.add_argument("--window-key")
    parser.add_argument("--workspace-id")
    parser.add_argument("--output-id")
    parser.add_argument("--compositor-runtime-state", type=Path, default=default_compositor_runtime_state())
    parser.add_argument("--compositor-window-state", type=Path, default=default_compositor_window_state())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        result = run_action(args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            state = load_state(args.agent_socket, args.fixture, args.session_id)
            compositor_summary = load_compositor_summary(
                args.compositor_runtime_state,
                args.compositor_window_state,
            )
            model = build_model(
                state,
                args.session_id,
                args.user_id,
                args.intent,
                args.title,
                args.state,
                compositor_summary,
            )
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    state = load_state(args.agent_socket, args.fixture, args.session_id)
    compositor_summary = load_compositor_summary(
        args.compositor_runtime_state,
        args.compositor_window_state,
    )
    model = build_model(
        state,
        args.session_id,
        args.user_id,
        args.intent,
        args.title,
        args.state,
        compositor_summary,
    )
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

