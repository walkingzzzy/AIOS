#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from functools import lru_cache
from pathlib import Path

FILTER_FIELDS = {
    "source",
    "severity",
    "provider_id",
    "capability_id",
    "decision",
    "status",
    "session_id",
    "task_id",
    "approval_id",
    "audit_id",
    "error_code",
    "text",
    "since",
    "until",
    "fleet_id",
    "governance_group",
    "provider_ref",
    "attestation_mode",
    "control_plane_status",
    "approval_ref",
}

AUDIT_LOG_SOURCES = {"policy", "runtime", "remote", "compat"}
REMOTE_GOVERNANCE_SOURCE_FILTERS = {"browser", "office", "compat"}


def default_policy_audit_log() -> Path:
    return Path(os.environ.get("AIOS_POLICYD_AUDIT_LOG", "/var/lib/aios/policyd/audit.jsonl"))


def default_runtime_events_log() -> Path:
    return Path(
        os.environ.get(
            "AIOS_RUNTIMED_EVENTS_LOG",
            "/var/lib/aios/runtimed/runtime-events.jsonl",
        )
    )


def default_remote_audit_log() -> Path:
    return Path(
        os.environ.get(
            "AIOS_RUNTIMED_REMOTE_AUDIT_LOG",
            "/var/lib/aios/runtimed/remote-audit.jsonl",
        )
    )


def default_compat_observability_log() -> Path:
    return Path(
        os.environ.get(
            "AIOS_COMPAT_OBSERVABILITY_LOG",
            "/var/lib/aios/compat/compat-observability.jsonl",
        )
    )


def load_component_module(component: str, module_name: str):
    shell_root = Path(__file__).resolve().parents[1]
    module_path = shell_root / component / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"aios_shell_{component.replace('-', '_')}_{module_name}",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def remote_governance_helpers():
    return load_component_module("remote-governance", "prototype")


def default_browser_remote_registry() -> Path:
    return remote_governance_helpers().default_browser_remote_registry()


def default_office_remote_registry() -> Path:
    return remote_governance_helpers().default_office_remote_registry()


def default_provider_registry_state_dir() -> Path:
    return remote_governance_helpers().default_provider_registry_state_dir()


