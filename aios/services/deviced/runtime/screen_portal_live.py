#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from helper_contract import apply_helper_contract, build_evidence, build_transport


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def probe_portal_service() -> tuple[bool, str | None, str | None]:
    commands = (
        [
            "gdbus",
            "introspect",
            "--session",
            "--dest",
            "org.freedesktop.portal.Desktop",
            "--object-path",
            "/org/freedesktop/portal/desktop",
        ],
        [
            "busctl",
            "--user",
            "introspect",
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
        ],
    )
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=True,
                timeout=3,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        excerpt = " ".join(completed.stdout.split())[:240]
        return True, command[0], excerpt or None
    return False, None, None


def main() -> int:
    state_path = Path(
        os.environ.get(
            "AIOS_DEVICED_SCREENCAST_STATE_PATH",
            "/var/lib/aios/deviced/screencast-state.json",
        )
    )
    has_session_bus = bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
    portal_service_reachable = False
    portal_probe_tool = None
    portal_probe_excerpt = None
    if has_session_bus:
        (
            portal_service_reachable,
            portal_probe_tool,
            portal_probe_excerpt,
        ) = probe_portal_service()

    payload = read_json(state_path)
    base_payload = dict(payload or {})
    backend_origin = "os-native" if portal_service_reachable else "runtime-helper"
    base_payload["release_grade_backend"] = "xdg-desktop-portal-screencast"
    base_payload["release_grade_backend_id"] = "xdg-desktop-portal-screencast"
    base_payload["release_grade_backend_origin"] = backend_origin
    base_payload["release_grade_backend_stack"] = "portal+pipewire"
    base_payload["release_grade_contract_kind"] = "release-grade-runtime-helper"
    base_payload["adapter_hint"] = "screen.portal-native"
    base_payload["portal_service_reachable"] = portal_service_reachable
    if portal_probe_tool is not None:
        base_payload["portal_service_probe_tool"] = portal_probe_tool
    if portal_probe_excerpt is not None:
        base_payload["portal_service_probe_excerpt"] = portal_probe_excerpt

    base_payload = apply_helper_contract(
        base_payload,
        modality="screen",
        release_grade_backend="xdg-desktop-portal-screencast",
        release_grade_backend_id="xdg-desktop-portal-screencast",
        release_grade_backend_origin=backend_origin,
        release_grade_backend_stack="portal+pipewire",
        adapter_hint="screen.portal-native",
        collector="screen.portal-live",
        transport=build_transport(
            "portal+pipewire",
            endpoint=str(state_path),
            stream_ref=(
                f"pipewire-node:{base_payload.get('stream_node_id')}"
                if base_payload.get("stream_node_id") is not None
                else None
            ),
            details={
                "dbus_session_bus": has_session_bus,
                "portal_session_ref": base_payload.get("portal_session_ref"),
                "portal_service_reachable": portal_service_reachable,
                "portal_service_probe_tool": portal_probe_tool,
            },
        ),
        evidence=build_evidence(
            state_ref=str(state_path),
            probe_tool=portal_probe_tool,
            probe_excerpt=portal_probe_excerpt,
            details={
                "dbus_session_bus": has_session_bus,
                "state_present": payload is not None,
                "portal_service_reachable": portal_service_reachable,
            },
        ),
    )

    if payload is not None:
        result = {
            "available": True,
            "readiness": "native-live",
            "details": [
                f"screencast_state={state_path}",
                f"dbus_session_bus={has_session_bus}",
                f"portal_service_reachable={portal_service_reachable}",
            ],
            "payload": {
                **base_payload,
                "dbus_session_bus": has_session_bus,
            },
            "source": "deviced-runtime-helper",
        }
    elif has_session_bus:
        result = {
            "available": False,
            "readiness": "native-ready",
            "details": [
                f"screencast_state={state_path}",
                "dbus_session_bus=true",
                f"portal_service_reachable={portal_service_reachable}",
            ],
            "payload": {
                **base_payload,
                "dbus_session_bus": has_session_bus,
            },
            "source": "deviced-runtime-helper",
        }
    else:
        result = {
            "available": False,
            "readiness": "session-unavailable",
            "details": [
                f"screencast_state={state_path}",
                "dbus_session_bus=false",
                "portal_service_reachable=false",
            ],
            "payload": None,
            "source": "deviced-runtime-helper",
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
