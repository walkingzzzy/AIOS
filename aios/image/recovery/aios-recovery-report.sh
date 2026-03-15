#!/usr/bin/env bash
set -euo pipefail

SURFACE_PATH="${AIOS_RECOVERY_SURFACE_PATH:-/var/lib/aios/updated/recovery-surface.json}"
DIAGNOSTICS_DIR="${AIOS_RECOVERY_DIAGNOSTICS_DIR:-/var/lib/aios/updated/diagnostics}"
BOOT_CONTROL_PATH="${AIOS_RECOVERY_BOOT_CONTROL_PATH:-/var/lib/aios/updated/boot-control.json}"

echo "AIOS recovery mode"
echo "recovery_surface: $SURFACE_PATH"
echo "diagnostics_dir: $DIAGNOSTICS_DIR"
echo "boot_control: $BOOT_CONTROL_PATH"

if [[ -f "$SURFACE_PATH" ]]; then
  echo "--- recovery surface ---"
  cat "$SURFACE_PATH"
fi

if [[ -f "$BOOT_CONTROL_PATH" ]]; then
  echo "--- boot control ---"
  cat "$BOOT_CONTROL_PATH"
fi
