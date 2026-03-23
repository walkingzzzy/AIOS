"""Unified media capture abstraction for deviced.

Provides a coordination layer for audio, video, input-event, and screen
capture sessions.  No actual media processing is performed — the module
orchestrates external capture tools and exposes machine-readable state
for the deviced health subsystem.
"""

from __future__ import annotations

import abc
import atexit
import enum
import json
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class CaptureKind(enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"
    INPUT = "input"
    SCREEN = "screen"


class SessionState(enum.Enum):
    IDLE = "idle"
    PROBING = "probing"
    CAPTURING = "capturing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True)
class ProbeResult:
    """Snapshot of backend availability returned by ``probe()``."""
    available: bool
    kind: CaptureKind
    backend_name: str
    device_paths: List[str] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass
class CaptureConfig:
    """Per-session capture parameters passed to ``start_capture``."""
    device: Optional[str] = None
    format: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    resolution: Optional[str] = None
    framerate: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class CaptureStatus:
    """Instantaneous status snapshot for a capture session."""
    session_id: str
    state: SessionState
    backend: str
    kind: CaptureKind
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    frames_captured: int = 0
    bytes_captured: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        d["kind"] = self.kind.value
        return d


@dataclass
class CaptureEvidence:
    """Machine-readable evidence block for validation pipelines."""
    session_id: str
    backend: str
    kind: CaptureKind
    probe_result: Dict[str, Any]
    status: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


# ---------------------------------------------------------------------------
# Abstract capture backend
# ---------------------------------------------------------------------------

class CaptureBackend(abc.ABC):
    """Base class for media capture backends.

    Each concrete backend wraps a Linux capture subsystem and exposes a
    uniform lifecycle: *probe → start → stop → evidence*.
    """

    def __init__(self, kind: CaptureKind, name: str) -> None:
        self._kind = kind
        self._name = name
        self._state = SessionState.IDLE
        self._session_id: Optional[str] = None
        self._started_at: Optional[float] = None
        self._stopped_at: Optional[float] = None
        self._frames: int = 0
        self._bytes: int = 0
        self._error: Optional[str] = None
        self._probe_cache: Optional[ProbeResult] = None
        self._lock = threading.Lock()

    # -- public properties --------------------------------------------------

    @property
    def kind(self) -> CaptureKind:
        return self._kind

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> SessionState:
        return self._state

    # -- abstract interface -------------------------------------------------

    @abc.abstractmethod
    def _do_probe(self) -> ProbeResult:
        """Backend-specific availability probe."""

    @abc.abstractmethod
    def _do_start(self, config: CaptureConfig) -> None:
        """Backend-specific capture start."""

    @abc.abstractmethod
    def _do_stop(self) -> None:
        """Backend-specific capture stop."""

    # -- public API ---------------------------------------------------------

    def probe(self) -> ProbeResult:
        with self._lock:
            self._state = SessionState.PROBING
            try:
                self._probe_cache = self._do_probe()
            except Exception as exc:
                self._probe_cache = ProbeResult(
                    available=False,
                    kind=self._kind,
                    backend_name=self._name,
                    error=str(exc),
                )
            self._state = SessionState.IDLE
            return self._probe_cache

    def start_capture(self, config: CaptureConfig | None = None) -> str:
        config = config or CaptureConfig()
        with self._lock:
            if self._state == SessionState.CAPTURING:
                raise RuntimeError(f"{self._name}: already capturing")
            self._session_id = str(uuid.uuid4())
            self._started_at = time.time()
            self._stopped_at = None
            self._frames = 0
            self._bytes = 0
            self._error = None
            try:
                self._do_start(config)
                self._state = SessionState.CAPTURING
            except Exception as exc:
                self._state = SessionState.ERROR
                self._error = str(exc)
                raise
            return self._session_id

    def stop_capture(self) -> None:
        with self._lock:
            if self._state != SessionState.CAPTURING:
                return
            self._state = SessionState.STOPPING
            try:
                self._do_stop()
            except Exception as exc:
                self._error = str(exc)
            finally:
                self._stopped_at = time.time()
                self._state = SessionState.STOPPED

    def get_status(self) -> CaptureStatus:
        with self._lock:
            return CaptureStatus(
                session_id=self._session_id or "",
                state=self._state,
                backend=self._name,
                kind=self._kind,
                started_at=self._started_at,
                stopped_at=self._stopped_at,
                frames_captured=self._frames,
                bytes_captured=self._bytes,
                error=self._error,
            )

    def get_evidence(self) -> CaptureEvidence:
        status = self.get_status()
        return CaptureEvidence(
            session_id=status.session_id,
            backend=self._name,
            kind=self._kind,
            probe_result=self._probe_cache.to_dict() if self._probe_cache else {},
            status=status.to_dict(),
        )


# ---------------------------------------------------------------------------
# PipeWire audio capture backend
# ---------------------------------------------------------------------------

class PipeWireCaptureBackend(CaptureBackend):
    """Audio capture via PipeWire (wpctl / pw-cli)."""

    def __init__(self) -> None:
        super().__init__(CaptureKind.AUDIO, "pipewire")
        self._capture_node_id: Optional[str] = None

    def _do_probe(self) -> ProbeResult:
        import shutil
        import subprocess

        wpctl = shutil.which("wpctl")
        pw_cli = shutil.which("pw-cli")

        if not (wpctl or pw_cli):
            return ProbeResult(
                available=False,
                kind=self._kind,
                backend_name=self._name,
                error="neither wpctl nor pw-cli found on PATH",
            )

        devices: List[str] = []
        caps: Dict[str, Any] = {"wpctl": wpctl is not None, "pw_cli": pw_cli is not None}

        if wpctl:
            try:
                result = subprocess.run(
                    [wpctl, "status"],
                    capture_output=True, text=True, timeout=5,
                )
                caps["wpctl_status_ok"] = result.returncode == 0
            except Exception:
                caps["wpctl_status_ok"] = False

        return ProbeResult(
            available=True,
            kind=self._kind,
            backend_name=self._name,
            device_paths=devices,
            capabilities=caps,
        )

    def _do_start(self, config: CaptureConfig) -> None:
        # In a real deployment pw-record would be spawned as a subprocess
        # streaming audio into a ring buffer.  This coordination layer only
        # records that capture has logically started.
        self._capture_node_id = config.device

    def _do_stop(self) -> None:
        self._capture_node_id = None


# ---------------------------------------------------------------------------
# V4L2 video capture backend
# ---------------------------------------------------------------------------

class V4L2CaptureBackend(CaptureBackend):
    """Video capture via v4l2 (v4l2-ctl / ffmpeg)."""

    def __init__(self) -> None:
        super().__init__(CaptureKind.VIDEO, "v4l2")
        self._device_path: Optional[str] = None

    def _do_probe(self) -> ProbeResult:
        import glob
        import shutil

        v4l2_ctl = shutil.which("v4l2-ctl")
        ffmpeg = shutil.which("ffmpeg")
        video_devs = sorted(glob.glob("/dev/video*"))

        if not video_devs:
            return ProbeResult(
                available=False,
                kind=self._kind,
                backend_name=self._name,
                error="no /dev/video* devices found",
            )

        return ProbeResult(
            available=True,
            kind=self._kind,
            backend_name=self._name,
            device_paths=video_devs,
            capabilities={
                "v4l2_ctl": v4l2_ctl is not None,
                "ffmpeg": ffmpeg is not None,
                "device_count": len(video_devs),
            },
        )

    def _do_start(self, config: CaptureConfig) -> None:
        self._device_path = config.device or "/dev/video0"

    def _do_stop(self) -> None:
        self._device_path = None


# ---------------------------------------------------------------------------
# Libinput input-event capture backend
# ---------------------------------------------------------------------------

class LibinputCaptureBackend(CaptureBackend):
    """Input event capture via libinput."""

    def __init__(self) -> None:
        super().__init__(CaptureKind.INPUT, "libinput")

    def _do_probe(self) -> ProbeResult:
        import glob
        import shutil

        libinput = shutil.which("libinput")
        input_devs = sorted(glob.glob("/dev/input/event*"))

        return ProbeResult(
            available=libinput is not None and len(input_devs) > 0,
            kind=self._kind,
            backend_name=self._name,
            device_paths=input_devs,
            capabilities={
                "libinput": libinput is not None,
                "device_count": len(input_devs),
            },
            error=None if libinput else "libinput binary not found",
        )

    def _do_start(self, config: CaptureConfig) -> None:
        pass  # coordination-only

    def _do_stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# XDG portal screen capture backend
# ---------------------------------------------------------------------------

class PortalScreenCaptureBackend(CaptureBackend):
    """Screen capture via the XDG Desktop Portal (D-Bus)."""

    PORTAL_DEST = "org.freedesktop.portal.Desktop"
    SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"

    def __init__(self) -> None:
        super().__init__(CaptureKind.SCREEN, "xdg-portal")

    def _do_probe(self) -> ProbeResult:
        import shutil
        import os

        has_dbus = "DBUS_SESSION_BUS_ADDRESS" in os.environ
        gdbus = shutil.which("gdbus")

        return ProbeResult(
            available=has_dbus and gdbus is not None,
            kind=self._kind,
            backend_name=self._name,
            capabilities={
                "dbus_session": has_dbus,
                "gdbus": gdbus is not None,
                "portal_dest": self.PORTAL_DEST,
            },
            error=None if has_dbus else "D-Bus session bus not available",
        )

    def _do_start(self, config: CaptureConfig) -> None:
        pass  # coordination-only

    def _do_stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Capture session wrapper
# ---------------------------------------------------------------------------

class MediaCaptureSession:
    """Represents a single active (or completed) capture session."""

    def __init__(self, backend: CaptureBackend) -> None:
        self._backend = backend
        self._session_id: Optional[str] = None

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def backend(self) -> CaptureBackend:
        return self._backend

    def start(self, config: CaptureConfig | None = None) -> str:
        self._session_id = self._backend.start_capture(config)
        return self._session_id

    def stop(self) -> None:
        self._backend.stop_capture()

    def status(self) -> CaptureStatus:
        return self._backend.get_status()

    def evidence(self) -> CaptureEvidence:
        return self._backend.get_evidence()

    def __enter__(self) -> "MediaCaptureSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class MediaCaptureManager:
    """Orchestrates multiple concurrent capture sessions and exports
    machine-readable state for deviced health reporting."""

    _instance: Optional["MediaCaptureManager"] = None

    def __init__(self) -> None:
        self._sessions: Dict[str, MediaCaptureSession] = {}
        self._lock = threading.Lock()
        self._shutdown = False

        self._prev_sigterm = signal.getsignal(signal.SIGTERM)
        self._prev_sigint = signal.getsignal(signal.SIGINT)

        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (OSError, ValueError):
            pass  # non-main thread or unsupported platform

        atexit.register(self.shutdown)

    # -- singleton accessor (optional) --------------------------------------

    @classmethod
    def get_instance(cls) -> "MediaCaptureManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- session lifecycle --------------------------------------------------

    def create_session(self, backend: CaptureBackend) -> MediaCaptureSession:
        session = MediaCaptureSession(backend)
        return session

    def register_session(self, session: MediaCaptureSession) -> None:
        with self._lock:
            sid = session.session_id
            if sid is None:
                raise ValueError("session has not been started yet")
            self._sessions[sid] = session

    def start_session(
        self,
        backend: CaptureBackend,
        config: CaptureConfig | None = None,
    ) -> MediaCaptureSession:
        session = self.create_session(backend)
        session.start(config)
        self.register_session(session)
        return session

    def stop_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session:
            session.stop()

    def remove_session(self, session_id: str) -> Optional[MediaCaptureSession]:
        with self._lock:
            return self._sessions.pop(session_id, None)

    # -- bulk operations ----------------------------------------------------

    def active_sessions(self) -> List[MediaCaptureSession]:
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.backend.state == SessionState.CAPTURING
            ]

    def all_sessions(self) -> List[MediaCaptureSession]:
        with self._lock:
            return list(self._sessions.values())

    # -- health export ------------------------------------------------------

    def health_snapshot(self) -> Dict[str, Any]:
        """Machine-readable health payload for deviced."""
        with self._lock:
            sessions_data = []
            for s in self._sessions.values():
                sessions_data.append(s.status().to_dict())
            return {
                "subsystem": "media_capture",
                "session_count": len(self._sessions),
                "active_count": sum(
                    1 for s in self._sessions.values()
                    if s.backend.state == SessionState.CAPTURING
                ),
                "sessions": sessions_data,
            }

    def export_evidence(self) -> List[Dict[str, Any]]:
        """Export evidence blocks for all tracked sessions."""
        with self._lock:
            return [s.evidence().to_dict() for s in self._sessions.values()]

    # -- cleanup ------------------------------------------------------------

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        with self._lock:
            ids = list(self._sessions.keys())
        for sid in ids:
            self.stop_session(sid)
        with self._lock:
            self._sessions.clear()
        self._restore_signals()

    def _signal_handler(self, signum: int, frame: Any) -> None:
        self.shutdown()
        prev = self._prev_sigterm if signum == signal.SIGTERM else self._prev_sigint
        if callable(prev):
            prev(signum, frame)

    def _restore_signals(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self._prev_sigterm)
            signal.signal(signal.SIGINT, self._prev_sigint)
        except (OSError, ValueError):
            pass

    def __enter__(self) -> "MediaCaptureManager":
        return self

    def __exit__(self, *exc: object) -> None:
        self.shutdown()


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

ALL_BACKENDS: Sequence[type[CaptureBackend]] = (
    PipeWireCaptureBackend,
    V4L2CaptureBackend,
    LibinputCaptureBackend,
    PortalScreenCaptureBackend,
)


def create_all_backends() -> List[CaptureBackend]:
    """Instantiate one of each known capture backend."""
    return [cls() for cls in ALL_BACKENDS]
