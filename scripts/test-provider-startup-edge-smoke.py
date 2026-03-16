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
import textwrap
import time
from pathlib import Path

from aios_cargo_bins import default_aios_bin_dir, resolve_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS provider startup-edge smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing required binaries")
    parser.add_argument("--sessiond", type=Path, help="Path to sessiond binary")
    parser.add_argument("--policyd", type=Path, help="Path to policyd binary")
    parser.add_argument("--runtimed", type=Path, help="Path to runtimed binary")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument(
        "--system-files-provider",
        type=Path,
        help="Path to system-files-provider binary",
    )
    parser.add_argument(
        "--system-intent-provider",
        type=Path,
        help="Path to system-intent-provider binary",
    )
    parser.add_argument(
        "--device-metadata-provider",
        type=Path,
        help="Path to device-metadata-provider binary",
    )
    parser.add_argument(
        "--runtime-local-inference-provider",
        type=Path,
        help="Path to runtime-local-inference-provider binary",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for sockets and RPC calls",
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help="Keep temp runtime/state directory on success",
    )
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
        print("Missing binaries for provider startup-edge smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print(
            "Build them first, for example: cargo build -p aios-sessiond -p aios-policyd -p aios-runtimed -p aios-deviced -p aios-system-files-provider -p aios-system-intent-provider -p aios-device-metadata-provider -p aios-runtime-local-inference-provider"
        )
        raise SystemExit(2)


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


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_response(socket_path, method, params, timeout)
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def portal_issue(
    sessiond_socket: Path,
    *,
    user_id: str,
    session_id: str,
    kind: str,
    target: Path,
    timeout: float,
) -> dict:
    return rpc_call(
        sessiond_socket,
        "portal.handle.issue",
        {
            "kind": kind,
            "user_id": user_id,
            "session_id": session_id,
            "target": str(target),
            "scope": {"source": "provider-startup-edge-smoke"},
            "expiry_seconds": 300,
            "revocable": True,
            "audit_tags": ["provider-startup-edge-smoke", kind],
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
    timeout: float,
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
            "constraints": {},
            "execution_location": "local",
        },
        timeout=timeout,
    )


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
            return rpc_call(socket_path, "system.health.get", {}, timeout=min(timeout, 1.5))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health on {socket_path}: {last_error}")


def note_map(health: dict) -> dict[str, str]:
    notes: dict[str, str] = {}
    for note in health.get("notes", []):
        if isinstance(note, str) and "=" in note:
            key, value = note.split("=", 1)
            notes[key] = value
    return notes


