#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prototype import (
    build_system_assistant_state,
    default_agent_socket,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_model_dir,
    default_model_registry,
    default_runtime_platform_env_path,
    default_task_fixture,
    render_state,
)


def build_summary(state: dict) -> dict:
    ai_state = state.get("ai_state") or {}
    readiness = ai_state.get("readiness") or {}
    provider_state = state.get("provider_state") or {}
    privacy_state = state.get("privacy_state") or {}
    request = state.get("request") or {}
    return {
        "intent": request.get("intent"),
        "risk_level": request.get("risk_level"),
        "risk_label": request.get("risk_label"),
        "approval_required": request.get("approval_required", False),
        "route_target_component": request.get("route_target_component"),
        "resolved_session_id": state.get("resolved_session_id"),
        "task_count": len(state.get("tasks") or []),
        "pending_approval_count": len(state.get("pending_approvals") or []),
        "readiness_state": readiness.get("state"),
        "readiness_label": readiness.get("state_label"),
        "default_text_generation_model": ai_state.get("default_text_generation_model"),
        "route_preference": provider_state.get("route_preference"),
        "route_preference_label": provider_state.get("route_preference_label"),
        "approval_default_policy": privacy_state.get("approval_default_policy"),
        "approval_default_policy_label": privacy_state.get("approval_default_policy_label"),
        "diagnostics": state.get("diagnostics", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS system assistant shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=["summary", "status", "request"],
    )
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--task-fixture", type=Path, default=default_task_fixture())
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--intent", default="")
    parser.add_argument("--title")
    parser.add_argument("--task-state", default="planned")
    parser.add_argument("--ai-readiness", type=Path, default=default_ai_readiness_path())
    parser.add_argument(
        "--ai-onboarding-report",
        type=Path,
        default=default_ai_onboarding_report_path(),
    )
    parser.add_argument("--model-dir", type=Path, default=default_model_dir())
    parser.add_argument("--model-registry", type=Path, default=default_model_registry())
    parser.add_argument(
        "--runtime-platform-env",
        type=Path,
        default=default_runtime_platform_env_path(),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state = build_system_assistant_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.model_dir,
        args.model_registry,
        args.runtime_platform_env,
        args.agent_socket,
        args.fixture,
        args.task_fixture,
        args.approval_fixture,
        args.session_id,
        args.intent,
    )
    payload = build_summary(state)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_state(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
