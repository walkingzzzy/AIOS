#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Iterable

from prototype import (
    apply_recommended_distribution_selection,
    build_model_library_state,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_import_source,
    default_model_dir,
    default_model_registry,
    default_recommended_download_staging_dir,
    default_recommended_preload_roots,
    default_recommended_source_map,
    delete_registered_model,
    import_local_model,
    set_default_model_selection,
)


STATUS_TONES = {
    "ready": "positive",
    "partial": "warning",
    "unavailable": "warning",
    "error": "critical",
}


def inventory_tone(source_status: str | None) -> str:
    if not source_status:
        return "neutral"
    return STATUS_TONES.get(source_status, "neutral")


def defaults_by_capability(state: dict[str, Any]) -> dict[str, str | None]:
    return {
        "text-generation": state.get("default_text_generation_model"),
        "embedding": state.get("default_embedding_model"),
        "reranking": state.get("default_reranking_model"),
    }


def model_value(entry: dict[str, Any], default_capabilities: list[str]) -> str:
    capabilities = ",".join(entry.get("capabilities") or []) or "-"
    quantization = entry.get("quantization") or "-"
    source_kind = entry.get("source_kind") or "-"
    default_text = ",".join(default_capabilities) if default_capabilities else "-"
    return (
        f"{entry.get('format') or 'unknown'} | caps={capabilities} | "
        f"default={default_text} | quant={quantization} | source={source_kind}"
    )


def header_status(state: dict[str, Any]) -> str:
    inventory = state.get("inventory") or {}
    if inventory.get("source_status") == "error":
        return "error"
    if state.get("effective_local_model_count", 0):
        return "ready"
    if state.get("import_candidate", {}).get("configured"):
        return "import-pending"
    return "empty"


def recommended_plan_tone(status: str | None) -> str:
    if status in {"installed"}:
        return "positive"
    if status in {"ready-import", "ready-download"}:
        return "positive"
    if status in {"manual-required", "missing-source"}:
        return "warning"
    if status == "unsupported":
        return "critical"
    return "neutral"


def recommended_resolution_detail(entry: dict[str, Any]) -> str:
    resolved = entry.get("resolved_source") or {}
    detail = str(resolved.get("detail") or "").strip()
    if detail:
        return detail
    return entry.get("description") or "-"


