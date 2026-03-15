from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


VALID_TRUST_MODES = {"permissive", "allowlist", "deny"}
VALID_REMOTE_AUTH_MODES = {"none", "bearer", "header", "execution-token"}
VALID_REMOTE_ATTESTATION_MODES = {"bootstrap", "verified"}
DEFAULT_AGENTD_SOCKET_ENV = "AIOS_COMPAT_AGENTD_SOCKET"


@dataclass(frozen=True)
class RemoteSupportError(RuntimeError):
    category: str
    error_code: str
    message: str
    retryable: bool = False
    details: dict[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        payload = {
            "category": self.category,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            payload.update(self.details)
        return payload


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
    control_plane_provider_id: str | None = None
    registration_status: str | None = None
    last_heartbeat_at: str | None = None
    heartbeat_ttl_seconds: int | None = None
    revoked_at: str | None = None
    revocation_reason: str | None = None
    attestation: "RemoteAttestation | None" = None
    governance: "RemoteGovernance | None" = None

    def to_payload(self) -> dict[str, object]:
        payload = {
            "provider_ref": self.provider_ref,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "auth_mode": self.auth_mode,
            "auth_header_name": self.auth_header_name,
            "auth_secret_env": self.auth_secret_env,
            "target_hash": self.target_hash,
            "registered_at": self.registered_at,
            "display_name": self.display_name,
            "control_plane_provider_id": self.control_plane_provider_id,
            "registration_status": remote_registration_status(self),
            "last_heartbeat_at": self.last_heartbeat_at,
            "heartbeat_ttl_seconds": self.heartbeat_ttl_seconds,
            "revoked_at": self.revoked_at,
            "revocation_reason": self.revocation_reason,
        }
        if self.attestation is not None:
            payload["attestation"] = self.attestation.to_payload()
        if self.governance is not None:
            payload["governance"] = self.governance.to_payload()
        return payload


@dataclass(frozen=True)
class RemoteAttestation:
    mode: str
    issuer: str | None = None
    subject: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    evidence_ref: str | None = None
    digest: str | None = None
    status: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "issuer": self.issuer,
            "subject": self.subject,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "evidence_ref": self.evidence_ref,
            "digest": self.digest,
            "status": self.status,
        }


@dataclass(frozen=True)
class RemoteGovernance:
    fleet_id: str
    governance_group: str
    policy_group: str | None = None
    registered_by: str | None = None
    approval_ref: str | None = None
    allow_lateral_movement: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "fleet_id": self.fleet_id,
            "governance_group": self.governance_group,
            "policy_group": self.policy_group,
            "registered_by": self.registered_by,
            "approval_ref": self.approval_ref,
            "allow_lateral_movement": self.allow_lateral_movement,
        }


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_rfc3339(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_remote_attestation(payload: object) -> RemoteAttestation | None:
    if not isinstance(payload, dict):
        return None
    mode = optional_text(payload.get("mode"))
    if mode is None:
        return None
    return RemoteAttestation(
        mode=mode,
        issuer=optional_text(payload.get("issuer")),
        subject=optional_text(payload.get("subject")),
        issued_at=optional_text(payload.get("issued_at")),
        expires_at=optional_text(payload.get("expires_at")),
        evidence_ref=optional_text(payload.get("evidence_ref")),
        digest=optional_text(payload.get("digest")),
        status=optional_text(payload.get("status")),
    )


def load_remote_governance(payload: object) -> RemoteGovernance | None:
    if not isinstance(payload, dict):
        return None
    fleet_id = optional_text(payload.get("fleet_id"))
    governance_group = optional_text(payload.get("governance_group"))
    if fleet_id is None or governance_group is None:
        return None
    allow_lateral_movement = payload.get("allow_lateral_movement", False)
    return RemoteGovernance(
        fleet_id=fleet_id,
        governance_group=governance_group,
        policy_group=optional_text(payload.get("policy_group")),
        registered_by=optional_text(payload.get("registered_by")),
        approval_ref=optional_text(payload.get("approval_ref")),
        allow_lateral_movement=bool(allow_lateral_movement),
    )


def remote_target_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.strip().encode("utf-8")).hexdigest()


