#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_artifacts(artifacts: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in artifacts.items():
        if value in (None, ""):
            continue
        normalized[key] = str(value)
    return normalized


def merge_non_empty(base: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    for key, value in (overlay or {}).items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def prune_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }


def surface_for_component(snapshot: dict[str, Any] | None, component: str) -> dict[str, Any] | None:
    if not snapshot:
        return None
    return next(
        (item for item in snapshot.get("surfaces", []) if item.get("component") == component),
        None,
    )


def surface_model_meta(snapshot: dict[str, Any] | None, component: str) -> dict[str, Any]:
    surface = surface_for_component(snapshot, component)
    if not surface:
        return {}
    model = surface.get("model") or {}
    meta = model.get("meta")
    return meta if isinstance(meta, dict) else {}


def surface_header(snapshot: dict[str, Any] | None, component: str) -> dict[str, Any]:
    surface = surface_for_component(snapshot, component)
    if not surface:
        return {}
    model = surface.get("model") or {}
    header = model.get("header")
    return header if isinstance(header, dict) else {}


def snapshot_summary(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}
    summary = snapshot.get("summary") or {}
    session_plan = snapshot.get("session_plan") or {}
    return {
        "profile_id": snapshot.get("profile_id"),
        "surface_count": snapshot.get("surface_count"),
        "total_surface_count": snapshot.get("total_surface_count"),
        "active_modal_surface": summary.get("active_modal_surface"),
        "primary_attention_surface": summary.get("primary_attention_surface"),
        "top_stack_surface": summary.get("top_stack_surface"),
        "attention_surface_count": summary.get("attention_surface_count"),
        "blocked_surface_count": summary.get("blocked_surface_count"),
        "modal_surface_count": summary.get("modal_surface_count"),
        "attention_components": summary.get("attention_components", []),
        "blocked_components": summary.get("blocked_components", []),
        "stack_order": summary.get("stack_order", []),
        "workspace_surface": summary.get("workspace_surface"),
        "session_plan": {
            "entrypoint": session_plan.get("entrypoint"),
            "desktop_host": session_plan.get("desktop_host"),
            "session_backend": session_plan.get("session_backend"),
        },
    }


