#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prototype import default_sessiond_socket, handle_kind_summary, load_handles


STATUS_TONES = {
    "pending": "warning",
    "ready": "neutral",
    "selected": "positive",
    "confirmed": "positive",
    "awaiting-approval": "warning",
    "cancelled": "neutral",
    "failed": "critical",
    "timed-out": "critical",
}

KIND_LABELS = {
    "file_handle": "File",
    "directory_handle": "Directory",
    "export_target_handle": "Export Target",
    "screen_share_handle": "Screen Share",
    "window_handle": "Window",
    "contact_ref": "Contact",
    "remote_account_ref": "Remote Account",
}

KIND_PRIORITY = {
    "screen_share_handle": 40,
    "window_handle": 32,
    "export_target_handle": 24,
    "file_handle": 16,
    "directory_handle": 12,
    "contact_ref": 8,
    "remote_account_ref": 8,
}

TERMINAL_STATUSES = {"confirmed", "awaiting-approval", "cancelled", "timed-out"}
EVENT_HISTORY_LIMIT = 16
POLICY_TOKEN_ISSUE = "policy.token.issue"
DEVICE_CAPTURE_REQUEST = "device.capture.request"
DEFAULT_POLICYD_SOCKET = Path("/run/aios/policyd/policyd.sock")
DEFAULT_DEVICED_SOCKET = Path("/run/aios/deviced/deviced.sock")
DEFAULT_SCREEN_CAPTURE_PROVIDER_SOCKET = Path(
    "/run/aios/screen-provider/screen-capture-provider.sock"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tone_for_status(status: str | None) -> str:
    if not status:
        return "neutral"
    return STATUS_TONES.get(status, "neutral")


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


def rpc_call(socket_path: Path, method: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
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
        raise RuntimeError(str(response["error"]))
    return response["result"]


def scope_string(scope: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = scope.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def scope_bool(scope: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = scope.get(key)
        if isinstance(value, bool):
            return value
    return False


def screen_capture_request_from_handle(
    session_id: str | None,
    task_id: str | None,
    handle: dict[str, Any],
) -> dict[str, Any]:
    scope = handle_scope(handle)
    target = str(handle.get("target") or "screen://current-display")
    window_ref = scope_string(scope, "window_ref", "focused_window_ref")
    if target.startswith("window://"):
        window_ref = target.split("://", 1)[1]
    source_device = scope_string(scope, "display_ref", "source_device", "monitor_ref")
    continuous = scope_bool(scope, "continuous") or scope_string(scope, "capture_mode") == "continuous"
    return {
        "modality": "screen",
        "session_id": session_id,
        "task_id": task_id,
        "continuous": continuous,
        "window_ref": window_ref,
        "source_device": source_device,
    }


def screen_capture_scope_constraints(handle: dict[str, Any]) -> dict[str, Any]:
    scope = handle_scope(handle)
    constraints: dict[str, Any] = {}

    for key in ("window_ref", "display_ref", "portal_session_ref"):
        value = scope_string(scope, key)
        if value:
            constraints[key] = value

    if "continuous" in scope and isinstance(scope.get("continuous"), bool):
        constraints["continuous"] = scope["continuous"]

    return constraints


def invoke_screen_capture_chain(
    *,
    policy_socket: Path,
    deviced_socket: Path,
    screen_provider_socket: Path,
    user_id: str,
    session_id: str | None,
    task_id: str | None,
    request: dict[str, Any],
    handle: dict[str, Any],
) -> dict[str, Any]:
    capability_id = str(request.get("capability_id") or "device.capture.screen.read")
    approval_ref = request.get("approval_ref")
    capture_request = screen_capture_request_from_handle(session_id, task_id, handle)

    if (
        screen_provider_socket.exists()
        and policy_socket.exists()
        and session_id not in (None, "")
        and task_id not in (None, "")
    ):
        scope_constraints = screen_capture_scope_constraints(handle)
        target_hash = scope_string(handle_scope(handle), "target_hash")
        token_payload = {
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "execution_location": "local",
            "constraints": scope_constraints,
        }
        if target_hash:
            token_payload["target_hash"] = target_hash
        if approval_ref not in (None, ""):
            token_payload["approval_ref"] = approval_ref
        token = rpc_call(policy_socket, POLICY_TOKEN_ISSUE, token_payload)
        provider_result = rpc_call(
            screen_provider_socket,
            capability_id,
            {
                "execution_token": token,
                "portal_handle": handle,
            },
        )
        return {
            "invoked": True,
            "transport": "screen-provider",
            "provider_id": provider_result.get("provider_id"),
            "capture_request": provider_result.get("capture_request") or capture_request,
            "capture": provider_result.get("capture"),
            "preview_object": provider_result.get("preview_object"),
            "selected_target": provider_result.get("selected_target") or handle.get("target"),
        }

    if deviced_socket.exists():
        capture_response = rpc_call(deviced_socket, DEVICE_CAPTURE_REQUEST, capture_request)
        return {
            "invoked": True,
            "transport": "deviced-direct",
            "provider_id": None,
            "capture_request": capture_request,
            "capture": capture_response.get("capture"),
            "preview_object": capture_response.get("preview_object"),
            "selected_target": handle.get("target"),
        }

    return {
        "invoked": False,
        "transport": "not-configured",
        "provider_id": None,
        "capture_request": capture_request,
        "capture": None,
        "preview_object": None,
        "selected_target": handle.get("target"),
    }


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


def availability_reason_text(status: str, handle: dict[str, Any], retry_after: str | None) -> str:
    if status == "revoked":
        revoked_at = handle.get("revoked_at")
        return f"Handle was revoked at {revoked_at}" if revoked_at else "Handle was revoked"
    if status == "expired":
        expiry = handle.get("expiry")
        return f"Handle expired at {expiry}" if expiry else "Handle expired"
    if status == "resource-missing":
        return "Requested resource is no longer available"
    if status == "backend-unavailable":
        return "Required backend is currently unavailable"
    if status == "retry-later" and retry_after:
        return f"Resource can be retried after {retry_after}"
    if status == "retry-later":
        return "Resource is temporarily unavailable; retry later"
    if status == "unavailable":
        return "Requested resource is unavailable"
    return ""


def handle_availability_details(handle: dict[str, Any]) -> dict[str, Any]:
    scope = handle_scope(handle)
    retry_after = str(handle.get("retry_after") or scope.get("retry_after") or "").strip() or None

    if handle.get("revoked_at"):
        return {
            "status": "revoked",
            "selectable": False,
            "reason": availability_reason_text("revoked", handle, retry_after),
            "retry_after": retry_after,
        }

    expiry = parse_timestamp(handle.get("expiry"))
    if expiry is not None and expiry <= datetime.now(timezone.utc):
        return {
            "status": "expired",
            "selectable": False,
            "reason": availability_reason_text("expired", handle, retry_after),
            "retry_after": retry_after,
        }

    availability = normalize_handle_availability(handle.get("availability") or scope.get("availability"))
    if handle.get("resource_missing") or scope.get("resource_missing"):
        availability = "resource-missing"
    elif handle.get("backend_available") is False or scope.get("backend_available") is False:
        availability = "backend-unavailable"
    elif availability == "unavailable" and retry_after is not None:
        availability = "retry-later"

    if availability != "available":
        reason = str(handle.get("unavailable_reason") or scope.get("unavailable_reason") or "").strip() or None
        return {
            "status": availability,
            "selectable": False,
            "reason": reason or availability_reason_text(availability, handle, retry_after),
            "retry_after": retry_after,
        }

    return {
        "status": "available",
        "selectable": True,
        "reason": None,
        "retry_after": retry_after,
    }


def load_fixture_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text() or "{}")
    if not isinstance(payload, dict):
        raise SystemExit(f"invalid chooser fixture payload: {path}")
    return payload


def save_fixture_payload(path: Path, payload: dict[str, Any]) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def requested_kinds(request: dict[str, Any]) -> list[str]:
    values = request.get("requested_kinds")
    if isinstance(values, list):
        return [str(item) for item in values if str(item).strip()]
    requested_kind = request.get("requested_kind")
    if requested_kind not in (None, ""):
        return [str(requested_kind)]
    return []


def display_kind(kind: str | None) -> str:
    if not kind:
        return "Unknown"
    return KIND_LABELS.get(kind, kind.replace("_", " ").title())


def target_label(handle: dict[str, Any]) -> str:
    scope = handle.get("scope") or {}
    if isinstance(scope, dict):
        for key in ("display_name", "title", "label"):
            value = scope.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    target = str(handle.get("target") or "-")
    if target == "window://focused":
        return "Focused Window"
    if target == "screen://current-display":
        return "Current Display"
    if "://" in target:
        _, suffix = target.split("://", 1)
        return suffix or target
    if "/" in target:
        return target.rstrip("/").rsplit("/", 1)[-1] or target
    return target


def handle_availability(handle: dict[str, Any]) -> tuple[str, bool]:
    details = handle_availability_details(handle)
    return str(details.get("status") or "available"), bool(details.get("selectable"))


def handle_matches_requested_kind(handle: dict[str, Any], kinds: list[str]) -> bool:
    if not kinds:
        return True
    return str(handle.get("kind")) in kinds


def handle_priority(handle: dict[str, Any], request: dict[str, Any]) -> int:
    status, selectable = handle_availability(handle)
    if not selectable:
        if status == "revoked":
            return -1000
        if status in {"resource-missing", "backend-unavailable", "unavailable"}:
            return -900
        return -800

    requested = requested_kinds(request)
    handle_id = str(handle.get("handle_id") or "")
    target = str(handle.get("target") or "")
    priority = KIND_PRIORITY.get(str(handle.get("kind") or ""), 0)

    if handle_matches_requested_kind(handle, requested):
        priority += 120
    if handle_id == request.get("selected_handle_id"):
        priority += 240
    if handle_id == request.get("confirmed_handle_id"):
        priority += 320
    if target == "window://focused":
        priority += 12
    if target == "screen://current-display":
        priority += 8
    return priority


def find_handle(handles: list[dict[str, Any]], handle_id: str | None) -> dict[str, Any] | None:
    if not handle_id:
        return None
    return next((item for item in handles if item.get("handle_id") == handle_id), None)


def choose_focus_handle(handles: list[dict[str, Any]], request: dict[str, Any]) -> dict[str, Any] | None:
    if not handles:
        return None
    ranked = sorted(
        handles,
        key=lambda handle: (
            -handle_priority(handle, request),
            target_label(handle).lower(),
            str(handle.get("handle_id") or ""),
        ),
    )
    return ranked[0]


def default_title(requested: list[str]) -> str:
    if not requested:
        return "Portal Chooser"
    if len(requested) == 1:
        return f"Choose {display_kind(requested[0])}"
    return "Choose Portal Target"


def default_subtitle(session_id: str | None, requested: list[str], handle_count: int) -> str:
    session_label = f"session {session_id}" if session_id else "no active session"
    requested_label = ", ".join(display_kind(kind) for kind in requested) if requested else "any handle"
    return f"{session_label} · {requested_label} · {handle_count} candidates"


def normalize_request(request: dict[str, Any] | None, handles: list[dict[str, Any]], session_id: str | None) -> dict[str, Any]:
    payload = dict(request or {})
    payload["chooser_id"] = str(payload.get("chooser_id") or "portal-chooser")

    requested = requested_kinds(payload)
    payload["requested_kinds"] = requested
    payload["selection_mode"] = str(payload.get("selection_mode") or "single")
    payload["approval_status"] = str(payload.get("approval_status") or "not-required")
    payload["attempt_count"] = int(payload.get("attempt_count") or 0)
    payload["max_attempts"] = max(1, int(payload.get("max_attempts") or 3))

    status = str(payload.get("status") or "").strip().lower()
    if status in {"timeout", "timed_out"} or payload.get("timed_out"):
        status = "timed-out"
    elif not status:
        if payload.get("confirmed_handle_id"):
            status = "confirmed"
        elif payload.get("selected_handle_id"):
            status = "selected"
        elif handles:
            status = "ready"
        else:
            status = "pending"

    valid_statuses = set(STATUS_TONES)
    if status not in valid_statuses:
        status = "ready" if handles else "pending"
    if status == "selected" and not payload.get("selected_handle_id"):
        status = "ready" if handles else "pending"
    if status == "confirmed" and not payload.get("confirmed_handle_id"):
        status = "selected" if payload.get("selected_handle_id") else ("ready" if handles else "pending")

    matching_handles = [handle for handle in handles if handle_matches_requested_kind(handle, requested)]
    selectable_handles = [handle for handle in handles if handle_availability(handle)[1]]
    selectable_matching = [handle for handle in matching_handles if handle_availability(handle)[1]]
    unavailable_matching = [handle for handle in matching_handles if not handle_availability(handle)[1]]

    if status in {"pending", "ready"}:
        if handles and not selectable_handles:
            status = "failed"
        elif requested and matching_handles and not selectable_matching and unavailable_matching:
            status = "failed"

    payload["status"] = status
    payload["title"] = str(payload.get("title") or default_title(requested))
    payload["subtitle"] = str(payload.get("subtitle") or default_subtitle(session_id, requested, len(handles)))
    if not payload.get("retry_after"):
        retry_source = next(
            (
                handle_availability_details(handle).get("retry_after")
                for handle in (unavailable_matching or handles)
                if handle_availability_details(handle).get("retry_after")
            ),
            None,
        )
        if retry_source:
            payload["retry_after"] = retry_source

    if status == "failed" and not payload.get("error_message"):
        message = str(payload.get("last_unavailable_reason") or "").strip()
        if not message:
            failure_handle = next(
                (
                    handle
                    for handle in (unavailable_matching or handles)
                    if not handle_availability(handle)[1]
                ),
                None,
            )
            if failure_handle is not None:
                message = str(handle_availability_details(failure_handle).get("reason") or "").strip()
        if message:
            payload["error_message"] = message

    history = payload.get("history")
    if isinstance(history, list):
        payload["history"] = [item for item in history if isinstance(item, dict)][-EVENT_HISTORY_LIMIT:]
    else:
        payload["history"] = []
    return payload


def chooser_fixture_request(fixture: Path | None) -> dict[str, Any]:
    if fixture is None:
        return {}
    return load_fixture_payload(fixture).get("request") or {}


def list_handles_with_request(
    socket_path: Path,
    session_id: str | None,
    fixture: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    handles = load_handles(socket_path, session_id, fixture)
    request = normalize_request(chooser_fixture_request(fixture), handles, session_id)
    return handles, request


def handle_item_status(
    handle: dict[str, Any],
    request: dict[str, Any],
    focus_handle_id: str | None,
) -> str:
    availability, selectable = handle_availability(handle)
    handle_id = str(handle.get("handle_id") or "")
    if handle_id and handle_id == request.get("confirmed_handle_id"):
        return "confirmed"
    if handle_id and handle_id == request.get("selected_handle_id"):
        return "selected"
    if not selectable:
        return availability
    if handle_id and handle_id == focus_handle_id:
        return "recommended"
    return "available"


def availability_tone(status: str) -> str:
    if status in {"revoked", "resource-missing", "backend-unavailable", "unavailable"}:
        return "critical"
    if status in {"expired", "retry-later"}:
        return "warning"
    if status in {"selected", "confirmed"}:
        return "positive"
    if status == "recommended":
        return "warning"
    return "neutral"


def scope_summary(handle: dict[str, Any]) -> list[str]:
    scope = handle_scope(handle)

    summary: list[str] = []
    for key in (
        "display_name",
        "backend",
        "resolution",
        "window_ref",
        "display_ref",
        "portal_session_ref",
        "continuous",
        "adapter_id",
        "export_format",
        "export_label",
        "target_hash",
    ):
        value = scope.get(key)
        if value not in (None, "", [], {}):
            summary.append(f"{key}={value}")
    return summary


def selection_detail_items(handle: dict[str, Any] | None) -> list[dict[str, Any]]:
    if handle is None:
        return []

    availability = handle_availability_details(handle)
    scope = handle_scope(handle)
    items = [
        {
            "label": "Handle ID",
            "value": handle.get("handle_id", "-"),
            "tone": "neutral",
        },
        {
            "label": "Kind",
            "value": display_kind(handle.get("kind")),
            "tone": "neutral",
        },
        {
            "label": "Target",
            "value": handle.get("target", "-"),
            "tone": "neutral",
        },
        {
            "label": "Availability",
            "value": availability.get("status", "available"),
            "tone": availability_tone(str(availability.get("status") or "available")),
        },
    ]

    if availability.get("reason"):
        items.append(
            {
                "label": "Unavailable Reason",
                "value": availability["reason"],
                "tone": "critical" if availability.get("status") != "expired" else "warning",
            }
        )
    if availability.get("retry_after"):
        items.append(
            {
                "label": "Retry After",
                "value": availability["retry_after"],
                "tone": "warning",
            }
        )

    for key in (
        "display_name",
        "backend",
        "resolution",
        "window_ref",
        "display_ref",
        "portal_session_ref",
        "continuous",
        "adapter_id",
        "export_format",
        "export_label",
        "target_hash",
    ):
        value = scope.get(key)
        if value not in (None, "", [], {}):
            items.append(
                {
                    "label": key,
                    "value": value,
                    "tone": "neutral",
                }
            )

    audit_tags = handle.get("audit_tags")
    if isinstance(audit_tags, list) and audit_tags:
        items.append(
            {
                "label": "Audit Tags",
                "value": ", ".join(str(tag) for tag in audit_tags),
                "tone": "neutral",
            }
        )
    return items


def approval_route_required(request: dict[str, Any]) -> bool:
    return request.get("approval_status") in {"required", "pending"} and bool(
        request.get("approval_ref") or request.get("capability_id")
    )


def request_section_items(
    request: dict[str, Any],
    selected_handle: dict[str, Any] | None,
    confirmed_handle: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    items = [
        {
            "label": "Chooser Status",
            "value": request.get("status"),
            "tone": tone_for_status(request.get("status")),
        },
        {
            "label": "Requested Kinds",
            "value": ", ".join(display_kind(kind) for kind in request.get("requested_kinds", [])) or "Any",
            "tone": "neutral",
        },
        {
            "label": "Selection Mode",
            "value": request.get("selection_mode", "single"),
            "tone": "neutral",
        },
        {
            "label": "Approval",
            "value": request.get("approval_status", "not-required"),
            "tone": "warning" if request.get("approval_status") in {"required", "pending"} else "neutral",
        },
        {
            "label": "Attempts",
            "value": f"{request.get('attempt_count', 0)} / {request.get('max_attempts', 1)}",
            "tone": "neutral",
        },
    ]

    if selected_handle is not None:
        items.append(
            {
                "label": "Selected Target",
                "value": f"{target_label(selected_handle)} ({display_kind(selected_handle.get('kind'))})",
                "tone": "positive",
            }
        )
    if confirmed_handle is not None:
        items.append(
            {
                "label": "Confirmed Target",
                "value": f"{target_label(confirmed_handle)} ({display_kind(confirmed_handle.get('kind'))})",
                "tone": "positive",
            }
        )
    if request.get("expires_at"):
        items.append(
            {
                "label": "Expires At",
                "value": request["expires_at"],
                "tone": "neutral",
            }
        )
    if request.get("error_message"):
        items.append(
            {
                "label": "Last Error",
                "value": request["error_message"],
                "tone": "critical" if request.get("status") in {"failed", "timed-out"} else "warning",
            }
        )
    if request.get("last_unavailable_reason") and request.get("last_unavailable_reason") != request.get("error_message"):
        items.append(
            {
                "label": "Unavailable Reason",
                "value": request["last_unavailable_reason"],
                "tone": "warning",
            }
        )
    if request.get("retry_after"):
        items.append(
            {
                "label": "Retry After",
                "value": request["retry_after"],
                "tone": "warning",
            }
        )
    if request.get("approval_ref"):
        items.append(
            {
                "label": "Approval Ref",
                "value": request["approval_ref"],
                "tone": "warning",
            }
        )
    if request.get("capability_id"):
        items.append(
            {
                "label": "Capability",
                "value": request["capability_id"],
                "tone": "warning" if request.get("approval_status") in {"required", "pending"} else "neutral",
            }
        )
    if request.get("capture_transport"):
        items.append(
            {
                "label": "Capture Chain",
                "value": request["capture_transport"],
                "tone": "positive" if request.get("capture_status") == "sampled" else "neutral",
            }
        )
    if request.get("capture_status"):
        items.append(
            {
                "label": "Capture Status",
                "value": request["capture_status"],
                "tone": "positive" if request.get("capture_status") == "sampled" else "warning",
            }
        )
    if request.get("capture_id"):
        items.append(
            {
                "label": "Capture ID",
                "value": request["capture_id"],
                "tone": "positive",
            }
        )
    if request.get("capture_provider_id"):
        items.append(
            {
                "label": "Capture Provider",
                "value": request["capture_provider_id"],
                "tone": "neutral",
            }
        )
    audit_tags = request.get("audit_tags")
    if isinstance(audit_tags, list) and audit_tags:
        items.append(
            {
                "label": "Audit Tags",
                "value": ", ".join(str(tag) for tag in audit_tags),
                "tone": "neutral",
            }
        )
    return items


def history_section_items(request: dict[str, Any]) -> list[dict[str, Any]]:
    history = request.get("history")
    if not isinstance(history, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in reversed(history[-6:]):
        if not isinstance(entry, dict):
            continue
        action = entry.get("action", "unknown")
        status = entry.get("status", "unknown")
        detail_bits = []
        if entry.get("selected_handle_id"):
            detail_bits.append(f"selected={entry['selected_handle_id']}")
        if entry.get("confirmed_handle_id"):
            detail_bits.append(f"confirmed={entry['confirmed_handle_id']}")
        if entry.get("target_component"):
            detail_bits.append(f"route={entry['target_component']}")
        if entry.get("reason"):
            detail_bits.append(f"reason={entry['reason']}")
        if entry.get("error_message"):
            detail_bits.append(f"error={entry['error_message']}")
        if entry.get("unavailable_reason"):
            detail_bits.append(f"unavailable={entry['unavailable_reason']}")
        if entry.get("retry_after"):
            detail_bits.append(f"retry_after={entry['retry_after']}")
        if entry.get("capture_transport"):
            detail_bits.append(f"capture={entry['capture_transport']}")
        if entry.get("capture_status"):
            detail_bits.append(f"capture_status={entry['capture_status']}")
        if entry.get("capture_id"):
            detail_bits.append(f"capture_id={entry['capture_id']}")
        items.append(
            {
                "label": entry.get("recorded_at", "-"),
                "value": f"{action} [{status}]" + (f" · {' · '.join(detail_bits)}" if detail_bits else ""),
                "tone": tone_for_status(status),
            }
        )
    return items


def build_model(handles: list[dict[str, Any]], session_id: str | None, request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = normalize_request(request, handles, session_id)
    summary = handle_kind_summary(handles)
    selected_handle = find_handle(handles, request.get("selected_handle_id"))
    confirmed_handle = find_handle(handles, request.get("confirmed_handle_id"))
    focus_handle = choose_focus_handle(handles, request)
    focus_handle_id = focus_handle.get("handle_id") if focus_handle else None
    requested = request.get("requested_kinds", [])
    requested_unavailable_handle = next(
        (
            handle
            for handle in handles
            if handle_matches_requested_kind(handle, requested) and not handle_availability(handle)[1]
        ),
        None,
    )
    detail_handle = confirmed_handle or selected_handle or requested_unavailable_handle or focus_handle

    handle_items = []
    matching_handle_count = 0
    selectable_handle_count = 0
    unavailable_handle_count = 0
    request_closed = request.get("status") in TERMINAL_STATUSES

    ranked_handles = sorted(
        handles,
        key=lambda handle: (
            -handle_priority(handle, request),
            target_label(handle).lower(),
            str(handle.get("handle_id") or ""),
        ),
    )

    for handle in ranked_handles:
        handle_id = str(handle.get("handle_id") or "")
        availability_details = handle_availability_details(handle)
        availability = str(availability_details.get("status") or "available")
        selectable = bool(availability_details.get("selectable"))
        status = handle_item_status(handle, request, focus_handle_id)
        matches_requested = handle_matches_requested_kind(handle, requested)
        if matches_requested:
            matching_handle_count += 1
        if selectable:
            selectable_handle_count += 1
        else:
            unavailable_handle_count += 1

        action = {
            "action_id": "select-handle",
            "label": "Select",
            "handle_id": handle_id,
            "enabled": selectable and not request_closed,
        }
        if not matches_requested and requested:
            action["reason"] = "kind-mismatch"
        elif not selectable and availability_details.get("reason"):
            action["reason"] = availability_details["reason"]

        value_parts = [str(handle.get("target") or "-"), *scope_summary(handle)]
        if not selectable:
            value_parts.append(f"availability={availability}")
            if availability_details.get("reason"):
                value_parts.append(f"reason={availability_details['reason']}")
            if availability_details.get("retry_after"):
                value_parts.append(f"retry_after={availability_details['retry_after']}")

        handle_items.append(
            {
                "label": target_label(handle),
                "value": " · ".join(value_parts),
                "status": status,
                "kind": display_kind(handle.get("kind")),
                "handle_id": handle_id,
                "tone": availability_tone(status),
                "action": action,
            }
        )

    confirm_handle = selected_handle or confirmed_handle or focus_handle
    confirm_matches_request = confirm_handle is not None and handle_matches_requested_kind(confirm_handle, requested)
    no_selectable_requested = bool(requested) and matching_handle_count > 0 and not any(
        handle_availability(handle)[1] for handle in handles if handle_matches_requested_kind(handle, requested)
    )
    allow_focus_confirmation = not requested or confirm_matches_request or not no_selectable_requested
    if selected_handle is None and confirmed_handle is None and not allow_focus_confirmation:
        confirm_handle = None

    confirm_handle_details = handle_availability_details(confirm_handle) if confirm_handle is not None else None
    preferred_requested_handle = pick_requested_handle(handles, request)
    prefer_requested_enabled = bool(preferred_requested_handle) and (
        preferred_requested_handle.get("handle_id") != request.get("selected_handle_id")
    )

    actions = [
        {
            "action_id": "refresh",
            "label": "Refresh Handles",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "prefer-requested",
            "label": "Prefer Requested Kind",
            "enabled": prefer_requested_enabled and not request_closed,
            "tone": "warning" if requested else "neutral",
        },
        {
            "action_id": "confirm-selection",
            "label": "Confirm Selection",
            "enabled": (
                confirm_handle is not None
                and bool(confirm_handle_details and confirm_handle_details.get("selectable"))
                and request.get("status") not in {"confirmed", "awaiting-approval", "cancelled", "timed-out", "failed"}
            ),
            "tone": "positive",
            "handle_id": confirm_handle.get("handle_id") if confirm_handle else None,
            "reason": None if confirm_handle_details is None else confirm_handle_details.get("reason"),
        },
        {
            "action_id": "review-approval",
            "label": "Review Approval",
            "enabled": approval_route_required(request),
            "tone": "warning",
        },
        {
            "action_id": "cancel-selection",
            "label": "Cancel",
            "enabled": request.get("status") not in {"confirmed", "cancelled"},
            "tone": "neutral",
        },
        {
            "action_id": "retry-selection",
            "label": "Retry",
            "enabled": request.get("status") in {"failed", "timed-out", "cancelled"} or (
                selectable_handle_count == 0 and request.get("attempt_count", 0) < request.get("max_attempts", 1)
            ),
            "tone": "warning",
        },
    ]

    return {
        "component_id": "portal-chooser",
        "panel_id": "portal-chooser-panel",
        "panel_kind": "shell-panel-skeleton",
        "header": {
            "title": request.get("title", "Portal Chooser"),
            "subtitle": request.get("subtitle", f"{len(handles)} handles bound to session"),
            "status": request.get("status", "pending"),
            "tone": tone_for_status(request.get("status")),
        },
        "badges": [
            {"label": "Total", "value": len(handles), "tone": "neutral"},
            {"label": "Matches", "value": matching_handle_count, "tone": "neutral"},
            {"label": "Selectable", "value": selectable_handle_count, "tone": "neutral"},
            {"label": "Unavailable", "value": unavailable_handle_count, "tone": "warning" if unavailable_handle_count else "neutral"},
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "request",
                "title": "Request",
                "items": request_section_items(request, selected_handle, confirmed_handle),
                "empty_state": "No chooser request metadata",
            },
            {
                "section_id": "handles",
                "title": "Available Handles",
                "items": handle_items,
                "empty_state": "No portal handles",
            },
            {
                "section_id": "kinds",
                "title": "Handle Mix",
                "items": [
                    {"label": display_kind(kind), "value": count, "tone": "neutral"}
                    for kind, count in sorted(summary.items())
                ],
                "empty_state": "No handle kinds",
            },
            {
                "section_id": "selection-details",
                "title": "Selection Details",
                "items": selection_detail_items(detail_handle),
                "empty_state": "Select or confirm a handle to inspect its details",
            },
            {
                "section_id": "history",
                "title": "Recent Events",
                "items": history_section_items(request),
                "empty_state": "No chooser events recorded yet",
            },
        ],
        "meta": {
            "session_id": session_id,
            "chooser_id": request.get("chooser_id"),
            "chooser_status": request.get("status"),
            "handle_count": len(handles),
            "handle_summary": summary,
            "requested_kinds": requested,
            "focus_handle_id": focus_handle_id,
            "selected_handle_id": request.get("selected_handle_id"),
            "confirmed_handle_id": request.get("confirmed_handle_id"),
            "selected_handle_kind": selected_handle.get("kind") if selected_handle else None,
            "matching_handle_count": matching_handle_count,
            "selectable_handle_count": selectable_handle_count,
            "unavailable_handle_count": unavailable_handle_count,
            "detail_handle_id": detail_handle.get("handle_id") if detail_handle else None,
            "approval_ref": request.get("approval_ref"),
            "approval_route_required": approval_route_required(request),
            "capture_transport": request.get("capture_transport"),
            "capture_status": request.get("capture_status"),
            "capture_id": request.get("capture_id"),
            "capture_provider_id": request.get("capture_provider_id"),
            "audit_tag_count": len(request.get("audit_tags", [])) if isinstance(request.get("audit_tags"), list) else 0,
            "history_count": len(request.get("history", [])) if isinstance(request.get("history"), list) else 0,
        },
    }


def render_text(panel: dict[str, Any]) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    lines.append("actions: " + ", ".join(action["label"] for action in panel["actions"] if action.get("enabled", False)))
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if not items:
            lines.append(f"- {section['empty_state']}")
            continue
        for item in items:
            if section["section_id"] == "handles":
                lines.append(
                    f"- {item['label']} ({item['kind']}) [{item['status']}] -> {item['value']}"
                )
                continue
            value = item.get("value")
            if value not in (None, ""):
                lines.append(f"- {item['label']}: {value}")
            elif item.get("status"):
                lines.append(f"- {item['label']}: {item['status']}")
            else:
                lines.append(f"- {item['label']}")
    return "\n".join(lines)


def update_fixture_request(
    fixture: Path,
    request: dict[str, Any],
    *,
    action: str,
    selected_handle: dict[str, Any] | None = None,
    error_message: str | None = None,
    unavailable_reason: str | None = None,
    retry_after: str | None = None,
    target_component: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    payload = load_fixture_payload(fixture)
    payload_request = payload.setdefault("request", {})
    payload_request.update(request)
    payload_request["last_action"] = action
    payload_request["updated_at"] = utc_now()

    if selected_handle is not None:
        payload_request["selected_handle_id"] = selected_handle.get("handle_id")
        payload_request["selected_target"] = selected_handle.get("target")
    if error_message is not None:
        payload_request["error_message"] = error_message
    if unavailable_reason is not None:
        payload_request["last_unavailable_reason"] = unavailable_reason
    if retry_after is not None:
        payload_request["retry_after"] = retry_after

    history = payload_request.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "recorded_at": payload_request["updated_at"],
            "action": action,
            "status": payload_request.get("status"),
            "selected_handle_id": payload_request.get("selected_handle_id"),
            "confirmed_handle_id": payload_request.get("confirmed_handle_id"),
            "target_component": target_component,
            "reason": reason,
            "error_message": error_message,
            "unavailable_reason": unavailable_reason,
            "retry_after": retry_after,
            "capture_transport": payload_request.get("capture_transport"),
            "capture_status": payload_request.get("capture_status"),
            "capture_id": payload_request.get("capture_id"),
        }
    )
    payload_request["history"] = history[-EVENT_HISTORY_LIMIT:]

    save_fixture_payload(fixture, payload)
    return payload_request


def action_result(
    *,
    session_id: str | None,
    action: str,
    status: str,
    handles: list[dict[str, Any]],
    selected_handle: dict[str, Any] | None = None,
    confirmed_handle: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    target_component: str | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "status": status,
        "session_id": session_id,
        "handle_count": len(handles),
        "selected_handle_id": selected_handle.get("handle_id") if selected_handle else None,
        "confirmed_handle_id": confirmed_handle.get("handle_id") if confirmed_handle else None,
        "selected_target": selected_handle.get("target") if selected_handle else None,
        "selected_kind": selected_handle.get("kind") if selected_handle else None,
        "requested_kinds": (request or {}).get("requested_kinds", []),
        "target_component": target_component,
        "error_message": (request or {}).get("error_message"),
        "retry_after": (request or {}).get("retry_after"),
        "last_unavailable_reason": (request or {}).get("last_unavailable_reason"),
        "capture_transport": (request or {}).get("capture_transport"),
        "capture_status": (request or {}).get("capture_status"),
        "capture_id": (request or {}).get("capture_id"),
        "capture_provider_id": (request or {}).get("capture_provider_id"),
        "preview_object_kind": (request or {}).get("preview_object_kind"),
        "capture_request": (request or {}).get("capture_request"),
        "capture": (request or {}).get("capture"),
        "preview_object": (request or {}).get("preview_object"),
        "history_count": len((request or {}).get("history", [])) if isinstance((request or {}).get("history"), list) else 0,
    }


def pick_requested_handle(handles: list[dict[str, Any]], request: dict[str, Any]) -> dict[str, Any] | None:
    requested = request.get("requested_kinds", [])
    matching = [
        handle
        for handle in handles
        if handle_matches_requested_kind(handle, requested) and handle_availability(handle)[1]
    ]
    if not matching:
        return None
    return choose_focus_handle(matching, request)


def handle_failure_payload(candidate: dict[str, Any] | None) -> tuple[str, str | None]:
    if candidate is None:
        return "No selectable portal handle is available", None
    details = handle_availability_details(candidate)
    message = str(details.get("reason") or "No selectable portal handle is available")
    retry_after = details.get("retry_after")
    return message, retry_after


def perform_action(
    socket_path: Path,
    session_id: str | None,
    fixture: Path | None,
    action: str,
    handle_id: str | None,
    reason: str | None,
    *,
    task_id: str | None = None,
    user_id: str = "local-user",
    policy_socket: Path = DEFAULT_POLICYD_SOCKET,
    deviced_socket: Path = DEFAULT_DEVICED_SOCKET,
    screen_provider_socket: Path = DEFAULT_SCREEN_CAPTURE_PROVIDER_SOCKET,
) -> dict[str, Any]:
    handles, request = list_handles_with_request(socket_path, session_id, fixture)
    focus_handle = choose_focus_handle(handles, request)
    selected_handle = find_handle(handles, request.get("selected_handle_id"))
    confirmed_handle = find_handle(handles, request.get("confirmed_handle_id"))

    if action == "refresh":
        status = request.get("status", "pending")
        if status in {"pending", "ready"} and handles and not selected_handle:
            status = "ready"
        if fixture is not None:
            request = update_fixture_request(
                fixture,
                {
                    **request,
                    "status": status,
                    "error_message": None if status == "ready" else request.get("error_message"),
                },
                action=action,
                target_component="portal-chooser",
            )
        return action_result(
            session_id=session_id,
            action=action,
            status=status,
            handles=handles,
            selected_handle=selected_handle,
            request=request,
            target_component="portal-chooser",
        )

    if action == "prefer-requested":
        candidate = pick_requested_handle(handles, request)
        if candidate is None:
            if fixture is not None:
                request = update_fixture_request(
                    fixture,
                    {**request, "status": "failed"},
                    action=action,
                    error_message="No handles match the requested kind",
                    target_component="portal-chooser",
                )
            return action_result(
                session_id=session_id,
                action=action,
                status="failed",
                handles=handles,
                request=request,
                target_component="portal-chooser",
            )
        if fixture is not None:
            request = update_fixture_request(
                fixture,
                {
                    **request,
                    "status": "selected",
                    "selected_handle_id": candidate.get("handle_id"),
                    "confirmed_handle_id": None,
                    "error_message": None,
                    "timed_out": False,
                },
                action=action,
                selected_handle=candidate,
                target_component="portal-chooser",
            )
        return action_result(
            session_id=session_id,
            action=action,
            status="selected",
            handles=handles,
            selected_handle=candidate,
            request=request,
            target_component="portal-chooser",
        )

    if action == "select-handle":
        candidate = find_handle(handles, handle_id) or focus_handle
        if candidate is None:
            raise SystemExit("--handle-id is required for select-handle")
        if not handle_availability(candidate)[1]:
            message, retry_after = handle_failure_payload(candidate)
            if fixture is not None:
                request = update_fixture_request(
                    fixture,
                    {
                        **request,
                        "status": "failed",
                        "confirmed_handle_id": None,
                    },
                    action=action,
                    error_message=message,
                    unavailable_reason=message,
                    retry_after=retry_after,
                    target_component="portal-chooser",
                )
            return action_result(
                session_id=session_id,
                action=action,
                status="failed",
                handles=handles,
                request=request,
                target_component="portal-chooser",
            )
        if fixture is not None:
            request = update_fixture_request(
                fixture,
                {
                    **request,
                    "status": "selected",
                    "selected_handle_id": candidate.get("handle_id"),
                    "confirmed_handle_id": None,
                    "error_message": None,
                    "last_unavailable_reason": None,
                    "timed_out": False,
                },
                action=action,
                selected_handle=candidate,
                target_component="portal-chooser",
            )
        return action_result(
            session_id=session_id,
            action=action,
            status="selected",
            handles=handles,
            selected_handle=candidate,
            request=request,
            target_component="portal-chooser",
        )

    if action == "confirm-selection":
        candidate = find_handle(handles, handle_id) or selected_handle or focus_handle
        if candidate is None or not handle_availability(candidate)[1]:
            message, retry_after = handle_failure_payload(candidate)
            if fixture is not None:
                request = update_fixture_request(
                    fixture,
                    {
                        **request,
                        "status": "failed",
                        "confirmed_handle_id": None,
                    },
                    action=action,
                    error_message=message,
                    unavailable_reason=message,
                    retry_after=retry_after,
                    target_component="portal-chooser",
                    reason=reason,
                )
            return action_result(
                session_id=session_id,
                action=action,
                status="failed",
                handles=handles,
                selected_handle=selected_handle,
                request=request,
                target_component="portal-chooser",
            )
        capture_chain = None
        if (
            candidate is not None
            and candidate.get("kind") == "screen_share_handle"
            and not approval_route_required(request)
        ):
            try:
                capture_chain = invoke_screen_capture_chain(
                    policy_socket=policy_socket,
                    deviced_socket=deviced_socket,
                    screen_provider_socket=screen_provider_socket,
                    user_id=user_id,
                    session_id=session_id,
                    task_id=task_id,
                    request=request,
                    handle=candidate,
                )
            except Exception as error:  # noqa: BLE001
                message = f"screen capture dispatch failed: {error}"
                if fixture is not None:
                    request = update_fixture_request(
                        fixture,
                        {
                            **request,
                            "status": "failed",
                            "confirmed_handle_id": None,
                            "capture_transport": None,
                            "capture_status": None,
                            "capture_id": None,
                            "capture_provider_id": None,
                            "capture_request": None,
                            "capture": None,
                            "preview_object": None,
                            "preview_object_kind": None,
                        },
                        action=action,
                        selected_handle=candidate,
                        error_message=message,
                        unavailable_reason=None,
                        retry_after=None,
                        target_component="device-backend-status",
                        reason=reason,
                    )
                return action_result(
                    session_id=session_id,
                    action=action,
                    status="failed",
                    handles=handles,
                    selected_handle=candidate,
                    request=request,
                    target_component="device-backend-status",
                )
        status = "awaiting-approval" if approval_route_required(request) else "confirmed"
        target_component = "approval-panel" if approval_route_required(request) else "task-surface"
        updated_request = {
            **request,
            "status": status,
            "selected_handle_id": candidate.get("handle_id"),
            "confirmed_handle_id": candidate.get("handle_id"),
            "confirmed_at": utc_now(),
            "error_message": None,
            "last_unavailable_reason": None,
            "reason": reason,
        }
        if candidate.get("kind") != "screen_share_handle" or approval_route_required(request):
            updated_request.update(
                {
                    "capture_transport": None,
                    "capture_status": None,
                    "capture_id": None,
                    "capture_provider_id": None,
                    "capture_request": None,
                    "capture": None,
                    "preview_object": None,
                    "preview_object_kind": None,
                }
            )
        if capture_chain is not None:
            updated_request.update(
                {
                    "capture_transport": capture_chain.get("transport"),
                    "capture_status": (capture_chain.get("capture") or {}).get("status")
                    if capture_chain.get("invoked")
                    else "skipped",
                    "capture_id": (capture_chain.get("capture") or {}).get("capture_id"),
                    "capture_provider_id": capture_chain.get("provider_id"),
                    "capture_request": capture_chain.get("capture_request"),
                    "capture": capture_chain.get("capture"),
                    "preview_object": capture_chain.get("preview_object"),
                    "preview_object_kind": (capture_chain.get("preview_object") or {}).get("kind"),
                }
            )
        if fixture is not None:
            request = update_fixture_request(
                fixture,
                updated_request,
                action=action,
                selected_handle=candidate,
                target_component=target_component,
                reason=reason,
            )
        else:
            request = updated_request
        return action_result(
            session_id=session_id,
            action=action,
            status=status,
            handles=handles,
            selected_handle=candidate,
            confirmed_handle=candidate,
            request=request,
            target_component=target_component,
        )

    if action == "review-approval":
        target_component = "approval-panel" if approval_route_required(request) else "portal-chooser"
        if fixture is not None:
            request = update_fixture_request(
                fixture,
                request,
                action=action,
                target_component=target_component,
            )
        return action_result(
            session_id=session_id,
            action=action,
            status=request.get("status", "pending"),
            handles=handles,
            selected_handle=selected_handle,
            confirmed_handle=confirmed_handle,
            request=request,
            target_component=target_component,
        )

    if action == "cancel-selection":
        if fixture is not None:
            request = update_fixture_request(
                fixture,
                {
                    **request,
                    "status": "cancelled",
                    "cancelled_at": utc_now(),
                    "reason": reason,
                },
                action=action,
                target_component="portal-chooser",
                reason=reason,
            )
        return action_result(
            session_id=session_id,
            action=action,
            status="cancelled",
            handles=handles,
            selected_handle=selected_handle,
            request=request,
            target_component="portal-chooser",
        )

    if action == "retry-selection":
        next_attempt = int(request.get("attempt_count", 0)) + 1
        selectable_exists = any(handle_availability(handle)[1] for handle in handles)
        retry_after = str(request.get("retry_after") or "").strip() or None
        unavailable_reason = str(request.get("last_unavailable_reason") or request.get("error_message") or "").strip() or None
        status = "ready" if selectable_exists else "pending"
        if fixture is not None:
            request = update_fixture_request(
                fixture,
                {
                    **request,
                    "status": status,
                    "attempt_count": next_attempt,
                    "selected_handle_id": None,
                    "confirmed_handle_id": None,
                    "error_message": None if selectable_exists else unavailable_reason,
                    "timed_out": False,
                    "retried_at": utc_now(),
                },
                action=action,
                error_message=None if selectable_exists else unavailable_reason,
                unavailable_reason=unavailable_reason,
                retry_after=retry_after,
                target_component="portal-chooser",
            )
        return action_result(
            session_id=session_id,
            action=action,
            status=status,
            handles=handles,
            request=request,
            target_component="portal-chooser",
        )

    raise SystemExit(f"unknown action: {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS portal chooser panel skeleton")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--socket", type=Path, default=default_sessiond_socket())
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--handle-fixture", type=Path)
    parser.add_argument("--policy-socket", type=Path, default=DEFAULT_POLICYD_SOCKET)
    parser.add_argument("--deviced-socket", type=Path, default=DEFAULT_DEVICED_SOCKET)
    parser.add_argument(
        "--screen-provider-socket",
        type=Path,
        default=DEFAULT_SCREEN_CAPTURE_PROVIDER_SOCKET,
    )
    parser.add_argument("--action")
    parser.add_argument("--handle-id")
    parser.add_argument("--reason")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "watch":
        for index in range(max(1, args.iterations)):
            handles, request = list_handles_with_request(args.socket, args.session_id, args.handle_fixture)
            model = build_model(handles, args.session_id, request)
            print(json.dumps(model, indent=2, ensure_ascii=False) if args.json else render_text(model))
            if index + 1 < args.iterations:
                time.sleep(args.interval)
        return 0

    handles, request = list_handles_with_request(args.socket, args.session_id, args.handle_fixture)
    model = build_model(handles, args.session_id, request)
    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        result = perform_action(
            args.socket,
            args.session_id,
            args.handle_fixture,
            args.action,
            args.handle_id,
            args.reason,
            task_id=args.task_id,
            user_id=args.user_id,
            policy_socket=args.policy_socket,
            deviced_socket=args.deviced_socket,
            screen_provider_socket=args.screen_provider_socket,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
