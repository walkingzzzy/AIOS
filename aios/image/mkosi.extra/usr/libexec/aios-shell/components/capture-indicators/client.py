#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

from prototype import default_indicator_path, load_state, render


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS capture indicators shell client")
    parser.add_argument("command", nargs="?", default="status", choices=["status", "watch"])
    parser.add_argument("--path", type=Path, default=default_indicator_path())
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "status":
        state = load_state(args.path)
        if args.json:
            print(json.dumps(state or {"active": []}, indent=2, ensure_ascii=False))
        else:
            print(render(state))
        return 0

    while True:
        state = load_state(args.path)
        if args.json:
            print(json.dumps(state or {"active": []}, indent=2, ensure_ascii=False))
        else:
            print(render(state))
        time.sleep(args.interval)
        print("---")


if __name__ == "__main__":
    raise SystemExit(main())
