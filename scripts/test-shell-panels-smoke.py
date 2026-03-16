#!/usr/bin/env python3
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
    temp_root = make_temp_dir("aios-shell-panels-")
    failed = False
    try:
        recovery_surface = temp_root / "recovery-surface.json"
        recovery_surface.write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-09T00:00:00Z",
                    "service_id": "aios-updated",
                    "overall_status": "degraded",
                    "deployment_status": "apply-triggered",
                    "rollback_ready": True,
                    "current_slot": "b",
                    "last_good_slot": "a",
                    "staged_slot": "b",
                    "recovery_points": ["recovery-100.json", "recovery-200.json"],
                    "diagnostic_bundles": ["bundle-1.json"],
                    "available_actions": ["refresh-health", "check-updates", "rollback", "export-bundle"],
                    "notes": ["boot_reconciled=apply:b", "recovery_point_verified=recovery-200"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

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
                            "state": "approved",
                            "title": "summarize docs",
                            "created_at": "2026-03-08T00:01:00Z",
                        },
                    ],
                    "plans": {
                        "task-1": {
                            "steps": [{"step": "open docs", "status": "in_progress"}],
                            "summary": "Open docs from the shared workspace",
                            "route_preference": "tool-calling",
                            "candidate_capabilities": ["provider.fs.open"],
                            "next_action": "retry",
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
                    "provider_resolutions": {
                        "task-1": {
                            "capability_id": "provider.fs.open",
                            "selected": {
                                "provider_id": "system.files.local",
                                "display_name": "System Files",
                                "kind": "system-provider",
                                "execution_location": "local",
                                "health_status": "available",
                                "disabled": False,
                                "score": 120,
                            },
                            "candidates": [
                                {
                                    "provider_id": "system.files.local",
                                    "display_name": "System Files",
                                    "kind": "system-provider",
                                    "execution_location": "local",
                                    "health_status": "available",
                                    "disabled": False,
                                    "score": 120,
                                }
                            ],
                            "reason": "selected provider system.files.local for provider.fs.open",
                        }
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        compositor_runtime_state = temp_root / "compositor-runtime-state.json"
        compositor_runtime_state.write_text(
            json.dumps(
                {
                    "phase": "ready",
                    "session": {
                        "runtime_state_status": "published(ready)",
                        "window_manager_status": "persistent(saved=2)",
                        "workspace_count": 3,
                        "active_workspace_index": 1,
                        "active_workspace_id": "workspace-2",
                        "active_output_id": "display-2",
                        "managed_window_count": 2,
                        "visible_window_count": 1,
                        "floating_window_count": 1,
                        "minimized_window_count": 1,
                        "window_move_count": 4,
                        "window_resize_count": 2,
                        "window_minimize_count": 1,
                        "window_restore_count": 1,
                        "last_minimized_window_key": "window-beta",
                        "last_restored_window_key": "window-alpha",
                        "workspace_window_counts": {
                            "workspace-1": 1,
                            "workspace-2": 1,
                        },
                        "managed_windows": [
                            {
                                "window_key": "window-alpha",
                                "title": "Docs",
                                "app_id": "org.demo.docs",
                                "output_id": "display-2",
                                "workspace_id": "workspace-2",
                                "window_policy": "workspace-window",
                                "visible": True,
                                "minimized": False,
                            },
                            {
                                "window_key": "window-beta",
                                "title": "Chat",
                                "app_id": "org.demo.chat",
                                "output_id": "display-1",
                                "workspace_id": "workspace-2",
                                "window_policy": "floating-utility",
                                "visible": False,
                                "minimized": True,
                            },
                        ],
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        compositor_window_state = temp_root / "compositor-window-state.json"
        compositor_window_state.write_text(
            json.dumps(
                {
                    "schema": "aios.shell.compositor.window-state/v1",
                    "active_workspace_index": 1,
                    "active_output_id": "display-2",
                    "windows": [
                        {
                            "window_key": "window-alpha",
                            "app_id": "org.demo.docs",
                            "title": "Docs",
                            "slot_id": None,
                            "output_id": "display-2",
                            "workspace_index": 1,
                            "window_policy": "workspace-window",
                            "rect": {"x": 24, "y": 24, "width": 1280, "height": 720},
                            "minimized": False,
                            "last_seen_at_ms": 1,
                        },
                        {
                            "window_key": "window-beta",
                            "app_id": "org.demo.chat",
                            "title": "Chat",
                            "slot_id": None,
                            "output_id": "display-1",
                            "workspace_index": 1,
                            "window_policy": "floating-utility",
                            "rect": {"x": 128, "y": 96, "width": 960, "height": 640},
                            "minimized": True,
                            "last_seen_at_ms": 2,
                        },
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        session_fixture = temp_root / "session-fixture.json"
        session_fixture.write_text(
            json.dumps(
                {
                    "sessions": [
                        {
                            "session_id": "session-1",
                            "user_id": "user-1",
                            "created_at": "2026-03-08T00:00:00Z",
                            "status": "active",
                        }
                    ],
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
                            "state": "approved",
                            "title": "summarize docs",
                            "created_at": "2026-03-08T00:01:00Z",
                        },
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

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
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        indicator_state = temp_root / "indicator-state.json"
        indicator_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-09T00:00:00Z",
                    "notes": ["active_indicators=1"],
                    "active": [
                        {
                            "indicator_id": "indicator-1",
                            "capture_id": "cap-1",
                            "modality": "screen",
                            "message": "Screen capture active",
                            "continuous": False,
                            "started_at": "2026-03-09T00:00:00Z",
                            "approval_status": "approved",
                        }
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        evidence_dir = temp_root / "backend-evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screen_evidence = evidence_dir / "screen-backend-evidence.json"
        screen_evidence.write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-09T00:00:00Z",
                    "service_id": "aios-deviced",
                    "modality": "screen",
                    "backend": "screen-capture-portal",
                    "available": False,
                    "readiness": "missing-session-bus",
                    "source": "fixture-screen-helper",
                    "adapter_id": "screen.builtin-preview",
                    "execution_path": "builtin-preview",
                    "release_grade_backend_id": "xdg-desktop-portal-screencast",
                    "release_grade_backend_origin": "runtime-helper",
                    "release_grade_backend_stack": "portal+pipewire",
                    "contract_kind": "release-grade-runtime-helper",
                    "baseline": "command-adapter",
                    "state_refs": ["/tmp/fixture-screen-state.json"],
                    "probe": {"available": False, "readiness": "missing-session-bus", "source": "fixture-screen-helper"},
                    "baseline_payload": {"portal_session_ref": "portal-fixture-1"},
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        audio_evidence = evidence_dir / "audio-backend-evidence.json"
        audio_evidence.write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-09T00:00:00Z",
                    "service_id": "aios-deviced",
                    "modality": "audio",
                    "backend": "pipewire-audio",
                    "available": True,
                    "readiness": "native-live",
                    "source": "fixture-audio-helper",
                    "adapter_id": "audio.pipewire-live",
                    "execution_path": "native-live",
                    "release_grade_backend_id": "pipewire",
                    "release_grade_backend_origin": "os-native",
                    "release_grade_backend_stack": "pipewire",
                    "contract_kind": "release-grade-runtime-helper",
                    "baseline": "os-native-backend",
                    "state_refs": ["/tmp/fixture-pipewire-node.json"],
                    "probe": {"available": True, "readiness": "native-live", "source": "fixture-audio-helper"},
                    "baseline_payload": {"node_id": 77},
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        backend_state = temp_root / "backend-state.json"
        backend_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-09T00:00:00Z",
                    "statuses": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "available": False,
                            "readiness": "missing-session-bus",
                            "details": [
                                "dbus_session_bus=false",
                                f"evidence_artifact={screen_evidence}",
                            ],
                        },
                        {
                            "modality": "audio",
                            "backend": "pipewire-audio",
                            "available": True,
                            "readiness": "native-live",
                            "details": [f"evidence_artifact={audio_evidence}"],
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
                            "backend": "pipewire-audio",
                            "adapter_id": "audio.pipewire-live",
                            "execution_path": "native-live",
                            "preview_object_kind": "audio_sample",
                            "notes": [],
                        },
                    ],
                    "ui_tree_snapshot": {
                        "snapshot_id": "tree-live-1",
                        "capture_mode": "native-live",
                        "application_count": 1,
                        "focus_node": "desktop-0/app-0/0",
                        "adapter_id": "ui_tree.atspi-probe",
                        "collector": "fixture",
                    },
                    "ui_tree_support_matrix": [
                        {
                            "environment_id": "current-session",
                            "available": True,
                            "readiness": "native-live",
                            "current": True,
                            "details": ["desktop_environment=fixture", "session_type=wayland"],
                        },
                        {
                            "environment_id": "state-bridge",
                            "available": False,
                            "readiness": "missing-state-file",
                            "current": False,
                            "details": ["ui_tree_state_path=/tmp/missing.json"],
                        },
                    ],
                    "backend_summary": {
                        "overall_status": "attention",
                        "status_count": 2,
                        "available_status_count": 1,
                        "adapter_count": 2,
                        "attention_count": 1,
                        "continuous_collector_count": 0,
                        "ui_tree_support_route_count": 2,
                        "ui_tree_support_ready_count": 1,
                        "ui_tree_snapshot_present": True,
                        "ui_tree_capture_mode": "native-live",
                        "ui_tree_current_support": "native-live",
                        "readiness_summary": {
                            "missing-session-bus": 1,
                            "native-live": 1,
                        },
                        "evidence_artifact_count": 2,
                        "evidence_present_count": 2,
                        "evidence_missing_count": 0,
                        "evidence_baselines": [
                            "command-adapter",
                            "os-native-backend",
                        ],
                    },
                    "notes": [
                        "policy_socket_configured=true",
                        f"backend_evidence_dir={evidence_dir}",
                        "backend_evidence_artifact_count=2",
                        f"backend_evidence_artifact[screen]={screen_evidence}",
                        f"backend_evidence_artifact[audio]={audio_evidence}",
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        panel_action_log = temp_root / "panel-action-events.jsonl"
        panel_action_log.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "sequence": 1,
                            "event_id": "panel-action-event-000001",
                            "kind": "panel-action.dispatch",
                            "recorded_at_ms": 1,
                            "tick": 1,
                            "slot_id": "notification-center",
                            "component": "notification-center",
                            "panel_id": "notification-center-panel",
                            "action_id": "refresh",
                            "input_kind": "pointer-button",
                            "focus_policy": "retain-client-focus",
                            "status": "dispatch-ok(refresh)",
                            "summary": "Refresh Feed: status=ready",
                            "error": None,
                            "payload": {"result": {"status": "ready"}},
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "sequence": 2,
                            "event_id": "panel-action-event-000002",
                            "kind": "panel-action.dispatch",
                            "recorded_at_ms": 2,
                            "tick": 2,
                            "slot_id": "approval-panel",
                            "component": "approval-panel",
                            "panel_id": "approval-panel-shell",
                            "action_id": "approve",
                            "input_kind": "pointer-button",
                            "focus_policy": "shell-modal",
                            "status": "dispatch-failed(approve)",
                            "summary": "approval callback failed",
                            "error": "approval callback failed",
                            "payload": {"result": {"status": "failed"}},
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n"
        )

        policy_audit_log = temp_root / "policy-audit.jsonl"
        policy_audit_log.write_text(
            json.dumps(
                {
                    "audit_id": "audit-1",
                    "timestamp": "2026-03-09T00:00:00Z",
                    "user_id": "user-1",
                    "session_id": "session-1",
                    "task_id": "task-remote-1",
                    "capability_id": "compat.browser.navigate",
                    "decision": "denied",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

        runtime_events_log = temp_root / "runtime-events.jsonl"
        runtime_events_log.write_text(
            json.dumps(
                {
                    "event_id": "runtime-1",
                    "kind": "runtime.infer.timeout",
                    "task_id": "task-runtime-1",
                    "backend_id": "remote-gpu",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

        remote_audit_log = temp_root / "remote-audit.jsonl"
        remote_audit_log.write_text(
            json.dumps(
                {
                    "audit_id": "remote-1",
                    "status": "error",
                    "provider_id": "compat.browser.remote.worker",
                    "task_id": "task-remote-2",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

        compat_observability_log = temp_root / "compat-observability.jsonl"
        compat_observability_log.write_text(
            json.dumps(
                {
                    "audit_id": "compat-1",
                    "decision": "allowed",
                    "provider_id": "compat.office.document.local",
                    "task_id": "task-compat-1",
                    "result": {"error_code": "office_remote_pdf_missing"},
                },
                ensure_ascii=False,
            )
            + "\n"
        )

        browser_remote_registry = temp_root / "browser-remote-registry.json"
        browser_remote_registry.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "entries": [
                        {
                            "provider_ref": "browser.remote.worker",
                            "endpoint": "https://browser.remote.example/bridge",
                            "capabilities": ["compat.browser.navigate"],
                            "auth_mode": "bearer",
                            "auth_secret_env": "BROWSER_REMOTE_SECRET",
                            "target_hash": "sha256:browser",
                            "registered_at": "2026-03-09T00:00:00Z",
                            "control_plane_provider_id": "compat.browser.remote.worker",
                            "registration_status": "active",
                            "last_heartbeat_at": "2026-03-09T00:05:00Z",
                            "heartbeat_ttl_seconds": 3600,
                            "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                            "governance": {
                                "fleet_id": "fleet-browser",
                                "governance_group": "operator-audit",
                                "policy_group": "compat-browser-remote",
                                "approval_ref": "approval-browser-1",
                                "registered_by": "panel-smoke",
                                "allow_lateral_movement": False
                            }
                        }
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        office_remote_registry = temp_root / "office-remote-registry.json"
        office_remote_registry.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "entries": [
                        {
                            "provider_ref": "office.remote.worker",
                            "endpoint": "https://office.remote.example/bridge",
                            "capabilities": ["compat.document.open"],
                            "auth_mode": "bearer",
                            "auth_secret_env": "OFFICE_REMOTE_SECRET",
                            "target_hash": "sha256:office",
                            "registered_at": "2026-03-09T00:00:00Z",
                            "control_plane_provider_id": "compat.office.remote.worker",
                            "registration_status": "active",
                            "last_heartbeat_at": "2020-01-01T00:00:00Z",
                            "heartbeat_ttl_seconds": 60,
                            "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                            "governance": {
                                "fleet_id": "fleet-office",
                                "governance_group": "operator-audit",
                                "policy_group": "compat-office-remote",
                                "approval_ref": "approval-office-1",
                                "registered_by": "panel-smoke",
                                "allow_lateral_movement": False
                            }
                        }
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        provider_registry_state_dir = temp_root / "provider-registry"
        descriptor_dir = provider_registry_state_dir / "descriptors"
        health_dir = provider_registry_state_dir / "health"
        descriptor_dir.mkdir(parents=True, exist_ok=True)
        health_dir.mkdir(parents=True, exist_ok=True)
        (descriptor_dir / "compat.browser.remote.worker.json").write_text(
            json.dumps(
                {
                    "provider_id": "compat.browser.remote.worker",
                    "display_name": "Browser Remote Worker",
                    "kind": "compat-provider",
                    "execution_location": "attested_remote",
                    "remote_registration": {
                        "source_provider_id": "compat.browser.automation.local",
                        "provider_ref": "browser.remote.worker",
                        "endpoint": "https://browser.remote.example/bridge",
                        "registration_status": "active",
                        "last_heartbeat_at": "2026-03-09T00:05:00Z",
                        "heartbeat_ttl_seconds": 3600,
                        "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                        "governance": {"fleet_id": "fleet-browser", "governance_group": "operator-audit"}
                    }
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        (health_dir / "compat.browser.remote.worker.json").write_text(
            json.dumps(
                {
                    "provider_id": "compat.browser.remote.worker",
                    "status": "available",
                    "disabled": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        (descriptor_dir / "compat.office.remote.worker.json").write_text(
            json.dumps(
                {
                    "provider_id": "compat.office.remote.worker",
                    "display_name": "Office Remote Worker",
                    "kind": "compat-provider",
                    "execution_location": "attested_remote",
                    "remote_registration": {
                        "source_provider_id": "compat.office.document.local",
                        "provider_ref": "office.remote.worker",
                        "endpoint": "https://office.remote.example/bridge",
                        "registration_status": "active",
                        "last_heartbeat_at": "2026-03-09T00:00:00Z",
                        "heartbeat_ttl_seconds": 3600,
                        "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                        "governance": {"fleet_id": "fleet-office", "governance_group": "operator-audit"}
                    }
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        (health_dir / "compat.office.remote.worker.json").write_text(
            json.dumps(
                {
                    "provider_id": "compat.office.remote.worker",
                    "status": "unavailable",
                    "disabled": False,
                    "last_error": "bridge offline"
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        output = run_python(ROOT / "aios/shell/components/recovery-surface/panel.py", "model", "--surface", str(recovery_surface))
        recovery_model = json.loads(output)
        require(recovery_model["panel_id"] == "recovery-panel", "recovery panel id mismatch")
        require(recovery_model["meta"]["recovery_point_count"] == 2, "recovery panel recovery-point count mismatch")
        require(recovery_model["meta"]["data_source_status"] == "ready", "recovery panel data-source status mismatch")
        require(recovery_model["meta"]["panel_state"] == "operation-pending", "recovery panel state mismatch")

        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/panel.py",
            "action",
            "--surface",
            str(recovery_surface),
            "--socket",
            str(temp_root / "missing-updated.sock"),
            "--action",
            "export-bundle",
            "--reason",
            "panel-smoke-export",
        )
        recovery_export = json.loads(output)
        require(recovery_export["target_component"] == "recovery-surface", "recovery export route mismatch")
        require(recovery_export["route_reason"] == "bundle-exported", "recovery export route reason mismatch")
        require(recovery_export["data_source_mode"] == "surface-file-fallback", "recovery export fallback mode mismatch")
        require(Path(recovery_export["bundle_path"]).exists(), "recovery export bundle path missing")
        require(recovery_export["diagnostic_bundle_count"] == 2, "recovery export bundle count mismatch")

        output = run_python(ROOT / "aios/shell/components/recovery-surface/panel.py", "model", "--surface", str(recovery_surface))
        recovery_export_model = json.loads(output)
        require(recovery_export_model["meta"]["diagnostic_bundle_count"] == 2, "recovery export model bundle count mismatch")

        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/panel.py",
            "action",
            "--surface",
            str(recovery_surface),
            "--socket",
            str(temp_root / "missing-updated.sock"),
            "--action",
            "rollback",
            "--recovery-id",
            "recovery-200",
            "--reason",
            "panel-smoke-rollback",
        )
        recovery_rollback = json.loads(output)
        require(recovery_rollback["target_component"] == "recovery-surface", "recovery rollback route mismatch")
        require(recovery_rollback["route_reason"] == "rollback-issued", "recovery rollback route reason mismatch")
        require(recovery_rollback["status"] == "accepted", "recovery rollback status mismatch")
        require(recovery_rollback["rollback_target"] == "a", "recovery rollback target mismatch")
        require(recovery_rollback["deployment_status"] == "rollback-triggered", "recovery rollback deployment mismatch")

        output = run_python(ROOT / "aios/shell/components/recovery-surface/panel.py", "model", "--surface", str(recovery_surface))
        recovery_rollback_model = json.loads(output)
        rollback_slots = next(section for section in recovery_rollback_model["sections"] if section["section_id"] == "slots")
        require(
            any(item["label"] == "Staged Slot" and item["value"] == "a" for item in rollback_slots["items"]),
            "recovery rollback staged slot mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/recovery-surface/panel.py",
            "model",
            "--surface",
            str(temp_root / "missing-recovery-surface.json"),
            "--socket",
            str(temp_root / "missing-updated.sock"),
        )
        recovery_fallback_model = json.loads(output)
        require(
            recovery_fallback_model["meta"]["data_source_status"] == "fallback-empty",
            "recovery panel fallback status mismatch",
        )
        require(
            bool(recovery_fallback_model["meta"]["data_source_error"]),
            "recovery panel fallback error missing",
        )

        output = run_python(
            ROOT / "aios/shell/components/task-surface/panel.py",
            "model",
            "--fixture",
            str(task_fixture),
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--compositor-runtime-state",
            str(compositor_runtime_state),
            "--compositor-window-state",
            str(compositor_window_state),
        )
        task_model = json.loads(output)
        require(task_model["panel_id"] == "task-panel", "task panel id mismatch")
        require(task_model["meta"]["task_count"] == 2, "task panel task count mismatch")
        require(task_model["meta"]["plan_step_count"] == 1, "task panel plan count mismatch")
        require(task_model["meta"]["task_event_count"] == 2, "task panel event count mismatch")
        require(task_model["meta"]["focus_task_title"] == "open docs", "task panel focus title mismatch")
        require(task_model["meta"]["plan_route_preference"] == "tool-calling", "task panel route preference mismatch")
        require(task_model["meta"]["plan_next_action"] == "retry", "task panel next action mismatch")
        require(task_model["meta"]["primary_capability"] == "provider.fs.open", "task panel primary capability mismatch")
        require(task_model["meta"]["provider_selected_id"] == "system.files.local", "task panel provider selection mismatch")
        require(task_model["meta"]["provider_candidate_count"] == 1, "task panel provider candidate count mismatch")
        require(task_model["meta"]["data_source_status"] == "ready", "task panel data-source status mismatch")
        require(task_model["meta"]["compositor_data_status"] == "ready", "task panel compositor status mismatch")
        require(task_model["meta"]["active_workspace_id"] == "workspace-2", "task panel workspace id mismatch")
        require(task_model["meta"]["managed_window_count"] == 2, "task panel managed window count mismatch")
        require(task_model["meta"]["minimized_window_count"] == 1, "task panel minimized window count mismatch")
        workspace_section = next(
            section for section in task_model["sections"] if section["section_id"] == "workspace-windows"
        )
        require(len(workspace_section["items"]) == 2, "task panel workspace window section mismatch")
        minimized_section = next(
            section for section in task_model["sections"] if section["section_id"] == "minimized-windows"
        )
        require(len(minimized_section["items"]) == 1, "task panel minimized section mismatch")
        require(
            "approved" in task_model["meta"]["recent_task_event_states"],
            "task panel recent event states mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/task-surface/panel.py",
            "model",
            "--socket",
            str(temp_root / "missing-sessiond.sock"),
            "--agent-socket",
            str(temp_root / "missing-agentd.sock"),
            "--session-id",
            "session-missing",
        )
        task_fallback_model = json.loads(output)
        require(task_fallback_model["panel_id"] == "task-panel", "task panel fallback id mismatch")
        require(task_fallback_model["meta"]["task_count"] == 0, "task panel fallback task count mismatch")
        require(
            task_fallback_model["meta"]["data_source_status"] == "fallback-empty",
            "task panel fallback status mismatch",
        )
        require(
            bool(task_fallback_model["meta"]["data_source_error"]),
            "task panel fallback error missing",
        )

        output = run_python(
            ROOT / "aios/shell/components/approval-panel/panel.py",
            "model",
            "--fixture",
            str(approval_fixture),
            "--session-id",
            "session-1",
        )
        approval_model = json.loads(output)
        require(approval_model["panel_id"] == "approval-panel-shell", "approval panel id mismatch")
        require(approval_model["meta"]["approval_count"] == 1, "approval panel count mismatch")
        require(approval_model["meta"]["data_source_status"] == "ready", "approval panel data-source status mismatch")

        output = run_python(
            ROOT / "aios/shell/components/approval-panel/panel.py",
            "model",
            "--socket",
            str(temp_root / "missing-policyd.sock"),
            "--session-id",
            "session-missing",
        )
        approval_fallback_model = json.loads(output)
        require(
            approval_fallback_model["meta"]["approval_count"] == 0,
            "approval panel fallback approval count mismatch",
        )
        require(
            approval_fallback_model["meta"]["data_source_status"] == "fallback-empty",
            "approval panel fallback status mismatch",
        )
        require(
            bool(approval_fallback_model["meta"]["data_source_error"]),
            "approval panel fallback error missing",
        )

        output = run_python(
            ROOT / "aios/shell/components/notification-center/panel.py",
            "model",
            "--recovery-surface",
            str(recovery_surface),
            "--indicator-state",
            str(indicator_state),
            "--backend-state",
            str(backend_state),
            "--panel-action-log",
            str(panel_action_log),
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--approval-fixture",
            str(approval_fixture),
            "--compositor-runtime-state",
            str(compositor_runtime_state),
            "--compositor-window-state",
            str(compositor_window_state),
        )
        notification_model = json.loads(output)
        require(notification_model["panel_id"] == "notification-center-panel", "notification panel id mismatch")
        require(notification_model["meta"]["notification_count"] == 13, "notification panel count mismatch")
        require(notification_model["meta"]["severity_summary"]["high"] == 5, "notification panel severity mismatch")
        require(notification_model["meta"]["source_summary"]["shell"] == 2, "notification panel shell source mismatch")
        require(notification_model["meta"]["source_summary"]["compositor"] == 2, "notification panel compositor source mismatch")
        require(notification_model["meta"]["kind_summary"]["panel-action-error"] == 1, "notification panel shell error kind mismatch")
        require(notification_model["meta"]["operator_audit_issue_count"] == 4, "notification panel operator audit issue mismatch")
        require(notification_model["meta"]["operator_audit_task_count"] == 4, "notification panel operator audit task mismatch")
        require(
            notification_model["meta"]["backend_evidence_present_count"] == 2,
            "notification panel backend evidence count mismatch",
        )
        require(
            sorted(notification_model["meta"]["backend_evidence_backend_ids"])
            == ["pipewire", "xdg-desktop-portal-screencast"],
            "notification panel release-grade backend ids mismatch",
        )
        require(
            notification_model["meta"]["remote_governance_issue_count"] >= 2,
            "notification panel remote governance issue mismatch",
        )
        require(
            notification_model["meta"]["remote_governance_matched_entry_count"] == 2,
            "notification panel remote governance matched count mismatch",
        )
        remote_governance_section = next(
            section for section in notification_model["sections"] if section["section_id"] == "remote-governance"
        )
        require(
            remote_governance_section["items"][1]["value"] >= 2,
            "notification panel remote governance section issue mismatch",
        )
        backend_evidence_section = next(
            section for section in notification_model["sections"] if section["section_id"] == "device-backend-evidence"
        )
        require(
            backend_evidence_section["items"][0]["value"] == 2,
            "notification panel backend evidence section ready mismatch",
        )
        require(
            backend_evidence_section["items"][2]["value"] == "pipewire, xdg-desktop-portal-screencast",
            "notification panel backend evidence ids mismatch",
        )
        window_manager_section = next(
            section for section in notification_model["sections"] if section["section_id"] == "window-manager"
        )
        require(window_manager_section["items"][2]["value"] == "workspace-2", "notification panel workspace section mismatch")
        require(window_manager_section["items"][5]["value"] == 1, "notification panel minimized section mismatch")

        output = run_python(
            ROOT / "aios/shell/components/notification-center/panel.py",
            "action",
            "--recovery-surface",
            str(recovery_surface),
            "--indicator-state",
            str(indicator_state),
            "--backend-state",
            str(backend_state),
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--approval-fixture",
            str(approval_fixture),
            "--compositor-runtime-state",
            str(compositor_runtime_state),
            "--compositor-window-state",
            str(compositor_window_state),
            "--action",
            "inspect-remote-governance",
        )
        notification_action = json.loads(output)
        require(notification_action["enabled"] is True, "notification panel remote governance action disabled")
        require(
            notification_action["target_component"] == "remote-governance",
            "notification panel remote governance action target mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/notification-center/panel.py",
            "action",
            "--recovery-surface",
            str(recovery_surface),
            "--indicator-state",
            str(indicator_state),
            "--backend-state",
            str(backend_state),
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--approval-fixture",
            str(approval_fixture),
            "--compositor-runtime-state",
            str(compositor_runtime_state),
            "--compositor-window-state",
            str(compositor_window_state),
            "--action",
            "inspect-window-manager",
        )
        notification_window_manager_action = json.loads(output)
        require(notification_window_manager_action["enabled"] is True, "notification panel window manager action disabled")
        require(
            notification_window_manager_action["target_component"] == "task-surface",
            "notification panel window manager action target mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/operator-audit/panel.py",
            "model",
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--issue-only",
            "--source",
            "compat",
            "--provider-id",
            "compat.office.document.local",
            "--task-id",
            "task-compat-1",
            "--write-report",
            str(temp_root / "operator-audit-report.json"),
        )
        operator_audit_model = json.loads(output)
        require(operator_audit_model["panel_id"] == "operator-audit-panel", "operator audit panel id mismatch")
        require(operator_audit_model["meta"]["record_count"] == 4, "operator audit panel record count mismatch")
        require(operator_audit_model["meta"]["matched_record_count"] == 1, "operator audit panel matched record count mismatch")
        require(operator_audit_model["meta"]["issue_count"] == 1, "operator audit panel issue count mismatch")
        require(operator_audit_model["meta"]["task_count"] == 1, "operator audit panel task count mismatch")
        require(
            operator_audit_model["meta"]["source_counts"]["compat"] == 1,
            "operator audit panel compat source count mismatch",
        )
        require(
            operator_audit_model["meta"]["issue_only"] is True,
            "operator audit panel issue-only flag mismatch",
        )
        require(
            operator_audit_model["meta"]["filters"]["provider_id"] == "compat.office.document.local",
            "operator audit panel provider filter mismatch",
        )
        require(
            operator_audit_model["meta"]["query"]["report_path"] == str(temp_root / "operator-audit-report.json"),
            "operator audit panel report path mismatch",
        )
        require(
            operator_audit_model["meta"]["filtered_source_counts"]["compat"] == 1,
            "operator audit panel filtered source count mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/operator-audit/panel.py",
            "model",
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--issue-only",
            "--fleet-id",
            "fleet-office",
        )
        operator_audit_governance_model = json.loads(output)
        require(
            operator_audit_governance_model["meta"]["matched_record_count"] == 1,
            "operator audit governance matched count mismatch",
        )
        require(
            operator_audit_governance_model["meta"]["issue_count"] >= 2,
            "operator audit governance issue count mismatch",
        )
        require(
            operator_audit_governance_model["meta"]["remote_governance_matched_entry_count"] == 1,
            "operator audit governance remote matched count mismatch",
        )
        require(
            operator_audit_governance_model["meta"]["remote_governance_issue_count"] >= 2,
            "operator audit governance remote issue mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/operator-audit/panel.py",
            "action",
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--fleet-id",
            "fleet-office",
            "--action",
            "inspect-remote-governance",
        )
        operator_audit_governance_action = json.loads(output)
        require(
            operator_audit_governance_action["enabled"] is True,
            "operator audit governance inspect action disabled",
        )
        require(
            operator_audit_governance_action["target_component"] == "remote-governance",
            "operator audit governance inspect target mismatch",
        )
        require(
            (operator_audit_governance_action.get("remote_governance_filters") or {}).get("fleet_id") == "fleet-office",
            "operator audit governance inspect fleet filter mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/capture-indicators/panel.py",
            "model",
            "--path",
            str(indicator_state),
        )
        capture_model = json.loads(output)
        require(capture_model["panel_id"] == "capture-indicators-panel", "capture indicators panel id mismatch")
        require(capture_model["meta"]["active_count"] == 1, "capture indicators panel count mismatch")
        require(capture_model["header"]["status"] == "active", "capture indicators panel status mismatch")

        output = run_python(
            ROOT / "aios/shell/components/device-backend-status/panel.py",
            "model",
            "--path",
            str(backend_state),
        )
        backend_full_model = json.loads(output)
        require(backend_full_model["panel_id"] == "device-backend-status-panel", "backend full panel id mismatch")
        require(backend_full_model["meta"]["summary_source"] == "backend_summary", "backend panel should prefer published backend summary")
        require(backend_full_model["meta"]["attention_count"] == 1, "backend full panel attention mismatch")
        require(backend_full_model["meta"]["status_count"] == 2, "backend full panel status count mismatch")
        require(backend_full_model["meta"]["available_status_count"] == 1, "backend full panel available count mismatch")
        require(backend_full_model["meta"]["evidence_artifact_count"] == 2, "backend full panel evidence artifact count mismatch")
        require(
            sorted(backend_full_model["meta"]["release_grade_backend_ids"])
            == ["pipewire", "xdg-desktop-portal-screencast"],
            "backend full panel release-grade backend ids mismatch",
        )
        require(backend_full_model["meta"]["readiness_summary"]["missing-session-bus"] == 1, "backend full panel readiness summary mismatch")

        output = run_python(
            ROOT / "aios/shell/components/device-backend-status/panel.py",
            "model",
            "--path",
            str(backend_state),
            "--attention-only",
        )
        backend_model = json.loads(output)
        require(backend_model["panel_id"] == "device-backend-status-panel", "backend panel id mismatch")
        require(backend_model["meta"]["summary_source"] == "filtered", "backend panel attention view should use filtered summary")
        require(backend_model["meta"]["attention_count"] == 1, "backend panel attention mismatch")
        require(backend_model["meta"]["status_count"] == 1, "backend panel filtered status count mismatch")
        require(backend_model["meta"]["ui_tree_available"] is True, "backend panel missing ui_tree snapshot")
        require(backend_model["meta"]["ui_tree_capture_mode"] == "native-live", "backend panel ui_tree mode mismatch")
        require(backend_model["meta"]["ui_tree_focus"] == "desktop-0/app-0/0", "backend panel ui_tree focus mismatch")
        require(backend_model["meta"]["ui_tree_support_route_count"] == 2, "backend panel ui_tree route count mismatch")
        require(backend_model["meta"]["ui_tree_support_ready_count"] == 1, "backend panel ui_tree ready route mismatch")
        require(backend_model["meta"]["ui_tree_current_support"] == "native-live", "backend panel current ui_tree support mismatch")
        require(backend_model["meta"]["evidence_artifact_count"] == 1, "backend panel evidence artifact count mismatch")
        require(
            backend_model["meta"]["release_grade_backend_ids"] == ["xdg-desktop-portal-screencast"],
            "backend panel release-grade backend ids mismatch",
        )
        require(
            backend_model["meta"]["evidence_dir"] == str(evidence_dir),
            "backend panel evidence dir mismatch",
        )
        backend_evidence_section = next(
            section for section in backend_model["sections"] if section["section_id"] == "backend-evidence"
        )
        require(
            backend_evidence_section["items"][0]["value"] == "xdg-desktop-portal-screencast",
            "backend evidence backend id mismatch",
        )
        require(
            backend_evidence_section["items"][0]["baseline"] == "command-adapter",
            "backend evidence baseline mismatch",
        )
        require(
            backend_evidence_section["items"][0]["backend_origin"] == "runtime-helper",
            "backend evidence origin mismatch",
        )
        require(
            backend_evidence_section["items"][0]["contract_kind"] == "release-grade-runtime-helper",
            "backend evidence contract mismatch",
        )
        require(
            backend_evidence_section["items"][0]["artifact_path"] == str(screen_evidence),
            "backend evidence artifact path mismatch",
        )

        backend_attention_bridge = temp_root / "backend-attention-bridge.json"
        backend_attention_bridge.write_text(
            json.dumps(
                {
                    "statuses": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "available": False,
                            "readiness": "missing-session-bus",
                            "details": ["dbus_session_bus=false"],
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
                            "modality": "input",
                            "backend": "libinput",
                            "adapter_id": "input.libinput-state-root",
                            "execution_path": "native-state-bridge",
                            "preview_object_kind": "input_event_batch",
                            "notes": ["input_root=/dev/input"],
                        },
                    ],
                    "ui_tree_snapshot": {
                        "snapshot_id": "tree-state-1",
                        "capture_mode": "native-state-bridge",
                        "application_count": 1,
                        "focus_node": "desktop-0/app-0/2",
                        "adapter_id": "ui_tree.atspi-state-file",
                    },
                    "ui_tree_support_matrix": [
                        {
                            "environment_id": "current-session",
                            "available": True,
                            "readiness": "native-state-bridge",
                            "current": True,
                            "details": ["desktop_environment=fixture", "session_type=headless"],
                        },
                        {
                            "environment_id": "screen-ocr-fallback",
                            "available": True,
                            "readiness": "screen-frame+ocr",
                            "current": False,
                            "details": ["fallback_path=screen_frame+ocr"],
                        },
                    ],
                    "notes": ["available_backends=1", "backend_count=2"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        output = run_python(
            ROOT / "aios/shell/components/device-backend-status/panel.py",
            "model",
            "--path",
            str(backend_attention_bridge),
            "--attention-only",
        )
        backend_bridge_model = json.loads(output)
        require(backend_bridge_model["meta"]["summary_source"] == "filtered", "backend panel state-bridge attention view should stay filtered")
        require(backend_bridge_model["meta"]["attention_count"] == 1, "backend panel state-bridge attention mismatch")
        require(backend_bridge_model["meta"]["status_count"] == 1, "backend panel should filter native-state-bridge status")
        require(
            backend_bridge_model["meta"]["ui_tree_capture_mode"] == "native-state-bridge",
            "backend panel should retain ui_tree snapshot in attention mode",
        )
        require(
            backend_bridge_model["meta"]["ui_tree_current_support"] == "native-state-bridge",
            "backend panel should retain current ui_tree support route",
        )

        output = run_python(
            ROOT / "aios/shell/components/remote-governance/panel.py",
            "model",
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--issue-only",
            "--fleet-id",
            "fleet-office",
        )
        governance_model = json.loads(output)
        require(governance_model["panel_id"] == "remote-governance-panel", "remote governance panel id mismatch")
        require(governance_model["meta"]["matched_entry_count"] == 1, "remote governance matched count mismatch")
        require(governance_model["meta"]["issue_count"] >= 2, "remote governance issue count mismatch")
        require(governance_model["meta"]["fleet_count"] == 1, "remote governance fleet count mismatch")
        require(
            governance_model["meta"]["query"]["filters"]["fleet_id"] == "fleet-office",
            "remote governance fleet filter mismatch",
        )
        governance_entries = next(
            section for section in governance_model["sections"] if section["section_id"] == "entries"
        )
        require(
            governance_entries["items"][0]["value"] == "stale",
            "remote governance stale registration mismatch",
        )
        governance_fleets = next(
            section for section in governance_model["sections"] if section["section_id"] == "fleets"
        )
        require(
            governance_fleets["items"][0]["label"] == "fleet-office",
            "remote governance fleet summary mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/components/launcher/panel.py",
            "model",
            "--fixture",
            str(session_fixture),
            "--session-id",
            "session-1",
            "--user-id",
            "user-1",
            "--intent",
            "open docs",
        )
        launcher_model = json.loads(output)
        require(launcher_model["panel_id"] == "launcher-panel", "launcher panel id mismatch")
        require(launcher_model["meta"]["task_count"] == 2, "launcher panel task count mismatch")
        require(launcher_model["meta"]["recent_session_count"] == 1, "launcher recent session count mismatch")
        require(launcher_model["meta"]["suggestion_count"] >= 1, "launcher suggestion count mismatch")
        require(launcher_model["meta"]["restore_available"] is True, "launcher restore availability mismatch")
        require(
            launcher_model["meta"]["restore_target_component"] == "task-surface",
            "launcher restore target mismatch",
        )
        require(
            launcher_model["meta"]["restore_recovery_status"] == "baseline",
            "launcher restore recovery status mismatch",
        )
        require(launcher_model["meta"]["data_source_status"] == "ready", "launcher panel data-source status mismatch")
        require(any(action["action_id"] == "create-task" for action in launcher_model["actions"]), "launcher panel missing create-task action")
        recent_sessions = next(
            section for section in launcher_model["sections"] if section["section_id"] == "recent-sessions"
        )
        require(recent_sessions["items"][0]["action"]["action_id"] == "resume-session", "launcher recent session action mismatch")
        restore_section = next(
            section for section in launcher_model["sections"] if section["section_id"] == "restore"
        )
        require(restore_section["items"][1]["value"] == "ready", "launcher restore section readiness mismatch")

        output = run_python(
            ROOT / "aios/shell/components/launcher/panel.py",
            "model",
            "--socket",
            str(temp_root / "missing-launcher-sessiond.sock"),
            "--session-id",
            "session-missing",
            "--user-id",
            "user-1",
            "--intent",
            "open docs",
        )
        launcher_fallback_model = json.loads(output)
        require(launcher_fallback_model["panel_id"] == "launcher-panel", "launcher fallback panel id mismatch")
        require(launcher_fallback_model["meta"]["session_count"] == 0, "launcher fallback session count mismatch")
        require(
            launcher_fallback_model["meta"]["data_source_status"] == "fallback-empty",
            "launcher fallback status mismatch",
        )
        require(
            bool(launcher_fallback_model["meta"]["data_source_error"]),
            "launcher fallback error missing",
        )

        output = run_python(
            ROOT / "aios/shell/components/notification-center/panel.py",
            "render",
            "--recovery-surface",
            str(recovery_surface),
            "--indicator-state",
            str(indicator_state),
            "--backend-state",
            str(backend_state),
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--approval-fixture",
            str(approval_fixture),
        )
        require("Notification Center [high]" in output, "notification panel render missing header")
        require("Review Approvals" in output, "notification panel render missing action")
        require("[Remote Governance]" in output, "notification panel render missing remote governance section")

        output = run_python(
            ROOT / "aios/shell/components/operator-audit/panel.py",
            "render",
            "--policy-audit-log",
            str(policy_audit_log),
            "--runtime-events-log",
            str(runtime_events_log),
            "--remote-audit-log",
            str(remote_audit_log),
            "--compat-observability-log",
            str(compat_observability_log),
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
        )
        require("Operator Audit [critical]" in output, "operator audit panel render missing header")
        require("[Issues]" in output, "operator audit panel render missing issues section")
        require("[Remote Governance]" in output, "operator audit panel render missing governance section")

        output = run_python(
            ROOT / "aios/shell/components/remote-governance/panel.py",
            "render",
            "--browser-remote-registry",
            str(browser_remote_registry),
            "--office-remote-registry",
            str(office_remote_registry),
            "--provider-registry-state-dir",
            str(provider_registry_state_dir),
            "--issue-only",
        )
        require("Compat Remote Governance [attention]" in output, "remote governance panel render missing header")
        require("[Governance Issues]" in output, "remote governance panel render missing issues section")
        require("office.remote.worker" in output, "remote governance panel render missing office remote entry")

        output = run_python(
            ROOT / "aios/shell/components/launcher/panel.py",
            "render",
            "--fixture",
            str(session_fixture),
            "--session-id",
            "session-1",
            "--user-id",
            "user-1",
            "--intent",
            "open docs",
        )
        require("Launcher Panel [active]" in output, "launcher panel render missing header")
        require("[Recent Sessions]" in output, "launcher panel render missing recent sessions section")
        require("task-1: open docs [planned]" in output, "launcher panel render missing task")

        print("shell panels smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell panels smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
