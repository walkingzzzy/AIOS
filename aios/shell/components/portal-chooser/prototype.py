#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_sessiond_socket() -> Path:
    return Path(os.environ.get("AIOS_SESSIOND_SOCKET_PATH", "/run/aios/sessiond/sessiond.sock"))


def default_agent_socket() -> Path:
    return Path(os.environ.get("AIOS_AGENTD_SOCKET_PATH", "/run/aios/agentd/agentd.sock"))


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    if not hasattr(socket, "AF_UNIX"):
        raise RuntimeError(f"unix-domain-socket-unavailable:{socket_path}")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response["result"]


def load_payload(
    socket_path: Path,
    agent_socket_path: Path | None,
    session_id: str | None,
    fixture: Path | None,
) -> dict[str, Any]:
    if fixture is not None and fixture.exists():
        payload = json.loads(fixture.read_text() or "{}")
        return payload if isinstance(payload, dict) else {}
    if not session_id:
        return {"handles": []}
    effective_socket = agent_socket_path or socket_path
    method = "agent.portal.handle.list" if agent_socket_path is not None else "portal.handle.list"
    try:
        result = rpc_call(effective_socket, method, {"session_id": session_id})
    except Exception as primary_error:
        if effective_socket != socket_path:
            try:
                result = rpc_call(socket_path, "portal.handle.list", {"session_id": session_id})
            except Exception as fallback_error:
                message = str(fallback_error)
                return {
                    "handles": [],
                    "request": {
                        "status": "failed",
                        "error_message": message,
                        "source_error": message,
                    },
                }
        else:
            message = str(primary_error)
            return {
                "handles": [],
                "request": {
                    "status": "failed",
                    "error_message": message,
                    "source_error": message,
                },
            }
    return {
        "handles": result.get("handles", []),
        "request": result.get("request") or {},
    }


def load_handles(
    socket_path: Path,
    agent_socket_path: Path | None,
    session_id: str | None,
    fixture: Path | None,
) -> list[dict]:
    return load_payload(socket_path, agent_socket_path, session_id, fixture).get("handles", [])


def load_request(
    socket_path: Path,
    agent_socket_path: Path | None,
    session_id: str | None,
    fixture: Path | None,
) -> dict[str, Any]:
    return load_payload(socket_path, agent_socket_path, session_id, fixture).get("request") or {}


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def handle_scope(handle: dict[str, Any]) -> dict[str, Any]:
    scope = handle.get("scope") or {}
    return scope if isinstance(scope, dict) else {}


def normalize_handle_availability(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    if normalized in {"", "available", "ready", "selectable"}:
        return "available"
    if normalized in {"resource-missing", "missing"}:
        return "resource-missing"
    if normalized in {"backend-unavailable", "backend-missing"}:
        return "backend-unavailable"
    if normalized in {"retry-later", "cooldown", "throttled"}:
        return "retry-later"
    return "unavailable"


def handle_availability_details(handle: dict[str, Any]) -> dict[str, Any]:
    scope = handle_scope(handle)
    retry_after = str(handle.get("retry_after") or scope.get("retry_after") or "").strip() or None
    if handle.get("revoked_at"):
        return {"status": "revoked", "selectable": False, "retry_after": retry_after}

    expiry = parse_timestamp(handle.get("expiry"))
    if expiry is not None and expiry <= datetime.now(timezone.utc):
        return {"status": "expired", "selectable": False, "retry_after": retry_after}

    availability = normalize_handle_availability(handle.get("availability") or scope.get("availability"))
    if handle.get("resource_missing") or scope.get("resource_missing"):
        availability = "resource-missing"
    elif handle.get("backend_available") is False or scope.get("backend_available") is False:
        availability = "backend-unavailable"
    elif availability == "unavailable" and retry_after is not None:
        availability = "retry-later"

    return {
        "status": availability,
        "selectable": availability == "available",
        "retry_after": retry_after,
        "reason": str(handle.get("unavailable_reason") or scope.get("unavailable_reason") or "").strip() or None,
    }


def handle_kind_summary(handles: list[dict]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for handle in handles:
        kind = handle.get("kind", "unknown")
        summary[kind] = summary.get(kind, 0) + 1
    return summary


def handle_availability_summary(handles: list[dict]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for handle in handles:
        status = handle_availability_details(handle)["status"]
        summary[status] = summary.get(status, 0) + 1
    return summary


def print_handles(handles: list[dict]) -> None:
    if not handles:
        print("no portal handles")
        return
    for handle in handles:
        scope = handle.get("scope") or {}
        display_name = scope.get("display_name") if isinstance(scope, dict) else None
        print(
            f"- {handle.get('handle_id', '-')}: {handle.get('kind', 'unknown')} "
            f"target={handle.get('target', '-')}"
            + (f" display={display_name}" if display_name else "")
        )


def build_summary(handles: list[dict], session_id: str | None, request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = request or {}
    audit_tags = request.get("audit_tags") if isinstance(request.get("audit_tags"), list) else []
    requested_kinds = request.get("requested_kinds", [])
    matching_handles = [handle for handle in handles if not requested_kinds or handle.get("kind") in requested_kinds]
    selectable_handles = [handle for handle in handles if handle_availability_details(handle)["selectable"]]
    unavailable_handles = [handle for handle in handles if not handle_availability_details(handle)["selectable"]]
    requested_unavailable = [
        handle
        for handle in matching_handles
        if not handle_availability_details(handle)["selectable"]
    ]
    retry_after = str(request.get("retry_after") or "").strip() or None
    if retry_after is None:
        retry_after = next(
            (
                handle_availability_details(handle).get("retry_after")
                for handle in requested_unavailable or unavailable_handles
                if handle_availability_details(handle).get("retry_after")
            ),
            None,
        )
    return {
        "total": len(handles),
        "by_kind": handle_kind_summary(handles),
        "by_availability": handle_availability_summary(handles),
        "session_id": session_id,
        "chooser_id": request.get("chooser_id"),
        "requested_kinds": requested_kinds,
        "approval_status": request.get("approval_status"),
        "status": request.get("status"),
        "selectable_total": len(selectable_handles),
        "unavailable_total": len(unavailable_handles),
        "matching_total": len(matching_handles),
        "requested_unavailable_total": len(requested_unavailable),
        "selected_handle_id": request.get("selected_handle_id"),
        "confirmed_handle_id": request.get("confirmed_handle_id"),
        "error_message": request.get("error_message"),
        "retry_after": retry_after,
        "audit_tags": audit_tags,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS portal chooser prototype")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "summary"])
    parser.add_argument("--socket", type=Path, default=default_sessiond_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--session-id")
    parser.add_argument("--handle-fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = load_payload(args.socket, args.agent_socket, args.session_id, args.handle_fixture)
    handles = payload.get("handles", [])
    request = payload.get("request") or {}
    if args.command == "summary":
        payload = build_summary(handles, args.session_id, request)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"total: {payload['total']}")
            print(json.dumps(payload["by_kind"], indent=2, ensure_ascii=False))
        return 0

    if args.json:
        print(json.dumps({"handles": handles, "request": request}, indent=2, ensure_ascii=False))
    else:
        print_handles(handles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())