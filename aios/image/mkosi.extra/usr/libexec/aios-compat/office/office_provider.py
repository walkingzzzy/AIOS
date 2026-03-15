#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

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


PROVIDER_ID = "compat.office.document.local"
DECLARED_CAPABILITIES = [
    "compat.document.open",
    "compat.office.export_pdf",
]
REQUIRED_PERMISSIONS = [
    "document.user-selected",
]
COMPAT_PERMISSION_SCHEMA_REF = "aios/compat-permission-manifest.schema.json"
RESULT_PROTOCOL_SCHEMA_REF = "aios/compat-office-result.schema.json"
DESCRIPTOR_FILENAME = "office.document.local.json"
WORKER_CONTRACT = "compat-office-document-v1"
AUDIT_SCHEMA_VERSION = "2026-03-13"
DEFAULT_AUDIT_LOG_ENV = "AIOS_COMPAT_OFFICE_AUDIT_LOG"
DEFAULT_USER_ID = "compat-user"
DEFAULT_SESSION_ID = "compat-session"
DEFAULT_TASK_ID = "compat-task"
SUPPORTED_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".log",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
}
PDF_PAGE_WIDTH = 612
PDF_PAGE_HEIGHT = 792
PDF_MARGIN_LEFT = 72
PDF_START_Y = 720
PDF_LINE_HEIGHT = 14
PDF_WRAP_WIDTH = 88
PDF_LINES_PER_PAGE = 46
COMMAND_EXIT_CODES = {
    "invalid_request": 2,
    "precondition_failed": 3,
    "permission_denied": 13,
    "internal": 1,
}


@dataclass(frozen=True)
class DocumentContent:
    source_path: Path
    mime_type: str
    title: str
    text_content: str
    size_bytes: int
    line_count: int
    char_count: int
    loaded_at: str


@dataclass(frozen=True)
class OfficeContext:
    command: str
    operation: str | None
    capability_id: str | None
    source_path: str | None
    output_path: str | None
    preview_chars: int | None
    started_at: str


class OfficeCommandError(RuntimeError):
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


class HtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._title_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
        elif tag == "title":
            self._title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
        elif tag == "title" and self._title_depth > 0:
            self._title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        stripped = data.strip()
        if self._title_depth > 0 and stripped:
            self.title_parts.append(stripped)
        if stripped:
            self.text_parts.append(stripped)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS office compat provider baseline runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("manifest")
    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--audit-log", type=Path)
    add_policy_args(health_parser)
    subparsers.add_parser("permissions")

    open_parser = subparsers.add_parser("open")
    open_parser.add_argument("--path", type=Path, required=True)
    open_parser.add_argument("--preview-chars", type=int, default=240)
    open_parser.add_argument("--audit-log", type=Path)
    add_policy_args(open_parser)

    export_parser = subparsers.add_parser("export-pdf")
    export_parser.add_argument("--path", type=Path, required=True)
    export_parser.add_argument("--output-path", type=Path, required=True)
    export_parser.add_argument("--audit-log", type=Path)
    add_policy_args(export_parser)

    return parser.parse_args()


def context_from_args(args: argparse.Namespace) -> OfficeContext:
    started_at = utc_now()
    if args.command == "open":
        return OfficeContext(
            command="open",
            operation="compat.document.open",
            capability_id="compat.document.open",
            source_path=str(args.path),
            output_path=None,
            preview_chars=args.preview_chars,
            started_at=started_at,
        )
    if args.command == "export-pdf":
        return OfficeContext(
            command="export-pdf",
            operation="compat.office.export_pdf",
            capability_id="compat.office.export_pdf",
            source_path=str(args.path),
            output_path=str(args.output_path),
            preview_chars=None,
            started_at=started_at,
        )
    return OfficeContext(
        command=args.command,
        operation=None,
        capability_id=None,
        source_path=None,
        output_path=None,
        preview_chars=None,
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
            "open-local-document",
            "export-text-pdf",
            "permission-manifest",
            "office-result-protocol-v1",
            "audit-jsonl",
        ],
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "notes": [
            "Baseline local document runtime is available",
            "Structured compat-office-document-v1 payloads are emitted for success and error paths",
            "Optional JSONL audit sink can be configured for machine-readable evidence",
            "Supports text, markdown, and HTML documents with text-only PDF export",
        ],
    }


