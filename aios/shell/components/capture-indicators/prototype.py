#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def default_indicator_path() -> Path:
    return Path(
        os.environ.get(
            "AIOS_DEVICED_INDICATOR_STATE_PATH",
            "/var/lib/aios/deviced/indicator-state.json",
        )
    )


def load_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def render(state: dict | None) -> str:
    if state is None:
        return "no active indicator state"

    lines: list[str] = [f"updated_at: {state['updated_at']}"]
    for item in state.get("active", []):
        label = item["message"]
        approval = item.get("approval_status")
        if approval:
            label = f"{label} [{approval}]"
        lines.append(f"- {item['modality']}: {label}")
    return "\n".join(lines)


def show(path: Path) -> None:
    print(render(load_state(path)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS capture indicator prototype")
    parser.add_argument("--path", type=Path, default=default_indicator_path())
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.watch:
        state = load_state(args.path)
        if args.json:
            print(json.dumps(state or {"active": []}, indent=2, ensure_ascii=False))
        else:
            print(render(state))
    else:
        while True:
            show(args.path)
            time.sleep(args.interval)
            print("---")
