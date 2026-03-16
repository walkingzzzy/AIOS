#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from prototype import default_agent_socket, default_socket, fixture_call, rpc_call


STATE_TONES = {
    "planned": "neutral",
    "approved": "positive",
    "replanned": "warning",
    "in_progress": "warning",
    "executing": "warning",
    "completed": "positive",
    "failed": "critical",
    "cancelled": "neutral",
    "rejected": "critical",
    "created": "neutral",
}


def tone_for(state: str | None) -> str:
    if not state:
        return "neutral"
    return STATE_TONES.get(state, "neutral")


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


def load_compositor_summary(
    runtime_state_path: Path | None,
    window_state_path: Path | None,
) -> dict:
    runtime_payload, runtime_error = load_json_payload(runtime_state_path)
    window_payload, window_error = load_json_payload(window_state_path)
    runtime_session = runtime_payload.get("session")
    if not isinstance(runtime_session, dict):
        runtime_session = runtime_payload if isinstance(runtime_payload, dict) else {}

    managed_windows = [
        item
        for item in runtime_session.get("managed_windows", [])
        if isinstance(item, dict)
    ]
    if not managed_windows:
        managed_windows = derive_managed_windows(window_payload, runtime_session)

    workspace_window_counts = runtime_session.get("workspace_window_counts")
    if not isinstance(workspace_window_counts, dict):
        workspace_window_counts = {}
    if not workspace_window_counts:
        derived_workspace_counts: dict[str, int] = {}
        for window in managed_windows:
            workspace_id = str(window.get("workspace_id") or "workspace-1")
            derived_workspace_counts[workspace_id] = derived_workspace_counts.get(workspace_id, 0) + 1
        workspace_window_counts = derived_workspace_counts

    active_workspace_index = parse_int(
        runtime_session.get("active_workspace_index"),
        parse_int(window_payload.get("active_workspace_index"), 0),
    )
    active_workspace_id = runtime_session.get("active_workspace_id") or f"workspace-{active_workspace_index + 1}"
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
        "active_output_id": runtime_session.get("active_output_id") or window_payload.get("active_output_id"),
        "output_count": parse_int(runtime_session.get("output_count"), len(outputs)),
        "outputs": outputs,
        "managed_window_count": parse_int(runtime_session.get("managed_window_count"), len(managed_windows)),
        "visible_window_count": parse_int(
            runtime_session.get("visible_window_count"),
            sum(1 for item in managed_windows if item.get("visible")),
        ),
        "floating_window_count": parse_int(
            runtime_session.get("floating_window_count"),
            sum(1 for item in managed_windows if item.get("floating")),
        ),
        "minimized_window_count": parse_int(
            runtime_session.get("minimized_window_count"),
            sum(1 for item in managed_windows if item.get("minimized")),
        ),
        "window_move_count": parse_int(runtime_session.get("window_move_count"), 0),
        "window_resize_count": parse_int(runtime_session.get("window_resize_count"), 0),
        "window_minimize_count": parse_int(runtime_session.get("window_minimize_count"), 0),
        "window_restore_count": parse_int(runtime_session.get("window_restore_count"), 0),
        "last_minimized_window_key": runtime_session.get("last_minimized_window_key"),
        "last_restored_window_key": runtime_session.get("last_restored_window_key"),
        "workspace_window_counts": dict(sorted(workspace_window_counts.items())),
        "managed_windows": managed_windows,
    }


def list_tasks(
    agent_socket: Path,
    fixture: Path | None,
    session_id: str,
    state: str | None,
    limit: int | None,
) -> dict:
    if fixture is not None:
        args = argparse.Namespace(
            session_id=session_id,
            state=state,
            limit=limit,
            task_id=None,
        )
        return fixture_call(fixture, "list", args)
    return rpc_call(
        agent_socket,
        "agent.task.list",
        {"session_id": session_id, "state": state, "limit": limit},
    )


