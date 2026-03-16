#!/usr/bin/env python3
import json
import os
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
    temp_root = Path(tempfile.mkdtemp(prefix="aios-shell-chooser-"))
    failed = False
    try:
        handle_fixture = temp_root / "portal-handles.json"
        handle_fixture.write_text(
            json.dumps(
                {
                    "request": {
                        "chooser_id": "chooser-1",
                        "title": "Choose Portal Target",
                        "subtitle": "session session-chooser · Screen Share, Export Target · 3 candidates",
                        "status": "pending",
                        "requested_kinds": ["screen_share_handle", "export_target_handle"],
                        "selection_mode": "single",
                        "approval_status": "pending",
                        "attempt_count": 1,
                        "max_attempts": 3,
                        "expires_at": "2026-03-20T10:00:00Z",
                        "audit_tags": ["screen", "portal", "chooser"],
                    },
                    "handles": [
                        {
                            "handle_id": "ph-file",
                            "kind": "file_handle",
                            "target": "/tmp/report.txt",
                            "scope": {
                                "display_name": "report.txt",
                                "target_hash": "hash-file",
                            },
                        },
                        {
                            "handle_id": "ph-export",
                            "kind": "export_target_handle",
                            "target": "/tmp/report.pdf",
                            "scope": {
                                "display_name": "report.pdf",
                                "export_format": "pdf",
                                "adapter_id": "export.local-pdf",
                            },
                        },
                        {
                            "handle_id": "ph-directory",
                            "kind": "directory_handle",
                            "target": "/tmp/reports",
                            "scope": {
                                "display_name": "reports",
                                "target_hash": "hash-directory",
                            },
                        },
                        {
                            "handle_id": "ph-screen",
                            "kind": "screen_share_handle",
                            "target": "screen://current-display",
                            "scope": {
                                "display_name": "Current Display",
                                "backend": "pipewire",
                                "resolution": "2560x1440",
                            },
                        },
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        profile = temp_root / "shell-profile.yaml"
        profile.write_text(
            json.dumps(
                {
                    "profile_id": "portal-chooser-smoke",
                    "components": {
                        "launcher": False,
                        "notification_center": False,
                        "task_surface": False,
                        "approval_panel": False,
                        "recovery_surface": False,
                        "portal_chooser": True,
                        "capture_indicators": False,
                        "device_backend_status": False,
                    },
                    "paths": {
                        "sessiond_socket": "/tmp/missing-sessiond.sock",
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/prototype.py",
            "summary",
            "--handle-fixture",
            str(handle_fixture),
            "--json",
        )
        summary = json.loads(output)
        require(summary["total"] == 4, "portal chooser prototype summary total mismatch")
        require(summary["by_kind"]["screen_share_handle"] == 1, "portal chooser prototype summary screen count mismatch")
        require(summary["by_kind"]["directory_handle"] == 1, "portal chooser prototype summary directory count mismatch")
        require(summary["requested_kinds"] == ["screen_share_handle", "export_target_handle"], "portal chooser prototype request kinds mismatch")
        require(summary["audit_tags"] == ["screen", "portal", "chooser"], "portal chooser prototype audit tag mismatch")
        require(summary["selectable_total"] == 4, "portal chooser prototype selectable total mismatch")
        require(summary["unavailable_total"] == 0, "portal chooser prototype unavailable total mismatch")

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/client.py",
            "summary",
            "--handle-fixture",
            str(handle_fixture),
            "--json",
        )
        client_summary = json.loads(output)
        require(client_summary["by_kind"]["export_target_handle"] == 1, "portal chooser client summary export count mismatch")
        require(client_summary["approval_status"] == "pending", "portal chooser client approval status mismatch")
        require(client_summary["matching_total"] == 2, "portal chooser client matching total mismatch")

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/panel.py",
            "model",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
            "--json",
        )
        panel = json.loads(output)
        require(panel["panel_id"] == "portal-chooser-panel", "portal chooser panel id mismatch")
        require(panel["meta"]["handle_count"] == 4, "portal chooser panel count mismatch")
        require(panel["meta"]["data_source_status"] == "ready", "portal chooser panel data-source status mismatch")
        require(panel["meta"]["focus_handle_id"] == "ph-screen", "portal chooser focus handle mismatch")
        require(panel["header"]["status"] == "pending", "portal chooser initial status mismatch")
        require(panel["sections"][1]["items"][0]["handle_id"] == "ph-screen", "portal chooser ranked handle mismatch")
        require(panel["meta"]["audit_tag_count"] == 3, "portal chooser audit tag count mismatch")
        require(panel["meta"]["history_count"] == 0, "portal chooser initial history count mismatch")
        require(panel["sections"][1]["items"][0]["value"].endswith("resolution=2560x1440"), "portal chooser scope summary mismatch")
        require(
            any(item["label"] == "Audit Tags" for item in panel["sections"][0]["items"]),
            "portal chooser request section should include audit tags",
        )
        require(
            panel["sections"][3]["items"][0]["label"] == "Handle ID",
            "portal chooser selection details section mismatch",
        )

        fallback_panel = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "model",
                "--session-id",
                "session-missing",
                "--json",
            )
        )
        require(
            fallback_panel["meta"]["data_source_status"] == "fallback-empty",
            "portal chooser fallback status mismatch",
        )
        require(
            bool(fallback_panel["meta"]["data_source_error"]),
            "portal chooser fallback error missing",
        )
        require(fallback_panel["header"]["status"] == "failed", "portal chooser fallback header status mismatch")
        require(
            any(item["label"] == "Last Error" for item in fallback_panel["sections"][0]["items"]),
            "portal chooser fallback should expose source error",
        )

        standalone_snapshot = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/standalone.py",
                "snapshot",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(handle_fixture),
                "--json",
            )
        )
        require(
            standalone_snapshot["selected_handle_id"] == "ph-screen",
            "portal chooser standalone snapshot selected handle mismatch",
        )
        require(
            standalone_snapshot["model"]["meta"]["detail_handle_id"] == "ph-screen",
            "portal chooser standalone detail handle mismatch",
        )

        fallback_standalone_snapshot = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/standalone.py",
                "snapshot",
                "--session-id",
                "session-missing",
                "--json",
            )
        )
        require(
            fallback_standalone_snapshot["status"] == "failed",
            "portal chooser fallback standalone status mismatch",
        )
        require(
            fallback_standalone_snapshot["model"]["meta"]["data_source_status"] == "fallback-empty",
            "portal chooser fallback standalone data-source status mismatch",
        )
        require(
            bool(fallback_standalone_snapshot["model"]["meta"]["data_source_error"]),
            "portal chooser fallback standalone error missing",
        )

        export_prefix = temp_root / "portal-chooser-export"
        standalone_export = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/standalone.py",
                "export",
                "--session-id",
                "session-missing",
                "--output-prefix",
                str(export_prefix),
                "--json",
            )
        )
        require(
            standalone_export["snapshot"]["model"]["meta"]["data_source_status"] == "fallback-empty",
            "portal chooser fallback export data-source status mismatch",
        )
        require(
            Path(standalone_export["artifacts"]["json"]).exists(),
            "portal chooser export json artifact missing",
        )
        require(
            Path(standalone_export["artifacts"]["manifest"]).exists(),
            "portal chooser export manifest artifact missing",
        )
        export_manifest = json.loads(Path(standalone_export["artifacts"]["manifest"]).read_text())
        require(export_manifest["summary"]["status"] == "failed", "portal chooser export status mismatch")
        require(export_manifest["summary"]["handle_count"] == 0, "portal chooser export handle count mismatch")

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/panel.py",
            "action",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
            "--action",
            "prefer-requested",
        )
        prefer_requested = json.loads(output)
        require(prefer_requested["status"] == "selected", "portal chooser prefer-requested status mismatch")
        require(prefer_requested["selected_handle_id"] == "ph-screen", "portal chooser prefer-requested handle mismatch")
        require(prefer_requested["history_count"] == 1, "portal chooser prefer-requested history mismatch")

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/panel.py",
            "model",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
            "--json",
        )
        selected_panel = json.loads(output)
        require(selected_panel["header"]["status"] == "selected", "portal chooser selected status mismatch")
        require(selected_panel["meta"]["selected_handle_id"] == "ph-screen", "portal chooser selected handle meta mismatch")
        require(selected_panel["meta"]["history_count"] == 1, "portal chooser selected model history mismatch")

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/panel.py",
            "action",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
            "--action",
            "confirm-selection",
            "--reason",
            "chooser smoke confirm",
        )
        confirmed = json.loads(output)
        require(confirmed["status"] == "confirmed", "portal chooser confirm status mismatch")
        require(confirmed["confirmed_handle_id"] == "ph-screen", "portal chooser confirm handle mismatch")
        require(confirmed["target_component"] == "task-surface", "portal chooser confirm route mismatch")
        require(confirmed["history_count"] == 2, "portal chooser confirm history mismatch")

        approval_fixture = temp_root / "portal-handles-approval.json"
        approval_fixture.write_text(handle_fixture.read_text())
        approval_payload = json.loads(approval_fixture.read_text())
        approval_payload["request"].update(
            {
                "status": "selected",
                "selected_handle_id": "ph-screen",
                "confirmed_handle_id": None,
                "approval_status": "pending",
                "approval_ref": "approval-chooser-1",
                "capability_id": "device.capture.screen",
            }
        )
        approval_fixture.write_text(json.dumps(approval_payload, indent=2, ensure_ascii=False))

        approval_model = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "model",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(approval_fixture),
                "--json",
            )
        )
        require(
            approval_model["meta"]["approval_route_required"] is True,
            "portal chooser approval route should be required",
        )
        require(
            any(item["label"] == "Approval Ref" for item in approval_model["sections"][0]["items"]),
            "portal chooser request section should include approval ref",
        )

        approval_review = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(approval_fixture),
                "--action",
                "review-approval",
            )
        )
        require(
            approval_review["target_component"] == "approval-panel",
            "portal chooser review approval route mismatch",
        )
        require(approval_review["history_count"] >= 3, "portal chooser review approval history mismatch")

        approval_confirm = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(approval_fixture),
                "--action",
                "confirm-selection",
            )
        )
        require(
            approval_confirm["status"] == "awaiting-approval",
            "portal chooser approval-aware confirm status mismatch",
        )
        require(
            approval_confirm["target_component"] == "approval-panel",
            "portal chooser approval-aware confirm route mismatch",
        )
        require(approval_confirm["history_count"] >= 4, "portal chooser approval-aware history mismatch")

        chooser_serve = subprocess.run(
            [
                sys.executable,
                str(ROOT / "aios/shell/components/portal-chooser/standalone.py"),
                "serve",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(handle_fixture),
                "--duration",
                "0.1",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "DISPLAY": "", "WAYLAND_DISPLAY": ""},
        )
        combined = (chooser_serve.stdout + chooser_serve.stderr).strip()
        if chooser_serve.returncode != 0:
            require("Traceback" not in combined, "portal chooser standalone failure should be graceful")
            require(
                "GUI display unavailable" in combined,
                "portal chooser standalone failure message mismatch",
            )

        fixture_payload = json.loads(handle_fixture.read_text())
        fixture_payload["request"]["status"] = "failed"
        fixture_payload["request"]["error_message"] = "portal worker unavailable"
        handle_fixture.write_text(json.dumps(fixture_payload, indent=2, ensure_ascii=False))

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/panel.py",
            "action",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
            "--action",
            "retry-selection",
        )
        retry = json.loads(output)
        require(retry["status"] == "ready", "portal chooser retry status mismatch")

        unavailable_fixture = temp_root / "portal-handles-unavailable.json"
        unavailable_fixture.write_text(
            json.dumps(
                {
                    "request": {
                        "chooser_id": "chooser-unavailable",
                        "title": "Choose Screen Share Target",
                        "status": "pending",
                        "requested_kinds": ["screen_share_handle"],
                        "selection_mode": "single",
                        "approval_status": "not-required",
                        "attempt_count": 1,
                        "max_attempts": 3,
                    },
                    "handles": [
                        {
                            "handle_id": "ph-screen-unavailable",
                            "kind": "screen_share_handle",
                            "target": "screen://display-2",
                            "availability": "unavailable",
                            "unavailable_reason": "screen backend busy",
                            "retry_after": "2026-03-20T10:05:00Z",
                            "scope": {
                                "display_name": "Conference Display",
                                "backend": "pipewire",
                                "display_ref": "display-2",
                            },
                        },
                        {
                            "handle_id": "ph-file-fallback",
                            "kind": "file_handle",
                            "target": "/tmp/fallback.txt",
                            "scope": {
                                "display_name": "fallback.txt",
                            },
                        },
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        unavailable_model = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "model",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(unavailable_fixture),
                "--json",
            )
        )
        require(unavailable_model["header"]["status"] == "failed", "portal chooser unavailable status mismatch")
        require(unavailable_model["meta"]["unavailable_handle_count"] == 1, "portal chooser unavailable count mismatch")
        require(
            unavailable_model["meta"]["detail_handle_id"] == "ph-screen-unavailable",
            "portal chooser unavailable detail handle mismatch",
        )
        require(
            any(
                item["handle_id"] == "ph-screen-unavailable" and item["status"] == "retry-later"
                for item in unavailable_model["sections"][1]["items"]
            ),
            "portal chooser unavailable handle status mismatch",
        )
        require(
            any(item["label"] == "Retry After" for item in unavailable_model["sections"][0]["items"]),
            "portal chooser request should expose retry-after",
        )
        confirm_action = next(
            item for item in unavailable_model["actions"] if item.get("action_id") == "confirm-selection"
        )
        require(confirm_action["enabled"] is False, "portal chooser confirm should be disabled for unavailable request")

        unavailable_summary = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/client.py",
                "summary",
                "--handle-fixture",
                str(unavailable_fixture),
                "--json",
            )
        )
        require(unavailable_summary["status"] == "pending", "portal chooser unavailable client status mismatch")
        require(
            unavailable_summary["requested_unavailable_total"] == 1,
            "portal chooser unavailable requested count mismatch",
        )
        require(
            unavailable_summary["retry_after"] == "2026-03-20T10:05:00Z",
            "portal chooser unavailable client retry-after mismatch",
        )

        unavailable_select = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(unavailable_fixture),
                "--action",
                "select-handle",
                "--handle-id",
                "ph-screen-unavailable",
            )
        )
        require(unavailable_select["status"] == "failed", "portal chooser unavailable select should fail")
        require(
            unavailable_select["error_message"] == "screen backend busy",
            "portal chooser unavailable select error mismatch",
        )
        require(
            unavailable_select["retry_after"] == "2026-03-20T10:05:00Z",
            "portal chooser unavailable select retry-after mismatch",
        )

        unavailable_retry = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(unavailable_fixture),
                "--action",
                "retry-selection",
            )
        )
        require(unavailable_retry["status"] == "ready", "portal chooser unavailable retry status mismatch")
        require(unavailable_retry["history_count"] == 2, "portal chooser unavailable retry history mismatch")

        fallback_select = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(unavailable_fixture),
                "--action",
                "select-handle",
                "--handle-id",
                "ph-file-fallback",
            )
        )
        require(
            fallback_select["selected_handle_id"] == "ph-file-fallback",
            "portal chooser fallback select mismatch",
        )

        fallback_confirm = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(unavailable_fixture),
                "--action",
                "confirm-selection",
            )
        )
        require(fallback_confirm["status"] == "confirmed", "portal chooser fallback confirm mismatch")
        require(
            fallback_confirm["target_component"] == "task-surface",
            "portal chooser fallback route mismatch",
        )

        timeout_fixture = temp_root / "portal-handles-timeout.json"
        timeout_fixture.write_text(
            json.dumps(
                {
                    "request": {
                        "chooser_id": "chooser-timeout",
                        "status": "timed_out",
                        "requested_kinds": ["export_target_handle"],
                        "selection_mode": "single",
                        "approval_status": "not-required",
                        "attempt_count": 2,
                        "max_attempts": 3,
                        "error_message": "portal request timed out",
                    },
                    "handles": [],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        timeout_model = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "model",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(timeout_fixture),
                "--json",
            )
        )
        require(timeout_model["header"]["status"] == "timed-out", "portal chooser timeout normalization mismatch")

        timeout_retry = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "session-chooser",
                "--handle-fixture",
                str(timeout_fixture),
                "--action",
                "retry-selection",
            )
        )
        require(timeout_retry["status"] == "pending", "portal chooser timeout retry mismatch")
        require(timeout_retry["history_count"] == 1, "portal chooser timeout retry history mismatch")

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/panel.py",
            "action",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
            "--action",
            "select-handle",
            "--handle-id",
            "ph-file",
        )
        manual_select = json.loads(output)
        require(manual_select["selected_handle_id"] == "ph-file", "portal chooser manual select handle mismatch")

        output = run_python(
            ROOT / "aios/shell/components/portal-chooser/panel.py",
            "action",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
            "--action",
            "cancel-selection",
            "--reason",
            "chooser smoke cancel",
        )
        cancelled = json.loads(output)
        require(cancelled["status"] == "cancelled", "portal chooser cancel status mismatch")

        output = run_python(
            ROOT / "aios/shell/shellctl.py",
            "--profile",
            str(profile),
            "--json",
            "panel",
            "portal-chooser",
            "model",
            "--session-id",
            "session-chooser",
            "--handle-fixture",
            str(handle_fixture),
        )
        shellctl_panel = json.loads(output)
        require(shellctl_panel["panel_id"] == "portal-chooser-panel", "shellctl portal chooser panel mismatch")
        require(shellctl_panel["meta"]["handle_summary"]["file_handle"] == 1, "shellctl portal chooser handle summary mismatch")
        require(shellctl_panel["header"]["status"] == "cancelled", "shellctl portal chooser final status mismatch")
        require(shellctl_panel["meta"]["history_count"] >= 5, "shellctl portal chooser final history mismatch")

        print("shell chooser smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"shell chooser smoke failed: {error}")
        return 1
    finally:
        if not failed:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

