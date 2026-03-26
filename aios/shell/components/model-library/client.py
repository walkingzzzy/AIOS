#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prototype import (
    build_model_library_state,
    default_ai_onboarding_report_path,
    default_ai_readiness_path,
    default_import_source,
    default_model_dir,
    default_model_registry,
)


def build_summary(state: dict) -> dict:
    readiness = state.get("readiness") or {}
    inventory = state.get("inventory") or {}
    import_candidate = state.get("import_candidate") or {}
    return {
        "state": readiness.get("state"),
        "state_label": readiness.get("state_label"),
        "tone": readiness.get("tone"),
        "ai_mode": readiness.get("ai_mode"),
        "inventory_status": inventory.get("source_status"),
        "local_model_count": state.get("effective_local_model_count", 0),
        "default_text_generation_model": state.get("default_text_generation_model"),
        "default_embedding_model": state.get("default_embedding_model"),
        "default_reranking_model": state.get("default_reranking_model"),
        "import_source_configured": import_candidate.get("configured", False),
        "import_source_ready": import_candidate.get("ready", False),
        "import_source_path": import_candidate.get("source_path"),
        "diagnostics": state.get("diagnostics", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS model library shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=["summary", "status", "inventory", "defaults"],
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state = build_model_library_state(
        args.ai_readiness,
        args.ai_onboarding_report,
        args.model_dir,
        args.model_registry,
        args.import_source,
    )
    if args.command in {"summary", "status"}:
        payload = build_summary(state)
    elif args.command == "inventory":
        payload = state.get("inventory") or {}
    else:
        payload = {
            "text-generation": state.get("default_text_generation_model"),
            "embedding": state.get("default_embedding_model"),
            "reranking": state.get("default_reranking_model"),
        }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
