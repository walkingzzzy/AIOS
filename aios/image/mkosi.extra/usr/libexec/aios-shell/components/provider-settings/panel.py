#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Iterable

from prototype import (
    apply_provider_settings,
    build_provider_settings_state,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_runtime_platform_env_path,
)


STATUS_TONES = {
    "configured": "positive",
    "local-only": "positive",
    "partial": "warning",
    "missing-endpoint": "warning",
    "disabled": "neutral",
}


def panel_status(state: dict[str, Any]) -> str:
    if not state.get("provider_enabled", True):
        return "disabled"
    if state.get("endpoint_configured"):
        return "configured"
    if state.get("ai_mode") == "local":
        return "local-only"
    if state.get("ai_mode") == "cloud":
        return "missing-endpoint"
    return "partial"


def tone_for_status(status: str) -> str:
    return STATUS_TONES.get(status, "neutral")


def endpoint_badge_value(state: dict[str, Any]) -> str:
    if state.get("endpoint_model"):
        return str(state.get("endpoint_model"))
    if state.get("endpoint_configured"):
        return "configured"
    return "missing"


def build_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    provider_enabled = bool(state.get("provider_enabled", True))
    endpoint_configured = bool(state.get("endpoint_configured"))
    onboarding_available = bool(state.get("onboarding_endpoint_available"))
    return [
        {
            "action_id": "refresh",
            "label": "Refresh Settings",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "save-provider-settings",
            "label": "Save Provider Settings",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "disable-provider" if provider_enabled else "enable-provider",
            "label": "Disable Provider" if provider_enabled else "Enable Provider",
            "enabled": True,
            "tone": "warning" if provider_enabled else "positive",
            "provider_enabled": not provider_enabled,
        },
        {
            "action_id": "set-mode-local",
            "label": "Set Local Mode",
            "enabled": provider_enabled,
            "tone": "positive" if state.get("ai_mode") == "local" else "neutral",
            "ai_mode": "local",
        },
        {
            "action_id": "set-mode-hybrid",
            "label": "Set Hybrid Mode",
            "enabled": provider_enabled,
            "tone": "positive" if state.get("ai_mode") == "hybrid" else "neutral",
            "ai_mode": "hybrid",
        },
        {
            "action_id": "set-mode-cloud",
            "label": "Set Cloud Mode",
            "enabled": provider_enabled,
            "tone": "positive" if state.get("ai_mode") == "cloud" else "warning",
            "ai_mode": "cloud",
        },
        {
            "action_id": "route-local-first",
            "label": "Prefer Local",
            "enabled": provider_enabled,
            "tone": "positive" if state.get("route_preference") == "local-first" else "neutral",
            "route_preference": "local-first",
        },
        {
            "action_id": "route-remote-first",
            "label": "Prefer Remote",
            "enabled": provider_enabled and endpoint_configured,
            "tone": "positive" if state.get("route_preference") == "remote-first" else "neutral",
            "route_preference": "remote-first",
        },
        {
            "action_id": "route-remote-only",
            "label": "Remote Only",
            "enabled": provider_enabled and endpoint_configured,
            "tone": "warning" if state.get("route_preference") == "remote-only" else "neutral",
            "route_preference": "remote-only",
        },
        {
            "action_id": "use-onboarding-endpoint",
            "label": "Apply Suggested Endpoint",
            "enabled": onboarding_available,
            "tone": "positive" if onboarding_available else "neutral",
            "use_onboarding_endpoint": True,
        },
        {
            "action_id": "clear-remote-endpoint",
            "label": "Clear Remote Endpoint",
            "enabled": bool(
                state.get("persisted_endpoint_base_url")
                or state.get("persisted_endpoint_model")
                or state.get("endpoint_api_key_configured")
            ),
            "tone": "warning",
            "clear_remote_endpoint": True,
        },
    ]


