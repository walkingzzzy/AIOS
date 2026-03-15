#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from shell_evidence_manifest import write_shell_evidence_manifest
from mock_device_capture_rpc import managed_mock_deviced


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS shell repeated stability smoke harness")
    parser.add_argument("--iterations", type=int, default=3, help="How many repeated acceptance cycles to run")
    parser.add_argument("--keep-state", action="store_true", help="Keep temporary fixtures and artifacts on success")
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
        intent="shell-stability",
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


def build_iteration_assets(base: Path, *, deviced_socket: Path) -> dict[str, Path]:
    launcher_fixture = base / "launcher-fixture.json"
    task_fixture = base / "task-fixture.json"
    approval_fixture = base / "approvals.json"
    chooser_fixture = base / "handles.json"
    recovery_surface = base / "recovery-surface.json"
    indicator_state = base / "indicator-state.json"
    backend_state = base / "backend-state.json"
    panel_action_log = base / "panel-action-events.jsonl"
    profile = base / "formal-shell-profile.json"

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
                "chooser_id": "stability-chooser",
                "title": "Choose Screen Share Target",
                "status": "pending",
                "requested_kinds": ["screen_share_handle"],
                "selection_mode": "single",
                "approval_status": "not-required",
                "attempt_count": 0,
                "max_attempts": 2,
                "audit_tags": ["shell", "stability", "smoke"],
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
                }
            ],
            "adapters": [
                {
                    "modality": "screen",
                    "backend": "screen-capture-portal",
                    "adapter_id": "screen.builtin-preview",
                    "execution_path": "builtin-preview",
                    "preview_object_kind": "screen_frame",
                    "notes": ["fallback preview available"],
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
    panel_action_log.write_text("")
    write_json(
        profile,
        {
            "profile_id": "shell-stability-smoke",
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
                "recovery_surface_model": str(recovery_surface),
                "capture_indicator_state": str(indicator_state),
                "device_backend_state": str(backend_state),
                "deviced_socket": str(deviced_socket),
            },
            "compositor": {
                "manifest_path": str((ROOT / "aios/shell/compositor/Cargo.toml").resolve()),
                "config_path": str((ROOT / "aios/shell/compositor/default-compositor.conf").resolve()),
                "panel_action_log_path": str(panel_action_log),
            },
        },
    )

    return {
        "launcher_fixture": launcher_fixture,
        "task_fixture": task_fixture,
        "approval_fixture": approval_fixture,
        "chooser_fixture": chooser_fixture,
        "panel_action_log": panel_action_log,
        "profile": profile,
    }


def snapshot_for_iteration(assets: dict[str, Path]) -> dict:
    return json.loads(
        run_python(
            ROOT / "aios/shell/runtime/shell_session.py",
            "snapshot",
            "--json",
            "--profile",
            str(assets["profile"]),
            "--desktop-host",
            "gtk",
            "--session-backend",
            "compositor",
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--launcher-fixture",
            str(assets["launcher_fixture"]),
            "--task-fixture",
            str(assets["task_fixture"]),
            "--approval-fixture",
            str(assets["approval_fixture"]),
            "--chooser-fixture",
            str(assets["chooser_fixture"]),
        )
    )


def export_for_iteration(assets: dict[str, Path], output_prefix: Path) -> dict:
    return json.loads(
        run_python(
            ROOT / "aios/shell/runtime/shell_session.py",
            "export",
            "--json",
            "--profile",
            str(assets["profile"]),
            "--desktop-host",
            "gtk",
            "--session-backend",
            "compositor",
            "--session-id",
            "session-1",
            "--task-id",
            "task-1",
            "--launcher-fixture",
            str(assets["launcher_fixture"]),
            "--task-fixture",
            str(assets["task_fixture"]),
            "--approval-fixture",
            str(assets["approval_fixture"]),
            "--chooser-fixture",
            str(assets["chooser_fixture"]),
            "--output-prefix",
            str(output_prefix),
        )
    )


def main() -> int:
    args = parse_args()
    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-stability-"))
    failed = False

    try:
        shell_desktop_gtk, shellctl = load_shell_modules()
        records: list[dict] = []
        artifact_index: dict[str, str] = {}
        mock_deviced_socket = temp_root / "mock-deviced.sock"

        with managed_mock_deviced(mock_deviced_socket, service_id="stability-mock-deviced"):
            for iteration in range(1, max(1, args.iterations) + 1):
                iteration_root = temp_root / f"iteration-{iteration}"
                assets = build_iteration_assets(iteration_root, deviced_socket=mock_deviced_socket)
                loaded_profile = shellctl.load_profile(assets["profile"])
                action_args = build_action_args(
                    profile=assets["profile"],
                    launcher_fixture=assets["launcher_fixture"],
                    task_fixture=assets["task_fixture"],
                    approval_fixture=assets["approval_fixture"],
                    chooser_fixture=assets["chooser_fixture"],
                )

                initial_snapshot = snapshot_for_iteration(assets)
                require(
                    initial_snapshot["summary"]["active_modal_surface"] == "approval-panel",
                    f"stability iteration {iteration} initial modal mismatch",
                )

                initial_components = {surface["component"]: surface for surface in initial_snapshot["surfaces"]}
                launcher_resume = shell_desktop_gtk.dispatch_panel_action(
                    loaded_profile,
                    action_args,
                    initial_snapshot,
                    "launcher",
                    next(
                        action
                        for action in initial_components["launcher"]["model"]["actions"]
                        if action.get("action_id") == "resume-session"
                    ),
                )
                require(
                    launcher_resume["result"]["target_component"] == "task-surface",
                    f"stability iteration {iteration} launcher route mismatch",
                )
                require(
                    launcher_resume["result"]["restore_status"] == "baseline",
                    f"stability iteration {iteration} launcher restore mismatch",
                )
                approval_action = shell_desktop_gtk.dispatch_panel_action(
                    loaded_profile,
                    action_args,
                    initial_snapshot,
                    "approval-panel",
                    next(
                        action
                        for action in initial_components["approval-panel"]["model"]["actions"]
                        if action.get("action_id") == "approve"
                    ),
                )
                require(
                    approval_action["result"]["target_component"] == "task-surface",
                    f"stability iteration {iteration} approval route mismatch",
                )

                post_approval_snapshot = snapshot_for_iteration(assets)
                require(
                    post_approval_snapshot["summary"]["active_modal_surface"] == "portal-chooser",
                    f"stability iteration {iteration} chooser modal mismatch",
                )
                chooser_components = {surface["component"]: surface for surface in post_approval_snapshot["surfaces"]}
                chooser_select = shell_desktop_gtk.dispatch_panel_action(
                    loaded_profile,
                    action_args,
                    post_approval_snapshot,
                    "portal-chooser",
                    next(
                        action
                        for action in chooser_components["portal-chooser"]["model"]["actions"]
                        if action.get("action_id") == "prefer-requested"
                    ),
                )
                require(
                    chooser_select["result"]["selected_handle_id"] == "handle-screen",
                    f"stability iteration {iteration} chooser selection mismatch",
                )

                selected_snapshot = snapshot_for_iteration(assets)
                selected_components = {surface["component"]: surface for surface in selected_snapshot["surfaces"]}
                chooser_confirm = shell_desktop_gtk.dispatch_panel_action(
                    loaded_profile,
                    action_args,
                    selected_snapshot,
                    "portal-chooser",
                    next(
                        action
                        for action in selected_components["portal-chooser"]["model"]["actions"]
                        if action.get("action_id") == "confirm-selection"
                    ),
                )
                require(
                    chooser_confirm["result"]["target_component"] == "task-surface",
                    f"stability iteration {iteration} chooser confirm route mismatch",
                )

                recovery_route = shell_desktop_gtk.dispatch_panel_action(
                    loaded_profile,
                    action_args,
                    selected_snapshot,
                    "notification-center",
                    next(
                        action
                        for action in selected_components["notification-center"]["model"]["actions"]
                        if action.get("action_id") == "open-recovery"
                    ),
                )
                device_route = shell_desktop_gtk.dispatch_panel_action(
                    loaded_profile,
                    action_args,
                    selected_snapshot,
                    "notification-center",
                    next(
                        action
                        for action in selected_components["notification-center"]["model"]["actions"]
                        if action.get("action_id") == "inspect-device-health"
                    ),
                )
                require(
                    recovery_route["result"]["target_component"] == "recovery-surface",
                    f"stability iteration {iteration} recovery route mismatch",
                )
                require(
                    device_route["result"]["target_component"] == "device-backend-status",
                    f"stability iteration {iteration} device route mismatch",
                )

                export_prefix = iteration_root / "artifacts" / "shell-stability"
                export_payload = export_for_iteration(assets, export_prefix)
                json_artifact = Path(export_payload["artifacts"]["json"])
                text_artifact = Path(export_payload["artifacts"]["text"])
                require(json_artifact.exists(), f"stability iteration {iteration} JSON artifact missing")
                require(text_artifact.exists(), f"stability iteration {iteration} text artifact missing")

                exported_snapshot = export_payload["snapshot"]
                require(
                    exported_snapshot["summary"]["active_modal_surface"] is None,
                    f"stability iteration {iteration} exported modal mismatch",
                )
                require(
                    exported_snapshot["summary"]["primary_attention_surface"] == "recovery-surface",
                    f"stability iteration {iteration} exported attention mismatch",
                )

                records.append(
                    {
                        "iteration": iteration,
                        "resume_target_component": launcher_resume["result"]["target_component"],
                        "restore_status": launcher_resume["result"]["restore_status"],
                        "active_modal_sequence": [
                            initial_snapshot["summary"]["active_modal_surface"],
                            post_approval_snapshot["summary"]["active_modal_surface"],
                            exported_snapshot["summary"]["active_modal_surface"],
                        ],
                        "primary_attention_surface": exported_snapshot["summary"]["primary_attention_surface"],
                        "selected_handle_id": chooser_select["result"]["selected_handle_id"],
                        "confirm_target_component": chooser_confirm["result"]["target_component"],
                        "recovery_target_component": recovery_route["result"]["target_component"],
                        "device_target_component": device_route["result"]["target_component"],
                        "surface_count": exported_snapshot["surface_count"],
                        "artifacts": export_payload["artifacts"],
                    }
                )
                artifact_index[f"iteration_{iteration}_json"] = str(json_artifact)
                artifact_index[f"iteration_{iteration}_text"] = str(text_artifact)

        require(records, "stability smoke produced no records")
        expected_sequence = ["approval-panel", "portal-chooser", None]
        for record in records:
            require(
                record["active_modal_sequence"] == expected_sequence,
                f"stability modal sequence mismatch in iteration {record['iteration']}",
            )
            require(
                record["resume_target_component"] == "task-surface",
                f"stability resume route mismatch in iteration {record['iteration']}",
            )
            require(
                record["restore_status"] == "baseline",
                f"stability restore status mismatch in iteration {record['iteration']}",
            )
            require(
                record["primary_attention_surface"] == "recovery-surface",
                f"stability attention mismatch in iteration {record['iteration']}",
            )
            require(
                record["selected_handle_id"] == "handle-screen",
                f"stability handle selection mismatch in iteration {record['iteration']}",
            )
            require(
                record["confirm_target_component"] == "task-surface",
                f"stability confirm route mismatch in iteration {record['iteration']}",
            )
            require(
                record["recovery_target_component"] == "recovery-surface",
                f"stability recovery route mismatch in iteration {record['iteration']}",
            )
            require(
                record["device_target_component"] == "device-backend-status",
                f"stability device route mismatch in iteration {record['iteration']}",
            )

        manifest_path = temp_root / "shell-stability-manifest.json"
        manifest = write_shell_evidence_manifest(
            manifest_path,
            suite="shell-stability",
            artifacts=artifact_index,
            snapshot=None,
            records=records,
            evidence={
                "routes": [
                    {
                        "iteration": record["iteration"],
                        "action": "launcher.resume-session",
                        "target_component": record["resume_target_component"],
                        "status": record["restore_status"],
                    }
                    for record in records
                ]
                + [
                    {
                        "iteration": record["iteration"],
                        "action": "chooser.confirm-selection",
                        "target_component": record["confirm_target_component"],
                        "selected_handle_id": record["selected_handle_id"],
                    }
                    for record in records
                ]
                + [
                    {
                        "iteration": record["iteration"],
                        "action": "notification.open-recovery",
                        "target_component": record["recovery_target_component"],
                    }
                    for record in records
                ]
                + [
                    {
                        "iteration": record["iteration"],
                        "action": "notification.inspect-device-health",
                        "target_component": record["device_target_component"],
                    }
                    for record in records
                ],
                "modal_timeline": [
                    {
                        "iteration": record["iteration"],
                        "phase": "initial",
                        "active_modal_surface": record["active_modal_sequence"][0],
                    }
                    for record in records
                ]
                + [
                    {
                        "iteration": record["iteration"],
                        "phase": "post-approval",
                        "active_modal_surface": record["active_modal_sequence"][1],
                    }
                    for record in records
                ]
                + [
                    {
                        "iteration": record["iteration"],
                        "phase": "exported",
                        "active_modal_surface": record["active_modal_sequence"][2],
                        "primary_attention_surface": record["primary_attention_surface"],
                    }
                    for record in records
                ],
                "restore": {
                    "available": True,
                    "target_component": "task-surface",
                    "recovery_status": "baseline",
                },
            },
            extra={
                "iterations": len(records),
                "expected_modal_sequence": expected_sequence,
            },
        )
        require(manifest_path.exists(), "shell stability manifest missing")
        require(manifest["suite"] == "shell-stability", "shell stability manifest suite mismatch")
        require(len(manifest["records"]) == len(records), "shell stability manifest record count mismatch")
        require(
            len(manifest["evidence"]["modal_timeline"]) == len(records) * 3,
            "shell stability modal timeline evidence mismatch",
        )
        require(
            len(manifest["evidence"]["routes"]) == len(records) * 4,
            "shell stability route evidence mismatch",
        )

        print("shell stability smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell stability smoke failed: {error}")
        return 1
    finally:
        if failed or args.keep_state:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
