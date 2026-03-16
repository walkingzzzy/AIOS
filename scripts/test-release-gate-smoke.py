#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CHECK_RELEASE_GATE_SCRIPT = ROOT / "scripts" / "check-release-gate.py"
SAMPLE_DIR = ROOT / "aios" / "observability" / "samples"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "release-gate-vendor-runtime-smoke-report"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify release-gate vendor runtime sign-off behavior")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help="Output prefix for the generated smoke summary report",
    )
    parser.add_argument("--keep-state", action="store_true", help="Keep the synthetic fixture directory on success")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sample_payload(name: str) -> Any:
    return load_json(SAMPLE_DIR / name)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def scenario_slug(name: str) -> str:
    collapsed = "".join(ch.lower() if ch.isalnum() else "-" for ch in name)
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return collapsed.strip("-") or "scenario"


def write_release_checklist(path: Path) -> None:
    write_text(
        path,
        """# Synthetic Release Checklist

<!-- aios-release-gate-rules:start -->
```yaml
release_gate:
  use_matrix_blocking: false
  warn_on_non_blocking_failures: true
hardware_evidence:
  required_by_default: true
```
<!-- aios-release-gate-rules:end -->
""",
    )


def build_hardware_evidence_index(
    path: Path,
    *,
    baseline_kind: str,
    real_machine_signoff_status: str,
    vendor_runtime_signoff_status: str,
    evidence_count: int,
    evidence_paths: list[str],
    provider_ids: list[str],
    runtime_service_ids: list[str],
    provider_statuses: list[str],
    backend_ids: list[str],
) -> None:
    release_grade_backends = {
        "backend_ids": ",".join(backend_ids),
        "origins": "vendor-runtime" if backend_ids else "",
        "stacks": "tensorrt" if backend_ids else "",
        "contract_kinds": "vendor-runtime-evidence-v1" if backend_ids else "",
    }
    payload = {
        "platform_id": "nvidia-jetson-orin-agx" if backend_ids else "generic-x86_64-uefi",
        "profile": str(ROOT / "aios" / "hardware" / "profiles" / "nvidia-jetson-orin-agx.yaml"),
        "validation_status": "passed",
        "generated_at": "2026-03-16T00:00:00Z",
        "summary": {
            "passed": True,
            "record_count": 2,
            "unique_boot_ids": ["boot-a", "boot-b"],
            "final_current_slot": "b",
            "final_last_good_slot": "b",
        },
        "artifacts": {
            "platform_media_manifest": "",
            "installer_image": None,
            "recovery_image": None,
            "system_image": None,
            "installer_report": "",
            "vendor_firmware_hook_report": "",
            "evaluator_json": str(path.parent / "tier1-hardware-boot-evidence-report.json"),
            "evaluator_markdown": "",
            "support_matrix": str(path.parent / "tier1-hardware-support-matrix.md"),
            "known_limitations": str(path.parent / "tier1-hardware-known-limitations.md"),
            "installer_log": "",
            "recovery_log": "",
            "device_backend_state_artifact": "",
            "vendor_runtime_evidence": evidence_paths,
            "photos": [],
            "boot_evidence_report": str(path.parent / "tier1-hardware-boot-evidence-report.json"),
            "boot_evidence_markdown": str(path.parent / "tier1-hardware-boot-evidence-report.md"),
        },
        "device_runtime": {
            "backend_state_artifact": None,
            "release_grade_backends": release_grade_backends,
            "vendor_runtime": {
                "vendor_runtime_signoff_status": vendor_runtime_signoff_status,
                "evidence_count": evidence_count,
                "evidence_paths": evidence_paths,
                "provider_ids": provider_ids,
                "runtime_service_ids": runtime_service_ids,
                "provider_statuses": provider_statuses,
                "provider_kinds": ["managed-worker"] if provider_ids else [],
                "backend_ids": backend_ids,
                "runtime_binaries": ["/usr/bin/trtexec"] if backend_ids else [],
                "engine_paths": ["/var/lib/aios/engines/resnet50.plan"] if evidence_paths else [],
                "contract_kinds": ["vendor-runtime-evidence-v1"] if evidence_paths else [],
                "issues": [],
            },
        },
        "checks": [
            {
                "name": "minimum_boots",
                "passed": True,
                "detail": "observed 2 unique boot ids",
            }
        ],
        "notes": ["release gate vendor runtime smoke fixture"],
        "operator": "release-gate-smoke",
        "date": "2026-03-16",
        "baseline_kind": baseline_kind,
        "validation_scope": "smoke-test",
        "real_machine_signoff_status": real_machine_signoff_status,
        "nominated_machines_manifest": str(ROOT / "aios" / "hardware" / "tier1-nominated-machines.yaml"),
        "nominated_machine_ids": ["nvidia-jetson-orin-agx"],
        "nominated_machine_count": 1,
    }
    write_json(path, payload)


