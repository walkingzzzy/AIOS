#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "aios" / "observability" / "schemas"
OVERLAY_SCHEMA_DIR = (
    ROOT
    / "aios"
    / "image"
    / "mkosi.extra"
    / "usr"
    / "share"
    / "aios"
    / "schemas"
    / "observability"
)
SAMPLE_DIR = ROOT / "aios" / "observability" / "samples"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "observability-schema-validation-report"
UTF8 = "utf-8"

EXPECTED_SCHEMAS = {
    "audit-event.schema.json": "audit-event.sample.json",
    "audit-evidence-report.schema.json": "audit-evidence-report.sample.json",
    "trace-event.schema.json": "trace-event.sample.json",
    "diagnostic-bundle.schema.json": "diagnostic-bundle.sample.json",
    "health-event.schema.json": "health-event.sample.json",
    "recovery-evidence.schema.json": "recovery-evidence.sample.json",
    "validation-report.schema.json": "validation-report.sample.json",
    "evidence-index.schema.json": "evidence-index.sample.json",
    "release-gate-report.schema.json": "release-gate-report.sample.json",
    "full-regression-report.schema.json": "full-regression-report.sample.json",
    "cross-service-correlation-report.schema.json": "cross-service-correlation-report.sample.json",
    "cross-service-health-report.schema.json": "cross-service-health-report.sample.json",
}

CORRELATION_REQUIREMENTS = {
    "audit-event.schema.json": ["session_id", "task_id", "approval_id", "provider_id", "image_id", "artifact_path"],
    "trace-event.schema.json": ["session_id", "task_id", "provider_id", "image_id", "artifact_path"],
    "diagnostic-bundle.schema.json": ["service_id", "update_id", "boot_id", "image_id", "artifact_path"],
    "health-event.schema.json": ["service_id", "update_id", "boot_id", "image_id", "artifact_path", "runtime_service_id", "provider_status", "backend_id"],
    "recovery-evidence.schema.json": ["service_id", "update_id", "boot_id", "image_id", "artifact_path"],
}

OPTIONAL_ARTIFACT_VALIDATIONS = {
    "audit-evidence-report.schema.json": ROOT / "out" / "validation" / "audit-evidence-report.json",
    "validation-report.schema.json": ROOT / "out" / "validation" / "system-delivery-validation-report.json",
    "evidence-index.schema.json": ROOT / "out" / "validation" / "system-delivery-validation-evidence-index.json",
    "release-gate-report.schema.json": ROOT / "out" / "validation" / "release-gate-report.json",
    "full-regression-report.schema.json": ROOT / "out" / "validation" / "full-regression-report.json",
    "cross-service-correlation-report.schema.json": ROOT / "out" / "validation" / "cross-service-correlation-report.json",
    "cross-service-health-report.schema.json": ROOT / "out" / "validation" / "cross-service-health-report.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AIOS observability schemas and sample payloads")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help="Output prefix for the generated .json and .md reports",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding=UTF8))


def result(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def validate_schema(schema_path: Path) -> dict[str, str]:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    return result(schema_path.name, "passed", "schema is valid")


def validate_sample(schema_path: Path, sample_path: Path) -> dict[str, str]:
    schema = load_json(schema_path)
    sample = load_json(sample_path)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(sample)
    return result(sample_path.name, "passed", f"sample matches {schema_path.name}")


def validate_overlay_sync(schema_path: Path) -> dict[str, str]:
    overlay_path = OVERLAY_SCHEMA_DIR / schema_path.name
    if not overlay_path.exists():
        raise RuntimeError(f"overlay schema missing: {overlay_path}")
    if schema_path.read_text(encoding=UTF8) != overlay_path.read_text(encoding=UTF8):
        raise RuntimeError(f"overlay schema out of sync: {schema_path} != {overlay_path}")
    return result(
        f"{schema_path.name}:overlay-sync",
        "passed",
        f"overlay schema matches source: {overlay_path}",
    )


def validate_correlation_fields(schema_path: Path) -> dict[str, str]:
    expected_fields = CORRELATION_REQUIREMENTS.get(schema_path.name)
    if not expected_fields:
        return result(f"{schema_path.name}:correlation-fields", "passed", "no extra correlation policy for this schema")
    schema = load_json(schema_path)
    properties = schema.get("properties", {})
    missing = [field for field in expected_fields if field not in properties]
    if missing:
        raise RuntimeError(f"missing correlation fields: {', '.join(missing)}")
    return result(
        f"{schema_path.name}:correlation-fields",
        "passed",
        f"contains correlation fields: {', '.join(expected_fields)}",
    )


def validate_optional_artifact(schema_path: Path) -> dict[str, str]:
    artifact_path = OPTIONAL_ARTIFACT_VALIDATIONS.get(schema_path.name)
    if artifact_path is None:
        return result(f"{schema_path.name}:artifact", "passed", "no artifact validation configured")
    if not artifact_path.exists():
        return result(f"{schema_path.name}:artifact", "skipped", f"artifact not present: {artifact_path}")
    schema = load_json(schema_path)
    sample = load_json(artifact_path)
    if isinstance(sample, dict) and set(sample.keys()) <= {"status"}:
        return result(
            f"{schema_path.name}:artifact",
            "skipped",
            f"artifact placeholder is incomplete and was ignored: {artifact_path}",
        )
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(sample)
    return result(f"{schema_path.name}:artifact", "passed", f"artifact matches schema: {artifact_path}")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Observability Schema Validation Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        "",
        "## Results",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
    ]
    for item in report["results"]:
        lines.append(f"| `{item['name']}` | `{item['status']}` | {item['detail']} |")
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding=UTF8)


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding=UTF8)


def main() -> int:
    args = parse_args()
    results: list[dict[str, str]] = []
    failed = False

    for schema_name, sample_name in EXPECTED_SCHEMAS.items():
        schema_path = SCHEMA_DIR / schema_name
        sample_path = SAMPLE_DIR / sample_name
        if not schema_path.exists():
            results.append(result(schema_name, "failed", "schema file missing"))
            failed = True
            continue
        if not sample_path.exists():
            results.append(result(sample_name, "failed", "sample file missing"))
            failed = True
            continue

        for validator in (
            lambda: validate_schema(schema_path),
            lambda: validate_overlay_sync(schema_path),
            lambda: validate_sample(schema_path, sample_path),
            lambda: validate_correlation_fields(schema_path),
            lambda: validate_optional_artifact(schema_path),
        ):
            try:
                results.append(validator())
            except Exception as exc:  # noqa: BLE001
                failed = True
                results.append(result(f"{schema_name}", "failed", str(exc)))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "failed" if failed else "passed",
        "results": results,
    }
    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    write_report(json_path, report)
    write_markdown(markdown_path, render_markdown(report))
    print(json.dumps({
        "overall_status": report["overall_status"],
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "results": results,
    }, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
