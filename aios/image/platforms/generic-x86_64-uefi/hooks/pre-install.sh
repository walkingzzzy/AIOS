#!/usr/bin/env bash
set -euo pipefail

report_dir="${AIOS_INSTALLER_REPORT_DIR:-/run/aios-installer}/hook-reports"
mkdir -p "$report_dir"
cat >"$report_dir/pre-install.json" <<EOF
{
  "stage": "${AIOS_INSTALLER_HOOK_STAGE:-pre-install}",
  "vendor_id": "${AIOS_INSTALLER_VENDOR_ID:-}",
  "hardware_profile_id": "${AIOS_INSTALLER_HARDWARE_PROFILE_ID:-}",
  "install_id": "${AIOS_INSTALLER_INSTALL_ID:-}"
}
EOF
