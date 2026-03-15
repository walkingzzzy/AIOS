#!/usr/bin/env bash
set -euo pipefail

sysroot="${AIOS_INSTALLER_SYSROOT:-}"
[[ -n "$sysroot" ]] || exit 64
target="$sysroot/etc/aios/installer/vendor-firmware-hook-report.json"
mkdir -p "$(dirname "$target")"
cat >"$target" <<EOF
{
  "stage": "${AIOS_INSTALLER_HOOK_STAGE:-post-install}",
  "vendor_id": "${AIOS_INSTALLER_VENDOR_ID:-}",
  "hardware_profile_id": "${AIOS_INSTALLER_HARDWARE_PROFILE_ID:-}",
  "install_id": "${AIOS_INSTALLER_INSTALL_ID:-}"
}
EOF
