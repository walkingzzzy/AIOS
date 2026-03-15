#!/usr/bin/env bash
set -euo pipefail

json_escape() {
  printf '%s' "$1" | sed -e 's#\\#\\\\#g' -e 's#"#\\"#g'
}

log() {
  printf '[aios-installer] %s\n' "$*"
}

SOURCE_DISK="${AIOS_INSTALLER_SOURCE_DISK:-/dev/vdb}"
SOURCE_IMAGE_FILE="${AIOS_INSTALLER_SOURCE_IMAGE_FILE:-}"
TARGET_DISK="${AIOS_INSTALLER_TARGET_DISK:-/dev/vdc}"
RECOVERY_DISK="${AIOS_INSTALLER_RECOVERY_DISK:-}"
SOURCE_PROFILE="${AIOS_INSTALLER_SOURCE_PROFILE:-qemu-x86_64-dev}"
RECOVERY_PROFILE="${AIOS_INSTALLER_RECOVERY_PROFILE:-qemu-x86_64-recovery}"
INSTALL_SOURCE="${AIOS_INSTALLER_INSTALL_SOURCE:-installer-media}"
INSTALLER_VERSION="${AIOS_INSTALLER_VERSION:-aios-installer-media-v1}"
INSTALL_SLOT="${AIOS_INSTALLER_INSTALL_SLOT:-a}"
BOOT_BACKEND="${AIOS_INSTALLER_BOOT_BACKEND:-firmware}"
VENDOR_ID="${AIOS_INSTALLER_VENDOR_ID:-}"
HARDWARE_PROFILE_ID="${AIOS_INSTALLER_HARDWARE_PROFILE_ID:-}"
ESP_PARTLABEL="${AIOS_INSTALLER_ESP_PARTLABEL:-AIOS-ESP}"
ROOT_PARTLABEL="${AIOS_INSTALLER_ROOT_PARTLABEL:-AIOS-root}"
VAR_PARTLABEL="${AIOS_INSTALLER_VAR_PARTLABEL:-AIOS-var}"
ESP_PARTITION_INDEX="${AIOS_INSTALLER_ESP_PARTITION_INDEX:-1}"
ROOT_PARTITION_INDEX="${AIOS_INSTALLER_ROOT_PARTITION_INDEX:-2}"
VAR_PARTITION_INDEX="${AIOS_INSTALLER_VAR_PARTITION_INDEX:-3}"
PRE_INSTALL_HOOK="${AIOS_INSTALLER_PRE_INSTALL_HOOK:-}"
POST_INSTALL_HOOK="${AIOS_INSTALLER_POST_INSTALL_HOOK:-}"
COPY_BLOCK_SIZE="${AIOS_INSTALLER_COPY_BLOCK_SIZE:-16M}"
INSTALL_ID="${AIOS_INSTALLER_INSTALL_ID:-installer-$(date -u +%Y%m%d%H%M%SZ)}"
INSTALL_MODE="image-clone"
RECOVERY_DEFAULT_TARGET="aios-recovery.target"
REPORT_DIR="${AIOS_INSTALLER_REPORT_DIR:-/run/aios-installer}"
REPORT_FILE="$REPORT_DIR/report.json"
COMPLETED_STAMP="$REPORT_DIR/completed"
TARGET_ROOT="/run/aios-installer/target-root"
TARGET_VAR="$TARGET_ROOT/var"
TARGET_BOOT="$TARGET_ROOT/boot"
TARGET_OVERLAY_DIR="${AIOS_INSTALLER_TARGET_OVERLAY_DIR:-/usr/share/aios/installer/target-overlay}"
ROOT_PARTITION=""
VAR_PARTITION=""
ESP_PARTITION=""
SOURCE_SIZE_BYTES=""
TARGET_SIZE_BYTES=""
RECOVERY_SIZE_BYTES=""
RECOVERY_MANIFEST_PRESENT=false
FIRSTBOOT_RESET=false
TARGET_OVERLAY_APPLIED=false
SOURCE_DEVICE_KIND="block-device"
FAILURE_REASON=""
STATUS="failed"
PRE_INSTALL_HOOK_STATUS="not-configured"
POST_INSTALL_HOOK_STATUS="not-configured"

