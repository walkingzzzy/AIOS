#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "aios" / "compat" / "mcp-bridge" / "runtime" / "mcp_bridge_provider.py"
DEFAULT_WORK_ROOT = ROOT / "out" / "validation" / "mcp-bridge-provider-smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat MCP bridge provider smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp audit/fixture directory on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for audit logs and fixtures")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing the agentd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for agentd control-plane smoke")
    return parser.parse_args()


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "AIOSBridgeSmoke/0.3"

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


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    base_dir = bin_dir or default_aios_bin_dir(ROOT)
    return resolve_binary_path(base_dir, name)


def provider_descriptor_dirs() -> list[Path]:
    return [
        ROOT / "aios" / "sdk" / "providers",
        ROOT / "aios" / "runtime" / "providers",
        ROOT / "aios" / "shell" / "providers",
        ROOT / "aios" / "compat" / "browser" / "providers",
        ROOT / "aios" / "compat" / "office" / "providers",
        ROOT / "aios" / "compat" / "mcp-bridge" / "providers",
        ROOT / "aios" / "compat" / "code-sandbox" / "providers",
    ]


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"

def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def wait_for_socket(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=1.5)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def build_agentd_env(temp_root: Path) -> tuple[dict[str, str], Path]:
    runtime_root = temp_root / "run"
    state_root = temp_root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    socket_path = runtime_root / "agentd" / "agentd.sock"
    env = os.environ.copy()
    env.update(
        {
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "agentd"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "agentd"),
            "AIOS_AGENTD_SOCKET_PATH": str(socket_path),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "registry"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": os.pathsep.join(str(path) for path in provider_descriptor_dirs()),
            "AIOS_PROVIDER_REMOTE_REQUIRE_VERIFIED_ATTESTATION": "1",
            "AIOS_PROVIDER_REMOTE_ALLOWED_FLEETS": "fleet-mcp",
            "AIOS_PROVIDER_REMOTE_ALLOWED_GOVERNANCE_GROUPS": "operator-audit",
        }
    )
    return env, socket_path


