#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXED_MACHINE_ID = "89abcdef0123456789abcdef01234567\n"
UTF8 = "utf-8"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate AIOS installer integration and firstboot install metadata"
    )
    parser.add_argument("--bundle-dir", type=Path, default=ROOT / "out" / "aios-system-delivery")
    parser.add_argument(
        "--recovery-image-dir",
        type=Path,
        default=ROOT / "aios" / "image" / "recovery.output",
    )
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


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


def install_fake_machine_id_setup(bin_dir: Path) -> Path:
    script_path = bin_dir / "systemd-machine-id-setup"
    script_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "root=\"\"\n"
        "while [[ $# -gt 0 ]]; do\n"
        "  case \"$1\" in\n"
        "    --root)\n"
        "      root=\"$2\"\n"
        "      shift 2\n"
        "      ;;\n"
        "    --root=*)\n"
        "      root=\"${1#--root=}\"\n"
        "      shift\n"
        "      ;;\n"
        "    *)\n"
        "      shift\n"
        "      ;;\n"
        "  esac\n"
        "done\n"
        "if [[ -z \"$root\" ]]; then\n"
        "  root=/\n"
        "fi\n"
        f"printf '{FIXED_MACHINE_ID}' > \"$root/etc/machine-id\"\n"
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script_path


