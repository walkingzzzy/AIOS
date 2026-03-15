from __future__ import annotations

import argparse
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any


POLICY_TOKEN_VERIFY = "policy.token.verify"
DEFAULT_EXECUTION_TOKEN_ENV = "AIOS_COMPAT_EXECUTION_TOKEN"
DEFAULT_EXECUTION_TOKEN_FILE_ENV = "AIOS_COMPAT_EXECUTION_TOKEN_FILE"
DEFAULT_POLICYD_SOCKET_ENV = "AIOS_COMPAT_POLICYD_SOCKET"
DEFAULT_OBSERVABILITY_LOG_ENV = "AIOS_COMPAT_OBSERVABILITY_LOG"


@dataclass(frozen=True)
class CompatPolicyContext:
    mode: str
    policyd_socket: Path | None
    execution_token: dict[str, Any] | None
    token_context: dict[str, Any] | None
    verification: dict[str, Any] | None
    shared_audit_log: Path | None

    @property
    def token_verified(self) -> bool:
        return bool(self.verification and self.verification.get("valid"))

    def describe(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "token_verified": self.token_verified,
            "policyd_socket": str(self.policyd_socket) if self.policyd_socket is not None else None,
            "shared_audit_log": str(self.shared_audit_log) if self.shared_audit_log is not None else None,
            "execution_token": self.token_context,
            "token_verification": self.verification,
        }


class CompatPolicyError(RuntimeError):
    def __init__(
        self,
        *,
        category: str,
        error_code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        policy_context: CompatPolicyContext | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.policy_context = policy_context

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "category": self.category,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }
        payload.update(self.details)
        return payload


def add_policy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--execution-token")
    parser.add_argument("--execution-token-file", type=Path)
    parser.add_argument("--policyd-socket", type=Path)
    parser.add_argument("--shared-audit-log", type=Path)


def append_jsonl(path: Path | None, entry: dict[str, Any]) -> None:
    if path is None:
        return
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def resolve_shared_audit_log(args: argparse.Namespace | None = None) -> Path | None:
    value = getattr(args, "shared_audit_log", None) if args is not None else None
    if value is not None:
        return value
    raw = os.environ.get(DEFAULT_OBSERVABILITY_LOG_ENV)
    return Path(raw) if raw else None


def resolve_policyd_socket(args: argparse.Namespace | None = None) -> Path | None:
    value = getattr(args, "policyd_socket", None) if args is not None else None
    if value is not None:
        return value
    raw = os.environ.get(DEFAULT_POLICYD_SOCKET_ENV)
    return Path(raw) if raw else None


