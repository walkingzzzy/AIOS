#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "aios" / "compat" / "mcp-bridge" / "runtime" / "mcp_bridge_provider.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat MCP bridge provider smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp audit/fixture directory on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for audit logs and fixtures")
    return parser.parse_args()


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "AIOSBridgeSmoke/0.2"

    def send_json(self, status_code: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw_body)
        if self.path == "/mcp":
            if self.headers.get("Authorization") != "Bearer smoke-secret":
                self.send_json(401, {"error": "missing bearer auth"})
                return
            if self.headers.get("X-AIOS-Remote-Provider") != "tools.echo.remote":
                self.send_json(401, {"error": "provider ref missing"})
                return
            response = {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "echo_method": payload.get("method"),
                    "echo_params": payload.get("params") or {},
                    "remote_provider": self.headers.get("X-AIOS-Remote-Provider"),
                    "target_hash": self.headers.get("X-AIOS-Target-Hash"),
                },
            }
        elif self.path == "/a2a":
            encoded_token = self.headers.get("X-AIOS-Execution-Token")
            if not encoded_token:
                self.send_json(401, {"error": "missing execution token"})
                return
            token = json.loads(base64.urlsafe_b64decode(encoded_token.encode("ascii")).decode("utf-8"))
            if self.headers.get("X-AIOS-Remote-Provider") != "a2a.forward.remote":
                self.send_json(401, {"error": "provider ref missing"})
                return
            if token.get("capability_id") != "compat.a2a.forward":
                self.send_json(401, {"error": "token capability mismatch"})
                return
            if token.get("target_hash") != self.headers.get("X-AIOS-Target-Hash"):
                self.send_json(401, {"error": "token target hash mismatch"})
                return
            response = {
                "accepted": True,
                "received": payload,
                "remote_provider": self.headers.get("X-AIOS-Remote-Provider"),
            }
        elif self.path == "/slow":
            time.sleep(0.5)
            response = {"delayed": True}
        else:
            response = {"error": "unknown path"}
        self.send_json(200, response)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_json_command(
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> tuple[int, dict]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        [sys.executable, str(RUNTIME), *args],
        cwd=ROOT,
        env=command_env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {sys.executable} {RUNTIME} {' '.join(args)}\n"
            f"{completed.stderr.strip()}\n{completed.stdout.strip()}"
        )
    return completed.returncode, json.loads(completed.stdout)


