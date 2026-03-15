#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "aios-ci.yml"
POLICY_PATH = ROOT / "tests" / "observability" / "ci-artifact-governance.yaml"
VALIDATION_REPORT_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "validation-report.schema.json"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "ci-artifact-governance-report"
COMMAND = "python3 scripts/test-ci-artifact-governance-smoke.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AIOS CI artifact governance policy against the workflow")
    parser.add_argument("--workflow", type=Path, default=WORKFLOW_PATH)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n")


def normalize_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def make_check(
    check_id: str,
    summary: str,
    status: str,
    detail: str,
    evidence_paths: list[str],
    parsed_output: Any | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "summary": summary,
        "command": COMMAND,
        "status": status,
        "returncode": 0 if status == "passed" else 1,
        "duration_seconds": 0.0,
        "stdout": detail,
        "stderr": "",
        "parsed_output": parsed_output,
        "evidence_paths": evidence_paths,
    }


def fail(
    check_id: str,
    summary: str,
    detail: str,
    evidence_paths: list[str],
    parsed_output: Any | None = None,
) -> dict[str, Any]:
    return make_check(check_id, summary, "failed", detail, evidence_paths, parsed_output)


def passed(
    check_id: str,
    summary: str,
    detail: str,
    evidence_paths: list[str],
    parsed_output: Any | None = None,
) -> dict[str, Any]:
    return make_check(check_id, summary, "passed", detail, evidence_paths, parsed_output)


def find_step(steps: list[dict[str, Any]], *, name: str, uses: str) -> tuple[int, dict[str, Any]] | None:
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if step.get("name") == name and step.get("uses") == uses:
            return index, step
    return None


def validate_upload(job_id: str, steps: list[dict[str, Any]], upload_spec: dict[str, Any], evidence_paths: list[str]) -> dict[str, Any]:
    summary = f"Validate upload-artifact policy for workflow job `{job_id}`"
    found = find_step(steps, name=str(upload_spec["step_name"]), uses=str(upload_spec["uses"]))
    if found is None:
        return fail(f"{job_id}-artifact-upload", summary, "upload step missing from workflow", evidence_paths, upload_spec)
    _, step = found
    with_block = step.get("with")
    if not isinstance(with_block, dict):
        return fail(f"{job_id}-artifact-upload", summary, "upload step missing `with` block", evidence_paths, upload_spec)

    actual_paths = normalize_paths(with_block.get("path"))
    expected_paths = normalize_paths(upload_spec.get("required_paths"))
    actual_retention = with_block.get("retention-days")
    detail_parts: list[str] = []

    if step.get("if") != upload_spec.get("if_condition"):
        return fail(
            f"{job_id}-artifact-upload",
            summary,
            f"unexpected upload condition: {step.get('if')!r}",
            evidence_paths,
            {"expected": upload_spec, "actual": step},
        )
    if with_block.get("name") != upload_spec.get("artifact_name"):
        return fail(
            f"{job_id}-artifact-upload",
            summary,
            f"artifact name mismatch: expected {upload_spec.get('artifact_name')}, got {with_block.get('name')}",
            evidence_paths,
            {"expected": upload_spec, "actual": step},
        )
    if with_block.get("if-no-files-found") != upload_spec.get("if_no_files_found"):
        return fail(
            f"{job_id}-artifact-upload",
            summary,
            f"if-no-files-found mismatch: expected {upload_spec.get('if_no_files_found')}, got {with_block.get('if-no-files-found')}",
            evidence_paths,
            {"expected": upload_spec, "actual": step},
        )
    if int(actual_retention) != int(upload_spec.get("retention_days")):
        return fail(
            f"{job_id}-artifact-upload",
            summary,
            f"retention-days mismatch: expected {upload_spec.get('retention_days')}, got {actual_retention}",
            evidence_paths,
            {"expected": upload_spec, "actual": step},
        )
    if actual_paths != expected_paths:
        return fail(
            f"{job_id}-artifact-upload",
            summary,
            "artifact upload paths drifted from policy",
            evidence_paths,
            {"expected_paths": expected_paths, "actual_paths": actual_paths},
        )

    detail_parts.append(f"artifact={with_block.get('name')}")
    detail_parts.append(f"retention_days={actual_retention}")
    detail_parts.append(f"paths={len(actual_paths)}")
    return passed(
        f"{job_id}-artifact-upload",
        summary,
        "; ".join(detail_parts),
        evidence_paths,
        {"artifact_name": with_block.get("name"), "paths": actual_paths},
    )


