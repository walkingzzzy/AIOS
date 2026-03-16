#!/usr/bin/env python3
import argparse
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path


def default_socket() -> Path:
    return Path(os.environ.get("AIOS_SESSIOND_SOCKET_PATH", "/run/aios/sessiond/sessiond.sock"))


def default_agent_socket() -> Path:
    return Path(os.environ.get("AIOS_AGENTD_SOCKET_PATH", "/run/aios/agentd/agentd.sock"))


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    if not hasattr(socket, "AF_UNIX"):
        raise RuntimeError(f"unix-domain-socket-unavailable:{socket_path}")
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response["result"]


def load_fixture(path: Path) -> dict:
    if not path.exists():
        return {"tasks": [], "plans": {}}
    return json.loads(path.read_text())


def save_fixture(path: Path, payload: dict) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def list_fixture_events(payload: dict, task_id: str, limit: int | None) -> list[dict]:
    raw_events = payload.get("events", {})
    if isinstance(raw_events, dict):
        items = list(raw_events.get(task_id, []))
    elif isinstance(raw_events, list):
        items = [item for item in raw_events if item.get("task_id") == task_id]
    else:
        items = []
    if limit is not None:
        items = items[:limit]
    return items


def fixture_call(path: Path, command: str, args: argparse.Namespace) -> dict:
    payload = load_fixture(path)
    tasks = payload.setdefault("tasks", [])
    plans = payload.setdefault("plans", {})
    if command == "list":
        if not args.session_id:
            raise SystemExit("--session-id is required for list")
        items = [item for item in tasks if item.get("session_id") == args.session_id]
        if args.state:
            items = [item for item in items if item.get("state") == args.state]
        if args.limit is not None:
            items = items[: args.limit]
        return {"tasks": items}
    if not args.task_id:
        raise SystemExit("--task-id is required")
    record = next((item for item in tasks if item.get("task_id") == args.task_id), None)
    if record is None:
        raise SystemExit(f"unknown task_id: {args.task_id}")
    if command == "show":
        return record
    if command == "update":
        if not args.state:
            raise SystemExit("--state is required for update")
        record["state"] = args.state
        save_fixture(path, payload)
        return record
    if command == "events":
        return {
            "events": list_fixture_events(payload, args.task_id, args.limit),
        }
    return {
        "task_id": args.task_id,
        "plan": plans.get(args.task_id, {}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def print_tasks(result: dict) -> None:
    tasks = result.get("tasks", [])
    if not tasks:
        print("no tasks")
        return
    for item in tasks:
        title = item.get("title") or "-"
        print(f"- {item['task_id']}: {item['state']} title={title} session={item['session_id']}")


def print_events(result: dict) -> None:
    events = result.get("events", [])
    if not events:
        print("no task events")
        return
    for item in events:
        metadata = item.get("metadata") or {}
        reason = metadata.get("reason")
        suffix = f" reason={reason}" if reason else ""
        print(
            f"- {item['event_id']}: {item['from_state']} -> {item['to_state']} at={item['created_at']}{suffix}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS task surface prototype")
    parser.add_argument(
        "command",
        nargs="?",
        default="list",
        choices=["list", "show", "update", "plan", "events"],
    )
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--state")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reason")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.fixture is not None:
        result = fixture_call(args.fixture, args.command, args)
    elif args.command == "list":
        if not args.session_id:
            raise SystemExit("--session-id is required for list")
        result = rpc_call(
            args.agent_socket,
            "agent.task.list",
            {"session_id": args.session_id, "state": args.state, "limit": args.limit},
        )
    elif args.command == "show":
        if not args.task_id:
            raise SystemExit("--task-id is required for show")
        result = rpc_call(
            args.agent_socket,
            "agent.task.get",
            {"task_id": args.task_id, "event_limit": args.limit or 10},
        )
    elif args.command == "update":
        if not args.task_id:
            raise SystemExit("--task-id is required for update")
        if not args.state:
            raise SystemExit("--state is required for update")
        result = rpc_call(
            args.agent_socket,
            "agent.task.state.update",
            {"task_id": args.task_id, "new_state": args.state, "reason": args.reason},
        )
    elif args.command == "plan":
        if not args.task_id:
            raise SystemExit("--task-id is required for plan")
        result = rpc_call(args.agent_socket, "agent.task.plan.get", {"task_id": args.task_id})
    else:
        if not args.task_id:
            raise SystemExit("--task-id is required for events")
        result = rpc_call(
            args.agent_socket,
            "agent.task.events.list",
            {"task_id": args.task_id, "limit": args.limit or 10, "reverse": True},
        )

    if args.command == "list" and not args.json:
        print_tasks(result)
    elif args.command == "events" and not args.json:
        print_events(result)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))