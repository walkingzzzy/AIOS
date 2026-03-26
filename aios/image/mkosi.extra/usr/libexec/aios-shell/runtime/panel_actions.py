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
    elif component == "system-assistant":
        session_id = action_value(surface, action, "session_id", "resolved_session_id")
        if session_id:
            command.extend(["--session-id", str(session_id)])
        user_id = action_value(surface, action, "user_id")
        if user_id:
            command.extend(["--user-id", str(user_id)])
        intent = action_value(surface, action, "intent", "request_intent")
        if intent:
            command.extend(["--intent", str(intent)])
        title = action_value(surface, action, "title", "request_title")
        if title:
            command.extend(["--title", str(title)])
        task_state = action_value(surface, action, "task_state")
        if task_state:
            command.extend(["--task-state", str(task_state)])
        approval_lane = action_value(surface, action, "approval_lane")
        if approval_lane:
            command.extend(["--approval-lane", str(approval_lane)])
        capability_id = action_value(surface, action, "capability_id")
        if capability_id:
            command.extend(["--capability-id", str(capability_id)])
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
    elif component == "model-library":
        source_path = action_value(surface, action, "source_path", "import_source_path")
        if source_path:
            command.extend(["--source-path", str(source_path)])
        model_id = action_value(surface, action, "model_id", "focus_model_id")
        if model_id:
            command.extend(["--model-id", str(model_id)])
        capability = action_value(surface, action, "capability")
        if capability:
            command.extend(["--capability", str(capability)])
        for alias in action.get("aliases", []) or []:
            command.extend(["--alias", str(alias)])
        for capability_item in action.get("capabilities", []) or []:
            if capability_item == capability:
                continue
            command.extend(["--capability", str(capability_item)])
        if action.get("set_default"):
            command.append("--set-default")
        if action.get("symlink"):
            command.append("--symlink")
        if action.get("keep_file"):
            command.append("--keep-file")
        quantization = action_value(surface, action, "quantization")
        if quantization:
            command.extend(["--quantization", str(quantization)])
        parameters_estimate = action_value(surface, action, "parameters_estimate")
        if parameters_estimate:
            command.extend(["--parameters-estimate", str(parameters_estimate)])
    elif component == "provider-settings":
        provider_enabled = action.get("provider_enabled")
        if provider_enabled is True:
            command.append("--provider-enabled")
        elif provider_enabled is False:
            command.append("--provider-disabled")
        ai_mode = action_value(surface, action, "ai_mode")
        if ai_mode:
            command.extend(["--ai-mode", str(ai_mode)])
        route_preference = action_value(surface, action, "route_preference")
        if route_preference:
            command.extend(["--route-preference", str(route_preference)])
        privacy_profile = action_value(surface, action, "privacy_profile")
        if privacy_profile:
            command.extend(["--privacy-profile", str(privacy_profile)])
        endpoint_base_url = action_value(surface, action, "endpoint_base_url")
        if endpoint_base_url:
            command.extend(["--endpoint-base-url", str(endpoint_base_url)])
        endpoint_model = action_value(surface, action, "endpoint_model")
        if endpoint_model:
            command.extend(["--endpoint-model", str(endpoint_model)])
        api_key = action_value(surface, action, "api_key")
        if api_key:
            command.extend(["--api-key", str(api_key)])
        if action.get("clear_api_key"):
            command.append("--clear-api-key")
        if action.get("clear_remote_endpoint"):
            command.append("--clear-remote-endpoint")
        if action.get("use_onboarding_endpoint"):
            command.append("--use-onboarding-endpoint")
    elif component == "privacy-memory":
        memory_enabled = action.get("memory_enabled")
        if memory_enabled is True:
            command.append("--memory-enabled")
        elif memory_enabled is False:
            command.append("--memory-disabled")
        memory_retention_days = action_value(surface, action, "memory_retention_days")
        if memory_retention_days not in (None, ""):
            command.extend(["--memory-retention-days", str(memory_retention_days)])
        audit_retention_days = action_value(surface, action, "audit_retention_days")
        if audit_retention_days not in (None, ""):
            command.extend(["--audit-retention-days", str(audit_retention_days)])
        approval_policy = action_value(surface, action, "approval_default_policy")
        if approval_policy:
            command.extend(["--approval-policy", str(approval_policy)])
        remote_prompt_level = action_value(surface, action, "remote_prompt_level")
        if remote_prompt_level:
            command.extend(["--remote-prompt-level", str(remote_prompt_level)])

    if component in {"launcher", "task-surface"}:
        for flag, keys in (
            ("--window-key", ("window_key",)),
            ("--workspace-id", ("workspace_id", "active_workspace_id")),
            ("--output-id", ("output_id", "active_output_id")),
        ):
            value = action_value(surface, action, *keys)
            if value not in (None, ""):
                command.extend([flag, str(value)])

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
        if result.get("window_action"):
            window_key = result.get("window_key") or result.get("restored_window_key") or "window"
            workspace_id = result.get("workspace_id") or result.get("active_workspace_id")
            output_id = result.get("output_id") or result.get("active_output_id")
            details = [window_key]
            if workspace_id:
                details.append(str(workspace_id))
            if output_id:
                details.append(str(output_id))
            return f"{label}: {' · '.join(details)} [{result.get('window_action')}]"
        task_id = result.get("task_id") or (result.get("task") or {}).get("task_id")
        if task_id:
            state = result.get("state") or result.get("new_state")
            if state:
                return f"{label}: {task_id} -> {state}"
            return f"{label}: updated {task_id}"

    if component == "launcher" and result.get("window_action"):
        window_key = result.get("window_key") or result.get("restored_window_key") or "window"
        workspace_id = result.get("workspace_id") or result.get("active_workspace_id")
        output_id = result.get("output_id") or result.get("active_output_id")
        details = [window_key]
        if workspace_id:
            details.append(str(workspace_id))
        if output_id:
            details.append(str(output_id))
        return f"{label}: {' · '.join(details)} [{result.get('window_action')}]"

    if component == "approval-panel":
        approval_ref = result.get("approval_ref")
        status = result.get("status")
        if approval_ref and status:
            return f"{label}: {approval_ref} -> {status}"

    if component == "privacy-memory":
        memory_enabled = result.get("memory_enabled")
        memory_retention_days = result.get("memory_retention_days")
        audit_retention_days = result.get("audit_retention_days")
        approval_policy = result.get("approval_default_policy")
        remote_prompt_level = result.get("remote_prompt_level")
        details = [
            f"memory={'on' if memory_enabled else 'off'}" if memory_enabled is not None else None,
            (
                f"retention={memory_retention_days}d/{audit_retention_days}d"
                if memory_retention_days not in (None, "") and audit_retention_days not in (None, "")
                else None
            ),
            f"policy={approval_policy}" if approval_policy else None,
            f"remote_prompt={remote_prompt_level}" if remote_prompt_level else None,
        ]
        details = [item for item in details if item]
        if details:
            return f"{label}: {' '.join(details)}"

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

