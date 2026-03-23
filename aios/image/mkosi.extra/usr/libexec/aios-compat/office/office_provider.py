#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import textwrap
import time
import base64
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from pathlib import PurePosixPath
from xml.etree import ElementTree

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
DEFAULT_REMOTE_REGISTRY_ENV = "AIOS_OFFICE_REMOTE_REGISTRY"
DEFAULT_REMOTE_AUTH_SECRET_ENV = "AIOS_OFFICE_REMOTE_AUTH_SECRET"
DEFAULT_TRUST_MODE_ENV = "AIOS_OFFICE_TRUST_MODE"
DEFAULT_ALLOWLIST_ENV = "AIOS_OFFICE_ALLOWLIST"
DEFAULT_REMOTE_ATTESTATION_MODE_ENV = "AIOS_OFFICE_REMOTE_ATTESTATION_MODE"
DEFAULT_REMOTE_FLEET_ID_ENV = "AIOS_OFFICE_REMOTE_FLEET_ID"
DEFAULT_REMOTE_GOVERNANCE_GROUP_ENV = "AIOS_OFFICE_REMOTE_GOVERNANCE_GROUP"
DEFAULT_REMOTE_POLICY_GROUP_ENV = "AIOS_OFFICE_REMOTE_POLICY_GROUP"
DEFAULT_REMOTE_APPROVAL_REF_ENV = "AIOS_OFFICE_REMOTE_APPROVAL_REF"
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
    ".docx",
    ".xlsx",
    ".pptx",
}
OOXML_MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
PDF_PAGE_WIDTH = 612
PDF_PAGE_HEIGHT = 792
PDF_MARGIN_LEFT = 72
PDF_START_Y = 720
PDF_LINE_HEIGHT = 14
PDF_WRAP_WIDTH = 88
PDF_LINES_PER_PAGE = 46
DEFAULT_TIMEOUT_SECONDS = 10.0
COMMAND_EXIT_CODES = {
    "invalid_request": 2,
    "precondition_failed": 3,
    "permission_denied": 13,
    "internal": 1,
}
PROVIDER_REGISTER_METHOD = "provider.register"


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
    endpoint: str | None
    provider_ref: str | None
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


def xml_local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def xml_attr(element: ElementTree.Element, local_name: str) -> str | None:
    direct = element.attrib.get(local_name)
    if direct:
        return direct
    for key, value in element.attrib.items():
        if xml_local_name(key) == local_name:
            return value
    return None


def office_mime_type(source_path: Path) -> str:
    return OOXML_MIME_TYPES.get(source_path.suffix.lower()) or mimetypes.guess_type(str(source_path))[0] or "text/plain"


