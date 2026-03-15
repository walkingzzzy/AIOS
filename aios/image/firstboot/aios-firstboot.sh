#!/usr/bin/env bash
set -euo pipefail

ROOT_PREFIX="${AIOS_FIRSTBOOT_ROOT:-}"

root_path() {
  local path="$1"
  if [[ -n "$ROOT_PREFIX" ]]; then
    printf '%s%s' "$ROOT_PREFIX" "$path"
  else
    printf '%s' "$path"
  fi
}

resolve_rooted_path() {
  local path="$1"
  if [[ -z "$path" ]]; then
    printf ''
  elif [[ "$path" == /* ]]; then
    root_path "$path"
  else
    printf '%s' "$path"
  fi
}

json_escape() {
  printf '%s' "$1" | sed -e 's#\\#\\\\#g' -e 's#"#\\"#g'
}

write_random_seed() {
  local temp_path="${RANDOM_SEED_PATH}.tmp"
  rm -f "$temp_path"

  if command -v openssl >/dev/null 2>&1; then
    openssl rand -out "$temp_path" "$RANDOM_SEED_SIZE_BYTES" >/dev/null 2>&1 || rm -f "$temp_path"
  fi

  if [[ ! -s "$temp_path" && -r /dev/urandom ]]; then
    dd if=/dev/urandom of="$temp_path" bs=1 count="$RANDOM_SEED_SIZE_BYTES" 2>/dev/null || rm -f "$temp_path"
  fi

  if [[ -s "$temp_path" ]]; then
    chmod 600 "$temp_path"
    mv "$temp_path" "$RANDOM_SEED_PATH"
    return 0
  fi

  rm -f "$temp_path"
  return 1
}

MACHINE_ID_SETUP_BIN="${AIOS_FIRSTBOOT_MACHINE_ID_SETUP_BIN:-systemd-machine-id-setup}"
RANDOM_SEED_SIZE_BYTES="${AIOS_FIRSTBOOT_RANDOM_SEED_SIZE_BYTES:-512}"
PROFILE_ID="${AIOS_FIRSTBOOT_PROFILE_ID:-unknown}"
CHANNEL="${AIOS_FIRSTBOOT_CHANNEL:-dev}"
SUPPORT_URL="${AIOS_FIRSTBOOT_SUPPORT_URL:-}"
INSTALL_ID="${AIOS_FIRSTBOOT_INSTALL_ID:-}"
INSTALL_SOURCE="${AIOS_FIRSTBOOT_INSTALL_SOURCE:-}"
INSTALLER_VERSION="${AIOS_FIRSTBOOT_INSTALLER_VERSION:-}"
INSTALL_MODE="${AIOS_FIRSTBOOT_INSTALL_MODE:-}"
INSTALL_SLOT="${AIOS_FIRSTBOOT_INSTALL_SLOT:-}"
BOOT_BACKEND="${AIOS_FIRSTBOOT_BOOT_BACKEND:-}"
VENDOR_ID="${AIOS_FIRSTBOOT_VENDOR_ID:-}"
HARDWARE_PROFILE_ID="${AIOS_FIRSTBOOT_HARDWARE_PROFILE_ID:-}"
INSTALL_MANIFEST_PATH="${AIOS_FIRSTBOOT_INSTALL_MANIFEST:-}"
RECOVERY_IMAGE_PROFILE="${AIOS_FIRSTBOOT_RECOVERY_IMAGE_PROFILE:-}"
RECOVERY_DEFAULT_TARGET="${AIOS_FIRSTBOOT_RECOVERY_DEFAULT_TARGET:-}"
RECOVERY_IMAGE_MANIFEST_PATH="${AIOS_FIRSTBOOT_RECOVERY_IMAGE_MANIFEST:-}"

STAMP_DIR="$(root_path /var/lib/aios/firstboot)"
STAMP_FILE="$STAMP_DIR/initialized"
REPORT_FILE="$STAMP_DIR/report.json"
MACHINE_ID_PATH="$(root_path /etc/machine-id)"
DBUS_MACHINE_ID_PATH="$(root_path /var/lib/dbus/machine-id)"
RANDOM_SEED_PATH="$(root_path /var/lib/systemd/random-seed)"
INSTALL_MANIFEST_RESOLVED_PATH="$(resolve_rooted_path "$INSTALL_MANIFEST_PATH")"
RECOVERY_IMAGE_MANIFEST_RESOLVED_PATH="$(resolve_rooted_path "$RECOVERY_IMAGE_MANIFEST_PATH")"

mkdir -p \
  "$STAMP_DIR" \
  "$(root_path /etc/aios)" \
  "$(root_path /etc/aios/installer)" \
  "$(root_path /var/lib/aios/registry)" \
  "$(root_path /var/lib/aios/updated/recovery)" \
  "$(dirname "$DBUS_MACHINE_ID_PATH")" \
  "$(dirname "$RANDOM_SEED_PATH")"

if [[ -f "$STAMP_FILE" ]]; then
  exit 0
fi

if [[ ! -e "$MACHINE_ID_PATH" ]]; then
  : >"$MACHINE_ID_PATH"
fi

if [[ -e "$DBUS_MACHINE_ID_PATH" || -L "$DBUS_MACHINE_ID_PATH" ]]; then
  rm -f "$DBUS_MACHINE_ID_PATH"
fi
ln -s /etc/machine-id "$DBUS_MACHINE_ID_PATH"

machine_id_generated=false
machine_id_state="preserved"
if [[ ! -s "$MACHINE_ID_PATH" ]]; then
  machine_id_state="empty"
  if command -v "$MACHINE_ID_SETUP_BIN" >/dev/null 2>&1; then
    if [[ -n "$ROOT_PREFIX" ]]; then
      "$MACHINE_ID_SETUP_BIN" --root "$ROOT_PREFIX" >/dev/null 2>&1 || true
    else
      "$MACHINE_ID_SETUP_BIN" >/dev/null 2>&1 || true
    fi
  fi
fi

if [[ "$machine_id_state" == "empty" && -s "$MACHINE_ID_PATH" ]]; then
  machine_id_generated=true
  machine_id_state="generated"
elif [[ ! -s "$MACHINE_ID_PATH" ]]; then
  machine_id_state="empty"
fi

random_seed_generated=false
random_seed_state="preserved"
if [[ ! -s "$RANDOM_SEED_PATH" ]]; then
  random_seed_state="absent"
  rm -f "$RANDOM_SEED_PATH"
  if write_random_seed; then
    random_seed_generated=true
    random_seed_state="generated"
  fi
fi

random_seed_present=false
random_seed_size_bytes=0
if [[ -s "$RANDOM_SEED_PATH" ]]; then
  random_seed_present=true
  random_seed_size_bytes="$(wc -c < "$RANDOM_SEED_PATH" | tr -d ' ' )"
elif [[ -e "$RANDOM_SEED_PATH" ]]; then
  random_seed_state="empty"
fi

install_metadata_present=false
if [[ -n "$INSTALL_ID$INSTALL_SOURCE$INSTALLER_VERSION$INSTALL_MODE$INSTALL_SLOT$BOOT_BACKEND$VENDOR_ID$HARDWARE_PROFILE_ID$INSTALL_MANIFEST_PATH$RECOVERY_IMAGE_PROFILE$RECOVERY_DEFAULT_TARGET$RECOVERY_IMAGE_MANIFEST_PATH" ]]; then
  install_metadata_present=true
fi

install_manifest_present=false
if [[ -n "$INSTALL_MANIFEST_RESOLVED_PATH" && -e "$INSTALL_MANIFEST_RESOLVED_PATH" ]]; then
  install_manifest_present=true
fi

recovery_image_manifest_present=false
if [[ -n "$RECOVERY_IMAGE_MANIFEST_RESOLVED_PATH" && -e "$RECOVERY_IMAGE_MANIFEST_RESOLVED_PATH" ]]; then
  recovery_image_manifest_present=true
fi

cat >"$REPORT_FILE" <<EOF
{
  "initialized_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "profile_id": "$(json_escape "$PROFILE_ID")",
  "channel": "$(json_escape "$CHANNEL")",
  "support_url": "$(json_escape "$SUPPORT_URL")",
  "root_prefix": "$(json_escape "$ROOT_PREFIX")",
  "machine_id_path": "$(json_escape "$MACHINE_ID_PATH")",
  "machine_id_state": "$(json_escape "$machine_id_state")",
  "machine_id_generated": ${machine_id_generated},
  "dbus_machine_id_path": "$(json_escape "$DBUS_MACHINE_ID_PATH")",
  "dbus_machine_id_target": "/etc/machine-id",
  "random_seed_path": "$(json_escape "$RANDOM_SEED_PATH")",
  "random_seed_state": "$(json_escape "$random_seed_state")",
  "random_seed_generated": ${random_seed_generated},
  "random_seed_present": ${random_seed_present},
  "random_seed_size_bytes": ${random_seed_size_bytes},
  "install_metadata_present": ${install_metadata_present},
  "install_id": "$(json_escape "$INSTALL_ID")",
  "install_source": "$(json_escape "$INSTALL_SOURCE")",
  "installer_version": "$(json_escape "$INSTALLER_VERSION")",
  "install_mode": "$(json_escape "$INSTALL_MODE")",
  "install_slot": "$(json_escape "$INSTALL_SLOT")",
  "boot_backend": "$(json_escape "$BOOT_BACKEND")",
  "vendor_id": "$(json_escape "$VENDOR_ID")",
  "hardware_profile_id": "$(json_escape "$HARDWARE_PROFILE_ID")",
  "install_manifest_path": "$(json_escape "$INSTALL_MANIFEST_PATH")",
  "install_manifest_present": ${install_manifest_present},
  "recovery_image_profile": "$(json_escape "$RECOVERY_IMAGE_PROFILE")",
  "recovery_default_target": "$(json_escape "$RECOVERY_DEFAULT_TARGET")",
  "recovery_image_manifest_path": "$(json_escape "$RECOVERY_IMAGE_MANIFEST_PATH")",
  "recovery_image_manifest_present": ${recovery_image_manifest_present}
}
EOF

echo "AIOS_FIRSTBOOT_REPORT profile_id=$PROFILE_ID channel=$CHANNEL machine_id_state=$machine_id_state machine_id_generated=$machine_id_generated random_seed_state=$random_seed_state random_seed_present=$random_seed_present random_seed_size_bytes=$random_seed_size_bytes install_metadata_present=$install_metadata_present install_id=${INSTALL_ID:-none} install_source=${INSTALL_SOURCE:-none} install_slot=${INSTALL_SLOT:-unknown} boot_backend=${BOOT_BACKEND:-unknown} report=$REPORT_FILE"

touch "$STAMP_FILE"
