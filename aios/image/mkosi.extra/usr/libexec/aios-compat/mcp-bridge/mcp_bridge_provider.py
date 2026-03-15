#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios.compat.runtime_support import (
    CompatPolicyContext,
    CompatPolicyError,
    add_policy_args,
    append_jsonl,
    resolve_policy_context,
    standalone_policy_context,
)


PROVIDER_ID = "compat.mcp.bridge.local"
DECLARED_CAPABILITIES = [
    "compat.mcp.call",
    "compat.a2a.forward",
]
REQUIRED_PERMISSIONS = [
    "bridge.remote",
]
COMPAT_PERMISSION_SCHEMA_REF = "aios/compat-permission-manifest.schema.json"
RESULT_PROTOCOL_SCHEMA_REF = "aios/compat-mcp-bridge-result.schema.json"
DESCRIPTOR_FILENAME = "mcp.bridge.local.json"
DEFAULT_TIMEOUT_SECONDS = 10.0
WORKER_CONTRACT = "compat-mcp-bridge-v1"
AUDIT_SCHEMA_VERSION = "2026-03-13"
DEFAULT_AUDIT_LOG_ENV = "AIOS_COMPAT_MCP_BRIDGE_AUDIT_LOG"
DEFAULT_USER_ID = "compat-user"
DEFAULT_SESSION_ID = "compat-session"
DEFAULT_TASK_ID = "compat-task"
DEFAULT_TRUST_MODE = "permissive"
VALID_TRUST_MODES = {"permissive", "allowlist", "deny"}
COMMAND_EXIT_CODES = {
    "invalid_request": 2,
    "precondition_failed": 3,
    "permission_denied": 13,
    "timeout": 124,
    "unavailable": 69,
    "remote_error": 70,
    "internal": 1,
}


@dataclass(frozen=True)
class BridgeContext:
    command: str
    operation: str | None
    capability_id: str | None
    endpoint: str | None
    timeout_seconds: float | None
    request_payload: object | None
    request_kind: str | None
    tool: str | None
    request_id: str | None
    started_at: str


class BridgeCommandError(RuntimeError):
    def __init__(
        self,
        *,
        category: str,
        error_code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    @property
    def exit_code(self) -> int:
        return COMMAND_EXIT_CODES.get(self.category, 1)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "category": self.category,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }
        payload.update(self.details)
        return payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS MCP bridge provider baseline runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("manifest")
    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--audit-log", type=Path)
    add_policy_args(health_parser)
    subparsers.add_parser("permissions")

    call_parser = subparsers.add_parser("call")
    call_parser.add_argument("--endpoint", required=True)
    call_parser.add_argument("--tool", required=True)
    call_parser.add_argument("--arguments", default="{}")
    call_parser.add_argument("--request-id", default="1")
    call_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    call_parser.add_argument("--audit-log", type=Path)
    add_policy_args(call_parser)

    forward_parser = subparsers.add_parser("forward")
    forward_parser.add_argument("--endpoint", required=True)
    forward_parser.add_argument("--payload", required=True)
    forward_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    forward_parser.add_argument("--audit-log", type=Path)
    add_policy_args(forward_parser)

    return parser.parse_args()


def resolve_descriptor_path() -> str:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[1] / "providers" / DESCRIPTOR_FILENAME,
        current.parents[3] / "share" / "aios" / "providers" / DESCRIPTOR_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


def resolve_audit_log(args: argparse.Namespace) -> Path | None:
    audit_log = getattr(args, "audit_log", None)
    if audit_log is not None:
        return audit_log
    raw = os.environ.get(DEFAULT_AUDIT_LOG_ENV)
    return Path(raw) if raw else None


