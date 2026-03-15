#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
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
DEFAULT_REMOTE_REGISTRY_ENV = "AIOS_MCP_BRIDGE_REMOTE_REGISTRY"
DEFAULT_REMOTE_AUTH_SECRET_ENV = "AIOS_MCP_BRIDGE_REMOTE_AUTH_SECRET"
VALID_TRUST_MODES = {"permissive", "allowlist", "deny"}
VALID_REMOTE_AUTH_MODES = {"none", "bearer", "header", "execution-token"}
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
    provider_ref: str | None
    timeout_seconds: float | None
    request_payload: object | None
    request_kind: str | None
    tool: str | None
    request_id: str | None
    started_at: str


@dataclass(frozen=True)
class RemoteRegistration:
    provider_ref: str
    endpoint: str
    capabilities: list[str]
    auth_mode: str
    auth_header_name: str | None
    auth_secret_env: str | None
    target_hash: str
    registered_at: str
    display_name: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "provider_ref": self.provider_ref,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "auth_mode": self.auth_mode,
            "auth_header_name": self.auth_header_name,
            "auth_secret_env": self.auth_secret_env,
            "target_hash": self.target_hash,
            "registered_at": self.registered_at,
            "display_name": self.display_name,
        }


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
    health_parser.add_argument("--remote-registry", type=Path)
    add_policy_args(health_parser)
    subparsers.add_parser("permissions")

    list_parser = subparsers.add_parser("list-remotes")
    list_parser.add_argument("--remote-registry", type=Path)

    register_parser = subparsers.add_parser("register-remote")
    register_parser.add_argument("--provider-ref", required=True)
    register_parser.add_argument("--endpoint", required=True)
    register_parser.add_argument("--capability", action="append", dest="capabilities", required=True)
    register_parser.add_argument(
        "--auth-mode",
        default="none",
        choices=sorted(VALID_REMOTE_AUTH_MODES),
    )
    register_parser.add_argument("--auth-header-name")
    register_parser.add_argument("--auth-secret-env")
    register_parser.add_argument("--display-name")
    register_parser.add_argument("--remote-registry", type=Path)

    call_parser = subparsers.add_parser("call")
    call_parser.add_argument("--endpoint")
    call_parser.add_argument("--provider-ref")
    call_parser.add_argument("--tool", required=True)
    call_parser.add_argument("--arguments", default="{}")
    call_parser.add_argument("--request-id", default="1")
    call_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    call_parser.add_argument("--audit-log", type=Path)
    call_parser.add_argument("--remote-registry", type=Path)
    add_policy_args(call_parser)

    forward_parser = subparsers.add_parser("forward")
    forward_parser.add_argument("--endpoint")
    forward_parser.add_argument("--provider-ref")
    forward_parser.add_argument("--payload", required=True)
    forward_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    forward_parser.add_argument("--audit-log", type=Path)
    forward_parser.add_argument("--remote-registry", type=Path)
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


def resolve_remote_registry_path(args: argparse.Namespace | None = None) -> Path:
    configured = getattr(args, "remote_registry", None) if args is not None else None
    if configured is not None:
        return configured
    raw = os.environ.get(DEFAULT_REMOTE_REGISTRY_ENV)
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "state" / "aios" / "compat-mcp-bridge" / "remote-registry.json"


def remote_target_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.strip().encode("utf-8")).hexdigest()


def load_remote_registry(args: argparse.Namespace | None = None) -> tuple[Path, list[RemoteRegistration]]:
    path = resolve_remote_registry_path(args)
    if not path.exists():
        return path, []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise RuntimeError(f"remote registry entries must be a list: {path}")
    registrations = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        registrations.append(
            RemoteRegistration(
                provider_ref=str(item.get("provider_ref") or ""),
                endpoint=str(item.get("endpoint") or ""),
                capabilities=[
                    str(capability)
                    for capability in item.get("capabilities", [])
                    if isinstance(capability, str) and capability
                ],
                auth_mode=str(item.get("auth_mode") or "none"),
                auth_header_name=(
                    str(item.get("auth_header_name"))
                    if item.get("auth_header_name") is not None
                    else None
                ),
                auth_secret_env=(
                    str(item.get("auth_secret_env"))
                    if item.get("auth_secret_env") is not None
                    else None
                ),
                target_hash=str(item.get("target_hash") or remote_target_hash(str(item.get("endpoint") or ""))),
                registered_at=str(item.get("registered_at") or ""),
                display_name=(
                    str(item.get("display_name"))
                    if item.get("display_name") is not None
                    else None
                ),
            )
        )
    return path, registrations


