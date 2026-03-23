#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios.compat.runtime_support import (
    CompatPolicyContext,
    CompatPolicyError,
    add_policy_args,
    append_jsonl,
    resolve_policy_context,
    standalone_policy_context,
)
from aios.compat.remote_runtime_support import (
    RemoteAttestation,
    RemoteGovernance,
    RemoteRegistration,
    RemoteSupportError,
    VALID_REMOTE_ATTESTATION_MODES,
    VALID_REMOTE_AUTH_MODES,
    agentd_rpc,
    agentd_socket_path,
    encode_execution_token,
    find_remote_registration,
    load_remote_registry,
    normalize_remote_provider_id,
    post_json,
    remote_registration_status,
    remote_registration_summary,
    remote_target_hash,
    remove_remote_registration,
    revoke_remote_registration,
    resolve_trust_policy,
    touch_remote_registration,
    upsert_remote_registration,
    write_remote_registry,
)


PROVIDER_ID = "compat.browser.automation.local"
DECLARED_CAPABILITIES = [
    "compat.browser.navigate",
    "compat.browser.extract",
]
REQUIRED_PERMISSIONS = [
    "browser.compat",
]
COMPAT_PERMISSION_SCHEMA_REF = "aios/compat-permission-manifest.schema.json"
RESULT_PROTOCOL_SCHEMA_REF = "aios/compat-browser-result.schema.json"
DESCRIPTOR_FILENAME = "browser.automation.local.json"
WORKER_CONTRACT = "compat-browser-fetch-v1"
AUDIT_SCHEMA_VERSION = "2026-03-13"
DEFAULT_AUDIT_LOG_ENV = "AIOS_COMPAT_BROWSER_AUDIT_LOG"
DEFAULT_USER_ID = "compat-user"
DEFAULT_SESSION_ID = "compat-session"
DEFAULT_TASK_ID = "compat-task"
DEFAULT_REMOTE_REGISTRY_ENV = "AIOS_BROWSER_REMOTE_REGISTRY"
DEFAULT_REMOTE_AUTH_SECRET_ENV = "AIOS_BROWSER_REMOTE_AUTH_SECRET"
DEFAULT_TRUST_MODE_ENV = "AIOS_BROWSER_TRUST_MODE"
DEFAULT_ALLOWLIST_ENV = "AIOS_BROWSER_ALLOWLIST"
DEFAULT_REMOTE_ATTESTATION_MODE_ENV = "AIOS_BROWSER_REMOTE_ATTESTATION_MODE"
DEFAULT_REMOTE_FLEET_ID_ENV = "AIOS_BROWSER_REMOTE_FLEET_ID"
DEFAULT_REMOTE_GOVERNANCE_GROUP_ENV = "AIOS_BROWSER_REMOTE_GOVERNANCE_GROUP"
DEFAULT_REMOTE_POLICY_GROUP_ENV = "AIOS_BROWSER_REMOTE_POLICY_GROUP"
DEFAULT_REMOTE_APPROVAL_REF_ENV = "AIOS_BROWSER_REMOTE_APPROVAL_REF"
DEFAULT_SESSION_STORE_ENV = "AIOS_BROWSER_SESSION_STORE"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TEXT_PREVIEW_CHARS = 240
DEFAULT_TIMEOUT_SECONDS = 10.0
WHITESPACE_RE = re.compile(r"\s+")
PROVIDER_REGISTER_METHOD = "provider.register"
COMMAND_EXIT_CODES = {
    "invalid_request": 2,
    "precondition_failed": 3,
    "permission_denied": 13,
    "timeout": 124,
    "unavailable": 69,
    "remote_error": 70,
    "internal": 1,
}


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    resolved_url: str
    final_url: str
    status_code: int
    content_type: str
    charset: str | None
    body_text: str
    truncated: bool
    fetched_at: str


@dataclass(frozen=True)
class Selector:
    kind: str
    value: str


@dataclass(frozen=True)
class BrowserContext:
    command: str
    operation: str | None
    capability_id: str | None
    raw_url: str | None
    selector: str | None
    endpoint: str | None
    provider_ref: str | None
    timeout_seconds: float | None
    max_links: int | None
    max_text_chars: int | None
    max_chars: int | None
    session_id: str | None
    window_id: str | None
    tab_id: str | None
    started_at: str


class BrowserCommandError(RuntimeError):
    def __init__(
        self,
        *,
        category: str,
        error_code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    @property
    def exit_code(self) -> int:
        return COMMAND_EXIT_CODES.get(self.category, 1)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "category": self.category,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }
        payload.update(self.details)
        return payload


class DocumentSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._title_depth = 0
        self._current_link_href: str | None = None
        self._current_link_text: list[str] = []
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if tag == "title":
            self._title_depth += 1
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._current_link_href = href
                self._current_link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if tag == "title" and self._title_depth > 0:
            self._title_depth -= 1
            return
        if tag == "a" and self._current_link_href is not None:
            link_text = collapse_whitespace("".join(self._current_link_text))
            self.links.append(
                {
                    "href": self._current_link_href,
                    "text": link_text,
                }
            )
            self._current_link_href = None
            self._current_link_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        if self._title_depth > 0:
            self.title_parts.append(data)
        collapsed = collapse_whitespace(data)
        if collapsed:
            self.text_parts.append(collapsed)
        if self._current_link_href is not None:
            self._current_link_text.append(data)


class SelectorTextParser(HTMLParser):
    def __init__(self, selector: Selector) -> None:
        super().__init__(convert_charrefs=True)
        self.selector = selector
        self._ignored_depth = 0
        self._capture_depth = 0
        self.matches = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        if self._capture_depth > 0:
            self._capture_depth += 1
        elif selector_matches(self.selector, tag, attrs_map):
            self._capture_depth = 1
            self.matches += 1

        if tag in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._capture_depth > 0:
            self._capture_depth -= 1
        if tag in {"script", "style"} and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0 or self._capture_depth <= 0:
            return
        collapsed = collapse_whitespace(data)
        if collapsed:
            self.text_parts.append(collapsed)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collapse_whitespace(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()


def resolve_browser_session_store_path(*, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    raw = os.environ.get(DEFAULT_SESSION_STORE_ENV)
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "state" / "aios" / "compat-browser" / "session-store.json"


def load_browser_session_store(
    args: argparse.Namespace | None = None,
) -> tuple[Path, list[dict[str, object]]]:
    path = resolve_browser_session_store_path(
        explicit=getattr(args, "session_store", None) if args is not None else None,
    )
    if not path.exists():
        return path, []

    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("sessions", [])
    if not isinstance(entries, list):
        raise RuntimeError(f"browser session store sessions must be a list: {path}")
    sessions = [item for item in entries if isinstance(item, dict)]
    return path, sessions


def write_browser_session_store(path: Path, sessions: list[dict[str, object]]) -> None:
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "sessions": sessions,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def make_browser_state_id(prefix: str) -> str:
    return f"{prefix}-{time.time_ns()}"


def new_browser_tab_state() -> dict[str, object]:
    now = utc_now()
    return {
        "tab_id": make_browser_state_id("tab"),
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "url": None,
        "title": None,
        "history": [],
        "last_navigation_at": None,
        "last_extract_at": None,
        "last_selector": None,
        "text_preview": None,
        "text_length": None,
        "matched_count": None,
        "link_count": None,
        "links": [],
        "fetch": None,
        "body_text": None,
    }


def new_browser_window_state() -> dict[str, object]:
    now = utc_now()
    tab = new_browser_tab_state()
    return {
        "window_id": make_browser_state_id("window"),
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "active_tab_id": tab["tab_id"],
        "tabs": [tab],
    }


def new_browser_session_state() -> dict[str, object]:
    now = utc_now()
    window = new_browser_window_state()
    return {
        "session_id": make_browser_state_id("session"),
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "active_window_id": window["window_id"],
        "windows": [window],
    }


def sanitize_browser_tab_state(tab: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in tab.items() if key != "body_text"}


def sanitize_browser_window_state(window: dict[str, object]) -> dict[str, object]:
    sanitized = {key: value for key, value in window.items() if key != "tabs"}
    sanitized["tabs"] = [
        sanitize_browser_tab_state(tab)
        for tab in window.get("tabs", [])
        if isinstance(tab, dict)
    ]
    return sanitized


def sanitize_browser_session_state(session: dict[str, object]) -> dict[str, object]:
    sanitized = {key: value for key, value in session.items() if key != "windows"}
    sanitized["windows"] = [
        sanitize_browser_window_state(window)
        for window in session.get("windows", [])
        if isinstance(window, dict)
    ]
    return sanitized


def browser_session_store_payload(
    session_store: Path,
    sessions: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "session_store": str(session_store),
        "active_session_count": len(sessions),
        "sessions": [sanitize_browser_session_state(session) for session in sessions],
    }


def find_browser_session(
    sessions: list[dict[str, object]],
    session_id: str,
) -> tuple[int | None, dict[str, object] | None]:
    for index, session in enumerate(sessions):
        if str(session.get("session_id") or "") == session_id:
            return index, session
    return None, None


def ensure_browser_session_active(session: dict[str, object]) -> None:
    if str(session.get("status") or "active") != "active":
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_inactive",
            message=f"browser session is not active: {session.get('session_id')}",
            retryable=False,
        )


def resolve_browser_window(
    session: dict[str, object],
    window_id: str | None,
) -> dict[str, object]:
    windows = [item for item in session.get("windows", []) if isinstance(item, dict)]
    if not windows:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_empty",
            message=f"browser session has no windows: {session.get('session_id')}",
            retryable=False,
        )
    if window_id is not None:
        for window in windows:
            if str(window.get("window_id") or "") == window_id:
                return window
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_window_not_found",
            message=f"browser window not found: {window_id}",
            retryable=False,
            details={"session_id": session.get("session_id"), "window_id": window_id},
        )
    active_window_id = str(session.get("active_window_id") or "")
    for window in windows:
        if str(window.get("window_id") or "") == active_window_id:
            return window
    return windows[0]


def resolve_browser_tab(
    session: dict[str, object],
    window_id: str | None,
    tab_id: str | None,
) -> tuple[dict[str, object], dict[str, object]]:
    windows = [item for item in session.get("windows", []) if isinstance(item, dict)]
    if tab_id is not None and window_id is None:
        for window in windows:
            tabs = [item for item in window.get("tabs", []) if isinstance(item, dict)]
            for tab in tabs:
                if str(tab.get("tab_id") or "") == tab_id:
                    return window, tab
    window = resolve_browser_window(session, window_id)
    tabs = [item for item in window.get("tabs", []) if isinstance(item, dict)]
    if not tabs:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_window_empty",
            message=f"browser window has no tabs: {window.get('window_id')}",
            retryable=False,
            details={"session_id": session.get("session_id"), "window_id": window.get("window_id")},
        )
    if tab_id is not None:
        for tab in tabs:
            if str(tab.get("tab_id") or "") == tab_id:
                return window, tab
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_tab_not_found",
            message=f"browser tab not found: {tab_id}",
            retryable=False,
            details={
                "session_id": session.get("session_id"),
                "window_id": window.get("window_id"),
                "tab_id": tab_id,
            },
        )
    active_tab_id = str(window.get("active_tab_id") or "")
    for tab in tabs:
        if str(tab.get("tab_id") or "") == active_tab_id:
            return window, tab
    return window, tabs[0]


