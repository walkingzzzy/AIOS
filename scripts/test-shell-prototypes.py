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
    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-prototypes-"))
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
        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/prototype.py",
            "status",
            "--surface",
            str(recovery_surface),
        )
        require("current_slot: b" in output, "recovery surface status output missing current slot")
        require("rollback_ready: True" in output, "recovery surface status output missing rollback flag")

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
            ROOT / "aios/shell/components/capture-indicators/prototype.py",
            "--path",
            str(indicator_state),
        )
        require("screen: Screen capture active [approved]" in output, "capture indicator output mismatch")

        backend_state = temp_root / "backend-state.json"
        backend_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-08T00:00:00Z",
                    "statuses": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "available": True,
                            "readiness": "native-state-bridge",
                            "details": ["screencast_state=/tmp/screencast-state.json"],
                        },
                        {
                            "modality": "audio",
                            "backend": "pipewire",
                            "available": True,
                            "readiness": "native-state-bridge",
                            "details": ["pipewire_node=/tmp/pipewire-node.json"],
                        },
                        {
                            "modality": "input",
                            "backend": "libinput",
                            "available": True,
                            "readiness": "native-state-bridge",
                            "details": ["input_root=/dev/input"],
                        },
                        {
                            "modality": "camera",
                            "backend": "pipewire-camera",
                            "available": False,
                            "readiness": "disabled",
                            "details": ["camera_enabled=false"],
                        },
                        {
                            "modality": "ui_tree",
                            "backend": "at-spi",
                            "available": True,
                            "readiness": "native-state-bridge",
                            "details": ["ui_tree_state=/tmp/ui-tree-state.json"],
                        },
                    ],
                    "adapters": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "adapter_id": "screen.portal-state-file",
                            "execution_path": "native-state-bridge",
                            "preview_object_kind": "screen_frame",
                            "notes": ["screencast_state=/tmp/screencast-state.json"],
                        },
                        {
                            "modality": "audio",
                            "backend": "pipewire",
                            "adapter_id": "audio.pipewire-state-root",
                            "execution_path": "native-state-bridge",
                            "preview_object_kind": "audio_chunk",
                            "notes": ["pipewire_node=/tmp/pipewire-node.json"],
                        },
                    ],
                    "notes": ["available_backends=4", "backend_count=5"],
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/device-backend-status/prototype.py",
            "--fixture",
            str(backend_state),
        )
        require("screen-capture-portal [native-state-bridge]" in output, "backend status output missing screen backend")
        require("camera: pipewire-camera [disabled] available=False" in output, "backend status output missing camera backend")
        require("adapter: screen -> screen.portal-state-file [native-state-bridge]" in output, "backend status output missing adapter line")
        require("note: backend_count=5" in output, "backend status output missing notes")

        approval_fixture = temp_root / "approvals.json"
        approval_fixture.write_text(
            json.dumps(
                {
                    "approvals": [
                        {
                            "approval_ref": "approval-1",
                            "user_id": "user-1",
                            "session_id": "session-1",
                            "task_id": "task-1",
                            "capability_id": "device.capture.audio",
                            "approval_lane": "high-risk",
                            "status": "pending",
                            "execution_location": "local",
                            "created_at": "2026-03-08T00:00:00Z",
                            "reason": "microphone request",
                        }
                    ]
                }
            )
        )

        backend_attention_state = temp_root / "backend-attention.json"
        backend_attention_state.write_text(
            json.dumps(
                {
                    "statuses": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "available": False,
                            "readiness": "missing-session-bus",
                            "details": ["dbus_session_bus=false"],
                        }
                    ],
                    "adapters": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "adapter_id": "screen.builtin-preview",
                            "execution_path": "builtin-preview",
                            "preview_object_kind": "screen_frame",
                            "notes": ["falling back to builtin preview"],
                        }
                    ],
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/notification-center/prototype.py",
            "--recovery-surface",
            str(recovery_surface),
            "--indicator-state",
            str(indicator_state),
            "--backend-state",
            str(backend_attention_state),
            "--approval-fixture",
            str(approval_fixture),
        )
        require("Approval pending: device.capture.audio" in output, "notification center missing approval item")
        require("Screen capture active" in output, "notification center missing capture item")
        require("Deployment state: apply-triggered" in output, "notification center missing recovery item")
        require("Backend attention: screen is missing-session-bus" in output, "notification center missing backend item")

        approval_fixture = temp_root / "approvals.json"
        approval_fixture.write_text(
            json.dumps(
                {
                    "approvals": [
                        {
                            "approval_ref": "approval-1",
                            "user_id": "user-1",
                            "session_id": "session-1",
                            "task_id": "task-1",
                            "capability_id": "device.capture.audio",
                            "approval_lane": "high-risk",
                            "status": "pending",
                            "execution_location": "local",
                            "created_at": "2026-03-08T00:00:00Z",
                            "reason": "microphone request",
                        }
                    ]
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/approval-panel/prototype.py",
            "list",
            "--fixture",
            str(approval_fixture),
        )
        require("approval-1" in output and "pending" in output, "approval list output mismatch")
        output = run_python(
            ROOT / "aios/shell/components/approval-panel/prototype.py",
            "resolve",
            "--fixture",
            str(approval_fixture),
            "--approval-ref",
            "approval-1",
            "--status",
            "approved",
        )
        require('"status": "approved"' in output, "approval resolve output mismatch")

        session_fixture = temp_root / "session-fixture.json"
        output = run_python(
            ROOT / "aios/shell/components/launcher/prototype.py",
            "create-session",
            "--fixture",
            str(session_fixture),
            "--user-id",
            "user-1",
            "--intent",
            "open docs",
        )
        require('"session_id": "session-1"' in output, "launcher output missing session")
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
                            }
                        ]
                    },
                }
            )
        )
        output = run_python(
            ROOT / "aios/shell/components/task-surface/prototype.py",
            "list",
            "--fixture",
            str(task_fixture),
            "--session-id",
            "session-1",
        )
        require("task-1" in output and "planned" in output, "task surface list output mismatch")
        output = run_python(
            ROOT / "aios/shell/components/task-surface/prototype.py",
            "update",
            "--fixture",
            str(task_fixture),
            "--task-id",
            "task-1",
            "--state",
            "approved",
            "--reason",
            "smoke",
        )
        require('"state": "approved"' in output, "task surface update output mismatch")
        output = run_python(
            ROOT / "aios/shell/components/task-surface/prototype.py",
            "plan",
            "--fixture",
            str(task_fixture),
            "--task-id",
            "task-1",
        )
        require('"steps"' in output, "task plan output mismatch")
        output = run_python(
            ROOT / "aios/shell/components/task-surface/prototype.py",
            "events",
            "--fixture",
            str(task_fixture),
            "--task-id",
            "task-1",
        )
        require("created -> planned" in output, "task events output mismatch")

        print("shell prototype smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell prototype smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
