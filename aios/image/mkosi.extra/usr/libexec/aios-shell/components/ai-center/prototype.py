#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


READINESS_TONES = {
    "local-ready": "positive",
    "hybrid-ready": "positive",
    "cloud-ready": "positive",
    "hybrid-remote-only": "warning",
    "setup-pending": "warning",
    "not-ready": "critical",
    "disabled": "neutral",
}

READINESS_LABELS = {
    "local-ready": "Local Ready",
    "hybrid-ready": "Hybrid Ready",
    "cloud-ready": "Cloud Ready",
    "hybrid-remote-only": "Remote Only",
    "setup-pending": "Setup Pending",
    "not-ready": "Not Ready",
    "disabled": "Disabled",
}

MODE_LABELS = {
    "local": "Local",
    "cloud": "Cloud",
    "hybrid": "Hybrid",
    "later": "Later",
}

_MODEL_MANAGER_CLASS = None
_MODEL_MANAGER_MODULE: ModuleType | None = None
_REMOTE_GOVERNANCE_PROTOTYPE_MODULE: ModuleType | None = None


def default_ai_readiness_path() -> Path:
    value = os.environ.get("AIOS_SHELL_AI_READINESS_PATH")
    return Path(value) if value else Path("/var/lib/aios/runtime/ai-readiness.json")


def default_ai_onboarding_report_path() -> Path:
    value = os.environ.get("AIOS_SHELL_AI_ONBOARDING_REPORT_PATH")
    return Path(value) if value else Path("/var/lib/aios/onboarding/ai-onboarding-report.json")


def default_model_dir() -> Path:
    value = os.environ.get("AIOS_MODEL_DIR")
    return Path(value) if value else Path("/var/lib/aios/models")


def default_model_registry() -> Path:
    value = os.environ.get("AIOS_MODEL_REGISTRY")
    return Path(value) if value else default_model_dir() / "model-registry.yaml"


def default_browser_remote_registry() -> Path:
    return load_remote_governance_prototype_module().default_browser_remote_registry()


def default_office_remote_registry() -> Path:
    return load_remote_governance_prototype_module().default_office_remote_registry()


def default_mcp_remote_registry() -> Path:
    return load_remote_governance_prototype_module().default_mcp_remote_registry()


