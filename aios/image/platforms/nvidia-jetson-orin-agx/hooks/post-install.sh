#!/usr/bin/env bash
set -euo pipefail

json_escape() {
  printf '%s' "$1" | sed -e 's#\\#\\\\#g' -e 's#"#\\"#g'
}

NVBOOTCTRL_BIN="${AIOS_NVIDIA_NVBOOTCTRL_BIN:-${AIOS_UPDATED_NVIDIA_NVBOOTCTRL_BIN:-nvbootctrl}}"
SYSROOT="${AIOS_INSTALLER_SYSROOT:-}"
TARGET="${SYSROOT}/etc/aios/installer/nvidia-firmware-hook-report.json"

[[ -n "$SYSROOT" ]] || {
  printf 'missing AIOS_INSTALLER_SYSROOT\n' >&2
  exit 64
}

if ! command -v "$NVBOOTCTRL_BIN" >/dev/null 2>&1 && [[ ! -x "$NVBOOTCTRL_BIN" ]]; then
  printf 'missing nvbootctrl binary: %s\n' "$NVBOOTCTRL_BIN" >&2
  exit 127
fi

current_slot="$("$NVBOOTCTRL_BIN" get-current-slot 2>/dev/null | tr -d ' \r\n' || true)"
slot_dump="$("$NVBOOTCTRL_BIN" dump-slots-info 2>/dev/null | tr '\n' ';' | sed 's/;*$//' || true)"

mkdir -p "$(dirname "$TARGET")"
cat >"$TARGET" <<EOF
{
  "stage": "$(json_escape "${AIOS_INSTALLER_HOOK_STAGE:-post-install}")",
  "vendor_id": "$(json_escape "${AIOS_INSTALLER_VENDOR_ID:-nvidia}")",
  "hardware_profile_id": "$(json_escape "${AIOS_INSTALLER_HARDWARE_PROFILE_ID:-nvidia-jetson-orin-agx}")",
  "install_id": "$(json_escape "${AIOS_INSTALLER_INSTALL_ID:-}")",
  "install_slot": "$(json_escape "${AIOS_INSTALLER_INSTALL_SLOT:-}")",
  "nvbootctrl_binary": "$(json_escape "$NVBOOTCTRL_BIN")",
  "current_slot": "$(json_escape "$current_slot")",
  "slots_info": "$(json_escape "$slot_dump")"
}
EOF
