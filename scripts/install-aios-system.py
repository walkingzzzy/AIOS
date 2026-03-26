#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE_DIR = ROOT / "out" / "aios-system-delivery"
DEFAULT_RECOVERY_IMAGE_DIR = ROOT / "aios" / "image" / "recovery.output"
UTF8 = "utf-8"
LOCAL_CPU_WORKER_LAUNCHER = "/usr/libexec/aios/runtime/workers/launch_local_cpu_worker.sh"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install an AIOS system delivery bundle into a target sysroot"
    )
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--sysroot", type=Path, required=True)
    parser.add_argument(
        "--install-id",
        help="Stable install identifier written into firstboot metadata",
    )
    parser.add_argument("--install-source", default="system-delivery-bundle")
    parser.add_argument("--installer-version", help="Installer version string")
    parser.add_argument("--install-mode", default="offline-copy")
    parser.add_argument("--slot", choices=("a", "b"), default="a")
    parser.add_argument(
        "--boot-backend",
        choices=("state-file", "bootctl", "firmware"),
        default="firmware",
    )
    parser.add_argument("--recovery-image-dir", type=Path, default=DEFAULT_RECOVERY_IMAGE_DIR)
    parser.add_argument("--vendor-id")
    parser.add_argument("--hardware-profile-id")
    parser.add_argument("--runtime-profile-path")
    ai_group = parser.add_mutually_exclusive_group()
    ai_group.add_argument("--ai-enabled", dest="ai_enabled", action="store_true")
    ai_group.add_argument("--ai-disabled", dest="ai_enabled", action="store_false")
    parser.set_defaults(ai_enabled=True)
    parser.add_argument(
        "--ai-mode",
        choices=("local", "cloud", "hybrid", "later"),
        default="hybrid",
    )
    parser.add_argument(
        "--ai-privacy-profile",
        choices=("strict-local", "balanced", "cloud-enhanced"),
        default="balanced",
    )
    parser.add_argument(
        "--ai-auto-pull-default-model",
        action="store_true",
        help="Allow firstboot onboarding to auto-pull the suggested default model",
    )
    parser.add_argument(
        "--ai-auto-model-source",
        default="ollama-library",
        help="Suggested default model source written into installer/firstboot metadata",
    )
    parser.add_argument(
        "--ai-auto-model-id",
        default="qwen2.5:7b-instruct",
        help="Suggested default model identifier written into installer/firstboot metadata",
    )
    parser.add_argument(
        "--ai-endpoint-base-url",
        default="",
        help="Optional remote AI endpoint base URL recorded for firstboot onboarding",
    )
    parser.add_argument(
        "--ai-endpoint-model",
        default="",
        help="Optional remote AI endpoint model recorded for firstboot onboarding",
    )
    parser.add_argument("--esp-partlabel", default="AIOS-ESP")
    parser.add_argument("--root-partlabel", default="AIOS-root")
    parser.add_argument("--var-partlabel", default="AIOS-var")
    parser.add_argument("--esp-partition-index", type=int, default=1)
    parser.add_argument("--root-partition-index", type=int, default=2)
    parser.add_argument("--var-partition-index", type=int, default=3)
    parser.add_argument("--pre-install-hook", type=Path)
    parser.add_argument("--post-install-hook", type=Path)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the target sysroot before installing",
    )
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def git_installer_version() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0 and completed.stdout.strip():
        return f"git-{completed.stdout.strip()}"
    return "local-dev"


