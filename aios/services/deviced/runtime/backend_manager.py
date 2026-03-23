#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_IDS = (
    "screen.portal-native",
    "audio.pipewire-native",
    "input.libinput-native",
    "camera.v4l-native",
    "ui_tree.atspi-native",
)

ADAPTER_CONTRACTS: dict[str, str] = {
    "screen.portal-native": "formal-native-backend",
    "audio.pipewire-native": "formal-native-backend",
    "input.libinput-native": "formal-native-backend",
    "camera.v4l-native": "formal-native-backend",
    "ui_tree.atspi-native": "formal-native-backend",
}

MODALITY_MAP: dict[str, str] = {
    "screen.portal-native": "screen",
    "audio.pipewire-native": "audio",
    "input.libinput-native": "input",
    "camera.v4l-native": "camera",
    "ui_tree.atspi-native": "ui_tree",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_probe(command: list[str], timeout: float = 3.0) -> tuple[bool, str | None]:
    try:
        completed = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False, None
    excerpt = " ".join(completed.stdout.split())[:240]
    return True, excerpt or None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


@dataclass
class ProbeResult:
    available: bool
    readiness: str
    adapter_contract: str
    details: list[str]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "readiness": self.readiness,
            "adapter_contract": self.adapter_contract,
            "details": list(self.details),
            "evidence": dict(self.evidence),
        }


