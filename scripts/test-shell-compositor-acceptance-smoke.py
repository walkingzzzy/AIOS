#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from shell_evidence_manifest import write_shell_evidence_manifest


ROOT = Path(__file__).resolve().parent.parent
COMPOSITOR_MANIFEST = ROOT / "aios/shell/compositor/Cargo.toml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def run_python(script: Path, *args: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def run_compositor(config_path: Path) -> dict:
    completed = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(COMPOSITOR_MANIFEST),
            "--",
            "--config",
            str(config_path),
            "--once",
            "--emit-json",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    require(lines, "compositor acceptance produced no output")
    require("starting shell compositor" in lines[0], "compositor acceptance startup log missing")
    return json.loads(lines[-1])


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-compositor-acceptance-"))
    failed = False
    try:
        launcher_fixture = temp_root / "launcher-fixture.json"
        task_fixture = temp_root / "task-fixture.json"
        approval_fixture = temp_root / "approvals.json"
        chooser_fixture = temp_root / "handles.json"
        recovery_surface = temp_root / "recovery-surface.json"
        indicator_state = temp_root / "indicator-state.json"
        backend_state = temp_root / "backend-state.json"
        panel_action_log = temp_root / "panel-action-events.jsonl"
        profile = temp_root / "formal-shell-profile.json"
        export_prefix = temp_root / "acceptance-artifacts" / "shell-compositor-acceptance"
        compositor_config = temp_root / "compositor-acceptance.conf"

        write_json(
            launcher_fixture,
            {
                "sessions": [
                    {
                        "session_id": "session-1",
                        "user_id": "user-1",
                        "created_at": "2026-03-09T00:00:00Z",
                        "status": "active",
                    }
                ],
                "tasks": [
                    {
                        "task_id": "task-1",
                        "session_id": "session-1",
                        "state": "planned",
                        "title": "prepare support handoff",
                        "created_at": "2026-03-09T00:01:00Z",
                    }
                ],
            },
        )
        write_json(
            task_fixture,
            {
                "tasks": [
                    {
                        "task_id": "task-1",
                        "session_id": "session-1",
                        "state": "planned",
                        "title": "prepare support handoff",
                        "created_at": "2026-03-09T00:01:00Z",
                    },
                    {
                        "task_id": "task-2",
                        "session_id": "session-1",
                        "state": "approved",
                        "title": "collect device diagnostics",
                        "created_at": "2026-03-09T00:02:00Z",
                    },
                ],
                "plans": {
                    "task-1": {
                        "steps": [
                            {"step": "resume shell session", "status": "completed"},
                            {"step": "review approval", "status": "in_progress"},
                            {"step": "confirm screen share target", "status": "pending"},
                        ]
                    }
                },
            },
        )
        write_json(
            approval_fixture,
            {
                "approvals": [
                    {
                        "approval_ref": "approval-1",
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "task_id": "task-1",
                        "capability_id": "device.capture.screen.read",
                        "approval_lane": "device-capture-review",
                        "status": "pending",
                        "execution_location": "local",
                        "created_at": "2026-03-09T00:03:00Z",
                        "reason": "screen share request",
                    }
                ]
            },
        )
        write_json(
            chooser_fixture,
            {
                "request": {
                    "chooser_id": "compositor-acceptance-chooser",
                    "title": "Choose Screen Share Target",
                    "status": "pending",
                    "requested_kinds": ["screen_share_handle", "export_target_handle"],
                    "selection_mode": "single",
                    "approval_status": "pending",
                    "attempt_count": 0,
                    "max_attempts": 2,
                    "audit_tags": ["shell", "compositor", "acceptance"],
                },
                "handles": [
                    {
                        "handle_id": "handle-file",
                        "kind": "file_handle",
                        "target": "/workspace/notes.txt",
                    },
                    {
                        "handle_id": "handle-directory",
                        "kind": "directory_handle",
                        "target": "/workspace/reports",
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
                            "backend": "pipewire",
                            "display_ref": "display-1",
                        },
                    },
                ],
            },
        )
        write_json(
            recovery_surface,
            {
                "service_id": "aios-updated",
                "overall_status": "warning",
                "deployment_status": "apply-triggered",
                "current_slot": "a",
                "last_good_slot": "a",
                "staged_slot": "b",
                "rollback_ready": True,
                "recovery_points": ["recovery-1.json"],
                "diagnostic_bundles": ["diag-1.json"],
                "available_actions": ["check-updates", "rollback", "export-bundle"],
            },
        )
        write_json(
            indicator_state,
            {
                "updated_at": "2026-03-09T00:05:00Z",
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
                "notes": ["active_indicators=1"],
            },
        )
        write_json(
            backend_state,
            {
                "updated_at": "2026-03-09T00:06:00Z",
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
                        "backend": "pipewire-audio",
                        "available": True,
                        "readiness": "native-live",
                        "details": [],
                    },
                ],
                "adapters": [
                    {
                        "modality": "screen",
                        "backend": "screen-capture-portal",
                        "adapter_id": "screen.portal-live",
                        "execution_path": "native-live",
                        "preview_object_kind": "screen_frame",
                        "notes": ["fallback preview"],
                    }
                ],
                "ui_tree_snapshot": {
                    "snapshot_id": "tree-live-1",
                    "capture_mode": "native-live",
                    "application_count": 1,
                    "focus_node": "desktop-0/app-0/0",
                    "adapter_id": "ui_tree.atspi-probe",
                },
            },
        )
        browser_remote_registry = temp_root / "browser-remote-registry.json"
        office_remote_registry = temp_root / "office-remote-registry.json"
        provider_registry_state_dir = temp_root / "provider-registry"
        write_json(
            browser_remote_registry,
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
        )
        write_json(
            office_remote_registry,
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
        )
        write_json(
            provider_registry_state_dir / "descriptors" / "compat.browser.remote.worker.json",
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
        )
        write_json(
            provider_registry_state_dir / "health" / "compat.browser.remote.worker.json",
            {
                "provider_id": "compat.browser.remote.worker",
                "status": "available",
                "disabled": False,
            },
        )
        write_json(
            provider_registry_state_dir / "descriptors" / "compat.office.remote.worker.json",
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
        )
        write_json(
            provider_registry_state_dir / "health" / "compat.office.remote.worker.json",
            {
                "provider_id": "compat.office.remote.worker",
                "status": "available",
                "disabled": False,
            },
        )
        profile_payload = {
            "profile_id": "shell-compositor-acceptance",
            "desktop_host": "gtk",
            "session_backend": "compositor",
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
                "panel_action_log_path": str(panel_action_log),
                "browser_remote_registry": str(browser_remote_registry),
                "office_remote_registry": str(office_remote_registry),
                "provider_registry_state_dir": str(provider_registry_state_dir),
            },
            "host_runtime": {
                "nested_fallback": "standalone-tk",
            },
            "compositor": {
                "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                "panel_action_log_path": str(panel_action_log),
            },
        }
        write_json(profile, profile_payload)

        exported = json.loads(
            run_python(
                ROOT / "aios/shell/runtime/shell_session.py",
                "export",
                "--json",
                "--profile",
                str(profile),
                "--desktop-host",
                "gtk",
                "--session-backend",
                "compositor",
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
                str(export_prefix),
            )
        )
        snapshot = exported["snapshot"]
        artifacts = exported["artifacts"]
        json_artifact = Path(artifacts["json"])
        text_artifact = Path(artifacts["text"])
        require(json_artifact.exists(), "compositor acceptance shell export JSON missing")
        require(text_artifact.exists(), "compositor acceptance shell export text missing")
        require(snapshot["surface_count"] == 9, "compositor acceptance shell export surface count mismatch")
        require(
            snapshot["summary"]["active_modal_surface"] == "approval-panel",
            "compositor acceptance shell export active modal mismatch",
        )
        require(
            snapshot["summary"]["primary_attention_surface"] == "recovery-surface",
            "compositor acceptance shell export attention mismatch",
        )
        require(
            snapshot["summary"]["top_stack_surface"] == "approval-panel",
            "compositor acceptance shell export top stack mismatch",
        )
        require(
            snapshot["summary"]["modal_surface_count"] == 3,
            "compositor acceptance shell export modal count mismatch",
        )
        require(
            snapshot["summary"]["blocked_surface_count"] == 3,
            "compositor acceptance shell export blocked count mismatch",
        )
        component_map = {surface["component"]: surface for surface in snapshot["surfaces"]}
        require(
            component_map["remote-governance"]["model"]["meta"]["matched_entry_count"] == 2,
            "compositor acceptance remote governance matched count mismatch",
        )
        require(
            component_map["remote-governance"]["model"]["meta"]["issue_count"] >= 1,
            "compositor acceptance remote governance issue count mismatch",
        )

        compositor_config.write_text(
            "\n".join(
                [
                    "service_id = shell-compositor-acceptance",
                    "desktop_host = gtk",
                    "session_backend = smithay-wayland-frontend",
                    "seat_name = seat-acceptance",
                    "pointer_enabled = true",
                    "keyboard_enabled = true",
                    "touch_enabled = true",
                    "keyboard_layout = us",
                    "placeholder_surfaces = launcher,task-surface,approval-panel,portal-chooser,notification-center,recovery-surface,capture-indicators,remote-governance,device-backend-status",
                    f"panel_snapshot_path = {json_artifact}",
                    f"panel_action_log_path = {panel_action_log}",
                    "panel_snapshot_refresh_ticks = 1",
                    "tick_ms = 1",
                ]
            )
            + "\n"
        )

        first = run_compositor(compositor_config)
        second = run_compositor(compositor_config)

        for payload in (first, second):
            require(payload["service_id"] == "shell-compositor-acceptance", "compositor acceptance service_id mismatch")
            require(payload["runtime"] == "smithay-wayland-frontend", "compositor acceptance runtime mismatch")
            require(payload["desktop_host"] == "gtk", "compositor acceptance desktop host mismatch")
            require(payload["panel_snapshot_source"] == "path", "compositor acceptance panel snapshot source mismatch")
            require(
                payload["panel_snapshot_profile_id"] == "shell-compositor-acceptance",
                "compositor acceptance panel snapshot profile mismatch",
            )
            require(payload["panel_snapshot_surface_count"] == 9, "compositor acceptance snapshot surface count mismatch")
            require(payload["surface_count"] == 9, "compositor acceptance compositor surface count mismatch")
            require(payload["panel_host_bound_count"] == 9, "compositor acceptance host bound count mismatch")
            require(payload["panel_host_status"] == "ready(9/9)", "compositor acceptance host status mismatch")
            require(
                payload["panel_embedding_status"] == "panel-host-ready(9/9)",
                "compositor acceptance embedding status mismatch",
            )
            require(
                payload["active_modal_surface_id"] == "approval-panel",
                "compositor acceptance active modal mismatch",
            )
            require(
                payload["primary_attention_surface_id"] in {"approval-panel", "recovery-surface"},
                "compositor acceptance primary attention mismatch",
            )
            require(payload["attention_surface_count"] >= 4, "compositor acceptance attention count mismatch")
            require(payload["stacking_status"].startswith("panel-host-only("), "compositor acceptance stacking mismatch")
            require(payload["panel_action_event_count"] == 0, "compositor acceptance action event count mismatch")
            require(payload["panel_action_events"] == [], "compositor acceptance action event payload mismatch")
            require(
                payload["panel_action_log_path"] == str(panel_action_log),
                "compositor acceptance action log path mismatch",
            )
            require(
                any(surface["surface_id"] == "remote-governance" for surface in payload["surfaces"]),
                "compositor acceptance missing remote governance surface",
            )
            require(payload["topmost_surface_id"] is not None, "compositor acceptance topmost surface missing")

        stable_keys = [
            "panel_snapshot_profile_id",
            "panel_snapshot_surface_count",
            "panel_host_bound_count",
            "panel_host_status",
            "panel_embedding_status",
            "active_modal_surface_id",
            "primary_attention_surface_id",
            "attention_surface_count",
            "stacking_status",
            "surface_count",
        ]
        for key in stable_keys:
            require(first[key] == second[key], f"compositor acceptance stability mismatch for {key}")

        manifest_path = export_prefix.parent / "shell-compositor-acceptance-manifest.json"
        manifest = write_shell_evidence_manifest(
            manifest_path,
            suite="shell-compositor-acceptance",
            artifacts={
                **artifacts,
                "panel_action_log": str(panel_action_log),
                "compositor_config": str(compositor_config),
            },
            snapshot=snapshot,
            records=[
                {
                    "phase": "first",
                    "run": "first",
                    "active_modal_surface_id": first["active_modal_surface_id"],
                    "primary_attention_surface_id": first["primary_attention_surface_id"],
                    "surface_count": first["surface_count"],
                    "stacking_status": first["stacking_status"],
                },
                {
                    "phase": "second",
                    "run": "second",
                    "active_modal_surface_id": second["active_modal_surface_id"],
                    "primary_attention_surface_id": second["primary_attention_surface_id"],
                    "surface_count": second["surface_count"],
                    "stacking_status": second["stacking_status"],
                },
            ],
            evidence={
                "modal_timeline": [
                    {
                        "phase": "shell-export",
                        "active_modal_surface": snapshot["summary"]["active_modal_surface"],
                        "primary_attention_surface": snapshot["summary"]["primary_attention_surface"],
                        "top_stack_surface": snapshot["summary"]["top_stack_surface"],
                    },
                    {
                        "phase": "compositor-first",
                        "active_modal_surface": first["active_modal_surface_id"],
                        "primary_attention_surface": first["primary_attention_surface_id"],
                        "top_stack_surface": first["topmost_surface_id"],
                    },
                    {
                        "phase": "compositor-second",
                        "active_modal_surface": second["active_modal_surface_id"],
                        "primary_attention_surface": second["primary_attention_surface_id"],
                        "top_stack_surface": second["topmost_surface_id"],
                    },
                ],
            },
            extra={
                "stable_keys": stable_keys,
                "panel_action_log_path": str(panel_action_log),
            },
        )
        require(manifest_path.exists(), "compositor acceptance manifest missing")
        require(manifest["suite"] == "shell-compositor-acceptance", "compositor acceptance manifest suite mismatch")
        require(len(manifest["records"]) == 2, "compositor acceptance manifest record count mismatch")
        require(
            manifest["evidence"]["restore"]["available"] is True,
            "compositor acceptance restore evidence mismatch",
        )
        require(
            manifest["evidence"]["backend_status"]["status"] == "attention",
            "compositor acceptance backend evidence mismatch",
        )
        require(
            manifest["evidence"]["modal_timeline"][1]["active_modal_surface"] == "approval-panel",
            "compositor acceptance modal evidence mismatch",
        )

        print("shell compositor acceptance smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell compositor acceptance smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
