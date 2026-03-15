#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXED_MACHINE_ID = "0123456789abcdef0123456789abcdef\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AIOS first-boot hygiene and idempotence")
    parser.add_argument("--bundle-dir", type=Path, required=True)
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


def main() -> int:
    args = parse_args()
    bundle_dir = args.bundle_dir.resolve()
    rootfs_dir = bundle_dir / "rootfs"
    firstboot_script = rootfs_dir / "usr" / "libexec" / "aios" / "aios-firstboot.sh"
    require(firstboot_script.exists(), f"missing firstboot script: {firstboot_script}")

    temp_root = Path(tempfile.mkdtemp(prefix="aios-firstboot-smoke-", dir="/tmp"))
    fake_bin_dir = temp_root / "bin"
    fake_bin_dir.mkdir(parents=True, exist_ok=True)
    install_fake_machine_id_setup(fake_bin_dir)

    try:
        shutil.copytree(rootfs_dir / "etc", temp_root / "etc", symlinks=True)
        shutil.copytree(rootfs_dir / "var", temp_root / "var", symlinks=True)

        machine_id_path = temp_root / "etc" / "machine-id"
        dbus_machine_id_path = temp_root / "var" / "lib" / "dbus" / "machine-id"
        random_seed_path = temp_root / "var" / "lib" / "systemd" / "random-seed"
        report_path = temp_root / "var" / "lib" / "aios" / "firstboot" / "report.json"
        stamp_path = temp_root / "var" / "lib" / "aios" / "firstboot" / "initialized"

        require(machine_id_path.exists(), "temp root missing /etc/machine-id")
        require(machine_id_path.read_text() == "", "expected empty /etc/machine-id before firstboot")
        require(dbus_machine_id_path.is_symlink(), "expected dbus machine-id symlink before firstboot")
        require(os.readlink(dbus_machine_id_path) == "/etc/machine-id", "unexpected dbus machine-id symlink target")
        require(not random_seed_path.exists(), "expected no random-seed before firstboot")

        env = os.environ.copy()
        env.update(
            {
                "AIOS_FIRSTBOOT_ROOT": str(temp_root),
                "AIOS_FIRSTBOOT_MACHINE_ID_SETUP_BIN": str(fake_bin_dir / "systemd-machine-id-setup"),
                "AIOS_FIRSTBOOT_PROFILE_ID": "qemu-x86_64-dev",
                "AIOS_FIRSTBOOT_CHANNEL": "dev",
                "AIOS_FIRSTBOOT_SUPPORT_URL": "https://example.invalid/aios/support",
                "AIOS_FIRSTBOOT_RANDOM_SEED_SIZE_BYTES": "64",
                "PATH": f"{fake_bin_dir}:{env.get('PATH', '')}",
            }
        )

        subprocess.run(["bash", str(firstboot_script)], check=True, env=env, cwd=ROOT)

        require(stamp_path.exists(), "firstboot did not create initialized stamp")
        require(report_path.exists(), "firstboot did not create report")
        require(machine_id_path.read_text() == FIXED_MACHINE_ID, "firstboot did not initialize machine-id")
        require(dbus_machine_id_path.is_symlink(), "dbus machine-id should remain a symlink")
        require(os.readlink(dbus_machine_id_path) == "/etc/machine-id", "dbus machine-id symlink target changed")
        require(random_seed_path.exists(), "firstboot did not materialize random-seed")
        random_seed_bytes = random_seed_path.read_bytes()
        require(len(random_seed_bytes) == 64, "firstboot random-seed size mismatch")

        first_report = json.loads(report_path.read_text())
        require(first_report.get("machine_id_state") == "generated", "report should record generated machine-id")
        require(first_report.get("machine_id_generated") is True, "report should record machine-id generation")
        require(first_report.get("random_seed_state") == "generated", "report should record generated random-seed")
        require(first_report.get("random_seed_generated") is True, "report should record random-seed generation")
        require(first_report.get("random_seed_present") is True, "report should record present random-seed")
        require(first_report.get("random_seed_size_bytes") == 64, "report random-seed size mismatch")
        require(first_report.get("dbus_machine_id_target") == "/etc/machine-id", "report dbus machine-id target mismatch")
        require(first_report.get("profile_id") == "qemu-x86_64-dev", "report profile mismatch")

        report_snapshot = report_path.read_text()
        report_mtime_ns = report_path.stat().st_mtime_ns
        random_seed_snapshot = random_seed_bytes
        random_seed_mtime_ns = random_seed_path.stat().st_mtime_ns
        subprocess.run(["bash", str(firstboot_script)], check=True, env=env, cwd=ROOT)
        require(report_path.read_text() == report_snapshot, "firstboot should be idempotent once initialized")
        require(report_path.stat().st_mtime_ns == report_mtime_ns, "idempotent firstboot should not rewrite report")
        require(machine_id_path.read_text() == FIXED_MACHINE_ID, "machine-id changed after second firstboot run")
        require(random_seed_path.read_bytes() == random_seed_snapshot, "random-seed changed after second firstboot run")
        require(random_seed_path.stat().st_mtime_ns == random_seed_mtime_ns, "idempotent firstboot should not rewrite random-seed")

        summary = {
            "bundle_dir": str(bundle_dir),
            "firstboot_script": str(firstboot_script),
            "temp_root": str(temp_root),
            "machine_id": machine_id_path.read_text().strip(),
            "report_path": str(report_path),
            "machine_id_state": first_report.get("machine_id_state"),
            "random_seed_present": first_report.get("random_seed_present"),
            "random_seed_size_bytes": first_report.get("random_seed_size_bytes"),
        }
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
