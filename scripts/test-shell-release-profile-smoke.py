#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RELEASE_PROFILE = ROOT / "aios" / "shell" / "profiles" / "release-shell-profile.yaml"
SESSION_ENTRYPOINT = ROOT / "aios" / "shell" / "runtime" / "shell_session.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_python(*args: str) -> str:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def run_json(*args: str) -> dict:
    output = run_python(*args)
    require(bool(output), f"no output from {' '.join(args)}")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        lines = [line for line in output.splitlines() if line.strip()]
        require(lines, f"no JSON payload from {' '.join(args)}")
        return json.loads(lines[-1])


def main() -> int:
    require(RELEASE_PROFILE.exists(), "release shell profile missing")

    plan = run_json(str(SESSION_ENTRYPOINT), "plan", "--profile", str(RELEASE_PROFILE), "--json")
    require(plan["profile_id"] == "release-shell", "release profile id mismatch")
    require(plan["entrypoint"] == "formal", "release profile entrypoint mismatch")
    require(plan["desktop_host"] == "gtk", "release profile desktop host mismatch")
    require(plan["session_backend"] == "compositor", "release profile backend mismatch")
    require(
        plan["host_runtime"]["nested_fallback"] == "disabled",
        "release profile nested fallback mismatch",
    )
    require(
        plan["host_runtime"]["compositor_required"] is True,
        "release profile compositor_required mismatch",
    )
    require(
        plan["compositor"]["backend_mode"] == "drm-kms",
        "release profile compositor backend mismatch",
    )
    require(
        Path(plan["compositor"]["config_path"]).name == "release-compositor.conf",
        "release profile compositor config mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_BACKEND"] == "drm-kms",
        "release profile compositor env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_DRM_DISABLE_CONNECTORS"] == "false",
        "release profile connector env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_WORKSPACE_TOPLEVEL_MODE"] == "fullscreen",
        "release profile workspace mode env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_WORKSPACE_COUNT"] == 4,
        "release profile workspace count env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_DEFAULT_WORKSPACE_INDEX"] == 0,
        "release profile default workspace env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_OUTPUT_LAYOUT_MODE"] == "horizontal",
        "release profile output layout env mismatch",
    )
    require(
        str(plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_WINDOW_STATE_PATH"]).endswith(
            "/var/lib/aios/shell/compositor/release-windows.json"
        ),
        "release profile window state env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_RUNTIME_LOCK_PATH"]
        == "/run/aios/shell/compositor/release.lock",
        "release profile runtime lock env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_RUNTIME_READY_PATH"]
        == "/run/aios/shell/compositor/release-ready.json",
        "release profile runtime ready env mismatch",
    )
    require(
        str(plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_PATH"]).endswith(
            "/var/lib/aios/shell/compositor/release-state.json"
        ),
        "release profile runtime state env mismatch",
    )
    require(
        plan["compositor"]["env"]["AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_REFRESH_TICKS"] == 1,
        "release profile runtime state refresh env mismatch",
    )

    probe = run_json(str(SESSION_ENTRYPOINT), "probe", "--profile", str(RELEASE_PROFILE), "--json")
    require(probe["compositor_backend"] == "drm-kms", "release probe backend mismatch")
    require("process_boundary_status" in probe, "release probe process boundary status missing")
    require("runtime_lock_status" in probe, "release probe runtime lock status missing")
    require("runtime_ready_status" in probe, "release probe runtime ready status missing")
    require("runtime_state_status" in probe, "release probe runtime state status missing")
    require("input_backend_status" in probe, "release probe input backend status missing")
    require("workspace_toplevel_mode" in probe, "release probe workspace mode missing")
    require("workspace_count" in probe, "release probe workspace count missing")
    require("active_workspace_id" in probe, "release probe active workspace missing")
    require("window_state_path" in probe, "release probe window state path missing")
    require("output_layout_mode" in probe, "release probe output layout missing")
    require("minimized_window_count" in probe, "release probe minimized window count missing")
    require("window_minimize_count" in probe, "release probe window minimize count missing")
    require("window_restore_count" in probe, "release probe window restore count missing")
    require("workspace_window_counts" in probe, "release probe workspace window counts missing")
    require("drm_connector_name" in probe, "release probe drm connector field missing")

    require(probe["workspace_toplevel_mode"] == "fullscreen", "release probe workspace mode mismatch")
    require(probe["workspace_count"] == 4, "release probe workspace count mismatch")
    require(probe["active_workspace_id"] == "workspace-1", "release probe active workspace mismatch")
    require(
        str(probe["window_state_path"]).endswith("/var/lib/aios/shell/compositor/release-windows.json"),
        "release probe window state path mismatch",
    )
    require(probe["output_layout_mode"] == "horizontal", "release probe output layout mismatch")
    require(probe["minimized_window_count"] == 0, "release probe minimized window count mismatch")
    require(probe["window_minimize_count"] == 0, "release probe window minimize count mismatch")
    require(probe["window_restore_count"] == 0, "release probe window restore count mismatch")
    require(probe["workspace_window_counts"] == {}, "release probe workspace window counts mismatch")

    if sys.platform.startswith("linux"):
        require(
            probe["lifecycle_state"] in {"probe-ready", "probe-failed"},
            "linux release probe lifecycle mismatch",
        )
        require(
            probe["smithay_status"] == "smithay-drm-kms",
            "linux release probe smithay status mismatch",
        )
        require(
            probe["renderer_backend"] == "drm-kms-gbm-egl",
            "linux release probe renderer backend mismatch",
        )
        if probe["lifecycle_state"] == "probe-ready":
            require(
                probe["renderer_status"].startswith("active("),
                "linux release probe should expose active renderer status",
            )
        else:
            require(
                probe["renderer_status"].startswith("probe-failed:"),
                "linux release probe failure status mismatch",
            )
    else:
        require(
            probe["lifecycle_state"] == "probe-unavailable",
            "non-linux release probe lifecycle mismatch",
        )
        require(
            probe["smithay_status"] == "drm-kms-unavailable-non-linux",
            "non-linux release probe smithay status mismatch",
        )
        require(
            probe["renderer_status"] == "drm-kms-unavailable-non-linux",
            "non-linux release probe renderer status mismatch",
        )

    print("shell release profile smoke passed")
    print(
        json.dumps(
            {
                "profile_id": plan["profile_id"],
                "backend_mode": plan["compositor"]["backend_mode"],
                "probe_lifecycle": probe["lifecycle_state"],
                "probe_renderer_status": probe["renderer_status"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