def validate_download(job_id: str, steps: list[dict[str, Any]], download_spec: dict[str, Any], evidence_paths: list[str]) -> dict[str, Any]:
    summary = f"Validate download-artifact policy for workflow job `{job_id}`"
    found = find_step(steps, name=str(download_spec["step_name"]), uses=str(download_spec["uses"]))
    if found is None:
        return fail(f"{job_id}-artifact-download", summary, "download step missing from workflow", evidence_paths, download_spec)
    index, step = found
    with_block = step.get("with")
    if not isinstance(with_block, dict):
        return fail(f"{job_id}-artifact-download", summary, "download step missing `with` block", evidence_paths, download_spec)

    if with_block.get("name") != download_spec.get("artifact_name"):
        return fail(
            f"{job_id}-artifact-download",
            summary,
            f"downloaded artifact mismatch: expected {download_spec.get('artifact_name')}, got {with_block.get('name')}",
            evidence_paths,
            {"expected": download_spec, "actual": step},
        )

    actual_path = str(with_block.get("path") or ".")
    expected_path = str(download_spec.get("path") or ".")
    if actual_path != expected_path:
        return fail(
            f"{job_id}-artifact-download",
            summary,
            f"download path mismatch: expected {expected_path}, got {actual_path}",
            evidence_paths,
            {"expected": download_spec, "actual": step},
        )

    for target_name in download_spec.get("must_precede_steps", []):
        target_index = next(
            (
                candidate_index
                for candidate_index, candidate in enumerate(steps)
                if isinstance(candidate, dict) and candidate.get("name") == target_name
            ),
            None,
        )
        if target_index is None:
            return fail(
                f"{job_id}-artifact-download",
                summary,
                f"required downstream step missing: {target_name}",
                evidence_paths,
                {"expected": download_spec},
            )
        if index >= target_index:
            return fail(
                f"{job_id}-artifact-download",
                summary,
                f"download step must run before `{target_name}`",
                evidence_paths,
                {"download_step": step.get("name"), "target_step": target_name},
            )

    return passed(
        f"{job_id}-artifact-download",
        summary,
        f"downloads `{with_block.get('name')}` to `{actual_path}` before downstream governance steps",
        evidence_paths,
        {"artifact_name": with_block.get("name"), "path": actual_path},
    )


def validate_policy_structure(policy_jobs: list[dict[str, Any]], evidence_paths: list[str]) -> dict[str, Any]:
    summary = "Validate CI artifact governance policy structure"
    seen_ids: set[str] = set()
    seen_artifact_names: set[str] = set()
    for item in policy_jobs:
        job_id = item.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            return fail("artifact-policy-structure", summary, "policy job missing non-empty `job_id`", evidence_paths, item)
        if job_id in seen_ids:
            return fail("artifact-policy-structure", summary, f"duplicate job_id in policy: {job_id}", evidence_paths, item)
        seen_ids.add(job_id)
        upload = item.get("upload")
        if not isinstance(upload, dict):
            return fail("artifact-policy-structure", summary, f"{job_id} missing `upload` policy", evidence_paths, item)
        artifact_name = upload.get("artifact_name")
        if not isinstance(artifact_name, str) or not artifact_name.endswith("-artifacts"):
            return fail("artifact-policy-structure", summary, f"{job_id} has invalid artifact name: {artifact_name}", evidence_paths, item)
        if artifact_name in seen_artifact_names:
            return fail("artifact-policy-structure", summary, f"duplicate artifact name in policy: {artifact_name}", evidence_paths, item)
        seen_artifact_names.add(artifact_name)
    return passed(
        "artifact-policy-structure",
        summary,
        f"policy covers {len(policy_jobs)} jobs with unique artifact bundles",
        evidence_paths,
        {"job_ids": sorted(seen_ids), "artifact_names": sorted(seen_artifact_names)},
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS CI Artifact Governance Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Workflow: `{report['workflow']}`",
        f"- Policy: `{report['policy']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
    ]
    for item in report["checks"]:
        lines.append(
            f"| `{item['check_id']}` | `{item['status']}` | {item['stdout']} |"
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    policy = load_yaml(args.policy)
    workflow = load_yaml(args.workflow)
    schema = load_json(VALIDATION_REPORT_SCHEMA)

    evidence_paths = [str(args.workflow), str(args.policy)]
    checks: list[dict[str, Any]] = []
    failed = False

    jobs = workflow.get("jobs")
    policy_jobs = policy.get("jobs")
    if not isinstance(jobs, dict):
        raise SystemExit("workflow file must contain a jobs mapping")
    if not isinstance(policy_jobs, list) or not policy_jobs:
        raise SystemExit("artifact policy must contain a non-empty jobs list")

    structure_check = validate_policy_structure(policy_jobs, evidence_paths)
    checks.append(structure_check)
    failed = failed or structure_check["status"] != "passed"

    for policy_job in policy_jobs:
        job_id = str(policy_job["job_id"])
        workflow_job = jobs.get(job_id)
        if not isinstance(workflow_job, dict):
            checks.append(
                fail(
                    f"{job_id}-workflow-job",
                    f"Validate workflow job `{job_id}` exists",
                    "workflow job missing",
                    evidence_paths,
                    {"job_id": job_id},
                )
            )
            failed = True
            continue

        steps = workflow_job.get("steps")
        if not isinstance(steps, list):
            checks.append(
                fail(
                    f"{job_id}-workflow-job",
                    f"Validate workflow job `{job_id}` steps",
                    "workflow job missing steps list",
                    evidence_paths,
                    {"job_id": job_id},
                )
            )
            failed = True
            continue

        checks.append(
            passed(
                f"{job_id}-workflow-job",
                f"Validate workflow job `{job_id}` exists",
                f"workflow job contains {len(steps)} steps",
                evidence_paths,
                {"job_id": job_id, "step_count": len(steps)},
            )
        )

        for download_spec in policy_job.get("required_downloads", []):
            check = validate_download(job_id, steps, download_spec, evidence_paths)
            checks.append(check)
            failed = failed or check["status"] != "passed"

        upload_check = validate_upload(job_id, steps, policy_job["upload"], evidence_paths)
        checks.append(upload_check)
        failed = failed or upload_check["status"] != "passed"

    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ROOT),
        "overall_status": "failed" if failed else "passed",
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "workflow": str(args.workflow),
        "policy": str(args.policy),
        "checks": checks,
    }
    write_json(json_path, report)
    write_markdown(markdown_path, render_markdown(report))
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(report)
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "check_count": len(checks),
                "failing_checks": [item["check_id"] for item in checks if item["status"] != "passed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