cleanup() {
  if mountpoint -q "$TARGET_BOOT"; then
    umount "$TARGET_BOOT" || true
  fi
  if mountpoint -q "$TARGET_VAR"; then
    umount "$TARGET_VAR" || true
  fi
  if mountpoint -q "$TARGET_ROOT"; then
    umount "$TARGET_ROOT" || true
  fi
}
trap cleanup EXIT

sync_path() {
  local path="$1"
  if [[ -e "$path" ]] && sync -f "$path" >/dev/null 2>&1; then
    return 0
  fi
  sync >/dev/null 2>&1 || true
}

flush_block_device() {
  local device="$1"
  if [[ -n "$device" && -b "$device" ]]; then
    blockdev --flushbufs "$device" >/dev/null 2>&1 || true
  fi
}

flush_target_state() {
  log "flushing target install state"
  if mountpoint -q "$TARGET_BOOT"; then
    sync_path "$TARGET_BOOT"
  fi
  if mountpoint -q "$TARGET_VAR"; then
    sync_path "$TARGET_VAR"
  fi
  if mountpoint -q "$TARGET_ROOT"; then
    sync_path "$TARGET_ROOT"
  fi
  flush_block_device "$ESP_PARTITION"
  flush_block_device "$VAR_PARTITION"
  flush_block_device "$ROOT_PARTITION"
  flush_block_device "$TARGET_DISK"
}

write_report() {
  mkdir -p "$REPORT_DIR"
  cat >"$REPORT_FILE" <<EOF
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "status": "$(json_escape "$STATUS")",
  "failure_reason": "$(json_escape "$FAILURE_REASON")",
  "source_disk": "$(json_escape "$SOURCE_DISK")",
  "source_image_file": "$(json_escape "$SOURCE_IMAGE_FILE")",
  "source_device_kind": "$(json_escape "$SOURCE_DEVICE_KIND")",
  "target_disk": "$(json_escape "$TARGET_DISK")",
  "recovery_disk": "$(json_escape "$RECOVERY_DISK")",
  "source_profile": "$(json_escape "$SOURCE_PROFILE")",
  "recovery_profile": "$(json_escape "$RECOVERY_PROFILE")",
  "install_id": "$(json_escape "$INSTALL_ID")",
  "install_source": "$(json_escape "$INSTALL_SOURCE")",
  "installer_version": "$(json_escape "$INSTALLER_VERSION")",
  "install_mode": "$(json_escape "$INSTALL_MODE")",
  "install_slot": "$(json_escape "$INSTALL_SLOT")",
  "boot_backend": "$(json_escape "$BOOT_BACKEND")",
  "vendor_id": "$(json_escape "$VENDOR_ID")",
  "hardware_profile_id": "$(json_escape "$HARDWARE_PROFILE_ID")",
  "source_size_bytes": "$(json_escape "$SOURCE_SIZE_BYTES")",
  "target_size_bytes": "$(json_escape "$TARGET_SIZE_BYTES")",
  "recovery_size_bytes": "$(json_escape "$RECOVERY_SIZE_BYTES")",
  "root_partition": "$(json_escape "$ROOT_PARTITION")",
  "var_partition": "$(json_escape "$VAR_PARTITION")",
  "esp_partition": "$(json_escape "$ESP_PARTITION")",
  "partition_strategy": {
    "esp_partlabel": "$(json_escape "$ESP_PARTLABEL")",
    "root_partlabel": "$(json_escape "$ROOT_PARTLABEL")",
    "var_partlabel": "$(json_escape "$VAR_PARTLABEL")",
    "esp_partition_index": "$(json_escape "$ESP_PARTITION_INDEX")",
    "root_partition_index": "$(json_escape "$ROOT_PARTITION_INDEX")",
    "var_partition_index": "$(json_escape "$VAR_PARTITION_INDEX")"
  },
  "firmware_hooks": {
    "pre_install": {
      "path": "$(json_escape "$PRE_INSTALL_HOOK")",
      "status": "$(json_escape "$PRE_INSTALL_HOOK_STATUS")"
    },
    "post_install": {
      "path": "$(json_escape "$POST_INSTALL_HOOK")",
      "status": "$(json_escape "$POST_INSTALL_HOOK_STATUS")"
    }
  },
  "recovery_manifest_present": ${RECOVERY_MANIFEST_PRESENT},
  "firstboot_reset": ${FIRSTBOOT_RESET},
  "target_overlay_dir": "$(json_escape "$TARGET_OVERLAY_DIR")",
  "target_overlay_applied": ${TARGET_OVERLAY_APPLIED},
  "report_path": "$(json_escape "$REPORT_FILE")"
}
EOF
}

