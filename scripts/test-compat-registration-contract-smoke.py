#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

from jsonschema import Draft202012Validator, RefResolver


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "aios" / "sdk" / "schemas"
BROWSER_RUNTIME = ROOT / "aios" / "compat" / "browser" / "runtime" / "browser_provider.py"
OFFICE_RUNTIME = ROOT / "aios" / "compat" / "office" / "runtime" / "office_provider.py"
MCP_RUNTIME = ROOT / "aios" / "compat" / "mcp-bridge" / "runtime" / "mcp_bridge_provider.py"
WORK_ROOT = ROOT / "out" / "validation" / "compat-registration-contract"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rewrite_schema_refs(payload: Any, id_map: dict[str, str]) -> Any:
    if isinstance(payload, dict):
        rewritten: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"$id", "$ref"} and isinstance(value, str):
                normalized = value.removeprefix("aios/")
                rewritten[key] = id_map.get(normalized, value)
                continue
            rewritten[key] = rewrite_schema_refs(value, id_map)
        return rewritten
    if isinstance(payload, list):
        return [rewrite_schema_refs(item, id_map) for item in payload]
    return payload


def build_validator(schema_name: str) -> Draft202012Validator:
    raw_schemas: dict[str, Any] = {}
    for schema_path in sorted(SCHEMA_DIR.glob("*.json")):
        schema = load_json(schema_path)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            continue
        normalized = schema_id.removeprefix("aios/")
        raw_schemas[normalized] = schema
    id_map = {
        name: f"https://schemas.aios.local/{name}"
        for name in raw_schemas
    }
    store = {
        id_map[name]: rewrite_schema_refs(schema, id_map)
        for name, schema in raw_schemas.items()
    }
    schema = store[id_map[schema_name]]
    Draft202012Validator.check_schema(schema)
    resolver = RefResolver.from_schema(schema, store=store)
    return Draft202012Validator(
        schema,
        resolver=resolver,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def run_json_command(runtime: Path, *args: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        [sys.executable, str(runtime), *args],
        cwd=ROOT,
        env=command_env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {sys.executable} {runtime} {' '.join(args)}\n"
            f"{completed.stderr.strip()}\n{completed.stdout.strip()}"
        )
    return json.loads(completed.stdout)


def build_remote_descriptor(
    *,
    descriptor_path: Path,
    provider_id: str,
    capability_ids: list[str],
    remote_registration: dict[str, Any],
) -> dict[str, Any]:
    descriptor = load_json(descriptor_path)
    descriptor["provider_id"] = provider_id
    descriptor["execution_location"] = "attested_remote"
    descriptor["display_name"] = remote_registration.get("display_name") or remote_registration["provider_ref"]
    descriptor["trust_policy_modes"] = sorted(
        {
            *descriptor.get("trust_policy_modes", []),
            "registered-remote",
            remote_registration["auth_mode"],
        }
    )
    descriptor["audit_tags"] = sorted({*descriptor.get("audit_tags", []), "remote"})
    descriptor["supported_targets"] = sorted({*descriptor.get("supported_targets", []), "registered-remote"})
    descriptor["capabilities"] = [
        capability
        for capability in descriptor.get("capabilities", [])
        if isinstance(capability, dict) and capability.get("capability_id") in capability_ids
    ]
    compat_manifest = descriptor.get("compat_permission_manifest")
    if isinstance(compat_manifest, dict):
        compat_manifest["provider_id"] = provider_id
        compat_manifest["execution_location"] = "attested_remote"
        compat_manifest["capabilities"] = [
            capability
            for capability in compat_manifest.get("capabilities", [])
            if isinstance(capability, dict) and capability.get("capability_id") in capability_ids
        ]
        descriptor["compat_permission_manifest"] = compat_manifest
    descriptor["remote_registration"] = remote_registration
    return descriptor


def browser_registry_sample(temp_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry_path = temp_root / "browser-remote-registry.json"
    env = {
        "AIOS_BROWSER_TRUST_MODE": "allowlist",
        "AIOS_BROWSER_ALLOWLIST": "127.0.0.1,localhost",
        "AIOS_BROWSER_REMOTE_REGISTRY": str(registry_path),
    }
    run_json_command(
        BROWSER_RUNTIME,
        "register-remote",
        "--provider-ref",
        "browser.remote.worker",
        "--endpoint",
        "http://127.0.0.1/browser",
        "--capability",
        "compat.browser.navigate",
        "--capability",
        "compat.browser.extract",
        "--auth-mode",
        "bearer",
        "--auth-secret-env",
        "BROWSER_REMOTE_SECRET",
        "--display-name",
        "Remote Browser Worker",
        "--attestation-mode",
        "verified",
        "--attestation-issuer",
        "compat-registration-smoke",
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
        "scripts/test-compat-registration-contract-smoke.py",
        "--approval-ref",
        "approval-browser-1",
        "--heartbeat-ttl-seconds",
        "600",
        env=env,
    )
    run_json_command(
        BROWSER_RUNTIME,
        "heartbeat-remote",
        "--provider-ref",
        "browser.remote.worker",
        env=env,
    )
    run_json_command(
        BROWSER_RUNTIME,
        "revoke-remote",
        "--provider-ref",
        "browser.remote.worker",
        "--reason",
        "rotation-complete",
        env=env,
    )
    registry_payload = load_json(registry_path)
    remote_registration = dict(registry_payload["entries"][0])
    remote_registration["source_provider_id"] = "compat.browser.automation.local"
    remote_registration["control_plane_provider_id"] = "compat.browser.remote.worker"
    descriptor = build_remote_descriptor(
        descriptor_path=ROOT / "aios" / "compat" / "browser" / "providers" / "browser.automation.local.json",
        provider_id="compat.browser.remote.worker",
        capability_ids=["compat.browser.navigate", "compat.browser.extract"],
        remote_registration=remote_registration,
    )
    return registry_payload, descriptor


def office_registry_sample(temp_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry_path = temp_root / "office-remote-registry.json"
    env = {
        "AIOS_OFFICE_TRUST_MODE": "allowlist",
        "AIOS_OFFICE_ALLOWLIST": "127.0.0.1,localhost",
        "AIOS_OFFICE_REMOTE_REGISTRY": str(registry_path),
    }
    run_json_command(
        OFFICE_RUNTIME,
        "register-remote",
        "--provider-ref",
        "office.remote.worker",
        "--endpoint",
        "http://127.0.0.1/office",
        "--capability",
        "compat.document.open",
        "--capability",
        "compat.office.export_pdf",
        "--auth-mode",
        "bearer",
        "--auth-secret-env",
        "OFFICE_REMOTE_SECRET",
        "--display-name",
        "Remote Office Worker",
        "--attestation-mode",
        "verified",
        "--attestation-issuer",
        "compat-registration-smoke",
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
        "scripts/test-compat-registration-contract-smoke.py",
        "--approval-ref",
        "approval-office-1",
        "--heartbeat-ttl-seconds",
        "600",
        env=env,
    )
    registry_payload = load_json(registry_path)
    remote_registration = dict(registry_payload["entries"][0])
    remote_registration["source_provider_id"] = "compat.office.document.local"
    remote_registration["control_plane_provider_id"] = "compat.office.remote.worker"
    descriptor = build_remote_descriptor(
        descriptor_path=ROOT / "aios" / "compat" / "office" / "providers" / "office.document.local.json",
        provider_id="compat.office.remote.worker",
        capability_ids=["compat.document.open", "compat.office.export_pdf"],
        remote_registration=remote_registration,
    )
    return registry_payload, descriptor


def mcp_registry_sample(temp_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry_path = temp_root / "mcp-remote-registry.json"
    env = {
        "AIOS_MCP_BRIDGE_TRUST_MODE": "allowlist",
        "AIOS_MCP_BRIDGE_ALLOWLIST": "127.0.0.1,localhost",
        "AIOS_MCP_BRIDGE_REMOTE_REGISTRY": str(registry_path),
    }
    run_json_command(
        MCP_RUNTIME,
        "register-remote",
        "--provider-ref",
        "tools.echo.remote",
        "--endpoint",
        "http://127.0.0.1/mcp",
        "--capability",
        "compat.mcp.call",
        "--auth-mode",
        "bearer",
        "--auth-secret-env",
        "MCP_BRIDGE_REMOTE_SECRET",
        "--display-name",
        "Remote MCP Worker",
        "--attestation-mode",
        "verified",
        "--attestation-issuer",
        "compat-registration-smoke",
        "--attestation-subject",
        "tools.echo.remote",
        "--attestation-expires-at",
        "2030-01-01T00:00:00Z",
        "--fleet-id",
        "fleet-mcp",
        "--governance-group",
        "operator-audit",
        "--policy-group",
        "compat-mcp-remote",
        "--registered-by",
        "scripts/test-compat-registration-contract-smoke.py",
        "--approval-ref",
        "approval-mcp-1",
        "--heartbeat-ttl-seconds",
        "600",
        env=env,
    )
    run_json_command(
        MCP_RUNTIME,
        "heartbeat-remote",
        "--provider-ref",
        "tools.echo.remote",
        env=env,
    )
    registry_payload = load_json(registry_path)
    remote_registration = dict(registry_payload["entries"][0])
    remote_registration["source_provider_id"] = "compat.mcp.bridge.local"
    remote_registration["control_plane_provider_id"] = "compat.mcp.remote.worker"
    descriptor = build_remote_descriptor(
        descriptor_path=ROOT / "aios" / "compat" / "mcp-bridge" / "providers" / "mcp.bridge.local.json",
        provider_id="compat.mcp.remote.worker",
        capability_ids=["compat.mcp.call"],
        remote_registration=remote_registration,
    )
    return registry_payload, descriptor


def main() -> int:
    descriptor_validator = build_validator("provider-descriptor.schema.json")
    registration_validator = build_validator("provider-remote-registration.schema.json")
    registry_validator = build_validator("provider-remote-registry.schema.json")

    local_descriptors = [
        ROOT / "aios" / "compat" / "browser" / "providers" / "browser.automation.local.json",
        ROOT / "aios" / "compat" / "office" / "providers" / "office.document.local.json",
        ROOT / "aios" / "compat" / "mcp-bridge" / "providers" / "mcp.bridge.local.json",
    ]
    for descriptor_path in local_descriptors:
        descriptor_validator.validate(load_json(descriptor_path))

    if WORK_ROOT.exists():
        shutil.rmtree(WORK_ROOT, ignore_errors=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    browser_registry, browser_descriptor = browser_registry_sample(WORK_ROOT)
    office_registry, office_descriptor = office_registry_sample(WORK_ROOT)
    mcp_registry, mcp_descriptor = mcp_registry_sample(WORK_ROOT)

    for registry_payload in (browser_registry, office_registry, mcp_registry):
        registry_validator.validate(registry_payload)
        for item in registry_payload["entries"]:
            registration_validator.validate(item)

    for descriptor in (browser_descriptor, office_descriptor, mcp_descriptor):
        descriptor_validator.validate(descriptor)

    summary = {
        "status": "passed",
        "validated_local_descriptors": len(local_descriptors),
        "validated_remote_registries": 3,
        "validated_remote_descriptors": 3,
        "schemas": [
            "aios/provider-descriptor.schema.json",
            "aios/provider-remote-registration.schema.json",
            "aios/provider-remote-registry.schema.json",
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
