#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from prototype import build_summary, default_sessiond_socket, load_payload, print_handles


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS portal chooser shell client")
    parser.add_argument("command", nargs="?", default="summary", choices=["list", "summary"])
    parser.add_argument("--socket", type=Path, default=default_sessiond_socket())
    parser.add_argument("--session-id")
    parser.add_argument("--handle-fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = load_payload(args.socket, args.session_id, args.handle_fixture)
    handles = payload.get("handles", [])
    request = payload.get("request") or {}
    if args.command == "list":
        if args.json:
            print(json.dumps({"handles": handles, "request": request}, indent=2, ensure_ascii=False))
        else:
            print_handles(handles)
        return 0

    summary = build_summary(handles, args.session_id, request)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"total: {summary['total']}")
        print(json.dumps(summary["by_kind"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
