#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType

from prototype import default_agent_socket, default_socket, fixture_call, rpc_call


STATUS_TONES = {
    "pending": "warning",
    "approved": "positive",
    "rejected": "critical",
}
_PRIVACY_MEMORY_PROTOTYPE_MODULE: ModuleType | None = None


def _load_module(module_name: str, path: Path) -> ModuleType:
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_privacy_memory_prototype_module() -> ModuleType:
    global _PRIVACY_MEMORY_PROTOTYPE_MODULE
    if _PRIVACY_MEMORY_PROTOTYPE_MODULE is not None:
        return _PRIVACY_MEMORY_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "privacy-memory" / "prototype.py"
    _PRIVACY_MEMORY_PROTOTYPE_MODULE = _load_module(
        "aios_shell_privacy_memory_prototype",
        module_path,
    )
    return _PRIVACY_MEMORY_PROTOTYPE_MODULE


def default_runtime_platform_env_path() -> Path:
    return load_privacy_memory_prototype_module().default_runtime_platform_env_path()


def build_privacy_memory_state(runtime_platform_env_path: Path | None) -> dict:
    return load_privacy_memory_prototype_module().build_privacy_memory_state(runtime_platform_env_path)


def tone_for(status: str | None) -> str:
    if not status:
        return "neutral"
    return STATUS_TONES.get(status, "neutral")


def list_approvals(agent_socket_path: Path, fixture: Path | None, session_id: str | None, task_id: str | None, status: str | None) -> dict:
    if fixture is not None:
        args = argparse.Namespace(session_id=session_id, task_id=task_id, status=status, approval_ref=None)
        return fixture_call(fixture, "list", args)
    return rpc_call(
        agent_socket_path,
        "agent.approval.list",
        {"session_id": session_id, "task_id": task_id, "status": status},
    )


def resolve_approval(socket_path: Path, fixture: Path | None, approval_ref: str, status: str, resolver: str, reason: str | None) -> dict:
    if fixture is not None:
        args = argparse.Namespace(approval_ref=approval_ref, status=status, resolver=resolver, reason=reason)
        return fixture_call(fixture, "resolve", args)
    return rpc_call(
        socket_path,
        "agent.approval.resolve",
        {"approval_ref": approval_ref, "status": status, "resolver": resolver, "reason": reason},
    )


def load_approvals_with_fallback(
    agent_socket_path: Path,
    fixture: Path | None,
    session_id: str | None,
    task_id: str | None,
    status: str | None,
) -> tuple[dict, str | None]:
    try:
        return list_approvals(agent_socket_path, fixture, session_id, task_id, status), None
    except Exception as error:
        return {"approvals": []}, str(error)


