#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path
from typing import Any


RUNTIME_ROOT = Path(__file__).resolve().parent
SHELL_ROOT = RUNTIME_ROOT.parent
DEFAULT_DESKTOP_HOST = "tk"
DEFAULT_SESSION_BACKEND = "standalone"
VALID_DESKTOP_HOSTS = {"tk", "gtk"}
VALID_SESSION_BACKENDS = {"standalone", "compositor"}
VALID_NESTED_FALLBACKS = {"disabled", "standalone-gtk", "standalone-tk"}


def add_runtime_selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--desktop-host", choices=sorted(VALID_DESKTOP_HOSTS))
    parser.add_argument("--session-backend", choices=sorted(VALID_SESSION_BACKENDS))
    parser.add_argument("--compositor-manifest", type=Path)
    parser.add_argument("--compositor-config", type=Path)


def normalize_desktop_host(value: str | None) -> str:
    host = (value or DEFAULT_DESKTOP_HOST).strip().lower()
    if host not in VALID_DESKTOP_HOSTS:
        raise SystemExit(f"unsupported desktop host: {host}")
    return host


def normalize_session_backend(value: str | None) -> str:
    backend = (value or DEFAULT_SESSION_BACKEND).strip().lower()
    if backend not in VALID_SESSION_BACKENDS:
        raise SystemExit(f"unsupported session backend: {backend}")
    return backend


def normalize_nested_fallback(value: str | None, desktop_host: str) -> str:
    fallback = (value or ("standalone-gtk" if desktop_host == "gtk" else "disabled")).strip().lower()
    if fallback not in VALID_NESTED_FALLBACKS:
        raise SystemExit(f"unsupported nested fallback: {fallback}")
    return fallback


def parse_optional_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def resolve_profile_relative(profile_path: Path, value: str | Path | None, default: Path) -> Path:
    if value in (None, ""):
        return default.resolve()

    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (profile_path.parent / candidate).resolve()


def resolve_optional_profile_relative(profile_path: Path, value: str | Path | None) -> str | None:
    if value in (None, ""):
        return None

    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve())
    return str((profile_path.parent / candidate).resolve())


