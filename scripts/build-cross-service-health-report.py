#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "cross-service-health-report"
HEALTH_EVENT_SCHEMA = ROOT / "aios" / "observability" / "schemas" / "health-event.schema.json"
HEALTH_REPORT_SCHEMA = (
    ROOT / "aios" / "observability" / "schemas" / "cross-service-health-report.schema.json"
)
CURRENT_SCHEMA_VERSION = "2026-03-13"
SOURCE_KINDS = {
    "rpc-service",
    "rpc-update",
    "provider-registry",
    "command-health",
    "delivery-artifact",
    "evidence-index",
}
COMPONENT_KINDS = {"service", "provider", "runtime", "shell", "device", "update", "platform", "hardware"}
EVENT_SUMMARY_FIELDS = {
    "provider_ids": "provider_id",
    "runtime_service_ids": "runtime_service_id",
    "provider_statuses": "provider_status",
    "backend_ids": "backend_id",
}
DEFAULT_REQUIRED_DELIVERY_KEYS = [
    "generated_at",
    "schema_version",
    "rootfs_overlay",
    "firstboot",
    "shell",
    "recovery",
    "installer",
    "schemas",
    "files",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AIOS cross-service health report")
    parser.add_argument("--spec", type=Path, required=True, help="YAML or JSON source specification")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help="Output prefix for the generated .json, .md, and .jsonl files",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Default timeout in seconds for RPC and command probes",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_document(path: Path) -> Any:
    text = path.read_text()
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False) for item in payloads]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n")


def build_validator(schema_path: Path) -> Draft202012Validator:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def rpc_call(socket_path: Path, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"RPC {method} returned non-object result")
    return result


def run_health_command(command: list[str], timeout: float) -> tuple[dict[str, Any], str]:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"returncode={completed.returncode}"
        raise RuntimeError(detail)
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("health command returned empty stdout")
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("health command must return a JSON object")
    return payload, completed.stderr.strip()


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        items.append(value)
    return items


def parse_note_map(notes: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for note in notes:
        if "=" not in note:
            continue
        key, value = note.split("=", 1)
        if key and value:
            mapping[key] = value
    return mapping


def provider_registry_rpc_method(source: dict[str, Any]) -> str:
    configured = source.get("rpc_method")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    if str(source.get("service_id") or "").strip() == "aios-agentd":
        return "agent.provider.health.get"
    return "provider.health.get"

def ensure_source_spec(source: dict[str, Any]) -> None:
    required_fields = ["source_id", "kind", "component_kind"]
    for field in required_fields:
        value = source.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"source missing required field `{field}`")
    if source["kind"] not in SOURCE_KINDS:
        raise RuntimeError(f"unsupported source kind: {source['kind']}")
    if source["component_kind"] not in COMPONENT_KINDS:
        raise RuntimeError(f"unsupported component_kind: {source['component_kind']}")

    kind_requirements = {
        "rpc-service": ["socket_path"],
        "rpc-update": ["socket_path"],
        "provider-registry": ["socket_path"],
        "command-health": ["command"],
        "delivery-artifact": ["manifest_path"],
        "evidence-index": ["index_path"],
    }
    for field in kind_requirements.get(source["kind"], []):
        if field == "command":
            command = source.get("command")
            if isinstance(command, list) and command:
                continue
            if isinstance(command, str) and command.strip():
                continue
            raise RuntimeError(f"{source['source_id']}: command-health source requires non-empty `command`")
        value = source.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"{source['source_id']}: source kind `{source['kind']}` requires `{field}`")


def sanitized_id(value: str) -> str:
    collapsed = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return collapsed.strip("-") or "item"


def normalize_status(raw_status: Any) -> str:
    value = str(raw_status or "").strip().lower()
    mapping = {
        "ready": "ready",
        "idle": "idle",
        "degraded": "degraded",
        "blocked": "blocked",
        "failed": "failed",
        "healthy": "ready",
        "warning": "degraded",
        "unhealthy": "blocked",
        "available": "ready",
        "ok": "ready",
        "success": "ready",
        "passed": "ready",
        "unavailable": "blocked",
        "disabled": "blocked",
        "error": "failed",
        "failed": "failed",
    }
    return mapping.get(value, "degraded" if value else "failed")


