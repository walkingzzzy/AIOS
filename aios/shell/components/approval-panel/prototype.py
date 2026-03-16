#!/usr/bin/env python3
import argparse
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path


def default_socket() -> Path:
    return Path(os.environ.get("AIOS_POLICYD_SOCKET_PATH", "/run/aios/policyd/policyd.sock"))


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
        return {"approvals": []}
    return json.loads(path.read_text())


def save_fixture(path: Path, payload: dict) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def fixture_call(path: Path, command: str, args: argparse.Namespace) -> dict:
    payload = load_fixture(path)
    approvals = payload.setdefault("approvals", [])
    if command == "create":
        record = {
            "approval_ref": f"approval-{len(approvals) + 1}",
            "user_id": args.user_id,
            "session_id": args.session_id,
            "task_id": args.task_id,
            "capability_id": args.capability_id,
            "approval_lane": args.approval_lane,
            "status": args.status or "pending",
            "execution_location": args.execution_location,
            "reason": args.reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        approvals.append(record)
        save_fixture(path, payload)
        return record
    if command == "list":
        items = approvals
        if args.session_id:
            items = [item for item in items if item.get("session_id") == args.session_id]
        if args.task_id:
            items = [item for item in items if item.get("task_id") == args.task_id]
        if args.status:
            items = [item for item in items if item.get("status") == args.status]
        return {"approvals": items}
    if not args.approval_ref:
        raise SystemExit("--approval-ref is required")
    record = next((item for item in approvals if item.get("approval_ref") == args.approval_ref), None)
    if record is None:
        raise SystemExit(f"unknown approval_ref: {args.approval_ref}")
    if command == "get":
        return record
    record["status"] = args.status or "approved"
    record["resolver"] = args.resolver
    record["reason"] = args.reason
    record["resolved_at"] = datetime.now(timezone.utc).isoformat()
    save_fixture(path, payload)
    return record


def print_list(result: dict) -> None:
    approvals = result.get("approvals", [])
    if not approvals:
        print("no approvals")
        return
    for item in approvals:
        reason = item.get("reason") or "-"
        print(
            f"- {item['approval_ref']}: {item['status']} capability={item['capability_id']} "
            f"session={item['session_id']} task={item['task_id']} lane={item['approval_lane']} reason={reason}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS approval panel prototype")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "get", "create", "resolve"])
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--approval-ref")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--capability-id", default="device.capture.audio")
    parser.add_argument("--approval-lane", default="high-risk")
    parser.add_argument("--execution-location", default="local")
    parser.add_argument("--status")
    parser.add_argument("--resolver", default="shell-approval-panel")
    parser.add_argument("--reason")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.fixture is not None:
        result = fixture_call(args.fixture, args.command, args)
    elif args.command == "list":
        result = rpc_call(
            args.agent_socket,
            "agent.approval.list",
            {"session_id": args.session_id, "task_id": args.task_id, "status": args.status},
        )
    elif args.command == "create":
        if not args.session_id or not args.task_id:
            raise SystemExit("--session-id and --task-id are required for create")
        result = rpc_call(
            args.agent_socket,
            "agent.approval.create",
            {
                "user_id": args.user_id,
                "session_id": args.session_id,
                "task_id": args.task_id,
                "capability_id": args.capability_id,
                "approval_lane": args.approval_lane,
                "execution_location": args.execution_location,
                "reason": args.reason,
            },
        )
    elif args.command == "get":
        if not args.approval_ref:
            raise SystemExit("--approval-ref is required for get")
        result = rpc_call(args.agent_socket, "agent.approval.get", {"approval_ref": args.approval_ref})
    else:
        if not args.approval_ref:
            raise SystemExit("--approval-ref is required for resolve")
        result = rpc_call(
            args.agent_socket,
            "agent.approval.resolve",
            {
                "approval_ref": args.approval_ref,
                "status": args.status or "approved",
                "resolver": args.resolver,
                "reason": args.reason,
            },
        )

    if args.command == "list" and not args.json:
        print_list(result)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))