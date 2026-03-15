#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_IMAGE_DIR="$ROOT_DIR/aios/image"
IMAGE_DIR="${AIOS_IMAGE_SOURCE_DIR:-$DEFAULT_IMAGE_DIR}"
HOST_OUTPUT_DIR="${AIOS_IMAGE_OUTPUT_DIR_OVERRIDE:-$IMAGE_DIR/mkosi.output}"
MKOSI_SOURCE_DIR="${AIOS_MKOSI_SOURCE_DIR:-$ROOT_DIR/.cache/mkosi-src}"
MKOSI_CONTAINER_IMAGE="${AIOS_MKOSI_CONTAINER_IMAGE:-fedora:42}"
MKOSI_CONTAINER_PLATFORM="${AIOS_MKOSI_CONTAINER_PLATFORM:-}"
MKOSI_BUILDER_TAG="${AIOS_IMAGE_BUILDER_TAG:-aios-mkosi-builder:local}"
FORCE_DOCKER="${AIOS_IMAGE_BUILD_USE_DOCKER:-}"
SKIP_OVERLAY_SYNC="${AIOS_SKIP_OVERLAY_SYNC:-}"
LINUX_BINARY_STRATEGY="${AIOS_IMAGE_LINUX_BINARY_STRATEGY:-auto}"
REUSE_LOCAL_BUILDER="${AIOS_IMAGE_REUSE_LOCAL_BUILDER:-1}"
BUILDER_RETRIES="${AIOS_IMAGE_BUILDER_RETRIES:-3}"
REUSE_EXISTING_OUTPUT="${AIOS_IMAGE_REUSE_EXISTING_OUTPUT:-1}"

host_mkosi_available=false
docker_available=false
buildx_available=false
git_available=false
containerized_build_available=false
build_mode="blocked"
linux_binary_strategy="$LINUX_BINARY_STRATEGY"
docker_platform_args=()
cached_container_bin_dir_available=false
cached_container_bin_dir=""

detect_output_stem() {
  local mkosi_conf="${IMAGE_DIR}/mkosi.conf"
  if [[ ! -f "$mkosi_conf" ]]; then
    return 0
  fi
  awk -F= '
    /^\[Output\]/ { in_output=1; next }
    /^\[/ { in_output=0 }
    in_output && $1 == "Output" {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)
      print $2
      exit
    }
  ' "$mkosi_conf"
}

output_artifacts_ready() {
  local output_dir="$1"
  local output_stem="$2"
  [[ -n "$output_stem" ]] || return 1
  [[ -f "$output_dir/$output_stem.raw" ]] || return 1
  [[ -f "$output_dir/$output_stem.efi" ]] || return 1
  [[ -f "$output_dir/$output_stem.initrd" ]] || return 1
  [[ -f "$output_dir/$output_stem.vmlinuz" ]] || return 1
}

detect_image_architecture() {
  local mkosi_conf="${IMAGE_DIR}/mkosi.conf"
  if [[ ! -f "$mkosi_conf" ]]; then
    return 0
  fi
  awk -F= '
    /^\[Distribution\]/ { in_distribution=1; next }
    /^\[/ { in_distribution=0 }
    in_distribution && $1 == "Architecture" {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)
      print $2
      exit
    }
  ' "$mkosi_conf"
}

default_container_platform() {
  case "$(detect_image_architecture)" in
    x86-64)
      printf 'linux/amd64\n'
      ;;
    arm64|aarch64)
      printf 'linux/arm64\n'
      ;;
    *)
      printf '%s\n' "$MKOSI_CONTAINER_PLATFORM"
      ;;
  esac
}

requested_builder_arch() {
  local platform="$1"
  case "$platform" in
    */amd64)
      printf 'amd64\n'
      ;;
    */arm64)
      printf 'arm64\n'
      ;;
    *)
      return 0
      ;;
  esac
}

