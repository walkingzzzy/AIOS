#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = RUNTIME_ROOT.parent
for candidate in (SHELL_ROOT, RUNTIME_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import shellctl
from panel_actions import dispatch_panel_action, select_panel_action, summarize_action_result
from shell_snapshot import add_snapshot_arguments, build_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch shell panel actions for panel-host slots")
    add_snapshot_arguments(parser)
    parser.add_argument("--component")
    parser.add_argument("--action")
    parser.add_argument("--input-kind")
    return parser.parse_args()


def resolve_component(args: argparse.Namespace) -> str:
    component = (
        args.component
        or os.environ.get("AIOS_SHELL_PANEL_COMPONENT")
        or os.environ.get("AIOS_SHELL_PANEL_SLOT_ID")
    )
    if not component:
        raise SystemExit("panel component is required")
    return shellctl.normalize_component(component)


def resolve_action_id(args: argparse.Namespace) -> str | None:
    return args.action or os.environ.get("AIOS_SHELL_PANEL_ACTION_ID")


def main() -> int:
    args = parse_args()
    profile = shellctl.load_profile(args.profile)
    component = resolve_component(args)
    action_id = resolve_action_id(args)

    snapshot = build_snapshot(profile, args)
    action = select_panel_action(snapshot, component, action_id)
    payload = dispatch_panel_action(profile, args, snapshot, component, action)
    result = payload["result"]
    response = {
        "component": component,
        "panel_id": os.environ.get("AIOS_SHELL_PANEL_ID"),
        "slot_id": os.environ.get("AIOS_SHELL_PANEL_SLOT_ID", component),
        "action_id": action.get("action_id"),
        "input_kind": args.input_kind or os.environ.get("AIOS_SHELL_PANEL_INPUT_KIND"),
        "summary": summarize_action_result(component, action, result),
        "result": result,
    }

    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
