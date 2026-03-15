#!/usr/bin/env python3
from __future__ import annotations

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
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="aios-portal-flow-"))
    failed = False
    try:
        chooser_fixture = temp_root / "chooser-fixture.json"
        chooser_fixture_approval = temp_root / "chooser-fixture-approval.json"
        chooser_fixture_cancel = temp_root / "chooser-fixture-cancel.json"
        chooser_fixture_unavailable = temp_root / "chooser-fixture-unavailable.json"
        profile = temp_root / "shell-profile.json"
        export_prefix = temp_root / "portal-artifacts" / "chooser-flow"

        base_payload = {
            "request": {
                "chooser_id": "portal-flow",
                "title": "Choose Portal Target",
                "subtitle": "session portal-session-1 · export, screen · 4 candidates",
                "status": "pending",
                "requested_kinds": ["screen_share_handle", "export_target_handle"],
                "selection_mode": "single",
                "approval_status": "not-required",
                "attempt_count": 0,
                "max_attempts": 3,
                "audit_tags": ["portal", "flow", "smoke"],
            },
            "handles": [
                {
                    "handle_id": "handle-file",
                    "kind": "file_handle",
                    "target": "/workspace/report.md",
                    "scope": {"display_name": "report.md"},
                },
                {
                    "handle_id": "handle-directory",
                    "kind": "directory_handle",
                    "target": "/workspace/reports",
                    "scope": {"display_name": "reports"},
                },
                {
                    "handle_id": "handle-export",
                    "kind": "export_target_handle",
                    "target": "/workspace/export/report.pdf",
                    "scope": {
                        "display_name": "report.pdf",
                        "export_format": "pdf",
                        "export_label": "Share as PDF",
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
        }
        write_json(chooser_fixture, base_payload)
        write_json(chooser_fixture_cancel, json.loads(json.dumps(base_payload)))

        approval_payload = json.loads(json.dumps(base_payload))
        approval_payload["request"].update(
            {
                "status": "selected",
                "selected_handle_id": "handle-screen",
                "approval_status": "pending",
                "approval_ref": "approval-portal-flow-1",
                "capability_id": "device.capture.screen.read",
            }
        )
        write_json(chooser_fixture_approval, approval_payload)
        write_json(
            chooser_fixture_unavailable,
            {
                "request": {
                    "chooser_id": "portal-flow-unavailable",
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
                        "handle_id": "handle-screen-unavailable",
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
                        "handle_id": "handle-export-fallback",
                        "kind": "export_target_handle",
                        "target": "/workspace/export/fallback.pdf",
                        "scope": {
                            "display_name": "fallback.pdf",
                            "export_format": "pdf",
                            "export_label": "Fallback PDF",
                        },
                    },
                ],
            },
        )

        write_json(
            profile,
            {
                "profile_id": "portal-flow-smoke",
                "components": {
                    "portal_chooser": True,
                },
                "paths": {
                    "sessiond_socket": "/tmp/missing-sessiond.sock",
                },
            },
        )

        prototype_summary = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/prototype.py",
                "summary",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture),
                "--json",
            )
        )
        require(prototype_summary["total"] == 4, "portal flow prototype total mismatch")
        require(
            prototype_summary["audit_tags"] == ["portal", "flow", "smoke"],
            "portal flow prototype audit tags mismatch",
        )

        chooser_snapshot = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/standalone.py",
                "snapshot",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture),
                "--json",
            )
        )
        require(
            chooser_snapshot["selected_handle_id"] == "handle-screen",
            "portal flow standalone selected handle mismatch",
        )

        chooser_export = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/standalone.py",
                "export",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture),
                "--output-prefix",
                str(export_prefix),
                "--json",
            )
        )
        json_artifact = Path(chooser_export["artifacts"]["json"])
        text_artifact = Path(chooser_export["artifacts"]["text"])
        manifest_artifact = Path(chooser_export["artifacts"]["manifest"])
        require(json_artifact.exists(), "portal flow standalone JSON artifact missing")
        require(text_artifact.exists(), "portal flow standalone text artifact missing")
        require(manifest_artifact.exists(), "portal flow standalone manifest artifact missing")
        require(
            "Choose Portal Target" in text_artifact.read_text(),
            "portal flow standalone text artifact mismatch",
        )
        chooser_manifest = json.loads(manifest_artifact.read_text())
        require(chooser_manifest["suite"] == "portal-chooser-export", "portal flow standalone manifest suite mismatch")
        require(
            chooser_manifest["summary"]["handle_count"] == 4,
            "portal flow standalone manifest handle count mismatch",
        )
        require(
            chooser_manifest["summary"]["unavailable_handle_count"] == 0,
            "portal flow standalone manifest unavailable count mismatch",
        )

        shellctl_snapshot = json.loads(
            run_python(
                ROOT / "aios/shell/shellctl.py",
                "--profile",
                str(profile),
                "--json",
                "chooser",
                "snapshot",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture),
            )
        )
        require(
            shellctl_snapshot["model"]["meta"]["handle_count"] == 4,
            "portal flow shellctl chooser handle count mismatch",
        )

        approval_review = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_approval),
                "--action",
                "review-approval",
            )
        )
        require(
            approval_review["target_component"] == "approval-panel",
            "portal flow approval review route mismatch",
        )
        require(approval_review["history_count"] >= 1, "portal flow approval review history mismatch")

        approval_confirm = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_approval),
                "--action",
                "confirm-selection",
            )
        )
        require(
            approval_confirm["status"] == "awaiting-approval",
            "portal flow approval confirm status mismatch",
        )
        require(
            approval_confirm["target_component"] == "approval-panel",
            "portal flow approval confirm route mismatch",
        )
        require(approval_confirm["history_count"] >= 2, "portal flow approval confirm history mismatch")

        export_select = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture),
                "--action",
                "select-handle",
                "--handle-id",
                "handle-export",
            )
        )
        require(
            export_select["selected_handle_id"] == "handle-export",
            "portal flow export select mismatch",
        )
        require(export_select["history_count"] >= 1, "portal flow export select history mismatch")

        export_confirm = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture),
                "--action",
                "confirm-selection",
            )
        )
        require(export_confirm["status"] == "confirmed", "portal flow export confirm mismatch")
        require(
            export_confirm["target_component"] == "task-surface",
            "portal flow export confirm route mismatch",
        )
        require(export_confirm["history_count"] >= 2, "portal flow export confirm history mismatch")

        cancel_result = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_cancel),
                "--action",
                "cancel-selection",
                "--reason",
                "portal flow cancel",
            )
        )
        require(cancel_result["status"] == "cancelled", "portal flow cancel mismatch")
        require(cancel_result["history_count"] >= 1, "portal flow cancel history mismatch")

        unavailable_model = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "model",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_unavailable),
                "--json",
            )
        )
        require(unavailable_model["header"]["status"] == "failed", "portal flow unavailable status mismatch")
        require(
            unavailable_model["meta"]["detail_handle_id"] == "handle-screen-unavailable",
            "portal flow unavailable detail mismatch",
        )
        require(
            any(item["label"] == "Retry After" for item in unavailable_model["sections"][0]["items"]),
            "portal flow unavailable retry-after missing",
        )

        unavailable_select = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_unavailable),
                "--action",
                "select-handle",
                "--handle-id",
                "handle-screen-unavailable",
            )
        )
        require(unavailable_select["status"] == "failed", "portal flow unavailable select mismatch")
        require(
            unavailable_select["error_message"] == "screen backend busy",
            "portal flow unavailable error mismatch",
        )

        unavailable_retry = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_unavailable),
                "--action",
                "retry-selection",
            )
        )
        require(unavailable_retry["status"] == "ready", "portal flow unavailable retry mismatch")
        require(unavailable_retry["history_count"] >= 2, "portal flow unavailable retry history mismatch")

        fallback_select = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_unavailable),
                "--action",
                "select-handle",
                "--handle-id",
                "handle-export-fallback",
            )
        )
        require(
            fallback_select["selected_handle_id"] == "handle-export-fallback",
            "portal flow fallback select mismatch",
        )

        fallback_confirm = json.loads(
            run_python(
                ROOT / "aios/shell/components/portal-chooser/panel.py",
                "action",
                "--session-id",
                "portal-session-1",
                "--handle-fixture",
                str(chooser_fixture_unavailable),
                "--action",
                "confirm-selection",
            )
        )
        require(fallback_confirm["status"] == "confirmed", "portal flow fallback confirm mismatch")
        require(
            fallback_confirm["target_component"] == "task-surface",
            "portal flow fallback route mismatch",
        )

        print("portal flow smoke passed")
        return 0
    except Exception as error:
        failed = True
        print(f"portal flow smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
