#!/usr/bin/env bash
set -euo pipefail

BOOTCTL_BIN="${AIOS_PLATFORM_BOOTCTL_BIN:-${AIOS_UPDATED_BOOTCTL_BIN:-bootctl}}"
ENTRY_PREFIX="${AIOS_PLATFORM_BOOT_ENTRY_PREFIX:-aios}"
STATE_DIR="${AIOS_UPDATED_BOOT_ENTRY_STATE_DIR:-/var/lib/aios/updated/boot}"
VERB="${1:-}"
shift || true

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --state-dir)
      STATE_DIR="$2"
      shift 2
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done
if (( ${#ARGS[@]} > 0 )); then
  set -- "${ARGS[@]}"
else
  set --
fi

mkdir -p "$STATE_DIR"

slot_entry() {
  printf '%s-%s.conf\n' "$ENTRY_PREFIX" "$1"
}

normalize_slot() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    a|slot-a|slot_a|${ENTRY_PREFIX}-a|${ENTRY_PREFIX}-a.conf) printf 'a\n' ;;
    b|slot-b|slot_b|${ENTRY_PREFIX}-b|${ENTRY_PREFIX}-b.conf) printf 'b\n' ;;
    *) return 1 ;;
  esac
}

read_slot_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    tr -d ' \r\n' < "$path"
    return 0
  fi
  return 1
}

current_slot() {
  if read_slot_file "$STATE_DIR/current-slot" >/dev/null 2>&1; then
    read_slot_file "$STATE_DIR/current-slot"
    return 0
  fi
  if [[ -f "$STATE_DIR/current-entry" ]]; then
    normalize_slot "$(tr -d ' \r\n' < "$STATE_DIR/current-entry")" && return 0
  fi
  return 1
}

call_bootctl() {
  if command -v "$BOOTCTL_BIN" >/dev/null 2>&1; then
    "$BOOTCTL_BIN" "$@"
  else
    return 127
  fi
}

case "$VERB" in
  status)
    slot="$(current_slot || true)"
    if [[ -n "$slot" ]]; then
      printf 'current_slot=%s\n' "$slot"
      printf 'active_slot=%s\n' "$slot"
    fi
    if [[ -f "$STATE_DIR/next-slot" ]]; then
      printf 'next_slot=%s\n' "$(tr -d ' \r\n' < "$STATE_DIR/next-slot")"
    fi
    printf 'backend=systemd-boot-bridge\n'
    ;;
  set-active|rollback)
    slot="$(normalize_slot "${1:-}")"
    entry="$(slot_entry "$slot")"
    call_bootctl set-oneshot "$entry" >/dev/null 2>&1 || true
    printf '%s\n' "$slot" > "$STATE_DIR/next-slot"
    printf '%s\n' "$entry" > "$STATE_DIR/next-entry"
    printf 'next_slot=%s\n' "$slot"
    printf 'next_entry=%s\n' "$entry"
    ;;
  mark-good)
    slot="$(normalize_slot "${1:-$(current_slot || echo a)}")"
    entry="$(slot_entry "$slot")"
    printf '%s\n' "$slot" > "$STATE_DIR/current-slot"
    printf '%s\n' "$slot" > "$STATE_DIR/last-good-slot"
    printf '%s\n' "$entry" > "$STATE_DIR/current-entry"
    rm -f "$STATE_DIR/next-slot" "$STATE_DIR/next-entry"
    printf 'current_slot=%s\n' "$slot"
    printf 'last_good_slot=%s\n' "$slot"
    ;;
  *)
    printf 'unsupported firmwarectl verb: %s\n' "$VERB" >&2
    exit 64
    ;;
esac
