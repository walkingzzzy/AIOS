#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OVERLAY_DIR="${AIOS_IMAGE_OVERLAY_DIR:-$ROOT_DIR/aios/image/mkosi.extra}"
BIN_DIR="${AIOS_BIN_DIR:-}"
LINUX_BINARY_STRATEGY="${AIOS_IMAGE_LINUX_BINARY_STRATEGY:-auto}"
PRECHECK=false
FORWARD_ARGS=()
CACHED_CONTAINER_BIN_DIR=""

resolve_python_bin() {
  if [[ -n "${AIOS_PYTHON_BIN:-}" ]]; then
    printf '%s\n' "$AIOS_PYTHON_BIN"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf 'python3\n'
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf 'python\n'
    return 0
  fi
  printf 'python3\n'
}

PYTHON_BIN="$(resolve_python_bin)"

default_aios_bin_dir() {
  PYTHONPATH="$ROOT_DIR/scripts" "$PYTHON_BIN" - "$ROOT_DIR" <<'PY'
from pathlib import Path
import sys

from aios_cargo_bins import default_aios_bin_dir

print(default_aios_bin_dir(Path(sys.argv[1])))
PY
}

default_container_native_bin_dir() {
  PYTHONPATH="$ROOT_DIR/scripts" "$PYTHON_BIN" - "$ROOT_DIR" <<'PY'
from pathlib import Path
import sys

from aios_cargo_bins import default_container_native_bin_dir

print(default_container_native_bin_dir(Path(sys.argv[1])))
PY
}

cached_container_bin_dir_ready() {
  PYTHONPATH="$ROOT_DIR/scripts" "$PYTHON_BIN" - "$1" <<'PY'
from pathlib import Path
import sys

from aios_cargo_bins import has_expected_aios_binaries

raise SystemExit(0 if has_expected_aios_binaries(Path(sys.argv[1])) else 1)
PY
}

detect_host_target() {
  if [[ -n "${AIOS_HOST_TARGET_OVERRIDE:-}" ]]; then
    printf '%s\n' "$AIOS_HOST_TARGET_OVERRIDE"
    return 0
  fi
  PYTHONPATH="$ROOT_DIR/scripts" "$PYTHON_BIN" - "$ROOT_DIR" <<'PY'
from pathlib import Path
import sys

from aios_cargo_bins import detect_host_target

print(detect_host_target(Path(sys.argv[1]) / "aios") or "")
PY
}