def load_compat_permission_manifest() -> dict[str, object]:
    descriptor_path = resolve_descriptor_path()
    descriptor = json.loads(Path(descriptor_path).read_text(encoding="utf-8"))
    permission_manifest = descriptor.get("compat_permission_manifest")
    if not isinstance(permission_manifest, dict):
        raise RuntimeError(f"descriptor missing compat_permission_manifest: {descriptor_path}")

    capability_ids = [
        item.get("capability_id")
        for item in permission_manifest.get("capabilities", [])
        if isinstance(item, dict)
    ]
    if permission_manifest.get("schema_version") != "1.0.0":
        raise RuntimeError("unsupported compat permission manifest schema_version")
    if permission_manifest.get("provider_id") != PROVIDER_ID:
        raise RuntimeError("compat permission manifest provider_id mismatch")
    if permission_manifest.get("execution_location") != "sandbox":
        raise RuntimeError("compat permission manifest execution_location mismatch")
    if permission_manifest.get("required_permissions") != REQUIRED_PERMISSIONS:
        raise RuntimeError("compat permission manifest required_permissions mismatch")
    if capability_ids != DECLARED_CAPABILITIES:
        raise RuntimeError("compat permission manifest capability list mismatch")

    return permission_manifest


def compat_capability(capability_id: str | None) -> dict[str, object]:
    if capability_id is None:
        return {}
    for capability in load_compat_permission_manifest().get("capabilities", []):
        if isinstance(capability, dict) and capability.get("capability_id") == capability_id:
            return capability
    return {}


def build_manifest() -> dict[str, object]:
    trust_policy = resolve_trust_policy()
    return {
        "provider_id": PROVIDER_ID,
        "execution_location": "sandbox",
        "status": "baseline",
        "worker_contract": WORKER_CONTRACT,
        "declared_capabilities": DECLARED_CAPABILITIES,
        "required_permissions": REQUIRED_PERMISSIONS,
        "implemented_methods": [
            "jsonrpc-http-call",
            "json-http-forward",
            "permission-manifest",
            "bridge-result-protocol-v1",
            "bridge-trust-policy-v1",
            "audit-jsonl",
        ],
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "trust_policy": trust_policy,
        "notes": [
            "Baseline HTTP bridge runtime is available",
            "Structured compat-mcp-bridge-v1 result protocol is emitted on success and failure",
            "Optional JSONL audit sink can be configured for machine-readable evidence",
            "Remote auth and provider registration are still pending",
        ],
    }


def enforce_timeout_budget(timeout_seconds: float) -> None:
    resource_budget = load_compat_permission_manifest().get("resource_budget", {})
    if not isinstance(resource_budget, dict):
        return
    max_timeout_seconds = resource_budget.get("max_timeout_seconds")
    if isinstance(max_timeout_seconds, (int, float)) and timeout_seconds > float(max_timeout_seconds):
        raise BridgeCommandError(
            category="invalid_request",
            error_code="bridge_timeout_exceeds_budget",
            message=(
                "requested timeout exceeds compat permission manifest budget: "
                f"{timeout_seconds}s > {max_timeout_seconds}s"
            ),
            retryable=False,
            details={"budget_max_timeout_seconds": float(max_timeout_seconds)},
        )


def configured_allowlist() -> list[str]:
    raw_value = os.environ.get("AIOS_MCP_BRIDGE_ALLOWLIST", "")
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def resolve_trust_policy() -> dict[str, object]:
    configured_mode = os.environ.get("AIOS_MCP_BRIDGE_TRUST_MODE", DEFAULT_TRUST_MODE).strip().lower()
    if not configured_mode:
        configured_mode = DEFAULT_TRUST_MODE

    allowlist = configured_allowlist()
    mode = configured_mode if configured_mode in VALID_TRUST_MODES else "invalid"
    notes: list[str] = []
    status = "available"

    if mode == "invalid":
        status = "degraded"
        notes.append(
            "Unrecognized AIOS_MCP_BRIDGE_TRUST_MODE; remote calls will be rejected until configuration is fixed"
        )
    elif mode == "permissive":
        status = "degraded"
        notes.append(
            "Trust policy is permissive; set AIOS_MCP_BRIDGE_TRUST_MODE=allowlist to enforce AIOS_MCP_BRIDGE_ALLOWLIST"
        )
    elif mode == "allowlist":
        if allowlist:
            notes.append("Endpoint host must match AIOS_MCP_BRIDGE_ALLOWLIST")
        else:
            status = "degraded"
            notes.append("Allowlist mode is configured without AIOS_MCP_BRIDGE_ALLOWLIST entries")
    elif mode == "deny":
        status = "degraded"
        notes.append("Trust policy denies all remote bridge calls")

    return {
        "mode": mode,
        "configured_mode": configured_mode,
        "enforced": mode in {"allowlist", "deny"},
        "allowlist": allowlist,
        "status": status,
        "notes": notes,
    }


