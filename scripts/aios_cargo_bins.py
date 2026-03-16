from __future__ import annotations

import os
import platform
import subprocess
from functools import lru_cache
from pathlib import Path


EXPECTED_AIOS_BINARIES = [
    "agentd",
    "sessiond",
    "policyd",
    "runtimed",
    "deviced",
    "updated",
    "device-metadata-provider",
    "runtime-local-inference-provider",
    "system-intent-provider",
    "system-files-provider",
]


def cargo_target_bin_dir(root: Path, target: str | None) -> Path:
    aios_root = root / "aios"
    target_dir = Path(os.environ.get("CARGO_TARGET_DIR", aios_root / "target"))
    if target:
        return target_dir / target / "debug"
    return target_dir / "debug"


def default_container_native_bin_dir(root: Path) -> Path:
    override = os.environ.get("AIOS_DELIVERY_CACHED_BIN_DIR")
    if override:
        return Path(override)
    return root / "out" / "aios-delivery-container-target" / "debug"


def expected_aios_binaries() -> list[str]:
    return list(EXPECTED_AIOS_BINARIES)


def binary_artifact_name(name: str) -> str:
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name


def resolve_binary_path(bin_dir: Path, name: str) -> Path:
    direct = bin_dir / name
    if direct.exists():
        return direct

    artifact = bin_dir / binary_artifact_name(name)
    if artifact.exists():
        return artifact

    return artifact if artifact != direct else direct


def has_expected_aios_binaries(bin_dir: Path) -> bool:
    return all(resolve_binary_path(bin_dir, name).exists() for name in EXPECTED_AIOS_BINARIES)


def default_aios_bin_dir(root: Path) -> Path:
    explicit_target = os.environ.get("CARGO_BUILD_TARGET")
    aios_root = root / "aios"
    host_target = detect_host_target(aios_root)

    candidates: list[Path] = []
    # Default host builds land in target/debug; only prefer target/<triple>/debug
    # when the caller explicitly asked Cargo to build for a target triple.
    if explicit_target:
        candidates.append(cargo_target_bin_dir(root, explicit_target))
        candidates.append(cargo_target_bin_dir(root, None))
    else:
        candidates.append(cargo_target_bin_dir(root, None))
        if host_target:
            candidates.append(cargo_target_bin_dir(root, host_target))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


@lru_cache(maxsize=1)
def detect_host_target(aios_root: Path) -> str | None:
    explicit = os.environ.get("CARGO_BUILD_TARGET")
    if explicit:
        return explicit

    try:
        completed = subprocess.run(
            ["rustc", "-vV"],
            cwd=aios_root,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        completed = None

    if completed and completed.returncode == 0:
        for line in completed.stdout.splitlines():
            if line.startswith("host: "):
                return line.split(": ", 1)[1].strip()

    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine == "arm64":
        machine = "aarch64"

    if system == "darwin":
        return f"{machine}-apple-darwin"
    if system == "linux":
        return f"{machine}-unknown-linux-gnu"

    return None