def parse_xml_payload(source_path: Path, member_name: str, payload: bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise OfficeCommandError(
            category="invalid_request",
            error_code="office_document_parse_failed",
            message=f"failed to parse document payload: {source_path.name}:{member_name}",
            retryable=False,
            details={"source_path": str(source_path), "member_name": member_name},
        ) from exc


def parse_zip_document(source_path: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(source_path)
    except zipfile.BadZipFile as exc:
        raise OfficeCommandError(
            category="invalid_request",
            error_code="office_document_parse_failed",
            message=f"unsupported or corrupted Office document: {source_path}",
            retryable=False,
            details={"source_path": str(source_path)},
        ) from exc


def normalize_document_lines(lines: list[str]) -> str:
    normalized: list[str] = []
    for line in lines:
        candidate = collapse_whitespace(line)
        if candidate:
            normalized.append(candidate)
    return "\n".join(normalized)


def parse_docx_paragraphs(root: ElementTree.Element) -> list[str]:
    paragraphs: list[str] = []
    for paragraph in root.iter():
        if xml_local_name(paragraph.tag) != "p":
            continue
        fragments: list[str] = []
        for node in paragraph.iter():
            local_name = xml_local_name(node.tag)
            if local_name == "t" and node.text:
                fragments.append(node.text)
            elif local_name == "tab":
                fragments.append("\t")
            elif local_name in {"br", "cr"}:
                fragments.append("\n")
        text = normalize_document_lines("".join(fragments).splitlines())
        if text:
            paragraphs.append(text)
    return paragraphs


def parse_docx_document(source_path: Path) -> tuple[str, str]:
    with parse_zip_document(source_path) as archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names:
            raise OfficeCommandError(
                category="invalid_request",
                error_code="office_document_parse_failed",
                message=f"missing word/document.xml in Office document: {source_path}",
                retryable=False,
                details={"source_path": str(source_path)},
            )
        ordered_parts = [
            "word/document.xml",
            *sorted(name for name in names if name.startswith("word/header") and name.endswith(".xml")),
            *sorted(name for name in names if name.startswith("word/footer") and name.endswith(".xml")),
        ]
        blocks: list[str] = []
        for member_name in ordered_parts:
            paragraphs = parse_docx_paragraphs(
                parse_xml_payload(source_path, member_name, archive.read(member_name))
            )
            if paragraphs:
                blocks.append("\n".join(paragraphs))
    text_content = "\n\n".join(blocks).strip()
    return infer_title(source_path, text_content), text_content


def join_zip_path(base_name: str, target: str) -> str:
    return str(PurePosixPath(base_name).parent.joinpath(target).as_posix())


def load_xlsx_shared_strings(
    source_path: Path,
    archive: zipfile.ZipFile,
) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = parse_xml_payload(source_path, "xl/sharedStrings.xml", archive.read("xl/sharedStrings.xml"))
    shared_strings: list[str] = []
    for item in root.iter():
        if xml_local_name(item.tag) != "si":
            continue
        fragments = [text for node in item.iter() if xml_local_name(node.tag) == "t" and (text := node.text)]
        shared_strings.append(collapse_whitespace("".join(fragments)))
    return shared_strings


def load_xlsx_sheet_specs(
    source_path: Path,
    archive: zipfile.ZipFile,
) -> list[tuple[str, str]]:
    workbook_name = "xl/workbook.xml"
    if workbook_name not in archive.namelist():
        return []
    workbook_root = parse_xml_payload(source_path, workbook_name, archive.read(workbook_name))
    rel_name = "xl/_rels/workbook.xml.rels"
    relationship_targets: dict[str, str] = {}
    if rel_name in archive.namelist():
        rel_root = parse_xml_payload(source_path, rel_name, archive.read(rel_name))
        for relationship in rel_root.iter():
            if xml_local_name(relationship.tag) != "Relationship":
                continue
            rel_id = xml_attr(relationship, "Id")
            target = xml_attr(relationship, "Target")
            if rel_id and target:
                relationship_targets[rel_id] = join_zip_path(workbook_name, target)

    sheets: list[tuple[str, str]] = []
    for index, sheet in enumerate(
        item for item in workbook_root.iter() if xml_local_name(item.tag) == "sheet"
    ):
        name = xml_attr(sheet, "name") or f"Sheet{index + 1}"
        rel_id = xml_attr(sheet, "id")
        member_name = relationship_targets.get(rel_id or "")
        if member_name:
            sheets.append((name, member_name))
    if sheets:
        return sheets

    fallback_members = sorted(
        name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    return [(f"Sheet{index + 1}", member_name) for index, member_name in enumerate(fallback_members)]


def xlsx_cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = xml_attr(cell, "t") or ""
    value_text = None
    formula_text = None
    inline_fragments: list[str] = []

    for node in cell:
        local_name = xml_local_name(node.tag)
        if local_name == "v" and node.text is not None:
            value_text = node.text
        elif local_name == "f" and node.text is not None:
            formula_text = node.text
        elif local_name == "is":
            inline_fragments.extend(
                text for text_node in node.iter() if xml_local_name(text_node.tag) == "t" and (text := text_node.text)
            )

    if cell_type == "s" and value_text is not None:
        try:
            index = int(value_text)
        except ValueError:
            return collapse_whitespace(value_text)
        if 0 <= index < len(shared_strings):
            return shared_strings[index]
        return str(index)
    if cell_type == "inlineStr":
        return collapse_whitespace("".join(inline_fragments))
    if cell_type == "b" and value_text is not None:
        return "TRUE" if value_text == "1" else "FALSE"
    if value_text is not None:
        return collapse_whitespace(value_text)
    if formula_text is not None:
        return f"={collapse_whitespace(formula_text)}"
    return collapse_whitespace("".join(inline_fragments))


def parse_xlsx_sheet_rows(root: ElementTree.Element, shared_strings: list[str]) -> list[str]:
    rows: list[str] = []
    for row in root.iter():
        if xml_local_name(row.tag) != "row":
            continue
        values: list[str] = []
        for cell in row:
            if xml_local_name(cell.tag) != "c":
                continue
            value = xlsx_cell_text(cell, shared_strings)
            if value:
                values.append(value)
        if values:
            rows.append("\t".join(values))
    return rows


def parse_xlsx_document(source_path: Path) -> tuple[str, str]:
    with parse_zip_document(source_path) as archive:
        shared_strings = load_xlsx_shared_strings(source_path, archive)
        sheet_specs = load_xlsx_sheet_specs(source_path, archive)
        blocks: list[str] = []
        for sheet_name, member_name in sheet_specs:
            if member_name not in archive.namelist():
                continue
            rows = parse_xlsx_sheet_rows(
                parse_xml_payload(source_path, member_name, archive.read(member_name)),
                shared_strings,
            )
            if rows:
                blocks.append("\n".join([f"[工作表] {sheet_name}", *rows]))
    text_content = "\n\n".join(blocks).strip()
    title = blocks[0].splitlines()[0].replace("[工作表] ", "", 1) if blocks else source_path.stem
    return title, text_content


def slide_sort_key(member_name: str) -> tuple[int, str]:
    digits = "".join(character for character in Path(member_name).stem if character.isdigit())
    if digits:
        return int(digits), member_name
    return 0, member_name


def parse_pptx_document(source_path: Path) -> tuple[str, str]:
    with parse_zip_document(source_path) as archive:
        slide_members = sorted(
            (
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ),
            key=slide_sort_key,
        )
        blocks: list[str] = []
        title: str | None = None
        for index, member_name in enumerate(slide_members, start=1):
            root = parse_xml_payload(source_path, member_name, archive.read(member_name))
            texts = [
                collapse_whitespace(node.text or "")
                for node in root.iter()
                if xml_local_name(node.tag) == "t" and collapse_whitespace(node.text or "")
            ]
            if texts:
                title = title or texts[0]
                blocks.append("\n".join([f"[幻灯片 {index}]", *texts]))
    text_content = "\n\n".join(blocks).strip()
    return title or infer_title(source_path, text_content), text_content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS office compat provider baseline runtime")
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

    open_parser = subparsers.add_parser("open")
    open_parser.add_argument("--path", type=Path, required=True)
    open_parser.add_argument("--endpoint")
    open_parser.add_argument("--provider-ref")
    open_parser.add_argument("--preview-chars", type=int, default=240)
    open_parser.add_argument("--audit-log", type=Path)
    open_parser.add_argument("--remote-registry", type=Path)
    add_policy_args(open_parser)

    export_parser = subparsers.add_parser("export-pdf")
    export_parser.add_argument("--path", type=Path, required=True)
    export_parser.add_argument("--output-path", type=Path, required=True)
    export_parser.add_argument("--endpoint")
    export_parser.add_argument("--provider-ref")
    export_parser.add_argument("--audit-log", type=Path)
    export_parser.add_argument("--remote-registry", type=Path)
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
            endpoint=args.endpoint,
            provider_ref=args.provider_ref,
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
            endpoint=args.endpoint,
            provider_ref=args.provider_ref,
            preview_chars=None,
            started_at=started_at,
        )
    return OfficeContext(
        command=args.command,
        operation=None,
        capability_id=None,
        source_path=None,
        output_path=None,
        endpoint=None,
        provider_ref=None,
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


def load_office_remote_registry(
    args: argparse.Namespace | None = None,
) -> tuple[Path, list[RemoteRegistration]]:
    return load_remote_registry(
        explicit=getattr(args, "remote_registry", None) if args is not None else None,
        env_var=DEFAULT_REMOTE_REGISTRY_ENV,
        state_subdir="compat-office",
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


def office_trust_policy() -> dict[str, object]:
    return resolve_trust_policy(
        mode_env=DEFAULT_TRUST_MODE_ENV,
        allowlist_env=DEFAULT_ALLOWLIST_ENV,
        default_mode="permissive",
    )


def office_remote_attestation(args: argparse.Namespace) -> RemoteAttestation:
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
        or f"attestation://compat-office/{args.provider_ref}"
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


def office_remote_governance(args: argparse.Namespace) -> RemoteGovernance:
    return RemoteGovernance(
        fleet_id=(
            args.fleet_id
            or os.environ.get(DEFAULT_REMOTE_FLEET_ID_ENV)
            or "compat-office-local"
        ),
        governance_group=(
            args.governance_group
            or os.environ.get(DEFAULT_REMOTE_GOVERNANCE_GROUP_ENV)
            or "operator-audit"
        ),
        policy_group=(
            args.policy_group
            or os.environ.get(DEFAULT_REMOTE_POLICY_GROUP_ENV)
            or "compat-office-remote"
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
        raise OfficeCommandError(
            category="permission_denied",
            error_code="office_remote_provider_revoked",
            message=f"registered remote office provider is revoked: {registration.provider_ref}",
            retryable=False,
            details={
                "provider_ref": registration.provider_ref,
                "registration_status": status,
                "revoked_at": registration.revoked_at,
                "revocation_reason": registration.revocation_reason,
                "remote_registry": str(registry_path),
            },
        )
    raise OfficeCommandError(
        category="precondition_failed",
        error_code="office_remote_provider_stale",
        message=f"registered remote office provider is not active: {registration.provider_ref}",
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
    context: OfficeContext,
    args: argparse.Namespace,
) -> tuple[Path, RemoteRegistration | None]:
    path, registrations = load_office_remote_registry(args)
    match: RemoteRegistration | None = None

    if context.provider_ref:
        match = next(
            (registration for registration in registrations if registration.provider_ref == context.provider_ref),
            None,
        )
        if match is None:
            raise OfficeCommandError(
                category="precondition_failed",
                error_code="office_remote_provider_not_registered",
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
        raise OfficeCommandError(
            category="invalid_request",
            error_code="office_endpoint_registration_mismatch",
            message="endpoint does not match the registered remote office provider endpoint",
            retryable=False,
            details={
                "provider_ref": match.provider_ref,
                "registered_endpoint": match.endpoint,
                "requested_endpoint": context.endpoint,
                "remote_registry": str(path),
            },
        )

    if context.capability_id and context.capability_id not in match.capabilities:
        raise OfficeCommandError(
            category="permission_denied",
            error_code="office_capability_not_registered",
            message=f"registered remote office provider does not allow {context.capability_id}",
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
    context: OfficeContext,
    registration: RemoteRegistration | None,
) -> str | None:
    return context.endpoint or (registration.endpoint if registration is not None else None)


def build_remote_auth_headers(
    *,
    context: OfficeContext,
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
            raise OfficeCommandError(
                category="precondition_failed",
                error_code="office_remote_secret_missing",
                message=f"remote auth secret env is not set: {secret_env}",
                retryable=False,
                details={"provider_ref": registration.provider_ref, "auth_secret_env": secret_env},
            )
        effective_header = header_name or ("Authorization" if auth_mode == "bearer" else "X-AIOS-Office-Secret")
        headers[effective_header] = f"Bearer {secret}" if auth_mode == "bearer" else secret
        return headers

    if auth_mode == "execution-token":
        if not isinstance(policy_context.execution_token, dict):
            raise OfficeCommandError(
                category="precondition_failed",
                error_code="office_execution_token_missing",
                message="registered remote office provider requires execution_token auth",
                retryable=False,
                details={"provider_ref": registration.provider_ref},
            )
        token_context = policy_context.token_context or {}
        if token_context.get("capability_id") != context.capability_id:
            raise OfficeCommandError(
                category="permission_denied",
                error_code="office_execution_token_capability_mismatch",
                message="execution token capability does not match office operation",
                retryable=False,
                details={
                    "provider_ref": registration.provider_ref,
                    "expected_capability_id": context.capability_id,
                    "token_capability_id": token_context.get("capability_id"),
                },
            )
        if token_context.get("execution_location") != "sandbox":
            raise OfficeCommandError(
                category="permission_denied",
                error_code="office_execution_token_location_mismatch",
                message="execution token execution_location must be sandbox for compat office bridge",
                retryable=False,
                details={"provider_ref": registration.provider_ref},
            )
        if token_context.get("target_hash") != registration.target_hash:
            raise OfficeCommandError(
                category="permission_denied",
                error_code="office_execution_token_target_mismatch",
                message="execution token target_hash does not match registered remote office target",
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

    raise OfficeCommandError(
        category="precondition_failed",
        error_code="office_remote_auth_mode_invalid",
        message=f"unsupported remote auth mode: {auth_mode}",
        retryable=False,
        details={"provider_ref": registration.provider_ref, "auth_mode": auth_mode},
    )


def build_manifest() -> dict[str, object]:
    trust_policy = office_trust_policy()
    registry_path, registrations = load_office_remote_registry()
    summary = remote_registration_summary(registrations)
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
            "remote-register",
            "remote-list",
            "remote-heartbeat",
            "remote-revoke",
            "remote-unregister",
            "remote-control-plane-register",
            "remote-office-bridge",
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
        "notes": [
            "Baseline local document runtime is available",
            "Structured compat-office-document-v1 payloads are emitted for success and error paths",
            "Optional JSONL audit sink can be configured for machine-readable evidence",
            "Registered remote office workers can open/export documents over authenticated HTTP bridge",
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
    suffix = source_path.suffix.lower()
    mime_type = office_mime_type(source_path)

    if suffix in {".html", ".htm"} or mime_type == "text/html":
        raw_text = decode_bytes(raw_bytes)
        title, text_content = parse_html_document(source_path, raw_text)
    elif suffix == ".docx":
        title, text_content = parse_docx_document(source_path)
    elif suffix == ".xlsx":
        title, text_content = parse_xlsx_document(source_path)
    elif suffix == ".pptx":
        title, text_content = parse_pptx_document(source_path)
    else:
        raw_text = decode_bytes(raw_bytes)
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
            "path": context.source_path,
            "output_path": context.output_path,
            "endpoint": context.endpoint,
            "provider_ref": context.provider_ref,
            "preview_chars": context.preview_chars,
        },
        "document": document or build_document_info(),
        "export": export or build_export_info(),
        "remote_bridge": remote_bridge,
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
    remote_bridge: dict[str, object] | None,
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
        endpoint=context.endpoint,
        provider_ref=context.provider_ref,
        preview_chars=context.preview_chars,
        started_at=context.started_at,
    )
    result_protocol = build_result_protocol(
        status="error",
        context=error_context,
        document=None,
        export=None,
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
            "remote_provider_ref": remote_bridge.get("provider_ref"),
            "remote_auth_mode": remote_bridge.get("auth_mode"),
            "remote_endpoint": remote_bridge.get("endpoint"),
            "remote_target_hash": remote_bridge.get("target_hash"),
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
    trust_policy = office_trust_policy()
    registry_path, registrations = load_office_remote_registry()
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
        "engine": "text-document+remote-office-bridge",
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
        "notes": [
            "Structured compat-office-document-v1 payloads are enabled",
            "Centralized policy/token verification is enabled when policyd_socket + execution_token are supplied",
            "Registered remote office workers can open/export documents over authenticated HTTP bridge",
            "Remote registrations carry attestation and fleet governance metadata for control-plane promotion",
        ],
    }


def handle_list_remotes(args: argparse.Namespace) -> dict[str, object]:
    registry_path, registrations = load_office_remote_registry(args)
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
        raise OfficeCommandError(
            category="invalid_request",
            error_code="office_remote_capability_invalid",
            message=f"unsupported office remote capability: {invalid[0]}",
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
        attestation=office_remote_attestation(args),
        governance=office_remote_governance(args),
    )
    registry_path, registrations = load_office_remote_registry(args)
    updated = upsert_remote_registration(registrations, registration)
    write_remote_registry(registry_path, updated)
    return {
        "provider_id": PROVIDER_ID,
        "remote_registry": str(registry_path),
        "registration": registration.to_payload(),
        "registered_remote_count": len(updated),
    }


def handle_heartbeat_remote(args: argparse.Namespace) -> dict[str, object]:
    registry_path, registrations = load_office_remote_registry(args)
    index, registration = find_remote_registration(registrations, provider_ref=args.provider_ref)
    if index is None or registration is None:
        raise OfficeCommandError(
            category="precondition_failed",
            error_code="office_remote_provider_not_registered",
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
    registry_path, registrations = load_office_remote_registry(args)
    index, registration = find_remote_registration(registrations, provider_ref=args.provider_ref)
    if index is None or registration is None:
        raise OfficeCommandError(
            category="precondition_failed",
            error_code="office_remote_provider_not_registered",
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
    registry_path, registrations = load_office_remote_registry(args)
    updated, removed = remove_remote_registration(registrations, provider_ref=args.provider_ref)
    if removed is None:
        raise OfficeCommandError(
            category="precondition_failed",
            error_code="office_remote_provider_not_registered",
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
    descriptor["degradation_policy"] = "fallback-to-local-office-compat"
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
    registry_path, registrations = load_office_remote_registry(args)
    registration = next(
        (item for item in registrations if item.provider_ref == args.provider_ref),
        None,
    )
    if registration is None:
        raise OfficeCommandError(
            category="precondition_failed",
            error_code="office_remote_provider_not_registered",
            message=f"remote provider is not registered: {args.provider_ref}",
            retryable=False,
            details={"remote_registry": str(registry_path)},
        )
    ensure_remote_registration_usable(registration, registry_path=registry_path)
    provider_id = args.provider_id or normalize_remote_provider_id(
        "compat.office.remote",
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
            error_prefix="office",
        )
    except RemoteSupportError as exc:
        raise OfficeCommandError(
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


def encode_document_payload(document: DocumentContent) -> dict[str, object]:
    return {
        "source_name": document.source_path.name,
        "source_path": str(document.source_path),
        "mime_type": document.mime_type,
        "title": document.title,
        "size_bytes": document.size_bytes,
        "line_count": document.line_count,
        "char_count": document.char_count,
        "loaded_at": document.loaded_at,
        "text_content": document.text_content,
        "document_base64": base64.b64encode(document.source_path.read_bytes()).decode("ascii"),
    }


def handle_open(
    context: OfficeContext,
    path: Path,
    preview_chars: int,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
    args: argparse.Namespace,
) -> dict[str, object]:
    document = load_document(path)
    if context.endpoint or context.provider_ref:
        registry_path, registration = resolve_remote_registration(context, args)
        endpoint = resolve_effective_endpoint(context, registration)
        if endpoint is None:
            raise OfficeCommandError(
                category="internal",
                error_code="office_remote_context_incomplete",
                message="office remote open context is incomplete",
                retryable=False,
            )
        trust_policy = office_trust_policy()
        request_payload = {
            "provider_id": PROVIDER_ID,
            "worker_contract": WORKER_CONTRACT,
            "operation": context.operation,
            "request": {
                "capability_id": context.capability_id,
                "preview_chars": preview_chars,
                "document": encode_document_payload(document),
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
                timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                trust_policy=trust_policy,
                error_prefix="office",
                user_agent="AIOSOfficeCompat/0.3",
                extra_headers=headers,
            )
        except RemoteSupportError as exc:
            raise OfficeCommandError(
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
            raise OfficeCommandError(
                category="remote_error",
                error_code="office_remote_response_invalid",
                message="remote office worker returned a non-object response",
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
        preview = str(response.get("preview") or document.text_content[:preview_chars])
        document_payload = build_document_info(
            document=document,
            preview=preview,
            supported_export_formats=["pdf"],
        )
        document_payload["title"] = response.get("title") or document_payload["title"]
        document_payload["mime_type"] = response.get("mime_type") or document_payload["mime_type"]
        document_payload["preview"] = preview
        return build_success_payload(
            status=str(response.get("status") or "ok"),
            context=context,
            document=document_payload,
            export=None,
            remote_bridge=remote_bridge_payload(
                endpoint=endpoint,
                registration=registration,
                registry_path=registry_path,
                trust_policy=trust_policy,
                response_status=int(remote_result.get("status_code") or 200),
            ),
            extra_payload={
                "path": str(document.source_path),
                "title": document_payload["title"],
                "mime_type": document_payload["mime_type"],
                "size_bytes": document.size_bytes,
                "line_count": document.line_count,
                "char_count": document.char_count,
                "preview": preview,
                "loaded_at": document.loaded_at,
                "supported_export_formats": ["pdf"],
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
        remote_bridge=None,
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
    args: argparse.Namespace,
) -> dict[str, object]:
    document = load_document(path)
    if context.endpoint or context.provider_ref:
        registry_path, registration = resolve_remote_registration(context, args)
        endpoint = resolve_effective_endpoint(context, registration)
        if endpoint is None:
            raise OfficeCommandError(
                category="internal",
                error_code="office_remote_context_incomplete",
                message="office remote export context is incomplete",
                retryable=False,
            )
        trust_policy = office_trust_policy()
        request_payload = {
            "provider_id": PROVIDER_ID,
            "worker_contract": WORKER_CONTRACT,
            "operation": context.operation,
            "request": {
                "capability_id": context.capability_id,
                "output_format": "pdf",
                "document": encode_document_payload(document),
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
                timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                trust_policy=trust_policy,
                error_prefix="office",
                user_agent="AIOSOfficeCompat/0.3",
                extra_headers=headers,
            )
        except RemoteSupportError as exc:
            raise OfficeCommandError(
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
            raise OfficeCommandError(
                category="remote_error",
                error_code="office_remote_response_invalid",
                message="remote office worker returned a non-object response",
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
        pdf_base64 = response.get("pdf_base64")
        if not isinstance(pdf_base64, str) or not pdf_base64:
            raise OfficeCommandError(
                category="remote_error",
                error_code="office_remote_pdf_missing",
                message="remote office worker did not return pdf_base64",
                retryable=True,
                details={
                    "remote_bridge": remote_bridge_payload(
                        endpoint=endpoint,
                        registration=registration,
                        registry_path=registry_path,
                        trust_policy=trust_policy,
                        response_status=int(remote_result.get("status_code") or 200),
                    )
                },
            )
        pdf_bytes = base64.b64decode(pdf_base64.encode("ascii"))
        resolved_output = output_path.expanduser().resolve()
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_bytes(pdf_bytes)
        exported_at = str(response.get("exported_at") or utc_now())
        document_payload = build_document_info(
            document=document,
            preview=None,
            supported_export_formats=["pdf"],
        )
        export_payload = build_export_info(
            output_path=str(resolved_output),
            mime_type=str(response.get("mime_type") or "application/pdf"),
            page_count=int(response.get("page_count") or 1),
            bytes_written=len(pdf_bytes),
            exported_at=exported_at,
        )
        return build_success_payload(
            status=str(response.get("status") or "ok"),
            context=context,
            document=document_payload,
            export=export_payload,
            remote_bridge=remote_bridge_payload(
                endpoint=endpoint,
                registration=registration,
                registry_path=registry_path,
                trust_policy=trust_policy,
                response_status=int(remote_result.get("status_code") or 200),
            ),
            extra_payload={
                "source_path": str(document.source_path),
                "output_path": str(resolved_output),
                "mime_type": export_payload["mime_type"],
                "page_count": export_payload["page_count"],
                "bytes_written": len(pdf_bytes),
                "title": document.title,
                "exported_at": exported_at,
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
        remote_bridge=None,
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
                args,
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
                args,
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
