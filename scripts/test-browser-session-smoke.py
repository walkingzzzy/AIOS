#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "aios" / "compat" / "browser" / "runtime" / "browser_provider.py"
DEFAULT_WORK_ROOT = ROOT / "out" / "validation" / "browser-session-smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS browser session lifecycle smoke harness")
    parser.add_argument("--keep-state", action="store_true", help="Keep generated fixtures on success")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for generated fixtures and audit logs")
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_json_command(*args: str, check: bool = True, env: dict[str, str] | None = None) -> tuple[int, dict]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        [sys.executable, str(RUNTIME), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=command_env,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {sys.executable} {RUNTIME} {' '.join(args)}\n"
            f"{completed.stderr.strip()}\n{completed.stdout.strip()}"
        )
    return completed.returncode, json.loads(completed.stdout)


def find_session(payload: dict[str, object], session_id: str) -> dict[str, object]:
    sessions = payload.get("sessions") or []
    for session in sessions:
        if isinstance(session, dict) and session.get("session_id") == session_id:
            return session
    raise RuntimeError(f"session not found in payload: {session_id}")


def find_window(session: dict[str, object], window_id: str) -> dict[str, object]:
    windows = session.get("windows") or []
    for window in windows:
        if isinstance(window, dict) and window.get("window_id") == window_id:
            return window
    raise RuntimeError(f"window not found in payload: {window_id}")


def find_tab(window: dict[str, object], tab_id: str) -> dict[str, object]:
    tabs = window.get("tabs") or []
    for tab in tabs:
        if isinstance(tab, dict) and tab.get("tab_id") == tab_id:
            return tab
    raise RuntimeError(f"tab not found in payload: {tab_id}")