def resolve_bash_binary() -> Path | None:
    if os.name == "nt":
        candidates: list[Path] = []
        for env_name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
            program_root = os.environ.get(env_name)
            if not program_root:
                continue
            git_root = Path(program_root) / "Git"
            candidates.extend([git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe"])
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None
    resolved = shutil.which("bash")
    return Path(resolved) if resolved else None


def bash_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if drive:
        return f"/{drive}{resolved.as_posix()[2:]}"
    return resolved.as_posix()


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding=UTF8).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(f"{key}={value}\n" for key, value in values.items())
    path.write_text(rendered, encoding=UTF8)


def env_flag(value: bool) -> str:
    return "1" if value else "0"


def build_ai_config(args: argparse.Namespace) -> dict[str, object]:
    return {
        "enabled": bool(args.ai_enabled),
        "mode": args.ai_mode,
        "privacy_profile": args.ai_privacy_profile,
        "auto_pull_default_model": bool(args.ai_auto_pull_default_model),
        "auto_model_source": args.ai_auto_model_source,
        "auto_model_id": args.ai_auto_model_id,
        "endpoint_base_url": args.ai_endpoint_base_url,
        "endpoint_model": args.ai_endpoint_model,
    }


def write_runtime_platform_env(
    sysroot: Path,
    hardware_profile_id: str | None,
    ai_config: dict[str, object],
    runtime_profile_path: str | None = None,
) -> Path:
    env_path = sysroot / "etc" / "aios" / "runtime" / "platform.env"
    values = load_env(env_path)
    if hardware_profile_id:
        values["AIOS_RUNTIMED_HARDWARE_PROFILE_ID"] = hardware_profile_id
    if runtime_profile_path:
        values["AIOS_RUNTIMED_RUNTIME_PROFILE"] = runtime_profile_path
    values["AIOS_RUNTIMED_PRODUCT_MODE"] = "1"
    values["AIOS_RUNTIMED_AI_ENABLED"] = env_flag(bool(ai_config["enabled"]))
    values["AIOS_RUNTIMED_AI_MODE"] = str(ai_config["mode"])
    values["AIOS_RUNTIMED_AI_PRIVACY_PROFILE"] = str(ai_config["privacy_profile"])
    if ai_config.get("enabled") and ai_config.get("mode") in {"local", "hybrid"}:
        values["AIOS_RUNTIMED_LOCAL_CPU_COMMAND"] = LOCAL_CPU_WORKER_LAUNCHER
    else:
        values.pop("AIOS_RUNTIMED_LOCAL_CPU_COMMAND", None)
    endpoint_base_url = str(ai_config.get("endpoint_base_url") or "")
    endpoint_model = str(ai_config.get("endpoint_model") or "")
    if endpoint_base_url:
        values["AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL"] = endpoint_base_url
    else:
        values.pop("AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL", None)
    if endpoint_model:
        values["AIOS_RUNTIMED_AI_ENDPOINT_MODEL"] = endpoint_model
    else:
        values.pop("AIOS_RUNTIMED_AI_ENDPOINT_MODEL", None)
    write_env(env_path, values)
    return env_path


def copy_rootfs(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.iterdir()):
        target = destination / entry.name
        if entry.is_symlink():
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            target.symlink_to(entry.readlink())
            continue
        if entry.is_dir():
            shutil.copytree(entry, target, symlinks=True, dirs_exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)


def hook_summary(
    stage: str,
    hook_path: Path,
    completed: subprocess.CompletedProcess[str],
) -> dict[str, object]:
    return {
        "stage": stage,
        "path": str(hook_path),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[:512],
        "stderr": completed.stderr.strip()[:512],
        "status": "succeeded" if completed.returncode == 0 else "failed",
    }


def run_hook(
    *,
    stage: str,
    hook_path: Path | None,
    sysroot: Path,
    install_id: str,
    install_source: str,
    installer_version: str,
    install_mode: str,
    slot: str,
    boot_backend: str,
    vendor_id: str | None,
    hardware_profile_id: str | None,
    partition_strategy: dict[str, object],
) -> dict[str, object] | None:
    if hook_path is None:
        return None

    bash_binary = resolve_bash_binary()
    hook_path = hook_path.resolve()
    require(hook_path.exists(), f"missing {stage} hook: {hook_path}")
    require(bash_binary is not None, f"usable bash runtime unavailable for {stage} hook: {hook_path}")
    env = os.environ.copy()
    env.update(
        {
            "AIOS_INSTALLER_HOOK_STAGE": stage,
            "AIOS_INSTALLER_SYSROOT": bash_path(sysroot),
            "AIOS_INSTALLER_INSTALL_ID": install_id,
            "AIOS_INSTALLER_INSTALL_SOURCE": install_source,
            "AIOS_INSTALLER_INSTALLER_VERSION": installer_version,
            "AIOS_INSTALLER_INSTALL_MODE": install_mode,
            "AIOS_INSTALLER_INSTALL_SLOT": slot,
            "AIOS_INSTALLER_BOOT_BACKEND": boot_backend,
            "AIOS_INSTALLER_PARTITION_STRATEGY_JSON": json.dumps(partition_strategy),
        }
    )
    if vendor_id:
        env["AIOS_INSTALLER_VENDOR_ID"] = vendor_id
    if hardware_profile_id:
        env["AIOS_INSTALLER_HARDWARE_PROFILE_ID"] = hardware_profile_id

    completed = subprocess.run(
        [str(bash_binary), bash_path(hook_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    summary = hook_summary(stage, hook_path, completed)
    require(
        completed.returncode == 0,
        f"{stage} hook failed: {hook_path}: {completed.stderr.strip() or completed.stdout.strip()}",
    )
    return summary


def main() -> int:
    args = parse_args()
    bundle_dir = args.bundle_dir.resolve()
    sysroot = args.sysroot.resolve()
    rootfs_dir = bundle_dir / "rootfs"
    require(rootfs_dir.exists(), f"missing delivery rootfs: {rootfs_dir}")

    if args.clean and sysroot.exists():
        shutil.rmtree(sysroot)
    sysroot.mkdir(parents=True, exist_ok=True)
    copy_rootfs(rootfs_dir, sysroot)

    install_id = args.install_id or f"install-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    installer_version = args.installer_version or git_installer_version()
    generated_at = datetime.now(timezone.utc).isoformat()
    ai_config = build_ai_config(args)
    partition_strategy = {
        "esp_partlabel": args.esp_partlabel,
        "root_partlabel": args.root_partlabel,
        "var_partlabel": args.var_partlabel,
        "esp_partition_index": args.esp_partition_index,
        "root_partition_index": args.root_partition_index,
        "var_partition_index": args.var_partition_index,
    }

    pre_install_hook = run_hook(
        stage="pre-install",
        hook_path=args.pre_install_hook,
        sysroot=sysroot,
        install_id=install_id,
        install_source=args.install_source,
        installer_version=installer_version,
        install_mode=args.install_mode,
        slot=args.slot,
        boot_backend=args.boot_backend,
        vendor_id=args.vendor_id,
        hardware_profile_id=args.hardware_profile_id,
        partition_strategy=partition_strategy,
    )

    recovery_manifest = None
    recovery_manifest_source = args.recovery_image_dir.resolve() / "recovery-image-manifest.json"
    recovery_manifest_target = sysroot / "etc" / "aios" / "installer" / "recovery-image-manifest.json"
    if recovery_manifest_source.exists():
        recovery_manifest = json.loads(recovery_manifest_source.read_text(encoding=UTF8))
        recovery_manifest_target.parent.mkdir(parents=True, exist_ok=True)
        recovery_manifest_target.write_text(
            json.dumps(recovery_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding=UTF8,
        )

    install_manifest = {
        "generated_at": generated_at,
        "bundle_dir": str(bundle_dir),
        "rootfs_source": str(rootfs_dir),
        "sysroot": str(sysroot),
        "install_id": install_id,
        "install_source": args.install_source,
        "installer_version": installer_version,
        "install_mode": args.install_mode,
        "install_slot": args.slot,
        "boot_backend": args.boot_backend,
        "vendor_id": args.vendor_id,
        "hardware_profile_id": args.hardware_profile_id,
        "partition_strategy": partition_strategy,
        "ai_config": ai_config,
        "firmware_hooks": {
            "pre_install": pre_install_hook,
            "post_install": None,
        },
        "recovery_image_manifest": (
            str(recovery_manifest_target.relative_to(sysroot)) if recovery_manifest else None
        ),
        "recovery_image": recovery_manifest,
    }
    install_manifest_path = sysroot / "etc" / "aios" / "installer" / "install-manifest.json"
    install_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    install_manifest_path.write_text(
        json.dumps(install_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding=UTF8,
    )

    env_path = sysroot / "etc" / "aios" / "firstboot" / "aios-firstboot.env"
    env_values = load_env(env_path)
    env_values.update(
        {
            "AIOS_FIRSTBOOT_INSTALL_ID": install_id,
            "AIOS_FIRSTBOOT_INSTALL_SOURCE": args.install_source,
            "AIOS_FIRSTBOOT_INSTALLER_VERSION": installer_version,
            "AIOS_FIRSTBOOT_INSTALL_MODE": args.install_mode,
            "AIOS_FIRSTBOOT_INSTALL_SLOT": args.slot,
            "AIOS_FIRSTBOOT_BOOT_BACKEND": args.boot_backend,
            "AIOS_FIRSTBOOT_INSTALL_MANIFEST": "/etc/aios/installer/install-manifest.json",
            "AIOS_FIRSTBOOT_AI_ENABLED": env_flag(bool(ai_config["enabled"])),
            "AIOS_FIRSTBOOT_AI_MODE": str(ai_config["mode"]),
            "AIOS_FIRSTBOOT_AI_PRIVACY_PROFILE": str(ai_config["privacy_profile"]),
            "AIOS_FIRSTBOOT_AI_AUTO_PULL_DEFAULT_MODEL": env_flag(
                bool(ai_config["auto_pull_default_model"])
            ),
        }
    )
    if ai_config.get("auto_model_source"):
        env_values["AIOS_FIRSTBOOT_AI_AUTO_MODEL_SOURCE"] = str(ai_config["auto_model_source"])
    else:
        env_values.pop("AIOS_FIRSTBOOT_AI_AUTO_MODEL_SOURCE", None)
    if ai_config.get("auto_model_id"):
        env_values["AIOS_FIRSTBOOT_AI_AUTO_MODEL_ID"] = str(ai_config["auto_model_id"])
    else:
        env_values.pop("AIOS_FIRSTBOOT_AI_AUTO_MODEL_ID", None)
    if ai_config.get("endpoint_base_url"):
        env_values["AIOS_FIRSTBOOT_AI_ENDPOINT_BASE_URL"] = str(ai_config["endpoint_base_url"])
    else:
        env_values.pop("AIOS_FIRSTBOOT_AI_ENDPOINT_BASE_URL", None)
    if ai_config.get("endpoint_model"):
        env_values["AIOS_FIRSTBOOT_AI_ENDPOINT_MODEL"] = str(ai_config["endpoint_model"])
    else:
        env_values.pop("AIOS_FIRSTBOOT_AI_ENDPOINT_MODEL", None)
    if args.vendor_id:
        env_values["AIOS_FIRSTBOOT_VENDOR_ID"] = args.vendor_id
    if args.hardware_profile_id:
        env_values["AIOS_FIRSTBOOT_HARDWARE_PROFILE_ID"] = args.hardware_profile_id
    if recovery_manifest:
        env_values.update(
            {
                "AIOS_FIRSTBOOT_RECOVERY_IMAGE_PROFILE": str(
                    recovery_manifest.get("profile", "")
                ),
                "AIOS_FIRSTBOOT_RECOVERY_DEFAULT_TARGET": str(
                    recovery_manifest.get("default_target", "")
                ),
                "AIOS_FIRSTBOOT_RECOVERY_IMAGE_MANIFEST": "/etc/aios/installer/recovery-image-manifest.json",
            }
        )
    write_env(env_path, env_values)
    runtime_env_path = write_runtime_platform_env(
        sysroot,
        args.hardware_profile_id,
        ai_config,
        args.runtime_profile_path,
    )

    boot_state_dir = sysroot / "var" / "lib" / "aios" / "updated" / "boot"
    boot_state_dir.mkdir(parents=True, exist_ok=True)
    (boot_state_dir / "current-slot").write_text(f"{args.slot}\n", encoding=UTF8)
    (boot_state_dir / "last-good-slot").write_text(f"{args.slot}\n", encoding=UTF8)
    (boot_state_dir / "current-entry").write_text(f"aios-{args.slot}.conf\n", encoding=UTF8)
    next_slot = boot_state_dir / "next-slot"
    if next_slot.exists():
        next_slot.unlink()

    post_install_hook = run_hook(
        stage="post-install",
        hook_path=args.post_install_hook,
        sysroot=sysroot,
        install_id=install_id,
        install_source=args.install_source,
        installer_version=installer_version,
        install_mode=args.install_mode,
        slot=args.slot,
        boot_backend=args.boot_backend,
        vendor_id=args.vendor_id,
        hardware_profile_id=args.hardware_profile_id,
        partition_strategy=partition_strategy,
    )
    install_manifest["firmware_hooks"]["post_install"] = post_install_hook
    install_manifest_path.write_text(
        json.dumps(install_manifest, indent=2, ensure_ascii=False) + "\n"
    )

    summary = {
        "bundle_dir": str(bundle_dir),
        "sysroot": str(sysroot),
        "install_manifest": str(install_manifest_path),
        "env_path": str(env_path),
        "install_id": install_id,
        "install_source": args.install_source,
        "installer_version": installer_version,
        "install_slot": args.slot,
        "boot_backend": args.boot_backend,
        "vendor_id": args.vendor_id,
        "hardware_profile_id": args.hardware_profile_id,
        "ai_config": ai_config,
        "runtime_profile_path": args.runtime_profile_path,
        "partition_strategy": partition_strategy,
        "pre_install_hook": pre_install_hook,
        "post_install_hook": post_install_hook,
        "recovery_manifest": str(recovery_manifest_target) if recovery_manifest else None,
        "runtime_platform_env": str(runtime_env_path) if runtime_env_path else None,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
