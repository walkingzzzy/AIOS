#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Iterable

from prototype import (
    apply_privacy_memory_settings,
    build_privacy_memory_state,
    default_runtime_platform_env_path,
)


STATUS_TONES = {
    "configured": "positive",
    "attention": "warning",
    "memory-disabled": "neutral",
}


def panel_status(state: dict[str, Any]) -> str:
    if not state.get("memory_enabled", True):
        return "memory-disabled"
    if state.get("diagnostics"):
        return "attention"
    return "configured"


def tone_for_status(status: str) -> str:
    return STATUS_TONES.get(status, "neutral")


def build_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    memory_enabled = bool(state.get("memory_enabled", True))
    return [
        {
            "action_id": "refresh",
            "label": "Refresh Settings",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "save-privacy-memory",
            "label": "Save Privacy Settings",
            "enabled": True,
            "tone": "neutral",
        },
        {
            "action_id": "disable-memory" if memory_enabled else "enable-memory",
            "label": "Disable Memory" if memory_enabled else "Enable Memory",
            "enabled": True,
            "tone": "warning" if memory_enabled else "positive",
            "memory_enabled": not memory_enabled,
        },
        {
            "action_id": "set-memory-retention-7",
            "label": "Memory 7 Days",
            "enabled": True,
            "tone": "warning" if state.get("memory_retention_days") == 7 else "neutral",
            "memory_retention_days": 7,
        },
        {
            "action_id": "set-memory-retention-30",
            "label": "Memory 30 Days",
            "enabled": True,
            "tone": "positive" if state.get("memory_retention_days") == 30 else "neutral",
            "memory_retention_days": 30,
        },
        {
            "action_id": "set-memory-retention-90",
            "label": "Memory 90 Days",
            "enabled": True,
            "tone": "neutral" if state.get("memory_retention_days") != 90 else "positive",
            "memory_retention_days": 90,
        },
        {
            "action_id": "set-audit-retention-30",
            "label": "Audit 30 Days",
            "enabled": True,
            "tone": "warning" if state.get("audit_retention_days") == 30 else "neutral",
            "audit_retention_days": 30,
        },
        {
            "action_id": "set-audit-retention-90",
            "label": "Audit 90 Days",
            "enabled": True,
            "tone": "positive" if state.get("audit_retention_days") == 90 else "neutral",
            "audit_retention_days": 90,
        },
        {
            "action_id": "set-audit-retention-180",
            "label": "Audit 180 Days",
            "enabled": True,
            "tone": "neutral" if state.get("audit_retention_days") != 180 else "positive",
            "audit_retention_days": 180,
        },
        {
            "action_id": "approval-policy-prompt-required",
            "label": "Prompt Required",
            "enabled": True,
            "tone": "positive" if state.get("approval_default_policy") == "prompt-required" else "neutral",
            "approval_default_policy": "prompt-required",
        },
        {
            "action_id": "approval-policy-session-trust",
            "label": "Session Trust",
            "enabled": True,
            "tone": "neutral" if state.get("approval_default_policy") != "session-trust" else "positive",
            "approval_default_policy": "session-trust",
        },
        {
            "action_id": "approval-policy-operator-gate",
            "label": "Operator Gate",
            "enabled": True,
            "tone": "warning" if state.get("approval_default_policy") == "operator-gate" else "neutral",
            "approval_default_policy": "operator-gate",
        },
        {
            "action_id": "remote-prompt-full",
            "label": "Remote Prompt Full",
            "enabled": True,
            "tone": "positive" if state.get("remote_prompt_level") == "full" else "neutral",
            "remote_prompt_level": "full",
        },
        {
            "action_id": "remote-prompt-summary",
            "label": "Remote Prompt Summary",
            "enabled": True,
            "tone": "neutral" if state.get("remote_prompt_level") != "summary" else "positive",
            "remote_prompt_level": "summary",
        },
        {
            "action_id": "remote-prompt-minimal",
            "label": "Remote Prompt Minimal",
            "enabled": True,
            "tone": "warning" if state.get("remote_prompt_level") == "minimal" else "neutral",
            "remote_prompt_level": "minimal",
        },
    ]