def touch_browser_session(
    session: dict[str, object],
    window: dict[str, object],
    tab: dict[str, object] | None = None,
) -> str:
    now = utc_now()
    session["updated_at"] = now
    session["active_window_id"] = window.get("window_id")
    window["updated_at"] = now
    if tab is not None:
        window["active_tab_id"] = tab.get("tab_id")
        tab["updated_at"] = now
    return now


def build_browser_session_binding(
    session_store: Path,
    session: dict[str, object],
    window: dict[str, object] | None = None,
    tab: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_store": str(session_store),
        "session": sanitize_browser_session_state(session),
    }
    if window is not None:
        payload["window"] = sanitize_browser_window_state(window)
    if tab is not None:
        payload["tab"] = sanitize_browser_tab_state(tab)
    return payload


def ensure_session_arguments_coherent(context: BrowserContext) -> None:
    if context.session_id is None and (context.window_id is not None or context.tab_id is not None):
        raise BrowserCommandError(
            category="invalid_request",
            error_code="browser_session_id_required",
            message="window_id or tab_id requires session_id",
            retryable=False,
        )
    if (context.endpoint or context.provider_ref) and context.session_id is not None:
        raise BrowserCommandError(
            category="invalid_request",
            error_code="browser_remote_session_unsupported",
            message="registered remote browser bridge does not yet support local session binding",
            retryable=False,
        )


def record_browser_navigation_session(
    args: argparse.Namespace,
    context: BrowserContext,
    fetch: dict[str, object],
    *,
    body_text: str,
    title: str,
    text_preview: str,
    text_length: int,
    links: list[dict[str, str]],
) -> dict[str, object] | None:
    if context.session_id is None:
        return None
    session_store, sessions = load_browser_session_store(args)
    _, session = find_browser_session(sessions, context.session_id)
    if session is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_not_found",
            message=f"browser session not found: {context.session_id}",
            retryable=False,
            details={"session_store": str(session_store), "session_id": context.session_id},
        )
    ensure_browser_session_active(session)
    window, tab = resolve_browser_tab(session, context.window_id, context.tab_id)
    now = touch_browser_session(session, window, tab)
    final_url = fetch.get("final_url") or fetch.get("resolved_url") or context.raw_url
    history = tab.get("history")
    if not isinstance(history, list):
        history = []
    if final_url and (not history or history[-1] != final_url):
        history.append(final_url)
    tab["history"] = history[-12:]
    tab["url"] = final_url
    tab["title"] = title or tab.get("title") or final_url
    tab["last_navigation_at"] = now
    tab["text_preview"] = text_preview
    tab["text_length"] = text_length
    tab["link_count"] = len(links)
    tab["links"] = links
    tab["fetch"] = fetch
    tab["body_text"] = body_text
    write_browser_session_store(session_store, sessions)
    return build_browser_session_binding(session_store, session, window, tab)


def record_browser_extract_session(
    args: argparse.Namespace,
    context: BrowserContext,
    fetch: dict[str, object],
    *,
    text: str,
    matched_count: int,
) -> dict[str, object] | None:
    if context.session_id is None:
        return None
    session_store, sessions = load_browser_session_store(args)
    _, session = find_browser_session(sessions, context.session_id)
    if session is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_not_found",
            message=f"browser session not found: {context.session_id}",
            retryable=False,
            details={"session_store": str(session_store), "session_id": context.session_id},
        )
    ensure_browser_session_active(session)
    window, tab = resolve_browser_tab(session, context.window_id, context.tab_id)
    now = touch_browser_session(session, window, tab)
    final_url = fetch.get("final_url") or fetch.get("resolved_url") or context.raw_url
    if final_url:
        tab["url"] = final_url
    tab["last_extract_at"] = now
    tab["last_selector"] = context.selector
    tab["matched_count"] = matched_count
    tab["text_preview"] = text[:TEXT_PREVIEW_CHARS]
    tab["text_length"] = len(text)
    tab["fetch"] = fetch
    write_browser_session_store(session_store, sessions)
    return build_browser_session_binding(session_store, session, window, tab)


def handle_list_sessions(args: argparse.Namespace) -> dict[str, object]:
    session_store, sessions = load_browser_session_store(args)
    payload = browser_session_store_payload(session_store, sessions)
    payload["provider_id"] = PROVIDER_ID
    return payload


def handle_open_session(args: argparse.Namespace) -> dict[str, object]:
    session_store, sessions = load_browser_session_store(args)
    session = new_browser_session_state()
    sessions.append(session)
    write_browser_session_store(session_store, sessions)
    window = next(item for item in session["windows"] if isinstance(item, dict))
    tab = next(item for item in window["tabs"] if isinstance(item, dict))
    payload = build_browser_session_binding(session_store, session, window, tab)
    payload.update(
        {
            "provider_id": PROVIDER_ID,
            "opened": True,
            "active_session_count": len(sessions),
        }
    )
    return payload


def handle_close_session(args: argparse.Namespace) -> dict[str, object]:
    session_store, sessions = load_browser_session_store(args)
    index, session = find_browser_session(sessions, args.session_id)
    if index is None or session is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_not_found",
            message=f"browser session not found: {args.session_id}",
            retryable=False,
            details={"session_store": str(session_store), "session_id": args.session_id},
        )
    removed = sessions.pop(index)
    write_browser_session_store(session_store, sessions)
    return {
        "provider_id": PROVIDER_ID,
        "session_store": str(session_store),
        "closed": True,
        "active_session_count": len(sessions),
        "session": sanitize_browser_session_state(removed),
    }


def handle_open_window(args: argparse.Namespace) -> dict[str, object]:
    session_store, sessions = load_browser_session_store(args)
    _, session = find_browser_session(sessions, args.session_id)
    if session is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_not_found",
            message=f"browser session not found: {args.session_id}",
            retryable=False,
            details={"session_store": str(session_store), "session_id": args.session_id},
        )
    ensure_browser_session_active(session)
    window = new_browser_window_state()
    session_windows = session.setdefault("windows", [])
    if not isinstance(session_windows, list):
        session_windows = []
        session["windows"] = session_windows
    session_windows.append(window)
    tab = next(item for item in window["tabs"] if isinstance(item, dict))
    touch_browser_session(session, window, tab)
    write_browser_session_store(session_store, sessions)
    payload = build_browser_session_binding(session_store, session, window, tab)
    payload.update({"provider_id": PROVIDER_ID, "opened": True})
    return payload


def handle_close_window(args: argparse.Namespace) -> dict[str, object]:
    session_store, sessions = load_browser_session_store(args)
    _, session = find_browser_session(sessions, args.session_id)
    if session is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_not_found",
            message=f"browser session not found: {args.session_id}",
            retryable=False,
            details={"session_store": str(session_store), "session_id": args.session_id},
        )
    ensure_browser_session_active(session)
    windows = [item for item in session.get("windows", []) if isinstance(item, dict)]
    if len(windows) <= 1:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_last_window_cannot_close",
            message="cannot close the last browser window in a session",
            retryable=False,
            details={"session_id": args.session_id, "window_id": args.window_id},
        )
    index = next(
        (idx for idx, window in enumerate(windows) if str(window.get("window_id") or "") == args.window_id),
        None,
    )
    if index is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_window_not_found",
            message=f"browser window not found: {args.window_id}",
            retryable=False,
            details={"session_id": args.session_id, "window_id": args.window_id},
        )
    removed = windows.pop(index)
    session["windows"] = windows
    next_window = windows[0]
    next_tab = [item for item in next_window.get("tabs", []) if isinstance(item, dict)][0]
    touch_browser_session(session, next_window, next_tab)
    write_browser_session_store(session_store, sessions)
    return {
        "provider_id": PROVIDER_ID,
        "session_store": str(session_store),
        "closed": True,
        "session": sanitize_browser_session_state(session),
        "window": sanitize_browser_window_state(removed),
    }


def handle_open_tab(args: argparse.Namespace) -> dict[str, object]:
    session_store, sessions = load_browser_session_store(args)
    _, session = find_browser_session(sessions, args.session_id)
    if session is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_not_found",
            message=f"browser session not found: {args.session_id}",
            retryable=False,
            details={"session_store": str(session_store), "session_id": args.session_id},
        )
    ensure_browser_session_active(session)
    window = resolve_browser_window(session, args.window_id)
    tabs = window.setdefault("tabs", [])
    if not isinstance(tabs, list):
        tabs = []
        window["tabs"] = tabs
    tab = new_browser_tab_state()
    tabs.append(tab)
    touch_browser_session(session, window, tab)
    write_browser_session_store(session_store, sessions)
    payload = build_browser_session_binding(session_store, session, window, tab)
    payload.update({"provider_id": PROVIDER_ID, "opened": True})
    return payload