def load_tasks_with_fallback(
    socket_path: Path,
    fixture: Path | None,
    session_id: str,
    state: str | None,
    limit: int | None,
) -> tuple[dict, str | None]:
    try:
        return list_tasks(socket_path, fixture, session_id, state, limit), None
    except Exception as error:
        return {"tasks": []}, str(error)


def get_task(agent_socket: Path, fixture: Path | None, task_id: str | None) -> dict | None:
    if not task_id:
        return None
    try:
        if fixture is not None:
            args = argparse.Namespace(task_id=task_id)
            return fixture_call(fixture, "show", args)
        return rpc_call(
            agent_socket,
            "agent.task.get",
            {"task_id": task_id, "event_limit": 10},
        ).get("task")
    except Exception:
        return None


def get_plan(agent_socket: Path, fixture: Path | None, task_id: str | None) -> dict | None:
    if not task_id:
        return None
    try:
        if fixture is not None:
            args = argparse.Namespace(task_id=task_id)
            return fixture_call(fixture, "plan", args)
        return rpc_call(agent_socket, "agent.task.plan.get", {"task_id": task_id})
    except Exception:
        return None


def update_task_state(
    socket_path: Path,
    fixture: Path | None,
    task_id: str,
    new_state: str,
    reason: str | None,
) -> dict:
    if fixture is not None:
        args = argparse.Namespace(task_id=task_id, state=new_state, reason=reason)
        return fixture_call(fixture, "update", args)
    return rpc_call(
        socket_path,
        "agent.task.state.update",
        {"task_id": task_id, "new_state": new_state, "reason": reason},
    )


def list_task_events(
    agent_socket: Path,
    fixture: Path | None,
    task_id: str | None,
    limit: int,
) -> dict:
    if not task_id:
        return {"events": []}
    try:
        if fixture is not None:
            args = argparse.Namespace(task_id=task_id, limit=limit)
            return fixture_call(fixture, "events", args)
        return rpc_call(
            agent_socket,
            "agent.task.events.list",
            {"task_id": task_id, "limit": limit, "reverse": True},
        )
    except Exception:
        return {"events": []}


def load_fixture_payload(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text())


def primary_capability(plan_result: dict | None) -> str | None:
    if not plan_result:
        return None
    plan = plan_result.get("plan", {})
    capabilities = plan.get("candidate_capabilities") or []
    if not capabilities:
        return None
    return capabilities[0]


def resolve_provider(
    agent_socket: Path,
    fixture: Path | None,
    task_id: str | None,
    plan_result: dict | None,
) -> tuple[dict | None, str | None, str | None]:
    capability_id = primary_capability(plan_result)
    if not capability_id:
        return None, None, None

    if fixture is not None:
        payload = load_fixture_payload(fixture)
        resolutions = payload.get("provider_resolutions", {})
        for key in (task_id, capability_id):
            if key and isinstance(resolutions.get(key), dict):
                return resolutions[key], capability_id, None
        return None, capability_id, None

    if not task_id:
        return None, capability_id, None

    try:
        response = rpc_call(
            agent_socket,
            "agent.task.get",
            {"task_id": task_id, "event_limit": 1},
        )
    except Exception as error:
        return None, capability_id, str(error)

    return response.get("provider_resolution"), capability_id, None


def build_summary(tasks: list[dict]) -> dict:
    by_state: dict[str, int] = {}
    for item in tasks:
        state = item.get("state", "unknown")
        by_state[state] = by_state.get(state, 0) + 1
    return {"total": len(tasks), "by_state": by_state}


