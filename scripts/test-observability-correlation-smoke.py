#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "cross-service-correlation-report"
SESSIOND_MIGRATIONS = [
    ROOT / "aios" / "services" / "sessiond" / "migrations" / "0001_init.sql",
    ROOT / "aios" / "services" / "sessiond" / "migrations" / "0002_task_events.sql",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS observability correlation smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing compiled binaries")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--keep-state", action="store_true")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def extract_state_root(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith("state retained at:"):
            return Path(line.split(":", 1)[1].strip())
        if line.startswith("state retained at "):
            return Path(line.removeprefix("state retained at ").strip())
    raise RuntimeError("failed to parse retained state root from team-b smoke output")


def extract_skip_reason(stdout: str, stderr: str) -> str | None:
    for line in [*stdout.splitlines(), *stderr.splitlines()]:
        if line.startswith("team-b control-plane smoke skipped:"):
            return line.split(":", 1)[1].strip()
    return None


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in records)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def write_runtime_export_bundle(
    state_root: Path,
    runtime_events: list[dict[str, object]],
    remote_audits: list[dict[str, object]],
    observability_records: list[dict[str, object]],
) -> Path:
    export_root = state_root / "runtimed" / "exports" / "runtime-observability-synthetic"
    runtime_events_path = export_root / "runtime-events.jsonl"
    remote_audit_path = export_root / "attested-remote-audit.jsonl"
    observability_path = export_root / "observability.jsonl"
    manifest_path = export_root / "manifest.json"
    write_jsonl(runtime_events_path, runtime_events)
    write_jsonl(remote_audit_path, remote_audits)
    write_jsonl(observability_path, observability_records)

    task_ids = sorted(
        {
            str(item.get("task_id"))
            for item in [*runtime_events, *remote_audits, *observability_records]
            if isinstance(item.get("task_id"), str) and item.get("task_id")
        }
    )
    backend_ids = sorted(
        {
            str(item.get("backend_id"))
            for item in [*runtime_events, *remote_audits, *observability_records]
            if isinstance(item.get("backend_id"), str) and item.get("backend_id")
        }
    )
    artifact_paths = sorted(
        {
            str(item.get("artifact_path"))
            for item in [*runtime_events, *remote_audits, *observability_records]
            if isinstance(item.get("artifact_path"), str) and item.get("artifact_path")
        }
    )
    manifest = {
        "export_id": "runtime-observability-synthetic",
        "created_at": "2026-03-16T00:03:00+00:00",
        "service_id": "aios-runtimed",
        "counts": {
            "runtime_event_count": len(runtime_events),
            "observability_count": len(observability_records),
            "remote_audit_count": len(remote_audits),
            "backend_count": len(backend_ids),
            "correlated_task_count": len(task_ids),
            "artifact_count": len(artifact_paths),
        },
        "correlation": {
            "task_ids": task_ids,
            "backend_ids": backend_ids,
            "artifact_paths": artifact_paths,
        },
        "exported_artifacts": {
            "manifest_path": str(manifest_path),
            "runtime_events_path": str(runtime_events_path),
            "remote_audit_path": str(remote_audit_path),
            "observability_path": str(observability_path),
        },
        "runtime_events": runtime_events,
        "remote_audit": remote_audits,
        "observability": observability_records,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def find_runtime_export_manifest(state_root: Path) -> Path | None:
    export_root = state_root / "runtimed" / "exports"
    if not export_root.exists():
        return None
    manifests = sorted(export_root.glob("*/manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return manifests[0] if manifests else None


def create_session_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for migration in SESSIOND_MIGRATIONS:
            connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO sessions (session_id, user_id, metadata_json, created_at, last_resumed_at, status) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            (
                "session-correlation",
                "user-correlation",
                json.dumps({"source": "synthetic-fallback"}, ensure_ascii=False),
                "2026-03-16T00:00:00+00:00",
                "2026-03-16T00:10:00+00:00",
                "active",
            ),
        )
        connection.executemany(
            "INSERT INTO tasks (task_id, session_id, title, state, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            [
                (
                    "task-runtime",
                    "session-correlation",
                    "GPU vendor runtime correlation",
                    "completed",
                    "2026-03-16T00:01:00+00:00",
                ),
                (
                    "task-approval",
                    "session-correlation",
                    "Approval audit correlation",
                    "waiting-approval",
                    "2026-03-16T00:02:00+00:00",
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO task_events (event_id, task_id, from_state, to_state, metadata_json, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            [
                (
                    "event-runtime-1",
                    "task-runtime",
                    "queued",
                    "running",
                    json.dumps({"route_state": "attested-remote"}, ensure_ascii=False),
                    "2026-03-16T00:01:10+00:00",
                ),
                (
                    "event-runtime-2",
                    "task-runtime",
                    "running",
                    "completed",
                    json.dumps({"provider_id": "nvidia.jetson.tensorrt"}, ensure_ascii=False),
                    "2026-03-16T00:01:20+00:00",
                ),
                (
                    "event-approval-1",
                    "task-approval",
                    "queued",
                    "waiting-approval",
                    json.dumps({"approval_id": "approval-runtime-1"}, ensure_ascii=False),
                    "2026-03-16T00:02:10+00:00",
                ),
            ],
        )
        connection.execute(
            "INSERT INTO task_plans (task_id, plan_json, updated_at) VALUES (?1, ?2, ?3)",
            (
                "task-runtime",
                json.dumps({"steps": [{"step": "run vendor backend", "status": "completed"}]}, ensure_ascii=False),
                "2026-03-16T00:01:05+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO memory_working_refs (ref_id, session_id, payload_json, created_at) VALUES (?1, ?2, ?3, ?4)",
            (
                "wm-runtime-1",
                "session-correlation",
                json.dumps({"task_id": "task-runtime", "kind": "runtime-context"}, ensure_ascii=False),
                "2026-03-16T00:01:15+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO memory_episodic_entries (entry_id, session_id, summary, metadata_json, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            (
                "ep-runtime-1",
                "session-correlation",
                "Vendor runtime execution evidence captured.",
                json.dumps({"task_id": "task-runtime"}, ensure_ascii=False),
                "2026-03-16T00:01:30+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def build_report(report_prefix: Path, state_root: Path, runtime_export: Path | None = None) -> dict:
    session_db = resolve_state_path(
        state_root,
        "sessiond.sqlite3",
        "sessiond/sessiond.sqlite3",
    )
    policy_audit_log = resolve_state_path(
        state_root,
        "audit.jsonl",
        "policyd/audit.jsonl",
    )
    build_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "build-observability-correlation-report.py"),
        "--session-db",
        str(session_db),
        "--policy-audit-log",
        str(policy_audit_log),
    ]
    if runtime_export is not None:
        build_cmd.extend([
            "--runtime-observability-export",
            str(runtime_export),
        ])
    else:
        build_cmd.extend([
            "--runtime-events-log",
            str(resolve_state_path(state_root, "runtime-events.jsonl", "runtimed/runtime-events.jsonl")),
            "--remote-audit-log",
            str(resolve_state_path(state_root, "remote-audit.jsonl", "runtimed/remote-audit.jsonl")),
            "--observability-log",
            str(resolve_state_path(state_root, "observability.jsonl", "runtimed/observability.jsonl")),
        ])
    build_cmd.extend([
        "--output-prefix",
        str(report_prefix),
    ])
    build_completed = subprocess.run(build_cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if build_completed.returncode != 0:
        sys.stdout.write(build_completed.stdout)
        sys.stderr.write(build_completed.stderr)
        raise SystemExit(build_completed.returncode)

    json_report = report_prefix.with_suffix(".json")
    require(json_report.exists(), "correlation report json was not written")
    return json.loads(json_report.read_text(encoding="utf-8"))


def resolve_state_path(state_root: Path, *relative_candidates: str) -> Path:
    for relative in relative_candidates:
        candidate = state_root / relative
        if candidate.exists():
            return candidate
    return state_root / relative_candidates[0]


def assert_baseline_report(payload: dict) -> None:
    require(payload["summary"]["task_count"] >= 2, "expected at least two correlated tasks")
    require(payload["summary"]["audit_entry_count"] >= 2, "expected correlated audit entries")
    require(payload["summary"]["runtime_event_count"] >= 1, "expected correlated runtime events")
    require(isinstance(payload["summary"].get("provider_ids"), list), "correlation report summary missing provider_ids list")
    require(
        isinstance(payload["summary"].get("runtime_service_ids"), list),
        "correlation report summary missing runtime_service_ids list",
    )
    require(
        isinstance(payload["summary"].get("provider_statuses"), list),
        "correlation report summary missing provider_statuses list",
    )
    require(
        isinstance(payload["summary"].get("artifact_paths"), list),
        "correlation report summary missing artifact_paths list",
    )
    require(
        isinstance(payload["summary"].get("backend_ids"), list),
        "correlation report summary missing backend_ids list",
    )

    correlations = {item["task_id"]: item for item in payload["correlations"]}
    require(
        any("runtime.infer.completed" in item["runtime_event_kinds"] for item in correlations.values()),
        "correlation report missing runtime completion event",
    )
    require(
        any("approval-pending" in item["audit_decisions"] for item in correlations.values()),
        "correlation report missing approval-pending decision",
    )
    require(
        any("approval-approved" in item["audit_decisions"] for item in correlations.values()),
        "correlation report missing approval-approved decision",
    )
    require(
        any("task.state.updated" in item["observability_kinds"] for item in correlations.values()),
        "correlation report missing sessiond lifecycle observability records",
    )


def assert_vendor_metadata(payload: dict, vendor_evidence: Path) -> None:
    correlations = {item["task_id"]: item for item in payload["correlations"]}
    require(
        "nvidia.jetson.tensorrt" in payload["summary"].get("provider_ids", []),
        "correlation report summary missing vendor provider id",
    )
    require(
        "aios-runtimed.jetson-vendor-helper" in payload["summary"].get("runtime_service_ids", []),
        "correlation report summary missing runtime service id",
    )
    require(
        "available" in payload["summary"].get("provider_statuses", []),
        "correlation report summary missing provider status",
    )
    require(
        str(vendor_evidence) in payload["summary"].get("artifact_paths", []),
        "correlation report summary missing vendor evidence artifact",
    )
    require(
        "local-gpu" in payload["summary"].get("backend_ids", []),
        "correlation report summary missing backend id",
    )
    runtime_task = correlations.get("task-runtime")
    require(runtime_task is not None, "correlation report missing task-runtime entry")
    require(
        "nvidia.jetson.tensorrt" in runtime_task.get("provider_ids", []),
        "task-runtime correlation missing provider id",
    )
    require(
        "aios-runtimed.jetson-vendor-helper" in runtime_task.get("runtime_service_ids", []),
        "task-runtime correlation missing runtime service id",
    )
    require(
        "available" in runtime_task.get("provider_statuses", []),
        "task-runtime correlation missing provider status",
    )
    require(
        str(vendor_evidence) in runtime_task.get("artifact_paths", []),
        "task-runtime correlation missing vendor evidence artifact",
    )
    require(
        "local-gpu" in runtime_task.get("backend_ids", []),
        "task-runtime correlation missing backend id",
    )


def run_synthetic_fallback(keep_state: bool) -> int:
    temp_root = DEFAULT_OUTPUT_PREFIX.parent / f"{DEFAULT_OUTPUT_PREFIX.name}-synthetic-state"
    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        state_root = temp_root / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        create_session_db(state_root / "sessiond.sqlite3")

        vendor_evidence = state_root / "vendor-execution.json"
        vendor_evidence.write_text(
            json.dumps(
                {
                    "backend_id": "local-gpu",
                    "provider_id": "nvidia.jetson.tensorrt",
                    "provider_status": "available",
                    "runtime_service_id": "aios-runtimed.jetson-vendor-helper",
                    "contract_kind": "vendor-runtime-evidence-v1",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        write_jsonl(
            state_root / "audit.jsonl",
            [
                {
                    "timestamp": "2026-03-16T00:01:00+00:00",
                    "session_id": "session-correlation",
                    "task_id": "task-runtime",
                    "decision": "approval-pending",
                    "capability_id": "runtime.infer.submit",
                    "approval_id": "approval-runtime-1",
                    "provider_id": "runtime.local.inference",
                    "selected_provider_id": "nvidia.jetson.tensorrt",
                },
                {
                    "timestamp": "2026-03-16T00:02:00+00:00",
                    "session_id": "session-correlation",
                    "task_id": "task-approval",
                    "decision": "approval-approved",
                    "capability_id": "runtime.infer.submit",
                    "provider_id": "runtime.local.inference",
                    "result": {"approval_ref": "approval-runtime-1"},
                },
            ],
        )
        runtime_event_records = [
            {
                "timestamp": "2026-03-16T00:01:20+00:00",
                "session_id": "session-correlation",
                "task_id": "task-runtime",
                "kind": "runtime.infer.completed",
                "backend_id": "local-gpu",
                "provider_id": "nvidia.jetson.tensorrt",
                "runtime_service_id": "aios-runtimed.jetson-vendor-helper",
                "provider_status": "available",
                "artifact_path": str(vendor_evidence),
            }
        ]
        remote_audit_records = [
            {
                "timestamp": "2026-03-16T00:01:21+00:00",
                "session_id": "session-correlation",
                "task_id": "task-runtime",
                "status": "completed",
                "backend_id": "local-gpu",
                "provider_id": "nvidia.jetson.tensorrt",
                "runtime_service_id": "aios-runtimed.jetson-vendor-helper",
                "provider_status": "available",
                "artifact_path": str(vendor_evidence),
            }
        ]
        observability_records = [
            {
                "timestamp": "2026-03-16T00:01:25+00:00",
                "session_id": "session-correlation",
                "task_id": "task-runtime",
                "kind": "task.state.updated",
                "backend_id": "local-gpu",
                "provider_id": "nvidia.jetson.tensorrt",
                "runtime_service_id": "aios-runtimed.jetson-vendor-helper",
                "provider_status": "available",
                "artifact_path": str(vendor_evidence),
            },
            {
                "timestamp": "2026-03-16T00:02:05+00:00",
                "session_id": "session-correlation",
                "task_id": "task-approval",
                "kind": "task.state.updated",
            },
        ]
        write_jsonl(state_root / "runtime-events.jsonl", runtime_event_records)
        write_jsonl(state_root / "remote-audit.jsonl", remote_audit_records)
        write_jsonl(state_root / "observability.jsonl", observability_records)
        runtime_export = write_runtime_export_bundle(
            state_root,
            runtime_event_records,
            remote_audit_records,
            observability_records,
        )

        report_prefix = DEFAULT_OUTPUT_PREFIX
        payload = build_report(report_prefix, state_root, runtime_export=runtime_export)
        assert_baseline_report(payload)
        assert_vendor_metadata(payload, vendor_evidence)
        print(
            json.dumps(
                {
                    "mode": "synthetic-fallback",
                    "state_root": str(temp_root),
                    "json_report": str(report_prefix.with_suffix(".json")),
                    "markdown_report": str(report_prefix.with_suffix(".md")),
                    "task_count": payload["summary"]["task_count"],
                    "provider_ids": payload["summary"]["provider_ids"],
                    "runtime_service_ids": payload["summary"]["runtime_service_ids"],
                    "backend_ids": payload["summary"].get("backend_ids", []),
                    "runtime_export": str(runtime_export),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        print(f"state retained at: {temp_root}")


def main() -> int:
    args = parse_args()
    team_b_cmd = [sys.executable, str(ROOT / "scripts" / "test-team-b-control-plane-smoke.py"), "--keep-state", "--timeout", str(args.timeout)]
    if args.bin_dir is not None:
        team_b_cmd.extend(["--bin-dir", str(args.bin_dir)])

    completed = subprocess.run(team_b_cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)

    skip_reason = extract_skip_reason(completed.stdout, completed.stderr)
    if skip_reason is not None:
        print(f"observability correlation smoke fallback: {skip_reason}")
        return run_synthetic_fallback(args.keep_state)

    state_root = extract_state_root(completed.stdout)
    runtime_export = find_runtime_export_manifest(state_root / "state")
    require(runtime_export is not None, "team-b control-plane smoke did not leave a runtime export manifest")
    report_prefix = ROOT / "out" / "validation" / "cross-service-correlation-report"
    payload = build_report(report_prefix, state_root / "state", runtime_export=runtime_export)
    assert_baseline_report(payload)

    print(
        json.dumps(
            {
                "mode": "end-to-end",
                "state_root": str(state_root),
                "json_report": str(report_prefix.with_suffix(".json")),
                "markdown_report": str(report_prefix.with_suffix(".md")),
                "task_count": payload["summary"]["task_count"],
                "audit_entry_count": payload["summary"]["audit_entry_count"],
                "runtime_event_count": payload["summary"]["runtime_event_count"],
                "provider_ids": payload["summary"]["provider_ids"],
                "runtime_service_ids": payload["summary"]["runtime_service_ids"],
                "backend_ids": payload["summary"].get("backend_ids", []),
                "runtime_export": str(runtime_export),
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    if not args.keep_state:
        shutil.rmtree(state_root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


