#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXED_MACHINE_ID = "0123456789abcdef0123456789abcdef\n"
HOST_LINK_PLACEHOLDER_PREFIX = "aios-host-link-target:"
DEFAULT_WORK_ROOT = ROOT / "out" / "validation" / "firstboot-hygiene-smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AIOS first-boot hygiene and idempotence")
    parser.add_argument("--bundle-dir", type=Path, required=True)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def read_symlink_target(path: Path) -> str | None:
    if path.is_symlink():
        return os.readlink(path)
    if path.is_file():
        payload = path.read_text(encoding="utf-8").strip()
        if payload.startswith(HOST_LINK_PLACEHOLDER_PREFIX):
            return payload[len(HOST_LINK_PLACEHOLDER_PREFIX):]
    return None


def resolve_work_root() -> Path:
    if DEFAULT_WORK_ROOT.exists():
        shutil.rmtree(DEFAULT_WORK_ROOT, ignore_errors=True)
    DEFAULT_WORK_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_WORK_ROOT


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


def main() -> int:
    args = parse_args()
    bundle_dir = args.bundle_dir.resolve()
    rootfs_dir = bundle_dir / "rootfs"
    firstboot_script = rootfs_dir / "usr" / "libexec" / "aios" / "aios-firstboot.sh"
    require(firstboot_script.exists(), f"missing firstboot script: {firstboot_script}")

    if os.name == "nt":
        print("firstboot hygiene smoke skipped: firstboot bootstrap execution requires Linux-host symlink and entropy semantics")
        return 0

    bash_binary = resolve_bash_binary()
    if bash_binary is None:
        print("firstboot hygiene smoke skipped: usable bash runtime unavailable on this platform")
        return 0

    temp_root = resolve_work_root()
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
        require(read_symlink_target(dbus_machine_id_path) == "/etc/machine-id", "unexpected dbus machine-id symlink target before firstboot")
        require(not random_seed_path.exists(), "expected no random-seed before firstboot")

        env = os.environ.copy()
        env.update(
            {
                "AIOS_FIRSTBOOT_ROOT": bash_path(temp_root),
                "AIOS_FIRSTBOOT_MACHINE_ID_SETUP_BIN": bash_path(fake_bin_dir / "systemd-machine-id-setup"),
                "AIOS_FIRSTBOOT_PROFILE_ID": "qemu-x86_64-dev",
                "AIOS_FIRSTBOOT_CHANNEL": "dev",
                "AIOS_FIRSTBOOT_SUPPORT_URL": "https://example.invalid/aios/support",
                "AIOS_FIRSTBOOT_RANDOM_SEED_SIZE_BYTES": "64",
                "PATH": f"{bash_path(fake_bin_dir)}{os.pathsep}{env.get('PATH', '')}",
            }
        )

        subprocess.run([str(bash_binary), bash_path(firstboot_script)], check=True, env=env, cwd=ROOT)

        require(stamp_path.exists(), "firstboot did not create initialized stamp")
        require(report_path.exists(), "firstboot did not create report")
        require(machine_id_path.read_text() == FIXED_MACHINE_ID, "firstboot did not initialize machine-id")
        require(read_symlink_target(dbus_machine_id_path) == "/etc/machine-id", "dbus machine-id symlink target changed")
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
