#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from prototype import default_backend_state, default_socket, load_model, render


IGNORE_READINESS = {
    "native-ready",
    "native-live",
    "native-state-bridge",
    "command-adapter",
    "disabled",
    "native-stub",
}


def needs_attention(status: dict) -> bool:
    return status.get("readiness") not in IGNORE_READINESS


def filter_attention(model: dict | None) -> dict | None:
    if model is None:
        return None
    result = deepcopy(model)
    statuses = [item for item in result.get("statuses", []) if needs_attention(item)]
    modalities = {item.get("modality") for item in statuses}
    result["statuses"] = statuses
    result["adapters"] = [
        item for item in result.get("adapters", []) if item.get("modality") in modalities
    ]
    result["evidence_artifacts"] = [
        item for item in result.get("evidence_artifacts", []) if item.get("modality") in modalities
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS device backend status shell client")
    parser.add_argument("command", nargs="?", default="status", choices=["status", "attention"])
    parser.add_argument("--path", type=Path, default=default_backend_state())
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    model = load_model(args.path, args.fixture, args.socket)
    if args.command == "attention":
        model = filter_attention(model)

    if args.json:
        print(json.dumps(model or {"statuses": [], "adapters": [], "notes": []}, indent=2, ensure_ascii=False))
    else:
        print(render(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