def build_model(state: dict[str, Any]) -> dict[str, Any]:
    readiness = state.get("readiness") or {}
    inventory = state.get("inventory") or {}
    recommended_catalog = state.get("recommended_catalog") or {}
    recommended_distribution = state.get("recommended_distribution") or {}
    import_candidate = state.get("import_candidate") or {}
    diagnostics = list(state.get("diagnostics") or [])
    defaults = defaults_by_capability(state)
    models = list(inventory.get("models") or [])
    model_ids = {str(item.get("model_id")) for item in models if item.get("model_id")}
    suggested_model_id = import_candidate.get("suggested_model_id")
    import_duplicate = bool(suggested_model_id and suggested_model_id in model_ids)
    import_enabled = bool(import_candidate.get("ready")) and not import_duplicate

    actions = [
        {
            "action_id": "refresh",
            "label": "Refresh Library",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "import-local-model",
            "label": "Import Pending Source",
            "enabled": import_enabled,
            "tone": "positive" if import_enabled else "warning",
            "source_path": import_candidate.get("source_path"),
            "model_id": suggested_model_id,
            "capabilities": ["text-generation"],
            "set_default": False,
        },
        {
            "action_id": "apply-recommended-strategies",
            "label": "Apply Recommended Strategies",
            "enabled": bool(recommended_distribution.get("actionable_count", 0)),
            "tone": (
                "positive" if recommended_distribution.get("actionable_count", 0) else "warning"
            ),
        },
    ]

    overview_items = [
        {
            "label": "AI Mode",
            "value": state.get("mode_label") or "Unknown",
            "tone": "neutral",
        },
        {
            "label": "Readiness",
            "value": readiness.get("state_label") or "Unknown",
            "tone": readiness.get("tone", "neutral"),
        },
        {
            "label": "Inventory Status",
            "value": inventory.get("source_status") or "unknown",
            "tone": inventory_tone(inventory.get("source_status")),
        },
        {
            "label": "Local Models",
            "value": state.get("effective_local_model_count", 0),
            "tone": "positive" if state.get("effective_local_model_count", 0) else "warning",
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

    import_items = [
        {
            "label": "Configured",
            "value": import_candidate.get("configured", False),
            "tone": "positive" if import_candidate.get("configured") else "neutral",
        },
        {
            "label": "Ready",
            "value": import_candidate.get("ready", False),
            "tone": "positive" if import_candidate.get("ready") else "warning",
        },
        {
            "label": "Source Path",
            "value": import_candidate.get("source_path") or "-",
            "tone": "neutral",
        },
        {
            "label": "Suggested Model ID",
            "value": suggested_model_id or "-",
            "tone": "neutral" if suggested_model_id else "warning",
        },
        {
            "label": "Detected Format",
            "value": import_candidate.get("format") or "unknown",
            "tone": "positive" if import_candidate.get("valid") else "warning",
        },
        {
            "label": "SHA256",
            "value": import_candidate.get("sha256") or "-",
            "tone": "neutral",
        },
        {
            "label": "Error",
            "value": import_candidate.get("error") or ("duplicate-model-id" if import_duplicate else "-"),
            "tone": "warning" if import_candidate.get("error") or import_duplicate else "neutral",
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
            "value": ", ".join(
                f"{key}:{value}"
                for key, value in sorted((recommended_catalog.get("strategy_counts") or {}).items())
            )
            or "-",
            "tone": "neutral",
        },
        {
            "label": "Actionable Plans",
            "value": recommended_distribution.get("actionable_count", 0),
            "tone": (
                "positive" if recommended_distribution.get("actionable_count", 0) else "neutral"
            ),
        },
        {
            "label": "Pending Plans",
            "value": recommended_distribution.get("pending_count", 0),
            "tone": "warning" if recommended_distribution.get("pending_count", 0) else "neutral",
        },
        {
            "label": "Manual Plans",
            "value": recommended_distribution.get("manual_count", 0),
            "tone": "warning" if recommended_distribution.get("manual_count", 0) else "neutral",
        },
        {
            "label": "Unsupported Plans",
            "value": recommended_distribution.get("unsupported_count", 0),
            "tone": "critical" if recommended_distribution.get("unsupported_count", 0) else "neutral",
        },
    ]

    recommended_distribution_items = [
        {
            "label": "Preload Roots",
            "value": ", ".join(recommended_distribution.get("preload_roots") or []) or "-",
            "tone": "neutral",
        },
        {
            "label": "Source Map",
            "value": recommended_distribution.get("source_map_path") or "-",
            "tone": inventory_tone(recommended_distribution.get("source_map_status")),
        },
        {
            "label": "Source Map Status",
            "value": recommended_distribution.get("source_map_status") or "missing",
            "tone": inventory_tone(recommended_distribution.get("source_map_status")),
        },
        {
            "label": "Download Staging Dir",
            "value": recommended_distribution.get("download_staging_dir") or "-",
            "tone": "neutral",
        },
        {
            "label": "Source Map Error",
            "value": recommended_distribution.get("source_map_error") or "-",
            "tone": "warning" if recommended_distribution.get("source_map_error") else "neutral",
        },
        {
            "label": "Catalog Error",
            "value": recommended_distribution.get("catalog_error") or "-",
            "tone": "warning" if recommended_distribution.get("catalog_error") else "neutral",
        },
    ]

    default_items = [
        {
            "label": capability,
            "value": model_id or "-",
            "tone": "positive" if model_id else "warning",
        }
        for capability, model_id in defaults.items()
    ]

    registered_items = []
    default_action_items = []
    delete_action_items = []
    recommended_model_items = []
    for entry in list(recommended_distribution.get("models") or [])[:8]:
        if not isinstance(entry, dict):
            continue
        actionable = bool(entry.get("actionable")) and not bool(entry.get("installed"))
        row = {
            "label": entry.get("display_name") or entry.get("model_id") or "recommended-model",
            "value": (
                f"{','.join(entry.get('capabilities') or []) or '-'} | "
                f"{entry.get('distribution_strategy') or 'manual-import'} | "
                f"{entry.get('status') or 'manual-required'}"
            ),
            "detail": recommended_resolution_detail(entry),
            "tone": recommended_plan_tone(entry.get("status")),
        }
        if actionable:
            row["action"] = {
                "action_id": "install-recommended-model",
                "label": "Install Recommended",
                "enabled": True,
                "tone": "positive",
                "model_id": entry.get("model_id"),
                "set_default": bool(entry.get("default_recommended")),
            }
        recommended_model_items.append(row)
    for entry in models:
        model_id = entry.get("model_id")
        if not model_id:
            continue
        default_capabilities = [
            capability for capability, default_model in defaults.items() if default_model == model_id
        ]
        registered_items.append(
            {
                "label": model_id,
                "value": model_value(entry, default_capabilities),
                "detail": entry.get("path") or "-",
                "tone": "positive" if default_capabilities else "neutral",
            }
        )

        for capability in list(entry.get("capabilities") or []):
            if defaults.get(capability) == model_id:
                continue
            default_action_items.append(
                {
                    "label": capability,
                    "value": model_id,
                    "tone": "positive",
                    "action": {
                        "action_id": "set-default-model",
                        "label": "Set Default",
                        "enabled": True,
                        "tone": "positive",
                        "model_id": model_id,
                        "capability": capability,
                    },
                }
            )

        delete_action_items.append(
            {
                "label": model_id,
                "value": entry.get("path") or "-",
                "tone": "warning" if default_capabilities else "neutral",
                "action": {
                    "action_id": "delete-model",
                    "label": "Delete",
                    "enabled": True,
                    "tone": "critical",
                    "model_id": model_id,
                },
            }
        )

    return {
        "component_id": "model-library",
        "panel_id": "model-library-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Model Library",
            "subtitle": (
                f"{state.get('mode_label', 'Unknown')} | "
                f"{state.get('effective_local_model_count', 0)} local models | "
                f"defaults text={state.get('default_text_generation_model') or '-'}"
            ),
            "status": header_status(state),
            "tone": inventory_tone(inventory.get("source_status")),
        },
        "badges": [
            {
                "label": "Models",
                "value": state.get("effective_local_model_count", 0),
                "tone": "positive" if state.get("effective_local_model_count", 0) else "warning",
            },
            {
                "label": "Inventory",
                "value": inventory.get("source_status") or "unknown",
                "tone": inventory_tone(inventory.get("source_status")),
            },
            {
                "label": "Import Source",
                "value": "ready"
                if import_candidate.get("ready")
                else ("configured" if import_candidate.get("configured") else "missing"),
                "tone": "positive" if import_candidate.get("ready") else "warning",
            },
            {
                "label": "Diagnostics",
                "value": len(diagnostics),
                "tone": "warning" if diagnostics else "neutral",
            },
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "overview",
                "title": "Overview",
                "items": overview_items,
                "empty_state": "No model library overview",
            },
            {
                "section_id": "import-source",
                "title": "Import Source",
                "items": import_items,
                "empty_state": "No import source configured",
            },
            {
                "section_id": "recommended-catalog",
                "title": "Recommended Catalog",
                "items": recommended_items,
                "empty_state": "No recommended catalog available",
            },
            {
                "section_id": "recommended-distribution",
                "title": "Recommended Distribution",
                "items": recommended_distribution_items,
                "empty_state": "No recommended distribution plan available",
            },
            {
                "section_id": "recommended-models",
                "title": "Recommended Models",
                "items": recommended_model_items,
                "empty_state": "No recommended models available",
            },
            {
                "section_id": "default-routes",
                "title": "Default Routes",
                "items": default_items,
                "empty_state": "No default model configured",
            },
            {
                "section_id": "registered-models",
                "title": "Registered Models",
                "items": registered_items,
                "empty_state": "No registered local models",
            },
            {
                "section_id": "default-actions",
                "title": "Default Switch Actions",
                "items": default_action_items,
                "empty_state": "No alternate default candidate available",
            },
            {
                "section_id": "delete-actions",
                "title": "Delete Actions",
                "items": delete_action_items,
                "empty_state": "No registered models to delete",
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
            "ai_mode": readiness.get("ai_mode"),
            "mode_label": state.get("mode_label"),
            "readiness_state": readiness.get("state"),
            "inventory_status": inventory.get("source_status"),
            "inventory_error": inventory.get("source_error"),
            "local_model_count": state.get("effective_local_model_count", 0),
            "inventory_local_model_count": state.get("inventory_local_model_count", 0),
            "reported_local_model_count": state.get("reported_local_model_count", 0),
            "default_text_generation_model": state.get("default_text_generation_model"),
            "default_embedding_model": state.get("default_embedding_model"),
            "default_reranking_model": state.get("default_reranking_model"),
            "recommended_catalog_status": recommended_catalog.get("source_status"),
            "recommended_model_count": recommended_catalog.get("model_count", 0),
            "recommended_installed_count": recommended_catalog.get("installed_count", 0),
            "recommended_distribution_actionable_count": recommended_distribution.get("actionable_count", 0),
            "recommended_distribution_pending_count": recommended_distribution.get("pending_count", 0),
            "recommended_distribution_manual_count": recommended_distribution.get("manual_count", 0),
            "recommended_distribution_unsupported_count": recommended_distribution.get("unsupported_count", 0),
            "recommended_distribution_source_map_status": recommended_distribution.get("source_map_status"),
            "recommended_distribution_source_map_path": recommended_distribution.get("source_map_path"),
            "recommended_distribution_download_staging_dir": recommended_distribution.get(
                "download_staging_dir"
            ),
            "recommended_distribution_preload_roots": recommended_distribution.get("preload_roots") or [],
            "import_source_configured": import_candidate.get("configured", False),
            "import_source_ready": import_candidate.get("ready", False),
            "import_source_path": import_candidate.get("source_path"),
            "import_source_error": import_candidate.get("error"),
            "suggested_model_id": suggested_model_id,
            "duplicate_import_model_id": import_duplicate,
            "model_ids": sorted(model_ids),
            "diagnostics_count": len(diagnostics),
            "diagnostics": diagnostics,
        },
    }


def render_text(panel: dict[str, Any]) -> str:
    lines = []
    header = panel.get("header", {})
    lines.append(f"{header.get('title', 'Model Library')} [{header.get('status', 'unknown')}]")
    lines.append(header.get("subtitle", "-"))
    badges = panel.get("badges", [])
    if badges:
        lines.append("badges: " + ", ".join(f"{item.get('label')}: {item.get('value')}" for item in badges))
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
            label = item.get("label", "-")
            value = item.get("value", "-")
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def iter_actions(model: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for action in model.get("actions", []):
        if isinstance(action, dict):
            yield action
    for section in model.get("sections", []):
        for item in section.get("items", []):
            row_action = item.get("action")
            if isinstance(row_action, dict):
                yield row_action


def select_action(model: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    capability = (args.capability or [None])[0]
    source_path = str(args.source_path or args.import_source) if (args.source_path or args.import_source) else None
    matches = [
        action
        for action in iter_actions(model)
        if action.get("action_id") == args.action
    ]
    if args.model_id:
        matches = [action for action in matches if action.get("model_id") == args.model_id]
    if capability:
        matches = [
            action
            for action in matches
            if action.get("capability") == capability
            or capability in list(action.get("capabilities") or [])
        ]
    if source_path:
        matches = [
            action
            for action in matches
            if action.get("source_path") is None
            or str(action.get("source_path") or "") == source_path
        ]
    if not matches:
        raise SystemExit(f"unknown action: {args.action}")
    return matches[0]


def current_model(args: argparse.Namespace) -> dict[str, Any]:
    state = build_model_library_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.model_dir,
        args.model_registry,
        args.import_source,
        args.recommended_preload_root,
        args.recommended_source_map,
        args.recommended_download_staging_dir,
    )
    return build_model(state)


def action_result_base(args: argparse.Namespace, selected: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": args.action,
        "enabled": bool(selected.get("enabled", False)),
        "target_component": "model-library" if selected.get("enabled", False) else None,
        "target_route": None,
        "status": model.get("header", {}).get("status"),
        "inventory_status": model.get("meta", {}).get("inventory_status"),
        "local_model_count": model.get("meta", {}).get("local_model_count", 0),
        "default_text_generation_model": model.get("meta", {}).get("default_text_generation_model"),
        "default_embedding_model": model.get("meta", {}).get("default_embedding_model"),
        "default_reranking_model": model.get("meta", {}).get("default_reranking_model"),
        "diagnostics_count": model.get("meta", {}).get("diagnostics_count", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS model library panel")
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
    parser.add_argument("--import-source", type=Path, default=default_import_source())
    parser.add_argument("--recommended-preload-root", action="append", type=Path, default=None)
    parser.add_argument("--recommended-source-map", type=Path, default=default_recommended_source_map())
    parser.add_argument(
        "--recommended-download-staging-dir",
        type=Path,
        default=default_recommended_download_staging_dir(),
    )
    parser.add_argument("--action")
    parser.add_argument("--source-path", type=Path)
    parser.add_argument("--model-id")
    parser.add_argument("--capability", action="append", choices=["text-generation", "embedding", "reranking"])
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--set-default", action="store_true")
    parser.add_argument("--symlink", action="store_true")
    parser.add_argument("--keep-file", action="store_true")
    parser.add_argument("--quantization")
    parser.add_argument("--parameters-estimate")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        model = current_model(args)
        selected = select_action(model, args)
        result = action_result_base(args, selected, model)
        if not selected.get("enabled", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.action == "refresh":
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.action == "import-local-model":
            source_path = args.source_path or args.import_source
            if source_path is None:
                raise SystemExit("--source-path or --import-source is required for import-local-model")
            import_result = import_local_model(
                args.model_dir,
                args.model_registry,
                source_path,
                model_id=args.model_id or selected.get("model_id"),
                capabilities=args.capability or list(selected.get("capabilities") or []),
                aliases=args.alias,
                set_default=args.set_default or bool(selected.get("set_default")),
                symlink=args.symlink or bool(selected.get("symlink")),
                quantization=args.quantization or str(selected.get("quantization") or ""),
                parameters_estimate=args.parameters_estimate or str(selected.get("parameters_estimate") or ""),
            )
            result.update(import_result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.action == "set-default-model":
            capability = (args.capability or [selected.get("capability")])[0]
            model_id = args.model_id or selected.get("model_id")
            if not capability:
                raise SystemExit("--capability is required for set-default-model")
            if not model_id:
                raise SystemExit("--model-id is required for set-default-model")
            default_result = set_default_model_selection(
                args.model_dir,
                args.model_registry,
                capability,
                model_id,
            )
            result.update(default_result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.action == "delete-model":
            model_id = args.model_id or selected.get("model_id")
            if not model_id:
                raise SystemExit("--model-id is required for delete-model")
            delete_result = delete_registered_model(
                args.model_dir,
                args.model_registry,
                model_id,
                keep_file=args.keep_file or bool(selected.get("keep_file")),
            )
            result.update(delete_result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.action in {"apply-recommended-strategies", "install-recommended-model"}:
            selected_model_ids = None
            if args.action == "install-recommended-model":
                selected_model_id = args.model_id or selected.get("model_id")
                if not selected_model_id:
                    raise SystemExit("--model-id is required for install-recommended-model")
                selected_model_ids = [selected_model_id]
            set_default_policy = "always" if (args.set_default or selected.get("set_default")) else "if-missing"
            apply_result = apply_recommended_distribution_selection(
                args.model_dir,
                args.model_registry,
                model_ids=selected_model_ids,
                preload_roots=args.recommended_preload_root,
                source_map=args.recommended_source_map,
                download_staging_dir=args.recommended_download_staging_dir,
                set_default_policy=set_default_policy,
            )
            result.update(apply_result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        raise SystemExit(f"unsupported action: {args.action}")

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