retry() {
  local attempts="$1"
  shift
  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if (( attempt >= attempts )); then
      return 1
    fi
    printf 'retrying command (%s/%s): %s\n' "$((attempt + 1))" "$attempts" "$*" >&2
    sleep "$attempt"
    attempt=$((attempt + 1))
  done
}

detect_host_target() {
  if [[ -n "${AIOS_HOST_TARGET_OVERRIDE:-}" ]]; then
    printf '%s\n' "$AIOS_HOST_TARGET_OVERRIDE"
    return 0
  fi
  PYTHONPATH="$ROOT_DIR/scripts" python3 - "$ROOT_DIR" <<'PY'
from pathlib import Path
import sys

from aios_cargo_bins import detect_host_target

print(detect_host_target(Path(sys.argv[1]) / "aios") or "")
PY
}

default_container_native_bin_dir() {
  PYTHONPATH="$ROOT_DIR/scripts" python3 - "$ROOT_DIR" <<'PY'
from pathlib import Path
import sys

from aios_cargo_bins import default_container_native_bin_dir

print(default_container_native_bin_dir(Path(sys.argv[1])))
PY
}

cached_container_bin_dir_ready() {
  PYTHONPATH="$ROOT_DIR/scripts" python3 - "$1" <<'PY'
from pathlib import Path
import sys

from aios_cargo_bins import has_expected_aios_binaries

raise SystemExit(0 if has_expected_aios_binaries(Path(sys.argv[1])) else 1)
PY
}

if [[ -z "$MKOSI_CONTAINER_PLATFORM" ]]; then
  MKOSI_CONTAINER_PLATFORM="$(default_container_platform)"
fi

if [[ -n "$MKOSI_CONTAINER_PLATFORM" ]]; then
  docker_platform_args=(--platform "$MKOSI_CONTAINER_PLATFORM")
fi

if command -v mkosi >/dev/null 2>&1; then
  host_mkosi_available=true
fi

if command -v docker >/dev/null 2>&1 && docker ps >/dev/null 2>&1; then
  docker_available=true
fi

if command -v docker >/dev/null 2>&1 && docker buildx version >/dev/null 2>&1; then
  buildx_available=true
fi

if command -v git >/dev/null 2>&1; then
  git_available=true
fi

cached_container_bin_dir="$(default_container_native_bin_dir)"
if cached_container_bin_dir_ready "$cached_container_bin_dir"; then
  cached_container_bin_dir_available=true
fi

if [[ "$linux_binary_strategy" == "auto" ]]; then
  if [[ -n "${AIOS_BIN_DIR:-}" ]]; then
    linux_binary_strategy="host-bin-dir"
  else
    host_target="$(detect_host_target)"
    if [[ "$host_target" == "x86_64-unknown-linux-gnu" ]]; then
      if [[ "$docker_available" == "true" && "$buildx_available" == "true" ]]; then
        linux_binary_strategy="container-native-linux-x86_64"
      elif [[ "$cached_container_bin_dir_available" == "true" ]]; then
        linux_binary_strategy="container-cached-bin-dir"
      else
        linux_binary_strategy="host-bin-dir"
      fi
    else
      linux_binary_strategy="container-native-linux-x86_64"
    fi
  fi
fi

if [[ "$host_mkosi_available" == "true" ]]; then
  build_mode="host"
elif [[ "$docker_available" == "true" && "$git_available" == "true" ]]; then
  containerized_build_available=true
  build_mode="docker"
fi

sync_overlay_if_needed() {
  if [[ "$SKIP_OVERLAY_SYNC" == "1" || "$SKIP_OVERLAY_SYNC" == "true" ]]; then
    return 0
  fi
  AIOS_IMAGE_LINUX_BINARY_STRATEGY="$linux_binary_strategy" \
  bash "$ROOT_DIR/scripts/sync-aios-image-overlay.sh"
}

