#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


LOCAL_CPU_WORKER_LAUNCHER = "/usr/libexec/aios/runtime/workers/launch_local_cpu_worker.sh"
MANAGED_ENV_KEYS = (
    "AIOS_RUNTIMED_AI_ENABLED",
    "AIOS_RUNTIMED_AI_MODE",
    "AIOS_RUNTIMED_AI_PRIVACY_PROFILE",
    "AIOS_RUNTIMED_AI_ROUTE_PREFERENCE",
    "AIOS_RUNTIMED_LOCAL_CPU_COMMAND",
    "AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL",
    "AIOS_RUNTIMED_AI_ENDPOINT_MODEL",
    "AIOS_RUNTIMED_AI_ENDPOINT_API_KEY",
)
ROUTE_PREFERENCE_LABELS = {
    "local-first": "Local First",
    "remote-first": "Remote First",
    "remote-only": "Remote Only",
}
PRIVACY_PROFILE_LABELS = {
    "strict-local": "Strict Local",
    "balanced": "Balanced",
    "cloud-enhanced": "Cloud Enhanced",
}

_UNSET = object()
_AI_CENTER_PROTOTYPE_MODULE: ModuleType | None = None


def _load_module(module_name: str, path: Path) -> ModuleType:
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_ai_center_prototype_module() -> ModuleType:
    global _AI_CENTER_PROTOTYPE_MODULE
    if _AI_CENTER_PROTOTYPE_MODULE is not None:
        return _AI_CENTER_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "ai-center" / "prototype.py"
    _AI_CENTER_PROTOTYPE_MODULE = _load_module("aios_shell_ai_center_prototype", module_path)
    return _AI_CENTER_PROTOTYPE_MODULE


def default_ai_readiness_path() -> Path:
    return load_ai_center_prototype_module().default_ai_readiness_path()


def default_ai_onboarding_report_path() -> Path:
    return load_ai_center_prototype_module().default_ai_onboarding_report_path()


def default_runtime_platform_env_path() -> Path:
    value = os.environ.get("AIOS_SHELL_RUNTIME_PLATFORM_ENV")
    return Path(value) if value else Path("/etc/aios/runtime/platform.env")


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_ai_mode(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"local", "cloud", "hybrid", "later"}:
        return candidate
    return "hybrid"


