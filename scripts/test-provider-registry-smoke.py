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


EXPECTED_BUILTIN_PROVIDERS = {
    "system.intent.local",
    "system.files.local",
    "device.metadata.local",
    "runtime.local.inference",
    "shell.control.local",
    "shell.screen-capture.portal",
    "compat.browser.automation.local",
    "compat.office.document.local",
    "compat.mcp.bridge.local",
    "compat.code.sandbox.local",
}

EXPECTED_RESOLUTIONS = {
    "system.intent.execute": "system.intent.local",
    "provider.fs.open": "system.files.local",
    "device.metadata.get": "device.metadata.local",
    "runtime.infer.submit": "runtime.local.inference",
    "runtime.embed.vectorize": "runtime.local.inference",
    "runtime.rerank.score": "runtime.local.inference",
    "shell.notification.open": "shell.control.local",
    "shell.operator-audit.open": "shell.control.local",
    "shell.window.focus": "shell.control.local",
    "shell.panel-events.list": "shell.control.local",
    "device.capture.screen.read": "shell.screen-capture.portal",
    "compat.browser.navigate": "compat.browser.automation.local",
    "compat.document.open": "compat.office.document.local",
    "compat.mcp.call": "compat.mcp.bridge.local",
    "compat.code.execute": "compat.code.sandbox.local",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS provider registry smoke harness")
    parser.add_argument("--bin-dir", type=Path, help="Directory containing the agentd binary")
    parser.add_argument("--agentd", type=Path, help="Path to agentd binary")
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


def ensure_binaries(paths: dict[str, Path]) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.exists()]
    if missing:
        print("Missing binaries for provider registry smoke harness:")
        for item in missing:
            print(f"  - {item}")
        print("Build them first, for example: cargo build -p aios-agentd")
        raise SystemExit(2)


