#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "aios" / "compat" / "browser" / "runtime" / "browser_provider.py"
DEFAULT_WORK_ROOT = ROOT / "out" / "validation" / "browser-provider-smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat browser provider smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp audit/fixture directory on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for audit logs and fixtures")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing the agentd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for agentd control-plane smoke")
    return parser.parse_args()


class BrowserHandler(BaseHTTPRequestHandler):
    server_version = "AIOSBrowserSmoke/0.2"

    def _send_json(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/slow":
            time.sleep(0.5)
            body = "<html><title>Slow</title><body>Slow response</body></html>"
        else:
            body = "<html><title>Remote</title><body>Remote response</body></html>"

        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.headers.get("Authorization") != "Bearer browser-secret":
            self._send_json({"status": "error", "error": "missing bearer auth"})
            return
        if self.headers.get("X-AIOS-Remote-Provider") != "browser.remote.worker":
            self._send_json({"status": "error", "error": "provider ref missing"})
            return
        request = payload.get("request") or {}
        operation = payload.get("operation")
        if operation == "compat.browser.navigate":
            self._send_json(
                {
                    "status": "ok",
                    "title": "Remote Browser Worker",
                    "text_preview": "Remote browser bridge executed",
                    "text_length": 30,
                    "link_count": 1,
                    "links": [{"href": "https://remote.example/docs", "text": "Remote Docs"}],
                    "fetch": {
                        "requested_url": request.get("url"),
                        "resolved_url": request.get("url"),
                        "final_url": request.get("url"),
                        "status_code": 200,
                        "content_type": "text/html",
                        "charset": "utf-8",
                        "truncated": False,
                        "fetched_at": "2026-03-14T00:00:00Z",
                    },
                }
            )
            return
        if operation == "compat.browser.extract":
            self._send_json(
                {
                    "status": "ok",
                    "text": "Remote extraction text",
                    "text_preview": "Remote extraction text",
                    "text_length": 22,
                    "matched_count": 1,
                    "fetch": {
                        "requested_url": request.get("url"),
                        "resolved_url": request.get("url"),
                        "final_url": request.get("url"),
                        "status_code": 200,
                        "content_type": "text/html",
                        "charset": "utf-8",
                        "truncated": False,
                        "fetched_at": "2026-03-14T00:00:00Z",
                    },
                }
            )
            return
        self._send_json({"status": "error", "error": "unsupported operation"})

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
            "AIOS_PROVIDER_REMOTE_ALLOWED_FLEETS": "fleet-browser",
            "AIOS_PROVIDER_REMOTE_ALLOWED_GOVERNANCE_GROUPS": "operator-audit",
        }
    )
    return env, socket_path


