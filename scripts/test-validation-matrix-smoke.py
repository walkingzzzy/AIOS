#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "tests" / "observability" / "validation-matrix.yaml"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "validation-matrix-report"
SYSTEM_VALIDATION_REPORT = ROOT / "out" / "validation" / "system-delivery-validation-report.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "aios-ci.yml"
REQUIRED_WORKFLOW_JOBS = {"validate", "system-validation", "nightly-container-delivery"}
REQUIRED_COVERAGE_DOMAINS = {
    "observability-governance",
    "control-plane",
    "runtime",
    "provider",
    "shell",
    "device",
    "compat",
    "image-recovery-update",
    "hardware-evidence",
    "release-governance",
}
STATUS_SOURCE_FIELDS = {
    "report-status": {"report_path", "field", "expected_values"},
    "system-validation-check": {"check_id"},
    "health-check": {"check_id"},
    "health-group": {"check_ids"},
    "provider-health": {"provider_id"},
    "provider-group": {"provider_ids"},
    "artifact-exists": {"paths"},
    "json-required-keys": {"path", "required_keys"},
    "json-conditions": {"path", "conditions"},
    "checklist-rules": set(),
}

REQUIRED_ENTRY_FIELDS = {
    "check_id": str,
    "owner": str,
    "gate": str,
    "domain": str,
    "blocking": bool,
    "command": str,
    "artifacts": list,
    "source_paths": list,
    "failure_symptom": str,
    "triage": str,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the AIOS machine-readable validation matrix")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def result(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def normalize_command(command: str) -> str:
    return " ".join(command.strip().split())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Validation Matrix Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Matrix: `{report['matrix_path']}`",
        "",
        "## Results",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
    ]
    for item in report["results"]:
        lines.append(f"| `{item['name']}` | `{item['status']}` | {item['detail']} |")
    return "\n".join(lines)


def validate_entry(entry: dict[str, Any], known_ids: set[str]) -> list[dict[str, str]]:
    check_id = entry.get("check_id", "<missing>")
    results: list[dict[str, str]] = []

    for field, expected_type in REQUIRED_ENTRY_FIELDS.items():
        if field not in entry:
            raise RuntimeError(f"{check_id}: missing required field `{field}`")
        if not isinstance(entry[field], expected_type):
            raise RuntimeError(
                f"{check_id}: field `{field}` must be {expected_type.__name__}"
            )

    if check_id in known_ids:
        raise RuntimeError(f"duplicate check_id: {check_id}")
    known_ids.add(check_id)

    for field in ("artifacts", "source_paths"):
        if not entry[field]:
            raise RuntimeError(f"{check_id}: `{field}` must not be empty")
        if not all(isinstance(item, str) and item for item in entry[field]):
            raise RuntimeError(f"{check_id}: `{field}` entries must be non-empty strings")

    for source_path in entry["source_paths"]:
        if not (ROOT / source_path).exists():
            raise RuntimeError(f"{check_id}: source path missing: {source_path}")

    triage_path = ROOT / entry["triage"]
    if not triage_path.exists():
        raise RuntimeError(f"{check_id}: triage path missing: {entry['triage']}")

    workflow_jobs = entry.get("workflow_jobs", [])
    if workflow_jobs:
        if not isinstance(workflow_jobs, list) or not all(isinstance(item, str) and item for item in workflow_jobs):
            raise RuntimeError(f"{check_id}: `workflow_jobs` must be a list of non-empty strings")

    coverage_domains = entry.get("coverage_domains", [])
    if coverage_domains:
        if not isinstance(coverage_domains, list) or not all(isinstance(item, str) and item for item in coverage_domains):
            raise RuntimeError(f"{check_id}: `coverage_domains` must be a list of non-empty strings")

    status_source = entry.get("status_source")
    if entry["blocking"] and not isinstance(status_source, dict):
        raise RuntimeError(f"{check_id}: blocking checks must define a `status_source` mapping")
    if status_source is not None:
        if not isinstance(status_source, dict):
            raise RuntimeError(f"{check_id}: `status_source` must be a mapping")
        kind = status_source.get("kind")
        if kind not in STATUS_SOURCE_FIELDS:
            raise RuntimeError(f"{check_id}: unsupported status_source kind `{kind}`")
        missing_fields = sorted(
            field for field in STATUS_SOURCE_FIELDS[kind] if field not in status_source
        )
        if missing_fields:
            raise RuntimeError(
                f"{check_id}: status_source `{kind}` missing fields: {', '.join(missing_fields)}"
            )

    results.append(
        result(
            check_id,
            "passed",
            f"gate={entry['gate']}, domain={entry['domain']}, owner={entry['owner']}, symptom={entry['failure_symptom']}",
        )
    )
    return results


def extract_workflow_commands(job: dict[str, Any]) -> set[str]:
    commands: set[str] = set()
    for step in job.get("steps", []):
        run = step.get("run")
        if not isinstance(run, str):
            continue
        for line in run.splitlines():
            stripped = line.strip()
            if not stripped or stripped.endswith("\\"):
                continue
            commands.add(normalize_command(stripped))
    return commands


