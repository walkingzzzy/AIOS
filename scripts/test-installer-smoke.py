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


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
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

    temp_root = Path(tempfile.mkdtemp(prefix="aios-installer-smoke-"))
    sysroot = temp_root / "sysroot"
    fake_bin_dir = temp_root / "bin"
    fake_bin_dir.mkdir(parents=True, exist_ok=True)
    install_fake_machine_id_setup(fake_bin_dir)
    pre_hook = write_hook_script(temp_root / "pre-install-hook.sh", "pre-install.json")
    post_hook = write_hook_script(temp_root / "post-install-hook.sh", "post-install.json")
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
        report_path = sysroot / "var" / "lib" / "aios" / "firstboot" / "report.json"
        boot_state_dir = sysroot / "var" / "lib" / "aios" / "updated" / "boot"

        require(env_path.exists(), f"missing installed firstboot env: {env_path}")
        require(manifest_path.exists(), f"missing install manifest: {manifest_path}")
        require(runtime_env_path.exists(), f"missing installed runtimed platform env: {runtime_env_path}")
        require(firstboot_script.exists(), f"missing installed firstboot script: {firstboot_script}")
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
        require(pre_hook_marker.exists(), f"missing pre-install hook marker: {pre_hook_marker}")
        require(post_hook_marker.exists(), f"missing post-install hook marker: {post_hook_marker}")

        env = os.environ.copy()
        env.update(env_values)
        env.update(
            {
                "AIOS_FIRSTBOOT_ROOT": str(sysroot),
                "AIOS_FIRSTBOOT_MACHINE_ID_SETUP_BIN": str(
                    fake_bin_dir / "systemd-machine-id-setup"
                ),
                "PATH": f"{fake_bin_dir}:{env.get('PATH', '')}",
                "AIOS_FIRSTBOOT_RANDOM_SEED_SIZE_BYTES": "64",
            }
        )
        subprocess.run(["bash", str(firstboot_script)], cwd=ROOT, env=env, check=True)

        require(report_path.exists(), "firstboot report not generated after install")
        report = json.loads(report_path.read_text())
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
            "machine_id": (sysroot / "etc" / "machine-id").read_text().strip(),
            "install_id": report.get("install_id"),
            "boot_backend": report.get("boot_backend"),
            "random_seed_present": report.get("random_seed_present"),
            "vendor_id": report.get("vendor_id"),
            "hardware_profile_id": report.get("hardware_profile_id"),
            "recovery_manifest_present": report.get("recovery_image_manifest_present"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