print_preflight() {
  local status="ready"
  local output_stem=""
  local existing_output_ready=false
  output_stem="$(detect_output_stem)"
  if output_artifacts_ready "$HOST_OUTPUT_DIR" "$output_stem"; then
    existing_output_ready=true
  fi
  if [[ "$build_mode" == "blocked" && "$existing_output_ready" != "true" ]]; then
    status="blocked"
  fi
  printf '{"status":"%s","build_mode":"%s","mkosi_available":%s,"docker_available":%s,"buildx_available":%s,"git_available":%s,"containerized_build_available":%s,"mkosi_source_dir":"%s","image_dir":"%s","host_output_dir":"%s","mkosi_conf":"%s","overlay_sync":"%s","container_platform":"%s","linux_binary_strategy":"%s","builder_tag":"%s","reuse_local_builder":"%s","reuse_existing_output":"%s","output_stem":"%s","existing_output_ready":%s,"host_target":"%s","cached_container_bin_dir":"%s","cached_container_bin_dir_ready":%s}\n' \
    "$status" \
    "$build_mode" \
    "$host_mkosi_available" \
    "$docker_available" \
    "$buildx_available" \
    "$git_available" \
    "$containerized_build_available" \
    "$MKOSI_SOURCE_DIR" \
    "$IMAGE_DIR" \
    "$HOST_OUTPUT_DIR" \
    "$IMAGE_DIR/mkosi.conf" \
    "$ROOT_DIR/scripts/sync-aios-image-overlay.sh" \
    "$MKOSI_CONTAINER_PLATFORM" \
    "$linux_binary_strategy" \
    "$MKOSI_BUILDER_TAG" \
    "$REUSE_LOCAL_BUILDER" \
    "$REUSE_EXISTING_OUTPUT" \
    "$output_stem" \
    "$existing_output_ready" \
    "$(detect_host_target)" \
    "$cached_container_bin_dir" \
    "$cached_container_bin_dir_available"
}

if [[ "${1:-}" == "--preflight" ]]; then
  print_preflight
  exit 0
fi