def build_focus_actions(focus_task: dict | None) -> list[dict]:
    if not focus_task:
        return []

    task_id = focus_task.get("task_id")
    state = focus_task.get("state")
    normalized_state = "executing" if state == "in_progress" else state
    actions: list[dict] = []

    if normalized_state in {"planned", "replanned"}:
        actions.append(
            {
                "action_id": "approve-task",
                "label": "Approve Task",
                "task_id": task_id,
                "target_state": "approved",
                "enabled": True,
            }
        )
        actions.append(
            {
                "action_id": "start-task",
                "label": "Start Task",
                "task_id": task_id,
                "target_state": "executing",
                "enabled": True,
            }
        )
        actions.append(
            {
                "action_id": "cancel-task",
                "label": "Cancel Task",
                "task_id": task_id,
                "target_state": "cancelled",
                "enabled": True,
            }
        )
    elif normalized_state == "approved":
        actions.append(
            {
                "action_id": "start-task",
                "label": "Start Task",
                "task_id": task_id,
                "target_state": "executing",
                "enabled": True,
            }
        )
        actions.append(
            {
                "action_id": "fail-task",
                "label": "Mark Failed",
                "task_id": task_id,
                "target_state": "failed",
                "enabled": True,
            }
        )
        actions.append(
            {
                "action_id": "cancel-task",
                "label": "Cancel Task",
                "task_id": task_id,
                "target_state": "cancelled",
                "enabled": True,
            }
        )
    elif normalized_state == "executing":
        actions.append(
            {
                "action_id": "complete-task",
                "label": "Complete Task",
                "task_id": task_id,
                "target_state": "completed",
                "enabled": True,
            }
        )
        actions.append(
            {
                "action_id": "fail-task",
                "label": "Mark Failed",
                "task_id": task_id,
                "target_state": "failed",
                "enabled": True,
            }
        )
        actions.append(
            {
                "action_id": "cancel-task",
                "label": "Cancel Task",
                "task_id": task_id,
                "target_state": "cancelled",
                "enabled": True,
            }
        )
    elif normalized_state == "failed":
        actions.append(
            {
                "action_id": "replan-task",
                "label": "Replan Task",
                "task_id": task_id,
                "target_state": "replanned",
                "enabled": True,
            }
        )
        actions.append(
            {
                "action_id": "cancel-task",
                "label": "Cancel Task",
                "task_id": task_id,
                "target_state": "cancelled",
                "enabled": True,
            }
        )

    return actions


