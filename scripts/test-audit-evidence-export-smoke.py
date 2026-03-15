#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STATE_PATTERNS = [
    re.compile(r"state kept at:?\s*(?P<path>.+)$"),
    re.compile(r"state retained at:?\s*(?P<path>.+)$"),
    re.compile(r"state preserved at:?\s*(?P<path>.+)$"),
    re.compile(r"Preserved .* state at:\s*(?P<path>.+)$"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS audit evidence export smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing compiled binaries")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--keep-state", action="store_true")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def extract_state_root(stdout: str, label: str) -> Path:
    for line in stdout.splitlines():
        stripped = line.strip()
        for pattern in STATE_PATTERNS:
            match = pattern.search(stripped)
            if match:
                return Path(match.group("path").strip())
    raise RuntimeError(f"failed to parse retained state root from {label} output")


def run_smoke(command: list[str], label: str) -> Path:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    return extract_state_root(completed.stdout, label)


def compat_runtime_audit_log(root: Path, provider_id: str) -> Path:
    path = root / "audit" / f"{provider_id.replace('.', '-')}.jsonl"
    require(path.exists(), f"missing compat audit log: {path}")
    return path


def compat_shared_audit_log(root: Path) -> Path:
    path = root / "audit" / "compat-observability.jsonl"
    require(path.exists(), f"missing compat shared audit log: {path}")
    return path


def sorted_matching_paths(root: Path, pattern: str) -> list[Path]:
    return sorted(path for path in root.glob(pattern) if path.is_file())