fail() {
  FAILURE_REASON="$1"
  STATUS="failed"
  write_report
  echo "AIOS_INSTALLER_REPORT status=failed source_disk=$SOURCE_DISK target_disk=$TARGET_DISK reason=$(printf '%s' "$FAILURE_REASON" | tr ' ' '_') report=$REPORT_FILE"
  exit 1
}

require_block_device() {
  local path="$1"
  if [[ ! -b "$path" ]]; then
    fail "missing block device: $path"
  fi
}

partition_by_label() {
  local disk="$1"
  local label="$2"
  while read -r path partlabel; do
    if [[ "$partlabel" == "$label" ]]; then
      printf '%s\n' "$path"
      return 0
    fi
  done < <(lsblk -nrpo PATH,PARTLABEL "$disk")
  return 1
}

partition_by_index() {
  local disk="$1"
  local index="$2"
  local candidate
  candidate="${disk}${index}"
  if [[ "$disk" =~ [0-9]$ ]]; then
    candidate="${disk}p${index}"
  fi
  if [[ -b "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  return 1
}

run_hook() {
  local stage="$1"
  local hook_path="$2"
  if [[ -z "$hook_path" ]]; then
    return 0
  fi
  [[ -f "$hook_path" ]] || fail "missing ${stage} hook: $hook_path"

  if AIOS_INSTALLER_HOOK_STAGE="$stage" \
     AIOS_INSTALLER_SYSROOT="$TARGET_ROOT" \
     AIOS_INSTALLER_INSTALL_ID="$INSTALL_ID" \
     AIOS_INSTALLER_INSTALL_SOURCE="$INSTALL_SOURCE" \
     AIOS_INSTALLER_INSTALLER_VERSION="$INSTALLER_VERSION" \
     AIOS_INSTALLER_INSTALL_MODE="$INSTALL_MODE" \
     AIOS_INSTALLER_INSTALL_SLOT="$INSTALL_SLOT" \
     AIOS_INSTALLER_BOOT_BACKEND="$BOOT_BACKEND" \
     AIOS_INSTALLER_VENDOR_ID="$VENDOR_ID" \
     AIOS_INSTALLER_HARDWARE_PROFILE_ID="$HARDWARE_PROFILE_ID" \
     AIOS_INSTALLER_ESP_PARTLABEL="$ESP_PARTLABEL" \
     AIOS_INSTALLER_ROOT_PARTLABEL="$ROOT_PARTLABEL" \
     AIOS_INSTALLER_VAR_PARTLABEL="$VAR_PARTLABEL" \
     AIOS_INSTALLER_ESP_PARTITION_INDEX="$ESP_PARTITION_INDEX" \
     AIOS_INSTALLER_ROOT_PARTITION_INDEX="$ROOT_PARTITION_INDEX" \
     AIOS_INSTALLER_VAR_PARTITION_INDEX="$VAR_PARTITION_INDEX" \
     AIOS_INSTALLER_REPORT_DIR="$REPORT_DIR" \
     bash "$hook_path"; then
    if [[ "$stage" == "pre-install" ]]; then
      PRE_INSTALL_HOOK_STATUS="succeeded"
    else
      POST_INSTALL_HOOK_STATUS="succeeded"
    fi
  else
    if [[ "$stage" == "pre-install" ]]; then
      PRE_INSTALL_HOOK_STATUS="failed"
    else
      POST_INSTALL_HOOK_STATUS="failed"
    fi
    fail "${stage} hook failed: $hook_path"
  fi
}

reset_firstboot_state() {
  mkdir -p "$TARGET_ROOT/etc" "$TARGET_ROOT/var/lib/dbus" "$TARGET_ROOT/var/lib/aios/firstboot"
  : > "$TARGET_ROOT/etc/machine-id"
  rm -f "$TARGET_ROOT/var/lib/systemd/random-seed"
  rm -f "$TARGET_ROOT/var/lib/dbus/machine-id"
  ln -s /etc/machine-id "$TARGET_ROOT/var/lib/dbus/machine-id"
  rm -f "$TARGET_ROOT/var/lib/aios/firstboot/initialized"
  rm -f "$TARGET_ROOT/var/lib/aios/firstboot/report.json"
  FIRSTBOOT_RESET=true
}

rewrite_firstboot_env() {
  local env_path="$TARGET_ROOT/etc/aios/firstboot/aios-firstboot.env"
  local tmp_path
  tmp_path="$(mktemp)"
  mkdir -p "$(dirname "$env_path")"
  if [[ -f "$env_path" ]]; then
    grep -Ev '^(AIOS_FIRSTBOOT_INSTALL_ID|AIOS_FIRSTBOOT_INSTALL_SOURCE|AIOS_FIRSTBOOT_INSTALLER_VERSION|AIOS_FIRSTBOOT_INSTALL_MODE|AIOS_FIRSTBOOT_INSTALL_SLOT|AIOS_FIRSTBOOT_BOOT_BACKEND|AIOS_FIRSTBOOT_VENDOR_ID|AIOS_FIRSTBOOT_HARDWARE_PROFILE_ID|AIOS_FIRSTBOOT_INSTALL_MANIFEST|AIOS_FIRSTBOOT_RECOVERY_IMAGE_PROFILE|AIOS_FIRSTBOOT_RECOVERY_DEFAULT_TARGET|AIOS_FIRSTBOOT_RECOVERY_IMAGE_MANIFEST)=' "$env_path" > "$tmp_path" || true
  fi
  {
    cat "$tmp_path"
    printf 'AIOS_FIRSTBOOT_INSTALL_ID=%s\n' "$INSTALL_ID"
    printf 'AIOS_FIRSTBOOT_INSTALL_SOURCE=%s\n' "$INSTALL_SOURCE"
    printf 'AIOS_FIRSTBOOT_INSTALLER_VERSION=%s\n' "$INSTALLER_VERSION"
    printf 'AIOS_FIRSTBOOT_INSTALL_MODE=%s\n' "$INSTALL_MODE"
    printf 'AIOS_FIRSTBOOT_INSTALL_SLOT=%s\n' "$INSTALL_SLOT"
    printf 'AIOS_FIRSTBOOT_BOOT_BACKEND=%s\n' "$BOOT_BACKEND"
    printf 'AIOS_FIRSTBOOT_VENDOR_ID=%s\n' "$VENDOR_ID"
    printf 'AIOS_FIRSTBOOT_HARDWARE_PROFILE_ID=%s\n' "$HARDWARE_PROFILE_ID"
    printf 'AIOS_FIRSTBOOT_INSTALL_MANIFEST=%s\n' '/etc/aios/installer/install-manifest.json'
    printf 'AIOS_FIRSTBOOT_RECOVERY_IMAGE_PROFILE=%s\n' "$RECOVERY_PROFILE"
    printf 'AIOS_FIRSTBOOT_RECOVERY_DEFAULT_TARGET=%s\n' "$RECOVERY_DEFAULT_TARGET"
    if [[ "$RECOVERY_MANIFEST_PRESENT" == true ]]; then
      printf 'AIOS_FIRSTBOOT_RECOVERY_IMAGE_MANIFEST=%s\n' '/etc/aios/installer/recovery-image-manifest.json'
    fi
  } > "$env_path"
  rm -f "$tmp_path"
}

write_target_manifests() {
  local installer_dir="$TARGET_ROOT/etc/aios/installer"
  local install_manifest_path="$installer_dir/install-manifest.json"
  local recovery_manifest_path="$installer_dir/recovery-image-manifest.json"
  mkdir -p "$installer_dir"
  cat >"$install_manifest_path" <<EOF
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "install_id": "$(json_escape "$INSTALL_ID")",
  "install_source": "$(json_escape "$INSTALL_SOURCE")",
  "installer_version": "$(json_escape "$INSTALLER_VERSION")",
  "install_mode": "$(json_escape "$INSTALL_MODE")",
  "install_slot": "$(json_escape "$INSTALL_SLOT")",
  "boot_backend": "$(json_escape "$BOOT_BACKEND")",
  "vendor_id": "$(json_escape "$VENDOR_ID")",
  "hardware_profile_id": "$(json_escape "$HARDWARE_PROFILE_ID")",
  "source_disk": "$(json_escape "$SOURCE_DISK")",
  "source_image_file": "$(json_escape "$SOURCE_IMAGE_FILE")",
  "source_device_kind": "$(json_escape "$SOURCE_DEVICE_KIND")",
  "target_disk": "$(json_escape "$TARGET_DISK")",
  "source_profile": "$(json_escape "$SOURCE_PROFILE")",
  "root_partition": "$(json_escape "$ROOT_PARTITION")",
  "var_partition": "$(json_escape "$VAR_PARTITION")",
  "esp_partition": "$(json_escape "$ESP_PARTITION")",
  "partition_strategy": {
    "esp_partlabel": "$(json_escape "$ESP_PARTLABEL")",
    "root_partlabel": "$(json_escape "$ROOT_PARTLABEL")",
    "var_partlabel": "$(json_escape "$VAR_PARTLABEL")",
    "esp_partition_index": "$(json_escape "$ESP_PARTITION_INDEX")",
    "root_partition_index": "$(json_escape "$ROOT_PARTITION_INDEX")",
    "var_partition_index": "$(json_escape "$VAR_PARTITION_INDEX")"
  },
  "firmware_hooks": {
    "pre_install": {
      "path": "$(json_escape "$PRE_INSTALL_HOOK")",
      "status": "$(json_escape "$PRE_INSTALL_HOOK_STATUS")"
    },
    "post_install": {
      "path": "$(json_escape "$POST_INSTALL_HOOK")",
      "status": "$(json_escape "$POST_INSTALL_HOOK_STATUS")"
    }
  }
}
EOF

  if [[ -n "$RECOVERY_DISK" && -b "$RECOVERY_DISK" ]]; then
    RECOVERY_MANIFEST_PRESENT=true
    RECOVERY_SIZE_BYTES="$(blockdev --getsize64 "$RECOVERY_DISK")"
    cat >"$recovery_manifest_path" <<EOF
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "profile": "$(json_escape "$RECOVERY_PROFILE")",
  "default_target": "$(json_escape "$RECOVERY_DEFAULT_TARGET")",
  "source_disk": "$(json_escape "$RECOVERY_DISK")",
  "size_bytes": "$(json_escape "$RECOVERY_SIZE_BYTES")",
  "mode": "external-recovery-media"
}
EOF
  else
    rm -f "$recovery_manifest_path"
  fi
}

