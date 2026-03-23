#!/usr/bin/env python3
import json
import os
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
    temp_root = make_temp_dir("aios-shellctl-")
    failed = False
    try:
        recovery_surface = temp_root / "recovery-surface.json"
        recovery_surface.write_text(
            json.dumps(
                {
                    "service_id": "aios-updated",
                    "overall_status": "degraded",
                    "deployment_status": "apply-triggered",
                    "rollback_ready": True,
                    "current_slot": "b",
                    "last_good_slot": "a",
                    "staged_slot": "b",
                    "available_actions": ["check-updates", "rollback"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        indicator_state = temp_root / "indicator-state.json"
        indicator_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-08T00:00:00Z",
                    "notes": ["active_indicators=1"],
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
                    "modality": "screen",
                    "baseline": "command-adapter",
                    "artifact_path": str(screen_evidence),
                    "execution_path": "builtin-preview",
                    "source": "shellctl-smoke",
                    "release_grade_backend_id": "xdg-desktop-portal-screencast",
                    "release_grade_backend_origin": "runtime-helper",
                    "release_grade_backend_stack": "portal+pipewire",
                    "contract_kind": "release-grade-runtime-helper",
                    "state_refs": ["/tmp/fixture-screen-state.json"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        audio_evidence = evidence_dir / "audio-backend-evidence.json"
        audio_evidence.write_text(
            json.dumps(
                {
                    "modality": "audio",
                    "baseline": "os-native-backend",
                    "artifact_path": str(audio_evidence),
                    "execution_path": "native-live",
                    "source": "shellctl-smoke",
                    "release_grade_backend_id": "pipewire",
                    "release_grade_backend_origin": "os-native",
                    "release_grade_backend_stack": "pipewire",
                    "contract_kind": "release-grade-runtime-helper",
                    "state_refs": ["/tmp/fixture-audio-state.json"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

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
                            "details": ["dbus_session_bus=false", f"evidence_artifact={screen_evidence}"],
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
                    },
                    "notes": [
                        f"backend_evidence_dir={evidence_dir}",
                        "backend_evidence_artifact_count=2",
                        f"backend_evidence_artifact[screen]={screen_evidence}",
                        f"backend_evidence_artifact[audio]={audio_evidence}"
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
                            "slot_id": "launcher",
                            "component": "launcher",
                            "panel_id": "launcher-panel",
                            "action_id": "create-session",
                            "input_kind": "pointer-button",
                            "focus_policy": "retain-client-focus",
                            "status": "dispatch-ok(create-session)",
                            "summary": "Create Session: session-1 ready",
                            "error": None,
                            "payload": {"result": {"session_id": "session-1"}},
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
                            "status": "dispatch-error(approve)",
                            "summary": "bridge missing",
                            "error": "bridge missing",
                            "payload": None,
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
                            "control_plane_provider_id": "compat.browser.remote.worker",
                            "registration_status": "active",
                            "last_heartbeat_at": "2030-01-01T00:00:00Z",
                            "heartbeat_ttl_seconds": 3600,
                            "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                            "governance": {"fleet_id": "fleet-browser", "governance_group": "operator-audit"}
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
                            "control_plane_provider_id": "compat.office.remote.worker",
                            "registration_status": "active",
                            "last_heartbeat_at": "2020-01-01T00:00:00Z",
                            "heartbeat_ttl_seconds": 60,
                            "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                            "governance": {"fleet_id": "fleet-office", "governance_group": "operator-audit"}
                        }
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        mcp_remote_registry = temp_root / "mcp-remote-registry.json"
        mcp_remote_registry.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "entries": [
                        {
                            "provider_ref": "mcp.remote.worker",
                            "endpoint": "https://mcp.remote.example/bridge",
                            "control_plane_provider_id": "compat.mcp.bridge.remote",
                            "registration_status": "active",
                            "last_heartbeat_at": "2030-01-01T00:00:00Z",
                            "heartbeat_ttl_seconds": 3600,
                            "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                            "governance": {"fleet_id": "fleet-mcp", "governance_group": "operator-audit"}
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
                        "last_heartbeat_at": "2030-01-01T00:00:00Z",
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
            json.dumps({"provider_id": "compat.browser.remote.worker", "status": "available", "disabled": False}, indent=2, ensure_ascii=False)
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
                        "last_heartbeat_at": "2030-01-01T00:00:00Z",
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
            json.dumps({"provider_id": "compat.office.remote.worker", "status": "unavailable", "disabled": False}, indent=2, ensure_ascii=False)
        )

        (descriptor_dir / "compat.mcp.bridge.remote.json").write_text(
            json.dumps(
                {
                    "provider_id": "compat.mcp.bridge.remote",
                    "display_name": "MCP Remote Worker",
                    "kind": "compat-provider",
                    "execution_location": "attested_remote",
                    "remote_registration": {
                        "source_provider_id": "compat.mcp.bridge.local",
                        "provider_ref": "mcp.remote.worker",
                        "endpoint": "https://mcp.remote.example/bridge",
                        "registration_status": "active",
                        "last_heartbeat_at": "2030-01-01T00:00:00Z",
                        "heartbeat_ttl_seconds": 3600,
                        "attestation": {"mode": "verified", "status": "trusted", "expires_at": "2030-01-01T00:00:00Z"},
                        "governance": {"fleet_id": "fleet-mcp", "governance_group": "operator-audit"}
                    }
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        (health_dir / "compat.mcp.bridge.remote.json").write_text(
            json.dumps({"provider_id": "compat.mcp.bridge.remote", "status": "available", "disabled": False}, indent=2, ensure_ascii=False)
        )

        os.environ["AIOS_POLICYD_AUDIT_LOG"] = str(policy_audit_log)
        os.environ["AIOS_RUNTIMED_EVENTS_LOG"] = str(runtime_events_log)
        os.environ["AIOS_RUNTIMED_REMOTE_AUDIT_LOG"] = str(remote_audit_log)
        os.environ["AIOS_COMPAT_OBSERVABILITY_LOG"] = str(compat_observability_log)
        os.environ["AIOS_MCP_BRIDGE_REMOTE_REGISTRY"] = str(mcp_remote_registry)

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

        profile = temp_root / "shell-profile.yaml"
        profile.write_text(
            json.dumps(
                {
                    "profile_id": "test-shellctl",
                    "desktop_host": "tk",
                    "session_backend": "standalone",
                    "components": {
                        "launcher": True,
                        "notification_center": True,
                        "operator_audit": True,
                        "remote_governance": True,
                        "task_surface": True,
                        "approval_panel": True,
                        "recovery_surface": True,
                        "portal_chooser": True,
                        "capture_indicators": True,
                        "device_backend_status": True,
                    },
                    "paths": {
                        "sessiond_socket": "/tmp/missing-sessiond.sock",
                        "policyd_socket": "/tmp/missing-policyd.sock",
                        "updated_socket": "/tmp/missing-updated.sock",
                        "recovery_surface_model": str(recovery_surface),
                        "capture_indicator_state": str(indicator_state),
                        "device_backend_state": str(backend_state),
                        "deviced_socket": "/tmp/missing-deviced.sock",
                        "browser_remote_registry": str(browser_remote_registry),
                        "office_remote_registry": str(office_remote_registry),
                        "mcp_remote_registry": str(mcp_remote_registry),
                        "provider_registry_state_dir": str(provider_registry_state_dir),
                    },
                    "compositor": {
                        "manifest_path": "../compositor/Cargo.toml",
                        "config_path": "../compositor/default-compositor.conf",
                        "panel_action_log_path": str(panel_action_log),
                        "runtime_state_path": str(compositor_runtime_state),
                        "window_state_path": str(compositor_window_state),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        output = run_python(ROOT / "aios/shell/shellctl.py", "--profile", str(profile), "--json", "components")
        components = json.loads(output)
        require("launcher" in components["enabled"], "shellctl components missing launcher")
        require("notification-center" in components["enabled"], "shellctl components missing notification-center")
        require("operator-audit" in components["enabled"], "shellctl components missing operator-audit")
        require("remote-governance" in components["enabled"], "shellctl components missing remote-governance")
        require("portal-chooser" in components["enabled"], "shellctl components missing portal-chooser")

        output = run_python(ROOT / "aios/shell/shellctl.py", "--profile", str(profile), "--json", "session", "plan")
        session_plan = json.loads(output)
        require(session_plan["desktop_host"] == "tk", "shellctl session default host mismatch")
        require(session_plan["session_backend"] == "standalone", "shellctl session default backend mismatch")

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

        output = run_python(ROOT / "aios/shell/shellctl.py", "--profile", str(profile), "--json", "status")
        status = json.loads(output)
        require(
            status["components"]["recovery-surface"]["deployment_status"] == "apply-triggered",
            "shellctl status missing recovery deployment",
        )
        require(
            status["components"]["notification-center"]["total"] == 10,
            "shellctl status notification summary mismatch",
        )
        require(
            status["components"]["notification-center"]["by_source"]["shell"] == 2,
            "shellctl status notification shell source mismatch",
        )
        require(
            status["components"]["notification-center"]["operator_audit_issue_count"] == 4,
            "shellctl status notification operator audit mismatch",
        )
        require(
            status["components"]["notification-center"]["remote_governance_issue_count"] >= 2,
            "shellctl status notification remote governance mismatch",
        )
        require(
            len(status["components"]["capture-indicators"]["active"]) == 1,
            "shellctl status indicator summary mismatch",
        )
        require(
            len(status["components"]["device-backend-status"]["statuses"]) == 1,
            "shellctl status backend attention mismatch",
        )
        require(
            status["components"]["operator-audit"]["issue_count"] == 7,
            "shellctl status operator audit issue mismatch",
        )
        require(
            status["components"]["operator-audit"]["remote_governance_issue_count"] >= 2,
            "shellctl status operator audit remote governance mismatch",
        )
        require(
            status["components"]["remote-governance"]["matched_entry_count"] == 3,
            "shellctl status remote governance count mismatch",
        )
        require(
            status["components"]["remote-governance"]["fleet_count"] == 3,
            "shellctl status remote governance fleet count mismatch",
        )
        require(
            status["components"]["remote-governance"]["source_counts"].get("mcp") == 1,
            "shellctl status remote governance mcp source mismatch",
        )
        require(
            status["components"]["remote-governance"]["issue_count"] >= 2,
            "shellctl status remote governance issue mismatch",
        )

        session_fixture = temp_root / "session-fixture.json"
        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "component",
            "launcher",
            "create-session",
            "--fixture",
            str(session_fixture),
            "--user-id",
            "user-1",
            "--intent",
            "open docs",
        )
        launcher = json.loads(output)
        require(launcher["session"]["session_id"] == "session-1", "shellctl launcher dispatch mismatch")

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
        chooser_fixture = temp_root / "chooser-fixture.json"
        chooser_fixture.write_text(
            json.dumps(
                {
                    "request": {
                        "chooser_id": "shellctl-chooser",
                        "title": "Choose Portal Target",
                        "status": "pending",
                        "requested_kinds": ["screen_share_handle", "export_target_handle"],
                        "approval_status": "pending",
                        "audit_tags": ["portal", "shellctl"],
                    },
                    "handles": [
                        {
                            "handle_id": "handle-file",
                            "kind": "file_handle",
                            "target": "/workspace/notes.txt",
                        },
                        {
                            "handle_id": "handle-export",
                            "kind": "export_target_handle",
                            "target": "/workspace/export/report.pdf",
                            "scope": {
                                "display_name": "report.pdf",
                                "export_format": "pdf",
                            },
                        },
                        {
                            "handle_id": "handle-screen",
                            "kind": "screen_share_handle",
                            "target": "screen://current-display",
                            "scope": {
                                "display_name": "Current Display",
                            },
                        },
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "component",
            "task-surface",
            "summary",
            "--fixture",
            str(task_fixture),
            "--session-id",
            "session-1",
        )
        task_summary = json.loads(output)
        require(task_summary["total"] == 2, "shellctl task summary mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "component",
            "task-surface",
            "events",
            "--fixture",
            str(task_fixture),
            "--task-id",
            "task-1",
        )
        require("planned -> approved" in output, "shellctl task events mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "task-surface",
            "model",
            "--fixture",
            str(task_fixture),
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
        )
        task_panel = json.loads(output)
        require(task_panel["panel_id"] == "task-panel", "shellctl task panel mismatch")
        require(task_panel["meta"]["task_event_count"] == 2, "shellctl task panel event count mismatch")
        require(task_panel["meta"]["plan_route_preference"] == "tool-calling", "shellctl task panel route preference mismatch")
        require(task_panel["meta"]["primary_capability"] == "provider.fs.open", "shellctl task panel primary capability mismatch")
        require(task_panel["meta"]["provider_selected_id"] == "system.files.local", "shellctl task panel provider selection mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "chooser",
            "snapshot",
            "--session-id",
            "session-1",
            "--handle-fixture",
            str(chooser_fixture),
        )
        chooser_snapshot = json.loads(output)
        require(
            chooser_snapshot["selected_handle_id"] == "handle-screen",
            "shellctl chooser snapshot selected handle mismatch",
        )
        require(
            chooser_snapshot["model"]["meta"]["handle_count"] == 3,
            "shellctl chooser snapshot handle count mismatch",
        )

        chooser_export_prefix = temp_root / "chooser-export" / "portal-chooser"
        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "chooser",
            "export",
            "--session-id",
            "session-1",
            "--handle-fixture",
            str(chooser_fixture),
            "--output-prefix",
            str(chooser_export_prefix),
        )
        chooser_export = json.loads(output)
        require(
            Path(chooser_export["artifacts"]["json"]).exists(),
            "shellctl chooser export JSON artifact missing",
        )
        require(
            Path(chooser_export["artifacts"]["text"]).exists(),
            "shellctl chooser export text artifact missing",
        )
        require(
            Path(chooser_export["artifacts"]["manifest"]).exists(),
            "shellctl chooser export manifest artifact missing",
        )
        chooser_manifest = json.loads(Path(chooser_export["artifacts"]["manifest"]).read_text())
        require(
            chooser_manifest["summary"]["handle_count"] == 3,
            "shellctl chooser export manifest handle count mismatch",
        )
        require(
            chooser_manifest["summary"]["selected_handle_id"] is None,
            "shellctl chooser export manifest selected handle mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "component",
            "approval-panel",
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
        approval = json.loads(output)
        require(approval["approval_ref"] == "approval-2", "shellctl approval create mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "recovery-surface",
            "model",
        )
        recovery_panel = json.loads(output)
        require(recovery_panel["panel_id"] == "recovery-panel", "shellctl recovery panel mismatch")
        require(recovery_panel["meta"]["action_count"] == 2, "shellctl recovery panel action count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "notification-center",
            "model",
            "--approval-fixture",
            str(approval_fixture),
        )
        notification_panel = json.loads(output)
        require(notification_panel["panel_id"] == "notification-center-panel", "shellctl notification panel mismatch")
        require(notification_panel["meta"]["notification_count"] == 14, "shellctl notification panel count mismatch")
        require(notification_panel["meta"]["source_summary"]["shell"] == 2, "shellctl notification panel shell source mismatch")
        require(notification_panel["meta"]["source_summary"]["compositor"] == 2, "shellctl notification panel compositor source mismatch")
        require(
            notification_panel["meta"]["operator_audit_issue_count"] == 4,
            "shellctl notification panel operator audit mismatch",
        )
        require(
            notification_panel["meta"]["backend_evidence_present_count"] == 2,
            "shellctl notification panel backend evidence mismatch",
        )
        require(
            sorted(notification_panel["meta"]["backend_evidence_backend_ids"])
            == ["pipewire", "xdg-desktop-portal-screencast"],
            "shellctl notification panel release-grade backend ids mismatch",
        )
        require(
            notification_panel["meta"]["compositor_active_workspace_id"] == "workspace-2",
            "shellctl notification panel compositor workspace mismatch",
        )
        require(
            notification_panel["meta"]["compositor_minimized_window_count"] == 1,
            "shellctl notification panel compositor minimized mismatch",
        )
        require(
            notification_panel["meta"]["compositor_release_grade_output_status"] == "uninitialized",
            "shellctl notification panel compositor output status mismatch",
        )
        require(
            notification_panel["meta"]["remote_governance_issue_count"] >= 2,
            "shellctl notification panel remote governance mismatch",
        )
        require(
            notification_panel["meta"]["remote_governance_matched_entry_count"] == 3,
            "shellctl notification panel remote governance matched mismatch",
        )
        require(
            notification_panel["meta"]["remote_governance_fleet_count"] == 3,
            "shellctl notification panel remote governance fleet mismatch",
        )
        require(
            notification_panel["meta"]["remote_governance_source_counts"].get("mcp") == 1,
            "shellctl notification panel remote governance mcp source mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "operator-audit",
            "model",
            "--issue-only",
        )
        operator_audit_panel = json.loads(output)
        require(operator_audit_panel["panel_id"] == "operator-audit-panel", "shellctl operator audit panel mismatch")
        require(operator_audit_panel["meta"]["issue_count"] == 7, "shellctl operator audit issue count mismatch")
        require(operator_audit_panel["meta"]["issue_only"] is True, "shellctl operator audit issue-only mismatch")
        require(
            operator_audit_panel["meta"]["remote_governance_issue_count"] >= 2,
            "shellctl operator audit remote governance issue mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "capture-indicators",
            "model",
        )
        capture_panel = json.loads(output)
        require(capture_panel["panel_id"] == "capture-indicators-panel", "shellctl capture panel mismatch")
        require(capture_panel["meta"]["active_count"] == 1, "shellctl capture panel active count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "device-backend-status",
            "model",
            "--attention-only",
        )
        backend_panel = json.loads(output)
        require(backend_panel["panel_id"] == "device-backend-status-panel", "shellctl backend panel mismatch")
        require(backend_panel["meta"]["status_count"] == 1, "shellctl backend panel filtered status mismatch")
        require(backend_panel["meta"]["ui_tree_available"] is True, "shellctl backend panel missing ui_tree snapshot")
        require(backend_panel["meta"]["ui_tree_capture_mode"] == "native-live", "shellctl backend panel ui_tree mode mismatch")
        require(backend_panel["meta"]["evidence_artifact_count"] == 1, "shellctl backend evidence count mismatch")
        require(
            backend_panel["meta"]["release_grade_backend_ids"] == ["xdg-desktop-portal-screencast"],
            "shellctl backend release-grade backend ids mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "remote-governance",
            "model",
            "--issue-only",
            "--fleet-id",
            "fleet-office",
        )
        remote_governance_panel = json.loads(output)
        require(
            remote_governance_panel["panel_id"] == "remote-governance-panel",
            "shellctl remote governance panel mismatch",
        )
        require(
            remote_governance_panel["meta"]["matched_entry_count"] == 1,
            "shellctl remote governance matched entry mismatch",
        )
        require(
            remote_governance_panel["meta"]["issue_count"] >= 2,
            "shellctl remote governance issue count mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "launcher",
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
        launcher_panel = json.loads(output)
        require(launcher_panel["panel_id"] == "launcher-panel", "shellctl launcher panel mismatch")
        require(launcher_panel["meta"]["task_count"] >= 1, "shellctl launcher panel task count mismatch")
        require(launcher_panel["meta"]["recent_session_count"] == 1, "shellctl launcher recent session mismatch")
        require(launcher_panel["meta"]["active_workspace_id"] == "workspace-2", "shellctl launcher workspace mismatch")
        require(launcher_panel["meta"]["minimized_window_count"] == 1, "shellctl launcher minimized window count mismatch")
        launcher_active_windows = next(
            section for section in launcher_panel["sections"] if section["section_id"] == "active-workspace-windows"
        )
        require(len(launcher_active_windows["items"]) == 1, "shellctl launcher active workspace window count mismatch")
        require(
            launcher_active_windows["items"][0]["action"]["action_id"] == "focus-window",
            "shellctl launcher active workspace action mismatch",
        )
        launcher_minimized_windows = next(
            section for section in launcher_panel["sections"] if section["section_id"] == "minimized-windows"
        )
        require(len(launcher_minimized_windows["items"]) == 1, "shellctl launcher minimized windows section mismatch")
        require(
            launcher_minimized_windows["items"][0]["action"]["action_id"] == "restore-window",
            "shellctl launcher restore action mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "launcher",
            "action",
            "--fixture",
            str(session_fixture),
            "--session-id",
            "session-1",
            "--action",
            "restore-window",
            "--window-key",
            "window-beta",
            "--workspace-id",
            "workspace-2",
            "--output-id",
            "display-2",
        )
        launcher_restore = json.loads(output)
        require(launcher_restore["target_component"] == "task-surface", "shellctl launcher restore target mismatch")
        require(launcher_restore["window_action"] == "restore-window", "shellctl launcher restore action mismatch")
        require(launcher_restore["minimized_window_count"] == 0, "shellctl launcher restore minimized count mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "launcher",
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
        launcher_panel_after_restore = json.loads(output)
        require(
            launcher_panel_after_restore["meta"]["minimized_window_count"] == 0,
            "shellctl launcher restore result mismatch",
        )
        launcher_active_windows_after_restore = next(
            section
            for section in launcher_panel_after_restore["sections"]
            if section["section_id"] == "active-workspace-windows"
        )
        require(
            len(launcher_active_windows_after_restore["items"]) == 2,
            "shellctl launcher restored workspace window count mismatch",
        )

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "launcher",
            "action",
            "--fixture",
            str(session_fixture),
            "--session-id",
            "session-1",
            "--action",
            "create-task",
            "--title",
            "triage alerts",
            "--state",
            "planned",
        )
        launcher_action = json.loads(output)
        require(launcher_action["task"]["task_id"] == "task-2", "shellctl launcher panel action mismatch")

        print("shellctl smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shellctl smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