resolve_linux_binary_strategy() {
  local docker_available=false
  local buildx_available=false
  local cached_container_ready=false

  if [[ "$LINUX_BINARY_STRATEGY" != "auto" ]]; then
    printf '%s\n' "$LINUX_BINARY_STRATEGY"
    return 0
  fi

  if [[ -n "$BIN_DIR" ]]; then
    printf 'host-bin-dir\n'
    return 0
  fi

  local host_target
  host_target="$(detect_host_target)"
  if cached_container_bin_dir_ready "$CACHED_CONTAINER_BIN_DIR"; then
    cached_container_ready=true
  fi
  if [[ "$host_target" == "x86_64-unknown-linux-gnu" ]]; then
    if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
      docker_available=true
    fi
    if command -v docker >/dev/null 2>&1 && docker buildx version >/dev/null 2>&1; then
      buildx_available=true
    fi
    if [[ "$docker_available" == "true" && "$buildx_available" == "true" ]]; then
      printf 'container-native-linux-x86_64\n'
    elif [[ "$cached_container_ready" == "true" ]]; then
      printf 'container-cached-bin-dir\n'
    else
      printf 'host-bin-dir\n'
    fi
  else
    printf 'container-native-linux-x86_64\n'
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preflight)
      PRECHECK=true
      shift
      ;;
    --overlay-dir)
      OVERLAY_DIR="$2"
      shift 2
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ "$OVERLAY_DIR" != /* ]]; then
  OVERLAY_DIR="$(cd "$(pwd -P)" && printf '%s/%s\n' "$(pwd -P)" "$OVERLAY_DIR")"
fi

CACHED_CONTAINER_BIN_DIR="$(default_container_native_bin_dir)"
resolved_linux_binary_strategy="$(resolve_linux_binary_strategy)"

if [[ "$PRECHECK" == "true" ]]; then
  explicit_bin_dir=false
  if [[ -n "$BIN_DIR" ]]; then
    explicit_bin_dir=true
  fi
  cached_container_ready=false
  if [[ -n "$CACHED_CONTAINER_BIN_DIR" ]] && cached_container_bin_dir_ready "$CACHED_CONTAINER_BIN_DIR"; then
    cached_container_ready=true
  fi
  PYTHONPATH="$ROOT_DIR/scripts" "$PYTHON_BIN" -     "$OVERLAY_DIR"     "$resolved_linux_binary_strategy"     "$explicit_bin_dir"     "$(detect_host_target)"     "$CACHED_CONTAINER_BIN_DIR"     "$cached_container_ready" <<'PY'
import json
import sys


def as_bool(value: str) -> bool:
    return value == "true"


payload = {
    "status": "ready",
    "overlay_dir": sys.argv[1],
    "linux_binary_strategy": sys.argv[2],
    "has_explicit_bin_dir": as_bool(sys.argv[3]),
    "host_target": sys.argv[4],
    "cached_container_bin_dir": sys.argv[5],
    "cached_container_bin_dir_ready": as_bool(sys.argv[6]),
}
print(json.dumps(payload, ensure_ascii=False))
PY
  exit 0
fi

case "$resolved_linux_binary_strategy" in
  host-bin-dir)
    if [[ -z "$BIN_DIR" ]]; then
      BIN_DIR="$(default_aios_bin_dir)"
    fi
    if (( ${#FORWARD_ARGS[@]} > 0 )); then
      exec "$PYTHON_BIN" "$ROOT_DIR/scripts/build-aios-delivery.py" \
        --bin-dir "$BIN_DIR" \
        --build-missing \
        --no-archive \
        --sync-overlay "$OVERLAY_DIR" \
        "${FORWARD_ARGS[@]}"
    fi
    exec "$PYTHON_BIN" "$ROOT_DIR/scripts/build-aios-delivery.py" \
      --bin-dir "$BIN_DIR" \
      --build-missing \
      --no-archive \
      --sync-overlay "$OVERLAY_DIR"
    ;;
  container-cached-bin-dir)
    BIN_DIR="$CACHED_CONTAINER_BIN_DIR"
    if (( ${#FORWARD_ARGS[@]} > 0 )); then
      exec "$PYTHON_BIN" "$ROOT_DIR/scripts/build-aios-delivery.py" \
        --bin-dir "$BIN_DIR" \
        --no-archive \
        --sync-overlay "$OVERLAY_DIR" \
        "${FORWARD_ARGS[@]}"
    fi
    exec "$PYTHON_BIN" "$ROOT_DIR/scripts/build-aios-delivery.py" \
      --bin-dir "$BIN_DIR" \
      --no-archive \
      --sync-overlay "$OVERLAY_DIR"
    ;;
  container-native-linux-x86_64)
    if (( ${#FORWARD_ARGS[@]} > 0 )); then
      exec bash "$ROOT_DIR/scripts/build-aios-delivery-container.sh" \
        --no-archive \
        --sync-overlay "$OVERLAY_DIR" \
        "${FORWARD_ARGS[@]}"
    fi
    exec bash "$ROOT_DIR/scripts/build-aios-delivery-container.sh" \
      --no-archive \
      --sync-overlay "$OVERLAY_DIR"
    ;;
  *)
    printf 'unsupported AIOS_IMAGE_LINUX_BINARY_STRATEGY: %s\n' "$resolved_linux_binary_strategy" >&2
    exit 64
    ;;
esac
