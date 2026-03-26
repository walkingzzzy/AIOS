#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from prototype import (
    build_ai_center_state,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_browser_remote_registry,
    default_model_dir,
    default_model_registry,
    default_mcp_remote_registry,
    default_office_remote_registry,
    default_provider_registry_state_dir,
)


def inventory_tone(source_status: str | None) -> str:
    if source_status == "ready":
        return "positive"
    if source_status in {"partial", "error"}:
        return "warning"
    return "neutral"


def capability_value(capability_summary: dict[str, int]) -> str:
    if not capability_summary:
        return "-"
    return ", ".join(f"{key}:{value}" for key, value in capability_summary.items())


def strategy_value(strategy_counts: dict[str, int]) -> str:
    if not strategy_counts:
        return "-"
    return ", ".join(f"{key}:{value}" for key, value in sorted(strategy_counts.items()))


def model_value(entry: dict[str, Any]) -> str:
    capabilities = ",".join(entry.get("capabilities") or []) or "-"
    quantization = entry.get("quantization") or "-"
    return f"{entry.get('format') or 'unknown'} | caps={capabilities} | quant={quantization}"


def remote_governance_tone(summary: dict[str, Any]) -> str:
    if summary.get("source_status") == "error":
        return "warning"
    if int(summary.get("issue_count") or 0) > 0:
        return "warning"
    if int(summary.get("matched_entry_count") or 0) > 0:
        return "positive"
    return "neutral"


