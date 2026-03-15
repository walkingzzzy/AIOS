#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


FILTER_FIELDS = {
    "source",
    "severity",
    "fleet_id",
    "governance_group",
    "status",
    "provider_ref",
    "provider_id",
    "attestation_mode",
    "control_plane_status",
    "approval_ref",
    "text",
}

SEVERITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "info": 1,
}
STATUS_ORDER = {
    "revoked": 3,
    "stale": 2,
    "active": 1,
    "missing": 0,
    "unknown": 0,
}


def default_browser_remote_registry() -> Path:
    return Path(
        os.environ.get(
            "AIOS_BROWSER_REMOTE_REGISTRY",
            str(Path.home() / ".local" / "state" / "aios" / "compat-browser" / "remote-registry.json"),
        )
    )


def default_office_remote_registry() -> Path:
    return Path(
        os.environ.get(
            "AIOS_OFFICE_REMOTE_REGISTRY",
            str(Path.home() / ".local" / "state" / "aios" / "compat-office" / "remote-registry.json"),
        )
    )


def default_provider_registry_state_dir() -> Path:
    return Path(
        os.environ.get(
            "AIOS_AGENTD_PROVIDER_REGISTRY_STATE_DIR",
            "/var/lib/aios/registry",
        )
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_rfc3339(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_json(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def remote_registration_status(payload: dict) -> str:
    current = optional_text(payload.get("registration_status")) or "active"
    current = current.lower()
    if optional_text(payload.get("revoked_at")) or current == "revoked":
        return "revoked"
    ttl = optional_int(payload.get("heartbeat_ttl_seconds"))
    if ttl is not None and ttl > 0:
        heartbeat = parse_rfc3339(optional_text(payload.get("last_heartbeat_at"))) or parse_rfc3339(
            optional_text(payload.get("registered_at"))
        )
        if heartbeat is None:
            return "stale"
        if (datetime.now(timezone.utc) - heartbeat).total_seconds() > ttl:
            return "stale"
    return current or "unknown"


def infer_source(remote_registration: dict, provider_id: str | None) -> str:
    source_provider_id = optional_text(remote_registration.get("source_provider_id"))
    haystack = " ".join(
        value
        for value in (
            source_provider_id,
            provider_id,
            optional_text(remote_registration.get("provider_ref")),
        )
        if value
    ).lower()
    if "office" in haystack:
        return "office"
    if "browser" in haystack:
        return "browser"
    return "compat"


def load_remote_registry(path: Path, source: str) -> list[dict]:
    payload = load_json(path) or {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return []
    registrations: list[dict] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        registrations.append({"source": source, "registry_path": str(path), "registration": dict(item)})
    return registrations


def load_provider_registry(state_dir: Path) -> dict[str, object]:
    descriptors_dir = state_dir / "descriptors"
    health_dir = state_dir / "health"
    descriptors: dict[str, dict] = {}
    descriptor_paths: dict[str, str] = {}
    remote_lookup: dict[tuple[str, str], str] = {}
    if descriptors_dir.exists():
        for path in sorted(descriptors_dir.glob("*.json")):
            payload = load_json(path)
            if payload is None:
                continue
            provider_id = optional_text(payload.get("provider_id"))
            if provider_id is None:
                continue
            descriptors[provider_id] = payload
            descriptor_paths[provider_id] = str(path)
            remote = payload.get("remote_registration")
            if isinstance(remote, dict):
                provider_ref = optional_text(remote.get("provider_ref"))
                endpoint = optional_text(remote.get("endpoint"))
                if provider_ref and endpoint:
                    remote_lookup[(provider_ref, endpoint)] = provider_id

    health: dict[str, dict] = {}
    health_paths: dict[str, str] = {}
    if health_dir.exists():
        for path in sorted(health_dir.glob("*.json")):
            payload = load_json(path)
            if payload is None:
                continue
            provider_id = optional_text(payload.get("provider_id"))
            if provider_id is None:
                continue
            health[provider_id] = payload
            health_paths[provider_id] = str(path)

    return {
        "state_dir": str(state_dir),
        "descriptors": descriptors,
        "descriptor_paths": descriptor_paths,
        "remote_lookup": remote_lookup,
        "health": health,
        "health_paths": health_paths,
    }


def attestation_fields(payload: dict | None) -> dict:
    source = payload if isinstance(payload, dict) else {}
    return {
        "attestation_mode": optional_text(source.get("mode")),
        "attestation_status": optional_text(source.get("status")),
        "attestation_expires_at": optional_text(source.get("expires_at")),
        "attestation_issuer": optional_text(source.get("issuer")),
        "attestation_subject": optional_text(source.get("subject")),
    }


def governance_fields(payload: dict | None) -> dict:
    source = payload if isinstance(payload, dict) else {}
    return {
        "fleet_id": optional_text(source.get("fleet_id")),
        "governance_group": optional_text(source.get("governance_group")),
        "policy_group": optional_text(source.get("policy_group")),
        "registered_by": optional_text(source.get("registered_by")),
        "approval_ref": optional_text(source.get("approval_ref")),
        "allow_lateral_movement": bool(source.get("allow_lateral_movement", False)),
    }


def normalize_remote_entry(
    *,
    source: str,
    registry_path: str | None,
    registration: dict | None,
    descriptor: dict | None,
    descriptor_path: str | None,
    health: dict | None,
    health_path: str | None,
) -> dict:
    registration_payload = registration if isinstance(registration, dict) else {}
    descriptor_remote = descriptor.get("remote_registration") if isinstance(descriptor, dict) else {}
    descriptor_remote = descriptor_remote if isinstance(descriptor_remote, dict) else {}
    provider_ref = optional_text(registration_payload.get("provider_ref")) or optional_text(
        descriptor_remote.get("provider_ref")
    )
    endpoint = optional_text(registration_payload.get("endpoint")) or optional_text(
        descriptor_remote.get("endpoint")
    )
    control_plane_provider_id = optional_text(registration_payload.get("control_plane_provider_id")) or optional_text(
        descriptor.get("provider_id") if isinstance(descriptor, dict) else None
    )
    registration_status_value = remote_registration_status(
        registration_payload if registration_payload else descriptor_remote
    )
    descriptor_registration_status = (
        remote_registration_status(descriptor_remote) if descriptor_remote else None
    )
    registration_attestation = attestation_fields(registration_payload.get("attestation"))
    descriptor_attestation = attestation_fields(descriptor_remote.get("attestation"))
    registration_governance = governance_fields(registration_payload.get("governance"))
    descriptor_governance = governance_fields(descriptor_remote.get("governance"))
    health_status = optional_text((health or {}).get("status")) or ("missing" if descriptor else "missing")

    entry = {
        "entry_id": f"{source}:{provider_ref or control_plane_provider_id or endpoint or 'remote'}",
        "source": source,
        "provider_ref": provider_ref,
        "endpoint": endpoint,
        "target_hash": optional_text(registration_payload.get("target_hash")) or optional_text(
            descriptor_remote.get("target_hash")
        ),
        "registered_at": optional_text(registration_payload.get("registered_at")) or optional_text(
            descriptor_remote.get("registered_at")
        ),
        "registration_status": registration_status_value,
        "descriptor_registration_status": descriptor_registration_status,
        "last_heartbeat_at": optional_text(registration_payload.get("last_heartbeat_at")) or optional_text(
            descriptor_remote.get("last_heartbeat_at")
        ),
        "heartbeat_ttl_seconds": optional_int(registration_payload.get("heartbeat_ttl_seconds"))
        or optional_int(descriptor_remote.get("heartbeat_ttl_seconds")),
        "revoked_at": optional_text(registration_payload.get("revoked_at")) or optional_text(
            descriptor_remote.get("revoked_at")
        ),
        "revocation_reason": optional_text(registration_payload.get("revocation_reason")) or optional_text(
            descriptor_remote.get("revocation_reason")
        ),
        "control_plane_provider_id": control_plane_provider_id,
        "control_plane_registered": descriptor is not None,
        "control_plane_health_status": health_status,
        "control_plane_disabled": bool((health or {}).get("disabled", False)),
        "control_plane_disabled_reason": optional_text((health or {}).get("disabled_reason")),
        "control_plane_last_error": optional_text((health or {}).get("last_error")),
        "descriptor_path": descriptor_path,
        "health_path": health_path,
        "remote_registry_path": registry_path,
        "descriptor_present": descriptor is not None,
        "health_present": health is not None,
        "descriptor_only": not registration_payload and descriptor is not None,
        "descriptor_display_name": optional_text((descriptor or {}).get("display_name")),
        "descriptor_kind": optional_text((descriptor or {}).get("kind")),
        "descriptor_execution_location": optional_text((descriptor or {}).get("execution_location")),
        **{
            key: value
            for key, value in registration_attestation.items()
            if value is not None
        },
        **{
            key: value
            for key, value in registration_governance.items()
            if value is not None or key == "allow_lateral_movement"
        },
        "descriptor_attestation_mode": descriptor_attestation.get("attestation_mode"),
        "descriptor_attestation_status": descriptor_attestation.get("attestation_status"),
        "descriptor_attestation_expires_at": descriptor_attestation.get("attestation_expires_at"),
        "descriptor_fleet_id": descriptor_governance.get("fleet_id"),
        "descriptor_governance_group": descriptor_governance.get("governance_group"),
        "descriptor_policy_group": descriptor_governance.get("policy_group"),
        "descriptor_approval_ref": descriptor_governance.get("approval_ref"),
    }
    return entry


def issue(
    entry: dict,
    *,
    severity: str,
    kind: str,
    title: str,
    detail: str,
) -> dict:
    return {
        "entry_id": entry.get("entry_id"),
        "source": entry.get("source"),
        "severity": severity,
        "kind": kind,
        "title": title,
        "detail": detail,
        "provider_ref": entry.get("provider_ref"),
        "provider_id": entry.get("control_plane_provider_id"),
        "fleet_id": entry.get("fleet_id"),
        "registration_status": entry.get("registration_status"),
    }


def build_entry_issues(entry: dict) -> list[dict]:
    issues: list[dict] = []
    if entry.get("descriptor_only"):
        issues.append(
            issue(
                entry,
                severity="high",
                kind="orphan-control-plane",
                title="Orphan control-plane descriptor",
                detail=f"provider_id={entry.get('control_plane_provider_id') or '-'} has no matching remote registry entry",
            )
        )
    if entry.get("registration_status") == "revoked":
        issues.append(
            issue(
                entry,
                severity="critical",
                kind="revoked-remote",
                title="Remote registration revoked",
                detail=f"reason={entry.get('revocation_reason') or '-'} provider_ref={entry.get('provider_ref') or '-'}",
            )
        )
    elif entry.get("registration_status") == "stale":
        issues.append(
            issue(
                entry,
                severity="high",
                kind="stale-heartbeat",
                title="Remote heartbeat stale",
                detail=f"provider_ref={entry.get('provider_ref') or '-'} ttl={entry.get('heartbeat_ttl_seconds') or '-'}",
            )
        )
    if not entry.get("control_plane_provider_id"):
        issues.append(
            issue(
                entry,
                severity="medium",
                kind="unpromoted-remote",
                title="Control-plane promotion missing",
                detail=f"provider_ref={entry.get('provider_ref') or '-'} has no control-plane provider id",
            )
        )
    elif not entry.get("control_plane_registered"):
        issues.append(
            issue(
                entry,
                severity="high",
                kind="missing-control-plane-descriptor",
                title="Control-plane descriptor missing",
                detail=f"provider_id={entry.get('control_plane_provider_id') or '-'} not found in provider registry",
            )
        )
    health_status = entry.get("control_plane_health_status")
    if entry.get("control_plane_registered") and health_status == "missing":
        issues.append(
            issue(
                entry,
                severity="medium",
                kind="missing-health-state",
                title="Control-plane health missing",
                detail=f"provider_id={entry.get('control_plane_provider_id') or '-'} has no health artifact",
            )
        )
    elif health_status == "degraded":
        issues.append(
            issue(
                entry,
                severity="medium",
                kind="degraded-control-plane",
                title="Control-plane degraded",
                detail=f"provider_id={entry.get('control_plane_provider_id') or '-'} health=degraded",
            )
        )
    elif health_status == "unavailable":
        issues.append(
            issue(
                entry,
                severity="high",
                kind="unavailable-control-plane",
                title="Control-plane unavailable",
                detail=f"provider_id={entry.get('control_plane_provider_id') or '-'} health=unavailable",
            )
        )
    if entry.get("control_plane_disabled"):
        issues.append(
            issue(
                entry,
                severity="high",
                kind="disabled-control-plane",
                title="Control-plane disabled",
                detail=f"reason={entry.get('control_plane_disabled_reason') or '-'} provider_id={entry.get('control_plane_provider_id') or '-'}",
            )
        )
    if not entry.get("attestation_mode"):
        issues.append(
            issue(
                entry,
                severity="medium",
                kind="missing-attestation",
                title="Attestation missing",
                detail=f"provider_ref={entry.get('provider_ref') or '-'} has no attestation metadata",
            )
        )
    expires_at = parse_rfc3339(entry.get("attestation_expires_at"))
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        issues.append(
            issue(
                entry,
                severity="high",
                kind="expired-attestation",
                title="Attestation expired",
                detail=f"provider_ref={entry.get('provider_ref') or '-'} expires_at={entry.get('attestation_expires_at')}",
            )
        )
    attestation_status = entry.get("attestation_status")
    if attestation_status not in (None, "trusted", "valid"):
        issues.append(
            issue(
                entry,
                severity="medium",
                kind="untrusted-attestation",
                title="Attestation not trusted",
                detail=f"provider_ref={entry.get('provider_ref') or '-'} status={attestation_status}",
            )
        )
    if not entry.get("fleet_id") or not entry.get("governance_group"):
        issues.append(
            issue(
                entry,
                severity="medium",
                kind="incomplete-governance",
                title="Governance metadata incomplete",
                detail=f"provider_ref={entry.get('provider_ref') or '-'} fleet/group missing",
            )
        )
    if entry.get("descriptor_registration_status") not in (None, entry.get("registration_status")):
        issues.append(
            issue(
                entry,
                severity="medium",
                kind="control-plane-drift",
                title="Control-plane lifecycle drift",
                detail=(
                    f"provider_id={entry.get('control_plane_provider_id') or '-'} "
                    f"descriptor={entry.get('descriptor_registration_status')} "
                    f"registry={entry.get('registration_status')}"
                ),
            )
        )
    if entry.get("allow_lateral_movement"):
        issues.append(
            issue(
                entry,
                severity="info",
                kind="lateral-movement-allowed",
                title="Lateral movement allowed",
                detail=f"provider_ref={entry.get('provider_ref') or '-'} governance allows lateral movement",
            )
        )
    return issues


def searchable_text(entry: dict) -> str:
    values = [
        entry.get("source"),
        entry.get("provider_ref"),
        entry.get("control_plane_provider_id"),
        entry.get("endpoint"),
        entry.get("fleet_id"),
        entry.get("governance_group"),
        entry.get("policy_group"),
        entry.get("registration_status"),
        entry.get("attestation_mode"),
        entry.get("control_plane_health_status"),
        entry.get("approval_ref"),
        entry.get("registered_by"),
    ]
    values.extend(issue_item.get("title") for issue_item in entry.get("issues", []))
    values.extend(issue_item.get("detail") for issue_item in entry.get("issues", []))
    return " ".join(str(value) for value in values if value not in (None, ""))


def entry_matches(entry: dict, filters: dict[str, object]) -> bool:
    source = optional_text(filters.get("source"))
    if source and entry.get("source") != source:
        return False
    severity = optional_text(filters.get("severity"))
    if severity:
        severities = {item.get("severity") for item in entry.get("issues", [])}
        if severity not in severities:
            return False
    fleet_id = optional_text(filters.get("fleet_id"))
    if fleet_id and entry.get("fleet_id") != fleet_id:
        return False
    governance_group = optional_text(filters.get("governance_group"))
    if governance_group and entry.get("governance_group") != governance_group:
        return False
    status = optional_text(filters.get("status"))
    if status and entry.get("registration_status") != status:
        return False
    provider_ref = optional_text(filters.get("provider_ref"))
    if provider_ref and entry.get("provider_ref") != provider_ref:
        return False
    provider_id = optional_text(filters.get("provider_id"))
    if provider_id and entry.get("control_plane_provider_id") != provider_id:
        return False
    attestation_mode = optional_text(filters.get("attestation_mode"))
    if attestation_mode and entry.get("attestation_mode") != attestation_mode:
        return False
    control_plane_status = optional_text(filters.get("control_plane_status"))
    if control_plane_status and entry.get("control_plane_health_status") != control_plane_status:
        return False
    approval_ref = optional_text(filters.get("approval_ref"))
    if approval_ref and entry.get("approval_ref") != approval_ref:
        return False
    text = optional_text(filters.get("text"))
    if text and text.lower() not in searchable_text(entry).lower():
        return False
    return True


def severity_rank(severity: str | None) -> int:
    return SEVERITY_ORDER.get((severity or "").lower(), 0)


def status_rank(status: str | None) -> int:
    return STATUS_ORDER.get((status or "").lower(), 0)


def sort_entries(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda item: (
            -severity_rank(item.get("issue_severity")),
            -status_rank(item.get("registration_status")),
            item.get("source") or "",
            item.get("provider_ref") or item.get("control_plane_provider_id") or "",
        ),
    )


def fleet_summary(entries: list[dict]) -> list[dict]:
    fleets: dict[str, dict] = {}
    for entry in entries:
        fleet_id = entry.get("fleet_id") or "unassigned"
        bucket = fleets.setdefault(
            fleet_id,
            {
                "fleet_id": fleet_id,
                "entry_count": 0,
                "issue_count": 0,
                "status_counts": {},
                "sources": set(),
            },
        )
        bucket["entry_count"] += 1
        bucket["issue_count"] += int(entry.get("issue_count") or 0)
        status = entry.get("registration_status") or "unknown"
        status_counts = bucket["status_counts"]
        status_counts[status] = status_counts.get(status, 0) + 1
        if entry.get("source"):
            bucket["sources"].add(entry["source"])
    result = []
    for fleet_id, bucket in fleets.items():
        result.append(
            {
                "fleet_id": fleet_id,
                "entry_count": bucket["entry_count"],
                "issue_count": bucket["issue_count"],
                "status_counts": bucket["status_counts"],
                "sources": sorted(bucket["sources"]),
            }
        )
    result.sort(key=lambda item: (-item["issue_count"], -item["entry_count"], item["fleet_id"]))
    return result


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def load_remote_governance(
    browser_remote_registry: Path,
    office_remote_registry: Path,
    provider_registry_state_dir: Path,
    *,
    limit: int = 10,
    filters: dict[str, object] | None = None,
    issue_only: bool = False,
    report_path: Path | None = None,
) -> dict:
    registry_state = load_provider_registry(provider_registry_state_dir)
    descriptors = registry_state["descriptors"]
    descriptor_paths = registry_state["descriptor_paths"]
    remote_lookup = registry_state["remote_lookup"]
    health = registry_state["health"]
    health_paths = registry_state["health_paths"]

    raw_entries = [
        *load_remote_registry(browser_remote_registry, "browser"),
        *load_remote_registry(office_remote_registry, "office"),
    ]
    entries: list[dict] = []
    matched_provider_ids: set[str] = set()
    for item in raw_entries:
        registration = item["registration"]
        provider_id = optional_text(registration.get("control_plane_provider_id"))
        if provider_id is None:
            lookup_key = (
                optional_text(registration.get("provider_ref")) or "",
                optional_text(registration.get("endpoint")) or "",
            )
            provider_id = remote_lookup.get(lookup_key)
        descriptor = descriptors.get(provider_id) if provider_id else None
        if provider_id:
            matched_provider_ids.add(provider_id)
        normalized = normalize_remote_entry(
            source=item["source"],
            registry_path=item["registry_path"],
            registration=registration,
            descriptor=descriptor,
            descriptor_path=descriptor_paths.get(provider_id) if provider_id else None,
            health=health.get(provider_id) if provider_id else None,
            health_path=health_paths.get(provider_id) if provider_id else None,
        )
        entries.append(normalized)

    for provider_id, descriptor in descriptors.items():
        if provider_id in matched_provider_ids:
            continue
        remote_registration = descriptor.get("remote_registration")
        if not isinstance(remote_registration, dict):
            continue
        normalized = normalize_remote_entry(
            source=infer_source(remote_registration, provider_id),
            registry_path=None,
            registration=None,
            descriptor=descriptor,
            descriptor_path=descriptor_paths.get(provider_id),
            health=health.get(provider_id),
            health_path=health_paths.get(provider_id),
        )
        entries.append(normalized)

    for entry in entries:
        issues = build_entry_issues(entry)
        highest = max((severity_rank(item.get("severity")) for item in issues), default=0)
        issue_severity = next(
            (name for name, rank in SEVERITY_ORDER.items() if rank == highest),
            None,
        )
        entry["issues"] = issues
        entry["issue_count"] = len(issues)
        entry["issue_severity"] = issue_severity

    filters = {key: value for key, value in (filters or {}).items() if value not in (None, "")}
    matched_entries = [entry for entry in entries if entry_matches(entry, filters)]
    if issue_only:
        matched_entries = [entry for entry in matched_entries if entry.get("issue_count", 0) > 0]
    matched_entries = sort_entries(matched_entries)
    visible_entries = matched_entries[: max(1, min(limit, 32))]
    visible_entry_ids = {entry.get("entry_id") for entry in visible_entries}
    visible_issues = []
    for entry in visible_entries:
        visible_issues.extend(entry.get("issues", []))
    visible_issues.sort(
        key=lambda item: (
            -severity_rank(item.get("severity")),
            item.get("source") or "",
            item.get("provider_ref") or item.get("provider_id") or "",
        )
    )
    source_counts: dict[str, int] = {}
    filtered_source_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    filtered_status_counts: dict[str, int] = {}
    for entry in entries:
        source = entry.get("source") or "compat"
        source_counts[source] = source_counts.get(source, 0) + 1
        status = entry.get("registration_status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    for entry in matched_entries:
        source = entry.get("source") or "compat"
        filtered_source_counts[source] = filtered_source_counts.get(source, 0) + 1
        status = entry.get("registration_status") or "unknown"
        filtered_status_counts[status] = filtered_status_counts.get(status, 0) + 1
    payload = {
        "generated_at": utc_now(),
        "entry_count": len(entries),
        "matched_entry_count": len(matched_entries),
        "issue_count": sum(int(entry.get("issue_count") or 0) for entry in matched_entries),
        "source_counts": source_counts,
        "filtered_source_counts": filtered_source_counts,
        "status_counts": status_counts,
        "filtered_status_counts": filtered_status_counts,
        "fleet_ids": sorted({entry.get("fleet_id") for entry in matched_entries if entry.get("fleet_id")}),
        "governance_groups": sorted(
            {entry.get("governance_group") for entry in matched_entries if entry.get("governance_group")}
        ),
        "attestation_modes": sorted(
            {entry.get("attestation_mode") for entry in matched_entries if entry.get("attestation_mode")}
        ),
        "control_plane_provider_ids": sorted(
            {
                entry.get("control_plane_provider_id")
                for entry in matched_entries
                if entry.get("control_plane_provider_id")
            }
        ),
        "control_plane_registered_count": sum(
            1 for entry in matched_entries if entry.get("control_plane_registered")
        ),
        "entries": visible_entries,
        "issues": visible_issues,
        "fleet_summary": fleet_summary(matched_entries),
        "artifact_paths": {
            "browser_remote_registry": str(browser_remote_registry),
            "office_remote_registry": str(office_remote_registry),
            "provider_registry_state_dir": str(provider_registry_state_dir),
        },
        "query": {
            "filters": filters,
            "issue_only": issue_only,
            "limit": max(1, min(limit, 32)),
            "report_path": str(report_path) if report_path is not None else None,
        },
        "notes": [
            f"descriptor_count={len(descriptors)}",
            f"health_count={len(health)}",
            f"visible_entry_ids={','.join(sorted(value for value in visible_entry_ids if value))}",
        ],
    }
    if report_path is not None:
        write_report(report_path, payload)
    return payload


def render(payload: dict) -> str:
    lines = []
    lines.append(f"generated_at: {payload.get('generated_at')}")
    lines.append(
        "summary: "
        f"matched={payload.get('matched_entry_count', 0)} "
        f"issues={payload.get('issue_count', 0)} "
        f"fleets={len(payload.get('fleet_summary', []))}"
    )
    for entry in payload.get("entries", []):
        lines.append(
            "entry: "
            f"{entry.get('source')} "
            f"{entry.get('provider_ref') or entry.get('control_plane_provider_id') or '-'} "
            f"[{entry.get('registration_status')}] "
            f"fleet={entry.get('fleet_id') or '-'} "
            f"control_plane={entry.get('control_plane_provider_id') or '-'} "
            f"health={entry.get('control_plane_health_status') or '-'}"
        )
    for issue_item in payload.get("issues", []):
        lines.append(
            "issue: "
            f"{issue_item.get('severity')} {issue_item.get('title')} :: {issue_item.get('detail')}"
        )
    for note in payload.get("notes", []):
        lines.append(f"note: {note}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS compat remote governance prototype")
    parser.add_argument("--browser-remote-registry", type=Path, default=default_browser_remote_registry())
    parser.add_argument("--office-remote-registry", type=Path, default=default_office_remote_registry())
    parser.add_argument("--provider-registry-state-dir", type=Path, default=default_provider_registry_state_dir())
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--source")
    parser.add_argument("--severity")
    parser.add_argument("--fleet-id")
    parser.add_argument("--governance-group")
    parser.add_argument("--status")
    parser.add_argument("--provider-ref")
    parser.add_argument("--provider-id")
    parser.add_argument("--attestation-mode")
    parser.add_argument("--control-plane-status")
    parser.add_argument("--approval-ref")
    parser.add_argument("--text")
    parser.add_argument("--issue-only", action="store_true")
    parser.add_argument("--write-report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    filters = {
        "source": args.source,
        "severity": args.severity,
        "fleet_id": args.fleet_id,
        "governance_group": args.governance_group,
        "status": args.status,
        "provider_ref": args.provider_ref,
        "provider_id": args.provider_id,
        "attestation_mode": args.attestation_mode,
        "control_plane_status": args.control_plane_status,
        "approval_ref": args.approval_ref,
        "text": args.text,
    }
    payload = load_remote_governance(
        args.browser_remote_registry,
        args.office_remote_registry,
        args.provider_registry_state_dir,
        limit=args.limit,
        filters=filters,
        issue_only=args.issue_only,
        report_path=args.write_report,
    )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render(payload))
