#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS system-files provider smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing sessiond/policyd/system-files-provider binaries")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--provider", type=Path, help="Path to system-files-provider binary")
    parser.add_argument("--user-id", default="provider-smoke-user", help="User id for the smoke request")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(repo_root()), name)


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"

def ensure_binaries(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing binaries for provider smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print("Build them first, for example: cargo build -p aios-sessiond -p aios-policyd -p aios-system-files-provider")
        raise SystemExit(2)


def rpc_response(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
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
    return json.loads(data.decode("utf-8"))


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_response(socket_path, method, params, timeout)
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


def note_map(health: dict) -> dict[str, str]:
    notes: dict[str, str] = {}
    for note in health.get("notes", []):
        if isinstance(note, str) and "=" in note:
            key, value = note.split("=", 1)
            notes[key] = value
    return notes


def read_json_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def wait_for_json_lines(path: Path, timeout: float, predicate, description: str) -> list[dict]:
    deadline = time.time() + timeout
    last_seen: list[dict] = []
    while time.time() < deadline:
        if path.exists():
            last_seen = read_json_lines(path)
            if predicate(last_seen):
                return last_seen
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for {description} in {path}: {last_seen}")


def make_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_SESSIOND_RUNTIME_DIR": str(runtime_root / "sessiond"),
            "AIOS_SESSIOND_STATE_DIR": str(state_root / "sessiond"),
            "AIOS_SESSIOND_SOCKET_PATH": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_SESSIOND_DATABASE": str(state_root / "sessiond" / "sessiond.sqlite3"),
            "AIOS_SESSIOND_PORTAL_STATE_DIR": str(state_root / "sessiond" / "portal"),
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "policyd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "policyd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(repo / "aios" / "policy" / "profiles" / "default-policy.yaml"),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(repo / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "policyd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
            "AIOS_SYSTEM_FILES_PROVIDER_RUNTIME_DIR": str(runtime_root / "system-files-provider"),
            "AIOS_SYSTEM_FILES_PROVIDER_STATE_DIR": str(state_root / "system-files-provider"),
            "AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH": str(runtime_root / "system-files-provider" / "system-files-provider.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_SESSIOND_SOCKET": str(runtime_root / "sessiond" / "sessiond.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_POLICYD_SOCKET": str(runtime_root / "policyd" / "policyd.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_AGENTD_SOCKET": str(runtime_root / "agentd" / "agentd.sock"),
            "AIOS_SYSTEM_FILES_PROVIDER_DESCRIPTOR_PATH": str(
                repo / "aios" / "sdk" / "providers" / "system-files.local.json"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_AUDIT_LOG": str(state_root / "system-files-provider" / "audit.jsonl"),
            "AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "system-files-provider" / "observability.jsonl"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_PREVIEW_BYTES": "4096",
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_DIRECTORY_ENTRIES": "32",
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_CONCURRENCY": "1",
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_DELETE_AFFECTED_PATHS": "8",
            "AIOS_SYSTEM_FILES_PROVIDER_TEST_STARTUP_RESERVE_MS": "900",
        }
    )
    return env


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


def portal_issue(sessiond_socket: Path, user_id: str, session_id: str, kind: str, target: Path, timeout: float) -> dict:
    return rpc_call(
        sessiond_socket,
        "portal.handle.issue",
        {
            "kind": kind,
            "user_id": user_id,
            "session_id": session_id,
            "target": str(target),
            "scope": {"source": "provider-smoke"},
            "expiry_seconds": 300,
            "revocable": True,
            "audit_tags": ["provider-smoke", kind],
        },
        timeout=timeout,
    )


def issue_token(
    policyd_socket: Path,
    *,
    user_id: str,
    session_id: str,
    task_id: str,
    capability_id: str,
    target_hash: str,
    approval_ref: str | None,
    timeout: float,
    constraints: dict | None = None,
) -> dict:
    return rpc_call(
        policyd_socket,
        "policy.token.issue",
        {
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "target_hash": target_hash,
            "approval_ref": approval_ref,
            "constraints": constraints or {},
            "execution_location": "local",
        },
        timeout=timeout,
    )


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("system-files provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "sessiond": resolve_binary("sessiond", args.sessiond, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "provider": resolve_binary("system-files-provider", args.provider, args.bin_dir),
    }
    ensure_binaries(binaries)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-provider-fs-smoke-", dir="/tmp"))
    workspace = temp_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    preview_file = workspace / "preview.txt"
    preview_file.write_text("hello from aios provider smoke\n")
    preview_dir = workspace / "preview-dir"
    preview_dir.mkdir()
    (preview_dir / "nested.txt").write_text("nested entry\n")
    delete_dir = workspace / "delete-me"
    delete_dir.mkdir()
    (delete_dir / "child-a.txt").write_text("A\n")
    nested = delete_dir / "nested"
    nested.mkdir()
    (nested / "child-b.txt").write_text("B\n")

    env = make_env(temp_root)
    processes: dict[str, subprocess.Popen] = {}
    failed = False

    try:
        for name in ["sessiond", "policyd", "provider"]:
            processes[name] = launch(binaries[name], env)

        sockets = {
            "sessiond": Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            "policyd": Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            "provider": Path(env["AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH"]),
        }

        for name, socket_path in sockets.items():
            wait_for_socket(socket_path, args.timeout)
            health = wait_for_health(socket_path, args.timeout)
            print(f"{name} ready: {health['status']} @ {health['socket_path']}")
            if name == "provider":
                provider_notes = note_map(health)
                audit_log_path = Path(env["AIOS_SYSTEM_FILES_PROVIDER_AUDIT_LOG"])
                observability_log_path = Path(
                    env["AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG"]
                )
                require(
                    any(note == f"audit_log_path={audit_log_path}" for note in health["notes"]),
                    "provider health missing audit log path",
                )
                require(
                    provider_notes.get("observability_log_path")
                    == str(observability_log_path),
                    "provider health missing observability log path",
                )
                require(
                    any(note == "max_concurrency=1" for note in health["notes"]),
                    "provider health missing concurrency budget note",
                )
                require(
                    any(note == "max_delete_affected_paths=8" for note in health["notes"]),
                    "provider health missing delete affected-path budget note",
                )

        session_result = rpc_call(
            sockets["sessiond"],
            "session.create",
            {"user_id": args.user_id, "metadata": {"source": "provider-smoke"}},
            timeout=args.timeout,
        )
        session_id = session_result["session"]["session_id"]
        task_id = session_result["task"]["task_id"]
        alternate_session = rpc_call(
            sockets["sessiond"],
            "session.create",
            {"user_id": args.user_id, "metadata": {"source": "provider-smoke-alt"}},
            timeout=args.timeout,
        )["session"]["session_id"]

        file_handle = portal_issue(
            sockets["sessiond"],
            args.user_id,
            session_id,
            "file_handle",
            preview_file,
            timeout=args.timeout,
        )
        hidden_lookup = rpc_call(
            sockets["sessiond"],
            "portal.handle.lookup",
            {
                "handle_id": file_handle["handle_id"],
                "session_id": alternate_session,
                "user_id": args.user_id,
            },
            timeout=args.timeout,
        )
        require(
            hidden_lookup.get("handle") is None,
            "portal lookup leaked file handle across session boundary",
        )
        file_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id=session_id,
            task_id=task_id,
            capability_id="provider.fs.open",
            target_hash=file_handle["scope"]["target_hash"],
            approval_ref=None,
            timeout=args.timeout,
        )
        budget_blocked_open = rpc_response(
            sockets["provider"],
            "provider.fs.open",
            {
                "handle_id": file_handle["handle_id"],
                "execution_token": file_token,
                "include_content": True,
                "max_bytes": 128,
                "max_entries": 16,
            },
            timeout=args.timeout,
        )
        require(budget_blocked_open.get("error") is not None, "startup-reserved budget did not reject provider.fs.open")
        concurrency_error_message = budget_blocked_open["error"].get("message", "")
        require(
            "provider concurrency budget exhausted" in concurrency_error_message,
            "provider.fs.open did not fail with concurrency budget exhaustion during startup reserve",
        )
        time.sleep(1.0)

        file_open = rpc_call(
            sockets["provider"],
            "provider.fs.open",
            {
                "handle_id": file_handle["handle_id"],
                "execution_token": file_token,
                "include_content": True,
                "max_bytes": 128,
                "max_entries": 16,
            },
            timeout=args.timeout,
        )
        require(file_open["content_preview"].startswith("hello from aios provider smoke"), "file preview content mismatch")
        require(file_open["target_hash"] == file_handle["scope"]["target_hash"], "target hash mismatch for file open")

        directory_handle = portal_issue(
            sockets["sessiond"],
            args.user_id,
            session_id,
            "directory_handle",
            preview_dir,
            timeout=args.timeout,
        )
        directory_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id=session_id,
            task_id=task_id,
            capability_id="provider.fs.open",
            target_hash=directory_handle["scope"]["target_hash"],
            approval_ref=None,
            timeout=args.timeout,
        )
        directory_open = rpc_call(
            sockets["provider"],
            "provider.fs.open",
            {
                "handle_id": directory_handle["handle_id"],
                "execution_token": directory_token,
                "include_content": False,
                "max_entries": 16,
            },
            timeout=args.timeout,
        )
        entry_names = {entry["name"] for entry in directory_open.get("entries", [])}
        require("nested.txt" in entry_names, "directory listing did not include nested.txt")

        delete_handle = portal_issue(
            sockets["sessiond"],
            args.user_id,
            session_id,
            "directory_handle",
            delete_dir,
            timeout=args.timeout,
        )
        delete_eval = rpc_call(
            sockets["policyd"],
            "policy.evaluate",
            {
                "user_id": args.user_id,
                "session_id": session_id,
                "task_id": task_id,
                "capability_id": "system.file.bulk_delete",
                "execution_location": "local",
                "target_hash": delete_handle["scope"]["target_hash"],
                "constraints": {},
            },
            timeout=args.timeout,
        )
        approval_ref = delete_eval.get("approval_ref")
        require(bool(approval_ref), "bulk delete policy did not return approval_ref")
        rpc_call(
            sockets["policyd"],
            "approval.resolve",
            {
                "approval_ref": approval_ref,
                "status": "approved",
                "resolver": "provider-smoke",
                "reason": "smoke-approved",
            },
            timeout=args.timeout,
        )
        delete_token_without_constraints = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id=session_id,
            task_id=task_id,
            capability_id="system.file.bulk_delete",
            target_hash=delete_handle["scope"]["target_hash"],
            approval_ref=approval_ref,
            timeout=args.timeout,
        )
        delete_without_constraints = rpc_call(
            sockets["provider"],
            "system.file.bulk_delete",
            {
                "handle_id": delete_handle["handle_id"],
                "execution_token": delete_token_without_constraints,
                "recursive": True,
                "dry_run": True,
            },
            timeout=args.timeout,
        )
        require(delete_without_constraints["status"] == "skipped", "directory delete without constraints should be skipped")
        require(
            "allow_directory_delete=true" in (delete_without_constraints.get("reason") or ""),
            "directory delete without constraints did not explain missing allow_directory_delete",
        )

        scoped_delete_eval = rpc_call(
            sockets["policyd"],
            "policy.evaluate",
            {
                "user_id": args.user_id,
                "session_id": session_id,
                "task_id": task_id,
                "capability_id": "system.file.bulk_delete",
                "execution_location": "local",
                "target_hash": delete_handle["scope"]["target_hash"],
                "constraints": {
                    "allow_directory_delete": True,
                    "allow_recursive": True,
                    "max_affected_paths": 8,
                },
            },
            timeout=args.timeout,
        )
        scoped_approval_ref = scoped_delete_eval.get("approval_ref")
        require(bool(scoped_approval_ref), "scoped bulk delete approval_ref missing")
        rpc_call(
            sockets["policyd"],
            "approval.resolve",
            {
                "approval_ref": scoped_approval_ref,
                "status": "approved",
                "resolver": "provider-smoke",
                "reason": "scoped delete approved",
            },
            timeout=args.timeout,
        )

        delete_token_too_small = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id=session_id,
            task_id=task_id,
            capability_id="system.file.bulk_delete",
            target_hash=delete_handle["scope"]["target_hash"],
            approval_ref=scoped_approval_ref,
            timeout=args.timeout,
            constraints={
                "allow_directory_delete": True,
                "allow_recursive": True,
                "max_affected_paths": 2,
            },
        )
        delete_too_small = rpc_call(
            sockets["provider"],
            "system.file.bulk_delete",
            {
                "handle_id": delete_handle["handle_id"],
                "execution_token": delete_token_too_small,
                "recursive": True,
                "dry_run": True,
            },
            timeout=args.timeout,
        )
        require(delete_too_small["status"] == "skipped", "directory delete with too-small max_affected_paths should be skipped")
        require(
            "max_affected_paths" in (delete_too_small.get("reason") or ""),
            "directory delete with too-small max_affected_paths did not explain scope overflow",
        )

        delete_token = issue_token(
            sockets["policyd"],
            user_id=args.user_id,
            session_id=session_id,
            task_id=task_id,
            capability_id="system.file.bulk_delete",
            target_hash=delete_handle["scope"]["target_hash"],
            approval_ref=scoped_approval_ref,
            timeout=args.timeout,
            constraints={
                "allow_directory_delete": True,
                "allow_recursive": True,
                "max_affected_paths": 8,
            },
        )

        delete_dry_run = rpc_call(
            sockets["provider"],
            "system.file.bulk_delete",
            {
                "handle_id": delete_handle["handle_id"],
                "execution_token": delete_token,
                "recursive": True,
                "dry_run": True,
            },
            timeout=args.timeout,
        )
        affected_paths = set(delete_dry_run.get("affected_paths", []))
        require(delete_dry_run["status"] == "would-delete", "dry-run bulk delete should return would-delete")
        require(str(delete_dir) in affected_paths, "dry-run bulk delete missing root directory")
        require(str(nested / "child-b.txt") in affected_paths, "dry-run bulk delete missing nested child")

        delete_result = rpc_call(
            sockets["provider"],
            "system.file.bulk_delete",
            {
                "handle_id": delete_handle["handle_id"],
                "execution_token": delete_token,
                "recursive": True,
                "dry_run": False,
            },
            timeout=args.timeout,
        )
        require(delete_result["status"] == "deleted", "bulk delete should report deleted")
        require(not delete_dir.exists(), "bulk delete did not remove target directory")
        consumed_verify = rpc_call(
            sockets["policyd"],
            "policy.token.verify",
            {
                "token": delete_token,
                "target_hash": delete_handle["scope"]["target_hash"],
            },
            timeout=args.timeout,
        )
        require(
            consumed_verify["valid"] is False,
            "consumed bulk-delete token should not verify again",
        )
        require(
            "already consumed" in consumed_verify["reason"],
            "consumed bulk-delete token should explain reuse rejection",
        )

        provider_audit_log = Path(env["AIOS_SYSTEM_FILES_PROVIDER_AUDIT_LOG"])
        require(provider_audit_log.exists(), "provider audit log was not created")
        audit_entries = read_json_lines(provider_audit_log)
        require(len(audit_entries) >= 4, "provider audit log did not record enough entries")
        operations = [(entry.get("operation"), entry.get("status")) for entry in audit_entries]
        decisions = [(entry.get("operation"), entry.get("decision")) for entry in audit_entries]
        require(("provider.fs.open", "opened") in operations, "provider audit log missing open entry")
        require(("system.file.bulk_delete", "would-delete") in operations, "provider audit log missing dry-run delete entry")
        require(("system.file.bulk_delete", "deleted") in operations, "provider audit log missing delete entry")
        require(
            ("provider.fs.open", "allowed") in decisions,
            "provider audit log missing allowed open decision",
        )
        require(
            ("system.file.bulk_delete", "dry-run") in decisions,
            "provider audit log missing dry-run delete decision",
        )
        require(
            ("system.file.bulk_delete", "allowed") in decisions,
            "provider audit log missing allowed delete decision",
        )
        require(
            all(entry.get("schema_version") for entry in audit_entries),
            "provider audit log missing schema_version",
        )
        require(
            all(entry.get("generated_at") for entry in audit_entries),
            "provider audit log missing generated_at",
        )
        require(
            all(entry.get("artifact_path") == str(provider_audit_log) for entry in audit_entries),
            "provider audit log artifact_path mismatch",
        )

        provider_process = processes["provider"]
        if provider_process.poll() is None:
            provider_process.send_signal(signal.SIGINT)
            provider_process.wait(timeout=5)

        provider_observability_log = Path(
            env["AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG"]
        )
        observability_entries = wait_for_json_lines(
            provider_observability_log,
            args.timeout,
            lambda entries: {
                entry.get("kind")
                for entry in entries
                if isinstance(entry, dict) and entry.get("kind")
            }
            >= {"provider.runtime.started", "provider.runtime.stopped"},
            "system-files provider lifecycle observability events",
        )
        require(
            any(
                entry.get("kind") == "provider.runtime.started"
                and (entry.get("payload") or {}).get("socket_path")
                == env["AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH"]
                for entry in observability_entries
            ),
            "provider observability log missing startup socket payload",
        )
        require(
            any(
                entry.get("kind") == "provider.runtime.stopped"
                and (entry.get("payload") or {}).get("reason")
                in {"shutdown-signal", "provider server stopped"}
                for entry in observability_entries
            ),
            "provider observability log missing shutdown reason",
        )

        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "alternate_session_id": alternate_session,
                    "task_id": task_id,
                    "file_handle_id": file_handle["handle_id"],
                    "directory_handle_id": directory_handle["handle_id"],
                    "delete_handle_id": delete_handle["handle_id"],
                    "cross_session_lookup_hidden": True,
                    "dry_run_count": len(delete_dry_run.get("affected_paths", [])),
                    "workspace": str(workspace),
                    "provider_audit_entries": len(audit_entries),
                    "provider_observability_entries": len(observability_entries),
                    "provider_max_concurrency": 1,
                    "provider_max_delete_affected_paths": 8,
                    "concurrency_rejection": concurrency_error_message,
                    "directory_delete_missing_constraint_status": delete_without_constraints.get("status"),
                    "directory_delete_scope_limit_status": delete_too_small.get("status"),
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"Provider smoke harness failed: {exc}")
        return 1
    finally:
        terminate(list(processes.values()))
        print_logs(processes)
        if failed or args.keep_state:
            print(f"State kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
