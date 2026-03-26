#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prototype import (
    build_privacy_memory_state,
    default_runtime_platform_env_path,
    render_state,
)


def build_summary(state: dict) -> dict:
    return {
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
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS privacy and memory shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=["summary", "status", "config"],
    )
    parser.add_argument(
        "--runtime-platform-env",
        type=Path,
        default=default_runtime_platform_env_path(),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state = build_privacy_memory_state(args.runtime_platform_env)
    payload = state if args.command == "config" else build_summary(state)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_state(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