def default_provider_registry_state_dir() -> Path:
    return load_remote_governance_prototype_module().default_provider_registry_state_dir()


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_json_payload(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, None
    if not path.exists():
        return {}, f"missing:{path}"
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return {}, str(error)
    if isinstance(payload, dict):
        return payload, None
    return {}, f"invalid-json-object:{path}"


def readiness_tone(state: str | None) -> str:
    if not state:
        return "neutral"
    return READINESS_TONES.get(state, "neutral")


def readiness_label(state: str | None) -> str:
    return READINESS_LABELS.get(state or "", state or "Unknown")


def mode_label(mode: str | None) -> str:
    return MODE_LABELS.get(mode or "", mode or "Unknown")


def load_ai_readiness_summary(readiness_path: Path | None, report_path: Path | None) -> dict[str, Any]:
    readiness_payload, readiness_error = load_json_payload(readiness_path)
    report_payload, report_error = load_json_payload(report_path)
    has_source = bool(readiness_payload or report_payload)
    errors = [error for error in (readiness_error, report_error) if error]
    source_status = "ready" if has_source else "unavailable"
    if has_source and errors:
        source_status = "partial"

    state = readiness_payload.get("state") or report_payload.get("readiness_state")
    reason = readiness_payload.get("reason") or report_payload.get("readiness_reason")
    next_action = readiness_payload.get("next_action") or report_payload.get("next_action")
    local_model_count = readiness_payload.get("local_model_count")
    if local_model_count is None:
        local_model_count = report_payload.get("local_model_count")
    endpoint_configured = readiness_payload.get("endpoint_configured")
    if endpoint_configured is None:
        endpoint_configured = report_payload.get("endpoint_configured")
    ai_enabled = readiness_payload.get("ai_enabled")
    if ai_enabled is None:
        ai_enabled = report_payload.get("ai_enabled")

    return {
        "state": state,
        "state_label": readiness_label(state),
        "tone": readiness_tone(state),
        "reason": reason,
        "next_action": next_action,
        "ai_enabled": bool(ai_enabled) if ai_enabled is not None else None,
        "ai_mode": readiness_payload.get("ai_mode") or report_payload.get("ai_mode"),
        "privacy_profile": report_payload.get("privacy_profile"),
        "auto_pull_default_model": report_payload.get("auto_pull_default_model"),
        "local_model_count": parse_int(local_model_count, 0),
        "endpoint_configured": bool(endpoint_configured),
        "endpoint_base_url": report_payload.get("endpoint_base_url"),
        "endpoint_model": report_payload.get("endpoint_model"),
        "has_source": has_source,
        "source_status": source_status,
        "source_error": "; ".join(errors) if errors else None,
        "readiness_path": str(readiness_path) if readiness_path else None,
        "report_path": readiness_payload.get("report_path") or (str(report_path) if report_path else None),
    }


def load_model_manager_class():
    global _MODEL_MANAGER_CLASS
    if _MODEL_MANAGER_CLASS is not None:
        return _MODEL_MANAGER_CLASS

    _MODEL_MANAGER_CLASS = load_model_manager_module().ModelManager
    return _MODEL_MANAGER_CLASS


def load_model_manager_module() -> ModuleType:
    global _MODEL_MANAGER_MODULE
    if _MODEL_MANAGER_MODULE is not None:
        return _MODEL_MANAGER_MODULE

    module_path = Path(__file__).resolve().parents[3] / "runtime" / "model_manager.py"
    if not module_path.exists():
        raise FileNotFoundError(f"model_manager missing: {module_path}")
    spec = importlib.util.spec_from_file_location("aios_runtime_model_manager", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load model_manager from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _MODEL_MANAGER_MODULE = module
    return _MODEL_MANAGER_MODULE


def load_remote_governance_prototype_module() -> ModuleType:
    global _REMOTE_GOVERNANCE_PROTOTYPE_MODULE
    if _REMOTE_GOVERNANCE_PROTOTYPE_MODULE is not None:
        return _REMOTE_GOVERNANCE_PROTOTYPE_MODULE

    module_path = Path(__file__).resolve().parents[1] / "remote-governance" / "prototype.py"
    spec = importlib.util.spec_from_file_location("aios_shell_remote_governance_prototype", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load remote_governance from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _REMOTE_GOVERNANCE_PROTOTYPE_MODULE = module
    return _REMOTE_GOVERNANCE_PROTOTYPE_MODULE


def load_model_inventory(model_dir: Path | None, registry_path: Path | None) -> dict[str, Any]:
    fallback_registry = registry_path.with_suffix(".json") if registry_path is not None else None
    has_source = bool(
        (model_dir is not None and model_dir.exists())
        or (registry_path is not None and registry_path.exists())
        or (fallback_registry is not None and fallback_registry.exists())
    )
    result: dict[str, Any] = {
        "model_dir": str(model_dir) if model_dir else None,
        "registry_path": str(registry_path) if registry_path else None,
        "has_source": has_source,
        "source_status": "ready" if has_source else "unavailable",
        "source_error": None,
        "model_count": 0,
        "models": [],
        "defaults": {},
        "loaded_registry_count": 0,
        "scanned_model_count": 0,
    }

    try:
        manager_class = load_model_manager_class()
        manager = manager_class(model_dir=model_dir, registry_path=registry_path)
        loaded_registry_count = manager.load_registry(registry_path)
        scanned_models = manager.scan_directory(model_dir)
        inventory = manager.export_inventory()
        models = sorted(
            [item for item in inventory.get("models", []) if isinstance(item, dict)],
            key=lambda item: str(item.get("model_id") or ""),
        )
        result.update(
            {
                "has_source": has_source or loaded_registry_count > 0 or bool(scanned_models),
                "source_status": (
                    "ready"
                    if has_source or loaded_registry_count > 0 or bool(scanned_models)
                    else "unavailable"
                ),
                "model_count": parse_int(inventory.get("model_count"), len(models)),
                "models": models,
                "defaults": dict(inventory.get("defaults") or {}),
                "loaded_registry_count": loaded_registry_count,
                "scanned_model_count": len(scanned_models),
            }
        )
    except Exception as error:
        result["source_status"] = "error"
        result["source_error"] = str(error)

    return result


def default_model_for_capability(inventory: dict[str, Any], capability: str) -> str | None:
    defaults = inventory.get("defaults") or {}
    if isinstance(defaults, dict):
        value = defaults.get(capability)
        if isinstance(value, str) and value:
            return value
    for entry in inventory.get("models", []):
        if capability in list(entry.get("capabilities") or []):
            model_id = entry.get("model_id")
            if isinstance(model_id, str) and model_id:
                return model_id
    return None


def capability_summary(models: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for entry in models:
        for capability in list(entry.get("capabilities") or []):
            summary[capability] = summary.get(capability, 0) + 1
    return dict(sorted(summary.items()))


def load_recommended_catalog_summary(inventory: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_status": "missing",
        "source_error": None,
        "catalog_id": None,
        "catalog_label": None,
        "model_count": 0,
        "strategy_counts": {},
        "capability_counts": {},
        "installed_count": 0,
        "installed_model_ids": [],
        "default_recommendations": {},
        "models": [],
    }
    try:
        module = load_model_manager_module()
        catalog = module.load_recommended_model_catalog()
        summary = module.summarize_recommended_model_catalog(catalog, inventory=inventory)
        result.update(summary)
    except Exception as error:
        result["source_status"] = "error"
        result["source_error"] = str(error)
    return result


def load_remote_governance_summary(
    browser_remote_registry: Path | None,
    office_remote_registry: Path | None,
    mcp_remote_registry: Path | None,
    provider_registry_state_dir: Path | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_status": "unavailable",
        "source_error": None,
        "matched_entry_count": 0,
        "issue_count": 0,
        "fleet_count": 0,
        "source_counts": {},
        "control_plane_registered_count": 0,
        "top_issues": [],
    }
    try:
        module = load_remote_governance_prototype_module()
        payload = module.load_remote_governance(
            browser_remote_registry or default_browser_remote_registry(),
            office_remote_registry or default_office_remote_registry(),
            mcp_remote_registry or default_mcp_remote_registry(),
            provider_registry_state_dir or default_provider_registry_state_dir(),
            limit=6,
        )
        result.update(
            {
                "source_status": "ready",
                "matched_entry_count": parse_int(payload.get("matched_entry_count"), 0),
                "issue_count": parse_int(payload.get("issue_count"), 0),
                "fleet_count": len(payload.get("fleet_summary") or []),
                "source_counts": dict(payload.get("filtered_source_counts") or payload.get("source_counts") or {}),
                "control_plane_registered_count": parse_int(
                    payload.get("control_plane_registered_count"),
                    0,
                ),
                "top_issues": [
                    item.get("title") or "issue"
                    for item in list(payload.get("issues") or [])[:3]
                    if isinstance(item, dict)
                ],
            }
        )
    except Exception as error:
        result["source_status"] = "error"
        result["source_error"] = str(error)
    return result


def build_ai_center_state(
    readiness_path: Path | None,
    report_path: Path | None,
    model_dir: Path | None,
    model_registry: Path | None,
    browser_remote_registry: Path | None = None,
    office_remote_registry: Path | None = None,
    mcp_remote_registry: Path | None = None,
    provider_registry_state_dir: Path | None = None,
) -> dict[str, Any]:
    readiness = load_ai_readiness_summary(readiness_path, report_path)
    inventory = load_model_inventory(model_dir, model_registry)
    recommended_catalog = load_recommended_catalog_summary(inventory)
    remote_governance = load_remote_governance_summary(
        browser_remote_registry,
        office_remote_registry,
        mcp_remote_registry,
        provider_registry_state_dir,
    )
    inventory_count = parse_int(inventory.get("model_count"), 0)
    reported_count = parse_int(readiness.get("local_model_count"), 0)
    effective_local_model_count = (
        inventory_count if inventory.get("source_status") == "ready" else reported_count
    )
    models = list(inventory.get("models") or [])
    diagnostics: list[str] = []
    if readiness.get("source_error"):
        diagnostics.append(f"readiness_source={readiness['source_error']}")
    if inventory.get("source_error"):
        diagnostics.append(f"inventory_source={inventory['source_error']}")
    if (
        readiness.get("has_source")
        and inventory.get("source_status") == "ready"
        and inventory_count != reported_count
    ):
        diagnostics.append(
            f"local_model_count_drift=reported:{reported_count},inventory:{inventory_count}"
        )
    if readiness.get("reason"):
        diagnostics.append(f"readiness_reason={readiness['reason']}")
    if recommended_catalog.get("source_error"):
        diagnostics.append(f"recommended_catalog={recommended_catalog['source_error']}")
    if remote_governance.get("source_error"):
        diagnostics.append(f"remote_governance={remote_governance['source_error']}")

    return {
        "readiness": readiness,
        "inventory": inventory,
        "recommended_catalog": recommended_catalog,
        "remote_governance": remote_governance,
        "effective_local_model_count": effective_local_model_count,
        "reported_local_model_count": reported_count,
        "inventory_local_model_count": inventory_count,
        "default_text_generation_model": default_model_for_capability(
            inventory, "text-generation"
        ),
        "default_embedding_model": default_model_for_capability(inventory, "embedding"),
        "default_reranking_model": default_model_for_capability(inventory, "reranking"),
        "capability_summary": capability_summary(models),
        "diagnostics": diagnostics,
        "mode_label": mode_label(readiness.get("ai_mode")),
    }


def render_state(state: dict[str, Any]) -> str:
    readiness = state.get("readiness") or {}
    inventory = state.get("inventory") or {}
    lines = [
        f"readiness: {readiness.get('state_label', 'Unknown')}",
        f"mode: {state.get('mode_label', 'Unknown')}",
        f"ai_enabled: {readiness.get('ai_enabled')}",
        f"local_models: {state.get('effective_local_model_count', 0)}",
        f"reported_local_models: {state.get('reported_local_model_count', 0)}",
        f"inventory_status: {inventory.get('source_status', 'unknown')}",
        f"default_text_model: {state.get('default_text_generation_model') or '-'}",
        (
            "remote_endpoint: "
            f"{readiness.get('endpoint_model') or ('configured' if readiness.get('endpoint_configured') else 'missing')}"
        ),
    ]
    if readiness.get("privacy_profile"):
        lines.append(f"privacy_profile: {readiness['privacy_profile']}")
    if readiness.get("reason"):
        lines.append(f"reason: {readiness['reason']}")
    for entry in inventory.get("models", [])[:6]:
        lines.append(
            "model: "
            f"{entry.get('model_id') or '-'} "
            f"format={entry.get('format') or 'unknown'} "
            f"caps={','.join(entry.get('capabilities') or []) or '-'}"
        )
    for item in state.get("diagnostics", []):
        lines.append(f"diag: {item}")
    return "\n".join(lines)
