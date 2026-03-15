#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from aios_governance_common import (
    RELEASE_CHECKLIST,
    ROOT,
    get_nested_field,
    parse_release_gate_rules,
    read_json,
)


MATRIX_PATH = ROOT / "tests" / "observability" / "validation-matrix.yaml"
EVIDENCE_INDEX_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "evidence-index.schema.json"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "governance-evidence-index"
DEFAULT_REPORTS = {
    "observability_schema": ROOT / "out" / "validation" / "observability-schema-validation-report.json",
    "validation_matrix": ROOT / "out" / "validation" / "validation-matrix-report.json",
    "cross_service_correlation": ROOT / "out" / "validation" / "cross-service-correlation-report.json",
    "cross_service_health": ROOT / "out" / "validation" / "cross-service-health-report.json",
    "system_validation": ROOT / "out" / "validation" / "system-delivery-validation-report.json",
    "full_regression": ROOT / "out" / "validation" / "full-regression-report.json",
}
DEFAULT_REQUIRED_MANIFEST_KEYS = [
    "generated_at",
    "schema_version",
    "rootfs_overlay",
    "firstboot",
    "shell",
    "recovery",
    "installer",
    "schemas",
    "files",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the AIOS governance evidence index from validation artifacts")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--release-checklist", type=Path, default=RELEASE_CHECKLIST)
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n")


def validate_json(schema_path: Path, payload_path: Path) -> None:
    schema = read_json(schema_path)
    payload = read_json(payload_path)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)


def classify_artifact(path: str) -> str:
    lowered = path.lower()
    suffix = Path(path).suffix.lower()
    if suffix == ".log":
        return "logs"
    if suffix in {".raw", ".img", ".qcow2"}:
        return "images"
    if suffix in {".py", ".sh"}:
        return "scripts"
    if suffix in {".json", ".yaml", ".yml", ".conf", ".service", ".sock"} or "manifest" in lowered:
        return "configs"
    return "other"


def normalize_report_status(value: Any, expected_values: list[str] | None = None) -> tuple[str, str]:
    expected = expected_values or ["passed"]
    normalized = str(value)
    if normalized in expected:
        return "passed", f"field matched expected values: {normalized}"
    return "failed", f"field value `{normalized}` not in expected set: {', '.join(expected)}"


def load_report(report_cache: dict[str, Any], path: Path) -> Any:
    key = str(path)
    if key not in report_cache:
        report_cache[key] = read_json(path) if path.exists() else None
    return report_cache[key]


