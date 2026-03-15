#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from prototype import default_socket, fixture_call, print_events, print_tasks, rpc_call


def print_task(task: dict) -> None:
    print(f"task_id: {task.get('task_id')}")
    print(f"session_id: {task.get('session_id')}")
    print(f"state: {task.get('state')}")
    print(f"title: {task.get('title') or '-'}")


def build_summary(result: dict) -> dict:
    tasks = result.get("tasks", [])
    by_state: dict[str, int] = {}
    for item in tasks:
        state = item.get("state", "unknown")
        by_state[state] = by_state.get(state, 0) + 1
    return {"total": len(tasks), "by_state": by_state}


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS task surface shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="list",
        choices=["list", "show", "update", "plan", "summary", "events"],
    )
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--state")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reason")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    command = args.command
    effective_command = "list" if command == "summary" else command
    if args.fixture is not None:
        result = fixture_call(args.fixture, effective_command, args)
    elif effective_command == "list":
        if not args.session_id:
            raise SystemExit("--session-id is required for list/summary")
        result = rpc_call(
            args.socket,
            "task.list",
            {"session_id": args.session_id, "state": args.state, "limit": args.limit},
        )
    elif effective_command == "show":
        if not args.task_id:
            raise SystemExit("--task-id is required for show")
        result = rpc_call(args.socket, "task.get", {"task_id": args.task_id})
    elif effective_command == "update":
        if not args.task_id:
            raise SystemExit("--task-id is required for update")
        if not args.state:
            raise SystemExit("--state is required for update")
        result = rpc_call(
            args.socket,
            "task.state.update",
            {"task_id": args.task_id, "new_state": args.state, "reason": args.reason},
        )
    elif effective_command == "plan":
        if not args.task_id:
            raise SystemExit("--task-id is required for plan")
        result = rpc_call(args.socket, "task.plan.get", {"task_id": args.task_id})
    else:
        if not args.task_id:
            raise SystemExit("--task-id is required for events")
        result = rpc_call(
            args.socket,
            "task.events.list",
            {"task_id": args.task_id, "limit": args.limit or 10, "reverse": True},
        )

    if command == "summary":
        summary = build_summary(result)
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"total: {summary['total']}")
            print(f"by_state: {json.dumps(summary['by_state'], ensure_ascii=False, sort_keys=True)}")
    elif command == "list" and not args.json:
        print_tasks(result)
    elif command == "events" and not args.json:
        print_events(result)
    elif command in {"show", "update"} and not args.json:
        print_task(result)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
