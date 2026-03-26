#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from aios_cargo_bins import cargo_target_bin_dir, default_aios_bin_dir, resolve_binary_path


ROOT = Path(__file__).resolve().parent.parent
AIOS_ROOT = ROOT / "aios"
DEFAULT_OUTPUT_DIR = ROOT / "out" / "aios-system-delivery"

COMPONENTS = [
    {
        "component_id": "aios-sessiond",
        "kind": "service",
        "package": "aios-sessiond",
        "binary": "sessiond",
        "unit": AIOS_ROOT / "services" / "sessiond" / "units" / "aios-sessiond.service",
        "metadata": AIOS_ROOT / "services" / "sessiond" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-policyd",
        "kind": "service",
        "package": "aios-policyd",
        "binary": "policyd",
        "unit": AIOS_ROOT / "services" / "policyd" / "units" / "aios-policyd.service",
        "metadata": AIOS_ROOT / "services" / "policyd" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-runtimed",
        "kind": "service",
        "package": "aios-runtimed",
        "binary": "runtimed",
        "unit": AIOS_ROOT / "services" / "runtimed" / "units" / "aios-runtimed.service",
        "metadata": AIOS_ROOT / "services" / "runtimed" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-agentd",
        "kind": "service",
        "package": "aios-agentd",
        "binary": "agentd",
        "unit": AIOS_ROOT / "services" / "agentd" / "units" / "aios-agentd.service",
        "metadata": AIOS_ROOT / "services" / "agentd" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-deviced",
        "kind": "service",
        "package": "aios-deviced",
        "binary": "deviced",
        "unit": AIOS_ROOT / "services" / "deviced" / "units" / "aios-deviced.service",
        "metadata": AIOS_ROOT / "services" / "deviced" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-updated",
        "kind": "service",
        "package": "aios-updated",
        "binary": "updated",
        "unit": AIOS_ROOT / "services" / "updated" / "units" / "aios-updated.service",
        "metadata": AIOS_ROOT / "services" / "updated" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-device-metadata-provider",
        "kind": "provider",
        "package": "aios-device-metadata-provider",
        "binary": "device-metadata-provider",
        "unit": AIOS_ROOT / "providers" / "device-metadata" / "units" / "aios-device-metadata-provider.service",
        "metadata": AIOS_ROOT / "providers" / "device-metadata" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-runtime-local-inference-provider",
        "kind": "provider",
        "package": "aios-runtime-local-inference-provider",
        "binary": "runtime-local-inference-provider",
        "unit": AIOS_ROOT / "providers" / "runtime-local-inference" / "units" / "aios-runtime-local-inference-provider.service",
        "metadata": AIOS_ROOT / "providers" / "runtime-local-inference" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-system-intent-provider",
        "kind": "provider",
        "package": "aios-system-intent-provider",
        "binary": "system-intent-provider",
        "unit": AIOS_ROOT / "providers" / "system-intent" / "units" / "aios-system-intent-provider.service",
        "metadata": AIOS_ROOT / "providers" / "system-intent" / "service.yaml",
        "enabled": True,
    },
    {
        "component_id": "aios-system-files-provider",
        "kind": "provider",
        "package": "aios-system-files-provider",
        "binary": "system-files-provider",
        "unit": AIOS_ROOT / "providers" / "system-files" / "units" / "aios-system-files-provider.service",
        "metadata": AIOS_ROOT / "providers" / "system-files" / "service.yaml",
        "enabled": True,
    },
]

CONFIG_MAPPINGS = [
    (AIOS_ROOT / "policy" / "profiles" / "default-policy.yaml", "etc/aios/policy/default-policy.yaml"),
    (AIOS_ROOT / "policy" / "capabilities" / "default-capability-catalog.yaml", "etc/aios/policy/default-capability-catalog.yaml"),
    (AIOS_ROOT / "runtime" / "profiles" / "default-runtime-profile.yaml", "etc/aios/runtime/default-runtime-profile.yaml"),
    (AIOS_ROOT / "runtime" / "profiles" / "default-route-profile.yaml", "etc/aios/runtime/default-route-profile.yaml"),
    (AIOS_ROOT / "shell" / "profiles" / "default-shell-profile.yaml", "etc/aios/shell/default-shell-profile.yaml"),
    (AIOS_ROOT / "shell" / "profiles" / "formal-shell-profile.yaml", "etc/aios/shell/formal-shell-profile.yaml"),
    (AIOS_ROOT / "shell" / "profiles" / "release-shell-profile.yaml", "etc/aios/shell/release-shell-profile.yaml"),
]

