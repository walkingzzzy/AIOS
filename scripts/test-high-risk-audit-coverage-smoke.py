#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "tests" / "observability" / "high-risk-audit-coverage.yaml"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "high-risk-audit-coverage-report"

COMMON_ENTRY_FIELDS = {
    "entry_id": str,
    "entry_type": str,
    "owner": str,
    "coverage_mode": str,
    "code_paths": list,
    "validation_commands": list,
    "required_patterns": list,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate AIOS high-risk capability and update/recovery audit coverage"
    )
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def result(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


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


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS High-risk Audit Coverage Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Matrix: `{report['matrix_path']}`",
        f"- Source catalog: `{report['source_capability_catalog']}`",
        f"- Image catalog: `{report['image_capability_catalog']}`",
        "",
        "## Summary",
        "",
        f"- High-risk capabilities in catalog: `{report['summary']['high_risk_capability_count']}`",
        f"- Covered high-risk capabilities: `{report['summary']['covered_high_risk_capabilities']}`",
        f"- Required operational paths: `{report['summary']['required_operation_count']}`",
        f"- Covered operational paths: `{report['summary']['covered_operations']}`",
        "",
        "## Results",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
    ]
    for item in report["results"]:
        lines.append(f"| `{item['name']}` | `{item['status']}` | {item['detail']} |")
    return "\n".join(lines)


def load_high_risk_capabilities(path: Path) -> list[str]:
    payload = load_yaml(path)
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise RuntimeError(f"{path} must contain a non-empty `capabilities` list")
    high_risk = []
    for item in capabilities:
        if not isinstance(item, dict):
            raise RuntimeError(f"{path} contains a non-mapping capability entry")
        if item.get("risk_tier") == "high":
            capability_id = item.get("capability_id")
            if not isinstance(capability_id, str) or not capability_id:
                raise RuntimeError(f"{path} contains a high-risk capability without capability_id")
            high_risk.append(capability_id)
    return sorted(set(high_risk))


