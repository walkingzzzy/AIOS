#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_DIR="$ROOT_DIR/aios/image"
OUTPUT_DIR="${AIOS_IMAGE_OUTPUT_DIR:-$IMAGE_DIR/mkosi.output}"
HOST_OS="$(uname -s)"
HOST_ARCH="$(uname -m)"
DEFAULT_ACCEL="tcg"
DEFAULT_CPU="max"
if [[ "$HOST_OS" == "Darwin" && "$HOST_ARCH" == "arm64" ]]; then
  DEFAULT_ACCEL="tcg"
  DEFAULT_CPU="max"
elif [[ "$HOST_OS" == "Darwin" ]]; then
  DEFAULT_ACCEL="hvf:tcg"
  DEFAULT_CPU="host"
elif [[ "$HOST_OS" == "Linux" ]]; then
  DEFAULT_ACCEL="kvm:tcg"
  DEFAULT_CPU="host"
fi
ACCEL="${AIOS_QEMU_ACCEL:-$DEFAULT_ACCEL}"
CPU_MODEL="${AIOS_QEMU_CPU:-$DEFAULT_CPU}"
DISPLAY_MODE="${AIOS_QEMU_DISPLAY:-none}"
MONITOR_MODE="${AIOS_QEMU_MONITOR:-none}"
SERIAL_MODE="${AIOS_QEMU_SERIAL:-stdio}"
MEMORY_MB="${AIOS_QEMU_MEMORY_MB:-4096}"
SMP="${AIOS_QEMU_SMP:-4}"
SSH_PORT="${AIOS_QEMU_SSH_PORT:-2222}"
OVMF_CODE="${AIOS_QEMU_OVMF_CODE:-}"
OVMF_VARS="${AIOS_QEMU_OVMF_VARS:-}"
KERNEL_CMDLINE_EXTRA="${AIOS_QEMU_KERNEL_CMDLINE_EXTRA:-}"

if [[ -z "$OVMF_CODE" ]]; then
  for candidate in \
    /opt/homebrew/Cellar/qemu/*/share/qemu/edk2-x86_64-code.fd \
    /usr/local/Cellar/qemu/*/share/qemu/edk2-x86_64-code.fd \
    /usr/share/OVMF/OVMF_CODE.fd \
    /usr/share/OVMF/OVMF_CODE_4M.fd \
    /usr/share/edk2/ovmf/OVMF_CODE.fd \
    /usr/share/edk2/ovmf/OVMF_CODE_4M.fd \
    /usr/share/qemu/OVMF.fd; do
    if [[ -f "$candidate" ]]; then
      OVMF_CODE="$candidate"
      break
    fi
  done
fi

IMAGE_PATH="${AIOS_QEMU_IMAGE_PATH:-}"
if [[ -z "$IMAGE_PATH" && -d "$OUTPUT_DIR" ]]; then
  IMAGE_PATH="$(find "$OUTPUT_DIR" -maxdepth 2 \( -name '*.raw' -o -name '*.qcow2' -o -name '*.img' \) | sort | head -n 1)"
fi

if [[ "${1:-}" == "--preflight" ]]; then
  QEMU_AVAILABLE=false
  if command -v qemu-system-x86_64 >/dev/null 2>&1; then
    QEMU_AVAILABLE=true
  fi
  IMAGE_FOUND=false
  if [[ -n "$IMAGE_PATH" ]]; then
    IMAGE_FOUND=true
  fi
  STATUS="ready"
  if [[ "$QEMU_AVAILABLE" != "true" || "$IMAGE_FOUND" != "true" ]]; then
    STATUS="blocked"
  fi
  printf '{"status":"%s","qemu_available":%s,"image_found":%s,"default_accel":"%s","cpu_model":"%s","display":"%s","serial":"%s","ovmf_code_found":%s,"output_dir":"%s","image_path":"%s"}
'     "$STATUS"     "$QEMU_AVAILABLE"     "$IMAGE_FOUND"     "$ACCEL"     "$CPU_MODEL"     "$DISPLAY_MODE"     "$SERIAL_MODE"     "$([[ -n "$OVMF_CODE" ]] && echo true || echo false)"     "$OUTPUT_DIR"     "$IMAGE_PATH"
  exit 0
fi

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  echo "qemu-system-x86_64 is not installed; install QEMU first." >&2
  exit 1
fi

if [[ -z "$IMAGE_PATH" ]]; then
  echo "No disk image found in $OUTPUT_DIR. Run scripts/build-aios-image.sh first." >&2
  exit 1
fi

IMAGE_FORMAT="raw"
if [[ "$IMAGE_PATH" == *.qcow2 ]]; then
  IMAGE_FORMAT="qcow2"
fi

QEMU_ARGS=(
  -machine "q35,accel=$ACCEL"
  -cpu "$CPU_MODEL"
  -m "$MEMORY_MB"
  -smp "$SMP"
  -display "$DISPLAY_MODE"
  -monitor "$MONITOR_MODE"
  -serial "$SERIAL_MODE"
  -drive "if=virtio,format=$IMAGE_FORMAT,file=$IMAGE_PATH"
  -nic "user,model=virtio-net-pci,hostfwd=tcp::${SSH_PORT}-:22"
)

if [[ -n "$OVMF_CODE" ]]; then
  QEMU_ARGS+=( -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE" )
fi

if [[ -n "$OVMF_VARS" ]]; then
  QEMU_ARGS+=( -drive "if=pflash,format=raw,file=$OVMF_VARS" )
fi

if [[ -n "$KERNEL_CMDLINE_EXTRA" ]]; then
  escaped_extra="${KERNEL_CMDLINE_EXTRA//,/,,}"
  QEMU_ARGS+=(
    -smbios "type=11,value=io.systemd.stub.kernel-cmdline-extra=$escaped_extra"
    -smbios "type=11,value=io.systemd.boot.kernel-cmdline-extra=$escaped_extra"
  )
fi

exec qemu-system-x86_64 "${QEMU_ARGS[@]}"