def decode_bytes(body: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def resolve_supported_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise OfficeCommandError(
            category="precondition_failed",
            error_code="office_document_missing",
            message=f"missing document: {resolved}",
            retryable=False,
            details={"source_path": str(resolved)},
        )
    if not resolved.is_file():
        raise OfficeCommandError(
            category="invalid_request",
            error_code="office_document_not_file",
            message=f"document path must be a file: {resolved}",
            retryable=False,
            details={"source_path": str(resolved)},
        )
    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise OfficeCommandError(
            category="invalid_request",
            error_code="office_document_type_unsupported",
            message=f"unsupported document type for baseline runtime: {suffix or '<none>'}",
            retryable=False,
            details={"source_path": str(resolved), "suffix": suffix or None},
        )
    return resolved


def parse_html_document(source_path: Path, raw_text: str) -> tuple[str, str]:
    parser = HtmlTextParser()
    parser.feed(raw_text)
    parser.close()
    title = collapse_whitespace(" ".join(parser.title_parts)) or source_path.stem
    text_content = "\n".join(parser.text_parts)
    return title, text_content


def infer_title(source_path: Path, text_content: str) -> str:
    for line in text_content.splitlines():
        candidate = line.strip().lstrip("#*- ")
        if candidate:
            return candidate[:120]
    return source_path.stem


def load_document(path: Path) -> DocumentContent:
    source_path = resolve_supported_path(path)
    raw_bytes = source_path.read_bytes()
    raw_text = decode_bytes(raw_bytes)
    mime_type = mimetypes.guess_type(str(source_path))[0] or "text/plain"

    if source_path.suffix.lower() in {".html", ".htm"} or mime_type == "text/html":
        title, text_content = parse_html_document(source_path, raw_text)
    else:
        text_content = raw_text
        title = infer_title(source_path, text_content)

    text_content = text_content.strip()
    return DocumentContent(
        source_path=source_path,
        mime_type=mime_type,
        title=title,
        text_content=text_content,
        size_bytes=len(raw_bytes),
        line_count=len(text_content.splitlines()) if text_content else 0,
        char_count=len(text_content),
        loaded_at=utc_now(),
    )


def pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_pdf_lines(text_content: str) -> list[str]:
    wrapped_lines: list[str] = []
    for raw_line in text_content.splitlines() or [""]:
        cleaned = raw_line.rstrip()
        if not cleaned:
            wrapped_lines.append("")
            continue
        segments = textwrap.wrap(
            cleaned,
            width=PDF_WRAP_WIDTH,
            replace_whitespace=False,
            drop_whitespace=False,
        )
        wrapped_lines.extend(segments or [""])
    return wrapped_lines or [""]


def build_pdf(text_content: str) -> tuple[bytes, int]:
    all_lines = wrap_pdf_lines(text_content)
    pages = [all_lines[index : index + PDF_LINES_PER_PAGE] for index in range(0, len(all_lines), PDF_LINES_PER_PAGE)]
    if not pages:
        pages = [[""]]

    page_object_ids: list[int] = []
    content_object_ids: list[int] = []
    next_object_id = 3
    for _ in pages:
        page_object_ids.append(next_object_id)
        content_object_ids.append(next_object_id + 1)
        next_object_id += 2
    font_object_id = next_object_id

    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    objects[2] = f"<< /Type /Pages /Count {len(page_object_ids)} /Kids [ {kids} ] >>".encode("utf-8")

    if not (len(page_object_ids) == len(content_object_ids) == len(pages)):
        raise OfficeCommandError(
            category="internal",
            error_code="office_pdf_layout_inconsistent",
            message="pdf object layout is inconsistent",
            retryable=False,
        )

    for page_object_id, content_object_id, page_lines in zip(page_object_ids, content_object_ids, pages):
        stream_lines = [
            "BT",
            "/F1 11 Tf",
            f"{PDF_MARGIN_LEFT} {PDF_START_Y} Td",
            f"{PDF_LINE_HEIGHT} TL",
        ]
        if page_lines:
            stream_lines.append(f"({pdf_escape(page_lines[0])}) Tj")
            for line in page_lines[1:]:
                stream_lines.append("T*")
                stream_lines.append(f"({pdf_escape(line)}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("utf-8")
        objects[page_object_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_WIDTH} {PDF_PAGE_HEIGHT}] /Resources << /Font << /F1 {font_object_id} 0 R >> >> /Contents {content_object_id} 0 R >>"
        ).encode("utf-8")
        objects[content_object_id] = b"<< /Length " + str(len(stream)).encode("utf-8") + b" >>\nstream\n" + stream + b"\nendstream"

    objects[font_object_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    pdf_bytes = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, font_object_id + 1):
        offsets.append(len(pdf_bytes))
        pdf_bytes.extend(f"{object_id} 0 obj\n".encode("utf-8"))
        pdf_bytes.extend(objects[object_id])
        pdf_bytes.extend(b"\nendobj\n")

    xref_offset = len(pdf_bytes)
    pdf_bytes.extend(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
    pdf_bytes.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_bytes.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
    pdf_bytes.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("utf-8"))
    return bytes(pdf_bytes), len(pages)