def write_remote_registry(path: Path, registrations: list[RemoteRegistration]) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "entries": [registration.to_payload() for registration in registrations],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    registry_path, registrations = load_remote_registry()
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
            "remote-register",
            "remote-list",
            "remote-auth-header-v1",
        ],
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "trust_policy": trust_policy,
        "remote_registry": {
            "path": str(registry_path),
            "registered_remote_count": len(registrations),
            "registered_providers": [registration.provider_ref for registration in registrations],
            "auth_modes": sorted({registration.auth_mode for registration in registrations}),
        },
        "notes": [
            "Baseline HTTP bridge runtime is available",
            "Structured compat-mcp-bridge-v1 result protocol is emitted on success and failure",
            "Optional JSONL audit sink can be configured for machine-readable evidence",
            "Persistent remote registration and remote auth header strategies are available",
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


def resolve_remote_registration(
    context: BridgeContext,
    capability_id: str | None,
    args: argparse.Namespace,
) -> tuple[Path, RemoteRegistration | None]:
    path, registrations = load_remote_registry(args)
    match: RemoteRegistration | None = None

    if context.provider_ref:
        match = next(
            (registration for registration in registrations if registration.provider_ref == context.provider_ref),
            None,
        )
        if match is None:
            raise BridgeCommandError(
                category="precondition_failed",
                error_code="bridge_remote_provider_not_registered",
                message=f"remote provider is not registered: {context.provider_ref}",
                retryable=False,
                details={"provider_ref": context.provider_ref, "remote_registry": str(path)},
            )
    elif context.endpoint:
        match = next(
            (registration for registration in registrations if registration.endpoint == context.endpoint),
            None,
        )

    if match is None:
        return path, None

    if context.endpoint and context.endpoint != match.endpoint:
        raise BridgeCommandError(
            category="invalid_request",
            error_code="bridge_endpoint_registration_mismatch",
            message="endpoint does not match the registered remote provider endpoint",
            retryable=False,
            details={
                "provider_ref": match.provider_ref,
                "registered_endpoint": match.endpoint,
                "requested_endpoint": context.endpoint,
                "remote_registry": str(path),
            },
        )

    if capability_id and capability_id not in match.capabilities:
        raise BridgeCommandError(
            category="permission_denied",
            error_code="bridge_capability_not_registered",
            message=f"registered remote provider does not allow {capability_id}",
            retryable=False,
            details={
                "provider_ref": match.provider_ref,
                "registered_capabilities": match.capabilities,
                "remote_registry": str(path),
            },
        )

    return path, match


def resolve_effective_endpoint(
    context: BridgeContext,
    registration: RemoteRegistration | None,
) -> str:
    endpoint = context.endpoint or (registration.endpoint if registration is not None else None)
    if not endpoint:
        raise BridgeCommandError(
            category="invalid_request",
            error_code="bridge_endpoint_required",
            message="call/forward requires --endpoint or --provider-ref",
            retryable=False,
        )
    return endpoint


def remote_auth_description(
    registration: RemoteRegistration | None,
    registry_path: Path | None,
) -> dict[str, object]:
    if registration is None:
        return {
            "registered": False,
            "provider_ref": None,
            "auth_mode": None,
            "target_hash": None,
            "registry_path": str(registry_path) if registry_path is not None else None,
        }
    return {
        "registered": True,
        "provider_ref": registration.provider_ref,
        "display_name": registration.display_name,
        "auth_mode": registration.auth_mode,
        "auth_header_name": registration.auth_header_name,
        "auth_secret_env": registration.auth_secret_env,
        "target_hash": registration.target_hash,
        "capabilities": registration.capabilities,
        "endpoint": registration.endpoint,
        "registered_at": registration.registered_at,
        "registry_path": str(registry_path) if registry_path is not None else None,
    }


def encode_execution_token(token: dict[str, object]) -> str:
    encoded = json.dumps(token, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii")


def build_remote_auth_headers(
    *,
    context: BridgeContext,
    registration: RemoteRegistration | None,
    policy_context: CompatPolicyContext,
) -> dict[str, str]:
    if registration is None:
        return {}

    headers = {
        "X-AIOS-Remote-Provider": registration.provider_ref,
        "X-AIOS-Target-Hash": registration.target_hash,
    }
    auth_mode = registration.auth_mode
    header_name = registration.auth_header_name

    if auth_mode == "none":
        return headers

    if auth_mode in {"bearer", "header"}:
        secret_env = registration.auth_secret_env or DEFAULT_REMOTE_AUTH_SECRET_ENV
        secret = os.environ.get(secret_env)
        if not secret:
            raise BridgeCommandError(
                category="precondition_failed",
                error_code="bridge_remote_secret_missing",
                message=f"remote auth secret env is not set: {secret_env}",
                retryable=False,
                details={"provider_ref": registration.provider_ref, "auth_secret_env": secret_env},
            )
        effective_header = header_name or ("Authorization" if auth_mode == "bearer" else "X-AIOS-Bridge-Secret")
        headers[effective_header] = f"Bearer {secret}" if auth_mode == "bearer" else secret
        return headers

    if auth_mode == "execution-token":
        if not isinstance(policy_context.execution_token, dict):
            raise BridgeCommandError(
                category="precondition_failed",
                error_code="bridge_execution_token_missing",
                message="registered remote requires execution_token auth",
                retryable=False,
                details={"provider_ref": registration.provider_ref},
            )
        token_context = policy_context.token_context or {}
        if token_context.get("capability_id") != context.capability_id:
            raise BridgeCommandError(
                category="permission_denied",
                error_code="bridge_execution_token_capability_mismatch",
                message="execution token capability does not match bridge operation",
                retryable=False,
                details={
                    "provider_ref": registration.provider_ref,
                    "expected_capability_id": context.capability_id,
                    "token_capability_id": token_context.get("capability_id"),
                },
            )
        if token_context.get("execution_location") != "sandbox":
            raise BridgeCommandError(
                category="permission_denied",
                error_code="bridge_execution_token_location_mismatch",
                message="execution token execution_location must be sandbox for compat bridge",
                retryable=False,
                details={"provider_ref": registration.provider_ref},
            )
        if token_context.get("target_hash") != registration.target_hash:
            raise BridgeCommandError(
                category="permission_denied",
                error_code="bridge_execution_token_target_mismatch",
                message="execution token target_hash does not match registered remote target",
                retryable=False,
                details={
                    "provider_ref": registration.provider_ref,
                    "expected_target_hash": registration.target_hash,
                    "token_target_hash": token_context.get("target_hash"),
                },
            )
        effective_header = header_name or "X-AIOS-Execution-Token"
        headers[effective_header] = encode_execution_token(policy_context.execution_token)
        signature = policy_context.execution_token.get("signature")
        if isinstance(signature, str) and signature:
            headers["X-AIOS-Execution-Token-Signature"] = signature
        return headers

    raise BridgeCommandError(
        category="precondition_failed",
        error_code="bridge_remote_auth_mode_invalid",
        message=f"unsupported remote auth mode: {auth_mode}",
        retryable=False,
        details={"provider_ref": registration.provider_ref, "auth_mode": auth_mode},
    )


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


def post_json(
    endpoint: str,
    payload: object,
    timeout_seconds: float,
    trust_policy: dict[str, object],
    extra_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    target = validate_endpoint(endpoint, trust_policy)
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "AIOSMcpBridge/0.2",
    }
    headers.update(extra_headers or {})
    request = Request(
        endpoint,
        data=encoded,
        headers=headers,
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
        "request_headers": headers,
    }


def build_context_from_args(args: argparse.Namespace) -> BridgeContext:
    started_at = utc_now()
    if args.command == "call":
        return BridgeContext(
            command="call",
            operation="compat.mcp.call",
            capability_id="compat.mcp.call",
            endpoint=args.endpoint,
            provider_ref=args.provider_ref,
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
            provider_ref=args.provider_ref,
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
        provider_ref=None,
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
    registration: RemoteRegistration | None,
    registry_path: Path | None,
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
            "provider_ref": context.provider_ref,
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
            "remote_auth": remote_auth_description(registration, registry_path),
            **policy_context.describe(),
        },
        "remote": {
            "http_status": remote.get("http_status"),
            "response_kind": remote.get("response_kind", "empty"),
            "response": remote.get("response"),
            "content_type": remote.get("content_type"),
            "request_headers": remote.get("request_headers"),
        },
        "audit": {
            "audit_id": None,
            "audit_log": None,
            "capability_id": context.capability_id,
            "audit_tags": capability.get("audit_tags", permission_manifest.get("audit_tags", [])),
            "taint_behavior": permission_manifest.get("taint_behavior"),
            "remote_registration": remote_auth_description(registration, registry_path),
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
    registration: RemoteRegistration | None,
    registry_path: Path | None,
) -> dict[str, object]:
    finished_at = utc_now()
    result_protocol = build_result_protocol(
        context=context,
        trust_policy=trust_policy,
        finished_at=finished_at,
        remote=remote,
        error=None,
        policy_context=policy_context,
        registration=registration,
        registry_path=registry_path,
    )
    payload = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "ok",
        "operation": context.operation,
        "capability_id": context.capability_id,
        "endpoint": context.endpoint,
        "provider_ref": context.provider_ref,
        "remote_status": remote["http_status"],
        "request": context.request_payload,
        response_field: remote["response"],
        "response_kind": remote["response_kind"],
        "trust_policy": trust_policy,
        "remote_registration": remote_auth_description(registration, registry_path),
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
        registration,
        registry_path,
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
    registration: RemoteRegistration | None,
    registry_path: Path | None,
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
        registration=registration,
        registry_path=registry_path,
    )
    payload: dict[str, object] = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "error",
        "command": context.command,
        "operation": context.operation,
        "capability_id": context.capability_id,
        "endpoint": context.endpoint,
        "provider_ref": context.provider_ref,
        "trust_policy": trust_policy,
        "remote_registration": remote_auth_description(registration, registry_path),
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
        registration,
        registry_path,
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
    registration: RemoteRegistration | None,
    registry_path: Path | None,
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
            "provider_ref": context.provider_ref,
            "tool": context.tool,
            "request_id": context.request_id,
            "remote_status": payload.get("remote_status"),
            "trust_mode": trust_policy.get("mode"),
            "error_code": error_payload.get("error_code"),
            "policy_mode": policy_context.mode,
            "token_verified": policy_context.token_verified,
            "remote_auth_mode": registration.auth_mode if registration is not None else None,
            "remote_target_hash": registration.target_hash if registration is not None else None,
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
            f"remote_registered={registration is not None}",
        ],
    }
    if registration is not None:
        entry["remote_registration"] = remote_auth_description(registration, registry_path)
    append_jsonl(audit_log, entry)
    append_jsonl(policy_context.shared_audit_log, entry)
    return audit_id


