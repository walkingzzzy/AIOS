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
        return {"sessions": [], "tasks": []}
    return json.loads(path.read_text())


def save_fixture(path: Path, payload: dict) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def fixture_call(path: Path, command: str, args: argparse.Namespace) -> dict:
    payload = load_fixture(path)
    sessions = payload.setdefault("sessions", [])
    tasks = payload.setdefault("tasks", [])
    now = datetime.now(timezone.utc).isoformat()
    if command == "create-session":
        session_id = f"session-{len(sessions) + 1}"
        task_id = f"task-{len(tasks) + 1}"
        session = {
            "session_id": session_id,
            "user_id": args.user_id,
            "created_at": now,
            "status": "active",
        }
        task = {
            "task_id": task_id,
            "session_id": session_id,
            "state": "planned",
            "title": args.intent,
            "created_at": now,
        }
        sessions.append(session)
        tasks.append(task)
        save_fixture(path, payload)
        return {"session": session, "task": task}
    if not args.session_id:
        raise SystemExit("--session-id is required")
    session = next((item for item in sessions if item.get("session_id") == args.session_id), None)
    if session is None:
        raise SystemExit(f"unknown session_id: {args.session_id}")
    if command == "resume":
        session["status"] = "active"
        session["last_resumed_at"] = now
        save_fixture(path, payload)
        return {
            "session": session,
            "recovery": {
                "recovery_id": f"recovery-{args.session_id}",
                "session_id": args.session_id,
                "status": "baseline",
                "restored_at": now,
            },
        }
    task = {
        "task_id": f"task-{len(tasks) + 1}",
        "session_id": args.session_id,
        "state": args.state,
        "title": args.title,
        "created_at": now,
    }
    tasks.append(task)
    save_fixture(path, payload)
    return {"task": task}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS launcher prototype")
    parser.add_argument("command", nargs="?", default="create-session", choices=["create-session", "resume", "create-task"])
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--intent", default="shell-launcher")
    parser.add_argument("--session-id")
    parser.add_argument("--title")
    parser.add_argument("--state", default="planned")
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

    print(json.dumps(result, indent=2, ensure_ascii=False))