def readiness_for_status(status: str) -> bool:
    return status in {"ready", "idle"}


def fail_on_statuses(source: dict[str, Any]) -> set[str]:
    configured = source.get("fail_on_statuses")
    if configured is not None:
        return {normalize_status(item) for item in as_string_list(configured)}
    if source["kind"] == "provider-registry" and not source.get("provider_ids"):
        return set()
    return {"blocked", "failed"}


def source_label(source: dict[str, Any]) -> str:
    return {
        "rpc-service": "rpc",
        "rpc-update": "rpc",
        "provider-registry": "rpc",
        "command-health": "probe",
        "delivery-artifact": "operator",
        "evidence-index": "operator",
    }[source["kind"]]


def artifact_hint(source: dict[str, Any]) -> str | None:
    for key in ("artifact_path", "probe_path", "socket_path", "manifest_path", "index_path"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value
    command = source.get("command")
    if isinstance(command, list):
        for part in command:
            if isinstance(part, str) and part.endswith(".py"):
                return part
    return None


def unique_sorted_strings(values: list[str]) -> list[str]:
    return sorted(unique_strings(values))


def first_or_none(values: list[str]) -> str | None:
    return values[0] if len(values) == 1 else None


def collect_event_strings(events: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for event in events:
        value = event.get(field)
        if isinstance(value, str) and value:
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value if str(item).strip())
    return unique_sorted_strings(values)


def collect_event_summary_strings(
    events: list[dict[str, Any]],
    plural_field: str,
    singular_field: str | None = None,
) -> list[str]:
    values = collect_event_strings(events, plural_field)
    if singular_field:
        values = unique_sorted_strings(values + collect_event_strings(events, singular_field))
    return values


def evidence_index_vendor_runtime_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "provider_ids": [],
        "runtime_service_ids": [],
        "provider_statuses": [],
        "backend_ids": [],
        "artifact_paths": [],
        "vendor_runtime_signoff_status": None,
        "evidence_count": None,
    }
    device_runtime = payload.get("device_runtime")
    vendor_runtime = device_runtime.get("vendor_runtime") if isinstance(device_runtime, dict) else None
    if not isinstance(vendor_runtime, dict):
        artifacts = payload.get("artifacts")
        if isinstance(artifacts, dict):
            metadata["artifact_paths"] = unique_sorted_strings(
                as_string_list(artifacts.get("vendor_runtime_evidence"))
            )
        return metadata

    metadata["provider_ids"] = unique_sorted_strings(as_string_list(vendor_runtime.get("provider_ids")))
    metadata["runtime_service_ids"] = unique_sorted_strings(as_string_list(vendor_runtime.get("runtime_service_ids")))
    metadata["provider_statuses"] = unique_sorted_strings(as_string_list(vendor_runtime.get("provider_statuses")))
    metadata["backend_ids"] = unique_sorted_strings(as_string_list(vendor_runtime.get("backend_ids")))
    metadata["artifact_paths"] = unique_sorted_strings(
        as_string_list(vendor_runtime.get("evidence_paths"))
        + as_string_list((payload.get("artifacts") or {}).get("vendor_runtime_evidence") if isinstance(payload.get("artifacts"), dict) else None)
    )
    signoff_status = vendor_runtime.get("vendor_runtime_signoff_status")
    if isinstance(signoff_status, str) and signoff_status:
        metadata["vendor_runtime_signoff_status"] = signoff_status
    evidence_count = vendor_runtime.get("evidence_count")
    if isinstance(evidence_count, int):
        metadata["evidence_count"] = evidence_count
    elif metadata["artifact_paths"]:
        metadata["evidence_count"] = len(metadata["artifact_paths"])
    return metadata


