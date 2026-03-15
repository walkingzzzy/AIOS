#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from aios_governance_common import RELEASE_CHECKLIST, ROOT, parse_release_gate_rules, read_json


DEFAULT_VALIDATION_REPORT = ROOT / "out" / "validation" / "system-delivery-validation-report.json"
DEFAULT_EVIDENCE_INDEX = ROOT / "out" / "validation" / "governance-evidence-index.json"
DEFAULT_HEALTH_REPORT = ROOT / "out" / "validation" / "cross-service-health-report.json"
DEFAULT_HARDWARE_EVIDENCE_INDEX = ROOT / "out" / "validation" / "tier1-hardware-evidence-index.json"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "release-gate-report"
VALIDATION_REPORT_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "validation-report.schema.json"
EVIDENCE_INDEX_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "evidence-index.schema.json"
HEALTH_REPORT_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "cross-service-health-report.schema.json"
RELEASE_GATE_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "release-gate-report.schema.json"
GOVERNANCE_EVIDENCE_BUILDER = ROOT / "scripts" / "build-governance-evidence-index.py"
HARDWARE_EVIDENCE_BUILDER = ROOT / "scripts" / "build-default-hardware-evidence-index.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the AIOS release gate from machine-readable validation artifacts")
    parser.add_argument("--validation-report", type=Path, default=DEFAULT_VALIDATION_REPORT)
    parser.add_argument("--evidence-index", type=Path, default=DEFAULT_EVIDENCE_INDEX)
    parser.add_argument("--health-report", type=Path, default=DEFAULT_HEALTH_REPORT)
    parser.add_argument("--hardware-evidence-index", type=Path)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--release-checklist", type=Path, default=RELEASE_CHECKLIST)
    parser.add_argument(
        "--require-hardware-evidence",
        action="store_true",
        help="Treat missing hardware evidence index as a blocking failure",
    )
    return parser.parse_args()


def validate_json(schema_path: Path, payload_path: Path) -> None:
    schema = read_json(schema_path)
    payload = read_json(payload_path)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)


def make_check(check_id: str, status: str, blocking: bool, detail: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "blocking": blocking,
        "detail": detail,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Release Gate Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Gate status: `{report['gate_status']}`",
        f"- Validation report: `{report['validation_report']}`",
        f"- Evidence index: `{report['evidence_index']}`",
        f"- Cross-service health report: `{report['health_report']}`",
        f"- Hardware evidence index: `{report['hardware_evidence_index']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Blocking | Detail |",
        "|-------|--------|----------|--------|",
    ]
    for item in report["checks"]:
        lines.append(
            f"| `{item['check_id']}` | `{item['status']}` | `{item['blocking']}` | {item['detail']} |"
        )
    if report["warnings"]:
        lines.extend(
            [
                "",
                "## Warnings",
                "",
                *[f"- {warning}" for warning in report["warnings"]],
            ]
        )
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n")


def collect_report_checks(validation_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["check_id"]: item
        for item in validation_report.get("checks", [])
        if isinstance(item, dict) and item.get("check_id")
    }