def rpc_call(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
    response = rpc_request(socket_path, method, params, timeout)
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    return response["result"]


def rpc_request(socket_path: Path, method: str, params: dict, timeout: float) -> dict:
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


def unix_rpc_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and os.name != "nt"

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
            "AIOS_PROVIDER_REMOTE_REQUIRE_VERIFIED_ATTESTATION": "1",
            "AIOS_PROVIDER_REMOTE_ALLOWED_FLEETS": "fleet-browser",
            "AIOS_PROVIDER_REMOTE_ALLOWED_GOVERNANCE_GROUPS": "operator-audit",
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


def provider_ids(discovery_result: dict) -> set[str]:
    return {
        candidate["provider_id"]
        for candidate in discovery_result.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("provider_id")
    }


def provider_health_map(health_result: dict) -> dict[str, dict]:
    return {
        provider["provider_id"]: provider
        for provider in health_result.get("providers", [])
        if isinstance(provider, dict) and provider.get("provider_id")
    }


def build_dynamic_descriptor() -> dict:
    template_path = repo_root() / "aios" / "compat" / "code-sandbox" / "providers" / "code.sandbox.local.json"
    descriptor = json.loads(template_path.read_text())
    descriptor["provider_id"] = "compat.test.dynamic"
    descriptor["display_name"] = "Dynamic Compat Test Provider"
    descriptor["owner"] = "aios-tests"
    descriptor["capabilities"] = [
        {
            "capability_id": "compat.test.ping",
            "read_only": True,
            "recoverable": True,
            "approval_required": False,
            "external_side_effect": False,
            "dynamic_code": False,
            "user_interaction_required": False,
            "supported_targets": ["text"],
            "input_schema_refs": ["aios/test.ping.request"],
            "output_schema_refs": ["aios/test.ping.response"],
            "audit_tags": ["test", "dynamic"],
        }
    ]
    descriptor["execution_location"] = "local"
    descriptor["sandbox_class"] = "dynamic-test"
    descriptor["required_permissions"] = []
    descriptor["resource_budget"] = {
        "max_memory_mb": 64,
        "max_cpu_percent": 20,
        "max_concurrency": 1,
    }
    descriptor["supported_targets"] = ["text"]
    descriptor["input_schema_refs"] = ["aios/test.ping.request"]
    descriptor["output_schema_refs"] = ["aios/test.ping.response"]
    descriptor["timeout_policy"] = "bounded-5s"
    descriptor["retry_policy"] = "no-retry"
    descriptor["healthcheck"] = {
        "kind": "process",
        "endpoint": "dynamic-test-provider",
        "interval_seconds": 30,
    }
    descriptor["audit_tags"] = ["test", "dynamic"]
    descriptor["taint_behavior"] = "input-propagates"
    descriptor["degradation_policy"] = "deny-on-unavailable"
    return descriptor


def build_remote_descriptor() -> dict:
    template_path = repo_root() / "aios" / "compat" / "browser" / "providers" / "browser.automation.local.json"
    descriptor = json.loads(template_path.read_text())
    descriptor["provider_id"] = "compat.browser.remote.worker"
    descriptor["display_name"] = "Remote Browser Worker"
    descriptor["owner"] = "aios-tests"
    descriptor["execution_location"] = "attested_remote"
    descriptor["capabilities"] = [
        capability
        for capability in descriptor["capabilities"]
        if capability["capability_id"] == "compat.browser.navigate"
    ]
    descriptor["compat_permission_manifest"]["capabilities"] = [
        capability
        for capability in descriptor["compat_permission_manifest"]["capabilities"]
        if capability["capability_id"] == "compat.browser.navigate"
    ]
    descriptor["trust_policy_modes"] = ["registered-remote", "bearer"]
    descriptor["remote_registration"] = {
        "source_provider_id": "compat.browser.automation.local",
        "provider_ref": "browser.remote.worker",
        "endpoint": "https://browser.remote.example/bridge",
        "auth_mode": "bearer",
        "auth_secret_env": "BROWSER_REMOTE_SECRET",
        "target_hash": "sha256:browser-remote-worker",
        "capabilities": ["compat.browser.navigate"],
        "registered_at": "2026-03-14T00:00:00Z",
        "display_name": "Remote Browser Worker",
        "control_plane_provider_id": "compat.browser.remote.worker",
        "attestation": {
            "mode": "verified",
            "issuer": "registry-smoke-attestor",
            "subject": "browser.remote.worker",
            "issued_at": "2026-03-14T00:00:00Z",
            "expires_at": "2030-01-01T00:00:00Z",
            "evidence_ref": "evidence://remote/browser",
            "digest": "sha256:browser-remote-attestation",
            "status": "trusted",
        },
        "governance": {
            "fleet_id": "fleet-browser",
            "governance_group": "operator-audit",
            "policy_group": "compat-browser-remote",
            "registered_by": "scripts/test-provider-registry-smoke.py",
            "approval_ref": "approval-remote-browser-1",
            "allow_lateral_movement": False,
        },
    }
    return descriptor


def build_disallowed_remote_descriptor() -> dict:
    descriptor = build_remote_descriptor()
    descriptor["provider_id"] = "compat.browser.remote.disallowed"
    descriptor["display_name"] = "Disallowed Remote Browser Worker"
    descriptor["remote_registration"]["provider_ref"] = "browser.remote.disallowed"
    descriptor["remote_registration"]["control_plane_provider_id"] = "compat.browser.remote.disallowed"
    descriptor["remote_registration"]["attestation"]["subject"] = "browser.remote.disallowed"
    descriptor["remote_registration"]["governance"]["fleet_id"] = "fleet-rogue"
    return descriptor


def allocate_temp_root() -> Path:
    if Path("/tmp").exists():
        return Path(tempfile.mkdtemp(prefix="aios-registry-", dir="/tmp"))
    return Path(tempfile.mkdtemp(prefix="aios-registry-"))


def main() -> int:
    args = parse_args()
    if not unix_rpc_supported():
        print("provider registry smoke skipped: unix rpc transport unsupported on this platform")
        return 0
    binaries = {
        "agentd": resolve_binary("agentd", args.agentd, args.bin_dir),
    }
    ensure_binaries(binaries)

    temp_root = allocate_temp_root()
    env = make_env(temp_root)
    registry_state_dir = Path(env["AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR"])
    socket_path = Path(env["AIOS_AGENTD_SOCKET_PATH"])
    processes: dict[str, subprocess.Popen] = {}
    failed = False

    try:
        processes["agentd"] = launch(binaries["agentd"], env)
        wait_for_socket(socket_path, args.timeout)
        health = wait_for_health(socket_path, args.timeout)
        print(f"agentd ready: {health['status']} @ {health['socket_path']}")

        all_providers = rpc_call(socket_path, "agent.provider.discover", {}, timeout=args.timeout)
        discovered_builtin_providers = provider_ids(all_providers)
        require(
            EXPECTED_BUILTIN_PROVIDERS.issubset(discovered_builtin_providers),
            f"missing builtin providers: {sorted(EXPECTED_BUILTIN_PROVIDERS - discovered_builtin_providers)}",
        )

        health_result = rpc_call(socket_path, "agent.provider.health.get", {}, timeout=args.timeout)
        builtin_health = provider_health_map(health_result)
        require(
            EXPECTED_BUILTIN_PROVIDERS.issubset(set(builtin_health)),
            f"missing health state for providers: {sorted(EXPECTED_BUILTIN_PROVIDERS - set(builtin_health))}",
        )

        descriptor = rpc_call(
            socket_path,
            "agent.provider.get_descriptor",
            {"provider_id": "compat.code.sandbox.local"},
            timeout=args.timeout,
        )
        require(
            descriptor.get("descriptor", {}).get("provider_id") == "compat.code.sandbox.local",
            "failed to read compat.code.sandbox.local descriptor",
        )

        checked_resolutions: list[str] = []
        for capability_id, provider_id in EXPECTED_RESOLUTIONS.items():
            resolved = rpc_call(
                socket_path,
                "agent.provider.resolve_capability",
                {
                    "capability_id": capability_id,
                    "require_healthy": True,
                    "include_disabled": False,
                },
                timeout=args.timeout,
            )
            selected = resolved.get("selected") or {}
            require(
                selected.get("provider_id") == provider_id,
                f"capability {capability_id} resolved to {selected.get('provider_id')} instead of {provider_id}",
            )
            checked_resolutions.append(capability_id)

        reported_unavailable = rpc_call(
            socket_path,
            "agent.provider.health.report",
            {
                "provider_id": "system.files.local",
                "status": "unavailable",
                "last_error": "registry-smoke-simulated-stop",
                "circuit_open": False,
            },
            timeout=args.timeout,
        )
        require(reported_unavailable.get("status") == "unavailable", "provider.health.report did not mark system.files.local unavailable")

        unavailable_resolution = rpc_call(
            socket_path,
            "agent.provider.resolve_capability",
            {
                "capability_id": "provider.fs.open",
                "preferred_execution_location": "local",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            unavailable_resolution.get("selected") is None,
            "provider.resolve_capability still selected system.files.local after health report unavailable",
        )

        reported_available = rpc_call(
            socket_path,
            "agent.provider.health.report",
            {
                "provider_id": "system.files.local",
                "status": "available",
                "circuit_open": False,
            },
            timeout=args.timeout,
        )
        require(reported_available.get("status") == "available", "provider.health.report did not restore system.files.local availability")

        rehealthy_resolution = rpc_call(
            socket_path,
            "agent.provider.resolve_capability",
            {
                "capability_id": "provider.fs.open",
                "preferred_execution_location": "local",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            (rehealthy_resolution.get("selected") or {}).get("provider_id") == "system.files.local",
            "system.files.local did not recover after provider.health.report available",
        )

        disabled = rpc_call(
            socket_path,
            "agent.provider.disable",
            {
                "provider_id": "compat.code.sandbox.local",
                "reason": "registry-smoke",
            },
            timeout=args.timeout,
        )
        require(disabled.get("disabled") is True, "provider.disable did not mark compat.code.sandbox.local disabled")
        require(disabled.get("status") == "disabled", "provider.disable did not set disabled status")

        disabled_discovery = rpc_call(
            socket_path,
            "agent.provider.discover",
            {
                "capability_id": "compat.code.execute",
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            not disabled_discovery.get("candidates"),
            "disabled provider still appeared in healthy discovery results",
        )

        disabled_resolution = rpc_call(
            socket_path,
            "agent.provider.resolve_capability",
            {
                "capability_id": "compat.code.execute",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            disabled_resolution.get("selected") is None,
            "disabled provider should not be selected while require_healthy=true",
        )

        disabled_inclusive = rpc_call(
            socket_path,
            "agent.provider.discover",
            {
                "capability_id": "compat.code.execute",
                "include_disabled": True,
            },
            timeout=args.timeout,
        )
        inclusive_candidates = disabled_inclusive.get("candidates", [])
        require(len(inclusive_candidates) == 1, "expected one disabled compat.code.execute provider candidate")
        require(inclusive_candidates[0].get("disabled") is True, "disabled provider did not surface as disabled")

        enabled = rpc_call(
            socket_path,
            "agent.provider.enable",
            {
                "provider_id": "compat.code.sandbox.local",
            },
            timeout=args.timeout,
        )
        require(enabled.get("disabled") is False, "provider.enable did not clear disabled flag")
        require(enabled.get("status") == "available", "provider.enable did not restore available status")

        reenabled_resolution = rpc_call(
            socket_path,
            "agent.provider.resolve_capability",
            {
                "capability_id": "compat.code.execute",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            (reenabled_resolution.get("selected") or {}).get("provider_id") == "compat.code.sandbox.local",
            "compat.code.sandbox.local did not recover after provider.enable",
        )

        dynamic_descriptor = build_dynamic_descriptor()
        dynamic_provider_id = dynamic_descriptor["provider_id"]
        register_result = rpc_call(
            socket_path,
            "agent.provider.register",
            {"descriptor": dynamic_descriptor},
            timeout=args.timeout,
        )
        require(register_result.get("provider_id") == dynamic_provider_id, "provider.register returned an unexpected provider_id")
        require(register_result.get("source") == "dynamic", "provider.register did not mark the provider as dynamic")

        descriptor_path = registry_state_dir / "descriptors" / f"{dynamic_provider_id}.json"
        health_path = registry_state_dir / "health" / f"{dynamic_provider_id}.json"
        require(descriptor_path.exists(), "dynamic descriptor file was not written")
        require(health_path.exists(), "dynamic health file was not written")

        dynamic_discovery = rpc_call(
            socket_path,
            "agent.provider.discover",
            {
                "capability_id": "compat.test.ping",
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            provider_ids(dynamic_discovery) == {dynamic_provider_id},
            "dynamic provider discovery did not return the registered provider",
        )

        dynamic_descriptor_result = rpc_call(
            socket_path,
            "agent.provider.get_descriptor",
            {"provider_id": dynamic_provider_id},
            timeout=args.timeout,
        )
        require(
            dynamic_descriptor_result.get("descriptor", {}).get("provider_id") == dynamic_provider_id,
            "dynamic provider descriptor lookup failed",
        )

        dynamic_resolution = rpc_call(
            socket_path,
            "agent.provider.resolve_capability",
            {
                "capability_id": "compat.test.ping",
                "preferred_kind": "compat-provider",
                "preferred_execution_location": "local",
                "require_healthy": True,
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        require(
            (dynamic_resolution.get("selected") or {}).get("provider_id") == dynamic_provider_id,
            "dynamic provider did not resolve by capability",
        )

        remote_descriptor = build_remote_descriptor()
        remote_provider_id = remote_descriptor["provider_id"]
        remote_register_result = rpc_call(
            socket_path,
            "agent.provider.register",
            {"descriptor": remote_descriptor},
            timeout=args.timeout,
        )
        require(
            remote_register_result.get("provider_id") == remote_provider_id,
            "remote provider.register returned an unexpected provider_id",
        )

        remote_descriptor_result = rpc_call(
            socket_path,
            "agent.provider.get_descriptor",
            {"provider_id": remote_provider_id},
            timeout=args.timeout,
        )
        remote_registration = (remote_descriptor_result.get("descriptor") or {}).get("remote_registration") or {}
        require(
            remote_registration.get("provider_ref") == "browser.remote.worker",
            "remote provider descriptor missing provider_ref",
        )
        require(
            remote_registration.get("auth_mode") == "bearer",
            "remote provider descriptor missing auth mode",
        )
        require(
            (remote_registration.get("attestation") or {}).get("issuer") == "registry-smoke-attestor",
            "remote provider descriptor missing attestation issuer",
        )
        require(
            (remote_registration.get("governance") or {}).get("fleet_id") == "fleet-browser",
            "remote provider descriptor missing governance fleet id",
        )

        remote_discovery = rpc_call(
            socket_path,
            "agent.provider.discover",
            {
                "capability_id": "compat.browser.navigate",
                "execution_location": "attested_remote",
                "include_disabled": False,
            },
            timeout=args.timeout,
        )
        remote_candidates = remote_discovery.get("candidates", [])
        require(remote_candidates, "expected attested_remote browser candidate")
        require(
            remote_candidates[0].get("provider_id") == remote_provider_id,
            "remote browser candidate provider mismatch",
        )
        require(
            (remote_candidates[0].get("remote_registration") or {}).get("endpoint")
            == "https://browser.remote.example/bridge",
            "remote browser candidate missing endpoint metadata",
        )
        require(
            ((remote_candidates[0].get("remote_registration") or {}).get("attestation") or {}).get("mode")
            == "verified",
            "remote browser candidate missing attestation metadata",
        )
        require(
            ((remote_candidates[0].get("remote_registration") or {}).get("governance") or {}).get("governance_group")
            == "operator-audit",
            "remote browser candidate missing governance metadata",
        )

        remote_resolution = rpc_call(
            socket_path,
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
            (remote_resolution.get("selected") or {}).get("provider_id") == remote_provider_id,
            "remote browser provider did not resolve by attested_remote preference",
        )
        require(
            (((remote_resolution.get("selected") or {}).get("remote_registration") or {}).get("attestation") or {}).get("status")
            == "trusted",
            "remote browser resolution missing attestation status",
        )

        disallowed_remote_response = rpc_request(
            socket_path,
            "agent.provider.register",
            {"descriptor": build_disallowed_remote_descriptor()},
            timeout=args.timeout,
        )
        error_message = ((disallowed_remote_response.get("error") or {}).get("message") or "")
        require(
            "AIOS_PROVIDER_REMOTE_ALLOWED_FLEETS" in error_message,
            "disallowed remote registration should be rejected by fleet governance",
        )

        unregister_result = rpc_call(
            socket_path,
            "agent.provider.unregister",
            {"provider_id": dynamic_provider_id},
            timeout=args.timeout,
        )
        require(unregister_result.get("unregistered") is True, "provider.unregister did not confirm success")
        require(not descriptor_path.exists(), "dynamic descriptor file still exists after unregister")
        require(not health_path.exists(), "dynamic health file still exists after unregister")

        post_unregister = rpc_call(
            socket_path,
            "agent.provider.get_descriptor",
            {"provider_id": dynamic_provider_id},
            timeout=args.timeout,
        )
        require(post_unregister.get("descriptor") is None, "dynamic descriptor still resolves after unregister")

        remote_unregister_result = rpc_call(
            socket_path,
            "agent.provider.unregister",
            {"provider_id": remote_provider_id},
            timeout=args.timeout,
        )
        require(remote_unregister_result.get("unregistered") is True, "remote provider.unregister did not confirm success")

        print(
            json.dumps(
                {
                    "builtin_provider_count": len(discovered_builtin_providers),
                    "checked_resolutions": checked_resolutions,
                    "dynamic_provider_id": dynamic_provider_id,
                    "remote_provider_id": remote_provider_id,
                    "registry_state_dir": str(registry_state_dir),
                    "lifecycle_report_provider": "system.files.local",
                                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        failed = True
        print(f"Provider registry smoke failed: {exc}")
        return 1
    finally:
        terminate(list(processes.values()))
        print_logs(processes)
        if failed or args.keep_state:
            print(f"provider registry smoke state preserved at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