def build_session_plan(
    profile: dict[str, Any],
    profile_path: Path,
    args: argparse.Namespace | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    cli_host = None if args is None else getattr(args, "desktop_host", None)
    cli_backend = None if args is None else getattr(args, "session_backend", None)
    cli_manifest = None if args is None else getattr(args, "compositor_manifest", None)
    cli_config = None if args is None else getattr(args, "compositor_config", None)

    env_map = os.environ if env is None else env
    session_options = profile.get("session", {}) or {}
    desktop_host = normalize_desktop_host(
        cli_host or env_map.get("AIOS_SHELL_DESKTOP_HOST") or profile.get("desktop_host") or DEFAULT_DESKTOP_HOST
    )
    session_backend = normalize_session_backend(
        cli_backend
        or env_map.get("AIOS_SHELL_SESSION_BACKEND")
        or profile.get("session_backend")
        or DEFAULT_SESSION_BACKEND
    )

    compositor = profile.get("compositor", {}) or {}
    compositor_backend = (
        env_map.get("AIOS_SHELL_COMPOSITOR_BACKEND")
        or compositor.get("backend_mode")
        or "winit"
    )
    drm_device_path = resolve_optional_profile_relative(
        profile_path.resolve(),
        env_map.get("AIOS_SHELL_COMPOSITOR_DRM_DEVICE_PATH")
        or compositor.get("drm_device_path"),
    )
    drm_disable_connectors = parse_optional_bool(
        env_map.get("AIOS_SHELL_COMPOSITOR_DRM_DISABLE_CONNECTORS")
        if "AIOS_SHELL_COMPOSITOR_DRM_DISABLE_CONNECTORS" in env_map
        else compositor.get("drm_disable_connectors"),
        default=False,
    )
    manifest_path = resolve_profile_relative(
        profile_path.resolve(),
        cli_manifest or env_map.get("AIOS_SHELL_COMPOSITOR_MANIFEST") or compositor.get("manifest_path"),
        SHELL_ROOT / "compositor" / "Cargo.toml",
    )
    config_path = resolve_profile_relative(
        profile_path.resolve(),
        cli_config or env_map.get("AIOS_SHELL_COMPOSITOR_CONFIG") or compositor.get("config_path"),
        SHELL_ROOT / "compositor" / "default-compositor.conf",
    )

    host_entrypoint = RUNTIME_ROOT / ("shell_desktop_gtk.py" if desktop_host == "gtk" else "shell_desktop.py")
    compatibility_entrypoint = RUNTIME_ROOT / "shell_desktop.py"
    session_entrypoint = RUNTIME_ROOT / "shell_session.py"
    panel_host_bridge_entrypoint = RUNTIME_ROOT / "shell_panel_host_bridge.py"
    panel_host_service_entrypoint = RUNTIME_ROOT / "shell_panel_bridge_service.py"
    panel_clients_entrypoint = RUNTIME_ROOT / "shell_panel_clients_gtk.py"
    panel_snapshot_refresh_ticks = normalize_refresh_ticks(
        env_map.get("AIOS_SHELL_COMPOSITOR_PANEL_SNAPSHOT_REFRESH_TICKS")
        or compositor.get("panel_snapshot_refresh_ticks")
    )
    panel_action_log_path = resolve_optional_profile_relative(
        profile_path.resolve(),
        env_map.get("AIOS_SHELL_COMPOSITOR_PANEL_ACTION_LOG_PATH")
        or compositor.get("panel_action_log_path"),
    )
    runtime_lock_path = resolve_optional_profile_relative(
        profile_path.resolve(),
        env_map.get("AIOS_SHELL_COMPOSITOR_RUNTIME_LOCK_PATH")
        or compositor.get("runtime_lock_path"),
    )
    runtime_ready_path = resolve_optional_profile_relative(
        profile_path.resolve(),
        env_map.get("AIOS_SHELL_COMPOSITOR_RUNTIME_READY_PATH")
        or compositor.get("runtime_ready_path"),
    )
    runtime_state_path = resolve_optional_profile_relative(
        profile_path.resolve(),
        env_map.get("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_PATH")
        or compositor.get("runtime_state_path"),
    )
    runtime_state_refresh_ticks = normalize_refresh_ticks(
        env_map.get("AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_REFRESH_TICKS")
        or compositor.get("runtime_state_refresh_ticks")
    )
    panel_snapshot_command = None
    panel_action_command = None
    panel_service_command = None
    gtk_host_command = env_map.get("AIOS_SHELL_SESSION_GTK_HOST_COMMAND") or session_options.get(
        "gtk_host_command"
    )
    gtk_panel_client_command = env_map.get("AIOS_SHELL_SESSION_GTK_PANEL_CLIENT_COMMAND") or session_options.get(
        "gtk_panel_client_command"
    )
    nested_fallback = normalize_nested_fallback(
        env_map.get("AIOS_SHELL_NESTED_FALLBACK") or session_options.get("nested_fallback"),
        desktop_host,
    )
    compositor_required = parse_optional_bool(
        env_map.get("AIOS_SHELL_COMPOSITOR_REQUIRED")
        if "AIOS_SHELL_COMPOSITOR_REQUIRED" in env_map
        else session_options.get("compositor_required"),
        default=False,
    )
    entrypoint = (
        session_options.get("entrypoint")
        or ("formal" if desktop_host == "gtk" and session_backend == "compositor" else "compatibility")
    )
    if session_backend == "compositor":
        panel_snapshot_command = build_panel_snapshot_command(
            session_entrypoint.resolve(),
            profile_path.resolve(),
            args,
        )
        panel_action_command = build_panel_action_command(
            panel_host_bridge_entrypoint.resolve(),
            profile_path.resolve(),
            args,
        )
        panel_service_command = build_panel_service_command(
            panel_host_service_entrypoint.resolve(),
            profile_path.resolve(),
            args,
        )
        if desktop_host == "gtk" and not gtk_host_command:
            gtk_panel_client_command = gtk_panel_client_command or build_panel_client_command(
                panel_clients_entrypoint.resolve(),
                profile_path.resolve(),
                args,
            )

    if desktop_host == "gtk" and session_backend == "compositor" and gtk_panel_client_command:
        host_launch_mode = "python-gtk-panel-clients"
    elif gtk_host_command:
        host_launch_mode = "external-command"
    else:
        host_launch_mode = "python-gtk-host" if desktop_host == "gtk" else "python-tk-host"

    return {
        "profile_id": profile.get("profile_id", "unknown"),
        "entrypoint": entrypoint,
        "desktop_host": desktop_host,
        "session_backend": session_backend,
        "host_entrypoint": str(host_entrypoint.resolve()),
        "session_entrypoint": str(session_entrypoint.resolve()),
        "compatibility_entrypoint": str(compatibility_entrypoint.resolve()),
        "host_runtime": {
            "gtk_host_command": gtk_host_command,
            "gtk_panel_client_command": gtk_panel_client_command,
            "panel_clients_enabled": bool(gtk_panel_client_command),
            "host_launch_mode": host_launch_mode,
            "nested_fallback": nested_fallback,
            "compositor_required": compositor_required,
        },
        "panel_host_bridge": {
            "enabled": session_backend == "compositor" and panel_snapshot_command is not None,
            "transport": "socket-service" if session_backend == "compositor" else "disabled",
            "service_command": panel_service_command,
            "snapshot_command": panel_snapshot_command,
            "action_command": panel_action_command,
            "action_log_path": panel_action_log_path if session_backend == "compositor" else None,
            "refresh_ticks": panel_snapshot_refresh_ticks,
        },
        "compositor": {
            "backend_mode": compositor_backend,
            "env": {
                "AIOS_SHELL_COMPOSITOR_BACKEND": compositor_backend,
                "AIOS_SHELL_COMPOSITOR_DRM_DEVICE_PATH": drm_device_path,
                "AIOS_SHELL_COMPOSITOR_DRM_DISABLE_CONNECTORS": str(drm_disable_connectors).lower(),
                "AIOS_SHELL_COMPOSITOR_RUNTIME_LOCK_PATH": runtime_lock_path,
                "AIOS_SHELL_COMPOSITOR_RUNTIME_READY_PATH": runtime_ready_path,
                "AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_PATH": runtime_state_path,
                "AIOS_SHELL_COMPOSITOR_RUNTIME_STATE_REFRESH_TICKS": runtime_state_refresh_ticks,
            },
            "manifest_path": str(manifest_path),
            "config_path": str(config_path),
            "launch_command": [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                str(manifest_path),
                "--",
                "--config",
                str(config_path),
            ],
        },
}


def build_panel_snapshot_command(
    session_entrypoint: Path,
    profile_path: Path,
    args: argparse.Namespace | None,
) -> str | None:
    command = [
        sys.executable or "python3",
        str(session_entrypoint),
        "snapshot",
        "--profile",
        str(profile_path),
        "--json",
    ]
    if args is not None:
        append_snapshot_args(command, args)
    return shlex.join(command)


def build_panel_action_command(
    panel_host_bridge_entrypoint: Path,
    profile_path: Path,
    args: argparse.Namespace | None,
) -> str | None:
    command = [
        sys.executable or "python3",
        str(panel_host_bridge_entrypoint),
        "--profile",
        str(profile_path),
    ]
    if args is not None:
        append_snapshot_args(command, args)
    return shlex.join(command)


def build_panel_service_command(
    panel_host_service_entrypoint: Path,
    profile_path: Path,
    args: argparse.Namespace | None,
) -> str | None:
    command = [
        sys.executable or "python3",
        str(panel_host_service_entrypoint),
        "--profile",
        str(profile_path),
    ]
    if args is not None:
        append_snapshot_args(command, args)
    return shlex.join(command)


def build_panel_client_command(
    panel_clients_entrypoint: Path,
    profile_path: Path,
    args: argparse.Namespace | None,
) -> str | None:
    command = [
        sys.executable or "python3",
        str(panel_clients_entrypoint),
        "serve",
        "--profile",
        str(profile_path),
    ]
    if args is not None:
        append_snapshot_args(command, args)
    return shlex.join(command)


def append_snapshot_args(command: list[str], args: argparse.Namespace) -> None:
    string_fields = [
        ("session_id", "--session-id"),
        ("task_id", "--task-id"),
        ("user_id", "--user-id"),
        ("intent", "--intent"),
        ("title", "--title"),
        ("task_state", "--task-state"),
        ("task_state_filter", "--task-state-filter"),
        ("status_filter", "--status-filter"),
        ("tone_filter", "--tone-filter"),
    ]
    for field_name, flag in string_fields:
        value = getattr(args, field_name, None)
        if value not in (None, ""):
            command.extend([flag, str(value)])

    integer_fields = [("limit", "--limit")]
    for field_name, flag in integer_fields:
        value = getattr(args, field_name, None)
        if value is not None:
            command.extend([flag, str(value)])

    path_fields = [
        ("launcher_fixture", "--launcher-fixture"),
        ("task_fixture", "--task-fixture"),
        ("approval_fixture", "--approval-fixture"),
        ("chooser_fixture", "--chooser-fixture"),
    ]
    for field_name, flag in path_fields:
        value = getattr(args, field_name, None)
        if value is not None:
            command.extend([flag, str(Path(value).expanduser().resolve())])

    if getattr(args, "include_disabled", False):
        command.append("--include-disabled")

    for surface in getattr(args, "surfaces", []) or []:
        if surface not in (None, ""):
            command.extend(["--surface", str(surface)])


def normalize_refresh_ticks(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 10
    return max(1, parsed)


def render_session_plan(plan: dict[str, Any]) -> str:
    compositor = plan["compositor"]
    host_runtime = plan["host_runtime"]
    panel_host_bridge = plan["panel_host_bridge"]
    lines = [
        f"profile_id: {plan['profile_id']}",
        f"entrypoint: {plan['entrypoint']}",
        f"desktop_host: {plan['desktop_host']}",
        f"session_backend: {plan['session_backend']}",
        f"host_entrypoint: {plan['host_entrypoint']}",
        f"session_entrypoint: {plan['session_entrypoint']}",
        f"compatibility_entrypoint: {plan['compatibility_entrypoint']}",
        f"host_launch_mode: {host_runtime['host_launch_mode']}",
        f"nested_fallback: {host_runtime['nested_fallback']}",
        f"compositor_required: {host_runtime['compositor_required']}",
        f"panel_host_bridge_enabled: {panel_host_bridge['enabled']}",
        f"panel_host_bridge_transport: {panel_host_bridge['transport']}",
        f"panel_snapshot_refresh_ticks: {panel_host_bridge['refresh_ticks']}",
        f"compositor_backend: {compositor['backend_mode']}",
        f"compositor_manifest: {compositor['manifest_path']}",
        f"compositor_config: {compositor['config_path']}",
        "compositor_launch: " + " ".join(compositor["launch_command"]),
    ]
    if compositor["env"].get("AIOS_SHELL_COMPOSITOR_DRM_DEVICE_PATH"):
        lines.append(
            "drm_device_path: " + compositor["env"]["AIOS_SHELL_COMPOSITOR_DRM_DEVICE_PATH"]
        )
    if host_runtime["gtk_host_command"]:
        lines.append("gtk_host_command: " + host_runtime["gtk_host_command"])
    if host_runtime.get("gtk_panel_client_command"):
        lines.append("gtk_panel_client_command: " + host_runtime["gtk_panel_client_command"])
    if panel_host_bridge["snapshot_command"]:
        lines.append("panel_snapshot_command: " + panel_host_bridge["snapshot_command"])
    if panel_host_bridge.get("service_command"):
        lines.append("panel_service_command: " + panel_host_bridge["service_command"])
    if panel_host_bridge["action_command"]:
        lines.append("panel_action_command: " + panel_host_bridge["action_command"])
    if panel_host_bridge["action_log_path"]:
        lines.append("panel_action_log_path: " + panel_host_bridge["action_log_path"])
    return "\n".join(lines)
