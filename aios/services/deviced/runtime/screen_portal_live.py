#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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


def main() -> int:
    state_path = Path(
        os.environ.get(
            "AIOS_DEVICED_SCREENCAST_STATE_PATH",
            "/var/lib/aios/deviced/screencast-state.json",
        )
    )
    has_session_bus = bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
    payload = read_json(state_path)
    base_payload = dict(payload or {})
    base_payload["release_grade_backend"] = "portal-screen-helper"
    base_payload["adapter_hint"] = "screen.portal-native"
    base_payload = apply_helper_contract(
        base_payload,
        modality="screen",
        release_grade_backend="portal-screen-helper",
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
            },
        ),
        evidence=build_evidence(
            state_ref=str(state_path),
            details={
                "dbus_session_bus": has_session_bus,
                "state_present": payload is not None,
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
            ],
            "payload": base_payload,
            "source": "deviced-runtime-helper",
        }
    else:
        result = {
            "available": False,
            "readiness": "session-unavailable",
            "details": [
                f"screencast_state={state_path}",
                "dbus_session_bus=false",
            ],
            "payload": None,
            "source": "deviced-runtime-helper",
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