def install_fake_ollama(bin_dir: Path) -> Path:
    script_path = bin_dir / "ollama"
    script_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$AIOS_TEST_OLLAMA_LOG\"\n"
        "if [[ \"${1:-}\" != \"pull\" ]]; then\n"
        "  exit 2\n"
        "fi\n"
        "if [[ \"${2:-}\" != \"$AIOS_EXPECTED_MODEL_ID\" ]]; then\n"
        "  exit 3\n"
        "fi\n"
        "exit 0\n"
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script_path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding=UTF8).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_hook_script(path: Path, marker_name: str) -> Path:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "sysroot=\"${AIOS_INSTALLER_SYSROOT:?}\"\n"
        "marker_dir=\"$sysroot/var/lib/aios/installer-hooks\"\n"
        "mkdir -p \"$marker_dir\"\n"
        f"cat > \"$marker_dir/{marker_name}\" <<EOF\n"
        "{\n"
        "  \"stage\": \"${AIOS_INSTALLER_HOOK_STAGE:-}\",\n"
        "  \"vendor_id\": \"${AIOS_INSTALLER_VENDOR_ID:-}\",\n"
        "  \"hardware_profile_id\": \"${AIOS_INSTALLER_HARDWARE_PROFILE_ID:-}\",\n"
        "  \"install_id\": \"${AIOS_INSTALLER_INSTALL_ID:-}\"\n"
        "}\n"
        "EOF\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def main() -> int:
    args = parse_args()
    bundle_dir = args.bundle_dir.resolve()
    require((bundle_dir / "rootfs").exists(), f"missing bundle rootfs: {bundle_dir / 'rootfs'}")
    bash_binary = resolve_bash_binary()
    if bash_binary is None:
        print("installer smoke skipped: usable bash runtime unavailable on this platform")
        return 0

    temp_root = Path(tempfile.mkdtemp(prefix="aios-installer-smoke-"))
    sysroot = temp_root / "sysroot"
    fake_bin_dir = temp_root / "bin"
    fake_bin_dir.mkdir(parents=True, exist_ok=True)
    install_fake_machine_id_setup(fake_bin_dir)
    install_fake_ollama(fake_bin_dir)
    pre_hook = write_hook_script(temp_root / "pre-install-hook.sh", "pre-install.json")
    post_hook = write_hook_script(temp_root / "post-install-hook.sh", "post-install.json")
    ollama_log = temp_root / "ollama.log"
    partition_strategy = {
        "esp_partlabel": "AIOS-ESP-VENDOR",
        "root_partlabel": "AIOS-root-vendor",
        "var_partlabel": "AIOS-var-vendor",
        "esp_partition_index": 11,
        "root_partition_index": 12,
        "var_partition_index": 13,
    }

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "install-aios-system.py"),
                "--bundle-dir",
                str(bundle_dir),
                "--sysroot",
                str(sysroot),
                "--install-id",
                "smoke-install-001",
                "--install-source",
                "installer-smoke",
                "--installer-version",
                "installer-smoke-v1",
                "--slot",
                "b",
                "--boot-backend",
                "firmware",
                "--ai-enabled",
                "--ai-mode",
                "hybrid",
                "--ai-privacy-profile",
                "strict-local",
                "--ai-auto-pull-default-model",
                "--ai-auto-model-source",
                "ollama-library",
                "--ai-auto-model-id",
                "qwen2.5:7b-instruct",
                "--ai-endpoint-base-url",
                "http://127.0.0.1:11434/v1",
                "--ai-endpoint-model",
                "qwen2.5:7b-instruct",
                "--vendor-id",
                "acme",
                "--hardware-profile-id",
                "acme-x1",
                "--runtime-profile-path",
                "/usr/share/aios/runtime/platforms/acme-x1/default-runtime-profile.yaml",
                "--esp-partlabel",
                partition_strategy["esp_partlabel"],
                "--root-partlabel",
                partition_strategy["root_partlabel"],
                "--var-partlabel",
                partition_strategy["var_partlabel"],
                "--esp-partition-index",
                str(partition_strategy["esp_partition_index"]),
                "--root-partition-index",
                str(partition_strategy["root_partition_index"]),
                "--var-partition-index",
                str(partition_strategy["var_partition_index"]),
                "--pre-install-hook",
                str(pre_hook),
                "--post-install-hook",
                str(post_hook),
                "--recovery-image-dir",
                str(args.recovery_image_dir.resolve()),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        install_summary = json.loads(completed.stdout)

        env_path = sysroot / "etc" / "aios" / "firstboot" / "aios-firstboot.env"
        manifest_path = sysroot / "etc" / "aios" / "installer" / "install-manifest.json"
        recovery_manifest_path = (
            sysroot / "etc" / "aios" / "installer" / "recovery-image-manifest.json"
        )
        runtime_env_path = sysroot / "etc" / "aios" / "runtime" / "platform.env"
        pre_hook_marker = sysroot / "var" / "lib" / "aios" / "installer-hooks" / "pre-install.json"
        post_hook_marker = sysroot / "var" / "lib" / "aios" / "installer-hooks" / "post-install.json"
        firstboot_script = sysroot / "usr" / "libexec" / "aios" / "aios-firstboot.sh"
        onboarding_script = sysroot / "usr" / "libexec" / "aios" / "aios-ai-onboarding.sh"
        recommended_catalog = (
            sysroot / "usr" / "libexec" / "aios" / "runtime" / "recommended-model-catalog.yaml"
        )
        report_path = sysroot / "var" / "lib" / "aios" / "firstboot" / "report.json"
        onboarding_report_path = (
            sysroot / "var" / "lib" / "aios" / "onboarding" / "ai-onboarding-report.json"
        )
        ai_readiness_path = sysroot / "var" / "lib" / "aios" / "runtime" / "ai-readiness.json"
        boot_state_dir = sysroot / "var" / "lib" / "aios" / "updated" / "boot"

        require(env_path.exists(), f"missing installed firstboot env: {env_path}")
        require(manifest_path.exists(), f"missing install manifest: {manifest_path}")
        require(runtime_env_path.exists(), f"missing installed runtimed platform env: {runtime_env_path}")
        require(firstboot_script.exists(), f"missing installed firstboot script: {firstboot_script}")
        require(onboarding_script.exists(), f"missing installed onboarding script: {onboarding_script}")
        require(recommended_catalog.exists(), f"missing installed recommended catalog: {recommended_catalog}")
        require(
            (boot_state_dir / "current-slot").read_text().strip() == "b",
            "installer should seed current-slot=b",
        )
        require(
            (boot_state_dir / "last-good-slot").read_text().strip() == "b",
            "installer should seed last-good-slot=b",
        )
        require(
            (boot_state_dir / "current-entry").read_text().strip() == "aios-b.conf",
            "installer should seed current-entry=aios-b.conf",
        )

        env_values = load_env(env_path)
        require(
            env_values.get("AIOS_FIRSTBOOT_INSTALL_ID") == "smoke-install-001",
            "install id missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_INSTALL_SOURCE") == "installer-smoke",
            "install source missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_INSTALLER_VERSION") == "installer-smoke-v1",
            "installer version missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_INSTALL_SLOT") == "b",
            "install slot missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_BOOT_BACKEND") == "firmware",
            "boot backend missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_VENDOR_ID") == "acme",
            "vendor id missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_HARDWARE_PROFILE_ID") == "acme-x1",
            "hardware profile id missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_INSTALL_MANIFEST")
            == "/etc/aios/installer/install-manifest.json",
            "install manifest path missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_ENABLED") == "1",
            "AI enabled flag missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_MODE") == "hybrid",
            "AI mode missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_PRIVACY_PROFILE") == "strict-local",
            "AI privacy profile missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_AUTO_PULL_DEFAULT_MODEL") == "1",
            "AI auto-pull flag missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_AUTO_MODEL_SOURCE") == "ollama-library",
            "AI auto model source missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_AUTO_MODEL_ID") == "qwen2.5:7b-instruct",
            "AI auto model id missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_ENDPOINT_BASE_URL") == "http://127.0.0.1:11434/v1",
            "AI endpoint base url missing from firstboot env",
        )
        require(
            env_values.get("AIOS_FIRSTBOOT_AI_ENDPOINT_MODEL") == "qwen2.5:7b-instruct",
            "AI endpoint model missing from firstboot env",
        )
        if args.recovery_image_dir.exists() and (
            args.recovery_image_dir / "recovery-image-manifest.json"
        ).exists():
            require(recovery_manifest_path.exists(), "expected copied recovery manifest")
            require(
                env_values.get("AIOS_FIRSTBOOT_RECOVERY_IMAGE_MANIFEST")
                == "/etc/aios/installer/recovery-image-manifest.json",
                "recovery manifest path missing from firstboot env",
            )
        runtime_env_values = load_env(runtime_env_path)
        require(
            runtime_env_values.get("AIOS_RUNTIMED_HARDWARE_PROFILE_ID") == "acme-x1",
            "runtimed platform env missing hardware profile id",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_RUNTIME_PROFILE")
            == "/usr/share/aios/runtime/platforms/acme-x1/default-runtime-profile.yaml",
            "runtimed platform env missing runtime profile path",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_PRODUCT_MODE") == "1",
            "runtimed platform env missing product mode flag",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_AI_ENABLED") == "1",
            "runtimed platform env missing AI enabled flag",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_AI_MODE") == "hybrid",
            "runtimed platform env missing AI mode",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_AI_PRIVACY_PROFILE") == "strict-local",
            "runtimed platform env missing AI privacy profile",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_LOCAL_CPU_COMMAND")
            == "/usr/libexec/aios/runtime/workers/launch_local_cpu_worker.sh",
            "runtimed platform env missing local cpu worker launcher",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL")
            == "http://127.0.0.1:11434/v1",
            "runtimed platform env missing AI endpoint base url",
        )
        require(
            runtime_env_values.get("AIOS_RUNTIMED_AI_ENDPOINT_MODEL")
            == "qwen2.5:7b-instruct",
            "runtimed platform env missing AI endpoint model",
        )

        manifest = json.loads(manifest_path.read_text())
        require(manifest.get("vendor_id") == "acme", "install manifest vendor_id mismatch")
        require(
            manifest.get("hardware_profile_id") == "acme-x1",
            "install manifest hardware_profile_id mismatch",
        )
        require(
            manifest.get("partition_strategy") == partition_strategy,
            "install manifest partition strategy mismatch",
        )
        require(
            manifest.get("firmware_hooks", {})
            .get("pre_install", {})
            .get("status")
            == "succeeded",
            "install manifest pre-install hook status mismatch",
        )
        require(
            manifest.get("firmware_hooks", {})
            .get("post_install", {})
            .get("status")
            == "succeeded",
            "install manifest post-install hook status mismatch",
        )
        require(
            manifest.get("ai_config", {}).get("enabled") is True,
            "install manifest ai_config.enabled mismatch",
        )
        require(
            manifest.get("ai_config", {}).get("mode") == "hybrid",
            "install manifest ai_config.mode mismatch",
        )
        require(
            manifest.get("ai_config", {}).get("privacy_profile") == "strict-local",
            "install manifest ai_config.privacy_profile mismatch",
        )
        require(pre_hook_marker.exists(), f"missing pre-install hook marker: {pre_hook_marker}")
        require(post_hook_marker.exists(), f"missing post-install hook marker: {post_hook_marker}")

        if os.name == "nt":
            summary = {
                "install_summary": install_summary,
                "firstboot_execution": "skipped-windows-host",
                "manifest_path": str(manifest_path),
                "env_path": str(env_path),
                "runtime_env_path": str(runtime_env_path),
                "pre_hook_marker": str(pre_hook_marker),
                "post_hook_marker": str(post_hook_marker),
                "vendor_id": manifest.get("vendor_id"),
                "hardware_profile_id": manifest.get("hardware_profile_id"),
            }
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0

        env = os.environ.copy()
        env.update(env_values)
        env.update(
            {
                "AIOS_FIRSTBOOT_ROOT": bash_path(sysroot),
                "AIOS_FIRSTBOOT_MACHINE_ID_SETUP_BIN": bash_path(
                    fake_bin_dir / "systemd-machine-id-setup"
                ),
                "AIOS_FIRSTBOOT_RANDOM_SEED_SIZE_BYTES": "64",
                "AIOS_EXPECTED_MODEL_ID": "qwen2.5:7b-instruct",
                "AIOS_TEST_OLLAMA_LOG": bash_path(ollama_log),
                "PATH": f"{bash_path(fake_bin_dir)}{os.pathsep}{env.get('PATH', '')}",
            }
        )
        subprocess.run([str(bash_binary), bash_path(firstboot_script)], cwd=ROOT, env=env, check=True)
        subprocess.run([str(bash_binary), bash_path(onboarding_script)], cwd=ROOT, env=env, check=True)

        require(report_path.exists(), "firstboot report not generated after install")
        require(onboarding_report_path.exists(), "AI onboarding report not generated after install")
        require(ai_readiness_path.exists(), "AI readiness state not generated after install")
        report = json.loads(report_path.read_text(encoding=UTF8))
        onboarding_report = json.loads(onboarding_report_path.read_text(encoding=UTF8))
        ai_readiness = json.loads(ai_readiness_path.read_text(encoding=UTF8))
        require(
            report.get("machine_id_generated") is True,
            "firstboot should generate machine-id in installed sysroot",
        )
        require(
            report.get("install_metadata_present") is True,
            "firstboot report should mark install metadata present",
        )
        require(
            report.get("random_seed_present") is True,
            "firstboot report should mark random-seed present",
        )
        require(
            report.get("random_seed_size_bytes") == 64,
            "firstboot report random-seed size mismatch",
        )
        require(
            report.get("install_id") == "smoke-install-001",
            "firstboot report install_id mismatch",
        )
        require(
            report.get("install_source") == "installer-smoke",
            "firstboot report install_source mismatch",
        )
        require(
            report.get("installer_version") == "installer-smoke-v1",
            "firstboot report installer version mismatch",
        )
        require(
            report.get("install_slot") == "b",
            "firstboot report install slot mismatch",
        )
        require(
            report.get("boot_backend") == "firmware",
            "firstboot report boot backend mismatch",
        )
        require(report.get("vendor_id") == "acme", "firstboot report vendor_id mismatch")
        require(
            report.get("hardware_profile_id") == "acme-x1",
            "firstboot report hardware_profile_id mismatch",
        )
        require(
            report.get("install_manifest_present") is True,
            "firstboot report should detect install manifest",
        )
        require(
            onboarding_report.get("ai_enabled") is True,
            "AI onboarding report should record ai_enabled=true",
        )
        require(
            onboarding_report.get("auto_pull_attempted") is True,
            "AI onboarding report should attempt auto-pull with fake ollama",
        )
        require(
            onboarding_report.get("auto_pull_status") == "pulled",
            "AI onboarding auto-pull status mismatch",
        )
        require(
            onboarding_report.get("auto_pull_endpoint_adopted") is False,
            "AI onboarding should keep installer-provided endpoint unchanged",
        )
        require(
            onboarding_report.get("auto_pull_command") == "ollama pull qwen2.5:7b-instruct",
            "AI onboarding auto-pull command mismatch",
        )
        require(
            onboarding_report.get("readiness_state") == "hybrid-remote-only",
            "AI onboarding readiness state mismatch",
        )
        require(
            onboarding_report.get("endpoint_configured") is True,
            "AI onboarding report should detect configured endpoint",
        )
        require(
            ai_readiness.get("state") == "hybrid-remote-only",
            "AI readiness state mismatch",
        )
        require(
            ai_readiness.get("next_action") == "none",
            "AI readiness next_action mismatch",
        )
        require(
            ollama_log.read_text(encoding=UTF8).strip() == "pull qwen2.5:7b-instruct",
            "installer smoke fake ollama invocation mismatch",
        )
        require(
            (sysroot / "etc" / "machine-id").read_text() == FIXED_MACHINE_ID,
            "installed machine-id mismatch",
        )
        require(
            (sysroot / "var" / "lib" / "systemd" / "random-seed").exists(),
            "installed random-seed missing",
        )
        if recovery_manifest_path.exists():
            recovery_manifest = json.loads(recovery_manifest_path.read_text())
            require(
                report.get("recovery_image_profile")
                == recovery_manifest.get("profile", ""),
                "firstboot recovery profile mismatch",
            )
            require(
                report.get("recovery_default_target")
                == recovery_manifest.get("default_target", ""),
                "firstboot recovery target mismatch",
            )
            require(
                report.get("recovery_image_manifest_present") is True,
                "firstboot report should detect recovery manifest",
            )

        summary = {
            "install_summary": install_summary,
            "report_path": str(report_path),
            "machine_id": (sysroot / "etc" / "machine-id").read_text(encoding=UTF8).strip(),
            "install_id": report.get("install_id"),
            "boot_backend": report.get("boot_backend"),
            "random_seed_present": report.get("random_seed_present"),
            "vendor_id": report.get("vendor_id"),
            "hardware_profile_id": report.get("hardware_profile_id"),
            "recovery_manifest_present": report.get("recovery_image_manifest_present"),
            "ai_readiness_state": ai_readiness.get("state"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