DESCRIPTOR_DIRECTORIES = [
    AIOS_ROOT / "sdk" / "providers",
    AIOS_ROOT / "runtime" / "providers",
    AIOS_ROOT / "shell" / "providers",
    AIOS_ROOT / "compat" / "browser" / "providers",
    AIOS_ROOT / "compat" / "office" / "providers",
    AIOS_ROOT / "compat" / "mcp-bridge" / "providers",
    AIOS_ROOT / "compat" / "code-sandbox" / "providers",
]

COMPAT_RUNTIME_DIRECTORIES = [
    (AIOS_ROOT / "compat" / "browser" / "runtime", "browser"),
    (AIOS_ROOT / "compat" / "office" / "runtime", "office"),
    (AIOS_ROOT / "compat" / "mcp-bridge" / "runtime", "mcp-bridge"),
    (AIOS_ROOT / "compat" / "code-sandbox" / "runtime", "code-sandbox"),
]

SCHEMA_DIRECTORIES = [
    AIOS_ROOT / "image" / "schemas",
    AIOS_ROOT / "hardware" / "schemas",
    AIOS_ROOT / "sdk" / "schemas",
    AIOS_ROOT / "policy" / "schemas",
    AIOS_ROOT / "runtime" / "schemas",
    AIOS_ROOT / "observability" / "schemas",
    AIOS_ROOT / "services" / "updated" / "schemas",
]

IMAGE_ASSETS = [
    (AIOS_ROOT / "image" / "mkosi.conf", "image/mkosi.conf"),
    (AIOS_ROOT / "image" / "boot", "image/boot"),
    (AIOS_ROOT / "image" / "firstboot", "image/firstboot"),
    (AIOS_ROOT / "image" / "recovery", "image/recovery"),
    (AIOS_ROOT / "image" / "installer", "image/installer"),
    (AIOS_ROOT / "image" / "repart.d", "image/repart.d"),
    (AIOS_ROOT / "image" / "sysupdate.d", "image/sysupdate.d"),
    (AIOS_ROOT / "image" / "profiles", "image/profiles"),
    (AIOS_ROOT / "image" / "platforms", "image/platforms"),
    (AIOS_ROOT / "hardware" / "profiles", "image/hardware-profiles"),
    (ROOT / "scripts" / "boot-qemu.sh", "image/scripts/boot-qemu.sh"),
    (ROOT / "scripts" / "build-aios-image.sh", "image/scripts/build-aios-image.sh"),
    (ROOT / "scripts" / "build-aios-recovery-image.sh", "image/scripts/build-aios-recovery-image.sh"),
    (ROOT / "scripts" / "build-aios-installer-image.sh", "image/scripts/build-aios-installer-image.sh"),
    (ROOT / "scripts" / "install-aios-system.py", "image/scripts/install-aios-system.py"),
    (ROOT / "scripts" / "sync-aios-image-overlay.sh", "image/scripts/sync-aios-image-overlay.sh"),
]

TMPFILES_SOURCE = AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "lib" / "tmpfiles.d" / "aios.conf"
TASK_SYNC_SCRIPT = ROOT / "scripts" / "sync-aios-task-metadata.py"
UPDATED_PLATFORM_SOURCE = AIOS_ROOT / "services" / "updated" / "platforms"
RUNTIME_PLATFORM_SOURCE = AIOS_ROOT / "runtime" / "platforms"
HARDWARE_EVIDENCE_SOURCE = AIOS_ROOT / "hardware" / "evidence"

BOOT_ROOTFS_MAPPINGS = [
    (AIOS_ROOT / "image" / "boot" / "loader" / "loader.conf", "usr/share/aios/boot/loader/loader.conf"),
    (AIOS_ROOT / "image" / "boot" / "kernel-command-line.txt", "usr/share/aios/boot/kernel-command-line.txt"),
]