def handle_health(
    trust_policy: dict[str, object],
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
    args: argparse.Namespace,
) -> dict[str, object]:
    permission_manifest = load_compat_permission_manifest()
    registry_path, registrations = load_remote_registry(args)
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
        "remote_registry_path": str(registry_path),
        "registered_remote_count": len(registrations),
        "registered_remotes": [registration.to_payload() for registration in registrations],
        "remote_auth_modes": sorted({registration.auth_mode for registration in registrations}),
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
            f"registered_remotes={len(registrations)}",
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
    args: argparse.Namespace,
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

    registry_path, registration = resolve_remote_registration(context, context.capability_id, args)
    endpoint = resolve_effective_endpoint(context, registration)
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
        endpoint=endpoint,
        provider_ref=registration.provider_ref if registration is not None else context.provider_ref,
        timeout_seconds=timeout_seconds,
        request_payload=request_payload,
        request_kind="jsonrpc",
        tool=tool,
        request_id=request_id,
        started_at=context.started_at,
    )
    remote = post_json(
        endpoint,
        request_payload,
        timeout_seconds,
        trust_policy,
        build_remote_auth_headers(
            context=context,
            registration=registration,
            policy_context=policy_context,
        ),
    )
    return build_success_payload(
        context=context,
        trust_policy=trust_policy,
        remote=remote,
        response_field="response",
        audit_log=audit_log,
        policy_context=policy_context,
        registration=registration,
        registry_path=registry_path,
    )