def wait_for_health_notes(socket_path: Path, expected: dict[str, str], timeout: float) -> dict:
    deadline = time.time() + timeout
    last_seen = None
    while time.time() < deadline:
        health = wait_for_health(socket_path, min(timeout, 1.5))
        last_seen = health
        notes = note_map(health)
        if all(notes.get(key) == value for key, value in expected.items()):
            return health
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for health notes {expected}: {last_seen}")


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


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def terminate(processes: dict[str, subprocess.Popen]) -> dict[str, str]:
    for process in processes.values():
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    deadline = time.time() + 5
    for process in processes.values():
        if process.poll() is not None:
            continue
        remaining = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    logs: dict[str, str] = {}
    for name, process in processes.items():
        logs[name] = process.stdout.read() if process.stdout else ""
    return logs


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def build_runtime_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    runtime_profile = state_root / "rt.yaml"
    runtime_profile.write_text(
        textwrap.dedent(
            """\
            profile_id: startup-edge-runtime
            scope: system
            default_backend: local-gpu
            allowed_backends:
              - local-cpu
              - local-gpu
            local_model_pool:
              - smoke-model
            remote_model_pool: []
            embedding_backend: local-embedding
            rerank_backend: local-reranker
            cpu_fallback: true
            memory_budget_mb: 2048
            kv_cache_budget_mb: 512
            timeout_ms: 30000
            max_concurrency: 2
            max_parallel_models: 1
            offload_policy: manual-only
            degradation_policy: fallback-local-cpu
            observability_level: standard
            """
        )
    )
    route_profile = state_root / "route.yaml"
    shutil.copyfile(
        repo / "aios" / "runtime" / "profiles" / "default-route-profile.yaml",
        route_profile,
    )

    backend_script = state_root / "mock_runtime_backend.py"
    backend_script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import sys

            backend_id = sys.argv[1]
            request = json.loads(sys.stdin.read() or "{}")
            print(json.dumps({
                "route_state": "local-wrapper",
                "content": f"startup-edge wrapper response from {backend_id} for {request.get('task_id')}",
                "reason": "startup-edge mock backend",
                "estimated_latency_ms": request.get("estimated_latency_ms", 0),
            }))
            """
        )
    )
    backend_script.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "pd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "pd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(
                repo / "aios" / "policy" / "profiles" / "default-policy.yaml"
            ),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(
                repo / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"
            ),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "pd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "pd" / "token.key"),
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "rt"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "rt"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "rt" / "rt.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_LOCAL_CPU_COMMAND": f"python3 {backend_script} local-cpu",
            "AIOS_RUNTIMED_LOCAL_GPU_COMMAND": f"python3 {backend_script} local-gpu",
        }
    )
    return env


def build_device_metadata_env(
    root: Path,
    *,
    agentd_socket: Path,
    descriptor_path: Path,
) -> dict[str, str]:
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    pipewire_socket_path = state_root / "deviced" / "pipewire-0"
    input_root = state_root / "deviced" / "input"
    camera_root = state_root / "deviced" / "camera"
    screencast_state_path = state_root / "deviced" / "screencast-state.json"
    pipewire_node_path = state_root / "deviced" / "pipewire-node.json"

    pipewire_socket_path.parent.mkdir(parents=True, exist_ok=True)
    input_root.mkdir(parents=True, exist_ok=True)
    camera_root.mkdir(parents=True, exist_ok=True)
    pipewire_socket_path.write_text("ready\n")
    (input_root / "event0").write_text("keyboard\n")
    (input_root / "mouse0").write_text("mouse\n")
    (camera_root / "video0").write_text("ready\n")
    screencast_state_path.write_text(
        json.dumps(
            {
                "portal_session_ref": "startup-edge-portal-session",
                "stream_node_id": 42,
                "window_ref": "window-1",
                "resolution": "1280x720",
            }
        )
    )
    pipewire_node_path.write_text(
        json.dumps(
            {
                "node_id": 77,
                "channel_layout": "stereo",
            }
        )
    )

    env = os.environ.copy()
    env.update(
        {
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root / "deviced"),
            "AIOS_DEVICED_STATE_DIR": str(state_root / "deviced"),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced" / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "deviced" / "captures.json"),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(
                state_root / "deviced" / "indicator-state.json"
            ),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(
                state_root / "deviced" / "backend-state.json"
            ),
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_CAMERA_ENABLED": "1",
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
            "AIOS_DEVICE_METADATA_PROVIDER_RUNTIME_DIR": str(
                runtime_root / "device-metadata-provider"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_STATE_DIR": str(
                state_root / "device-metadata-provider"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_SOCKET_PATH": str(
                runtime_root
                / "device-metadata-provider"
                / "device-metadata-provider.sock"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_DEVICED_SOCKET": str(
                runtime_root / "deviced" / "deviced.sock"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_AGENTD_SOCKET": str(agentd_socket),
            "AIOS_DEVICE_METADATA_PROVIDER_DESCRIPTOR_PATH": str(descriptor_path),
            "AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "device-metadata-provider" / "observability.jsonl"
            ),
        }
    )
    return env


def build_system_files_env(
    root: Path,
    *,
    agentd_socket: Path,
    descriptor_path: Path,
) -> tuple[dict[str, str], Path]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    workspace = state_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    preview_file = workspace / "preview.txt"
    preview_file.write_text("hello from system-files startup edge\n")

    env = os.environ.copy()
    env.update(
        {
            "AIOS_SESSIOND_RUNTIME_DIR": str(runtime_root / "sd"),
            "AIOS_SESSIOND_STATE_DIR": str(state_root / "sd"),
            "AIOS_SESSIOND_SOCKET_PATH": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_SESSIOND_DATABASE": str(state_root / "sd" / "sd.sqlite3"),
            "AIOS_SESSIOND_PORTAL_STATE_DIR": str(state_root / "sd" / "portal"),
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "pd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "pd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(
                repo / "aios" / "policy" / "profiles" / "default-policy.yaml"
            ),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(
                repo / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"
            ),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "pd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "pd" / "token.key"),
            "AIOS_SYSTEM_FILES_PROVIDER_RUNTIME_DIR": str(runtime_root / "fs"),
            "AIOS_SYSTEM_FILES_PROVIDER_STATE_DIR": str(state_root / "fs"),
            "AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH": str(
                runtime_root / "fs" / "fs.sock"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_SESSIOND_SOCKET": str(
                runtime_root / "sd" / "sd.sock"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_POLICYD_SOCKET": str(
                runtime_root / "pd" / "pd.sock"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_AGENTD_SOCKET": str(agentd_socket),
            "AIOS_SYSTEM_FILES_PROVIDER_DESCRIPTOR_PATH": str(descriptor_path),
            "AIOS_SYSTEM_FILES_PROVIDER_AUDIT_LOG": str(
                state_root / "fs" / "audit.jsonl"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "fs" / "observability.jsonl"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_PREVIEW_BYTES": "4096",
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_DIRECTORY_ENTRIES": "32",
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_CONCURRENCY": "1",
            "AIOS_SYSTEM_FILES_PROVIDER_MAX_DELETE_AFFECTED_PATHS": "8",
            "AIOS_SYSTEM_FILES_PROVIDER_TEST_STARTUP_RESERVE_MS": "0",
        }
    )
    return env, preview_file


def run_system_intent_startup_edge(root: Path, binaries: dict[str, Path], timeout: float) -> dict:
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    fake_agentd_dir = runtime_root / "ag"
    fake_agentd_dir.mkdir(parents=True, exist_ok=True)
    missing_descriptor = state_root / "missing-system-intent.json"

    repo = repo_root()
    env = os.environ.copy()
    env.update(
        {
            "AIOS_SESSIOND_RUNTIME_DIR": str(runtime_root / "sd"),
            "AIOS_SESSIOND_STATE_DIR": str(state_root / "sd"),
            "AIOS_SESSIOND_SOCKET_PATH": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_SESSIOND_DATABASE": str(state_root / "sd" / "sessiond.sqlite3"),
            "AIOS_SESSIOND_PORTAL_STATE_DIR": str(state_root / "sd" / "portal"),
            "AIOS_POLICYD_RUNTIME_DIR": str(runtime_root / "pd"),
            "AIOS_POLICYD_STATE_DIR": str(state_root / "pd"),
            "AIOS_POLICYD_SOCKET_PATH": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_POLICYD_POLICY_PATH": str(
                repo / "aios" / "policy" / "profiles" / "default-policy.yaml"
            ),
            "AIOS_POLICYD_CAPABILITY_CATALOG_PATH": str(
                repo / "aios" / "policy" / "capabilities" / "default-capability-catalog.yaml"
            ),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "pd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "pd" / "token.key"),
            "AIOS_SYSTEM_INTENT_PROVIDER_RUNTIME_DIR": str(runtime_root / "si"),
            "AIOS_SYSTEM_INTENT_PROVIDER_STATE_DIR": str(state_root / "si"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH": str(runtime_root / "si" / "si.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SESSIOND_SOCKET": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_POLICYD_SOCKET": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_AGENTD_SOCKET": str(fake_agentd_dir / "agentd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_DESCRIPTOR_PATH": str(missing_descriptor),
            "AIOS_SYSTEM_INTENT_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "si" / "observability.jsonl"
            ),
            "AIOS_SYSTEM_INTENT_PROVIDER_MAX_CONCURRENCY": "1",
        }
    )

    processes = {
        "sessiond": launch(binaries["sessiond"], env),
        "policyd": launch(binaries["policyd"], env),
        "provider": launch(binaries["system_intent_provider"], env),
    }
    try:
        sockets = {
            "sessiond": Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            "policyd": Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            "provider": Path(env["AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH"]),
        }
        for socket_path in sockets.values():
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)
        provider_health = wait_for_health_notes(
            sockets["provider"],
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "descriptor-missing",
            },
            timeout,
        )
        provider_notes = note_map(provider_health)
        require(
            "registry_last_sync_failure" in provider_notes,
            "system intent provider health notes missing registry_last_sync_failure during startup-edge test",
        )
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_SYSTEM_INTENT_PROVIDER_OBSERVABILITY_LOG"],
            "system intent provider health missing observability log path",
        )
        observability_entries = wait_for_json_lines(
            Path(env["AIOS_SYSTEM_INTENT_PROVIDER_OBSERVABILITY_LOG"]),
            timeout,
            lambda entries: {
                entry.get("kind")
                for entry in entries
                if isinstance(entry, dict) and entry.get("kind")
            }
            >= {
                "provider.runtime.started",
                "provider.registry.descriptor-missing",
                "provider.registry.health-sync-failed",
            },
            "system intent startup-edge observability events",
        )

        intent = "Open /tmp/edge-report.md and summarize it locally"
        session_result = rpc_call(
            sockets["sessiond"],
            "session.create",
            {"user_id": "startup-edge-user", "metadata": {"initial_intent": intent}},
            timeout=timeout,
        )
        token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "startup-edge-user",
                "session_id": session_result["session"]["session_id"],
                "task_id": session_result["task"]["task_id"],
                "capability_id": "system.intent.execute",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=timeout,
        )
        response = rpc_call(
            sockets["provider"],
            "system.intent.execute",
            {"execution_token": token, "intent": intent},
            timeout=timeout,
        )

        require(
            response.get("provider_id") == "system.intent.local",
            "system intent provider did not serve requests without registry",
        )
        require(
            response.get("plan_source") == "provider-heuristic",
            "system intent provider did not fall back to heuristic planning during startup-edge test",
        )
        require(
            "provider.fs.open" in response.get("candidate_capabilities", []),
            "system intent startup-edge response lost provider.fs.open capability",
        )
        return {
            "provider_id": response.get("provider_id"),
            "plan_source": response.get("plan_source"),
            "candidate_capabilities": response.get("candidate_capabilities"),
            "registry_registration_state": provider_notes.get(
                "registry_registration_state"
            ),
            "observability_event_count": len(observability_entries),
        }
    finally:
        logs = terminate(processes)
        provider_log = logs.get("provider", "")
        require(
            "provider descriptor missing; skipping self-registration" in provider_log,
            "system intent provider log did not record missing descriptor startup path",
        )
        require(
            "failed to report provider health to agentd" in provider_log,
            "system intent provider log did not record unreachable registry startup path",
        )


def run_system_files_startup_edge(
    root: Path, binaries: dict[str, Path], timeout: float
) -> dict:
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    fake_agentd_dir = runtime_root / "ag"
    fake_agentd_dir.mkdir(parents=True, exist_ok=True)
    missing_descriptor = state_root / "missing-system-files.json"
    env, preview_file = build_system_files_env(
        root,
        agentd_socket=fake_agentd_dir / "agentd.sock",
        descriptor_path=missing_descriptor,
    )

    processes = {
        "sessiond": launch(binaries["sessiond"], env),
        "policyd": launch(binaries["policyd"], env),
        "provider": launch(binaries["system_files_provider"], env),
    }
    try:
        sockets = {
            "sessiond": Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            "policyd": Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            "provider": Path(env["AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH"]),
        }
        for socket_path in sockets.values():
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)

        provider_health = wait_for_health_notes(
            sockets["provider"],
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "descriptor-missing",
            },
            timeout,
        )
        provider_notes = note_map(provider_health)
        require(
            "registry_last_sync_failure" in provider_notes,
            "system-files provider health notes missing registry_last_sync_failure during startup-edge test",
        )
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG"],
            "system-files provider health missing observability log path",
        )
        observability_entries = wait_for_json_lines(
            Path(env["AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG"]),
            timeout,
            lambda entries: {
                entry.get("kind")
                for entry in entries
                if isinstance(entry, dict) and entry.get("kind")
            }
            >= {
                "provider.runtime.started",
                "provider.registry.descriptor-missing",
                "provider.registry.health-sync-failed",
            },
            "system-files startup-edge observability events",
        )

        session_result = rpc_call(
            sockets["sessiond"],
            "session.create",
            {"user_id": "startup-edge-fs-user", "metadata": {"source": "startup-edge"}},
            timeout=timeout,
        )
        session_id = session_result["session"]["session_id"]
        task_id = session_result["task"]["task_id"]
        file_handle = portal_issue(
            sockets["sessiond"],
            user_id="startup-edge-fs-user",
            session_id=session_id,
            kind="file_handle",
            target=preview_file,
            timeout=timeout,
        )
        token = issue_token(
            sockets["policyd"],
            user_id="startup-edge-fs-user",
            session_id=session_id,
            task_id=task_id,
            capability_id="provider.fs.open",
            target_hash=file_handle["scope"]["target_hash"],
            timeout=timeout,
        )
        response = rpc_call(
            sockets["provider"],
            "provider.fs.open",
            {
                "handle_id": file_handle["handle_id"],
                "execution_token": token,
                "include_content": True,
                "max_bytes": 128,
                "max_entries": 16,
            },
            timeout=timeout,
        )

        require(
            response.get("provider_id") == "system.files.local",
            "system-files provider did not serve requests without registry",
        )
        require(
            response.get("content_preview", "").startswith(
                "hello from system-files startup edge"
            ),
            "system-files startup-edge response lost file preview content",
        )
        require(
            response.get("target_hash") == file_handle["scope"]["target_hash"],
            "system-files startup-edge response lost target hash binding",
        )
        return {
            "provider_id": response.get("provider_id"),
            "object_kind": response.get("object_kind"),
            "registry_registration_state": provider_notes.get(
                "registry_registration_state"
            ),
            "observability_event_count": len(observability_entries),
        }
    finally:
        logs = terminate(processes)
        provider_log = logs.get("provider", "")
        require(
            "provider descriptor missing; skipping self-registration" in provider_log,
            "system-files provider log did not record missing descriptor startup path",
        )
        require(
            "failed to report provider health to agentd" in provider_log,
            "system-files provider log did not record unreachable registry startup path",
        )


def run_device_metadata_startup_edge(
    root: Path, binaries: dict[str, Path], timeout: float
) -> dict:
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    fake_agentd_dir = runtime_root / "ag"
    fake_agentd_dir.mkdir(parents=True, exist_ok=True)
    missing_descriptor = state_root / "missing-device-metadata.json"
    env = build_device_metadata_env(
        root,
        agentd_socket=fake_agentd_dir / "agentd.sock",
        descriptor_path=missing_descriptor,
    )

    processes = {
        "deviced": launch(binaries["deviced"], env),
        "provider": launch(binaries["device_metadata_provider"], env),
    }
    try:
        sockets = {
            "deviced": Path(env["AIOS_DEVICED_SOCKET_PATH"]),
            "provider": Path(env["AIOS_DEVICE_METADATA_PROVIDER_SOCKET_PATH"]),
        }
        for socket_path in sockets.values():
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)
        provider_health = wait_for_health_notes(
            sockets["provider"],
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "descriptor-missing",
                "deviced_status": "available",
            },
            timeout,
        )
        provider_notes = note_map(provider_health)
        require(
            provider_health.get("status") == "ready",
            "device metadata provider should remain ready during startup-edge test",
        )
        require(
            "registry_last_sync_failure" in provider_notes,
            "device metadata provider health notes missing registry_last_sync_failure during startup-edge test",
        )
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG"],
            "device metadata provider health missing observability log path",
        )
        observability_entries = wait_for_json_lines(
            Path(env["AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG"]),
            timeout,
            lambda entries: {
                entry.get("kind")
                for entry in entries
                if isinstance(entry, dict) and entry.get("kind")
            }
            >= {
                "provider.runtime.started",
                "provider.registry.descriptor-missing",
                "provider.registry.health-sync-failed",
            },
            "device metadata startup-edge observability events",
        )

        metadata = rpc_call(
            sockets["provider"],
            "device.metadata.get",
            {
                "modalities": ["screen", "audio", "input", "camera"],
                "only_available": True,
                "include_state_notes": True,
            },
            timeout=timeout,
        )
        require(
            metadata.get("provider_id") == "device.metadata.local",
            "device metadata provider did not serve requests without registry",
        )
        require(
            metadata.get("device_service_id") == "aios-deviced",
            "device metadata startup-edge response lost device_service_id",
        )
        require(
            metadata.get("summary", {}).get("overall_status") == "ready",
            "device metadata provider did not preserve readiness during startup-edge test",
        )
        entries = {entry["modality"]: entry for entry in metadata.get("entries", [])}
        require(
            set(entries) == {"screen", "audio", "input", "camera"},
            f"unexpected device metadata modalities during startup-edge test: {sorted(entries)}",
        )
        require(
            entries["screen"].get("adapter_id") == "screen.portal-native",
            "device metadata startup-edge screen adapter mismatch",
        )
        require(
            entries["audio"].get("adapter_id") == "audio.pipewire-native",
            "device metadata startup-edge audio adapter mismatch",
        )
        require(
            entries["input"].get("adapter_id") == "input.libinput-native",
            "device metadata startup-edge input adapter mismatch",
        )
        require(
            entries["camera"].get("adapter_id") == "camera.v4l-native",
            "device metadata startup-edge camera adapter mismatch",
        )
        require(
            "approval_mode=metadata-only" in metadata.get("notes", []),
            "device metadata startup-edge response missing state notes",
        )
        return {
            "provider_id": metadata.get("provider_id"),
            "overall_status": metadata.get("summary", {}).get("overall_status"),
            "modalities": sorted(entries),
            "registry_registration_state": provider_notes.get(
                "registry_registration_state"
            ),
            "observability_event_count": len(observability_entries),
        }
    finally:
        logs = terminate(processes)
        provider_log = logs.get("provider", "")
        require(
            "provider descriptor missing; skipping self-registration" in provider_log,
            "device metadata provider log did not record missing descriptor startup path",
        )
        require(
            "failed to report provider health to agentd" in provider_log,
            "device metadata provider log did not record unreachable registry startup path",
        )


def run_runtime_local_inference_startup_edge(
    root: Path, binaries: dict[str, Path], timeout: float
) -> dict:
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    fake_agentd_dir = runtime_root / "ag"
    fake_agentd_dir.mkdir(parents=True, exist_ok=True)
    missing_descriptor = state_root / "missing-runtime-local-inference.json"

    env = build_runtime_env(root)
    env.update(
        {
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_RUNTIME_DIR": str(runtime_root / "rli"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_STATE_DIR": str(state_root / "rli"),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_SOCKET_PATH": str(
                runtime_root / "rli" / "rli.sock"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_RUNTIMED_SOCKET": str(
                runtime_root / "rt" / "rt.sock"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_POLICYD_SOCKET": str(
                runtime_root / "pd" / "pd.sock"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_AGENTD_SOCKET": str(
                fake_agentd_dir / "agentd.sock"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_DESCRIPTOR_PATH": str(
                missing_descriptor
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "rli" / "observability.jsonl"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_MAX_CONCURRENCY": "1",
        }
    )

    processes = {
        "policyd": launch(binaries["policyd"], env),
        "runtimed": launch(binaries["runtimed"], env),
        "provider": launch(binaries["runtime_local_inference_provider"], env),
    }
    try:
        sockets = {
            "policyd": Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            "runtimed": Path(env["AIOS_RUNTIMED_SOCKET_PATH"]),
            "provider": Path(env["AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_SOCKET_PATH"]),
        }
        for socket_path in sockets.values():
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)
        provider_health = wait_for_health_notes(
            sockets["provider"],
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "descriptor-missing",
            },
            timeout,
        )
        provider_notes = note_map(provider_health)
        require(
            "registry_last_sync_failure" in provider_notes,
            "runtime local inference provider health notes missing registry_last_sync_failure during startup-edge test",
        )
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG"],
            "runtime local inference provider health missing observability log path",
        )
        observability_entries = wait_for_json_lines(
            Path(env["AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG"]),
            timeout,
            lambda entries: {
                entry.get("kind")
                for entry in entries
                if isinstance(entry, dict) and entry.get("kind")
            }
            >= {
                "provider.runtime.started",
                "provider.registry.descriptor-missing",
                "provider.registry.health-sync-failed",
            },
            "runtime local inference startup-edge observability events",
        )

        token = rpc_call(
            sockets["policyd"],
            "policy.token.issue",
            {
                "user_id": "startup-edge-runtime-user",
                "session_id": "startup-edge-runtime-session",
                "task_id": "startup-edge-runtime-task",
                "capability_id": "runtime.infer.submit",
                "execution_location": "local",
                "constraints": {},
            },
            timeout=timeout,
        )
        response = rpc_call(
            sockets["provider"],
            "runtime.infer.submit",
            {
                "session_id": "startup-edge-runtime-session",
                "task_id": "startup-edge-runtime-task",
                "prompt": "Summarize startup edge runtime provider behavior",
                "model": "smoke-model",
                "preferred_backend": "local-gpu",
                "execution_token": token,
            },
            timeout=timeout,
        )

        require(
            response.get("provider_id") == "runtime.local.inference",
            "runtime local inference provider did not serve requests without registry",
        )
        require(
            response.get("backend_id") == "local-gpu",
            "runtime local inference provider did not preserve preferred backend during startup-edge test",
        )
        require(
            response.get("provider_status") == "available",
            "runtime local inference provider did not remain available without registry",
        )
        return {
            "provider_id": response.get("provider_id"),
            "backend_id": response.get("backend_id"),
            "provider_status": response.get("provider_status"),
            "route_state": response.get("route_state"),
            "registry_registration_state": provider_notes.get(
                "registry_registration_state"
            ),
            "observability_event_count": len(observability_entries),
        }
    finally:
        logs = terminate(processes)
        provider_log = logs.get("provider", "")
        require(
            "provider descriptor missing; skipping self-registration" in provider_log,
            "runtime local inference provider log did not record missing descriptor startup path",
        )
        require(
            "failed to report provider health to agentd" in provider_log,
            "runtime local inference provider log did not record unreachable registry startup path",
        )


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("provider startup-edge smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "sessiond": resolve_binary("sessiond", args.sessiond, args.bin_dir),
        "policyd": resolve_binary("policyd", args.policyd, args.bin_dir),
        "runtimed": resolve_binary("runtimed", args.runtimed, args.bin_dir),
        "deviced": resolve_binary("deviced", args.deviced, args.bin_dir),
        "system_files_provider": resolve_binary(
            "system-files-provider", args.system_files_provider, args.bin_dir
        ),
        "system_intent_provider": resolve_binary(
            "system-intent-provider", args.system_intent_provider, args.bin_dir
        ),
        "device_metadata_provider": resolve_binary(
            "device-metadata-provider",
            args.device_metadata_provider,
            args.bin_dir,
        ),
        "runtime_local_inference_provider": resolve_binary(
            "runtime-local-inference-provider",
            args.runtime_local_inference_provider,
            args.bin_dir,
        ),
    }
    ensure_binaries(binaries)

    temp_root = Path(
        tempfile.mkdtemp(prefix="aios-prov-edge-", dir="/tmp" if Path("/tmp").exists() else None)
    )
    failed = False
    try:
        system_files = run_system_files_startup_edge(
            temp_root / "fs", binaries, args.timeout
        )
        system_intent = run_system_intent_startup_edge(
            temp_root / "si", binaries, args.timeout
        )
        device_metadata = run_device_metadata_startup_edge(
            temp_root / "dm", binaries, args.timeout
        )
        runtime_local_inference = run_runtime_local_inference_startup_edge(
            temp_root / "rli", binaries, args.timeout
        )
        print(
            json.dumps(
                {
                    "system_files": system_files,
                    "system_intent": system_intent,
                    "device_metadata": device_metadata,
                    "runtime_local_inference": runtime_local_inference,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"provider startup-edge smoke failed: {exc}")
        return 1
    finally:
        if args.keep_state or failed:
            print(f"Preserved provider startup-edge smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
