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
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TEXT_PREVIEW_CHARS = 240
DEFAULT_TIMEOUT_SECONDS = 10.0
WHITESPACE_RE = re.compile(r"\s+")
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
    timeout_seconds: float | None
    max_links: int | None
    max_text_chars: int | None
    max_chars: int | None
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS browser compat provider baseline runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("manifest")
    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--audit-log", type=Path)
    add_policy_args(health_parser)
    subparsers.add_parser("permissions")

    navigate_parser = subparsers.add_parser("navigate")
    navigate_parser.add_argument("--url", required=True)
    navigate_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    navigate_parser.add_argument("--max-links", type=int, default=8)
    navigate_parser.add_argument("--max-text-chars", type=int, default=TEXT_PREVIEW_CHARS)
    navigate_parser.add_argument("--audit-log", type=Path)
    add_policy_args(navigate_parser)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--url", required=True)
    extract_parser.add_argument("--selector")
    extract_parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    extract_parser.add_argument("--max-chars", type=int, default=4096)
    extract_parser.add_argument("--audit-log", type=Path)
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
            timeout_seconds=args.timeout_seconds,
            max_links=args.max_links,
            max_text_chars=args.max_text_chars,
            max_chars=None,
            started_at=started_at,
        )
    if args.command == "extract":
        return BrowserContext(
            command="extract",
            operation="compat.browser.extract",
            capability_id="compat.browser.extract",
            raw_url=args.url,
            selector=args.selector,
            timeout_seconds=args.timeout_seconds,
            max_links=None,
            max_text_chars=None,
            max_chars=args.max_chars,
            started_at=started_at,
        )
    return BrowserContext(
        command=args.command,
        operation=None,
        capability_id=None,
        raw_url=None,
        selector=None,
        timeout_seconds=None,
        max_links=None,
        max_text_chars=None,
        max_chars=None,
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


def build_manifest() -> dict[str, object]:
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
        ],
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "notes": [
            "Baseline HTML/text fetch runtime is available",
            "Structured compat-browser-fetch-v1 payloads are emitted for success, not-found, and error paths",
            "Optional JSONL audit sink can be configured for machine-readable evidence",
            "JavaScript execution and real browser bridge remain pending",
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
            "timeout_seconds": context.timeout_seconds,
            "max_links": context.max_links,
            "max_text_chars": context.max_text_chars,
            "max_chars": context.max_chars,
        },
        "fetch": fetch or fetch_info(requested_url=context.raw_url),
        "document": document or build_document_info(),
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
    fetch_result: FetchResult,
    document: dict[str, object],
    extra_payload: dict[str, object],
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    finished_at = utc_now()
    result_protocol = build_result_protocol(
        status=status,
        context=context,
        fetch=fetch_info_from_result(fetch_result),
        document=document,
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
            "policy_mode": policy_context.mode,
            "token_verified": policy_context.token_verified,
            "session_id": token_context.get("session_id"),
            "task_id": token_context.get("task_id"),
            "approval_ref": token_context.get("approval_ref"),
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
        "engine": "html-fetch-baseline",
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
        "notes": [
            "Supports file://, http://, and https:// targets",
            "Structured compat-browser-fetch-v1 payloads are enabled",
            "Centralized policy/token verification is enabled when policyd_socket + execution_token are supplied",
            "No JavaScript execution; intended as a governed fallback runtime",
        ],
    }


def handle_navigate(
    context: BrowserContext,
    max_links: int,
    max_text_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    if context.raw_url is None or context.timeout_seconds is None:
        raise BrowserCommandError(
            category="internal",
            error_code="browser_context_incomplete",
            message="browser navigate context is incomplete",
            retryable=False,
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
    return build_success_payload(
        status="ok",
        context=context,
        fetch_result=result,
        document=document,
        extra_payload={
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
        },
        audit_log=audit_log,
        policy_context=policy_context,
    )


def handle_extract(
    context: BrowserContext,
    max_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    if context.raw_url is None or context.timeout_seconds is None:
        raise BrowserCommandError(
            category="internal",
            error_code="browser_context_incomplete",
            message="browser extract context is incomplete",
            retryable=False,
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
    return build_success_payload(
        status=payload_status,
        context=context,
        fetch_result=result,
        document=document,
        extra_payload={
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
        },
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
            )
        elif args.command == "extract":
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=False,
            )
            payload = handle_extract(context, args.max_chars, audit_log, policy_context)
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
