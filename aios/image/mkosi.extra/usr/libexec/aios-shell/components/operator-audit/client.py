#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from prototype import (
    default_browser_remote_registry,
    default_compat_observability_log,
    default_mcp_remote_registry,
    default_office_remote_registry,
    default_policy_audit_log,
    default_provider_registry_state_dir,
    default_remote_audit_log,
    default_runtime_events_log,
    load_operator_audit,
)
_PRIVACY_MEMORY_PROTOTYPE_MODULE: ModuleType | None = None


def _load_module(module_name: str, path: Path) -> ModuleType:
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_privacy_memory_prototype_module() -> ModuleType:
    global _PRIVACY_MEMORY_PROTOTYPE_MODULE
    if _PRIVACY_MEMORY_PROTOTYPE_MODULE is not None:
        return _PRIVACY_MEMORY_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "privacy-memory" / "prototype.py"
    _PRIVACY_MEMORY_PROTOTYPE_MODULE = _load_module(
        "aios_shell_privacy_memory_prototype",
        module_path,
    )
    return _PRIVACY_MEMORY_PROTOTYPE_MODULE


def default_runtime_platform_env_path() -> Path:
    return load_privacy_memory_prototype_module().default_runtime_platform_env_path()


def build_privacy_memory_state(runtime_platform_env_path: Path | None) -> dict:
    return load_privacy_memory_prototype_module().build_privacy_memory_state(runtime_platform_env_path)


def build_summary(audit: dict, privacy_memory: dict | None = None) -> dict:
    remote_governance = audit.get("remote_governance") or {}
    privacy_memory = privacy_memory or {}
    return {
        "record_count": audit.get("record_count", 0),
        "issue_count": audit.get("issue_count", 0),
        "task_count": len(audit.get("task_ids", [])),
        "by_source": audit.get("source_counts", {}),
        "issue_by_source": audit.get("issue_source_counts", {}),
        "remote_governance_entry_count": remote_governance.get("entry_count", 0),
        "remote_governance_matched_entry_count": remote_governance.get("matched_entry_count", 0),
        "remote_governance_issue_count": remote_governance.get("issue_count", 0),
        "remote_governance_fleet_count": remote_governance.get("fleet_count", 0),
        "artifact_paths": audit.get("artifact_paths", {}),
        "memory_enabled": privacy_memory.get("memory_enabled", True),
        "memory_retention_days": privacy_memory.get("memory_retention_days"),
        "audit_retention_days": privacy_memory.get("audit_retention_days"),
        "approval_default_policy": privacy_memory.get("approval_default_policy"),
        "remote_prompt_level": privacy_memory.get("remote_prompt_level"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS operator audit shell client")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "summary", "issues"])
    parser.add_argument("--policy-audit-log", type=Path, default=default_policy_audit_log())
    parser.add_argument("--runtime-events-log", type=Path, default=default_runtime_events_log())
    parser.add_argument("--remote-audit-log", type=Path, default=default_remote_audit_log())
    parser.add_argument(
        "--compat-observability-log",
        type=Path,
        default=default_compat_observability_log(),
    )
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--mcp-remote-registry", type=Path, default=default_mcp_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--source")
    parser.add_argument("--severity")
    parser.add_argument("--provider-id")
    parser.add_argument("--provider-ref")
    parser.add_argument("--capability-id")
    parser.add_argument("--decision")
    parser.add_argument("--status")
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--approval-id")
    parser.add_argument("--approval-ref")
    parser.add_argument("--audit-id")
    parser.add_argument("--error-code")
    parser.add_argument("--text")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--fleet-id")
    parser.add_argument("--governance-group")
    parser.add_argument("--attestation-mode")
    parser.add_argument("--control-plane-status")
    parser.add_argument("--write-report", type=Path)
    parser.add_argument("--runtime-platform-env", type=Path, default=default_runtime_platform_env_path())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    filters = {
        "source": args.source,
        "severity": args.severity,
        "provider_id": args.provider_id,
        "provider_ref": args.provider_ref,
        "capability_id": args.capability_id,
        "decision": args.decision,
        "status": args.status,
        "session_id": args.session_id,
        "task_id": args.task_id,
        "approval_id": args.approval_id,
        "approval_ref": args.approval_ref,
        "audit_id": args.audit_id,
        "error_code": args.error_code,
        "text": args.text,
        "since": args.since,
        "until": args.until,
        "fleet_id": args.fleet_id,
        "governance_group": args.governance_group,
        "attestation_mode": args.attestation_mode,
        "control_plane_status": args.control_plane_status,
    }
    audit = load_operator_audit(
        args.policy_audit_log,
        args.runtime_events_log,
        args.remote_audit_log,
        args.compat_observability_log,
        browser_remote_registry=args.browser_remote_registry,
        office_remote_registry=args.office_remote_registry,
        mcp_remote_registry=args.mcp_remote_registry,
        provider_registry_state_dir=args.provider_registry_state_dir,
        limit=args.limit,
        filters=filters,
        report_path=args.write_report,
    )

    if args.command == "summary":
        summary = build_summary(audit, build_privacy_memory_state(args.runtime_platform_env))
        summary["matched_record_count"] = audit.get("matched_record_count", 0)
        summary["filters"] = (audit.get("query") or {}).get("filters", {})
        summary["report_path"] = (audit.get("query") or {}).get("report_path")
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"record_count: {summary['record_count']}")
            print(f"matched_record_count: {summary['matched_record_count']}")
            print(f"issue_count: {summary['issue_count']}")
            print(f"task_count: {summary['task_count']}")
            print(f"by_source: {json.dumps(summary['by_source'], ensure_ascii=False, sort_keys=True)}")
            print(
                f"issue_by_source: {json.dumps(summary['issue_by_source'], ensure_ascii=False, sort_keys=True)}"
            )
            print(f"remote_governance_issue_count: {summary['remote_governance_issue_count']}")
            print(f"remote_governance_matched_entry_count: {summary['remote_governance_matched_entry_count']}")
            print(f"filters: {json.dumps(summary['filters'], ensure_ascii=False, sort_keys=True)}")
            print(f"report_path: {summary['report_path'] or '-'}")
        return 0

    key = "issues" if args.command == "issues" else "recent_records"
    payload = {key: audit.get(key, [])}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        items = payload[key]
        if not items:
            print("no operator audit records")
        for item in items:
            print(
                f"- [{item.get('source')}] {item.get('title')} :: {item.get('detail')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