def build_model(state: dict[str, Any]) -> dict[str, Any]:
    status = panel_status(state)
    diagnostics = list(state.get("diagnostics") or [])
    return {
        "component_id": "provider-settings",
        "panel_id": "provider-settings-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Provider Settings",
            "subtitle": (
                f"{state.get('ai_mode_label', 'Unknown')} | "
                f"{'enabled' if state.get('provider_enabled', True) else 'disabled'} | "
                f"{state.get('route_preference_label', 'Unknown')}"
            ),
            "status": status,
            "tone": tone_for_status(status),
        },
        "badges": [
            {
                "label": "Provider",
                "value": "enabled" if state.get("provider_enabled", True) else "disabled",
                "tone": "positive" if state.get("provider_enabled", True) else "neutral",
            },
            {
                "label": "Mode",
                "value": state.get("ai_mode_label") or "Unknown",
                "tone": "neutral",
            },
            {
                "label": "Route",
                "value": state.get("route_preference_label") or "Unknown",
                "tone": "neutral",
            },
            {
                "label": "Remote",
                "value": endpoint_badge_value(state),
                "tone": "positive" if state.get("endpoint_configured") else "warning",
            },
            {
                "label": "API Key",
                "value": "configured" if state.get("endpoint_api_key_configured") else "missing",
                "tone": "positive" if state.get("endpoint_api_key_configured") else "neutral",
            },
            {
                "label": "Diagnostics",
                "value": len(diagnostics),
                "tone": "warning" if diagnostics else "neutral",
            },
        ],
        "actions": build_actions(state),
        "sections": [
            {
                "section_id": "overview",
                "title": "Overview",
                "items": [
                    {
                        "label": "Provider Enabled",
                        "value": state.get("provider_enabled", True),
                        "tone": "positive" if state.get("provider_enabled", True) else "neutral",
                    },
                    {
                        "label": "AI Mode",
                        "value": state.get("ai_mode_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "Route Preference",
                        "value": state.get("route_preference_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "Privacy Profile",
                        "value": state.get("privacy_profile_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "Local CPU Worker",
                        "value": state.get("local_cpu_enabled", False),
                        "tone": "positive" if state.get("local_cpu_enabled", False) else "neutral",
                    },
                    {
                        "label": "Runtime Platform Env",
                        "value": state.get("runtime_platform_env_path") or "-",
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No provider overview available",
            },
            {
                "section_id": "remote-endpoint",
                "title": "Remote Endpoint",
                "items": [
                    {
                        "label": "Configured",
                        "value": state.get("endpoint_configured", False),
                        "tone": "positive" if state.get("endpoint_configured", False) else "warning",
                    },
                    {
                        "label": "Source",
                        "value": state.get("endpoint_source") or "none",
                        "tone": "neutral",
                    },
                    {
                        "label": "Endpoint Base URL",
                        "value": state.get("endpoint_base_url") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Endpoint Model",
                        "value": state.get("endpoint_model") or "-",
                        "tone": "positive" if state.get("endpoint_model") else "warning",
                    },
                    {
                        "label": "API Key",
                        "value": state.get("endpoint_api_key_masked") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "API Key Configured",
                        "value": state.get("endpoint_api_key_configured", False),
                        "tone": "positive" if state.get("endpoint_api_key_configured", False) else "neutral",
                    },
                ],
                "empty_state": "No remote endpoint configured",
            },
            {
                "section_id": "onboarding-endpoint",
                "title": "Onboarding Suggestion",
                "items": [
                    {
                        "label": "Suggested Available",
                        "value": state.get("onboarding_endpoint_available", False),
                        "tone": "positive" if state.get("onboarding_endpoint_available", False) else "neutral",
                    },
                    {
                        "label": "Suggested Base URL",
                        "value": state.get("onboarding_endpoint_base_url") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Suggested Model",
                        "value": state.get("onboarding_endpoint_model") or "-",
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No onboarding endpoint suggestion",
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
            "provider_enabled": state.get("provider_enabled", True),
            "ai_mode": state.get("ai_mode"),
            "ai_mode_label": state.get("ai_mode_label"),
            "privacy_profile": state.get("privacy_profile"),
            "privacy_profile_label": state.get("privacy_profile_label"),
            "route_preference": state.get("route_preference"),
            "route_preference_label": state.get("route_preference_label"),
            "endpoint_configured": state.get("endpoint_configured", False),
            "endpoint_source": state.get("endpoint_source"),
            "endpoint_base_url": state.get("endpoint_base_url"),
            "endpoint_model": state.get("endpoint_model"),
            "endpoint_api_key_configured": state.get("endpoint_api_key_configured", False),
            "endpoint_api_key_masked": state.get("endpoint_api_key_masked"),
            "runtime_platform_env_path": state.get("runtime_platform_env_path"),
            "runtime_platform_env_exists": state.get("runtime_platform_env_exists", False),
            "local_cpu_enabled": state.get("local_cpu_enabled", False),
            "onboarding_endpoint_available": state.get("onboarding_endpoint_available", False),
            "onboarding_endpoint_base_url": state.get("onboarding_endpoint_base_url"),
            "onboarding_endpoint_model": state.get("onboarding_endpoint_model"),
            "diagnostics_count": len(diagnostics),
            "diagnostics": diagnostics,
        },
    }


def render_text(panel: dict[str, Any]) -> str:
    lines = []
    header = panel.get("header", {})
    lines.append(f"{header.get('title', 'Provider Settings')} [{header.get('status', 'unknown')}]")
    lines.append(header.get("subtitle", "-"))
    badges = panel.get("badges", [])
    if badges:
        lines.append(
            "badges: " + ", ".join(f"{item.get('label')}: {item.get('value')}" for item in badges)
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


def iter_actions(model: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for action in model.get("actions", []):
        if isinstance(action, dict):
            yield action
    for section in model.get("sections", []):
        for item in section.get("items", []):
            row_action = item.get("action")
            if isinstance(row_action, dict):
                yield row_action


def select_action(model: dict[str, Any], action_id: str) -> dict[str, Any]:
    selected = next((item for item in iter_actions(model) if item.get("action_id") == action_id), None)
    if selected is None:
        raise SystemExit(f"unknown action: {action_id}")
    return selected


def current_model(args: argparse.Namespace) -> dict[str, Any]:
    state = build_provider_settings_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.runtime_platform_env,
    )
    return build_model(state)


def action_result_base(
    args: argparse.Namespace,
    selected: dict[str, Any],
    model: dict[str, Any],
) -> dict[str, Any]:
    meta = model.get("meta") or {}
    return {
        "action": args.action,
        "enabled": bool(selected.get("enabled", False)),
        "target_component": "provider-settings" if selected.get("enabled", False) else None,
        "target_route": None,
        "status": model.get("header", {}).get("status"),
        "provider_enabled": meta.get("provider_enabled", True),
        "ai_mode": meta.get("ai_mode"),
        "route_preference": meta.get("route_preference"),
        "endpoint_configured": meta.get("endpoint_configured", False),
        "endpoint_model": meta.get("endpoint_model"),
        "endpoint_api_key_configured": meta.get("endpoint_api_key_configured", False),
        "endpoint_api_key_masked": meta.get("endpoint_api_key_masked"),
        "runtime_platform_env_path": meta.get("runtime_platform_env_path"),
        "local_cpu_enabled": meta.get("local_cpu_enabled", False),
        "diagnostics_count": meta.get("diagnostics_count", 0),
    }


def apply_action(args: argparse.Namespace, selected: dict[str, Any]) -> dict[str, Any]:
    provider_enabled = None
    if args.provider_enabled:
        provider_enabled = True
    elif args.provider_disabled:
        provider_enabled = False
    elif selected.get("provider_enabled") is not None:
        provider_enabled = bool(selected.get("provider_enabled"))

    ai_mode = args.ai_mode or selected.get("ai_mode")
    route_preference = args.route_preference or selected.get("route_preference")
    use_onboarding_endpoint = bool(args.use_onboarding_endpoint or selected.get("use_onboarding_endpoint"))
    clear_remote_endpoint = bool(args.clear_remote_endpoint or selected.get("clear_remote_endpoint"))
    clear_api_key = bool(args.clear_api_key or selected.get("clear_api_key"))

    return apply_provider_settings(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.runtime_platform_env,
        provider_enabled=provider_enabled,
        ai_mode=ai_mode,
        route_preference=route_preference,
        privacy_profile=args.privacy_profile,
        endpoint_base_url=args.endpoint_base_url,
        endpoint_model=args.endpoint_model,
        endpoint_api_key=args.api_key,
        clear_api_key=clear_api_key,
        clear_remote_endpoint=clear_remote_endpoint,
        use_onboarding_endpoint=use_onboarding_endpoint,
    )


def action_state_result(action_id: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "saved" if action_id != "refresh" else "refreshed",
        "provider_enabled": state.get("provider_enabled", True),
        "ai_mode": state.get("ai_mode"),
        "ai_mode_label": state.get("ai_mode_label"),
        "privacy_profile": state.get("privacy_profile"),
        "privacy_profile_label": state.get("privacy_profile_label"),
        "route_preference": state.get("route_preference"),
        "route_preference_label": state.get("route_preference_label"),
        "endpoint_configured": state.get("endpoint_configured", False),
        "endpoint_source": state.get("endpoint_source"),
        "endpoint_base_url": state.get("endpoint_base_url"),
        "endpoint_model": state.get("endpoint_model"),
        "endpoint_api_key_configured": state.get("endpoint_api_key_configured", False),
        "endpoint_api_key_masked": state.get("endpoint_api_key_masked"),
        "runtime_platform_env_path": state.get("runtime_platform_env_path"),
        "local_cpu_enabled": state.get("local_cpu_enabled", False),
        "diagnostics": state.get("diagnostics", []),
        "diagnostics_count": len(state.get("diagnostics") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS provider settings panel")
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
    parser.add_argument(
        "--runtime-platform-env",
        type=Path,
        default=default_runtime_platform_env_path(),
    )
    parser.add_argument("--action")
    provider_group = parser.add_mutually_exclusive_group()
    provider_group.add_argument("--provider-enabled", action="store_true")
    provider_group.add_argument("--provider-disabled", action="store_true")
    parser.add_argument("--ai-mode", choices=["local", "cloud", "hybrid", "later"])
    parser.add_argument(
        "--route-preference",
        choices=["local-first", "remote-first", "remote-only"],
    )
    parser.add_argument(
        "--privacy-profile",
        choices=["strict-local", "balanced", "cloud-enhanced"],
    )
    parser.add_argument("--endpoint-base-url")
    parser.add_argument("--endpoint-model")
    parser.add_argument("--api-key")
    parser.add_argument("--clear-api-key", action="store_true")
    parser.add_argument("--clear-remote-endpoint", action="store_true")
    parser.add_argument("--use-onboarding-endpoint", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.action:
            raise SystemExit("--action is required for action")
        model = current_model(args)
        selected = select_action(model, args.action)
        result = action_result_base(args, selected, model)
        if not selected.get("enabled", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.action == "refresh":
            refreshed_state = build_provider_settings_state(
                args.ai_readiness,
                args.ai_onboarding_report,
                args.runtime_platform_env,
            )
            print(
                json.dumps(
                    {**result, **action_state_result(args.action, refreshed_state)},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        updated_state = apply_action(args, selected)
        result.update(action_state_result(args.action, updated_state))
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