FIRSTBOOT_ROOTFS_MAPPINGS = [
    (AIOS_ROOT / "image" / "firstboot" / "aios-firstboot.service", "usr/lib/systemd/system/aios-firstboot.service"),
    (AIOS_ROOT / "image" / "firstboot" / "aios-firstboot.sh", "usr/libexec/aios/aios-firstboot.sh"),
    (AIOS_ROOT / "image" / "firstboot" / "aios-ai-onboarding.service", "usr/lib/systemd/system/aios-ai-onboarding.service"),
    (AIOS_ROOT / "image" / "firstboot" / "aios-ai-onboarding.sh", "usr/libexec/aios/aios-ai-onboarding.sh"),
    (AIOS_ROOT / "image" / "firstboot" / "aios-firstboot.env", "etc/aios/firstboot/aios-firstboot.env"),
]

RUNTIME_ROOTFS_MAPPINGS = [
    (AIOS_ROOT / "runtime" / "model_manager.py", "usr/libexec/aios/runtime/model_manager.py"),
    (AIOS_ROOT / "runtime" / "recommended-model-catalog.yaml", "usr/libexec/aios/runtime/recommended-model-catalog.yaml"),
    (AIOS_ROOT / "runtime" / "workers" / "local_cpu_worker.py", "usr/libexec/aios/runtime/workers/local_cpu_worker.py"),
    (AIOS_ROOT / "runtime" / "workers" / "launch_local_cpu_worker.sh", "usr/libexec/aios/runtime/workers/launch_local_cpu_worker.sh"),
]

RECOVERY_ROOTFS_MAPPINGS = [
    (AIOS_ROOT / "image" / "recovery" / "aios-recovery.target", "usr/lib/systemd/system/aios-recovery.target"),
    (AIOS_ROOT / "image" / "recovery" / "aios-recovery-shell.service", "usr/lib/systemd/system/aios-recovery-shell.service"),
    (AIOS_ROOT / "image" / "recovery" / "aios-recovery-report.sh", "usr/libexec/aios/aios-recovery-report.sh"),
    (AIOS_ROOT / "image" / "recovery" / "profile.yaml", "usr/share/aios/recovery/profile.yaml"),
]

INSTALLER_ROOTFS_MAPPINGS = [
    (AIOS_ROOT / "image" / "installer" / "aios-installer.target", "usr/lib/systemd/system/aios-installer.target"),
    (AIOS_ROOT / "image" / "installer" / "aios-installer.service", "usr/lib/systemd/system/aios-installer.service"),
    (AIOS_ROOT / "image" / "installer" / "kernel-command-line.txt", "usr/share/aios/installer/kernel-command-line.txt"),
    (AIOS_ROOT / "image" / "installer" / "aios-installer-run.sh", "usr/libexec/aios/aios-installer-run.sh"),
    (AIOS_ROOT / "image" / "installer" / "aios-installer-guided.sh", "usr/libexec/aios/aios-installer-guided.sh"),
    (AIOS_ROOT / "image" / "installer" / "aios-installer.env", "etc/aios/installer/aios-installer.env"),
    (AIOS_ROOT / "image" / "installer" / "profile.yaml", "usr/share/aios/installer/profile.yaml"),
]

INSTALLER_ROOTFS_TREES = [
    (AIOS_ROOT / "image" / "installer" / "ui", "usr/share/aios/installer/ui"),
]

HARDWARE_EVIDENCE_ROOTFS_MAPPINGS = [
    (HARDWARE_EVIDENCE_SOURCE / "aios-boot-evidence.service", "usr/lib/systemd/system/aios-boot-evidence.service"),
    (HARDWARE_EVIDENCE_SOURCE / "aios-boot-evidence.sh", "usr/libexec/aios/aios-boot-evidence.sh"),
]

MASKED_SYSTEMD_UNITS = ["systemd-firstboot.service"]
HOST_LINK_PLACEHOLDER_PREFIX = "aios-host-link-target:"


def write_symlink_or_placeholder(path: Path, target: Path | str) -> str:
    target_text = str(target)
    if path.exists() or path.is_symlink():
        path.unlink()
    try:
        path.symlink_to(Path(target_text))
    except OSError as error:
        if os.name != "nt" or getattr(error, "winerror", None) != 1314:
            raise
        path.write_text(f"{HOST_LINK_PLACEHOLDER_PREFIX}{target_text}\n")
    return target_text