def remote_registration_status(
    registration: RemoteRegistration,
    *,
    now: datetime | None = None,
) -> str:
    current = (registration.registration_status or "active").strip().lower() or "active"
    if registration.revoked_at:
        return "revoked"
    if current == "revoked":
        return "revoked"
    ttl = registration.heartbeat_ttl_seconds
    if ttl is not None and ttl > 0:
        heartbeat = parse_rfc3339(registration.last_heartbeat_at) or parse_rfc3339(registration.registered_at)
        if heartbeat is None:
            return "stale"
        current_time = now or datetime.now(timezone.utc)
        if (current_time - heartbeat).total_seconds() > ttl:
            return "stale"
    return current


def remote_registration_summary(registrations: list[RemoteRegistration]) -> dict[str, object]:
    counts: dict[str, int] = {}
    stale_provider_refs: list[str] = []
    revoked_provider_refs: list[str] = []
    for registration in registrations:
        status = remote_registration_status(registration)
        counts[status] = counts.get(status, 0) + 1
        if status == "stale":
            stale_provider_refs.append(registration.provider_ref)
        if status == "revoked":
            revoked_provider_refs.append(registration.provider_ref)
    return {
        "counts": counts,
        "stale_provider_refs": sorted(stale_provider_refs),
        "revoked_provider_refs": sorted(revoked_provider_refs),
    }


def touch_remote_registration(
    registration: RemoteRegistration,
    *,
    timestamp: str | None = None,
) -> RemoteRegistration:
    touched_at = timestamp or utc_now()
    return replace(
        registration,
        registration_status="active",
        last_heartbeat_at=touched_at,
        revoked_at=None,
        revocation_reason=None,
    )


def revoke_remote_registration(
    registration: RemoteRegistration,
    *,
    reason: str | None = None,
    timestamp: str | None = None,
) -> RemoteRegistration:
    revoked_at = timestamp or utc_now()
    return replace(
        registration,
        registration_status="revoked",
        revoked_at=revoked_at,
        revocation_reason=reason or registration.revocation_reason,
    )


def find_remote_registration(
    registrations: list[RemoteRegistration],
    *,
    provider_ref: str | None = None,
    endpoint: str | None = None,
) -> tuple[int, RemoteRegistration] | tuple[None, None]:
    for index, registration in enumerate(registrations):
        if provider_ref and registration.provider_ref == provider_ref:
            return index, registration
        if endpoint and registration.endpoint == endpoint:
            return index, registration
    return None, None


def resolve_remote_registry_path(
    *,
    explicit: Path | None,
    env_var: str,
    state_subdir: str,
) -> Path:
    if explicit is not None:
        return explicit
    raw = os.environ.get(env_var)
    if raw:
        return Path(raw)
    return (
        Path.home()
        / ".local"
        / "state"
        / "aios"
        / state_subdir
        / "remote-registry.json"
    )


def load_remote_registry(
    *,
    explicit: Path | None,
    env_var: str,
    state_subdir: str,
) -> tuple[Path, list[RemoteRegistration]]:
    path = resolve_remote_registry_path(
        explicit=explicit,
        env_var=env_var,
        state_subdir=state_subdir,
    )
    if not path.exists():
        return path, []

    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise RuntimeError(f"remote registry entries must be a list: {path}")

    registrations: list[RemoteRegistration] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        endpoint = str(item.get("endpoint") or "")
        registrations.append(
            RemoteRegistration(
                provider_ref=str(item.get("provider_ref") or ""),
                endpoint=endpoint,
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
                target_hash=str(item.get("target_hash") or remote_target_hash(endpoint)),
                registered_at=str(item.get("registered_at") or ""),
                display_name=(
                    str(item.get("display_name"))
                    if item.get("display_name") is not None
                    else None
                ),
                control_plane_provider_id=(
                    str(item.get("control_plane_provider_id"))
                    if item.get("control_plane_provider_id") is not None
                    else None
                ),
                registration_status=optional_text(item.get("registration_status")),
                last_heartbeat_at=optional_text(item.get("last_heartbeat_at")),
                heartbeat_ttl_seconds=optional_int(item.get("heartbeat_ttl_seconds")),
                revoked_at=optional_text(item.get("revoked_at")),
                revocation_reason=optional_text(item.get("revocation_reason")),
                attestation=load_remote_attestation(item.get("attestation")),
                governance=load_remote_governance(item.get("governance")),
            )
        )
    return path, registrations