def normalize_privacy_profile(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in PRIVACY_PROFILE_LABELS:
        return candidate
    return "balanced"


def default_route_preference(ai_mode: str) -> str:
    if ai_mode == "cloud":
        return "remote-only"
    return "local-first"


def normalize_route_preference(value: Any, ai_mode: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate not in ROUTE_PREFERENCE_LABELS:
        candidate = default_route_preference(ai_mode)
    if ai_mode == "cloud":
        return "remote-only"
    if ai_mode == "local":
        return "local-first"
    return candidate


def route_preference_label(value: str) -> str:
    return ROUTE_PREFERENCE_LABELS.get(value, value or "Unknown")


def privacy_profile_label(value: str) -> str:
    return PRIVACY_PROFILE_LABELS.get(value, value or "Unknown")


def mask_secret(value: str | None) -> str:
    if not value:
        return "-"
    stripped = value.strip()
    if not stripped:
        return "-"
    if len(stripped) <= 4:
        return "*" * len(stripped)
    if len(stripped) <= 8:
        return "*" * (len(stripped) - 2) + stripped[-2:]
    return stripped[:2] + "*" * (len(stripped) - 6) + stripped[-4:]


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


def build_ai_readiness_summary(
    readiness_path: Path | None,
    report_path: Path | None,
) -> dict[str, Any]:
    return load_ai_center_prototype_module().load_ai_readiness_summary(readiness_path, report_path)


def build_provider_settings_state(
    readiness_path: Path | None,
    report_path: Path | None,
    runtime_platform_env_path: Path | None,
) -> dict[str, Any]:
    readiness = build_ai_readiness_summary(readiness_path, report_path)
    runtime_platform_env = runtime_platform_env_path or default_runtime_platform_env_path()
    env_values = load_env(runtime_platform_env)
    onboarding_base_url = str(readiness.get("endpoint_base_url") or "").strip()
    onboarding_model = str(readiness.get("endpoint_model") or "").strip()
    persisted_base_url = str(env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL") or "").strip()
    persisted_model = str(env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_MODEL") or "").strip()
    persisted_api_key = str(env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_API_KEY") or "").strip()
    effective_base_url = persisted_base_url or onboarding_base_url
    effective_model = persisted_model or onboarding_model
    ai_mode = normalize_ai_mode(env_values.get("AIOS_RUNTIMED_AI_MODE") or readiness.get("ai_mode"))
    provider_enabled = parse_bool(
        env_values.get("AIOS_RUNTIMED_AI_ENABLED"),
        default=readiness.get("ai_enabled") if readiness.get("ai_enabled") is not None else True,
    )
    privacy_profile = normalize_privacy_profile(
        env_values.get("AIOS_RUNTIMED_AI_PRIVACY_PROFILE") or readiness.get("privacy_profile")
    )
    route_preference = normalize_route_preference(
        env_values.get("AIOS_RUNTIMED_AI_ROUTE_PREFERENCE"),
        ai_mode,
    )
    endpoint_configured = bool(effective_base_url and effective_model)
    endpoint_source = "none"
    if persisted_base_url or persisted_model:
        endpoint_source = "runtime-platform-env"
    elif onboarding_base_url or onboarding_model:
        endpoint_source = "onboarding-report"
    local_cpu_enabled = (
        str(env_values.get("AIOS_RUNTIMED_LOCAL_CPU_COMMAND") or "").strip()
        == LOCAL_CPU_WORKER_LAUNCHER
    )
    diagnostics: list[str] = []
    if not runtime_platform_env.exists():
        diagnostics.append(f"runtime_env_missing={runtime_platform_env}")
    if not provider_enabled:
        diagnostics.append("provider_disabled=true")
    if route_preference.startswith("remote") and not endpoint_configured:
        diagnostics.append("remote_route_without_endpoint=true")
    if ai_mode == "cloud" and not endpoint_configured:
        diagnostics.append("cloud_mode_requires_endpoint=true")
    if local_cpu_enabled and ai_mode not in {"local", "hybrid"}:
        diagnostics.append("local_cpu_command_active_outside_local_modes=true")
    if readiness.get("source_error"):
        diagnostics.append(f"readiness_source={readiness['source_error']}")
    return {
        "readiness": readiness,
        "env_values": env_values,
        "runtime_platform_env_path": str(runtime_platform_env),
        "runtime_platform_env_exists": runtime_platform_env.exists(),
        "provider_enabled": provider_enabled,
        "ai_mode": ai_mode,
        "ai_mode_label": load_ai_center_prototype_module().mode_label(ai_mode),
        "privacy_profile": privacy_profile,
        "privacy_profile_label": privacy_profile_label(privacy_profile),
        "route_preference": route_preference,
        "route_preference_label": route_preference_label(route_preference),
        "endpoint_source": endpoint_source,
        "endpoint_configured": endpoint_configured,
        "endpoint_base_url": effective_base_url,
        "endpoint_model": effective_model,
        "persisted_endpoint_base_url": persisted_base_url,
        "persisted_endpoint_model": persisted_model,
        "endpoint_api_key_raw": persisted_api_key,
        "endpoint_api_key_configured": bool(persisted_api_key),
        "endpoint_api_key_masked": mask_secret(persisted_api_key),
        "onboarding_endpoint_available": bool(onboarding_base_url and onboarding_model),
        "onboarding_endpoint_base_url": onboarding_base_url,
        "onboarding_endpoint_model": onboarding_model,
        "local_cpu_enabled": local_cpu_enabled,
        "managed_keys": list(MANAGED_ENV_KEYS),
        "diagnostics": diagnostics,
    }


def apply_provider_settings(
    readiness_path: Path | None,
    report_path: Path | None,
    runtime_platform_env_path: Path | None,
    *,
    provider_enabled: bool | None = None,
    ai_mode: str | None = None,
    route_preference: str | None = None,
    privacy_profile: str | None = None,
    endpoint_base_url: Any = _UNSET,
    endpoint_model: Any = _UNSET,
    endpoint_api_key: Any = _UNSET,
    clear_api_key: bool = False,
    clear_remote_endpoint: bool = False,
    use_onboarding_endpoint: bool = False,
) -> dict[str, Any]:
    state = build_provider_settings_state(
        readiness_path,
        report_path,
        runtime_platform_env_path,
    )
    env_values = dict(state.get("env_values") or {})
    next_provider_enabled = state.get("provider_enabled", True)
    if provider_enabled is not None:
        next_provider_enabled = bool(provider_enabled)
    next_ai_mode = normalize_ai_mode(ai_mode or state.get("ai_mode"))
    next_route_preference = normalize_route_preference(
        route_preference or state.get("route_preference"),
        next_ai_mode,
    )
    next_privacy_profile = normalize_privacy_profile(
        privacy_profile or state.get("privacy_profile")
    )
    next_endpoint_base_url = str(env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL") or "").strip()
    next_endpoint_model = str(env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_MODEL") or "").strip()
    next_endpoint_api_key = str(env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_API_KEY") or "").strip()

    if use_onboarding_endpoint:
        onboarding_base_url = str(state.get("onboarding_endpoint_base_url") or "").strip()
        onboarding_model = str(state.get("onboarding_endpoint_model") or "").strip()
        if not onboarding_base_url or not onboarding_model:
            raise ValueError("onboarding endpoint is not available")
        next_endpoint_base_url = onboarding_base_url
        next_endpoint_model = onboarding_model

    if endpoint_base_url is not _UNSET:
        next_endpoint_base_url = str(endpoint_base_url or "").strip()
    if endpoint_model is not _UNSET:
        next_endpoint_model = str(endpoint_model or "").strip()
    if endpoint_api_key is not _UNSET:
        next_endpoint_api_key = str(endpoint_api_key or "").strip()
    if clear_api_key:
        next_endpoint_api_key = ""
    if clear_remote_endpoint:
        next_endpoint_base_url = ""
        next_endpoint_model = ""
        next_endpoint_api_key = ""

    managed_values = {
        "AIOS_RUNTIMED_AI_ENABLED": "1" if next_provider_enabled else "0",
        "AIOS_RUNTIMED_AI_MODE": next_ai_mode,
        "AIOS_RUNTIMED_AI_PRIVACY_PROFILE": next_privacy_profile,
        "AIOS_RUNTIMED_AI_ROUTE_PREFERENCE": next_route_preference,
    }
    if next_provider_enabled and next_ai_mode in {"local", "hybrid"}:
        managed_values["AIOS_RUNTIMED_LOCAL_CPU_COMMAND"] = LOCAL_CPU_WORKER_LAUNCHER
    if next_endpoint_base_url:
        managed_values["AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL"] = next_endpoint_base_url
    if next_endpoint_model:
        managed_values["AIOS_RUNTIMED_AI_ENDPOINT_MODEL"] = next_endpoint_model
    if next_endpoint_api_key:
        managed_values["AIOS_RUNTIMED_AI_ENDPOINT_API_KEY"] = next_endpoint_api_key

    runtime_platform_env = runtime_platform_env_path or default_runtime_platform_env_path()
    write_env(runtime_platform_env, managed_values)
    return build_provider_settings_state(
        readiness_path,
        report_path,
        runtime_platform_env,
    )


def render_state(state: dict[str, Any]) -> str:
    lines = [
        f"provider_enabled: {state.get('provider_enabled')}",
        f"ai_mode: {state.get('ai_mode_label')}",
        f"route_preference: {state.get('route_preference_label')}",
        f"privacy_profile: {state.get('privacy_profile_label')}",
        f"endpoint_configured: {state.get('endpoint_configured')}",
        f"endpoint_source: {state.get('endpoint_source')}",
        f"endpoint_base_url: {state.get('endpoint_base_url') or '-'}",
        f"endpoint_model: {state.get('endpoint_model') or '-'}",
        f"endpoint_api_key: {state.get('endpoint_api_key_masked') or '-'}",
        f"runtime_platform_env: {state.get('runtime_platform_env_path')}",
        f"local_cpu_enabled: {state.get('local_cpu_enabled')}",
    ]
    for item in state.get("diagnostics", []):
        lines.append(f"diag: {item}")
    return "\n".join(lines)
