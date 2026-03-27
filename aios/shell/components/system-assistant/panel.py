#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from prototype import (
    build_system_assistant_state,
    create_approval_request,
    create_session_request,
    create_task_request,
    default_agent_socket,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_model_dir,
    default_model_registry,
    default_runtime_platform_env_path,
    default_task_fixture,
    resume_session_request,
)


STATUS_TONES = {
    "ready": "positive",
    "approval-required": "warning",
    "attention": "warning",
    "idle": "neutral",
}
HIDDEN_BY_REMOTE_PROMPT_POLICY = "Hidden by remote prompt policy"


def tone_for_status(status: str) -> str:
    return STATUS_TONES.get(status, "neutral")


def header_status(state: dict[str, Any]) -> str:
    request = state.get("request") or {}
    if request.get("approval_required"):
        return "approval-required"
    if state.get("pending_approvals"):
        return "attention"
    if request.get("intent"):
        return "ready"
    return "idle"


def remote_prompt_level(privacy_state: dict[str, Any]) -> str:
    value = str(privacy_state.get("remote_prompt_level") or "full").strip().lower()
    return value if value in {"full", "summary", "minimal"} else "full"


def clip_text(value: Any, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def display_request_intent(request: dict[str, Any], privacy_state: dict[str, Any]) -> str:
    intent = request.get("intent")
    if not intent:
        return "-"
    level = remote_prompt_level(privacy_state)
    if level == "minimal":
        return HIDDEN_BY_REMOTE_PROMPT_POLICY
    if level == "summary":
        return clip_text(intent, 72)
    return str(intent)


def display_request_title(
    title: str | None,
    request: dict[str, Any],
    privacy_state: dict[str, Any],
) -> str:
    resolved = title or request.get("intent")
    if not resolved:
        return "-"
    level = remote_prompt_level(privacy_state)
    if level == "minimal":
        return HIDDEN_BY_REMOTE_PROMPT_POLICY
    if level == "summary":
        return clip_text(resolved, 72)
    return str(resolved)


def display_risk_reasons(
    request: dict[str, Any],
    privacy_state: dict[str, Any],
) -> list[str]:
    reasons = [str(item) for item in request.get("risk_reasons") or [] if item]
    if not reasons:
        return []

    level = remote_prompt_level(privacy_state)
    if level == "full":
        return reasons
    if level == "summary":
        categories = [str(item) for item in request.get("risk_categories") or [] if item]
        if categories:
            return [f"High-risk category: {item}" for item in categories]
        return ["High-risk request requires approval"]
    return ["Detailed request hidden by remote prompt policy"]


def approval_reason_for_request(
    intent: str,
    request: dict[str, Any],
    privacy_state: dict[str, Any],
) -> str:
    level = remote_prompt_level(privacy_state)
    if level == "full":
        return "assistant high-risk request: " + intent

    categories = [str(item) for item in request.get("risk_categories") or [] if item]
    if level == "summary":
        category_summary = ",".join(categories) if categories else "high-risk"
        return f"assistant high-risk request summary: categories={category_summary}"

    return "assistant high-risk request (details hidden by remote prompt policy)"


def build_actions(
    state: dict[str, Any],
    user_id: str,
    title: str | None,
    task_state: str,
    approval_lane: str,
) -> list[dict[str, Any]]:
    request = state.get("request") or {}
    resolved_session_id = state.get("resolved_session_id")
    pending_approvals = list(state.get("pending_approvals") or [])
    return [
        {
            "action_id": "submit-request",
            "label": "Submit Request",
            "enabled": bool(request.get("intent")),
            "tone": "warning" if request.get("approval_required") else "positive",
            "user_id": user_id,
            "intent": request.get("intent"),
            "title": title or request.get("intent"),
            "task_state": task_state,
            "approval_lane": approval_lane,
            "capability_id": request.get("capability_id"),
        },
        {
            "action_id": "resume-session",
            "label": "Resume Session",
            "enabled": bool(resolved_session_id),
            "tone": "neutral",
            "session_id": resolved_session_id,
        },
        {
            "action_id": "open-task-surface",
            "label": "Open Task Surface",
            "enabled": bool(resolved_session_id or state.get("tasks")),
            "tone": "neutral",
            "session_id": resolved_session_id,
        },
        {
            "action_id": "open-approval-panel",
            "label": "Review Approvals",
            "enabled": bool(pending_approvals or request.get("approval_required")),
            "tone": "warning",
            "session_id": resolved_session_id,
            "approval_ref": (pending_approvals[0] if pending_approvals else {}).get("approval_ref"),
        },
        {"action_id": "open-ai-center", "label": "Open AI Center", "enabled": True, "tone": "neutral"},
        {
            "action_id": "open-provider-settings",
            "label": "Open Provider Settings",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "open-model-library",
            "label": "Open Model Library",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "open-privacy-memory",
            "label": "Open Privacy & Memory",
            "enabled": True,
            "tone": "neutral",
        },
    ]


def task_item(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": task.get("title") or task.get("task_id") or "task",
        "value": task.get("state") or "unknown",
        "detail": task.get("task_id") or "-",
        "tone": "positive" if task.get("state") in {"approved", "completed"} else "neutral",
    }


def approval_item(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": record.get("approval_ref") or "approval",
        "value": record.get("status") or "unknown",
        "detail": record.get("capability_id") or "-",
        "tone": "warning" if record.get("status") == "pending" else "neutral",
    }


def build_model(
    state: dict[str, Any],
    user_id: str,
    title: str | None,
    task_state: str,
    approval_lane: str,
) -> dict[str, Any]:
    ai_state = state.get("ai_state") or {}
    readiness = ai_state.get("readiness") or {}
    provider_state = state.get("provider_state") or {}
    privacy_state = state.get("privacy_state") or {}
    launcher_state = state.get("launcher_state") or {}
    focus_session = state.get("focus_session") or {}
    request = state.get("request") or {}
    tasks = list(state.get("tasks") or [])
    approvals = list(state.get("approvals") or [])
    pending_approvals = list(state.get("pending_approvals") or [])
    status = header_status(state)
    request_intent_display = display_request_intent(request, privacy_state)
    request_title_display = display_request_title(title, request, privacy_state)
    risk_reasons_display = display_risk_reasons(request, privacy_state)
    return {
        "component_id": "system-assistant",
        "panel_id": "system-assistant-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "System Assistant",
            "subtitle": (
                f"{ai_state.get('mode_label', 'Unknown')} | "
                f"{len(tasks)} tasks | "
                f"{len(pending_approvals)} pending approvals"
            ),
            "status": status,
            "tone": tone_for_status(status),
        },
        "badges": [
            {
                "label": "Request",
                "value": request.get("risk_label") or "No Request",
                "tone": "warning" if request.get("approval_required") else "neutral",
            },
            {
                "label": "Model",
                "value": ai_state.get("default_text_generation_model") or "-",
                "tone": "positive" if ai_state.get("default_text_generation_model") else "warning",
            },
            {
                "label": "Route",
                "value": provider_state.get("route_preference_label") or "Unknown",
                "tone": "neutral",
            },
            {
                "label": "Approvals",
                "value": len(pending_approvals),
                "tone": "warning" if pending_approvals else "neutral",
            },
            {
                "label": "Policy",
                "value": privacy_state.get("approval_default_policy_label") or "Unknown",
                "tone": "neutral",
            },
            {
                "label": "Readiness",
                "value": readiness.get("state_label") or "Unknown",
                "tone": readiness.get("tone", "neutral"),
            },
        ],
        "actions": build_actions(state, user_id, title, task_state, approval_lane),
        "sections": [
            {
                "section_id": "request",
                "title": "Request",
                "items": [
                    {"label": "user_id", "value": user_id, "tone": "neutral"},
                    {"label": "intent", "value": request_intent_display, "tone": "neutral"},
                    {"label": "task_title", "value": request_title_display, "tone": "neutral"},
                    {"label": "task_state", "value": task_state, "tone": "neutral"},
                    {
                        "label": "risk_level",
                        "value": request.get("risk_label") or "No Request",
                        "tone": "warning" if request.get("approval_required") else "neutral",
                    },
                    {
                        "label": "target_surface",
                        "value": request.get("route_target_component") or "system-assistant",
                        "tone": "neutral",
                    },
                    {
                        "label": "approval_lane",
                        "value": approval_lane,
                        "tone": "neutral",
                    },
                ]
                + [
                    {
                        "label": f"risk_reason_{index + 1}",
                        "value": value,
                        "tone": "warning",
                    }
                    for index, value in enumerate(risk_reasons_display)
                ],
                "empty_state": "No request prepared",
            },
            {
                "section_id": "ai-posture",
                "title": "AI Posture",
                "items": [
                    {
                        "label": "readiness",
                        "value": readiness.get("state_label") or "Unknown",
                        "tone": readiness.get("tone", "neutral"),
                    },
                    {
                        "label": "readiness_reason",
                        "value": readiness.get("reason") or "-",
                        "tone": readiness.get("tone", "neutral"),
                    },
                    {
                        "label": "mode",
                        "value": ai_state.get("mode_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "default_text_model",
                        "value": ai_state.get("default_text_generation_model") or "-",
                        "tone": "positive" if ai_state.get("default_text_generation_model") else "warning",
                    },
                    {
                        "label": "endpoint_model",
                        "value": readiness.get("endpoint_model") or "-",
                        "tone": "positive" if readiness.get("endpoint_model") else "neutral",
                    },
                    {
                        "label": "local_models",
                        "value": ai_state.get("effective_local_model_count", 0),
                        "tone": "positive" if ai_state.get("effective_local_model_count", 0) else "warning",
                    },
                    {
                        "label": "route_preference",
                        "value": provider_state.get("route_preference_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "provider_enabled",
                        "value": provider_state.get("provider_enabled", True),
                        "tone": "positive" if provider_state.get("provider_enabled", True) else "neutral",
                    },
                ],
                "empty_state": "No AI posture available",
            },
            {
                "section_id": "permission-posture",
                "title": "Permission Posture",
                "items": [
                    {
                        "label": "approval_default_policy",
                        "value": privacy_state.get("approval_default_policy_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "remote_prompt_level",
                        "value": privacy_state.get("remote_prompt_level_label") or "Unknown",
                        "tone": "warning" if privacy_state.get("remote_prompt_level") == "minimal" else "neutral",
                    },
                    {
                        "label": "memory_enabled",
                        "value": privacy_state.get("memory_enabled", True),
                        "tone": "positive" if privacy_state.get("memory_enabled", True) else "neutral",
                    },
                    {
                        "label": "memory_retention_days",
                        "value": privacy_state.get("memory_retention_days"),
                        "tone": "neutral",
                    },
                    {
                        "label": "audit_retention_days",
                        "value": privacy_state.get("audit_retention_days"),
                        "tone": "neutral",
                    },
                    {
                        "label": "pending_approval_count",
                        "value": len(pending_approvals),
                        "tone": "warning" if pending_approvals else "neutral",
                    },
                ],
                "empty_state": "No permission posture available",
            },
            {
                "section_id": "active-session",
                "title": "Active Session",
                "items": [] if not focus_session else [
                    {
                        "label": "session_id",
                        "value": focus_session.get("session_id"),
                        "tone": "neutral",
                    },
                    {
                        "label": "status",
                        "value": focus_session.get("status") or "unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "created_at",
                        "value": focus_session.get("created_at") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "task_count",
                        "value": len(tasks),
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No active session",
            },
            {
                "section_id": "tasks",
                "title": "Tasks",
                "items": [task_item(item) for item in tasks[:6]],
                "empty_state": "No active tasks",
            },
            {
                "section_id": "approvals",
                "title": "Approvals",
                "items": [approval_item(item) for item in approvals[:6]],
                "empty_state": "No approvals available",
            },
            {
                "section_id": "diagnostics",
                "title": "Diagnostics",
                "items": [
                    {"label": f"diag-{index + 1}", "value": item, "tone": "warning"}
                    for index, item in enumerate(state.get("diagnostics") or [])
                ],
                "empty_state": "No diagnostics",
            },
        ],
        "meta": {
            "user_id": user_id,
            "request_intent": request_intent_display,
            "request_title": request_title_display,
            "task_state": task_state,
            "risk_level": request.get("risk_level"),
            "risk_label": request.get("risk_label"),
            "risk_categories": request.get("risk_categories") or [],
            "risk_reasons": risk_reasons_display,
            "approval_required": request.get("approval_required", False),
            "approval_lane": approval_lane,
            "capability_id": request.get("capability_id"),
            "resolved_session_id": state.get("resolved_session_id"),
            "focus_task_id": (tasks[0] if tasks else {}).get("task_id"),
            "session_count": launcher_state.get("session_count", len(launcher_state.get("sessions", []))),
            "task_count": len(tasks),
            "pending_approval_count": len(pending_approvals),
            "pending_approval_ref": (pending_approvals[0] if pending_approvals else {}).get("approval_ref"),
            "default_text_generation_model": ai_state.get("default_text_generation_model"),
            "readiness_state": readiness.get("state"),
            "readiness_label": readiness.get("state_label"),
            "readiness_reason": readiness.get("reason"),
            "ai_mode": readiness.get("ai_mode"),
            "route_preference": provider_state.get("route_preference"),
            "route_preference_label": provider_state.get("route_preference_label"),
            "provider_enabled": provider_state.get("provider_enabled", True),
            "endpoint_model": provider_state.get("endpoint_model"),
            "approval_default_policy": privacy_state.get("approval_default_policy"),
            "approval_default_policy_label": privacy_state.get("approval_default_policy_label"),
            "remote_prompt_level": privacy_state.get("remote_prompt_level"),
            "remote_prompt_level_label": privacy_state.get("remote_prompt_level_label"),
            "memory_enabled": privacy_state.get("memory_enabled", True),
            "memory_retention_days": privacy_state.get("memory_retention_days"),
            "audit_retention_days": privacy_state.get("audit_retention_days"),
            "data_source_status": launcher_state.get("data_source_status", "ready"),
            "data_source_error": launcher_state.get("data_source_error"),
            "diagnostics_count": len(state.get("diagnostics") or []),
            "diagnostics": state.get("diagnostics") or [],
        },
    }


def render_text(panel: dict[str, Any]) -> str:
    lines = []
    header = panel.get("header", {})
    lines.append(f"{header.get('title', 'System Assistant')} [{header.get('status', 'unknown')}]")
    lines.append(header.get("subtitle", "-"))
    badges = panel.get("badges", [])
    if badges:
        lines.append(
            "badges: " + ", ".join(f"{item.get('label')}: {item.get('value')}" for item in badges)
        )
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
            lines.append(f"- {item.get('label', '-')}: {item.get('value', '-')}")
    return "\n".join(lines)


def current_model(args: argparse.Namespace) -> dict[str, Any]:
    state = build_system_assistant_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.model_dir,
        args.model_registry,
        args.runtime_platform_env,
        args.agent_socket,
        args.fixture,
        args.task_fixture,
        args.approval_fixture,
        args.session_id,
        args.intent,
    )
    return build_model(
        state,
        args.user_id,
        args.title,
        args.task_state,
        args.approval_lane,
    )


def route_action(action_id: str) -> str | None:
    if action_id == "open-task-surface":
        return "task-surface"
    if action_id == "open-approval-panel":
        return "approval-panel"
    if action_id == "open-ai-center":
        return "ai-center"
    if action_id == "open-provider-settings":
        return "provider-settings"
    if action_id == "open-model-library":
        return "model-library"
    if action_id == "open-privacy-memory":
        return "privacy-memory"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS system assistant panel")
    parser.add_argument(
        "command",
        nargs="?",
        default="render",
        choices=["render", "model", "action", "watch"],
    )
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--task-fixture", type=Path, default=default_task_fixture())
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--intent", default="")
    parser.add_argument("--title")
    parser.add_argument("--task-state", default="planned")
    parser.add_argument("--approval-lane", default="high-risk")
    parser.add_argument("--capability-id")
    parser.add_argument("--action")
    parser.add_argument("--ai-readiness", type=Path, default=default_ai_readiness_path())
    parser.add_argument(
        "--ai-onboarding-report",
        type=Path,
        default=default_ai_onboarding_report_path(),
    )
    parser.add_argument("--model-dir", type=Path, default=default_model_dir())
    parser.add_argument("--model-registry", type=Path, default=default_model_registry())
    parser.add_argument(
        "--runtime-platform-env",
        type=Path,
        default=default_runtime_platform_env_path(),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        model = current_model(args)
        selected = next(
            (item for item in model.get("actions", []) if item.get("action_id") == args.action),
            None,
        )
        if selected is None:
            raise SystemExit(f"unknown action: {args.action}")
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "target_component": route_action(args.action) if selected.get("enabled", False) else None,
            "target_route": None,
            "risk_level": model.get("meta", {}).get("risk_level"),
            "approval_required": model.get("meta", {}).get("approval_required", False),
            "resolved_session_id": model.get("meta", {}).get("resolved_session_id"),
            "pending_approval_count": model.get("meta", {}).get("pending_approval_count", 0),
        }
        if not selected.get("enabled", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.action == "resume-session":
            session_id = args.session_id or selected.get("session_id") or model.get("meta", {}).get("resolved_session_id")
            if not session_id:
                raise SystemExit("--session-id is required for resume-session")
            resume_result = resume_session_request(
                args.agent_socket,
                args.fixture,
                session_id=str(session_id),
            )
            session = resume_result.get("session") or {}
            recovery = resume_result.get("recovery") or {}
            result.update(
                {
                    "status": "resumed",
                    "target_component": "task-surface",
                    "session": session,
                    "recovery": recovery,
                    "resumed_session_id": session.get("session_id"),
                    "recovery_id": recovery.get("recovery_id"),
                }
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        routed_component = route_action(args.action)
        if routed_component is not None and args.action != "submit-request":
            result.update({"status": "routed", "target_component": routed_component})
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.action != "submit-request":
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        effective_intent = args.intent or selected.get("intent") or model.get("meta", {}).get("request_intent")
        if not effective_intent:
            raise SystemExit("--intent is required for submit-request")
        request_state = build_system_assistant_state(
            args.ai_readiness,
            args.ai_onboarding_report,
            args.model_dir,
            args.model_registry,
            args.runtime_platform_env,
            args.agent_socket,
            args.fixture,
            args.task_fixture,
            args.approval_fixture,
            args.session_id,
            effective_intent,
        )
        request = request_state.get("request") or {}
        privacy_state = request_state.get("privacy_state") or {}
        risk_reasons_display = display_risk_reasons(request, privacy_state)
        session_result = None
        task_result = None
        task: dict[str, Any] = {}
        effective_session_id = request_state.get("resolved_session_id")
        if effective_session_id:
            task_result = create_task_request(
                args.agent_socket,
                args.fixture,
                args.task_fixture,
                session_id=str(effective_session_id),
                title=str(args.title or selected.get("title") or effective_intent),
                state=str(args.task_state or selected.get("task_state") or "planned"),
            )
            task = task_result.get("task") or task_result
            effective_task_id = task.get("task_id")
        else:
            session_result = create_session_request(
                args.agent_socket,
                args.fixture,
                args.task_fixture,
                user_id=str(args.user_id or selected.get("user_id") or "local-user"),
                intent=str(effective_intent),
            )
            session = session_result.get("session") or {}
            task = session_result.get("task") or {}
            effective_session_id = session.get("session_id")
            effective_task_id = task.get("task_id")
            if not effective_task_id and effective_session_id:
                task_result = create_task_request(
                    args.agent_socket,
                    args.fixture,
                    args.task_fixture,
                    session_id=str(effective_session_id),
                    title=str(args.title or selected.get("title") or effective_intent),
                    state=str(args.task_state or selected.get("task_state") or "planned"),
                )
                task = task_result.get("task") or task_result
                effective_task_id = task.get("task_id")

        result.update(
            {
                "status": "submitted",
                "session": (session_result or {}).get("session"),
                "task": task,
                "session_id": effective_session_id,
                "task_id": effective_task_id,
                "route_reason": request.get("route_reason"),
                "risk_categories": request.get("risk_categories") or [],
                "risk_reasons": risk_reasons_display,
                "capability_id": args.capability_id or request.get("capability_id"),
            }
        )
        if request.get("approval_required") and effective_session_id and effective_task_id:
            approval = create_approval_request(
                args.agent_socket,
                args.approval_fixture,
                user_id=str(args.user_id or selected.get("user_id") or "local-user"),
                session_id=str(effective_session_id),
                task_id=str(effective_task_id),
                capability_id=str(args.capability_id or request.get("capability_id") or "system.assistant.request.execute"),
                approval_lane=str(args.approval_lane or selected.get("approval_lane") or "high-risk"),
                reason=approval_reason_for_request(str(effective_intent), request, privacy_state),
            )
            result.update(
                {
                    "status": "approval-required",
                    "target_component": "approval-panel",
                    "approval_required": True,
                    "approval": approval,
                    "approval_ref": approval.get("approval_ref"),
                }
            )
        else:
            result.update({"target_component": "task-surface", "approval_required": False})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            model = current_model(args)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    model = current_model(args)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
