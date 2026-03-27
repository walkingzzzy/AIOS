#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prototype import (
    default_browser_remote_registry,
    default_remote_registration_request_path,
    default_office_remote_registry,
    default_mcp_remote_registry,
    default_provider_registry_state_dir,
    load_remote_governance,
    load_remote_registration_request,
)


def build_summary(governance: dict, request_summary: dict) -> dict:
    return {
        "entry_count": governance.get("entry_count", 0),
        "matched_entry_count": governance.get("matched_entry_count", 0),
        "issue_count": governance.get("issue_count", 0),
        "fleet_count": len(governance.get("fleet_summary", [])),
        "source_counts": governance.get("source_counts", {}),
        "filtered_source_counts": governance.get("filtered_source_counts", {}),
        "status_counts": governance.get("status_counts", {}),
        "filtered_status_counts": governance.get("filtered_status_counts", {}),
        "fleet_ids": governance.get("fleet_ids", []),
        "control_plane_provider_ids": governance.get("control_plane_provider_ids", []),
        "query": governance.get("query", {}),
        "artifact_paths": governance.get("artifact_paths", {}),
        "request_source_status": request_summary.get("source_status"),
        "request_ready": request_summary.get("ready", False),
        "request_provider_ref": request_summary.get("provider_ref"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS compat remote governance shell client")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "summary", "issues"])
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--mcp-remote-registry", type=Path, default=default_mcp_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--remote-registration-request", type=Path, default=default_remote_registration_request_path())
    parser.add_argument("--runtime-platform-env", type=Path)
    parser.add_argument("--agent-socket", type=Path)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--source")
    parser.add_argument("--severity")
    parser.add_argument("--fleet-id")
    parser.add_argument("--governance-group")
    parser.add_argument("--status")
    parser.add_argument("--provider-ref")
    parser.add_argument("--provider-id")
    parser.add_argument("--attestation-mode")
    parser.add_argument("--control-plane-status")
    parser.add_argument("--approval-ref")
    parser.add_argument("--text")
    parser.add_argument("--issue-only", action="store_true")
    parser.add_argument("--write-report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    filters = {
        "source": args.source,
        "severity": args.severity,
        "fleet_id": args.fleet_id,
        "governance_group": args.governance_group,
        "status": args.status,
        "provider_ref": args.provider_ref,
        "provider_id": args.provider_id,
        "attestation_mode": args.attestation_mode,
        "control_plane_status": args.control_plane_status,
        "approval_ref": args.approval_ref,
        "text": args.text,
    }
    governance = load_remote_governance(
        args.browser_remote_registry,
        args.office_remote_registry,
        args.mcp_remote_registry,
        args.provider_registry_state_dir,
        limit=args.limit,
        filters=filters,
        issue_only=args.issue_only,
        report_path=args.write_report,
    )
    request_summary = load_remote_registration_request(args.remote_registration_request)

    if args.command == "summary":
        summary = build_summary(governance, request_summary)
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"entry_count: {summary['entry_count']}")
            print(f"matched_entry_count: {summary['matched_entry_count']}")
            print(f"issue_count: {summary['issue_count']}")
            print(f"fleet_count: {summary['fleet_count']}")
            print(f"source_counts: {json.dumps(summary['source_counts'], ensure_ascii=False, sort_keys=True)}")
            print(
                f"filtered_status_counts: {json.dumps(summary['filtered_status_counts'], ensure_ascii=False, sort_keys=True)}"
            )
            print(
                f"fleet_ids: {json.dumps(summary['fleet_ids'], ensure_ascii=False)}"
            )
        return 0

    key = "issues" if args.command == "issues" else "entries"
    payload = {key: governance.get(key, [])}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        items = payload[key]
        if not items:
            print("no remote governance entries")
        for item in items:
            if key == "issues":
                print(
                    f"- [{item.get('severity')}] {item.get('title')} :: {item.get('detail')}"
                )
            else:
                print(
                    f"- [{item.get('source')}] {item.get('provider_ref') or item.get('control_plane_provider_id') or '-'} "
                    f"status={item.get('registration_status')} fleet={item.get('fleet_id') or '-'} "
                    f"control_plane={item.get('control_plane_provider_id') or '-'}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
