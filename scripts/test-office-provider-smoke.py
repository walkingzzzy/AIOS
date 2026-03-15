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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "aios" / "compat" / "office" / "runtime" / "office_provider.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat office provider smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp audit/fixture directory on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for audit logs and fixtures")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing the agentd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for agentd control-plane smoke")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(ROOT) / name


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
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    import time

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
            "AIOS_PROVIDER_REMOTE_ALLOWED_FLEETS": "fleet-office",
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


class OfficeHandler(BaseHTTPRequestHandler):
    server_version = "AIOSOfficeSmoke/0.2"

    def _send_json(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.headers.get("Authorization") != "Bearer office-secret":
            self._send_json({"status": "error", "error": "missing bearer auth"})
            return
        if self.headers.get("X-AIOS-Remote-Provider") != "office.remote.worker":
            self._send_json({"status": "error", "error": "provider ref missing"})
            return
        request = payload.get("request") or {}
        document = request.get("document") or {}
        if payload.get("operation") == "compat.document.open":
            self._send_json(
                {
                    "status": "ok",
                    "title": document.get("title") or "Remote Office Worker",
                    "mime_type": document.get("mime_type") or "text/markdown",
                    "preview": "Remote office preview ready",
                }
            )
            return
        if payload.get("operation") == "compat.office.export_pdf":
            pdf_bytes = b"%PDF-1.4\n%remote office smoke\n%%EOF\n"
            self._send_json(
                {
                    "status": "ok",
                    "mime_type": "application/pdf",
                    "page_count": 1,
                    "exported_at": "2026-03-14T00:00:00Z",
                    "pdf_base64": __import__("base64").b64encode(pdf_bytes).decode("ascii"),
                }
            )
            return
        self._send_json({"status": "error", "error": "unsupported operation"})

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), OfficeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    temp_root = args.output_dir or Path(tempfile.mkdtemp(prefix="aios-office-provider-"))
    temp_root.mkdir(parents=True, exist_ok=True)
    agentd_binary = resolve_binary("agentd", args.agentd, args.bin_dir)
    agentd_process: subprocess.Popen | None = None
    failed = False
    try:
        audit_log = temp_root / "office-audit.jsonl"
        remote_registry = temp_root / "office-remote-registry.json"
        env = {
            "AIOS_COMPAT_OFFICE_AUDIT_LOG": str(audit_log),
            "AIOS_OFFICE_TRUST_MODE": "allowlist",
            "AIOS_OFFICE_ALLOWLIST": "127.0.0.1,localhost",
            "AIOS_OFFICE_REMOTE_REGISTRY": str(remote_registry),
            "OFFICE_REMOTE_SECRET": "office-secret",
        }
        document_path = temp_root / "sample.md"
        pdf_path = temp_root / "sample.pdf"
        remote_pdf_path = temp_root / "sample-remote.pdf"
        unsupported_path = temp_root / "sample.docx"
        missing_path = temp_root / "missing.md"
        document_path.write_text(
            "# AIOS Office Smoke\n\nThis is a markdown document for PDF export.\n\n- item one\n- item two\n",
            encoding="utf-8",
        )
        unsupported_path.write_text("not really a docx", encoding="utf-8")

        _, manifest = run_json_command("manifest", env=env)
        require(manifest["provider_id"] == "compat.office.document.local", "manifest provider mismatch")
        require(manifest["status"] == "baseline", "manifest status should be baseline")
        require(manifest["worker_contract"] == "compat-office-document-v1", "manifest worker contract mismatch")
        require(
            {
                "open-local-document",
                "export-text-pdf",
                "permission-manifest",
                "office-result-protocol-v1",
                "audit-jsonl",
                "remote-register",
                "remote-list",
                "remote-control-plane-register",
                "remote-office-bridge",
            }.issubset(
                set(manifest["implemented_methods"])
            ),
            "manifest methods mismatch",
        )
        require(
            manifest["result_protocol_schema_ref"] == "aios/compat-office-result.schema.json",
            "manifest result protocol schema mismatch",
        )
        require(
            (manifest.get("compat_permission_manifest") or {}).get("provider_id")
            == "compat.office.document.local",
            "manifest compat permission manifest mismatch",
        )

        _, health = run_json_command("health", env=env)
        require(health["status"] == "available", "health status should be available")
        require(health["engine"] == "text-document+remote-office-bridge", "unexpected office engine")
        require(health["worker_contract"] == "compat-office-document-v1", "health worker contract mismatch")
        require(
            health["result_protocol_schema_ref"] == "aios/compat-office-result.schema.json",
            "health result protocol schema mismatch",
        )
        require(health["audit_log_configured"] is True, "health should report audit log configured")
        require(health["audit_log_path"] == str(audit_log), "health audit log path mismatch")
        require((health.get("trust_policy") or {}).get("mode") == "allowlist", "office trust mode mismatch")
        require(health["registered_remote_count"] == 0, "office remote registry should start empty")
        _, permissions = run_json_command("permissions", env=env)
        require(
            permissions["required_permissions"] == ["document.user-selected"],
            "office permissions mismatch",
        )

        remote_endpoint = f"http://127.0.0.1:{server.server_address[1]}/office"
        _, remote_registered = run_json_command(
            "register-remote",
            "--provider-ref",
            "office.remote.worker",
            "--endpoint",
            remote_endpoint,
            "--capability",
            "compat.document.open",
            "--capability",
            "compat.office.export_pdf",
            "--auth-mode",
            "bearer",
            "--auth-secret-env",
            "OFFICE_REMOTE_SECRET",
            "--attestation-mode",
            "verified",
            "--attestation-issuer",
            "office-smoke-attestor",
            "--attestation-subject",
            "office.remote.worker",
            "--attestation-expires-at",
            "2030-01-01T00:00:00Z",
            "--fleet-id",
            "fleet-office",
            "--governance-group",
            "operator-audit",
            "--policy-group",
            "compat-office-remote",
            "--registered-by",
            "scripts/test-office-provider-smoke.py",
            "--approval-ref",
            "approval-remote-office-1",
            "--heartbeat-ttl-seconds",
            "600",
            env=env,
        )
        require(remote_registered["registration"]["target_hash"], "office remote target hash missing")
        require(
            ((remote_registered["registration"].get("attestation") or {}).get("mode") == "verified"),
            "office remote registration should include verified attestation",
        )
        require(
            ((remote_registered["registration"].get("governance") or {}).get("fleet_id") == "fleet-office"),
            "office remote registration should include fleet governance",
        )
        _, remote_listing = run_json_command("list-remotes", env=env)
        require(remote_listing["registered_remote_count"] == 1, "office remote registry count mismatch")
        listed_remote = remote_listing["registered_remotes"][0]
        require(
            ((listed_remote.get("attestation") or {}).get("issuer") == "office-smoke-attestor"),
            "office remote registry attestation issuer mismatch",
        )
        require(
            ((listed_remote.get("governance") or {}).get("governance_group") == "operator-audit"),
            "office remote registry governance group mismatch",
        )
        require(
            listed_remote.get("registration_status") == "active",
            "office remote registry status mismatch",
        )
        require(
            listed_remote.get("heartbeat_ttl_seconds") == 600,
            "office remote heartbeat ttl mismatch",
        )
        _, heartbeat_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "office.remote.worker",
            env=env,
        )
        require(
            heartbeat_remote["registration"]["registration_status"] == "active",
            "office remote heartbeat should keep registration active",
        )
        require(
            heartbeat_remote["registration"].get("last_heartbeat_at"),
            "office remote heartbeat should update last_heartbeat_at",
        )

        control_plane_provider_id = None
        control_plane_mode = "skipped"
        if agentd_binary.exists():
            control_plane_env, agentd_socket = build_agentd_env(temp_root)
            agentd_process = launch(agentd_binary, control_plane_env)
            wait_for_socket(agentd_socket, args.timeout)
            wait_for_health(agentd_socket, args.timeout)
            _, control_plane = run_json_command(
                "register-control-plane",
                "--provider-ref",
                "office.remote.worker",
                "--agentd-socket",
                str(agentd_socket),
                env=env,
            )
            control_plane_provider_id = control_plane["control_plane_provider_id"]
            require(
                control_plane["record"]["provider_id"] == control_plane_provider_id,
                "office control-plane provider id mismatch",
            )
            require(
                control_plane["record"]["descriptor"]["execution_location"] == "attested_remote",
                "office control-plane execution_location mismatch",
            )
            remote_registration = (
                (control_plane["record"].get("descriptor") or {}).get("remote_registration") or {}
            )
            require(
                remote_registration.get("provider_ref") == "office.remote.worker",
                "office control-plane remote provider ref mismatch",
            )
            require(
                remote_registration.get("control_plane_provider_id") == control_plane_provider_id,
                "office control-plane remote registration id mismatch",
            )
            require(
                ((remote_registration.get("attestation") or {}).get("mode") == "verified"),
                "office control-plane remote attestation mismatch",
            )
            require(
                ((remote_registration.get("governance") or {}).get("fleet_id") == "fleet-office"),
                "office control-plane remote governance mismatch",
            )
            refreshed_remote_listing = run_json_command("list-remotes", env=env)[1]
            refreshed_remote = refreshed_remote_listing["registered_remotes"][0]
            require(
                refreshed_remote.get("control_plane_provider_id") == control_plane_provider_id,
                "office remote registry did not persist control_plane_provider_id",
            )
            resolved = rpc_call(
                agentd_socket,
                "provider.resolve_capability",
                {
                    "capability_id": "compat.document.open",
                    "preferred_execution_location": "attested_remote",
                    "require_healthy": True,
                    "include_disabled": False,
                },
                timeout=args.timeout,
            )
            require(
                (resolved.get("selected") or {}).get("provider_id") == control_plane_provider_id,
                "office control-plane provider was not selected for attested_remote resolution",
            )
            resolved_remote = (resolved.get("selected") or {}).get("remote_registration") or {}
            require(
                resolved_remote.get("target_hash") == refreshed_remote.get("target_hash"),
                "office resolved remote target hash mismatch",
            )
            require(
                ((resolved_remote.get("attestation") or {}).get("issuer") == "office-smoke-attestor"),
                "office resolved remote attestation issuer mismatch",
            )
            require(
                ((resolved_remote.get("governance") or {}).get("governance_group") == "operator-audit"),
                "office resolved remote governance group mismatch",
            )
            control_plane_mode = "validated"

        _, open_payload = run_json_command("open", "--path", str(document_path), env=env)
        require(open_payload["status"] == "ok", "open should succeed")
        require(open_payload["title"] == "AIOS Office Smoke", "document title mismatch")
        require("markdown document for PDF export" in open_payload["preview"], "document preview mismatch")
        require(
            (open_payload.get("result_protocol") or {}).get("status") == "ok",
            "open result protocol should report ok",
        )
        require(open_payload.get("audit_id"), "open should expose audit_id")
        require(open_payload.get("audit_log") == str(audit_log), "open audit log mismatch")

        _, export_payload = run_json_command("export-pdf", "--path", str(document_path), "--output-path", str(pdf_path), env=env)
        require(export_payload["status"] == "ok", "export-pdf should succeed")
        require(pdf_path.exists(), "pdf output was not created")
        require(pdf_path.read_bytes().startswith(b"%PDF-1.4"), "pdf header mismatch")
        require(export_payload["page_count"] >= 1, "page count should be at least one")
        require(export_payload["bytes_written"] == pdf_path.stat().st_size, "bytes_written should match output file size")
        require(
            (export_payload.get("result_protocol") or {}).get("status") == "ok",
            "export result protocol should report ok",
        )

        _, remote_open = run_json_command(
            "open",
            "--path",
            str(document_path),
            "--provider-ref",
            "office.remote.worker",
            env=env,
        )
        require(remote_open["preview"] == "Remote office preview ready", "remote office preview mismatch")
        require(
            (remote_open.get("remote_bridge") or {}).get("provider_ref") == "office.remote.worker",
            "remote office provider ref mismatch",
        )

        _, remote_export = run_json_command(
            "export-pdf",
            "--path",
            str(document_path),
            "--output-path",
            str(remote_pdf_path),
            "--provider-ref",
            "office.remote.worker",
            env=env,
        )
        require(remote_pdf_path.exists(), "remote office pdf output missing")
        require(remote_export["page_count"] == 1, "remote office page count mismatch")
        require(remote_export["bytes_written"] == remote_pdf_path.stat().st_size, "remote office bytes mismatch")

        _, stale_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "office.remote.worker",
            "--heartbeat-at",
            "2020-01-01T00:00:00Z",
            env=env,
        )
        require(
            stale_remote["registration"]["registration_status"] == "stale",
            "office stale heartbeat should mark remote stale",
        )
        stale_code, stale_payload = run_json_command(
            "open",
            "--path",
            str(document_path),
            "--provider-ref",
            "office.remote.worker",
            check=False,
            env=env,
        )
        require(stale_code == 3, f"stale office remote should exit 3, got {stale_code}")
        require(
            (stale_payload.get("error") or {}).get("error_code") == "office_remote_provider_stale",
            "stale office remote error code mismatch",
        )
        _, recovered_remote = run_json_command(
            "heartbeat-remote",
            "--provider-ref",
            "office.remote.worker",
            env=env,
        )
        require(
            recovered_remote["registration"]["registration_status"] == "active",
            "office remote heartbeat recovery mismatch",
        )
        _, revoked_remote = run_json_command(
            "revoke-remote",
            "--provider-ref",
            "office.remote.worker",
            "--reason",
            "operator-testing",
            env=env,
        )
        require(
            revoked_remote["registration"]["registration_status"] == "revoked",
            "office remote revoke status mismatch",
        )
        revoked_code, revoked_payload = run_json_command(
            "open",
            "--path",
            str(document_path),
            "--provider-ref",
            "office.remote.worker",
            check=False,
            env=env,
        )
        require(revoked_code == 13, f"revoked office remote should exit 13, got {revoked_code}")
        require(
            (revoked_payload.get("error") or {}).get("error_code") == "office_remote_provider_revoked",
            "revoked office remote error code mismatch",
        )
        _, unregistered_remote = run_json_command(
            "unregister-remote",
            "--provider-ref",
            "office.remote.worker",
            env=env,
        )
        require(unregistered_remote["unregistered"] is True, "office remote unregister mismatch")
        _, final_remote_listing = run_json_command("list-remotes", env=env)
        require(
            final_remote_listing["registered_remote_count"] == 0,
            "office remote registry should be empty after unregister",
        )

        missing_code, missing_payload = run_json_command("open", "--path", str(missing_path), check=False, env=env)
        require(missing_code == 3, f"missing file should exit 3, got {missing_code}")
        require(
            (missing_payload.get("error") or {}).get("error_code") == "office_document_missing",
            "missing file error code mismatch",
        )

        unsupported_code, unsupported_payload = run_json_command("open", "--path", str(unsupported_path), check=False, env=env)
        require(unsupported_code == 2, f"unsupported type should exit 2, got {unsupported_code}")
        require(
            (unsupported_payload.get("error") or {}).get("error_code") == "office_document_type_unsupported",
            "unsupported type error code mismatch",
        )
        require(audit_log.exists(), "office audit log should be created")
        audit_entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line.strip()]
        require(len(audit_entries) >= 4, "office audit log should contain command entries")
        require(any(entry["decision"] == "allowed" for entry in audit_entries), "office audit log missing allowed entry")
        require(any((entry.get("result") or {}).get("error_code") == "office_document_missing" for entry in audit_entries), "office audit log missing missing-file entry")
        require(any((entry.get("result") or {}).get("error_code") == "office_document_type_unsupported" for entry in audit_entries), "office audit log missing unsupported-type entry")
        require(all(entry.get("schema_version") == "2026-03-13" for entry in audit_entries), "office audit log schema_version mismatch")
        require(all(entry.get("artifact_path") == str(audit_log) for entry in audit_entries), "office audit log artifact_path mismatch")

        print(
            json.dumps(
                {
                    "provider_id": manifest["provider_id"],
                    "worker_contract": manifest["worker_contract"],
                    "title": open_payload["title"],
                    "remote_preview": remote_open["preview"],
                    "control_plane_mode": control_plane_mode,
                    "control_plane_provider_id": control_plane_provider_id,
                    "pdf_bytes": export_payload["bytes_written"],
                    "page_count": export_payload["page_count"],
                    "missing_error": missing_payload["error"]["error_code"],
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