def build_model(state: dict[str, Any]) -> dict[str, Any]:
    status = panel_status(state)
    diagnostics = list(state.get("diagnostics") or [])
    return {
        "component_id": "privacy-memory",
        "panel_id": "privacy-memory-panel",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Privacy & Memory",
            "subtitle": (
                f"{'memory on' if state.get('memory_enabled', True) else 'memory off'} | "
                f"{state.get('memory_retention_days')}d memory | "
                f"{state.get('audit_retention_days')}d audit | "
                f"{state.get('remote_prompt_level_label', 'Unknown')}"
            ),
            "status": status,
            "tone": tone_for_status(status),
        },
        "badges": [
            {
                "label": "Memory",
                "value": "enabled" if state.get("memory_enabled", True) else "disabled",
                "tone": "positive" if state.get("memory_enabled", True) else "neutral",
            },
            {
                "label": "Memory Retention",
                "value": f"{state.get('memory_retention_days')}d",
                "tone": "neutral",
            },
            {
                "label": "Audit Retention",
                "value": f"{state.get('audit_retention_days')}d",
                "tone": "neutral",
            },
            {
                "label": "Approval",
                "value": state.get("approval_default_policy_label") or "Unknown",
                "tone": "neutral",
            },
            {
                "label": "Remote Prompt",
                "value": state.get("remote_prompt_level_label") or "Unknown",
                "tone": "warning" if state.get("remote_prompt_level") == "minimal" else "neutral",
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
                        "label": "Memory Enabled",
                        "value": state.get("memory_enabled", True),
                        "tone": "positive" if state.get("memory_enabled", True) else "neutral",
                    },
                    {
                        "label": "Runtime Platform Env",
                        "value": state.get("runtime_platform_env_path") or "-",
                        "tone": "neutral",
                    },
                    {
                        "label": "Runtime Env Exists",
                        "value": state.get("runtime_platform_env_exists", False),
                        "tone": "positive" if state.get("runtime_platform_env_exists", False) else "warning",
                    },
                    {
                        "label": "Managed Keys",
                        "value": len(state.get("managed_keys") or []),
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No privacy overview available",
            },
            {
                "section_id": "retention",
                "title": "Retention",
                "items": [
                    {
                        "label": "Memory Retention Days",
                        "value": state.get("memory_retention_days"),
                        "tone": "neutral",
                    },
                    {
                        "label": "Audit Retention Days",
                        "value": state.get("audit_retention_days"),
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No retention policy configured",
            },
            {
                "section_id": "governance",
                "title": "Governance Defaults",
                "items": [
                    {
                        "label": "Default High-Risk Policy",
                        "value": state.get("approval_default_policy_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "Remote Prompt Level",
                        "value": state.get("remote_prompt_level_label") or "Unknown",
                        "tone": "warning" if state.get("remote_prompt_level") == "minimal" else "neutral",
                    },
                ],
                "empty_state": "No governance defaults configured",
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
            "memory_enabled": state.get("memory_enabled", True),
            "memory_retention_days": state.get("memory_retention_days"),
            "audit_retention_days": state.get("audit_retention_days"),
            "approval_default_policy": state.get("approval_default_policy"),
            "approval_default_policy_label": state.get("approval_default_policy_label"),
            "remote_prompt_level": state.get("remote_prompt_level"),
            "remote_prompt_level_label": state.get("remote_prompt_level_label"),
            "runtime_platform_env_path": state.get("runtime_platform_env_path"),
            "runtime_platform_env_exists": state.get("runtime_platform_env_exists", False),
            "diagnostics_count": len(diagnostics),
            "diagnostics": diagnostics,
        },
    }


def render_text(panel: dict[str, Any]) -> str:
    lines = []
    header = panel.get("header", {})
    lines.append(f"{header.get('title', 'Privacy & Memory')} [{header.get('status', 'unknown')}]")
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
    state = build_privacy_memory_state(args.runtime_platform_env)
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
        "target_component": "privacy-memory" if selected.get("enabled", False) else None,
        "target_route": None,
        "status": model.get("header", {}).get("status"),
        "memory_enabled": meta.get("memory_enabled", True),
        "memory_retention_days": meta.get("memory_retention_days"),
        "audit_retention_days": meta.get("audit_retention_days"),
        "approval_default_policy": meta.get("approval_default_policy"),
        "remote_prompt_level": meta.get("remote_prompt_level"),
        "runtime_platform_env_path": meta.get("runtime_platform_env_path"),
        "diagnostics_count": meta.get("diagnostics_count", 0),
    }


def apply_action(args: argparse.Namespace, selected: dict[str, Any]) -> dict[str, Any]:
    memory_enabled = None
    if args.memory_enabled:
        memory_enabled = True
    elif args.memory_disabled:
        memory_enabled = False
    elif selected.get("memory_enabled") is not None:
        memory_enabled = bool(selected.get("memory_enabled"))

    memory_retention_days = (
        args.memory_retention_days
        if args.memory_retention_days is not None
        else selected.get("memory_retention_days")
    )
    audit_retention_days = (
        args.audit_retention_days
        if args.audit_retention_days is not None
        else selected.get("audit_retention_days")
    )
    approval_default_policy = args.approval_policy or selected.get("approval_default_policy")
    remote_prompt_level = args.remote_prompt_level or selected.get("remote_prompt_level")

    return apply_privacy_memory_settings(
        args.runtime_platform_env,
        memory_enabled=memory_enabled,
        memory_retention_days=memory_retention_days,
        audit_retention_days=audit_retention_days,
        approval_default_policy=approval_default_policy,
        remote_prompt_level=remote_prompt_level,
    )


def action_state_result(action_id: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "saved" if action_id != "refresh" else "refreshed",
        "memory_enabled": state.get("memory_enabled", True),
        "memory_retention_days": state.get("memory_retention_days"),
        "audit_retention_days": state.get("audit_retention_days"),
        "approval_default_policy": state.get("approval_default_policy"),
        "approval_default_policy_label": state.get("approval_default_policy_label"),
        "remote_prompt_level": state.get("remote_prompt_level"),
        "remote_prompt_level_label": state.get("remote_prompt_level_label"),
        "runtime_platform_env_path": state.get("runtime_platform_env_path"),
        "runtime_platform_env_exists": state.get("runtime_platform_env_exists", False),
        "diagnostics": state.get("diagnostics", []),
        "diagnostics_count": len(state.get("diagnostics") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS privacy and memory panel")
    parser.add_argument(
        "command",
        nargs="?",
        default="render",
        choices=["render", "model", "action", "watch"],
    )
    parser.add_argument(
        "--runtime-platform-env",
        type=Path,
        default=default_runtime_platform_env_path(),
    )
    parser.add_argument("--action")
    memory_group = parser.add_mutually_exclusive_group()
    memory_group.add_argument("--memory-enabled", action="store_true")
    memory_group.add_argument("--memory-disabled", action="store_true")
    parser.add_argument("--memory-retention-days", type=int)
    parser.add_argument("--audit-retention-days", type=int)
    parser.add_argument(
        "--approval-policy",
        choices=["prompt-required", "session-trust", "operator-gate"],
    )
    parser.add_argument(
        "--remote-prompt-level",
        choices=["full", "summary", "minimal"],
    )
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
            refreshed_state = build_privacy_memory_state(args.runtime_platform_env)
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
