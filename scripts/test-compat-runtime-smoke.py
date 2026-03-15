#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir


COMPAT_PROVIDERS = {
    "compat.audit.query.local": {
        "descriptor": "aios/compat/audit-query/providers/audit.query.local.json",
        "runtime": "aios/compat/audit-query/runtime/compat_audit_query_provider.py",
        "manifest_args": ["manifest"],
        "health_args": ["health"],
        "permissions_args": ["permissions"],
        "audit_log_env_var": "AIOS_COMPAT_AUDIT_QUERY_AUDIT_LOG",
        "implemented_methods": [
            "audit-entry-query",
            "saved-query-store",
            "saved-query-list",
            "interactive-query-script",
            "query-history-jsonl",
            "audit-query-result-protocol-v1",
        ],
        "worker_contract": "compat-audit-query-v1",
        "result_protocol_schema_ref": "aios/compat-audit-query-result.schema.json",
        "capabilities": [
            "compat.audit.query",
            "compat.audit.saved_query.run",
        ],
        "required_permissions": ["audit.read"],
        "expected_runtime_status": "available",
    },
    "compat.browser.automation.local": {
        "descriptor": "aios/compat/browser/providers/browser.automation.local.json",
        "runtime": "aios/compat/browser/runtime/browser_provider.py",
        "manifest_args": ["manifest"],
        "health_args": ["health"],
        "permissions_args": ["permissions"],
        "audit_log_env_var": "AIOS_COMPAT_BROWSER_AUDIT_LOG",
        "implemented_methods": [
            "navigate-fetch",
            "extract-selector-text",
            "permission-manifest",
            "browser-result-protocol-v1",
            "audit-jsonl",
        ],
        "worker_contract": "compat-browser-fetch-v1",
        "result_protocol_schema_ref": "aios/compat-browser-result.schema.json",
        "capabilities": [
            "compat.browser.navigate",
            "compat.browser.extract",
        ],
        "required_permissions": ["browser.compat"],
        "expected_runtime_status": "available",
    },
    "compat.office.document.local": {
        "descriptor": "aios/compat/office/providers/office.document.local.json",
        "runtime": "aios/compat/office/runtime/office_provider.py",
        "manifest_args": ["manifest"],
        "health_args": ["health"],
        "permissions_args": ["permissions"],
        "audit_log_env_var": "AIOS_COMPAT_OFFICE_AUDIT_LOG",
        "implemented_methods": [
            "open-local-document",
            "export-text-pdf",
            "permission-manifest",
            "office-result-protocol-v1",
            "audit-jsonl",
        ],
        "worker_contract": "compat-office-document-v1",
        "result_protocol_schema_ref": "aios/compat-office-result.schema.json",
        "capabilities": [
            "compat.document.open",
            "compat.office.export_pdf",
        ],
        "required_permissions": ["document.user-selected"],
        "expected_runtime_status": "available",
    },
    "compat.mcp.bridge.local": {
        "descriptor": "aios/compat/mcp-bridge/providers/mcp.bridge.local.json",
        "runtime": "aios/compat/mcp-bridge/runtime/mcp_bridge_provider.py",
        "manifest_args": ["manifest"],
        "health_args": ["health"],
        "permissions_args": ["permissions"],
        "env": {
            "AIOS_MCP_BRIDGE_TRUST_MODE": "allowlist",
            "AIOS_MCP_BRIDGE_ALLOWLIST": "127.0.0.1,localhost",
        },
        "audit_log_env_var": "AIOS_COMPAT_MCP_BRIDGE_AUDIT_LOG",
        "implemented_methods": [
            "jsonrpc-http-call",
            "json-http-forward",
            "permission-manifest",
            "bridge-result-protocol-v1",
            "audit-jsonl",
        ],
        "capabilities": [
            "compat.mcp.call",
            "compat.a2a.forward",
        ],
        "required_permissions": ["bridge.remote"],
        "worker_contract": "compat-mcp-bridge-v1",
        "result_protocol_schema_ref": "aios/compat-mcp-bridge-result.schema.json",
        "expected_runtime_status": "available",
    },
    "compat.code.sandbox.local": {
        "descriptor": "aios/compat/code-sandbox/providers/code.sandbox.local.json",
        "runtime": "aios/compat/code-sandbox/runtime/aios_sandbox_executor.py",
        "manifest_args": ["manifest"],
        "health_args": ["health"],
        "permissions_args": ["permissions"],
        "audit_log_env_var": "AIOS_COMPAT_CODE_SANDBOX_AUDIT_LOG",
        "implemented_methods": [
            "execute-python-script",
            "export-output-artifacts",
            "permission-manifest",
            "audit-jsonl",
            "compat-sandbox-executor-v1",
        ],
        "worker_contract": "compat-sandbox-executor-v1",
        "result_protocol_schema_ref": "aios/compat-sandbox-result.schema.json",
        "capabilities": [
            "compat.code.execute",
        ],
        "required_permissions": ["sandbox.local"],
        "expected_runtime_status": "available",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS compat runtime integration smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing the agentd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(repo_root()) / name


def ensure_binaries(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing binaries for compat runtime smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print("Build them first, for example: cargo build -p aios-agentd")
        raise SystemExit(2)


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


def issue_execution_token(
    socket_path: Path,
    capability_id: str,
    *,
    session_id: str,
    task_id: str,
    timeout: float,
) -> dict:
    approval_ref = None
    if capability_id in {"compat.a2a.forward", "compat.code.execute"}:
        evaluation = rpc_call(
            socket_path,
            "policy.evaluate",
            {
                "user_id": "compat-runtime-smoke",
                "session_id": session_id,
                "task_id": task_id,
                "capability_id": capability_id,
                "execution_location": "sandbox",
                "intent": f"compat runtime smoke for {capability_id}",
            },
            timeout=timeout,
        )
        approval_ref = evaluation.get("approval_ref")
        require(approval_ref, f"policy.evaluate did not emit approval_ref for {capability_id}")
        rpc_call(
            socket_path,
            "approval.resolve",
            {
                "approval_ref": approval_ref,
                "status": "approved",
                "resolver": "compat-runtime-smoke",
                "reason": "smoke approved",
            },
            timeout=timeout,
        )

    token = rpc_call(
        socket_path,
        "policy.token.issue",
        {
            "user_id": "compat-runtime-smoke",
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "approval_ref": approval_ref,
            "constraints": {},
            "execution_location": "sandbox",
        },
        timeout=timeout,
    )
    verification = rpc_call(
        socket_path,
        "policy.token.verify",
        {
            "token": token,
            "consume": False,
        },
        timeout=timeout,
    )
    require(verification.get("valid") is True, f"issued token did not verify for {capability_id}")
    return token


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def make_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    provider_dirs = [
        repo / "aios" / "sdk" / "providers",
        repo / "aios" / "runtime" / "providers",
        repo / "aios" / "shell" / "providers",
        repo / "aios" / "compat" / "audit-query" / "providers",
        repo / "aios" / "compat" / "browser" / "providers",
        repo / "aios" / "compat" / "office" / "providers",
        repo / "aios" / "compat" / "mcp-bridge" / "providers",
        repo / "aios" / "compat" / "code-sandbox" / "providers",
    ]

    env = os.environ.copy()
    env.update(
        {
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "agentd"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "agentd"),
            "AIOS_AGENTD_SOCKET_PATH": str(runtime_root / "agentd" / "agentd.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "runtimed" / "runtimed.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "registry"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": os.pathsep.join(str(path) for path in provider_dirs),
        }
    )
    return env


def make_policyd_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    return {
        "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "policyd"),
        "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
        "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "policyd" / "policyd.sock"),
        "AIOS_POLICYD_POLICY_PATH": str(repo / "aios" / "policy" / "profiles" / "default-policy.yaml"),
        "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(
            repo / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"
        ),
        "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
        "AIOS_POLICYD_AUDIT_INDEX_PATH": str(state_root / "policyd" / "audit-index.json"),
        "AIOS_POLICYD_AUDIT_ARCHIVE_DIR": str(state_root / "policyd" / "audit-archive"),
        "AIOS_POLICYD_OBSERVABILITY_LOG": str(state_root / "policyd" / "observability.jsonl"),
        "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
    }


class CompatBridgeHandler(BaseHTTPRequestHandler):
    server_version = "AIOSCompatBridgeSmoke/0.1"

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw_body)
        if self.path == "/mcp":
            response = {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "echo_method": payload.get("method"),
                    "echo_params": payload.get("params") or {},
                },
            }
        elif self.path == "/a2a":
            response = {"accepted": True, "received": payload}
        else:
            response = {"error": "unknown path"}

        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    deadline = time.time() + 5
    for process in processes:
        if process.poll() is not None:
            continue
        remaining = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def print_logs(processes: dict[str, subprocess.Popen]) -> None:
    for name, process in processes.items():
        output = ""
        if process.stdout and process.poll() is not None:
            output = process.stdout.read()
        if output.strip():
            print(f"\n--- {name} log ---")
            print(output.rstrip())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def allocate_temp_root() -> Path:
    if Path("/tmp").exists():
        return Path(tempfile.mkdtemp(prefix="aios-compat-", dir="/tmp"))
    return Path(tempfile.mkdtemp(prefix="aios-compat-"))


