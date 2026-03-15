#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "aios" / "compat" / "audit-query" / "runtime" / "compat_audit_query_provider.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat audit query provider smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp audit/fixture directory on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for audit logs and fixtures")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_json_command(
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
) -> tuple[int, dict]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        [sys.executable, str(RUNTIME), *args],
        cwd=ROOT,
        text=True,
        input=stdin_text,
        capture_output=True,
        env=command_env,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {sys.executable} {RUNTIME} {' '.join(args)}\n"
            f"{completed.stderr.strip()}\n{completed.stdout.strip()}"
        )
    return completed.returncode, json.loads(completed.stdout)


def write_source_log(path: Path) -> None:
    entries = [
        {
            "schema_version": "2026-03-13",
            "audit_id": "audit-1",
            "timestamp": "2026-03-14T10:00:00+00:00",
            "provider_id": "compat.mcp.bridge.local",
            "capability_id": "compat.mcp.call",
            "decision": "allowed",
            "status": "ok",
            "session_id": "session-bridge",
            "task_id": "task-1",
            "result": {"status": "ok"},
        },
        {
            "schema_version": "2026-03-13",
            "audit_id": "audit-2",
            "timestamp": "2026-03-14T10:01:00+00:00",
            "provider_id": "compat.mcp.bridge.local",
            "capability_id": "compat.a2a.forward",
            "decision": "denied",
            "status": "error",
            "session_id": "session-bridge",
            "task_id": "task-2",
            "result": {"status": "error", "error_code": "bridge_remote_timeout"},
        },
        {
            "schema_version": "2026-03-13",
            "audit_id": "audit-3",
            "timestamp": "2026-03-14T10:02:00+00:00",
            "provider_id": "compat.browser.automation.local",
            "capability_id": "compat.browser.navigate",
            "decision": "allowed",
            "status": "ok",
            "session_id": "session-browser",
            "task_id": "task-3",
            "result": {"status": "ok"},
        },
        {
            "schema_version": "2026-03-13",
            "audit_id": "audit-4",
            "timestamp": "2026-03-14T10:03:00+00:00",
            "provider_id": "compat.office.document.local",
            "capability_id": "compat.document.open",
            "decision": "allowed",
            "status": "error",
            "session_id": "session-office",
            "task_id": "task-4",
            "result": {"status": "error", "error_code": "office_timeout"},
        },
        {
            "schema_version": "2026-03-13",
            "audit_id": "audit-5",
            "timestamp": "2026-03-14T10:04:00+00:00",
            "provider_id": "compat.mcp.bridge.local",
            "capability_id": "compat.mcp.call",
            "decision": "allowed",
            "status": "ok",
            "session_id": "session-bridge",
            "task_id": "task-5",
            "result": {"status": "ok"},
        },
    ]
    path.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    temp_root = args.output_dir or Path(tempfile.mkdtemp(prefix="aios-compat-audit-query-"))
    temp_root.mkdir(parents=True, exist_ok=True)
    failed = False
    try:
        source_log = temp_root / "compat-observability.jsonl"
        audit_log = temp_root / "audit-query-provider.jsonl"
        store_dir = temp_root / "store"
        report_path = temp_root / "query-report.json"
        write_source_log(source_log)
        env = {
            "AIOS_COMPAT_OBSERVABILITY_LOG": str(source_log),
            "AIOS_COMPAT_AUDIT_QUERY_AUDIT_LOG": str(audit_log),
            "AIOS_COMPAT_AUDIT_QUERY_STORE_DIR": str(store_dir),
        }

        _, manifest = run_json_command("manifest", env=env)
        require(manifest["provider_id"] == "compat.audit.query.local", "manifest provider mismatch")
        require(manifest["worker_contract"] == "compat-audit-query-v1", "manifest worker contract mismatch")
        require(
            {
                "audit-entry-query",
                "saved-query-store",
                "interactive-query-script",
                "audit-query-result-protocol-v1",
            }.issubset(set(manifest["implemented_methods"])),
            "manifest methods mismatch",
        )

        _, health = run_json_command("health", env=env)
        require(health["status"] == "available", "health status mismatch")
        require(health["source_log_path"] == str(source_log), "health source log mismatch")
        require(health["audit_log_path"] == str(audit_log), "health audit log mismatch")
        require(health["store_dir"] == str(store_dir), "health store dir mismatch")

        _, permissions = run_json_command("permissions", env=env)
        require(permissions["required_permissions"] == ["audit.read"], "permissions mismatch")

        _, query_payload = run_json_command(
            "query",
            "--provider-id",
            "compat.mcp.bridge.local",
            "--decision",
            "allowed",
            "--limit",
            "2",
            "--write-report",
            str(report_path),
            env=env,
        )
        require(query_payload["status"] == "ok", "query should succeed")
        require(query_payload["match_count"] == 2, "query match count mismatch")
        require(query_payload["report_path"] == str(report_path), "query report path mismatch")
        require(report_path.exists(), "query report not written")

        _, save_payload = run_json_command(
            "save-query",
            "--query-id",
            "bridge-denies",
            "--provider-id",
            "compat.mcp.bridge.local",
            "--decision",
            "denied",
            env=env,
        )
        require(save_payload["saved_query"]["query_id"] == "bridge-denies", "saved query id mismatch")

        _, listed = run_json_command("list-saved-queries", env=env)
        require(listed["saved_query_count"] == 1, "saved query count mismatch")

        _, run_payload = run_json_command("run-saved-query", "--query-id", "bridge-denies", env=env)
        require(run_payload["status"] == "ok", "run-saved-query should succeed")
        require(run_payload["match_count"] == 1, "run-saved-query match count mismatch")
        require(Path(run_payload["report_path"]).exists(), "saved query report missing")

        interactive_script = "\n".join(
            [
                "save office-timeouts provider_id=compat.office.document.local error_code=office_timeout",
                "run bridge-denies",
                "query provider_id=compat.browser.automation.local limit=1",
                "list",
                "exit",
            ]
        )
        _, interactive_payload = run_json_command(
            "interactive",
            env=env,
            stdin_text=interactive_script,
        )
        transcript = interactive_payload["transcript"]
        require(len(transcript) >= 4, "interactive transcript too short")
        require(any(item.get("match_count") == 1 for item in transcript if item.get("status") == "ok"), "interactive query result missing")
        require(interactive_payload["saved_query_count"] == 2, "interactive saved query count mismatch")

        require(audit_log.exists(), "provider audit log should be created")
        audit_entries = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        require(len(audit_entries) >= 4, "provider audit log should contain command entries")
        require(all(entry["schema_version"] == "2026-03-14" for entry in audit_entries), "provider audit schema mismatch")

        print(
            json.dumps(
                {
                    "provider_id": manifest["provider_id"],
                    "worker_contract": manifest["worker_contract"],
                    "query_match_count": query_payload["match_count"],
                    "saved_query_count": interactive_payload["saved_query_count"],
                    "provider_audit_entries": len(audit_entries),
                    "store_dir": str(store_dir),
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
        preserve_state = failed or args.keep_state or args.output_dir is not None
        if preserve_state:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