def read_symlink_or_placeholder(path: Path) -> str | None:
    if path.is_symlink():
        return os.readlink(path)
    if path.is_file():
        try:
            payload = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            return None
        if payload.startswith(HOST_LINK_PLACEHOLDER_PREFIX):
            return payload[len(HOST_LINK_PLACEHOLDER_PREFIX):]
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AIOS system delivery bundle")
    parser.add_argument(
        "--bin-dir",
        type=Path,
        help="Directory containing compiled AIOS binaries",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for the assembled delivery bundle",
    )
    parser.add_argument(
        "--sync-overlay",
        type=Path,
        help="Optional mkosi.extra target to refresh from the generated rootfs overlay",
    )
    parser.add_argument(
        "--build-missing",
        action="store_true",
        help="Build missing binaries before assembling the bundle",
    )
    parser.add_argument(
        "--cargo-target",
        help="Optional cargo target triple to use when --build-missing compiles binaries",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip creating a tar.gz archive next to the output directory",
    )
    args = parser.parse_args()
    if args.bin_dir is None:
        args.bin_dir = (
            cargo_target_bin_dir(ROOT, args.cargo_target)
            if args.cargo_target
            else default_aios_bin_dir(ROOT)
        )
    return args


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_task_metadata() -> None:
    completed = subprocess.run(
        [sys.executable, str(TASK_SYNC_SCRIPT)],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or "failed to sync AIOS task metadata")


def resolve_git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def ensure_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | 0o111)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)

    def ignore(_current: str, names: list[str]) -> set[str]:
        ignored = {"__pycache__"}
        ignored.update(name for name in names if name.endswith(".pyc"))
        return ignored

    shutil.copytree(source, destination, ignore=ignore)


def ensure_binaries(bin_dir: Path, build_missing: bool, cargo_target: str | None = None) -> list[Path]:
    missing = [
        component
        for component in COMPONENTS
        if not resolve_binary_path(bin_dir, component["binary"]).exists()
    ]
    if missing and build_missing:
        packages = [component["package"] for component in missing]
        command = ["cargo", "build"]
        if cargo_target:
            command.extend(["--target", cargo_target])
        command.extend(sum([["-p", package] for package in packages], []))
        run(command, cwd=AIOS_ROOT)
        missing = [
            component
            for component in COMPONENTS
            if not resolve_binary_path(bin_dir, component["binary"]).exists()
        ]

    if missing:
        missing_lines = ", ".join(sorted(component["binary"] for component in missing))
        raise SystemExit(f"missing binaries in {bin_dir}: {missing_lines}")

    return [resolve_binary_path(bin_dir, component["binary"]) for component in COMPONENTS]


def create_unit_wants(rootfs_dir: Path, unit_name: str) -> None:
    wants_dir = rootfs_dir / "usr" / "lib" / "systemd" / "system" / "multi-user.target.wants"
    wants_dir.mkdir(parents=True, exist_ok=True)
    target = wants_dir / unit_name
    if target.exists() or target.is_symlink():
        target.unlink()
    write_symlink_or_placeholder(target, Path("..") / unit_name)


def mask_systemd_unit(rootfs_dir: Path, unit_name: str) -> str:
    mask_path = rootfs_dir / "etc" / "systemd" / "system" / unit_name
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    if mask_path.exists() or mask_path.is_symlink():
        mask_path.unlink()
    write_symlink_or_placeholder(mask_path, "/dev/null")
    return mask_path.relative_to(rootfs_dir).as_posix()


def generate_systemd_preset(rootfs_dir: Path, extra_units: list[str] | None = None) -> list[str]:
    preset_path = rootfs_dir / "usr" / "lib" / "systemd" / "system-preset" / "90-aios.preset"
    preset_path.parent.mkdir(parents=True, exist_ok=True)
    unit_names = [component["unit"].name for component in COMPONENTS if component["enabled"]]
    unit_names.extend(extra_units or [])
    unit_names = sorted(dict.fromkeys(unit_names))
    preset_path.write_text("\n".join(f"enable {unit}" for unit in unit_names) + "\n")
    return unit_names


