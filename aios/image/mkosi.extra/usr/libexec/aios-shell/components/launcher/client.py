#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from prototype import default_agent_socket, default_socket, fixture_call, rpc_call


def print_result(command: str, result: dict) -> None:
    if command == "create-session":
        session = result.get("session", {})
        task = result.get("task", {})
        print(f"session_id: {session.get('session_id')}")
        print(f"user_id: {session.get('user_id')}")
        print(f"task_id: {task.get('task_id')}")
        print(f"task_state: {task.get('state')}")
        return
    if command == "resume":
        session = result.get("session", {})
        recovery = result.get("recovery", {})
        print(f"session_id: {session.get('session_id')}")
        print(f"status: {session.get('status')}")
        print(f"recovery_id: {recovery.get('recovery_id')}")
        print(f"recovery_status: {recovery.get('status')}")
        return
    task = result.get("task", result)
    print(f"task_id: {task.get('task_id')}")
    print(f"session_id: {task.get('session_id')}")
    print(f"state: {task.get('state')}")
    print(f"title: {task.get('title') or '-'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS launcher shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="create-session",
        choices=["create-session", "resume", "create-task"],
    )
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--intent", default="shell-launcher")
    parser.add_argument("--session-id")
    parser.add_argument("--title")
    parser.add_argument("--state", default="planned")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.fixture is not None:
        result = fixture_call(args.fixture, args.command, args)
    elif args.command == "create-session":
        result = rpc_call(
            args.agent_socket,
            "agent.session.create",
            {"user_id": args.user_id, "metadata": {"initial_intent": args.intent}},
        )
    elif args.command == "resume":
        if not args.session_id:
            raise SystemExit("--session-id is required for resume")
        result = rpc_call(args.agent_socket, "agent.session.resume", {"session_id": args.session_id})
    else:
        if not args.session_id:
            raise SystemExit("--session-id is required for create-task")
        result = rpc_call(
            args.agent_socket,
            "agent.task.create",
            {"session_id": args.session_id, "title": args.title, "state": args.state},
        )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_result(args.command, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())