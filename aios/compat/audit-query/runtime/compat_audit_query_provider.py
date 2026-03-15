#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios.compat.runtime_support import add_policy_args, append_jsonl, standalone_policy_context


PROVIDER_ID = "compat.audit.query.local"
DECLARED_CAPABILITIES = [
    "compat.audit.query",
    "compat.audit.saved_query.run",
]
REQUIRED_PERMISSIONS = ["audit.read"]
COMPAT_PERMISSION_SCHEMA_REF = "aios/compat-permission-manifest.schema.json"
RESULT_PROTOCOL_SCHEMA_REF = "aios/compat-audit-query-result.schema.json"
DESCRIPTOR_FILENAME = "audit.query.local.json"
WORKER_CONTRACT = "compat-audit-query-v1"
AUDIT_SCHEMA_VERSION = "2026-03-14"
DEFAULT_AUDIT_LOG_ENV = "AIOS_COMPAT_AUDIT_QUERY_AUDIT_LOG"
DEFAULT_SOURCE_LOG_ENV = "AIOS_COMPAT_AUDIT_QUERY_SOURCE_LOG"
DEFAULT_STORE_DIR_ENV = "AIOS_COMPAT_AUDIT_QUERY_STORE_DIR"

COMMAND_EXIT_CODES = {
    "invalid_request": 2,
    "precondition_failed": 3,
    "internal": 1,
}

FILTER_FIELDS = {
    "provider_id",
    "capability_id",
    "decision",
    "status",
    "session_id",
    "task_id",
    "audit_id",
    "error_code",
    "text",
    "since",
    "until",
}


@dataclass(frozen=True)
class QueryContext:
    command: str
    operation: str
    query_id: str | None
    filters: dict[str, object]
    limit: int | None
    started_at: str