def build_model(state: dict[str, Any]) -> dict[str, Any]:
    readiness = state.get("readiness") or {}
    inventory = state.get("inventory") or {}
    recommended_catalog = state.get("recommended_catalog") or {}
    remote_governance = state.get("remote_governance") or {}
    diagnostics = list(state.get("diagnostics") or [])
    effective_local_model_count = int(state.get("effective_local_model_count") or 0)
    inventory_model_count = int(state.get("inventory_local_model_count") or 0)
    reported_local_model_count = int(state.get("reported_local_model_count") or 0)
    endpoint_configured = bool(readiness.get("endpoint_configured"))
    next_action = readiness.get("next_action")
    next_action_pending = next_action not in (None, "", "none")
    onboarding_action_required = next_action_pending or not effective_local_model_count

    actions = [
        {
            "action_id": "refresh",
            "label": "Refresh AI Center",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "open-model-library",
            "label": "Open Model Library",
            "enabled": True,
            "tone": "positive" if effective_local_model_count else "warning",
        },
        {
            "action_id": "open-provider-settings",
            "label": "Open Provider Settings",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "open-privacy-memory",
            "label": "Open Privacy & Memory",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "open-remote-governance",
            "label": "Open Remote Governance",
            "enabled": True,
            "tone": remote_governance_tone(remote_governance),
        },
        {
            "action_id": "rerun-ai-onboarding",
            "label": "Rerun AI Onboarding",
            "enabled": onboarding_action_required,
            "tone": "warning",
        },
    ]

    overview_items = [
        {
            "label": "AI Enabled",
            "value": readiness.get("ai_enabled"),
            "tone": "positive" if readiness.get("ai_enabled") else "neutral",
        },
        {
            "label": "Readiness",
            "value": readiness.get("state_label") or "Unknown",
            "tone": readiness.get("tone", "neutral"),
        },
        {
            "label": "Reason",
            "value": readiness.get("reason") or "-",
            "tone": readiness.get("tone", "neutral"),
        },
        {
            "label": "Mode",
            "value": state.get("mode_label") or "Unknown",
            "tone": "neutral",
        },
        {
            "label": "Privacy Profile",
            "value": readiness.get("privacy_profile") or "-",
            "tone": "neutral",
        },
        {
            "label": "Auto Pull Default Model",
            "value": readiness.get("auto_pull_default_model"),
            "tone": "positive" if readiness.get("auto_pull_default_model") else "neutral",
        },
        {
            "label": "Next Action",
            "value": next_action or "none",
            "tone": "warning" if next_action_pending else "neutral",
        },
    ]

    inventory_items = [
        {
            "label": "Effective Local Models",
            "value": effective_local_model_count,
            "tone": "positive" if effective_local_model_count else "warning",
        },
        {
            "label": "Reported Local Models",
            "value": reported_local_model_count,
            "tone": "neutral",
        },
        {
            "label": "Inventory Local Models",
            "value": inventory_model_count,
            "tone": "positive" if inventory_model_count else "neutral",
        },
        {
            "label": "Inventory Status",
            "value": inventory.get("source_status") or "unknown",
            "tone": inventory_tone(inventory.get("source_status")),
        },
        {
            "label": "Default Text Model",
            "value": state.get("default_text_generation_model") or "-",
            "tone": "positive" if state.get("default_text_generation_model") else "warning",
        },
        {
            "label": "Default Embedding Model",
            "value": state.get("default_embedding_model") or "-",
            "tone": "neutral",
        },
        {
            "label": "Default Reranking Model",
            "value": state.get("default_reranking_model") or "-",
            "tone": "neutral",
        },
        {
            "label": "Capabilities",
            "value": capability_value(state.get("capability_summary") or {}),
            "tone": "neutral",
        },
        {
            "label": "Model Dir",
            "value": inventory.get("model_dir") or "-",
            "tone": "neutral",
        },
        {
            "label": "Model Registry",
            "value": inventory.get("registry_path") or "-",
            "tone": "neutral",
        },
    ]

    endpoint_items = [
        {
            "label": "Configured",
            "value": endpoint_configured,
            "tone": "positive" if endpoint_configured else "warning",
        },
        {
            "label": "Endpoint Base URL",
            "value": readiness.get("endpoint_base_url") or "-",
            "tone": "neutral",
        },
        {
            "label": "Endpoint Model",
            "value": readiness.get("endpoint_model") or "-",
            "tone": "positive" if readiness.get("endpoint_model") else "neutral",
        },
    ]

    recommended_items = [
        {
            "label": "Catalog Status",
            "value": recommended_catalog.get("source_status") or "missing",
            "tone": inventory_tone(recommended_catalog.get("source_status")),
        },
        {
            "label": "Recommended Models",
            "value": recommended_catalog.get("model_count", 0),
            "tone": "positive" if recommended_catalog.get("model_count", 0) else "neutral",
        },
        {
            "label": "Installed Recommended",
            "value": recommended_catalog.get("installed_count", 0),
            "tone": "positive" if recommended_catalog.get("installed_count", 0) else "warning",
        },
        {
            "label": "Strategies",
            "value": strategy_value(recommended_catalog.get("strategy_counts") or {}),
            "tone": "neutral",
        },
    ]

    recommended_models = [
        {
            "label": entry.get("display_name") or entry.get("model_id") or "recommended-model",
            "value": (
                f"{','.join(entry.get('capabilities') or []) or '-'} | "
                f"{entry.get('distribution_strategy') or 'manual-import'} | "
                f"{'installed' if entry.get('installed') else 'not-installed'}"
            ),
            "detail": entry.get("description") or "-",
            "tone": "positive" if entry.get("installed") else "neutral",
        }
        for entry in list(recommended_catalog.get("models") or [])[:6]
        if isinstance(entry, dict)
    ]

    ecosystem_items = [
        {
            "label": "Remote Governance",
            "value": remote_governance.get("source_status") or "unavailable",
            "tone": remote_governance_tone(remote_governance),
        },
        {
            "label": "Matched Remotes",
            "value": remote_governance.get("matched_entry_count", 0),
            "tone": "positive" if remote_governance.get("matched_entry_count", 0) else "neutral",
        },
        {
            "label": "Governance Issues",
            "value": remote_governance.get("issue_count", 0),
            "tone": "warning" if remote_governance.get("issue_count", 0) else "neutral",
        },
        {
            "label": "Fleets",
            "value": remote_governance.get("fleet_count", 0),
            "tone": "neutral",
        },
        {
            "label": "Source Mix",
            "value": capability_value(remote_governance.get("source_counts") or {}),
            "tone": "neutral",
        },
    ]

    registered_models = [
        {
            "label": entry.get("model_id") or "model",
            "value": model_value(entry),
            "detail": entry.get("path") or "-",
            "tone": "positive"
            if entry.get("model_id") == state.get("default_text_generation_model")
            else "neutral",
            "capabilities": entry.get("capabilities") or [],
            "format": entry.get("format"),
            "path": entry.get("path"),
            "source_kind": entry.get("source_kind"),
        }
        for entry in list(inventory.get("models") or [])[:8]
        if isinstance(entry, dict)
    ]

    source_items = [
        {
            "label": "Readiness Source",
            "value": readiness.get("source_status") or "unknown",
            "tone": inventory_tone(readiness.get("source_status")),
        },
        {
            "label": "Readiness Path",
            "value": readiness.get("readiness_path") or "-",
            "tone": "neutral",
        },
        {
            "label": "Onboarding Report",
            "value": readiness.get("report_path") or "-",
            "tone": "neutral",
        },
        {
            "label": "Inventory Source",
            "value": inventory.get("source_status") or "unknown",
            "tone": inventory_tone(inventory.get("source_status")),
        },
        {
            "label": "Inventory Error",
            "value": inventory.get("source_error") or "-",
            "tone": "warning" if inventory.get("source_error") else "neutral",
        },
        {
            "label": "Recommended Catalog",
            "value": recommended_catalog.get("source_path") or "-",
            "tone": "neutral",
        },
        {
            "label": "Recommended Catalog Error",
            "value": recommended_catalog.get("source_error") or "-",
            "tone": "warning" if recommended_catalog.get("source_error") else "neutral",
        },
        {
            "label": "Remote Governance Error",
            "value": remote_governance.get("source_error") or "-",
            "tone": "warning" if remote_governance.get("source_error") else "neutral",
        },
    ]

    return {
        "component_id": "ai-center",
        "panel_id": "ai-center-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "AI Center",
            "subtitle": (
                f"{state.get('mode_label', 'Unknown')} | "
                f"{effective_local_model_count} local models | "
                f"{'remote configured' if endpoint_configured else 'remote missing'}"
            ),
            "status": readiness.get("state") or "unknown",
            "tone": readiness.get("tone", "neutral"),
        },
        "badges": [
            {
                "label": "Readiness",
                "value": readiness.get("state_label") or "Unknown",
                "tone": readiness.get("tone", "neutral"),
            },
            {
                "label": "Mode",
                "value": state.get("mode_label") or "Unknown",
                "tone": "neutral",
            },
            {
                "label": "Local Models",
                "value": effective_local_model_count,
                "tone": "positive" if effective_local_model_count else "warning",
            },
            {
                "label": "Remote",
                "value": readiness.get("endpoint_model")
                or ("configured" if endpoint_configured else "missing"),
                "tone": "positive" if endpoint_configured else "warning",
            },
            {
                "label": "Recommended",
                "value": recommended_catalog.get("installed_count", 0),
                "tone": "positive" if recommended_catalog.get("installed_count", 0) else "neutral",
            },
            {
                "label": "Remotes",
                "value": remote_governance.get("matched_entry_count", 0),
                "tone": remote_governance_tone(remote_governance),
            },
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "overview",
                "title": "Overview",
                "items": overview_items,
                "empty_state": "No AI overview available",
            },
            {
                "section_id": "model-inventory",
                "title": "Model Inventory",
                "items": inventory_items,
                "empty_state": "No model inventory available",
            },
            {
                "section_id": "registered-models",
                "title": "Registered Models",
                "items": registered_models,
                "empty_state": "No registered local models",
            },
            {
                "section_id": "recommended-summary",
                "title": "Recommended Catalog",
                "items": recommended_items,
                "empty_state": "No recommended catalog available",
            },
            {
                "section_id": "recommended-models",
                "title": "Recommended Models",
                "items": recommended_models,
                "empty_state": "No recommended models available",
            },
            {
                "section_id": "remote-endpoint",
                "title": "Remote Endpoint",
                "items": endpoint_items,
                "empty_state": "No remote endpoint configured",
            },
            {
                "section_id": "external-ecosystem",
                "title": "External Ecosystem",
                "items": ecosystem_items,
                "empty_state": "No external ecosystem summary",
            },
            {
                "section_id": "sources",
                "title": "Sources",
                "items": source_items,
                "empty_state": "No AI source metadata",
            },
            {
                "section_id": "diagnostics",
                "title": "Diagnostics",
                "items": [
                    {"label": f"diag-{index + 1}", "value": item, "tone": "warning"}
                    for index, item in enumerate(diagnostics)
                ],
                "empty_state": "No diagnostics",
            },
        ],
        "meta": {
            "ai_enabled": readiness.get("ai_enabled"),
            "ai_mode": readiness.get("ai_mode"),
            "mode_label": state.get("mode_label"),
            "readiness_state": readiness.get("state"),
            "readiness_label": readiness.get("state_label"),
            "readiness_reason": readiness.get("reason"),
            "next_action": next_action,
            "privacy_profile": readiness.get("privacy_profile"),
            "auto_pull_default_model": readiness.get("auto_pull_default_model"),
            "reported_local_model_count": reported_local_model_count,
            "inventory_local_model_count": inventory_model_count,
            "local_model_count": effective_local_model_count,
            "inventory_status": inventory.get("source_status"),
            "inventory_error": inventory.get("source_error"),
            "default_text_generation_model": state.get("default_text_generation_model"),
            "default_embedding_model": state.get("default_embedding_model"),
            "default_reranking_model": state.get("default_reranking_model"),
            "capability_summary": state.get("capability_summary") or {},
            "endpoint_configured": endpoint_configured,
            "endpoint_base_url": readiness.get("endpoint_base_url"),
            "endpoint_model": readiness.get("endpoint_model"),
            "readiness_source_status": readiness.get("source_status"),
            "readiness_source_error": readiness.get("source_error"),
            "readiness_path": readiness.get("readiness_path"),
            "onboarding_report_path": readiness.get("report_path"),
            "model_dir": inventory.get("model_dir"),
            "model_registry_path": inventory.get("registry_path"),
            "recommended_catalog_status": recommended_catalog.get("source_status"),
            "recommended_catalog_path": recommended_catalog.get("source_path"),
            "recommended_catalog_error": recommended_catalog.get("source_error"),
            "recommended_model_count": recommended_catalog.get("model_count", 0),
            "recommended_installed_count": recommended_catalog.get("installed_count", 0),
            "recommended_strategy_counts": recommended_catalog.get("strategy_counts") or {},
            "remote_governance_status": remote_governance.get("source_status"),
            "remote_governance_issue_count": remote_governance.get("issue_count", 0),
            "remote_governance_matched_entry_count": remote_governance.get("matched_entry_count", 0),
            "remote_governance_fleet_count": remote_governance.get("fleet_count", 0),
            "remote_governance_source_counts": remote_governance.get("source_counts") or {},
            "diagnostics_count": len(diagnostics),
            "diagnostics": diagnostics,
        },
    }


