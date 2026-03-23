#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from shell_test_temp import make_temp_dir, restore_session_temp_root, set_session_temp_root


ROOT = Path(__file__).resolve().parent.parent


def run_python(*args: str) -> str:
    completed = subprocess.run([sys.executable, *args], cwd=ROOT, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    previous_temp_root = set_session_temp_root()
    temp_root = make_temp_dir("aios-shell-desktop-")
    success = False

    try:

        launcher_fixture = temp_root / "launcher.json"
        launcher_fixture.write_text(
            json.dumps(
                {
                    "sessions": [
                        {
                            "session_id": "session-1",
                            "user_id": "user-1",
                            "status": "active",
                            "created_at": "2026-03-09T00:00:00Z",
                        }
                    ],
                    "tasks": [
                        {
                            "task_id": "task-1",
                            "session_id": "session-1",
                            "state": "planned",
                            "title": "Open recovery dashboard",
                            "created_at": "2026-03-09T00:01:00Z",
                        }
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        task_fixture = temp_root / "tasks.json"
        task_fixture.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "task_id": "task-1",
                            "session_id": "session-1",
                            "state": "planned",
                            "title": "Open recovery dashboard",
                            "created_at": "2026-03-09T00:01:00Z",
                        },
                        {
                            "task_id": "task-2",
                            "session_id": "session-1",
                            "state": "approved",
                            "title": "Review export target",
                            "created_at": "2026-03-09T00:02:00Z",
                        },
                    ],
                    "plans": {
                        "task-1": {
                            "steps": [
                                {"step": "Open desktop snapshot", "status": "completed"},
                                {"step": "Inspect portal chooser", "status": "in_progress"},
                            ]
                        }
                    },
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
                            "approval_lane": "device-capture-review",
                            "status": "pending",
                            "execution_location": "local",
                            "created_at": "2026-03-09T00:03:00Z",
                            "reason": "microphone request",
                        }
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        chooser_fixture = temp_root / "handles.json"
        chooser_fixture.write_text(
            json.dumps(
                {
                    "request": {
                        "chooser_id": "chooser-desktop",
                        "title": "Choose Screen Share Target",
                        "status": "pending",
                        "requested_kinds": ["screen_share_handle"],
                        "selection_mode": "single",
                        "attempt_count": 0,
                        "max_attempts": 2,
                    },
                    "handles": [
                        {
                            "handle_id": "handle-1",
                            "kind": "file_handle",
                            "target": "/workspace/notes.txt",
                        },
                        {
                            "handle_id": "handle-export",
                            "kind": "export_target_handle",
                            "target": "/workspace/export/report.pdf",
                        },
                        {
                            "handle_id": "handle-directory",
                            "kind": "directory_handle",
                            "target": "/workspace/reports",
                        },
                        {
                            "handle_id": "handle-2",
                            "kind": "screen_share_handle",
                            "target": "display-1",
                        },
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        recovery_surface = temp_root / "recovery-surface.json"
        recovery_surface.write_text(
            json.dumps(
                {
                    "service_id": "aios-updated",
                    "overall_status": "warning",
                    "deployment_status": "apply-triggered",
                    "current_slot": "a",
                    "last_good_slot": "a",
                    "staged_slot": "b",
                    "rollback_ready": True,
                    "available_actions": ["rollback", "export-bundle"],
                    "recovery_points": ["rp-1.json"],
                    "diagnostic_bundles": ["bundle-1.json"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        indicator_state = temp_root / "indicator-state.json"
        indicator_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-09T00:04:00Z",
                    "notes": ["active_indicators=1"],
                    "active": [
                        {
                            "indicator_id": "indicator-1",
                            "capture_id": "capture-1",
                            "modality": "screen",
                            "message": "Screen capture active",
                            "continuous": False,
                            "started_at": "2026-03-09T00:04:00Z",
                            "approval_status": "pending",
                        }
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        backend_state = temp_root / "backend-state.json"
        backend_state.write_text(
            json.dumps(
                {
                    "updated_at": "2026-03-09T00:05:00Z",
                    "statuses": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "available": True,
                            "readiness": "native-live",
                            "details": ["probe_source=builtin-probe"],
                        },
                        {
                            "modality": "audio",
                            "backend": "pipewire",
                            "available": True,
                            "readiness": "native-live",
                            "details": ["probe_source=builtin-probe"],
                        },
                    ],
                    "adapters": [
                        {
                            "modality": "screen",
                            "backend": "screen-capture-portal",
                            "adapter_id": "screen.portal-probe",
                            "execution_path": "native-live",
                            "preview_object_kind": "screen_frame",
                            "notes": ["probe_source=builtin-probe"],
                        },
                        {
                            "modality": "audio",
                            "backend": "pipewire",
                            "adapter_id": "audio.pipewire-probe",
                            "execution_path": "native-live",
                            "preview_object_kind": "audio_chunk",
                            "notes": ["probe_source=builtin-probe"],
                        },
                    ],
                    "notes": ["available_backends=2"],
                },
                indent=2,
                ensure_ascii=False,
            )
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
                            "last_heartbeat_at": "2026-03-09T00:05:00Z",
                            "heartbeat_ttl_seconds": 3600,
                            "attestation": {
                                "mode": "verified",
                                "status": "trusted",
                                "expires_at": "2030-01-01T00:00:00Z",
                            },
                            "governance": {
                                "fleet_id": "fleet-browser",
                                "governance_group": "operator-audit",
                            },
                        }
                    ],
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
                            "attestation": {
                                "mode": "verified",
                                "status": "trusted",
                                "expires_at": "2030-01-01T00:00:00Z",
                            },
                            "governance": {
                                "fleet_id": "fleet-office",
                                "governance_group": "operator-audit",
                            },
                        }
                    ],
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
                        "attestation": {
                            "mode": "verified",
                            "status": "trusted",
                            "expires_at": "2030-01-01T00:00:00Z",
                        },
                        "governance": {
                            "fleet_id": "fleet-browser",
                            "governance_group": "operator-audit",
                        },
                    },
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
                        "attestation": {
                            "mode": "verified",
                            "status": "trusted",
                            "expires_at": "2030-01-01T00:00:00Z",
                        },
                        "governance": {
                            "fleet_id": "fleet-office",
                            "governance_group": "operator-audit",
                        },
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        (health_dir / "compat.office.remote.worker.json").write_text(
            json.dumps(
                {
                    "provider_id": "compat.office.remote.worker",
                    "status": "available",
                    "disabled": False,
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        profile = temp_root / "shell-profile.yaml"
        profile.write_text(
            json.dumps(
                {
                    "profile_id": "shell-desktop-smoke",
                    "desktop_host": "tk",
                    "session_backend": "standalone",
                    "components": {
                        "launcher": True,
                        "task_surface": True,
                        "approval_panel": True,
                        "portal_chooser": True,
                        "notification_center": True,
                        "recovery_surface": True,
                        "capture_indicators": True,
                        "remote_governance": True,
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
                        "provider_registry_state_dir": str(provider_registry_state_dir),
                    },
                    "compositor": {
                        "manifest_path": "../compositor/Cargo.toml",
                        "config_path": "../compositor/default-compositor.conf",
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        desktop_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_desktop.py"),
            "snapshot",
            "--json",
            "--profile",
            str(profile),
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--launcher-fixture",
            str(launcher_fixture),
            "--task-fixture",
            str(task_fixture),
            "--approval-fixture",
            str(approval_fixture),
            "--chooser-fixture",
            str(chooser_fixture),
        )
        snapshot = json.loads(desktop_output)
        require(snapshot["surface_count"] == 9, "desktop snapshot surface count mismatch")
        require(snapshot["summary"]["visible_surface_count"] == 9, "desktop summary visible surface count mismatch")
        require(snapshot["summary"]["total_surface_count"] == 9, "desktop summary total surface count mismatch")
        require(sum(snapshot["summary"]["status_counts"].values()) == snapshot["surface_count"], "desktop summary status counts mismatch")
        require(snapshot["summary"]["component_names"][0] == "launcher", "desktop summary component order mismatch")
        require(snapshot["summary"]["modal_surface_count"] == 3, "desktop modal surface count mismatch")
        require(snapshot["summary"]["attention_surface_count"] >= 4, "desktop attention surface count mismatch")
        require(snapshot["summary"]["blocked_surface_count"] == 3, "desktop blocked surface count mismatch")
        require(snapshot["summary"]["top_stack_surface"] == "approval-panel", "desktop top stack surface mismatch")
        require(
            snapshot["summary"]["component_roles"]["portal-chooser"] == "modal",
            "desktop component role mismatch",
        )
        require(
            snapshot["summary"]["focus_policy_counts"]["shell-modal"] == 3,
            "desktop focus policy count mismatch",
        )
        require(
            snapshot["summary"]["interaction_mode_counts"]["blocked-by-modal"] == 3,
            "desktop interaction mode count mismatch",
        )
        require(
            "recovery-surface" in snapshot["summary"]["attention_components"],
            "desktop attention components mismatch",
        )
        require(
            "task-surface" in snapshot["summary"]["blocked_components"],
            "desktop blocked components mismatch",
        )
        require(snapshot["summary"]["active_modal_surface"] == "approval-panel", "desktop active modal surface mismatch")
        require(snapshot["summary"]["primary_attention_surface"] == "recovery-surface", "desktop attention surface mismatch")
        require(snapshot["summary"]["stack_order"][0] == "approval-panel", "desktop stack order mismatch")
        component_map = {surface["component"]: surface for surface in snapshot["surfaces"]}
        require(component_map["launcher"]["panel_id"] == "launcher-panel", "launcher panel missing from desktop snapshot")
        require(component_map["task-surface"]["blocked_by"] == "approval-panel", "task surface modal blocking mismatch")
        require(component_map["approval-panel"]["interaction_mode"] == "modal", "approval panel interaction mismatch")
        require(component_map["task-surface"]["model"]["meta"]["task_count"] == 2, "task surface count mismatch")
        require(component_map["approval-panel"]["model"]["meta"]["approval_count"] == 1, "approval panel count mismatch")
        require(component_map["portal-chooser"]["model"]["meta"]["handle_count"] == 4, "portal chooser handle count mismatch")
        require(component_map["portal-chooser"]["model"]["meta"]["focus_handle_id"] == "handle-2", "portal chooser focus handle mismatch")
        require(component_map["portal-chooser"]["model"]["header"]["status"] == "pending", "portal chooser initial status mismatch")
        require(component_map["notification-center"]["model"]["meta"]["notification_count"] >= 3, "notification center missing feed")
        require(component_map["recovery-surface"]["model"]["meta"]["recovery_point_count"] == 1, "recovery surface point count mismatch")
        require(component_map["capture-indicators"]["model"]["meta"]["active_count"] == 1, "capture indicators count mismatch")
        require(
            component_map["remote-governance"]["model"]["meta"]["matched_entry_count"] == 2,
            "remote governance matched count mismatch",
        )
        require(
            component_map["remote-governance"]["model"]["meta"]["issue_count"] >= 1,
            "remote governance issue count mismatch",
        )
        require(component_map["device-backend-status"]["model"]["meta"]["status_count"] == 2, "device backend status count mismatch")

        runtime_dir = ROOT / "aios" / "shell" / "runtime"
        shell_dir = ROOT / "aios" / "shell"
        for candidate in (shell_dir, runtime_dir):
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
        import shell_desktop
        import shell_desktop_gtk
        import shellctl

        action_args = argparse.Namespace(
            profile=profile,
            session_id="session-1",
            task_id="task-1",
            user_id="local-user",
            intent="shell-desktop",
            title=None,
            task_state="planned",
            task_state_filter=None,
            limit=None,
            launcher_fixture=launcher_fixture,
            task_fixture=task_fixture,
            approval_fixture=approval_fixture,
            chooser_fixture=chooser_fixture,
            include_disabled=False,
            interval=2.0,
            duration=0.0,
            surfaces=None,
            status_filter=None,
            tone_filter=None,
            output_prefix=None,
            json=False,
        )
        loaded_profile = shellctl.load_profile(profile)
        task_action = component_map["task-surface"]["model"]["actions"][0]
        task_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "task-surface",
            task_action,
        )
        require(
            task_action_result["result"]["state"] == "approved",
            "gtk task action should update the task fixture",
        )
        chooser_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "portal-chooser",
            next(
                action
                for action in component_map["portal-chooser"]["model"]["actions"]
                if action.get("action_id") == "prefer-requested"
            ),
        )
        require(
            chooser_action_result["result"]["status"] == "selected",
            "gtk chooser action should select the requested target",
        )
        require(
            chooser_action_result["result"]["selected_handle_id"] == "handle-2",
            "gtk chooser action should prefer the screen share handle",
        )
        require(
            shell_desktop_gtk.next_surface_from_action_result(
                "portal-chooser",
                chooser_action_result["result"],
            )
            == "portal-chooser",
            "portal chooser intermediate action should keep chooser selected",
        )

        tk_notification_action_result = shell_desktop.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "notification-center",
            next(
                action
                for action in component_map["notification-center"]["model"]["actions"]
                if action.get("action_id") == "review-approvals"
            ),
        )
        require(
            tk_notification_action_result["result"]["target_component"] == "approval-panel",
            "tk notification action should route to approval panel",
        )
        require(
            shell_desktop.next_surface_from_action_result(
                "notification-center",
                tk_notification_action_result["result"],
            )
            == "approval-panel",
            "tk notification route helper mismatch",
        )
        require(
            shell_desktop.ordered_snapshot_surfaces(snapshot)[0]["component"] == "approval-panel",
            "tk desktop ordering helper should honor stack order",
        )

        notification_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "notification-center",
            next(
                action
                for action in component_map["notification-center"]["model"]["actions"]
                if action.get("action_id") == "review-approvals"
            ),
        )
        require(
            notification_action_result["result"]["target_component"] == "approval-panel",
            "notification center review action should route to approval panel",
        )
        require(
            shell_desktop_gtk.next_surface_from_action_result(
                "notification-center",
                notification_action_result["result"],
            )
            == "approval-panel",
            "notification center route helper mismatch",
        )

        capture_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "capture-indicators",
            next(
                action
                for action in component_map["capture-indicators"]["model"]["actions"]
                if action.get("action_id") == "review-approvals"
            ),
        )
        require(
            capture_action_result["result"]["target_component"] == "approval-panel",
            "capture indicators review action should route to approval panel",
        )

        backend_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "device-backend-status",
            next(
                action
                for action in component_map["device-backend-status"]["model"]["actions"]
                if action.get("action_id") == "focus-attention"
            ),
        )
        require(
            backend_action_result["result"]["attention_only"] is True,
            "device backend focus-attention should enable attention-only mode",
        )

        remote_governance_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "remote-governance",
            next(
                action
                for action in component_map["remote-governance"]["model"]["actions"]
                if action.get("action_id") == "focus-issues"
            ),
        )
        require(
            remote_governance_action_result["result"]["issue_only"] is True,
            "remote governance focus-issues should enable issue-only mode",
        )

        launcher_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "launcher",
            next(
                action
                for action in component_map["launcher"]["model"]["actions"]
                if action.get("action_id") == "resume-session"
            ),
        )
        require(
            launcher_action_result["result"]["target_component"] == "task-surface",
            "launcher resume action should route to task surface",
        )

        approval_action_result = shell_desktop_gtk.dispatch_panel_action(
            loaded_profile,
            action_args,
            snapshot,
            "approval-panel",
            next(
                action
                for action in component_map["approval-panel"]["model"]["actions"]
                if action.get("action_id") == "approve"
            ),
        )
        require(
            approval_action_result["result"]["target_component"] == "task-surface",
            "approval action should route back to task surface",
        )

        shellctl_output = run_python(
            str(ROOT / "aios/shell/shellctl.py"),
            "--profile",
            str(profile),
            "--json",
            "desktop",
            "snapshot",
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--launcher-fixture",
            str(launcher_fixture),
            "--task-fixture",
            str(task_fixture),
            "--approval-fixture",
            str(approval_fixture),
            "--chooser-fixture",
            str(chooser_fixture),
        )
        shellctl_snapshot = json.loads(shellctl_output)
        require(shellctl_snapshot["surface_count"] == snapshot["surface_count"], "shellctl desktop snapshot mismatch")
        require(shellctl_snapshot["profile_id"] == "shell-desktop-smoke", "shellctl desktop profile mismatch")

        session_plan_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_session.py"),
            "plan",
            "--json",
            "--profile",
            str(profile),
        )
        session_plan = json.loads(session_plan_output)
        require(session_plan["desktop_host"] == "tk", "shell session default desktop host mismatch")
        require(session_plan["session_backend"] == "standalone", "shell session default backend mismatch")
        require(
            Path(session_plan["compositor"]["manifest_path"]).name == "Cargo.toml",
            "shell session compositor manifest mismatch",
        )

        shellctl_session_output = run_python(
            str(ROOT / "aios/shell/shellctl.py"),
            "--profile",
            str(profile),
            "--json",
            "session",
            "plan",
        )
        shellctl_session_plan = json.loads(shellctl_session_output)
        require(shellctl_session_plan["session_backend"] == "standalone", "shellctl session plan backend mismatch")

        gtk_snapshot_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_session.py"),
            "snapshot",
            "--json",
            "--profile",
            str(profile),
            "--desktop-host",
            "gtk",
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--launcher-fixture",
            str(launcher_fixture),
            "--task-fixture",
            str(task_fixture),
            "--approval-fixture",
            str(approval_fixture),
            "--chooser-fixture",
            str(chooser_fixture),
        )
        gtk_snapshot = json.loads(gtk_snapshot_output)
        require(gtk_snapshot["session_plan"]["desktop_host"] == "gtk", "gtk snapshot host resolution mismatch")
        require(gtk_snapshot["surface_count"] == snapshot["surface_count"], "gtk snapshot surface count mismatch")

        filtered_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_desktop.py"),
            "snapshot",
            "--json",
            "--profile",
            str(profile),
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--launcher-fixture",
            str(launcher_fixture),
            "--task-fixture",
            str(task_fixture),
            "--approval-fixture",
            str(approval_fixture),
            "--chooser-fixture",
            str(chooser_fixture),
            "--surface",
            "approval-panel",
            "--surface",
            "portal-chooser",
        )
        filtered_snapshot = json.loads(filtered_output)
        require(filtered_snapshot["surface_count"] == 2, "desktop filtered snapshot surface count mismatch")
        require(
            {surface["component"] for surface in filtered_snapshot["surfaces"]} == {"approval-panel", "portal-chooser"},
            "desktop filtered snapshot component set mismatch",
        )
        require(
            filtered_snapshot["summary"]["applied_filters"]["components"] == ["approval-panel", "portal-chooser"],
            "desktop filtered snapshot filters mismatch",
        )

        output_prefix = temp_root / "desktop-export"
        export_output = run_python(
            str(ROOT / "aios/shell/runtime/shell_desktop.py"),
            "export",
            "--json",
            "--profile",
            str(profile),
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--launcher-fixture",
            str(launcher_fixture),
            "--task-fixture",
            str(task_fixture),
            "--approval-fixture",
            str(approval_fixture),
            "--chooser-fixture",
            str(chooser_fixture),
            "--output-prefix",
            str(output_prefix),
        )
        export_payload = json.loads(export_output)
        json_artifact = Path(export_payload["artifacts"]["json"])
        text_artifact = Path(export_payload["artifacts"]["text"])
        require(json_artifact.exists(), "desktop export JSON artifact missing")
        require(text_artifact.exists(), "desktop export text artifact missing")
        exported_snapshot = json.loads(json_artifact.read_text())
        require(exported_snapshot["surface_count"] == snapshot["surface_count"], "desktop export JSON mismatch")
        require("## overview" in text_artifact.read_text(), "desktop export text missing overview section")

        gtk_serve = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_session.py"),
                "serve",
                "--profile",
                str(profile),
                "--desktop-host",
                "gtk",
                "--duration",
                "0.1",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "DISPLAY": "", "WAYLAND_DISPLAY": ""},
        )
        combined = (gtk_serve.stdout + gtk_serve.stderr).strip()
        if gtk_serve.returncode != 0:
            require("Traceback" not in combined, "gtk host failure should be graceful")
            require(
                "GTK host unavailable" in combined or "GUI display unavailable" in combined,
                "gtk host failure message mismatch",
            )

        tk_serve = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/runtime/shell_desktop.py"),
                "serve",
                "--profile",
                str(profile),
                "--duration",
                "0.1",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "DISPLAY": "", "WAYLAND_DISPLAY": ""},
        )
        combined = (tk_serve.stdout + tk_serve.stderr).strip()
        if tk_serve.returncode != 0:
            require("Traceback" not in combined, "tk host failure should be graceful")
            require("GUI display unavailable" in combined, "tk host failure message mismatch")

        print("shell desktop smoke passed")
        success = True
        return 0
    finally:
        restore_session_temp_root(previous_temp_root)
        if success:
            shutil.rmtree(temp_root, ignore_errors=True)
        else:
            print(f"shell desktop smoke state kept at: {temp_root}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
