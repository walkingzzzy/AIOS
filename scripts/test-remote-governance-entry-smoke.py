#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = ROOT / "out" / "tmp"


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_python(script: Path, *args: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def main() -> int:
    temp_root = make_temp_dir("aios-remote-governance-entry-")
    failed = False
    try:
        browser_registry = temp_root / "browser-remote-registry.json"
        office_registry = temp_root / "office-remote-registry.json"
        mcp_registry = temp_root / "mcp-remote-registry.json"
        provider_registry_state_dir = temp_root / "provider-registry"
        request_path = temp_root / "remote-registration-request.json"
        agent_socket = temp_root / "missing-agentd.sock"
        profile = temp_root / "shell-profile.json"

        request_path.write_text(
            json.dumps(
                {
                    "provider_kind": "mcp",
                    "provider_ref": "mcp.remote.entry",
                    "endpoint": "https://mcp.remote.example/bridge",
                    "capabilities": ["compat.mcp.call", "compat.a2a.forward"],
                    "auth_mode": "none",
                    "display_name": "MCP Remote Entry",
                    "attestation": {
                        "mode": "verified",
                        "status": "trusted",
                        "issuer": "aios-smoke",
                        "subject": "mcp.remote.entry",
                    },
                    "governance": {
                        "fleet_id": "fleet-mcp-entry",
                        "governance_group": "remote-entry-smoke",
                        "approval_ref": "approval-mcp-entry-1",
                    },
                    "health_status": "available",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        profile.write_text(
            json.dumps(
                {
                    "profile_id": "remote-governance-entry-smoke",
                    "components": {
                        "remote_governance": True,
                    },
                    "paths": {
                        "browser_remote_registry": str(browser_registry),
                        "office_remote_registry": str(office_registry),
                        "mcp_remote_registry": str(mcp_registry),
                        "provider_registry_state_dir": str(provider_registry_state_dir),
                        "remote_registration_request_path": str(request_path),
                        "agentd_socket": str(agent_socket),
                    },
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        output = run_python(
            ROOT / "aios" / "shell" / "shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "remote-governance",
            "model",
        )
        panel = json.loads(output)
        require(panel["panel_id"] == "remote-governance-panel", "remote governance panel id mismatch")
        require(panel["meta"]["request_ready"] is True, "remote governance request readiness mismatch")
        require(
            panel["meta"]["request_capabilities"] == ["compat.mcp.call", "compat.a2a.forward"],
            "remote governance request capabilities mismatch",
        )

        output = run_python(
            ROOT / "aios" / "shell" / "shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "remote-governance",
            "action",
            "--action",
            "register-and-promote-request",
        )
        apply_result = json.loads(output)
        require(apply_result["status"] == "promoted", "remote governance entry promotion status mismatch")
        require(
            apply_result["promotion_mode"] == "offline-fallback",
            "remote governance entry promotion mode mismatch",
        )
        control_plane_provider_id = apply_result["control_plane_provider_id"]
        require(
            control_plane_provider_id.startswith("compat.mcp.remote."),
            "remote governance entry control plane provider id mismatch",
        )
        require(Path(apply_result["descriptor_path"]).exists(), "remote governance descriptor missing")
        require(Path(apply_result["health_path"]).exists(), "remote governance health missing")

        registry_payload = json.loads(mcp_registry.read_text(encoding="utf-8"))
        require(len(registry_payload["entries"]) == 1, "remote governance registry entry count mismatch")
        require(
            registry_payload["entries"][0]["control_plane_provider_id"] == control_plane_provider_id,
            "remote governance registry control plane id mismatch",
        )
        require(
            registry_payload["entries"][0]["capabilities"] == ["compat.mcp.call", "compat.a2a.forward"],
            "remote governance registry capabilities mismatch",
        )

        output = run_python(
            ROOT / "aios" / "shell" / "shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "remote-governance",
            "model",
        )
        final_panel = json.loads(output)
        require(
            final_panel["meta"]["matched_entry_count"] == 1,
            "remote governance final matched entry count mismatch",
        )
        require(
            final_panel["meta"]["control_plane_registered_count"] == 1,
            "remote governance final promoted count mismatch",
        )
        require(
            final_panel["meta"]["request_provider_ref"] == "mcp.remote.entry",
            "remote governance final request provider ref mismatch",
        )

        print("remote governance entry smoke passed")
        return 0
    except Exception as error:  # noqa: BLE001
        failed = True
        print(f"remote governance entry smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
