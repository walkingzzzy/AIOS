#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from typing import Any

import shellctl
from shell_snapshot import panel_context_args


def surface_for_component(snapshot: dict[str, Any], component: str) -> dict[str, Any] | None:
    return next(
        (item for item in snapshot.get("surfaces", []) if item.get("component") == component),
        None,
    )


def surface_meta_value(surface: dict[str, Any], *keys: str) -> Any:
    meta = (surface.get("model") or {}).get("meta") or {}
    for key in keys:
        value = meta.get(key)
        if value not in (None, ""):
            return value
    return None


def action_value(surface: dict[str, Any], action: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = action.get(key)
        if value not in (None, ""):
            return value
    return surface_meta_value(surface, *keys)


def build_action_command(
    _profile: dict[str, Any],
    args,
    component: str,
    surface: dict[str, Any],
    action: dict[str, Any],
) -> list[str]:
    context_args = panel_context_args(args, component)
    if context_args is None:
        raise ValueError(f"missing shell context for {component}")

    command = ["action", *context_args]
    action_id = action.get("action_id")
    if action_id:
        command.extend(["--action", action_id])

    if component == "launcher":
        session_id = action_value(surface, action, "session_id", "resolved_session_id")
        if session_id:
            command.extend(["--session-id", str(session_id)])
        intent = action_value(surface, action, "intent")
        if intent:
            command.extend(["--intent", str(intent)])
        target_state = action.get("target_state")
        if target_state:
            command.extend(["--state", str(target_state)])
        title = action_value(surface, action, "title") or args.title
        if title:
            command.extend(["--title", str(title)])
    elif component == "task-surface":
        task_id = action_value(surface, action, "task_id", "focus_task_id")
        if task_id:
            command.extend(["--task-id", str(task_id)])
        target_state = action.get("target_state")
        if target_state:
            command.extend(["--new-state", str(target_state)])
    elif component == "approval-panel":
        approval_ref = action_value(surface, action, "approval_ref", "focus_approval_ref")
        if approval_ref:
            command.extend(["--approval-ref", str(approval_ref)])
        target_status = action.get("target_status")
        if target_status:
            command.extend(["--status", str(target_status)])
    elif component == "recovery-surface":
        target_version = action_value(surface, action, "target_version")
        if target_version:
            command.extend(["--target-version", str(target_version)])
        recovery_id = action_value(surface, action, "recovery_id")
        if recovery_id:
            command.extend(["--recovery-id", str(recovery_id)])
        reason = action_value(surface, action, "reason")
        if reason:
            command.extend(["--reason", str(reason)])
    elif component == "portal-chooser":
        handle_id = action_value(surface, action, "handle_id", "selected_handle_id", "focus_handle_id")
        if handle_id:
            command.extend(["--handle-id", str(handle_id)])
        reason = action_value(surface, action, "reason")
        if reason:
            command.extend(["--reason", str(reason)])
    elif component == "device-backend-status" and action_id == "focus-attention":
        command.append("--attention-only")

    if component not in shellctl.COMPONENT_PANELS:
        raise ValueError(f"unsupported panel action target: {component}")
    return command


def dispatch_panel_action(
    profile: dict[str, Any],
    args,
    snapshot: dict[str, Any],
    component: str,
    action: dict[str, Any],
) -> dict[str, Any]:
    surface = surface_for_component(snapshot, component)
    if surface is None:
        raise ValueError(f"surface missing for component {component}")

    command = build_action_command(profile, args, component, surface, action)
    result = shellctl.run_panel(profile, component, command, expect_json=True)
    if not isinstance(result, dict):
        return {"component": component, "command": command, "result": {"raw_result": result}}
    return {"component": component, "command": command, "result": result}


def select_panel_action(
    snapshot: dict[str, Any],
    component: str,
    action_id: str | None = None,
) -> dict[str, Any]:
    surface = surface_for_component(snapshot, component)
    if surface is None:
        raise ValueError(f"surface missing for component {component}")
    model = surface.get("model") or {}
    actions = list(model.get("actions", []))
    if action_id:
        selected = next((item for item in actions if item.get("action_id") == action_id), None)
        if selected is None:
            raise ValueError(f"action missing for component {component}: {action_id}")
        return selected

    selected = next((item for item in actions if item.get("enabled", True)), None)
    if selected is None:
        raise ValueError(f"no enabled action available for component {component}")
    return selected


def clip_text(text: str, limit: int = 160) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3] + "..."


def summarize_action_result(component: str, action: dict[str, Any], result: dict[str, Any]) -> str:
    label = action.get("label", action.get("action_id", "Action"))
    action_id = action.get("action_id")

    if component == "launcher":
        session = result.get("session") or {}
        task = result.get("task") or {}
        if action_id == "create-session" and session.get("session_id"):
            return f"{label}: {session['session_id']} ready"
        if action_id == "resume-session" and session.get("session_id"):
            return f"{label}: resumed {session['session_id']}"
        if action_id == "create-task" and task.get("task_id"):
            return f"{label}: {task['task_id']} [{task.get('state', 'unknown')}]"

    if component == "task-surface":
        task_id = result.get("task_id") or (result.get("task") or {}).get("task_id")
        if task_id:
            state = result.get("state") or result.get("new_state")
            if state:
                return f"{label}: {task_id} -> {state}"
            return f"{label}: updated {task_id}"

    if component == "approval-panel":
        approval_ref = result.get("approval_ref")
        status = result.get("status")
        if approval_ref and status:
            return f"{label}: {approval_ref} -> {status}"

    if component == "recovery-surface":
        if result.get("overall_status"):
            return f"{label}: overall {result['overall_status']}"
        if result.get("status"):
            return f"{label}: status {result['status']}"

    if component == "portal-chooser":
        handle_id = result.get("confirmed_handle_id") or result.get("selected_handle_id")
        status = result.get("status")
        if handle_id and status:
            return f"{label}: {handle_id} [{status}]"
        if status:
            return f"{label}: {status}"

    summary_fields = [
        key
        for key in (
            "status",
            "notification_count",
            "attention_count",
            "active_count",
            "handle_count",
            "selected_handle_id",
            "confirmed_handle_id",
            "target_component",
            "session_id",
            "task_id",
            "approval_ref",
        )
        if result.get(key) not in (None, "")
    ]
    if summary_fields:
        details = " ".join(f"{key}={result[key]}" for key in summary_fields)
        return clip_text(f"{label}: {details}")

    return clip_text(f"{label}: {json.dumps(result, ensure_ascii=False)}")


def process_error_text(error: subprocess.CalledProcessError) -> str:
    return error.stderr.strip() or error.stdout.strip() or str(error)