def validate_workflow_alignment(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not WORKFLOW_PATH.exists():
        raise RuntimeError(f"workflow file missing: {WORKFLOW_PATH}")

    workflow = load_yaml(WORKFLOW_PATH)
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        raise RuntimeError("workflow does not contain a jobs mapping")

    missing_jobs = sorted(REQUIRED_WORKFLOW_JOBS - set(jobs))
    if missing_jobs:
        raise RuntimeError(f"workflow missing required jobs: {', '.join(missing_jobs)}")

    job_commands = {job_name: extract_workflow_commands(job) for job_name, job in jobs.items() if isinstance(job, dict)}
    tracked_jobs = {job: 0 for job in REQUIRED_WORKFLOW_JOBS}
    results: list[dict[str, str]] = []
    for entry in entries:
        workflow_jobs = entry.get("workflow_jobs", [])
        if not workflow_jobs:
            continue
        command = normalize_command(entry["command"])
        for job_name in workflow_jobs:
            if job_name not in job_commands:
                raise RuntimeError(f"{entry['check_id']}: workflow job missing: {job_name}")
            if command not in job_commands[job_name]:
                raise RuntimeError(
                    f"{entry['check_id']}: command missing from workflow job `{job_name}`: {entry['command']}"
                )
            tracked_jobs[job_name] = tracked_jobs.get(job_name, 0) + 1
        results.append(
            result(
                f"{entry['check_id']}:workflow",
                "passed",
                f"mapped to jobs: {', '.join(workflow_jobs)}",
            )
        )

    uncovered_jobs = sorted(job for job, count in tracked_jobs.items() if count == 0)
    if uncovered_jobs:
        raise RuntimeError(f"matrix has no workflow-linked entries for jobs: {', '.join(uncovered_jobs)}")
    results.append(
        result(
            "workflow-job-coverage",
            "passed",
            f"tracked jobs covered: {', '.join(sorted(REQUIRED_WORKFLOW_JOBS))}",
        )
    )
    return results


def validate_coverage_domains(entries: list[dict[str, Any]]) -> dict[str, str]:
    coverage = {
        item
        for entry in entries
        for item in entry.get("coverage_domains", [entry["domain"]])
        if isinstance(item, str) and item
    }
    missing = sorted(REQUIRED_COVERAGE_DOMAINS - coverage)
    if missing:
        raise RuntimeError(f"matrix missing coverage domains: {', '.join(missing)}")
    return result(
        "coverage-domain-alignment",
        "passed",
        f"matrix covers domains: {', '.join(sorted(coverage))}",
    )


def validate_system_validation_alignment(entries: list[dict[str, Any]]) -> dict[str, str]:
    matrix_ids = {
        entry["check_id"]
        for entry in entries
        if isinstance(entry.get("status_source"), dict)
        and entry["status_source"].get("kind") == "system-validation-check"
    }
    if not SYSTEM_VALIDATION_REPORT.exists():
        return result(
            "system-validation-alignment",
            "skipped",
            f"report not present: {SYSTEM_VALIDATION_REPORT}",
        )

    report = json.loads(SYSTEM_VALIDATION_REPORT.read_text())
    report_ids = {item["check_id"] for item in report.get("checks", [])}
    missing = sorted(report_ids - matrix_ids)
    extra = sorted(matrix_ids - report_ids)
    if missing or extra:
        detail = []
        if missing:
            detail.append(f"missing matrix entries for report checks: {', '.join(missing)}")
        if extra:
            detail.append(f"matrix contains system-validation checks not in report: {', '.join(extra)}")
        raise RuntimeError("; ".join(detail))
    return result(
        "system-validation-alignment",
        "passed",
        f"matrix covers {len(report_ids)} system-validation checks",
    )


def main() -> int:
    args = parse_args()
    results: list[dict[str, str]] = []
    failed = False

    if not args.matrix.exists():
        raise SystemExit(f"missing validation matrix: {args.matrix}")

    payload = load_yaml(args.matrix)
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("validation matrix must contain a non-empty `entries` list")

    known_ids: set[str] = set()
    for entry in entries:
        try:
            results.extend(validate_entry(entry, known_ids))
        except Exception as exc:  # noqa: BLE001
            failed = True
            results.append(result(entry.get("check_id", "<missing>"), "failed", str(exc)))

    try:
        results.extend(validate_workflow_alignment(entries))
    except Exception as exc:  # noqa: BLE001
        failed = True
        results.append(result("workflow-alignment", "failed", str(exc)))

    try:
        results.append(validate_coverage_domains(entries))
    except Exception as exc:  # noqa: BLE001
        failed = True
        results.append(result("coverage-domain-alignment", "failed", str(exc)))

    try:
        results.append(validate_system_validation_alignment(entries))
    except Exception as exc:  # noqa: BLE001
        failed = True
        results.append(result("system-validation-alignment", "failed", str(exc)))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "failed" if failed else "passed",
        "matrix_path": str(args.matrix),
        "entry_count": len(entries),
        "results": results,
    }
    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    write_json(json_path, report)
    write_markdown(markdown_path, render_markdown(report))
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "entry_count": len(entries),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
