#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${AIOS_DELIVERY_DOCKERFILE:-$ROOT_DIR/docker/aios-delivery.Dockerfile}"
DOCKER_PLATFORM="${AIOS_DELIVERY_DOCKER_PLATFORM:-linux/amd64}"
BUILDER_TAG="${AIOS_DELIVERY_BUILDER_TAG:-aios-delivery-builder:local}"
OUTPUT_DIR="${AIOS_DELIVERY_OUTPUT_DIR:-$ROOT_DIR/out/aios-system-delivery}"
BUILD_RETRIES="${AIOS_DELIVERY_DOCKER_BUILD_RETRIES:-3}"
CARGO_BIN="${AIOS_DELIVERY_CONTAINER_CARGO_BIN:-/usr/local/cargo/bin/cargo}"
CONTAINER_TOOLCHAIN="${AIOS_DELIVERY_CONTAINER_TOOLCHAIN:-1.85.0}"
REUSE_LOCAL_BUILDER="${AIOS_DELIVERY_REUSE_LOCAL_BUILDER:-1}"
WORKSPACE_MOUNT="/workspace"
CONTAINER_TARGET_DIR="${AIOS_DELIVERY_CONTAINER_TARGET_DIR:-$WORKSPACE_MOUNT/out/aios-delivery-container-target}"
PRECHECK=false
NO_ARCHIVE=false
SYNC_OVERLAY=""

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

PACKAGES=(
  aios-agentd
  aios-sessiond
  aios-policyd
  aios-runtimed
  aios-deviced
  aios-updated
  aios-device-metadata-provider
  aios-runtime-local-inference-provider
  aios-system-intent-provider
  aios-system-files-provider
)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preflight)
      PRECHECK=true
      shift
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --no-archive)
      NO_ARCHIVE=true
      shift
      ;;
    --sync-overlay)
      SYNC_OVERLAY="$2"
      shift 2
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      exit 64
      ;;
  esac
done

docker_available=false
buildx_available=false
if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
  docker_available=true
fi
if command -v docker >/dev/null 2>&1 && docker buildx version >/dev/null 2>&1; then
  buildx_available=true
fi

if [[ "$PRECHECK" == "true" ]]; then
  dockerfile_exists=false
  if [[ -f "$DOCKERFILE" ]]; then
    dockerfile_exists=true
  fi
  preflight_status=blocked
  if [[ "$docker_available" == "true" && "$buildx_available" == "true" ]]; then
    preflight_status=ready
  fi
  "$PYTHON_BIN" -     "$preflight_status"     "$docker_available"     "$buildx_available"     "$DOCKERFILE"     "$dockerfile_exists"     "$DOCKER_PLATFORM"     "$BUILDER_TAG"     "$OUTPUT_DIR"     "$BUILD_RETRIES"     "$CARGO_BIN"     "$CONTAINER_TOOLCHAIN"     "$REUSE_LOCAL_BUILDER"     "$CONTAINER_TARGET_DIR" <<'PY'
import json
import sys


def as_bool(value: str) -> bool:
    return value == "true"


payload = {
    "status": sys.argv[1],
    "docker_available": as_bool(sys.argv[2]),
    "buildx_available": as_bool(sys.argv[3]),
    "dockerfile": sys.argv[4],
    "dockerfile_exists": as_bool(sys.argv[5]),
    "docker_platform": sys.argv[6],
    "builder_tag": sys.argv[7],
    "output_dir": sys.argv[8],
    "build_retries": sys.argv[9],
    "cargo_bin": sys.argv[10],
    "container_toolchain": sys.argv[11],
    "reuse_local_builder": sys.argv[12],
    "container_target_dir": sys.argv[13],
    "linux_binary_strategy": "container-native-linux-x86_64",
}
print(json.dumps(payload, ensure_ascii=False))
PY
  exit 0
fi

if [[ "$docker_available" != "true" ]]; then
  printf 'docker is required for container-native delivery builds\n' >&2
  exit 1
fi
if [[ "$buildx_available" != "true" ]]; then
  printf 'docker buildx is required for container-native delivery builds\n' >&2
  exit 1
fi
if [[ ! -f "$DOCKERFILE" ]]; then
  printf 'missing Dockerfile: %s\n' "$DOCKERFILE" >&2
  exit 1
fi

build_args=()
for package in "${PACKAGES[@]}"; do
  build_args+=("-p" "$package")
done

container_output_dir="$OUTPUT_DIR"
case "$OUTPUT_DIR" in
  "$ROOT_DIR")
    container_output_dir="$WORKSPACE_MOUNT"
    ;;
  "$ROOT_DIR"/*)
    container_output_dir="$WORKSPACE_MOUNT/${OUTPUT_DIR#"$ROOT_DIR"/}"
    ;;
esac

container_sync_overlay=""
case "$SYNC_OVERLAY" in
  "")
    ;;
  "$ROOT_DIR")
    container_sync_overlay="$WORKSPACE_MOUNT"
    ;;
  "$ROOT_DIR"/*)
    container_sync_overlay="$WORKSPACE_MOUNT/${SYNC_OVERLAY#"$ROOT_DIR"/}"
    ;;
  *)
    printf 'sync overlay path must be inside workspace: %s\n' "$SYNC_OVERLAY" >&2
    exit 64
    ;;
esac

container_bin_dir="$CONTAINER_TARGET_DIR/debug"
delivery_cmd="python3 scripts/build-aios-delivery.py --bin-dir $(printf '%q' "$container_bin_dir") --output-dir $(printf '%q' "$container_output_dir")"
if [[ "$NO_ARCHIVE" == "true" ]]; then
  delivery_cmd+=" --no-archive"
fi
if [[ -n "$container_sync_overlay" ]]; then
  delivery_cmd+=" --sync-overlay $(printf '%q' "$container_sync_overlay")"
fi

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

if [[ "$REUSE_LOCAL_BUILDER" == "1" ]] && docker image inspect "$BUILDER_TAG" >/dev/null 2>&1; then
  printf 'using cached builder image: %s\n' "$BUILDER_TAG" >&2
else
  retry "$BUILD_RETRIES" docker buildx build --load --platform "$DOCKER_PLATFORM" -f "$DOCKERFILE" -t "$BUILDER_TAG" "$ROOT_DIR"
fi
docker run --rm --platform "$DOCKER_PLATFORM" -v "$ROOT_DIR:$WORKSPACE_MOUNT" -w "$WORKSPACE_MOUNT" "$BUILDER_TAG" bash -lc "
  set -euo pipefail
  export PATH=\"$(dirname "$CARGO_BIN"):\$PATH\"
  export RUSTUP_TOOLCHAIN=\"$(printf '%q' "$CONTAINER_TOOLCHAIN")\"
  export CARGO_TARGET_DIR=\"$(printf '%q' "$CONTAINER_TARGET_DIR")\"
  cd /workspace/aios
  \"$CARGO_BIN\" build --locked ${build_args[*]}
  cd /workspace
  $delivery_cmd
"