def main() -> int:
    args = parse_args()
    state_roots: list[Path] = []

    team_b_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "test-team-b-control-plane-smoke.py"),
        "--keep-state",
        "--timeout",
        str(args.timeout),
    ]
    shell_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "test-shell-provider-smoke.py"),
        "--keep-state",
        "--timeout",
        str(args.timeout),
    ]
    device_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "test-deviced-policy-approval-smoke.py"),
        "--keep-state",
        "--timeout",
        str(args.timeout),
    ]
    provider_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "test-runtime-local-inference-provider-smoke.py"),
        "--keep-state",
        "--timeout",
        str(args.timeout),
    ]
    compat_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "test-compat-runtime-smoke.py"),
        "--keep-state",
        "--timeout",
        str(args.timeout),
    ]
    updated_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "test-updated-smoke.py"),
        "--keep-state",
        "--timeout",
        str(args.timeout),
    ]
    if args.bin_dir is not None:
        for command in [team_b_cmd, shell_cmd, device_cmd, provider_cmd, compat_cmd, updated_cmd]:
            command.extend(["--bin-dir", str(args.bin_dir)])

    try:
        team_b_root = run_smoke(team_b_cmd, "team-b control-plane smoke")
        state_roots.append(team_b_root)
        shell_root = run_smoke(shell_cmd, "shell provider smoke")
        state_roots.append(shell_root)
        device_root = run_smoke(device_cmd, "deviced policy approval smoke")
        state_roots.append(device_root)
        provider_root = run_smoke(provider_cmd, "runtime local inference provider smoke")
        state_roots.append(provider_root)
        updated_root = run_smoke(updated_cmd, "updated smoke")
        state_roots.append(updated_root)

        hardware_completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build-default-hardware-evidence-index.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if hardware_completed.returncode != 0:
            sys.stdout.write(hardware_completed.stdout)
            sys.stderr.write(hardware_completed.stderr)
            raise SystemExit(hardware_completed.returncode)

        compat_root = run_smoke(compat_cmd, "compat runtime smoke")
        state_roots.append(compat_root)

        report_prefix = ROOT / "out" / "validation" / "audit-evidence-report"
        domain_config_path = ROOT / "out" / "validation" / "audit-evidence-domain-config.json"

        team_b_state = team_b_root / "state"
        shell_state = shell_root / "state"
        device_state = device_root / "state"
        provider_state = provider_root / "state"
        updated_state = updated_root / "state"

        team_b_audit_log = team_b_state / "policyd" / "audit.jsonl"
        team_b_audit_index = team_b_state / "policyd" / "audit-index.json"
        session_db = team_b_state / "sessiond" / "sessiond.sqlite3"
        runtime_events_log = team_b_state / "runtimed" / "runtime-events.jsonl"
        remote_audit_log = team_b_state / "runtimed" / "remote-audit.jsonl"
        observability_log = team_b_state / "runtimed" / "observability.jsonl"
        updated_bundle_paths = sorted_matching_paths(updated_state / "diagnostics", "*.json")
        updated_recovery_paths = sorted_matching_paths(updated_state / "recovery", "*.json")
        require(updated_bundle_paths, "updated smoke did not retain any diagnostic bundles")
        require(updated_recovery_paths, "updated smoke did not retain any recovery records")

        domain_config_path.parent.mkdir(parents=True, exist_ok=True)
        domain_config = {
            "domains": {
                "shell": {
                    "audit_logs": [str(shell_state / "policyd" / "audit.jsonl")],
                    "jsonl_logs": [
                        {
                            "kind": "panel_actions",
                            "path": str(shell_state / "shell-provider" / "panel-action-events.jsonl"),
                        }
                    ],
                    "json_files": [
                        {
                            "kind": "focus_state",
                            "path": str(shell_state / "shell-provider" / "focus-state.json"),
                        }
                    ],
                },
                "device": {
                    "audit_logs": [str(device_state / "policyd" / "audit.jsonl")],
                    "observability_logs": [str(device_state / "observability.jsonl")],
                    "json_files": [
                        {
                            "kind": "capture_state",
                            "path": str(device_state / "deviced" / "captures.json"),
                        },
                        {
                            "kind": "backend_state",
                            "path": str(device_state / "deviced" / "backend-state.json"),
                        },
                    ],
                },
                "provider": {
                    "audit_logs": [str(provider_state / "policyd" / "audit.jsonl")],
                    "observability_logs": [
                        str(provider_state / "rli" / "observability.jsonl"),
                        str(provider_state / "runtimed" / "observability.jsonl"),
                    ],
                    "json_files": [
                        {
                            "kind": "provider_health",
                            "path": str(provider_state / "registry" / "health" / "runtime.local.inference.json"),
                        }
                    ],
                    "notes": [
                        "synthetic provider baseline retained for operator-facing evidence export"
                    ],
                },
                "compat": {
                    "jsonl_logs": [
                        {
                            "kind": "browser_audit",
                            "path": str(
                                compat_runtime_audit_log(
                                    compat_root,
                                    "compat.browser.automation.local",
                                )
                            ),
                        },
                        {
                            "kind": "office_audit",
                            "path": str(
                                compat_runtime_audit_log(
                                    compat_root,
                                    "compat.office.document.local",
                                )
                            ),
                        },
                        {
                            "kind": "mcp_bridge_audit",
                            "path": str(
                                compat_runtime_audit_log(
                                    compat_root,
                                    "compat.mcp.bridge.local",
                                )
                            ),
                        },
                        {
                            "kind": "code_sandbox_audit",
                            "path": str(
                                compat_runtime_audit_log(
                                    compat_root,
                                    "compat.code.sandbox.local",
                                )
                            ),
                        },
                        {
                            "kind": "shared_compat_observability",
                            "path": str(compat_shared_audit_log(compat_root)),
                        },
                    ],
                    "notes": [
                        "compat runtime smoke retained a shared compat observability sink with centralized policy evidence"
                    ],
                },
                "updated": {
                    "observability_logs": [str(updated_state / "observability.jsonl")],
                    "json_files": [
                        {
                            "kind": "health_probe",
                            "path": str(updated_state / "health-probe.json"),
                        },
                        {
                            "kind": "deployment_state",
                            "path": str(updated_state / "deployment-state.json"),
                        },
                        {
                            "kind": "recovery_surface",
                            "path": str(updated_state / "recovery-surface.json"),
                        },
                        {
                            "kind": "boot_state",
                            "path": str(updated_state / "boot-control.json"),
                        },
                        {
                            "kind": "system_delivery_validation_index",
                            "path": str(ROOT / "out" / "validation" / "system-delivery-validation-evidence-index.json"),
                        },
                        {
                            "kind": "system_delivery_validation_report",
                            "path": str(ROOT / "out" / "validation" / "system-delivery-validation-report.json"),
                        },
                        *[
                            {
                                "kind": "recovery_record",
                                "path": str(path),
                            }
                            for path in updated_recovery_paths
                        ],
                        *[
                            {
                                "kind": "diagnostic_bundle",
                                "path": str(path),
                            }
                            for path in updated_bundle_paths
                        ],
                    ],
                    "notes": [
                        "updated/recovery retained state and system-delivery validation artifacts exported for operator-facing evidence"
                    ],
                },
                "hardware": {
                    "json_files": [
                        {
                            "kind": "hardware_evidence_index",
                            "path": str(ROOT / "out" / "validation" / "tier1-hardware-evidence-index.json"),
                        },
                        {
                            "kind": "hardware_validation_report",
                            "path": str(ROOT / "out" / "validation" / "tier1-hardware-boot-evidence-report.json"),
                        },
                    ],
                    "notes": [
                        "default Tier 1 hardware evidence baseline retained for operator-facing export"
                    ],
                },
            }
        }
        domain_config_path.write_text(json.dumps(domain_config, indent=2, ensure_ascii=False) + "\n")

        build_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "build-audit-evidence-report.py"),
            "--session-db",
            str(session_db),
            "--policy-audit-log",
            str(team_b_audit_log),
            "--audit-index",
            str(team_b_audit_index),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--observability-log",
            str(observability_log),
            "--domain-config",
            str(domain_config_path),
            "--output-prefix",
            str(report_prefix),
        ]
        build_completed = subprocess.run(build_cmd, cwd=ROOT, text=True, capture_output=True, check=False)
        if build_completed.returncode != 0:
            sys.stdout.write(build_completed.stdout)
            sys.stderr.write(build_completed.stderr)
            raise SystemExit(build_completed.returncode)

        json_report = report_prefix.with_suffix(".json")
        markdown_report = report_prefix.with_suffix(".md")
        require(json_report.exists(), "audit evidence report json was not written")
        require(markdown_report.exists(), "audit evidence report markdown was not written")

        payload = json.loads(json_report.read_text())
        require(payload["summary"]["task_count"] >= 2, "expected at least two tasks in audit evidence report")
        require(payload["summary"]["audit_entry_count"] >= 4, "expected approval audit evidence in report")
        require(payload["summary"]["approval_ref_count"] >= 2, "expected multiple approval references across domains")
        require(payload["summary"]["runtime_event_count"] >= 1, "expected runtime events in report")
        require(payload["summary"]["observability_record_count"] >= 1, "expected observability records in report")
        require(
            set(
                [
                    "control-plane",
                    "shell",
                    "provider",
                    "compat",
                    "device",
                    "updated",
                    "hardware",
                    "release-signoff",
                ]
            ).issubset(set(payload["summary"]["covered_domains"])),
            "report missing one or more required evidence domains",
        )
        require(
            "approval-pending" in payload["summary"]["audit_decisions"],
            "report missing approval-pending decision",
        )
        require(
            "approval-approved" in payload["summary"]["audit_decisions"],
            "report missing approval-approved decision",
        )
        require(
            "token-issued" in payload["summary"]["audit_decisions"],
            "report missing token-issued decision",
        )
        require(
            str(team_b_audit_log) in payload["summary"]["artifact_paths"],
            "report summary missing policy audit artifact path",
        )
        require(
            payload["audit_store"]["active_segment_path"] == str(team_b_audit_log),
            "report audit store active segment path mismatch",
        )
        require(
            any(item["approval_refs"] for item in payload["tasks"]),
            "report tasks missing approval references",
        )
        require(
            any("runtime.infer.completed" in item["runtime_event_kinds"] for item in payload["tasks"]),
            "report tasks missing runtime completion evidence",
        )

        shell_domain = payload["domain_evidence"]["shell"]
        provider_domain = payload["domain_evidence"]["provider"]
        compat_domain = payload["domain_evidence"]["compat"]
        compat_overview = payload["compat_audit_overview"]
        device_domain = payload["domain_evidence"]["device"]
        updated_domain = payload["domain_evidence"]["updated"]
        hardware_domain = payload["domain_evidence"]["hardware"]
        release_signoff_domain = payload["domain_evidence"]["release-signoff"]

        require("shell.panel-events.list" in shell_domain["capability_ids"], "shell domain missing panel-events capability")
        require("approve" in shell_domain["action_ids"], "shell domain missing approval-panel action evidence")
        require("runtime.local.inference" in provider_domain["provider_ids"], "provider domain missing runtime.local.inference evidence")
        require("provider.runtime.started" in provider_domain["event_kinds"], "provider domain missing provider lifecycle evidence")
        require(
            {
                "compat.browser.automation.local",
                "compat.office.document.local",
                "compat.mcp.bridge.local",
                "compat.code.sandbox.local",
            }.issubset(set(compat_domain["provider_ids"])),
            "compat domain missing provider coverage",
        )
        require(compat_overview["provider_count"] == 4, "compat overview missing provider count")
        require(
            compat_overview["centralized_policy_record_count"] >= 4,
            "compat overview missing centralized policy coverage",
        )
        require(
            compat_overview["token_verified_record_count"] >= 4,
            "compat overview missing token verified coverage",
        )
        require(
            compat_overview["timeout_record_count"] >= 1,
            "compat overview missing sandbox timeout evidence",
        )
        require(
            str(compat_shared_audit_log(compat_root)) in compat_overview["shared_audit_log_paths"],
            "compat overview missing shared compat audit log path",
        )
        require(
            any(
                item["provider_id"] == "compat.code.sandbox.local" and item["timeout_record_count"] >= 1
                for item in compat_overview["providers"]
            ),
            "compat overview missing code sandbox timeout summary",
        )
        require("device.capture.audio" in device_domain["capability_ids"], "device domain missing capture approval capability")
        require(device_domain["approval_refs"], "device domain missing approval references")
        require(
            "update.apply.completed" in updated_domain["event_kinds"],
            "updated domain missing update.apply observability evidence",
        )
        require(
            "recovery.bundle.exported" in updated_domain["event_kinds"],
            "updated domain missing recovery bundle export evidence",
        )
        require(
            "update.rollback.completed" in updated_domain["event_kinds"],
            "updated domain missing update.rollback observability evidence",
        )
        require(
            str(updated_state / "recovery-surface.json") in updated_domain["artifact_paths"],
            "updated domain missing recovery surface artifact",
        )
        require(
            any(item["kind"] == "system_delivery_validation_index" and item["present"] for item in updated_domain["sources"]),
            "updated domain missing system delivery validation evidence index",
        )
        require(
            any(item["kind"] == "recovery_record" and item["present"] for item in updated_domain["sources"]),
            "updated domain missing retained recovery record evidence",
        )
        require(
            "synthetic-tier1-release-gate" in hardware_domain["status_values"] or "passed" in hardware_domain["status_values"],
            "hardware domain missing baseline status evidence",
        )
        require(
            str(ROOT / "out" / "validation" / "tier1-hardware-evidence-index.json") in hardware_domain["artifact_paths"],
            "hardware domain missing default evidence index artifact",
        )
        require(
            any(item["kind"] == "governance_evidence_index" and item["present"] for item in release_signoff_domain["sources"]),
            "release-signoff domain missing governance evidence source",
        )
        require(
            any(item["kind"] == "release_gate_report" and item["present"] for item in release_signoff_domain["sources"]),
            "release-signoff domain missing release gate report source",
        )
        require(
            "passed" in release_signoff_domain["status_values"],
            "release-signoff domain missing passed release-governance status evidence",
        )
        require(
            str(ROOT / "out" / "validation" / "governance-evidence-index.json") in release_signoff_domain["artifact_paths"],
            "release-signoff domain missing governance evidence artifact",
        )
        require(
            str(ROOT / "out" / "validation" / "release-gate-report.json") in release_signoff_domain["artifact_paths"],
            "release-signoff domain missing release gate artifact",
        )
        require(
            any("real-machine hardware validation evidence" in note for note in release_signoff_domain["notes"]),
            "release-signoff domain missing real-machine sign-off discovery note",
        )

        print(
            json.dumps(
                {
                    "state_roots": [str(path) for path in state_roots],
                    "json_report": str(json_report),
                    "markdown_report": str(markdown_report),
                    "task_count": payload["summary"]["task_count"],
                    "approval_ref_count": payload["summary"]["approval_ref_count"],
                    "audit_entry_count": payload["summary"]["audit_entry_count"],
                    "covered_domains": payload["summary"]["covered_domains"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        if not args.keep_state:
            for path in state_roots:
                shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