seed_boot_state() {
  local boot_dir="$TARGET_ROOT/var/lib/aios/updated/boot"
  mkdir -p "$boot_dir"
  printf '%s\n' "$INSTALL_SLOT" > "$boot_dir/current-slot"
  printf '%s\n' "$INSTALL_SLOT" > "$boot_dir/last-good-slot"
  printf 'aios-%s.conf\n' "$INSTALL_SLOT" > "$boot_dir/current-entry"
  rm -f "$boot_dir/next-slot" "$boot_dir/next-entry"
}

apply_target_overlay() {
  if [[ ! -d "$TARGET_OVERLAY_DIR" ]]; then
    return 0
  fi
  log "applying target overlay from $TARGET_OVERLAY_DIR"
  cp -a "$TARGET_OVERLAY_DIR"/. "$TARGET_ROOT"/
  TARGET_OVERLAY_APPLIED=true
}

log "installer target booted"
if [[ -z "$SOURCE_IMAGE_FILE" ]]; then
  require_block_device "$SOURCE_DISK"
else
  [[ -f "$SOURCE_IMAGE_FILE" ]] || fail "missing source image file: $SOURCE_IMAGE_FILE"
  SOURCE_DEVICE_KIND="payload-file"
fi
require_block_device "$TARGET_DISK"
if [[ -n "$RECOVERY_DISK" ]]; then
  require_block_device "$RECOVERY_DISK"
