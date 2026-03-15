#!/usr/bin/env bash
set -euo pipefail

NVBOOTCTRL_BIN="${AIOS_NVIDIA_NVBOOTCTRL_BIN:-${AIOS_UPDATED_NVIDIA_NVBOOTCTRL_BIN:-nvbootctrl}}"
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

require_tool() {
  if command -v "$NVBOOTCTRL_BIN" >/dev/null 2>&1 || [[ -x "$NVBOOTCTRL_BIN" ]]; then
    return 0
  fi
  printf 'missing nvbootctrl binary: %s\n' "$NVBOOTCTRL_BIN" >&2
  exit 127
}

normalize_slot() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | tr -d ' \r\n')"
  case "$value" in
    0|a|slot-a|slot_a|aios-a|aios-a.conf) printf 'a\n' ;;
    1|b|slot-b|slot_b|aios-b|aios-b.conf) printf 'b\n' ;;
    *) return 1 ;;
  esac
}

slot_index() {
  case "$(normalize_slot "$1")" in
    a) printf '0\n' ;;
    b) printf '1\n' ;;
  esac
}

slot_entry() {
  printf 'aios-%s.conf\n' "$1"
}

run_tool() {
  require_tool
  "$NVBOOTCTRL_BIN" "$@"
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
    normalize_slot "$(read_slot_file "$STATE_DIR/current-slot")"
    return 0
  fi
  normalize_slot "$(run_tool get-current-slot 2>/dev/null || true)"
}

slots_dump() {
  run_tool dump-slots-info 2>/dev/null | tr '\n' ';' | sed 's/;*$//' || true
}

case "$VERB" in
  status)
    slot="$(current_slot || true)"
    if [[ -n "$slot" ]]; then
      printf 'current_slot=%s\n' "$slot"
      printf 'active_slot=%s\n' "$slot"
    fi
    printf 'backend=nvidia-nvbootctrl-adapter\n'
    printf 'tool_binary=%s\n' "$NVBOOTCTRL_BIN"
    dump="$(slots_dump)"
    if [[ -n "$dump" ]]; then
      printf 'slots_info=%s\n' "$dump"
    fi
    ;;
  set-active|rollback)
    slot="$(normalize_slot "${1:-}")"
    index="$(slot_index "$slot")"
    entry="$(slot_entry "$slot")"
    run_tool set-active-boot-slot "$index" >/dev/null
    printf '%s\n' "$slot" > "$STATE_DIR/next-slot"
    printf '%s\n' "$entry" > "$STATE_DIR/next-entry"
    printf 'next_slot=%s\n' "$slot"
    printf 'next_entry=%s\n' "$entry"
    ;;
  mark-good)
    slot="${1:-$(current_slot || echo a)}"
    slot="$(normalize_slot "$slot")"
    entry="$(slot_entry "$slot")"
    run_tool mark-boot-successful >/dev/null
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
