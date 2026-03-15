#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from prototype import default_socket, fixture_call, load_fixture, rpc_call


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
    }


def load_live_state(socket_path: Path, session_id: str | None) -> dict:
    sessions: list[dict] = []
    focus_session = None
    recovery = None
    tasks: list[dict] = []

    try:
        sessions_result = rpc_call(socket_path, "session.list", {"limit": SESSION_LIST_LIMIT})
        sessions = sort_sessions(list(sessions_result.get("sessions", [])))
    except Exception:
        sessions = []

    focus_session_id = session_id or ((sessions[0] if sessions else {}).get("session_id"))
    if focus_session_id:
        try:
            evidence = rpc_call(
                socket_path,
                "session.evidence.get",
                {"session_id": focus_session_id, "limit": 20},
            )
            focus_session = evidence.get("session")
            recovery = evidence.get("recovery")
            tasks = sort_tasks(list(evidence.get("tasks", [])))
        except Exception:
            focus_session = next(
                (item for item in sessions if item.get("session_id") == focus_session_id),
                None,
            )
            recovery = None
            tasks = []

    if focus_session is not None and not any(
        item.get("session_id") == focus_session.get("session_id") for item in sessions
    ):
        sessions = sort_sessions([focus_session, *sessions])

    return {
        "sessions": sessions,
        "tasks": tasks,
        "all_tasks": tasks,
        "focus_session": focus_session,
        "recovery": recovery,
        "session_count": len(sessions),
        "task_count_total": len(tasks),
    }


def load_state(socket_path: Path, fixture: Path | None, session_id: str | None) -> dict:
    if fixture is not None:
        return load_fixture_state(fixture, session_id)
    return load_live_state(socket_path, session_id)


def build_model(state: dict, requested_session_id: str | None, user_id: str, intent: str, title: str | None, task_state: str) -> dict:
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

    return {
        "component_id": "launcher",
        "panel_id": "launcher-panel",
        "panel_kind": "shell-panel-skeleton",
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
                    {"label": "created_at", "value": focus_session.get("created_at", "-"), "tone": "neutral"},
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
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    lines.append("badges: " + ", ".join(f"{item['label']}: {item['value']}" for item in panel["badges"]))
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
        sessions = rpc_call(args.socket, "session.list", {"limit": 1}).get("sessions", [])
    except Exception:
        return None
    if sessions:
        return sessions[0].get("session_id")
    return None


def run_action(args: argparse.Namespace) -> dict:
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
            result = rpc_call(args.socket, "session.create", {"user_id": args.user_id, "metadata": {"initial_intent": args.intent}})
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
            result = rpc_call(args.socket, "session.resume", {"session_id": session_id})
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
            result = rpc_call(args.socket, "task.create", {"session_id": session_id, "title": args.title or args.intent, "state": args.state})
        return {
            **result,
            "target_component": "task-surface",
        }

    raise SystemExit(f"unknown action: {args.action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS launcher panel skeleton")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--intent", default="shell-launcher")
    parser.add_argument("--title")
    parser.add_argument("--state", default="planned")
    parser.add_argument("--action")
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
            state = load_state(args.socket, args.fixture, args.session_id)
            model = build_model(state, args.session_id, args.user_id, args.intent, args.title, args.state)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    state = load_state(args.socket, args.fixture, args.session_id)
    model = build_model(state, args.session_id, args.user_id, args.intent, args.title, args.state)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