fi

if [[ -n "$SOURCE_IMAGE_FILE" ]]; then
  SOURCE_SIZE_BYTES="$(stat -c %s "$SOURCE_IMAGE_FILE")"
else
  SOURCE_SIZE_BYTES="$(blockdev --getsize64 "$SOURCE_DISK")"
fi
TARGET_SIZE_BYTES="$(blockdev --getsize64 "$TARGET_DISK")"
if (( TARGET_SIZE_BYTES < SOURCE_SIZE_BYTES )); then
  fail "target disk is smaller than source image"
fi

if [[ -n "$SOURCE_IMAGE_FILE" ]]; then
  log "copying bootable source image from $SOURCE_IMAGE_FILE to $TARGET_DISK"
  dd if="$SOURCE_IMAGE_FILE" of="$TARGET_DISK" bs="$COPY_BLOCK_SIZE" conv=fsync status=progress
else
  log "copying bootable source image from $SOURCE_DISK to $TARGET_DISK"
  dd if="$SOURCE_DISK" of="$TARGET_DISK" bs="$COPY_BLOCK_SIZE" conv=fsync status=progress
fi
flush_block_device "$TARGET_DISK"
blockdev --rereadpt "$TARGET_DISK" >/dev/null 2>&1 || true
partprobe "$TARGET_DISK" >/dev/null 2>&1 || true
udevadm settle >/dev/null 2>&1 || true
sleep 1

