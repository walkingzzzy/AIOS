#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


MANAGED_ENV_KEYS = (
    "AIOS_RUNTIMED_MEMORY_ENABLED",
    "AIOS_RUNTIMED_MEMORY_RETENTION_DAYS",
    "AIOS_RUNTIMED_AUDIT_RETENTION_DAYS",
    "AIOS_RUNTIMED_APPROVAL_DEFAULT_POLICY",
    "AIOS_RUNTIMED_REMOTE_PROMPT_LEVEL",
)
APPROVAL_POLICY_LABELS = {
    "prompt-required": "Prompt Required",
    "session-trust": "Session Trust",
    "operator-gate": "Operator Gate",
}
REMOTE_PROMPT_LEVEL_LABELS = {
    "full": "Full Disclosure",
    "summary": "Summary",
    "minimal": "Minimal Banner",
}
DEFAULT_MEMORY_ENABLED = True
DEFAULT_MEMORY_RETENTION_DAYS = 30
DEFAULT_AUDIT_RETENTION_DAYS = 90
DEFAULT_APPROVAL_POLICY = "prompt-required"
DEFAULT_REMOTE_PROMPT_LEVEL = "full"


def default_runtime_platform_env_path() -> Path:
    value = os.environ.get("AIOS_SHELL_RUNTIME_PLATFORM_ENV")
    return Path(value) if value else Path("/etc/aios/runtime/platform.env")


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_retention_days(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 3650))