def run_json_command(command: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> tuple[int, dict]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        env=command_env,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr.strip()}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not return JSON: {' '.join(command)}") from exc
    return completed.returncode, payload


def main() -> int:
    args = parse_args()
    binaries = {
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
    }
    ensure_binaries(binaries)

    temp_root = allocate_temp_root()
    env = make_env(temp_root)
    policyd_env = make_policyd_env(temp_root)
    socket_path = Path(env["AIOS_AGENTD_SOCKET_PATH"])
    policyd_socket_path = Path(policyd_env["AIOS_POLICYD_SOCKET_PATH"])
    processes: dict[str, subprocess.Popen] = {}
    failed = False
    bridge_server = ThreadingHTTPServer(("127.0.0.1", 0), CompatBridgeHandler)
    bridge_thread = threading.Thread(target=bridge_server.serve_forever, daemon=True)
    bridge_thread.start()

    try:
        processes["policyd"] = launch(binaries["policyd"], {**os.environ.copy(), **policyd_env})
        wait_for_socket(policyd_socket_path, args.timeout)
        wait_for_health(policyd_socket_path, args.timeout)
        processes["agentd"] = launch(binaries["agentd"], env)
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        print(f"agentd ready: {health['status']} @ {health['socket_path']}")
        shared_compat_audit_log = temp_root / "audit" / "compat-observability.jsonl"

        compat_discovery = rpc_call(
            socket_path,
            "provider.discover",
            {
                "kind": "compat-provider",
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        discovered_provider_ids = {
            candidate["provider_id"]
            for candidate in compat_discovery.get("candidates", [])
            if isinstance(candidate, dict) and candidate.get("provider_id")
        }
        require(
            discovered_provider_ids == set(COMPAT_PROVIDERS),
            f"unexpected compat provider set: {sorted(discovered_provider_ids)}",
        )

        runtime_checks: list[dict[str, object]] = []
        for provider_id, config in COMPAT_PROVIDERS.items():
            descriptor_path = repo_root() / config["descriptor"]
            runtime_path = repo_root() / config["runtime"]
            descriptor = json.loads(descriptor_path.read_text())
            runtime_env = dict(config.get("env") or {})
            runtime_env["AIOS_COMPAT_POLICYD_SOCKET"] = str(policyd_socket_path)
            runtime_env["AIOS_COMPAT_OBSERVABILITY_LOG"] = str(shared_compat_audit_log)
            audit_log_env_var = config.get("audit_log_env_var")
            audit_log_path: Path | None = None
            if isinstance(audit_log_env_var, str):
                audit_root = temp_root / "audit"
                audit_root.mkdir(parents=True, exist_ok=True)
                audit_log_path = audit_root / f"{provider_id.replace('.', '-')}.jsonl"
                runtime_env[audit_log_env_var] = str(audit_log_path)
            descriptor_capabilities = [
                capability["capability_id"] for capability in descriptor.get("capabilities", [])
            ]
            expected_capabilities = config["capabilities"]
            expected_required_permissions = config["required_permissions"]
            require(
                descriptor_capabilities == expected_capabilities,
                f"descriptor capabilities mismatch for {provider_id}: {descriptor_capabilities}",
            )
            descriptor_permission_manifest = descriptor.get("compat_permission_manifest") or {}
            require(
                descriptor_permission_manifest.get("required_permissions") == expected_required_permissions,
                f"descriptor compat permission manifest mismatch for {provider_id}",
            )
            expected_worker_contract = config.get("worker_contract")
            if expected_worker_contract is not None:
                require(
                    descriptor.get("worker_contract") == expected_worker_contract,
                    f"descriptor worker contract mismatch for {provider_id}",
                )
            expected_result_protocol_schema_ref = config.get("result_protocol_schema_ref")
            if expected_result_protocol_schema_ref is not None:
                require(
                    descriptor.get("result_protocol_schema_ref") == expected_result_protocol_schema_ref,
                    f"descriptor result protocol schema mismatch for {provider_id}",
                )

            descriptor_lookup = rpc_call(
                socket_path,
                "provider.get_descriptor",
                {"provider_id": provider_id},
                timeout=args.timeout,
            )
            rpc_descriptor = descriptor_lookup.get("descriptor") or {}
            require(
                rpc_descriptor.get("provider_id") == provider_id,
                f"registry did not return descriptor for {provider_id}",
            )
            require(
                (rpc_descriptor.get("compat_permission_manifest") or {}).get("provider_id") == provider_id,
                f"registry did not preserve compat permission manifest for {provider_id}",
            )
            if expected_worker_contract is not None:
                require(
                    rpc_descriptor.get("worker_contract") == expected_worker_contract,
                    f"registry descriptor worker contract mismatch for {provider_id}",
                )
            if expected_result_protocol_schema_ref is not None:
                require(
                    rpc_descriptor.get("result_protocol_schema_ref") == expected_result_protocol_schema_ref,
                    f"registry descriptor result protocol schema mismatch for {provider_id}",
                )

            _, manifest = run_json_command(
                [sys.executable, str(runtime_path), *config["manifest_args"]],
                env=runtime_env,
            )
            require(manifest.get("provider_id") == provider_id, f"manifest provider mismatch for {provider_id}")
            require(
                manifest.get("declared_capabilities") == expected_capabilities,
                f"manifest capability mismatch for {provider_id}",
            )
            require(
                manifest.get("required_permissions") == expected_required_permissions,
                f"manifest required permissions mismatch for {provider_id}",
            )
            runtime_permission_manifest = manifest.get("compat_permission_manifest") or {}
            require(
                runtime_permission_manifest.get("provider_id") == provider_id,
                f"manifest compat permission manifest mismatch for {provider_id}",
            )
            require(
                runtime_permission_manifest.get("required_permissions") == expected_required_permissions,
                f"manifest compat permission required permissions mismatch for {provider_id}",
            )
            if expected_worker_contract is not None:
                require(
                    manifest.get("worker_contract") == expected_worker_contract,
                    f"manifest worker contract mismatch for {provider_id}",
                )
            if expected_result_protocol_schema_ref is not None:
                require(
                    manifest.get("result_protocol_schema_ref") == expected_result_protocol_schema_ref,
                    f"manifest result protocol schema mismatch for {provider_id}",
                )
            expected_implemented_methods = config.get("implemented_methods")
            if expected_implemented_methods is not None:
                require(
                    set(expected_implemented_methods).issubset(set(manifest.get("implemented_methods") or [])),
                    f"manifest implemented methods mismatch for {provider_id}",
                )

            _, runtime_permissions = run_json_command(
                [sys.executable, str(runtime_path), *config["permissions_args"]],
                env=runtime_env,
            )
            require(
                runtime_permissions.get("provider_id") == provider_id,
                f"permissions provider mismatch for {provider_id}",
            )
            require(
                runtime_permissions.get("required_permissions") == expected_required_permissions,
                f"permissions required permissions mismatch for {provider_id}",
            )

            _, runtime_health = run_json_command(
                [sys.executable, str(runtime_path), *config["health_args"]],
                env=runtime_env,
            )
            require(
                runtime_health.get("provider_id") == provider_id,
                f"health provider mismatch for {provider_id}",
            )
            expected_runtime_status = config.get("expected_runtime_status")
            if expected_runtime_status is not None:
                require(
                    runtime_health.get("status") == expected_runtime_status,
                    f"runtime status mismatch for {provider_id}: expected {expected_runtime_status}, got {runtime_health.get('status')}",
                )
            require(
                (runtime_health.get("compat_permission_manifest") or {}).get("provider_id") == provider_id,
                f"health compat permission manifest mismatch for {provider_id}",
            )
            if expected_worker_contract is not None:
                require(
                    runtime_health.get("worker_contract") == expected_worker_contract,
                    f"health worker contract mismatch for {provider_id}",
                )
            if expected_result_protocol_schema_ref is not None:
                require(
                    runtime_health.get("result_protocol_schema_ref") == expected_result_protocol_schema_ref,
                    f"health result protocol schema mismatch for {provider_id}",
                )
            if audit_log_path is not None:
                require(
                    runtime_health.get("audit_log_configured") is True,
                    f"health audit_log_configured mismatch for {provider_id}",
                )
                require(
                    runtime_health.get("audit_log_path") == str(audit_log_path),
                    f"health audit_log_path mismatch for {provider_id}",
                )
                require(
                    runtime_health.get("shared_audit_log_configured") is True,
                    f"health shared_audit_log_configured mismatch for {provider_id}",
                )
                require(
                    runtime_health.get("shared_audit_log_path") == str(shared_compat_audit_log),
                    f"health shared_audit_log_path mismatch for {provider_id}",
                )
                require(
                    runtime_health.get("policyd_socket") == str(policyd_socket_path),
                    f"health policyd_socket mismatch for {provider_id}",
                )

            resolved = rpc_call(
                socket_path,
                "provider.resolve_capability",
                {
                    "capability_id": expected_capabilities[0],
                    "preferred_kind": "compat-provider",
                    "require_healthy": True,
                    "include_disabled": False,
                },
                timeout=args.timeout,
            )
            selected = resolved.get("selected") or {}
            require(
                selected.get("provider_id") == provider_id,
                f"capability {expected_capabilities[0]} resolved to {selected.get('provider_id')} instead of {provider_id}",
            )

            runtime_checks.append(
                {
                    "provider_id": provider_id,
                    "capabilities": expected_capabilities,
                    "runtime_status": runtime_health.get("status"),
                    "required_permissions": expected_required_permissions,
                    "audit_log_configured": runtime_health.get("audit_log_configured"),
                }
            )

        fixtures_root = temp_root / "fixtures"
        fixtures_root.mkdir(parents=True, exist_ok=True)
        browser_fixture = fixtures_root / "browser.html"
        browser_fixture.write_text(
            (
                "<html><head><title>Compat Runtime Smoke</title></head>"
                "<body><div id='content'>centralized browser policy path</div></body></html>"
            ),
            encoding="utf-8",
        )
        office_fixture = fixtures_root / "office.md"
        office_fixture.write_text(
            "# Compat Runtime Smoke\n\ncentralized office policy path\n",
            encoding="utf-8",
        )
        office_pdf = fixtures_root / "office.pdf"
        bridge_endpoint = f"http://127.0.0.1:{bridge_server.server_address[1]}"

        provider_audit_paths = {
            provider_id: temp_root / "audit" / f"{provider_id.replace('.', '-')}.jsonl"
            for provider_id in COMPAT_PROVIDERS
        }

        browser_token = issue_execution_token(
            policyd_socket_path,
            "compat.browser.navigate",
            session_id="compat-browser-session",
            task_id="compat-browser-task",
            timeout=args.timeout,
        )
        browser_env = {
            "AIOS_COMPAT_POLICYD_SOCKET": str(policyd_socket_path),
            "AIOS_COMPAT_OBSERVABILITY_LOG": str(shared_compat_audit_log),
            "AIOS_COMPAT_BROWSER_AUDIT_LOG": str(provider_audit_paths["compat.browser.automation.local"]),
            "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(browser_token),
        }
        _, browser_payload = run_json_command(
            [
                sys.executable,
                str(repo_root() / COMPAT_PROVIDERS["compat.browser.automation.local"]["runtime"]),
                "navigate",
                "--url",
                browser_fixture.resolve().as_uri(),
            ],
            env=browser_env,
        )
        require(browser_payload.get("status") == "ok", "browser token-verified navigate failed")
        require(
            ((browser_payload.get("result_protocol") or {}).get("policy") or {}).get("mode") == "policyd-verified",
            "browser result protocol missing policyd-verified mode",
        )
        require(
            (((browser_payload.get("result_protocol") or {}).get("policy") or {}).get("execution_token") or {}).get("session_id")
            == "compat-browser-session",
            "browser result protocol missing execution token session_id",
        )

        office_token = issue_execution_token(
            policyd_socket_path,
            "compat.document.open",
            session_id="compat-office-session",
            task_id="compat-office-task",
            timeout=args.timeout,
        )
        office_env = {
            "AIOS_COMPAT_POLICYD_SOCKET": str(policyd_socket_path),
            "AIOS_COMPAT_OBSERVABILITY_LOG": str(shared_compat_audit_log),
            "AIOS_COMPAT_OFFICE_AUDIT_LOG": str(provider_audit_paths["compat.office.document.local"]),
            "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(office_token),
        }
        _, office_payload = run_json_command(
            [
                sys.executable,
                str(repo_root() / COMPAT_PROVIDERS["compat.office.document.local"]["runtime"]),
                "open",
                "--path",
                str(office_fixture),
            ],
            env=office_env,
        )
        require(office_payload.get("status") == "ok", "office token-verified open failed")
        require(
            ((office_payload.get("result_protocol") or {}).get("policy") or {}).get("mode") == "policyd-verified",
            "office result protocol missing policyd-verified mode",
        )

        bridge_token = issue_execution_token(
            policyd_socket_path,
            "compat.mcp.call",
            session_id="compat-bridge-session",
            task_id="compat-bridge-task",
            timeout=args.timeout,
        )
        bridge_env = {
            "AIOS_COMPAT_POLICYD_SOCKET": str(policyd_socket_path),
            "AIOS_COMPAT_OBSERVABILITY_LOG": str(shared_compat_audit_log),
            "AIOS_COMPAT_MCP_BRIDGE_AUDIT_LOG": str(provider_audit_paths["compat.mcp.bridge.local"]),
            "AIOS_MCP_BRIDGE_TRUST_MODE": "allowlist",
            "AIOS_MCP_BRIDGE_ALLOWLIST": "127.0.0.1,localhost",
            "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(bridge_token),
        }
        _, bridge_payload = run_json_command(
            [
                sys.executable,
                str(repo_root() / COMPAT_PROVIDERS["compat.mcp.bridge.local"]["runtime"]),
                "call",
                "--endpoint",
                f"{bridge_endpoint}/mcp",
                "--tool",
                "tools.echo",
                "--arguments",
                '{"message":"compat-smoke"}',
            ],
            env=bridge_env,
        )
        require(bridge_payload.get("status") == "ok", "bridge token-verified call failed")
        require(
            ((bridge_payload.get("result_protocol") or {}).get("policy") or {}).get("mode") == "policyd-verified",
            "bridge result protocol missing policyd-verified mode",
        )

        with tempfile.TemporaryDirectory(prefix="aios-compat-code-") as sandbox_dir:
            success_script = Path(sandbox_dir) / "success.py"
            success_script.write_text("print('compat-sandbox-ok')\n")
            sandbox_token = issue_execution_token(
                policyd_socket_path,
                "compat.code.execute",
                session_id="compat-sandbox-session",
                task_id="compat-sandbox-task",
                timeout=args.timeout,
            )
            sandbox_env = {
                "AIOS_COMPAT_POLICYD_SOCKET": str(policyd_socket_path),
                "AIOS_COMPAT_OBSERVABILITY_LOG": str(shared_compat_audit_log),
                "AIOS_COMPAT_CODE_SANDBOX_AUDIT_LOG": str(provider_audit_paths["compat.code.sandbox.local"]),
                "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(sandbox_token),
            }

            _, success_payload = run_json_command(
                [
                    sys.executable,
                    str(repo_root() / COMPAT_PROVIDERS["compat.code.sandbox.local"]["runtime"]),
                    "execute",
                    "--code-file",
                    str(success_script),
                    "--timeout-seconds",
                    "2",
                    "--memory-mb",
                    "128",
                    "--json",
                ],
                env=sandbox_env,
            )
            require(success_payload["exit_code"] == 0, "code sandbox success path returned non-zero exit_code")
            require(
                "compat-sandbox-ok" in success_payload["stdout"],
                "code sandbox success path did not emit expected marker",
            )
            result_protocol = success_payload.get("result_protocol") or {}
            require(
                result_protocol.get("protocol_version") == "1.0.0",
                "code sandbox result protocol version mismatch",
            )
            require(
                (result_protocol.get("policy") or {}).get("compat_permission_manifest", {}).get("provider_id")
                == "compat.code.sandbox.local",
                "code sandbox result protocol missing compat permission manifest",
            )
            require(
                result_protocol.get("worker_contract") == "compat-sandbox-executor-v1",
                "code sandbox result protocol worker contract mismatch",
            )
            require(
                (result_protocol.get("audit") or {}).get("capability_id") == "compat.code.execute",
                "code sandbox result protocol missing audit capability_id",
            )
            require(
                (result_protocol.get("policy") or {}).get("mode") == "policyd-verified",
                "code sandbox result protocol missing policyd-verified mode",
            )
            require(
                ((result_protocol.get("audit") or {}).get("execution_token") or {}).get("approval_ref"),
                "code sandbox result protocol missing approval_ref",
            )

            timeout_script = Path(sandbox_dir) / "timeout.py"
            timeout_script.write_text("import time\ntime.sleep(2)\n")
            timeout_token = issue_execution_token(
                policyd_socket_path,
                "compat.code.execute",
                session_id="compat-sandbox-timeout-session",
                task_id="compat-sandbox-timeout-task",
                timeout=args.timeout,
            )
            timeout_env = {
                **sandbox_env,
                "AIOS_COMPAT_EXECUTION_TOKEN": json.dumps(timeout_token),
            }
            timeout_code, timeout_payload = run_json_command(
                [
                    sys.executable,
                    str(repo_root() / COMPAT_PROVIDERS["compat.code.sandbox.local"]["runtime"]),
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
                env=timeout_env,
            )
            require(timeout_code == 124, f"expected timeout exit code 124, got {timeout_code}")
            require(timeout_payload["timed_out"] is True, "timeout payload did not mark timed_out=true")
            require(
                (timeout_payload.get("result_protocol") or {}).get("resources", {}).get("timed_out") is True,
                "timeout result protocol did not mark timed_out=true",
            )

        shared_entries = read_jsonl(shared_compat_audit_log)
        require(shared_entries, "shared compat observability log was not created")
        require(
            any(
                entry.get("provider_id") == "compat.browser.automation.local"
                and entry.get("session_id") == "compat-browser-session"
                for entry in shared_entries
            ),
            "shared compat observability log missing browser token-correlated entry",
        )
        require(
            any(
                entry.get("provider_id") == "compat.office.document.local"
                and entry.get("session_id") == "compat-office-session"
                for entry in shared_entries
            ),
            "shared compat observability log missing office token-correlated entry",
        )
        require(
            any(
                entry.get("provider_id") == "compat.mcp.bridge.local"
                and entry.get("session_id") == "compat-bridge-session"
                for entry in shared_entries
            ),
            "shared compat observability log missing bridge token-correlated entry",
        )
        require(
            any(
                entry.get("provider_id") == "compat.code.sandbox.local"
                and entry.get("approval_id")
                and entry.get("session_id") == "compat-sandbox-session"
                for entry in shared_entries
            ),
            "shared compat observability log missing sandbox approval-correlated entry",
        )

        print(
            json.dumps(
                {
                    "compat_provider_count": len(discovered_provider_ids),
                    "providers": runtime_checks,
                    "sandbox_timeout_exit_code": timeout_code,
                    "shared_compat_audit_log": str(shared_compat_audit_log),
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"Compat runtime smoke failed: {exc}")
        return 1
    finally:
        bridge_server.shutdown()
        bridge_server.server_close()
        bridge_thread.join(timeout=5)
        terminate(list(processes.values()))
        print_logs(processes)
        if failed or args.keep_state:
            print(f"compat runtime smoke state preserved at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
