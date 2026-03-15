#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from prototype import default_socket, fixture_call, rpc_call


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


def default_agent_socket() -> Path:
    return Path(os.environ.get("AIOS_AGENTD_SOCKET_PATH", "/run/aios/agentd/agentd.sock"))


def list_tasks(
    socket_path: Path,
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
        socket_path,
        "task.list",
        {"session_id": session_id, "state": state, "limit": limit},
    )


def get_task(socket_path: Path, fixture: Path | None, task_id: str | None) -> dict | None:
    if not task_id:
        return None
    try:
        if fixture is not None:
            args = argparse.Namespace(task_id=task_id)
            return fixture_call(fixture, "show", args)
        return rpc_call(socket_path, "task.get", {"task_id": task_id})
    except Exception:
        return None


def get_plan(socket_path: Path, fixture: Path | None, task_id: str | None) -> dict | None:
    if not task_id:
        return None
    try:
        if fixture is not None:
            args = argparse.Namespace(task_id=task_id)
            return fixture_call(fixture, "plan", args)
        return rpc_call(socket_path, "task.plan.get", {"task_id": task_id})
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
        "task.state.update",
        {"task_id": task_id, "new_state": new_state, "reason": reason},
    )


def list_task_events(
    socket_path: Path,
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
            socket_path,
            "task.events.list",
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

    try:
        response = rpc_call(
            agent_socket,
            "provider.resolve_capability",
            {
                "capability_id": capability_id,
                "require_healthy": True,
                "include_disabled": False,
            },
        )
    except Exception as error:
        return None, capability_id, str(error)

    return response, capability_id, None


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
) -> dict:
    tasks = tasks_result.get("tasks", [])
    summary = build_summary(tasks)
    plan = (plan_result or {}).get("plan") or {}
    task_events = task_events_result.get("events", [])

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

    return {
        "component_id": "task-surface",
        "panel_id": "task-panel",
        "panel_kind": "shell-panel-skeleton",
        "header": {
            "title": "Task Panel",
            "subtitle": f"session {session_id or '-'} · {summary['total']} tasks",
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
    parser = argparse.ArgumentParser(description="AIOS task surface panel skeleton")
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
            args.socket,
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
            tasks_result = list_tasks(
                args.socket, args.fixture, args.session_id, args.state, args.limit
            )
            focus_task_id = args.task_id or (tasks_result.get("tasks") or [{}])[0].get("task_id")
            focus_task = next(
                (item for item in tasks_result.get("tasks", []) if item.get("task_id") == focus_task_id),
                None,
            ) or get_task(args.socket, args.fixture, focus_task_id)
            plan_result = get_plan(args.socket, args.fixture, focus_task_id)
            task_events_result = list_task_events(
                args.socket,
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
            model = build_model(
                tasks_result,
                focus_task,
                plan_result,
                task_events_result,
                args.session_id,
                provider_resolution,
                provider_resolution_error,
                capability_id,
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

    tasks_result = list_tasks(args.socket, args.fixture, args.session_id, args.state, args.limit)
    focus_task_id = args.task_id or (tasks_result.get("tasks") or [{}])[0].get("task_id")
    focus_task = next(
        (item for item in tasks_result.get("tasks", []) if item.get("task_id") == focus_task_id),
        None,
    ) or get_task(args.socket, args.fixture, focus_task_id)
    plan_result = get_plan(args.socket, args.fixture, focus_task_id)
    task_events_result = list_task_events(
        args.socket,
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
    model = build_model(
        tasks_result,
        focus_task,
        plan_result,
        task_events_result,
        args.session_id,
        provider_resolution,
        provider_resolution_error,
        capability_id,
    )
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