def write_remote_registry(path: Path, registrations: list[RemoteRegistration]) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "entries": [registration.to_payload() for registration in registrations],
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def upsert_remote_registration(
    registrations: list[RemoteRegistration],
    registration: RemoteRegistration,
) -> list[RemoteRegistration]:
    _, existing = find_remote_registration(
        registrations,
        provider_ref=registration.provider_ref,
        endpoint=registration.endpoint,
    )
    if existing is not None:
        registration = replace(
            registration,
            control_plane_provider_id=registration.control_plane_provider_id or existing.control_plane_provider_id,
        )
    updated = [
        item
        for item in registrations
        if item.provider_ref != registration.provider_ref and item.endpoint != registration.endpoint
    ]
    updated.append(registration)
    updated.sort(key=lambda item: (item.provider_ref, item.endpoint))
    return updated


def remove_remote_registration(
    registrations: list[RemoteRegistration],
    *,
    provider_ref: str | None = None,
    endpoint: str | None = None,
) -> tuple[list[RemoteRegistration], RemoteRegistration | None]:
    index, match = find_remote_registration(registrations, provider_ref=provider_ref, endpoint=endpoint)
    if index is None or match is None:
        return registrations, None
    updated = registrations[:index] + registrations[index + 1 :]
    return updated, match


def resolve_trust_policy(
    *,
    mode_env: str,
    allowlist_env: str,
    default_mode: str = "permissive",
) -> dict[str, object]:
    configured_mode = os.environ.get(mode_env, default_mode).strip().lower()
    if not configured_mode:
        configured_mode = default_mode

    allowlist = [
        item.strip()
        for item in os.environ.get(allowlist_env, "").split(",")
        if item.strip()
    ]
    mode = configured_mode if configured_mode in VALID_TRUST_MODES else "invalid"
    notes: list[str] = []
    status = "available"

    if mode == "invalid":
        status = "degraded"
        notes.append(f"Unrecognized trust mode in {mode_env}")
    elif mode == "permissive":
        status = "degraded"
        notes.append(f"Trust policy is permissive; configure {mode_env}=allowlist for enforcement")
    elif mode == "allowlist":
        if allowlist:
            notes.append(f"Endpoint host must match {allowlist_env}")
        else:
            status = "degraded"
            notes.append(f"{mode_env}=allowlist requires at least one {allowlist_env} entry")
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


def validate_endpoint(
    endpoint: str,
    trust_policy: dict[str, object],
    *,
    error_prefix: str,
) -> dict[str, object]:
    target = target_details(endpoint)
    if target["scheme"] not in {"http", "https"}:
        raise RemoteSupportError(
            category="invalid_request",
            error_code=f"{error_prefix}_unsupported_endpoint_scheme",
            message=f"unsupported endpoint scheme: {target['scheme'] or '<none>'}",
            details={"target": target},
        )
    if not target["authority"]:
        raise RemoteSupportError(
            category="invalid_request",
            error_code=f"{error_prefix}_endpoint_host_missing",
            message="endpoint must include host",
            details={"target": target},
        )

    mode = str(trust_policy.get("mode", "invalid"))
    allowlist = [
        value
        for value in trust_policy.get("allowlist", [])
        if isinstance(value, str) and value.strip()
    ]
    if mode == "invalid":
        raise RemoteSupportError(
            category="precondition_failed",
            error_code=f"{error_prefix}_invalid_trust_mode",
            message="invalid remote trust policy configuration",
            details={"target": target, "trust_policy": trust_policy},
        )
    if mode == "deny":
        raise RemoteSupportError(
            category="permission_denied",
            error_code=f"{error_prefix}_remote_calls_denied",
            message="remote bridge calls are disabled by trust policy",
            details={"target": target, "trust_policy": trust_policy},
        )
    if mode == "allowlist":
        if not allowlist:
            raise RemoteSupportError(
                category="precondition_failed",
                error_code=f"{error_prefix}_allowlist_missing",
                message="allowlist trust mode requires at least one allowed host",
                details={"target": target, "trust_policy": trust_policy},
            )
        if target["host"] not in allowlist and target["authority"] not in allowlist:
            raise RemoteSupportError(
                category="permission_denied",
                error_code=f"{error_prefix}_endpoint_not_allowlisted",
                message=f"endpoint host not allowlisted: {target['host'] or target['authority']}",
                details={"target": target, "trust_policy": trust_policy},
            )
    return target


