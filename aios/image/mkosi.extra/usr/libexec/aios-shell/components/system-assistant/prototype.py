#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


_AI_CENTER_PROTOTYPE_MODULE: ModuleType | None = None
_PROVIDER_SETTINGS_PROTOTYPE_MODULE: ModuleType | None = None
_PRIVACY_MEMORY_PROTOTYPE_MODULE: ModuleType | None = None
_LAUNCHER_PROTOTYPE_MODULE: ModuleType | None = None
_LAUNCHER_PANEL_MODULE: ModuleType | None = None
_APPROVAL_PROTOTYPE_MODULE: ModuleType | None = None

HIGH_RISK_RULES = (
    {
        "category": "device-capture-screen",
        "capability_id": "device.capture.screen.read",
        "reason": "请求涉及屏幕捕获或屏幕共享",
        "keywords": (
            "screen",
            "screenshot",
            "screen share",
            "record screen",
            "capture screen",
            "录屏",
            "屏幕",
            "截图",
            "屏幕共享",
        ),
    },
    {
        "category": "device-capture-audio",
        "capability_id": "device.capture.audio",
        "reason": "请求涉及麦克风或音频捕获",
        "keywords": (
            "microphone",
            "mic",
            "record audio",
            "capture audio",
            "listen",
            "麦克风",
            "录音",
            "音频",
        ),
    },
    {
        "category": "device-capture-camera",
        "capability_id": "device.capture.camera",
        "reason": "请求涉及摄像头或图像采集",
        "keywords": (
            "camera",
            "webcam",
            "take photo",
            "摄像头",
            "拍照",
            "相机",
        ),
    },
    {
        "category": "storage-destructive",
        "capability_id": "system.storage.destructive",
        "reason": "请求涉及删除、擦除、格式化或回滚等破坏性操作",
        "keywords": (
            "delete",
            "remove",
            "wipe",
            "erase",
            "format",
            "destroy",
            "purge",
            "rollback",
            "删除",
            "移除",
            "擦除",
            "格式化",
            "销毁",
            "清空",
            "回滚",
        ),
    },
    {
        "category": "power-lifecycle",
        "capability_id": "system.power.lifecycle",
        "reason": "请求涉及重启、关机或恢复流程",
        "keywords": (
            "shutdown",
            "power off",
            "reboot",
            "restart",
            "recovery",
            "关机",
            "重启",
            "恢复模式",
        ),
    },
    {
        "category": "remote-transfer",
        "capability_id": "compat.remote.transfer",
        "reason": "请求涉及导出、上传、分享或向外部端点发送数据",
        "keywords": (
            "upload",
            "export",
            "share",
            "send",
            "publish",
            "sync",
            "cloud",
            "remote endpoint",
            "external",
            "上传",
            "导出",
            "分享",
            "发送",
            "云端",
            "远程",
            "外部",
        ),
    },
    {
        "category": "software-management",
        "capability_id": "system.software.manage",
        "reason": "请求涉及安装、卸载或变更系统软件",
        "keywords": (
            "install",
            "uninstall",
            "upgrade package",
            "apt ",
            "pip ",
            "npm ",
            "安装",
            "卸载",
            "升级软件",
            "安装包",
        ),
    },
)
SESSION_LIST_LIMIT = 6


def _load_module(module_name: str, path: Path) -> ModuleType:
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_ai_center_prototype_module() -> ModuleType:
    global _AI_CENTER_PROTOTYPE_MODULE
    if _AI_CENTER_PROTOTYPE_MODULE is not None:
        return _AI_CENTER_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "ai-center" / "prototype.py"
    _AI_CENTER_PROTOTYPE_MODULE = _load_module("aios_shell_ai_center_prototype", module_path)
    return _AI_CENTER_PROTOTYPE_MODULE


def load_provider_settings_prototype_module() -> ModuleType:
    global _PROVIDER_SETTINGS_PROTOTYPE_MODULE
    if _PROVIDER_SETTINGS_PROTOTYPE_MODULE is not None:
        return _PROVIDER_SETTINGS_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "provider-settings" / "prototype.py"
    _PROVIDER_SETTINGS_PROTOTYPE_MODULE = _load_module(
        "aios_shell_provider_settings_prototype",
        module_path,
    )
    return _PROVIDER_SETTINGS_PROTOTYPE_MODULE


def load_privacy_memory_prototype_module() -> ModuleType:
    global _PRIVACY_MEMORY_PROTOTYPE_MODULE
    if _PRIVACY_MEMORY_PROTOTYPE_MODULE is not None:
        return _PRIVACY_MEMORY_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "privacy-memory" / "prototype.py"
    _PRIVACY_MEMORY_PROTOTYPE_MODULE = _load_module(
        "aios_shell_privacy_memory_prototype",
        module_path,
    )
    return _PRIVACY_MEMORY_PROTOTYPE_MODULE


