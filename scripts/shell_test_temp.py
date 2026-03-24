#!/usr/bin/env python3
from __future__ import annotations

import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = (
    Path("/tmp")
    if os.name != "nt" and Path("/tmp").exists()
    else ROOT / ".tmp"
)


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def set_session_temp_root() -> str | None:
    previous = os.environ.get("AIOS_SHELL_SESSION_TEMP_ROOT")
    os.environ["AIOS_SHELL_SESSION_TEMP_ROOT"] = str(TEMP_ROOT_DIR.resolve())
    return previous


def restore_session_temp_root(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("AIOS_SHELL_SESSION_TEMP_ROOT", None)
    else:
        os.environ["AIOS_SHELL_SESSION_TEMP_ROOT"] = previous