def build_summary(approvals: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    for item in approvals:
        status = item.get("status", "unknown")
        lane = item.get("approval_lane", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_lane[lane] = by_lane.get(lane, 0) + 1
    return {"total": len(approvals), "by_status": by_status, "by_lane": by_lane}


def build_model(
    result: dict,
    session_id: str | None,
    task_id: str | None,
    privacy_memory: dict | None = None,
    data_source_error: str | None = None,
) -> dict:
    approvals = result.get("approvals", [])
    summary = build_summary(approvals)
    focus = next((item for item in approvals if item.get("status") == "pending"), approvals[0] if approvals else None)
    privacy_memory = privacy_memory or {}

    approval_items = [
        {
            "approval_ref": item.get("approval_ref"),
            "label": item.get("capability_id") or item.get("approval_ref"),
            "status": item.get("status"),
            "approval_lane": item.get("approval_lane"),
            "tone": tone_for(item.get("status")),
        }
        for item in approvals
    ]
    actions = []
    if focus:
        actions.extend(
            [
                {
                    "action_id": "approve",
                    "label": "Approve",
                    "approval_ref": focus.get("approval_ref"),
                    "target_status": "approved",
                    "enabled": focus.get("status") == "pending",
                },
                {
                    "action_id": "reject",
                    "label": "Reject",
                    "approval_ref": focus.get("approval_ref"),
                    "target_status": "rejected",
                    "enabled": focus.get("status") == "pending",
                },
            ]
        )

    return {
        "component_id": "approval-panel",
        "panel_id": "approval-panel-shell",
        "panel_kind": "shell-panel",
        "header": {
            "title": "Approval Panel",
            "subtitle": f"session {session_id or '-'} · task {task_id or '-'}",
            "status": (focus or {}).get("status", "idle"),
            "tone": tone_for((focus or {}).get("status")),
        },
        "badges": [
            {"label": "Total", "value": summary["total"], "tone": "neutral"},
            {"label": "Pending", "value": summary["by_status"].get("pending", 0), "tone": tone_for("pending")},
            {"label": "Lanes", "value": len(summary["by_lane"]), "tone": "neutral"},
            {
                "label": "Policy",
                "value": privacy_memory.get("approval_default_policy_label") or "Unknown",
                "tone": "neutral",
            },
        ],
        "actions": actions,
        "sections": [
            {
                "section_id": "approvals",
                "title": "Approvals",
                "items": approval_items,
                "empty_state": "No approvals found",
            },
            {
                "section_id": "lanes",
                "title": "Approval Lanes",
                "items": [
                    {"label": lane, "value": count, "tone": "neutral"}
                    for lane, count in sorted(summary["by_lane"].items())
                ],
                "empty_state": "No approval lanes",
            },
            {
                "section_id": "policy-defaults",
                "title": "Policy Defaults",
                "items": [
                    {
                        "label": "Default High-Risk Policy",
                        "value": privacy_memory.get("approval_default_policy_label") or "Unknown",
                        "tone": "neutral",
                    },
                    {
                        "label": "Remote Prompt Level",
                        "value": privacy_memory.get("remote_prompt_level_label") or "Unknown",
                        "tone": "warning" if privacy_memory.get("remote_prompt_level") == "minimal" else "neutral",
                    },
                    {
                        "label": "Memory Enabled",
                        "value": privacy_memory.get("memory_enabled", True),
                        "tone": "positive" if privacy_memory.get("memory_enabled", True) else "neutral",
                    },
                    {
                        "label": "Memory Retention Days",
                        "value": privacy_memory.get("memory_retention_days"),
                        "tone": "neutral",
                    },
                    {
                        "label": "Audit Retention Days",
                        "value": privacy_memory.get("audit_retention_days"),
                        "tone": "neutral",
                    },
                    {
                        "label": "Runtime Platform Env",
                        "value": privacy_memory.get("runtime_platform_env_path") or "-",
                        "tone": "neutral",
                    },
                ],
                "empty_state": "No policy defaults available",
            },
        ],
        "meta": {
            "session_id": session_id,
            "task_id": task_id,
            "focus_approval_ref": (focus or {}).get("approval_ref"),
            "approval_count": len(approvals),
            "status_summary": summary["by_status"],
            "memory_enabled": privacy_memory.get("memory_enabled", True),
            "memory_retention_days": privacy_memory.get("memory_retention_days"),
            "audit_retention_days": privacy_memory.get("audit_retention_days"),
            "approval_default_policy": privacy_memory.get("approval_default_policy"),
            "approval_default_policy_label": privacy_memory.get("approval_default_policy_label"),
            "remote_prompt_level": privacy_memory.get("remote_prompt_level"),
            "remote_prompt_level_label": privacy_memory.get("remote_prompt_level_label"),
            "runtime_platform_env_path": privacy_memory.get("runtime_platform_env_path"),
            "runtime_platform_env_exists": privacy_memory.get("runtime_platform_env_exists", False),
            "data_source_status": "ready" if data_source_error is None else "fallback-empty",
            "data_source_error": data_source_error,
        },
    }


def render_text(panel: dict) -> str:
    lines = []
    header = panel["header"]
    lines.append(f"{header['title']} [{header['status']}]")
    lines.append(header["subtitle"])
    lines.append("badges: " + ", ".join(f"{item['label']}: {item['value']}" for item in panel["badges"]))
    meta = panel.get("meta") or {}
    if meta.get("data_source_status") != "ready":
        lines.append(f"source: {meta.get('data_source_status')}")
        if meta.get("data_source_error"):
            lines.append(f"source_error: {meta['data_source_error']}")
    if panel["actions"]:
        lines.append("actions: " + ", ".join(action["label"] for action in panel["actions"] if action.get("enabled", True)))
    for section in panel["sections"]:
        lines.append(f"[{section['title']}]")
        items = section.get("items", [])
        if items:
            for item in items:
                if section["section_id"] == "approvals":
                    lines.append(f"- {item['approval_ref']}: {item['status']} lane={item['approval_lane']} capability={item['label']}")
                else:
                    lines.append(f"- {item['label']}: {item['value']}")
        else:
            lines.append(f"- {section['empty_state']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS approval panel")
    parser.add_argument("command", nargs="?", default="render", choices=["render", "model", "action", "watch"])
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--status")
    parser.add_argument("--runtime-platform-env", type=Path, default=default_runtime_platform_env_path())
    parser.add_argument("--approval-ref")
    parser.add_argument("--resolver", default="shell-approval-panel")
    parser.add_argument("--reason")
    parser.add_argument("--action")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    if args.command == "action":
        if not args.approval_ref:
            raise SystemExit("--approval-ref is required for action")
        target_status = args.status
        if not target_status:
            if args.action == "approve":
                target_status = "approved"
            elif args.action == "reject":
                target_status = "rejected"
            else:
                raise SystemExit("--status is required for custom action")
        result = resolve_approval(args.agent_socket, args.fixture, args.approval_ref, target_status, args.resolver, args.reason)
        result["target_component"] = "task-surface" if target_status == "approved" else "approval-panel"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "watch":
        iterations = max(1, args.iterations)
        for index in range(iterations):
            result, data_source_error = load_approvals_with_fallback(
                args.agent_socket,
                args.fixture,
                args.session_id,
                args.task_id,
                args.status,
            )
            model = build_model(
                result,
                args.session_id,
                args.task_id,
                build_privacy_memory_state(args.runtime_platform_env),
                data_source_error,
            )
            if args.json:
                print(json.dumps(model, indent=2, ensure_ascii=False))
            else:
                if index:
                    print()
                print(render_text(model))
            if index + 1 < iterations:
                time.sleep(args.interval)
        return 0

    result, data_source_error = load_approvals_with_fallback(
        args.agent_socket,
        args.fixture,
        args.session_id,
        args.task_id,
        args.status,
    )
    model = build_model(
        result,
        args.session_id,
        args.task_id,
        build_privacy_memory_state(args.runtime_platform_env),
        data_source_error,
    )
    if args.command == "model" or args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    else:
        print(render_text(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