def build_model(
    tasks_result: dict,
    focus_task: dict | None,
    plan_result: dict | None,
    task_events_result: dict,
    session_id: str | None,
    provider_resolution: dict | None,
    provider_resolution_error: str | None,
    capability_id: str | None,
    compositor_summary: dict | None,
    data_source_error: str | None = None,
) -> dict:
    tasks = tasks_result.get("tasks", [])
    summary = build_summary(tasks)
    plan = (plan_result or {}).get("plan") or {}
    task_events = task_events_result.get("events", [])
    compositor_summary = compositor_summary or {}

    task_items = [
        {
            "task_id": item.get("task_id"),
            "label": item.get("title") or item.get("task_id"),
            "state": item.get("state"),
            "value": item.get("task_id"),
            "session_id": item.get("session_id"),
            "created_at": item.get("created_at"),
            "tone": tone_for(item.get("state")),
        }
        for item in tasks
    ]

    plan_steps = []
    if plan_result:
        for index, step in enumerate(plan.get("steps", [])):
            plan_steps.append(
                {
                    "step_id": f"step-{index + 1}",
                    "label": step.get("step", f"step-{index + 1}"),
                    "status": step.get("status", "unknown"),
                    "tone": tone_for(step.get("status")),
                }
            )

    focus_items = []
    if focus_task:
        focus_items.extend(
            [
                {
                    "label": "task_id",
                    "value": focus_task.get("task_id"),
                    "tone": "neutral",
                },
                {
                    "label": "title",
                    "value": focus_task.get("title") or "-",
                    "tone": "neutral",
                },
                {
                    "label": "state",
                    "value": focus_task.get("state"),
                    "tone": tone_for(focus_task.get("state")),
                },
                {
                    "label": "created_at",
                    "value": focus_task.get("created_at", "-"),
                    "tone": "neutral",
                },
            ]
        )
    if plan.get("summary"):
        focus_items.append(
            {
                "label": "plan_summary",
                "value": plan.get("summary"),
                "tone": "neutral",
            }
        )
    if plan.get("route_preference"):
        focus_items.append(
            {
                "label": "route_preference",
                "value": plan.get("route_preference"),
                "tone": "neutral",
            }
        )
    if plan.get("next_action"):
        focus_items.append(
            {
                "label": "next_action",
                "value": plan.get("next_action"),
                "tone": "warning",
            }
        )
    if plan.get("candidate_capabilities"):
        focus_items.append(
            {
                "label": "candidate_capabilities",
                "value": ", ".join(plan.get("candidate_capabilities") or []),
                "tone": "neutral",
            }
        )

    event_items = [
        {
            "label": event.get("to_state", "unknown"),
            "value": " -> ".join(
                part
                for part in [event.get("from_state"), event.get("to_state")]
                if part
            ),
            "detail": (event.get("metadata") or {}).get("reason") or "-",
            "created_at": event.get("created_at"),
            "tone": tone_for(event.get("to_state")),
        }
        for event in task_events
    ]

    selected_provider = (provider_resolution or {}).get("selected") or {}
    provider_candidates = (provider_resolution or {}).get("candidates") or []

    provider_route_items = []
    if capability_id:
        provider_route_items.append(
            {
                "label": "primary_capability",
                "value": capability_id,
                "tone": "neutral",
            }
        )
    if selected_provider:
        provider_route_items.extend(
            [
                {
                    "label": "provider_id",
                    "value": selected_provider.get("provider_id"),
                    "tone": "positive",
                },
                {
                    "label": "display_name",
                    "value": selected_provider.get("display_name", "-"),
                    "tone": "neutral",
                },
                {
                    "label": "kind",
                    "value": selected_provider.get("kind", "-"),
                    "tone": "neutral",
                },
                {
                    "label": "execution_location",
                    "value": selected_provider.get("execution_location", "-"),
                    "tone": "neutral",
                },
                {
                    "label": "health_status",
                    "value": selected_provider.get("health_status", "-"),
                    "tone": (
                        "positive"
                        if selected_provider.get("health_status") == "available"
                        else "warning"
                    ),
                },
                {
                    "label": "score",
                    "value": selected_provider.get("score", 0),
                    "tone": "neutral",
                },
            ]
        )
    if provider_resolution and provider_resolution.get("reason"):
        provider_route_items.append(
            {
                "label": "resolution_reason",
                "value": provider_resolution.get("reason"),
                "tone": "neutral",
            }
        )
    if provider_resolution_error:
        provider_route_items.append(
            {
                "label": "registry_error",
                "value": provider_resolution_error,
                "tone": "critical",
            }
        )

    provider_candidate_items = [
        {
            "label": item.get("provider_id", "unknown"),
            "value": f"{item.get('kind', 'unknown')} @ {item.get('execution_location', 'unknown')}",
            "score": item.get("score", 0),
            "health_status": item.get("health_status", "unknown"),
            "tone": (
                "positive" if item.get("health_status") == "available" else "warning"
            ),
        }
        for item in provider_candidates
    ]

    actions = build_focus_actions(focus_task)
    active_workspace_id = compositor_summary.get("active_workspace_id")
    active_output_id = compositor_summary.get("active_output_id")
    workspace_window_counts = compositor_summary.get("workspace_window_counts") or {}
    current_workspace_windows = [
        item
        for item in compositor_summary.get("managed_windows", [])
        if item.get("workspace_id") == active_workspace_id
    ]
    minimized_windows = [
        item for item in compositor_summary.get("managed_windows", []) if item.get("minimized")
    ]
    workspace_items = [
        {
            "label": "window_manager_status",
            "value": compositor_summary.get("window_manager_status") or "unavailable",
            "tone": "warning" if compositor_summary.get("data_status") != "ready" else "neutral",
        },
        {
            "label": "runtime_phase",
            "value": compositor_summary.get("runtime_phase") or "unknown",
            "tone": "neutral",
        },
        {
            "label": "active_workspace",
            "value": active_workspace_id or "workspace-1",
            "tone": "positive",
        },
        {
            "label": "active_output",
            "value": active_output_id or "-",
            "tone": "neutral",
        },
        {
            "label": "workspace_count",
            "value": compositor_summary.get("workspace_count", 1),
            "tone": "neutral",
        },
        {
            "label": "workspace_windows",
            "value": workspace_window_counts.get(active_workspace_id or "workspace-1", 0),
            "tone": "neutral",
        },
        {
            "label": "minimized_windows",
            "value": compositor_summary.get("minimized_window_count", 0),
            "tone": "warning" if compositor_summary.get("minimized_window_count", 0) else "neutral",
        },
    ]
    if compositor_summary.get("last_minimized_window_key"):
        workspace_items.append(
            {
                "label": "last_minimized",
                "value": compositor_summary.get("last_minimized_window_key"),
                "tone": "warning",
            }
        )
    if compositor_summary.get("last_restored_window_key"):
        workspace_items.append(
            {
                "label": "last_restored",
                "value": compositor_summary.get("last_restored_window_key"),
                "tone": "positive",
            }
        )

    workspace_window_items = [
        {
            "label": item.get("title") or item.get("app_id") or item.get("window_key") or "window",
            "value": " · ".join(
                part
                for part in (
                    item.get("window_policy") or "workspace-window",
                    item.get("output_id") or "display-1",
                    "minimized" if item.get("minimized") else ("visible" if item.get("visible") else "hidden"),
                )
                if part
            ),
            "tone": "warning" if item.get("minimized") else "neutral",
        }
        for item in current_workspace_windows
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
        }
        for item in minimized_windows
    ]

    return {
        "component_id": "task-surface",
        "panel_id": "task-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Task Panel",
            "subtitle": (
                f"session {session_id or '-'} · {summary['total']} tasks"
                + (f" · {active_workspace_id}" if active_workspace_id else "")
                + (f" @ {active_output_id}" if active_output_id else "")
            ),
            "status": focus_task.get("state") if focus_task else "idle",
            "tone": tone_for(focus_task.get("state") if focus_task else None),
        },
        "badges": [
            {"label": "Total", "value": summary["total"], "tone": "neutral"},
            {
                "label": "Focus",
                "value": (focus_task or {}).get("task_id", "none"),
                "tone": tone_for((focus_task or {}).get("state")),
            },
            {"label": "States", "value": len(summary["by_state"]), "tone": "neutral"},
            {
                "label": "Provider",
                "value": selected_provider.get("provider_id", "unresolved"),
                "tone": "positive" if selected_provider else ("warning" if capability_id else "neutral"),
            },
            {
                "label": "Workspace",
                "value": active_workspace_id or "-",
                "tone": "positive" if active_workspace_id else "neutral",
            },
            {
                "label": "Windows",
                "value": compositor_summary.get("managed_window_count", 0),
                "tone": "neutral",
            },
            {
                "label": "Minimized",
                "value": compositor_summary.get("minimized_window_count", 0),
                "tone": "warning" if compositor_summary.get("minimized_window_count", 0) else "neutral",
            },
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "tasks",
                "title": "Tasks",
                "items": task_items,
                "empty_state": "No tasks in session",
            },
            {
                "section_id": "focus-task",
                "title": "Focus Task",
                "items": focus_items,
                "empty_state": "No focus task available",
            },
            {
                "section_id": "plan",
                "title": "Focus Plan",
                "items": plan_steps,
                "empty_state": "No plan steps available",
            },
            {
                "section_id": "recent-events",
                "title": "Recent Events",
                "items": event_items,
                "empty_state": "No recent task events",
            },
            {
                "section_id": "provider-route",
                "title": "Provider Route",
                "items": provider_route_items,
                "empty_state": "No provider resolution available",
            },
            {
                "section_id": "provider-candidates",
                "title": "Provider Candidates",
                "items": provider_candidate_items,
                "empty_state": "No provider candidates available",
            },
            {
                "section_id": "workspace-overview",
                "title": "Workspace Overview",
                "items": workspace_items,
                "empty_state": "No compositor workspace summary",
            },
            {
                "section_id": "workspace-windows",
                "title": "Workspace Windows",
                "items": workspace_window_items,
                "empty_state": "No windows in the active workspace",
            },
            {
                "section_id": "minimized-windows",
                "title": "Minimized Windows",
                "items": minimized_window_items,
                "empty_state": "No minimized windows",
            },
        ],
        "meta": {
            "session_id": session_id,
            "focus_task_id": (focus_task or {}).get("task_id"),
            "focus_task_title": (focus_task or {}).get("title"),
            "focus_task_state": (focus_task or {}).get("state"),
            "task_count": len(tasks),
            "plan_step_count": len(plan_steps),
            "task_event_count": len(task_events),
            "recent_task_event_states": [event.get("to_state") for event in task_events],
            "state_summary": summary["by_state"],
            "plan_summary": plan.get("summary"),
            "plan_route_preference": plan.get("route_preference"),
            "plan_next_action": plan.get("next_action"),
            "primary_capability": capability_id,
            "provider_selected_id": selected_provider.get("provider_id"),
            "provider_health_status": selected_provider.get("health_status"),
            "provider_candidate_count": len(provider_candidates),
            "provider_resolution_reason": (provider_resolution or {}).get("reason"),
            "provider_resolution_error": provider_resolution_error,
            "compositor_data_status": compositor_summary.get("data_status"),
            "compositor_data_error": compositor_summary.get("data_error"),
            "compositor_window_manager_status": compositor_summary.get("window_manager_status"),
            "compositor_runtime_phase": compositor_summary.get("runtime_phase"),
            "compositor_runtime_state_status": compositor_summary.get("runtime_state_status"),
            "compositor_runtime_state_path": compositor_summary.get("runtime_state_path"),
            "compositor_window_state_path": compositor_summary.get("window_state_path"),
            "workspace_count": compositor_summary.get("workspace_count", 1),
            "active_workspace_index": compositor_summary.get("active_workspace_index", 0),
            "active_workspace_id": active_workspace_id,
            "active_output_id": active_output_id,
            "output_count": compositor_summary.get("output_count", 0),
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
            "workspace_window_counts": workspace_window_counts,
            "data_source_status": "ready" if data_source_error is None else "fallback-empty",
            "data_source_error": data_source_error,
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    lines.append(
        "badges: " + ", ".join(f"{item['label']}: {item['value']}" for item in panel["badges"])
    )
    meta = panel.get("meta") or {}
    if meta.get("data_source_status") != "ready":
        lines.append(f"source: {meta.get('data_source_status')}")
        if meta.get("data_source_error"):
            lines.append(f"source_error: {meta['data_source_error']}")
    if panel["actions"]:
        lines.append(
            "actions: "
            + ", ".join(
                action["label"] for action in panel["actions"] if action.get("enabled", True)
            )
        )
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if items:
            for item in items:
                label = item.get("label") or item.get("task_id") or item.get("step_id")
                suffix = item.get("state") or item.get("status")
                if section["section_id"] == "provider-candidates":
                    lines.append(
                        f"- {label}: {item['value']} score={item.get('score', 0)} health={item.get('health_status', 'unknown')}"
                    )
                elif section["section_id"] == "tasks":
                    lines.append(
                        f"- {label}: {item.get('state')} task_id={item.get('task_id')} created_at={item.get('created_at')}"
                    )
                elif section["section_id"] == "recent-events":
                    lines.append(
                        f"- {label}: {item.get('value')} reason={item.get('detail')} at={item.get('created_at')}"
                    )
                elif suffix:
                    lines.append(f"- {label}: {suffix}")
                else:
                    lines.append(f"- {label}: {item.get('value')}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS task surface panel")
    parser.add_argument(
        "command",
        nargs="?",
        default="render",
        choices=["render", "model", "action", "watch"],
    )
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--state")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--event-limit", type=int, default=5)
    parser.add_argument("--new-state")
    parser.add_argument("--reason")
    parser.add_argument("--action")
    parser.add_argument("--compositor-runtime-state", type=Path, default=default_compositor_runtime_state())
    parser.add_argument("--compositor-window-state", type=Path, default=default_compositor_window_state())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.task_id:
            raise SystemExit("--task-id is required for action")
        target_state = args.new_state
        if not target_state:
            if args.action == "approve-task":
                target_state = "approved"
            elif args.action == "start-task":
                target_state = "executing"
            elif args.action == "complete-task":
                target_state = "completed"
            elif args.action == "fail-task":
                target_state = "failed"
            elif args.action == "cancel-task":
                target_state = "cancelled"
            elif args.action == "replan-task":
                target_state = "replanned"
            else:
                raise SystemExit("--new-state is required for custom action")
        result = update_task_state(
            args.agent_socket,
            args.fixture,
            args.task_id,
            target_state,
            args.reason,
        )
        result["target_component"] = "task-surface"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if not args.session_id:
        raise SystemExit("--session-id is required")

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            tasks_result, data_source_error = load_tasks_with_fallback(
                args.agent_socket, args.fixture, args.session_id, args.state, args.limit
            )
            focus_task_id = args.task_id or (tasks_result.get("tasks") or [{}])[0].get("task_id")
            if data_source_error is None:
                focus_task = next(
                    (item for item in tasks_result.get("tasks", []) if item.get("task_id") == focus_task_id),
                    None,
                ) or get_task(args.agent_socket, args.fixture, focus_task_id)
                plan_result = get_plan(args.agent_socket, args.fixture, focus_task_id)
                task_events_result = list_task_events(
                    args.agent_socket,
                    args.fixture,
                    focus_task_id,
                    args.event_limit,
                )
                provider_resolution, capability_id, provider_resolution_error = resolve_provider(
                    args.agent_socket,
                    args.fixture,
                    focus_task_id,
                    plan_result,
                )
            else:
                focus_task = None
                plan_result = None
                task_events_result = {"events": []}
                provider_resolution = None
                capability_id = None
                provider_resolution_error = None
            compositor_summary = load_compositor_summary(
                args.compositor_runtime_state,
                args.compositor_window_state,
            )
            model = build_model(
                tasks_result,
                focus_task,
                plan_result,
                task_events_result,
                args.session_id,
                provider_resolution,
                provider_resolution_error,
                capability_id,
                compositor_summary,
                data_source_error,
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

    tasks_result, data_source_error = load_tasks_with_fallback(
        args.agent_socket,
        args.fixture,
        args.session_id,
        args.state,
        args.limit,
    )
    focus_task_id = args.task_id or (tasks_result.get("tasks") or [{}])[0].get("task_id")
    if data_source_error is None:
        focus_task = next(
            (item for item in tasks_result.get("tasks", []) if item.get("task_id") == focus_task_id),
            None,
        ) or get_task(args.agent_socket, args.fixture, focus_task_id)
        plan_result = get_plan(args.agent_socket, args.fixture, focus_task_id)
        task_events_result = list_task_events(
            args.agent_socket,
            args.fixture,
            focus_task_id,
            args.event_limit,
        )
        provider_resolution, capability_id, provider_resolution_error = resolve_provider(
            args.agent_socket,
            args.fixture,
            focus_task_id,
            plan_result,
        )
    else:
        focus_task = None
        plan_result = None
        task_events_result = {"events": []}
        provider_resolution = None
        capability_id = None
        provider_resolution_error = None
    compositor_summary = load_compositor_summary(
        args.compositor_runtime_state,
        args.compositor_window_state,
    )
    model = build_model(
        tasks_result,
        focus_task,
        plan_result,
        task_events_result,
        args.session_id,
        provider_resolution,
        provider_resolution_error,
        capability_id,
        compositor_summary,
        data_source_error,
    )
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