reuse_existing_output_if_available() {
  local output_stem=""
  if [[ "$REUSE_EXISTING_OUTPUT" != "1" || $# -ne 0 ]]; then
    return 1
  fi
  output_stem="$(detect_output_stem)"
  if ! output_artifacts_ready "$HOST_OUTPUT_DIR" "$output_stem"; then
    return 1
  fi
  printf 'reusing existing mkosi output: %s (%s)\n' "$HOST_OUTPUT_DIR" "$output_stem" >&2
  return 0
}

ensure_mkosi_source() {
  if [[ -d "$MKOSI_SOURCE_DIR/.git" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "$MKOSI_SOURCE_DIR")"
  git clone --depth 1 https://github.com/systemd/mkosi.git "$MKOSI_SOURCE_DIR"
}

ensure_builder_image() {
  local requested_arch=""
  requested_arch="$(requested_builder_arch "$MKOSI_CONTAINER_PLATFORM" || true)"

  if [[ "$REUSE_LOCAL_BUILDER" == "1" ]] && docker image inspect "$MKOSI_BUILDER_TAG" >/dev/null 2>&1; then
    local existing_arch=""
    existing_arch="$(docker image inspect "$MKOSI_BUILDER_TAG" --format '{{.Architecture}}' 2>/dev/null || true)"
    if [[ -z "$requested_arch" || "$existing_arch" == "$requested_arch" ]]; then
      printf 'using cached mkosi builder image: %s\n' "$MKOSI_BUILDER_TAG" >&2
      return 0
    fi
    printf 'cached mkosi builder image architecture mismatch: have %s, need %s; rebuilding %s\n' \
      "$existing_arch" \
      "$requested_arch" \
      "$MKOSI_BUILDER_TAG" >&2
  fi

  local tmpdir
  tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/aios-mkosi-builder.XXXXXX")"
  cat > "$tmpdir/Dockerfile" <<EOF_DOCKERFILE
FROM $MKOSI_CONTAINER_IMAGE
RUN dnf install -y --setopt=install_weak_deps=False --setopt=timeout=30 --setopt=retries=10 \
      python3 git dnf systemd distribution-gpg-keys \
      dosfstools e2fsprogs xfsprogs squashfs-tools erofs-utils \
      btrfs-progs qemu-img xz zstd cpio tar util-linux findutils coreutils \
  && dnf clean all
EOF_DOCKERFILE

  local -a build_cmd=(docker build -t "$MKOSI_BUILDER_TAG")
  if [[ ${#docker_platform_args[@]} -gt 0 ]]; then
    build_cmd+=("${docker_platform_args[@]}")
  fi
  build_cmd+=("$tmpdir")
  retry "$BUILDER_RETRIES" "${build_cmd[@]}"
  rm -rf "$tmpdir"
}

run_host_build() {
  sync_overlay_if_needed
  mkdir -p "$HOST_OUTPUT_DIR"
  exec mkosi -C "$IMAGE_DIR" build "$@"
}

run_docker_build() {
  ensure_mkosi_source
  sync_overlay_if_needed
  ensure_builder_image
  mkdir -p "$HOST_OUTPUT_DIR"
  mkdir -p "$IMAGE_DIR"
  docker_cmd=(docker run --rm --privileged)
  if [[ ${#docker_platform_args[@]} -gt 0 ]]; then
    docker_cmd+=("${docker_platform_args[@]}")
  fi
  docker_cmd+=(
    -v "$ROOT_DIR:/workspace"
    -v "$MKOSI_SOURCE_DIR:/opt/mkosi"
    -v "$IMAGE_DIR:/src-image"
    -v "$HOST_OUTPUT_DIR:/host-output"
    -w /workspace
    "$MKOSI_BUILDER_TAG"
    bash -lc '
      set -euo pipefail
      image_root=/var/tmp/aios-image-build
      image_dir="$image_root/image"
      output_dir="$image_dir/mkosi.output"

      rm -rf "$image_root"
      mkdir -p "$image_dir" /host-output

      python3 - "$image_dir" <<"PY_COPY"
from pathlib import Path
import shutil
import sys

src = Path("/src-image")
dst = Path(sys.argv[1])
skip = {"mkosi.output", "recovery.output", "installer.output"}
for child in src.iterdir():
    if child.name in skip:
        continue
    target = dst / child.name
    if child.is_symlink():
        target.symlink_to(child.readlink())
    elif child.is_dir():
        shutil.copytree(child, target, symlinks=True)
    else:
        shutil.copy2(child, target, follow_symlinks=False)
PY_COPY

      export MKOSI_INTERPRETER=python3
      /opt/mkosi/bin/mkosi -C "$image_dir" build "$@"

      if [[ ! -d "$output_dir" ]]; then
        echo "mkosi completed without producing $output_dir" >&2
        exit 1
      fi

      rm -rf /host-output/*
      cp -R "$output_dir"/. /host-output/

      for cached_path in mkosi.cache mkosi.builddir mkosi.tools; do
        if [[ -e "$image_dir/$cached_path" ]]; then
          rm -rf "/src-image/$cached_path"
          cp -a "$image_dir/$cached_path" "/src-image/$cached_path"
        fi
      done
    ' bash "$@")
  exec "${docker_cmd[@]}"
}

if [[ "$FORCE_DOCKER" == "1" || "$FORCE_DOCKER" == "true" ]]; then
  if [[ "$containerized_build_available" != "true" ]]; then
    echo "containerized mkosi build is not available; require docker and git." >&2
    exit 1
  fi
  if reuse_existing_output_if_available "$@"; then
    exit 0
  fi
  run_docker_build "$@"
fi

if reuse_existing_output_if_available "$@"; then
  exit 0
fi

case "$build_mode" in
  host)
    run_host_build "$@"
    ;;
  docker)
    run_docker_build "$@"
    ;;
  *)
    echo "mkosi is not available on the host, and no docker+git fallback was detected." >&2
    exit 1
    ;;
esac
