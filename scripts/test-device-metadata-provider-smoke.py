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
    parser = argparse.ArgumentParser(description="AIOS device metadata provider smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing agentd/deviced/device-metadata-provider binaries")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
    parser.add_argument("--deviced", type=Path, help="Path to deviced binary")
    parser.add_argument("--provider", type=Path, help="Path to device-metadata-provider binary")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for sockets and RPC calls")
    parser.add_argument("--keep-state", action="store_true", help="Keep temp runtime/state directory on success")
    return parser.parse_args()


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent



def resolve_binary(name: str, explicit: Path | None, bin_dir: Path | None) -> Path:
    if explicit is not None:
        return resolve_binary_path(explicit.parent, explicit.name)
    if bin_dir is not None:
        return resolve_binary_path(bin_dir, name)
    return resolve_binary_path(default_aios_bin_dir(repo_root()), name)


def ensure_binaries(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing binaries for device metadata provider smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print("Build them first, for example: cargo build -p aios-agentd -p aios-deviced -p aios-device-metadata-provider")
        raise SystemExit(2)


def rpc_response(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
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


def rpc_expect_error(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_response(socket_path, method, params, timeout)
    error = response.get("error")
    if not error:
        raise RuntimeError(f"RPC {method} unexpectedly succeeded: {response}")
    return error


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


def wait_for_provider_health(socket_path: Path, provider_id: str, expected_status: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_seen = None
    while time.time() < deadline:
        health = rpc_call(
            socket_path,
            "agent.provider.health.get",
            {"provider_id": provider_id},
            timeout=min(timeout, 1.5),
        )
        providers = health.get("providers", [])
        if providers:
            last_seen = providers[0]
            if providers[0].get("status") == expected_status:
                return providers[0]
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for provider health={expected_status}: {last_seen}")


def launch(binary: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )



def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        process.send_signal(signal.SIGINT)

def terminate(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        stop_process(process)
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


def make_env(root: Path) -> dict[str, str]:
    repo = repo_root()
    runtime_root = root / "run"
    state_root = root / "state"
    runtime_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    sdk_provider_override = root / "provider-descriptors" / "sdk"
    sdk_provider_override.mkdir(parents=True, exist_ok=True)
    for descriptor in (repo / "aios" / "sdk" / "providers").glob("*.json"):
        if descriptor.name == "device.metadata.local.json":
            continue
        shutil.copy2(descriptor, sdk_provider_override / descriptor.name)

    provider_dirs = [
        sdk_provider_override,
        repo / "aios" / "runtime" / "providers",
        repo / "aios" / "shell" / "providers",
        repo / "aios" / "compat" / "browser" / "providers",
        repo / "aios" / "compat" / "office" / "providers",
        repo / "aios" / "compat" / "mcp-bridge" / "providers",
        repo / "aios" / "compat" / "code-sandbox" / "providers",
    ]

    pipewire_socket_path = state_root / "deviced" / "pipewire-0"
    input_root = state_root / "deviced" / "input"
    camera_root = state_root / "deviced" / "camera"
    screencast_state_path = state_root / "deviced" / "screencast-state.json"
    pipewire_node_path = state_root / "deviced" / "pipewire-node.json"
    ui_tree_state_path = state_root / "deviced" / "ui-tree-state.json"

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
                "portal_session_ref": "session-portal-1",
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
    ui_tree_state_path.write_text(
        json.dumps(
            {
                "snapshot_id": "tree-state-1",
                "focus_node": "screen-1",
                "capture_mode": "native-state-bridge",
            }
        )
    )

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
            "AIOS_DEVICED_RUNTIME_DIR": str(runtime_root / "deviced"),
            "AIOS_DEVICED_STATE_DIR": str(state_root / "deviced"),
            "AIOS_DEVICED_SOCKET_PATH": str(runtime_root / "deviced" / "deviced.sock"),
            "AIOS_DEVICED_CAPTURE_STATE_PATH": str(state_root / "deviced" / "captures.json"),
            "AIOS_DEVICED_INDICATOR_STATE_PATH": str(state_root / "deviced" / "indicator-state.json"),
            "AIOS_DEVICED_BACKEND_STATE_PATH": str(state_root / "deviced" / "backend-state.json"),
            "AIOS_DEVICED_PIPEWIRE_SOCKET_PATH": str(pipewire_socket_path),
            "AIOS_DEVICED_INPUT_DEVICE_ROOT": str(input_root),
            "AIOS_DEVICED_CAMERA_DEVICE_ROOT": str(camera_root),
            "AIOS_DEVICED_CAMERA_ENABLED": "1",
            "AIOS_DEVICED_UI_TREE_SUPPORTED": "1",
            "AIOS_DEVICED_SCREENCAST_STATE_PATH": str(screencast_state_path),
            "AIOS_DEVICED_PIPEWIRE_NODE_PATH": str(pipewire_node_path),
            "AIOS_DEVICED_UI_TREE_STATE_PATH": str(ui_tree_state_path),
            "AIOS_DEVICED_APPROVAL_MODE": "metadata-only",
            "AIOS_DEVICE_METADATA_PROVIDER_RUNTIME_DIR": str(runtime_root / "device-metadata-provider"),
            "AIOS_DEVICE_METADATA_PROVIDER_STATE_DIR": str(state_root / "device-metadata-provider"),
            "AIOS_DEVICE_METADATA_PROVIDER_SOCKET_PATH": str(
                runtime_root / "device-metadata-provider" / "device-metadata-provider.sock"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_DEVICED_SOCKET": str(runtime_root / "deviced" / "deviced.sock"),
            "AIOS_DEVICE_METADATA_PROVIDER_AGENTD_SOCKET": str(runtime_root / "agentd" / "agentd.sock"),
            "AIOS_DEVICE_METADATA_PROVIDER_DESCRIPTOR_PATH": str(
                repo / "aios" / "sdk" / "providers" / "device.metadata.local.json"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG": str(
                state_root / "device-metadata-provider" / "observability.jsonl"
            ),
            "AIOS_DEVICE_METADATA_PROVIDER_HARDWARE_PROFILE": str(
                repo / "aios" / "hardware" / "profiles" / "framework-laptop-13-amd-7040.yaml"
            ),
        }
    )
    return env


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("device metadata provider smoke skipped: unix rpc transport unsupported on this platform")
        return 0

    binaries = {
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
        "deviced": resolve_binary("deviced", args.deviced, args.bin_dir),
        "provider": resolve_binary("device-metadata-provider", args.provider, args.bin_dir),
    }
    ensure_binaries(binaries)

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="aios-device-metadata-provider-",
            dir="/tmp" if Path("/tmp").exists() else None,
        )
    )
    env = make_env(temp_root)
    sockets = {
        "agentd": Path(env["AIOS_AGENTD_SOCKET_PATH"]),
        "deviced": Path(env["AIOS_DEVICED_SOCKET_PATH"]),
        "provider": Path(env["AIOS_DEVICE_METADATA_PROVIDER_SOCKET_PATH"]),
    }
    processes: dict[str, subprocess.Popen] = {}
    failed = False

    try:
        for name in ["deviced", "agentd", "provider"]:
            processes[name] = launch(binaries[name], env)
            wait_for_socket(sockets[name], args.timeout)
            wait_for_health(sockets[name], args.timeout)

        provider_id = "device.metadata.local"
        provider_system_health = wait_for_health(sockets["provider"], args.timeout)
        provider_notes = note_map(provider_system_health)
        require(
            provider_notes.get("observability_log_path")
            == env["AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG"],
            "provider health missing observability log path",
        )
        require(
            provider_notes.get("device_backend_overall_status") == "ready",
            "provider health missing backend overall status",
        )
        require(
            provider_notes.get("device_backend_attention_count") == "0",
            "provider health missing backend attention count",
        )
        require(
            "xdg-desktop-portal-screencast" in (provider_notes.get("device_release_grade_backend_ids") or ""),
            "provider health missing release-grade backend ids",
        )
        require(
            provider_notes.get("device_hardware_profile_id") == "framework-laptop-13-amd-7040",
            "provider health missing hardware profile id",
        )
        require(
            provider_notes.get("device_hardware_profile_validation_status") == "matched",
            "provider health missing matched hardware profile validation status",
        )
        wait_for_provider_health(sockets["agentd"], provider_id, "available", args.timeout)

        resolution = rpc_call(
            sockets["agentd"],
            "agent.provider.resolve_capability",
            {
                "capability_id": "device.metadata.get",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            (resolution.get("selected") or {}).get("provider_id") == provider_id,
            f"device.metadata.get did not resolve to {provider_id}",
        )

        descriptor = rpc_call(
            sockets["agentd"],
            "agent.provider.get_descriptor",
            {"provider_id": provider_id},
            timeout=args.timeout,
        )
        require(
            (descriptor.get("descriptor") or {}).get("provider_id") == provider_id,
            "device metadata descriptor missing",
        )

        metadata = rpc_call(
            sockets["provider"],
            "device.metadata.get",
            {
                "modalities": ["screen", "audio", "input", "camera"],
                "only_available": True,
                "include_state_notes": True,
            },
            timeout=args.timeout,
        )
        require(metadata["provider_id"] == provider_id, "provider id mismatch")
        require(metadata["device_service_id"] == "aios-deviced", "device service id mismatch")
        require(metadata["active_capture_count"] == 0, "unexpected active captures in metadata snapshot")
        require(metadata["summary"]["overall_status"] == "ready", "metadata summary should report ready")
        require(
            metadata["summary"]["requested_modalities"] == ["audio", "camera", "input", "screen"],
            "metadata summary requested modalities mismatch",
        )
        require(metadata["summary"]["continuous_collector_count"] == 0, "unexpected continuous collectors in readiness summary")
        require(metadata["backend_summary"]["overall_status"] == "ready", "metadata backend summary should report ready")
        require(metadata["backend_summary"]["attention_count"] == 0, "metadata backend summary should not report attention items")
        require(
            metadata["backend_summary"]["available_status_count"] >= 4,
            "metadata backend summary should expose available backend status count",
        )
        require(isinstance(metadata.get("ui_tree_support_matrix"), list), "ui_tree support matrix missing from metadata response")
        entries = {entry["modality"]: entry for entry in metadata["entries"]}
        require(set(entries) == {"screen", "audio", "input", "camera"}, f"unexpected metadata modalities: {sorted(entries)}")
        require(entries["screen"]["adapter_id"] == "screen.portal-native", "screen adapter id mismatch")
        require(entries["audio"]["adapter_id"] == "audio.pipewire-native", "audio adapter id mismatch")
        require(entries["input"]["adapter_id"] == "input.libinput-native", "input adapter id mismatch")
        require(entries["camera"]["adapter_id"] == "camera.v4l-native", "camera adapter id mismatch")
        require(entries["camera"]["available"] is True, "camera should be available")
        require(
            "release_grade_backend_id=xdg-desktop-portal-screencast" in entries["screen"]["backend_details"],
            "screen metadata entry missing release-grade backend id",
        )
        require(
            "release_grade_backend_stack=portal+pipewire" in entries["screen"]["backend_details"],
            "screen metadata entry missing release-grade backend stack",
        )
        require(
            "release_grade_backend_id=pipewire" in entries["audio"]["backend_details"],
            "audio metadata entry missing release-grade backend id",
        )
        require(
            any(note.startswith("release_grade_backend_ids=") for note in metadata["notes"]),
            "metadata response missing aggregated release-grade backend ids",
        )
        require(
            any(note.startswith("release_grade_backend_id[screen]=") for note in metadata["notes"]),
            "metadata response missing screen release-grade backend note",
        )
        require("approval_mode=metadata-only" in metadata["notes"], "state notes not included in metadata response")
        require("overall_status=ready" in metadata["notes"], "metadata response missing overall status note")
        require("backend_overall_status=ready" in metadata["notes"], "metadata response missing backend overall status note")
        metadata_notes = note_map(metadata)
        require(
            metadata_notes.get("hardware_profile_id") == "framework-laptop-13-amd-7040",
            "metadata response missing hardware profile id",
        )
        require(
            metadata_notes.get("hardware_profile_required_modalities") == "audio,camera,input,screen,ui_tree",
            "metadata response missing required hardware profile modalities",
        )
        require(
            metadata_notes.get("hardware_profile_validation_status") == "matched",
            "metadata response missing matched hardware profile validation status",
        )
        require(
            metadata_notes.get("hardware_profile_missing_required_modalities") == "",
            "metadata response should not report missing required modalities",
        )
        require(
            "hardware_profile_expectation=required" in entries["screen"]["backend_details"],
            "screen metadata entry missing hardware profile expectation",
        )

        screen_only = rpc_call(
            sockets["provider"],
            "device.metadata.get",
            {
                "modalities": ["screen"],
                "only_available": True,
                "include_state_notes": False,
            },
            timeout=args.timeout,
        )
        require(len(screen_only["entries"]) == 1, "screen-only metadata filter failed")
        require(screen_only["entries"][0]["modality"] == "screen", "screen-only filter returned wrong modality")

        ui_tree_only = rpc_call(
            sockets["provider"],
            "device.metadata.get",
            {
                "modalities": ["ui_tree"],
                "only_available": True,
                "include_state_notes": False,
            },
            timeout=args.timeout,
        )
        require(ui_tree_only["summary"]["requested_modalities"] == ["ui_tree"], "ui_tree-only metadata request mismatch")
        require(ui_tree_only["summary"]["unknown_modalities"] == [], "ui_tree should not be treated as an unknown modality")
        require(ui_tree_only["summary"]["available_modalities"] == ["ui_tree"], "ui_tree should be reported as an available modality")
        require(len(ui_tree_only["entries"]) == 1, "ui_tree-only metadata filter failed")
        require(ui_tree_only["entries"][0]["modality"] == "ui_tree", "ui_tree-only filter returned wrong modality")
        require(ui_tree_only["entries"][0]["adapter_id"] == "ui_tree.atspi-state-file", "ui_tree adapter id mismatch")
        require(ui_tree_only["entries"][0]["available"] is True, "ui_tree should be available")
        require(ui_tree_only["entries"][0]["readiness"] == "native-live", "ui_tree readiness mismatch")
        require(
            "ui_tree_current_environment_id=current-session" in ui_tree_only["entries"][0]["backend_details"],
            "ui_tree metadata entry missing current support row detail",
        )
        require(
            "hardware_profile_expectation=required" in ui_tree_only["entries"][0]["backend_details"],
            "ui_tree metadata entry missing hardware profile expectation",
        )
        require(
            "hardware_profile_validation_status=matched" in ui_tree_only["entries"][0]["notes"],
            "ui_tree metadata entry missing hardware profile validation status",
        )

        deviced_process = processes["deviced"]
        stop_process(deviced_process)
        deviced_process.wait(timeout=5)

        dependency_outage = wait_for_provider_health(sockets["agentd"], provider_id, "unavailable", args.timeout)
        require(dependency_outage["provider_id"] == provider_id, "provider health did not downgrade after deviced outage")

        provider_health = rpc_call(
            sockets["provider"],
            "system.health.get",
            {},
            timeout=args.timeout,
        )
        require(provider_health["status"] == "degraded", "provider health should degrade when deviced is unavailable")
        provider_health_notes = note_map(provider_health)
        require(
            provider_health_notes.get("device_backend_overall_status") == "unavailable",
            "provider health missing unavailable backend overall status",
        )
        require(
            "deviced_status=unavailable" in provider_health.get("notes", []),
            "provider health missing deviced unavailable note",
        )

        unavailable_metadata = rpc_call(
            sockets["provider"],
            "device.metadata.get",
            {
                "modalities": ["screen", "audio", "input", "camera"],
                "only_available": False,
                "include_state_notes": False,
            },
            timeout=args.timeout,
        )
        require(
            unavailable_metadata["summary"]["overall_status"] == "unavailable",
            "metadata fallback should report unavailable during deviced outage",
        )
        require(
            unavailable_metadata["backend_summary"]["overall_status"] == "unavailable",
            "metadata fallback should expose unavailable backend summary during deviced outage",
        )
        require(unavailable_metadata["entries"] == [], "metadata outage response should not include stale entries")
        require(
            "backend_overall_status=unavailable" in unavailable_metadata["notes"],
            "metadata outage response missing backend overall status note",
        )
        require(
            "device_state_source=unavailable" in unavailable_metadata["notes"],
            "metadata outage response missing unavailable source note",
        )

        post_stop_resolution = rpc_call(
            sockets["agentd"],
            "agent.provider.resolve_capability",
            {
                "capability_id": "device.metadata.get",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(post_stop_resolution.get("selected") is None, "healthy resolution should be empty during deviced outage")

        processes["deviced"] = launch(binaries["deviced"], env)
        wait_for_socket(sockets["deviced"], args.timeout)
        wait_for_health(sockets["deviced"], args.timeout)

        recovered = wait_for_provider_health(sockets["agentd"], provider_id, "available", args.timeout)
        require(recovered["status"] == "available", "provider health did not recover after deviced restart")

        recovered_metadata = rpc_call(
            sockets["provider"],
            "device.metadata.get",
            {
                "modalities": ["screen", "audio", "input", "camera"],
                "only_available": True,
                "include_state_notes": False,
            },
            timeout=args.timeout,
        )
        require(
            recovered_metadata["summary"]["overall_status"] == "ready",
            "metadata summary did not recover after deviced restart",
        )

        provider_process = processes["provider"]
        stop_process(provider_process)
        provider_process.wait(timeout=5)

        observability_entries = wait_for_json_lines(
            Path(env["AIOS_DEVICE_METADATA_PROVIDER_OBSERVABILITY_LOG"]),
            args.timeout,
            lambda entries: {
                entry.get("kind")
                for entry in entries
                if isinstance(entry, dict) and entry.get("kind")
            }
            >= {
                "provider.runtime.started",
                "provider.runtime.stopped",
                "provider.registry.registered",
            }
            and {"ready", "blocked"}
            <= {
                entry.get("overall_status")
                for entry in entries
                if isinstance(entry, dict) and entry.get("overall_status")
            },
            "device metadata provider observability convergence",
        )

        unavailable = wait_for_provider_health(sockets["agentd"], provider_id, "unavailable", args.timeout)
        require(unavailable["provider_id"] == provider_id, "provider health unavailable transition missing")

        post_shutdown_resolution = rpc_call(
            sockets["agentd"],
            "agent.provider.resolve_capability",
            {
                "capability_id": "device.metadata.get",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(post_shutdown_resolution.get("selected") is None, "healthy resolution should be empty after provider shutdown")

        summary = {
            "provider_id": provider_id,
            "resolved_provider": resolution["selected"]["provider_id"],
            "modalities": sorted(entries),
            "startup_overall_status": metadata["summary"]["overall_status"],
            "outage_overall_status": unavailable_metadata["summary"]["overall_status"],
            "recovered_overall_status": recovered_metadata["summary"]["overall_status"],
            "recovered_provider_status": recovered["status"],
            "post_stop_status": unavailable["status"],
            "observability_event_count": len(observability_entries),
            "temp_root": str(temp_root),
        }
        print(json.dumps(summary, indent=2))
        return 0
    except Exception:
        failed = True
        raise
    finally:
        terminate(list(processes.values()))
        if failed:
            print_logs(processes)
        if args.keep_state or failed:
            print(f"device metadata provider smoke state preserved at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
