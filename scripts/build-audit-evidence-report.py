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
SCHEMA_PATH = ROOT / "aios" / "observability" / "schemas" / "audit-evidence-report.schema.json"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "audit-evidence-report"
DOMAIN_NAMES = [
    "control-plane",
    "shell",
    "provider",
    "compat",
    "device",
    "updated",
    "hardware",
    "release-signoff",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AIOS operator-facing audit evidence report")
    parser.add_argument("--session-db", type=Path, required=True)
    parser.add_argument("--policy-audit-log", type=Path)
    parser.add_argument("--audit-index", type=Path)
    parser.add_argument("--runtime-events-log", type=Path)
    parser.add_argument("--remote-audit-log", type=Path)
    parser.add_argument("--observability-log", type=Path)
    parser.add_argument("--domain-config", type=Path, help="Optional JSON file describing shell/provider/compat/device evidence sources")
    parser.add_argument("--session-id")
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


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


def read_optional_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    return load_json(path)


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


def path_string(path: Path | None) -> str | None:
    return str(path) if path is not None else None


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


def collect_task_ids(records: list[dict[str, Any]]) -> set[str]:
    return {
        str(item["task_id"])
        for item in records
        if isinstance(item.get("task_id"), str) and item["task_id"]
    }


def sorted_unique_strings(values: list[Any]) -> list[str]:
    return sorted({str(item) for item in values if isinstance(item, str) and item})


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def normalize_source_items(raw_items: Any, fallback_kind: str, fallback_format: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(raw_items, list):
        return items
    for raw_item in raw_items:
        if isinstance(raw_item, str) and raw_item:
            items.append({"kind": fallback_kind, "path": raw_item, "format": fallback_format})
            continue
        if not isinstance(raw_item, dict):
            continue
        path = raw_item.get("path")
        if not isinstance(path, str) or not path:
            continue
        kind = raw_item.get("kind") if isinstance(raw_item.get("kind"), str) and raw_item.get("kind") else fallback_kind
        fmt = raw_item.get("format") if isinstance(raw_item.get("format"), str) and raw_item.get("format") else fallback_format
        items.append({"kind": kind, "path": path, "format": fmt})
    return items


def dedupe_source_specs(source_specs: list[dict[str, str]]) -> list[dict[str, str]]:
    unique_specs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for spec in source_specs:
        key = (spec["kind"], spec["path"], spec["format"])
        if key in seen:
            continue
        seen.add(key)
        unique_specs.append(spec)
    return unique_specs


def load_domain_config(path: Path | None, notes: list[str]) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        notes.append(f"input file missing: domain_config={path}")
        return {}
    payload = load_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("domains"), dict):
        return dict(payload["domains"])
    if isinstance(payload, dict):
        return payload
    notes.append(f"domain config must be a JSON object: {path}")
    return {}


def build_domain_source_specs(raw_domain: Any) -> list[dict[str, str]]:
    if not isinstance(raw_domain, dict):
        return []
    sources: list[dict[str, str]] = []
    sources.extend(normalize_source_items(raw_domain.get("audit_logs"), "audit_log", "jsonl"))
    sources.extend(normalize_source_items(raw_domain.get("observability_logs"), "observability_log", "jsonl"))
    sources.extend(normalize_source_items(raw_domain.get("jsonl_logs"), "jsonl_log", "jsonl"))
    sources.extend(normalize_source_items(raw_domain.get("json_files"), "json_file", "json"))
    sources.extend(normalize_source_items(raw_domain.get("text_files"), "text_file", "text"))
    return dedupe_source_specs(sources)


def merge_domain_configs(current: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    list_fields = [
        "audit_logs",
        "observability_logs",
        "jsonl_logs",
        "json_files",
        "text_files",
        "notes",
    ]
    for domain_name, raw_domain in discovered.items():
        if not isinstance(raw_domain, dict):
            continue
        existing = merged.get(domain_name)
        if not isinstance(existing, dict):
            merged[domain_name] = dict(raw_domain)
            continue
        combined = dict(existing)
        for field in list_fields:
            values: list[Any] = []
            if isinstance(existing.get(field), list):
                values.extend(existing[field])
            if isinstance(raw_domain.get(field), list):
                values.extend(raw_domain[field])
            if values:
                combined[field] = values
        merged[domain_name] = combined
    return merged


def discover_release_signoff_domain() -> dict[str, Any]:
    validation_root = ROOT / "out" / "validation"
    platform_media_root = ROOT / "out" / "platform-media"
    real_machine_indexes = sorted(
        path
        for path in platform_media_root.glob("*/bringup/reports/hardware-validation-evidence.json")
        if path.is_file()
    )
    real_machine_reports = sorted(
        path
        for path in platform_media_root.glob("*/bringup/reports/hardware-validation-report.md")
        if path.is_file()
    )

    notes = [
        "release-signoff domain stitches validation, governance, release gate, and optional nominated-machine hardware sign-off evidence",
    ]
    if real_machine_indexes:
        notes.append(
            f"discovered {len(real_machine_indexes)} real-machine hardware validation evidence index artifact(s)"
        )
    else:
        notes.append(
            "no real-machine hardware validation evidence discovered under out/platform-media/*/bringup/reports"
        )

    return {
        "release-signoff": {
            "json_files": [
                {
                    "kind": "system_delivery_validation_index",
                    "path": str(validation_root / "system-delivery-validation-evidence-index.json"),
                },
                {
                    "kind": "system_delivery_validation_report",
                    "path": str(validation_root / "system-delivery-validation-report.json"),
                },
                {
                    "kind": "governance_evidence_index",
                    "path": str(validation_root / "governance-evidence-index.json"),
                },
                {
                    "kind": "release_gate_report",
                    "path": str(validation_root / "release-gate-report.json"),
                },
                *[
                    {
                        "kind": "real_machine_hardware_evidence_index",
                        "path": str(path),
                    }
                    for path in real_machine_indexes
                ],
            ],
            "text_files": [
                {
                    "kind": "governance_evidence_markdown",
                    "path": str(validation_root / "governance-evidence-index.md"),
                },
                {
                    "kind": "release_gate_markdown",
                    "path": str(validation_root / "release-gate-report.md"),
                },
                {
                    "kind": "release_checklist",
                    "path": str(ROOT / "docs" / "RELEASE_CHECKLIST.md"),
                },
                *[
                    {
                        "kind": "real_machine_hardware_validation_report",
                        "path": str(path),
                    }
                    for path in real_machine_reports
                ],
            ],
            "notes": notes,
        }
    }


def ordered_domain_names(domain_evidence: dict[str, Any]) -> list[str]:
    names = [name for name in DOMAIN_NAMES if name in domain_evidence]
    extras = sorted(name for name in domain_evidence if name not in DOMAIN_NAMES)
    return names + extras


def summarize_domain(
    domain_name: str,
    source_specs: list[dict[str, str]],
    declared_notes: list[str],
    *,
    approval_keys: set[str],
    provider_keys: set[str],
    artifact_keys: set[str],
    capability_keys: set[str],
    action_keys: set[str],
    status_keys: set[str],
    event_kind_keys: set[str],
) -> dict[str, Any]:
    artifact_paths: set[str] = set()
    audit_decisions: set[str] = set()
    event_kinds: set[str] = set()
    status_values: set[str] = set()
    provider_ids: set[str] = set()
    approval_refs: set[str] = set()
    capability_ids: set[str] = set()
    action_ids: set[str] = set()
    domain_notes = list(declared_notes)
    sources: list[dict[str, Any]] = []
    source_count = 0
    record_count = 0

    for spec in source_specs:
        path = Path(spec["path"])
        present = path.exists()
        source_record_count = 0
        artifact_paths.add(str(path))
        if not present:
            domain_notes.append(f"{domain_name}: missing source {spec['kind']}={path}")
            sources.append(
                {
                    "kind": spec["kind"],
                    "format": spec["format"],
                    "path": str(path),
                    "present": False,
                    "record_count": 0,
                }
            )
            continue

        source_count += 1
        if spec["format"] == "jsonl":
            records = read_jsonl(path)
            source_record_count = len(records)
            record_count += source_record_count
            audit_decisions.update(sorted_unique_strings([entry.get("decision") for entry in records]))
            event_kinds.update(sorted(collect_strings(records, event_kind_keys)))
            status_values.update(sorted(collect_strings(records, status_keys)))
            provider_ids.update(sorted(collect_strings(records, provider_keys)))
            approval_refs.update(sorted(collect_strings(records, approval_keys)))
            capability_ids.update(sorted(collect_strings(records, capability_keys)))
            action_ids.update(sorted(collect_strings(records, action_keys)))
            artifact_paths.update(collect_strings(records, artifact_keys))
        elif spec["format"] == "json":
            payload = read_optional_json(path)
            if payload is not None:
                source_record_count = 1
                record_count += 1
                audit_decisions.update(sorted(collect_strings(payload, {"decision"})))
                event_kinds.update(sorted(collect_strings(payload, event_kind_keys)))
                status_values.update(sorted(collect_strings(payload, status_keys)))
                provider_ids.update(sorted(collect_strings(payload, provider_keys)))
                approval_refs.update(sorted(collect_strings(payload, approval_keys)))
                capability_ids.update(sorted(collect_strings(payload, capability_keys)))
                action_ids.update(sorted(collect_strings(payload, action_keys)))
                artifact_paths.update(collect_strings(payload, artifact_keys))
        else:
            source_record_count = 1
            record_count += 1

        sources.append(
            {
                "kind": spec["kind"],
                "format": spec["format"],
                "path": str(path),
                "present": True,
                "record_count": source_record_count,
            }
        )

    return {
        "domain": domain_name,
        "source_count": source_count,
        "record_count": record_count,
        "artifact_paths": sorted(artifact_paths),
        "audit_decisions": sorted(audit_decisions),
        "event_kinds": sorted(event_kinds),
        "status_values": sorted(status_values),
        "provider_ids": sorted(provider_ids),
        "approval_refs": sorted(approval_refs),
        "capability_ids": sorted(capability_ids),
        "action_ids": sorted(action_ids),
        "sources": sources,
        "notes": domain_notes,
    }


def compat_record_key(record: dict[str, Any]) -> str:
    audit_id = record.get("audit_id")
    if isinstance(audit_id, str) and audit_id:
        return f"audit_id:{audit_id}"
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


def compat_record_status(record: dict[str, Any]) -> str | None:
    for candidate in (
        record.get("status"),
        record_result(record).get("status"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def compat_record_policy_mode(record: dict[str, Any]) -> str | None:
    result = record_result(record)
    candidate = result.get("policy_mode")
    if isinstance(candidate, str) and candidate:
        return candidate
    route_state = record.get("route_state")
    if isinstance(route_state, str) and route_state:
        if route_state.endswith("centralized-policy"):
            return "policyd-verified"
        if route_state.endswith("baseline"):
            return "standalone-local"
    return None


def compat_record_token_verified(record: dict[str, Any]) -> bool:
    result = record_result(record)
    if result.get("token_verified") is True:
        return True
    verification = record.get("token_verification")
    return isinstance(verification, dict) and verification.get("valid") is True


def compat_record_timed_out(record: dict[str, Any]) -> bool:
    result = record_result(record)
    if result.get("timed_out") is True:
        return True
    status = compat_record_status(record)
    if status == "timed_out":
        return True
    for candidate in (
        result.get("error_code"),
        (record.get("error") or {}).get("error_code") if isinstance(record.get("error"), dict) else None,
    ):
        if isinstance(candidate, str) and "timeout" in candidate:
            return True
    return False


def compat_shared_audit_source(spec: dict[str, str]) -> bool:
    kind = str(spec.get("kind") or "").lower()
    path = str(spec.get("path") or "").lower()
    return "shared" in kind or "observability" in kind or path.endswith("compat-observability.jsonl")


def build_compat_audit_overview(source_specs: list[dict[str, str]]) -> dict[str, Any]:
    seen_records: set[str] = set()
    records: list[dict[str, Any]] = []
    shared_audit_log_paths: set[str] = set()

    for spec in source_specs:
        path = Path(spec["path"])
        if compat_shared_audit_source(spec):
            shared_audit_log_paths.add(str(path))
        if not path.exists():
            continue
        payloads: list[dict[str, Any]] = []
        if spec["format"] == "jsonl":
            payloads = [item for item in read_jsonl(path) if isinstance(item, dict)]
        else:
            payload = read_optional_json(path)
            if isinstance(payload, dict):
                payloads = [payload]
            elif isinstance(payload, list):
                payloads = [item for item in payload if isinstance(item, dict)]
        for payload in payloads:
            key = compat_record_key(payload)
            if key in seen_records:
                continue
            seen_records.add(key)
            records.append(payload)

    provider_index: dict[str, dict[str, Any]] = {}
    overview = {
        "record_count": 0,
        "provider_count": 0,
        "provider_ids": [],
        "capability_ids": [],
        "route_states": [],
        "policy_modes": [],
        "shared_audit_log_paths": sorted(shared_audit_log_paths),
        "centralized_policy_record_count": 0,
        "standalone_policy_record_count": 0,
        "token_verified_record_count": 0,
        "approval_bound_record_count": 0,
        "denied_record_count": 0,
        "degraded_record_count": 0,
        "timeout_record_count": 0,
        "providers": [],
    }

    if not records:
        return overview

    for record in records:
        provider_id = record.get("provider_id")
        if not isinstance(provider_id, str) or not provider_id:
            provider_id = "unknown"
        capability_id = record.get("capability_id")
        route_state = record.get("route_state")
        policy_mode = compat_record_policy_mode(record)
        status = compat_record_status(record)
        approval_bound = bool(record.get("approval_id") or record_result(record).get("approval_ref"))
        timed_out = compat_record_timed_out(record)
        token_verified = compat_record_token_verified(record)
        denied = record.get("decision") == "denied"
        degraded = status == "degraded"

        item = provider_index.setdefault(
            provider_id,
            {
                "provider_id": provider_id,
                "record_count": 0,
                "capability_ids": set(),
                "route_states": set(),
                "status_values": set(),
                "policy_modes": set(),
                "token_verified_record_count": 0,
                "approval_bound_record_count": 0,
                "denied_record_count": 0,
                "degraded_record_count": 0,
                "timeout_record_count": 0,
                "shared_audit_log_paths": set(shared_audit_log_paths),
                "artifact_paths": set(),
            },
        )

        item["record_count"] += 1
        if isinstance(capability_id, str) and capability_id:
            item["capability_ids"].add(capability_id)
        if isinstance(route_state, str) and route_state:
            item["route_states"].add(route_state)
        if isinstance(status, str) and status:
            item["status_values"].add(status)
        if isinstance(policy_mode, str) and policy_mode:
            item["policy_modes"].add(policy_mode)
        if token_verified:
            item["token_verified_record_count"] += 1
        if approval_bound:
            item["approval_bound_record_count"] += 1
        if denied:
            item["denied_record_count"] += 1
        if degraded:
            item["degraded_record_count"] += 1
        if timed_out:
            item["timeout_record_count"] += 1
        artifact_path = record.get("artifact_path")
        if isinstance(artifact_path, str) and artifact_path:
            item["artifact_paths"].add(artifact_path)

        overview["record_count"] += 1
        if isinstance(capability_id, str) and capability_id:
            overview["capability_ids"].append(capability_id)
        if isinstance(route_state, str) and route_state:
            overview["route_states"].append(route_state)
        if isinstance(policy_mode, str) and policy_mode:
            overview["policy_modes"].append(policy_mode)
            if policy_mode == "policyd-verified":
                overview["centralized_policy_record_count"] += 1
            if policy_mode == "standalone-local":
                overview["standalone_policy_record_count"] += 1
        if token_verified:
            overview["token_verified_record_count"] += 1
        if approval_bound:
            overview["approval_bound_record_count"] += 1
        if denied:
            overview["denied_record_count"] += 1
        if degraded:
            overview["degraded_record_count"] += 1
        if timed_out:
            overview["timeout_record_count"] += 1

    provider_summaries: list[dict[str, Any]] = []
    for provider_id in sorted(provider_index):
        item = provider_index[provider_id]
        provider_summaries.append(
            {
                "provider_id": provider_id,
                "record_count": item["record_count"],
                "capability_ids": sorted(item["capability_ids"]),
                "route_states": sorted(item["route_states"]),
                "status_values": sorted(item["status_values"]),
                "policy_modes": sorted(item["policy_modes"]),
                "token_verified_record_count": item["token_verified_record_count"],
                "approval_bound_record_count": item["approval_bound_record_count"],
                "denied_record_count": item["denied_record_count"],
                "degraded_record_count": item["degraded_record_count"],
                "timeout_record_count": item["timeout_record_count"],
                "shared_audit_log_paths": sorted(item["shared_audit_log_paths"]),
                "artifact_paths": sorted(item["artifact_paths"]),
            }
        )

    overview["provider_count"] = len(provider_summaries)
    overview["provider_ids"] = sorted(provider_index)
    overview["capability_ids"] = sorted(set(overview["capability_ids"]))
    overview["route_states"] = sorted(set(overview["route_states"]))
    overview["policy_modes"] = sorted(set(overview["policy_modes"]))
    overview["providers"] = provider_summaries
    return overview


def record_result(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("result")
    return result if isinstance(result, dict) else {}


def approval_ref_for_record(record: dict[str, Any]) -> str | None:
    for value in (record.get("approval_id"), record_result(record).get("approval_ref")):
        if isinstance(value, str) and value:
            return value
    return None


def normalize_constraints(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def merge_scope_field(current: Any, candidate: Any) -> Any:
    if current not in (None, "", [], {}):
        return current
    if candidate in (None, "", [], {}):
        return current
    return candidate


def approval_scope_status(record: dict[str, Any]) -> str | None:
    result = record_result(record)
    status = result.get("status")
    if isinstance(status, str) and status:
        return status
    decision = record.get("decision")
    if isinstance(decision, str) and decision.startswith("approval-"):
        return decision.removeprefix("approval-")
    return None


def build_approval_scope_index(audit_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scopes_by_ref: dict[str, dict[str, Any]] = {}
    mismatches: list[dict[str, Any]] = []

    for record in audit_entries:
        approval_ref = approval_ref_for_record(record)
        if not approval_ref:
            continue

        result = record_result(record)
        scope = scopes_by_ref.setdefault(
            approval_ref,
            {
                "approval_ref": approval_ref,
                "session_id": record.get("session_id"),
                "task_id": record.get("task_id"),
                "capability_id": record.get("capability_id"),
                "approval_lane": record.get("route_state"),
                "execution_location": record.get("execution_location"),
                "status": None,
                "target_hash": None,
                "constraints": {},
                "decisions": set(),
                "mismatch_count": 0,
                "scope_mismatches": [],
            },
        )
        scope["decisions"].add(str(record.get("decision") or ""))
        scope["session_id"] = merge_scope_field(scope.get("session_id"), record.get("session_id"))
        scope["task_id"] = merge_scope_field(scope.get("task_id"), record.get("task_id"))
        scope["capability_id"] = merge_scope_field(scope.get("capability_id"), record.get("capability_id"))
        scope["approval_lane"] = merge_scope_field(scope.get("approval_lane"), record.get("route_state"))
        scope["execution_location"] = merge_scope_field(
            scope.get("execution_location"), record.get("execution_location")
        )
        scope["status"] = merge_scope_field(scope.get("status"), approval_scope_status(record))

        for candidate in (
            result.get("target_hash"),
            result.get("approved_target_hash"),
            result.get("requested_target_hash"),
        ):
            scope["target_hash"] = merge_scope_field(scope.get("target_hash"), candidate)

        for candidate in (
            normalize_constraints(result.get("constraints")),
            normalize_constraints(result.get("approved_constraints")),
            normalize_constraints(result.get("requested_constraints")),
        ):
            if len(candidate) > len(scope["constraints"]):
                scope["constraints"] = candidate

        if record.get("decision") == "approval-scope-mismatch":
            mismatch_payload = result.get("scope_mismatch")
            mismatch = mismatch_payload if isinstance(mismatch_payload, dict) else {}
            mismatch_entry = {
                "approval_ref": approval_ref,
                "task_id": record.get("task_id"),
                "capability_id": record.get("capability_id"),
                "timestamp": record.get("timestamp"),
                "reason": result.get("reason"),
                "scope_mismatch": mismatch,
            }
            scope["mismatch_count"] += 1
            scope["scope_mismatches"].append(mismatch_entry)
            mismatches.append(mismatch_entry)

    scopes = []
    for scope in scopes_by_ref.values():
        scope["decisions"] = sorted(item for item in scope["decisions"] if item)
        scope["scope_mismatches"] = sorted(
            scope["scope_mismatches"],
            key=lambda item: str(item.get("timestamp") or ""),
        )
        scopes.append(scope)
    scopes.sort(key=lambda item: (str(item.get("task_id") or ""), item["approval_ref"]))
    mismatches.sort(key=lambda item: str(item.get("timestamp") or ""))
    return scopes, mismatches


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Audit Evidence Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Session: `{report['session']['session_id']}`",
        f"- User: `{report['session']['user_id']}`",
        f"- Workspace: `{report['workspace']}`",
        "",
        "## Inputs",
        "",
        f"- Session DB: `{report['inputs']['session_db']}`",
        f"- Policy audit log: `{report['inputs']['policy_audit_log']}`",
        f"- Audit index: `{report['inputs']['audit_index']}`",
        f"- Runtime events log: `{report['inputs']['runtime_events_log']}`",
        f"- Remote audit log: `{report['inputs']['remote_audit_log']}`",
        f"- Observability log: `{report['inputs']['observability_log']}`",
        f"- Domain config: `{report['inputs']['domain_config']}`",
        "",
        "## Summary",
        "",
        f"- Tasks: `{report['summary']['task_count']}`",
        f"- Audit entries: `{report['summary']['audit_entry_count']}`",
        f"- Runtime events: `{report['summary']['runtime_event_count']}`",
        f"- Remote audits: `{report['summary']['remote_audit_count']}`",
        f"- Observability records: `{report['summary']['observability_record_count']}`",
        f"- Approval refs: `{report['summary']['approval_ref_count']}`",
        f"- Approval scopes: `{report['summary']['approval_scope_count']}`",
        f"- Target-bound approvals: `{report['summary']['target_bound_approval_count']}`",
        f"- Constraint-bound approvals: `{report['summary']['constraint_bound_approval_count']}`",
        f"- Approval scope mismatches: `{report['summary']['approval_scope_mismatch_count']}`",
        f"- Covered domains: `{', '.join(report['summary']['covered_domains']) or '-'}`",
        f"- Audit decisions: `{', '.join(report['summary']['audit_decisions']) or '-'}`",
        "",
        "## Domain Coverage",
        "",
        "| Domain | Sources | Records | Decisions | Events | Providers | Artifacts |",
        "|--------|---------|---------|-----------|--------|-----------|-----------|",
    ]
    for domain_name in ordered_domain_names(report["domain_evidence"]):
        item = report["domain_evidence"].get(domain_name)
        if item is None:
            continue
        lines.append(
            "| `{domain}` | `{sources}` | `{records}` | `{decisions}` | `{events}` | `{providers}` | `{artifacts}` |".format(
                domain=domain_name,
                sources=item["source_count"],
                records=item["record_count"],
                decisions=", ".join(item["audit_decisions"]) or "-",
                events=", ".join(item["event_kinds"]) or "-",
                providers=", ".join(item["provider_ids"]) or "-",
                artifacts=", ".join(item["artifact_paths"]) or "-",
            )
        )

    compat_overview = report["compat_audit_overview"]
    lines.extend(
        [
            "",
            "## Compat Audit Overview",
            "",
            f"- Compat records: `{compat_overview['record_count']}`",
            f"- Compat providers: `{compat_overview['provider_count']}`",
            f"- Policy modes: `{', '.join(compat_overview['policy_modes']) or '-'}`",
            f"- Token verified records: `{compat_overview['token_verified_record_count']}`",
            f"- Approval-bound records: `{compat_overview['approval_bound_record_count']}`",
            f"- Timeout records: `{compat_overview['timeout_record_count']}`",
            f"- Shared compat audit logs: `{', '.join(compat_overview['shared_audit_log_paths']) or '-'}`",
            "",
            "| Provider | Records | Policy Modes | Capabilities | Timeouts | Denied | Degraded | Shared Audit Logs |",
            "|----------|---------|--------------|--------------|----------|--------|----------|-------------------|",
        ]
    )
    for item in compat_overview["providers"]:
        lines.append(
            "| `{provider_id}` | `{record_count}` | `{policy_modes}` | `{capability_ids}` | `{timeout_count}` | `{denied_count}` | `{degraded_count}` | `{shared_audit_logs}` |".format(
                provider_id=item["provider_id"],
                record_count=item["record_count"],
                policy_modes=", ".join(item["policy_modes"]) or "-",
                capability_ids=", ".join(item["capability_ids"]) or "-",
                timeout_count=item["timeout_record_count"],
                denied_count=item["denied_record_count"],
                degraded_count=item["degraded_record_count"],
                shared_audit_logs=", ".join(item["shared_audit_log_paths"]) or "-",
            )
        )

    lines.extend(
        [
            "",
            "## Audit Store",
            "",
            f"- Active segment: `{report['audit_store']['active_segment_path']}`",
            f"- Active record count: `{report['audit_store']['active_record_count']}`",
            f"- Archived segments: `{report['audit_store']['archived_segment_count']}`",
            "",
            "## Tasks",
            "",
            "| Task | State | Audit Decisions | Approval Refs | Runtime Kinds | Observability Kinds | Artifacts |",
            "|------|-------|-----------------|---------------|---------------|---------------------|-----------|",
        ]
    )
    for item in report["tasks"]:
        lines.append(
            "| `{task_id}` | `{state}` | `{audit}` | `{approvals}` | `{runtime}` | `{observability}` | `{artifacts}` |".format(
                task_id=item["task_id"],
                state=item["state"],
                audit=", ".join(item["audit_decisions"]) or "-",
                approvals=", ".join(item["approval_refs"]) or "-",
                runtime=", ".join(item["runtime_event_kinds"]) or "-",
                observability=", ".join(item["observability_kinds"]) or "-",
                artifacts=", ".join(item["artifact_paths"]) or "-",
            )
        )
    if report["approval_scopes"]:
        lines.extend(
            [
                "",
                "## Approval Scope",
                "",
                "| Approval Ref | Task | Status | Target Hash | Constraints | Mismatches |",
                "|--------------|------|--------|-------------|-------------|------------|",
            ]
        )
        for item in report["approval_scopes"]:
            lines.append(
                "| `{approval_ref}` | `{task_id}` | `{status}` | `{target_hash}` | `{constraints}` | `{mismatches}` |".format(
                    approval_ref=item["approval_ref"],
                    task_id=item.get("task_id") or "-",
                    status=item.get("status") or "-",
                    target_hash=item.get("target_hash") or "-",
                    constraints=json.dumps(item.get("constraints") or {}, ensure_ascii=False, sort_keys=True),
                    mismatches=item.get("mismatch_count", 0),
                )
            )
    if report["notes"]:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n")


def main() -> int:
    args = parse_args()
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
        "SELECT task_id, session_id, state, title, created_at FROM tasks WHERE session_id = ?1 ORDER BY created_at ASC",
        (session_id,),
    )
    task_rows_by_id = {str(row["task_id"]): row for row in task_rows}

    task_events_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task_id in task_rows_by_id:
        event_rows = query_all(
            connection,
            "SELECT event_id, task_id, from_state, to_state, metadata_json, created_at FROM task_events WHERE task_id = ?1 ORDER BY created_at ASC",
            (task_id,),
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

    all_audit_records = read_jsonl(args.policy_audit_log)
    all_runtime_records = read_jsonl(args.runtime_events_log)
    all_remote_records = read_jsonl(args.remote_audit_log)
    all_observability_records = read_jsonl(args.observability_log)

    audit_entries = [item for item in all_audit_records if item.get("session_id") == session_id]
    runtime_events = [item for item in all_runtime_records if item.get("session_id") == session_id]
    remote_audits = [item for item in all_remote_records if item.get("session_id") == session_id]
    observability_records = [item for item in all_observability_records if item.get("session_id") == session_id]
    approval_scopes, approval_scope_mismatches = build_approval_scope_index(audit_entries)
    approval_scopes_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in approval_scopes:
        task_id = item.get("task_id")
        if isinstance(task_id, str) and task_id:
            approval_scopes_by_task[task_id].append(item)

    audit_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    runtime_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    remote_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observability_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in audit_entries:
        task_id = record.get("task_id")
        if isinstance(task_id, str) and task_id:
            audit_by_task[task_id].append(record)
    for record in runtime_events:
        task_id = record.get("task_id")
        if isinstance(task_id, str) and task_id:
            runtime_by_task[task_id].append(record)
    for record in remote_audits:
        task_id = record.get("task_id")
        if isinstance(task_id, str) and task_id:
            remote_by_task[task_id].append(record)
    for record in observability_records:
        task_id = record.get("task_id")
        if isinstance(task_id, str) and task_id:
            observability_by_task[task_id].append(record)

    task_ids = sorted(
        set(task_rows_by_id)
        | collect_task_ids(audit_entries)
        | collect_task_ids(runtime_events)
        | collect_task_ids(remote_audits)
        | collect_task_ids(observability_records)
    )

    inputs = {
        "session_db": path_string(args.session_db),
        "policy_audit_log": path_string(args.policy_audit_log),
        "audit_index": path_string(args.audit_index),
        "runtime_events_log": path_string(args.runtime_events_log),
        "remote_audit_log": path_string(args.remote_audit_log),
        "observability_log": path_string(args.observability_log),
        "domain_config": path_string(args.domain_config),
    }

    notes: list[str] = []
    for label, path in [
        ("policy_audit_log", args.policy_audit_log),
        ("audit_index", args.audit_index),
        ("runtime_events_log", args.runtime_events_log),
        ("remote_audit_log", args.remote_audit_log),
        ("observability_log", args.observability_log),
    ]:
        if path is not None and not path.exists():
            notes.append(f"input file missing: {label}={path}")

    audit_index = load_json(args.audit_index) if args.audit_index is not None and args.audit_index.exists() else None
    if audit_index is None:
        notes.append("audit index was not available; audit store summary fell back to active log metadata")

    archived_segments: list[dict[str, Any]] = []
    active_segment_path = path_string(args.policy_audit_log)
    active_record_count = len(all_audit_records)
    archived_segment_count = 0
    if isinstance(audit_index, dict):
        active_segment = audit_index.get("active_segment") or {}
        if isinstance(active_segment.get("path"), str) and active_segment["path"]:
            active_segment_path = str(active_segment["path"])
        if isinstance(active_segment.get("record_count"), int):
            active_record_count = int(active_segment["record_count"])
        raw_archived_segments = audit_index.get("archived_segments") or []
        if isinstance(raw_archived_segments, list):
            for item in raw_archived_segments:
                if not isinstance(item, dict):
                    continue
                archived_segments.append(
                    {
                        "path": str(item.get("path") or ""),
                        "record_count": int(item.get("record_count") or 0),
                        "first_timestamp": item.get("first_timestamp"),
                        "last_timestamp": item.get("last_timestamp"),
                    }
                )
        archived_segment_count = len(archived_segments)

    approval_keys = {"approval_id", "approval_ref"}
    provider_keys = {"provider_id", "selected_provider_id"}
    artifact_keys = {"artifact_path"}
    capability_keys = {"capability_id", "operation"}
    action_keys = {"action_id"}
    status_keys = {
        "status",
        "overall_status",
        "validation_status",
        "gate_status",
        "real_machine_signoff_status",
        "readiness",
    }
    event_kind_keys = {"kind"}

    tasks: list[dict[str, Any]] = []
    all_artifact_paths = {value for value in inputs.values() if isinstance(value, str) and value}
    all_artifact_paths.update(collect_strings(audit_entries, artifact_keys))
    all_artifact_paths.update(collect_strings(runtime_events, artifact_keys))
    all_artifact_paths.update(collect_strings(remote_audits, artifact_keys))
    all_artifact_paths.update(collect_strings(observability_records, artifact_keys))
    all_artifact_paths.update(str(item["path"]) for item in archived_segments if item.get("path"))
    if active_segment_path:
        all_artifact_paths.add(active_segment_path)

    all_approval_refs: set[str] = set()

    for task_id in task_ids:
        task_audit = audit_by_task.get(task_id, [])
        task_runtime = runtime_by_task.get(task_id, [])
        task_remote = remote_by_task.get(task_id, [])
        task_observability = observability_by_task.get(task_id, [])
        row = task_rows_by_id.get(task_id)

        approval_refs = sorted(
            collect_strings(task_audit, approval_keys)
            | collect_strings(task_remote, approval_keys)
            | collect_strings(task_observability, approval_keys)
        )
        all_approval_refs.update(approval_refs)

        provider_ids = sorted(
            collect_strings(task_audit, provider_keys)
            | collect_strings(task_runtime, provider_keys)
            | collect_strings(task_remote, provider_keys)
            | collect_strings(task_observability, provider_keys)
        )

        task_artifact_paths: set[str] = set()
        if row is not None:
            task_artifact_paths.add(str(args.session_db))
        if task_audit and args.policy_audit_log is not None:
            task_artifact_paths.add(str(args.policy_audit_log))
        if task_runtime and args.runtime_events_log is not None:
            task_artifact_paths.add(str(args.runtime_events_log))
        if task_remote and args.remote_audit_log is not None:
            task_artifact_paths.add(str(args.remote_audit_log))
        if task_observability and args.observability_log is not None:
            task_artifact_paths.add(str(args.observability_log))
        task_artifact_paths.update(collect_strings(task_audit, artifact_keys))
        task_artifact_paths.update(collect_strings(task_runtime, artifact_keys))
        task_artifact_paths.update(collect_strings(task_remote, artifact_keys))
        task_artifact_paths.update(collect_strings(task_observability, artifact_keys))

        item: dict[str, Any] = {
            "task_id": task_id,
            "state": str(row["state"]) if row is not None else "unknown",
            "title": row["title"] if row is not None else None,
            "audit_decisions": sorted_unique_strings([entry.get("decision") for entry in task_audit]),
            "runtime_event_kinds": sorted_unique_strings([entry.get("kind") for entry in task_runtime]),
            "remote_audit_statuses": sorted_unique_strings(
                [entry.get("status") or entry.get("decision") for entry in task_remote]
            ),
            "observability_kinds": sorted_unique_strings([entry.get("kind") for entry in task_observability]),
            "approval_refs": approval_refs,
            "approval_scopes": approval_scopes_by_task.get(task_id, []),
            "provider_ids": provider_ids,
            "artifact_paths": sorted(task_artifact_paths),
        }
        if row is not None:
            item["session_id"] = str(row["session_id"])
            item["created_at"] = str(row["created_at"])
            item["task_events"] = task_events_by_task.get(task_id, [])
        tasks.append(item)

    if not remote_audits:
        notes.append("no remote audit records matched the selected session")
    if not observability_records:
        notes.append("no shared observability records matched the selected session")
    if not any(item["approval_refs"] for item in tasks):
        notes.append("no approval references were found for the selected session")
    if not approval_scopes:
        notes.append("no approval scope details were derived from the selected session audit evidence")

    domain_evidence: dict[str, Any] = {}

    control_plane_sources = []
    if args.policy_audit_log is not None:
        control_plane_sources.append({"kind": "audit_log", "path": str(args.policy_audit_log), "format": "jsonl"})
    if args.runtime_events_log is not None:
        control_plane_sources.append({"kind": "runtime_events_log", "path": str(args.runtime_events_log), "format": "jsonl"})
    if args.remote_audit_log is not None:
        control_plane_sources.append({"kind": "remote_audit_log", "path": str(args.remote_audit_log), "format": "jsonl"})
    if args.observability_log is not None:
        control_plane_sources.append({"kind": "observability_log", "path": str(args.observability_log), "format": "jsonl"})
    if args.audit_index is not None:
        control_plane_sources.append({"kind": "audit_index", "path": str(args.audit_index), "format": "json"})

    control_plane_summary = summarize_domain(
        "control-plane",
        control_plane_sources,
        [],
        approval_keys=approval_keys,
        provider_keys=provider_keys,
        artifact_keys=artifact_keys,
        capability_keys=capability_keys,
        action_keys=action_keys,
        status_keys=status_keys,
        event_kind_keys=event_kind_keys,
    )
    control_plane_summary["task_count"] = len(tasks)
    control_plane_summary["artifact_paths"] = sorted(set(control_plane_summary["artifact_paths"]) | all_artifact_paths)
    domain_evidence["control-plane"] = control_plane_summary

    raw_domain_config = merge_domain_configs(
        load_domain_config(args.domain_config, notes),
        discover_release_signoff_domain(),
    )
    compat_audit_overview = build_compat_audit_overview(
        build_domain_source_specs(raw_domain_config.get("compat"))
    )
    for domain_name in ordered_domain_names(
        {
            "control-plane": {},
            **raw_domain_config,
        }
    ):
        if domain_name == "control-plane":
            continue
        raw_domain = raw_domain_config.get(domain_name)
        if raw_domain is None:
            continue
        domain_notes = normalize_string_list(raw_domain.get("notes")) if isinstance(raw_domain, dict) else []
        domain_summary = summarize_domain(
            domain_name,
            build_domain_source_specs(raw_domain),
            domain_notes,
            approval_keys=approval_keys,
            provider_keys=provider_keys,
            artifact_keys=artifact_keys,
            capability_keys=capability_keys,
            action_keys=action_keys,
            status_keys=status_keys,
            event_kind_keys=event_kind_keys,
        )
        domain_evidence[domain_name] = domain_summary
        all_artifact_paths.update(domain_summary["artifact_paths"])
        all_approval_refs.update(domain_summary["approval_refs"])

    covered_domains = sorted(
        domain_name
        for domain_name, item in domain_evidence.items()
        if item.get("source_count", 0) > 0 or item.get("record_count", 0) > 0
    )

    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    report = {
        "report_id": f"audit-evidence-{session_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ROOT),
        "session": {
            "session_id": str(session_row["session_id"]),
            "user_id": str(session_row["user_id"]),
            "status": str(session_row["status"]),
            "created_at": str(session_row["created_at"]),
            "last_resumed_at": session_row["last_resumed_at"],
            "metadata": parse_json_column(session_row["metadata_json"], {}),
        },
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "inputs": inputs,
        "audit_store": {
            "active_segment_path": active_segment_path,
            "active_record_count": active_record_count,
            "archived_segment_count": archived_segment_count,
            "archived_segments": archived_segments,
        },
        "summary": {
            "task_count": len(tasks),
            "audit_entry_count": len(audit_entries),
            "runtime_event_count": len(runtime_events),
            "remote_audit_count": len(remote_audits),
            "observability_record_count": len(observability_records),
            "approval_ref_count": len(all_approval_refs),
            "approval_scope_count": len(approval_scopes),
            "target_bound_approval_count": sum(1 for item in approval_scopes if item.get("target_hash")),
            "constraint_bound_approval_count": sum(
                1 for item in approval_scopes if isinstance(item.get("constraints"), dict) and item["constraints"]
            ),
            "approval_scope_mismatch_count": len(approval_scope_mismatches),
            "archived_segment_count": archived_segment_count,
            "domain_count": len(covered_domains),
            "covered_domains": covered_domains,
            "audit_decisions": sorted(
                {decision for item in tasks for decision in item["audit_decisions"]}
                | {decision for item in domain_evidence.values() for decision in item["audit_decisions"]}
            ),
            "runtime_event_kinds": sorted(
                {kind for item in tasks for kind in item["runtime_event_kinds"]}
            ),
            "observability_kinds": sorted(
                {kind for item in tasks for kind in item["observability_kinds"]}
            ),
            "artifact_paths": sorted(all_artifact_paths),
        },
        "domain_evidence": domain_evidence,
        "compat_audit_overview": compat_audit_overview,
        "approval_scopes": approval_scopes,
        "approval_scope_mismatches": approval_scope_mismatches,
        "tasks": tasks,
        "audit_entries": audit_entries,
        "runtime_events": runtime_events,
        "remote_audits": remote_audits,
        "observability_records": observability_records,
        "notes": notes,
    }

    schema = load_json(SCHEMA_PATH)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(report)

    write_json(json_path, report)
    write_markdown(markdown_path, build_markdown(report))
    print(
        json.dumps(
            {
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "session_id": session_id,
                "task_count": report["summary"]["task_count"],
                "approval_ref_count": report["summary"]["approval_ref_count"],
                "approval_scope_count": report["summary"]["approval_scope_count"],
                "audit_entry_count": report["summary"]["audit_entry_count"],
                "covered_domains": report["summary"]["covered_domains"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