def ensure_governance_evidence_index(path: Path) -> None:
    if path.exists():
        return
    completed = subprocess.run(
        [sys.executable, str(GOVERNANCE_EVIDENCE_BUILDER), "--output-prefix", str(path.with_suffix(""))],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"returncode={completed.returncode}"
        raise RuntimeError(f"failed to build governance evidence index: {detail}")


def ensure_default_hardware_evidence_index(path: Path) -> None:
    if path.exists():
        return
    completed = subprocess.run(
        [sys.executable, str(HARDWARE_EVIDENCE_BUILDER), "--output-dir", str(path.parent)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"returncode={completed.returncode}"
        raise RuntimeError(f"failed to build default hardware evidence index: {detail}")


def evaluate_hardware_evidence_index(path: Path) -> tuple[str, str, list[str]]:
    payload = read_json(path)
    missing: list[str] = []
    for key in ["validation_status", "summary", "artifacts"]:
        if key not in payload:
            missing.append(key)
    if missing:
        return "failed", f"hardware evidence index missing keys: {', '.join(missing)}", [str(path)]

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        return "failed", "hardware evidence summary must be an object", [str(path)]

    if payload.get("validation_status") != "passed":
        return "failed", f"hardware evidence validation_status={payload.get('validation_status')}", [str(path)]

    record_count = summary.get("record_count")
    if not isinstance(record_count, int) or record_count < 2:
        return "failed", f"hardware evidence record_count={record_count!r} < 2", [str(path)]

    nominated_machine_count = payload.get("nominated_machine_count")
    if nominated_machine_count is not None and (not isinstance(nominated_machine_count, int) or nominated_machine_count < 1):
        return "failed", f"hardware evidence nominated_machine_count={nominated_machine_count!r} < 1", [str(path)]

    detail_parts = [f"validation_status={payload.get('validation_status')}", f"record_count={record_count}"]
    baseline_kind = payload.get("baseline_kind")
    if isinstance(baseline_kind, str) and baseline_kind:
        detail_parts.append(f"baseline_kind={baseline_kind}")
    return "passed", "; ".join(detail_parts), [str(path)]


def evaluate_evidence_index_checks(
    evidence_checks: dict[str, dict[str, Any]],
    use_matrix_blocking: bool,
    warn_on_non_blocking_failures: bool,
    warnings: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if use_matrix_blocking:
        for check_id, item in sorted(evidence_checks.items()):
            blocking = bool(item.get("blocking"))
            if blocking:
                status = "passed" if item.get("status") == "passed" else "failed"
                results.append(
                    make_check(
                        check_id,
                        status,
                        True,
                        f"governance evidence status={item.get('status')}; gate={item.get('gate')}; domain={item.get('domain')}",
                    )
                )
            elif warn_on_non_blocking_failures and item.get("status") != "passed":
                warnings.append(
                    f"non-blocking governance check failed: {check_id} ({item.get('domain')})"
                )
                results.append(
                    make_check(
                        check_id,
                        "warning",
                        False,
                        f"governance evidence status={item.get('status')}; gate={item.get('gate')}; domain={item.get('domain')}",
                    )
                )
    return results


def main() -> int:
    args = parse_args()
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not args.release_checklist.exists():
        checks.append(make_check("release-checklist-exists", "failed", True, f"missing {args.release_checklist}"))
    else:
        checks.append(make_check("release-checklist-exists", "passed", True, str(args.release_checklist)))

    release_rules: dict[str, Any] | None = None
    if args.release_checklist.exists():
        try:
            release_rules = parse_release_gate_rules(args.release_checklist)
            checks.append(make_check("release-checklist-rules", "passed", True, "parsed machine-readable release gate rules"))
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("release-checklist-rules", "failed", True, str(exc)))

    validation_report = None
    evidence_index = None
    health_report = None

    if not args.validation_report.exists():
        checks.append(make_check("validation-report-exists", "failed", True, f"missing {args.validation_report}"))
    else:
        checks.append(make_check("validation-report-exists", "passed", True, str(args.validation_report)))
        try:
            validate_json(VALIDATION_REPORT_SCHEMA, args.validation_report)
            checks.append(make_check("validation-report-schema", "passed", True, "validation report matches schema"))
            validation_report = read_json(args.validation_report)
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("validation-report-schema", "failed", True, str(exc)))

    try:
        ensure_governance_evidence_index(args.evidence_index)
    except Exception as exc:  # noqa: BLE001
        checks.append(make_check("evidence-index-build", "failed", True, str(exc)))

    if not args.evidence_index.exists():
        checks.append(make_check("evidence-index-exists", "failed", True, f"missing {args.evidence_index}"))
    else:
        checks.append(make_check("evidence-index-exists", "passed", True, str(args.evidence_index)))
        try:
            validate_json(EVIDENCE_INDEX_SCHEMA, args.evidence_index)
            checks.append(make_check("evidence-index-schema", "passed", True, "evidence index matches schema"))
            evidence_index = read_json(args.evidence_index)
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("evidence-index-schema", "failed", True, str(exc)))

    if not args.health_report.exists():
        checks.append(make_check("health-report-exists", "failed", True, f"missing {args.health_report}"))
    else:
        checks.append(make_check("health-report-exists", "passed", True, str(args.health_report)))
        try:
            validate_json(HEALTH_REPORT_SCHEMA, args.health_report)
            checks.append(make_check("health-report-schema", "passed", True, "cross-service health report matches schema"))
            health_report = read_json(args.health_report)
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("health-report-schema", "failed", True, str(exc)))

    if validation_report is None:
        checks.append(make_check("validation-suite-report", "failed", True, "validation report could not be parsed"))

    if evidence_index is not None:
        if evidence_index.get("validation_status") == "passed":
            checks.append(make_check("governance-evidence-status", "passed", True, "governance evidence index validation_status=passed"))
        else:
            checks.append(make_check("governance-evidence-status", "failed", True, f"governance evidence index validation_status={evidence_index.get('validation_status')}"))

        evidence_checks = collect_report_checks(evidence_index)
        release_gate_rules = release_rules.get("release_gate", {}) if isinstance(release_rules, dict) else {}
        checks.extend(
            evaluate_evidence_index_checks(
                evidence_checks,
                bool(release_gate_rules.get("use_matrix_blocking", True)),
                bool(release_gate_rules.get("warn_on_non_blocking_failures", True)),
                warnings,
            )
        )

        required_coverage_domains = release_rules.get("required_coverage_domains", []) if isinstance(release_rules, dict) else []
        if required_coverage_domains:
            coverage_domains = sorted(
                {
                    str(domain)
                    for item in evidence_index.get("checks", [])
                    if isinstance(item, dict)
                    for domain in item.get("coverage_domains", [item.get("domain")])
                    if isinstance(domain, str) and domain
                }
            )
            missing_coverage = sorted(set(required_coverage_domains) - set(coverage_domains))
            if missing_coverage:
                checks.append(
                    make_check(
                        "coverage-domain-governance",
                        "failed",
                        True,
                        f"missing coverage domains: {', '.join(missing_coverage)}",
                    )
                )
            else:
                checks.append(
                    make_check(
                        "coverage-domain-governance",
                        "passed",
                        True,
                        f"covered domains: {', '.join(coverage_domains)}",
                    )
                )

    if health_report is not None:
        failed_checks = health_report.get("summary", {}).get("failed_checks", [])
        if health_report.get("overall_status") == "passed":
            checks.append(make_check("cross-service-health-export", "passed", True, "health report overall_status=passed"))
        else:
            detail = "health report overall_status=failed"
            if failed_checks:
                detail += f"; failed checks={', '.join(str(item) for item in failed_checks)}"
            checks.append(make_check("cross-service-health-export", "failed", True, detail))
        for item in health_report.get("warnings", []):
            warnings.append(f"cross-service health report: {item}")
        required_health_component_kinds = release_rules.get("required_health_component_kinds", []) if isinstance(release_rules, dict) else []
        if required_health_component_kinds:
            component_kinds = health_report.get("summary", {}).get("component_kinds", [])
            missing = sorted(set(required_health_component_kinds) - set(component_kinds))
            if missing:
                checks.append(
                    make_check(
                        "cross-service-health-coverage",
                        "failed",
                        True,
                        f"missing component kinds: {', '.join(missing)}",
                    )
                )
            else:
                checks.append(
                    make_check(
                        "cross-service-health-coverage",
                        "passed",
                        True,
                        f"covered component kinds: {', '.join(component_kinds)}",
                    )
                )

    hardware_rules = release_rules.get("hardware_evidence", {}) if isinstance(release_rules, dict) else {}
    hardware_required = args.require_hardware_evidence or bool(hardware_rules.get("required_by_default", False))
    hardware_evidence_index = args.hardware_evidence_index
    hardware_check_recorded = False
    if hardware_evidence_index is None and (hardware_required or DEFAULT_HARDWARE_EVIDENCE_INDEX.exists()):
        hardware_evidence_index = DEFAULT_HARDWARE_EVIDENCE_INDEX

    if hardware_evidence_index == DEFAULT_HARDWARE_EVIDENCE_INDEX:
        try:
            ensure_default_hardware_evidence_index(hardware_evidence_index)
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            if hardware_required:
                checks.append(make_check("hardware-evidence-index", "failed", True, detail))
            else:
                warnings.append(detail)
                checks.append(make_check("hardware-evidence-index", "warning", False, detail))
            hardware_check_recorded = True
            hardware_evidence_index = None

    if not hardware_check_recorded and (hardware_evidence_index is None or not hardware_evidence_index.exists()):
        detail = "hardware evidence index not provided"
        if hardware_required:
            checks.append(make_check("hardware-evidence-index", "failed", True, detail))
        else:
            warnings.append(detail)
            checks.append(make_check("hardware-evidence-index", "warning", False, detail))
    elif not hardware_check_recorded:
        try:
            status, detail, _artifacts = evaluate_hardware_evidence_index(hardware_evidence_index)
            checks.append(make_check("hardware-evidence-index", status, hardware_required, detail))
            payload = read_json(hardware_evidence_index)
            if payload.get("baseline_kind") == "synthetic-tier1-release-gate":
                warnings.append("hardware evidence gate is satisfied by the synthetic Tier 1 baseline; attach real-machine sign-off separately")
        except Exception as exc:  # noqa: BLE001
            checks.append(make_check("hardware-evidence-index", "failed", hardware_required, str(exc)))

    blocking_failures = [
        item["check_id"]
        for item in checks
        if item["blocking"] and item["status"] != "passed"
    ]
    gate_status = "failed" if blocking_failures else "passed"
    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ROOT),
        "overall_status": gate_status,
        "gate_status": gate_status,
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "release_checklist": str(args.release_checklist),
        "validation_report": str(args.validation_report),
        "evidence_index": str(args.evidence_index),
        "health_report": str(args.health_report),
        "hardware_evidence_index": None if hardware_evidence_index is None else str(hardware_evidence_index),
        "governance_rules": release_rules or {},
        "checks": checks,
        "blocking_checks": blocking_failures,
        "warnings": warnings,
    }

    write_json(json_path, report)
    write_markdown(markdown_path, render_markdown(report))
    validate_json(RELEASE_GATE_SCHEMA, json_path)
    print(
        json.dumps(
            {
                "gate_status": gate_status,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "blocking_checks": blocking_failures,
                "warnings": warnings,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if blocking_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