def handle_forward(
    *,
    context: BridgeContext,
    trust_policy: dict[str, object],
    payload_text: str,
    timeout_seconds: float,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
    args: argparse.Namespace,
) -> dict[str, object]:
    enforce_timeout_budget(timeout_seconds)
    payload = parse_json_argument(payload_text, "payload")
    registry_path, registration = resolve_remote_registration(context, context.capability_id, args)
    endpoint = resolve_effective_endpoint(context, registration)
    context = BridgeContext(
        command=context.command,
        operation=context.operation,
        capability_id=context.capability_id,
        endpoint=endpoint,
        provider_ref=registration.provider_ref if registration is not None else context.provider_ref,
        timeout_seconds=timeout_seconds,
        request_payload=payload,
        request_kind="json",
        tool=None,
        request_id=None,
        started_at=context.started_at,
    )
    remote = post_json(
        endpoint,
        payload,
        timeout_seconds,
        trust_policy,
        build_remote_auth_headers(
            context=context,
            registration=registration,
            policy_context=policy_context,
        ),
    )
    return build_success_payload(
        context=context,
        trust_policy=trust_policy,
        remote=remote,
        response_field="response",
        audit_log=audit_log,
        policy_context=policy_context,
        registration=registration,
        registry_path=registry_path,
    )


