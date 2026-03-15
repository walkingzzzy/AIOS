#!/usr/bin/env bash
set -euo pipefail

json_escape() {
  printf '%s' "$1" | sed -e 's#\\#\\\\#g' -e 's#"#\\"#g'
}

log() {
  printf '[aios-installer-guided] %s\n' "$*"
}

ENV_FILE="${AIOS_INSTALLER_ENV_FILE:-/etc/aios/installer/aios-installer.env}"
RUNNER="${AIOS_INSTALLER_RUNNER:-/usr/libexec/aios/aios-installer-run.sh}"
REPORT_DIR="${AIOS_INSTALLER_REPORT_DIR:-/run/aios-installer}"
SESSION_FILE="$REPORT_DIR/guided-session.json"
SUMMARY_FILE="$REPORT_DIR/guided-summary.txt"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

SOURCE_DISK="${AIOS_INSTALLER_SOURCE_DISK:-/dev/vdb}"
SOURCE_IMAGE_FILE="${AIOS_INSTALLER_SOURCE_IMAGE_FILE:-}"
TARGET_DISK="${AIOS_INSTALLER_TARGET_DISK:-/dev/vdc}"
RECOVERY_DISK="${AIOS_INSTALLER_RECOVERY_DISK:-}"
INSTALL_SLOT="${AIOS_INSTALLER_INSTALL_SLOT:-a}"
BOOT_BACKEND="${AIOS_INSTALLER_BOOT_BACKEND:-firmware}"
INSTALL_SOURCE="${AIOS_INSTALLER_INSTALL_SOURCE:-installer-media}"
PLATFORM_ID="${AIOS_INSTALLER_PLATFORM_ID:-generic-x86_64-uefi}"
PLATFORM_LABEL="${AIOS_INSTALLER_PLATFORM_LABEL:-$PLATFORM_ID}"
PLATFORM_PROFILE="${AIOS_INSTALLER_PLATFORM_PROFILE:-}"
VENDOR_ID="${AIOS_INSTALLER_VENDOR_ID:-}"
HARDWARE_PROFILE_ID="${AIOS_INSTALLER_HARDWARE_PROFILE_ID:-}"
PRE_INSTALL_HOOK="${AIOS_INSTALLER_PRE_INSTALL_HOOK:-}"
POST_INSTALL_HOOK="${AIOS_INSTALLER_POST_INSTALL_HOOK:-}"
GUIDED_MODE="${AIOS_INSTALLER_GUIDED_MODE:-auto}"
AUTO_CONFIRM_SECONDS="${AIOS_INSTALLER_GUIDED_AUTO_CONFIRM_SECONDS:-0}"
GUIDED_DRY_RUN="${AIOS_INSTALLER_GUIDED_DRY_RUN:-0}"
SELECTIONS_CHANGED=false

hook_status() {
  local path="$1"
  if [[ -z "$path" ]]; then
    printf 'not-configured\n'
    return 0
  fi
  if [[ -f "$path" ]]; then
    printf 'ready\n'
    return 0
  fi
  printf 'missing\n'
}

list_candidates() {
  if ! command -v lsblk >/dev/null 2>&1; then
    return 0
  fi
  lsblk -dnpo NAME,SIZE,MODEL,TYPE 2>/dev/null | awk '$4 == "disk" { print $1 "|" $2 "|" $3 }'
}

render_summary() {
  mkdir -p "$REPORT_DIR"
  {
    printf 'AIOS Guided Installer\n'
    printf '=====================\n'
    printf 'Platform       : %s\n' "$PLATFORM_LABEL"
    printf 'Platform ID    : %s\n' "$PLATFORM_ID"
    printf 'Platform Profile: %s\n' "${PLATFORM_PROFILE:-<unset>}"
    printf 'Install Source : %s\n' "$INSTALL_SOURCE"
    printf 'Boot Backend   : %s\n' "$BOOT_BACKEND"
    printf 'Install Slot   : %s\n' "$INSTALL_SLOT"
    printf 'Target Disk    : %s\n' "$TARGET_DISK"
    printf 'Recovery Disk  : %s\n' "${RECOVERY_DISK:-<unset>}"
    if [[ -n "$SOURCE_IMAGE_FILE" ]]; then
      printf 'Source Payload : %s\n' "$SOURCE_IMAGE_FILE"
    else
      printf 'Source Disk    : %s\n' "$SOURCE_DISK"
    fi
    printf 'Vendor ID      : %s\n' "${VENDOR_ID:-<unset>}"
    printf 'Hardware ID    : %s\n' "${HARDWARE_PROFILE_ID:-<unset>}"
    printf 'Pre Hook       : %s (%s)\n' "${PRE_INSTALL_HOOK:-<unset>}" "$(hook_status "$PRE_INSTALL_HOOK")"
    printf 'Post Hook      : %s (%s)\n' "${POST_INSTALL_HOOK:-<unset>}" "$(hook_status "$POST_INSTALL_HOOK")"
    printf 'Guided Mode    : %s\n' "$GUIDED_MODE"
    printf 'Auto Confirm   : %s\n' "$AUTO_CONFIRM_SECONDS"
    printf '\nVisible disks:\n'
    local candidates
    candidates="$(list_candidates || true)"
    if [[ -n "$candidates" ]]; then
      while IFS='|' read -r name size model; do
        printf '  - %s %s %s\n' "$name" "$size" "$model"
      done <<<"$candidates"
    else
      printf '  - lsblk unavailable\n'
    fi
  } | tee "$SUMMARY_FILE"
}