@dataclass
class BackendManager:
    pipewire_socket_path: Path = field(default_factory=lambda: Path(
        os.environ.get("AIOS_DEVICED_PIPEWIRE_SOCKET_PATH", "/run/user/1000/pipewire-0")
    ))
    pipewire_node_path: Path = field(default_factory=lambda: Path(
        os.environ.get("AIOS_DEVICED_PIPEWIRE_NODE_PATH", "/var/lib/aios/deviced/pipewire-node.json")
    ))
    input_device_root: Path = field(default_factory=lambda: Path(
        os.environ.get("AIOS_DEVICED_INPUT_DEVICE_ROOT", "/dev/input")
    ))
    camera_device_root: Path = field(default_factory=lambda: Path(
        os.environ.get("AIOS_DEVICED_CAMERA_DEVICE_ROOT", "/dev")
    ))
    screencast_state_path: Path = field(default_factory=lambda: Path(
        os.environ.get("AIOS_DEVICED_SCREENCAST_STATE_PATH", "/var/lib/aios/deviced/screencast-state.json")
    ))
    ui_tree_state_path: Path = field(default_factory=lambda: Path(
        os.environ.get("AIOS_DEVICED_UI_TREE_STATE_PATH", "/var/lib/aios/deviced/ui-tree-state.json")
    ))

    _probes: dict[str, ProbeResult] = field(default_factory=dict, init=False, repr=False)

    def probe_all(self) -> dict[str, ProbeResult]:
        self._probes = {}
        for backend_id in BACKEND_IDS:
            self._probes[backend_id] = self._dispatch_probe(backend_id)
        return dict(self._probes)

    def probe_backend(self, backend_id: str) -> ProbeResult:
        if backend_id not in BACKEND_IDS:
            raise ValueError(f"unknown backend_id: {backend_id}")
        result = self._dispatch_probe(backend_id)
        self._probes[backend_id] = result
        return result

    def get_readiness_matrix(self) -> list[dict[str, Any]]:
        if not self._probes:
            self.probe_all()
        return [
            {
                "backend_id": backend_id,
                "modality": MODALITY_MAP[backend_id],
                "available": result.available,
                "readiness": result.readiness,
                "adapter_contract": result.adapter_contract,
            }
            for backend_id, result in self._probes.items()
        ]

    def get_backend_state(self) -> dict[str, Any]:
        if not self._probes:
            self.probe_all()
        available_count = sum(1 for r in self._probes.values() if r.available)
        return {
            "generated_at": _utc_now(),
            "backend_count": len(self._probes),
            "available_count": available_count,
            "backends": {bid: r.to_dict() for bid, r in self._probes.items()},
            "readiness_matrix": self.get_readiness_matrix(),
            "notes": [
                f"available_backends={available_count}",
                f"total_backends={len(self._probes)}",
            ],
        }

    def _dispatch_probe(self, backend_id: str) -> ProbeResult:
        dispatch = {
            "screen.portal-native": self._probe_screen_portal,
            "audio.pipewire-native": self._probe_audio_pipewire,
            "input.libinput-native": self._probe_input_libinput,
            "camera.v4l-native": self._probe_camera_v4l,
            "ui_tree.atspi-native": self._probe_ui_tree_atspi,
        }
        return dispatch[backend_id]()

    def _probe_screen_portal(self) -> ProbeResult:
        contract = ADAPTER_CONTRACTS["screen.portal-native"]
        has_session_bus = bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
        state = _read_json(self.screencast_state_path)
        portal_reachable = False
        probe_tool: str | None = None
        probe_excerpt: str | None = None

        if has_session_bus:
            for command in (
                ["gdbus", "introspect", "--session",
                 "--dest", "org.freedesktop.portal.Desktop",
                 "--object-path", "/org/freedesktop/portal/desktop"],
                ["busctl", "--user", "introspect",
                 "org.freedesktop.portal.Desktop",
                 "/org/freedesktop/portal/desktop"],
            ):
                ok, excerpt = _run_probe(command)
                if ok:
                    portal_reachable = True
                    probe_tool = command[0]
                    probe_excerpt = excerpt
                    break

        available = state is not None
        if available:
            readiness = "native-live"
        elif has_session_bus:
            readiness = "native-ready"
        else:
            readiness = "session-unavailable"

        details = [
            f"screencast_state={self.screencast_state_path}",
            f"dbus_session_bus={has_session_bus}",
            f"portal_service_reachable={portal_reachable}",
        ]
        evidence: dict[str, Any] = {
            "collected_at": _utc_now(),
            "dbus_session_bus": has_session_bus,
            "state_present": state is not None,
            "portal_service_reachable": portal_reachable,
        }
        if probe_tool:
            evidence["probe_tool"] = probe_tool
        if probe_excerpt:
            evidence["probe_excerpt"] = probe_excerpt

        return ProbeResult(
            available=available,
            readiness=readiness,
            adapter_contract=contract,
            details=details,
            evidence=evidence,
        )

    def _probe_audio_pipewire(self) -> ProbeResult:
        contract = ADAPTER_CONTRACTS["audio.pipewire-native"]
        socket_present = self.pipewire_socket_path.exists()
        node = _read_json(self.pipewire_node_path)

        probe_tool: str | None = None
        probe_excerpt: str | None = None
        for command in (["wpctl", "status"], ["pw-cli", "ls", "Node"]):
            ok, excerpt = _run_probe(command)
            if ok:
                probe_tool = command[0]
                probe_excerpt = excerpt
                break

        available = socket_present
        readiness = "native-live" if socket_present else "dependency-missing"

        details = [
            f"pipewire_socket={self.pipewire_socket_path}",
            f"socket_present={socket_present}",
        ]
        if node:
            details.append(f"pipewire_node={self.pipewire_node_path}")
        else:
            details.append(f"pipewire_node_missing={self.pipewire_node_path}")

        evidence: dict[str, Any] = {
            "collected_at": _utc_now(),
            "pipewire_socket": str(self.pipewire_socket_path),
            "socket_present": socket_present,
        }
        if probe_tool:
            evidence["probe_tool"] = probe_tool
        if probe_excerpt:
            evidence["probe_excerpt"] = probe_excerpt
        if node:
            evidence["node_id"] = node.get("node_id")

        return ProbeResult(
            available=available,
            readiness=readiness,
            adapter_contract=contract,
            details=details,
            evidence=evidence,
        )

    def _probe_input_libinput(self) -> ProbeResult:
        contract = ADAPTER_CONTRACTS["input.libinput-native"]
        devices = self._enumerate_input_devices()

        probe_tool: str | None = None
        probe_excerpt: str | None = None
        live_devices: list[str] = []

        ok, excerpt = _run_probe(["libinput", "list-devices"])
        if ok and excerpt:
            probe_tool = "libinput"
            probe_excerpt = excerpt
            live_devices = [
                line.split(":", 1)[1].strip()
                for line in (excerpt or "").splitlines()
                if line.startswith("Device:")
            ]

        effective_devices = live_devices or devices
        available = bool(effective_devices)
        readiness = "native-live" if effective_devices else "device-missing"
        backend_origin = "os-native" if live_devices else "state-enumeration"

        details = [
            f"input_root={self.input_device_root}",
            f"device_count={len(effective_devices)}",
            f"backend_origin={backend_origin}",
        ]
        evidence: dict[str, Any] = {
            "collected_at": _utc_now(),
            "state_ref": str(self.input_device_root),
            "device_count": len(effective_devices),
            "backend_origin": backend_origin,
        }
        if probe_tool:
            evidence["probe_tool"] = probe_tool
        if probe_excerpt:
            evidence["probe_excerpt"] = probe_excerpt

        return ProbeResult(
            available=available,
            readiness=readiness,
            adapter_contract=contract,
            details=details,
            evidence=evidence,
        )

    def _probe_camera_v4l(self) -> ProbeResult:
        contract = ADAPTER_CONTRACTS["camera.v4l-native"]
        devices = self._enumerate_camera_devices()

        probe_tool: str | None = None
        probe_excerpt: str | None = None
        live_devices: list[str] = []

        ok, excerpt = _run_probe(["v4l2-ctl", "--list-devices"])
        if ok and excerpt:
            probe_tool = "v4l2-ctl"
            probe_excerpt = excerpt
            live_devices = [
                line.strip()
                for line in (excerpt or "").splitlines()
                if line.strip().startswith("/dev/video")
            ]

        effective_devices = live_devices or devices
        available = bool(effective_devices)
        readiness = "native-live" if effective_devices else "device-missing"
        backend_origin = "os-native" if live_devices else "state-enumeration"

        details = [
            f"camera_root={self.camera_device_root}",
            f"device_count={len(effective_devices)}",
            f"backend_origin={backend_origin}",
        ]
        evidence: dict[str, Any] = {
            "collected_at": _utc_now(),
            "state_ref": str(self.camera_device_root),
            "device_count": len(effective_devices),
            "backend_origin": backend_origin,
        }
        if probe_tool:
            evidence["probe_tool"] = probe_tool
        if probe_excerpt:
            evidence["probe_excerpt"] = probe_excerpt
        if effective_devices:
            evidence["device_path"] = effective_devices[0]

        return ProbeResult(
            available=available,
            readiness=readiness,
            adapter_contract=contract,
            details=details,
            evidence=evidence,
        )

    def _probe_ui_tree_atspi(self) -> ProbeResult:
        contract = ADAPTER_CONTRACTS["ui_tree.atspi-native"]
        has_atspi_bus = bool(os.environ.get("AT_SPI_BUS_ADDRESS"))
        state = _read_json(self.ui_tree_state_path)

        pyatspi_available = False
        try:
            import pyatspi  # type: ignore  # noqa: F401
            pyatspi_available = True
        except Exception:
            pass

        if state is not None:
            available = True
            readiness = "native-live"
        elif has_atspi_bus:
            available = False
            readiness = "native-ready"
        else:
            available = False
            readiness = "session-unavailable"

        details = [
            f"ui_tree_state={self.ui_tree_state_path}",
            f"at_spi_bus={has_atspi_bus}",
            f"pyatspi_available={pyatspi_available}",
        ]
        evidence: dict[str, Any] = {
            "collected_at": _utc_now(),
            "at_spi_bus": has_atspi_bus,
            "state_present": state is not None,
            "pyatspi_available": pyatspi_available,
        }
        if state:
            evidence["snapshot_id"] = state.get("snapshot_id")

        return ProbeResult(
            available=available,
            readiness=readiness,
            adapter_contract=contract,
            details=details,
            evidence=evidence,
        )

    def _enumerate_input_devices(self) -> list[str]:
        root = self.input_device_root
        if not root.exists():
            return []
        return sorted(
            item.name
            for item in root.iterdir()
            if item.name.startswith(("event", "mouse", "kbd"))
        )

    def _enumerate_camera_devices(self) -> list[str]:
        root = self.camera_device_root
        if not root.exists():
            return []
        return sorted(
            str(item)
            for item in root.iterdir()
            if item.name.startswith("video")
        )


def main() -> int:
    manager = BackendManager()
    state = manager.get_backend_state()
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