def handle_close_tab(args: argparse.Namespace) -> dict[str, object]:
    session_store, sessions = load_browser_session_store(args)
    _, session = find_browser_session(sessions, args.session_id)
    if session is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_session_not_found",
            message=f"browser session not found: {args.session_id}",
            retryable=False,
            details={"session_store": str(session_store), "session_id": args.session_id},
        )
    ensure_browser_session_active(session)
    window, _ = resolve_browser_tab(session, None, args.tab_id)
    tabs = [item for item in window.get("tabs", []) if isinstance(item, dict)]
    if len(tabs) <= 1:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_last_tab_cannot_close",
            message="cannot close the last browser tab in a window",
            retryable=False,
            details={"session_id": args.session_id, "tab_id": args.tab_id},
        )
    index = next(
        (idx for idx, tab in enumerate(tabs) if str(tab.get("tab_id") or "") == args.tab_id),
        None,
    )
    if index is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_tab_not_found",
            message=f"browser tab not found: {args.tab_id}",
            retryable=False,
            details={"session_id": args.session_id, "tab_id": args.tab_id},
        )
    removed = tabs.pop(index)
    window["tabs"] = tabs
    next_tab = tabs[0]
    touch_browser_session(session, window, next_tab)
    write_browser_session_store(session_store, sessions)
    return {
        "provider_id": PROVIDER_ID,
        "session_store": str(session_store),
        "closed": True,
        "session": sanitize_browser_session_state(session),
        "window": sanitize_browser_window_state(window),
        "tab": sanitize_browser_tab_state(removed),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS browser compat provider baseline runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("manifest")
    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--audit-log", type=Path)
    health_parser.add_argument("--remote-registry", type=Path)
    add_policy_args(health_parser)
    subparsers.add_parser("permissions")

    list_parser = subparsers.add_parser("list-remotes")
    list_parser.add_argument("--remote-registry", type=Path)

    register_parser = subparsers.add_parser("register-remote")
    register_parser.add_argument("--provider-ref", required=True)
    register_parser.add_argument("--endpoint", required=True)
    register_parser.add_argument("--capability", action="append", dest="capabilities", required=True)
    register_parser.add_argument(
        "--auth-mode",
        default="none",
        choices=sorted(VALID_REMOTE_AUTH_MODES),
    )
    register_parser.add_argument("--auth-header-name")
    register_parser.add_argument("--auth-secret-env")
    register_parser.add_argument("--display-name")
    register_parser.add_argument(
        "--attestation-mode",
        choices=sorted(VALID_REMOTE_ATTESTATION_MODES),
    )
    register_parser.add_argument("--attestation-issuer")
    register_parser.add_argument("--attestation-subject")
    register_parser.add_argument("--attestation-issued-at")
    register_parser.add_argument("--attestation-expires-at")
    register_parser.add_argument("--attestation-evidence-ref")
    register_parser.add_argument("--attestation-digest")
    register_parser.add_argument("--attestation-status")
    register_parser.add_argument("--fleet-id")
    register_parser.add_argument("--governance-group")
    register_parser.add_argument("--policy-group")
    register_parser.add_argument("--registered-by")
    register_parser.add_argument("--approval-ref")
    register_parser.add_argument("--allow-lateral-movement", action="store_true")
    register_parser.add_argument("--heartbeat-ttl-seconds", type=int)
    register_parser.add_argument("--remote-registry", type=Path)

    heartbeat_parser = subparsers.add_parser("heartbeat-remote")
    heartbeat_parser.add_argument("--provider-ref", required=True)
    heartbeat_parser.add_argument("--heartbeat-at")
    heartbeat_parser.add_argument("--remote-registry", type=Path)

    revoke_parser = subparsers.add_parser("revoke-remote")
    revoke_parser.add_argument("--provider-ref", required=True)
    revoke_parser.add_argument("--reason")
    revoke_parser.add_argument("--revoked-at")
    revoke_parser.add_argument("--remote-registry", type=Path)

    unregister_parser = subparsers.add_parser("unregister-remote")
    unregister_parser.add_argument("--provider-ref", required=True)
    unregister_parser.add_argument("--remote-registry", type=Path)

    control_plane_parser = subparsers.add_parser("register-control-plane")
    control_plane_parser.add_argument("--provider-ref", required=True)
    control_plane_parser.add_argument("--remote-registry", type=Path)
    control_plane_parser.add_argument("--agentd-socket", type=Path)
    control_plane_parser.add_argument("--provider-id")
    control_plane_parser.add_argument("--display-name")

    list_sessions_parser = subparsers.add_parser("list-sessions")
    list_sessions_parser.add_argument("--session-store", type=Path)

    open_session_parser = subparsers.add_parser("open-session")
    open_session_parser.add_argument("--session-store", type=Path)

    close_session_parser = subparsers.add_parser("close-session")
    close_session_parser.add_argument("--session-id", required=True)
    close_session_parser.add_argument("--session-store", type=Path)

    open_window_parser = subparsers.add_parser("open-window")
    open_window_parser.add_argument("--session-id", required=True)
    open_window_parser.add_argument("--session-store", type=Path)

    close_window_parser = subparsers.add_parser("close-window")
    close_window_parser.add_argument("--session-id", required=True)
    close_window_parser.add_argument("--window-id", required=True)
    close_window_parser.add_argument("--session-store", type=Path)

    open_tab_parser = subparsers.add_parser("open-tab")
    open_tab_parser.add_argument("--session-id", required=True)
    open_tab_parser.add_argument("--window-id")
    open_tab_parser.add_argument("--session-store", type=Path)

    close_tab_parser = subparsers.add_parser("close-tab")
    close_tab_parser.add_argument("--session-id", required=True)
    close_tab_parser.add_argument("--tab-id", required=True)
    close_tab_parser.add_argument("--session-store", type=Path)

    navigate_parser = subparsers.add_parser("navigate")
    navigate_parser.add_argument("--url", required=True)
    navigate_parser.add_argument("--endpoint")
    navigate_parser.add_argument("--provider-ref")
    navigate_parser.add_argument("--session-id")
    navigate_parser.add_argument("--window-id")
    navigate_parser.add_argument("--tab-id")
    navigate_parser.add_argument("--session-store", type=Path)
    navigate_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    navigate_parser.add_argument("--max-links", type=int, default=8)
    navigate_parser.add_argument("--max-text-chars", type=int, default=TEXT_PREVIEW_CHARS)
    navigate_parser.add_argument("--audit-log", type=Path)
    navigate_parser.add_argument("--remote-registry", type=Path)
    add_policy_args(navigate_parser)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--url", required=True)
    extract_parser.add_argument("--selector")
    extract_parser.add_argument("--endpoint")
    extract_parser.add_argument("--provider-ref")
    extract_parser.add_argument("--session-id")
    extract_parser.add_argument("--window-id")
    extract_parser.add_argument("--tab-id")
    extract_parser.add_argument("--session-store", type=Path)
    extract_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    extract_parser.add_argument("--max-chars", type=int, default=4096)
    extract_parser.add_argument("--audit-log", type=Path)
    extract_parser.add_argument("--remote-registry", type=Path)
    add_policy_args(extract_parser)

    return parser.parse_args()


def context_from_args(args: argparse.Namespace) -> BrowserContext:
    started_at = utc_now()
    if args.command == "navigate":
        return BrowserContext(
            command="navigate",
            operation="compat.browser.navigate",
            capability_id="compat.browser.navigate",
            raw_url=args.url,
            selector=None,
            endpoint=args.endpoint,
            provider_ref=args.provider_ref,
            timeout_seconds=args.timeout_seconds,
            max_links=args.max_links,
            max_text_chars=args.max_text_chars,
            max_chars=None,
            session_id=args.session_id,
            window_id=args.window_id,
            tab_id=args.tab_id,
            started_at=started_at,
        )
    if args.command == "extract":
        return BrowserContext(
            command="extract",
            operation="compat.browser.extract",
            capability_id="compat.browser.extract",
            raw_url=args.url,
            selector=args.selector,
            endpoint=args.endpoint,
            provider_ref=args.provider_ref,
            timeout_seconds=args.timeout_seconds,
            max_links=None,
            max_text_chars=None,
            max_chars=args.max_chars,
            session_id=args.session_id,
            window_id=args.window_id,
            tab_id=args.tab_id,
            started_at=started_at,
        )
    return BrowserContext(
        command=args.command,
        operation=None,
        capability_id=None,
        raw_url=None,
        selector=None,
        endpoint=None,
        provider_ref=None,
        timeout_seconds=None,
        max_links=None,
        max_text_chars=None,
        max_chars=None,
        session_id=getattr(args, "session_id", None),
        window_id=getattr(args, "window_id", None),
        tab_id=getattr(args, "tab_id", None),
        started_at=started_at,
    )


def resolve_descriptor_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[1] / "providers" / DESCRIPTOR_FILENAME,
        current.parents[3] / "share" / "aios" / "providers" / DESCRIPTOR_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_audit_log(args: argparse.Namespace) -> Path | None:
    audit_log = getattr(args, "audit_log", None)
    if audit_log is not None:
        return audit_log
    raw = os.environ.get(DEFAULT_AUDIT_LOG_ENV)
    return Path(raw) if raw else None


def load_browser_remote_registry(
    args: argparse.Namespace | None = None,
) -> tuple[Path, list[RemoteRegistration]]:
    return load_remote_registry(
        explicit=getattr(args, "remote_registry", None) if args is not None else None,
        env_var=DEFAULT_REMOTE_REGISTRY_ENV,
        state_subdir="compat-browser",
    )


def load_compat_permission_manifest() -> dict[str, object]:
    descriptor_path = resolve_descriptor_path()
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    permission_manifest = descriptor.get("compat_permission_manifest")
    if not isinstance(permission_manifest, dict):
        raise RuntimeError(f"descriptor missing compat_permission_manifest: {descriptor_path}")

    capability_ids = [
        item.get("capability_id")
        for item in permission_manifest.get("capabilities", [])
        if isinstance(item, dict)
    ]
    if permission_manifest.get("schema_version") != "1.0.0":
        raise RuntimeError("unsupported compat permission manifest schema_version")
    if permission_manifest.get("provider_id") != PROVIDER_ID:
        raise RuntimeError("compat permission manifest provider_id mismatch")
    if permission_manifest.get("execution_location") != "sandbox":
        raise RuntimeError("compat permission manifest execution_location mismatch")
    if permission_manifest.get("required_permissions") != REQUIRED_PERMISSIONS:
        raise RuntimeError("compat permission manifest required_permissions mismatch")
    if capability_ids != DECLARED_CAPABILITIES:
        raise RuntimeError("compat permission manifest capability list mismatch")

    return permission_manifest


def compat_capability(capability_id: str | None) -> dict[str, object]:
    if capability_id is None:
        return {}
    for capability in load_compat_permission_manifest().get("capabilities", []):
        if isinstance(capability, dict) and capability.get("capability_id") == capability_id:
            return capability
    return {}


def browser_trust_policy() -> dict[str, object]:
    return resolve_trust_policy(
        mode_env=DEFAULT_TRUST_MODE_ENV,
        allowlist_env=DEFAULT_ALLOWLIST_ENV,
        default_mode="permissive",
    )


def browser_remote_attestation(args: argparse.Namespace) -> RemoteAttestation:
    mode = (
        args.attestation_mode
        or os.environ.get(DEFAULT_REMOTE_ATTESTATION_MODE_ENV)
        or "bootstrap"
    ).strip().lower()
    issuer = args.attestation_issuer or (
        f"{PROVIDER_ID}.attestor" if mode == "verified" else None
    )
    subject = args.attestation_subject or args.provider_ref
    evidence_ref = (
        args.attestation_evidence_ref
        or f"attestation://compat-browser/{args.provider_ref}"
    )
    digest = args.attestation_digest or f"sha256:{remote_target_hash(args.endpoint)}"
    status = args.attestation_status or ("trusted" if mode == "verified" else "bootstrap")
    return RemoteAttestation(
        mode=mode,
        issuer=issuer,
        subject=subject,
        issued_at=args.attestation_issued_at or utc_now(),
        expires_at=args.attestation_expires_at,
        evidence_ref=evidence_ref,
        digest=digest,
        status=status,
    )


def browser_remote_governance(args: argparse.Namespace) -> RemoteGovernance:
    return RemoteGovernance(
        fleet_id=(
            args.fleet_id
            or os.environ.get(DEFAULT_REMOTE_FLEET_ID_ENV)
            or "compat-browser-local"
        ),
        governance_group=(
            args.governance_group
            or os.environ.get(DEFAULT_REMOTE_GOVERNANCE_GROUP_ENV)
            or "operator-audit"
        ),
        policy_group=(
            args.policy_group
            or os.environ.get(DEFAULT_REMOTE_POLICY_GROUP_ENV)
            or "compat-browser-remote"
        ),
        registered_by=args.registered_by or PROVIDER_ID,
        approval_ref=args.approval_ref or os.environ.get(DEFAULT_REMOTE_APPROVAL_REF_ENV),
        allow_lateral_movement=bool(args.allow_lateral_movement),
    )


def remote_auth_description(
    registration: RemoteRegistration | None,
    registry_path: Path | None,
) -> dict[str, object]:
    if registration is None:
        return {
            "registered": False,
            "provider_ref": None,
            "auth_mode": None,
            "target_hash": None,
            "registry_path": str(registry_path) if registry_path is not None else None,
        }
    return {
        "registered": True,
        "provider_ref": registration.provider_ref,
        "display_name": registration.display_name,
        "auth_mode": registration.auth_mode,
        "auth_header_name": registration.auth_header_name,
        "auth_secret_env": registration.auth_secret_env,
        "target_hash": registration.target_hash,
        "capabilities": registration.capabilities,
        "endpoint": registration.endpoint,
        "registered_at": registration.registered_at,
        "control_plane_provider_id": registration.control_plane_provider_id,
        "registration_status": remote_registration_status(registration),
        "last_heartbeat_at": registration.last_heartbeat_at,
        "heartbeat_ttl_seconds": registration.heartbeat_ttl_seconds,
        "revoked_at": registration.revoked_at,
        "revocation_reason": registration.revocation_reason,
        "attestation": (
            registration.attestation.to_payload()
            if registration.attestation is not None
            else None
        ),
        "governance": (
            registration.governance.to_payload()
            if registration.governance is not None
            else None
        ),
        "registry_path": str(registry_path) if registry_path is not None else None,
    }


def ensure_remote_registration_usable(
    registration: RemoteRegistration,
    *,
    registry_path: Path,
) -> None:
    status = remote_registration_status(registration)
    if status == "active":
        return
    if status == "revoked":
        raise BrowserCommandError(
            category="permission_denied",
            error_code="browser_remote_provider_revoked",
            message=f"registered remote browser provider is revoked: {registration.provider_ref}",
            retryable=False,
            details={
                "provider_ref": registration.provider_ref,
                "registration_status": status,
                "revoked_at": registration.revoked_at,
                "revocation_reason": registration.revocation_reason,
                "remote_registry": str(registry_path),
            },
        )
    raise BrowserCommandError(
        category="precondition_failed",
        error_code="browser_remote_provider_stale",
        message=f"registered remote browser provider is not active: {registration.provider_ref}",
        retryable=False,
        details={
            "provider_ref": registration.provider_ref,
            "registration_status": status,
            "last_heartbeat_at": registration.last_heartbeat_at,
            "heartbeat_ttl_seconds": registration.heartbeat_ttl_seconds,
            "remote_registry": str(registry_path),
        },
    )


def resolve_remote_registration(
    context: BrowserContext,
    args: argparse.Namespace,
) -> tuple[Path, RemoteRegistration | None]:
    path, registrations = load_browser_remote_registry(args)
    match: RemoteRegistration | None = None

    if context.provider_ref:
        match = next(
            (registration for registration in registrations if registration.provider_ref == context.provider_ref),
            None,
        )
        if match is None:
            raise BrowserCommandError(
                category="precondition_failed",
                error_code="browser_remote_provider_not_registered",
                message=f"remote provider is not registered: {context.provider_ref}",
                retryable=False,
                details={"provider_ref": context.provider_ref, "remote_registry": str(path)},
            )
    elif context.endpoint:
        match = next(
            (registration for registration in registrations if registration.endpoint == context.endpoint),
            None,
        )

    if match is None:
        return path, None

    if context.endpoint and context.endpoint != match.endpoint:
        raise BrowserCommandError(
            category="invalid_request",
            error_code="browser_endpoint_registration_mismatch",
            message="endpoint does not match the registered remote browser provider endpoint",
            retryable=False,
            details={
                "provider_ref": match.provider_ref,
                "registered_endpoint": match.endpoint,
                "requested_endpoint": context.endpoint,
                "remote_registry": str(path),
            },
        )

    if context.capability_id and context.capability_id not in match.capabilities:
        raise BrowserCommandError(
            category="permission_denied",
            error_code="browser_capability_not_registered",
            message=f"registered remote browser provider does not allow {context.capability_id}",
            retryable=False,
            details={
                "provider_ref": match.provider_ref,
                "registered_capabilities": match.capabilities,
                "remote_registry": str(path),
            },
        )

    ensure_remote_registration_usable(match, registry_path=path)
    return path, match


def resolve_effective_endpoint(
    context: BrowserContext,
    registration: RemoteRegistration | None,
) -> str | None:
    return context.endpoint or (registration.endpoint if registration is not None else None)


def build_remote_auth_headers(
    *,
    context: BrowserContext,
    registration: RemoteRegistration | None,
    policy_context: CompatPolicyContext,
) -> dict[str, str]:
    if registration is None:
        return {}

    headers = {
        "X-AIOS-Remote-Provider": registration.provider_ref,
        "X-AIOS-Target-Hash": registration.target_hash,
    }
    auth_mode = registration.auth_mode
    header_name = registration.auth_header_name

    if auth_mode == "none":
        return headers

    if auth_mode in {"bearer", "header"}:
        secret_env = registration.auth_secret_env or DEFAULT_REMOTE_AUTH_SECRET_ENV
        secret = os.environ.get(secret_env)
        if not secret:
            raise BrowserCommandError(
                category="precondition_failed",
                error_code="browser_remote_secret_missing",
                message=f"remote auth secret env is not set: {secret_env}",
                retryable=False,
                details={"provider_ref": registration.provider_ref, "auth_secret_env": secret_env},
            )
        effective_header = header_name or ("Authorization" if auth_mode == "bearer" else "X-AIOS-Browser-Secret")
        headers[effective_header] = f"Bearer {secret}" if auth_mode == "bearer" else secret
        return headers

    if auth_mode == "execution-token":
        if not isinstance(policy_context.execution_token, dict):
            raise BrowserCommandError(
                category="precondition_failed",
                error_code="browser_execution_token_missing",
                message="registered remote browser provider requires execution_token auth",
                retryable=False,
                details={"provider_ref": registration.provider_ref},
            )
        token_context = policy_context.token_context or {}
        if token_context.get("capability_id") != context.capability_id:
            raise BrowserCommandError(
                category="permission_denied",
                error_code="browser_execution_token_capability_mismatch",
                message="execution token capability does not match browser operation",
                retryable=False,
                details={
                    "provider_ref": registration.provider_ref,
                    "expected_capability_id": context.capability_id,
                    "token_capability_id": token_context.get("capability_id"),
                },
            )
        if token_context.get("execution_location") != "sandbox":
            raise BrowserCommandError(
                category="permission_denied",
                error_code="browser_execution_token_location_mismatch",
                message="execution token execution_location must be sandbox for compat browser bridge",
                retryable=False,
                details={"provider_ref": registration.provider_ref},
            )
        if token_context.get("target_hash") != registration.target_hash:
            raise BrowserCommandError(
                category="permission_denied",
                error_code="browser_execution_token_target_mismatch",
                message="execution token target_hash does not match registered remote browser target",
                retryable=False,
                details={
                    "provider_ref": registration.provider_ref,
                    "expected_target_hash": registration.target_hash,
                    "token_target_hash": token_context.get("target_hash"),
                },
            )
        effective_header = header_name or "X-AIOS-Execution-Token"
        headers[effective_header] = encode_execution_token(policy_context.execution_token)
        signature = policy_context.execution_token.get("signature")
        if isinstance(signature, str) and signature:
            headers["X-AIOS-Execution-Token-Signature"] = signature
        return headers

    raise BrowserCommandError(
        category="precondition_failed",
        error_code="browser_remote_auth_mode_invalid",
        message=f"unsupported remote auth mode: {auth_mode}",
        retryable=False,
        details={"provider_ref": registration.provider_ref, "auth_mode": auth_mode},
    )


def build_manifest() -> dict[str, object]:
    trust_policy = browser_trust_policy()
    registry_path, registrations = load_browser_remote_registry()
    session_store_path, sessions = load_browser_session_store()
    summary = remote_registration_summary(registrations)
    return {
        "provider_id": PROVIDER_ID,
        "execution_location": "sandbox",
        "status": "baseline",
        "worker_contract": WORKER_CONTRACT,
        "declared_capabilities": DECLARED_CAPABILITIES,
        "required_permissions": REQUIRED_PERMISSIONS,
        "implemented_methods": [
            "navigate-fetch",
            "extract-selector-text",
            "permission-manifest",
            "browser-result-protocol-v1",
            "audit-jsonl",
            "remote-register",
            "remote-list",
            "remote-heartbeat",
            "remote-revoke",
            "remote-unregister",
            "remote-control-plane-register",
            "remote-browser-bridge",
            "session-list",
            "session-open",
            "session-close",
            "window-open",
            "window-close",
            "tab-open",
            "tab-close",
        ],
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "trust_policy": trust_policy,
        "remote_registry": {
            "path": str(registry_path),
            "registered_remote_count": len(registrations),
            "registered_providers": [registration.provider_ref for registration in registrations],
            "auth_modes": sorted({registration.auth_mode for registration in registrations}),
            "status_counts": summary["counts"],
            "control_plane_provider_ids": sorted(
                {
                    registration.control_plane_provider_id
                    for registration in registrations
                    if registration.control_plane_provider_id
                }
            ),
        },
        "session_store": {
            "path": str(session_store_path),
            "active_session_count": len(sessions),
            "session_ids": [str(session.get("session_id")) for session in sessions],
        },
        "notes": [
            "Baseline HTML/text fetch runtime is available",
            "Structured compat-browser-fetch-v1 payloads are emitted for success, not-found, and error paths",
            "Optional JSONL audit sink can be configured for machine-readable evidence",
            "Registered remote browser workers can be bridged over HTTP with auth and trust policy",
            "Local browser session/window/tab lifecycle is persisted through a session store",
        ],
    }


def enforce_timeout_budget(timeout_seconds: float) -> None:
    resource_budget = load_compat_permission_manifest().get("resource_budget", {})
    if not isinstance(resource_budget, dict):
        return
    max_timeout_seconds = resource_budget.get("max_timeout_seconds")
    if isinstance(max_timeout_seconds, (int, float)) and timeout_seconds > float(max_timeout_seconds):
        raise BrowserCommandError(
            category="invalid_request",
            error_code="browser_timeout_exceeds_budget",
            message=(
                "requested timeout exceeds compat permission manifest budget: "
                f"{timeout_seconds}s > {max_timeout_seconds}s"
            ),
            retryable=False,
            details={"budget_max_timeout_seconds": float(max_timeout_seconds)},
        )


def resolve_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme:
        return raw_url

    candidate = Path(raw_url).expanduser()
    if candidate.exists():
        return candidate.resolve().as_uri()

    return f"https://{raw_url}"


def decode_bytes(body: bytes, charset: str | None) -> str:
    encodings: list[str] = []
    if charset:
        encodings.append(charset)
    encodings.extend(["utf-8", "utf-16", "latin-1"])
    for encoding in encodings:
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def fetch_info(
    *,
    requested_url: str | None,
    resolved_url: str | None = None,
    final_url: str | None = None,
    status_code: int | None = None,
    content_type: str | None = None,
    charset: str | None = None,
    truncated: bool = False,
    fetched_at: str | None = None,
) -> dict[str, object]:
    return {
        "requested_url": requested_url,
        "resolved_url": resolved_url,
        "final_url": final_url,
        "status_code": status_code,
        "content_type": content_type,
        "charset": charset,
        "truncated": truncated,
        "fetched_at": fetched_at,
    }


def fetch_info_from_result(result: FetchResult) -> dict[str, object]:
    return fetch_info(
        requested_url=result.requested_url,
        resolved_url=result.resolved_url,
        final_url=result.final_url,
        status_code=result.status_code,
        content_type=result.content_type,
        charset=result.charset,
        truncated=result.truncated,
        fetched_at=result.fetched_at,
    )


def fetch_url(raw_url: str, timeout_seconds: float) -> FetchResult:
    resolved_url = resolve_url(raw_url)
    parsed = urlparse(resolved_url)
    if parsed.scheme not in {"file", "http", "https"}:
        raise BrowserCommandError(
            category="invalid_request",
            error_code="browser_unsupported_url_scheme",
            message=f"unsupported URL scheme: {parsed.scheme or '<none>'}",
            retryable=False,
            details={"fetch": fetch_info(requested_url=raw_url, resolved_url=resolved_url)},
        )

    request = Request(
        resolved_url,
        headers={
            "User-Agent": "AIOSBrowserCompat/0.2",
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            truncated = len(body) > MAX_RESPONSE_BYTES
            if truncated:
                body = body[:MAX_RESPONSE_BYTES]
            final_url = response.geturl()
            headers = response.headers
            content_type = headers.get_content_type() if hasattr(headers, "get_content_type") else "application/octet-stream"
            charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
            status_code = getattr(response, "status", None) or 200
    except HTTPError as exc:
        raise BrowserCommandError(
            category="remote_error",
            error_code="browser_http_error",
            message=f"browser fetch target returned HTTP {exc.code}",
            retryable=exc.code >= 500,
            details={
                "fetch": fetch_info(
                    requested_url=raw_url,
                    resolved_url=resolved_url,
                    final_url=getattr(exc, "url", resolved_url),
                    status_code=exc.code,
                    content_type=exc.headers.get("Content-Type", "") if exc.headers else None,
                    fetched_at=utc_now(),
                )
            },
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise BrowserCommandError(
            category="timeout",
            error_code="browser_fetch_timeout",
            message=f"browser fetch timed out after {timeout_seconds}s",
            retryable=True,
            details={
                "fetch": fetch_info(
                    requested_url=raw_url,
                    resolved_url=resolved_url,
                    final_url=resolved_url,
                    fetched_at=utc_now(),
                )
            },
        ) from exc
    except URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            raise BrowserCommandError(
                category="timeout",
                error_code="browser_fetch_timeout",
                message=f"browser fetch timed out after {timeout_seconds}s",
                retryable=True,
                details={
                    "fetch": fetch_info(
                        requested_url=raw_url,
                        resolved_url=resolved_url,
                        final_url=resolved_url,
                        fetched_at=utc_now(),
                    )
                },
            ) from exc
        if isinstance(exc.reason, FileNotFoundError):
            raise BrowserCommandError(
                category="precondition_failed",
                error_code="browser_source_missing",
                message=f"missing browser source: {raw_url}",
                retryable=False,
                details={
                    "fetch": fetch_info(
                        requested_url=raw_url,
                        resolved_url=resolved_url,
                        final_url=resolved_url,
                        fetched_at=utc_now(),
                    )
                },
            ) from exc
        raise BrowserCommandError(
            category="unavailable",
            error_code="browser_fetch_unavailable",
            message=f"browser fetch target unavailable: {exc.reason}",
            retryable=True,
            details={
                "fetch": fetch_info(
                    requested_url=raw_url,
                    resolved_url=resolved_url,
                    final_url=resolved_url,
                    fetched_at=utc_now(),
                )
            },
        ) from exc

    if content_type == "application/octet-stream":
        guessed_type, _ = mimetypes.guess_type(urlparse(final_url).path)
        if guessed_type:
            content_type = guessed_type

    return FetchResult(
        requested_url=raw_url,
        resolved_url=resolved_url,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        charset=charset,
        body_text=decode_bytes(body, charset),
        truncated=truncated,
        fetched_at=utc_now(),
    )


def parse_selector(raw_selector: str | None) -> Selector | None:
    if raw_selector is None:
        return None
    selector = raw_selector.strip()
    if not selector:
        return None
    if selector.startswith("#"):
        return Selector(kind="id", value=selector[1:])
    if selector.startswith("."):
        return Selector(kind="class", value=selector[1:])
    return Selector(kind="tag", value=selector.lower())


def selector_matches(selector: Selector, tag: str, attrs: dict[str, str]) -> bool:
    if selector.kind == "tag":
        return tag == selector.value
    if selector.kind == "id":
        return attrs.get("id") == selector.value
    if selector.kind == "class":
        class_names = attrs.get("class", "").split()
        return selector.value in class_names
    return False


def is_html_document(result: FetchResult) -> bool:
    content_type = result.content_type.lower()
    return "html" in content_type or result.final_url.endswith((".html", ".htm"))


def summarize_document(body_text: str) -> dict[str, object]:
    parser = DocumentSummaryParser()
    parser.feed(body_text)
    parser.close()
    title = collapse_whitespace("".join(parser.title_parts))
    text_content = collapse_whitespace(" ".join(parser.text_parts))
    return {
        "title": title,
        "text_content": text_content,
        "links": parser.links,
    }


def build_document_info(
    *,
    title: str | None = None,
    text_length: int | None = None,
    link_count: int | None = None,
    matched_count: int | None = None,
    text_preview: str | None = None,
    text: str | None = None,
    links: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "text_length": text_length,
        "link_count": link_count,
        "matched_count": matched_count,
        "text_preview": text_preview,
        "text": text,
        "links": links,
    }


def build_result_protocol(
    *,
    status: str,
    context: BrowserContext,
    fetch: dict[str, object] | None,
    document: dict[str, object] | None,
    remote_bridge: dict[str, object] | None,
    finished_at: str,
    error: dict[str, object] | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    permission_manifest = load_compat_permission_manifest()
    capability = compat_capability(context.capability_id)
    return {
        "protocol_version": "1.0.0",
        "worker_contract": WORKER_CONTRACT,
        "provider_id": PROVIDER_ID,
        "status": status,
        "operation": context.operation,
        "execution_location": "sandbox",
        "request": {
            "capability_id": context.capability_id,
            "url": context.raw_url,
            "selector": context.selector,
            "endpoint": context.endpoint,
            "provider_ref": context.provider_ref,
            "timeout_seconds": context.timeout_seconds,
            "max_links": context.max_links,
            "max_text_chars": context.max_text_chars,
            "max_chars": context.max_chars,
            "session_id": context.session_id,
            "window_id": context.window_id,
            "tab_id": context.tab_id,
        },
        "fetch": fetch or fetch_info(requested_url=context.raw_url),
        "document": document or build_document_info(),
        "remote_bridge": remote_bridge,
        "policy": {
            "compat_permission_manifest": permission_manifest,
            "network_access": capability.get("network_access"),
            "filesystem_access": capability.get("filesystem_access"),
            **policy_context.describe(),
        },
        "audit": {
            "audit_id": None,
            "audit_log": None,
            "capability_id": context.capability_id,
            "audit_tags": capability.get("audit_tags", permission_manifest.get("audit_tags", [])),
            "taint_behavior": permission_manifest.get("taint_behavior"),
            "shared_audit_log": (
                str(policy_context.shared_audit_log)
                if policy_context.shared_audit_log is not None
                else None
            ),
            "execution_token": policy_context.token_context,
            "token_verification": policy_context.verification,
        },
        "timestamps": {
            "started_at": context.started_at,
            "finished_at": finished_at,
        },
        "error": error,
    }


def build_success_payload(
    *,
    status: str,
    context: BrowserContext,
    fetch: dict[str, object],
    document: dict[str, object],
    remote_bridge: dict[str, object] | None,
    extra_payload: dict[str, object],
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    finished_at = utc_now()
    result_protocol = build_result_protocol(
        status=status,
        context=context,
        fetch=fetch,
        document=document,
        remote_bridge=remote_bridge,
        finished_at=finished_at,
        error=None,
        policy_context=policy_context,
    )
    payload = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": status,
        "operation": context.operation,
        "capability_id": context.capability_id,
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "result_protocol": result_protocol,
    }
    payload.update(extra_payload)
    payload["audit_id"] = append_audit_log(audit_log, payload, context, policy_context)
    payload["audit_log"] = str(audit_log) if audit_log is not None else None
    (payload.get("result_protocol") or {}).get("audit", {})["audit_id"] = payload["audit_id"]
    (payload.get("result_protocol") or {}).get("audit", {})["audit_log"] = payload["audit_log"]
    return payload


def build_error_payload(
    *,
    context: BrowserContext,
    error: BrowserCommandError,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    finished_at = utc_now()
    fetch_payload = error.details.get("fetch")
    fetch = fetch_payload if isinstance(fetch_payload, dict) else None
    result_protocol = build_result_protocol(
        status="error",
        context=context,
        fetch=fetch,
        document=None,
        remote_bridge=(
            error.details.get("remote_bridge")
            if isinstance(error.details.get("remote_bridge"), dict)
            else None
        ),
        finished_at=finished_at,
        error=error.to_payload(),
        policy_context=policy_context,
    )
    payload = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "status": "error",
        "command": context.command,
        "operation": context.operation,
        "capability_id": context.capability_id,
        "message": error.message,
        "error": error.to_payload(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "result_protocol": result_protocol,
        "finished_at": finished_at,
    }
    if isinstance(error.details.get("remote_bridge"), dict):
        payload["remote_bridge"] = error.details["remote_bridge"]
    payload["audit_id"] = append_audit_log(audit_log, payload, context, policy_context)
    payload["audit_log"] = str(audit_log) if audit_log is not None else None
    (payload.get("result_protocol") or {}).get("audit", {})["audit_id"] = payload["audit_id"]
    (payload.get("result_protocol") or {}).get("audit", {})["audit_log"] = payload["audit_log"]
    return payload


def append_audit_log(
    audit_log: Path | None,
    payload: dict[str, object],
    context: BrowserContext,
    policy_context: CompatPolicyContext,
) -> str | None:
    if audit_log is None and policy_context.shared_audit_log is None:
        return None
    if audit_log is not None and audit_log.parent:
        audit_log.parent.mkdir(parents=True, exist_ok=True)
    audit_id = f"browser-compat-{time.time_ns()}"
    status = str(payload.get("status", "error"))
    permission_manifest = load_compat_permission_manifest()
    capability = compat_capability(context.capability_id)
    error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    remote_bridge = (
        payload.get("remote_bridge")
        if isinstance(payload.get("remote_bridge"), dict)
        else {}
    )
    if error_payload.get("category") in {"invalid_request", "precondition_failed", "permission_denied"}:
        decision = "denied"
    else:
        decision = "allowed"
    timestamp = utc_now()
    token_context = policy_context.token_context or {}
    artifact_path = str(audit_log or policy_context.shared_audit_log)
    entry = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audit_id": audit_id,
        "timestamp": timestamp,
        "generated_at": timestamp,
        "user_id": token_context.get("user_id")
        or os.environ.get("AIOS_COMPAT_BROWSER_AUDIT_USER_ID", DEFAULT_USER_ID),
        "session_id": token_context.get("session_id")
        or os.environ.get("AIOS_COMPAT_BROWSER_AUDIT_SESSION_ID", DEFAULT_SESSION_ID),
        "task_id": token_context.get("task_id")
        or os.environ.get("AIOS_COMPAT_BROWSER_AUDIT_TASK_ID", DEFAULT_TASK_ID),
        "provider_id": PROVIDER_ID,
        "capability_id": context.capability_id,
        "approval_id": token_context.get("approval_ref"),
        "decision": decision,
        "execution_location": "sandbox",
        "route_state": (
            "compat-browser-centralized-policy"
            if policy_context.mode == "policyd-verified"
            else "compat-browser-baseline"
        ),
        "taint_summary": token_context.get("taint_summary")
        or permission_manifest.get("taint_behavior"),
        "artifact_path": artifact_path,
        "status": status,
        "operation": context.operation,
        "audit_tags": capability.get("audit_tags", permission_manifest.get("audit_tags", [])),
        "result": {
            "status": status,
            "operation": context.operation,
            "url": context.raw_url,
            "selector": context.selector,
            "status_code": payload.get("status_code"),
            "content_type": payload.get("content_type"),
            "title": payload.get("title"),
            "matched_count": payload.get("matched_count"),
            "link_count": payload.get("link_count"),
            "error_code": error_payload.get("error_code"),
            "remote_provider_ref": remote_bridge.get("provider_ref"),
            "remote_auth_mode": remote_bridge.get("auth_mode"),
            "remote_endpoint": remote_bridge.get("endpoint"),
            "remote_target_hash": remote_bridge.get("target_hash"),
            "policy_mode": policy_context.mode,
            "token_verified": policy_context.token_verified,
            "session_id": token_context.get("session_id"),
            "task_id": token_context.get("task_id"),
            "approval_ref": token_context.get("approval_ref"),
            "browser_session_id": context.session_id,
            "browser_window_id": context.window_id,
            "browser_tab_id": context.tab_id,
        },
        "execution_token": token_context or None,
        "token_verification": policy_context.verification,
        "notes": [
            f"worker_contract={WORKER_CONTRACT}",
            f"result_protocol_schema_ref={RESULT_PROTOCOL_SCHEMA_REF}",
            f"policy_mode={policy_context.mode}",
        ],
    }
    append_jsonl(audit_log, entry)
    append_jsonl(policy_context.shared_audit_log, entry)
    return audit_id


def handle_health(audit_log: Path | None, policy_context: CompatPolicyContext) -> dict[str, object]:
    permission_manifest = load_compat_permission_manifest()
    trust_policy = browser_trust_policy()
    registry_path, registrations = load_browser_remote_registry()
    session_store_path, sessions = load_browser_session_store()
    fleet_ids = sorted(
        {
            registration.governance.fleet_id
            for registration in registrations
            if registration.governance is not None
        }
    )
    governance_groups = sorted(
        {
            registration.governance.governance_group
            for registration in registrations
            if registration.governance is not None
        }
    )
    attestation_modes = sorted(
        {
            registration.attestation.mode
            for registration in registrations
            if registration.attestation is not None
        }
    )
    summary = remote_registration_summary(registrations)
    return {
        "status": "available",
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "execution_location": "sandbox",
        "declared_capabilities": DECLARED_CAPABILITIES,
        "required_permissions": REQUIRED_PERMISSIONS,
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": permission_manifest,
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "engine": "html-fetch+session-store+remote-browser-bridge",
        "audit_log_configured": audit_log is not None,
        "audit_log_path": str(audit_log) if audit_log is not None else None,
        "shared_audit_log_configured": policy_context.shared_audit_log is not None,
        "shared_audit_log_path": (
            str(policy_context.shared_audit_log)
            if policy_context.shared_audit_log is not None
            else None
        ),
        "policyd_socket": (
            str(policy_context.policyd_socket)
            if policy_context.policyd_socket is not None
            else None
        ),
        "policy_mode": policy_context.mode,
        "trust_policy": trust_policy,
        "registered_remote_count": len(registrations),
        "remote_registry_path": str(registry_path),
        "remote_auth_modes": sorted({registration.auth_mode for registration in registrations}),
        "remote_attestation_modes": attestation_modes,
        "remote_fleet_ids": fleet_ids,
        "remote_governance_groups": governance_groups,
        "remote_status_counts": summary["counts"],
        "remote_stale_provider_refs": summary["stale_provider_refs"],
        "remote_revoked_provider_refs": summary["revoked_provider_refs"],
        "session_store_path": str(session_store_path),
        "active_session_count": len(sessions),
        "active_session_ids": [str(session.get("session_id")) for session in sessions],
        "notes": [
            "Supports file://, http://, and https:// targets",
            "Structured compat-browser-fetch-v1 payloads are enabled",
            "Centralized policy/token verification is enabled when policyd_socket + execution_token are supplied",
            "Registered remote browser workers can execute navigate/extract over authenticated HTTP bridge",
            "Remote registrations carry attestation and fleet governance metadata for control-plane promotion",
            "Local browser session/window/tab state is persisted in the session store",
        ],
    }


def handle_list_remotes(args: argparse.Namespace) -> dict[str, object]:
    registry_path, registrations = load_browser_remote_registry(args)
    summary = remote_registration_summary(registrations)
    return {
        "provider_id": PROVIDER_ID,
        "remote_registry": str(registry_path),
        "registered_remote_count": len(registrations),
        "remote_status_counts": summary["counts"],
        "registered_remotes": [registration.to_payload() for registration in registrations],
    }


def handle_register_remote(args: argparse.Namespace) -> dict[str, object]:
    invalid = [capability for capability in args.capabilities if capability not in DECLARED_CAPABILITIES]
    if invalid:
        raise BrowserCommandError(
            category="invalid_request",
            error_code="browser_remote_capability_invalid",
            message=f"unsupported browser remote capability: {invalid[0]}",
            retryable=False,
            details={"declared_capabilities": DECLARED_CAPABILITIES},
        )
    registration = RemoteRegistration(
        provider_ref=args.provider_ref,
        endpoint=args.endpoint,
        capabilities=sorted(set(args.capabilities)),
        auth_mode=args.auth_mode,
        auth_header_name=args.auth_header_name,
        auth_secret_env=args.auth_secret_env,
        target_hash=remote_target_hash(args.endpoint),
        registered_at=utc_now(),
        display_name=args.display_name,
        registration_status="active",
        last_heartbeat_at=utc_now(),
        heartbeat_ttl_seconds=args.heartbeat_ttl_seconds,
        attestation=browser_remote_attestation(args),
        governance=browser_remote_governance(args),
    )
    registry_path, registrations = load_browser_remote_registry(args)
    updated = upsert_remote_registration(registrations, registration)
    write_remote_registry(registry_path, updated)
    return {
        "provider_id": PROVIDER_ID,
        "remote_registry": str(registry_path),
        "registration": registration.to_payload(),
        "registered_remote_count": len(updated),
    }


def handle_heartbeat_remote(args: argparse.Namespace) -> dict[str, object]:
    registry_path, registrations = load_browser_remote_registry(args)
    index, registration = find_remote_registration(registrations, provider_ref=args.provider_ref)
    if index is None or registration is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_remote_provider_not_registered",
            message=f"remote provider is not registered: {args.provider_ref}",
            retryable=False,
            details={"remote_registry": str(registry_path)},
        )
    updated_registration = touch_remote_registration(registration, timestamp=args.heartbeat_at)
    updated = list(registrations)
    updated[index] = updated_registration
    write_remote_registry(registry_path, updated)
    return {
        "provider_id": PROVIDER_ID,
        "remote_registry": str(registry_path),
        "registration": updated_registration.to_payload(),
        "registered_remote_count": len(updated),
    }


def handle_revoke_remote(args: argparse.Namespace) -> dict[str, object]:
    registry_path, registrations = load_browser_remote_registry(args)
    index, registration = find_remote_registration(registrations, provider_ref=args.provider_ref)
    if index is None or registration is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_remote_provider_not_registered",
            message=f"remote provider is not registered: {args.provider_ref}",
            retryable=False,
            details={"remote_registry": str(registry_path)},
        )
    updated_registration = revoke_remote_registration(
        registration,
        reason=args.reason,
        timestamp=args.revoked_at,
    )
    updated = list(registrations)
    updated[index] = updated_registration
    write_remote_registry(registry_path, updated)
    return {
        "provider_id": PROVIDER_ID,
        "remote_registry": str(registry_path),
        "registration": updated_registration.to_payload(),
        "registered_remote_count": len(updated),
    }


def handle_unregister_remote(args: argparse.Namespace) -> dict[str, object]:
    registry_path, registrations = load_browser_remote_registry(args)
    updated, removed = remove_remote_registration(registrations, provider_ref=args.provider_ref)
    if removed is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_remote_provider_not_registered",
            message=f"remote provider is not registered: {args.provider_ref}",
            retryable=False,
            details={"remote_registry": str(registry_path)},
        )
    write_remote_registry(registry_path, updated)
    return {
        "provider_id": PROVIDER_ID,
        "remote_registry": str(registry_path),
        "unregistered": True,
        "registration": removed.to_payload(),
        "registered_remote_count": len(updated),
    }


def build_control_plane_descriptor(
    registration: RemoteRegistration,
    *,
    provider_id: str,
    display_name: str | None,
) -> dict[str, object]:
    descriptor = json.loads(resolve_descriptor_path().read_text(encoding="utf-8"))
    descriptor["provider_id"] = provider_id
    descriptor["display_name"] = display_name or registration.display_name or registration.provider_ref
    descriptor["execution_location"] = "attested_remote"
    descriptor["trust_policy_modes"] = sorted({"registered-remote", registration.auth_mode})
    descriptor["degradation_policy"] = "fallback-to-local-browser-compat"
    descriptor["audit_tags"] = sorted({*descriptor.get("audit_tags", []), "remote"})
    descriptor["supported_targets"] = sorted({*descriptor.get("supported_targets", []), "registered-remote"})
    descriptor["capabilities"] = [
        capability
        for capability in descriptor.get("capabilities", [])
        if isinstance(capability, dict)
        and capability.get("capability_id") in registration.capabilities
    ]
    compat_manifest = descriptor.get("compat_permission_manifest") or {}
    if isinstance(compat_manifest, dict):
        compat_manifest["provider_id"] = provider_id
        compat_manifest["execution_location"] = "attested_remote"
        compat_manifest["capabilities"] = [
            capability
            for capability in compat_manifest.get("capabilities", [])
            if isinstance(capability, dict)
            and capability.get("capability_id") in registration.capabilities
        ]
        descriptor["compat_permission_manifest"] = compat_manifest
    descriptor["remote_registration"] = {
        "source_provider_id": PROVIDER_ID,
        "provider_ref": registration.provider_ref,
        "endpoint": registration.endpoint,
        "auth_mode": registration.auth_mode,
        "auth_header_name": registration.auth_header_name,
        "auth_secret_env": registration.auth_secret_env,
        "target_hash": registration.target_hash,
        "capabilities": registration.capabilities,
        "registered_at": registration.registered_at,
        "display_name": registration.display_name,
        "control_plane_provider_id": provider_id,
        "registration_status": remote_registration_status(registration),
        "last_heartbeat_at": registration.last_heartbeat_at,
        "heartbeat_ttl_seconds": registration.heartbeat_ttl_seconds,
        "revoked_at": registration.revoked_at,
        "revocation_reason": registration.revocation_reason,
        "attestation": (
            registration.attestation.to_payload()
            if registration.attestation is not None
            else None
        ),
        "governance": (
            registration.governance.to_payload()
            if registration.governance is not None
            else None
        ),
    }
    return descriptor


def handle_register_control_plane(args: argparse.Namespace) -> dict[str, object]:
    registry_path, registrations = load_browser_remote_registry(args)
    registration = next(
        (item for item in registrations if item.provider_ref == args.provider_ref),
        None,
    )
    if registration is None:
        raise BrowserCommandError(
            category="precondition_failed",
            error_code="browser_remote_provider_not_registered",
            message=f"remote provider is not registered: {args.provider_ref}",
            retryable=False,
            details={"remote_registry": str(registry_path)},
        )
    ensure_remote_registration_usable(registration, registry_path=registry_path)
    provider_id = args.provider_id or normalize_remote_provider_id(
        "compat.browser.remote",
        registration.provider_ref,
    )
    descriptor = build_control_plane_descriptor(
        registration,
        provider_id=provider_id,
        display_name=args.display_name,
    )
    try:
        record = agentd_rpc(
            agentd_socket_path(args.agentd_socket),
            PROVIDER_REGISTER_METHOD,
            {"descriptor": descriptor},
            error_prefix="browser",
        )
    except RemoteSupportError as exc:
        raise BrowserCommandError(
            category=exc.category,
            error_code=exc.error_code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details or {},
        ) from exc
    updated_registrations = [
        RemoteRegistration(
            provider_ref=item.provider_ref,
            endpoint=item.endpoint,
            capabilities=item.capabilities,
            auth_mode=item.auth_mode,
            auth_header_name=item.auth_header_name,
            auth_secret_env=item.auth_secret_env,
            target_hash=item.target_hash,
            registered_at=item.registered_at,
            display_name=item.display_name,
            control_plane_provider_id=provider_id if item.provider_ref == registration.provider_ref else item.control_plane_provider_id,
            registration_status=item.registration_status,
            last_heartbeat_at=item.last_heartbeat_at,
            heartbeat_ttl_seconds=item.heartbeat_ttl_seconds,
            revoked_at=item.revoked_at,
            revocation_reason=item.revocation_reason,
            attestation=item.attestation,
            governance=item.governance,
        )
        for item in registrations
    ]
    write_remote_registry(registry_path, updated_registrations)
    return {
        "provider_id": PROVIDER_ID,
        "remote_registry": str(registry_path),
        "control_plane_provider_id": provider_id,
        "agentd_socket": str(agentd_socket_path(args.agentd_socket)),
        "record": record,
    }


def remote_bridge_payload(
    *,
    endpoint: str | None,
    registration: RemoteRegistration | None,
    registry_path: Path | None,
    trust_policy: dict[str, object],
    response_status: int | None = None,
) -> dict[str, object]:
    payload = remote_auth_description(registration, registry_path)
    payload.update(
        {
            "endpoint": endpoint,
            "trust_mode": trust_policy.get("mode"),
            "trust_enforced": trust_policy.get("enforced"),
            "response_status": response_status,
        }
    )
    return payload


def handle_remote_navigate(
    context: BrowserContext,
    *,
    max_links: int,
    max_text_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
    args: argparse.Namespace,
) -> dict[str, object]:
    registry_path, registration = resolve_remote_registration(context, args)
    endpoint = resolve_effective_endpoint(context, registration)
    if endpoint is None or context.timeout_seconds is None:
        raise BrowserCommandError(
            category="internal",
            error_code="browser_remote_context_incomplete",
            message="browser remote navigate context is incomplete",
            retryable=False,
        )
    trust_policy = browser_trust_policy()
    request_payload = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "operation": context.operation,
        "request": {
            "capability_id": context.capability_id,
            "url": context.raw_url,
            "timeout_seconds": context.timeout_seconds,
            "max_links": max_links,
            "max_text_chars": max_text_chars,
        },
    }
    headers = build_remote_auth_headers(
        context=context,
        registration=registration,
        policy_context=policy_context,
    )
    try:
        remote_result = post_json(
            endpoint,
            request_payload,
            timeout_seconds=context.timeout_seconds,
            trust_policy=trust_policy,
            error_prefix="browser",
            user_agent="AIOSBrowserCompat/0.3",
            extra_headers=headers,
        )
    except RemoteSupportError as exc:
        raise BrowserCommandError(
            category=exc.category,
            error_code=exc.error_code,
            message=exc.message,
            retryable=exc.retryable,
            details={
                **(exc.details or {}),
                "remote_bridge": remote_bridge_payload(
                    endpoint=endpoint,
                    registration=registration,
                    registry_path=registry_path,
                    trust_policy=trust_policy,
                ),
            },
        ) from exc
    response = remote_result.get("response")
    if not isinstance(response, dict):
        raise BrowserCommandError(
            category="remote_error",
            error_code="browser_remote_response_invalid",
            message="remote browser worker returned a non-object response",
            retryable=True,
            details={
                "remote_bridge": remote_bridge_payload(
                    endpoint=endpoint,
                    registration=registration,
                    registry_path=registry_path,
                    trust_policy=trust_policy,
                    response_status=int(remote_result.get("status_code") or 0),
                )
            },
        )
    links = response.get("links") if isinstance(response.get("links"), list) else []
    document = response.get("document") if isinstance(response.get("document"), dict) else {}
    payload_status = str(response.get("status") or "ok")
    fetch = response.get("fetch") if isinstance(response.get("fetch"), dict) else fetch_info(
        requested_url=context.raw_url,
        resolved_url=response.get("resolved_url"),
        final_url=response.get("final_url") or endpoint,
        status_code=int(remote_result.get("status_code") or 200),
        content_type=str(response.get("content_type")) if response.get("content_type") is not None else None,
        charset=str(response.get("charset")) if response.get("charset") is not None else None,
        truncated=bool(response.get("truncated", False)),
        fetched_at=str(response.get("fetched_at")) if response.get("fetched_at") is not None else utc_now(),
    )
    normalized_document = build_document_info(
        title=str(document.get("title") or response.get("title") or ""),
        text_length=int(document.get("text_length") or response.get("text_length") or 0),
        link_count=int(document.get("link_count") or response.get("link_count") or len(links)),
        matched_count=None,
        text_preview=str(document.get("text_preview") or response.get("text_preview") or ""),
        text=None,
        links=links[:max_links],
    )
    return build_success_payload(
        status=payload_status,
        context=context,
        fetch=fetch,
        document=normalized_document,
        remote_bridge=remote_bridge_payload(
            endpoint=endpoint,
            registration=registration,
            registry_path=registry_path,
            trust_policy=trust_policy,
            response_status=int(remote_result.get("status_code") or 200),
        ),
        extra_payload={
            "requested_url": fetch.get("requested_url"),
            "resolved_url": fetch.get("resolved_url"),
            "final_url": fetch.get("final_url"),
            "status_code": fetch.get("status_code"),
            "content_type": fetch.get("content_type"),
            "charset": fetch.get("charset"),
            "title": normalized_document["title"],
            "text_preview": normalized_document["text_preview"],
            "text_length": normalized_document["text_length"],
            "link_count": normalized_document["link_count"],
            "links": normalized_document["links"],
            "truncated": fetch.get("truncated"),
            "fetched_at": fetch.get("fetched_at"),
            "remote_bridge": remote_bridge_payload(
                endpoint=endpoint,
                registration=registration,
                registry_path=registry_path,
                trust_policy=trust_policy,
                response_status=int(remote_result.get("status_code") or 200),
            ),
            "remote_response": response,
        },
        audit_log=audit_log,
        policy_context=policy_context,
    )


def handle_remote_extract(
    context: BrowserContext,
    *,
    max_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
    args: argparse.Namespace,
) -> dict[str, object]:
    registry_path, registration = resolve_remote_registration(context, args)
    endpoint = resolve_effective_endpoint(context, registration)
    if endpoint is None or context.timeout_seconds is None:
        raise BrowserCommandError(
            category="internal",
            error_code="browser_remote_context_incomplete",
            message="browser remote extract context is incomplete",
            retryable=False,
        )
    trust_policy = browser_trust_policy()
    request_payload = {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "operation": context.operation,
        "request": {
            "capability_id": context.capability_id,
            "url": context.raw_url,
            "selector": context.selector,
            "timeout_seconds": context.timeout_seconds,
            "max_chars": max_chars,
        },
    }
    headers = build_remote_auth_headers(
        context=context,
        registration=registration,
        policy_context=policy_context,
    )
    try:
        remote_result = post_json(
            endpoint,
            request_payload,
            timeout_seconds=context.timeout_seconds,
            trust_policy=trust_policy,
            error_prefix="browser",
            user_agent="AIOSBrowserCompat/0.3",
            extra_headers=headers,
        )
    except RemoteSupportError as exc:
        raise BrowserCommandError(
            category=exc.category,
            error_code=exc.error_code,
            message=exc.message,
            retryable=exc.retryable,
            details={
                **(exc.details or {}),
                "remote_bridge": remote_bridge_payload(
                    endpoint=endpoint,
                    registration=registration,
                    registry_path=registry_path,
                    trust_policy=trust_policy,
                ),
            },
        ) from exc
    response = remote_result.get("response")
    if not isinstance(response, dict):
        raise BrowserCommandError(
            category="remote_error",
            error_code="browser_remote_response_invalid",
            message="remote browser worker returned a non-object response",
            retryable=True,
            details={
                "remote_bridge": remote_bridge_payload(
                    endpoint=endpoint,
                    registration=registration,
                    registry_path=registry_path,
                    trust_policy=trust_policy,
                    response_status=int(remote_result.get("status_code") or 0),
                )
            },
        )
    fetch = response.get("fetch") if isinstance(response.get("fetch"), dict) else fetch_info(
        requested_url=context.raw_url,
        resolved_url=response.get("resolved_url"),
        final_url=response.get("final_url") or endpoint,
        status_code=int(remote_result.get("status_code") or 200),
        content_type=str(response.get("content_type")) if response.get("content_type") is not None else None,
        charset=str(response.get("charset")) if response.get("charset") is not None else None,
        truncated=bool(response.get("truncated", False)),
        fetched_at=str(response.get("fetched_at")) if response.get("fetched_at") is not None else utc_now(),
    )
    text = str(response.get("text") or "")[:max_chars]
    matched_count = int(response.get("matched_count") or 0)
    payload_status = str(response.get("status") or ("ok" if text else "not-found"))
    normalized_document = build_document_info(
        title=None,
        text_length=int(response.get("text_length") or len(text)),
        link_count=None,
        matched_count=matched_count,
        text_preview=str(response.get("text_preview") or text[:TEXT_PREVIEW_CHARS]),
        text=text,
        links=None,
    )
    return build_success_payload(
        status=payload_status,
        context=context,
        fetch=fetch,
        document=normalized_document,
        remote_bridge=remote_bridge_payload(
            endpoint=endpoint,
            registration=registration,
            registry_path=registry_path,
            trust_policy=trust_policy,
            response_status=int(remote_result.get("status_code") or 200),
        ),
        extra_payload={
            "requested_url": fetch.get("requested_url"),
            "resolved_url": fetch.get("resolved_url"),
            "final_url": fetch.get("final_url"),
            "status_code": fetch.get("status_code"),
            "content_type": fetch.get("content_type"),
            "selector": context.selector,
            "matched_count": matched_count,
            "text": text,
            "truncated": fetch.get("truncated") or len(text) >= max_chars,
            "fetched_at": fetch.get("fetched_at"),
            "remote_bridge": remote_bridge_payload(
                endpoint=endpoint,
                registration=registration,
                registry_path=registry_path,
                trust_policy=trust_policy,
                response_status=int(remote_result.get("status_code") or 200),
            ),
            "remote_response": response,
        },
        audit_log=audit_log,
        policy_context=policy_context,
    )


def handle_navigate(
    context: BrowserContext,
    max_links: int,
    max_text_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
    args: argparse.Namespace,
) -> dict[str, object]:
    if context.raw_url is None or context.timeout_seconds is None:
        raise BrowserCommandError(
            category="internal",
            error_code="browser_context_incomplete",
            message="browser navigate context is incomplete",
            retryable=False,
        )
    ensure_session_arguments_coherent(context)
    if context.endpoint or context.provider_ref:
        return handle_remote_navigate(
            context,
            max_links=max_links,
            max_text_chars=max_text_chars,
            audit_log=audit_log,
            policy_context=policy_context,
            args=args,
        )
    enforce_timeout_budget(context.timeout_seconds)
    result = fetch_url(context.raw_url, context.timeout_seconds)
    title = ""
    text_preview = collapse_whitespace(result.body_text)[:max_text_chars]
    links: list[dict[str, str]] = []
    text_length = len(collapse_whitespace(result.body_text))

    if is_html_document(result):
        summary = summarize_document(result.body_text)
        title = str(summary["title"])
        text_content = str(summary["text_content"])
        text_length = len(text_content)
        text_preview = text_content[:max_text_chars]
        links = list(summary["links"])[:max_links]

    document = build_document_info(
        title=title,
        text_length=text_length,
        link_count=len(links),
        matched_count=None,
        text_preview=text_preview,
        text=None,
        links=links,
    )
    fetch = fetch_info_from_result(result)
    session_binding = record_browser_navigation_session(
        args,
        context,
        fetch,
        body_text=result.body_text,
        title=title,
        text_preview=text_preview,
        text_length=text_length,
        links=links,
    )
    extra_payload = {
        "requested_url": result.requested_url,
        "resolved_url": result.resolved_url,
        "final_url": result.final_url,
        "status_code": result.status_code,
        "content_type": result.content_type,
        "charset": result.charset,
        "title": title,
        "text_preview": text_preview,
        "text_length": text_length,
        "link_count": len(links),
        "links": links,
        "truncated": result.truncated,
        "fetched_at": result.fetched_at,
    }
    if session_binding is not None:
        extra_payload.update(session_binding)
    return build_success_payload(
        status="ok",
        context=context,
        fetch=fetch,
        document=document,
        remote_bridge=None,
        extra_payload=extra_payload,
        audit_log=audit_log,
        policy_context=policy_context,
    )


def handle_extract(
    context: BrowserContext,
    max_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
    args: argparse.Namespace,
) -> dict[str, object]:
    if context.raw_url is None or context.timeout_seconds is None:
        raise BrowserCommandError(
            category="internal",
            error_code="browser_context_incomplete",
            message="browser extract context is incomplete",
            retryable=False,
        )
    ensure_session_arguments_coherent(context)
    if context.endpoint or context.provider_ref:
        return handle_remote_extract(
            context,
            max_chars=max_chars,
            audit_log=audit_log,
            policy_context=policy_context,
            args=args,
        )
    enforce_timeout_budget(context.timeout_seconds)
    result = fetch_url(context.raw_url, context.timeout_seconds)
    selector = parse_selector(context.selector)
    matched_count = 0

    if selector is None:
        extracted_text = collapse_whitespace(result.body_text)
    elif is_html_document(result):
        parser = SelectorTextParser(selector)
        parser.feed(result.body_text)
        parser.close()
        extracted_text = collapse_whitespace(" ".join(parser.text_parts))
        matched_count = parser.matches
    else:
        extracted_text = ""

    payload_status = "ok" if extracted_text else "not-found"
    text_payload = extracted_text[:max_chars]
    document = build_document_info(
        title=None,
        text_length=len(extracted_text),
        link_count=None,
        matched_count=matched_count,
        text_preview=text_payload[:TEXT_PREVIEW_CHARS],
        text=text_payload,
        links=None,
    )
    fetch = fetch_info_from_result(result)
    session_binding = record_browser_extract_session(
        args,
        context,
        fetch,
        text=text_payload,
        matched_count=matched_count,
    )
    extra_payload = {
        "requested_url": result.requested_url,
        "resolved_url": result.resolved_url,
        "final_url": result.final_url,
        "status_code": result.status_code,
        "content_type": result.content_type,
        "selector": context.selector,
        "matched_count": matched_count,
        "text": text_payload,
        "truncated": result.truncated or len(extracted_text) > max_chars,
        "fetched_at": result.fetched_at,
    }
    if session_binding is not None:
        extra_payload.update(session_binding)
    return build_success_payload(
        status=payload_status,
        context=context,
        fetch=fetch,
        document=document,
        remote_bridge=None,
        extra_payload=extra_payload,
        audit_log=audit_log,
        policy_context=policy_context,
    )


def main() -> int:
    args = parse_args()
    context = context_from_args(args)
    audit_log = resolve_audit_log(args)
    policy_context = CompatPolicyContext(
        mode="standalone-local",
        policyd_socket=None,
        execution_token=None,
        token_context=None,
        verification=None,
        shared_audit_log=None,
    )
    try:
        policy_context = standalone_policy_context(args)
        if args.command == "manifest":
            payload: dict[str, object] = build_manifest()
        elif args.command == "health":
            payload = handle_health(audit_log, policy_context)
        elif args.command == "permissions":
            payload = load_compat_permission_manifest()
        elif args.command == "list-remotes":
            payload = handle_list_remotes(args)
        elif args.command == "register-remote":
            payload = handle_register_remote(args)
        elif args.command == "heartbeat-remote":
            payload = handle_heartbeat_remote(args)
        elif args.command == "revoke-remote":
            payload = handle_revoke_remote(args)
        elif args.command == "unregister-remote":
            payload = handle_unregister_remote(args)
        elif args.command == "register-control-plane":
            payload = handle_register_control_plane(args)
        elif args.command == "list-sessions":
            payload = handle_list_sessions(args)
        elif args.command == "open-session":
            payload = handle_open_session(args)
        elif args.command == "close-session":
            payload = handle_close_session(args)
        elif args.command == "open-window":
            payload = handle_open_window(args)
        elif args.command == "close-window":
            payload = handle_close_window(args)
        elif args.command == "open-tab":
            payload = handle_open_tab(args)
        elif args.command == "close-tab":
            payload = handle_close_tab(args)
        elif args.command == "navigate":
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=False,
            )
            payload = handle_navigate(
                context,
                args.max_links,
                args.max_text_chars,
                audit_log,
                policy_context,
                args,
            )
        elif args.command == "extract":
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=False,
            )
            payload = handle_extract(context, args.max_chars, audit_log, policy_context, args)
        else:
            raise BrowserCommandError(
                category="invalid_request",
                error_code="browser_unsupported_command",
                message=f"unsupported command: {args.command}",
                retryable=False,
            )
    except CompatPolicyError as exc:
        error = BrowserCommandError(
            category=exc.category,
            error_code=exc.error_code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    error=error,
                    audit_log=audit_log,
                    policy_context=exc.policy_context or policy_context,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return error.exit_code
    except BrowserCommandError as exc:
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    error=exc,
                    audit_log=audit_log,
                    policy_context=policy_context,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        error = BrowserCommandError(
            category="internal",
            error_code="browser_internal_error",
            message=str(exc),
            retryable=False,
        )
        print(
            json.dumps(
                build_error_payload(
                    context=context,
                    error=error,
                    audit_log=audit_log,
                    policy_context=policy_context,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return error.exit_code

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
