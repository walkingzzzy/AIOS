#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXECUTOR = ROOT / "aios" / "compat" / "code-sandbox" / "runtime" / "aios_sandbox_executor.py"
DEFAULT_WORK_ROOT = ROOT / "out" / "validation" / "code-sandbox-smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat code sandbox smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp audit/artifact directory on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for audit logs and fixtures")
    return parser.parse_args()


def run_json(command: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> tuple[int, dict]:
    completed = subprocess.run(
        command,
        check=check,
        text=True,
        capture_output=True,
        env=env,
    )
    return completed.returncode, json.loads(completed.stdout)


def resolve_work_root(output_dir: Path | None) -> Path:
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    if DEFAULT_WORK_ROOT.exists():
        shutil.rmtree(DEFAULT_WORK_ROOT, ignore_errors=True)
    DEFAULT_WORK_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_WORK_ROOT


def main() -> int:
    args = parse_args()
    manifest_code, manifest = run_json([sys.executable, str(EXECUTOR), "manifest"])
    if manifest_code != 0:
        raise SystemExit(f"manifest returned non-zero: {manifest_code}")
    if manifest["status"] != "available":
        raise SystemExit(f"unexpected manifest status: {manifest['status']}")
    if manifest.get("worker_contract") != "compat-sandbox-executor-v1":
        raise SystemExit("manifest worker contract mismatch")
    if manifest.get("result_protocol_schema_ref") != "aios/compat-sandbox-result.schema.json":
        raise SystemExit("manifest result protocol schema mismatch")
    compat_permission_manifest = manifest.get("compat_permission_manifest") or {}
    if compat_permission_manifest.get("provider_id") != "compat.code.sandbox.local":
        raise SystemExit("manifest did not expose compat permission manifest")

    permissions_code, permissions = run_json([sys.executable, str(EXECUTOR), "permissions"])
    if permissions_code != 0:
        raise SystemExit(f"permissions returned non-zero: {permissions_code}")
    if permissions.get("required_permissions") != ["sandbox.local"]:
        raise SystemExit(f"unexpected sandbox required permissions: {permissions.get('required_permissions')}")

    health_code, health = run_json([sys.executable, str(EXECUTOR), "health"])
    if health_code != 0:
        raise SystemExit(f"health returned non-zero: {health_code}")
    if health["engine"] not in {"bounded-local-python", "os-level-bwrap"}:
        raise SystemExit(f"unexpected health engine: {health['engine']}")
    if sorted(health.get("supported_engines") or []) != ["bounded-local-python", "os-level-bwrap"]:
        raise SystemExit("health supported_engines mismatch")
    if health.get("worker_contract") != "compat-sandbox-executor-v1":
        raise SystemExit("health worker contract mismatch")

    temp_root = resolve_work_root(args.output_dir)
    failed = False

    try:
        input_dir = temp_root / "input"
        output_dir = temp_root / "output"
        audit_log = temp_root / "audit.jsonl"
        script_path = temp_root / "task.py"
        input_dir.mkdir(parents=True, exist_ok=True)
        input_dir.joinpath("data.txt").write_text("artifact-ok\n")
        script_path.write_text(
            "from pathlib import Path\n"
            "import socket\n"
            "import subprocess\n"
            "source = Path('input/data.txt').read_text().strip()\n"
            "network_blocked = False\n"
            "try:\n"
            "    socket.create_connection(('example.com', 80), timeout=0.1)\n"
            "except Exception as exc:\n"
            "    network_blocked = isinstance(exc, PermissionError) or 'disabled' in str(exc).lower()\n"
            "subprocess_blocked = False\n"
            "try:\n"
            "    subprocess.run(['echo', 'x'], check=True)\n"
            "except Exception as exc:\n"
            "    subprocess_blocked = isinstance(exc, PermissionError) or 'disabled' in str(exc).lower()\n"
            "Path('output').mkdir(exist_ok=True)\n"
            "Path('output/result.txt').write_text(f'{source}:{network_blocked}:{subprocess_blocked}\\n')\n"
            "print(f'sandbox-ok:{source}:{network_blocked}:{subprocess_blocked}')\n"
        )

        env = os.environ.copy()
        env["AIOS_COMPAT_CODE_SANDBOX_AUDIT_LOG"] = str(audit_log)
        completed = subprocess.run(
            [
                sys.executable,
                str(EXECUTOR),
                "execute",
                "--code-file",
                str(script_path),
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
                "--timeout-seconds",
                "2",
                "--memory-mb",
                "128",
                "--json",
            ],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        payload = json.loads(completed.stdout)
        if payload["status"] != "ok":
            raise SystemExit(f"unexpected sandbox status: {payload['status']}")
        if payload["network_access"] != "disabled":
            raise SystemExit(f"unexpected network policy: {payload['network_access']}")
        if payload["subprocess_access"] != "disabled":
            raise SystemExit(f"unexpected subprocess policy: {payload['subprocess_access']}")
        if payload["sandbox_class"] != health["engine"]:
            raise SystemExit("sandbox class did not match reported engine")
        if "sandbox-ok:artifact-ok:True:True" not in payload["stdout"]:
            raise SystemExit("sandbox stdout did not contain expected marker")
        if payload["artifact_count"] != 1:
            raise SystemExit(f"unexpected artifact count: {payload['artifact_count']}")
        result_protocol = payload.get("result_protocol") or {}
        if result_protocol.get("protocol_version") != "1.0.0":
            raise SystemExit("sandbox result protocol version mismatch")
        if result_protocol.get("worker_contract") != "compat-sandbox-executor-v1":
            raise SystemExit("sandbox result protocol worker contract mismatch")
        if (result_protocol.get("request") or {}).get("language") != "python":
            raise SystemExit("sandbox result protocol request language mismatch")
        if (result_protocol.get("policy") or {}).get("compat_permission_manifest", {}).get("provider_id") != "compat.code.sandbox.local":
            raise SystemExit("sandbox result protocol missing compat permission manifest")
        if (result_protocol.get("policy") or {}).get("filesystem_access") != "sandbox-workspace":
            raise SystemExit("sandbox result protocol filesystem_access mismatch")
        if (result_protocol.get("resources") or {}).get("exit_code") != 0:
            raise SystemExit("sandbox result protocol exit code mismatch")
        if (result_protocol.get("audit") or {}).get("capability_id") != "compat.code.execute":
            raise SystemExit("sandbox result protocol missing audit capability_id")
        if (result_protocol.get("audit") or {}).get("taint_behavior") != "dynamic-code-tainted":
            raise SystemExit("sandbox result protocol missing audit taint behavior")
        if result_protocol.get("error") is not None:
            raise SystemExit("sandbox success path should not include error payload")
        result_path = output_dir / "result.txt"
        if result_path.read_text().strip() != "artifact-ok:True:True":
            raise SystemExit("sandbox output artifact content mismatch")
        if not audit_log.exists():
            raise SystemExit("audit log was not created")
        audit_entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line.strip()]
        if not audit_entries or audit_entries[-1]["decision"] != "allowed":
            raise SystemExit("sandbox audit log did not record allowed decision")
        latest = audit_entries[-1]
        if latest.get("schema_version") != "2026-03-13":
            raise SystemExit("sandbox audit log schema_version mismatch")
        if latest.get("generated_at") is None:
            raise SystemExit("sandbox audit log missing generated_at")
        if latest.get("artifact_path") != str(audit_log):
            raise SystemExit("sandbox audit log artifact_path mismatch")
        if latest.get("status") != "ok":
            raise SystemExit("sandbox audit log status mismatch")
        if latest.get("operation") != "compat.code.execute":
            raise SystemExit("sandbox audit log operation mismatch")

        timeout_script = temp_root / "timeout.py"
        timeout_script.write_text("import time\ntime.sleep(2)\n")
        timeout = subprocess.run(
            [
                sys.executable,
                str(EXECUTOR),
                "execute",
                "--code-file",
                str(timeout_script),
                "--timeout-seconds",
                "0.2",
                "--memory-mb",
                "128",
                "--json",
            ],
            check=False,
            text=True,
            capture_output=True,
            env=env,
        )
        timeout_payload = json.loads(timeout.stdout)
        if timeout.returncode != 124:
            raise SystemExit(f"unexpected timeout exit code: {timeout.returncode}")
        if timeout_payload.get("status") != "timed-out":
            raise SystemExit("sandbox timeout payload status mismatch")
        if (timeout_payload.get("error") or {}).get("error_code") != "sandbox_execution_timed_out":
            raise SystemExit("sandbox timeout error payload mismatch")

        denied = subprocess.run(
            [
                sys.executable,
                str(EXECUTOR),
                "execute",
                "--code-file",
                str(script_path),
                "--timeout-seconds",
                "12",
                "--memory-mb",
                "128",
                "--json",
            ],
            check=False,
            text=True,
            capture_output=True,
            env=env,
        )
        denied_payload = json.loads(denied.stdout)
        if denied.returncode == 0:
            raise SystemExit("sandbox denial path unexpectedly succeeded")
        if denied_payload.get("status") != "error":
            raise SystemExit("sandbox denial payload status mismatch")
        if (denied_payload.get("error") or {}).get("error_code") != "sandbox_timeout_budget_exceeded":
            raise SystemExit("sandbox denial error payload mismatch")
        if (denied_payload.get("result_protocol") or {}).get("error", {}).get("category") != "policy":
            raise SystemExit("sandbox denial result protocol missing policy category")

        denied_entry = [json.loads(line) for line in audit_log.read_text().splitlines() if line.strip()][-1]
        if denied_entry.get("decision") != "denied":
            raise SystemExit("sandbox denial audit decision mismatch")
        if denied_entry.get("status") != "error":
            raise SystemExit("sandbox denial audit status mismatch")

        print(json.dumps({"status": "ok", "executor": str(EXECUTOR), "audit_log": str(audit_log)}, indent=2))
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
