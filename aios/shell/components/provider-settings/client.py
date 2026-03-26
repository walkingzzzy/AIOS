#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prototype import (
    build_provider_settings_state,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_runtime_platform_env_path,
    render_state,
)


def build_summary(state: dict) -> dict:
    return {
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
        "diagnostics": state.get("diagnostics", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS provider settings shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=["summary", "status", "config"],
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state = build_provider_settings_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.runtime_platform_env,
    )
    payload = state if args.command == "config" else build_summary(state)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_state(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
