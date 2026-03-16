#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend="${AIOS_RUNTIME_WORKER_BACKEND_ID:-}"
mode="${AIOS_RUNTIME_WORKER_MODE:-unix}"
vendor_python="${AIOS_JETSON_VENDOR_WORKER_PYTHON:-${AIOS_JETSON_HELPER_PYTHON:-python3}}"
vendor_worker="${AIOS_JETSON_VENDOR_WORKER_PATH:-$script_dir/vendor_accel_worker.py}"

case "$backend" in
  local-gpu)
    command="${AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND:-}"
    ;;
  local-npu)
    command="${AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND:-}"
    ;;
  *)
    printf 'unsupported Jetson managed worker backend: %s\n' "$backend" >&2
    exit 64
    ;;
esac

if [[ -n "$command" ]]; then
  exec /bin/sh -lc "$command"
fi

if [[ "${AIOS_JETSON_ALLOW_REFERENCE_WORKER:-0}" == "1" ]]; then
  python_bin="${AIOS_JETSON_REFERENCE_WORKER_PYTHON:-python3}"
  reference_worker="${AIOS_JETSON_REFERENCE_WORKER_PATH:-$script_dir/reference_accel_worker.py}"
  case "$mode" in
    unix)
      exec "$python_bin" "$reference_worker" unix --backend "$backend" --socket "${AIOS_RUNTIME_WORKER_SOCKET_PATH:?}"
      ;;
    stdio)
      exec "$python_bin" "$reference_worker" stdio --backend "$backend"
      ;;
    *)
      printf 'unsupported Jetson managed worker mode: %s\n' "$mode" >&2
      exit 64
      ;;
  esac
fi

if [[ -f "$vendor_worker" ]]; then
  export AIOS_JETSON_VENDOR_EVIDENCE_DIR="${AIOS_JETSON_VENDOR_EVIDENCE_DIR:-${AIOS_RUNTIMED_STATE_DIR:-/var/lib/aios/runtimed}/jetson-vendor-evidence}"
  export AIOS_JETSON_VENDOR_ENGINE_ROOT="${AIOS_JETSON_VENDOR_ENGINE_ROOT:-/var/lib/aios/runtime/vendor-engines}"
  case "$mode" in
    unix)
      exec "$vendor_python" "$vendor_worker" unix --backend "$backend" --socket "${AIOS_RUNTIME_WORKER_SOCKET_PATH:?}"
      ;;
    stdio)
      exec "$vendor_python" "$vendor_worker" stdio --backend "$backend"
      ;;
    *)
      printf 'unsupported Jetson managed worker mode: %s\n' "$mode" >&2
      exit 64
      ;;
  esac
fi

printf '%s\n' \
  "Jetson managed worker bridge has no vendor runtime helper for ${backend}. " \
  "Set AIOS_JETSON_LOCAL_GPU_WORKER_COMMAND / AIOS_JETSON_LOCAL_NPU_WORKER_COMMAND, " \
  "ship vendor_accel_worker.py, or enable AIOS_JETSON_ALLOW_REFERENCE_WORKER=1 for the reference bridge." >&2
exit 69