def layout_evidence(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    summary = snapshot_summary(snapshot)
    return prune_empty(
        {
            "active_modal_surface": summary.get("active_modal_surface"),
            "primary_attention_surface": summary.get("primary_attention_surface"),
            "top_stack_surface": summary.get("top_stack_surface"),
            "workspace_surface": summary.get("workspace_surface"),
            "modal_surface_count": summary.get("modal_surface_count"),
            "attention_surface_count": summary.get("attention_surface_count"),
            "blocked_surface_count": summary.get("blocked_surface_count"),
            "attention_components": summary.get("attention_components"),
            "blocked_components": summary.get("blocked_components"),
            "stack_order": summary.get("stack_order"),
        }
    )


def restore_evidence(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    meta = surface_model_meta(snapshot, "launcher")
    if not meta:
        return {}
    return prune_empty(
        {
            "available": meta.get("restore_available"),
            "session_id": meta.get("restore_session_id") or meta.get("resolved_session_id"),
            "restore_point_at": meta.get("restore_point_at") or meta.get("focus_session_last_resumed_at"),
            "task_count": meta.get("restore_task_count") or meta.get("task_count"),
            "recent_session_count": meta.get("recent_session_count"),
            "recovery_id": meta.get("restore_recovery_id"),
            "recovery_status": meta.get("restore_recovery_status"),
            "target_component": meta.get("restore_target_component"),
            "session_status": meta.get("focus_session_status"),
        }
    )


def chooser_evidence(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    meta = surface_model_meta(snapshot, "portal-chooser")
    if not meta:
        return {}
    return prune_empty(
        {
            "session_id": meta.get("session_id"),
            "chooser_id": meta.get("chooser_id"),
            "status": meta.get("chooser_status"),
            "requested_kinds": meta.get("requested_kinds"),
            "selected_handle_id": meta.get("selected_handle_id"),
            "confirmed_handle_id": meta.get("confirmed_handle_id"),
            "selected_handle_kind": meta.get("selected_handle_kind"),
            "approval_ref": meta.get("approval_ref"),
            "approval_route_required": meta.get("approval_route_required"),
            "capture_transport": meta.get("capture_transport"),
            "capture_status": meta.get("capture_status"),
            "capture_id": meta.get("capture_id"),
            "capture_provider_id": meta.get("capture_provider_id"),
            "history_count": meta.get("history_count"),
        }
    )


def backend_status_evidence(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    meta = surface_model_meta(snapshot, "device-backend-status")
    header = surface_header(snapshot, "device-backend-status")
    if not meta and not header:
        return {}
    return prune_empty(
        {
            "status": header.get("status"),
            "tone": header.get("tone"),
            "attention_count": meta.get("attention_count"),
            "status_count": meta.get("status_count"),
            "adapter_count": meta.get("adapter_count"),
            "readiness_summary": meta.get("readiness_summary"),
            "attention_only": meta.get("attention_only"),
            "ui_tree_available": meta.get("ui_tree_available"),
            "ui_tree_capture_mode": meta.get("ui_tree_capture_mode"),
            "ui_tree_current_support": meta.get("ui_tree_current_support"),
            "ui_tree_support_route_count": meta.get("ui_tree_support_route_count"),
            "ui_tree_support_ready_count": meta.get("ui_tree_support_ready_count"),
        }
    )


def recovery_evidence(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    meta = surface_model_meta(snapshot, "recovery-surface")
    header = surface_header(snapshot, "recovery-surface")
    if not meta and not header:
        return {}
    return prune_empty(
        {
            "status": header.get("status"),
            "tone": header.get("tone"),
            "panel_state": meta.get("panel_state"),
            "recovery_point_count": meta.get("recovery_point_count"),
            "diagnostic_bundle_count": meta.get("diagnostic_bundle_count"),
            "latest_recovery_id": meta.get("latest_recovery_id"),
            "data_source_status": meta.get("data_source_status"),
        }
    )


def derive_route_evidence(records: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for record in records or []:
        action = record.get("action")
        target_component = record.get("target_component")
        if action in (None, "") and target_component in (None, ""):
            continue
        routes.append(
            prune_empty(
                {
                    "phase": record.get("phase"),
                    "iteration": record.get("iteration"),
                    "action": action,
                    "target_component": target_component,
                    "status": record.get("status"),
                    "selected_handle_id": record.get("selected_handle_id"),
                    "confirmed_handle_id": record.get("confirmed_handle_id"),
                    "attention_only": record.get("attention_only"),
                    "resumed_session_id": record.get("resumed_session_id"),
                    "recovery_id": record.get("recovery_id"),
                    "recovery_status": record.get("recovery_status"),
                }
            )
        )
    return routes


def normalize_modal_timeline(records: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for record in records or []:
        normalized = prune_empty(
            {
                "phase": record.get("phase"),
                "iteration": record.get("iteration"),
                "active_modal_surface": record.get("active_modal_surface"),
                "primary_attention_surface": record.get("primary_attention_surface"),
                "top_stack_surface": record.get("top_stack_surface"),
            }
        )
        if normalized:
            timeline.append(normalized)
    return timeline


def build_evidence(
    *,
    snapshot: dict[str, Any] | None,
    records: list[dict[str, Any]] | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    provided = evidence or {}
    layout = merge_non_empty(layout_evidence(snapshot), provided.get("layout"))
    restore = merge_non_empty(restore_evidence(snapshot), provided.get("restore"))
    chooser = merge_non_empty(chooser_evidence(snapshot), provided.get("chooser"))
    recovery = merge_non_empty(recovery_evidence(snapshot), provided.get("recovery"))
    backend_status = merge_non_empty(
        backend_status_evidence(snapshot),
        provided.get("backend_status"),
    )
    routes = provided.get("routes")
    if not isinstance(routes, list):
        routes = derive_route_evidence(records)
    modal_timeline = provided.get("modal_timeline")
    if not isinstance(modal_timeline, list):
        modal_timeline = []

    payload = {
        "layout": prune_empty(layout),
        "restore": prune_empty(restore),
        "chooser": prune_empty(chooser),
        "recovery": prune_empty(recovery),
        "backend_status": prune_empty(backend_status),
        "routes": routes,
        "modal_timeline": normalize_modal_timeline(modal_timeline),
    }
    handled_keys = {"layout", "restore", "chooser", "recovery", "backend_status", "routes", "modal_timeline"}
    for key, value in provided.items():
        if key in handled_keys or value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            payload[key] = prune_empty(value)
        else:
            payload[key] = value
    return prune_empty(payload)


def write_shell_evidence_manifest(
    manifest_path: Path,
    *,
    suite: str,
    artifacts: dict[str, Any],
    snapshot: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    evidence: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "suite": suite,
        "generated_at": utc_now(),
        "artifacts": normalize_artifacts(artifacts),
        "snapshot": snapshot_summary(snapshot),
        "records": records or [],
        "evidence": build_evidence(snapshot=snapshot, records=records, evidence=evidence),
        "extra": extra or {},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload
