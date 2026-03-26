#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from host_exec import bash_command, bash_path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLATFORM = "generic-x86_64-uefi"
BOOT_EVIDENCE_DIR = "/var/lib/aios/hardware-evidence/boots"
BOOT_EVIDENCE_SERVICE = ROOT / "aios" / "hardware" / "evidence" / "aios-boot-evidence.service"
BOOT_EVIDENCE_SCRIPT = ROOT / "aios" / "hardware" / "evidence" / "aios-boot-evidence.sh"
BOOT_EVIDENCE_EVALUATOR = ROOT / "scripts" / "evaluate-aios-hardware-boot-evidence.py"
HARDWARE_REPORT_RENDERER = ROOT / "scripts" / "render-aios-hardware-validation-report.py"
DEVICE_VALIDATION_COLLECTOR = ROOT / "scripts" / "collect-aios-device-validation.py"
TIER1_TEMPLATE = ROOT / "aios" / "hardware" / "profiles" / "tier1-template.yaml"
HARDWARE_PROFILE_DIR = ROOT / "aios" / "hardware" / "profiles"
TIER1_NOMINATIONS_PATH = ROOT / "aios" / "hardware" / "tier1-nominated-machines.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build/export AIOS platform installer and recovery media")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--platform-profile", type=Path, help="Path to platform profile YAML")
    parser.add_argument("--output-dir", type=Path, help="Directory for exported platform media")
    parser.add_argument("--system-image", type=Path, default=ROOT / "aios" / "image" / "mkosi.output" / "aios-qemu-x86_64.raw")
    parser.add_argument("--installer-image", type=Path, default=ROOT / "aios" / "image" / "installer.output" / "aios-qemu-x86_64-installer.raw")
    parser.add_argument("--recovery-image", type=Path, default=ROOT / "aios" / "image" / "recovery.output" / "aios-qemu-x86_64-recovery.raw")
    parser.add_argument("--build-platform-images", action="store_true", help="Rebuild installer/recovery images with platform overlays applied")
    parser.add_argument("--embed-system-image", action=argparse.BooleanOptionalAction, default=True, help="Embed the system image into installer media payload")
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def resolve_hardware_profile_path(hardware_profile_id: str | None) -> Path | None:
    if not hardware_profile_id:
        return None
    for suffix in (".yaml", ".yml", ".json"):
        candidate = HARDWARE_PROFILE_DIR / f"{hardware_profile_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def load_hardware_profile(hardware_profile_id: str | None) -> tuple[Path | None, dict[str, object]]:
    profile_path = resolve_hardware_profile_path(hardware_profile_id)
    if profile_path is None:
        return None, {}
    return profile_path, load_yaml(profile_path)


def load_tier1_nominations() -> list[dict[str, object]]:
    if not TIER1_NOMINATIONS_PATH.exists():
        return []
    payload = load_yaml(TIER1_NOMINATIONS_PATH) or {}
    entries = payload.get("nominated_machines")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def matching_tier1_nominations(
    platform_id: str,
    hardware_profile_id: str | None,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for entry in load_tier1_nominations():
        if entry.get("platform_media_id") == platform_id:
            matches.append(entry)
            continue
        if hardware_profile_id and entry.get("canonical_hardware_profile_id") == hardware_profile_id:
            matches.append(entry)
    return matches


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_file(path: Path, description: str) -> None:
    if not path.exists():
        raise SystemExit(f"missing {description}: {path}")


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def write_platform_env(path: Path, platform_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"AIOS_UPDATED_PLATFORM_PROFILE=/usr/share/aios/updated/platforms/{platform_id}/profile.yaml\n"
    )


def write_runtime_platform_env(
    path: Path,
    hardware_profile_id: str | None,
    runtime_profile_path: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if hardware_profile_id:
        lines.append(f"AIOS_RUNTIMED_HARDWARE_PROFILE_ID={hardware_profile_id}")
    if runtime_profile_path:
        lines.append(f"AIOS_RUNTIMED_RUNTIME_PROFILE={runtime_profile_path}")
    path.write_text("\n".join(lines) + "\n")


def resolve_runtime_profile_source(runtime_profile_path: str) -> Path:
    target = Path(runtime_profile_path)
    if runtime_profile_path.startswith("/usr/share/aios/runtime/platforms/"):
        relative = target.relative_to("/usr/share/aios/runtime/platforms")
        return ROOT / "aios" / "runtime" / "platforms" / relative
    if runtime_profile_path.startswith("/etc/aios/runtime/"):
        return ROOT / "aios" / "runtime" / "profiles" / target.name
    raise SystemExit(f"unsupported runtime profile path in platform media export: {runtime_profile_path}")


def copy_runtime_profile_asset(root: Path, runtime_profile_path: str) -> str:
    source = resolve_runtime_profile_source(runtime_profile_path)
    if runtime_profile_path.startswith("/usr/share/aios/runtime/platforms/"):
        relative = Path(runtime_profile_path).relative_to("/usr/share/aios/runtime/platforms")
        platform_root = relative.parts[0]
        source_dir = ROOT / "aios" / "runtime" / "platforms" / platform_root
        nested_relative = Path(*relative.parts[1:])
        ensure_file(source_dir / nested_relative, "runtime profile asset")
        destination_dir = root / "usr" / "share" / "aios" / "runtime" / "platforms" / platform_root
        copy_tree(source_dir, destination_dir)
        for entry in sorted(destination_dir.rglob("*")):
            if entry.is_file() and entry.suffix == ".sh":
                entry.chmod(entry.stat().st_mode | 0o111)
        return str((destination_dir / nested_relative).relative_to(root))
    ensure_file(source, "runtime profile asset")
    destination = root / runtime_profile_path.lstrip("/")
    copy_file(source, destination)
    return str(destination.relative_to(root))


def quote_env_value(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def write_installer_env(path: Path, platform_id: str, installer: dict, embed_system_image: bool) -> None:
    guided_ui = installer.get("guided_ui", {})
    lines = [
        f"AIOS_INSTALLER_TARGET_DISK={quote_env_value('/dev/nvme0n1')}",
        f"AIOS_INSTALLER_RECOVERY_DISK={quote_env_value('/dev/sdb')}",
        f"AIOS_INSTALLER_PLATFORM_ID={quote_env_value(platform_id)}",
        f"AIOS_INSTALLER_PLATFORM_LABEL={quote_env_value(installer.get('platform_label', platform_id))}",
        f"AIOS_INSTALLER_PLATFORM_PROFILE={quote_env_value(installer.get('updated_platform_profile', ''))}",
        f"AIOS_INSTALLER_TARGET_OVERLAY_DIR={quote_env_value(installer['target_overlay_dir'])}",
        f"AIOS_INSTALLER_INSTALL_SOURCE={quote_env_value('installer-media:embedded-payload' if embed_system_image else 'installer-media:external-payload')}",
        f"AIOS_INSTALLER_GUIDED_MODE={quote_env_value(guided_ui.get('mode', 'auto'))}",
        f"AIOS_INSTALLER_GUIDED_AUTO_CONFIRM_SECONDS={quote_env_value(guided_ui.get('auto_confirm_seconds', 0))}",
    ]
    if installer.get("vendor_id"):
        lines.append(f"AIOS_INSTALLER_VENDOR_ID={quote_env_value(installer['vendor_id'])}")
    if installer.get("hardware_profile_id"):
        lines.append(f"AIOS_INSTALLER_HARDWARE_PROFILE_ID={quote_env_value(installer['hardware_profile_id'])}")
    partition_strategy = installer.get("partition_strategy", {})
    env_map = {
        "esp_partlabel": "AIOS_INSTALLER_ESP_PARTLABEL",
        "root_partlabel": "AIOS_INSTALLER_ROOT_PARTLABEL",
        "var_partlabel": "AIOS_INSTALLER_VAR_PARTLABEL",
        "esp_partition_index": "AIOS_INSTALLER_ESP_PARTITION_INDEX",
        "root_partition_index": "AIOS_INSTALLER_ROOT_PARTITION_INDEX",
        "var_partition_index": "AIOS_INSTALLER_VAR_PARTITION_INDEX",
    }
    for key, env_name in env_map.items():
        value = partition_strategy.get(key)
        if value is not None:
            lines.append(f"{env_name}={quote_env_value(value)}")
    firmware_hooks = installer.get("firmware_hooks", {})
    if firmware_hooks.get("pre_install"):
        lines.append(f"AIOS_INSTALLER_PRE_INSTALL_HOOK={quote_env_value(firmware_hooks['pre_install'])}")
    if firmware_hooks.get("post_install"):
        lines.append(f"AIOS_INSTALLER_POST_INSTALL_HOOK={quote_env_value(firmware_hooks['post_install'])}")
    if embed_system_image:
        lines.append(f"AIOS_INSTALLER_SOURCE_IMAGE_FILE={quote_env_value(installer['source_payload_path'])}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def copy_installer_hook_assets(root: Path, profile_dir: Path, installer: dict) -> dict[str, str]:
    firmware_hooks = installer.get("firmware_hooks", {})
    hook_dir = profile_dir / "hooks"
    copied: dict[str, str] = {}
    stage_to_filename = {
        "pre_install": "pre-install.sh",
        "post_install": "post-install.sh",
    }
    for stage, filename in stage_to_filename.items():
        target_path = firmware_hooks.get(stage)
        if not target_path:
            continue
        source_path = hook_dir / filename
        ensure_file(source_path, f"{stage} firmware hook asset")
        destination = root / str(target_path).lstrip("/")
        copy_file(source_path, destination, executable=True)
        copied[stage] = str(destination.relative_to(root))
    return copied


def prepare_installer_overlay(
    root: Path,
    platform_id: str,
    system_image: Path,
    installer: dict,
    embed_system_image: bool,
    profile_dir: Path,
) -> dict[str, str]:
    metadata: dict[str, str] = {}
    target_overlay_root = root / installer["target_overlay_dir"].lstrip("/")
    target_env = target_overlay_root / installer.get(
        "updated_platform_env_path", "/etc/aios/updated/platform.env"
    ).lstrip("/")
    write_platform_env(target_env, platform_id)
    metadata["target_platform_env"] = str(target_env.relative_to(root))

    runtime_platform_env_path = installer.get("runtime_platform_env_path")
    hardware_profile_id = installer.get("hardware_profile_id")
    runtime_profile_path = installer.get("runtime_profile_path")
    if runtime_platform_env_path and (hardware_profile_id or runtime_profile_path):
        runtime_env = target_overlay_root / str(runtime_platform_env_path).lstrip("/")
        write_runtime_platform_env(
            runtime_env,
            str(hardware_profile_id) if hardware_profile_id else None,
            str(runtime_profile_path) if runtime_profile_path else None,
        )
        metadata["target_runtime_platform_env"] = str(runtime_env.relative_to(root))
    if runtime_profile_path:
        metadata["target_runtime_profile"] = copy_runtime_profile_asset(
            target_overlay_root, str(runtime_profile_path)
        )

    installer_env = root / "etc" / "aios" / "installer" / "aios-installer.env"
    write_installer_env(installer_env, platform_id, installer, embed_system_image)
    metadata["installer_env"] = str(installer_env.relative_to(root))
    metadata.update(
        {
            f"firmware_hook_{stage}": path
            for stage, path in copy_installer_hook_assets(root, profile_dir, installer).items()
        }
    )

    if embed_system_image:
        payload_path = root / installer["source_payload_path"].lstrip("/")
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(system_image, payload_path)
        metadata["source_payload"] = str(payload_path.relative_to(root))

    return metadata


def prepare_recovery_overlay(
    root: Path,
    platform_id: str,
    recovery: dict,
    hardware_profile_id: str | None,
) -> dict[str, str]:
    target_env = root / recovery.get(
        "updated_platform_env_path", "/etc/aios/updated/platform.env"
    ).lstrip("/")
    write_platform_env(target_env, platform_id)
    metadata = {"recovery_platform_env": str(target_env.relative_to(root))}
    runtime_platform_env_path = recovery.get("runtime_platform_env_path")
    runtime_profile_path = recovery.get("runtime_profile_path")
    if runtime_platform_env_path and (hardware_profile_id or runtime_profile_path):
        runtime_env = root / str(runtime_platform_env_path).lstrip("/")
        write_runtime_platform_env(
            runtime_env,
            hardware_profile_id,
            str(runtime_profile_path) if runtime_profile_path else None,
        )
        metadata["recovery_runtime_platform_env"] = str(runtime_env.relative_to(root))
    if runtime_profile_path:
        metadata["recovery_runtime_profile"] = copy_runtime_profile_asset(
            root, str(runtime_profile_path)
        )
    return metadata


def run_build(script: Path, output_dir: Path, overlay_dir: Path) -> None:
    env = os.environ.copy()
    env["AIOS_IMAGE_EXTRA_OVERLAY_DIR"] = bash_path(overlay_dir)
    env["AIOS_PYTHON_BIN"] = sys.executable
    if "installer" in script.name:
        env["AIOS_INSTALLER_IMAGE_OUTPUT_DIR"] = bash_path(output_dir)
    elif "recovery" in script.name:
        env["AIOS_RECOVERY_IMAGE_OUTPUT_DIR"] = bash_path(output_dir)
    subprocess.run(bash_command(script), cwd=ROOT, check=True, env=env)


def copy_artifact(source: Path, destination_dir: Path, destination_name: str) -> dict[str, object]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / destination_name
    shutil.copy2(source, destination)
    siblings: list[str] = [destination.name]
    prefix = source.stem
    for candidate in sorted(source.parent.iterdir()):
        if candidate == source or not candidate.is_file():
            continue
        if not candidate.name.startswith(prefix + "."):
            continue
        suffix = candidate.name[len(prefix):]
        sibling_destination = destination_dir / f"{destination.stem}{suffix}"
        shutil.copy2(candidate, sibling_destination)
        siblings.append(sibling_destination.name)
    return {
        "path": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": sha256(destination),
        "copied_files": siblings,
    }


def write_flash_script(path: Path, image_name: str) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "device=\"${1:-}\"\n"
        "if [[ -z \"$device\" ]]; then\n"
        "  echo \"usage: $0 /dev/<removable-disk>\" >&2\n"
        "  exit 64\n"
        "fi\n\n"
        "image=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)/" + image_name + "\"\n"
        "sudo dd if=\"$image\" of=\"$device\" bs=16M conv=fsync status=progress\n"
        "sudo sync\n"
    )
    path.chmod(0o755)


def copy_file(source: Path, destination: Path, executable: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if executable:
        destination.chmod(0o755)


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


def render_tier1_profile(
    platform_id: str,
    platform: dict,
    installer_export: dict[str, object],
    recovery_export: dict[str, object],
    system_export: dict[str, object],
    hardware_profile: dict[str, object],
) -> dict[str, object]:
    template = load_yaml(TIER1_TEMPLATE)
    if hardware_profile:
        for key, value in hardware_profile.items():
            if key == "id":
                continue
            template[key] = value
    template.update(
        {
            "id": f"{platform_id}-tier1",
            "arch": platform.get("arch", template.get("arch", "x86_64")),
            "boot_mode": platform.get("boot_mode", "uefi"),
            "boot": hardware_profile.get("boot", platform.get("boot_mode", template.get("boot"))),
            "platform_media_id": platform_id,
            "boot_evidence_dir": BOOT_EVIDENCE_DIR,
            "updated_platform_profile": platform["installer"].get("updated_platform_profile"),
            "platform_media_manifest": "../platform-media-manifest.json",
            "bringup_checklist": "checklists/install-rollback-checklist.md",
            "hardware_validation_report_template": "reports/hardware-validation-template.md",
            "evidence_index_template": "reports/evidence-index-template.json",
            "support_matrix": "support/support-matrix.md",
            "known_limitations": "support/known-limitations.md",
            "artifacts": {
                "installer_media": f"../installer-media/{Path(str(installer_export['path'])).name}",
                "recovery_media": f"../recovery-media/{Path(str(recovery_export['path'])).name}",
                "system_image": f"../system-image/{Path(str(system_export['path'])).name}",
            },
            "validation_workflow": [
                "flash installer media onto removable storage",
                "flash recovery media onto removable storage",
                "boot installer media and install AIOS onto the target disk",
                "boot the installed system and collect at least two unique boot_id evidence records",
                "evaluate the collected records with bringup/scripts/evaluate-boot-evidence.sh",
            ],
        }
    )
    if hardware_profile.get("id"):
        template["canonical_hardware_profile_id"] = hardware_profile["id"]
    return template


def write_bringup_readme(
    path: Path,
    platform_id: str,
    installer_export: dict[str, object],
    recovery_export: dict[str, object],
    system_export: dict[str, object],
    tier1_profile_name: str,
    hardware_profile_name: str | None,
    nominated_profile_names: list[str],
) -> None:
    installer_name = Path(str(installer_export["path"])).name
    recovery_name = Path(str(recovery_export["path"])).name
    system_name = Path(str(system_export["path"])).name
    lines = [
        "# Hardware Bring-up Kit",
        "",
        f"This directory is the repo-level handoff kit for `{platform_id}` hardware bring-up.",
        "",
        "Boundary:",
        "",
        "- It does not prove hardware success by itself.",
        "- Hardware validation is only complete after the target machine produces at least two unique boot_id records and those records pass the evaluator.",
        "",
        "## Included assets",
        "",
        f"- `../installer-media/{installer_name}` and `../installer-media/write-installer-media.sh`: flashable installer media.",
        f"- `../recovery-media/{recovery_name}` and `../recovery-media/write-recovery-media.sh`: flashable recovery media.",
        f"- `../system-image/{system_name}`: reference raw system image payload.",
        f"- `profiles/{tier1_profile_name}`: seeded Tier 1 profile template for the target machine.",
    ]
    if hardware_profile_name:
        lines.append(
            f"- `profiles/{hardware_profile_name}`: canonical hardware profile frozen for this platform handoff."
        )
    else:
        lines.append(
            "- `profiles/`: no canonical hardware profile asset was found, so the generated Tier 1 profile remains the only handoff profile."
        )
    if nominated_profile_names:
        lines.append(
            "- Formal nominated machine profiles: "
            + ", ".join(f"`profiles/{name}`" for name in nominated_profile_names)
            + "."
        )
    lines.extend(
        [
            "- `checklists/install-rollback-checklist.md`: hardware install / first-boot / rollback acceptance checklist.",
            "- `reports/hardware-validation-template.md`: bring-up record template for the target machine.",
            "- `reports/evidence-index-template.json`: structured evidence index template for logs, photos, evaluator outputs, and vendor runtime evidence.",
            "- `support/support-matrix.md`: current declared support matrix for the nominated machine/profile.",
            "- `support/known-limitations.md`: current release boundary and known limitation summary for the nominated machine/profile.",
            "- `assets/aios-boot-evidence.service` and `assets/aios-boot-evidence.sh`: boot evidence assets for retrofitting older systems.",
            "- `scripts/pull-boot-evidence.sh`: fetch boot evidence records from a target host over SSH.",
            "- `scripts/evaluate-boot-evidence.sh`: run the bundled cross-reboot evaluator.",
            "- `scripts/render-hardware-validation.sh`: render the final validation report and evidence index from evaluator output.",
            "- `scripts/collect-device-validation.sh`: collect deviced / device-metadata snapshots plus backend evidence into renderer-ready report args.",
            "- `scripts/collect-and-render-hardware-validation.sh`: optionally pull evidence, collect device validation, run the evaluator, then render the final validation report in one command.",
            "",
            "## Suggested workflow",
            "",
            "1. Review `support/support-matrix.md` and `support/known-limitations.md` before flashing media.",
            "2. Review any formal nominated machine profiles under `profiles/` before deciding which machine to validate first.",
            "3. Fill in the generated Tier 1 profile with the actual vendor/model/support notes.",
            "4. Keep the canonical hardware profile, nominated machine profile, and generated Tier 1 profile together in the bring-up archive.",
            "5. Flash the installer and recovery media onto separate removable disks.",
            "6. Boot the installer media, install AIOS to the target disk, then boot the installed system.",
            "7. Verify that `/etc/aios/updated/platform.env` points at the platform profile expected by this platform media export.",
            "8. If the target image does not already carry `aios-boot-evidence.service`, retrofit it into the mounted sysroot with `scripts/install-boot-evidence-assets.sh`.",
            "9. After each hardware boot, pull `/var/lib/aios/hardware-evidence/boots` back to the host and archive it.",
            "10. Collect `device.state.get` / `device.metadata.get` snapshots into `reports/device-validation/` once the installed system is reachable.",
            "11. If the platform ships a vendor runtime helper, set `AIOS_BRINGUP_VENDOR_RUNTIME_EVIDENCE_DIR` before running `scripts/collect-device-validation.sh` so `vendor-execution.json` artifacts are auto-wired into the final report.",
            "12. Tick off `checklists/install-rollback-checklist.md` as installer boot / install / firstboot / rollback milestones are completed.",
            "13. Once at least two unique boot IDs are collected, run the evaluator and attach its report to the bring-up record.",
            "",
            "## Example commands",
            "",
            "- Flash installer media: `./installer-media/write-installer-media.sh /dev/<installer-usb>`",
            "- Flash recovery media: `./recovery-media/write-recovery-media.sh /dev/<recovery-usb>`",
            "- Pull evidence: `./bringup/scripts/pull-boot-evidence.sh root@<target-host> ./out/hardware-boots`",
            "- Evaluate evidence: `./bringup/scripts/evaluate-boot-evidence.sh ./out/hardware-boots --expect-slot-transition a:b --expect-last-good-slot b`",
            "- Collect device validation snapshots: `AIOS_BRINGUP_DEVICE_VALIDATION_HOST=root@<target-host> AIOS_BRINGUP_VENDOR_RUNTIME_EVIDENCE_DIR=/var/lib/aios/runtimed/jetson-vendor-evidence ./bringup/scripts/collect-device-validation.sh ./out/device-validation`",
            "- Render final report: `./bringup/scripts/render-hardware-validation.sh ./out/hardware-boots/report.json --machine-vendor <vendor> --machine-model <model>`",
            "- Pull + collect + evaluate + render in one step: `AIOS_BRINGUP_PULL_HOST=root@<target-host> AIOS_BRINGUP_VENDOR_RUNTIME_EVIDENCE_DIR=/var/lib/aios/runtimed/jetson-vendor-evidence ./bringup/scripts/collect-and-render-hardware-validation.sh ./out/hardware-boots -- --machine-vendor <vendor> --machine-model <model>`",
            "",
            "Keep the resulting evaluator JSON/Markdown report with the Tier 1 machine record. Until that evidence exists, this platform remains repo/QEMU validated but not hardware validated.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def write_bringup_checklist(path: Path, platform_id: str) -> None:
    lines = [
        f"# {platform_id} Install / Rollback Checklist",
        "",
        f"- [ ] Confirm target machine matches `profiles/{platform_id}-tier1.yaml`.",
        "- [ ] Review `support/support-matrix.md` and `support/known-limitations.md` with the operator.",
        "- [ ] Record device serial number / asset tag / BIOS or firmware revision.",
        "- [ ] Flash installer media and recovery media successfully.",
        "- [ ] Boot installer media on the target machine.",
        "- [ ] Capture photo or serial-log evidence showing installer start.",
        "- [ ] Guided installer summary verified against the intended target disk and platform profile.",
        "- [ ] Complete installation to the target disk.",
        "- [ ] Archive installer report and any vendor firmware hook reports.",
        "- [ ] Boot the installed system successfully.",
        "- [ ] Confirm firstboot completed and `/etc/aios/updated/platform.env` points at the expected platform profile.",
        "- [ ] Collect at least two distinct boot evidence records with unique `boot_id` values.",
        "- [ ] Run `scripts/evaluate-boot-evidence.sh` against the collected evidence.",
        "- [ ] Run `scripts/collect-device-validation.sh` or equivalent and confirm the expected release-grade backend IDs are present.",
        "- [ ] If vendor runtime helper evidence is expected, confirm `vendor-execution.json` artifacts are attached to the final report.",
        "- [ ] Validate rollback path using the recovery media or staged update path.",
        "- [ ] Attach evaluator output, backend-state evidence, vendor runtime evidence, logs, and operator notes to `reports/hardware-validation-template.md`.",
        "- [ ] Mark hardware validation complete only after install, firstboot, rollback, and vendor runtime evidence (when applicable) are attached.",
        "",
    ]
    path.write_text("\n".join(lines))


def write_hardware_validation_report_template(path: Path, platform_id: str) -> None:
    lines = [
        f"# {platform_id} Hardware Validation Report",
        "",
        "## Machine Identity",
        "",
        "- Vendor:",
        "- Model:",
        "- Serial / Asset Tag:",
        "- CPU / RAM / Storage:",
        "- Firmware Version:",
        "",
        "## Media and Build Inputs",
        "",
        "- Installer image:",
        "- Recovery image:",
        "- System image:",
        "- Platform media manifest:",
        "- Tier1 profile:",
        "",
        "## Install Outcome",
        "",
        "- Installer boot observed:",
        "- Guided installer summary verified:",
        "- Target disk selected:",
        "- Installer report attached:",
        "- Vendor firmware hook report attached:",
        "",
        "## First Boot Outcome",
        "",
        "- Firstboot completed:",
        "- Updated platform profile verified:",
        "- Boot evidence directory collected:",
        "- Boot IDs observed:",
        "",
        "## Device And Multimodal Validation",
        "",
        "- deviced health:",
        "- device.state.get overall backend status:",
        "- device.state.get available backend count:",
        "- device.state.get ui_tree current support:",
        "- device.metadata.get readiness status:",
        "- device.metadata.get backend overall status:",
        "- device.metadata.get available modalities:",
        "- release-grade backend ids:",
        "- release-grade backend origins:",
        "- release-grade backend stacks:",
        "- release-grade contract kinds:",
        "- backend-state artifact attached:",
        "- vendor runtime sign-off status:",
        "- vendor runtime provider ids:",
        "- vendor runtime service ids:",
        "- vendor runtime statuses:",
        "- vendor runtime kinds:",
        "- vendor runtime backend ids:",
        "- vendor runtime evidence count:",
        "- vendor runtime evidence attached:",
        "",
        "## Rollback Outcome",
        "",
        "- Rollback trigger used:",
        "- Recovery media boot observed:",
        "- Post-rollback boot observed:",
        "- Final active slot / last-good-slot:",
        "",
        "## Attached Evidence",
        "",
        "- Evaluator JSON:",
        "- Evaluator Markdown:",
        "- Installer log:",
        "- Recovery log:",
        "- Photos / serial captures:",
        "- Vendor runtime evidence:",
        "",
        "## Open Issues",
        "",
        "- None / list issues here.",
        "",
        "## Sign-off",
        "",
        "- Operator:",
        "- Date:",
        "- Validation status: pending / passed / failed",
        "",
    ]
    path.write_text("\n".join(lines))


def write_evidence_index_template(path: Path, platform_id: str) -> None:
    payload = {
        "platform_id": platform_id,
        "validation_status": "pending",
        "artifacts": {
            "support_matrix": "support/support-matrix.md",
            "known_limitations": "support/known-limitations.md",
            "installer_report": "",
            "vendor_firmware_hook_report": "",
            "boot_evidence_dir": "",
            "evaluator_json": "",
            "evaluator_markdown": "",
            "device_backend_state_artifact": "",
            "vendor_runtime_evidence": [],
            "recovery_log": "",
            "photos": [],
        },
        "notes": [],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def capability_value(value: object | None) -> str:
    if value is None:
        return "unspecified"
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).strip()
    return text or "unspecified"


def render_support_matrix(
    platform_id: str,
    platform: dict,
    tier1_profile: dict[str, object],
    hardware_profile_name: str | None,
    nominated_profile_names: list[str],
) -> str:
    installer = platform.get("installer") or {}
    recovery = platform.get("recovery") or {}
    expectations = tier1_profile.get("boot_evidence_expectations") or {}
    validation_checks = [
        f"- Minimum boot IDs: {expectations.get('min_boots', 2)}",
        f"- Require boot success: {capability_value(expectations.get('require_boot_success'))}",
        f"- Require deployment state: {capability_value(expectations.get('require_deployment_state'))}",
        f"- Require boot state: {capability_value(expectations.get('require_boot_state'))}",
        f"- Require bootctl status: {capability_value(expectations.get('require_bootctl_status'))}",
        f"- Require firmware status: {capability_value(expectations.get('require_firmware_status'))}",
        f"- Require sysupdate listing: {capability_value(expectations.get('require_sysupdate_listing'))}",
    ]
    if expectations.get("expect_slot_transition"):
        validation_checks.append(f"- Expected slot transition: {expectations['expect_slot_transition']}")
    if expectations.get("expect_last_good_slot"):
        validation_checks.append(f"- Expected last-good-slot: {expectations['expect_last_good_slot']}")
    capabilities = [
        ("GPU", tier1_profile.get("gpu"), "Conditional acceleration path; requires runtime/backend evidence where applicable."),
        ("NPU", tier1_profile.get("npu"), "Conditional acceleration path; not release-ready without platform evidence."),
        ("Wi-Fi", tier1_profile.get("wifi"), "Machine capability declaration only; operator must verify on hardware."),
        ("Bluetooth", tier1_profile.get("bluetooth"), "Machine capability declaration only; operator must verify on hardware."),
        ("Audio", tier1_profile.get("audio"), "Device/media pipeline still depends on native backend validation."),
        ("Camera", tier1_profile.get("camera"), "Device/media pipeline still depends on native backend validation."),
    ]
    capability_lines = [
        "| Capability | Declared State | Notes |",
        "|------------|----------------|-------|",
    ]
    for name, state, note in capabilities:
        capability_lines.append(f"| {name} | {capability_value(state)} | {note} |")
    lines = [
        f"# {platform_id} Bring-up Support Matrix",
        "",
        "## Machine Binding",
        "",
        f"- Hardware profile ID: {tier1_profile.get('canonical_hardware_profile_id') or tier1_profile.get('id') or platform_id}",
        f"- Canonical hardware profile asset: {'profiles/' + hardware_profile_name if hardware_profile_name else 'not bundled'}",
        f"- Generated Tier 1 profile: profiles/{platform_id}-tier1.yaml",
        "- Formal nominated machine profiles: "
        + (", ".join(f"profiles/{name}" for name in nominated_profile_names) if nominated_profile_names else "none bundled"),
        f"- Platform label: {installer.get('platform_label', platform_id)}",
        f"- Vendor: {tier1_profile.get('vendor_id', 'unspecified')}",
        f"- Model: {tier1_profile.get('model', 'unspecified')}",
        f"- Architecture: {tier1_profile.get('arch', platform.get('arch', 'unspecified'))}",
        f"- Boot mode: {tier1_profile.get('boot', tier1_profile.get('boot_mode', platform.get('boot_mode', 'unspecified')))}",
        f"- Bring-up status: {tier1_profile.get('bringup_status', 'unspecified')}",
        f"- Hardware evidence required: {capability_value(tier1_profile.get('hardware_evidence_required'))}",
        "",
        "## Platform Wiring",
        "",
        f"- Updated platform profile: {installer.get('updated_platform_profile', 'unspecified')}",
        f"- Installer runtime profile: {installer.get('runtime_profile_path', 'unspecified')}",
        f"- Recovery runtime profile: {recovery.get('runtime_profile_path', 'unspecified')}",
        f"- Pre-install firmware hook: {(installer.get('firmware_hooks') or {}).get('pre_install', 'none')}",
        f"- Post-install firmware hook: {(installer.get('firmware_hooks') or {}).get('post_install', 'none')}",
        "",
        "## Declared Capabilities",
        "",
        *capability_lines,
        "",
        "## Validation Gate",
        "",
        *validation_checks,
        "",
    ]
    return "\n".join(lines)


def render_known_limitations(
    platform_id: str,
    tier1_profile: dict[str, object],
    hardware_profile_name: str | None,
) -> str:
    items: list[str] = []
    for note in tier1_profile.get("notes") or []:
        note_text = str(note).strip()
        if note_text:
            items.append(note_text)
    if hardware_profile_name is None:
        items.append(
            "No canonical hardware profile asset was bundled with this handoff; the generated Tier 1 profile must be frozen before release acceptance."
        )
    if tier1_profile.get("hardware_evidence_required"):
        items.append(
            "A real hardware validation report with at least two unique boot IDs is still required before this platform can be treated as hardware validated."
        )
    if tier1_profile.get("bringup_status") != "hardware-validated":
        items.append(
            f"Current bring-up status remains `{tier1_profile.get('bringup_status', 'unspecified')}`; repo/QEMU validation is not sufficient for release sign-off."
        )
    unique_items: list[str] = []
    for item in items:
        if item not in unique_items:
            unique_items.append(item)
    lines = [
        f"# {platform_id} Known Limitations",
        "",
    ]
    if not unique_items:
        lines.append("- None recorded.")
    else:
        lines.extend(f"- {item}" for item in unique_items)
    lines.append("")
    return "\n".join(lines)


def prepare_bringup_kit(
    root: Path,
    platform_id: str,
    platform: dict,
    installer_export: dict[str, object],
    recovery_export: dict[str, object],
    system_export: dict[str, object],
) -> dict[str, object]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    scripts_dir = root / "scripts"
    assets_dir = root / "assets"
    profiles_dir = root / "profiles"
    checklists_dir = root / "checklists"
    reports_dir = root / "reports"
    support_dir = root / "support"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir.mkdir(parents=True, exist_ok=True)
    checklists_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    support_dir.mkdir(parents=True, exist_ok=True)

    hardware_profile_id = platform.get("installer", {}).get("hardware_profile_id")
    canonical_hardware_profile_path, canonical_hardware_profile = load_hardware_profile(hardware_profile_id)
    canonical_hardware_profile_name: str | None = None
    if canonical_hardware_profile_path is not None:
        canonical_hardware_profile_name = canonical_hardware_profile_path.name
        copy_file(
            canonical_hardware_profile_path,
            profiles_dir / canonical_hardware_profile_name,
        )
    nominated_profile_names: list[str] = []
    for entry in matching_tier1_nominations(platform_id, hardware_profile_id):
        profile_path_text = entry.get("profile_path")
        if not isinstance(profile_path_text, str) or not profile_path_text:
            continue
        source_path = ROOT / profile_path_text
        ensure_file(source_path, "nominated machine profile")
        profile_name = source_path.name
        destination = profiles_dir / profile_name
        if not destination.exists():
            copy_file(source_path, destination)
        if profile_name not in nominated_profile_names:
            nominated_profile_names.append(profile_name)

    copy_file(BOOT_EVIDENCE_SERVICE, assets_dir / BOOT_EVIDENCE_SERVICE.name)
    copy_file(BOOT_EVIDENCE_SCRIPT, assets_dir / BOOT_EVIDENCE_SCRIPT.name, executable=True)
    copy_file(BOOT_EVIDENCE_EVALUATOR, scripts_dir / BOOT_EVIDENCE_EVALUATOR.name, executable=True)
    copy_file(
        HARDWARE_REPORT_RENDERER,
        scripts_dir / HARDWARE_REPORT_RENDERER.name,
        executable=True,
    )
    copy_file(
        DEVICE_VALIDATION_COLLECTOR,
        scripts_dir / DEVICE_VALIDATION_COLLECTOR.name,
        executable=True,
    )

    install_script = scripts_dir / "install-boot-evidence-assets.sh"
    write_executable(
        install_script,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "sysroot=\"${1:-}\"\n"
        "if [[ -z \"$sysroot\" ]]; then\n"
        "  echo \"usage: $0 /path/to/mounted-sysroot\" >&2\n"
        "  exit 64\n"
        "fi\n\n"
        "script_dir=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        "assets_dir=\"$(cd \"$script_dir/../assets\" && pwd)\"\n"
        "mkdir -p \"$sysroot/usr/lib/systemd/system\" \"$sysroot/usr/libexec/aios\" \"$sysroot/etc/systemd/system/multi-user.target.wants\"\n"
        "cp \"$assets_dir/aios-boot-evidence.service\" \"$sysroot/usr/lib/systemd/system/aios-boot-evidence.service\"\n"
        "cp \"$assets_dir/aios-boot-evidence.sh\" \"$sysroot/usr/libexec/aios/aios-boot-evidence.sh\"\n"
        "chmod 0755 \"$sysroot/usr/libexec/aios/aios-boot-evidence.sh\"\n"
        "ln -sfn /usr/lib/systemd/system/aios-boot-evidence.service \"$sysroot/etc/systemd/system/multi-user.target.wants/aios-boot-evidence.service\"\n"
        "printf 'installed boot evidence assets into %s\\n' \"$sysroot\"\n"
    )

    pull_script = scripts_dir / "pull-boot-evidence.sh"
    write_executable(
        pull_script,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "host=\"${1:-}\"\n"
        "output_dir=\"${2:-./boots}\"\n"
        f"remote_dir=\"${{AIOS_BRINGUP_REMOTE_EVIDENCE_DIR:-{BOOT_EVIDENCE_DIR}}}\"\n"
        "remote_sudo=\"${AIOS_BRINGUP_REMOTE_SUDO:-sudo}\"\n"
        "if [[ -z \"$host\" ]]; then\n"
        "  echo \"usage: $0 user@host [output-dir]\" >&2\n"
        "  exit 64\n"
        "fi\n\n"
        "check_cmd=\"test -d '$remote_dir'\"\n"
        "tar_cmd=\"tar -C '$remote_dir' -cf - .\"\n"
        "if [[ -n \"$remote_sudo\" ]]; then\n"
        "  check_cmd=\"$remote_sudo $check_cmd\"\n"
        "  tar_cmd=\"$remote_sudo $tar_cmd\"\n"
        "fi\n\n"
        "mkdir -p \"$output_dir\"\n"
        "ssh \"$host\" \"$check_cmd\" >/dev/null\n"
        "ssh \"$host\" \"$tar_cmd\" | tar -xf - -C \"$output_dir\"\n"
        "printf 'pulled boot evidence into %s\\n' \"$output_dir\"\n"
    )

    evaluate_wrapper = scripts_dir / "evaluate-boot-evidence.sh"
    write_executable(
        evaluate_wrapper,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "input_dir=\"${1:-}\"\n"
        "if [[ -z \"$input_dir\" ]]; then\n"
        "  echo \"usage: $0 /path/to/boot-evidence-dir [extra evaluator args...]\" >&2\n"
        "  exit 64\n"
        "fi\n\n"
        "script_dir=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        f"profile_path=\"$script_dir/../profiles/{platform_id}-tier1.yaml\"\n"
        "cmd=(python3 \"$script_dir/evaluate-aios-hardware-boot-evidence.py\" --input-dir \"$input_dir\")\n"
        "if [[ -f \"$profile_path\" ]]; then\n"
        "  cmd+=(--profile \"$profile_path\")\n"
        "fi\n"
        "cmd+=(\"${@:2}\")\n"
        "\"${cmd[@]}\"\n"
    )

    device_validation_wrapper = scripts_dir / "collect-device-validation.sh"
    write_executable(
        device_validation_wrapper,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "script_dir=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        "output_dir=\"${1:-${AIOS_BRINGUP_DEVICE_VALIDATION_DIR:-$script_dir/../reports/device-validation}}\"\n"
        "remote_host=\"${AIOS_BRINGUP_DEVICE_VALIDATION_HOST:-${AIOS_BRINGUP_PULL_HOST:-}}\"\n"
        "remote_python=\"${AIOS_BRINGUP_REMOTE_PYTHON:-python3}\"\n"
        "remote_sudo=\"${AIOS_BRINGUP_REMOTE_SUDO:-sudo}\"\n"
        "deviced_socket=\"${AIOS_BRINGUP_DEVICED_SOCKET:-/run/aios/deviced/deviced.sock}\"\n"
        "device_metadata_socket=\"${AIOS_BRINGUP_DEVICE_METADATA_SOCKET:-/run/aios/device-metadata-provider/device-metadata-provider.sock}\"\n"
        "vendor_runtime_evidence_dir=\"${AIOS_BRINGUP_VENDOR_RUNTIME_EVIDENCE_DIR:-}\"\n"
        "timeout=\"${AIOS_BRINGUP_DEVICE_VALIDATION_TIMEOUT:-5}\"\n"
        "cmd=(python3 \"$script_dir/collect-aios-device-validation.py\" --output-dir \"$output_dir\" --deviced-socket \"$deviced_socket\" --device-metadata-socket \"$device_metadata_socket\" --timeout \"$timeout\")\n"
        "if [[ -n \"$vendor_runtime_evidence_dir\" ]]; then\n"
        "  cmd+=(--vendor-runtime-evidence-dir \"$vendor_runtime_evidence_dir\")\n"
        "fi\n"
        "if [[ -n \"$remote_host\" ]]; then\n"
        "  cmd+=(--remote-host \"$remote_host\" --remote-python \"$remote_python\")\n"
        "  if [[ -n \"$remote_sudo\" ]]; then\n"
        "    cmd+=(--remote-sudo \"$remote_sudo\")\n"
        "  fi\n"
        "fi\n"
        "cmd+=(\"${@:2}\")\n"
        "\"${cmd[@]}\"\n"
    )

    render_wrapper = scripts_dir / "render-hardware-validation.sh"
    write_executable(
        render_wrapper,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "evaluator_json=\"${1:-}\"\n"
        "if [[ -z \"$evaluator_json\" ]]; then\n"
        "  echo \"usage: $0 /path/to/evaluator-report.json [extra renderer args...]\" >&2\n"
        "  exit 64\n"
        "fi\n\n"
        "script_dir=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        f"profile_path=\"$script_dir/../profiles/{platform_id}-tier1.yaml\"\n"
        "report_out=\"${AIOS_BRINGUP_REPORT_OUT:-$script_dir/../reports/hardware-validation-report.md}\"\n"
        "evidence_index_out=\"${AIOS_BRINGUP_EVIDENCE_INDEX_OUT:-$script_dir/../reports/hardware-validation-evidence.json}\"\n"
        "support_matrix=\"${AIOS_BRINGUP_SUPPORT_MATRIX:-$script_dir/../support/support-matrix.md}\"\n"
        "known_limitations=\"${AIOS_BRINGUP_KNOWN_LIMITATIONS:-$script_dir/../support/known-limitations.md}\"\n"
        "device_validation_dir=\"${AIOS_BRINGUP_DEVICE_VALIDATION_DIR:-$script_dir/../reports/device-validation}\"\n"
        "device_validation_args_file=\"${AIOS_BRINGUP_DEVICE_VALIDATION_ARGS_FILE:-$device_validation_dir/renderer-args.txt}\"\n"
        "auto_renderer_args=()\n"
        "if [[ \"${AIOS_BRINGUP_AUTOWIRE_DEVICE_VALIDATION:-1}\" != \"0\" && -f \"$device_validation_args_file\" ]]; then\n"
        "  mapfile -t auto_renderer_args < \"$device_validation_args_file\"\n"
        "fi\n"
        "cmd=(python3 \"$script_dir/render-aios-hardware-validation-report.py\" --evaluator-json \"$evaluator_json\" --report-out \"$report_out\" --evidence-index-out \"$evidence_index_out\" --support-matrix \"$support_matrix\" --known-limitations \"$known_limitations\")\n"
        "if [[ -f \"$profile_path\" ]]; then\n"
        "  cmd+=(--profile \"$profile_path\")\n"
        "fi\n"
        "cmd+=(\"${auto_renderer_args[@]}\")\n"
        "cmd+=(\"${@:2}\")\n"
        "\"${cmd[@]}\"\n"
    )

    collect_wrapper = scripts_dir / "collect-and-render-hardware-validation.sh"
    write_executable(
        collect_wrapper,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        "input_dir=\"${1:-}\"\n"
        "if [[ -z \"$input_dir\" ]]; then\n"
        "  echo \"usage: $0 /path/to/boot-evidence-dir [evaluator args ...] [-- renderer args ...]\" >&2\n"
        "  echo \"optional: set AIOS_BRINGUP_PULL_HOST=user@host to pull evidence before evaluating\" >&2\n"
        "  exit 64\n"
        "fi\n"
        "shift\n\n"
        "script_dir=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        "evaluator_json=\"${AIOS_BRINGUP_EVALUATOR_JSON_OUT:-$script_dir/../reports/hardware-validation-evaluator.json}\"\n"
        "evaluator_md=\"${AIOS_BRINGUP_EVALUATOR_MD_OUT:-$script_dir/../reports/hardware-validation-evaluator.md}\"\n"
        "device_validation_dir=\"${AIOS_BRINGUP_DEVICE_VALIDATION_DIR:-$script_dir/../reports/device-validation}\"\n"
        "device_validation_mode=\"${AIOS_BRINGUP_COLLECT_DEVICE_VALIDATION:-auto}\"\n"
        "device_validation_host=\"${AIOS_BRINGUP_DEVICE_VALIDATION_HOST:-${AIOS_BRINGUP_PULL_HOST:-}}\"\n"
        "local_deviced_socket=\"${AIOS_BRINGUP_DEVICED_SOCKET:-/run/aios/deviced/deviced.sock}\"\n"
        "local_device_metadata_socket=\"${AIOS_BRINGUP_DEVICE_METADATA_SOCKET:-/run/aios/device-metadata-provider/device-metadata-provider.sock}\"\n"
        "mode=\"evaluator\"\n"
        "evaluator_args=()\n"
        "renderer_args=()\n"
        "while [[ $# -gt 0 ]]; do\n"
        "  if [[ \"$1\" == \"--\" ]]; then\n"
        "    mode=\"renderer\"\n"
        "    shift\n"
        "    continue\n"
        "  fi\n"
        "  if [[ \"$mode\" == \"evaluator\" ]]; then\n"
        "    evaluator_args+=(\"$1\")\n"
        "  else\n"
        "    renderer_args+=(\"$1\")\n"
        "  fi\n"
        "  shift\n"
        "done\n\n"
        "if [[ -n \"${AIOS_BRINGUP_PULL_HOST:-}\" ]]; then\n"
        "  \"$script_dir/pull-boot-evidence.sh\" \"$AIOS_BRINGUP_PULL_HOST\" \"$input_dir\"\n"
        "fi\n\n"
        "should_collect_device_validation=0\n"
        "if [[ \"$device_validation_mode\" == \"1\" || \"$device_validation_mode\" == \"always\" ]]; then\n"
        "  should_collect_device_validation=1\n"
        "elif [[ \"$device_validation_mode\" != \"0\" && \"$device_validation_mode\" != \"never\" ]]; then\n"
        "  if [[ -n \"$device_validation_host\" ]]; then\n"
        "    should_collect_device_validation=1\n"
        "  elif [[ -S \"$local_deviced_socket\" || -S \"$local_device_metadata_socket\" ]]; then\n"
        "    should_collect_device_validation=1\n"
        "  fi\n"
        "fi\n"
        "if [[ \"$should_collect_device_validation\" == \"1\" ]]; then\n"
        "  \"$script_dir/collect-device-validation.sh\" \"$device_validation_dir\"\n"
        "elif [[ \"$device_validation_mode\" == \"1\" || \"$device_validation_mode\" == \"always\" ]]; then\n"
        "  echo \"device validation collection requested but no local sockets or remote host are available\" >&2\n"
        "  exit 65\n"
        "fi\n\n"
        "\"$script_dir/evaluate-boot-evidence.sh\" \"$input_dir\" --output \"$evaluator_json\" --report-md \"$evaluator_md\" \"${evaluator_args[@]}\"\n"
        "\"$script_dir/render-hardware-validation.sh\" \"$evaluator_json\" --evaluator-md \"$evaluator_md\" \"${renderer_args[@]}\"\n"
        "printf 'wrote evaluator json to %s\\n' \"$evaluator_json\"\n"
        "printf 'wrote evaluator markdown to %s\\n' \"$evaluator_md\"\n"
        "if [[ -f \"$device_validation_dir/collection-summary.json\" ]]; then\n"
        "  printf 'wrote device validation summary to %s\\n' \"$device_validation_dir/collection-summary.json\"\n"
        "fi\n"
        "printf 'wrote final hardware validation report to %s\\n' \"${AIOS_BRINGUP_REPORT_OUT:-$script_dir/../reports/hardware-validation-report.md}\"\n"
        "printf 'wrote final evidence index to %s\\n' \"${AIOS_BRINGUP_EVIDENCE_INDEX_OUT:-$script_dir/../reports/hardware-validation-evidence.json}\"\n"
    )

    tier1_profile_name = f"{platform_id}-tier1.yaml"
    tier1_profile_path = profiles_dir / tier1_profile_name
    tier1_profile = render_tier1_profile(
        platform_id,
        platform,
        installer_export,
        recovery_export,
        system_export,
        canonical_hardware_profile,
    )
    tier1_profile_path.write_text(yaml.safe_dump(tier1_profile, sort_keys=False, allow_unicode=True))

    checklist_path = checklists_dir / "install-rollback-checklist.md"
    report_template_path = reports_dir / "hardware-validation-template.md"
    evidence_index_path = reports_dir / "evidence-index-template.json"
    support_matrix_path = support_dir / "support-matrix.md"
    known_limitations_path = support_dir / "known-limitations.md"
    write_bringup_checklist(checklist_path, platform_id)
    write_hardware_validation_report_template(report_template_path, platform_id)
    write_evidence_index_template(evidence_index_path, platform_id)
    support_matrix_path.write_text(
        render_support_matrix(
            platform_id,
            platform,
            tier1_profile,
            canonical_hardware_profile_name,
            nominated_profile_names,
        )
    )
    known_limitations_path.write_text(
        render_known_limitations(
            platform_id,
            tier1_profile,
            canonical_hardware_profile_name,
        )
    )

    readme_path = root / "README.md"
    write_bringup_readme(
        readme_path,
        platform_id,
        installer_export,
        recovery_export,
        system_export,
        tier1_profile_name,
        canonical_hardware_profile_name,
        nominated_profile_names,
    )

    return {
        "kit_dir": str(root),
        "readme": str(readme_path),
        "hardware_profile_id": hardware_profile_id,
        "canonical_hardware_profile": None
        if canonical_hardware_profile_name is None
        else str(profiles_dir / canonical_hardware_profile_name),
        "nominated_profiles": [str(profiles_dir / name) for name in nominated_profile_names],
        "tier1_profile": str(tier1_profile_path),
        "boot_evidence_dir": BOOT_EVIDENCE_DIR,
        "checklist": str(checklist_path),
        "report_template": str(report_template_path),
        "evidence_index_template": str(evidence_index_path),
        "support_matrix": str(support_matrix_path),
        "known_limitations": str(known_limitations_path),
        "scripts": {
            "install_boot_evidence_assets": str(install_script),
            "pull_boot_evidence": str(pull_script),
            "evaluate_boot_evidence": str(evaluate_wrapper),
            "collect_device_validation": str(device_validation_wrapper),
            "render_hardware_validation": str(render_wrapper),
            "collect_and_render_hardware_validation": str(collect_wrapper),
            "evaluator": str(scripts_dir / BOOT_EVIDENCE_EVALUATOR.name),
            "report_renderer": str(scripts_dir / HARDWARE_REPORT_RENDERER.name),
            "device_validation_collector": str(scripts_dir / DEVICE_VALIDATION_COLLECTOR.name),
        },
        "assets": {
            "boot_evidence_service": str(assets_dir / BOOT_EVIDENCE_SERVICE.name),
            "boot_evidence_script": str(assets_dir / BOOT_EVIDENCE_SCRIPT.name),
        },
    }


def main() -> int:
    args = parse_args()
    platform_profile = args.platform_profile or (ROOT / "aios" / "image" / "platforms" / args.platform / "profile.yaml")
    ensure_file(platform_profile, "platform profile")
    platform = load_yaml(platform_profile)
    platform_id = platform.get("platform_id", args.platform)
    output_dir = args.output_dir or (ROOT / "out" / "platform-media" / platform_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = platform_profile.parent
    installer = platform["installer"]
    recovery = platform["recovery"]

    build_metadata: dict[str, object] = {"rebuilt_images": False}
    installer_image = args.installer_image
    recovery_image = args.recovery_image

    installer_overlay_dir = output_dir / "config" / "installer-overlay"
    recovery_overlay_dir = output_dir / "config" / "recovery-overlay"
    if installer_overlay_dir.exists():
        shutil.rmtree(installer_overlay_dir)
    if recovery_overlay_dir.exists():
        shutil.rmtree(recovery_overlay_dir)
    installer_metadata = prepare_installer_overlay(
        installer_overlay_dir,
        platform_id,
        args.system_image,
        installer,
        args.embed_system_image,
        profile_dir,
    )
    recovery_metadata = prepare_recovery_overlay(
        recovery_overlay_dir,
        platform_id,
        recovery,
        installer.get("hardware_profile_id"),
    )

    if args.build_platform_images:
        ensure_file(args.system_image, "system image")
        temp_root = Path(tempfile.mkdtemp(prefix="aios-platform-media-"))
        runtime_installer_overlay = temp_root / "installer-overlay"
        runtime_recovery_overlay = temp_root / "recovery-overlay"
        shutil.copytree(installer_overlay_dir, runtime_installer_overlay)
        shutil.copytree(recovery_overlay_dir, runtime_recovery_overlay)

        installer_build_dir = output_dir / "build" / "installer"
        recovery_build_dir = output_dir / "build" / "recovery"
        installer_build_dir.mkdir(parents=True, exist_ok=True)
        recovery_build_dir.mkdir(parents=True, exist_ok=True)
        run_build(ROOT / "scripts" / "build-aios-installer-image.sh", installer_build_dir, runtime_installer_overlay)
        run_build(ROOT / "scripts" / "build-aios-recovery-image.sh", recovery_build_dir, runtime_recovery_overlay)
        installer_image = installer_build_dir / "aios-qemu-x86_64-installer.raw"
        recovery_image = recovery_build_dir / "aios-qemu-x86_64-recovery.raw"
        build_metadata = {
            "rebuilt_images": True,
            "installer_output_dir": str(installer_build_dir),
            "recovery_output_dir": str(recovery_build_dir),
        }

    ensure_file(args.system_image, "system image")
    ensure_file(installer_image, "installer image")
    ensure_file(recovery_image, "recovery image")

    installer_export = copy_artifact(installer_image, output_dir / "installer-media", f"aios-{platform_id}-installer.raw")
    recovery_export = copy_artifact(recovery_image, output_dir / "recovery-media", f"aios-{platform_id}-recovery.raw")
    system_export = copy_artifact(args.system_image, output_dir / "system-image", f"aios-{platform_id}-system.raw")

    write_flash_script(output_dir / "installer-media" / "write-installer-media.sh", Path(str(installer_export["path"])).name)
    write_flash_script(output_dir / "recovery-media" / "write-recovery-media.sh", Path(str(recovery_export["path"])).name)

    bringup = prepare_bringup_kit(output_dir / "bringup", platform_id, platform, installer_export, recovery_export, system_export)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform_id": platform_id,
        "platform_profile": str(platform_profile),
        "installer": installer,
        "recovery": recovery,
        "build": build_metadata,
        "embed_system_image": args.embed_system_image,
        "artifacts": {
            "installer_media": installer_export,
            "recovery_media": recovery_export,
            "system_image": system_export,
        },
        "config": {
            "installer_overlay": str(installer_overlay_dir),
            "installer_overlay_files": installer_metadata,
            "recovery_overlay": str(recovery_overlay_dir),
            "recovery_overlay_files": recovery_metadata,
        },
        "bringup": bringup,
    }

    manifest_path = output_dir / "platform-media-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
