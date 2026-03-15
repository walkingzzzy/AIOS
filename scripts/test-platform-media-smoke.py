#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed = value.strip()
        if len(parsed) >= 2 and parsed[0] == parsed[-1] == '"':
            parsed = parsed[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        values[key.strip()] = parsed
    return values


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="aios-platform-media-smoke-"))
    system_image = temp_root / "system.raw"
    installer_image = temp_root / "installer.raw"
    recovery_image = temp_root / "recovery.raw"
    system_image.write_bytes(b"system-image")
    installer_image.write_bytes(b"installer-image")
    recovery_image.write_bytes(b"recovery-image")

    def run_export(platform_profile: Path, output_dir: Path) -> dict:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "build-aios-platform-media.py"),
            "--platform-profile",
            str(platform_profile),
            "--output-dir",
            str(output_dir),
            "--system-image",
            str(system_image),
            "--installer-image",
            str(installer_image),
            "--recovery-image",
            str(recovery_image),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr)
            raise SystemExit(completed.returncode)
        return json.loads((output_dir / "platform-media-manifest.json").read_text())

    output_dir = temp_root / "out"
    manifest = run_export(
        ROOT / "aios" / "image" / "platforms" / "generic-x86_64-uefi" / "profile.yaml",
        output_dir,
    )
    require(manifest["platform_id"] == "generic-x86_64-uefi", "platform id mismatch")
    require(manifest["embed_system_image"] is True, "embed_system_image should default to true")
    require((output_dir / "installer-media" / "write-installer-media.sh").exists(), "missing installer flash script")
    require((output_dir / "recovery-media" / "write-recovery-media.sh").exists(), "missing recovery flash script")
    require((output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "etc" / "aios" / "updated" / "platform.env").exists(), "missing target overlay platform env")
    require((output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "etc" / "aios" / "runtime" / "platform.env").exists(), "missing target overlay runtime env")
    require((output_dir / "config" / "recovery-overlay" / "etc" / "aios" / "runtime" / "platform.env").exists(), "missing recovery overlay runtime env")
    installer_env_path = output_dir / "config" / "installer-overlay" / "etc" / "aios" / "installer" / "aios-installer.env"
    require(installer_env_path.exists(), "missing installer env")
    runtime_env_path = output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "etc" / "aios" / "runtime" / "platform.env"
    recovery_runtime_env_path = output_dir / "config" / "recovery-overlay" / "etc" / "aios" / "runtime" / "platform.env"
    target_runtime_profile_path = output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "etc" / "aios" / "runtime" / "default-runtime-profile.yaml"
    recovery_runtime_profile_path = output_dir / "config" / "recovery-overlay" / "etc" / "aios" / "runtime" / "default-runtime-profile.yaml"
    require(manifest["artifacts"]["installer_media"]["size_bytes"] == installer_image.stat().st_size, "installer size mismatch")
    require(manifest["artifacts"]["system_image"]["size_bytes"] == system_image.stat().st_size, "system size mismatch")
    require((output_dir / "bringup" / "README.md").exists(), "missing bringup README")
    require((output_dir / "bringup" / "scripts" / "pull-boot-evidence.sh").exists(), "missing bringup pull script")
    require((output_dir / "bringup" / "scripts" / "evaluate-boot-evidence.sh").exists(), "missing bringup evaluate wrapper")
    require((output_dir / "bringup" / "scripts" / "render-hardware-validation.sh").exists(), "missing bringup report render wrapper")
    require((output_dir / "bringup" / "scripts" / "collect-and-render-hardware-validation.sh").exists(), "missing bringup collect/render wrapper")
    require((output_dir / "bringup" / "scripts" / "render-aios-hardware-validation-report.py").exists(), "missing bringup report renderer")
    require((output_dir / "bringup" / "scripts" / "install-boot-evidence-assets.sh").exists(), "missing bringup install script")
    require((output_dir / "bringup" / "checklists" / "install-rollback-checklist.md").exists(), "missing bringup checklist")
    require((output_dir / "bringup" / "reports" / "hardware-validation-template.md").exists(), "missing hardware validation template")
    require((output_dir / "bringup" / "reports" / "evidence-index-template.json").exists(), "missing evidence index template")
    require((output_dir / "bringup" / "support" / "support-matrix.md").exists(), "missing bringup support matrix")
    require((output_dir / "bringup" / "support" / "known-limitations.md").exists(), "missing bringup known limitations")
    require((output_dir / "bringup" / "assets" / "aios-boot-evidence.service").exists(), "missing bringup evidence service asset")
    require((output_dir / "bringup" / "assets" / "aios-boot-evidence.sh").exists(), "missing bringup evidence script asset")
    tier1_profile = output_dir / "bringup" / "profiles" / "generic-x86_64-uefi-tier1.yaml"
    canonical_profile = output_dir / "bringup" / "profiles" / "generic-x86_64-uefi.yaml"
    nominated_framework_profile = output_dir / "bringup" / "profiles" / "framework-laptop-13-amd-7040.yaml"
    require(tier1_profile.exists(), "missing generated tier1 profile")
    require(canonical_profile.exists(), "missing bundled canonical hardware profile")
    require(nominated_framework_profile.exists(), "missing bundled nominated framework profile")
    tier1_text = tier1_profile.read_text()
    require("platform_media_id: generic-x86_64-uefi" in tier1_text, "tier1 profile missing platform_media_id")
    require("boot_evidence_dir: /var/lib/aios/hardware-evidence/boots" in tier1_text, "tier1 profile missing boot evidence dir")
    require("boot_evidence_expectations:" in tier1_text, "tier1 profile missing boot evidence expectations")
    require("vendor_id: generic" in tier1_text, "tier1 profile missing canonical vendor id")
    readme_text = (output_dir / "bringup" / "README.md").read_text()
    require("does not prove hardware success by itself" in readme_text, "bringup README missing hardware boundary note")
    require("write-installer-media.sh" in readme_text, "bringup README missing flash command guidance")
    require("install-rollback-checklist.md" in readme_text, "bringup README missing checklist guidance")
    require("support/support-matrix.md" in readme_text, "bringup README missing support matrix guidance")
    require("profiles/framework-laptop-13-amd-7040.yaml" in readme_text, "bringup README missing nominated framework profile")
    support_matrix_text = (output_dir / "bringup" / "support" / "support-matrix.md").read_text()
    require("Hardware profile ID: generic-x86_64-uefi" in support_matrix_text, "support matrix missing hardware profile id")
    require("Generated Tier 1 profile: profiles/generic-x86_64-uefi-tier1.yaml" in support_matrix_text, "support matrix missing tier1 profile path")
    require("Formal nominated machine profiles: profiles/framework-laptop-13-amd-7040.yaml" in support_matrix_text, "support matrix missing nominated framework profile")
    known_limitations_text = (output_dir / "bringup" / "support" / "known-limitations.md").read_text()
    require("repo-level reference bring-up target" in known_limitations_text, "known limitations missing reference target note")
    evaluate_wrapper_text = (output_dir / "bringup" / "scripts" / "evaluate-boot-evidence.sh").read_text()
    require("--profile" in evaluate_wrapper_text, "bringup evaluate wrapper missing tier1 profile wiring")
    render_wrapper_text = (output_dir / "bringup" / "scripts" / "render-hardware-validation.sh").read_text()
    require("--evaluator-json" in render_wrapper_text, "bringup render wrapper missing evaluator wiring")
    collect_wrapper_text = (output_dir / "bringup" / "scripts" / "collect-and-render-hardware-validation.sh").read_text()
    require("AIOS_BRINGUP_PULL_HOST" in collect_wrapper_text, "bringup collect/render wrapper missing pull host wiring")
    require("--report-md" in collect_wrapper_text, "bringup collect/render wrapper missing evaluator markdown wiring")
    require("render-hardware-validation.sh" in collect_wrapper_text, "bringup collect/render wrapper missing render chaining")
    require(manifest["bringup"]["boot_evidence_dir"] == "/var/lib/aios/hardware-evidence/boots", "manifest missing bringup evidence dir")
    require(manifest["bringup"]["hardware_profile_id"] == "generic-x86_64-uefi", "manifest missing hardware profile id")
    require(manifest["bringup"]["canonical_hardware_profile"].endswith("generic-x86_64-uefi.yaml"), "manifest missing canonical hardware profile asset")
    require(any(path.endswith("framework-laptop-13-amd-7040.yaml") for path in manifest["bringup"]["nominated_profiles"]), "manifest missing nominated framework profile asset")
    checklist_text = (output_dir / "bringup" / "checklists" / "install-rollback-checklist.md").read_text()
    require("Guided installer summary verified" in checklist_text, "bringup checklist missing guided installer checkpoint")
    require("support/support-matrix.md" in checklist_text, "bringup checklist missing support review checkpoint")
    report_template_text = (output_dir / "bringup" / "reports" / "hardware-validation-template.md").read_text()
    require("## Rollback Outcome" in report_template_text, "hardware validation template missing rollback section")
    installer_env = load_env(installer_env_path)
    require(installer_env.get("AIOS_INSTALLER_PLATFORM_ID") == "generic-x86_64-uefi", "installer env platform_id mismatch")
    require(
        installer_env.get("AIOS_INSTALLER_PLATFORM_PROFILE")
        == "/usr/share/aios/updated/platforms/generic-x86_64-uefi/profile.yaml",
        "installer env platform profile mismatch",
    )
    require(installer_env.get("AIOS_INSTALLER_GUIDED_MODE") == "auto", "installer env guided mode mismatch")
    require(installer_env.get("AIOS_INSTALLER_VENDOR_ID") == "generic", "installer env vendor_id mismatch")
    require(
        installer_env.get("AIOS_INSTALLER_HARDWARE_PROFILE_ID") == "generic-x86_64-uefi",
        "installer env hardware_profile_id mismatch",
    )
    runtime_env = load_env(runtime_env_path)
    require(
        runtime_env.get("AIOS_RUNTIMED_HARDWARE_PROFILE_ID") == "generic-x86_64-uefi",
        "target overlay runtime env hardware_profile_id mismatch",
    )
    require(
        runtime_env.get("AIOS_RUNTIMED_RUNTIME_PROFILE") == "/etc/aios/runtime/default-runtime-profile.yaml",
        "target overlay runtime env runtime profile mismatch",
    )
    recovery_runtime_env = load_env(recovery_runtime_env_path)
    require(
        recovery_runtime_env.get("AIOS_RUNTIMED_HARDWARE_PROFILE_ID") == "generic-x86_64-uefi",
        "recovery overlay runtime env hardware_profile_id mismatch",
    )
    require(
        recovery_runtime_env.get("AIOS_RUNTIMED_RUNTIME_PROFILE") == "/etc/aios/runtime/default-runtime-profile.yaml",
        "recovery overlay runtime env runtime profile mismatch",
    )
    require(target_runtime_profile_path.exists(), "missing target overlay runtime profile asset")
    require(recovery_runtime_profile_path.exists(), "missing recovery overlay runtime profile asset")
    require(
        installer_env.get("AIOS_INSTALLER_ROOT_PARTLABEL") == "AIOS-root",
        "installer env root partlabel mismatch",
    )
    require(
        installer_env.get("AIOS_INSTALLER_PRE_INSTALL_HOOK")
        == "/usr/share/aios/installer/hooks/pre-install.sh",
        "installer env pre-install hook mismatch",
    )
    require(
        installer_env.get("AIOS_INSTALLER_POST_INSTALL_HOOK")
        == "/usr/share/aios/installer/hooks/post-install.sh",
        "installer env post-install hook mismatch",
    )
    pre_hook_asset = output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "hooks" / "pre-install.sh"
    post_hook_asset = output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "hooks" / "post-install.sh"
    require(pre_hook_asset.exists(), f"missing copied pre-install hook asset: {pre_hook_asset}")
    require(post_hook_asset.exists(), f"missing copied post-install hook asset: {post_hook_asset}")
    jetson_output_dir = temp_root / "jetson-out"
    jetson_manifest = run_export(
        ROOT / "aios" / "image" / "platforms" / "nvidia-jetson-orin-agx" / "profile.yaml",
        jetson_output_dir,
    )
    require(jetson_manifest["platform_id"] == "nvidia-jetson-orin-agx", "jetson platform id mismatch")
    jetson_runtime_env_path = jetson_output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "etc" / "aios" / "runtime" / "platform.env"
    jetson_recovery_runtime_env_path = jetson_output_dir / "config" / "recovery-overlay" / "etc" / "aios" / "runtime" / "platform.env"
    jetson_runtime_profile_path = jetson_output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "usr" / "share" / "aios" / "runtime" / "platforms" / "nvidia-jetson-orin-agx" / "default-runtime-profile.yaml"
    jetson_recovery_runtime_profile_path = jetson_output_dir / "config" / "recovery-overlay" / "usr" / "share" / "aios" / "runtime" / "platforms" / "nvidia-jetson-orin-agx" / "default-runtime-profile.yaml"
    jetson_runtime_env = load_env(jetson_runtime_env_path)
    require(
        jetson_runtime_env.get("AIOS_RUNTIMED_HARDWARE_PROFILE_ID") == "nvidia-jetson-orin-agx",
        "jetson target runtime env hardware_profile_id mismatch",
    )
    require(
        jetson_runtime_env.get("AIOS_RUNTIMED_RUNTIME_PROFILE")
        == "/usr/share/aios/runtime/platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml",
        "jetson target runtime env runtime profile mismatch",
    )
    jetson_recovery_runtime_env = load_env(jetson_recovery_runtime_env_path)
    require(
        jetson_recovery_runtime_env.get("AIOS_RUNTIMED_RUNTIME_PROFILE")
        == "/usr/share/aios/runtime/platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml",
        "jetson recovery runtime env runtime profile mismatch",
    )
    require(jetson_runtime_profile_path.exists(), "missing jetson target runtime profile asset")
    require(jetson_recovery_runtime_profile_path.exists(), "missing jetson recovery runtime profile asset")
    jetson_worker_bridge_path = jetson_output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "usr" / "share" / "aios" / "runtime" / "platforms" / "nvidia-jetson-orin-agx" / "bin" / "launch-managed-worker.sh"
    jetson_reference_worker_path = jetson_output_dir / "config" / "installer-overlay" / "usr" / "share" / "aios" / "installer" / "target-overlay" / "usr" / "share" / "aios" / "runtime" / "platforms" / "nvidia-jetson-orin-agx" / "bin" / "reference_accel_worker.py"
    require(jetson_worker_bridge_path.exists(), "missing jetson worker bridge asset")
    require(jetson_reference_worker_path.exists(), "missing jetson reference worker asset")
    jetson_runtime_profile_text = jetson_runtime_profile_path.read_text()
    require(
        "default_backend: local-gpu" in jetson_runtime_profile_text,
        "jetson runtime profile should prefer local-gpu",
    )
    require(
        "launch-managed-worker.sh" in jetson_runtime_profile_text,
        "jetson runtime profile missing worker bridge command",
    )
    jetson_tier1_text = (jetson_output_dir / "bringup" / "profiles" / "nvidia-jetson-orin-agx-tier1.yaml").read_text()
    require("model: jetson-agx-orin-devkit" in jetson_tier1_text, "jetson tier1 profile missing canonical model")
    require("bringup_status: bringup-kit-only" in jetson_tier1_text, "jetson tier1 profile missing bringup status")
    jetson_canonical_profile = jetson_output_dir / "bringup" / "profiles" / "nvidia-jetson-orin-agx.yaml"
    require(jetson_canonical_profile.exists(), "missing bundled jetson canonical profile")
    jetson_support_matrix_text = (jetson_output_dir / "bringup" / "support" / "support-matrix.md").read_text()
    require("Hardware profile ID: nvidia-jetson-orin-agx" in jetson_support_matrix_text, "jetson support matrix missing hardware profile id")
    require("Formal nominated machine profiles: profiles/nvidia-jetson-orin-agx.yaml" in jetson_support_matrix_text, "jetson support matrix missing nominated profile")
    require("Post-install firmware hook: /usr/share/aios/installer/hooks/post-install.sh" in jetson_support_matrix_text, "jetson support matrix missing firmware hook")
    jetson_known_limitations_text = (jetson_output_dir / "bringup" / "support" / "known-limitations.md").read_text()
    require("Real hardware install and rollback evidence is still pending." in jetson_known_limitations_text, "jetson known limitations missing hardware evidence note")
    require(any(path.endswith("nvidia-jetson-orin-agx.yaml") for path in jetson_manifest["bringup"]["nominated_profiles"]), "jetson manifest missing nominated profile asset")

    print(
        json.dumps(
            {
                "generic_output_dir": str(output_dir),
                "generic_manifest": manifest,
                "jetson_output_dir": str(jetson_output_dir),
                "jetson_manifest": jetson_manifest,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