def prepare_firstboot_hygiene(rootfs_dir: Path) -> dict[str, object]:
    machine_id_path = rootfs_dir / "etc" / "machine-id"
    machine_id_path.parent.mkdir(parents=True, exist_ok=True)
    if machine_id_path.is_symlink():
        machine_id_path.unlink()
    machine_id_path.write_text("")

    dbus_machine_id_path = rootfs_dir / "var" / "lib" / "dbus" / "machine-id"
    dbus_machine_id_path.parent.mkdir(parents=True, exist_ok=True)
    if dbus_machine_id_path.exists() or dbus_machine_id_path.is_symlink():
        dbus_machine_id_path.unlink()
    write_symlink_or_placeholder(dbus_machine_id_path, "/etc/machine-id")

    random_seed_path = rootfs_dir / "var" / "lib" / "systemd" / "random-seed"
    random_seed_path.parent.mkdir(parents=True, exist_ok=True)
    if random_seed_path.exists() or random_seed_path.is_symlink():
        random_seed_path.unlink()

    return {
        "machine_id": machine_id_path.relative_to(rootfs_dir).as_posix(),
        "machine_id_state": "empty-file",
        "dbus_machine_id": dbus_machine_id_path.relative_to(rootfs_dir).as_posix(),
        "dbus_machine_id_target": read_symlink_or_placeholder(dbus_machine_id_path),
        "random_seed": random_seed_path.relative_to(rootfs_dir).as_posix(),
        "random_seed_present": False,
    }


def sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def collect_file_manifest(bundle_dir: Path, *, exclude: set[str] | None = None) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    excluded = exclude or set()
    for path in sorted(bundle_dir.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(bundle_dir).as_posix()
        if relative in excluded:
            continue
        link_target = read_symlink_or_placeholder(path)
        if link_target is not None:
            records.append(
                {
                    "path": relative,
                    "type": "symlink",
                    "target": link_target,
                }
            )
            continue
        records.append(
            {
                "path": relative,
                "type": "file",
                "sha256": sha256_for_path(path),
            }
        )
    return records


def sync_overlay_source_assets(overlay_dir: Path) -> None:
    copy_tree(
        RUNTIME_PLATFORM_SOURCE,
        overlay_dir / "usr" / "share" / "aios" / "runtime" / "platforms",
    )
    shell_compositor_overlay = overlay_dir / "usr" / "libexec" / "aios-shell" / "compositor"
    copy_tree(AIOS_ROOT / "shell" / "compositor" / "src", shell_compositor_overlay / "src")
    for name in ["Cargo.toml", "Cargo.lock", "default-compositor.conf", "release-compositor.conf"]:
        copy_file(AIOS_ROOT / "shell" / "compositor" / name, shell_compositor_overlay / name)


def sync_overlay(rootfs_dir: Path, overlay_dir: Path) -> None:
    if overlay_dir.exists():
        shutil.rmtree(overlay_dir)
    shutil.copytree(rootfs_dir, overlay_dir, symlinks=True)
    sync_overlay_source_assets(overlay_dir)


def write_manifest(bundle_dir: Path, payload: dict[str, object]) -> Path:
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return manifest_path


def create_archive(bundle_dir: Path) -> Path:
    archive_path = bundle_dir.parent / f"{bundle_dir.name}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(bundle_dir, arcname=bundle_dir.name, recursive=True)
    return archive_path


def stage_rootfs(bundle_dir: Path, bin_dir: Path) -> dict[str, object]:
    rootfs_dir = bundle_dir / "rootfs"
    if rootfs_dir.exists():
        shutil.rmtree(rootfs_dir)
    rootfs_dir.mkdir(parents=True, exist_ok=True)

    copy_file(TMPFILES_SOURCE, rootfs_dir / "usr" / "lib" / "tmpfiles.d" / "aios.conf")

    for source, relative in CONFIG_MAPPINGS:
        copy_file(source, rootfs_dir / relative)

    sysupdate_dir = rootfs_dir / "etc" / "systemd" / "sysupdate.d"
    sysupdate_dir.mkdir(parents=True, exist_ok=True)
    for entry in sorted((AIOS_ROOT / "image" / "sysupdate.d").iterdir()):
        if entry.is_file():
            copy_file(entry, sysupdate_dir / entry.name)

    boot_assets: list[str] = []
    for source, relative in BOOT_ROOTFS_MAPPINGS:
        destination = rootfs_dir / relative
        copy_file(source, destination)
        boot_assets.append(destination.relative_to(rootfs_dir).as_posix())

    firstboot_assets: dict[str, str] = {}
    for source, relative in FIRSTBOOT_ROOTFS_MAPPINGS:
        destination = rootfs_dir / relative
        copy_file(source, destination)
        if destination.suffix == ".sh":
            ensure_executable(destination)
        firstboot_assets[source.name] = destination.relative_to(rootfs_dir).as_posix()
    create_unit_wants(rootfs_dir, "aios-firstboot.service")
    create_unit_wants(rootfs_dir, "aios-ai-onboarding.service")

    runtime_assets: dict[str, str] = {}
    for source, relative in RUNTIME_ROOTFS_MAPPINGS:
        destination = rootfs_dir / relative
        copy_file(source, destination)
        if destination.suffix in {".sh", ".py"}:
            ensure_executable(destination)
        runtime_assets[source.name] = destination.relative_to(rootfs_dir).as_posix()
    masked_units = [mask_systemd_unit(rootfs_dir, unit_name) for unit_name in MASKED_SYSTEMD_UNITS]
    firstboot_hygiene = prepare_firstboot_hygiene(rootfs_dir)

    recovery_assets: dict[str, str] = {}
    for source, relative in RECOVERY_ROOTFS_MAPPINGS:
        destination = rootfs_dir / relative
        copy_file(source, destination)
        if destination.suffix == ".sh":
            ensure_executable(destination)
        recovery_assets[source.name] = destination.relative_to(rootfs_dir).as_posix()

    installer_assets: dict[str, str] = {}
    for source, relative in INSTALLER_ROOTFS_MAPPINGS:
        destination = rootfs_dir / relative
        copy_file(source, destination)
        if destination.suffix == ".sh":
            ensure_executable(destination)
        installer_assets[source.name] = destination.relative_to(rootfs_dir).as_posix()
    for source, relative in INSTALLER_ROOTFS_TREES:
        destination = rootfs_dir / relative
        copy_tree(source, destination)
        for entry in sorted(destination.rglob("*")):
            if entry.is_file():
                installer_assets[entry.name] = entry.relative_to(rootfs_dir).as_posix()

    hardware_evidence_assets: dict[str, str] = {}
    for source, relative in HARDWARE_EVIDENCE_ROOTFS_MAPPINGS:
        destination = rootfs_dir / relative
        copy_file(source, destination)
        if destination.suffix == ".sh":
            ensure_executable(destination)
        hardware_evidence_assets[source.name] = destination.relative_to(rootfs_dir).as_posix()
    create_unit_wants(rootfs_dir, "aios-boot-evidence.service")

    updated_platform_files: list[str] = []
    if UPDATED_PLATFORM_SOURCE.exists():
        share_root = rootfs_dir / "usr" / "share" / "aios" / "updated" / "platforms"
        libexec_root = rootfs_dir / "usr" / "libexec" / "aios-platform"
        for platform_dir in sorted(UPDATED_PLATFORM_SOURCE.iterdir()):
            if not platform_dir.is_dir():
                continue
            share_source = platform_dir / "share"
            if share_source.exists():
                destination = share_root / platform_dir.name
                copy_tree(share_source, destination)
                for entry in sorted(destination.rglob("*")):
                    if entry.is_file():
                        updated_platform_files.append(entry.relative_to(rootfs_dir).as_posix())
            libexec_source = platform_dir / "libexec"
            if libexec_source.exists():
                destination = libexec_root / platform_dir.name
                copy_tree(libexec_source, destination)
                for entry in sorted(destination.rglob("*")):
                    if entry.is_file():
                        if entry.suffix == ".sh":
                            ensure_executable(entry)
                        updated_platform_files.append(entry.relative_to(rootfs_dir).as_posix())

        default_platform_env = UPDATED_PLATFORM_SOURCE / "qemu-x86_64" / "share" / "platform.env"
        if default_platform_env.exists():
            copy_file(default_platform_env, rootfs_dir / "etc" / "aios" / "updated" / "platform.env")
            updated_platform_files.append("etc/aios/updated/platform.env")

    runtime_platform_files: list[str] = []
    if RUNTIME_PLATFORM_SOURCE.exists():
        runtime_platform_root = rootfs_dir / "usr" / "share" / "aios" / "runtime" / "platforms"
        for platform_dir in sorted(RUNTIME_PLATFORM_SOURCE.iterdir()):
            if not platform_dir.is_dir():
                continue
            destination = runtime_platform_root / platform_dir.name
            copy_tree(platform_dir, destination)
            for entry in sorted(destination.rglob("*")):
                if entry.is_file():
                    if entry.suffix == ".sh":
                        ensure_executable(entry)
                    runtime_platform_files.append(entry.relative_to(rootfs_dir).as_posix())

    component_records = []
    for component in COMPONENTS:
        binary_source = resolve_binary_path(bin_dir, component["binary"])
        binary_destination = rootfs_dir / "usr" / "libexec" / "aios" / component["binary"]
        metadata_name = f"{component['component_id']}.yaml"
        copy_file(binary_source, binary_destination)
        copy_file(component["unit"], rootfs_dir / "usr" / "lib" / "systemd" / "system" / component["unit"].name)
        copy_file(
            component["metadata"],
            rootfs_dir
            / "usr"
            / "share"
            / "aios"
            / "component-metadata"
            / component["kind"]
            / metadata_name,
        )
        if component["enabled"]:
            create_unit_wants(rootfs_dir, component["unit"].name)
        component_records.append(
            {
                "component_id": component["component_id"],
                "kind": component["kind"],
                "package": component["package"],
                "binary_path": binary_destination.relative_to(rootfs_dir).as_posix(),
                "unit_path": (Path("usr/lib/systemd/system") / component["unit"].name).as_posix(),
                "metadata_path": (
                    Path("usr/share/aios/component-metadata")
                    / component["kind"]
                    / metadata_name
                ).as_posix(),
                "enabled": component["enabled"],
            }
        )

    enabled_units = generate_systemd_preset(
        rootfs_dir,
        extra_units=["aios-firstboot.service", "aios-ai-onboarding.service", "aios-boot-evidence.service"],
    )

    providers_dir = rootfs_dir / "usr" / "share" / "aios" / "providers"
    providers_dir.mkdir(parents=True, exist_ok=True)
    provider_files: list[str] = []
    for directory in DESCRIPTOR_DIRECTORIES:
        for entry in sorted(directory.glob("*.json")):
            copy_file(entry, providers_dir / entry.name)
            provider_files.append((Path("usr/share/aios/providers") / entry.name).as_posix())

    compat_runtime_files: list[str] = []
    for source_dir, runtime_name in COMPAT_RUNTIME_DIRECTORIES:
        if not source_dir.exists():
            continue
        destination = rootfs_dir / "usr" / "libexec" / "aios-compat" / runtime_name
        copy_tree(source_dir, destination)
        for entry in sorted(destination.rglob("*")):
            if entry.is_file():
                compat_runtime_files.append(entry.relative_to(rootfs_dir).as_posix())

    schema_files: list[str] = []
    for directory in SCHEMA_DIRECTORIES:
        target_dir = rootfs_dir / "usr" / "share" / "aios" / "schemas" / directory.parent.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for entry in sorted(directory.glob("*.json")):
            copy_file(entry, target_dir / entry.name)
            schema_files.append((Path("usr/share/aios/schemas") / directory.parent.name / entry.name).as_posix())

    shell_destination = rootfs_dir / "usr" / "libexec" / "aios-shell"
    copy_tree(AIOS_ROOT / "shell" / "components", shell_destination / "components")
    copy_tree(AIOS_ROOT / "shell" / "profiles", shell_destination / "profiles")
    if (AIOS_ROOT / "shell" / "runtime").exists():
        copy_tree(AIOS_ROOT / "shell" / "runtime", shell_destination / "runtime")
    if (AIOS_ROOT / "shell" / "compositor").exists():
        copy_tree(AIOS_ROOT / "shell" / "compositor", shell_destination / "compositor")
    copy_file(AIOS_ROOT / "shell" / "shellctl.py", shell_destination / "shellctl.py")

    task_files: list[str] = []
    for entry in sorted((AIOS_ROOT / "tasks").glob("*.yaml")):
        destination = rootfs_dir / "usr" / "share" / "aios" / "tasks" / entry.name
        copy_file(entry, destination)
        task_files.append(destination.relative_to(rootfs_dir).as_posix())

    hardware_destination = rootfs_dir / "usr" / "share" / "aios" / "hardware"
    copy_tree(AIOS_ROOT / "hardware" / "profiles", hardware_destination / "profiles")

    return {
        "rootfs_dir": rootfs_dir,
        "components": component_records,
        "enabled_units": enabled_units,
        "provider_descriptors": sorted(provider_files),
        "boot_assets": sorted(boot_assets),
        "firstboot": firstboot_assets,
        "runtime_assets": runtime_assets,
        "firstboot_hygiene": firstboot_hygiene,
        "masked_units": sorted(masked_units),
        "recovery": recovery_assets,
        "installer": installer_assets,
        "hardware_evidence": hardware_evidence_assets,
        "updated_platforms": sorted(updated_platform_files),
        "runtime_platforms": sorted(runtime_platform_files),
        "compat_runtimes": sorted(compat_runtime_files),
        "schemas": sorted(schema_files),
        "task_files": sorted(task_files),
        "shell_entrypoint": "usr/libexec/aios-shell/shellctl.py",
        "shell_runtime_requirements": ["python3", "PyYAML"],
    }


def stage_image_assets(bundle_dir: Path) -> list[str]:
    records: list[str] = []
    for source, relative in IMAGE_ASSETS:
        destination = bundle_dir / relative
        if source.is_dir():
            copy_tree(source, destination)
            for entry in sorted(destination.rglob("*")):
                if entry.is_file():
                    records.append(entry.relative_to(bundle_dir).as_posix())
        else:
            copy_file(source, destination)
            records.append(destination.relative_to(bundle_dir).as_posix())
    return records


def main() -> int:
    args = parse_args()

    ensure_task_metadata()
    ensure_binaries(args.bin_dir, args.build_missing, args.cargo_target)

    bundle_dir = args.output_dir.resolve()
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    rootfs_info = stage_rootfs(bundle_dir, args.bin_dir.resolve())
    image_assets = stage_image_assets(bundle_dir)

    if args.sync_overlay is not None:
        sync_overlay(rootfs_info["rootfs_dir"], args.sync_overlay.resolve())

    manifest_payload = {
        "schema_version": "1.0.0",
        "bundle_name": "aios-system-delivery",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": resolve_git_commit(),
        "source_root": ROOT.as_posix(),
        "bin_dir": args.bin_dir.resolve().as_posix(),
        "rootfs_overlay": Path("rootfs").as_posix(),
        "components": rootfs_info["components"],
        "enabled_units": rootfs_info["enabled_units"],
        "provider_descriptors": rootfs_info["provider_descriptors"],
        "boot": rootfs_info["boot_assets"],
        "firstboot": rootfs_info["firstboot"],
        "runtime_assets": rootfs_info["runtime_assets"],
        "firstboot_hygiene": rootfs_info["firstboot_hygiene"],
        "masked_units": rootfs_info["masked_units"],
        "recovery": rootfs_info["recovery"],
        "installer": rootfs_info["installer"],
        "runtime_platforms": rootfs_info["runtime_platforms"],
        "compat": {
            "provider_descriptors": [
                path
                for path in rootfs_info["provider_descriptors"]
                if any(
                    marker in path
                    for marker in (
                        "browser.automation.local.json",
                        "office.document.local.json",
                        "mcp.bridge.local.json",
                        "code.sandbox.local.json",
                    )
                )
            ],
            "runtimes": rootfs_info["compat_runtimes"],
        },
        "schemas": rootfs_info["schemas"],
        "task_files": rootfs_info["task_files"],
        "shell": {
            "entrypoint": rootfs_info["shell_entrypoint"],
            "runtime_requirements": rootfs_info["shell_runtime_requirements"],
        },
        "image_assets": image_assets,
    }
    write_manifest(bundle_dir, manifest_payload)
    manifest_payload["files"] = collect_file_manifest(bundle_dir, exclude={"manifest.json"})
    write_manifest(bundle_dir, manifest_payload)

    archive_path = None
    if not args.no_archive:
        archive_path = create_archive(bundle_dir)

    print(
        json.dumps(
            {
                "bundle_dir": bundle_dir.as_posix(),
                "archive": archive_path.as_posix() if archive_path else None,
                "components": len(COMPONENTS),
                "enabled_units": len(rootfs_info["enabled_units"]),
                "provider_descriptors": len(rootfs_info["provider_descriptors"]),
                "task_files": len(rootfs_info["task_files"]),
                "overlay_synced": args.sync_overlay.resolve().as_posix() if args.sync_overlay else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
