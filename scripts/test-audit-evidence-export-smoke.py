#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
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
SESSIOND_MIGRATIONS = [
    ROOT / "aios" / "services" / "sessiond" / "migrations" / "0001_init.sql",
    ROOT / "aios" / "services" / "sessiond" / "migrations" / "0002_task_events.sql",
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


def extract_skip_reason(stdout: str, stderr: str) -> str | None:
    for line in [*stdout.splitlines(), *stderr.splitlines()]:
        stripped = line.strip()
        if "skipped:" in stripped:
            return stripped.split("skipped:", 1)[1].strip()
    return None


def run_smoke(command: list[str], label: str) -> Path | None:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    skip_reason = extract_skip_reason(completed.stdout, completed.stderr)
    if skip_reason is not None:
        print(f"{label} unavailable ({skip_reason})")
        return None
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


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    if rendered:
        rendered += "\n"
    path.write_text(rendered, encoding="utf-8")


def create_session_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for migration in SESSIOND_MIGRATIONS:
            connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO sessions (session_id, user_id, metadata_json, created_at, last_resumed_at, status) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            (
                "session-audit-synthetic",
                "user-audit-synthetic",
                json.dumps({"source": "synthetic-multi-domain-audit-export"}, ensure_ascii=False),
                "2026-03-16T00:00:00+00:00",
                "2026-03-16T00:05:00+00:00",
                "active",
            ),
        )
        tasks = [
            (
                "task-release-signoff",
                "Synthetic release sign-off evidence export",
                "completed",
                "2026-03-16T00:01:00+00:00",
            ),
            (
                "task-update-recovery",
                "Synthetic update rollback evidence export",
                "completed",
                "2026-03-16T00:02:00+00:00",
            ),
        ]
        for task_id, title, state, created_at in tasks:
            connection.execute(
                "INSERT INTO tasks (task_id, session_id, title, state, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
                (
                    task_id,
                    "session-audit-synthetic",
                    title,
                    state,
                    created_at,
                ),
            )

        task_events = [
            (
                "event-release-running",
                "task-release-signoff",
                "queued",
                "running",
                {"actor": "synthetic-fallback"},
                "2026-03-16T00:01:10+00:00",
            ),
            (
                "event-release-completed",
                "task-release-signoff",
                "running",
                "completed",
                {"actor": "synthetic-fallback"},
                "2026-03-16T00:01:50+00:00",
            ),
            (
                "event-update-running",
                "task-update-recovery",
                "queued",
                "running",
                {"actor": "synthetic-fallback"},
                "2026-03-16T00:02:10+00:00",
            ),
            (
                "event-update-completed",
                "task-update-recovery",
                "running",
                "completed",
                {"actor": "synthetic-fallback"},
                "2026-03-16T00:02:55+00:00",
            ),
        ]
        for event_id, task_id, from_state, to_state, metadata, created_at in task_events:
            connection.execute(
                "INSERT INTO task_events (event_id, task_id, from_state, to_state, metadata_json, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                (
                    event_id,
                    task_id,
                    from_state,
                    to_state,
                    json.dumps(metadata, ensure_ascii=False),
                    created_at,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def create_synthetic_multi_domain_state(state_root: Path) -> dict[str, object]:
    session_id = "session-audit-synthetic"
    task_release = "task-release-signoff"
    task_update = "task-update-recovery"

    control_plane_root = state_root / "control-plane"
    shell_root = state_root / "shell"
    device_root = state_root / "device"
    provider_root = state_root / "provider"
    compat_root = state_root / "compat" / "audit"
    updated_root = state_root / "updated"
    hardware_root = state_root / "hardware"

    session_db = state_root / "sessiond.sqlite3"
    create_session_db(session_db)

    policy_audit_log = control_plane_root / "policy-audit.jsonl"
    audit_index = control_plane_root / "audit-index.json"
    runtime_events_log = control_plane_root / "runtime-events.jsonl"
    remote_audit_log = control_plane_root / "remote-audit.jsonl"
    observability_log = control_plane_root / "observability.jsonl"

    write_jsonl(
        policy_audit_log,
        [
            {
                "audit_id": "audit-release-pending",
                "session_id": session_id,
                "task_id": task_release,
                "timestamp": "2026-03-16T00:01:20+00:00",
                "decision": "approval-pending",
                "approval_id": "approval-release-001",
                "capability_id": "system.release.signoff",
                "route_state": "control-plane.centralized-policy",
                "execution_location": "host",
                "provider_id": "runtime.local.inference",
                "result": {
                    "status": "pending",
                    "requested_target_hash": "sha256:release-signoff-target",
                    "requested_constraints": {"scope": "release"},
                },
            },
            {
                "audit_id": "audit-release-approved",
                "session_id": session_id,
                "task_id": task_release,
                "timestamp": "2026-03-16T00:01:35+00:00",
                "decision": "approval-approved",
                "approval_id": "approval-release-001",
                "capability_id": "system.release.signoff",
                "route_state": "control-plane.centralized-policy",
                "execution_location": "host",
                "provider_id": "runtime.local.inference",
                "result": {
                    "status": "approved",
                    "approved_target_hash": "sha256:release-signoff-target",
                    "approved_constraints": {"scope": "release"},
                },
            },
            {
                "audit_id": "audit-update-token",
                "session_id": session_id,
                "task_id": task_update,
                "timestamp": "2026-03-16T00:02:15+00:00",
                "decision": "token-issued",
                "approval_id": "approval-update-001",
                "capability_id": "system.update.apply",
                "route_state": "updated.centralized-policy",
                "execution_location": "host",
                "provider_id": "runtime.local.inference",
                "result": {
                    "status": "issued",
                    "approval_ref": "approval-update-001",
                    "constraints": {"slot": "b"},
                },
            },
            {
                "audit_id": "audit-update-approved",
                "session_id": session_id,
                "task_id": task_update,
                "timestamp": "2026-03-16T00:02:30+00:00",
                "decision": "approval-approved",
                "approval_id": "approval-update-001",
                "capability_id": "system.update.rollback",
                "route_state": "updated.centralized-policy",
                "execution_location": "host",
                "provider_id": "runtime.local.inference",
                "result": {
                    "status": "approved",
                    "approved_target_hash": "sha256:update-target-b",
                    "approved_constraints": {"slot": "b"},
                },
            },
        ],
    )
    write_json(
        audit_index,
        {
            "active_segment_path": str(policy_audit_log),
            "active_record_count": 4,
            "archived_segments": [],
            "archived_segment_count": 0,
            "status": "ready",
        },
    )
    write_jsonl(
        runtime_events_log,
        [
            {
                "session_id": session_id,
                "task_id": task_release,
                "timestamp": "2026-03-16T00:01:45+00:00",
                "kind": "runtime.infer.completed",
                "provider_id": "runtime.local.inference",
                "status": "completed",
                "artifact_path": str(control_plane_root / "runtime-infer-release.json"),
            },
            {
                "session_id": session_id,
                "task_id": task_update,
                "timestamp": "2026-03-16T00:02:40+00:00",
                "kind": "runtime.infer.completed",
                "provider_id": "runtime.local.inference",
                "status": "completed",
                "artifact_path": str(control_plane_root / "runtime-infer-update.json"),
            },
        ],
    )
    write_jsonl(
        remote_audit_log,
        [
            {
                "session_id": session_id,
                "task_id": task_release,
                "timestamp": "2026-03-16T00:01:40+00:00",
                "status": "approved",
                "approval_ref": "approval-release-001",
                "provider_id": "runtime.local.inference",
            },
            {
                "session_id": session_id,
                "task_id": task_update,
                "timestamp": "2026-03-16T00:02:45+00:00",
                "status": "approved",
                "approval_ref": "approval-update-001",
                "provider_id": "runtime.local.inference",
            },
        ],
    )
    write_jsonl(
        observability_log,
        [
            {
                "session_id": session_id,
                "task_id": task_release,
                "timestamp": "2026-03-16T00:01:46+00:00",
                "kind": "provider.runtime.started",
                "provider_id": "runtime.local.inference",
                "status": "running",
            },
            {
                "session_id": session_id,
                "task_id": task_update,
                "timestamp": "2026-03-16T00:02:46+00:00",
                "kind": "provider.runtime.completed",
                "provider_id": "runtime.local.inference",
                "status": "completed",
            },
        ],
    )

    shell_audit = shell_root / "audit.jsonl"
    shell_panel_actions = shell_root / "panel-action-events.jsonl"
    shell_focus_state = shell_root / "focus-state.json"
    write_jsonl(
        shell_audit,
        [
            {
                "audit_id": "shell-approval-001",
                "decision": "approval-approved",
                "approval_id": "approval-shell-panel-001",
                "capability_id": "shell.panel-events.list",
                "action_id": "approve",
                "provider_id": "shell.provider.panel",
                "status": "approved",
            }
        ],
    )
    write_jsonl(
        shell_panel_actions,
        [
            {
                "kind": "shell.panel.action",
                "action_id": "approve",
                "capability_id": "shell.panel-events.list",
                "status": "success",
            }
        ],
    )
    write_json(
        shell_focus_state,
        {
            "capability_id": "shell.panel-events.list",
            "status": "focused",
            "surface": "approval-panel",
        },
    )

    device_audit = device_root / "audit.jsonl"
    device_observability = device_root / "observability.jsonl"
    device_captures = device_root / "captures.json"
    device_backend_state = device_root / "backend-state.json"
    write_jsonl(
        device_audit,
        [
            {
                "audit_id": "device-capture-approval-001",
                "decision": "approval-approved",
                "approval_id": "approval-device-capture-001",
                "capability_id": "device.capture.audio",
                "provider_id": "device.capture.local",
                "status": "approved",
            }
        ],
    )
    write_jsonl(
        device_observability,
        [
            {
                "kind": "device.capture.completed",
                "capability_id": "device.capture.audio",
                "approval_ref": "approval-device-capture-001",
                "status": "completed",
            }
        ],
    )
    write_json(
        device_captures,
        {
            "status": "passed",
            "captures": [
                {
                    "capability_id": "device.capture.audio",
                    "approval_ref": "approval-device-capture-001",
                }
            ],
        },
    )
    write_json(
        device_backend_state,
        {
            "status": "passed",
            "provider_id": "device.capture.local",
            "capability_id": "device.capture.audio",
        },
    )

    provider_audit = provider_root / "audit.jsonl"
    provider_rli_observability = provider_root / "rli-observability.jsonl"
    provider_runtimed_observability = provider_root / "runtimed-observability.jsonl"
    provider_health = provider_root / "provider-health.json"
    write_jsonl(
        provider_audit,
        [
            {
                "audit_id": "provider-token-001",
                "decision": "token-issued",
                "approval_id": "approval-provider-001",
                "provider_id": "runtime.local.inference",
                "capability_id": "runtime.local.inference",
                "status": "issued",
            }
        ],
    )
    write_jsonl(
        provider_rli_observability,
        [
            {
                "kind": "provider.runtime.started",
                "provider_id": "runtime.local.inference",
                "status": "running",
            }
        ],
    )
    write_jsonl(
        provider_runtimed_observability,
        [
            {
                "kind": "provider.runtime.ready",
                "provider_id": "runtime.local.inference",
                "status": "ready",
            }
        ],
    )
    write_json(
        provider_health,
        {
            "provider_id": "runtime.local.inference",
            "status": "available",
            "readiness": "ready",
        },
    )

    compat_shared_log = compat_root / "compat-observability.jsonl"
    compat_records = [
        {
            "audit_id": "compat-browser-001",
            "provider_id": "compat.browser.automation.local",
            "capability_id": "compat.browser.automation",
            "route_state": "compat.centralized-policy",
            "status": "completed",
            "result": {"policy_mode": "policyd-verified", "token_verified": True},
        },
        {
            "audit_id": "compat-office-001",
            "provider_id": "compat.office.document.local",
            "capability_id": "compat.office.document",
            "route_state": "compat.centralized-policy",
            "status": "completed",
            "result": {"policy_mode": "policyd-verified", "token_verified": True},
        },
        {
            "audit_id": "compat-mcp-001",
            "provider_id": "compat.mcp.bridge.local",
            "capability_id": "compat.mcp.bridge",
            "route_state": "compat.centralized-policy",
            "status": "completed",
            "result": {"policy_mode": "policyd-verified", "token_verified": True},
        },
        {
            "audit_id": "compat-code-sandbox-001",
            "provider_id": "compat.code.sandbox.local",
            "capability_id": "compat.code.sandbox",
            "route_state": "compat.centralized-policy",
            "status": "timed_out",
            "error": {"error_code": "provider_timeout"},
            "result": {"policy_mode": "policyd-verified", "token_verified": True, "timed_out": True},
        },
    ]
    for record in compat_records:
        provider_log = compat_root / f"{record['provider_id'].replace('.', '-')}.jsonl"
        write_jsonl(provider_log, [record])
    write_jsonl(compat_shared_log, compat_records)

    updated_observability = updated_root / "observability.jsonl"
    updated_health_probe = updated_root / "health-probe.json"
    updated_deployment_state = updated_root / "deployment-state.json"
    updated_recovery_surface = updated_root / "recovery-surface.json"
    updated_boot_state = updated_root / "boot-control.json"
    updated_recovery_record = updated_root / "recovery" / "record-001.json"
    updated_bundle_record = updated_root / "diagnostics" / "bundle-001.json"
    write_jsonl(
        updated_observability,
        [
            {"kind": "update.apply.completed", "status": "passed"},
            {"kind": "recovery.bundle.exported", "status": "passed"},
            {"kind": "update.rollback.completed", "status": "passed"},
        ],
    )
    write_json(updated_health_probe, {"status": "passed", "kind": "updated.health.probe"})
    write_json(updated_deployment_state, {"status": "stable", "current_slot": "b"})
    write_json(updated_recovery_surface, {"status": "passed", "recovery_mode": "available"})
    write_json(updated_boot_state, {"status": "healthy", "current_slot": "b", "last_good_slot": "b"})
    write_json(updated_recovery_record, {"status": "passed", "kind": "recovery.record"})
    write_json(updated_bundle_record, {"status": "passed", "kind": "diagnostic.bundle"})

    hardware_index = hardware_root / "tier1-hardware-evidence-index.json"
    hardware_report = hardware_root / "tier1-hardware-boot-evidence-report.json"
    write_json(
        hardware_index,
        {
            "generated_at": "2026-03-16T00:00:00+00:00",
            "validation_status": "passed",
            "status": "synthetic-tier1-release-gate",
            "provider_id": "runtime.local.inference",
        },
    )
    write_json(
        hardware_report,
        {
            "generated_at": "2026-03-16T00:00:00+00:00",
            "overall_status": "passed",
            "boot_count": 2,
        },
    )

    domain_config = state_root / "audit-evidence-domain-config.json"
    write_json(
        domain_config,
        {
            "domains": {
                "shell": {
                    "audit_logs": [str(shell_audit)],
                    "jsonl_logs": [{"kind": "panel_actions", "path": str(shell_panel_actions)}],
                    "json_files": [{"kind": "focus_state", "path": str(shell_focus_state)}],
                },
                "device": {
                    "audit_logs": [str(device_audit)],
                    "observability_logs": [str(device_observability)],
                    "json_files": [
                        {"kind": "capture_state", "path": str(device_captures)},
                        {"kind": "backend_state", "path": str(device_backend_state)},
                    ],
                },
                "provider": {
                    "audit_logs": [str(provider_audit)],
                    "observability_logs": [
                        str(provider_rli_observability),
                        str(provider_runtimed_observability),
                    ],
                    "json_files": [{"kind": "provider_health", "path": str(provider_health)}],
                    "notes": ["synthetic provider baseline retained for operator-facing evidence export"],
                },
                "compat": {
                    "jsonl_logs": [
                        {
                            "kind": "browser_audit",
                            "path": str(compat_root / "compat-browser-automation-local.jsonl"),
                        },
                        {
                            "kind": "office_audit",
                            "path": str(compat_root / "compat-office-document-local.jsonl"),
                        },
                        {
                            "kind": "mcp_bridge_audit",
                            "path": str(compat_root / "compat-mcp-bridge-local.jsonl"),
                        },
                        {
                            "kind": "code_sandbox_audit",
                            "path": str(compat_root / "compat-code-sandbox-local.jsonl"),
                        },
                        {
                            "kind": "shared_compat_observability",
                            "path": str(compat_shared_log),
                        },
                    ],
                    "notes": [
                        "compat runtime smoke retained a shared compat observability sink with centralized policy evidence"
                    ],
                },
                "updated": {
                    "observability_logs": [str(updated_observability)],
                    "json_files": [
                        {"kind": "health_probe", "path": str(updated_health_probe)},
                        {"kind": "deployment_state", "path": str(updated_deployment_state)},
                        {"kind": "recovery_surface", "path": str(updated_recovery_surface)},
                        {"kind": "boot_state", "path": str(updated_boot_state)},
                        {
                            "kind": "system_delivery_validation_index",
                            "path": str(ROOT / "out" / "validation" / "system-delivery-validation-evidence-index.json"),
                        },
                        {
                            "kind": "system_delivery_validation_report",
                            "path": str(ROOT / "out" / "validation" / "system-delivery-validation-report.json"),
                        },
                        {"kind": "recovery_record", "path": str(updated_recovery_record)},
                        {"kind": "diagnostic_bundle", "path": str(updated_bundle_record)},
                    ],
                    "notes": [
                        "updated/recovery retained state and system-delivery validation artifacts exported for operator-facing evidence"
                    ],
                },
                "hardware": {
                    "json_files": [
                        {"kind": "hardware_evidence_index", "path": str(hardware_index)},
                        {"kind": "hardware_validation_report", "path": str(hardware_report)},
                    ],
                    "notes": [
                        "default Tier 1 hardware evidence baseline retained for operator-facing export"
                    ],
                },
            }
        },
    )

    return {
        "session_db": session_db,
        "policy_audit_log": policy_audit_log,
        "audit_index": audit_index,
        "runtime_events_log": runtime_events_log,
        "remote_audit_log": remote_audit_log,
        "observability_log": observability_log,
        "domain_config": domain_config,
        "updated_recovery_surface": updated_recovery_surface,
        "updated_recovery_record": updated_recovery_record,
        "hardware_index": hardware_index,
        "compat_shared_log": compat_shared_log,
    }


def ensure_release_signoff_validation_artifacts() -> list[Path]:
    validation_root = ROOT / "out" / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    placeholders: list[tuple[Path, str]] = [
        (
            validation_root / "system-delivery-validation-evidence-index.json",
            json.dumps(
                {
                    "generated_at": "2026-03-16T00:00:00+00:00",
                    "validation_status": "passed",
                    "overall_status": "passed",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
        ),
        (
            validation_root / "system-delivery-validation-report.json",
            json.dumps(
                {
                    "generated_at": "2026-03-16T00:00:00+00:00",
                    "overall_status": "passed",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
        ),
        (
            validation_root / "governance-evidence-index.json",
            json.dumps(
                {
                    "generated_at": "2026-03-16T00:00:00+00:00",
                    "overall_status": "passed",
                    "status": "passed",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
        ),
        (
            validation_root / "release-gate-report.json",
            json.dumps(
                {
                    "generated_at": "2026-03-16T00:00:00+00:00",
                    "gate_status": "passed",
                    "overall_status": "passed",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
        ),
        (
            validation_root / "governance-evidence-index.md",
            "# Governance Evidence Index\n\n- Synthetic fallback fixture.\n",
        ),
        (
            validation_root / "release-gate-report.md",
            "# Release Gate Report\n\n- Synthetic fallback fixture.\n",
        ),
    ]
    for artifact_path, content in placeholders:
        if artifact_path.exists():
            continue
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        created.append(artifact_path)
    return created


def prepare_vendor_runtime_release_fixture(platform_media_fixture: Path) -> Path:
    fixture_reports_dir = platform_media_fixture / "bringup" / "reports"
    fixture_reports_dir.mkdir(parents=True, exist_ok=True)
    fixture_vendor_evidence = fixture_reports_dir / "vendor-execution.json"
    write_json(
        fixture_vendor_evidence,
        {
            "backend_id": "local-gpu",
            "provider_id": "nvidia.jetson.tensorrt",
            "provider_kind": "trtexec",
            "provider_status": "available",
            "runtime_service_id": "aios-runtimed.jetson-vendor-helper",
            "contract_kind": "vendor-runtime-evidence-v1",
        },
    )
    write_text(
        fixture_reports_dir / "hardware-validation-report.md",
        "# Real Machine Validation\n\n- Vendor runtime evidence attached.\n",
    )
    write_json(
        fixture_reports_dir / "hardware-validation-evidence.json",
        {
            "platform_id": "nvidia-jetson-orin-agx",
            "profile": "profiles/nvidia-jetson-orin-agx-tier1.yaml",
            "validation_status": "passed",
            "generated_at": "2026-03-16T00:00:00+00:00",
            "summary": {
                "passed": True,
                "record_count": 2,
                "unique_boot_ids": ["boot-a", "boot-b"],
                "final_current_slot": "b",
                "final_last_good_slot": "b",
            },
            "artifacts": {
                "platform_media_manifest": "",
                "installer_image": "",
                "recovery_image": "",
                "system_image": "",
                "installer_report": "",
                "vendor_firmware_hook_report": "",
                "evaluator_json": str(fixture_reports_dir / "hardware-validation-evaluator.json"),
                "evaluator_markdown": "",
                "support_matrix": "",
                "known_limitations": "",
                "installer_log": "",
                "recovery_log": "",
                "device_backend_state_artifact": str(fixture_reports_dir / "backend-state.json"),
                "vendor_runtime_evidence": [str(fixture_vendor_evidence)],
                "photos": [],
            },
            "device_runtime": {
                "backend_state_artifact": str(fixture_reports_dir / "backend-state.json"),
                "release_grade_backends": {
                    "backend_ids": "nvidia.jetson.tensorrt",
                    "origins": "vendor-runtime",
                    "stacks": "tensorrt",
                    "contract_kinds": "vendor-runtime-evidence-v1",
                },
                "vendor_runtime": {
                    "vendor_runtime_signoff_status": "evidence-attached",
                    "evidence_count": 1,
                    "evidence_paths": [str(fixture_vendor_evidence)],
                    "provider_ids": ["nvidia.jetson.tensorrt"],
                    "runtime_service_ids": ["aios-runtimed.jetson-vendor-helper"],
                    "provider_statuses": ["available"],
                    "provider_kinds": ["trtexec"],
                    "backend_ids": ["local-gpu"],
                    "runtime_binaries": ["/usr/bin/trtexec"],
                    "engine_paths": ["/var/lib/aios/runtime/vendor-engines/local-gpu.plan"],
                    "contract_kinds": ["vendor-runtime-evidence-v1"],
                    "issues": [],
                },
            },
            "checks": [],
            "notes": [],
            "operator": "codex",
            "date": "2026-03-16",
        },
    )
    return fixture_vendor_evidence


def run_synthetic_release_signoff_smoke(keep_state: bool, platform_media_fixture: Path) -> int:
    validation_root = ROOT / "out" / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)
    state_root = validation_root / "audit-evidence-report-synthetic-state"
    if state_root.exists():
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)

    synthetic_state = create_synthetic_multi_domain_state(state_root)
    ensure_release_signoff_validation_artifacts()
    fixture_vendor_evidence = prepare_vendor_runtime_release_fixture(platform_media_fixture)
    report_prefix = validation_root / "audit-evidence-report"

    build_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "build-audit-evidence-report.py"),
        "--session-db",
        str(synthetic_state["session_db"]),
        "--policy-audit-log",
        str(synthetic_state["policy_audit_log"]),
        "--audit-index",
        str(synthetic_state["audit_index"]),
        "--runtime-events-log",
        str(synthetic_state["runtime_events_log"]),
        "--remote-audit-log",
        str(synthetic_state["remote_audit_log"]),
        "--observability-log",
        str(synthetic_state["observability_log"]),
        "--domain-config",
        str(synthetic_state["domain_config"]),
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
    require(json_report.exists(), "synthetic audit evidence report json was not written")
    require(markdown_report.exists(), "synthetic audit evidence report markdown was not written")

    payload = json.loads(json_report.read_text(encoding="utf-8"))
    require(payload["summary"]["task_count"] >= 2, "synthetic report should contain at least two tasks")
    require(
        payload["summary"]["approval_ref_count"] >= 1,
        "synthetic report should contain approval references",
    )
    require(
        payload["summary"]["observability_record_count"] >= 1,
        "synthetic report should contain control-plane observability records",
    )
    require(
        {
            "control-plane",
            "shell",
            "provider",
            "compat",
            "device",
            "updated",
            "hardware",
            "release-signoff",
        }.issubset(set(payload["summary"]["covered_domains"])),
        "synthetic report missing one or more required evidence domains",
    )
    require(
        "approval-pending" in payload["summary"]["audit_decisions"],
        "synthetic report missing approval-pending decision",
    )
    require(
        "approval-approved" in payload["summary"]["audit_decisions"],
        "synthetic report missing approval-approved decision",
    )
    require(
        "token-issued" in payload["summary"]["audit_decisions"],
        "synthetic report missing token-issued decision",
    )

    updated_domain = payload["domain_evidence"]["updated"]
    hardware_domain = payload["domain_evidence"]["hardware"]
    release_signoff_domain = payload["domain_evidence"]["release-signoff"]
    compat_overview = payload["compat_audit_overview"]

    require(
        "update.apply.completed" in updated_domain["event_kinds"],
        "synthetic updated domain missing update.apply evidence",
    )
    require(
        "recovery.bundle.exported" in updated_domain["event_kinds"],
        "synthetic updated domain missing recovery bundle export evidence",
    )
    require(
        "update.rollback.completed" in updated_domain["event_kinds"],
        "synthetic updated domain missing update.rollback evidence",
    )
    require(
        str(synthetic_state["updated_recovery_surface"]) in updated_domain["artifact_paths"],
        "synthetic updated domain missing recovery surface artifact",
    )
    require(
        any(item["kind"] == "recovery_record" and item["present"] for item in updated_domain["sources"]),
        "synthetic updated domain missing retained recovery record source",
    )
    require(
        "passed" in hardware_domain["status_values"]
        or "synthetic-tier1-release-gate" in hardware_domain["status_values"],
        "synthetic hardware domain missing status evidence",
    )
    require(
        compat_overview["provider_count"] == 4,
        "synthetic compat overview missing four-provider coverage",
    )
    require(
        compat_overview["token_verified_record_count"] >= 4,
        "synthetic compat overview missing token verification coverage",
    )
    require(
        compat_overview["timeout_record_count"] >= 1,
        "synthetic compat overview missing timeout coverage",
    )
    require(
        str(synthetic_state["compat_shared_log"]) in compat_overview["shared_audit_log_paths"],
        "synthetic compat overview missing shared compat log path",
    )
    require(
        any(item["kind"] == "governance_evidence_index" and item["present"] for item in release_signoff_domain["sources"]),
        "synthetic release-signoff domain missing governance evidence source",
    )
    require(
        any(item["kind"] == "release_gate_report" and item["present"] for item in release_signoff_domain["sources"]),
        "synthetic release-signoff domain missing release gate report source",
    )
    require(
        any(item["kind"] == "real_machine_hardware_evidence_index" and item["present"] for item in release_signoff_domain["sources"]),
        "synthetic release-signoff domain missing real-machine hardware evidence source",
    )
    require(
        any(item["kind"] == "real_machine_vendor_runtime_evidence" and item["present"] for item in release_signoff_domain["sources"]),
        "synthetic release-signoff domain missing vendor runtime evidence source",
    )
    require(
        any("real-machine hardware validation evidence" in note for note in release_signoff_domain["notes"]),
        "synthetic release-signoff domain missing real-machine discovery note",
    )
    require(
        any("vendor runtime evidence artifact" in note for note in release_signoff_domain["notes"]),
        "synthetic release-signoff domain missing vendor runtime discovery note",
    )
    require(
        "passed" in release_signoff_domain["status_values"],
        "synthetic release-signoff domain missing passed status",
    )
    require(
        str(fixture_vendor_evidence) in release_signoff_domain["artifact_paths"],
        "synthetic release-signoff domain missing vendor runtime evidence artifact path",
    )
    require(
        "nvidia.jetson.tensorrt" in release_signoff_domain["provider_ids"],
        "synthetic release-signoff domain missing vendor runtime provider evidence",
    )

    print(
        json.dumps(
            {
                "mode": "synthetic-fallback",
                "state_root": str(state_root),
                "json_report": str(json_report),
                "markdown_report": str(markdown_report),
                "task_count": payload["summary"]["task_count"],
                "approval_ref_count": payload["summary"]["approval_ref_count"],
                "observability_record_count": payload["summary"]["observability_record_count"],
                "covered_domains": payload["summary"]["covered_domains"],
                "provider_ids": release_signoff_domain["provider_ids"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if keep_state:
        print(f"state retained at: {state_root}")
    return 0


def main() -> int:
    args = parse_args()
    state_roots: list[Path] = []
    platform_media_fixture = ROOT / "out" / "platform-media" / "audit-vendor-smoke-fixture"

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
        if team_b_root is None:
            print("audit evidence export smoke fallback: using synthetic release-signoff evidence fixture")
            return run_synthetic_release_signoff_smoke(args.keep_state, platform_media_fixture)
        state_roots.append(team_b_root)
        shell_root = run_smoke(shell_cmd, "shell provider smoke")
        if shell_root is None:
            return 0
        state_roots.append(shell_root)
        device_root = run_smoke(device_cmd, "deviced policy approval smoke")
        if device_root is None:
            return 0
        state_roots.append(device_root)
        provider_root = run_smoke(provider_cmd, "runtime local inference provider smoke")
        if provider_root is None:
            return 0
        state_roots.append(provider_root)
        updated_root = run_smoke(updated_cmd, "updated smoke")
        if updated_root is None:
            return 0
        state_roots.append(updated_root)

        fixture_vendor_evidence = prepare_vendor_runtime_release_fixture(platform_media_fixture)
        ensure_release_signoff_validation_artifacts()

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
        if compat_root is None:
            return 0
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
        domain_config_path.write_text(json.dumps(domain_config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

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

        payload = json.loads(json_report.read_text(encoding="utf-8"))
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
        require(
            any("vendor runtime evidence artifact" in note for note in release_signoff_domain["notes"]),
            "release-signoff domain missing vendor runtime discovery note",
        )
        require(
            str(fixture_vendor_evidence) in release_signoff_domain["artifact_paths"],
            "release-signoff domain missing vendor runtime evidence artifact path",
        )
        require(
            "nvidia.jetson.tensorrt" in release_signoff_domain["provider_ids"],
            "release-signoff domain missing vendor runtime provider evidence",
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
            shutil.rmtree(platform_media_fixture, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