def build_document_info(
    *,
    document: DocumentContent | None = None,
    preview: str | None = None,
    supported_export_formats: list[str] | None = None,
) -> dict[str, object]:
    if document is None:
        return {
            "source_path": None,
            "mime_type": None,
            "title": None,
            "size_bytes": None,
            "line_count": None,
            "char_count": None,
            "loaded_at": None,
            "preview": preview,
            "supported_export_formats": supported_export_formats,
        }
    return {
        "source_path": str(document.source_path),
        "mime_type": document.mime_type,
        "title": document.title,
        "size_bytes": document.size_bytes,
        "line_count": document.line_count,
        "char_count": document.char_count,
        "loaded_at": document.loaded_at,
        "preview": preview,
        "supported_export_formats": supported_export_formats,
    }


def build_export_info(
    *,
    output_path: str | None = None,
    mime_type: str | None = None,
    page_count: int | None = None,
    bytes_written: int | None = None,
    exported_at: str | None = None,
) -> dict[str, object]:
    return {
        "output_path": output_path,
        "mime_type": mime_type,
        "page_count": page_count,
        "bytes_written": bytes_written,
        "exported_at": exported_at,
    }


def build_result_protocol(
    *,
    status: str,
    context: OfficeContext,
    document: dict[str, object] | None,
    export: dict[str, object] | None,
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
            "path": context.source_path,
            "output_path": context.output_path,
            "preview_chars": context.preview_chars,
        },
        "document": document or build_document_info(),
        "export": export or build_export_info(),
        "policy": {
            "compat_permission_manifest": permission_manifest,
            "filesystem_access": capability.get("filesystem_access"),
            "approval_required": capability.get("approval_required"),
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
    context: OfficeContext,
    document: dict[str, object],
    export: dict[str, object] | None,
    extra_payload: dict[str, object],
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    finished_at = utc_now()
    result_protocol = build_result_protocol(
        status=status,
        context=context,
        document=document,
        export=export,
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
    context: OfficeContext,
    error: OfficeCommandError,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    finished_at = utc_now()
    source_path = error.details.get("source_path")
    export_path = error.details.get("output_path")
    error_context = OfficeContext(
        command=context.command,
        operation=context.operation,
        capability_id=context.capability_id,
        source_path=source_path if isinstance(source_path, str) else context.source_path,
        output_path=export_path if isinstance(export_path, str) else context.output_path,
        preview_chars=context.preview_chars,
        started_at=context.started_at,
    )
    result_protocol = build_result_protocol(
        status="error",
        context=error_context,
        document=None,
        export=None,
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
    payload["audit_id"] = append_audit_log(audit_log, payload, error_context, policy_context)
    payload["audit_log"] = str(audit_log) if audit_log is not None else None
    (payload.get("result_protocol") or {}).get("audit", {})["audit_id"] = payload["audit_id"]
    (payload.get("result_protocol") or {}).get("audit", {})["audit_log"] = payload["audit_log"]
    return payload


def append_audit_log(
    audit_log: Path | None,
    payload: dict[str, object],
    context: OfficeContext,
    policy_context: CompatPolicyContext,
) -> str | None:
    if audit_log is None and policy_context.shared_audit_log is None:
        return None
    if audit_log is not None and audit_log.parent:
        audit_log.parent.mkdir(parents=True, exist_ok=True)
    audit_id = f"office-compat-{time.time_ns()}"
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
        or os.environ.get("AIOS_COMPAT_OFFICE_AUDIT_USER_ID", DEFAULT_USER_ID),
        "session_id": token_context.get("session_id")
        or os.environ.get("AIOS_COMPAT_OFFICE_AUDIT_SESSION_ID", DEFAULT_SESSION_ID),
        "task_id": token_context.get("task_id")
        or os.environ.get("AIOS_COMPAT_OFFICE_AUDIT_TASK_ID", DEFAULT_TASK_ID),
        "provider_id": PROVIDER_ID,
        "capability_id": context.capability_id,
        "approval_id": token_context.get("approval_ref"),
        "decision": decision,
        "execution_location": "sandbox",
        "route_state": (
            "compat-office-centralized-policy"
            if policy_context.mode == "policyd-verified"
            else "compat-office-baseline"
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
            "source_path": context.source_path,
            "output_path": context.output_path,
            "title": payload.get("title"),
            "mime_type": payload.get("mime_type"),
            "page_count": payload.get("page_count"),
            "bytes_written": payload.get("bytes_written"),
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
        "engine": "text-document-baseline",
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
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
            "Structured compat-office-document-v1 payloads are enabled",
            "Centralized policy/token verification is enabled when policyd_socket + execution_token are supplied",
            "No native docx/xlsx/pptx bridge; intended as a governed fallback runtime",
        ],
    }


def handle_open(
    context: OfficeContext,
    path: Path,
    preview_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    document = load_document(path)
    preview = document.text_content[:preview_chars]
    document_payload = build_document_info(
        document=document,
        preview=preview,
        supported_export_formats=["pdf"],
    )
    return build_success_payload(
        status="ok",
        context=context,
        document=document_payload,
        export=None,
        extra_payload={
            "path": str(document.source_path),
            "title": document.title,
            "mime_type": document.mime_type,
            "size_bytes": document.size_bytes,
            "line_count": document.line_count,
            "char_count": document.char_count,
            "preview": preview,
            "loaded_at": document.loaded_at,
            "supported_export_formats": ["pdf"],
        },
        audit_log=audit_log,
        policy_context=policy_context,
    )


def handle_export_pdf(
    context: OfficeContext,
    path: Path,
    output_path: Path,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    document = load_document(path)
    pdf_bytes, page_count = build_pdf(document.text_content)
    resolved_output = output_path.expanduser().resolve()
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_bytes(pdf_bytes)
    exported_at = utc_now()
    document_payload = build_document_info(document=document, preview=None, supported_export_formats=["pdf"])
    export_payload = build_export_info(
        output_path=str(resolved_output),
        mime_type="application/pdf",
        page_count=page_count,
        bytes_written=len(pdf_bytes),
        exported_at=exported_at,
    )
    return build_success_payload(
        status="ok",
        context=context,
        document=document_payload,
        export=export_payload,
        extra_payload={
            "source_path": str(document.source_path),
            "output_path": str(resolved_output),
            "mime_type": "application/pdf",
            "page_count": page_count,
            "bytes_written": len(pdf_bytes),
            "title": document.title,
            "exported_at": exported_at,
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
        elif args.command == "open":
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=False,
            )
            payload = handle_open(
                context,
                args.path,
                args.preview_chars,
                audit_log,
                policy_context,
            )
        elif args.command == "export-pdf":
            policy_context = resolve_policy_context(
                args,
                capability_id=context.capability_id,
                execution_location="sandbox",
                consume=False,
            )
            payload = handle_export_pdf(
                context,
                args.path,
                args.output_path,
                audit_log,
                policy_context,
            )
        else:
            raise OfficeCommandError(
                category="invalid_request",
                error_code="office_unsupported_command",
                message=f"unsupported command: {args.command}",
                retryable=False,
            )
    except CompatPolicyError as exc:
        error = OfficeCommandError(
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
    except OfficeCommandError as exc:
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
        error = OfficeCommandError(
            category="internal",
            error_code="office_internal_error",
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