def normalize_approval_policy(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in APPROVAL_POLICY_LABELS:
        return candidate
    return DEFAULT_APPROVAL_POLICY


def approval_policy_label(value: str) -> str:
    return APPROVAL_POLICY_LABELS.get(value, value or "Unknown")


def normalize_remote_prompt_level(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in REMOTE_PROMPT_LEVEL_LABELS:
        return candidate
    return DEFAULT_REMOTE_PROMPT_LEVEL


def remote_prompt_level_label(value: str) -> str:
    return REMOTE_PROMPT_LEVEL_LABELS.get(value, value or "Unknown")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def merge_env_text(existing_text: str, managed_values: dict[str, str]) -> str:
    preserved_lines: list[str] = []
    for raw_line in existing_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            preserved_lines.append(raw_line.rstrip())
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in MANAGED_ENV_KEYS:
            continue
        preserved_lines.append(raw_line.rstrip())
    while preserved_lines and not preserved_lines[-1].strip():
        preserved_lines.pop()
    managed_lines = [f"{key}={value}" for key, value in managed_values.items() if value not in (None, "")]
    return "\n".join([*preserved_lines, *managed_lines]).rstrip() + "\n"


def write_env(path: Path, managed_values: dict[str, str]) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merge_env_text(existing_text, managed_values), encoding="utf-8")


def build_privacy_memory_state(runtime_platform_env_path: Path | None) -> dict[str, Any]:
    runtime_platform_env = runtime_platform_env_path or default_runtime_platform_env_path()
    env_values = load_env(runtime_platform_env)
    memory_enabled = parse_bool(
        env_values.get("AIOS_RUNTIMED_MEMORY_ENABLED"),
        default=DEFAULT_MEMORY_ENABLED,
    )
    memory_retention_days = normalize_retention_days(
        env_values.get("AIOS_RUNTIMED_MEMORY_RETENTION_DAYS"),
        DEFAULT_MEMORY_RETENTION_DAYS,
    )
    audit_retention_days = normalize_retention_days(
        env_values.get("AIOS_RUNTIMED_AUDIT_RETENTION_DAYS"),
        DEFAULT_AUDIT_RETENTION_DAYS,
    )
    approval_default_policy = normalize_approval_policy(
        env_values.get("AIOS_RUNTIMED_APPROVAL_DEFAULT_POLICY")
    )
    remote_prompt_level = normalize_remote_prompt_level(
        env_values.get("AIOS_RUNTIMED_REMOTE_PROMPT_LEVEL")
    )
    diagnostics: list[str] = []
    if not runtime_platform_env.exists():
        diagnostics.append(f"runtime_env_missing={runtime_platform_env}")
    if not memory_enabled:
        diagnostics.append("memory_disabled=true")
    if audit_retention_days < memory_retention_days:
        diagnostics.append("audit_retention_shorter_than_memory=true")
    if remote_prompt_level == "minimal":
        diagnostics.append("remote_prompt_visibility=minimal")
    return {
        "env_values": env_values,
        "runtime_platform_env_path": str(runtime_platform_env),
        "runtime_platform_env_exists": runtime_platform_env.exists(),
        "memory_enabled": memory_enabled,
        "memory_retention_days": memory_retention_days,
        "audit_retention_days": audit_retention_days,
        "approval_default_policy": approval_default_policy,
        "approval_default_policy_label": approval_policy_label(approval_default_policy),
        "remote_prompt_level": remote_prompt_level,
        "remote_prompt_level_label": remote_prompt_level_label(remote_prompt_level),
        "managed_keys": list(MANAGED_ENV_KEYS),
        "diagnostics": diagnostics,
    }


def apply_privacy_memory_settings(
    runtime_platform_env_path: Path | None,
    *,
    memory_enabled: bool | None = None,
    memory_retention_days: Any = None,
    audit_retention_days: Any = None,
    approval_default_policy: str | None = None,
    remote_prompt_level: str | None = None,
) -> dict[str, Any]:
    state = build_privacy_memory_state(runtime_platform_env_path)
    next_memory_enabled = state.get("memory_enabled", DEFAULT_MEMORY_ENABLED)
    if memory_enabled is not None:
        next_memory_enabled = bool(memory_enabled)
    next_memory_retention_days = normalize_retention_days(
        memory_retention_days if memory_retention_days is not None else state.get("memory_retention_days"),
        DEFAULT_MEMORY_RETENTION_DAYS,
    )
    next_audit_retention_days = normalize_retention_days(
        audit_retention_days if audit_retention_days is not None else state.get("audit_retention_days"),
        DEFAULT_AUDIT_RETENTION_DAYS,
    )
    next_approval_default_policy = normalize_approval_policy(
        approval_default_policy or state.get("approval_default_policy")
    )
    next_remote_prompt_level = normalize_remote_prompt_level(
        remote_prompt_level or state.get("remote_prompt_level")
    )
    managed_values = {
        "AIOS_RUNTIMED_MEMORY_ENABLED": "1" if next_memory_enabled else "0",
        "AIOS_RUNTIMED_MEMORY_RETENTION_DAYS": str(next_memory_retention_days),
        "AIOS_RUNTIMED_AUDIT_RETENTION_DAYS": str(next_audit_retention_days),
        "AIOS_RUNTIMED_APPROVAL_DEFAULT_POLICY": next_approval_default_policy,
        "AIOS_RUNTIMED_REMOTE_PROMPT_LEVEL": next_remote_prompt_level,
    }
    runtime_platform_env = runtime_platform_env_path or default_runtime_platform_env_path()
    write_env(runtime_platform_env, managed_values)
    return build_privacy_memory_state(runtime_platform_env)


def render_state(state: dict[str, Any]) -> str:
    lines = [
        f"memory_enabled: {state.get('memory_enabled')}",
        f"memory_retention_days: {state.get('memory_retention_days')}",
        f"audit_retention_days: {state.get('audit_retention_days')}",
        f"approval_default_policy: {state.get('approval_default_policy_label')}",
        f"remote_prompt_level: {state.get('remote_prompt_level_label')}",
        f"runtime_platform_env: {state.get('runtime_platform_env_path')}",
    ]
    for item in state.get("diagnostics", []):
        lines.append(f"diag: {item}")
    return "\n".join(lines)
