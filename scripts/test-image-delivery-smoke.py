#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
AIOS_ROOT = ROOT / "aios"
HOST_LINK_PLACEHOLDER_PREFIX = "aios-host-link-target:"


def read_symlink_target(path: Path) -> str | None:
    if path.is_symlink():
        return os.readlink(path)
    if path.is_file():
        payload = path.read_text(encoding="utf-8").strip()
        if payload.startswith(HOST_LINK_PLACEHOLDER_PREFIX):
            return payload[len(HOST_LINK_PLACEHOLDER_PREFIX):]
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIOS image and delivery smoke validation")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    return parser.parse_args()


def require(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"missing {label}: {path}")


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def rust_source_has_inline_tests(source_dir: Path) -> bool:
    for path in source_dir.rglob("*.rs"):
        text = path.read_text(encoding="utf-8")
        if "#[cfg(test)]" in text or "#[test]" in text:
            return True
    return False


def executable_bit(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def tracked_tree_files(root: Path) -> list[Path]:
    tracked: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        tracked.append(relative)
    return sorted(tracked)


def compare_tree_contents(source_root: Path, mirror_root: Path, label: str) -> int:
    require(source_root, f"{label} source tree")
    require(mirror_root, f"{label} mirrored tree")
    source_files = tracked_tree_files(source_root)
    mirror_files = tracked_tree_files(mirror_root)
    ensure(
        source_files == mirror_files,
        f"{label} file list out of sync: {source_root} != {mirror_root}",
    )
    for relative_path in source_files:
        source = source_root / relative_path
        mirror = mirror_root / relative_path
        if source.read_bytes() != mirror.read_bytes():
            raise SystemExit(f"{label} file content out of sync: {source} != {mirror}")
        ensure(
            executable_bit(source) == executable_bit(mirror),
            f"{label} executable bit out of sync: {source} != {mirror}",
        )
    return len(source_files)


def main() -> int:
    args = parse_args()
    bundle_dir = args.bundle_dir.resolve()
    manifest_path = bundle_dir / "manifest.json"
    require(manifest_path, "manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    expected_rootfs_files = [
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "sessiond",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "policyd",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "runtimed",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "agentd",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "deviced",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "updated",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "device-metadata-provider",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "runtime-local-inference-provider",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "system-intent-provider",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "system-files-provider",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "aios-firstboot.sh",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "aios-ai-onboarding.sh",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "aios-recovery-report.sh",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "aios-installer-guided.sh",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "runtime" / "model_manager.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "runtime" / "recommended-model-catalog.yaml",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "runtime" / "workers" / "local_cpu_worker.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios" / "runtime" / "workers" / "launch_local_cpu_worker.sh",
        bundle_dir / "rootfs" / "usr" / "share" / "aios" / "boot" / "loader" / "loader.conf",
        bundle_dir / "rootfs" / "usr" / "share" / "aios" / "boot" / "kernel-command-line.txt",
        bundle_dir / "rootfs" / "usr" / "share" / "aios" / "installer" / "ui" / "README.md",
        bundle_dir / "rootfs" / "usr" / "lib" / "systemd" / "system" / "aios-firstboot.service",
        bundle_dir / "rootfs" / "usr" / "lib" / "systemd" / "system" / "aios-ai-onboarding.service",
        bundle_dir / "rootfs" / "usr" / "lib" / "systemd" / "system" / "aios-recovery.target",
        bundle_dir / "rootfs" / "usr" / "lib" / "systemd" / "system" / "aios-recovery-shell.service",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-compat" / "browser" / "browser_provider.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-compat" / "office" / "office_provider.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-compat" / "mcp-bridge" / "mcp_bridge_provider.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-compat" / "code-sandbox" / "aios_sandbox_executor.py",
        bundle_dir / "rootfs" / "etc" / "aios" / "policy" / "default-capability-catalog.yaml",
        bundle_dir / "rootfs" / "etc" / "aios" / "shell" / "formal-shell-profile.yaml",
        bundle_dir / "rootfs" / "etc" / "aios" / "shell" / "release-shell-profile.yaml",
        bundle_dir / "rootfs" / "etc" / "machine-id",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-shell" / "runtime" / "shell_control_provider.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-shell" / "runtime" / "shell_session.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-shell" / "components" / "portal-chooser" / "standalone.py",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-shell" / "compositor" / "Cargo.toml",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-shell" / "compositor" / "default-compositor.conf",
        bundle_dir / "rootfs" / "usr" / "libexec" / "aios-shell" / "compositor" / "release-compositor.conf",
    ]

    for path in expected_rootfs_files:
        require(path, "rootfs asset")

    masked_firstboot = bundle_dir / "rootfs" / "etc" / "systemd" / "system" / "systemd-firstboot.service"
    require(masked_firstboot, "masked systemd-firstboot unit")
    if read_symlink_target(masked_firstboot) != "/dev/null":
        raise SystemExit(f"unexpected systemd-firstboot mask target: {masked_firstboot}")

    tmpfiles_source = AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "lib" / "tmpfiles.d" / "aios.conf"
    tmpfiles_bundled = bundle_dir / "rootfs" / "usr" / "lib" / "tmpfiles.d" / "aios.conf"
    require(tmpfiles_source, "source tmpfiles config")
    require(tmpfiles_bundled, "bundled tmpfiles config")
    ensure(
        tmpfiles_source.read_text(encoding="utf-8") == tmpfiles_bundled.read_text(encoding="utf-8"),
        f"tmpfiles config out of sync: {tmpfiles_source} != {tmpfiles_bundled}",
    )
    tmpfiles_entries = {
        line.strip()
        for line in tmpfiles_bundled.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required_tmpfiles_entries = {
        "d /var/lib/aios/firstboot 0755 root root -",
        "d /var/lib/aios/updated/boot 0755 root root -",
        "d /var/lib/aios/updated/recovery 0755 root root -",
        "d /var/lib/aios/updated/diagnostics 0755 root root -",
        "d /var/lib/aios/onboarding 0755 root root -",
        "d /var/lib/aios/runtime 0755 root root -",
        "d /var/lib/aios/models 0755 root root -",
        "d /var/lib/aios/hardware-evidence 0755 root root -",
        "d /var/lib/aios/hardware-evidence/boots 0755 root root -",
        "d /var/log/aios 0755 root root -",
        "d /var/log/journal 2755 root systemd-journal -",
    }
    missing_tmpfiles_entries = sorted(required_tmpfiles_entries - tmpfiles_entries)
    ensure(
        not missing_tmpfiles_entries,
        f"tmpfiles config missing required state layout entries: {missing_tmpfiles_entries}",
    )

    machine_id = bundle_dir / "rootfs" / "etc" / "machine-id"
    require(machine_id, "empty machine-id file")
    if machine_id.read_text(encoding="utf-8") != "":
        raise SystemExit("expected /etc/machine-id to be empty in delivery bundle")

    dbus_machine_id = bundle_dir / "rootfs" / "var" / "lib" / "dbus" / "machine-id"
    if read_symlink_target(dbus_machine_id) != "/etc/machine-id":
        raise SystemExit(f"unexpected dbus machine-id target: {dbus_machine_id}")

    random_seed = bundle_dir / "rootfs" / "var" / "lib" / "systemd" / "random-seed"
    if random_seed.exists() or random_seed.is_symlink():
        raise SystemExit(f"expected random-seed to be absent from delivery bundle: {random_seed}")

    enabled_units = set(manifest.get("enabled_units", []))
    required_units = {
        "aios-sessiond.service",
        "aios-policyd.service",
        "aios-runtimed.service",
        "aios-agentd.service",
        "aios-deviced.service",
        "aios-updated.service",
        "aios-device-metadata-provider.service",
        "aios-runtime-local-inference-provider.service",
        "aios-system-intent-provider.service",
        "aios-system-files-provider.service",
        "aios-firstboot.service",
        "aios-ai-onboarding.service",
    }
    if not required_units.issubset(enabled_units):
        missing = sorted(required_units - enabled_units)
        raise SystemExit(f"manifest missing enabled units: {missing}")

    masked_units = set(manifest.get("masked_units", []))
    if "etc/systemd/system/systemd-firstboot.service" not in masked_units:
        raise SystemExit("manifest missing masked systemd-firstboot.service")

    firstboot_hygiene = manifest.get("firstboot_hygiene", {})
    if firstboot_hygiene.get("machine_id") != "etc/machine-id":
        raise SystemExit("manifest missing firstboot_hygiene machine-id path")
    if firstboot_hygiene.get("machine_id_state") != "empty-file":
        raise SystemExit("manifest machine-id state should be empty-file")
    if firstboot_hygiene.get("dbus_machine_id") != "var/lib/dbus/machine-id":
        raise SystemExit("manifest missing dbus machine-id path")
    if firstboot_hygiene.get("dbus_machine_id_target") != "/etc/machine-id":
        raise SystemExit("manifest dbus machine-id target mismatch")
    if firstboot_hygiene.get("random_seed") != "var/lib/systemd/random-seed":
        raise SystemExit("manifest missing random-seed path")
    if firstboot_hygiene.get("random_seed_present") is not False:
        raise SystemExit("manifest should record random-seed as absent")

    compat_descriptors = set(manifest.get("compat", {}).get("provider_descriptors", []))
    expected_descriptors = {
        "usr/share/aios/providers/browser.automation.local.json",
        "usr/share/aios/providers/office.document.local.json",
        "usr/share/aios/providers/mcp.bridge.local.json",
        "usr/share/aios/providers/code.sandbox.local.json",
    }
    if not expected_descriptors.issubset(compat_descriptors):
        missing = sorted(expected_descriptors - compat_descriptors)
        raise SystemExit(f"manifest missing compat descriptors: {missing}")

    config_sync_pairs = [
        (
            AIOS_ROOT / "policy" / "profiles" / "default-policy.yaml",
            bundle_dir / "rootfs" / "etc" / "aios" / "policy" / "default-policy.yaml",
        ),
        (
            AIOS_ROOT / "policy" / "capabilities" / "default-capability-catalog.yaml",
            bundle_dir / "rootfs" / "etc" / "aios" / "policy" / "default-capability-catalog.yaml",
        ),
        (
            AIOS_ROOT / "runtime" / "profiles" / "default-runtime-profile.yaml",
            bundle_dir / "rootfs" / "etc" / "aios" / "runtime" / "default-runtime-profile.yaml",
        ),
        (
            AIOS_ROOT / "runtime" / "profiles" / "default-route-profile.yaml",
            bundle_dir / "rootfs" / "etc" / "aios" / "runtime" / "default-route-profile.yaml",
        ),
        (
            AIOS_ROOT / "shell" / "profiles" / "default-shell-profile.yaml",
            bundle_dir / "rootfs" / "etc" / "aios" / "shell" / "default-shell-profile.yaml",
        ),
        (
            AIOS_ROOT / "shell" / "profiles" / "formal-shell-profile.yaml",
            bundle_dir / "rootfs" / "etc" / "aios" / "shell" / "formal-shell-profile.yaml",
        ),
        (
            AIOS_ROOT / "shell" / "profiles" / "release-shell-profile.yaml",
            bundle_dir / "rootfs" / "etc" / "aios" / "shell" / "release-shell-profile.yaml",
        ),
    ]
    for source, bundled in config_sync_pairs:
        require(source, "source config")
        require(bundled, "bundled config")
        if source.read_text(encoding="utf-8") != bundled.read_text(encoding="utf-8"):
            raise SystemExit(f"config out of sync: {source} != {bundled}")

    runtime_platform_asset_count = compare_tree_contents(
        AIOS_ROOT / "runtime" / "platforms",
        AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "share" / "aios" / "runtime" / "platforms",
        "runtime platform assets",
    )
    shell_compositor_source_count = compare_tree_contents(
        AIOS_ROOT / "shell" / "compositor" / "src",
        AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "libexec" / "aios-shell" / "compositor" / "src",
        "shell compositor source assets",
    )
    shell_compositor_config_pairs = [
        (
            AIOS_ROOT / "shell" / "compositor" / "Cargo.toml",
            AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "libexec" / "aios-shell" / "compositor" / "Cargo.toml",
        ),
        (
            AIOS_ROOT / "shell" / "compositor" / "Cargo.lock",
            AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "libexec" / "aios-shell" / "compositor" / "Cargo.lock",
        ),
        (
            AIOS_ROOT / "shell" / "compositor" / "default-compositor.conf",
            AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "libexec" / "aios-shell" / "compositor" / "default-compositor.conf",
        ),
        (
            AIOS_ROOT / "shell" / "compositor" / "release-compositor.conf",
            AIOS_ROOT / "image" / "mkosi.extra" / "usr" / "libexec" / "aios-shell" / "compositor" / "release-compositor.conf",
        ),
    ]
    for source, bundled in shell_compositor_config_pairs:
        require(source, "source shell compositor asset")
        require(bundled, "bundled shell compositor asset")
        ensure(
            source.read_text(encoding="utf-8") == bundled.read_text(encoding="utf-8"),
            f"shell compositor asset out of sync: {source} != {bundled}",
        )
    updated_platform_profiles = {
        "generic-x86_64-uefi": "/usr/libexec/aios-platform/generic-x86_64-uefi/health-probe.sh",
        "qemu-x86_64": "/usr/libexec/aios-platform/qemu-x86_64/health-probe.sh",
        "nvidia-jetson-orin-agx": "/usr/libexec/aios-platform/nvidia-jetson-orin-agx/health-probe.sh",
    }
    for platform_id, expected_command in updated_platform_profiles.items():
        profile_path = (
            bundle_dir
            / "rootfs"
            / "usr"
            / "share"
            / "aios"
            / "updated"
            / "platforms"
            / platform_id
            / "profile.yaml"
        )
        require(profile_path, "updated platform profile")
        profile = load_yaml(profile_path)
        ensure(
            profile.get("health_probe_command") == expected_command,
            f"{platform_id} updated profile missing health probe command",
        )
        probe_asset = (
            bundle_dir
            / "rootfs"
            / "usr"
            / "libexec"
            / "aios-platform"
            / platform_id
            / "health-probe.sh"
        )
        require(probe_asset, "updated platform health probe asset")
        if os.name != "nt":
            ensure(executable_bit(probe_asset), f"health probe should be executable: {probe_asset}")

    metadata_sync_pairs = [
        (
            AIOS_ROOT / "services" / "sessiond" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "service" / "aios-sessiond.yaml",
        ),
        (
            AIOS_ROOT / "services" / "policyd" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "service" / "aios-policyd.yaml",
        ),
        (
            AIOS_ROOT / "services" / "runtimed" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "service" / "aios-runtimed.yaml",
        ),
        (
            AIOS_ROOT / "services" / "agentd" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "service" / "aios-agentd.yaml",
        ),
        (
            AIOS_ROOT / "services" / "deviced" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "service" / "aios-deviced.yaml",
        ),
        (
            AIOS_ROOT / "services" / "updated" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "service" / "aios-updated.yaml",
        ),
        (
            AIOS_ROOT / "providers" / "device-metadata" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "provider" / "aios-device-metadata-provider.yaml",
        ),
        (
            AIOS_ROOT / "providers" / "runtime-local-inference" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "provider" / "aios-runtime-local-inference-provider.yaml",
        ),
        (
            AIOS_ROOT / "providers" / "system-intent" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "provider" / "aios-system-intent-provider.yaml",
        ),
        (
            AIOS_ROOT / "providers" / "system-files" / "service.yaml",
            bundle_dir / "rootfs" / "usr" / "share" / "aios" / "component-metadata" / "provider" / "aios-system-files-provider.yaml",
        ),
    ]
    for source, bundled in metadata_sync_pairs:
        require(source, "source metadata")
        require(bundled, "bundled metadata")
        if source.read_text(encoding="utf-8") != bundled.read_text(encoding="utf-8"):
            raise SystemExit(f"component metadata out of sync: {source} != {bundled}")

    sessiond_metadata = load_yaml(
        bundle_dir
        / "rootfs"
        / "usr"
        / "share"
        / "aios"
        / "component-metadata"
        / "service"
        / "aios-sessiond.yaml"
    )
    ensure(
        rust_source_has_inline_tests(AIOS_ROOT / "services" / "sessiond" / "src"),
        "sessiond inline rust tests were expected but not found",
    )
    ensure(
        "no-sessiond-tests" not in set(sessiond_metadata.get("blockers", [])),
        "sessiond metadata still claims no-sessiond-tests despite inline coverage",
    )

    approval_manifest = AIOS_ROOT / "shell" / "components" / "approval-panel" / "manifest.yaml"
    approval_panel = AIOS_ROOT / "shell" / "components" / "approval-panel" / "panel.py"
    require(approval_manifest, "approval panel manifest")
    require(approval_panel, "approval panel implementation")
    approval_metadata = load_yaml(approval_manifest)
    ensure(
        approval_metadata.get("role") == "shell-approval-surface",
        "approval panel manifest role mismatch",
    )
    policyd_metadata = load_yaml(
        bundle_dir
        / "rootfs"
        / "usr"
        / "share"
        / "aios"
        / "component-metadata"
        / "service"
        / "aios-policyd.yaml"
    )
    ensure(
        "no-shell-approval-surface" not in set(policyd_metadata.get("blockers", [])),
        "policyd metadata still claims no-shell-approval-surface despite shipped approval panel assets",
    )

    runtimed_metadata = load_yaml(
        bundle_dir
        / "rootfs"
        / "usr"
        / "share"
        / "aios"
        / "component-metadata"
        / "service"
        / "aios-runtimed.yaml"
    )
    worker_support = runtimed_metadata.get("worker_support", {})
    ensure(
        "runtime-worker-v1" in set(worker_support.get("contracts", [])),
        "runtimed metadata missing runtime-worker-v1 contract",
    )
    ensure(
        "unix-socket-worker" in set(worker_support.get("transports", [])),
        "runtimed metadata missing unix-socket-worker transport",
    )
    ensure(
        {"local-gpu", "local-npu"}.issubset(set(worker_support.get("managed_backends", []))),
        "runtimed metadata missing managed local GPU/NPU backends",
    )
    ensure(
        "hardware-profile" in set(worker_support.get("managed_worker_sources", [])),
        "runtimed metadata missing hardware-profile managed worker source",
    )
    ensure(
        "backend_worker_contract" in set(worker_support.get("health_notes", [])),
        "runtimed metadata missing backend_worker_contract health note",
    )
    ensure(
        "managed_worker_count" in set(worker_support.get("health_notes", [])),
        "runtimed metadata missing managed_worker_count health note",
    )
    ensure(
        "managed_worker_source" in set(worker_support.get("health_notes", [])),
        "runtimed metadata missing managed_worker_source health note",
    )
    ensure(
        "managed_worker_detail" in set(worker_support.get("health_notes", [])),
        "runtimed metadata missing managed_worker_detail health note",
    )
    runtimed_unit = (
        bundle_dir / "rootfs" / "usr" / "lib" / "systemd" / "system" / "aios-runtimed.service"
    )
    ensure(
        "EnvironmentFile=-/etc/aios/runtime/platform.env" in runtimed_unit.read_text(encoding="utf-8"),
        "runtimed unit missing runtime platform env wiring",
    )
    runtime_provider_unit = (
        bundle_dir
        / "rootfs"
        / "usr"
        / "lib"
        / "systemd"
        / "system"
        / "aios-runtime-local-inference-provider.service"
    )
    ensure(
        "EnvironmentFile=-/etc/aios/runtime/platform.env"
        in runtime_provider_unit.read_text(encoding="utf-8"),
        "runtime local inference provider unit missing runtime platform env wiring",
    )
    jetson_runtime_profile = (
        bundle_dir
        / "rootfs"
        / "usr"
        / "share"
        / "aios"
        / "runtime"
        / "platforms"
        / "nvidia-jetson-orin-agx"
        / "default-runtime-profile.yaml"
    )
    require(jetson_runtime_profile, "jetson runtime platform profile asset")
    jetson_runtime_profile_text = jetson_runtime_profile.read_text(encoding="utf-8")
    ensure(
        "profile_id: nvidia-jetson-orin-agx-default" in jetson_runtime_profile_text,
        "jetson runtime platform profile id mismatch",
    )
    ensure(
        "default_backend: local-gpu" in jetson_runtime_profile_text,
        "jetson runtime platform profile should prefer local-gpu",
    )
    ensure(
        "nvidia-jetson-orin-agx:" in jetson_runtime_profile_text,
        "jetson runtime platform profile missing hardware-profile key",
    )
    ensure(
        "launch-managed-worker.sh" in jetson_runtime_profile_text,
        "jetson runtime platform profile missing worker bridge command",
    )
    require(
        bundle_dir
        / "rootfs"
        / "usr"
        / "share"
        / "aios"
        / "runtime"
        / "platforms"
        / "nvidia-jetson-orin-agx"
        / "bin"
        / "launch-managed-worker.sh",
        "jetson worker bridge asset",
    )
    require(
        bundle_dir
        / "rootfs"
        / "usr"
        / "share"
        / "aios"
        / "runtime"
        / "platforms"
        / "nvidia-jetson-orin-agx"
        / "bin"
        / "vendor_accel_worker.py",
        "jetson vendor helper asset",
    )

    runtime_readme = (AIOS_ROOT / "runtime" / "README.md").read_text(encoding="utf-8")
    for needle in ("runtime-worker-v1", "unix://", "managed worker"):
        ensure(needle in runtime_readme, f"runtime README missing current runtime capability marker: {needle}")

    runtime_profile = load_yaml(AIOS_ROOT / "runtime" / "profiles" / "default-runtime-profile.yaml")
    ensure(
        "hardware_profile_managed_worker_commands" in runtime_profile,
        "default runtime profile missing hardware_profile_managed_worker_commands",
    )
    runtime_profile_schema = json.loads((AIOS_ROOT / "runtime" / "schemas" / "runtime-profile.schema.json").read_text(encoding="utf-8"))
    ensure(
        "hardware_profile_managed_worker_commands" in runtime_profile_schema.get("properties", {}),
        "runtime profile schema missing hardware_profile_managed_worker_commands",
    )

    image_schema_root = bundle_dir / "rootfs" / "usr" / "share" / "aios" / "schemas" / "image"
    image_schema_count = compare_tree_contents(
        AIOS_ROOT / "image" / "schemas",
        image_schema_root,
        "image schemas",
    )
    require(image_schema_root / "platform-media-profile.schema.json", "platform media profile schema asset")
    require(image_schema_root / "vendor-firmware-hook-report.schema.json", "vendor firmware hook report schema asset")

    sdk_schema_root = bundle_dir / "rootfs" / "usr" / "share" / "aios" / "schemas" / "sdk"
    sdk_schema_count = compare_tree_contents(
        AIOS_ROOT / "sdk" / "schemas",
        sdk_schema_root,
        "sdk schemas",
    )
    require(sdk_schema_root / "provider-descriptor.schema.json", "provider descriptor schema asset")
    require(sdk_schema_root / "provider-remote-registration.schema.json", "provider remote registration schema asset")
    require(sdk_schema_root / "provider-remote-registry.schema.json", "provider remote registry schema asset")

    hardware_schema_root = bundle_dir / "rootfs" / "usr" / "share" / "aios" / "schemas" / "hardware"
    hardware_schema_count = compare_tree_contents(
        AIOS_ROOT / "hardware" / "schemas",
        hardware_schema_root,
        "hardware schemas",
    )
    require(hardware_schema_root / "hardware-profile.schema.json", "hardware profile schema asset")
    require(hardware_schema_root / "hardware-boot-evidence-report.schema.json", "hardware boot evidence schema asset")
    require(hardware_schema_root / "hardware-validation-evidence-index.schema.json", "hardware validation evidence index schema asset")
    observability_schema_root = bundle_dir / "rootfs" / "usr" / "share" / "aios" / "schemas" / "observability"
    observability_schema_count = compare_tree_contents(
        AIOS_ROOT / "observability" / "schemas",
        observability_schema_root,
        "observability schemas",
    )
    require(observability_schema_root / "health-event.schema.json", "health event schema asset")
    require(observability_schema_root / "recovery-evidence.schema.json", "recovery evidence schema asset")
    require(observability_schema_root / "validation-report.schema.json", "validation report schema asset")
    require(observability_schema_root / "evidence-index.schema.json", "evidence index schema asset")
    require(observability_schema_root / "release-gate-report.schema.json", "release gate report schema asset")
    require(observability_schema_root / "cross-service-correlation-report.schema.json", "cross-service correlation schema asset")
    require(observability_schema_root / "cross-service-health-report.schema.json", "cross-service health schema asset")

    updated_schema_root = bundle_dir / "rootfs" / "usr" / "share" / "aios" / "schemas" / "updated"
    updated_schema_count = compare_tree_contents(
        AIOS_ROOT / "services" / "updated" / "schemas",
        updated_schema_root,
        "updated schemas",
    )
    require(updated_schema_root / "platform-profile.schema.json", "updated platform profile schema asset")
    summary = {
        "bundle_dir": str(bundle_dir),
        "components": len(manifest.get("components", [])),
        "enabled_units": len(enabled_units),
        "masked_units": len(masked_units),
        "compat_descriptors": len(compat_descriptors),
        "task_files": len(manifest.get("task_files", [])),
        "machine_id_state": firstboot_hygiene.get("machine_id_state"),
        "synced_configs": len(config_sync_pairs),
        "synced_image_schemas": image_schema_count,
        "synced_sdk_schemas": sdk_schema_count,
        "synced_hardware_schemas": hardware_schema_count,
        "synced_observability_schemas": observability_schema_count,
        "synced_updated_schemas": updated_schema_count,
        "synced_runtime_platform_assets": runtime_platform_asset_count,
        "synced_shell_compositor_sources": shell_compositor_source_count,
        "updated_platform_profiles_checked": len(updated_platform_profiles),
        "synced_component_metadata": len(metadata_sync_pairs),
        "metadata_semantics_checked": 7,
        "tmpfiles_entries_checked": len(required_tmpfiles_entries),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


