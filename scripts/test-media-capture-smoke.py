#!/usr/bin/env python3
"""Smoke tests for the deviced media-capture coordination layer.

Validates:
 1. All four capture backends can be instantiated
 2. Probe results have correct structure
 3. Status reporting works
 4. Evidence export format is valid
 5. Manager can track multiple sessions
 6. Cleanup works properly

Run:  python scripts/test-media-capture-smoke.py
"""

from __future__ import annotations

import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aios.services.deviced.runtime.media_capture import (
    ALL_BACKENDS,
    CaptureBackend,
    CaptureConfig,
    CaptureEvidence,
    CaptureKind,
    CaptureStatus,
    LibinputCaptureBackend,
    MediaCaptureManager,
    MediaCaptureSession,
    PipeWireCaptureBackend,
    PortalScreenCaptureBackend,
    ProbeResult,
    SessionState,
    V4L2CaptureBackend,
    create_all_backends,
)

_pass = 0
_fail = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    if condition:
        _pass += 1
    else:
        _fail += 1


# -----------------------------------------------------------------------
# 1. Backend instantiation
# -----------------------------------------------------------------------

def test_backend_instantiation() -> None:
    print("\n== 1. Backend instantiation ==")
    backends = create_all_backends()
    check("create_all_backends returns 4 backends", len(backends) == 4)

    expected = {
        PipeWireCaptureBackend: ("pipewire", CaptureKind.AUDIO),
        V4L2CaptureBackend: ("v4l2", CaptureKind.VIDEO),
        LibinputCaptureBackend: ("libinput", CaptureKind.INPUT),
        PortalScreenCaptureBackend: ("xdg-portal", CaptureKind.SCREEN),
    }

    for backend in backends:
        cls = type(backend)
        name, kind = expected.get(cls, (None, None))
        check(
            f"{cls.__name__} instantiable",
            isinstance(backend, CaptureBackend),
        )
        check(
            f"{cls.__name__} name={name}",
            backend.name == name,
            f"got {backend.name!r}",
        )
        check(
            f"{cls.__name__} kind={kind}",
            backend.kind == kind,
            f"got {backend.kind!r}",
        )
        check(
            f"{cls.__name__} initial state is IDLE",
            backend.state == SessionState.IDLE,
        )


# -----------------------------------------------------------------------
# 2. Probe result structure
# -----------------------------------------------------------------------

def test_probe_structure() -> None:
    print("\n== 2. Probe result structure ==")
    for backend in create_all_backends():
        result = backend.probe()
        check(
            f"{backend.name} probe returns ProbeResult",
            isinstance(result, ProbeResult),
        )
        check(
            f"{backend.name} probe.kind matches backend",
            result.kind == backend.kind,
        )
        check(
            f"{backend.name} probe.backend_name matches",
            result.backend_name == backend.name,
        )
        check(
            f"{backend.name} probe.available is bool",
            isinstance(result.available, bool),
        )
        check(
            f"{backend.name} probe.device_paths is list",
            isinstance(result.device_paths, list),
        )
        check(
            f"{backend.name} probe.capabilities is dict",
            isinstance(result.capabilities, dict),
        )

        d = result.to_dict()
        check(
            f"{backend.name} probe.to_dict() has required keys",
            all(k in d for k in ("available", "kind", "backend_name")),
        )
        check(
            f"{backend.name} probe.to_dict().kind is string",
            isinstance(d["kind"], str),
        )


# -----------------------------------------------------------------------
# 3. Status reporting
# -----------------------------------------------------------------------

def test_status_reporting() -> None:
    print("\n== 3. Status reporting ==")
    for backend in create_all_backends():
        st = backend.get_status()
        check(
            f"{backend.name} get_status returns CaptureStatus",
            isinstance(st, CaptureStatus),
        )
        check(
            f"{backend.name} status.state == IDLE before start",
            st.state == SessionState.IDLE,
        )
        check(
            f"{backend.name} status.backend matches",
            st.backend == backend.name,
        )
        check(
            f"{backend.name} status.kind matches",
            st.kind == backend.kind,
        )

        d = st.to_dict()
        check(
            f"{backend.name} status.to_dict() serialises enums",
            isinstance(d["state"], str) and isinstance(d["kind"], str),
        )


# -----------------------------------------------------------------------
# 4. Evidence export format
# -----------------------------------------------------------------------