def base_event(source: dict[str, Any], service_id: str, component_id: str | None = None) -> dict[str, Any]:
    event = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "service_id": service_id,
        "component_kind": source["component_kind"],
        "source": source_label(source),
    }
    if component_id:
        event["component_id"] = component_id
    for field in (
        "session_id",
        "task_id",
        "provider_id",
        "approval_id",
        "update_id",
        "boot_id",
        "image_id",
    ):
        value = source.get(field)
        if isinstance(value, str) and value.strip():
            event[field] = value
    hint = artifact_hint(source)
    if hint:
        event["artifact_path"] = hint
    source_notes = as_string_list(source.get("notes"))
    if source_notes:
        event["notes"] = source_notes
    return event


def finalize_event(
    source: dict[str, Any],
    event: dict[str, Any],
    index: int,
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    finalized = dict(event)
    finalized.setdefault(
        "event_id",
        f"health-{sanitized_id(source['source_id'])}-{index:02d}-{sanitized_id(str(finalized.get('component_id') or finalized.get('service_id') or 'event'))}",
    )
    finalized["generated_at"] = str(finalized.get("generated_at") or now_iso())
    finalized["schema_version"] = CURRENT_SCHEMA_VERSION
    finalized["notes"] = unique_strings(
        as_string_list(finalized.get("notes")) + as_string_list(extra_notes)
    )
    return finalized


def failure_event(source: dict[str, Any], detail: str) -> dict[str, Any]:
    service_id = str(source.get("service_id") or source["source_id"])
    event = base_event(source, service_id, source.get("component_id"))
    event.update(
        {
            "overall_status": "failed",
            "readiness": False,
            "summary": detail,
        }
    )
    return finalize_event(
        source,
        event,
        1,
        extra_notes=[f"collection_error={detail}"],
    )


def event_artifact_paths(events: list[dict[str, Any]]) -> list[str]:
    artifact_paths: list[str] = []
    for event in events:
        hint = event.get("artifact_path")
        if isinstance(hint, str) and hint:
            artifact_paths.append(hint)
        artifact_paths.extend(as_string_list(event.get("artifact_paths")))
        artifact_paths.extend(as_string_list(event.get("recovery_points")))
        artifact_paths.extend(as_string_list(event.get("diagnostic_bundles")))
    return unique_sorted_strings(artifact_paths)


def collect_rpc_service(source: dict[str, Any], timeout: float) -> tuple[list[dict[str, Any]], str, list[str]]:
    socket_path = Path(source["socket_path"])
    payload = rpc_call(socket_path, "system.health.get", {}, timeout)
    raw_notes = as_string_list(payload.get("notes"))
    event = base_event(
        source,
        str(payload.get("service_id") or source.get("service_id") or source["source_id"]),
        source.get("component_id"),
    )
    normalized = normalize_status(payload.get("status"))
    event.update(
        {
            "overall_status": normalized,
            "readiness": readiness_for_status(normalized),
            "summary": f"system.health.get status={payload.get('status', '<missing>')}",
            "artifact_path": str(source.get("artifact_path") or payload.get("socket_path") or socket_path),
        }
    )
    notes = raw_notes + [
        f"reported_status={payload.get('status', '<missing>')}",
        f"service_version={payload.get('version', '<missing>')}",
    ]
    if payload.get("started_at"):
        notes.append(f"service_started_at={payload['started_at']}")
    return [finalize_event(source, event, 1, extra_notes=notes)], "queried system.health.get", []


def collect_rpc_update(source: dict[str, Any], timeout: float) -> tuple[list[dict[str, Any]], str, list[str]]:
    socket_path = Path(source["socket_path"])
    system_payload = rpc_call(socket_path, "system.health.get", {}, timeout)
    update_payload = rpc_call(socket_path, "update.health.get", {}, timeout)
    system_notes = as_string_list(system_payload.get("notes"))
    note_lookup = parse_note_map(system_notes)
    probe_path = str(source.get("probe_path") or note_lookup.get("health_probe_path") or "")
    probe_payload: dict[str, Any] | None = None
    if probe_path:
        candidate = Path(probe_path)
        if candidate.exists():
            parsed = load_json(candidate)
            if isinstance(parsed, dict):
                probe_payload = parsed

    event = base_event(
        source,
        str(update_payload.get("service_id") or system_payload.get("service_id") or source.get("service_id") or source["source_id"]),
        source.get("component_id"),
    )
    normalized = normalize_status(update_payload.get("overall_status") or system_payload.get("status"))
    event.update(
        {
            "overall_status": normalized,
            "readiness": readiness_for_status(normalized),
            "last_check_at": update_payload.get("last_check_at"),
            "summary": f"update.health.get overall_status={update_payload.get('overall_status', '<missing>')}",
            "recovery_points": as_string_list(update_payload.get("recovery_points")),
            "diagnostic_bundles": as_string_list(update_payload.get("diagnostic_bundles")),
            "artifact_path": probe_path or str(source.get("artifact_path") or system_payload.get("socket_path") or socket_path),
        }
    )
    if probe_payload is not None:
        event["probe"] = {
            "status": probe_payload.get("overall_status"),
            "checked_at": update_payload.get("last_check_at"),
            "command": source.get("probe_command"),
            "summary": probe_payload.get("summary"),
        }
    notes = system_notes + as_string_list(update_payload.get("notes")) + [
        f"system_status={system_payload.get('status', '<missing>')}",
        f"rollback_ready={update_payload.get('rollback_ready', False)}",
    ]
    return [finalize_event(source, event, 1, extra_notes=notes)], "queried system.health.get and update.health.get", []


def provider_event(
    source: dict[str, Any],
    socket_path: Path,
    provider_payload: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    normalized = normalize_status(provider_payload.get("status"))
    if provider_payload.get("disabled"):
        normalized = "blocked"
    elif provider_payload.get("circuit_open"):
        normalized = "blocked"
    elif provider_payload.get("resource_pressure") and normalized == "ready":
        normalized = "degraded"

    event = base_event(
        source,
        str(source.get("service_id") or "aios-agentd"),
        str(provider_payload.get("provider_id") or source.get("component_id") or source["source_id"]),
    )
    provider_id = str(provider_payload.get("provider_id") or source.get("provider_id") or "")
    if provider_id:
        event["provider_id"] = provider_id
    event.update(
        {
            "overall_status": normalized,
            "readiness": readiness_for_status(normalized),
            "last_check_at": provider_payload.get("last_checked_at"),
            "summary": f"{provider_registry_rpc_method(source)} status={provider_payload.get('status', '<missing>')}",
            "artifact_path": str(source.get("artifact_path") or socket_path),
        }
    )
    notes = [
        f"disabled={provider_payload.get('disabled', False)}",
        f"circuit_open={provider_payload.get('circuit_open', False)}",
    ]
    if provider_payload.get("resource_pressure"):
        notes.append(f"resource_pressure={provider_payload['resource_pressure']}")
    if provider_payload.get("last_error"):
        notes.append(f"last_error={provider_payload['last_error']}")
    return finalize_event(source, event, index, extra_notes=notes)


def collect_provider_registry(source: dict[str, Any], timeout: float) -> tuple[list[dict[str, Any]], str, list[str]]:
    socket_path = Path(source["socket_path"])
    provider_ids = as_string_list(source.get("provider_ids"))
    method = provider_registry_rpc_method(source)
    warnings: list[str] = []
    events: list[dict[str, Any]] = []

    if provider_ids:
        for index, provider_id in enumerate(provider_ids, start=1):
            payload = rpc_call(socket_path, method, {"provider_id": provider_id}, timeout)
            providers = payload.get("providers")
            if not isinstance(providers, list) or not providers:
                raise RuntimeError(f"{method} missing provider `{provider_id}`")
            provider_payload = providers[0]
            if not isinstance(provider_payload, dict):
                raise RuntimeError(f"{method} returned malformed record for `{provider_id}`")
            events.append(provider_event(source, socket_path, provider_payload, index))
        return events, f"queried {method} for required providers", warnings

    payload = rpc_call(socket_path, method, {}, timeout)
    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        raise RuntimeError(f"{method} returned no providers")
    for index, provider_payload in enumerate(providers, start=1):
        if not isinstance(provider_payload, dict):
            raise RuntimeError(f"{method} returned malformed provider record")
        events.append(provider_event(source, socket_path, provider_payload, index))
    warnings.append("provider-registry source exported every registered provider")
    return events, f"queried {method}", warnings

def collect_command_health(source: dict[str, Any], timeout: float) -> tuple[list[dict[str, Any]], str, list[str]]:
    command_value = source["command"]
    command = (
        [str(item) for item in command_value]
        if isinstance(command_value, list)
        else shlex.split(str(command_value))
    )
    payload, stderr = run_health_command(command, timeout)
    service_id = str(
        payload.get("service_id")
        or source.get("service_id")
        or payload.get("provider_id")
        or source["source_id"]
    )
    component_id = str(
        source.get("component_id")
        or payload.get("provider_id")
        or source.get("provider_id")
        or service_id
    )
    event = base_event(source, service_id, component_id)
    normalized = normalize_status(payload.get("status"))
    provider_id = str(payload.get("provider_id") or source.get("provider_id") or "")
    if provider_id:
        event["provider_id"] = provider_id
    event.update(
        {
            "overall_status": normalized,
            "readiness": readiness_for_status(normalized),
            "summary": f"health command status={payload.get('status', '<missing>')}",
            "artifact_path": str(source.get("artifact_path") or payload.get("audit_log_path") or artifact_hint(source) or command[0]),
        }
    )
    notes = as_string_list(payload.get("notes"))
    for key in ("engine", "execution_location", "network_access", "subprocess_access"):
        value = payload.get(key)
        if value not in (None, ""):
            notes.append(f"{key}={value}")
    if stderr:
        notes.append(f"stderr={stderr}")
    notes.append(f"command={' '.join(command)}")
    return [finalize_event(source, event, 1, extra_notes=notes)], "executed command health probe", []


def collect_delivery_artifact(source: dict[str, Any], _timeout: float) -> tuple[list[dict[str, Any]], str, list[str]]:
    manifest_path = Path(source["manifest_path"])
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise RuntimeError("delivery manifest must be a JSON object")

    required_keys = as_string_list(source.get("required_keys")) or DEFAULT_REQUIRED_DELIVERY_KEYS
    missing = [key for key in required_keys if key not in manifest]
    normalized = "ready" if not missing else "blocked"
    event = base_event(
        source,
        str(source.get("service_id") or "aios-system-delivery"),
        source.get("component_id"),
    )
    detail = "delivery manifest contains required sections" if not missing else f"missing manifest keys: {', '.join(missing)}"
    event.update(
        {
            "overall_status": normalized,
            "readiness": not missing,
            "last_check_at": manifest.get("generated_at"),
            "summary": detail,
            "artifact_path": str(manifest_path),
        }
    )
    event["image_id"] = str(source.get("image_id") or manifest.get("bundle_name") or source["source_id"])
    notes = [
        f"bundle_name={manifest.get('bundle_name', '<missing>')}",
        f"schema_version={manifest.get('schema_version', '<missing>')}",
        f"components={len(manifest.get('components', []))}",
        f"files={len(manifest.get('files', []))}",
    ]
    return [finalize_event(source, event, 1, extra_notes=notes)], detail, []


def collect_evidence_index(source: dict[str, Any], _timeout: float) -> tuple[list[dict[str, Any]], str, list[str]]:
    index_path = Path(source["index_path"])
    payload = load_json(index_path)
    if not isinstance(payload, dict):
        raise RuntimeError("evidence index must be a JSON object")

    status_field = "validation_status"
    raw_status = payload.get("validation_status")
    if raw_status in (None, ""):
        raw_status = payload.get("overall_status")
        status_field = "overall_status"
    if raw_status in (None, ""):
        raw_status = payload.get("status")
        status_field = "status"
    normalized = normalize_status(raw_status)

    component_id = (
        source.get("component_id")
        or payload.get("platform_id")
        or payload.get("index_id")
        or payload.get("component_id")
    )
    service_id = str(
        payload.get("service_id")
        or source.get("service_id")
        or source["source_id"]
    )
    event = base_event(
        source,
        service_id,
        None if component_id in (None, "") else str(component_id),
    )
    summary = (
        f"evidence index {status_field}={raw_status}"
        if raw_status not in (None, "")
        else "evidence index status missing"
    )
    vendor_runtime = evidence_index_vendor_runtime_metadata(payload)
    related_artifact_paths = unique_sorted_strings([str(index_path), *vendor_runtime["artifact_paths"]])
    event.update(
        {
            "overall_status": normalized,
            "readiness": readiness_for_status(normalized),
            "last_check_at": payload.get("generated_at") or payload.get("evaluated_at"),
            "summary": summary,
            "artifact_path": str(index_path),
            "artifact_paths": related_artifact_paths,
        }
    )
    if vendor_runtime["provider_ids"]:
        event["provider_ids"] = vendor_runtime["provider_ids"]
        provider_id = first_or_none(vendor_runtime["provider_ids"])
        if provider_id:
            event["provider_id"] = provider_id
    if vendor_runtime["runtime_service_ids"]:
        event["runtime_service_ids"] = vendor_runtime["runtime_service_ids"]
        runtime_service_id = first_or_none(vendor_runtime["runtime_service_ids"])
        if runtime_service_id:
            event["runtime_service_id"] = runtime_service_id
    if vendor_runtime["provider_statuses"]:
        event["provider_statuses"] = vendor_runtime["provider_statuses"]
        provider_status = first_or_none(vendor_runtime["provider_statuses"])
        if provider_status:
            event["provider_status"] = provider_status
    if vendor_runtime["backend_ids"]:
        event["backend_ids"] = vendor_runtime["backend_ids"]
        backend_id = first_or_none(vendor_runtime["backend_ids"])
        if backend_id:
            event["backend_id"] = backend_id
    if vendor_runtime["vendor_runtime_signoff_status"]:
        event["vendor_runtime_signoff_status"] = vendor_runtime["vendor_runtime_signoff_status"]
    if vendor_runtime["evidence_count"] is not None:
        event["evidence_count"] = vendor_runtime["evidence_count"]

    notes = as_string_list(payload.get("notes"))
    for key in ("validation_kind", "validation_status", "overall_status", "status", "platform_id", "index_id"):
        value = payload.get(key)
        if value not in (None, ""):
            notes.append(f"{key}={value}")
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        for artifact_name, artifact_value in artifacts.items():
            if artifact_value not in (None, ""):
                notes.append(f"artifact_{artifact_name}={artifact_value}")
    if vendor_runtime["vendor_runtime_signoff_status"]:
        notes.append(f"vendor_runtime_signoff_status={vendor_runtime['vendor_runtime_signoff_status']}")
    if vendor_runtime["evidence_count"] is not None:
        notes.append(f"vendor_runtime_evidence_count={vendor_runtime['evidence_count']}")
    if vendor_runtime["provider_ids"]:
        notes.append(f"vendor_runtime_provider_ids={','.join(vendor_runtime['provider_ids'])}")
    if vendor_runtime["runtime_service_ids"]:
        notes.append(f"vendor_runtime_service_ids={','.join(vendor_runtime['runtime_service_ids'])}")
    if vendor_runtime["provider_statuses"]:
        notes.append(f"vendor_runtime_statuses={','.join(vendor_runtime['provider_statuses'])}")
    if vendor_runtime["backend_ids"]:
        notes.append(f"vendor_runtime_backend_ids={','.join(vendor_runtime['backend_ids'])}")
    return [finalize_event(source, event, 1, extra_notes=notes)], summary, []


def summarize_check(
    source: dict[str, Any],
    events: list[dict[str, Any]],
    detail: str,
    warnings: list[str],
    force_failed: bool = False,
) -> dict[str, Any]:
    health_statuses = sorted({str(event.get("overall_status")) for event in events if event.get("overall_status")})
    failed_statuses = sorted(status for status in health_statuses if status in fail_on_statuses(source))
    status = "failed" if force_failed or failed_statuses else "passed"
    summary = {
        "check_id": source["source_id"],
        "summary": str(source.get("summary") or f"{source['kind']} export for {source['source_id']}"),
        "status": status,
        "source_kind": source["kind"],
        "target": target_label(source),
        "component_kind": source["component_kind"],
        "event_count": len(events),
        "health_statuses": health_statuses,
        "service_ids": sorted({str(event.get("service_id")) for event in events if event.get("service_id")}),
        "artifact_paths": event_artifact_paths(events),
        "detail": detail,
        "notes": unique_strings(warnings),
    }
    for field, singular_field in EVENT_SUMMARY_FIELDS.items():
        summary[field] = collect_event_summary_strings(events, field, singular_field)
    return summary


def target_label(source: dict[str, Any]) -> str:
    if source["kind"] == "rpc-service":
        return f"system.health.get via {source['socket_path']}"
    if source["kind"] == "rpc-update":
        return f"system.health.get + update.health.get via {source['socket_path']}"
    if source["kind"] == "provider-registry":
        return f"{provider_registry_rpc_method(source)} via {source['socket_path']}"
    if source["kind"] == "command-health":
        command_value = source["command"]
        command = (
            [str(item) for item in command_value]
            if isinstance(command_value, list)
            else shlex.split(str(command_value))
        )
        return "command " + " ".join(command)
    if source["kind"] == "evidence-index":
        return f"evidence index {source['index_path']}"
    return f"manifest {source['manifest_path']}"


def collect_source(
    source: dict[str, Any],
    timeout: float,
    event_validator: Draft202012Validator,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    kind = source["kind"]
    warnings: list[str] = []
    try:
        if kind == "rpc-service":
            events, detail, warnings = collect_rpc_service(source, timeout)
        elif kind == "rpc-update":
            events, detail, warnings = collect_rpc_update(source, timeout)
        elif kind == "provider-registry":
            events, detail, warnings = collect_provider_registry(source, timeout)
        elif kind == "command-health":
            events, detail, warnings = collect_command_health(source, timeout)
        elif kind == "delivery-artifact":
            events, detail, warnings = collect_delivery_artifact(source, timeout)
        elif kind == "evidence-index":
            events, detail, warnings = collect_evidence_index(source, timeout)
        else:  # pragma: no cover - guarded by ensure_source_spec
            raise RuntimeError(f"unsupported source kind `{kind}`")

        for event in events:
            event_validator.validate(event)
        return summarize_check(source, events, detail, warnings), events, warnings
    except Exception as exc:  # noqa: BLE001
        failure = failure_event(source, str(exc))
        event_validator.validate(failure)
        detail = f"collection failed: {exc}"
        warnings.append(detail)
        return summarize_check(source, [failure], detail, warnings, force_failed=True), [failure], warnings


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Cross-Service Health Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- JSON report: `{report['json_report']}`",
        f"- Markdown report: `{report['markdown_report']}`",
        f"- Events JSONL: `{report['events_jsonl']}`",
        "",
        "## Summary",
        "",
        f"- Sources: `{report['summary']['source_count']}`",
        f"- Passed sources: `{report['summary']['passed_count']}`",
        f"- Failed sources: `{report['summary']['failed_count']}`",
        f"- Events: `{report['summary']['event_count']}`",
        f"- Component kinds: `{', '.join(report['summary']['component_kinds']) or '-'}`",
        f"- Services: `{', '.join(report['summary']['service_ids']) or '-'}`",
        f"- Providers: `{', '.join(report['summary'].get('provider_ids', [])) or '-'}`",
        f"- Runtime services: `{', '.join(report['summary'].get('runtime_service_ids', [])) or '-'}`",
        f"- Provider statuses: `{', '.join(report['summary'].get('provider_statuses', [])) or '-'}`",
        f"- Backend ids: `{', '.join(report['summary'].get('backend_ids', [])) or '-'}`",
        f"- Health statuses: `{', '.join(report['summary']['overall_statuses']) or '-'}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Kind | Component | Events | Health | Providers | Detail |",
        "|-------|--------|------|-----------|--------|--------|-----------|--------|",
    ]
    for item in report["checks"]:
        lines.append(
            "| `{check_id}` | `{status}` | `{source_kind}` | `{component_kind}` | `{event_count}` | `{health}` | `{providers}` | {detail} |".format(
                check_id=item["check_id"],
                status=item["status"],
                source_kind=item["source_kind"],
                component_kind=item["component_kind"],
                event_count=item["event_count"],
                health=", ".join(item["health_statuses"]) or "-",
                providers=", ".join(item.get("provider_ids", [])) or "-",
                detail=item["detail"],
            )
        )

    lines.extend(
        [
            "",
            "## Events",
            "",
            "| Service | Component | Status | Provider | Runtime Service | Backend | Artifact |",
            "|---------|-----------|--------|----------|-----------------|---------|----------|",
        ]
    )
    for event in report["events"]:
        lines.append(
            "| `{service_id}` | `{component}` | `{status}` | `{provider}` | `{runtime_service}` | `{backend}` | `{artifact}` |".format(
                service_id=event.get("service_id", "<missing>"),
                component=event.get("component_kind", "<missing>"),
                status=event.get("overall_status", "<missing>"),
                provider=event.get("provider_id") or ", ".join(as_string_list(event.get("provider_ids"))) or "-",
                runtime_service=event.get("runtime_service_id") or ", ".join(as_string_list(event.get("runtime_service_ids"))) or "-",
                backend=event.get("backend_id") or ", ".join(as_string_list(event.get("backend_ids"))) or "-",
                artifact=event.get("artifact_path", "-"),
            )
        )
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    spec_payload = load_document(args.spec)
    if not isinstance(spec_payload, dict):
        raise SystemExit("spec must decode to a mapping")
    sources = spec_payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SystemExit("spec must contain a non-empty `sources` list")

    event_validator = build_validator(HEALTH_EVENT_SCHEMA)
    report_validator = build_validator(HEALTH_REPORT_SCHEMA)

    checks: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    warnings: list[str] = []

    for raw_source in sources:
        if not isinstance(raw_source, dict):
            raise SystemExit("every source entry must be a mapping")
        ensure_source_spec(raw_source)
        timeout = float(raw_source.get("timeout_seconds") or args.timeout)
        check, source_events, source_warnings = collect_source(raw_source, timeout, event_validator)
        checks.append(check)
        events.extend(source_events)
        warnings.extend(source_warnings)

    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    events_jsonl_path = (
        args.output_prefix.parent
        / args.output_prefix.name.replace("-report", "-events")
    ).with_suffix(".jsonl")

    failed_checks = [item["check_id"] for item in checks if item["status"] != "passed"]
    report = {
        "report_id": f"health-report-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generated_at": now_iso(),
        "workspace": str(ROOT),
        "overall_status": "failed" if failed_checks else "passed",
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "events_jsonl": str(events_jsonl_path),
        "summary": {
            "source_count": len(checks),
            "passed_count": len([item for item in checks if item["status"] == "passed"]),
            "failed_count": len(failed_checks),
            "event_count": len(events),
            "component_kinds": sorted({item["component_kind"] for item in checks}),
            "service_ids": sorted({str(event.get("service_id")) for event in events if event.get("service_id")}),
            "provider_ids": collect_event_summary_strings(events, "provider_ids", "provider_id"),
            "runtime_service_ids": collect_event_summary_strings(events, "runtime_service_ids", "runtime_service_id"),
            "provider_statuses": collect_event_summary_strings(events, "provider_statuses", "provider_status"),
            "backend_ids": collect_event_summary_strings(events, "backend_ids", "backend_id"),
            "overall_statuses": sorted({str(event.get("overall_status")) for event in events if event.get("overall_status")}),
            "failed_checks": failed_checks,
            "artifact_paths": event_artifact_paths(events),
        },
        "checks": checks,
        "events": events,
        "warnings": unique_strings(warnings),
    }

    report_validator.validate(report)
    write_json(json_path, report)
    write_jsonl(events_jsonl_path, events)
    write_markdown(markdown_path, render_markdown(report))
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "events_jsonl": str(events_jsonl_path),
                "failed_checks": failed_checks,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if failed_checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
