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
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS portal file-handle smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing the sessiond binary")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
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


def ensure_binary(path: Path) -> None:
    if path.exists():
        return
    print(f"Missing binary: sessiond={path}")
    print("Build it first, for example: cargo build -p aios-sessiond")
    raise SystemExit(2)


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_response(socket_path, method, params, timeout)
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def rpc_response(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
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
    return json.loads(data.decode("utf-8"))


def run_python(script: Path, *args: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=repo_root(),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


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
    raise TimeoutError(f"Timed out waiting for sessiond health: {last_error}")


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
        }
    )
    return env


def main() -> int:
    args = parse_args()
    sessiond = resolve_binary("sessiond", args.sessiond, args.bin_dir)
    ensure_binary(sessiond)

    temp_root = Path(tempfile.mkdtemp(prefix="aios-prt-file-", dir="/tmp"))
    workspace = temp_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    file_path = workspace / "report.txt"
    file_path.write_text("portal file handle smoke\n")
    directory_path = workspace / "reports"
    directory_path.mkdir()

    env = make_env(temp_root)
    socket_path = Path(env["AIOS_SESSIOND_SOCKET_PATH"])
    process: subprocess.Popen | None = None
    failed = False
    try:
        process = launch(sessiond, env)
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        require(health["status"] == "ready", "sessiond did not become ready")

        session = rpc_call(
            socket_path,
            "session.create",
            {"user_id": "portal-smoke-user", "metadata": {"source": "portal-file-handle-smoke"}},
            timeout=args.timeout,
        )
        session_id = session["session"]["session_id"]

        file_handle = rpc_call(
            socket_path,
            "portal.handle.issue",
            {
                "kind": "file_handle",
                "user_id": "portal-smoke-user",
                "session_id": session_id,
                "target": str(file_path),
                "scope": {"source": "portal-file-handle-smoke"},
                "expiry_seconds": 300,
                "revocable": True,
                "audit_tags": ["portal", "file", "smoke"],
            },
            timeout=args.timeout,
        )
        require(file_handle["scope"]["display_name"] == "report.txt", "file handle display_name mismatch")
        require(file_handle["scope"]["target_kind"] == "file", "file handle target kind mismatch")
        require(file_handle["scope"]["availability"] == "available", "file handle availability mismatch")
        require(file_handle["scope"]["target_exists"] is True, "file handle target_exists mismatch")
        require(
            file_handle["scope"]["canonical_target"] == str(file_path.resolve()),
            "file handle canonical target mismatch",
        )

        directory_handle = rpc_call(
            socket_path,
            "portal.handle.issue",
            {
                "kind": "directory_handle",
                "user_id": "portal-smoke-user",
                "session_id": session_id,
                "target": str(directory_path),
                "scope": {"source": "portal-file-handle-smoke"},
                "expiry_seconds": 300,
                "revocable": True,
                "audit_tags": ["portal", "directory", "smoke"],
            },
            timeout=args.timeout,
        )
        require(directory_handle["scope"]["target_kind"] == "directory", "directory handle target kind mismatch")
        require(
            directory_handle["scope"]["display_name"] == "reports",
            "directory handle display_name mismatch",
        )

        missing_issue = rpc_response(
            socket_path,
            "portal.handle.issue",
            {
                "kind": "file_handle",
                "user_id": "portal-smoke-user",
                "session_id": session_id,
                "target": str(workspace / "missing.txt"),
                "scope": {"source": "portal-file-handle-smoke"},
                "expiry_seconds": 300,
                "revocable": True,
                "audit_tags": ["portal", "file", "smoke"],
            },
            timeout=args.timeout,
        )
        require(missing_issue.get("error") is not None, "missing file portal issue should fail")
        require(
            "portal target does not exist" in missing_issue["error"].get("message", ""),
            "missing file portal issue returned unexpected error",
        )

        wrong_kind_issue = rpc_response(
            socket_path,
            "portal.handle.issue",
            {
                "kind": "directory_handle",
                "user_id": "portal-smoke-user",
                "session_id": session_id,
                "target": str(file_path),
                "scope": {"source": "portal-file-handle-smoke"},
                "expiry_seconds": 300,
                "revocable": True,
                "audit_tags": ["portal", "directory", "smoke"],
            },
            timeout=args.timeout,
        )
        require(wrong_kind_issue.get("error") is not None, "wrong-kind portal issue should fail")
        require(
            "directory_handle target is not a directory"
            in wrong_kind_issue["error"].get("message", ""),
            "wrong-kind portal issue returned unexpected error",
        )

        chooser_summary = json.loads(
            run_python(
                repo_root() / "aios/shell/components/portal-chooser/prototype.py",
                "summary",
                "--socket",
                str(socket_path),
                "--session-id",
                session_id,
                "--json",
            )
        )
        require(chooser_summary["total"] == 2, "chooser live summary total mismatch")
        require(
            chooser_summary["by_kind"].get("file_handle") == 1,
            "chooser live summary missing file handle",
        )
        require(
            chooser_summary["by_kind"].get("directory_handle") == 1,
            "chooser live summary missing directory handle",
        )
        require(
            chooser_summary["selectable_total"] == 2,
            "chooser live summary selectable_total mismatch",
        )

        same_context = rpc_call(
            socket_path,
            "portal.handle.lookup",
            {
                "handle_id": file_handle["handle_id"],
                "session_id": session_id,
                "user_id": "portal-smoke-user",
            },
            timeout=args.timeout,
        )
        require(same_context["handle"]["handle_id"] == file_handle["handle_id"], "same-context lookup failed")

        wrong_session = rpc_call(
            socket_path,
            "portal.handle.lookup",
            {
                "handle_id": file_handle["handle_id"],
                "session_id": "wrong-session",
                "user_id": "portal-smoke-user",
            },
            timeout=args.timeout,
        )
        require(wrong_session.get("handle") is None, "cross-session portal lookup should be hidden")

        denied_revoke = rpc_call(
            socket_path,
            "portal.handle.revoke",
            {
                "handle_id": file_handle["handle_id"],
                "session_id": "wrong-session",
                "user_id": "portal-smoke-user",
                "reason": "should not apply",
            },
            timeout=args.timeout,
        )
        require(denied_revoke.get("handle") is None, "cross-session portal revoke should be hidden")

        allowed_revoke = rpc_call(
            socket_path,
            "portal.handle.revoke",
            {
                "handle_id": file_handle["handle_id"],
                "session_id": session_id,
                "user_id": "portal-smoke-user",
                "reason": "user requested",
            },
            timeout=args.timeout,
        )
        require(allowed_revoke["handle"]["revoked_at"], "portal revoke did not persist revoked_at")

        listed = rpc_call(
            socket_path,
            "portal.handle.list",
            {"session_id": session_id},
            timeout=args.timeout,
        )
        require(len(listed["handles"]) == 2, "portal list handle count mismatch")

        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "file_handle_id": file_handle["handle_id"],
                    "directory_handle_id": directory_handle["handle_id"],
                    "file_target_kind": file_handle["scope"]["target_kind"],
                    "chooser_total": chooser_summary["total"],
                    "wrong_session_hidden": wrong_session.get("handle") is None,
                    "revoked": bool(allowed_revoke["handle"]["revoked_at"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"portal file-handle smoke failed: {exc}")
        return 1
    finally:
        logs = terminate(process)
        if failed and logs.strip():
            print("\n--- sessiond log ---")
            print(logs.rstrip())
        if args.keep_state or failed:
            print(f"state kept at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
