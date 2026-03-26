#!/usr/bin/env bash
set -euo pipefail

export AIOS_WORKER_PRODUCT_MODE="${AIOS_WORKER_PRODUCT_MODE:-${AIOS_RUNTIMED_PRODUCT_MODE:-1}}"

exec /usr/bin/env python3 /usr/libexec/aios/runtime/workers/local_cpu_worker.py
