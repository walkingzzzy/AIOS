#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "cross-service-correlation-report"
CORRELATION_REPORT_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "cross-service-correlation-report.schema.json"
PROVIDER_KEYS = {"provider_id", "selected_provider_id"}
RUNTIME_SERVICE_KEYS = {"runtime_service_id"}
PROVIDER_STATUS_KEYS = {"provider_status"}
BACKEND_KEYS = {"backend_id", "resolved_backend", "fallback_backend", "selected_backend", "requested_backend", "actual_backend"}
ARTIFACT_KEYS = {
    "artifact_path",
    "evidence_path",
    "evidence_paths",
    "vendor_runtime_evidence",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AIOS cross-service observability correlation report")
    parser.add_argument("--session-db", type=Path, required=True)
    parser.add_argument("--policy-audit-log", type=Path)
    parser.add_argument("--runtime-events-log", type=Path)
    parser.add_argument("--remote-audit-log", type=Path)
    parser.add_argument("--observability-log", type=Path)
    parser.add_argument("--runtime-observability-export", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def build_validator(path: Path) -> Draft202012Validator:
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(json.loads(stripped))
    return records


def load_runtime_export(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"runtime observability export must be a JSON object: {path}")
    return payload


def runtime_export_records(
    runtime_export: dict[str, Any] | None,
    artifact_key: str,
    payload_key: str,
) -> list[dict[str, Any]]:
    if runtime_export is None:
        return []
    artifacts = runtime_export.get("exported_artifacts")
    if isinstance(artifacts, dict):
        artifact_path = artifacts.get(artifact_key)
        if isinstance(artifact_path, str) and artifact_path:
            records = read_jsonl(Path(artifact_path))
            if records:
                return records
    records = runtime_export.get(payload_key)
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    return []

def query_one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    cursor = connection.execute(sql, params)
    return cursor.fetchone()


def query_all(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    cursor = connection.execute(sql, params)
    return cursor.fetchall()


def resolve_session_id(connection: sqlite3.Connection, requested: str | None) -> str:
    if requested:
        return requested
    rows = query_all(connection, "SELECT session_id FROM sessions ORDER BY created_at DESC", ())
    if len(rows) != 1:
        raise SystemExit("session_id is required when session database contains zero or multiple sessions")
    return str(rows[0]["session_id"])


def parse_json_column(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    return json.loads(value)


def collect_strings(value: Any, keys: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                if isinstance(item, str) and item:
                    found.add(item)
                elif isinstance(item, list):
                    for child in item:
                        if isinstance(child, str) and child:
                            found.add(child)
            if isinstance(item, (dict, list)):
                found.update(collect_strings(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.update(collect_strings(item, keys))
    return found


def task_id_from_memory_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        raw = payload.get("task_id")
        if isinstance(raw, str) and raw:
            return raw
    return None


def approval_refs_from_audit(entries: list[dict[str, Any]]) -> list[str]:
    refs: set[str] = set()
    for entry in entries:
        raw = entry.get("approval_id")
        if isinstance(raw, str) and raw:
            refs.add(raw)
        result = entry.get("result")
        if isinstance(result, dict):
            raw = result.get("approval_ref")
            if isinstance(raw, str) and raw:
                refs.add(raw)
    return sorted(refs)


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Cross-Service Correlation Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Session: `{report['session']['session_id']}`",
        f"- User: `{report['session']['user_id']}`",
        "",
        "## Summary",
        "",
        f"- Tasks: `{report['summary']['task_count']}`",
        f"- Audit entries: `{report['summary']['audit_entry_count']}`",
        f"- Runtime events: `{report['summary']['runtime_event_count']}`",
        f"- Remote audit entries: `{report['summary']['remote_audit_count']}`",
        f"- Observability records: `{report['summary']['observability_record_count']}`",
        f"- Working memory entries: `{report['summary']['working_memory_count']}`",
        f"- Episodic entries: `{report['summary']['episodic_entry_count']}`",
        f"- Providers: `{', '.join(report['summary']['provider_ids']) or '-'}`",
        f"- Runtime services: `{', '.join(report['summary']['runtime_service_ids']) or '-'}`",
        f"- Provider statuses: `{', '.join(report['summary']['provider_statuses']) or '-'}`",
        f"- Backends: `{', '.join(report['summary'].get('backend_ids', [])) or '-'}`",
        f"- Artifacts: `{', '.join(report['summary']['artifact_paths']) or '-'}`",
        "",
        "## Tasks",
        "",
        "| Task | State | Audit Decisions | Runtime Events | Providers | Runtime Services | Backends | Transitions |",
        "|------|-------|-----------------|----------------|-----------|------------------|----------|-------------|",
    ]
    for item in report["correlations"]:
        lines.append(
            "| `{task_id}` | `{state}` | `{audit}` | `{runtime}` | `{providers}` | `{runtime_services}` | `{backends}` | `{transitions}` |".format(
                task_id=item["task_id"],
                state=item.get("state", "unknown"),
                audit=", ".join(item["audit_decisions"]) or "-",
                runtime=", ".join(item["runtime_event_kinds"]) or "-",
                providers=", ".join(item["provider_ids"]) or "-",
                runtime_services=", ".join(item["runtime_service_ids"]) or "-",
                backends=", ".join(item.get("backend_ids", [])) or "-",
                transitions=", ".join(item["state_transitions"]) or "-",
            )
        )
    if report["notes"]:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    validator = build_validator(CORRELATION_REPORT_SCHEMA)
    connection = sqlite3.connect(args.session_db)
    connection.row_factory = sqlite3.Row

    session_id = resolve_session_id(connection, args.session_id)
    session_row = query_one(
        connection,
        "SELECT session_id, user_id, metadata_json, created_at, last_resumed_at, status FROM sessions WHERE session_id = ?1",
        (session_id,),
    )
    if session_row is None:
        raise SystemExit(f"unknown session_id: {session_id}")

    task_rows = query_all(
        connection,
        "SELECT task_id, session_id, state, title, created_at FROM tasks WHERE session_id = ?1 ORDER BY created_at ASC LIMIT ?2",
        (session_id, max(1, args.limit)),
    )

    tasks: list[dict[str, Any]] = []
    task_ids = [str(row["task_id"]) for row in task_rows]
    task_events_by_task: dict[str, list[dict[str, Any]]] = {}
    for task_id in task_ids:
        event_rows = query_all(
            connection,
            "SELECT event_id, task_id, from_state, to_state, metadata_json, created_at FROM task_events WHERE task_id = ?1 ORDER BY created_at ASC LIMIT ?2",
            (task_id, max(1, args.limit)),
        )
        task_events_by_task[task_id] = [
            {
                "event_id": str(row["event_id"]),
                "task_id": str(row["task_id"]),
                "from_state": str(row["from_state"]),
                "to_state": str(row["to_state"]),
                "metadata": parse_json_column(row["metadata_json"], {}),
                "created_at": str(row["created_at"]),
            }
            for row in event_rows
        ]

    plan_by_task: dict[str, Any] = {}
    for row in query_all(
        connection,
        "SELECT task_id, plan_json FROM task_plans WHERE task_id IN ({})".format(",".join("?" for _ in task_ids)) if task_ids else "SELECT task_id, plan_json FROM task_plans WHERE 1=0",
        tuple(task_ids),
    ):
        plan_by_task[str(row["task_id"])] = parse_json_column(row["plan_json"], None)

    for row in task_rows:
        task_id = str(row["task_id"])
        tasks.append(
            {
                "task_id": task_id,
                "session_id": str(row["session_id"]),
                "state": str(row["state"]),
                "title": row["title"],
                "created_at": str(row["created_at"]),
                "plan": plan_by_task.get(task_id),
                "task_events": task_events_by_task.get(task_id, []),
            }
        )

    working_memory_rows = query_all(
        connection,
        "SELECT ref_id, session_id, payload_json, created_at FROM memory_working_refs WHERE session_id = ?1 ORDER BY created_at ASC LIMIT ?2",
        (session_id, max(1, args.limit)),
    )
    working_memory = [
        {
            "ref_id": str(row["ref_id"]),
            "session_id": str(row["session_id"]),
            "payload": parse_json_column(row["payload_json"], {}),
            "created_at": str(row["created_at"]),
        }
        for row in working_memory_rows
    ]

    episodic_rows = query_all(
        connection,
        "SELECT entry_id, session_id, summary, metadata_json, created_at FROM memory_episodic_entries WHERE session_id = ?1 ORDER BY created_at ASC LIMIT ?2",
        (session_id, max(1, args.limit)),
    )
    episodic_memory = [
        {
            "entry_id": str(row["entry_id"]),
            "session_id": str(row["session_id"]),
            "summary": str(row["summary"]),
            "metadata": parse_json_column(row["metadata_json"], {}),
            "created_at": str(row["created_at"]),
        }
        for row in episodic_rows
    ]

    runtime_export = load_runtime_export(args.runtime_observability_export)

    audit_entries = [
        item
        for item in read_jsonl(args.policy_audit_log)
        if item.get("session_id") == session_id
    ]
    runtime_events = [
        item
        for item in (
            read_jsonl(args.runtime_events_log)
            if args.runtime_events_log is not None
            else runtime_export_records(runtime_export, "runtime_events_path", "runtime_events")
        )
        if item.get("session_id") == session_id
    ]
    remote_audits = [
        item
        for item in (
            read_jsonl(args.remote_audit_log)
            if args.remote_audit_log is not None
            else runtime_export_records(runtime_export, "remote_audit_path", "remote_audit")
        )
        if item.get("session_id") == session_id
    ]
    observability_records = [
        item
        for item in (
            read_jsonl(args.observability_log)
            if args.observability_log is not None
            else runtime_export_records(runtime_export, "observability_path", "observability")
        )
        if item.get("session_id") == session_id
    ]

    audit_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    runtime_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    remote_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observability_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    memory_refs_by_task: dict[str, list[str]] = defaultdict(list)
    episodic_by_task: dict[str, list[str]] = defaultdict(list)

    for entry in audit_entries:
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            audit_by_task[task_id].append(entry)
    for entry in runtime_events:
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            runtime_by_task[task_id].append(entry)
    for entry in remote_audits:
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            remote_by_task[task_id].append(entry)
    for entry in observability_records:
        task_id = entry.get("task_id")
        if isinstance(task_id, str) and task_id:
            observability_by_task[task_id].append(entry)
    for entry in working_memory:
        task_id = task_id_from_memory_payload(entry["payload"])
        if task_id:
            memory_refs_by_task[task_id].append(entry["ref_id"])
    for entry in episodic_memory:
        task_id = entry["metadata"].get("task_id") if isinstance(entry["metadata"], dict) else None
        if isinstance(task_id, str) and task_id:
            episodic_by_task[task_id].append(entry["summary"])

    correlations: list[dict[str, Any]] = []
    for task in tasks:
        task_id = task["task_id"]
        task_audits = audit_by_task.get(task_id, [])
        task_runtime = runtime_by_task.get(task_id, [])
        task_remote = remote_by_task.get(task_id, [])
        task_observability = observability_by_task.get(task_id, [])
        state_transitions = [
            f"{item['from_state']}->{item['to_state']}"
            for item in task.get("task_events", [])
        ]
        provider_ids = sorted(
            collect_strings(task_audits, PROVIDER_KEYS)
            | collect_strings(task_runtime, PROVIDER_KEYS)
            | collect_strings(task_remote, PROVIDER_KEYS)
            | collect_strings(task_observability, PROVIDER_KEYS)
        )
        runtime_service_ids = sorted(
            collect_strings(task_runtime, RUNTIME_SERVICE_KEYS)
            | collect_strings(task_remote, RUNTIME_SERVICE_KEYS)
            | collect_strings(task_observability, RUNTIME_SERVICE_KEYS)
        )
        provider_statuses = sorted(
            collect_strings(task_runtime, PROVIDER_STATUS_KEYS)
            | collect_strings(task_remote, PROVIDER_STATUS_KEYS)
            | collect_strings(task_observability, PROVIDER_STATUS_KEYS)
        )
        backend_ids = sorted(
            collect_strings(task_runtime, BACKEND_KEYS)
            | collect_strings(task_remote, BACKEND_KEYS)
            | collect_strings(task_observability, BACKEND_KEYS)
        )
        artifact_paths = sorted(
            collect_strings(task_audits, ARTIFACT_KEYS)
            | collect_strings(task_runtime, ARTIFACT_KEYS)
            | collect_strings(task_remote, ARTIFACT_KEYS)
            | collect_strings(task_observability, ARTIFACT_KEYS)
        )
        correlations.append(
            {
                "task_id": task_id,
                "state": task["state"],
                "audit_decisions": sorted({str(item.get("decision")) for item in task_audits if item.get("decision")}),
                "runtime_event_kinds": sorted({str(item.get("kind")) for item in task_runtime if item.get("kind")}),
                "remote_audit_statuses": sorted({str(item.get("status")) for item in task_remote if item.get("status")}),
                "observability_kinds": sorted({str(item.get("kind")) for item in task_observability if item.get("kind")}),
                "state_transitions": state_transitions,
                "working_memory_refs": sorted(memory_refs_by_task.get(task_id, [])),
                "episodic_summaries": episodic_by_task.get(task_id, []),
                "approval_refs": approval_refs_from_audit(task_audits),
                "provider_ids": provider_ids,
                "runtime_service_ids": runtime_service_ids,
                "provider_statuses": provider_statuses,
                "backend_ids": backend_ids,
                "artifact_paths": artifact_paths,
            }
        )

    report = {
        "report_id": f"corr-{session_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session": {
            "session_id": str(session_row["session_id"]),
            "user_id": str(session_row["user_id"]),
            "status": str(session_row["status"]),
            "created_at": str(session_row["created_at"]),
            "last_resumed_at": session_row["last_resumed_at"],
            "metadata": parse_json_column(session_row["metadata_json"], {}),
        },
        "summary": {
            "task_count": len(tasks),
            "audit_entry_count": len(audit_entries),
            "runtime_event_count": len(runtime_events),
            "remote_audit_count": len(remote_audits),
            "observability_record_count": len(observability_records),
            "working_memory_count": len(working_memory),
            "episodic_entry_count": len(episodic_memory),
            "task_states": sorted({item["state"] for item in tasks}),
            "audit_decisions": sorted({str(item.get("decision")) for item in audit_entries if item.get("decision")}),
            "runtime_event_kinds": sorted({str(item.get("kind")) for item in runtime_events if item.get("kind")}),
            "provider_ids": sorted(
                collect_strings(audit_entries, PROVIDER_KEYS)
                | collect_strings(runtime_events, PROVIDER_KEYS)
                | collect_strings(remote_audits, PROVIDER_KEYS)
                | collect_strings(observability_records, PROVIDER_KEYS)
            ),
            "runtime_service_ids": sorted(
                collect_strings(runtime_events, RUNTIME_SERVICE_KEYS)
                | collect_strings(remote_audits, RUNTIME_SERVICE_KEYS)
                | collect_strings(observability_records, RUNTIME_SERVICE_KEYS)
            ),
            "provider_statuses": sorted(
                collect_strings(runtime_events, PROVIDER_STATUS_KEYS)
                | collect_strings(remote_audits, PROVIDER_STATUS_KEYS)
                | collect_strings(observability_records, PROVIDER_STATUS_KEYS)
            ),
            "backend_ids": sorted(
                collect_strings(runtime_events, BACKEND_KEYS)
                | collect_strings(remote_audits, BACKEND_KEYS)
                | collect_strings(observability_records, BACKEND_KEYS)
            ),
            "artifact_paths": sorted(
                collect_strings(audit_entries, ARTIFACT_KEYS)
                | collect_strings(runtime_events, ARTIFACT_KEYS)
                | collect_strings(remote_audits, ARTIFACT_KEYS)
                | collect_strings(observability_records, ARTIFACT_KEYS)
            ),
        },
        "tasks": tasks,
        "working_memory": working_memory,
        "episodic_memory": episodic_memory,
        "audit_entries": audit_entries,
        "runtime_events": runtime_events,
        "remote_audits": remote_audits,
        "observability_records": observability_records,
        "correlations": correlations,
        "notes": [
            f"session_db={args.session_db}",
            f"policy_audit_log={args.policy_audit_log}" if args.policy_audit_log else "policy_audit_log=missing",
            f"runtime_events_log={args.runtime_events_log}" if args.runtime_events_log else "runtime_events_log=missing",
            f"remote_audit_log={args.remote_audit_log}" if args.remote_audit_log else "remote_audit_log=missing",
            f"observability_log={args.observability_log}" if args.observability_log else "observability_log=missing",
            f"runtime_observability_export={args.runtime_observability_export}" if args.runtime_observability_export else "runtime_observability_export=missing",
        ],
    }

    validator.validate(report)

    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    markdown_path.write_text(build_markdown(report) + "\n")
    print(
        json.dumps(
            {
                "report_id": report["report_id"],
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "session_id": session_id,
                "task_count": report["summary"]["task_count"],
                "audit_entry_count": report["summary"]["audit_entry_count"],
                "runtime_event_count": report["summary"]["runtime_event_count"],
                "provider_ids": report["summary"]["provider_ids"],
                "runtime_service_ids": report["summary"]["runtime_service_ids"],
                "backend_ids": report["summary"].get("backend_ids", []),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