def evaluate_report_status(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    path = resolve_path(status_source["report_path"])
    report = load_report(report_cache, path)
    if report is None:
        return "failed", f"missing report: {path}", [str(path)]
    field = str(status_source.get("field") or "overall_status")
    value = get_nested_field(report, field)
    if value is None:
        return "failed", f"field `{field}` missing in report {path}", [str(path)]
    status, detail = normalize_report_status(value, status_source.get("expected_values"))
    return status, detail, [str(path)]


def find_report_check(report: dict[str, Any], check_id: str) -> dict[str, Any] | None:
    for item in report.get("checks", []):
        if isinstance(item, dict) and item.get("check_id") == check_id:
            return item
    return None


def evaluate_system_validation_check(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    path = resolve_path(status_source.get("report_path") or DEFAULT_REPORTS["system_validation"])
    report = load_report(report_cache, path)
    if report is None:
        return "failed", f"missing validation report: {path}", [str(path)]
    item = find_report_check(report, str(status_source["check_id"]))
    if item is None:
        return "failed", f"check `{status_source['check_id']}` missing from {path}", [str(path)]
    status = "passed" if item.get("status") == "passed" else "failed"
    return status, f"validation report status={item.get('status')}", [str(path), *item.get("evidence_paths", [])]


def load_health_report(report_cache: dict[str, Any], path_override: str | None = None) -> tuple[dict[str, Any] | None, Path]:
    path = resolve_path(path_override or DEFAULT_REPORTS["cross_service_health"])
    return load_report(report_cache, path), path


def evaluate_health_check(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    report, path = load_health_report(report_cache, status_source.get("report_path"))
    if report is None:
        return "failed", f"missing health report: {path}", [str(path)]
    item = find_report_check(report, str(status_source["check_id"]))
    if item is None:
        return "failed", f"health check `{status_source['check_id']}` missing from {path}", [str(path)]
    status = "passed" if item.get("status") == "passed" else "failed"
    return status, f"health report status={item.get('status')}", [str(path), *item.get("artifact_paths", [])]


def evaluate_health_group(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    report, path = load_health_report(report_cache, status_source.get("report_path"))
    if report is None:
        return "failed", f"missing health report: {path}", [str(path)]

    missing: list[str] = []
    failing: list[str] = []
    artifacts = [str(path)]
    for check_id in status_source["check_ids"]:
        item = find_report_check(report, str(check_id))
        if item is None:
            missing.append(str(check_id))
            continue
        artifacts.extend(item.get("artifact_paths", []))
        if item.get("status") != "passed":
            failing.append(f"{check_id}={item.get('status')}")
    if missing or failing:
        detail_parts = []
        if missing:
            detail_parts.append(f"missing checks: {', '.join(missing)}")
        if failing:
            detail_parts.append(f"failing checks: {', '.join(failing)}")
        return "failed", "; ".join(detail_parts), artifacts
    return "passed", f"group passed: {', '.join(status_source['check_ids'])}", artifacts


def iter_health_events_for_provider(report: dict[str, Any], provider_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in report.get("events", [])
        if isinstance(item, dict) and item.get("provider_id") == provider_id
    ]


def evaluate_provider_health(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    report, path = load_health_report(report_cache, status_source.get("report_path"))
    if report is None:
        return "failed", f"missing health report: {path}", [str(path)]
    provider_id = str(status_source["provider_id"])
    acceptable_statuses = status_source.get("acceptable_statuses") or ["ready", "idle"]
    events = iter_health_events_for_provider(report, provider_id)
    if not events:
        return "failed", f"provider `{provider_id}` missing from health report", [str(path)]
    statuses = sorted({str(item.get("overall_status")) for item in events if item.get("overall_status")})
    status = "passed" if all(item in acceptable_statuses for item in statuses) else "failed"
    artifacts = [str(path)]
    artifacts.extend(
        [
            str(item.get("artifact_path"))
            for item in events
            if isinstance(item.get("artifact_path"), str) and item.get("artifact_path")
        ]
    )
    return status, f"provider statuses={', '.join(statuses)}", artifacts


def evaluate_provider_group(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    acceptable_statuses = status_source.get("acceptable_statuses") or ["ready", "idle"]
    details: list[str] = []
    artifacts: list[str] = []
    failures: list[str] = []
    for provider_id in status_source["provider_ids"]:
        status, detail, event_artifacts = evaluate_provider_health(
            {
                "provider_id": provider_id,
                "report_path": status_source.get("report_path"),
                "acceptable_statuses": acceptable_statuses,
            },
            report_cache,
        )
        details.append(f"{provider_id}: {detail}")
        artifacts.extend(event_artifacts)
        if status != "passed":
            failures.append(provider_id)
    return (
        "failed" if failures else "passed",
        "; ".join(details),
        artifacts,
    )


def evaluate_artifact_exists(status_source: dict[str, Any]) -> tuple[str, str, list[str]]:
    paths = [resolve_path(item) for item in status_source["paths"]]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        return "failed", f"missing artifacts: {', '.join(missing)}", [str(path) for path in paths]
    return "passed", f"artifacts present: {', '.join(str(path) for path in paths)}", [str(path) for path in paths]


def evaluate_json_required_keys(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    path = resolve_path(status_source["path"])
    payload = load_report(report_cache, path)
    if payload is None:
        return "failed", f"missing json artifact: {path}", [str(path)]
    missing = [key for key in status_source.get("required_keys") or DEFAULT_REQUIRED_MANIFEST_KEYS if key not in payload]
    if missing:
        return "failed", f"missing keys: {', '.join(missing)}", [str(path)]
    return "passed", f"required keys present in {path.name}", [str(path)]


def evaluate_json_conditions(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    path = resolve_path(status_source["path"])
    payload = load_report(report_cache, path)
    if payload is None:
        return "failed", f"missing json artifact: {path}", [str(path)]

    failures: list[str] = []
    for condition in status_source["conditions"]:
        field = str(condition["field"])
        value = get_nested_field(payload, field)
        if condition.get("non_empty"):
            if value in (None, "", [], {}):
                failures.append(f"{field} is empty")
        if "equals" in condition and value != condition["equals"]:
            failures.append(f"{field}={value!r} != {condition['equals']!r}")
        if "minimum" in condition:
            if not isinstance(value, (int, float)) or value < condition["minimum"]:
                failures.append(f"{field}={value!r} < {condition['minimum']}")
        if "includes_all" in condition:
            if not isinstance(value, list):
                failures.append(f"{field} is not a list")
            else:
                missing = [item for item in condition["includes_all"] if item not in value]
                if missing:
                    failures.append(f"{field} missing values: {', '.join(str(item) for item in missing)}")
    if failures:
        return "failed", "; ".join(failures), [str(path)]
    return "passed", f"conditions satisfied for {path.name}", [str(path)]


def evaluate_checklist_rules(status_source: dict[str, Any]) -> tuple[str, str, list[str]]:
    checklist_path = resolve_path(status_source.get("checklist_path") or RELEASE_CHECKLIST)
    rules = parse_release_gate_rules(checklist_path)
    required_keys = ["release_gate", "required_coverage_domains", "required_health_component_kinds"]
    missing = [key for key in required_keys if key not in rules]
    if missing:
        return "failed", f"missing rule keys: {', '.join(missing)}", [str(checklist_path)]
    return "passed", f"parsed release gate rules from {checklist_path.name}", [str(checklist_path)]


def evaluate_status_source(status_source: dict[str, Any], report_cache: dict[str, Any]) -> tuple[str, str, list[str]]:
    kind = status_source["kind"]
    if kind == "report-status":
        return evaluate_report_status(status_source, report_cache)
    if kind == "system-validation-check":
        return evaluate_system_validation_check(status_source, report_cache)
    if kind == "health-check":
        return evaluate_health_check(status_source, report_cache)
    if kind == "health-group":
        return evaluate_health_group(status_source, report_cache)
    if kind == "provider-health":
        return evaluate_provider_health(status_source, report_cache)
    if kind == "provider-group":
        return evaluate_provider_group(status_source, report_cache)
    if kind == "artifact-exists":
        return evaluate_artifact_exists(status_source)
    if kind == "json-required-keys":
        return evaluate_json_required_keys(status_source, report_cache)
    if kind == "json-conditions":
        return evaluate_json_conditions(status_source, report_cache)
    if kind == "checklist-rules":
        return evaluate_checklist_rules(status_source)
    raise RuntimeError(f"unsupported status_source kind: {kind}")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Governance Evidence Index",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Validation status: `{report['validation_status']}`",
        f"- Workspace: `{report['workspace']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Blocking | Gate | Domain | Detail |",
        "|-------|--------|----------|------|--------|--------|",
    ]
    for item in report["checks"]:
        lines.append(
            "| `{check_id}` | `{status}` | `{blocking}` | `{gate}` | `{domain}` | {detail} |".format(
                check_id=item["check_id"],
                status=item["status"],
                blocking=item["blocking"],
                gate=item["gate"],
                domain=item["domain"],
                detail=item["detail"],
            )
        )
    if report.get("failing_checks"):
        lines.extend(["", "## Failing Checks", ""])
        lines.extend(f"- `{item}`" for item in report["failing_checks"])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    payload = load_yaml(args.matrix)
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("validation matrix must contain a non-empty entries list")

    report_cache: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []
    status_counts = {"passed": 0, "failed": 0}
    artifacts = {"logs": [], "images": [], "scripts": [], "configs": [], "other": []}
    unique_artifacts: set[str] = set()

    for entry in entries:
        status_source = entry.get("status_source")
        if not isinstance(status_source, dict):
            continue
        status, detail, derived_artifacts = evaluate_status_source(status_source, report_cache)
        status_counts[status] += 1
        evidence_paths = list(dict.fromkeys([*entry.get("artifacts", []), *derived_artifacts]))
        for artifact_path in evidence_paths:
            if artifact_path in unique_artifacts:
                continue
            unique_artifacts.add(artifact_path)
            artifacts[classify_artifact(artifact_path)].append(artifact_path)
        checks.append(
            {
                "check_id": entry["check_id"],
                "summary": entry["failure_symptom"],
                "status": status,
                "evidence_paths": evidence_paths,
                "owner": entry["owner"],
                "gate": entry["gate"],
                "domain": entry["domain"],
                "blocking": entry["blocking"],
                "triage": entry["triage"],
                "command": entry["command"],
                "workflow_jobs": entry.get("workflow_jobs", []),
                "coverage_domains": entry.get("coverage_domains", []),
                "detail": detail,
                "status_source": status_source,
            }
        )

    overall_status = "passed" if status_counts["failed"] == 0 else "failed"
    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    report = {
        "index_id": "governance-evidence-index",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validation_kind": "governance",
        "validation_status": overall_status,
        "workspace": str(ROOT),
        "report_paths": {
            "json_report": str(json_path),
            "markdown_report": str(markdown_path),
        },
        "status_counts": status_counts,
        "artifacts": artifacts,
        "checks": checks,
        "failing_checks": [item["check_id"] for item in checks if item["status"] != "passed"],
        "matrix_path": str(args.matrix),
        "release_checklist": str(args.release_checklist),
        "source_reports": {name: str(path) for name, path in DEFAULT_REPORTS.items()},
    }
    write_json(json_path, report)
    write_markdown(markdown_path, render_markdown(report))
    validate_json(EVIDENCE_INDEX_SCHEMA, json_path)
    print(
        json.dumps(
            {
                "validation_status": overall_status,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "check_count": len(checks),
                "failing_checks": report["failing_checks"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if overall_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