def remote_target_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.strip().encode("utf-8")).hexdigest()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), BridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    temp_root = args.output_dir or Path(tempfile.mkdtemp(prefix="aios-mcp-bridge-"))
    temp_root.mkdir(parents=True, exist_ok=True)
    failed = False

    try:
        endpoint_base = f"http://127.0.0.1:{server.server_address[1]}"
        audit_log = temp_root / "mcp-bridge-audit.jsonl"
        remote_registry = temp_root / "remote-registry.json"
        mcp_endpoint = f"{endpoint_base}/mcp"
        a2a_endpoint = f"{endpoint_base}/a2a"
        a2a_target_hash = remote_target_hash(a2a_endpoint)
        forward_token = {
            "user_id": "compat-smoke-user",
            "session_id": "compat-smoke-session",
            "task_id": "compat-smoke-task",
            "capability_id": "compat.a2a.forward",
            "target_hash": a2a_target_hash,
            "execution_location": "sandbox",
            "signature": "smoke-signature",
        }
        env = {
            "AIOS_MCP_BRIDGE_TRUST_MODE": "allowlist",
            "AIOS_MCP_BRIDGE_ALLOWLIST": "127.0.0.1,localhost",
            "AIOS_COMPAT_MCP_BRIDGE_AUDIT_LOG": str(audit_log),
            "AIOS_MCP_BRIDGE_REMOTE_REGISTRY": str(remote_registry),
            "MCP_BRIDGE_SMOKE_SECRET": "smoke-secret",
        }

        _, manifest = run_json_command("manifest", env=env)
        require(manifest["provider_id"] == "compat.mcp.bridge.local", "manifest provider mismatch")
        require(manifest["status"] == "baseline", "manifest status should be baseline")
        require(manifest["worker_contract"] == "compat-mcp-bridge-v1", "manifest worker contract mismatch")
        require(
            {
                "jsonrpc-http-call",
                "json-http-forward",
                "permission-manifest",
                "bridge-result-protocol-v1",
                "audit-jsonl",
                "remote-register",
                "remote-list",
                "remote-auth-header-v1",
            }.issubset(
                set(manifest["implemented_methods"])
            ),
            "manifest methods mismatch",
        )
        require(
            manifest["result_protocol_schema_ref"] == "aios/compat-mcp-bridge-result.schema.json",
            "manifest result protocol schema mismatch",
        )
        require(
            (manifest.get("compat_permission_manifest") or {}).get("provider_id") == "compat.mcp.bridge.local",
            "manifest compat permission manifest mismatch",
        )
        require(
            (manifest.get("trust_policy") or {}).get("mode") == "allowlist",
            "manifest trust mode mismatch",
        )

        _, health = run_json_command("health", env=env)
        require(health["status"] == "available", "health status should be available")
        require(health["engine"] == "http-bridge-baseline", "unexpected bridge engine")
        require(health["worker_contract"] == "compat-mcp-bridge-v1", "health worker contract mismatch")
        require((health.get("trust_policy") or {}).get("enforced") is True, "health trust policy should be enforced")
        require(health["audit_log_configured"] is True, "health should report audit log configured")
        require(health["audit_log_path"] == str(audit_log), "health audit log path mismatch")
        require(health["registered_remote_count"] == 0, "health should start with zero remote registrations")

        _, permissions = run_json_command("permissions", env=env)
        require(permissions["required_permissions"] == ["bridge.remote"], "mcp bridge permissions mismatch")

        _, registered_call = run_json_command(
            "register-remote",
            "--provider-ref",
            "tools.echo.remote",
            "--endpoint",
            mcp_endpoint,
            "--capability",
            "compat.mcp.call",
            "--auth-mode",
            "bearer",
            "--auth-secret-env",
            "MCP_BRIDGE_SMOKE_SECRET",
            env=env,
        )
        require(
            registered_call["registration"]["provider_ref"] == "tools.echo.remote",
            "call remote registration mismatch",
        )

        _, registered_forward = run_json_command(
            "register-remote",
            "--provider-ref",
            "a2a.forward.remote",
            "--endpoint",
            a2a_endpoint,
            "--capability",
            "compat.a2a.forward",
            "--auth-mode",
            "execution-token",
            env=env,
        )
        require(
            registered_forward["registration"]["target_hash"] == a2a_target_hash,
            "forward remote target hash mismatch",
        )

        _, listed = run_json_command("list-remotes", env=env)
        require(listed["registered_remote_count"] == 2, "remote registry count mismatch")
        require(
            {entry["provider_ref"] for entry in listed["registered_remotes"]}
            == {"tools.echo.remote", "a2a.forward.remote"},
            "listed remote refs mismatch",
        )

        _, registered_health = run_json_command("health", env=env)
        require(registered_health["registered_remote_count"] == 2, "health remote count mismatch")
        require(
            set(registered_health["remote_auth_modes"]) == {"bearer", "execution-token"},
            "health remote auth modes mismatch",
        )

        _, call_payload = run_json_command(
            "call",
            "--provider-ref",
            "tools.echo.remote",
            "--tool",
            "tools.echo",
            "--arguments",
            '{"message":"hello"}',
            env=env,
        )
        require(call_payload["status"] == "ok", "call should succeed")
        require(call_payload["response"]["result"]["echo_method"] == "tools.echo", "call method mismatch")
        require(call_payload["response"]["result"]["echo_params"]["message"] == "hello", "call params mismatch")
        require(
            (call_payload.get("result_protocol") or {}).get("status") == "ok",
            "call result protocol should report ok",
        )
        require(
            ((call_payload.get("result_protocol") or {}).get("policy") or {}).get("trust_mode") == "allowlist",
            "call result protocol trust mode mismatch",
        )
        require(call_payload.get("audit_id"), "call should expose audit_id")
        require(call_payload.get("audit_log") == str(audit_log), "call audit log mismatch")
        require(call_payload["provider_ref"] == "tools.echo.remote", "call provider ref mismatch")
        require(
            call_payload["response"]["result"]["remote_provider"] == "tools.echo.remote",
            "call remote provider header mismatch",
        )

        _, forward_payload = run_json_command(
            "forward",
            "--provider-ref",
            "a2a.forward.remote",
            "--payload",
            '{"task":"sync","priority":"normal"}',
            env={**env, "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(forward_token)},
        )
        require(forward_payload["status"] == "ok", "forward should succeed")
        require(forward_payload["response"]["accepted"] is True, "forward response should be accepted")
        require(forward_payload["response"]["received"]["task"] == "sync", "forward payload mismatch")
        require(
            forward_payload["response"]["remote_provider"] == "a2a.forward.remote",
            "forward remote provider mismatch",
        )

        trust_code, trust_payload = run_json_command(
            "call",
            "--endpoint",
            "https://example.com/mcp",
            "--tool",
            "tools.echo",
            "--arguments",
            '{"message":"blocked"}',
            env=env,
            check=False,
        )
        require(trust_code == 13, f"trust rejection should exit 13, got {trust_code}")
        require(trust_payload["status"] == "error", "trust rejection should return error payload")
        require(
            (trust_payload.get("error") or {}).get("error_code") == "bridge_endpoint_not_allowlisted",
            "trust rejection error code mismatch",
        )

        timeout_code, timeout_payload = run_json_command(
            "forward",
            "--endpoint",
            f"{endpoint_base}/slow",
            "--payload",
            '{"task":"delay"}',
            "--timeout-seconds",
            "0.1",
            env=env,
            check=False,
        )
        require(timeout_code == 124, f"timeout should exit 124, got {timeout_code}")
        require(timeout_payload["status"] == "error", "timeout should return error payload")
        require(
            (timeout_payload.get("error") or {}).get("error_code") == "bridge_remote_timeout",
            "timeout error code mismatch",
        )

        wrong_target_token = dict(forward_token)
        wrong_target_token["target_hash"] = "wrong-target-hash"
        wrong_target_code, wrong_target_payload = run_json_command(
            "forward",
            "--provider-ref",
            "a2a.forward.remote",
            "--payload",
            '{"task":"sync"}',
            env={**env, "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(wrong_target_token)},
            check=False,
        )
        require(wrong_target_code == 13, f"wrong target hash should exit 13, got {wrong_target_code}")
        require(
            (wrong_target_payload.get("error") or {}).get("error_code") == "bridge_execution_token_target_mismatch",
            "wrong target hash error code mismatch",
        )

        invalid_code, invalid_payload = run_json_command(
            "call",
            "--provider-ref",
            "tools.echo.remote",
            "--tool",
            "tools.echo",
            "--arguments",
            "{",
            env=env,
            check=False,
        )
        require(invalid_code == 2, f"invalid JSON should exit 2, got {invalid_code}")
        require(
            (invalid_payload.get("error") or {}).get("error_code") == "bridge_invalid_arguments_json",
            "invalid JSON error code mismatch",
        )
        require(audit_log.exists(), "mcp bridge audit log should be created")
        audit_entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line.strip()]
        require(len(audit_entries) >= 6, "mcp bridge audit log should contain command entries")
        require(any(entry["decision"] == "allowed" for entry in audit_entries), "mcp bridge audit log missing allowed entry")
        require(any(entry["decision"] == "denied" for entry in audit_entries), "mcp bridge audit log missing denied entry")
        require(any((entry.get("result") or {}).get("error_code") == "bridge_remote_timeout" for entry in audit_entries), "mcp bridge audit log missing timeout entry")
        require(
            any((entry.get("remote_registration") or {}).get("provider_ref") == "tools.echo.remote" for entry in audit_entries),
            "mcp bridge audit log missing remote registration metadata",
        )
        require(all(entry.get("schema_version") == "2026-03-13" for entry in audit_entries), "mcp bridge audit log schema_version mismatch")
        require(all(entry.get("artifact_path") == str(audit_log) for entry in audit_entries), "mcp bridge audit log artifact_path mismatch")

        print(
            json.dumps(
                {
                    "provider_id": manifest["provider_id"],
                    "worker_contract": manifest["worker_contract"],
                    "call_remote_status": call_payload["remote_status"],
                    "forward_remote_status": forward_payload["remote_status"],
                    "trust_mode": health["trust_policy"]["mode"],
                    "registered_remote_count": listed["registered_remote_count"],
                    "blocked_error": trust_payload["error"]["error_code"],
                    "timeout_error": timeout_payload["error"]["error_code"],
                    "wrong_target_error": wrong_target_payload["error"]["error_code"],
                    "audit_entries": len(audit_entries),
                    "audit_log": str(audit_log),
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
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        preserve_state = failed or args.keep_state or args.output_dir is not None
        if preserve_state:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
