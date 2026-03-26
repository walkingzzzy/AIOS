#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "full-regression-report"
SCHEMA_PATH = ROOT / "aios" / "observability" / "schemas" / "full-regression-report.schema.json"
UTF8 = "utf-8"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the AIOS full regression suite dry-run report")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help="Output prefix for the generated .json and .md reports",
    )
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_json(path: Path):
    return json.loads(path.read_text(encoding=UTF8))


def main() -> int:
    args = parse_args()
    output_prefix = args.output_prefix

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-aios-ci-local.py"),
            "--stage",
            "full",
            "--dry-run",
            "--output-prefix",
            str(output_prefix),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"dry-run regression suite failed: {completed.stderr.strip() or completed.stdout.strip()}")

    json_report = output_prefix.with_suffix(".json")
    markdown_report = output_prefix.with_suffix(".md")
    require(json_report.exists(), "missing full regression json report")
    require(markdown_report.exists(), "missing full regression markdown report")

    schema = load_json(SCHEMA_PATH)
    report = load_json(json_report)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(report)

    require(report["stage"] == "full", "unexpected regression stage")
    require(report["execution_mode"] == "dry-run", "unexpected execution mode")
    require(report["overall_status"] == "planned", "dry-run report should be planned")
    require(report["step_counts"]["planned"] == len(report["steps"]), "expected every dry-run step to be planned")
    require(all(step["status"] == "planned" for step in report["steps"]), "dry-run steps should all be planned")
    require(any(step["name"] == "CI artifact governance smoke" for step in report["steps"]), "missing CI artifact governance step")
    require(any(step["name"] == "Build default Tier1 hardware evidence" for step in report["steps"]), "missing default Tier1 hardware evidence step")
    require(any(step["name"] == "Audit evidence export smoke" for step in report["steps"]), "missing audit evidence export step")
    require(any(step["name"] == "Run full system delivery validation" for step in report["steps"]), "missing system delivery validation step")
    require(any(step["name"] == "Build governance evidence index" for step in report["steps"]), "missing governance evidence index step")
    require(any(step["name"] == "Run release gate" for step in report["steps"]), "missing release gate step")
    require("AIOS Full Regression Report" in markdown_report.read_text(encoding=UTF8), "markdown report title missing")

    print(
        json.dumps(
            {
                "overall_status": "passed",
                "json_report": str(json_report),
                "markdown_report": str(markdown_report),
                "planned_steps": report["step_counts"]["planned"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
