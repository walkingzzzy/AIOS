#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prototype import (
    build_ai_center_state,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_model_dir,
    default_model_registry,
    render_state,
)


def build_summary(state: dict) -> dict:
    readiness = state.get("readiness") or {}
    inventory = state.get("inventory") or {}
    return {
        "state": readiness.get("state"),
        "state_label": readiness.get("state_label"),
        "tone": readiness.get("tone"),
        "ai_enabled": readiness.get("ai_enabled"),
        "ai_mode": readiness.get("ai_mode"),
        "mode_label": state.get("mode_label"),
        "effective_local_model_count": state.get("effective_local_model_count", 0),
        "reported_local_model_count": state.get("reported_local_model_count", 0),
        "inventory_local_model_count": state.get("inventory_local_model_count", 0),
        "inventory_status": inventory.get("source_status"),
        "default_text_generation_model": state.get("default_text_generation_model"),
        "endpoint_configured": readiness.get("endpoint_configured", False),
        "endpoint_base_url": readiness.get("endpoint_base_url"),
        "endpoint_model": readiness.get("endpoint_model"),
        "privacy_profile": readiness.get("privacy_profile"),
        "next_action": readiness.get("next_action"),
        "diagnostics": state.get("diagnostics", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS AI center shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=["summary", "status", "inventory"],
    )
    parser.add_argument("--ai-readiness", type=Path, default=default_ai_readiness_path())
    parser.add_argument(
        "--ai-onboarding-report",
        type=Path,
        default=default_ai_onboarding_report_path(),
    )
    parser.add_argument("--model-dir", type=Path, default=default_model_dir())
    parser.add_argument("--model-registry", type=Path, default=default_model_registry())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state = build_ai_center_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.model_dir,
        args.model_registry,
    )

    payload = state.get("inventory") or {} if args.command == "inventory" else build_summary(state)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_state(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
