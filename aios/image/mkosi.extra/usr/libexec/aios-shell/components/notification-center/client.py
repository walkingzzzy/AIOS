#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from prototype import (
    build_notifications,
    default_panel_action_log,
    default_backend_state,
    default_deviced_socket,
    default_indicator_state,
    default_policy_socket,
    default_recovery_surface,
    default_updated_socket,
    list_approvals,
    load_backend_state,
    load_json,
    load_panel_action_events,
    load_recovery_surface,
    print_notifications,
)


def build_summary(notifications: list[dict]) -> dict:
    by_severity: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for item in notifications:
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        by_source[item["source"]] = by_source.get(item["source"], 0) + 1
    return {
        "total": len(notifications),
        "by_severity": by_severity,
        "by_source": by_source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS notification center shell client")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "summary"])
    parser.add_argument("--recovery-surface", type=Path, default=default_recovery_surface())
    parser.add_argument("--updated-socket", type=Path, default=default_updated_socket())
    parser.add_argument("--indicator-state", type=Path, default=default_indicator_state())
    parser.add_argument("--backend-state", type=Path, default=default_backend_state())
    parser.add_argument("--deviced-socket", type=Path, default=default_deviced_socket())
    parser.add_argument("--policy-socket", type=Path, default=default_policy_socket())
    parser.add_argument("--panel-action-log", type=Path, default=default_panel_action_log())
    parser.add_argument("--approval-fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    recovery_surface = load_recovery_surface(args.recovery_surface, args.updated_socket)
    indicator_state = load_json(args.indicator_state)
    backend_state = load_backend_state(args.backend_state, args.deviced_socket)
    panel_action_events = load_panel_action_events(args.panel_action_log)
    approvals = list_approvals(args.policy_socket, args.approval_fixture)
    notifications = build_notifications(
        recovery_surface,
        indicator_state,
        approvals,
        backend_state,
        panel_action_events,
    )

    if args.command == "summary":
        summary = build_summary(notifications)
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"total: {summary['total']}")
            print(f"by_severity: {json.dumps(summary['by_severity'], ensure_ascii=False, sort_keys=True)}")
            print(f"by_source: {json.dumps(summary['by_source'], ensure_ascii=False, sort_keys=True)}")
        return 0

    if args.json:
        print(json.dumps({"notifications": notifications}, indent=2, ensure_ascii=False))
    else:
        print_notifications(notifications)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