def load_execution_token(args: argparse.Namespace | None = None) -> dict[str, Any] | None:
    raw_token = getattr(args, "execution_token", None) if args is not None else None
    if raw_token is None:
        raw_token = os.environ.get(DEFAULT_EXECUTION_TOKEN_ENV)
    if raw_token:
        value = json.loads(raw_token)
        if not isinstance(value, dict):
            raise CompatPolicyError(
                category="invalid_request",
                error_code="compat_execution_token_invalid_json",
                message="execution token must decode to a JSON object",
                retryable=False,
            )
        return value

    token_file = getattr(args, "execution_token_file", None) if args is not None else None
    if token_file is None:
        raw_file = os.environ.get(DEFAULT_EXECUTION_TOKEN_FILE_ENV)
        token_file = Path(raw_file) if raw_file else None
    if token_file is None:
        return None
    if not token_file.exists():
        raise CompatPolicyError(
            category="precondition_failed",
            error_code="compat_execution_token_file_missing",
            message=f"execution token file missing: {token_file}",
            retryable=False,
        )
    value = json.loads(token_file.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompatPolicyError(
            category="invalid_request",
            error_code="compat_execution_token_invalid_json",
            message="execution token file must decode to a JSON object",
            retryable=False,
            details={"execution_token_file": str(token_file)},
        )
    return value


def token_context(token: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(token, dict):
        return None
    return {
        "user_id": token.get("user_id"),
        "session_id": token.get("session_id"),
        "task_id": token.get("task_id"),
        "capability_id": token.get("capability_id"),
        "execution_location": token.get("execution_location"),
        "approval_ref": token.get("approval_ref"),
        "taint_summary": token.get("taint_summary"),
        "target_hash": token.get("target_hash"),
        "constraints": token.get("constraints"),
    }


def standalone_policy_context(args: argparse.Namespace | None = None) -> CompatPolicyContext:
    token = load_execution_token(args)
    return CompatPolicyContext(
        mode="standalone-local",
        policyd_socket=resolve_policyd_socket(args),
        execution_token=token,
        token_context=token_context(token),
        verification=None,
        shared_audit_log=resolve_shared_audit_log(args),
    )


def resolve_policy_context(
    args: argparse.Namespace | None,
    *,
    capability_id: str | None,
    execution_location: str,
    consume: bool,
    target_hash: str | None = None,
) -> CompatPolicyContext:
    policyd_socket = resolve_policyd_socket(args)
    shared_audit_log = resolve_shared_audit_log(args)
    token = load_execution_token(args)
    current = CompatPolicyContext(
        mode="standalone-local",
        policyd_socket=policyd_socket,
        execution_token=token,
        token_context=token_context(token),
        verification=None,
        shared_audit_log=shared_audit_log,
    )

    if capability_id is None or policyd_socket is None:
        return current
    if not policyd_socket.exists():
        raise CompatPolicyError(
            category="unavailable",
            error_code="compat_policyd_socket_missing",
            message=f"configured policyd socket missing: {policyd_socket}",
            retryable=True,
            details={"policyd_socket": str(policyd_socket)},
            policy_context=current,
        )
    if token is None:
        raise CompatPolicyError(
            category="precondition_failed",
            error_code="compat_execution_token_missing",
            message=f"{capability_id} requires execution_token when centralized policy is enabled",
            retryable=False,
            details={"policyd_socket": str(policyd_socket)},
            policy_context=current,
        )

    current_context = token_context(token) or {}
    if current_context.get("capability_id") != capability_id:
        raise CompatPolicyError(
            category="permission_denied",
            error_code="compat_execution_token_capability_mismatch",
            message=f"execution token capability mismatch for {capability_id}",
            retryable=False,
            details={
                "expected_capability_id": capability_id,
                "token_capability_id": current_context.get("capability_id"),
            },
            policy_context=current,
        )
    if current_context.get("execution_location") != execution_location:
        raise CompatPolicyError(
            category="permission_denied",
            error_code="compat_execution_token_location_mismatch",
            message=(
                f"execution token location mismatch: expected {execution_location}, "
                f"got {current_context.get('execution_location')}"
            ),
            retryable=False,
            policy_context=current,
        )
    if target_hash is not None and current_context.get("target_hash") not in {None, target_hash}:
        raise CompatPolicyError(
            category="permission_denied",
            error_code="compat_execution_token_target_mismatch",
            message="execution token target_hash does not match the configured target",
            retryable=False,
            details={
                "expected_target_hash": target_hash,
                "token_target_hash": current_context.get("target_hash"),
            },
            policy_context=current,
        )

    verification = rpc_call(
        policyd_socket,
        POLICY_TOKEN_VERIFY,
        {
            "token": token,
            "target_hash": target_hash,
            "consume": consume,
        },
    )
    verified_context = CompatPolicyContext(
        mode="policyd-verified",
        policyd_socket=policyd_socket,
        execution_token=token,
        token_context=current_context,
        verification=verification,
        shared_audit_log=shared_audit_log,
    )
    if not verification.get("valid"):
        raise CompatPolicyError(
            category="permission_denied",
            error_code="compat_execution_token_rejected",
            message=f"execution token rejected: {verification.get('reason')}",
            retryable=False,
            details={"token_verification": verification},
            policy_context=verified_context,
        )
    return verified_context


def rpc_call(socket_path: Path, method: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2.5)
        try:
            client.connect(str(socket_path))
            client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(65536)
                if not chunk:
                    break
                data += chunk
        except OSError as error:
            raise CompatPolicyError(
                category="unavailable",
                error_code="compat_policyd_rpc_failed",
                message=f"failed to contact policyd: {error}",
                retryable=True,
                details={"policyd_socket": str(socket_path)},
            ) from error

    try:
        response = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise CompatPolicyError(
            category="internal",
            error_code="compat_policyd_invalid_response",
            message="policyd returned invalid JSON",
            retryable=True,
            details={"policyd_socket": str(socket_path)},
        ) from error

    if response.get("error"):
        raise CompatPolicyError(
            category="internal",
            error_code="compat_policyd_rpc_error",
            message=f"policyd RPC {method} failed: {response['error']}",
            retryable=True,
            details={"policyd_socket": str(socket_path), "rpc_method": method},
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise CompatPolicyError(
            category="internal",
            error_code="compat_policyd_invalid_result",
            message=f"policyd RPC {method} returned non-object result",
            retryable=True,
            details={"policyd_socket": str(socket_path), "rpc_method": method},
        )
    return result