def load_jsonl(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    records: list[dict] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def entry_timestamp(entry: dict) -> str:
    for key in ("timestamp", "generated_at", "created_at", "recorded_at", "finished_at"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def entry_status(entry: dict) -> str | None:
    value = entry.get("status")
    if isinstance(value, str) and value:
        return value
    result = entry.get("result")
    if isinstance(result, dict):
        nested = result.get("status")
        if isinstance(nested, str) and nested:
            return nested
    return None


def entry_error_code(entry: dict) -> str | None:
    result = entry.get("result")
    if isinstance(result, dict):
        error_code = result.get("error_code")
        if isinstance(error_code, str) and error_code:
            return error_code
    error_payload = entry.get("error")
    if isinstance(error_payload, dict):
        error_code = error_payload.get("error_code")
        if isinstance(error_code, str) and error_code:
            return error_code
    return None


def entry_provider_id(source: str, entry: dict) -> str | None:
    for key in ("provider_id", "provider_ref"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    result = entry.get("result")
    if isinstance(result, dict):
        for key in ("provider_id", "remote_provider_ref"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
    if source == "remote":
        target = entry.get("target")
        if isinstance(target, dict):
            provider_ref = target.get("provider_ref")
            if isinstance(provider_ref, str) and provider_ref:
                return provider_ref
    return None


def entry_capability_id(entry: dict) -> str | None:
    for key in ("capability_id", "operation"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    result = entry.get("result")
    if isinstance(result, dict):
        value = result.get("capability_id")
        if isinstance(value, str) and value:
            return value
    return None


def issue_for_policy(entry: dict) -> dict | None:
    decision = str(entry.get("decision") or "")
    if decision not in {
        "denied",
        "needs-approval",
        "approval-scope-mismatch",
        "approval-pending",
    }:
        return None
    severity = "high" if decision in {"denied", "approval-scope-mismatch"} else "medium"
    return {
        "source": "policy",
        "severity": severity,
        "kind": "policy",
        "title": f"Policy {decision}",
        "detail": (
            f"capability={entry.get('capability_id') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        ),
        "timestamp": entry_timestamp(entry),
        "task_id": entry.get("task_id"),
        "entry": entry,
    }


def issue_for_runtime(entry: dict) -> dict | None:
    kind = str(entry.get("kind") or "")
    if kind not in {"runtime.infer.timeout", "runtime.infer.fallback"}:
        return None
    return {
        "source": "runtime",
        "severity": "medium" if kind.endswith("timeout") else "info",
        "kind": "runtime",
        "title": f"Runtime {kind}",
        "detail": (
            f"backend={entry.get('backend_id') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        ),
        "timestamp": entry_timestamp(entry),
        "task_id": entry.get("task_id"),
        "entry": entry,
    }


def issue_for_remote(entry: dict) -> dict | None:
    status = str(entry.get("status") or "")
    if status in {"ok", "completed", "ready"}:
        return None
    return {
        "source": "remote",
        "severity": "high" if status in {"error", "failed"} else "medium",
        "kind": "remote",
        "title": f"Remote {status or 'attention'}",
        "detail": (
            f"provider={entry.get('provider_id') or entry.get('provider_ref') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        ),
        "timestamp": entry_timestamp(entry),
        "task_id": entry.get("task_id"),
        "entry": entry,
    }


def issue_for_compat(entry: dict) -> dict | None:
    result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
    error_code = result.get("error_code")
    decision = str(entry.get("decision") or "")
    if error_code in (None, "") and decision not in {"denied", "needs-approval"}:
        return None
    severity = "medium" if error_code else "high"
    return {
        "source": "compat",
        "severity": severity,
        "kind": "compat",
        "title": f"Compat {error_code or decision}",
        "detail": (
            f"provider={entry.get('provider_id') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        ),
        "timestamp": entry_timestamp(entry),
        "task_id": entry.get("task_id"),
        "entry": entry,
    }


def recent_record(source: str, entry: dict) -> dict:
    if source == "policy":
        title = f"Policy {entry.get('decision') or 'record'}"
        detail = (
            f"capability={entry.get('capability_id') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        )
    elif source == "runtime":
        title = f"Runtime {entry.get('kind') or 'event'}"
        detail = (
            f"backend={entry.get('backend_id') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        )
    elif source == "remote":
        title = f"Remote {entry.get('status') or 'event'}"
        detail = (
            f"provider={entry.get('provider_id') or entry.get('provider_ref') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        )
    else:
        result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
        title = f"Compat {result.get('error_code') or entry.get('decision') or 'event'}"
        detail = (
            f"provider={entry.get('provider_id') or '-'} "
            f"task={entry.get('task_id') or '-'}"
        )
    return {
        "source": source,
        "title": title,
        "detail": detail,
        "timestamp": entry_timestamp(entry),
        "task_id": entry.get("task_id"),
        "entry": entry,
    }


def governance_recent_record(entry: dict, generated_at: str | None) -> dict:
    provider = entry.get("provider_ref") or entry.get("control_plane_provider_id") or "remote"
    detail = (
        f"fleet={entry.get('fleet_id') or '-'} "
        f"status={entry.get('registration_status') or '-'} "
        f"health={entry.get('control_plane_health_status') or '-'} "
        f"issues={entry.get('issue_count', 0)}"
    )
    return {
        "source": "governance",
        "title": f"Governance {entry.get('registration_status') or 'entry'}",
        "detail": f"provider={provider} {detail}",
        "timestamp": entry.get("last_heartbeat_at") or entry.get("registered_at") or generated_at or "",
        "task_id": None,
        "entry": entry,
    }


def governance_issue_record(issue_item: dict, generated_at: str | None) -> dict:
    provider = issue_item.get("provider_ref") or issue_item.get("provider_id") or "remote"
    return {
        "source": "governance",
        "severity": issue_item.get("severity") or "info",
        "kind": issue_item.get("kind") or "governance",
        "title": issue_item.get("title") or "Governance issue",
        "detail": issue_item.get("detail") or f"provider={provider}",
        "timestamp": generated_at or "",
        "task_id": None,
        "entry": issue_item,
    }


def issue_for_entry(source: str, entry: dict) -> dict | None:
    if source == "policy":
        return issue_for_policy(entry)
    if source == "runtime":
        return issue_for_runtime(entry)
    if source == "remote":
        return issue_for_remote(entry)
    return issue_for_compat(entry)


def entry_field(source: str, entry: dict, name: str) -> object:
    if name == "source":
        return source
    if name == "severity":
        issue = issue_for_entry(source, entry)
        return issue.get("severity") if isinstance(issue, dict) else "info"
    if name == "provider_id":
        return entry_provider_id(source, entry)
    if name == "capability_id":
        return entry_capability_id(entry)
    if name == "status":
        return entry_status(entry)
    if name == "error_code":
        return entry_error_code(entry)
    return entry.get(name)


def governance_query_filters(filters: dict[str, object]) -> tuple[bool, dict[str, object]]:
    source = filters.get("source")
    if source in AUDIT_LOG_SOURCES and source not in REMOTE_GOVERNANCE_SOURCE_FILTERS:
        return False, {}

    governance_filters: dict[str, object] = {}
    if source in REMOTE_GOVERNANCE_SOURCE_FILTERS:
        governance_filters["source"] = source
    elif source == "governance":
        pass

    for key in (
        "severity",
        "fleet_id",
        "governance_group",
        "status",
        "provider_ref",
        "provider_id",
        "attestation_mode",
        "control_plane_status",
        "approval_ref",
        "text",
    ):
        value = filters.get(key)
        if value not in (None, ""):
            governance_filters[key] = value

    if "approval_ref" not in governance_filters:
        approval_value = filters.get("approval_id")
        if approval_value not in (None, ""):
            governance_filters["approval_ref"] = approval_value

    return True, governance_filters


def matches_filters(source: str, entry: dict, filters: dict[str, object]) -> bool:
    timestamp = entry_timestamp(entry)
    for key, expected in filters.items():
        if key == "text":
            haystack = json.dumps({"source": source, "entry": entry}, ensure_ascii=False, sort_keys=True)
            if str(expected) not in haystack:
                return False
            continue
        if key == "since":
            if timestamp and timestamp < str(expected):
                return False
            continue
        if key == "until":
            if timestamp and timestamp > str(expected):
                return False
            continue
        if str(entry_field(source, entry, key) or "") != str(expected):
            return False
    return True


def write_report(path: Path, payload: dict) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_operator_audit(
    policy_audit_log: Path | None,
    runtime_events_log: Path | None,
    remote_audit_log: Path | None,
    compat_observability_log: Path | None,
    *,
    browser_remote_registry: Path | None = None,
    office_remote_registry: Path | None = None,
    provider_registry_state_dir: Path | None = None,
    limit: int = 10,
    filters: dict[str, object] | None = None,
    report_path: Path | None = None,
) -> dict:
    limit = max(1, limit)
    active_filters = {
        key: value
        for key, value in (filters or {}).items()
        if key in FILTER_FIELDS and value not in (None, "")
    }
    source_records = {
        "policy": load_jsonl(policy_audit_log),
        "runtime": load_jsonl(runtime_events_log),
        "remote": load_jsonl(remote_audit_log),
        "compat": load_jsonl(compat_observability_log),
    }
    filtered_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    recent_records: list[dict] = []
    issues: list[dict] = []
    task_ids: set[str] = set()
    provider_ids: set[str] = set()
    capability_ids: set[str] = set()
    matched_entries: list[dict] = []
    matched_record_count = 0
    governance_payload: dict = {}
    governance_recent_records: list[dict] = []
    governance_issues: list[dict] = []

    for source, entries in source_records.items():
        filtered_entries = [
            entry for entry in entries[-96:] if matches_filters(source, entry, active_filters)
        ]
        if entries:
            source_counts[source] = len(entries)
        if filtered_entries:
            filtered_counts[source] = len(filtered_entries)
        matched_record_count += len(filtered_entries)
        for entry in filtered_entries:
            record = recent_record(source, entry)
            recent_records.append(record)
            task_id = record.get("task_id")
            if isinstance(task_id, str) and task_id:
                task_ids.add(task_id)
            provider_id = entry_provider_id(source, entry)
            if isinstance(provider_id, str) and provider_id:
                provider_ids.add(provider_id)
            capability_id = entry_capability_id(entry)
            if isinstance(capability_id, str) and capability_id:
                capability_ids.add(capability_id)
            matched_entries.append(
                {
                    "source": source,
                    "timestamp": entry_timestamp(entry),
                    "provider_id": provider_id,
                    "capability_id": capability_id,
                    "status": entry_status(entry),
                    "error_code": entry_error_code(entry),
                    "entry": entry,
                }
            )
            issue = issue_for_entry(source, entry)
            if issue is not None:
                issues.append(issue)

    governance_enabled, governance_filters = governance_query_filters(active_filters)
    if (
        governance_enabled
        and browser_remote_registry is not None
        and office_remote_registry is not None
        and provider_registry_state_dir is not None
    ):
        governance_payload = remote_governance_helpers().load_remote_governance(
            browser_remote_registry,
            office_remote_registry,
            provider_registry_state_dir,
            limit=32,
            filters=governance_filters,
            issue_only=False,
        )
        governance_entry_count = int(governance_payload.get("entry_count", 0))
        governance_matched_count = int(governance_payload.get("matched_entry_count", 0))
        if governance_entry_count:
            source_counts["governance"] = governance_entry_count
        if governance_matched_count:
            filtered_counts["governance"] = governance_matched_count
        matched_record_count += governance_matched_count

        for entry in governance_payload.get("entries", []):
            record = governance_recent_record(entry, governance_payload.get("generated_at"))
            governance_recent_records.append(record)
            recent_records.append(record)
            provider_id = entry.get("control_plane_provider_id") or entry.get("provider_ref")
            if isinstance(provider_id, str) and provider_id:
                provider_ids.add(provider_id)
            matched_entries.append(
                {
                    "source": "governance",
                    "timestamp": record["timestamp"],
                    "provider_id": provider_id,
                    "capability_id": None,
                    "status": entry.get("registration_status"),
                    "error_code": None,
                    "entry": entry,
                }
            )

        for issue_item in governance_payload.get("issues", []):
            issue_record = governance_issue_record(issue_item, governance_payload.get("generated_at"))
            governance_issues.append(issue_record)
            issues.append(issue_record)
            provider_id = issue_item.get("provider_id") or issue_item.get("provider_ref")
            if isinstance(provider_id, str) and provider_id:
                provider_ids.add(provider_id)

    recent_records.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    issues.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

    issue_source_counts: dict[str, int] = {}
    for issue in issues:
        source = str(issue.get("source") or "unknown")
        issue_source_counts[source] = issue_source_counts.get(source, 0) + 1
    timestamps = [
        entry.get("timestamp")
        for entry in matched_entries
        if isinstance(entry.get("timestamp"), str) and entry.get("timestamp")
    ]
    payload = {
        "record_count": sum(len(entries) for entries in source_records.values()) + int(governance_payload.get("entry_count", 0)),
        "matched_record_count": matched_record_count,
        "issue_count": len(issues),
        "source_counts": source_counts,
        "filtered_source_counts": filtered_counts,
        "issue_source_counts": issue_source_counts,
        "task_ids": sorted(task_ids),
        "provider_ids": sorted(provider_ids),
        "capability_ids": sorted(capability_ids),
        "recent_records": recent_records[:limit],
        "issues": issues[:limit],
        "matched_entries": matched_entries[:limit],
        "governance_recent_records": governance_recent_records[:limit],
        "governance_issues": governance_issues[:limit],
        "remote_governance": {
            "entry_count": int(governance_payload.get("entry_count", 0)),
            "matched_entry_count": int(governance_payload.get("matched_entry_count", 0)),
            "issue_count": int(governance_payload.get("issue_count", 0)),
            "fleet_count": len(governance_payload.get("fleet_summary", [])),
            "source_counts": governance_payload.get("source_counts", {}),
            "filtered_source_counts": governance_payload.get("filtered_source_counts", {}),
            "status_counts": governance_payload.get("status_counts", {}),
            "filtered_status_counts": governance_payload.get("filtered_status_counts", {}),
            "fleet_ids": governance_payload.get("fleet_ids", []),
            "artifact_paths": governance_payload.get("artifact_paths", {}),
            "filters": governance_filters,
        },
        "artifact_paths": {
            "policy_audit_log": (
                str(policy_audit_log) if policy_audit_log is not None and policy_audit_log.exists() else None
            ),
            "runtime_events_log": (
                str(runtime_events_log)
                if runtime_events_log is not None and runtime_events_log.exists()
                else None
            ),
            "remote_audit_log": (
                str(remote_audit_log) if remote_audit_log is not None and remote_audit_log.exists() else None
            ),
            "compat_observability_log": (
                str(compat_observability_log)
                if compat_observability_log is not None and compat_observability_log.exists()
                else None
            ),
            "browser_remote_registry": (
                str(browser_remote_registry)
                if browser_remote_registry is not None and browser_remote_registry.exists()
                else None
            ),
            "office_remote_registry": (
                str(office_remote_registry)
                if office_remote_registry is not None and office_remote_registry.exists()
                else None
            ),
            "provider_registry_state_dir": (
                str(provider_registry_state_dir)
                if provider_registry_state_dir is not None and provider_registry_state_dir.exists()
                else None
            ),
        },
        "query": {
            "filters": active_filters,
            "limit": limit,
            "matched_source_count": len(filtered_counts),
            "latest_timestamp": max(timestamps) if timestamps else None,
            "oldest_timestamp": min(timestamps) if timestamps else None,
            "report_path": str(report_path) if report_path is not None else None,
        },
    }
    if report_path is not None:
        write_report(report_path, payload)
    return payload
