#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


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
    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-clients-"))
    failed = False
    try:
        recovery_surface = temp_root / "recovery-surface.json"
        recovery_surface.write_text(
            json.dumps(
                {
                    "service_id": "aios-updated",
                    "overall_status": "ready",
                    "deployment_status": "apply-triggered",
                    "rollback_ready": True,
                    "current_slot": "b",
                    "last_good_slot": "a",
                    "staged_slot": "b",
                    "available_actions": ["check-updates", "rollback"],
                }
            )
        )
        session_fixture = temp_root / "session-fixture.json"
        output = run_python(
            ROOT / "aios/shell/components/launcher/client.py",
            "create-session",
            "--fixture",
            str(session_fixture),
            "--user-id",
            "user-1",
            "--intent",
            "open docs",
        )
        require("session_id: session-1" in output, "launcher client create-session mismatch")
        output = run_python(
            ROOT / "aios/shell/components/launcher/client.py",
            "resume",
            "--fixture",
            str(session_fixture),
            "--session-id",
            "session-1",
        )
        require("recovery_id: recovery-session-1" in output, "launcher client resume mismatch")

        task_fixture = temp_root / "task-fixture.json"
        task_fixture.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "task_id": "task-1",
                            "session_id": "session-1",
                            "state": "planned",
                            "title": "open docs",
                            "created_at": "2026-03-08T00:00:00Z",
                        },
                        {
                            "task_id": "task-2",
                            "session_id": "session-1",
                            "state": "in_progress",
                            "title": "summarize docs",
                            "created_at": "2026-03-08T00:01:00Z",
                        }
                    ],
                    "plans": {
                        "task-1": {
                            "steps": [
                                {"step": "open docs", "status": "in_progress"}
                            ]
                        }
                    },
                    "events": {
                        "task-1": [
                            {
                                "event_id": "evt-task-1-created",
                                "task_id": "task-1",
                                "from_state": "created",
                                "to_state": "planned",
                                "metadata": {"reason": None},
                                "created_at": "2026-03-08T00:00:00Z",
                            },
                            {
                                "event_id": "evt-task-1-approved",
                                "task_id": "task-1",
                                "from_state": "planned",
                                "to_state": "approved",
                                "metadata": {"reason": "user confirmed"},
                                "created_at": "2026-03-08T00:02:00Z",
                            },
                        ]
                    },
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/task-surface/client.py",
            "summary",
            "--fixture",
            str(task_fixture),
            "--session-id",
            "session-1",
        )
        require("total: 2" in output, "task client summary total mismatch")
        require('"in_progress": 1' in output and '"planned": 1' in output, "task client summary state mismatch")
        output = run_python(
            ROOT / "aios/shell/components/task-surface/client.py",
            "events",
            "--fixture",
            str(task_fixture),
            "--task-id",
            "task-1",
        )
        require("planned -> approved" in output, "task client events output mismatch")
        require("reason=user confirmed" in output, "task client events reason mismatch")
        output = run_python(
            ROOT / "aios/shell/components/task-surface/client.py",
            "update",
            "--fixture",
            str(task_fixture),
            "--task-id",
            "task-1",
            "--state",
            "approved",
        )
        require("state: approved" in output, "task client update mismatch")

        approval_fixture = temp_root / "approvals.json"
        output = run_python(
            ROOT / "aios/shell/components/approval-panel/client.py",
            "create",
            "--fixture",
            str(approval_fixture),
            "--user-id",
            "user-1",
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--capability-id",
            "device.capture.audio",
            "--approval-lane",
            "high-risk",
        )
        require("approval_ref: approval-1" in output, "approval client create mismatch")
        output = run_python(
            ROOT / "aios/shell/components/approval-panel/client.py",
            "summary",
            "--fixture",
            str(approval_fixture),
        )
        require("total: 1" in output, "approval client summary total mismatch")
        require('"pending": 1' in output, "approval client summary status mismatch")
        output = run_python(
            ROOT / "aios/shell/components/approval-panel/client.py",
            "resolve",
            "--fixture",
            str(approval_fixture),
            "--approval-ref",
            "approval-1",
            "--status",
            "approved",
        )
        require("status: approved" in output, "approval client resolve mismatch")

        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/client.py",
            "summary",
            "--surface",
            str(recovery_surface),
        )
        require("deployment: apply-triggered" in output, "recovery client summary missing deployment state")
        require("action_count: 2" in output, "recovery client summary missing action count")

        indicator_state = temp_root / "indicator-state.json"
        indicator_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-08T00:00:00Z",
                    "active": [
                        {
                            "indicator_id": "indicator-1",
                            "capture_id": "cap-1",
                            "modality": "screen",
                            "message": "Screen capture active",
                            "continuous": False,
                            "started_at": "2026-03-08T00:00:00Z",
                            "approval_status": "approved",
                        }
                    ],
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/capture-indicators/client.py",
            "status",
            "--path",
            str(indicator_state),
        )
        require("screen: Screen capture active [approved]" in output, "capture client output mismatch")

        backend_state = temp_root / "backend-state.json"
        backend_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-08T00:00:00Z",
                    "statuses": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "available": False,
                            "readiness": "missing-session-bus",
                            "details": ["dbus_session_bus=false"],
                        },
                        {
                            "modality": "audio",
                            "backend": "pipewire",
                            "available": True,
                            "readiness": "native-live",
                            "details": ["probe_source=probe-command"],
                        },
                        {
                            "modality": "input",
                            "backend": "libinput",
                            "available": True,
                            "readiness": "native-state-bridge",
                            "details": ["input_root=/dev/input"],
                        },
                    ],
                    "adapters": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "adapter_id": "screen.builtin-preview",
                            "execution_path": "builtin-preview",
                            "preview_object_kind": "screen_frame",
                            "notes": ["falling back to builtin preview"],
                        },
                        {
                            "modality": "audio",
                            "backend": "pipewire",
                            "adapter_id": "audio.pipewire-probe",
                            "execution_path": "native-live",
                            "preview_object_kind": "audio_chunk",
                            "notes": ["probe_payload=true"],
                        },
                        {
                            "modality": "input",
                            "backend": "libinput",
                            "adapter_id": "input.libinput-state-root",
                            "execution_path": "native-state-bridge",
                            "preview_object_kind": "input_event_batch",
                            "notes": ["input_root=/dev/input"],
                        },
                    ],
                    "notes": ["available_backends=2", "backend_count=3"],
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/device-backend-status/client.py",
            "attention",
            "--fixture",
            str(backend_state),
        )
        require("screen-capture-portal [missing-session-bus]" in output, "backend client attention missing screen backend")
        require("audio.pipewire-probe" not in output, "backend client attention should hide native-live backend")
        require("input.libinput-state-root" not in output, "backend client attention should hide native-state-bridge backend")

        approval_fixture = temp_root / "approvals.json"
        approval_fixture.write_text(
            json.dumps(
                {
                    "approvals": [
                        {
                            "approval_ref": "approval-1",
                            "task_id": "task-1",
                            "capability_id": "device.capture.audio",
                            "status": "pending",
                        }
                    ]
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/notification-center/client.py",
            "summary",
            "--recovery-surface",
            str(recovery_surface),
            "--indicator-state",
            str(indicator_state),
            "--backend-state",
            str(backend_state),
            "--approval-fixture",
            str(approval_fixture),
        )
        require("total: 5" in output, "notification client summary total mismatch")
        require('"high": 2' in output, "notification client summary severity mismatch")
        require('"updated": 2' in output, "notification client summary source mismatch")

        print("shell client smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell client smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
