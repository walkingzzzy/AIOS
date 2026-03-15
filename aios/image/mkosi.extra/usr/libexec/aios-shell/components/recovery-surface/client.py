#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from prototype import default_socket, default_surface, load_surface_or_rpc, print_status, rpc_call


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS recovery surface shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["status", "summary", "check", "apply", "rollback", "bundle"],
    )
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--surface", type=Path, default=default_surface())
    parser.add_argument("--target-version")
    parser.add_argument("--reason")
    parser.add_argument("--recovery-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "status":
        surface = load_surface_or_rpc(args.surface, args.socket)
        if args.json:
            print(json.dumps(surface, indent=2, ensure_ascii=False))
        else:
            print_status(surface)
        return 0

    if args.command == "summary":
        surface = load_surface_or_rpc(args.surface, args.socket)
        summary = {
            "service_id": surface.get("service_id"),
            "overall_status": surface.get("overall_status"),
            "deployment_status": surface.get("deployment_status"),
            "rollback_ready": surface.get("rollback_ready", False),
            "action_count": len(surface.get("available_actions", [])),
        }
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"service: {summary['service_id']}")
            print(f"overall: {summary['overall_status']}")
            print(f"deployment: {summary['deployment_status']}")
            print(f"rollback_ready: {summary['rollback_ready']}")
            print(f"action_count: {summary['action_count']}")
        return 0

    if args.command == "check":
        print(json.dumps(rpc_call(args.socket, "update.check", {}), indent=2, ensure_ascii=False))
        return 0

    if args.command == "apply":
        print(
            json.dumps(
                rpc_call(
                    args.socket,
                    "update.apply",
                    {"target_version": args.target_version, "reason": args.reason, "dry_run": False},
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "rollback":
        print(
            json.dumps(
                rpc_call(
                    args.socket,
                    "update.rollback",
                    {"recovery_id": args.recovery_id, "reason": args.reason, "dry_run": False},
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(
        json.dumps(
            rpc_call(args.socket, "recovery.bundle.export", {"reason": args.reason}),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