def test_evidence_export() -> None:
    print("\n== 4. Evidence export format ==")
    for backend in create_all_backends():
        backend.probe()
        ev = backend.get_evidence()
        check(
            f"{backend.name} get_evidence returns CaptureEvidence",
            isinstance(ev, CaptureEvidence),
        )
        check(
            f"{backend.name} evidence.backend matches",
            ev.backend == backend.name,
        )
        check(
            f"{backend.name} evidence.kind matches",
            ev.kind == backend.kind,
        )
        check(
            f"{backend.name} evidence.probe_result is dict",
            isinstance(ev.probe_result, dict),
        )

        d = ev.to_dict()
        required_keys = {"session_id", "backend", "kind", "probe_result", "status", "timestamp"}
        check(
            f"{backend.name} evidence.to_dict() keys",
            required_keys.issubset(d.keys()),
            f"missing: {required_keys - d.keys()}" if not required_keys.issubset(d.keys()) else "",
        )
        check(
            f"{backend.name} evidence timestamp > 0",
            d["timestamp"] > 0,
        )


# -----------------------------------------------------------------------
# 5. Manager multi-session tracking
# -----------------------------------------------------------------------

def test_manager_sessions() -> None:
    print("\n== 5. Manager multi-session tracking ==")
    manager = MediaCaptureManager()
    backends = create_all_backends()

    sessions: list[MediaCaptureSession] = []
    for b in backends:
        s = manager.start_session(b)
        sessions.append(s)

    check(
        "manager tracks all sessions",
        len(manager.all_sessions()) == len(backends),
        f"expected {len(backends)}, got {len(manager.all_sessions())}",
    )
    check(
        "all sessions are active",
        len(manager.active_sessions()) == len(backends),
    )

    health = manager.health_snapshot()
    check(
        "health_snapshot has correct keys",
        all(k in health for k in ("subsystem", "session_count", "active_count", "sessions")),
    )
    check(
        "health_snapshot subsystem == media_capture",
        health["subsystem"] == "media_capture",
    )
    check(
        "health_snapshot session_count matches",
        health["session_count"] == len(backends),
    )
    check(
        "health_snapshot active_count matches",
        health["active_count"] == len(backends),
    )

    evidence_list = manager.export_evidence()
    check(
        "export_evidence returns list of dicts",
        isinstance(evidence_list, list) and all(isinstance(e, dict) for e in evidence_list),
    )
    check(
        "export_evidence count matches sessions",
        len(evidence_list) == len(backends),
    )

    first_sid = sessions[0].session_id
    manager.stop_session(first_sid)
    check(
        "after stopping one session, active_count decreases",
        len(manager.active_sessions()) == len(backends) - 1,
    )

    removed = manager.remove_session(first_sid)
    check(
        "remove_session returns the session",
        removed is not None and removed.session_id == first_sid,
    )
    check(
        "after removal, total count decreases",
        len(manager.all_sessions()) == len(backends) - 1,
    )

    manager.shutdown()


# -----------------------------------------------------------------------
# 6. Cleanup
# -----------------------------------------------------------------------

def test_cleanup() -> None:
    print("\n== 6. Cleanup ==")

    manager = MediaCaptureManager()
    backends = create_all_backends()
    for b in backends:
        manager.start_session(b)

    check(
        "sessions active before shutdown",
        len(manager.active_sessions()) == len(backends),
    )

    manager.shutdown()

    check(
        "no sessions after shutdown",
        len(manager.all_sessions()) == 0,
    )

    for b in backends:
        check(
            f"{b.name} state is STOPPED after shutdown",
            b.state == SessionState.STOPPED,
        )

    # context-manager protocol
    with MediaCaptureManager() as mgr:
        backends2 = create_all_backends()
        for b in backends2:
            mgr.start_session(b)
        check(
            "context-manager: sessions active inside block",
            len(mgr.active_sessions()) == len(backends2),
        )

    check(
        "context-manager: sessions cleared after block",
        len(mgr.all_sessions()) == 0,
    )

    # MediaCaptureSession as context manager
    b = PipeWireCaptureBackend()
    with MediaCaptureSession(b) as sess:
        sess.start()
        check(
            "session context-manager: capturing inside block",
            b.state == SessionState.CAPTURING,
        )
    check(
        "session context-manager: stopped after block",
        b.state == SessionState.STOPPED,
    )


# -----------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("Media Capture Smoke Tests")
    print("=" * 60)

    try:
        test_backend_instantiation()
        test_probe_structure()
        test_status_reporting()
        test_evidence_export()
        test_manager_sessions()
        test_cleanup()
    except Exception:
        traceback.print_exc()
        print("\nFATAL: unhandled exception during smoke tests")
        return 1

    print("\n" + "=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed, {_pass + _fail} total")
    print("=" * 60)
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
