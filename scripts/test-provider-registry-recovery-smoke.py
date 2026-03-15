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

from aios_cargo_bins import default_aios_bin_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOS provider registry recovery smoke harness"
    )
    parser.add_argument("--bin-dir", type=Path, help="Directory containing required binaries")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
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
        help="Seconds to wait for sockets and registry convergence",
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
        return explicit
    if bin_dir is not None:
        return bin_dir / name
    return default_aios_bin_dir(repo_root()) / name


def ensure_binaries(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing binaries for provider registry recovery smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print(
            "Build them first, for example: cargo build -p aios-agentd -p aios-sessiond -p aios-policyd -p aios-runtimed -p aios-deviced -p aios-system-files-provider -p aios-system-intent-provider -p aios-device-metadata-provider -p aios-runtime-local-inference-provider"
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
            "scope": {"source": "provider-registry-recovery-smoke"},
            "expiry_seconds": 300,
            "revocable": True,
            "audit_tags": ["provider-registry-recovery-smoke", kind],
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


def wait_for_provider_health(
    socket_path: Path, provider_id: str, expected_status: str, timeout: float
) -> dict:
    deadline = time.time() + timeout
    last_seen = None
    while time.time() < deadline:
        result = rpc_call(
            socket_path,
            "provider.health.get",
            {"provider_id": provider_id},
            timeout=min(timeout, 1.5),
        )
        providers = result.get("providers", [])
        if providers:
            last_seen = providers[0]
            if (
                providers[0].get("status") == expected_status
                and providers[0].get("last_checked_at")
            ):
                return providers[0]
        time.sleep(0.1)
    raise TimeoutError(
        f"Timed out waiting for provider health={expected_status}: {last_seen}"
    )


def wait_for_resolution(
    socket_path: Path,
    capability_id: str,
    expected_provider_id: str,
    timeout: float,
) -> dict:
    deadline = time.time() + timeout
    last_seen = None
    while time.time() < deadline:
        result = rpc_call(
            socket_path,
            "provider.resolve_capability",
            {
                "capability_id": capability_id,
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=min(timeout, 1.5),
        )
        last_seen = result
        selected = result.get("selected") or {}
        if selected.get("provider_id") == expected_provider_id:
            return result
        time.sleep(0.1)
    raise TimeoutError(
        f"Timed out waiting for capability {capability_id} to resolve to {expected_provider_id}: {last_seen}"
    )


def wait_for_file(path: Path, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for file: {path}")


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


def print_logs(logs: dict[str, str]) -> None:
    for name, output in logs.items():
        if output.strip():
            print(f"\n--- {name} log ---")
            print(output.rstrip())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def system_intent_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    empty_provider_dir = state_root / "empty-providers"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    empty_provider_dir.mkdir(parents=True, exist_ok=True)
    (runtime_root / "ag").mkdir(parents=True, exist_ok=True)

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
                repo
                / "aios"
                / "policy"
                / "capabilities"
                / "default-capability-catalog.yaml"
            ),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "pd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "pd" / "token.key"),
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "ag"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "ag"),
            "AIOS_AGENTD_SOCKET_PATH": str(runtime_root / "ag" / "ag.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "rt" / "rt.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "rg"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": str(empty_provider_dir),
            "AIOS_SYSTEM_INTENT_PROVIDER_RUNTIME_DIR": str(runtime_root / "si"),
            "AIOS_SYSTEM_INTENT_PROVIDER_STATE_DIR": str(state_root / "si"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH": str(runtime_root / "si" / "si.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_SESSIOND_SOCKET": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_POLICYD_SOCKET": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_AGENTD_SOCKET": str(runtime_root / "ag" / "ag.sock"),
            "AIOS_SYSTEM_INTENT_PROVIDER_DESCRIPTOR_PATH": str(
                repo / "aios" / "sdk" / "providers" / "system-intent.local.json"
            ),
            "AIOS_SYSTEM_INTENT_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "si" / "observability.jsonl"
            ),
            "AIOS_SYSTEM_INTENT_PROVIDER_MAX_CONCURRENCY": "1",
        }
    )
    return env


def runtime_local_inference_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    empty_provider_dir = state_root / "empty-providers"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    empty_provider_dir.mkdir(parents=True, exist_ok=True)
    (runtime_root / "ag").mkdir(parents=True, exist_ok=True)

    runtime_profile = state_root / "rt.yaml"
    runtime_profile.write_text(
        textwrap.dedent(
            """\
            profile_id: registry-recovery-runtime
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
                "content": f"registry recovery response from {backend_id} for {request.get('task_id')}",
                "reason": "registry recovery mock backend",
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
                repo
                / "aios"
                / "policy"
                / "capabilities"
                / "default-capability-catalog.yaml"
            ),
            "AIOS_POLICYD_AUDIT_LOG": str(state_root / "pd" / "audit.jsonl"),
            "AIOS_POLICYD_TOKEN_KEY_PATH": str(state_root / "pd" / "token.key"),
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "ag"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "ag"),
            "AIOS_AGENTD_SOCKET_PATH": str(runtime_root / "ag" / "ag.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "rt" / "rt.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "rg"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": str(empty_provider_dir),
            "AIOS_RUNTIMED_RUNTIME_DIR": str(runtime_root / "rt"),
            "AIOS_RUNTIMED_STATE_DIR": str(state_root / "rt"),
            "AIOS_RUNTIMED_SOCKET_PATH": str(runtime_root / "rt" / "rt.sock"),
            "AIOS_RUNTIMED_RUNTIME_PROFILE": str(runtime_profile),
            "AIOS_RUNTIMED_ROUTE_PROFILE": str(route_profile),
            "AIOS_RUNTIMED_LOCAL_CPU_COMMAND": f"python3 {backend_script} local-cpu",
            "AIOS_RUNTIMED_LOCAL_GPU_COMMAND": f"python3 {backend_script} local-gpu",
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
                runtime_root / "ag" / "ag.sock"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_DESCRIPTOR_PATH": str(
                repo
                / "aios"
                / "runtime"
                / "providers"
                / "runtime.local-inference.json"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "rli" / "observability.jsonl"
            ),
            "AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_MAX_CONCURRENCY": "1",
        }
    )
    return env


def system_files_env(root: Path) -> tuple[dict[str, str], Path]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    empty_provider_dir = state_root / "empty-providers"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    empty_provider_dir.mkdir(parents=True, exist_ok=True)
    (runtime_root / "ag").mkdir(parents=True, exist_ok=True)

    workspace = state_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    preview_file = workspace / "preview.txt"
    preview_file.write_text("hello from system-files registry recovery\n")

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
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "ag"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "ag"),
            "AIOS_AGENTD_SOCKET_PATH": str(runtime_root / "ag" / "ag.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "rt" / "rt.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "rg"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": str(empty_provider_dir),
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
            "AIOS_SYSTEM_FILES_PROVIDER_AGENTD_SOCKET": str(
                runtime_root / "ag" / "ag.sock"
            ),
            "AIOS_SYSTEM_FILES_PROVIDER_DESCRIPTOR_PATH": str(
                repo / "aios" / "sdk" / "providers" / "system-files.local.json"
            ),
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


def device_metadata_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    empty_provider_dir = state_root / "empty-providers"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    empty_provider_dir.mkdir(parents=True, exist_ok=True)
    (runtime_root / "ag").mkdir(parents=True, exist_ok=True)

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
                "portal_session_ref": "registry-recovery-portal-session",
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
            "AIOS_AGENTD_RUNTIME_DIR": str(runtime_root / "ag"),
            "AIOS_AGENTD_STATE_DIR": str(state_root / "ag"),
            "AIOS_AGENTD_SOCKET_PATH": str(runtime_root / "ag" / "ag.sock"),
            "AIOS_AGENTD_SESSIOND_SOCKET": str(runtime_root / "sd" / "sd.sock"),
            "AIOS_AGENTD_POLICYD_SOCKET": str(runtime_root / "pd" / "pd.sock"),
            "AIOS_AGENTD_RUNTIMED_SOCKET": str(runtime_root / "rt" / "rt.sock"),
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR": str(state_root / "rg"),
            "AIOS_AGENTD_PROVIDER_DESCRIPTOR_DIRS": str(empty_provider_dir),
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
            "AIOS_DEVICE_METADATA_PROVIDER_AGENTD_SOCKET": str(
                runtime_root / "ag" / "ag.sock"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_DESCRIPTOR_PATH": str(
                repo / "aios" / "sdk" / "providers" / "device.metadata.local.json"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "device-metadata-provider" / "observability.jsonl"
            ),
        }
    )
    return env


def run_system_intent_registry_recovery(
    root: Path, binaries: dict[str, Path], timeout: float
) -> dict:
    env = system_intent_env(root)
    processes = {
        "sessiond": launch(binaries["sessiond"], env),
        "policyd": launch(binaries["policyd"], env),
        "provider": launch(binaries["system_intent_provider"], env),
    }

    try:
        provider_socket = Path(env["AIOS_SYSTEM_INTENT_PROVIDER_SOCKET_PATH"])
        for socket_path in [
            Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            provider_socket,
        ]:
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)

        processes["agentd"] = launch(binaries["agentd"], env)
        agentd_socket = Path(env["AIOS_AGENTD_SOCKET_PATH"])
        wait_for_socket(agentd_socket, timeout)
        wait_for_health(agentd_socket, timeout)

        provider_id = "system.intent.local"
        descriptor_path = (
            Path(env["AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR"])
            / "descriptors"
            / f"{provider_id}.json"
        )
        wait_for_file(descriptor_path, timeout)
        provider_health = wait_for_provider_health(
            agentd_socket, provider_id, "available", timeout
        )
        provider_system_health = wait_for_health_notes(
            provider_socket,
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "recovered",
                "registry_last_reported_status": "available",
            },
            timeout,
        )
        provider_notes = note_map(provider_system_health)
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_SYSTEM_INTENT_PROVIDER_OBSERVABILITY_LOG"],
            "system intent recovery health missing observability log path",
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
                "provider.registry.registration-failed",
                "provider.registry.recovered",
            }
            and any(entry.get("overall_status") == "ready" for entry in entries),
            "system intent recovery observability convergence",
        )
        resolution = wait_for_resolution(
            agentd_socket,
            "system.intent.execute",
            provider_id,
            timeout,
        )

        require(
            provider_health.get("last_error") is None,
            "system intent registry recovery left a stale last_error",
        )
        return {
            "provider_id": provider_id,
            "descriptor_path": str(descriptor_path),
            "health_status": provider_health.get("status"),
            "resolved_provider_id": (resolution.get("selected") or {}).get("provider_id"),
            "registry_registration_state": provider_notes.get("registry_registration_state"),
            "observability_event_count": len(observability_entries),
        }
    finally:
        print_logs(terminate(processes))


def run_system_files_registry_recovery(
    root: Path, binaries: dict[str, Path], timeout: float
) -> dict:
    env, preview_file = system_files_env(root)
    processes = {
        "sessiond": launch(binaries["sessiond"], env),
        "policyd": launch(binaries["policyd"], env),
        "provider": launch(binaries["system_files_provider"], env),
    }

    try:
        provider_socket = Path(env["AIOS_SYSTEM_FILES_PROVIDER_SOCKET_PATH"])
        for socket_path in [
            Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            provider_socket,
        ]:
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)

        processes["agentd"] = launch(binaries["agentd"], env)
        agentd_socket = Path(env["AIOS_AGENTD_SOCKET_PATH"])
        wait_for_socket(agentd_socket, timeout)
        wait_for_health(agentd_socket, timeout)

        provider_id = "system.files.local"
        descriptor_path = (
            Path(env["AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR"])
            / "descriptors"
            / f"{provider_id}.json"
        )
        wait_for_file(descriptor_path, timeout)
        provider_health = wait_for_provider_health(
            agentd_socket, provider_id, "available", timeout
        )
        provider_system_health = wait_for_health_notes(
            provider_socket,
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "recovered",
                "registry_last_reported_status": "available",
            },
            timeout,
        )
        provider_notes = note_map(provider_system_health)
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_SYSTEM_FILES_PROVIDER_OBSERVABILITY_LOG"],
            "system-files recovery health missing observability log path",
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
                "provider.registry.registration-failed",
                "provider.registry.recovered",
            }
            and any(entry.get("overall_status") == "ready" for entry in entries),
            "system-files recovery observability convergence",
        )
        resolution = wait_for_resolution(
            agentd_socket,
            "provider.fs.open",
            provider_id,
            timeout,
        )

        session_result = rpc_call(
            Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            "session.create",
            {
                "user_id": "registry-recovery-fs-user",
                "metadata": {"source": "registry-recovery"},
            },
            timeout=timeout,
        )
        session_id = session_result["session"]["session_id"]
        task_id = session_result["task"]["task_id"]
        file_handle = portal_issue(
            Path(env["AIOS_SESSIOND_SOCKET_PATH"]),
            user_id="registry-recovery-fs-user",
            session_id=session_id,
            kind="file_handle",
            target=preview_file,
            timeout=timeout,
        )
        token = issue_token(
            Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            user_id="registry-recovery-fs-user",
            session_id=session_id,
            task_id=task_id,
            capability_id="provider.fs.open",
            target_hash=file_handle["scope"]["target_hash"],
            timeout=timeout,
        )
        open_result = rpc_call(
            provider_socket,
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
            provider_health.get("last_error") is None,
            "system-files registry recovery left a stale last_error",
        )
        require(
            open_result.get("provider_id") == provider_id,
            "system-files provider did not serve requests after registry recovery",
        )
        return {
            "provider_id": provider_id,
            "descriptor_path": str(descriptor_path),
            "health_status": provider_health.get("status"),
            "resolved_provider_id": (resolution.get("selected") or {}).get("provider_id"),
            "object_kind": open_result.get("object_kind"),
            "registry_registration_state": provider_notes.get(
                "registry_registration_state"
            ),
            "observability_event_count": len(observability_entries),
        }
    finally:
        print_logs(terminate(processes))


def run_device_metadata_registry_recovery(
    root: Path, binaries: dict[str, Path], timeout: float
) -> dict:
    env = device_metadata_env(root)
    processes = {
        "deviced": launch(binaries["deviced"], env),
        "provider": launch(binaries["device_metadata_provider"], env),
    }

    try:
        provider_socket = Path(env["AIOS_DEVICE_METADATA_PROVIDER_SOCKET_PATH"])
        for socket_path in [
            Path(env["AIOS_DEVICED_SOCKET_PATH"]),
            provider_socket,
        ]:
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)

        processes["agentd"] = launch(binaries["agentd"], env)
        agentd_socket = Path(env["AIOS_AGENTD_SOCKET_PATH"])
        wait_for_socket(agentd_socket, timeout)
        wait_for_health(agentd_socket, timeout)

        provider_id = "device.metadata.local"
        descriptor_path = (
            Path(env["AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR"])
            / "descriptors"
            / f"{provider_id}.json"
        )
        wait_for_file(descriptor_path, timeout)
        provider_health = wait_for_provider_health(
            agentd_socket, provider_id, "available", timeout
        )
        provider_system_health = wait_for_health_notes(
            provider_socket,
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "recovered",
                "registry_last_reported_status": "available",
                "deviced_status": "available",
            },
            timeout,
        )
        provider_notes = note_map(provider_system_health)
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG"],
            "device metadata recovery health missing observability log path",
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
                "provider.registry.registration-failed",
                "provider.registry.recovered",
            }
            and any(entry.get("overall_status") == "ready" for entry in entries),
            "device metadata recovery observability convergence",
        )
        resolution = wait_for_resolution(
            agentd_socket,
            "device.metadata.get",
            provider_id,
            timeout,
        )
        metadata = rpc_call(
            provider_socket,
            "device.metadata.get",
            {
                "modalities": ["screen", "audio", "input", "camera"],
                "only_available": True,
                "include_state_notes": False,
            },
            timeout=timeout,
        )

        require(
            provider_health.get("last_error") is None,
            "device metadata registry recovery left a stale last_error",
        )
        require(
            metadata.get("summary", {}).get("overall_status") == "ready",
            "device metadata provider did not preserve readiness after registry recovery",
        )
        return {
            "provider_id": provider_id,
            "descriptor_path": str(descriptor_path),
            "health_status": provider_health.get("status"),
            "resolved_provider_id": (resolution.get("selected") or {}).get("provider_id"),
            "overall_status": metadata.get("summary", {}).get("overall_status"),
            "registry_registration_state": provider_notes.get(
                "registry_registration_state"
            ),
            "observability_event_count": len(observability_entries),
        }
    finally:
        print_logs(terminate(processes))


def run_runtime_local_inference_registry_recovery(
    root: Path, binaries: dict[str, Path], timeout: float
) -> dict:
    env = runtime_local_inference_env(root)
    processes = {
        "policyd": launch(binaries["policyd"], env),
        "runtimed": launch(binaries["runtimed"], env),
        "provider": launch(binaries["runtime_local_inference_provider"], env),
    }

    try:
        provider_socket = Path(env["AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_SOCKET_PATH"])
        for socket_path in [
            Path(env["AIOS_POLICYD_SOCKET_PATH"]),
            Path(env["AIOS_RUNTIMED_SOCKET_PATH"]),
            provider_socket,
        ]:
            wait_for_socket(socket_path, timeout)
            wait_for_health(socket_path, timeout)

        processes["agentd"] = launch(binaries["agentd"], env)
        agentd_socket = Path(env["AIOS_AGENTD_SOCKET_PATH"])
        wait_for_socket(agentd_socket, timeout)
        wait_for_health(agentd_socket, timeout)

        provider_id = "runtime.local.inference"
        descriptor_path = (
            Path(env["AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR"])
            / "descriptors"
            / f"{provider_id}.json"
        )
        wait_for_file(descriptor_path, timeout)
        provider_health = wait_for_provider_health(
            agentd_socket, provider_id, "available", timeout
        )
        provider_system_health = wait_for_health_notes(
            provider_socket,
            {
                "registry_sync_enabled": "true",
                "registry_registration_state": "recovered",
                "registry_last_reported_status": "available",
            },
            timeout,
        )
        provider_notes = note_map(provider_system_health)
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_RUNTIME_LOCAL_INFERENCE_PROVIDER_OBSERVABILITY_LOG"],
            "runtime local inference recovery health missing observability log path",
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
                "provider.registry.registration-failed",
                "provider.registry.recovered",
            }
            and any(entry.get("overall_status") == "ready" for entry in entries),
            "runtime local inference recovery observability convergence",
        )
        resolution = wait_for_resolution(
            agentd_socket,
            "runtime.infer.submit",
            provider_id,
            timeout,
        )

        require(
            provider_health.get("last_error") is None,
            "runtime local inference registry recovery left a stale last_error",
        )
        return {
            "provider_id": provider_id,
            "descriptor_path": str(descriptor_path),
            "health_status": provider_health.get("status"),
            "resolved_provider_id": (resolution.get("selected") or {}).get("provider_id"),
            "registry_registration_state": provider_notes.get("registry_registration_state"),
            "observability_event_count": len(observability_entries),
        }
    finally:
        print_logs(terminate(processes))


def main() -> int:
    args = parse_args()
    binaries = {
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
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
        tempfile.mkdtemp(
            prefix="aios-prov-registry-recovery-",
            dir="/tmp" if Path("/tmp").exists() else None,
        )
    )
    failed = False
    try:
        system_files = run_system_files_registry_recovery(
            temp_root / "fs", binaries, args.timeout
        )
        system_intent = run_system_intent_registry_recovery(
            temp_root / "si", binaries, args.timeout
        )
        device_metadata = run_device_metadata_registry_recovery(
            temp_root / "dm", binaries, args.timeout
        )
        runtime_local_inference = run_runtime_local_inference_registry_recovery(
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
        print(f"provider registry recovery smoke failed: {exc}")
        return 1
    finally:
        if args.keep_state or failed:
            print(f"Preserved provider registry recovery smoke state at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
