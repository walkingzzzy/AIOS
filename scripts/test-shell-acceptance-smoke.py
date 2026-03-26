#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from shell_evidence_manifest import write_shell_evidence_manifest
from shell_test_temp import make_temp_dir, restore_session_temp_root, set_session_temp_root
from mock_device_capture_rpc import managed_mock_deviced

ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS shell acceptance smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep temporary fixtures and exported artifacts on success")
    return parser.parse_args()


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


def build_action_args(
    *,
    profile: Path,
    launcher_fixture: Path,
    task_fixture: Path,
    approval_fixture: Path,
    chooser_fixture: Path,
):
    import argparse as argparse_module

    return argparse_module.Namespace(
        profile=profile,
        session_id="session-1",
        task_id="task-1",
        user_id="local-user",
        intent="shell-acceptance",
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


def load_shell_modules() -> tuple[object, object]:
    runtime_dir = ROOT / "aios" / "shell" / "runtime"
    shell_dir = ROOT / "aios" / "shell"
    for candidate in (shell_dir, runtime_dir):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    import shell_desktop_gtk  # noqa: WPS433
    import shellctl  # noqa: WPS433

    return shell_desktop_gtk, shellctl


def main() -> int:
    args = parse_args()
    previous_temp_root = set_session_temp_root()
    temp_root = make_temp_dir("aios-shell-acceptance-")
    failed = False

    try:
        launcher_fixture = temp_root / "launcher-fixture.json"
        task_fixture = temp_root / "task-fixture.json"
        approval_fixture = temp_root / "approvals.json"
        chooser_fixture = temp_root / "handles.json"
        recovery_surface = temp_root / "recovery-surface.json"
        indicator_state = temp_root / "indicator-state.json"
        backend_state = temp_root / "backend-state.json"
        ai_readiness = temp_root / "ai-readiness.json"
        ai_onboarding_report = temp_root / "ai-onboarding-report.json"
        ai_model_dir = temp_root / "models"
        ai_model_registry = temp_root / "model-registry.json"
        ai_model_import_source = temp_root / "import-model.gguf"
        runtime_platform_env = temp_root / "runtime-platform.env"
        compositor_runtime_state = temp_root / "compositor-runtime-state.json"
        compositor_window_state = temp_root / "compositor-window-state.json"
        panel_action_log = temp_root / "panel-action-events.jsonl"
        profile = temp_root / "formal-shell-profile.json"
        export_prefix = temp_root / "acceptance-artifacts" / "shell-acceptance"
        mock_deviced_socket = temp_root / "mock-deviced.sock"

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
                    "chooser_id": "acceptance-chooser",
                    "title": "Choose Screen Share Target",
                    "status": "pending",
                    "requested_kinds": ["screen_share_handle"],
                    "selection_mode": "single",
                    "approval_status": "pending",
                    "attempt_count": 0,
                    "max_attempts": 2,
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
                    },
                    {
                        "handle_id": "handle-directory",
                        "kind": "directory_handle",
                        "target": "/workspace/reports",
                    },
                    {
                        "handle_id": "handle-screen",
                        "kind": "screen_share_handle",
                        "target": "screen://current-display",
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
                "updated_at": "2026-03-09T00:04:00Z",
                "notes": ["active_indicators=1"],
                "active": [
                    {
                        "indicator_id": "indicator-1",
                        "capture_id": "capture-1",
                        "modality": "screen",
                        "message": "Screen capture waiting for review",
                        "continuous": False,
                        "started_at": "2026-03-09T00:04:00Z",
                        "approval_status": "pending",
                    }
                ],
            },
        )
        write_json(
            backend_state,
            {
                "updated_at": "2026-03-09T00:05:00Z",
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
                        "adapter_id": "screen.builtin-preview",
                        "execution_path": "builtin-preview",
                        "preview_object_kind": "screen_frame",
                        "notes": ["fallback preview available"],
                    },
                    {
                        "modality": "audio",
                        "backend": "pipewire-audio",
                        "adapter_id": "audio.pipewire-live",
                        "execution_path": "native-live",
                        "preview_object_kind": "audio_chunk",
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
                "ui_tree_support_matrix": [
                    {
                        "environment_id": "current-session",
                        "available": True,
                        "readiness": "native-live",
                        "current": True,
                        "details": ["session_type=wayland"],
                    }
                ],
                "notes": ["available_backends=2"],
            },
        )
        ai_model_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            ai_readiness,
            {
                "generated_at": "2026-03-09T00:00:00Z",
                "state": "setup-pending",
                "reason": "default model pull pending firstboot completion",
                "next_action": "open-ai-center",
                "ai_enabled": True,
                "ai_mode": "hybrid",
                "local_model_count": 0,
                "endpoint_configured": True,
                "report_path": str(ai_onboarding_report),
            },
        )
        write_json(
            ai_onboarding_report,
            {
                "generated_at": "2026-03-09T00:00:00Z",
                "ai_enabled": True,
                "ai_mode": "hybrid",
                "privacy_profile": "balanced",
                "endpoint_base_url": "http://127.0.0.1:11434/v1",
                "endpoint_model": "qwen2.5:7b-instruct",
                "endpoint_configured": True,
                "local_model_count": 0,
                "readiness_state": "setup-pending",
                "readiness_reason": "default model pull pending firstboot completion",
                "next_action": "open-ai-center",
            },
        )
        ai_model_import_source.write_bytes(b"GGUF" + b"\x00" * 64)
        runtime_platform_env.write_text(
            "\n".join(
                [
                    "AIOS_RUNTIMED_AI_ENABLED=1",
                    "AIOS_RUNTIMED_AI_MODE=hybrid",
                    "AIOS_RUNTIMED_AI_PRIVACY_PROFILE=balanced",
                    "AIOS_RUNTIMED_AI_ROUTE_PREFERENCE=local-first",
                    "AIOS_RUNTIMED_LOCAL_CPU_COMMAND=/usr/libexec/aios/runtime/workers/launch_local_cpu_worker.sh",
                    "AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL=http://127.0.0.1:11434/v1",
                    "AIOS_RUNTIMED_AI_ENDPOINT_MODEL=qwen2.5:7b-instruct",
                    "AIOS_RUNTIMED_AI_ENDPOINT_API_KEY=acceptance-secret-token",
                    "AIOS_RUNTIMED_MEMORY_ENABLED=1",
                    "AIOS_RUNTIMED_MEMORY_RETENTION_DAYS=30",
                    "AIOS_RUNTIMED_AUDIT_RETENTION_DAYS=90",
                    "AIOS_RUNTIMED_APPROVAL_DEFAULT_POLICY=prompt-required",
                    "AIOS_RUNTIMED_REMOTE_PROMPT_LEVEL=full",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        write_json(
            ai_model_registry,
            {
                "schema_version": "1.0.0",
                "models": {
                    "local-qwen-mini": {
                        "model_id": "local-qwen-mini",
                        "path": str(ai_model_dir / "local-qwen-mini.gguf"),
                        "format": "gguf",
                        "size_bytes": 7340032,
                        "sha256": "deadbeef",
                        "aliases": ["default-gen"],
                        "capabilities": ["text-generation"],
                        "quantization": "Q4_K_M",
                        "parameters_estimate": "7B",
                        "source_kind": "local-import-copy",
                        "source_uri": "file:///tmp/local-qwen-mini.gguf",
                    }
                },
                "aliases": {"default-gen": "local-qwen-mini"},
                "defaults": {"text-generation": "local-qwen-mini"},
            },
        )
        write_json(
            compositor_runtime_state,
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
        )
        write_json(
            compositor_window_state,
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
        )
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
                            "action_id": "resume-session",
                            "input_kind": "pointer-button",
                            "focus_policy": "retain-client-focus",
                            "status": "dispatch-ok(resume-session)",
                            "summary": "Resume Session: resumed session-1",
                            "error": None,
                            "payload": {"result": {"session_id": "session-1"}},
                        },
                        ensure_ascii=False,
                    )
                ]
            )
            + "\n"
        )
        write_json(
            profile,
            {
                "profile_id": "shell-acceptance-smoke",
                "desktop_host": "gtk",
                "session_backend": "compositor",
                "session": {
                    "entrypoint": "formal",
                    "nested_fallback": "standalone-tk",
                    "compositor_required": False,
                },
                "components": {
                    "launcher": True,
                    "task_surface": True,
                    "system_assistant": True,
                    "ai_center": True,
                    "provider_settings": True,
                    "privacy_memory": True,
                    "model_library": True,
                    "approval_panel": True,
                    "portal_chooser": True,
                    "notification_center": True,
                    "recovery_surface": True,
                    "capture_indicators": True,
                    "device_backend_status": True,
                },
                "paths": {
                    "sessiond_socket": "/tmp/missing-sessiond.sock",
                    "policyd_socket": "/tmp/missing-policyd.sock",
                    "updated_socket": "/tmp/missing-updated.sock",
                    "ai_readiness_path": str(ai_readiness),
                    "ai_onboarding_report_path": str(ai_onboarding_report),
                    "runtime_platform_env_path": str(runtime_platform_env),
                    "ai_model_dir": str(ai_model_dir),
                    "ai_model_registry": str(ai_model_registry),
                    "ai_model_import_source": str(ai_model_import_source),
                    "recovery_surface_model": str(recovery_surface),
                    "capture_indicator_state": str(indicator_state),
                    "device_backend_state": str(backend_state),
                    "deviced_socket": str(mock_deviced_socket),
                },
                "compositor": {
                    "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                    "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                    "panel_action_log_path": str(panel_action_log),
                    "runtime_state_path": str(compositor_runtime_state),
                    "window_state_path": str(compositor_window_state),
                },
            },
        )

        with managed_mock_deviced(mock_deviced_socket, service_id="acceptance-mock-deviced"):
            snapshot_output = run_python(
                ROOT / "aios/shell/runtime/shell_session.py",
                "snapshot",
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
            )
            snapshot = json.loads(snapshot_output)
            require(snapshot["session_plan"]["entrypoint"] == "formal", "shell acceptance entrypoint mismatch")
            require(snapshot["session_plan"]["session_backend"] == "compositor", "shell acceptance backend mismatch")
            require(snapshot["summary"]["active_modal_surface"] == "approval-panel", "shell acceptance active modal mismatch")
            require(snapshot["summary"]["managed_window_count"] == 2, "shell acceptance managed window count mismatch")
            require(snapshot["summary"]["minimized_window_count"] == 1, "shell acceptance minimized window count mismatch")
            require(snapshot["summary"]["active_workspace_id"] == "workspace-2", "shell acceptance workspace summary mismatch")

            shell_desktop_gtk, shellctl = load_shell_modules()
            loaded_profile = shellctl.load_profile(profile)
            action_args = build_action_args(
                profile=profile,
                launcher_fixture=launcher_fixture,
                task_fixture=task_fixture,
                approval_fixture=approval_fixture,
                chooser_fixture=chooser_fixture,
            )
            component_map = {surface["component"]: surface for surface in snapshot["surfaces"]}
            require(component_map["task-surface"]["model"]["meta"]["managed_window_count"] == 2, "shell acceptance task panel window count mismatch")
            require(component_map["task-surface"]["model"]["meta"]["task_inference_route"] == "local", "shell acceptance task route mismatch")
            require(component_map["task-surface"]["model"]["meta"]["task_model_source"] == "local-qwen-mini", "shell acceptance task model mismatch")
            require(component_map["notification-center"]["model"]["meta"]["compositor_minimized_window_count"] == 1, "shell acceptance notification compositor mismatch")
            require(component_map["notification-center"]["model"]["meta"]["ai_current_model"] == "local-qwen-mini", "shell acceptance notification AI model mismatch")
            require(
                component_map["system-assistant"]["model"]["meta"]["default_text_generation_model"] == "local-qwen-mini",
                "shell acceptance system assistant model mismatch",
            )
            require(
                component_map["system-assistant"]["model"]["meta"]["pending_approval_count"] == 1,
                "shell acceptance system assistant approval mismatch",
            )
            require(component_map["ai-center"]["model"]["meta"]["local_model_count"] == 1, "shell acceptance ai center model count mismatch")
            require(
                component_map["provider-settings"]["model"]["meta"]["route_preference"] == "local-first",
                "shell acceptance provider settings route mismatch",
            )
            require(
                component_map["provider-settings"]["model"]["meta"]["endpoint_api_key_configured"] is True,
                "shell acceptance provider settings api key mismatch",
            )
            require(
                component_map["privacy-memory"]["model"]["meta"]["memory_retention_days"] == 30,
                "shell acceptance privacy memory retention mismatch",
            )
            require(
                component_map["approval-panel"]["model"]["meta"]["approval_default_policy"] == "prompt-required",
                "shell acceptance approval policy mismatch",
            )
            require(component_map["model-library"]["model"]["meta"]["local_model_count"] == 1, "shell acceptance model library count mismatch")
            require(
                component_map["model-library"]["model"]["meta"]["import_source_ready"] is True,
                "shell acceptance model library import source mismatch",
            )
            require(
                component_map["ai-center"]["model"]["meta"]["default_text_generation_model"] == "local-qwen-mini",
                "shell acceptance ai center default model mismatch",
            )
            launcher_meta = component_map["launcher"]["model"]["meta"]
            require(launcher_meta["restore_available"] is True, "launcher restore availability mismatch")
            require(launcher_meta["restore_target_component"] == "task-surface", "launcher restore target mismatch")
            require(launcher_meta["restore_recovery_status"] == "baseline", "launcher restore status mismatch")

            launcher_resume = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "launcher",
                next(action for action in component_map["launcher"]["model"]["actions"] if action.get("action_id") == "resume-session"),
            )
            require(launcher_resume["result"]["target_component"] == "task-surface", "launcher route mismatch")
            require(launcher_resume["result"]["resumed_session_id"] == "session-1", "launcher resumed session mismatch")
            require(launcher_resume["result"]["recovery_status"] == "baseline", "launcher recovery status mismatch")
            require(launcher_resume["result"]["restore_status"] == "baseline", "launcher restore status mismatch")

            launcher_minimized_section = next(
                section for section in component_map["launcher"]["model"]["sections"] if section["section_id"] == "minimized-windows"
            )
            require(len(launcher_minimized_section["items"]) == 1, "launcher minimized window section mismatch")
            require(
                launcher_minimized_section["items"][0]["action"]["action_id"] == "restore-window",
                "launcher minimized restore action mismatch",
            )
            launcher_restore = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "launcher",
                launcher_minimized_section["items"][0]["action"],
            )
            require(launcher_restore["result"]["target_component"] == "task-surface", "launcher restore target mismatch")
            require(launcher_restore["result"]["window_action"] == "restore-window", "launcher restore action mismatch")
            require(launcher_restore["result"]["minimized_window_count"] == 0, "launcher restore minimized count mismatch")

            restored_snapshot = json.loads(
                run_python(
                    ROOT / "aios/shell/runtime/shell_session.py",
                    "snapshot",
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
                )
            )
            restored_components = {surface["component"]: surface for surface in restored_snapshot["surfaces"]}
            require(
                restored_components["launcher"]["model"]["meta"]["minimized_window_count"] == 0,
                "launcher restore snapshot mismatch",
            )
            require(
                restored_components["task-surface"]["model"]["meta"]["minimized_window_count"] == 0,
                "task surface restore snapshot mismatch",
            )

            notification_review = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "notification-center",
                next(action for action in component_map["notification-center"]["model"]["actions"] if action.get("action_id") == "review-approvals"),
            )
            require(notification_review["result"]["target_component"] == "approval-panel", "notification route mismatch")

            notification_ai_center = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "notification-center",
                next(action for action in component_map["notification-center"]["model"]["actions"] if action.get("action_id") == "open-ai-center"),
            )
            require(
                notification_ai_center["result"]["target_component"] == "ai-center",
                "notification ai center route mismatch",
            )

            system_assistant_ai_center = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "system-assistant",
                next(action for action in component_map["system-assistant"]["model"]["actions"] if action.get("action_id") == "open-ai-center"),
            )
            require(
                system_assistant_ai_center["result"]["target_component"] == "ai-center",
                "system assistant ai center route mismatch",
            )

            system_assistant_approval = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "system-assistant",
                next(action for action in component_map["system-assistant"]["model"]["actions"] if action.get("action_id") == "open-approval-panel"),
            )
            require(
                system_assistant_approval["result"]["target_component"] == "approval-panel",
                "system assistant approval route mismatch",
            )

            ai_center_open_library = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "ai-center",
                next(action for action in component_map["ai-center"]["model"]["actions"] if action.get("action_id") == "open-model-library"),
            )
            require(
                ai_center_open_library["result"]["target_component"] == "model-library",
                "ai center model library route mismatch",
            )

            ai_center_open_provider = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "ai-center",
                next(action for action in component_map["ai-center"]["model"]["actions"] if action.get("action_id") == "open-provider-settings"),
            )
            require(
                ai_center_open_provider["result"]["target_component"] == "provider-settings",
                "ai center provider settings route mismatch",
            )

            ai_center_open_privacy = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "ai-center",
                next(action for action in component_map["ai-center"]["model"]["actions"] if action.get("action_id") == "open-privacy-memory"),
            )
            require(
                ai_center_open_privacy["result"]["target_component"] == "privacy-memory",
                "ai center privacy memory route mismatch",
            )

            provider_settings_route = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "provider-settings",
                next(action for action in component_map["provider-settings"]["model"]["actions"] if action.get("action_id") == "route-remote-first"),
            )
            require(
                provider_settings_route["result"]["status"] == "saved",
                "provider settings dispatch status mismatch",
            )
            require(
                provider_settings_route["result"]["route_preference"] == "remote-first",
                "provider settings dispatch route mismatch",
            )

            privacy_memory_route = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "privacy-memory",
                next(action for action in component_map["privacy-memory"]["model"]["actions"] if action.get("action_id") == "remote-prompt-summary"),
            )
            require(
                privacy_memory_route["result"]["status"] == "saved",
                "privacy memory dispatch status mismatch",
            )
            require(
                privacy_memory_route["result"]["remote_prompt_level"] == "summary",
                "privacy memory dispatch prompt mismatch",
            )

            model_library_import = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "model-library",
                next(action for action in component_map["model-library"]["model"]["actions"] if action.get("action_id") == "import-local-model"),
            )
            require(model_library_import["result"]["status"] == "imported", "model library import dispatch mismatch")
            require(
                model_library_import["result"]["local_model_count"] == 2,
                "model library import dispatch count mismatch",
            )

            imported_snapshot = json.loads(
                run_python(
                    ROOT / "aios/shell/runtime/shell_session.py",
                    "snapshot",
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
                )
            )
            imported_components = {surface["component"]: surface for surface in imported_snapshot["surfaces"]}
            require(
                imported_components["model-library"]["model"]["meta"]["local_model_count"] == 2,
                "model library imported snapshot mismatch",
            )
            model_default_actions = next(
                section
                for section in imported_components["model-library"]["model"]["sections"]
                if section["section_id"] == "default-actions"
            )
            imported_default_action = next(
                item["action"]
                for item in model_default_actions["items"]
                if item["action"].get("model_id") == "import-model"
            )
            model_library_default = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                imported_snapshot,
                "model-library",
                imported_default_action,
            )
            require(
                model_library_default["result"]["status"] == "default-updated",
                "model library default dispatch mismatch",
            )

            default_snapshot = json.loads(
                run_python(
                    ROOT / "aios/shell/runtime/shell_session.py",
                    "snapshot",
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
                )
            )
            default_components = {surface["component"]: surface for surface in default_snapshot["surfaces"]}
            require(
                default_components["ai-center"]["model"]["meta"]["default_text_generation_model"] == "import-model",
                "ai center imported default snapshot mismatch",
            )
            delete_actions_section = next(
                section
                for section in default_components["model-library"]["model"]["sections"]
                if section["section_id"] == "delete-actions"
            )
            imported_delete_action = next(
                item["action"]
                for item in delete_actions_section["items"]
                if item["action"].get("model_id") == "import-model"
            )
            model_library_delete = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                default_snapshot,
                "model-library",
                imported_delete_action,
            )
            require(
                model_library_delete["result"]["status"] == "deleted",
                "model library delete dispatch mismatch",
            )

            deleted_snapshot = json.loads(
                run_python(
                    ROOT / "aios/shell/runtime/shell_session.py",
                    "snapshot",
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
                )
            )
            deleted_components = {surface["component"]: surface for surface in deleted_snapshot["surfaces"]}
            require(
                deleted_components["model-library"]["model"]["meta"]["local_model_count"] == 1,
                "model library deleted snapshot count mismatch",
            )
            require(
                deleted_components["ai-center"]["model"]["meta"]["default_text_generation_model"] == "local-qwen-mini",
                "ai center deleted snapshot default mismatch",
            )

            capture_review = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "capture-indicators",
                next(action for action in component_map["capture-indicators"]["model"]["actions"] if action.get("action_id") == "review-approvals"),
            )
            require(capture_review["result"]["target_component"] == "approval-panel", "capture route mismatch")

            approval_action = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                snapshot,
                "approval-panel",
                next(action for action in component_map["approval-panel"]["model"]["actions"] if action.get("action_id") == "approve"),
            )
            require(approval_action["result"]["status"] == "approved", "approval resolution mismatch")
            require(approval_action["result"]["target_component"] == "task-surface", "approval return route mismatch")

            post_approval_snapshot = json.loads(
                run_python(
                    ROOT / "aios/shell/runtime/shell_session.py",
                    "snapshot",
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
                )
            )
            require(
                post_approval_snapshot["summary"]["active_modal_surface"] == "portal-chooser",
                "post-approval active modal should move to chooser",
            )

            post_approval_components = {surface["component"]: surface for surface in post_approval_snapshot["surfaces"]}
            chooser_select = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                post_approval_snapshot,
                "portal-chooser",
                next(action for action in post_approval_components["portal-chooser"]["model"]["actions"] if action.get("action_id") == "prefer-requested"),
            )
            require(chooser_select["result"]["selected_handle_id"] == "handle-screen", "chooser selected handle mismatch")

            selected_snapshot = json.loads(
                run_python(
                    ROOT / "aios/shell/runtime/shell_session.py",
                    "snapshot",
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
                )
            )
            selected_components = {surface["component"]: surface for surface in selected_snapshot["surfaces"]}
            chooser_confirm = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                selected_snapshot,
                "portal-chooser",
                next(action for action in selected_components["portal-chooser"]["model"]["actions"] if action.get("action_id") == "confirm-selection"),
            )
            require(chooser_confirm["result"]["status"] == "confirmed", "chooser confirm mismatch")
            require(chooser_confirm["result"]["target_component"] == "task-surface", "chooser confirm route mismatch")

            notification_recovery = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                selected_snapshot,
                "notification-center",
                next(action for action in selected_components["notification-center"]["model"]["actions"] if action.get("action_id") == "open-recovery"),
            )
            require(notification_recovery["result"]["target_component"] == "recovery-surface", "recovery route mismatch")

            recovery_export = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                selected_snapshot,
                "recovery-surface",
                next(action for action in selected_components["recovery-surface"]["model"]["actions"] if action.get("action_id") == "export-bundle"),
            )
            require(recovery_export["result"]["target_component"] == "recovery-surface", "recovery export route mismatch")
            require(recovery_export["result"]["route_reason"] == "bundle-exported", "recovery export route reason mismatch")
            require(Path(recovery_export["result"]["bundle_path"]).exists(), "recovery export bundle missing")
            recovery_payload = json.loads(recovery_surface.read_text())
            require(len(recovery_payload["diagnostic_bundles"]) >= 2, "recovery export bundle count mismatch")

            notification_device = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                selected_snapshot,
                "notification-center",
                next(action for action in selected_components["notification-center"]["model"]["actions"] if action.get("action_id") == "inspect-device-health"),
            )
            require(notification_device["result"]["target_component"] == "device-backend-status", "device route mismatch")

            notification_window_manager = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                selected_snapshot,
                "notification-center",
                next(action for action in selected_components["notification-center"]["model"]["actions"] if action.get("action_id") == "inspect-window-manager"),
            )
            require(notification_window_manager["result"]["target_component"] == "task-surface", "window manager route mismatch")

            backend_focus = shell_desktop_gtk.dispatch_panel_action(
                loaded_profile,
                action_args,
                selected_snapshot,
                "device-backend-status",
                next(action for action in selected_components["device-backend-status"]["model"]["actions"] if action.get("action_id") == "focus-attention"),
            )
            require(backend_focus["result"]["attention_only"] is True, "device attention mode mismatch")
            require(backend_focus["result"]["route_reason"] == "attention-focus", "device attention route reason mismatch")
            require(
                backend_focus["result"]["ui_tree_current_support"] == "native-live",
                "device attention ui_tree support mismatch",
            )

            export_output = run_python(
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
            export_payload = json.loads(export_output)
            json_artifact = Path(export_payload["artifacts"]["json"])
            text_artifact = Path(export_payload["artifacts"]["text"])
            require(json_artifact.exists(), "shell acceptance JSON artifact missing")
            require(text_artifact.exists(), "shell acceptance text artifact missing")

            manifest_path = export_prefix.parent / "shell-acceptance-manifest.json"
            manifest = write_shell_evidence_manifest(
                manifest_path,
                suite="shell-acceptance",
                artifacts={
                    **export_payload["artifacts"],
                    "panel_action_log": str(panel_action_log),
                },
                snapshot=export_payload["snapshot"],
                records=[
                    {
                        "phase": "restore",
                        "action": "launcher.resume-session",
                        "target_component": launcher_resume["result"]["target_component"],
                        "resumed_session_id": launcher_resume["result"]["resumed_session_id"],
                        "recovery_id": launcher_resume["result"]["recovery_id"],
                        "recovery_status": launcher_resume["result"]["recovery_status"],
                        "status": launcher_resume["result"]["restore_status"],
                    },
                    {
                        "phase": "notification",
                        "action": "notification.review-approvals",
                        "target_component": notification_review["result"]["target_component"],
                    },
                    {
                        "phase": "capture",
                        "action": "capture.review-approvals",
                        "target_component": capture_review["result"]["target_component"],
                    },
                    {
                        "phase": "approval",
                        "action": "approval.approve",
                        "target_component": approval_action["result"]["target_component"],
                        "status": approval_action["result"]["status"],
                    },
                    {
                        "phase": "chooser-select",
                        "action": "chooser.prefer-requested",
                        "selected_handle_id": chooser_select["result"]["selected_handle_id"],
                    },
                    {
                        "phase": "chooser-confirm",
                        "action": "chooser.confirm-selection",
                        "target_component": chooser_confirm["result"]["target_component"],
                        "status": chooser_confirm["result"]["status"],
                        "confirmed_handle_id": chooser_confirm["result"]["confirmed_handle_id"],
                    },
                    {
                        "phase": "recovery-export",
                        "action": "recovery.export-bundle",
                        "target_component": recovery_export["result"]["target_component"],
                        "status": recovery_export["result"]["status"],
                        "bundle_path": recovery_export["result"]["bundle_path"],
                    },
                    {
                        "phase": "device-route",
                        "action": "notification.inspect-device-health",
                        "target_component": notification_device["result"]["target_component"],
                    },
                    {
                        "phase": "device-focus",
                        "action": "device-backend-status.focus-attention",
                        "target_component": backend_focus["result"]["target_component"],
                        "attention_only": backend_focus["result"]["attention_only"],
                        "status": backend_focus["result"]["status"],
                    },
                ],
                evidence={
                    "modal_timeline": [
                        {
                            "phase": "initial",
                            "active_modal_surface": snapshot["summary"]["active_modal_surface"],
                            "primary_attention_surface": snapshot["summary"]["primary_attention_surface"],
                            "top_stack_surface": snapshot["summary"]["top_stack_surface"],
                        },
                        {
                            "phase": "post-approval",
                            "active_modal_surface": post_approval_snapshot["summary"]["active_modal_surface"],
                            "primary_attention_surface": post_approval_snapshot["summary"]["primary_attention_surface"],
                            "top_stack_surface": post_approval_snapshot["summary"]["top_stack_surface"],
                        },
                        {
                            "phase": "selected",
                            "active_modal_surface": selected_snapshot["summary"]["active_modal_surface"],
                            "primary_attention_surface": selected_snapshot["summary"]["primary_attention_surface"],
                            "top_stack_surface": selected_snapshot["summary"]["top_stack_surface"],
                        },
                        {
                            "phase": "exported",
                            "active_modal_surface": export_payload["snapshot"]["summary"]["active_modal_surface"],
                            "primary_attention_surface": export_payload["snapshot"]["summary"]["primary_attention_surface"],
                            "top_stack_surface": export_payload["snapshot"]["summary"]["top_stack_surface"],
                        },
                    ],
                    "restore": {
                        "route_target_component": launcher_resume["result"]["target_component"],
                        "resumed_session_id": launcher_resume["result"]["resumed_session_id"],
                        "restore_status": launcher_resume["result"]["restore_status"],
                        "recovery_id": launcher_resume["result"]["recovery_id"],
                        "recovery_status": launcher_resume["result"]["recovery_status"],
                    },
                    "chooser": {
                        "route_target_component": chooser_confirm["result"]["target_component"],
                        "selected_handle_id": chooser_select["result"]["selected_handle_id"],
                        "confirmed_handle_id": chooser_confirm["result"]["confirmed_handle_id"],
                        "capture_transport": chooser_confirm["result"].get("capture_transport"),
                        "capture_status": chooser_confirm["result"].get("capture_status"),
                    },
                    "recovery": {
                        "route_target_component": recovery_export["result"]["target_component"],
                        "route_reason": recovery_export["result"]["route_reason"],
                        "bundle_path": recovery_export["result"]["bundle_path"],
                        "diagnostic_bundle_count": recovery_export["result"]["diagnostic_bundle_count"],
                    },
                    "backend_status": {
                        "route_target_component": notification_device["result"]["target_component"],
                        "attention_only": backend_focus["result"]["attention_only"],
                        "route_reason": backend_focus["result"]["route_reason"],
                        "readiness_summary": backend_focus["result"]["readiness_summary"],
                        "ui_tree_current_support": backend_focus["result"]["ui_tree_current_support"],
                    },
                },
                extra={
                    "panel_action_log_path": str(panel_action_log),
                    "export_prefix": str(export_prefix),
                },
            )

            exported_snapshot = json.loads(json_artifact.read_text())
            require(
                exported_snapshot["session_plan"]["entrypoint"] == "formal",
                "exported shell acceptance entrypoint mismatch",
            )
            require(exported_snapshot["surface_count"] >= 1, "exported snapshot should contain surfaces")
            require("## overview" in text_artifact.read_text(), "shell acceptance text artifact missing overview")
            require(manifest_path.exists(), "shell acceptance manifest missing")
            require(manifest["suite"] == "shell-acceptance", "shell acceptance manifest suite mismatch")
            require(
                manifest["snapshot"]["active_modal_surface"] == export_payload["snapshot"]["summary"]["active_modal_surface"],
                "shell acceptance manifest active modal mismatch",
            )
            require(len(manifest["records"]) == 9, "shell acceptance manifest record count mismatch")
            require(manifest["evidence"]["restore"]["available"] is True, "shell acceptance restore evidence missing")
            require(
                manifest["evidence"]["restore"]["route_target_component"] == "task-surface",
                "shell acceptance restore route evidence mismatch",
            )
            require(
                manifest["evidence"]["chooser"]["confirmed_handle_id"] == "handle-screen",
                "shell acceptance chooser evidence mismatch",
            )
            require(
                manifest["evidence"]["chooser"]["capture_status"] == "capturing",
                "shell acceptance chooser capture evidence mismatch",
            )
            require(
                manifest["evidence"]["recovery"]["route_target_component"] == "recovery-surface",
                "shell acceptance recovery evidence mismatch",
            )
            require(
                manifest["evidence"]["recovery"]["route_reason"] == "bundle-exported",
                "shell acceptance recovery route reason mismatch",
            )
            require(
                manifest["evidence"]["backend_status"]["route_target_component"] == "device-backend-status",
                "shell acceptance backend route evidence mismatch",
            )
            require(
                manifest["evidence"]["modal_timeline"][0]["active_modal_surface"] == "approval-panel",
                "shell acceptance modal timeline initial mismatch",
            )
            require(
                manifest["evidence"]["modal_timeline"][1]["active_modal_surface"] == "portal-chooser",
                "shell acceptance modal timeline approval mismatch",
            )

        print("shell acceptance smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell acceptance smoke failed: {error}")
        return 1
    finally:
        restore_session_temp_root(previous_temp_root)
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
