#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_text(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def env_bool(name: str) -> bool:
    value = env_text(name)
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def build_request_binding(modality: str) -> dict[str, object]:
    return {
        "modality": modality,
        "session_id": env_text("AIOS_DEVICED_SESSION_ID"),
        "task_id": env_text("AIOS_DEVICED_TASK_ID"),
        "window_ref": env_text("AIOS_DEVICED_WINDOW_REF"),
        "source_device": env_text("AIOS_DEVICED_SOURCE_DEVICE"),
        "continuous": env_bool("AIOS_DEVICED_CONTINUOUS"),
    }


def build_transport(
    kind: str,
    *,
    endpoint: str | None = None,
    stream_ref: str | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"kind": kind}
    if endpoint is not None:
        payload["endpoint"] = endpoint
    if stream_ref is not None:
        payload["stream_ref"] = stream_ref
    if details:
        payload["details"] = details
    return payload


def build_evidence(
    *,
    state_ref: str | None = None,
    probe_tool: str | None = None,
    probe_excerpt: str | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"collected_at": utc_now()}
    if state_ref is not None:
        payload["state_ref"] = state_ref
    if probe_tool is not None:
        payload["probe_tool"] = probe_tool
    if probe_excerpt is not None:
        payload["probe_excerpt"] = probe_excerpt
    if details:
        payload["details"] = details
    return payload


def apply_helper_contract(
    payload: dict[str, object],
    *,
    modality: str,
    release_grade_backend: str,
    release_grade_backend_id: str | None = None,
    release_grade_backend_origin: str | None = None,
    release_grade_backend_stack: str | None = None,
    contract_kind: str = "release-grade-runtime-helper",
    adapter_hint: str,
    collector: str,
    transport: dict[str, object],
    evidence: dict[str, object],
) -> dict[str, object]:
    request_binding = build_request_binding(modality)
    session_id = request_binding.get("session_id") or "anonymous-session"
    task_id = request_binding.get("task_id") or "ad-hoc-task"
    request_ref = f"{session_id}:{task_id}:{modality}"
    backend_id = release_grade_backend_id or release_grade_backend

    payload["release_grade_backend"] = release_grade_backend
    payload["release_grade_backend_id"] = backend_id
    payload["release_grade_contract_kind"] = contract_kind
    if release_grade_backend_origin is not None:
        payload["release_grade_backend_origin"] = release_grade_backend_origin
    if release_grade_backend_stack is not None:
        payload["release_grade_backend_stack"] = release_grade_backend_stack

    payload["request_binding"] = request_binding
    payload["session_contract"] = {
        "contract_version": "1.0.0",
        "contract_kind": contract_kind,
        "request_ref": request_ref,
        "lease_id": f"{adapter_hint}:{request_ref}",
        "negotiated_at": utc_now(),
        "collector": collector,
        "release_grade_backend": release_grade_backend,
        "release_grade_backend_id": backend_id,
        "adapter_hint": adapter_hint,
    }
    if release_grade_backend_origin is not None:
        payload["session_contract"]["release_grade_backend_origin"] = (
            release_grade_backend_origin
        )
    if release_grade_backend_stack is not None:
        payload["session_contract"]["release_grade_backend_stack"] = (
            release_grade_backend_stack
        )

    payload["transport"] = transport
    payload["evidence"] = evidence
    payload["media_pipeline"] = {
        "pipeline_class": "native-helper-evidence",
        "release_grade_backend": release_grade_backend,
        "release_grade_backend_id": backend_id,
        "adapter_hint": adapter_hint,
        "collector": collector,
        "continuous": request_binding["continuous"],
        "transport_kind": transport.get("kind"),
    }
    if release_grade_backend_origin is not None:
        payload["media_pipeline"]["release_grade_backend_origin"] = (
            release_grade_backend_origin
        )
    if release_grade_backend_stack is not None:
        payload["media_pipeline"]["release_grade_backend_stack"] = (
            release_grade_backend_stack
        )

    return payload