def run_json_command(*args: str, env: dict[str, str] | None = None, check: bool = True) -> tuple[int, dict]:
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
    if not unix_rpc_supported():
        print("mcp bridge provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), BridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    agentd_binary = resolve_binary("agentd", args.agentd, args.bin_dir)
    agentd_process: subprocess.Popen | None = None
    if args.output_dir is not None:
        temp_root = args.output_dir
        temp_root.mkdir(parents=True, exist_ok=True)
    else:
        if DEFAULT_WORK_ROOT.exists():
            shutil.rmtree(DEFAULT_WORK_ROOT, ignore_errors=True)
        DEFAULT_WORK_ROOT.mkdir(parents=True, exist_ok=True)
        temp_root = DEFAULT_WORK_ROOT
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
                "remote-control-plane-register",
                "remote-auth-header-v1",
            }.issubset(set(manifest["implemented_methods"])),
            "manifest methods mismatch",
        )
        require(
            manifest["result_protocol_schema_ref"] == "aios/compat-mcp-bridge-result.schema.json",
            "manifest result protocol schema mismatch",
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
            "--display-name",
            "Remote MCP Worker",
            "--attestation-mode",
            "verified",
            "--attestation-issuer",
            "mcp-smoke-attestor",
            "--attestation-subject",
            "tools.echo.remote",
            "--attestation-expires-at",
            "2030-01-01T00:00:00Z",
            "--fleet-id",
            "fleet-mcp",
            "--governance-group",
            "operator-audit",
            "--policy-group",
            "compat-mcp-remote",
            "--registered-by",
            "scripts/test-mcp-bridge-provider-smoke.py",
            "--approval-ref",
            "approval-mcp-1",
            "--heartbeat-ttl-seconds",
            "600",
            env=env,
        )
        require(registered_call["registration"]["provider_ref"] == "tools.echo.remote", "call remote registration mismatch")
        require(((registered_call["registration"].get("attestation") or {}).get("mode") == "verified"), "call remote attestation mismatch")
        require(((registered_call["registration"].get("governance") or {}).get("fleet_id") == "fleet-mcp"), "call remote governance mismatch")

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
            "--display-name",
            "Remote A2A Worker",
            "--attestation-mode",
            "bootstrap",
            "--fleet-id",
            "fleet-mcp",
            "--governance-group",
            "operator-audit",
            env=env,
        )
        require(registered_forward["registration"]["target_hash"] == a2a_target_hash, "forward remote target hash mismatch")

        _, listed = run_json_command("list-remotes", env=env)
        require(listed["registered_remote_count"] == 2, "remote registry count mismatch")
        require(listed.get("remote_status_counts", {}).get("active") == 2, "remote registry active count mismatch")
        listed_by_ref = {entry["provider_ref"]: entry for entry in listed["registered_remotes"]}
        require(set(listed_by_ref) == {"tools.echo.remote", "a2a.forward.remote"}, "listed remote refs mismatch")
        listed_remote = listed_by_ref["tools.echo.remote"]
        require(listed_remote.get("heartbeat_ttl_seconds") == 600, "remote heartbeat ttl mismatch")
        require(listed_remote.get("registration_status") == "active", "remote status mismatch")

        _, registered_health = run_json_command("health", env=env)
        require(registered_health["registered_remote_count"] == 2, "health remote count mismatch")
        require(set(registered_health["remote_auth_modes"]) == {"bearer", "execution-token"}, "health remote auth modes mismatch")
        require(set(registered_health["remote_attestation_modes"]) == {"bootstrap", "verified"}, "health attestation modes mismatch")
        require(registered_health["remote_fleet_ids"] == ["fleet-mcp"], "health fleet ids mismatch")
        require(registered_health["remote_governance_groups"] == ["operator-audit"], "health governance groups mismatch")
        require(registered_health.get("remote_status_counts", {}).get("active") == 2, "health active count mismatch")

        _, heartbeat_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "tools.echo.remote",
            env=env,
        )
        require(heartbeat_remote["registration"]["registration_status"] == "active", "heartbeat should keep remote active")
        require(heartbeat_remote["registration"].get("last_heartbeat_at"), "heartbeat should update last_heartbeat_at")

        control_plane_provider_id = None
        control_plane_mode = "skipped"
        control_plane_skip_reason = None
        if agentd_binary.exists():
            control_plane_env, agentd_socket = build_agentd_env(temp_root)
            agentd_process = launch(agentd_binary, control_plane_env)
            try:
                wait_for_socket(agentd_socket, args.timeout)
                wait_for_health(agentd_socket, args.timeout)
                _, control_plane = run_json_command(
                    "register-control-plane",
                    "--provider-ref",
                    "tools.echo.remote",
                    "--agentd-socket",
                    str(agentd_socket),
                    env=env,
                )
                control_plane_provider_id = control_plane["control_plane_provider_id"]
                require(control_plane["record"]["provider_id"] == control_plane_provider_id, "control-plane provider id mismatch")
                require(control_plane["record"]["descriptor"]["execution_location"] == "attested_remote", "control-plane execution_location mismatch")
                remote_registration = ((control_plane["record"].get("descriptor") or {}).get("remote_registration") or {})
                require(remote_registration.get("provider_ref") == "tools.echo.remote", "control-plane remote provider ref mismatch")
                require(remote_registration.get("control_plane_provider_id") == control_plane_provider_id, "control-plane remote provider id mismatch")
                require(((remote_registration.get("attestation") or {}).get("mode") == "verified"), "control-plane attestation mismatch")
                require(((remote_registration.get("governance") or {}).get("fleet_id") == "fleet-mcp"), "control-plane governance mismatch")
                refreshed_listing = run_json_command("list-remotes", env=env)[1]
                refreshed_remote = {
                    entry["provider_ref"]: entry for entry in refreshed_listing["registered_remotes"]
                }["tools.echo.remote"]
                require(refreshed_remote.get("control_plane_provider_id") == control_plane_provider_id, "registry did not persist control_plane_provider_id")
                resolved = rpc_call(
                    agentd_socket,
                    "agent.provider.resolve_capability",
                    {
                        "capability_id": "compat.mcp.call",
                        "preferred_execution_location": "attested_remote",
                        "require_healthy": True,
                        "include_disabled": False,
                    },
                    timeout=args.timeout,
                )
                require((resolved.get("selected") or {}).get("provider_id") == control_plane_provider_id, "attested_remote resolve did not select promoted provider")
                resolved_remote = (resolved.get("selected") or {}).get("remote_registration") or {}
                require(resolved_remote.get("target_hash") == refreshed_remote.get("target_hash"), "resolved remote target hash mismatch")
                require(((resolved_remote.get("attestation") or {}).get("issuer") == "mcp-smoke-attestor"), "resolved attestation issuer mismatch")
                require(((resolved_remote.get("governance") or {}).get("governance_group") == "operator-audit"), "resolved governance group mismatch")
                control_plane_mode = "validated"
            except Exception as exc:  # noqa: BLE001
                process_output = ""
                if agentd_process is not None and agentd_process.stdout is not None and agentd_process.poll() is not None:
                    process_output = agentd_process.stdout.read().strip()
                unsupported_transport = "unix rpc transport is not supported on this platform" in process_output.lower()
                if unsupported_transport or agentd_process is None or agentd_process.poll() is not None:
                    control_plane_skip_reason = process_output or str(exc)
                    control_plane_mode = "skipped"
                else:
                    raise
        else:
            control_plane_skip_reason = "agentd binary missing"

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
        require(call_payload["provider_ref"] == "tools.echo.remote", "call provider ref mismatch")
        require(call_payload["response"]["result"]["remote_provider"] == "tools.echo.remote", "call remote provider header mismatch")
        require((call_payload.get("result_protocol") or {}).get("status") == "ok", "call result protocol should report ok")
        require(call_payload.get("audit_id"), "call should expose audit_id")
        require(call_payload.get("audit_log") == str(audit_log), "call audit log mismatch")

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
        require(forward_payload["response"]["remote_provider"] == "a2a.forward.remote", "forward remote provider mismatch")

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
        require((trust_payload.get("error") or {}).get("error_code") == "bridge_endpoint_not_allowlisted", "trust rejection error code mismatch")

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
        require((timeout_payload.get("error") or {}).get("error_code") == "bridge_remote_timeout", "timeout error code mismatch")

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
        require((wrong_target_payload.get("error") or {}).get("error_code") == "bridge_execution_token_target_mismatch", "wrong target hash error code mismatch")

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
        require((invalid_payload.get("error") or {}).get("error_code") == "bridge_invalid_arguments_json", "invalid JSON error code mismatch")

        _, stale_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "tools.echo.remote",
            "--heartbeat-at",
            "2020-01-01T00:00:00Z",
            env=env,
        )
        require(stale_remote["registration"]["registration_status"] == "stale", "stale heartbeat should mark registration stale")
        stale_code, stale_payload = run_json_command(
            "call",
            "--provider-ref",
            "tools.echo.remote",
            "--tool",
            "tools.echo",
            "--arguments",
            '{"message":"stale"}',
            env=env,
            check=False,
        )
        require(stale_code == 3, f"stale remote should exit 3, got {stale_code}")
        require((stale_payload.get("error") or {}).get("error_code") == "bridge_remote_provider_stale", "stale remote error code mismatch")
        run_json_command("heartbeat-remote", "--provider-ref", "tools.echo.remote", env=env)

        _, revoked_remote = run_json_command(
            "revoke-remote",
            "--provider-ref",
            "a2a.forward.remote",
            "--reason",
            "rotation-complete",
            env=env,
        )
        require(revoked_remote["registration"]["registration_status"] == "revoked", "revoked remote status mismatch")
        revoked_code, revoked_payload = run_json_command(
            "forward",
            "--provider-ref",
            "a2a.forward.remote",
            "--payload",
            '{"task":"sync"}',
            env={**env, "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(forward_token)},
            check=False,
        )
        require(revoked_code == 13, f"revoked remote should exit 13, got {revoked_code}")
        require((revoked_payload.get("error") or {}).get("error_code") == "bridge_remote_provider_revoked", "revoked remote error code mismatch")

        _, unregistered_remote = run_json_command(
            "unregister-remote",
            "--provider-ref",
            "a2a.forward.remote",
            env=env,
        )
        require(unregistered_remote["unregistered"] is True, "unregister should return true")
        final_listing = run_json_command("list-remotes", env=env)[1]
        require(final_listing["registered_remote_count"] == 1, "final remote count mismatch")

        require(audit_log.exists(), "mcp bridge audit log should be created")
        audit_entries = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        require(len(audit_entries) >= 6, "mcp bridge audit log should contain command entries")
        require(any(entry["decision"] == "allowed" for entry in audit_entries), "mcp bridge audit log missing allowed entry")
        require(any(entry["decision"] == "denied" for entry in audit_entries), "mcp bridge audit log missing denied entry")
        require(any((entry.get("result") or {}).get("error_code") == "bridge_remote_timeout" for entry in audit_entries), "mcp bridge audit log missing timeout entry")
        require(any((entry.get("remote_registration") or {}).get("provider_ref") == "tools.echo.remote" for entry in audit_entries), "mcp bridge audit log missing remote registration metadata")
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
                    "registered_remote_count": final_listing["registered_remote_count"],
                    "control_plane_mode": control_plane_mode,
                    "control_plane_provider_id": control_plane_provider_id,
                    "control_plane_skip_reason": control_plane_skip_reason,
                    "blocked_error": trust_payload["error"]["error_code"],
                    "timeout_error": timeout_payload["error"]["error_code"],
                    "wrong_target_error": wrong_target_payload["error"]["error_code"],
                    "stale_error": stale_payload["error"]["error_code"],
                    "revoked_error": revoked_payload["error"]["error_code"],
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
        terminate(agentd_process)
        preserve_state = failed or args.keep_state or args.output_dir is not None
        if preserve_state:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
