#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


def parse_embedded_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return payload

    for index, char in enumerate(stripped):
        if char != "{":
            continue
        candidate = stripped[index:]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _existing_path(candidate: str | Path | None) -> Path | None:
    if candidate is None:
        return None
    path = Path(candidate).expanduser()
    return path if path.exists() else None


def _looks_like_wsl_bash_shim(path: Path) -> bool:
    normalized = str(path).lower()
    return normalized.endswith("\\system32\\bash.exe") or "windowsapps\\bash.exe" in normalized


def resolve_bash_binary() -> Path | None:
    override = _existing_path(os.environ.get("AIOS_BASH_BIN"))
    if override is not None:
        return override

    if os.name != "nt":
        resolved = shutil.which("bash")
        return Path(resolved) if resolved else None

    candidates: list[Path] = []
    for env_name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        program_root = os.environ.get(env_name)
        if not program_root:
            continue
        root = Path(program_root)
        candidates.extend(
            [
                root / "Git" / "bin" / "bash.exe",
                root / "Git" / "usr" / "bin" / "bash.exe",
            ]
        )
    candidates.extend(
        [
            Path("C:/msys64/usr/bin/bash.exe"),
            Path("C:/tools/msys64/usr/bin/bash.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    for command in ("bash.exe", "bash"):
        resolved = shutil.which(command)
        if not resolved:
            continue
        candidate = Path(resolved)
        if not _looks_like_wsl_bash_shim(candidate):
            return candidate
    return None


def bash_path(path: Path | str) -> str:
    if os.name != "nt":
        return str(path)
    resolved = Path(path).expanduser().resolve()
    drive = resolved.drive.rstrip(":").lower()
    if drive:
        return f"/{drive}{resolved.as_posix()[2:]}"
    return resolved.as_posix()


def bash_command(script: Path, *args: str | Path) -> list[str]:
    bash_binary = resolve_bash_binary()
    if bash_binary is None:
        raise RuntimeError(f"usable bash runtime unavailable for script: {script}")
    rendered_args = [bash_path(item) if isinstance(item, Path) else str(item) for item in args]
    return [str(bash_binary), bash_path(script), *rendered_args]


def prepend_binary_parent_to_path(env: dict[str, str], binary: Path | None) -> None:
    if binary is None:
        return
    parent = str(binary.parent)
    current = env.get("PATH", "")
    parts = [item for item in current.split(os.pathsep) if item]
    normalized_parent = parent.lower()
    if normalized_parent in {item.lower() for item in parts}:
        return
    env["PATH"] = os.pathsep.join([parent, *parts]) if parts else parent


def resolve_qemu_binary() -> Path | None:
    override = _existing_path(os.environ.get("AIOS_QEMU_BIN"))
    if override is not None:
        return override

    for command in ("qemu-system-x86_64", "qemu-system-x86_64.exe"):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)

    if os.name != "nt":
        return None

    candidates: list[Path] = []
    for env_name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        program_root = os.environ.get(env_name)
        if not program_root:
            continue
        root = Path(program_root)
        candidates.extend(
            [
                root / "qemu" / "qemu-system-x86_64.exe",
                root / "QEMU" / "qemu-system-x86_64.exe",
            ]
        )
    candidates.extend(
        [
            Path("C:/ProgramData/chocolatey/bin/qemu-system-x86_64.exe"),
            Path("C:/msys64/mingw64/bin/qemu-system-x86_64.exe"),
            Path("C:/tools/msys64/mingw64/bin/qemu-system-x86_64.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