def handle_register_remote(args: argparse.Namespace) -> dict[str, object]:
    _, existing = load_remote_registry(args)
    endpoint_details = validate_endpoint(args.endpoint, resolve_trust_policy())
    capabilities = [capability for capability in args.capabilities if capability in DECLARED_CAPABILITIES]
    if len(capabilities) != len(args.capabilities):
        raise BridgeCommandError(
            category="invalid_request",
            error_code="bridge_remote_capability_invalid",
            message="register-remote only accepts declared compat bridge capabilities",
            retryable=False,
            details={"requested_capabilities": args.capabilities},
        )
    registration = RemoteRegistration(
        provider_ref=args.provider_ref,
        endpoint=args.endpoint,
        capabilities=capabilities,
        auth_mode=args.auth_mode,
        auth_header_name=args.auth_header_name,
        auth_secret_env=args.auth_secret_env,
        target_hash=remote_target_hash(args.endpoint),
        registered_at=utc_now(),
        display_name=args.display_name,
    )
    filtered = [item for item in existing if item.provider_ref != registration.provider_ref]
    filtered.append(registration)
    filtered.sort(key=lambda item: item.provider_ref)
    path = resolve_remote_registry_path(args)
    write_remote_registry(path, filtered)
    return {
        "provider_id": PROVIDER_ID,
        "status": "ok",
        "command": "register-remote",
        "remote_registry_path": str(path),
        "registered_remote_count": len(filtered),
        "registration": registration.to_payload(),
        "endpoint": endpoint_details,
    }


def handle_list_remotes(args: argparse.Namespace) -> dict[str, object]:
    path, registrations = load_remote_registry(args)
    return {
        "provider_id": PROVIDER_ID,
        "status": "ok",
        "command": "list-remotes",
        "remote_registry_path": str(path),
        "registered_remote_count": len(registrations),
        "registered_remotes": [registration.to_payload() for registration in registrations],
    }


def main() -> int:
    args = parse_args()
    context = build_context_from_args(args)
    trust_policy = resolve_trust_policy()
    audit_log = resolve_audit_log(args)
    registry_path = resolve_remote_registry_path(args)
    registration: RemoteRegistration | None = None
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
            payload = handle_health(trust_policy, audit_log, policy_context, args)
        elif args.command == "permissions":
            payload = load_compat_permission_manifest()
        elif args.command == "register-remote":
            payload = handle_register_remote(args)
        elif args.command == "list-remotes":
            payload = handle_list_remotes(args)
        elif args.command == "call":
            registry_path, registration = resolve_remote_registration(context, context.capability_id, args)
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=False,
                target_hash=registration.target_hash if registration is not None else None,
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
                args=args,
            )
        elif args.command == "forward":
            registry_path, registration = resolve_remote_registration(context, context.capability_id, args)
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=True,
                target_hash=registration.target_hash if registration is not None else None,
            )
            payload = handle_forward(
                context=context,
                trust_policy=trust_policy,
                payload_text=args.payload,
                timeout_seconds=args.timeout_seconds,
                audit_log=audit_log,
                policy_context=policy_context,
                args=args,
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
                    registration=registration,
                    registry_path=registry_path,
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
                    registration=registration,
                    registry_path=registry_path,
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
                    registration=registration,
                    registry_path=registry_path,
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