def run_json_command(*args: str, check: bool = True, env: dict[str, str] | None = None) -> tuple[int, dict]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        [sys.executable, str(RUNTIME), *args],
        cwd=ROOT,
        text=True,
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


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("browser provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), BrowserHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if args.output_dir is not None:
        temp_root = args.output_dir
        temp_root.mkdir(parents=True, exist_ok=True)
    else:
        if DEFAULT_WORK_ROOT.exists():
            shutil.rmtree(DEFAULT_WORK_ROOT, ignore_errors=True)
        DEFAULT_WORK_ROOT.mkdir(parents=True, exist_ok=True)
        temp_root = DEFAULT_WORK_ROOT
    agentd_binary = resolve_binary("agentd", args.agentd, args.bin_dir)
    agentd_process: subprocess.Popen | None = None
    failed = False

    try:
        audit_log = temp_root / "browser-audit.jsonl"
        remote_registry = temp_root / "browser-remote-registry.json"
        env = {
            "AIOS_COMPAT_BROWSER_AUDIT_LOG": str(audit_log),
            "AIOS_BROWSER_TRUST_MODE": "allowlist",
            "AIOS_BROWSER_ALLOWLIST": "127.0.0.1,localhost",
            "AIOS_BROWSER_REMOTE_REGISTRY": str(remote_registry),
            "BROWSER_REMOTE_SECRET": "browser-secret",
        }
        fixture_path = temp_root / "fixture.html"
        fixture_path.write_text(
            """
            <html>
              <head>
                <title>AIOS Browser Smoke</title>
              </head>
              <body>
                <h1>Browser Provider Ready</h1>
                <div id="content">Browser provider smoke body.</div>
                <p class="note">Local HTML extraction works.</p>
                <a href="https://example.com/docs">Docs</a>
              </body>
            </html>
            """.strip(),
            encoding="utf-8",
        )
        fixture_url = fixture_path.resolve().as_uri()
        slow_url = f"http://127.0.0.1:{server.server_address[1]}/slow"

        _, manifest = run_json_command("manifest", env=env)
        require(manifest["provider_id"] == "compat.browser.automation.local", "manifest provider mismatch")
        require(manifest["status"] == "baseline", "manifest status should be baseline")
        require(manifest["worker_contract"] == "compat-browser-fetch-v1", "manifest worker contract mismatch")
        require(
            {
                "navigate-fetch",
                "extract-selector-text",
                "permission-manifest",
                "browser-result-protocol-v1",
                "audit-jsonl",
                "remote-register",
                "remote-list",
                "remote-control-plane-register",
                "remote-browser-bridge",
            }.issubset(
                set(manifest["implemented_methods"])
            ),
            "manifest methods mismatch",
        )
        require(
            manifest["result_protocol_schema_ref"] == "aios/compat-browser-result.schema.json",
            "manifest result protocol schema mismatch",
        )
        require(
            (manifest.get("compat_permission_manifest") or {}).get("provider_id")
            == "compat.browser.automation.local",
            "manifest compat permission manifest mismatch",
        )

        _, health = run_json_command("health", env=env)
        require(health["status"] == "available", "health status should be available")
        require(health["engine"] == "html-fetch+remote-browser-bridge", "unexpected browser engine")
        require(health["worker_contract"] == "compat-browser-fetch-v1", "health worker contract mismatch")
        require(
            health["result_protocol_schema_ref"] == "aios/compat-browser-result.schema.json",
            "health result protocol schema mismatch",
        )
        require(health["audit_log_configured"] is True, "health should report audit log configured")
        require(health["audit_log_path"] == str(audit_log), "health audit log path mismatch")
        require((health.get("trust_policy") or {}).get("mode") == "allowlist", "browser trust mode mismatch")
        require(health["registered_remote_count"] == 0, "browser remote registry should start empty")
        _, permissions = run_json_command("permissions", env=env)
        require(
            permissions["required_permissions"] == ["browser.compat"],
            "browser permissions mismatch",
        )

        remote_endpoint = f"http://127.0.0.1:{server.server_address[1]}/bridge"
        _, registered_remote = run_json_command(
            "register-remote",
            "--provider-ref",
            "browser.remote.worker",
            "--endpoint",
            remote_endpoint,
            "--capability",
            "compat.browser.navigate",
            "--capability",
            "compat.browser.extract",
            "--auth-mode",
            "bearer",
            "--auth-secret-env",
            "BROWSER_REMOTE_SECRET",
            "--attestation-mode",
            "verified",
            "--attestation-issuer",
            "browser-smoke-attestor",
            "--attestation-subject",
            "browser.remote.worker",
            "--attestation-expires-at",
            "2030-01-01T00:00:00Z",
            "--fleet-id",
            "fleet-browser",
            "--governance-group",
            "operator-audit",
            "--policy-group",
            "compat-browser-remote",
            "--registered-by",
            "scripts/test-browser-provider-smoke.py",
            "--approval-ref",
            "approval-remote-browser-1",
            "--heartbeat-ttl-seconds",
            "600",
            env=env,
        )
        require(
            registered_remote["registration"]["target_hash"],
            "browser remote registration should include target_hash",
        )
        require(
            ((registered_remote["registration"].get("attestation") or {}).get("mode") == "verified"),
            "browser remote registration should include verified attestation",
        )
        require(
            ((registered_remote["registration"].get("governance") or {}).get("fleet_id") == "fleet-browser"),
            "browser remote registration should include fleet governance",
        )
        _, remote_listing = run_json_command("list-remotes", env=env)
        require(remote_listing["registered_remote_count"] == 1, "browser remote registry count mismatch")
        listed_remote = remote_listing["registered_remotes"][0]
        require(
            ((listed_remote.get("attestation") or {}).get("issuer") == "browser-smoke-attestor"),
            "browser remote registry attestation issuer mismatch",
        )
        require(
            ((listed_remote.get("governance") or {}).get("governance_group") == "operator-audit"),
            "browser remote registry governance group mismatch",
        )
        require(listed_remote.get("registration_status") == "active", "browser remote registry status mismatch")
        require(listed_remote.get("heartbeat_ttl_seconds") == 600, "browser remote heartbeat ttl mismatch")
        _, heartbeat_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "browser.remote.worker",
            env=env,
        )
        require(
            heartbeat_remote["registration"]["registration_status"] == "active",
            "browser remote heartbeat should keep registration active",
        )
        require(
            heartbeat_remote["registration"].get("last_heartbeat_at"),
            "browser remote heartbeat should update last_heartbeat_at",
        )

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
                    "browser.remote.worker",
                    "--agentd-socket",
                    str(agentd_socket),
                    env=env,
                )
                control_plane_provider_id = control_plane["control_plane_provider_id"]
                require(
                    control_plane["record"]["provider_id"] == control_plane_provider_id,
                    "browser control-plane provider id mismatch",
                )
                require(
                    control_plane["record"]["descriptor"]["execution_location"] == "attested_remote",
                    "browser control-plane execution_location mismatch",
                )
                remote_registration = (
                    (control_plane["record"].get("descriptor") or {}).get("remote_registration") or {}
                )
                require(
                    remote_registration.get("provider_ref") == "browser.remote.worker",
                    "browser control-plane remote provider ref mismatch",
                )
                require(
                    remote_registration.get("control_plane_provider_id") == control_plane_provider_id,
                    "browser control-plane remote registration id mismatch",
                )
                require(
                    ((remote_registration.get("attestation") or {}).get("mode") == "verified"),
                    "browser control-plane remote attestation mismatch",
                )
                require(
                    ((remote_registration.get("governance") or {}).get("fleet_id") == "fleet-browser"),
                    "browser control-plane remote governance mismatch",
                )
                refreshed_remote_listing = run_json_command("list-remotes", env=env)[1]
                refreshed_remote = refreshed_remote_listing["registered_remotes"][0]
                require(
                    refreshed_remote.get("control_plane_provider_id") == control_plane_provider_id,
                    "browser remote registry did not persist control_plane_provider_id",
                )
                resolved = rpc_call(
                    agentd_socket,
                    "agent.provider.resolve_capability",
                    {
                        "capability_id": "compat.browser.navigate",
                        "preferred_execution_location": "attested_remote",
                        "require_healthy": True,
                        "include_disabled": False,
                    },
                    timeout=args.timeout,
                )
                require(
                    (resolved.get("selected") or {}).get("provider_id") == control_plane_provider_id,
                    "browser control-plane provider was not selected for attested_remote resolution",
                )
                resolved_remote = (resolved.get("selected") or {}).get("remote_registration") or {}
                require(
                    resolved_remote.get("target_hash") == refreshed_remote.get("target_hash"),
                    "browser resolved remote target hash mismatch",
                )
                require(
                    ((resolved_remote.get("attestation") or {}).get("issuer") == "browser-smoke-attestor"),
                    "browser resolved remote attestation issuer mismatch",
                )
                require(
                    ((resolved_remote.get("governance") or {}).get("governance_group") == "operator-audit"),
                    "browser resolved remote governance group mismatch",
                )
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

        _, navigate = run_json_command("navigate", "--url", fixture_url, "--max-links", "4", "--max-text-chars", "200", env=env)
        require(navigate["status"] == "ok", "navigate should return ok")
        require(navigate["title"] == "AIOS Browser Smoke", "navigate title mismatch")
        require("Browser provider smoke body." in navigate["text_preview"], "navigate preview missing body text")
        require(navigate["link_count"] == 1, "navigate should discover one link")
        require(navigate["links"][0]["href"] == "https://example.com/docs", "navigate link href mismatch")
        require(
            (navigate.get("result_protocol") or {}).get("status") == "ok",
            "navigate result protocol should report ok",
        )
        require(navigate.get("audit_id"), "navigate should expose audit_id")
        require(navigate.get("audit_log") == str(audit_log), "navigate audit log path mismatch")

        _, extract_content = run_json_command("extract", "--url", fixture_url, "--selector", "#content", env=env)
        require(extract_content["status"] == "ok", "#content extraction should succeed")
        require(extract_content["matched_count"] == 1, "#content should match exactly once")
        require(extract_content["text"] == "Browser provider smoke body.", "#content extraction mismatch")
        require(
            (extract_content.get("result_protocol") or {}).get("status") == "ok",
            "extract result protocol should report ok",
        )

        _, extract_heading = run_json_command("extract", "--url", fixture_url, "--selector", "h1", env=env)
        require(extract_heading["text"] == "Browser Provider Ready", "h1 extraction mismatch")

        _, extract_note = run_json_command("extract", "--url", fixture_url, "--selector", ".note", env=env)
        require(extract_note["text"] == "Local HTML extraction works.", ".note extraction mismatch")

        _, remote_navigate = run_json_command(
            "navigate",
            "--url",
            "https://remote.example/home",
            "--provider-ref",
            "browser.remote.worker",
            env=env,
        )
        require(remote_navigate["title"] == "Remote Browser Worker", "remote browser title mismatch")
        require(
            (remote_navigate.get("remote_bridge") or {}).get("provider_ref") == "browser.remote.worker",
            "remote browser provider ref mismatch",
        )

        _, remote_extract = run_json_command(
            "extract",
            "--url",
            "https://remote.example/home",
            "--selector",
            "#main",
            "--provider-ref",
            "browser.remote.worker",
            env=env,
        )
        require(remote_extract["text"] == "Remote extraction text", "remote browser extract mismatch")
        _, stale_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "browser.remote.worker",
            "--heartbeat-at",
            "2020-01-01T00:00:00Z",
            env=env,
        )
        require(
            stale_remote["registration"]["registration_status"] == "stale",
            "browser stale heartbeat should mark remote stale",
        )
        stale_code, stale_payload = run_json_command(
            "navigate",
            "--url",
            "https://remote.example/home",
            "--provider-ref",
            "browser.remote.worker",
            check=False,
            env=env,
        )
        require(stale_code == 3, f"stale browser remote should exit 3, got {stale_code}")
        require(
            (stale_payload.get("error") or {}).get("error_code") == "browser_remote_provider_stale",
            "stale browser remote error code mismatch",
        )
        _, recovered_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "browser.remote.worker",
            env=env,
        )
        require(
            recovered_remote["registration"]["registration_status"] == "active",
            "browser remote heartbeat recovery mismatch",
        )
        _, revoked_remote = run_json_command(
            "revoke-remote",
            "--provider-ref",
            "browser.remote.worker",
            "--reason",
            "operator-testing",
            env=env,
        )
        require(
            revoked_remote["registration"]["registration_status"] == "revoked",
            "browser remote revoke status mismatch",
        )
        revoked_code, revoked_payload = run_json_command(
            "navigate",
            "--url",
            "https://remote.example/home",
            "--provider-ref",
            "browser.remote.worker",
            check=False,
            env=env,
        )
        require(revoked_code == 13, f"revoked browser remote should exit 13, got {revoked_code}")
        require(
            (revoked_payload.get("error") or {}).get("error_code") == "browser_remote_provider_revoked",
            "revoked browser remote error code mismatch",
        )
        _, unregistered_remote = run_json_command(
            "unregister-remote",
            "--provider-ref",
            "browser.remote.worker",
            env=env,
        )
        require(unregistered_remote["unregistered"] is True, "browser remote unregister mismatch")
        _, final_remote_listing = run_json_command("list-remotes", env=env)
        require(final_remote_listing["registered_remote_count"] == 0, "browser remote registry should be empty after unregister")

        _, extract_missing = run_json_command("extract", "--url", fixture_url, "--selector", ".missing", env=env)
        require(extract_missing["status"] == "not-found", "missing selector should report not-found")
        require(extract_missing["matched_count"] == 0, "missing selector should have zero matches")
        require(
            (extract_missing.get("result_protocol") or {}).get("status") == "not-found",
            "missing selector result protocol should report not-found",
        )

        invalid_code, invalid_scheme = run_json_command("navigate", "--url", "ftp://example.com", check=False, env=env)
        require(invalid_code == 2, f"unsupported scheme should exit 2, got {invalid_code}")
        require(
            (invalid_scheme.get("error") or {}).get("error_code") == "browser_unsupported_url_scheme",
            "unsupported scheme error code mismatch",
        )

        timeout_code, timeout_payload = run_json_command(
            "navigate",
            "--url",
            slow_url,
            "--timeout-seconds",
            "0.1",
            check=False,
            env=env,
        )
        require(timeout_code == 124, f"browser timeout should exit 124, got {timeout_code}")
        require(
            (timeout_payload.get("error") or {}).get("error_code") == "browser_fetch_timeout",
            "browser timeout error code mismatch",
        )
        require(audit_log.exists(), "browser audit log should be created")
        audit_entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line.strip()]
        require(len(audit_entries) >= 6, "browser audit log should contain command entries")
        require(any(entry["decision"] == "allowed" for entry in audit_entries), "browser audit log missing allowed entry")
        require(any(entry.get("status") == "not-found" for entry in audit_entries), "browser audit log missing not-found status entry")
        require(any((entry.get("result") or {}).get("error_code") == "browser_fetch_timeout" for entry in audit_entries), "browser audit log missing timeout entry")
        require(all(entry.get("schema_version") == "2026-03-13" for entry in audit_entries), "browser audit log schema_version mismatch")
        require(all(entry.get("artifact_path") == str(audit_log) for entry in audit_entries), "browser audit log artifact_path mismatch")

        print(
            json.dumps(
                {
                    "provider_id": manifest["provider_id"],
                    "worker_contract": manifest["worker_contract"],
                    "title": navigate["title"],
                    "content_selector_text": extract_content["text"],
                    "remote_title": remote_navigate["title"],
                    "control_plane_mode": control_plane_mode,
                    "control_plane_provider_id": control_plane_provider_id,
                    "control_plane_skip_reason": control_plane_skip_reason,
                    "missing_selector_status": extract_missing["status"],
                    "timeout_error": timeout_payload["error"]["error_code"],
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
        terminate(agentd_process)
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