def target_details(endpoint: str | None) -> dict[str, object]:
    if not endpoint:
        return {
            "endpoint": None,
            "scheme": None,
            "authority": None,
            "host": None,
            "path": None,
        }
    parsed = urlparse(endpoint)
    return {
        "endpoint": endpoint,
        "scheme": parsed.scheme or None,
        "authority": parsed.netloc or None,
        "host": parsed.hostname or None,
        "path": parsed.path or "/",
    }


def validate_endpoint(endpoint: str, trust_policy: dict[str, object]) -> dict[str, object]:
    target = target_details(endpoint)
    if target["scheme"] not in {"http", "https"}:
        raise BridgeCommandError(
            category="invalid_request",
            error_code="bridge_unsupported_endpoint_scheme",
            message=f"unsupported endpoint scheme: {target['scheme'] or '<none>'}",
            retryable=False,
            details={"target": target},
        )
    if not target["authority"]:
        raise BridgeCommandError(
            category="invalid_request",
            error_code="bridge_endpoint_host_missing",
            message="endpoint must include host",
            retryable=False,
            details={"target": target},
        )

    mode = str(trust_policy.get("mode", "invalid"))
    allowlist = [
        value for value in trust_policy.get("allowlist", []) if isinstance(value, str) and value.strip()
    ]

    if mode == "invalid":
        raise BridgeCommandError(
            category="precondition_failed",
            error_code="bridge_invalid_trust_mode",
            message=(
                "invalid bridge trust policy configuration: "
                f"AIOS_MCP_BRIDGE_TRUST_MODE={trust_policy.get('configured_mode')!r}"
            ),
            retryable=False,
            details={"target": target, "trust_policy": trust_policy},
        )
    if mode == "deny":
        raise BridgeCommandError(
            category="permission_denied",
            error_code="bridge_remote_calls_denied",
            message="bridge trust policy is set to deny; remote calls are disabled",
            retryable=False,
            details={"target": target, "trust_policy": trust_policy},
        )
    if mode == "allowlist":
        if not allowlist:
            raise BridgeCommandError(
                category="precondition_failed",
                error_code="bridge_allowlist_missing",
                message="allowlist trust mode requires AIOS_MCP_BRIDGE_ALLOWLIST to contain at least one host",
                retryable=False,
                details={"target": target, "trust_policy": trust_policy},
            )
        if target["host"] not in allowlist and target["authority"] not in allowlist:
            raise BridgeCommandError(
                category="permission_denied",
                error_code="bridge_endpoint_not_allowlisted",
                message=f"endpoint host not allowlisted: {target['host'] or target['authority']}",
                retryable=False,
                details={"target": target, "trust_policy": trust_policy},
            )

    return target


