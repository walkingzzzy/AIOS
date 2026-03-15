#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS observability correlation smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing compiled binaries")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--keep-state", action="store_true")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def extract_state_root(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith("state retained at:"):
            return Path(line.split(":", 1)[1].strip())
        if line.startswith("state retained at "):
            return Path(line.removeprefix("state retained at ").strip())
    raise RuntimeError("failed to parse retained state root from team-b smoke output")


def main() -> int:
    args = parse_args()
    team_b_cmd = [sys.executable, str(ROOT / "scripts" / "test-team-b-control-plane-smoke.py"), "--keep-state", "--timeout", str(args.timeout)]
    if args.bin_dir is not None:
        team_b_cmd.extend(["--bin-dir", str(args.bin_dir)])

    completed = subprocess.run(team_b_cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)

    state_root = extract_state_root(completed.stdout)
    report_prefix = ROOT / "out" / "validation" / "cross-service-correlation-report"
    build_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "build-observability-correlation-report.py"),
        "--session-db",
        str(state_root / "state" / "sessiond" / "sessiond.sqlite3"),
        "--policy-audit-log",
        str(state_root / "state" / "policyd" / "audit.jsonl"),
        "--runtime-events-log",
        str(state_root / "state" / "runtimed" / "runtime-events.jsonl"),
        "--remote-audit-log",
        str(state_root / "state" / "runtimed" / "remote-audit.jsonl"),
        "--observability-log",
        str(state_root / "state" / "runtimed" / "observability.jsonl"),
        "--output-prefix",
        str(report_prefix),
    ]
    build_completed = subprocess.run(build_cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if build_completed.returncode != 0:
        sys.stdout.write(build_completed.stdout)
        sys.stderr.write(build_completed.stderr)
        raise SystemExit(build_completed.returncode)

    json_report = report_prefix.with_suffix(".json")
    require(json_report.exists(), "correlation report json was not written")
    payload = json.loads(json_report.read_text())
    require(payload["summary"]["task_count"] >= 2, "expected at least two correlated tasks")
    require(payload["summary"]["audit_entry_count"] >= 3, "expected correlated audit entries")
    require(payload["summary"]["runtime_event_count"] >= 1, "expected correlated runtime events")
    correlations = {item["task_id"]: item for item in payload["correlations"]}
    require(
        any("runtime.infer.completed" in item["runtime_event_kinds"] for item in correlations.values()),
        "correlation report missing runtime completion event",
    )
    require(
        any("approval-pending" in item["audit_decisions"] for item in correlations.values()),
        "correlation report missing approval-pending decision",
    )
    require(
        any("approval-approved" in item["audit_decisions"] for item in correlations.values()),
        "correlation report missing approval-approved decision",
    )
    require(
        any("task.state.updated" in item["observability_kinds"] for item in correlations.values()),
        "correlation report missing sessiond lifecycle observability records",
    )

    print(
        json.dumps(
            {
                "state_root": str(state_root),
                "json_report": str(json_report),
                "markdown_report": str(report_prefix.with_suffix(".md")),
                "task_count": payload["summary"]["task_count"],
                "audit_entry_count": payload["summary"]["audit_entry_count"],
                "runtime_event_count": payload["summary"]["runtime_event_count"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    if not args.keep_state:
        shutil.rmtree(state_root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