def render_text(panel: dict[str, Any]) -> str:
    lines = []
    header = panel.get("header", {})
    lines.append(f"{header.get('title', 'AI Center')} [{header.get('status', 'unknown')}]")
    lines.append(header.get("subtitle", "-"))
    badges = panel.get("badges", [])
    if badges:
        lines.append(
            "badges: "
            + ", ".join(f"{item.get('label')}: {item.get('value')}" for item in badges)
        )
    actions = [item.get("label") for item in panel.get("actions", []) if item.get("enabled", True)]
    if actions:
        lines.append("actions: " + ", ".join(actions))
    for section in panel.get("sections", []):
        lines.append(f"[{section.get('title', section.get('section_id', 'section'))}]")
        items = section.get("items", [])
        if not items:
            lines.append(f"- {section.get('empty_state', 'No items')}")
            continue
        for item in items:
            lines.append(f"- {item.get('label', '-')}: {item.get('value', '-')}")
    return "\n".join(lines)


def current_model(args: argparse.Namespace) -> dict[str, Any]:
    state = build_ai_center_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.model_dir,
        args.model_registry,
        args.browser_remote_registry,
        args.office_remote_registry,
        args.mcp_remote_registry,
        args.provider_registry_state_dir,
    )
    return build_model(state)


def action_route(action_id: str) -> tuple[str | None, str | None]:
    if action_id == "refresh":
        return "ai-center", None
    if action_id == "open-model-library":
        return "model-library", None
    if action_id == "open-provider-settings":
        return "provider-settings", None
    if action_id == "open-privacy-memory":
        return "privacy-memory", None
    if action_id == "open-remote-governance":
        return "remote-governance", None
    if action_id == "rerun-ai-onboarding":
        return "ai-center", "ai-onboarding"
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS AI center panel")
    parser.add_argument(
        "command",
        nargs="?",
        default="render",
        choices=["render", "model", "action", "watch"],
    )
    parser.add_argument("--ai-readiness", type=Path, default=default_ai_readiness_path())
    parser.add_argument(
        "--ai-onboarding-report",
        type=Path,
        default=default_ai_onboarding_report_path(),
    )
    parser.add_argument("--model-dir", type=Path, default=default_model_dir())
    parser.add_argument("--model-registry", type=Path, default=default_model_registry())
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--mcp-remote-registry", type=Path, default=default_mcp_remote_registry())
    parser.add_argument(
        "--provider-registry-state-dir",
        type=Path,
        default=default_provider_registry_state_dir(),
    )
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        model = current_model(args)
        selected = next(
            (item for item in model.get("actions", []) if item.get("action_id") == args.action),
            None,
        )
        if selected is None:
            raise SystemExit(f"unknown action: {args.action}")
        target_component, target_route = action_route(args.action)
        if not selected.get("enabled", False):
            target_component = None
            target_route = None
        result = {
            "action": args.action,
            "enabled": bool(selected.get("enabled", False)),
            "target_component": target_component,
            "target_route": target_route,
            "status": model.get("header", {}).get("status"),
            "readiness_state": model.get("meta", {}).get("readiness_state"),
            "ai_mode": model.get("meta", {}).get("ai_mode"),
            "local_model_count": model.get("meta", {}).get("local_model_count", 0),
            "inventory_local_model_count": model.get("meta", {}).get(
                "inventory_local_model_count", 0
            ),
            "default_text_generation_model": model.get("meta", {}).get(
                "default_text_generation_model"
            ),
            "endpoint_configured": model.get("meta", {}).get("endpoint_configured", False),
            "endpoint_model": model.get("meta", {}).get("endpoint_model"),
            "recommended_model_count": model.get("meta", {}).get("recommended_model_count", 0),
            "recommended_installed_count": model.get("meta", {}).get(
                "recommended_installed_count", 0
            ),
            "remote_governance_issue_count": model.get("meta", {}).get(
                "remote_governance_issue_count",
                0,
            ),
            "diagnostics_count": model.get("meta", {}).get("diagnostics_count", 0),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            model = current_model(args)
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    model = current_model(args)
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