class QueryCommandError(RuntimeError):
    def __init__(
        self,
        *,
        category: str,
        error_code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    @property
    def exit_code(self) -> int:
        return COMMAND_EXIT_CODES.get(self.category, 1)

    def to_payload(self) -> dict[str, object]:
        payload = {
            "category": self.category,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }
        payload.update(self.details)
        return payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat audit query provider")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("manifest")
    permissions_parser = subparsers.add_parser("permissions")

    health_parser = subparsers.add_parser("health")
    add_common_paths_args(health_parser)
    add_policy_args(health_parser)

    query_parser = subparsers.add_parser("query")
    add_common_paths_args(query_parser)
    add_query_filter_args(query_parser)
    query_parser.add_argument("--write-report", type=Path)
    add_policy_args(query_parser)

    save_parser = subparsers.add_parser("save-query")
    add_common_paths_args(save_parser)
    add_query_filter_args(save_parser)
    save_parser.add_argument("--query-id", required=True)
    save_parser.add_argument("--description")
    add_policy_args(save_parser)

    subparsers.add_parser("list-saved-queries")
    list_parser = subparsers.choices["list-saved-queries"]
    add_common_paths_args(list_parser)
    add_policy_args(list_parser)

    run_parser = subparsers.add_parser("run-saved-query")
    add_common_paths_args(run_parser)
    run_parser.add_argument("--query-id", required=True)
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--write-report", type=Path)
    add_policy_args(run_parser)

    interactive_parser = subparsers.add_parser("interactive")
    add_common_paths_args(interactive_parser)
    interactive_parser.add_argument("--script-file", type=Path)
    add_policy_args(interactive_parser)

    return parser.parse_args()


def add_common_paths_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--audit-log", type=Path)
    parser.add_argument("--source-log", type=Path)
    parser.add_argument("--store-dir", type=Path)


def add_query_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider-id")
    parser.add_argument("--capability-id")
    parser.add_argument("--decision")
    parser.add_argument("--status")
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--audit-id")
    parser.add_argument("--error-code")
    parser.add_argument("--text")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--limit", type=int)


def resolve_descriptor_path() -> str:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[1] / "providers" / DESCRIPTOR_FILENAME,
        current.parents[3] / "share" / "aios" / "providers" / DESCRIPTOR_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


def resolve_audit_log(args: argparse.Namespace) -> Path | None:
    audit_log = getattr(args, "audit_log", None)
    if audit_log is not None:
        return audit_log
    raw = os.environ.get(DEFAULT_AUDIT_LOG_ENV)
    return Path(raw) if raw else None


def resolve_source_log(args: argparse.Namespace) -> Path | None:
    source_log = getattr(args, "source_log", None)
    if source_log is not None:
        return source_log
    raw = os.environ.get(DEFAULT_SOURCE_LOG_ENV)
    if raw:
        return Path(raw)
    return standalone_policy_context(args).shared_audit_log


def resolve_store_dir(args: argparse.Namespace) -> Path:
    store_dir = getattr(args, "store_dir", None)
    if store_dir is not None:
        return store_dir
    raw = os.environ.get(DEFAULT_STORE_DIR_ENV)
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "state" / "aios" / "compat-audit-query"


def store_saved_queries_path(store_dir: Path) -> Path:
    return store_dir / "saved-queries.json"


def store_history_path(store_dir: Path) -> Path:
    return store_dir / "query-history.jsonl"


def load_compat_permission_manifest() -> dict[str, object]:
    descriptor_path = resolve_descriptor_path()
    descriptor = json.loads(Path(descriptor_path).read_text(encoding="utf-8"))
    permission_manifest = descriptor.get("compat_permission_manifest")
    if not isinstance(permission_manifest, dict):
        raise RuntimeError(f"descriptor missing compat_permission_manifest: {descriptor_path}")
    return permission_manifest


def build_manifest() -> dict[str, object]:
    return {
        "provider_id": PROVIDER_ID,
        "execution_location": "local",
        "status": "baseline",
        "worker_contract": WORKER_CONTRACT,
        "declared_capabilities": DECLARED_CAPABILITIES,
        "required_permissions": REQUIRED_PERMISSIONS,
        "implemented_methods": [
            "audit-entry-query",
            "saved-query-store",
            "saved-query-list",
            "interactive-query-script",
            "query-history-jsonl",
            "audit-query-result-protocol-v1",
        ],
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "notes": [
            "Queries compat JSONL audit entries with persistent saved-query state",
            "Interactive script mode can query, save, and rerun audit filters",
            "Persistent query history is stored under the provider state directory",
        ],
    }


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise QueryCommandError(
            category="precondition_failed",
            error_code="compat_audit_source_log_missing",
            message=f"compat audit source log missing: {path}",
            retryable=False,
            details={"source_log": str(path)},
        )
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            entries.append(value)
    return entries


def extract_filters(args: argparse.Namespace) -> dict[str, object]:
    filters: dict[str, object] = {}
    for field in FILTER_FIELDS:
        value = getattr(args, field.replace("-", "_"), None)
        if value not in {None, ""}:
            filters[field] = value
    return filters


def entry_timestamp(entry: dict[str, object]) -> str:
    value = entry.get("timestamp") or entry.get("generated_at") or entry.get("finished_at")
    return str(value or "")


def entry_status(entry: dict[str, object]) -> str | None:
    value = entry.get("status")
    if isinstance(value, str):
        return value
    result = entry.get("result")
    if isinstance(result, dict):
        status = result.get("status")
        if isinstance(status, str):
            return status
    return None


def entry_error_code(entry: dict[str, object]) -> str | None:
    result = entry.get("result")
    if isinstance(result, dict):
        error_code = result.get("error_code")
        if isinstance(error_code, str):
            return error_code
    return None


def entry_field(entry: dict[str, object], name: str) -> object:
    if name == "status":
        return entry_status(entry)
    if name == "error_code":
        return entry_error_code(entry)
    return entry.get(name)


def matches_filters(entry: dict[str, object], filters: dict[str, object]) -> bool:
    timestamp = entry_timestamp(entry)
    for key, expected in filters.items():
        if key == "text":
            haystack = json.dumps(entry, ensure_ascii=False, sort_keys=True)
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
        if str(entry_field(entry, key) or "") != str(expected):
            return False
    return True


def apply_query(entries: list[dict[str, object]], filters: dict[str, object], limit: int | None) -> list[dict[str, object]]:
    matched = [entry for entry in entries if matches_filters(entry, filters)]
    matched.sort(key=entry_timestamp, reverse=True)
    if limit is None or limit <= 0:
        return matched
    return matched[:limit]


def summarize_entries(entries: list[dict[str, object]]) -> dict[str, object]:
    by_provider: dict[str, int] = {}
    by_capability: dict[str, int] = {}
    by_decision: dict[str, int] = {}
    by_status: dict[str, int] = {}
    timestamps = [entry_timestamp(entry) for entry in entries if entry_timestamp(entry)]
    for entry in entries:
        provider_id = str(entry.get("provider_id") or "<unknown>")
        capability_id = str(entry.get("capability_id") or "<unknown>")
        decision = str(entry.get("decision") or "<unknown>")
        status = str(entry_status(entry) or "<unknown>")
        by_provider[provider_id] = by_provider.get(provider_id, 0) + 1
        by_capability[capability_id] = by_capability.get(capability_id, 0) + 1
        by_decision[decision] = by_decision.get(decision, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "entry_count": len(entries),
        "providers": by_provider,
        "capabilities": by_capability,
        "decisions": by_decision,
        "statuses": by_status,
        "latest_timestamp": max(timestamps) if timestamps else None,
        "oldest_timestamp": min(timestamps) if timestamps else None,
    }


def build_context(args: argparse.Namespace, operation: str, query_id: str | None = None) -> QueryContext:
    return QueryContext(
        command=args.command,
        operation=operation,
        query_id=query_id,
        filters=extract_filters(args),
        limit=getattr(args, "limit", None),
        started_at=utc_now(),
    )


def build_result_protocol(
    *,
    context: QueryContext,
    source_log: Path | None,
    store_dir: Path,
    audit_log: Path | None,
    match_count: int | None,
    report_path: Path | None,
    saved_query_count: int | None,
    error: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "protocol_version": "1.0.0",
        "worker_contract": WORKER_CONTRACT,
        "provider_id": PROVIDER_ID,
        "status": "error" if error else "ok",
        "operation": context.operation,
        "execution_location": "local",
        "request": {
            "command": context.command,
            "query_id": context.query_id,
            "filters": context.filters,
            "limit": context.limit,
        },
        "query": {
            "source_log": str(source_log) if source_log is not None else None,
            "match_count": match_count,
            "report_path": str(report_path) if report_path is not None else None,
        },
        "store": {
            "store_dir": str(store_dir),
            "saved_queries_path": str(store_saved_queries_path(store_dir)),
            "history_path": str(store_history_path(store_dir)),
            "saved_query_count": saved_query_count,
        },
        "audit": {
            "audit_log": str(audit_log) if audit_log is not None else None,
            "audit_tags": ["audit", "compat", "query"],
            "taint_behavior": "audit-observer",
        },
        "timestamps": {
            "started_at": context.started_at,
            "finished_at": utc_now(),
        },
        "error": error,
    }


def write_query_audit(
    audit_log: Path | None,
    *,
    context: QueryContext,
    source_log: Path | None,
    report_path: Path | None,
    match_count: int | None,
    error: dict[str, object] | None,
) -> None:
    if audit_log is None:
        return
    append_jsonl(
        audit_log,
        {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "audit_id": f"compat-audit-query-{time.time_ns()}",
            "timestamp": utc_now(),
            "provider_id": PROVIDER_ID,
            "capability_id": context.operation,
            "decision": "observed",
            "status": "error" if error else "ok",
            "execution_location": "local",
            "artifact_path": str(audit_log),
            "result": {
                "query_id": context.query_id,
                "source_log": str(source_log) if source_log is not None else None,
                "match_count": match_count,
                "error_code": error.get("error_code") if error else None,
                "report_path": str(report_path) if report_path is not None else None,
            },
            "notes": [
                f"worker_contract={WORKER_CONTRACT}",
                f"result_protocol_schema_ref={RESULT_PROTOCOL_SCHEMA_REF}",
            ],
        },
    )


def load_saved_queries(store_dir: Path) -> dict[str, dict[str, object]]:
    path = store_saved_queries_path(store_dir)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = payload.get("queries", {})
    if not isinstance(queries, dict):
        return {}
    return {
        str(query_id): dict(spec)
        for query_id, spec in queries.items()
        if isinstance(query_id, str) and isinstance(spec, dict)
    }


def write_saved_queries(store_dir: Path, queries: dict[str, dict[str, object]]) -> None:
    path = store_saved_queries_path(store_dir)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "updated_at": utc_now(),
        "queries": queries,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_history(
    store_dir: Path,
    *,
    action: str,
    query_id: str | None,
    filters: dict[str, object],
    source_log: Path | None,
    match_count: int | None,
    report_path: Path | None,
) -> None:
    append_jsonl(
        store_history_path(store_dir),
        {
            "timestamp": utc_now(),
            "action": action,
            "query_id": query_id,
            "filters": filters,
            "source_log": str(source_log) if source_log is not None else None,
            "match_count": match_count,
            "report_path": str(report_path) if report_path is not None else None,
        },
    )


def ensure_store_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_report(path: Path, payload: dict[str, object]) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def query_payload(
    *,
    context: QueryContext,
    source_log: Path,
    store_dir: Path,
    audit_log: Path | None,
    matched_entries: list[dict[str, object]],
    report_path: Path | None,
    saved_query_count: int,
    saved_query: dict[str, object] | None = None,
) -> dict[str, object]:
    result_protocol = build_result_protocol(
        context=context,
        source_log=source_log,
        store_dir=store_dir,
        audit_log=audit_log,
        match_count=len(matched_entries),
        report_path=report_path,
        saved_query_count=saved_query_count,
        error=None,
    )
    return {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "ok",
        "operation": context.operation,
        "query_id": context.query_id,
        "filters": context.filters,
        "limit": context.limit,
        "source_log": str(source_log),
        "match_count": len(matched_entries),
        "entries": matched_entries,
        "summary": summarize_entries(matched_entries),
        "report_path": str(report_path) if report_path is not None else None,
        "saved_query": saved_query,
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "result_protocol": result_protocol,
    }


def execute_query(
    *,
    context: QueryContext,
    source_log: Path,
    store_dir: Path,
    audit_log: Path | None,
    report_path: Path | None,
    saved_query: dict[str, object] | None = None,
) -> dict[str, object]:
    entries = load_jsonl(source_log)
    matched_entries = apply_query(entries, context.filters, context.limit)
    saved_query_count = len(load_saved_queries(store_dir))
    payload = query_payload(
        context=context,
        source_log=source_log,
        store_dir=store_dir,
        audit_log=audit_log,
        matched_entries=matched_entries,
        report_path=report_path,
        saved_query_count=saved_query_count,
        saved_query=saved_query,
    )
    if report_path is not None:
        write_report(report_path, payload)
    append_history(
        store_dir,
        action=context.command,
        query_id=context.query_id,
        filters=context.filters,
        source_log=source_log,
        match_count=len(matched_entries),
        report_path=report_path,
    )
    write_query_audit(
        audit_log,
        context=context,
        source_log=source_log,
        report_path=report_path,
        match_count=len(matched_entries),
        error=None,
    )
    return payload


def handle_health(args: argparse.Namespace) -> dict[str, object]:
    policy_context = standalone_policy_context(args)
    source_log = resolve_source_log(args)
    store_dir = resolve_store_dir(args)
    audit_log = resolve_audit_log(args)
    saved_queries = load_saved_queries(store_dir)
    return {
        "status": "available",
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "execution_location": "local",
        "declared_capabilities": DECLARED_CAPABILITIES,
        "required_permissions": REQUIRED_PERMISSIONS,
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "engine": "compat-audit-query-baseline",
        "source_log_configured": source_log is not None,
        "source_log_path": str(source_log) if source_log is not None else None,
        "store_dir": str(store_dir),
        "saved_query_count": len(saved_queries),
        "history_path": str(store_history_path(store_dir)),
        "audit_log_configured": audit_log is not None,
        "audit_log_path": str(audit_log) if audit_log is not None else None,
        "shared_audit_log_configured": policy_context.shared_audit_log is not None,
        "shared_audit_log_path": (
            str(policy_context.shared_audit_log)
            if policy_context.shared_audit_log is not None
            else None
        ),
        "policyd_socket": (
            str(policy_context.policyd_socket)
            if policy_context.policyd_socket is not None
            else None
        ),
        "notes": [
            "Persistent saved queries and query-history JSONL are available",
            "Interactive script mode is available for operator-driven filtering",
        ],
    }


def handle_query(args: argparse.Namespace) -> dict[str, object]:
    source_log = resolve_source_log(args)
    if source_log is None:
        raise QueryCommandError(
            category="precondition_failed",
            error_code="compat_audit_source_log_unconfigured",
            message="compat audit source log is not configured",
            retryable=False,
        )
    store_dir = resolve_store_dir(args)
    ensure_store_dir(store_dir)
    return execute_query(
        context=build_context(args, "compat.audit.query"),
        source_log=source_log,
        store_dir=store_dir,
        audit_log=resolve_audit_log(args),
        report_path=args.write_report,
    )


def handle_save_query(args: argparse.Namespace) -> dict[str, object]:
    store_dir = resolve_store_dir(args)
    ensure_store_dir(store_dir)
    saved_queries = load_saved_queries(store_dir)
    context = build_context(args, "compat.audit.saved_query.save", args.query_id)
    spec = {
        "query_id": args.query_id,
        "saved_at": utc_now(),
        "description": args.description,
        "filters": context.filters,
        "limit": context.limit,
    }
    saved_queries[args.query_id] = spec
    write_saved_queries(store_dir, saved_queries)
    append_history(
        store_dir,
        action="save-query",
        query_id=args.query_id,
        filters=context.filters,
        source_log=resolve_source_log(args),
        match_count=None,
        report_path=None,
    )
    write_query_audit(
        resolve_audit_log(args),
        context=context,
        source_log=resolve_source_log(args),
        report_path=None,
        match_count=None,
        error=None,
    )
    return {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "ok",
        "operation": "compat.audit.saved_query.save",
        "saved_query": spec,
        "saved_query_count": len(saved_queries),
        "store_dir": str(store_dir),
    }


def handle_list_saved_queries(args: argparse.Namespace) -> dict[str, object]:
    store_dir = resolve_store_dir(args)
    saved_queries = load_saved_queries(store_dir)
    context = QueryContext(
        command="list-saved-queries",
        operation="compat.audit.saved_query.list",
        query_id=None,
        filters={},
        limit=None,
        started_at=utc_now(),
    )
    write_query_audit(
        resolve_audit_log(args),
        context=context,
        source_log=resolve_source_log(args),
        report_path=None,
        match_count=len(saved_queries),
        error=None,
    )
    return {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "ok",
        "operation": "compat.audit.saved_query.list",
        "saved_query_count": len(saved_queries),
        "saved_queries": list(saved_queries.values()),
        "store_dir": str(store_dir),
    }


def handle_run_saved_query(args: argparse.Namespace) -> dict[str, object]:
    store_dir = resolve_store_dir(args)
    ensure_store_dir(store_dir)
    saved_queries = load_saved_queries(store_dir)
    saved_query = saved_queries.get(args.query_id)
    if saved_query is None:
        raise QueryCommandError(
            category="precondition_failed",
            error_code="compat_audit_saved_query_missing",
            message=f"saved query missing: {args.query_id}",
            retryable=False,
            details={"query_id": args.query_id},
        )
    source_log = resolve_source_log(args)
    if source_log is None:
        raise QueryCommandError(
            category="precondition_failed",
            error_code="compat_audit_source_log_unconfigured",
            message="compat audit source log is not configured",
            retryable=False,
        )
    context = QueryContext(
        command="run-saved-query",
        operation="compat.audit.saved_query.run",
        query_id=args.query_id,
        filters=dict(saved_query.get("filters") or {}),
        limit=args.limit if args.limit is not None else saved_query.get("limit"),
        started_at=utc_now(),
    )
    report_path = args.write_report
    if report_path is None:
        report_path = store_dir / "reports" / f"{args.query_id}-{int(time.time())}.json"
    return execute_query(
        context=context,
        source_log=source_log,
        store_dir=store_dir,
        audit_log=resolve_audit_log(args),
        report_path=report_path,
        saved_query=saved_query,
    )


def parse_interactive_tokens(command: str) -> tuple[str, list[str]]:
    tokens = [token for token in command.strip().split() if token]
    if not tokens:
        return "", []
    return tokens[0], tokens[1:]


def interactive_filters(tokens: list[str]) -> tuple[dict[str, object], int | None, Path | None]:
    filters: dict[str, object] = {}
    limit: int | None = None
    report_path: Path | None = None
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        normalized = key.strip().replace("-", "_")
        if normalized == "limit":
            limit = int(value)
        elif normalized == "report":
            report_path = Path(value)
        elif normalized in {field.replace("-", "_") for field in FILTER_FIELDS}:
            filters[normalized] = value
    return filters, limit, report_path


def handle_interactive(args: argparse.Namespace) -> dict[str, object]:
    store_dir = resolve_store_dir(args)
    ensure_store_dir(store_dir)
    source_log = resolve_source_log(args)
    audit_log = resolve_audit_log(args)
    if source_log is None:
        raise QueryCommandError(
            category="precondition_failed",
            error_code="compat_audit_source_log_unconfigured",
            message="compat audit source log is not configured",
            retryable=False,
        )
    script_text = (
        args.script_file.read_text(encoding="utf-8")
        if args.script_file is not None
        else sys.stdin.read()
    )
    transcript: list[dict[str, object]] = []
    for raw_line in script_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        action, tokens = parse_interactive_tokens(line)
        if action in {"exit", "quit"}:
            transcript.append({"command": line, "status": "exited"})
            break
        if action == "list":
            result = handle_list_saved_queries(args)
            transcript.append(
                {
                    "command": line,
                    "status": "ok",
                    "saved_query_count": result["saved_query_count"],
                }
            )
            continue
        if action == "save":
            if not tokens:
                raise QueryCommandError(
                    category="invalid_request",
                    error_code="compat_audit_interactive_save_missing_query_id",
                    message="interactive save requires a query id",
                    retryable=False,
                )
            query_id = tokens[0]
            filters, limit, _ = interactive_filters(tokens[1:])
            payload = dict(vars(args))
            payload.update(
                {
                    "command": "save-query",
                    "query_id": query_id,
                    "description": None,
                    "limit": limit,
                    "provider_id": filters.get("provider_id"),
                    "capability_id": filters.get("capability_id"),
                    "decision": filters.get("decision"),
                    "status": filters.get("status"),
                    "session_id": filters.get("session_id"),
                    "task_id": filters.get("task_id"),
                    "audit_id": filters.get("audit_id"),
                    "error_code": filters.get("error_code"),
                    "text": filters.get("text"),
                    "since": filters.get("since"),
                    "until": filters.get("until"),
                }
            )
            interactive_args = argparse.Namespace(**payload)
            result = handle_save_query(interactive_args)
            transcript.append({"command": line, "status": "ok", "saved_query": result["saved_query"]})
            continue
        if action in {"query", "run"}:
            if action == "run":
                if not tokens:
                    raise QueryCommandError(
                        category="invalid_request",
                        error_code="compat_audit_interactive_run_missing_query_id",
                        message="interactive run requires a query id",
                        retryable=False,
                    )
                query_id = tokens[0]
                filters, limit, report_path = interactive_filters(tokens[1:])
                payload = dict(vars(args))
                payload.update(
                    {
                        "command": "run-saved-query",
                        "query_id": query_id,
                        "limit": limit,
                        "write_report": report_path,
                    }
                )
                interactive_args = argparse.Namespace(**payload)
                result = handle_run_saved_query(interactive_args)
            else:
                filters, limit, report_path = interactive_filters(tokens)
                payload = dict(vars(args))
                payload.update(
                    {
                        "command": "query",
                        "write_report": report_path,
                        "limit": limit,
                        "provider_id": filters.get("provider_id"),
                        "capability_id": filters.get("capability_id"),
                        "decision": filters.get("decision"),
                        "status": filters.get("status"),
                        "session_id": filters.get("session_id"),
                        "task_id": filters.get("task_id"),
                        "audit_id": filters.get("audit_id"),
                        "error_code": filters.get("error_code"),
                        "text": filters.get("text"),
                        "since": filters.get("since"),
                        "until": filters.get("until"),
                    }
                )
                interactive_args = argparse.Namespace(**payload)
                result = handle_query(interactive_args)
            transcript.append(
                {
                    "command": line,
                    "status": "ok",
                    "match_count": result["match_count"],
                    "report_path": result["report_path"],
                }
            )
            continue
        raise QueryCommandError(
            category="invalid_request",
            error_code="compat_audit_interactive_command_invalid",
            message=f"unsupported interactive command: {action}",
            retryable=False,
        )

    context = QueryContext(
        command="interactive",
        operation="compat.audit.query.interactive",
        query_id=None,
        filters={},
        limit=None,
        started_at=utc_now(),
    )
    write_query_audit(
        audit_log,
        context=context,
        source_log=source_log,
        report_path=None,
        match_count=len(transcript),
        error=None,
    )
    return {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "ok",
        "operation": "compat.audit.query.interactive",
        "transcript": transcript,
        "source_log": str(source_log),
        "store_dir": str(store_dir),
        "saved_query_count": len(load_saved_queries(store_dir)),
    }


def build_error_payload(
    *,
    context: QueryContext,
    source_log: Path | None,
    store_dir: Path,
    audit_log: Path | None,
    error: QueryCommandError,
) -> dict[str, object]:
    result_protocol = build_result_protocol(
        context=context,
        source_log=source_log,
        store_dir=store_dir,
        audit_log=audit_log,
        match_count=None,
        report_path=None,
        saved_query_count=len(load_saved_queries(store_dir)),
        error=error.to_payload(),
    )
    payload = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "error",
        "operation": context.operation,
        "query_id": context.query_id,
        "filters": context.filters,
        "error": error.to_payload(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "result_protocol": result_protocol,
    }
    write_query_audit(
        audit_log,
        context=context,
        source_log=source_log,
        report_path=None,
        match_count=None,
        error=error.to_payload(),
    )
    return payload


def main() -> int:
    args = parse_args()
    context = QueryContext(
        command=args.command,
        operation="compat.audit.query",
        query_id=getattr(args, "query_id", None),
        filters=extract_filters(args),
        limit=getattr(args, "limit", None),
        started_at=utc_now(),
    )
    source_log = resolve_source_log(args)
    store_dir = resolve_store_dir(args)
    audit_log = resolve_audit_log(args)

    try:
        if args.command == "manifest":
            payload: dict[str, object] = build_manifest()
        elif args.command == "health":
            payload = handle_health(args)
        elif args.command == "permissions":
            payload = load_compat_permission_manifest()
        elif args.command == "query":
            payload = handle_query(args)
        elif args.command == "save-query":
            context = build_context(args, "compat.audit.saved_query.save", args.query_id)
            payload = handle_save_query(args)
        elif args.command == "list-saved-queries":
            context = QueryContext(
                command="list-saved-queries",
                operation="compat.audit.saved_query.list",
                query_id=None,
                filters={},
                limit=None,
                started_at=utc_now(),
            )
            payload = handle_list_saved_queries(args)
        elif args.command == "run-saved-query":
            context = QueryContext(
                command="run-saved-query",
                operation="compat.audit.saved_query.run",
                query_id=args.query_id,
                filters={},
                limit=getattr(args, "limit", None),
                started_at=utc_now(),
            )
            payload = handle_run_saved_query(args)
        elif args.command == "interactive":
            context = QueryContext(
                command="interactive",
                operation="compat.audit.query.interactive",
                query_id=None,
                filters={},
                limit=None,
                started_at=utc_now(),
            )
            payload = handle_interactive(args)
        else:
            raise QueryCommandError(
                category="invalid_request",
                error_code="compat_audit_command_invalid",
                message=f"unsupported command: {args.command}",
                retryable=False,
            )
    except QueryCommandError as exc:
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    source_log=source_log,
                    store_dir=store_dir,
                    audit_log=audit_log,
                    error=exc,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        error = QueryCommandError(
            category="internal",
            error_code="compat_audit_internal_error",
            message=str(exc),
            retryable=False,
        )
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    source_log=source_log,
                    store_dir=store_dir,
                    audit_log=audit_log,
                    error=error,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return error.exit_code

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