write_session() {
  local pre_status
  local post_status
  pre_status="$(hook_status "$PRE_INSTALL_HOOK")"
  post_status="$(hook_status "$POST_INSTALL_HOOK")"
  mkdir -p "$REPORT_DIR"
  cat >"$SESSION_FILE" <<EOF
{
  "platform_id": "$(json_escape "$PLATFORM_ID")",
  "platform_label": "$(json_escape "$PLATFORM_LABEL")",
  "platform_profile": "$(json_escape "$PLATFORM_PROFILE")",
  "install_source": "$(json_escape "$INSTALL_SOURCE")",
  "boot_backend": "$(json_escape "$BOOT_BACKEND")",
  "install_slot": "$(json_escape "$INSTALL_SLOT")",
  "target_disk": "$(json_escape "$TARGET_DISK")",
  "recovery_disk": "$(json_escape "$RECOVERY_DISK")",
  "source_disk": "$(json_escape "$SOURCE_DISK")",
  "source_image_file": "$(json_escape "$SOURCE_IMAGE_FILE")",
  "vendor_id": "$(json_escape "$VENDOR_ID")",
  "hardware_profile_id": "$(json_escape "$HARDWARE_PROFILE_ID")",
  "guided_mode": "$(json_escape "$GUIDED_MODE")",
  "auto_confirm_seconds": "$(json_escape "$AUTO_CONFIRM_SECONDS")",
  "pre_install_hook": {
    "path": "$(json_escape "$PRE_INSTALL_HOOK")",
    "status": "$(json_escape "$pre_status")"
  },
  "post_install_hook": {
    "path": "$(json_escape "$POST_INSTALL_HOOK")",
    "status": "$(json_escape "$post_status")"
  },
  "summary_path": "$(json_escape "$SUMMARY_FILE")",
  "runner": "$(json_escape "$RUNNER")"
}
EOF
}

maybe_prompt() {
  if [[ "$GUIDED_MODE" != "interactive" ]]; then
    return 0
  fi
  if [[ ! -t 0 || ! -t 1 ]]; then
    log "interactive mode requested without a TTY; continuing with current selections"
    return 0
  fi

  local answer
  printf '\nPress Enter to keep the current value.\n'
  read -r -p "Target disk [$TARGET_DISK]: " answer
  if [[ -n "$answer" ]]; then
    TARGET_DISK="$answer"
    export AIOS_INSTALLER_TARGET_DISK="$TARGET_DISK"
    SELECTIONS_CHANGED=true
  fi
  read -r -p "Recovery disk [${RECOVERY_DISK:-<unset>}]: " answer
  if [[ -n "$answer" ]]; then
    RECOVERY_DISK="$answer"
    export AIOS_INSTALLER_RECOVERY_DISK="$RECOVERY_DISK"
    SELECTIONS_CHANGED=true
  fi
  read -r -p "Install slot [$INSTALL_SLOT]: " answer
  if [[ "$answer" == "a" || "$answer" == "b" ]]; then
    INSTALL_SLOT="$answer"
    export AIOS_INSTALLER_INSTALL_SLOT="$INSTALL_SLOT"
    SELECTIONS_CHANGED=true
  fi
  read -r -p "Continue with installation? [y/N]: " answer
  case "${answer,,}" in
    y|yes) ;;
    *) log "installation cancelled by operator"; exit 1 ;;
  esac
}

maybe_wait() {
  if [[ "$GUIDED_MODE" == "interactive" ]]; then
    return 0
  fi
  if [[ "${AUTO_CONFIRM_SECONDS:-0}" =~ ^[0-9]+$ ]] && (( AUTO_CONFIRM_SECONDS > 0 )); then
    log "auto-confirming in ${AUTO_CONFIRM_SECONDS}s"
    sleep "$AUTO_CONFIRM_SECONDS"
  fi
}

render_summary
maybe_prompt
if [[ "$SELECTIONS_CHANGED" == "true" ]]; then
  render_summary
fi
write_session
maybe_wait

if [[ "$GUIDED_DRY_RUN" == "1" || "$GUIDED_DRY_RUN" == "true" ]]; then
  log "dry-run complete; installer runner not invoked"
  exit 0
fi

log "starting installer runner: $RUNNER"
exec /usr/bin/bash "$RUNNER"