def find_check(report: dict[str, Any], check_id: str) -> dict[str, Any]:
    for item in report.get("checks", []):
        if item.get("check_id") == check_id:
            return item
    raise RuntimeError(f"missing release gate check: {check_id}")


def run_release_gate(
    temp_root: Path,
    name: str,
    *,
    baseline_kind: str,
    real_machine_signoff_status: str,
    vendor_runtime_signoff_status: str,
    evidence_count: int,
    provider_ids: list[str],
    runtime_service_ids: list[str],
    provider_statuses: list[str],
    backend_ids: list[str],
    expect_returncode: int,
) -> dict[str, Any]:
    scenario_root = temp_root / scenario_slug(name)
    inputs_dir = scenario_root / "inputs"
    outputs_dir = scenario_root / "outputs"
    checklist_path = scenario_root / "RELEASE_CHECKLIST.md"
    validation_report = inputs_dir / "system-delivery-validation-report.json"
    evidence_index = inputs_dir / "governance-evidence-index.json"
    health_report = inputs_dir / "cross-service-health-report.json"
    hardware_evidence_index = inputs_dir / "hardware-validation-evidence.json"
    report_prefix = outputs_dir / "release-gate-report"
    vendor_evidence = inputs_dir / "vendor-execution.json"

    write_release_checklist(checklist_path)
    write_json(validation_report, load_sample_payload("validation-report.sample.json"))
    write_json(evidence_index, load_sample_payload("evidence-index.sample.json"))
    write_json(health_report, load_sample_payload("cross-service-health-report.sample.json"))

    evidence_paths: list[str] = []
    if evidence_count > 0:
        write_json(
            vendor_evidence,
            {
                "backend_id": backend_ids[0] if backend_ids else "local-gpu",
                "provider_id": provider_ids[0] if provider_ids else "nvidia.jetson.tensorrt",
                "provider_status": provider_statuses[0] if provider_statuses else "available",
                "runtime_service_id": runtime_service_ids[0] if runtime_service_ids else "aios-runtimed.jetson-vendor-helper",
                "contract_kind": "vendor-runtime-evidence-v1",
            },
        )
        evidence_paths.append(str(vendor_evidence))

    build_hardware_evidence_index(
        hardware_evidence_index,
        baseline_kind=baseline_kind,
        real_machine_signoff_status=real_machine_signoff_status,
        vendor_runtime_signoff_status=vendor_runtime_signoff_status,
        evidence_count=evidence_count,
        evidence_paths=evidence_paths,
        provider_ids=provider_ids,
        runtime_service_ids=runtime_service_ids,
        provider_statuses=provider_statuses,
        backend_ids=backend_ids,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(CHECK_RELEASE_GATE_SCRIPT),
            "--release-checklist",
            str(checklist_path),
            "--validation-report",
            str(validation_report),
            "--evidence-index",
            str(evidence_index),
            "--health-report",
            str(health_report),
            "--hardware-evidence-index",
            str(hardware_evidence_index),
            "--output-prefix",
            str(report_prefix),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout.strip():
        print(completed.stdout.rstrip())
    if completed.stderr.strip():
        print(completed.stderr.rstrip())
    require(
        completed.returncode == expect_returncode,
        f"{name}: unexpected release gate returncode {completed.returncode}, expected {expect_returncode}",
    )

    report_path = report_prefix.with_suffix(".json")
    require(report_path.exists(), f"{name}: release gate report missing")
    report = load_json(report_path)
    vendor_check = find_check(report, "hardware-vendor-runtime-signoff")
    return {
        "name": name,
        "returncode": completed.returncode,
        "report_path": str(report_path),
        "gate_status": report.get("gate_status"),
        "blocking_checks": list(report.get("blocking_checks", [])),
        "warnings": list(report.get("warnings", [])),
        "vendor_check": vendor_check,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# AIOS Release Gate Vendor Runtime Smoke Report",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Overall status: `{summary['overall_status']}`",
        "",
        "## Scenarios",
        "",
        "| Scenario | Gate | Vendor Check | Returncode | Detail |",
        "|----------|------|--------------|------------|--------|",
    ]
    for item in summary["scenarios"]:
        lines.append(
            "| `{name}` | `{gate}` | `{vendor}` | `{returncode}` | {detail} |".format(
                name=item["name"],
                gate=item["gate_status"],
                vendor=item["vendor_check"]["status"],
                returncode=item["returncode"],
                detail=item["vendor_check"]["detail"],
            )
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    temp_parent = ROOT / "out" / "tmp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = temp_parent / f"aios-release-gate-smoke-{uuid.uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    failed = False

    try:
        synthetic = run_release_gate(
            temp_root,
            "synthetic-baseline-warning",
            baseline_kind="synthetic-tier1-release-gate",
            real_machine_signoff_status="pending-separate-evidence",
            vendor_runtime_signoff_status="not-attached",
            evidence_count=0,
            provider_ids=[],
            runtime_service_ids=[],
            provider_statuses=[],
            backend_ids=[],
            expect_returncode=0,
        )
        require(
            synthetic["vendor_check"]["status"] == "warning",
            "synthetic baseline scenario should emit a vendor runtime warning",
        )
        require(
            any(
                "synthetic Tier 1 baseline does not attach vendor runtime sign-off" in warning
                for warning in synthetic["warnings"]
            ),
            "synthetic baseline scenario missing vendor runtime warning",
        )

        attached = run_release_gate(
            temp_root,
            "real-machine-signoff-attached",
            baseline_kind="nominated-machine-signoff",
            real_machine_signoff_status="collected",
            vendor_runtime_signoff_status="evidence-attached",
            evidence_count=1,
            provider_ids=["nvidia.jetson.tensorrt"],
            runtime_service_ids=["aios-runtimed.jetson-vendor-helper"],
            provider_statuses=["available"],
            backend_ids=["local-gpu"],
            expect_returncode=0,
        )
        require(
            attached["vendor_check"]["status"] == "passed",
            "real-machine attached scenario should pass vendor runtime check",
        )
        require(
            attached["gate_status"] == "passed",
            "real-machine attached scenario should pass the release gate",
        )

        inconsistent = run_release_gate(
            temp_root,
            "real-machine-signoff-incomplete",
            baseline_kind="nominated-machine-signoff",
            real_machine_signoff_status="collected",
            vendor_runtime_signoff_status="evidence-attached",
            evidence_count=0,
            provider_ids=[],
            runtime_service_ids=[],
            provider_statuses=[],
            backend_ids=["local-gpu"],
            expect_returncode=1,
        )
        require(
            inconsistent["vendor_check"]["status"] == "failed",
            "incomplete vendor sign-off scenario should fail vendor runtime check",
        )
        require(
            "hardware-vendor-runtime-signoff" in inconsistent["blocking_checks"],
            "incomplete vendor sign-off scenario should block the release gate",
        )

        scenarios = [synthetic, attached, inconsistent]
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": "passed",
            "temp_root": str(temp_root),
            "scenarios": scenarios,
        }
        json_path = args.output_prefix.with_suffix(".json")
        markdown_path = args.output_prefix.with_suffix(".md")
        write_json(json_path, summary)
        write_text(markdown_path, render_markdown(summary) + "\n")
        print(
            json.dumps(
                {
                    "overall_status": summary["overall_status"],
                    "json_report": str(json_path),
                    "markdown_report": str(markdown_path),
                    "scenarios": [
                        {
                            "name": item["name"],
                            "gate_status": item["gate_status"],
                            "vendor_check": item["vendor_check"]["status"],
                        }
                        for item in scenarios
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception:
        failed = True
        raise
    finally:
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