def main() -> int:
    args = parse_args()
    if args.output_dir is not None:
        temp_root = args.output_dir
        temp_root.mkdir(parents=True, exist_ok=True)
    else:
        if DEFAULT_WORK_ROOT.exists():
            shutil.rmtree(DEFAULT_WORK_ROOT, ignore_errors=True)
        DEFAULT_WORK_ROOT.mkdir(parents=True, exist_ok=True)
        temp_root = DEFAULT_WORK_ROOT

    failed = False
    try:
        audit_log = temp_root / "browser-session-audit.jsonl"
        session_store = temp_root / "browser-session-store.json"
        env = dict(os.environ)
        env["AIOS_COMPAT_BROWSER_AUDIT_LOG"] = str(audit_log)
        env["AIOS_BROWSER_SESSION_STORE"] = str(session_store)

        fixture_path = temp_root / "fixture.html"
        fixture_path.write_text(
            """
            <html>
              <head>
                <title>AIOS Browser Session Smoke</title>
              </head>
              <body>
                <h1>Session Lifecycle</h1>
                <div id="content">Session lifecycle state is persisted.</div>
                <p class="note">Bindings are written back to the session store.</p>
                <a href="https://example.com/session">Session Docs</a>
              </body>
            </html>
            """.strip(),
            encoding="utf-8",
        )
        fixture_url = fixture_path.resolve().as_uri()

        _, health = run_json_command("health", env=env)
        require(health["status"] == "available", "health status should be available")
        require(health["session_store_path"] == str(session_store), "health session store path mismatch")
        require(health["active_session_count"] == 0, "health should start with zero active sessions")

        _, opened_session = run_json_command("open-session", env=env)
        require(opened_session["opened"] is True, "open-session should report opened")
        require(opened_session["active_session_count"] == 1, "open-session should create one active session")
        require(opened_session["session_store"] == str(session_store), "open-session session store mismatch")
        session_id = opened_session["session"]["session_id"]
        first_window_id = opened_session["window"]["window_id"]
        first_tab_id = opened_session["tab"]["tab_id"]
        require(opened_session["session"]["active_window_id"] == first_window_id, "initial active window mismatch")
        require(opened_session["window"]["active_tab_id"] == first_tab_id, "initial active tab mismatch")

        _, listed_initial = run_json_command("list-sessions", env=env)
        require(listed_initial["provider_id"] == "compat.browser.automation.local", "list-sessions provider mismatch")
        require(listed_initial["active_session_count"] == 1, "list-sessions should report one active session")
        initial_session = find_session(listed_initial, session_id)
        require(initial_session["active_window_id"] == first_window_id, "listed initial active window mismatch")

        _, opened_window = run_json_command("open-window", "--session-id", session_id, env=env)
        second_window_id = opened_window["window"]["window_id"]
        base_window_tab_id = opened_window["tab"]["tab_id"]
        require(second_window_id != first_window_id, "open-window should create a distinct window")
        require(opened_window["session"]["active_window_id"] == second_window_id, "open-window active window mismatch")
        require(opened_window["window"]["active_tab_id"] == base_window_tab_id, "open-window active tab mismatch")

        _, opened_tab = run_json_command(
            "open-tab",
            "--session-id",
            session_id,
            "--window-id",
            second_window_id,
            env=env,
        )
        active_tab_id = opened_tab["tab"]["tab_id"]
        require(active_tab_id != base_window_tab_id, "open-tab should create a distinct tab")
        require(opened_tab["window"]["active_tab_id"] == active_tab_id, "open-tab active tab mismatch")

        _, navigate = run_json_command(
            "navigate",
            "--url",
            fixture_url,
            "--session-id",
            session_id,
            "--window-id",
            second_window_id,
            "--tab-id",
            active_tab_id,
            "--max-links",
            "4",
            "--max-text-chars",
            "160",
            env=env,
        )
        require(navigate["status"] == "ok", "navigate should return ok")
        require(navigate["title"] == "AIOS Browser Session Smoke", "navigate title mismatch")
        require(navigate["session_store"] == str(session_store), "navigate session store mismatch")
        require(navigate["session"]["session_id"] == session_id, "navigate session binding mismatch")
        require(navigate["window"]["window_id"] == second_window_id, "navigate window binding mismatch")
        require(navigate["tab"]["tab_id"] == active_tab_id, "navigate tab binding mismatch")
        require(navigate["tab"]["url"] == fixture_url, "navigate tab url mismatch")
        require(navigate["tab"]["title"] == "AIOS Browser Session Smoke", "navigate tab title mismatch")
        require(navigate["tab"]["history"] == [fixture_url], "navigate tab history mismatch")
        navigate_request = (navigate.get("result_protocol") or {}).get("request") or {}
        require(navigate_request.get("session_id") == session_id, "navigate result protocol session_id mismatch")
        require(navigate_request.get("window_id") == second_window_id, "navigate result protocol window_id mismatch")
        require(navigate_request.get("tab_id") == active_tab_id, "navigate result protocol tab_id mismatch")

        _, extract = run_json_command(
            "extract",
            "--url",
            fixture_url,
            "--selector",
            "#content",
            "--session-id",
            session_id,
            "--window-id",
            second_window_id,
            "--tab-id",
            active_tab_id,
            env=env,
        )
        require(extract["status"] == "ok", "extract should return ok")
        require(extract["matched_count"] == 1, "extract matched_count mismatch")
        require(extract["text"] == "Session lifecycle state is persisted.", "extract text mismatch")
        require(extract["tab"]["last_selector"] == "#content", "extract last_selector mismatch")
        require(extract["tab"]["text_preview"] == "Session lifecycle state is persisted.", "extract text_preview mismatch")
        require(extract["tab"]["matched_count"] == 1, "extract tab matched_count mismatch")
        extract_request = (extract.get("result_protocol") or {}).get("request") or {}
        require(extract_request.get("session_id") == session_id, "extract result protocol session_id mismatch")
        require(extract_request.get("window_id") == second_window_id, "extract result protocol window_id mismatch")
        require(extract_request.get("tab_id") == active_tab_id, "extract result protocol tab_id mismatch")

        _, listed_after = run_json_command("list-sessions", env=env)
        require(listed_after["active_session_count"] == 1, "list-sessions should keep one active session")
        stored_session = find_session(listed_after, session_id)
        stored_window = find_window(stored_session, second_window_id)
        stored_tab = find_tab(stored_window, active_tab_id)
        require(stored_session["active_window_id"] == second_window_id, "stored session active window mismatch")
        require(stored_window["active_tab_id"] == active_tab_id, "stored window active tab mismatch")
        require(stored_tab["url"] == fixture_url, "stored tab url mismatch")
        require(stored_tab["history"] == [fixture_url], "stored tab history mismatch")
        require(stored_tab["last_selector"] == "#content", "stored tab selector mismatch")
        require(stored_tab["matched_count"] == 1, "stored tab matched_count mismatch")
        require(stored_tab["link_count"] == 1, "stored tab link_count mismatch")

        _, closed_tab = run_json_command(
            "close-tab",
            "--session-id",
            session_id,
            "--tab-id",
            active_tab_id,
            env=env,
        )
        require(closed_tab["closed"] is True, "close-tab should report closed")
        require(closed_tab["tab"]["tab_id"] == active_tab_id, "close-tab removed tab mismatch")
        require(closed_tab["window"]["window_id"] == second_window_id, "close-tab window mismatch")
        require(closed_tab["window"]["active_tab_id"] == base_window_tab_id, "close-tab fallback active tab mismatch")

        _, closed_window = run_json_command(
            "close-window",
            "--session-id",
            session_id,
            "--window-id",
            second_window_id,
            env=env,
        )
        require(closed_window["closed"] is True, "close-window should report closed")
        require(closed_window["window"]["window_id"] == second_window_id, "close-window removed window mismatch")
        require(closed_window["session"]["active_window_id"] == first_window_id, "close-window fallback active window mismatch")

        _, closed_session = run_json_command("close-session", "--session-id", session_id, env=env)
        require(closed_session["closed"] is True, "close-session should report closed")
        require(closed_session["active_session_count"] == 0, "close-session active session count mismatch")
        require(closed_session["session"]["session_id"] == session_id, "close-session removed session mismatch")

        _, listed_final = run_json_command("list-sessions", env=env)
        require(listed_final["active_session_count"] == 0, "final list-sessions should be empty")
        require(listed_final["sessions"] == [], "final list-sessions payload mismatch")

        require(audit_log.exists(), "session smoke should produce audit log")
        audit_entries = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        require(len(audit_entries) >= 2, "session smoke audit log entry count mismatch")
        navigate_entry = next((entry for entry in audit_entries if entry.get("operation") == "compat.browser.navigate"), None)
        extract_entry = next((entry for entry in audit_entries if entry.get("operation") == "compat.browser.extract"), None)
        require(navigate_entry is not None, "audit log missing navigate entry")
        require(extract_entry is not None, "audit log missing extract entry")
        require((navigate_entry.get("result") or {}).get("browser_session_id") == session_id, "audit navigate session binding mismatch")
        require((navigate_entry.get("result") or {}).get("browser_window_id") == second_window_id, "audit navigate window binding mismatch")
        require((navigate_entry.get("result") or {}).get("browser_tab_id") == active_tab_id, "audit navigate tab binding mismatch")
        require((extract_entry.get("result") or {}).get("browser_session_id") == session_id, "audit extract session binding mismatch")
        require((extract_entry.get("result") or {}).get("browser_window_id") == second_window_id, "audit extract window binding mismatch")
        require((extract_entry.get("result") or {}).get("browser_tab_id") == active_tab_id, "audit extract tab binding mismatch")
        require(all(entry.get("artifact_path") == str(audit_log) for entry in audit_entries), "session smoke artifact_path mismatch")

        print(
            json.dumps(
                {
                    "provider_id": opened_session["provider_id"],
                    "session_store": str(session_store),
                    "session_id": session_id,
                    "window_id": second_window_id,
                    "tab_id": active_tab_id,
                    "navigate_title": navigate["title"],
                    "extract_text": extract["text"],
                    "audit_log": str(audit_log),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except Exception:
        failed = True
        raise
    finally:
        preserve_state = failed or args.keep_state or args.output_dir is not None
        if preserve_state:
            print(f"state preserved at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