def parse_json_argument(value: str, label: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise BridgeCommandError(
            category="invalid_request",
            error_code=f"bridge_invalid_{label}_json",
            message=f"invalid JSON for {label}",
            retryable=False,
            details={"argument": label},
        ) from exc


def decode_remote_body(body: bytes) -> tuple[str, object]:
    if not body:
        return "empty", None
    try:
        return "json", json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        text = body.decode("utf-8", errors="replace")
        return "text", text


def post_json(endpoint: str, payload: object, timeout_seconds: float, trust_policy: dict[str, object]) -> dict[str, object]:
    target = validate_endpoint(endpoint, trust_policy)
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=encoded,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AIOSMcpBridge/0.2",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", None) or response.getcode() or 200
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        body = exc.read()
        response_kind, response_payload = decode_remote_body(body)
        raise BridgeCommandError(
            category="remote_error",
            error_code="bridge_remote_http_error",
            message=f"remote endpoint returned HTTP {exc.code}",
            retryable=exc.code >= 500,
            details={
                "target": target,
                "remote": {
                    "http_status": exc.code,
                    "response_kind": response_kind,
                    "response": response_payload,
                    "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
                },
            },
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise BridgeCommandError(
            category="timeout",
            error_code="bridge_remote_timeout",
            message=f"remote endpoint timed out after {timeout_seconds}s",
            retryable=True,
            details={"target": target},
        ) from exc
    except URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            raise BridgeCommandError(
                category="timeout",
                error_code="bridge_remote_timeout",
                message=f"remote endpoint timed out after {timeout_seconds}s",
                retryable=True,
                details={"target": target},
            ) from exc
        raise BridgeCommandError(
            category="unavailable",
            error_code="bridge_remote_unavailable",
            message=f"remote endpoint unavailable: {exc.reason}",
            retryable=True,
            details={"target": target},
        ) from exc

    response_kind, response_payload = decode_remote_body(body)
    return {
        "target": target,
        "http_status": status_code,
        "response_kind": response_kind,
        "response": response_payload,
        "content_type": content_type,
    }


def build_context_from_args(args: argparse.Namespace) -> BridgeContext:
    started_at = utc_now()
    if args.command == "call":
        return BridgeContext(
            command="call",
            operation="compat.mcp.call",
            capability_id="compat.mcp.call",
            endpoint=args.endpoint,
            timeout_seconds=args.timeout_seconds,
            request_payload={
                "jsonrpc": "2.0",
                "id": args.request_id,
                "method": args.tool,
                "params_text": args.arguments,
            },
            request_kind="jsonrpc",
            tool=args.tool,
            request_id=args.request_id,
            started_at=started_at,
        )
    if args.command == "forward":
        return BridgeContext(
            command="forward",
            operation="compat.a2a.forward",
            capability_id="compat.a2a.forward",
            endpoint=args.endpoint,
            timeout_seconds=args.timeout_seconds,
            request_payload={"payload_text": args.payload},
            request_kind="json",
            tool=None,
            request_id=None,
            started_at=started_at,
        )
    return BridgeContext(
        command=args.command,
        operation=None,
        capability_id=None,
        endpoint=None,
        timeout_seconds=None,
        request_payload=None,
        request_kind=None,
        tool=None,
        request_id=None,
        started_at=started_at,
    )


def build_result_protocol(
    *,
    context: BridgeContext,
    trust_policy: dict[str, object],
    finished_at: str,
    remote: dict[str, object] | None,
    error: dict[str, object] | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    capability = compat_capability(context.capability_id)
    permission_manifest = load_compat_permission_manifest()
    remote = remote or {}
    return {
        "protocol_version": "1.0.0",
        "worker_contract": WORKER_CONTRACT,
        "provider_id": PROVIDER_ID,
        "status": "error" if error else "ok",
        "operation": context.operation,
        "execution_location": "sandbox",
        "request": {
            "capability_id": context.capability_id,
            "endpoint": context.endpoint,
            "timeout_seconds": context.timeout_seconds,
            "payload_kind": context.request_kind,
            "payload": context.request_payload,
            "tool": context.tool,
            "request_id": context.request_id,
        },
        "target": target_details(context.endpoint),
        "policy": {
            "trust_mode": trust_policy.get("mode"),
            "configured_mode": trust_policy.get("configured_mode"),
            "enforced": trust_policy.get("enforced"),
            "allowlist": trust_policy.get("allowlist"),
            "compat_permission_manifest": permission_manifest,
            **policy_context.describe(),
        },
        "remote": {
            "http_status": remote.get("http_status"),
            "response_kind": remote.get("response_kind", "empty"),
            "response": remote.get("response"),
            "content_type": remote.get("content_type"),
        },
        "audit": {
            "audit_id": None,
            "audit_log": None,
            "capability_id": context.capability_id,
            "audit_tags": capability.get("audit_tags", permission_manifest.get("audit_tags", [])),
            "taint_behavior": permission_manifest.get("taint_behavior"),
            "shared_audit_log": (
                str(policy_context.shared_audit_log)
                if policy_context.shared_audit_log is not None
                else None
            ),
            "execution_token": policy_context.token_context,
            "token_verification": policy_context.verification,
        },
        "timestamps": {
            "started_at": context.started_at,
            "finished_at": finished_at,
        },
        "error": error,
    }


def build_success_payload(
    *,
    context: BridgeContext,
    trust_policy: dict[str, object],
    remote: dict[str, object],
    response_field: str,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    finished_at = utc_now()
    result_protocol = build_result_protocol(
        context=context,
        trust_policy=trust_policy,
        finished_at=finished_at,
        remote=remote,
        error=None,
        policy_context=policy_context,
    )
    payload = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "ok",
        "operation": context.operation,
        "capability_id": context.capability_id,
        "endpoint": context.endpoint,
        "remote_status": remote["http_status"],
        "request": context.request_payload,
        response_field: remote["response"],
        "response_kind": remote["response_kind"],
        "trust_policy": trust_policy,
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "result_protocol": result_protocol,
    }
    if context.tool is not None:
        payload["tool"] = context.tool
    payload["called_at" if context.command == "call" else "forwarded_at"] = finished_at
    payload["audit_id"] = append_audit_log(
        audit_log,
        payload,
        context,
        trust_policy,
        policy_context,
    )
    payload["audit_log"] = str(audit_log) if audit_log is not None else None
    (payload.get("result_protocol") or {}).get("audit", {})["audit_id"] = payload["audit_id"]
    (payload.get("result_protocol") or {}).get("audit", {})["audit_log"] = payload["audit_log"]
    return payload


def build_error_payload(
    *,
    context: BridgeContext,
    trust_policy: dict[str, object],
    error: BridgeCommandError,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    finished_at = utc_now()
    remote = error.details.get("remote")
    remote_payload = remote if isinstance(remote, dict) else None
    result_protocol = build_result_protocol(
        context=context,
        trust_policy=trust_policy,
        finished_at=finished_at,
        remote=remote_payload,
        error=error.to_payload(),
        policy_context=policy_context,
    )
    payload: dict[str, object] = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "error",
        "command": context.command,
        "operation": context.operation,
        "capability_id": context.capability_id,
        "endpoint": context.endpoint,
        "trust_policy": trust_policy,
        "error": error.to_payload(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "result_protocol": result_protocol,
        "finished_at": finished_at,
    }
    if context.request_payload is not None:
        payload["request"] = context.request_payload
    if remote_payload is not None:
        payload["remote_status"] = remote_payload.get("http_status")
        payload["response"] = remote_payload.get("response")
        payload["response_kind"] = remote_payload.get("response_kind")
    if context.tool is not None:
        payload["tool"] = context.tool
    payload["audit_id"] = append_audit_log(
        audit_log,
        payload,
        context,
        trust_policy,
        policy_context,
    )
    payload["audit_log"] = str(audit_log) if audit_log is not None else None
    (payload.get("result_protocol") or {}).get("audit", {})["audit_id"] = payload["audit_id"]
    (payload.get("result_protocol") or {}).get("audit", {})["audit_log"] = payload["audit_log"]
    return payload


def append_audit_log(
    audit_log: Path | None,
    payload: dict[str, object],
    context: BridgeContext,
    trust_policy: dict[str, object],
    policy_context: CompatPolicyContext,
) -> str | None:
    if audit_log is None and policy_context.shared_audit_log is None:
        return None
    if audit_log is not None and audit_log.parent:
        audit_log.parent.mkdir(parents=True, exist_ok=True)
    audit_id = f"mcp-bridge-{time.time_ns()}"
    status = str(payload.get("status", "error"))
    permission_manifest = load_compat_permission_manifest()
    capability = compat_capability(context.capability_id)
    error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    if error_payload.get("error_code") == "bridge_endpoint_not_allowlisted":
        decision = "denied"
    elif error_payload.get("category") in {"invalid_request", "permission_denied"}:
        decision = "denied"
    else:
        decision = "allowed"
    timestamp = utc_now()
    token_context = policy_context.token_context or {}
    artifact_path = str(audit_log or policy_context.shared_audit_log)
    entry = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audit_id": audit_id,
        "timestamp": timestamp,
        "generated_at": timestamp,
        "user_id": token_context.get("user_id")
        or os.environ.get("AIOS_COMPAT_MCP_BRIDGE_AUDIT_USER_ID", DEFAULT_USER_ID),
        "session_id": token_context.get("session_id")
        or os.environ.get("AIOS_COMPAT_MCP_BRIDGE_AUDIT_SESSION_ID", DEFAULT_SESSION_ID),
        "task_id": token_context.get("task_id")
        or os.environ.get("AIOS_COMPAT_MCP_BRIDGE_AUDIT_TASK_ID", DEFAULT_TASK_ID),
        "provider_id": PROVIDER_ID,
        "capability_id": context.capability_id,
        "approval_id": token_context.get("approval_ref"),
        "decision": decision,
        "execution_location": "sandbox",
        "route_state": (
            "compat-mcp-bridge-centralized-policy"
            if policy_context.mode == "policyd-verified"
            else "compat-mcp-bridge-baseline"
        ),
        "taint_summary": token_context.get("taint_summary")
        or permission_manifest.get("taint_behavior"),
        "artifact_path": artifact_path,
        "status": status,
        "operation": context.operation,
        "audit_tags": capability.get("audit_tags", permission_manifest.get("audit_tags", [])),
        "result": {
            "status": status,
            "operation": context.operation,
            "endpoint": context.endpoint,
            "tool": context.tool,
            "request_id": context.request_id,
            "remote_status": payload.get("remote_status"),
            "trust_mode": trust_policy.get("mode"),
            "error_code": error_payload.get("error_code"),
            "policy_mode": policy_context.mode,
            "token_verified": policy_context.token_verified,
            "session_id": token_context.get("session_id"),
            "task_id": token_context.get("task_id"),
            "approval_ref": token_context.get("approval_ref"),
        },
        "execution_token": token_context or None,
        "token_verification": policy_context.verification,
        "notes": [
            f"worker_contract={WORKER_CONTRACT}",
            f"result_protocol_schema_ref={RESULT_PROTOCOL_SCHEMA_REF}",
            f"policy_mode={policy_context.mode}",
        ],
    }
    append_jsonl(audit_log, entry)
    append_jsonl(policy_context.shared_audit_log, entry)
    return audit_id


def handle_health(
    trust_policy: dict[str, object],
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    permission_manifest = load_compat_permission_manifest()
    return {
        "status": trust_policy["status"],
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "execution_location": "sandbox",
        "declared_capabilities": DECLARED_CAPABILITIES,
        "required_permissions": REQUIRED_PERMISSIONS,
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": permission_manifest,
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "engine": "http-bridge-baseline",
        "trust_policy": trust_policy,
        "audit_log_configured": audit_log is not None,
        "audit_log_path": str(audit_log) if audit_log is not None else None,
        "shared_audit_log_configured": policy_context.shared_audit_log is not None,
        "shared_audit_log_path": (
            str(policy_context.shared_audit_log)
            if policy_context.shared_audit_log is not None
            else None
        ),
        "policyd_socket": (
            str(policy_context.policyd_socket)
            if policy_context.policyd_socket is not None
            else None
        ),
        "policy_mode": policy_context.mode,
        "notes": [
            "Supports bounded HTTP/HTTPS POST bridging",
            "Structured compat-mcp-bridge-v1 success/error payloads are enabled",
            "Centralized policy/token verification is enabled when policyd_socket + execution_token are supplied",
            *[str(note) for note in trust_policy.get("notes", [])],
        ],
    }


def handle_call(
    *,
    context: BridgeContext,
    trust_policy: dict[str, object],
    tool: str,
    arguments_text: str,
    request_id: str,
    timeout_seconds: float,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    enforce_timeout_budget(timeout_seconds)
    arguments = parse_json_argument(arguments_text, "arguments")
    if not isinstance(arguments, dict):
        raise BridgeCommandError(
            category="invalid_request",
            error_code="bridge_call_arguments_not_object",
            message="MCP call arguments must decode to a JSON object",
            retryable=False,
        )

    request_payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": tool,
        "params": arguments,
    }
    context = BridgeContext(
        command=context.command,
        operation=context.operation,
        capability_id=context.capability_id,
        endpoint=context.endpoint,
        timeout_seconds=timeout_seconds,
        request_payload=request_payload,
        request_kind="jsonrpc",
        tool=tool,
        request_id=request_id,
        started_at=context.started_at,
    )
    remote = post_json(context.endpoint or "", request_payload, timeout_seconds, trust_policy)
    return build_success_payload(
        context=context,
        trust_policy=trust_policy,
        remote=remote,
        response_field="response",
        audit_log=audit_log,
        policy_context=policy_context,
    )


def handle_forward(
    *,
    context: BridgeContext,
    trust_policy: dict[str, object],
    payload_text: str,
    timeout_seconds: float,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    enforce_timeout_budget(timeout_seconds)
    payload = parse_json_argument(payload_text, "payload")
    context = BridgeContext(
        command=context.command,
        operation=context.operation,
        capability_id=context.capability_id,
        endpoint=context.endpoint,
        timeout_seconds=timeout_seconds,
        request_payload=payload,
        request_kind="json",
        tool=None,
        request_id=None,
        started_at=context.started_at,
    )
    remote = post_json(context.endpoint or "", payload, timeout_seconds, trust_policy)
    return build_success_payload(
        context=context,
        trust_policy=trust_policy,
        remote=remote,
        response_field="response",
        audit_log=audit_log,
        policy_context=policy_context,
    )


def main() -> int:
    args = parse_args()
    context = build_context_from_args(args)
    trust_policy = resolve_trust_policy()
    audit_log = resolve_audit_log(args)
    policy_context = CompatPolicyContext(
        mode="standalone-local",
        policyd_socket=None,
        execution_token=None,
        token_context=None,
        verification=None,
        shared_audit_log=None,
    )
    try:
        policy_context = standalone_policy_context(args)
        if args.command == "manifest":
            payload: dict[str, object] = build_manifest()
        elif args.command == "health":
            payload = handle_health(trust_policy, audit_log, policy_context)
        elif args.command == "permissions":
            payload = load_compat_permission_manifest()
        elif args.command == "call":
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=False,
            )
            payload = handle_call(
                context=context,
                trust_policy=trust_policy,
                tool=args.tool,
                arguments_text=args.arguments,
                request_id=args.request_id,
                timeout_seconds=args.timeout_seconds,
                audit_log=audit_log,
                policy_context=policy_context,
            )
        elif args.command == "forward":
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=True,
            )
            payload = handle_forward(
                context=context,
                trust_policy=trust_policy,
                payload_text=args.payload,
                timeout_seconds=args.timeout_seconds,
                audit_log=audit_log,
                policy_context=policy_context,
            )
        else:
            raise BridgeCommandError(
                category="invalid_request",
                error_code="bridge_unsupported_command",
                message=f"unsupported command: {args.command}",
                retryable=False,
            )
    except CompatPolicyError as exc:
        error = BridgeCommandError(
            category=exc.category,
            error_code=exc.error_code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    trust_policy=trust_policy,
                    error=error,
                    audit_log=audit_log,
                    policy_context=exc.policy_context or policy_context,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return error.exit_code
    except BridgeCommandError as exc:
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    trust_policy=trust_policy,
                    error=exc,
                    audit_log=audit_log,
                    policy_context=policy_context,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        error = BridgeCommandError(
            category="internal",
            error_code="bridge_internal_error",
            message=str(exc),
            retryable=False,
        )
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    trust_policy=trust_policy,
                    error=error,
                    audit_log=audit_log,
                    policy_context=policy_context,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return error.exit_code

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