def encode_execution_token(token: dict[str, object]) -> str:
    encoded = json.dumps(token, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii")


def post_json(
    endpoint: str,
    payload: object,
    *,
    timeout_seconds: float,
    trust_policy: dict[str, object],
    error_prefix: str,
    user_agent: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    target = validate_endpoint(endpoint, trust_policy, error_prefix=error_prefix)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
    if extra_headers:
        headers.update(extra_headers)
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            status_code = getattr(response, "status", None) or response.getcode() or 200
    except HTTPError as exc:
        body = exc.read()
        response_payload = _decode_remote_body(body)
        raise RemoteSupportError(
            category="remote_error",
            error_code=f"{error_prefix}_remote_http_error",
            message=f"remote endpoint returned HTTP {exc.code}",
            retryable=exc.code >= 500,
            details={
                "target": target,
                "status_code": exc.code,
                "response": response_payload,
            },
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise RemoteSupportError(
            category="timeout",
            error_code=f"{error_prefix}_remote_timeout",
            message=f"remote endpoint timed out after {timeout_seconds}s",
            retryable=True,
            details={"target": target},
        ) from exc
    except URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            raise RemoteSupportError(
                category="timeout",
                error_code=f"{error_prefix}_remote_timeout",
                message=f"remote endpoint timed out after {timeout_seconds}s",
                retryable=True,
                details={"target": target},
            ) from exc
        raise RemoteSupportError(
            category="unavailable",
            error_code=f"{error_prefix}_remote_unavailable",
            message=f"remote endpoint unavailable: {exc.reason}",
            retryable=True,
            details={"target": target},
        ) from exc

    return {
        "target": target,
        "status_code": status_code,
        "content_type": content_type,
        "response": _decode_remote_body(body),
    }


def agentd_socket_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    raw = os.environ.get(DEFAULT_AGENTD_SOCKET_ENV)
    if raw:
        return Path(raw)
    return Path("/run/aios/agentd/agentd.sock")


def agentd_rpc(socket_path: Path, method: str, params: dict[str, object], *, error_prefix: str) -> dict[str, object]:
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
        except OSError as exc:
            raise RemoteSupportError(
                category="unavailable",
                error_code=f"{error_prefix}_agentd_rpc_failed",
                message=f"failed to contact agentd: {exc}",
                retryable=True,
                details={"agentd_socket": str(socket_path)},
            ) from exc

    try:
        response = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RemoteSupportError(
            category="internal",
            error_code=f"{error_prefix}_agentd_invalid_response",
            message="agentd returned invalid JSON",
            retryable=True,
            details={"agentd_socket": str(socket_path)},
        ) from exc

    if response.get("error"):
        raise RemoteSupportError(
            category="internal",
            error_code=f"{error_prefix}_agentd_rpc_error",
            message=f"agentd RPC failed: {response['error']}",
            retryable=True,
            details={"agentd_socket": str(socket_path), "rpc_error": response["error"]},
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise RemoteSupportError(
            category="internal",
            error_code=f"{error_prefix}_agentd_result_invalid",
            message="agentd returned a non-object result",
            retryable=True,
            details={"agentd_socket": str(socket_path)},
        )
    return result


def normalize_remote_provider_id(prefix: str, provider_ref: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", provider_ref.strip().lower()).strip("-")
    normalized = normalized or "remote"
    return f"{prefix}.{normalized}"


def _decode_remote_body(body: bytes) -> object:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")