def load_launcher_prototype_module() -> ModuleType:
    global _LAUNCHER_PROTOTYPE_MODULE
    if _LAUNCHER_PROTOTYPE_MODULE is not None:
        return _LAUNCHER_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "launcher" / "prototype.py"
    _LAUNCHER_PROTOTYPE_MODULE = _load_module("aios_shell_launcher_prototype", module_path)
    return _LAUNCHER_PROTOTYPE_MODULE


def load_launcher_panel_module() -> ModuleType:
    global _LAUNCHER_PANEL_MODULE
    if _LAUNCHER_PANEL_MODULE is not None:
        return _LAUNCHER_PANEL_MODULE
    module_path = Path(__file__).resolve().parents[1] / "launcher" / "panel.py"
    _LAUNCHER_PANEL_MODULE = _load_module("aios_shell_launcher_panel", module_path)
    return _LAUNCHER_PANEL_MODULE


def load_approval_prototype_module() -> ModuleType:
    global _APPROVAL_PROTOTYPE_MODULE
    if _APPROVAL_PROTOTYPE_MODULE is not None:
        return _APPROVAL_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "approval-panel" / "prototype.py"
    _APPROVAL_PROTOTYPE_MODULE = _load_module("aios_shell_approval_prototype", module_path)
    return _APPROVAL_PROTOTYPE_MODULE


def default_agent_socket() -> Path:
    return load_launcher_prototype_module().default_agent_socket()


def default_ai_readiness_path() -> Path:
    return load_ai_center_prototype_module().default_ai_readiness_path()


def default_ai_onboarding_report_path() -> Path:
    return load_ai_center_prototype_module().default_ai_onboarding_report_path()


def default_model_dir() -> Path:
    return load_ai_center_prototype_module().default_model_dir()


def default_model_registry() -> Path:
    return load_ai_center_prototype_module().default_model_registry()


def default_runtime_platform_env_path() -> Path:
    return load_privacy_memory_prototype_module().default_runtime_platform_env_path()


def default_task_fixture() -> Path | None:
    value = os.environ.get("AIOS_SHELL_TASK_FIXTURE")
    if not value:
        return None
    return Path(value)


def normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def sort_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        sessions,
        key=lambda item: (
            item.get("last_resumed_at") or item.get("created_at") or "",
            item.get("created_at") or "",
        ),
        reverse=True,
    )


def sort_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tasks, key=lambda item: item.get("created_at") or "", reverse=True)


def load_launcher_fixture_state(path: Path, session_id: str | None) -> dict[str, Any]:
    launcher_module = load_launcher_prototype_module()
    payload = launcher_module.load_fixture(path)
    sessions = sort_sessions(list(payload.get("sessions", [])))
    all_tasks = sort_tasks(list(payload.get("tasks", [])))
    focus_session = None
    if session_id:
        focus_session = next(
            (item for item in sessions if item.get("session_id") == session_id),
            None,
        )
    elif sessions:
        focus_session = sessions[0]
    focus_tasks = all_tasks
    if focus_session is not None:
        focus_tasks = [
            item
            for item in all_tasks
            if item.get("session_id") == focus_session.get("session_id")
        ]
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


