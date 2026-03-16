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
    parser = argparse.ArgumentParser(description="AIOS policyd audit-store smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing the policyd binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
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


def ensure_binary(path: Path) -> None:
    if path.exists():
        return
    print(f"Missing binary: policyd={path}")
    print("Build it first, for example: cargo build -p aios-policyd")
    raise SystemExit(2)


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
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
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for socket: {path}")


def wait_for_health(socket_path: Path, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return rpc_call(socket_path, "system.health.get", {}, timeout=min(timeout, 1.0))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for policyd health: {last_error}")


def note_map(health: dict) -> dict[str, str]:
    notes: dict[str, str] = {}
    for note in health.get("notes", []):
        if isinstance(note, str) and "=" in note:
            key, value = note.split("=", 1)
            notes[key] = value
    return notes


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(process: subprocess.Popen | None) -> str:
    if process is None:
        return ""
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    return process.stdout.read() if process.stdout else ""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def make_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
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
            "AIOS_POLICYD_AUDIT_ROTATE_AFTER_BYTES": "700",
            "AIOS_POLICYD_AUDIT_RETENTION_DAYS": "30",
            "AIOS_POLICYD_AUDIT_MAX_ARCHIVES": "4",
            "AIOS_POLICYD_OBSERVABILITY_LOG": str(state_root / "policyd" / "observability.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "policyd" / "token.key"),
        }
    )
    return env


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("policyd audit-store smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    policyd = resolve_binary("policyd", args.policyd, args.bin_dir)
    ensure_binary(policyd)

    temp_dir = "/tmp" if Path("/tmp").exists() else None
    temp_root = Path(tempfile.mkdtemp(prefix="aios-policyd-audit-", dir=temp_dir))
    env = make_env(temp_root)
    socket_path = Path(env["AIOS_POLICYD_SOCKET_PATH"])
    process: subprocess.Popen | None = None
    failed = False
    try:
        process = launch(policyd, env)
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        notes = note_map(health)
        audit_log_path = Path(notes["audit"])
        audit_index_path = Path(notes["audit_index"])
        audit_archive_dir = Path(notes["audit_archive_dir"])
        require(audit_log_path == Path(env["AIOS_POLICYD_AUDIT_LOG"]), "audit log health note mismatch")
        require(audit_index_path == Path(env["AIOS_POLICYD_AUDIT_INDEX_PATH"]), "audit index health note mismatch")
        require(audit_archive_dir == Path(env["AIOS_POLICYD_AUDIT_ARCHIVE_DIR"]), "audit archive dir health note mismatch")

        latest_approval_ref = None
        latest_task_id = None
        for index in range(8):
            latest_task_id = f"audit-task-{index}"
            evaluation = rpc_call(
                socket_path,
                "policy.evaluate",
                {
                    "user_id": "audit-store-user",
                    "session_id": "audit-store-session",
                    "task_id": latest_task_id,
                    "capability_id": "system.file.bulk_delete",
                    "execution_location": "local",
                    "target_hash": "sha256:audit-store-smoke",
                    "constraints": {"allow_directory_delete": True},
                    "intent": "delete /tmp/audit-store-smoke and record rotation evidence " * 4,
                },
                timeout=args.timeout,
            )
            latest_approval_ref = evaluation.get("approval_ref")
            require(latest_approval_ref, "policy.evaluate should emit approval_ref for bulk delete")

        rpc_call(
            socket_path,
            "approval.resolve",
            {
                "approval_ref": latest_approval_ref,
                "status": "approved",
                "resolver": "audit-store-smoke",
                "reason": "smoke approved",
            },
            timeout=args.timeout,
        )
        token = rpc_call(
            socket_path,
            "policy.token.issue",
            {
                "user_id": "audit-store-user",
                "session_id": "audit-store-session",
                "task_id": latest_task_id,
                "capability_id": "system.file.bulk_delete",
                "target_hash": "sha256:audit-store-smoke",
                "approval_ref": latest_approval_ref,
                "constraints": {"allow_directory_delete": True},
                "execution_location": "local",
            },
            timeout=args.timeout,
        )
        verify = rpc_call(
            socket_path,
            "policy.token.verify",
            {
                "token": token,
                "target_hash": "sha256:audit-store-smoke",
            },
            timeout=args.timeout,
        )
        require(verify["valid"] is True, "issued token should verify")

        health_after = wait_for_health(socket_path, args.timeout)
        notes_after = note_map(health_after)
        require(int(notes_after.get("audit_archived_segments", "0")) >= 1, "audit store did not report archived segments")
        require(audit_index_path.exists(), "audit index artifact missing")
        require(audit_archive_dir.exists(), "audit archive directory missing")
        require(audit_log_path.exists(), "audit log artifact missing")

        index_payload = json.loads(audit_index_path.read_text())
        archived_segments = index_payload.get("archived_segments") or []
        require(archived_segments, "audit index should include archived segments")
        require(
            any(Path(segment["path"]).exists() for segment in archived_segments),
            "archived audit segment files missing on disk",
        )
        require(
            len(archived_segments) <= int(env["AIOS_POLICYD_AUDIT_MAX_ARCHIVES"]),
            "audit archive retention exceeded configured maximum",
        )
        require(
            index_payload["active_segment"]["record_count"] >= 1,
            "audit index active segment metadata mismatch",
        )

        query = rpc_call(
            socket_path,
            "policy.audit.query",
            {
                "session_id": "audit-store-session",
                "limit": 32,
                "reverse": True,
            },
            timeout=args.timeout,
        )
        require(
            len(query["entries"]) >= len(archived_segments) + 1,
            "audit query should include retained archived segments and the active log",
        )
        require(
            any(entry["decision"] == "approval-pending" for entry in query["entries"]),
            "audit query missing approval-pending entries",
        )
        require(
            any(entry["decision"] == "token-valid" for entry in query["entries"]),
            "audit query missing token-valid entry",
        )

        print(
            json.dumps(
                {
                    "audit_log": str(audit_log_path),
                    "audit_index": str(audit_index_path),
                    "audit_archive_dir": str(audit_archive_dir),
                    "archived_segments": len(archived_segments),
                    "queried_entries": len(query["entries"]),
                    "latest_approval_ref": latest_approval_ref,
                    "token_valid": verify["valid"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"policyd audit-store smoke failed: {exc}")
        return 1
    finally:
        logs = terminate(process)
        if failed and logs.strip():
            print("\n--- policyd log ---")
            print(logs.rstrip())
        if args.keep_state or failed:
            print(f"state kept at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
