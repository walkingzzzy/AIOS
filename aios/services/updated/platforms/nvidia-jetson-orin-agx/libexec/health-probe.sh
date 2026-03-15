#!/bin/sh
set -eu

export AIOS_UPDATED_PLATFORM_PROBE_ID="${AIOS_UPDATED_PLATFORM_PROBE_ID:-nvidia-jetson-orin-agx}"
exec /usr/libexec/aios-platform/generic-x86_64-uefi/health-probe.sh "$@"