def ensure_string_list(value: Any, *, field: str, entry_id: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RuntimeError(f"{entry_id}: `{field}` must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise RuntimeError(f"{entry_id}: `{field}` entries must be non-empty strings")
    return list(value)


def command_script_paths(commands: list[str], entry_id: str) -> list[Path]:
    paths: list[Path] = []
    for command in commands:
        tokens = shlex.split(command)
        script_path: Path | None = None
        for token in tokens:
            if token.startswith("-"):
                continue
            if token.endswith((".py", ".sh")) or token.startswith(("scripts/", "aios/")):
                candidate = resolve_path(token)
                if candidate.exists():
                    script_path = candidate
                    break
        if script_path is None:
            raise RuntimeError(
                f"{entry_id}: validation command does not reference an existing script path: {command}"
            )
        paths.append(script_path)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def validate_entry(
    entry: dict[str, Any],
    high_risk_capabilities: set[str],
    required_operations: set[str],
    known_entry_ids: set[str],
    seen_capabilities: set[str],
    seen_operations: set[str],
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    entry_id = entry.get("entry_id", "<missing>")

    if entry_id in known_entry_ids:
        raise RuntimeError(f"duplicate entry_id: {entry_id}")
    known_entry_ids.add(entry_id)

    for field, expected_type in COMMON_ENTRY_FIELDS.items():
        if field not in entry:
            raise RuntimeError(f"{entry_id}: missing required field `{field}`")
        if not isinstance(entry[field], expected_type):
            raise RuntimeError(
                f"{entry_id}: field `{field}` must be {expected_type.__name__}"
            )

    entry_type = entry["entry_type"]
    if entry_type not in {"capability", "operation"}:
        raise RuntimeError(f"{entry_id}: unsupported entry_type `{entry_type}`")

    code_paths = [resolve_path(item) for item in ensure_string_list(entry["code_paths"], field="code_paths", entry_id=entry_id)]
    missing_code_paths = [str(path) for path in code_paths if not path.exists()]
    if missing_code_paths:
        raise RuntimeError(
            f"{entry_id}: code paths missing: {', '.join(missing_code_paths)}"
        )

    validation_commands = ensure_string_list(
        entry["validation_commands"], field="validation_commands", entry_id=entry_id
    )
    searchable_paths = [*code_paths, *command_script_paths(validation_commands, entry_id)]
    required_patterns = ensure_string_list(
        entry["required_patterns"], field="required_patterns", entry_id=entry_id
    )
    combined_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in searchable_paths
    )
    missing_patterns = [pattern for pattern in required_patterns if pattern not in combined_text]
    if missing_patterns:
        raise RuntimeError(
            f"{entry_id}: required patterns missing: {', '.join(missing_patterns)}"
        )

    if entry_type == "capability":
        capability_id = entry.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            raise RuntimeError(f"{entry_id}: capability entries must define `capability_id`")
        if capability_id not in high_risk_capabilities:
            raise RuntimeError(
                f"{entry_id}: capability `{capability_id}` is not a high-risk catalog entry"
            )
        if capability_id in seen_capabilities:
            raise RuntimeError(f"duplicate capability coverage entry: {capability_id}")
        seen_capabilities.add(capability_id)
        subject = capability_id
    else:
        operation_id = entry.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise RuntimeError(f"{entry_id}: operation entries must define `operation_id`")
        if required_operations and operation_id not in required_operations:
            raise RuntimeError(
                f"{entry_id}: operation `{operation_id}` is not in `required_operations`"
            )
        if operation_id in seen_operations:
            raise RuntimeError(f"duplicate operation coverage entry: {operation_id}")
        seen_operations.add(operation_id)
        subject = operation_id

    results.append(
        result(
            entry_id,
            "passed",
            f"{entry_type}={subject}; coverage={entry['coverage_mode']}; code_paths={len(code_paths)}; validations={len(validation_commands)}",
        )
    )
    return results


def main() -> int:
    args = parse_args()
    if not args.matrix.exists():
        raise SystemExit(f"missing audit coverage matrix: {args.matrix}")

    payload = load_yaml(args.matrix)
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("audit coverage matrix must contain a non-empty `entries` list")

    source_catalog = resolve_path(
        payload.get("source_capability_catalog")
        or "aios/policy/capabilities/default-capability-catalog.yaml"
    )
    image_catalog = resolve_path(
        payload.get("image_capability_catalog")
        or "aios/image/mkosi.extra/etc/aios/policy/default-capability-catalog.yaml"
    )
    required_operations = set(
        ensure_string_list(
            payload.get("required_operations", []),
            field="required_operations",
            entry_id="matrix",
        )
    )

    results: list[dict[str, str]] = []
    failed = False

    try:
        source_high_risk = load_high_risk_capabilities(source_catalog)
        results.append(
            result(
                "source-capability-catalog",
                "passed",
                f"loaded {len(source_high_risk)} high-risk capabilities",
            )
        )
    except Exception as exc:  # noqa: BLE001
        source_high_risk = []
        failed = True
        results.append(result("source-capability-catalog", "failed", str(exc)))

    try:
        image_high_risk = load_high_risk_capabilities(image_catalog)
        results.append(
            result(
                "image-capability-catalog",
                "passed",
                f"loaded {len(image_high_risk)} high-risk capabilities",
            )
        )
    except Exception as exc:  # noqa: BLE001
        image_high_risk = []
        failed = True
        results.append(result("image-capability-catalog", "failed", str(exc)))

    if source_high_risk and image_high_risk:
        missing_from_image = sorted(set(source_high_risk) - set(image_high_risk))
        missing_from_source = sorted(set(image_high_risk) - set(source_high_risk))
        if missing_from_image or missing_from_source:
            failed = True
            detail_parts = []
            if missing_from_image:
                detail_parts.append(
                    f"missing from image catalog: {', '.join(missing_from_image)}"
                )
            if missing_from_source:
                detail_parts.append(
                    f"missing from source catalog: {', '.join(missing_from_source)}"
                )
            results.append(
                result("catalog-high-risk-alignment", "failed", "; ".join(detail_parts))
            )
        else:
            results.append(
                result(
                    "catalog-high-risk-alignment",
                    "passed",
                    f"high-risk capability sets aligned: {', '.join(source_high_risk)}",
                )
            )

    known_entry_ids: set[str] = set()
    seen_capabilities: set[str] = set()
    seen_operations: set[str] = set()

    for entry in entries:
        try:
            results.extend(
                validate_entry(
                    entry,
                    set(source_high_risk),
                    required_operations,
                    known_entry_ids,
                    seen_capabilities,
                    seen_operations,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failed = True
            results.append(result(entry.get("entry_id", "<missing>"), "failed", str(exc)))

    missing_capabilities = sorted(set(source_high_risk) - seen_capabilities)
    if missing_capabilities:
        failed = True
        results.append(
            result(
                "catalog-high-risk-coverage",
                "failed",
                f"matrix missing high-risk capabilities: {', '.join(missing_capabilities)}",
            )
        )
    else:
        results.append(
            result(
                "catalog-high-risk-coverage",
                "passed",
                f"matrix covers all high-risk capabilities: {', '.join(sorted(seen_capabilities))}",
            )
        )

    missing_operations = sorted(required_operations - seen_operations)
    if missing_operations:
        failed = True
        results.append(
            result(
                "required-operation-coverage",
                "failed",
                f"matrix missing required operations: {', '.join(missing_operations)}",
            )
        )
    else:
        results.append(
            result(
                "required-operation-coverage",
                "passed",
                f"matrix covers required operations: {', '.join(sorted(seen_operations))}",
            )
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "failed" if failed else "passed",
        "matrix_path": str(args.matrix.relative_to(ROOT)),
        "source_capability_catalog": str(source_catalog.relative_to(ROOT)),
        "image_capability_catalog": str(image_catalog.relative_to(ROOT)),
        "summary": {
            "high_risk_capability_count": len(source_high_risk),
            "covered_high_risk_capabilities": len(seen_capabilities),
            "required_operation_count": len(required_operations),
            "covered_operations": len(seen_operations),
            "high_risk_capabilities": sorted(source_high_risk),
            "required_operations": sorted(required_operations),
        },
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
                "summary": report["summary"],
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