ROOT_PARTITION="$(partition_by_label "$TARGET_DISK" "$ROOT_PARTLABEL" || true)"
VAR_PARTITION="$(partition_by_label "$TARGET_DISK" "$VAR_PARTLABEL" || true)"
ESP_PARTITION="$(partition_by_label "$TARGET_DISK" "$ESP_PARTLABEL" || true)"
if [[ -z "$ESP_PARTITION" ]]; then
  ESP_PARTITION="$(partition_by_index "$TARGET_DISK" "$ESP_PARTITION_INDEX" || true)"
fi
if [[ -z "$ROOT_PARTITION" ]]; then
  ROOT_PARTITION="$(partition_by_index "$TARGET_DISK" "$ROOT_PARTITION_INDEX" || true)"
fi
if [[ -z "$VAR_PARTITION" ]]; then
  VAR_PARTITION="$(partition_by_index "$TARGET_DISK" "$VAR_PARTITION_INDEX" || true)"
fi
[[ -n "$ROOT_PARTITION" ]] || fail "missing root partition on target disk (label=$ROOT_PARTLABEL index=$ROOT_PARTITION_INDEX)"
[[ -n "$ESP_PARTITION" ]] || fail "missing esp partition on target disk (label=$ESP_PARTLABEL index=$ESP_PARTITION_INDEX)"

mkdir -p "$TARGET_ROOT" "$TARGET_VAR" "$TARGET_BOOT"
mount "$ROOT_PARTITION" "$TARGET_ROOT"
if [[ -n "$VAR_PARTITION" ]]; then
  mount "$VAR_PARTITION" "$TARGET_VAR"
else
  mkdir -p "$TARGET_VAR"
  log 'target image does not expose a dedicated var partition; using root filesystem /var'
fi
mount "$ESP_PARTITION" "$TARGET_BOOT"

log "running installer hooks and writing target manifests"
run_hook "pre-install" "$PRE_INSTALL_HOOK"
log "resetting firstboot state"
reset_firstboot_state
log "writing target install manifests"
write_target_manifests
log "applying target overlay"
apply_target_overlay
log "rewriting target firstboot environment"
rewrite_firstboot_env
log "seeding updated boot state"
seed_boot_state
log "running post-install hook"
run_hook "post-install" "$POST_INSTALL_HOOK"
write_target_manifests
mkdir -p "$REPORT_DIR"
touch "$COMPLETED_STAMP"
STATUS="success"
write_report
flush_target_state

echo "AIOS_INSTALLER_REPORT status=success source_disk=$SOURCE_DISK target_disk=$TARGET_DISK install_id=$INSTALL_ID install_slot=$INSTALL_SLOT boot_backend=$BOOT_BACKEND root_partition=$ROOT_PARTITION recovery_manifest_present=$RECOVERY_MANIFEST_PRESENT firstboot_reset=$FIRSTBOOT_RESET report=$REPORT_FILE"
log "powering off installer media"
systemctl --no-block poweroff >/dev/null 2>&1 || true
