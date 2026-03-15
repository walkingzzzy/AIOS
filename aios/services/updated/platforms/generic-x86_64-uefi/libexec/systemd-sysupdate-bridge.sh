#!/usr/bin/env bash
set -euo pipefail

SYSUPDATE_BIN="${AIOS_PLATFORM_SYSUPDATE_BIN:-${AIOS_UPDATED_REAL_SYSUPDATE_BIN:-systemd-sysupdate}}"
original=("$@")
definitions_dir=""
subcommand=""

for ((i=0; i<${#original[@]}; i++)); do
  arg="${original[$i]}"
  if [[ "$arg" == "--definitions" && $((i + 1)) -lt ${#original[@]} ]]; then
    definitions_dir="${original[$((i + 1))]}"
  fi
done
if [[ ${#original[@]} -gt 0 ]]; then
  subcommand="${original[$((${#original[@]} - 1))]}"
fi

selected_definitions="$definitions_dir"
if [[ -n "$definitions_dir" ]]; then
  if [[ "$subcommand" == "update" ]]; then
    current_slot="${AIOS_UPDATED_CURRENT_SLOT:-a}"
    target_slot="${AIOS_UPDATED_TARGET_SLOT:-}"
    if [[ -z "$target_slot" ]]; then
      if [[ "$(printf '%s' "$current_slot" | tr '[:upper:]' '[:lower:]')" == "a" ]]; then
        target_slot="b"
      else
        target_slot="a"
      fi
    fi
    if [[ -d "$definitions_dir/slot-$target_slot" ]]; then
      selected_definitions="$definitions_dir/slot-$target_slot"
    fi
  elif [[ -d "$definitions_dir/common" ]]; then
    selected_definitions="$definitions_dir/common"
  fi
fi

rebuilt=()
replaced_definitions=false
skip_next=false
for arg in "${original[@]}"; do
  if [[ "$skip_next" == true ]]; then
    skip_next=false
    continue
  fi
  if [[ "$arg" == "--definitions" ]]; then
    rebuilt+=("--definitions" "$selected_definitions")
    replaced_definitions=true
    skip_next=true
    continue
  fi
  rebuilt+=("$arg")
done

if [[ "$replaced_definitions" == false && -n "$selected_definitions" ]]; then
  rebuilt=("--definitions" "$selected_definitions" "${rebuilt[@]}")
fi

exec "$SYSUPDATE_BIN" "${rebuilt[@]}"