def load_launcher_live_state(agent_socket_path: Path, session_id: str | None) -> dict[str, Any]:
    launcher_module = load_launcher_prototype_module()
    sessions: list[dict[str, Any]] = []
    focus_session = None
    recovery = None
    tasks: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        sessions_result = launcher_module.rpc_call(
            agent_socket_path,
            "agent.session.list",
            {"limit": SESSION_LIST_LIMIT},
        )
        sessions = sort_sessions(list(sessions_result.get("sessions", [])))
    except Exception as error:
        errors.append(str(error))

    focus_session_id = session_id or ((sessions[0] if sessions else {}).get("session_id"))
    if focus_session_id:
        try:
            evidence = launcher_module.rpc_call(
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
            errors.append(str(error))

    if focus_session is not None and not any(
        item.get("session_id") == focus_session.get("session_id") for item in sessions
    ):
        sessions = sort_sessions([focus_session, *sessions])

    if errors:
        data_source_status = (
            "partial"
            if sessions or focus_session is not None or tasks
            else "fallback-empty"
        )
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


def load_task_fixture_state(path: Path | None, session_id: str | None) -> tuple[list[dict[str, Any]], str | None]:
    if path is None:
        return [], None
    if not path.exists():
        return [], f"missing:{path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [], str(error)
    tasks = [item for item in payload.get("tasks", []) if isinstance(item, dict)]
    if session_id:
        tasks = [item for item in tasks if item.get("session_id") == session_id]
    tasks = sorted(tasks, key=lambda item: item.get("created_at") or "", reverse=True)
    return tasks, None


def write_task_fixture_record(path: Path | None, task: dict[str, Any]) -> None:
    if path is None:
        return
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    else:
        payload = {}
    tasks = [item for item in payload.get("tasks", []) if isinstance(item, dict)]
    tasks = [item for item in tasks if item.get("task_id") != task.get("task_id")]
    tasks.append(task)
    payload["tasks"] = tasks
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_launcher_tasks(
    launcher_state: dict[str, Any],
    task_fixture_path: Path | None,
    session_id: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    fixture_tasks, fixture_error = load_task_fixture_state(task_fixture_path, session_id)
    if fixture_tasks:
        return fixture_tasks, fixture_error
    return list(launcher_state.get("tasks", [])), fixture_error


def list_approvals(
    agent_socket_path: Path,
    approval_fixture: Path | None,
    session_id: str | None,
    task_id: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if approval_fixture is not None:
        args = argparse.Namespace(
            session_id=session_id,
            task_id=task_id,
            status=status,
            approval_ref=None,
        )
        try:
            result = load_approval_prototype_module().fixture_call(approval_fixture, "list", args)
        except Exception as error:
            return [], str(error)
        return list(result.get("approvals", [])), None
    try:
        result = load_approval_prototype_module().rpc_call(
            agent_socket_path,
            "agent.approval.list",
            {"session_id": session_id, "task_id": task_id, "status": status},
        )
    except Exception as error:
        return [], str(error)
    return list(result.get("approvals", [])), None


def create_session_request(
    agent_socket_path: Path,
    fixture: Path | None,
    task_fixture_path: Path | None,
    *,
    user_id: str,
    intent: str,
) -> dict[str, Any]:
    if fixture is not None:
        args = argparse.Namespace(
            user_id=user_id,
            intent=intent,
            session_id=None,
            title=None,
            state="planned",
        )
        result = load_launcher_prototype_module().fixture_call(fixture, "create-session", args)
        task = result.get("task")
        if isinstance(task, dict):
            write_task_fixture_record(task_fixture_path, task)
        return result
    return load_launcher_prototype_module().rpc_call(
        agent_socket_path,
        "agent.session.create",
        {"user_id": user_id, "metadata": {"initial_intent": intent}},
    )


def create_task_request(
    agent_socket_path: Path,
    fixture: Path | None,
    task_fixture_path: Path | None,
    *,
    session_id: str,
    title: str,
    state: str,
) -> dict[str, Any]:
    if fixture is not None:
        args = argparse.Namespace(
            session_id=session_id,
            title=title,
            state=state,
        )
        result = load_launcher_prototype_module().fixture_call(fixture, "create-task", args)
        task = result.get("task")
        if isinstance(task, dict):
            write_task_fixture_record(task_fixture_path, task)
        return result
    return load_launcher_prototype_module().rpc_call(
        agent_socket_path,
        "agent.task.create",
        {"session_id": session_id, "title": title, "state": state},
    )


def resume_session_request(
    agent_socket_path: Path,
    fixture: Path | None,
    *,
    session_id: str,
) -> dict[str, Any]:
    if fixture is not None:
        args = argparse.Namespace(session_id=session_id)
        return load_launcher_prototype_module().fixture_call(fixture, "resume", args)
    return load_launcher_prototype_module().rpc_call(
        agent_socket_path,
        "agent.session.resume",
        {"session_id": session_id},
    )


def create_approval_request(
    agent_socket_path: Path,
    approval_fixture: Path | None,
    *,
    user_id: str,
    session_id: str,
    task_id: str,
    capability_id: str,
    approval_lane: str,
    reason: str,
) -> dict[str, Any]:
    if approval_fixture is not None:
        args = argparse.Namespace(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            capability_id=capability_id,
            approval_lane=approval_lane,
            execution_location="local",
            status="pending",
            reason=reason,
        )
        return load_approval_prototype_module().fixture_call(approval_fixture, "create", args)
    return load_approval_prototype_module().rpc_call(
        agent_socket_path,
        "agent.approval.create",
        {
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "approval_lane": approval_lane,
            "execution_location": "local",
            "reason": reason,
        },
    )


def analyze_request(intent: str) -> dict[str, Any]:
    normalized = normalize_text(intent)
    lowered = normalized.lower()
    matched_rules: list[dict[str, Any]] = []
    for rule in HIGH_RISK_RULES:
        for keyword in rule["keywords"]:
            if keyword in lowered or keyword in normalized:
                matched_rules.append(rule)
                break
    if not normalized:
        return {
            "intent": "",
            "risk_level": "idle",
            "risk_label": "No Request",
            "approval_required": False,
            "route_target_component": "system-assistant",
            "route_reason": "request-missing",
            "capability_id": None,
            "risk_categories": [],
            "risk_reasons": [],
        }
    if not matched_rules:
        return {
            "intent": normalized,
            "risk_level": "standard",
            "risk_label": "Standard",
            "approval_required": False,
            "route_target_component": "task-surface",
            "route_reason": "standard-request",
            "capability_id": None,
            "risk_categories": [],
            "risk_reasons": [],
        }
    primary_rule = matched_rules[0]
    return {
        "intent": normalized,
        "risk_level": "high",
        "risk_label": "Approval Required",
        "approval_required": True,
        "route_target_component": "approval-panel",
        "route_reason": "high-risk-request",
        "capability_id": primary_rule["capability_id"],
        "risk_categories": [rule["category"] for rule in matched_rules],
        "risk_reasons": [rule["reason"] for rule in matched_rules],
    }


def build_system_assistant_state(
    ai_readiness_path: Path | None,
    ai_onboarding_report_path: Path | None,
    model_dir: Path | None,
    model_registry: Path | None,
    runtime_platform_env_path: Path | None,
    agent_socket_path: Path | None,
    fixture: Path | None,
    task_fixture_path: Path | None,
    approval_fixture: Path | None,
    session_id: str | None,
    intent: str,
) -> dict[str, Any]:
    ai_state = load_ai_center_prototype_module().build_ai_center_state(
        ai_readiness_path,
        ai_onboarding_report_path,
        model_dir,
        model_registry,
    )
    provider_state = load_provider_settings_prototype_module().build_provider_settings_state(
        ai_readiness_path,
        ai_onboarding_report_path,
        runtime_platform_env_path,
    )
    privacy_state = load_privacy_memory_prototype_module().build_privacy_memory_state(
        runtime_platform_env_path,
    )
    effective_agent_socket = agent_socket_path or default_agent_socket()
    if fixture is not None:
        launcher_state = load_launcher_fixture_state(fixture, session_id)
    else:
        launcher_state = load_launcher_live_state(effective_agent_socket, session_id)
    focus_session = launcher_state.get("focus_session") or {}
    resolved_session_id = session_id or focus_session.get("session_id")
    tasks, task_fixture_error = merge_launcher_tasks(
        launcher_state,
        task_fixture_path,
        resolved_session_id,
    )
    approvals, approvals_error = list_approvals(
        effective_agent_socket,
        approval_fixture,
        resolved_session_id,
    )
    pending_approvals = [
        item for item in approvals if item.get("status") == "pending"
    ]
    request = analyze_request(intent)
    diagnostics: list[str] = []
    diagnostics.extend(list(ai_state.get("diagnostics") or []))
    diagnostics.extend(list(provider_state.get("diagnostics") or []))
    diagnostics.extend(list(privacy_state.get("diagnostics") or []))
    if launcher_state.get("data_source_error"):
        diagnostics.append(f"session_source={launcher_state['data_source_error']}")
    if task_fixture_error:
        diagnostics.append(f"task_fixture={task_fixture_error}")
    if approvals_error:
        diagnostics.append(f"approval_source={approvals_error}")
    if request.get("approval_required"):
        diagnostics.append(
            "assistant_route=approval-panel("
            + ",".join(request.get("risk_categories") or [])
            + ")"
        )
    elif request.get("intent"):
        diagnostics.append("assistant_route=task-surface(standard-request)")

    return {
        "ai_state": ai_state,
        "provider_state": provider_state,
        "privacy_state": privacy_state,
        "launcher_state": launcher_state,
        "focus_session": focus_session,
        "resolved_session_id": resolved_session_id,
        "tasks": tasks,
        "approvals": approvals,
        "pending_approvals": pending_approvals,
        "request": request,
        "diagnostics": diagnostics,
    }


def render_state(state: dict[str, Any]) -> str:
    ai_state = state.get("ai_state") or {}
    readiness = ai_state.get("readiness") or {}
    provider_state = state.get("provider_state") or {}
    privacy_state = state.get("privacy_state") or {}
    request = state.get("request") or {}
    lines = [
        f"request: {request.get('intent') or '-'}",
        f"risk_level: {request.get('risk_label')}",
        f"resolved_session_id: {state.get('resolved_session_id') or '-'}",
        f"pending_approvals: {len(state.get('pending_approvals') or [])}",
        f"ai_readiness: {readiness.get('state_label') or 'Unknown'}",
        f"default_text_model: {ai_state.get('default_text_generation_model') or '-'}",
        f"route_preference: {provider_state.get('route_preference_label') or 'Unknown'}",
        f"approval_policy: {privacy_state.get('approval_default_policy_label') or 'Unknown'}",
    ]
    for item in state.get("diagnostics", []):
        lines.append(f"diag: {item}")
    return "\n".join(lines)
