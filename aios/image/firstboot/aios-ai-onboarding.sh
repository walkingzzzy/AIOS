#!/usr/bin/env bash
set -euo pipefail

ROOT_PREFIX="${AIOS_FIRSTBOOT_ROOT:-}"

root_path() {
  local path="$1"
  if [[ -n "$ROOT_PREFIX" ]]; then
    printf '%s%s' "$ROOT_PREFIX" "$path"
  else
    printf '%s' "$path"
  fi
}

resolve_rooted_path() {
  local path="$1"
  if [[ -z "$path" ]]; then
    printf ''
  elif [[ "$path" == /* ]]; then
    root_path "$path"
  else
    printf '%s' "$path"
  fi
}

json_escape() {
  printf '%s' "$1" | sed -e 's#\\#\\\\#g' -e 's#"#\\"#g'
}

is_truthy() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

json_bool() {
  if is_truthy "$1"; then
    printf 'true\n'
  else
    printf 'false\n'
  fi
}

upsert_env_value() {
  local path="$1"
  local key="$2"
  local value="${3:-}"
  local tmp_path

  tmp_path="$(mktemp)"
  mkdir -p "$(dirname "$path")"
  if [[ -f "$path" ]]; then
    grep -Ev "^${key}=" "$path" >"$tmp_path" || true
  fi
  if [[ -n "$value" ]]; then
    printf '%s=%s\n' "$key" "$value" >>"$tmp_path"
  fi
  cat "$tmp_path" >"$path"
  rm -f "$tmp_path"
}

count_local_models() {
  local model_dir="$1"
  if [[ ! -d "$model_dir" ]]; then
    printf '0\n'
    return 0
  fi
  find "$model_dir" -type f \( -name '*.gguf' -o -name '*.safetensors' -o -name '*.bin' \) | wc -l | tr -d ' '
}

first_local_model() {
  local model_dir="$1"
  if [[ ! -d "$model_dir" ]]; then
    printf ''
    return 0
  fi
  find "$model_dir" -type f \( -name '*.gguf' -o -name '*.safetensors' -o -name '*.bin' \) | sort | head -n 1
}

AI_ENABLED="${AIOS_FIRSTBOOT_AI_ENABLED:-1}"
AI_MODE="${AIOS_FIRSTBOOT_AI_MODE:-hybrid}"
AI_PRIVACY_PROFILE="${AIOS_FIRSTBOOT_AI_PRIVACY_PROFILE:-balanced}"
AI_AUTO_PULL_DEFAULT_MODEL="${AIOS_FIRSTBOOT_AI_AUTO_PULL_DEFAULT_MODEL:-0}"
AI_AUTO_MODEL_SOURCE="${AIOS_FIRSTBOOT_AI_AUTO_MODEL_SOURCE:-}"
AI_AUTO_MODEL_ID="${AIOS_FIRSTBOOT_AI_AUTO_MODEL_ID:-}"
AI_ENDPOINT_BASE_URL="${AIOS_FIRSTBOOT_AI_ENDPOINT_BASE_URL:-}"
AI_ENDPOINT_MODEL="${AIOS_FIRSTBOOT_AI_ENDPOINT_MODEL:-}"
AI_LOCAL_OLLAMA_ENDPOINT_BASE_URL="${AIOS_FIRSTBOOT_AI_LOCAL_OLLAMA_ENDPOINT_BASE_URL:-http://127.0.0.1:11434/v1}"
INSTALL_ID="${AIOS_FIRSTBOOT_INSTALL_ID:-}"
INSTALL_SOURCE="${AIOS_FIRSTBOOT_INSTALL_SOURCE:-}"
INSTALLER_VERSION="${AIOS_FIRSTBOOT_INSTALLER_VERSION:-}"
MODEL_DIR_RAW="${AIOS_MODEL_DIR:-/var/lib/aios/models}"
MODEL_DIR="$(resolve_rooted_path "$MODEL_DIR_RAW")"
RUNTIME_PLATFORM_ENV_RAW="${AIOS_RUNTIME_PLATFORM_ENV:-/etc/aios/runtime/platform.env}"
RUNTIME_PLATFORM_ENV="$(resolve_rooted_path "$RUNTIME_PLATFORM_ENV_RAW")"

ONBOARDING_DIR="$(root_path /var/lib/aios/onboarding)"
STAMP_FILE="$ONBOARDING_DIR/ai-onboarding-initialized"
REPORT_FILE="$ONBOARDING_DIR/ai-onboarding-report.json"
RUNTIME_STATE_DIR="$(root_path /var/lib/aios/runtime)"
READINESS_FILE="$RUNTIME_STATE_DIR/ai-readiness.json"

mkdir -p "$ONBOARDING_DIR" "$RUNTIME_STATE_DIR"

if [[ -f "$STAMP_FILE" ]]; then
  exit 0
fi

LOCAL_MODEL_COUNT=0
FIRST_LOCAL_MODEL=""
LOCAL_MODEL_PRESENT=false
ENDPOINT_CONFIGURED=false
AUTO_PULL_ENABLED=false
AUTO_PULL_ATTEMPTED=false
AUTO_PULL_STATUS="not-requested"
AUTO_PULL_MESSAGE=""
AUTO_PULL_ENDPOINT_ADOPTED=false
AUTO_PULL_COMMAND=""

refresh_local_model_state() {
  LOCAL_MODEL_COUNT="$(count_local_models "$MODEL_DIR")"
  FIRST_LOCAL_MODEL="$(first_local_model "$MODEL_DIR")"
  LOCAL_MODEL_PRESENT=false
  if [[ "${LOCAL_MODEL_COUNT:-0}" =~ ^[0-9]+$ ]] && (( LOCAL_MODEL_COUNT > 0 )); then
    LOCAL_MODEL_PRESENT=true
  fi
}

refresh_endpoint_state() {
  ENDPOINT_CONFIGURED=false
  if [[ -n "$AI_ENDPOINT_BASE_URL" && -n "$AI_ENDPOINT_MODEL" ]]; then
    ENDPOINT_CONFIGURED=true
  fi
}

persist_runtime_endpoint() {
  mkdir -p "$(dirname "$RUNTIME_PLATFORM_ENV")"
  upsert_env_value "$RUNTIME_PLATFORM_ENV" "AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL" "$AI_ENDPOINT_BASE_URL"
  upsert_env_value "$RUNTIME_PLATFORM_ENV" "AIOS_RUNTIMED_AI_ENDPOINT_MODEL" "$AI_ENDPOINT_MODEL"
}

run_auto_pull_default_model() {
  AUTO_PULL_ATTEMPTED=true
  if [[ -z "$AI_AUTO_MODEL_SOURCE" || -z "$AI_AUTO_MODEL_ID" ]]; then
    AUTO_PULL_STATUS="skipped-missing-config"
    AUTO_PULL_MESSAGE="auto model source or model id is missing"
    return 0
  fi

  case "$AI_AUTO_MODEL_SOURCE" in
    ollama-library)
      AUTO_PULL_COMMAND="ollama pull $AI_AUTO_MODEL_ID"
      if ! command -v ollama >/dev/null 2>&1; then
        AUTO_PULL_STATUS="provider-unavailable"
        AUTO_PULL_MESSAGE="ollama CLI is not installed"
        return 0
      fi
      if ollama pull "$AI_AUTO_MODEL_ID" >/dev/null 2>&1; then
        AUTO_PULL_STATUS="pulled"
        AUTO_PULL_MESSAGE="ollama pull completed"
        if [[ -z "$AI_ENDPOINT_BASE_URL" ]]; then
          AI_ENDPOINT_BASE_URL="$AI_LOCAL_OLLAMA_ENDPOINT_BASE_URL"
          AUTO_PULL_ENDPOINT_ADOPTED=true
        fi
        if [[ -z "$AI_ENDPOINT_MODEL" ]]; then
          AI_ENDPOINT_MODEL="$AI_AUTO_MODEL_ID"
          AUTO_PULL_ENDPOINT_ADOPTED=true
        fi
        refresh_endpoint_state
        if [[ "$ENDPOINT_CONFIGURED" == true ]]; then
          persist_runtime_endpoint
        fi
        return 0
      fi
      AUTO_PULL_STATUS="pull-failed"
      AUTO_PULL_MESSAGE="ollama pull returned a non-zero exit status"
      return 0
      ;;
    *)
      AUTO_PULL_STATUS="unsupported-source"
      AUTO_PULL_MESSAGE="unsupported auto model source: $AI_AUTO_MODEL_SOURCE"
      return 0
      ;;
  esac
}

refresh_local_model_state
refresh_endpoint_state
if is_truthy "$AI_AUTO_PULL_DEFAULT_MODEL"; then
  AUTO_PULL_ENABLED=true
fi
if [[ "$AUTO_PULL_ENABLED" == true && "$LOCAL_MODEL_PRESENT" != true ]]; then
  run_auto_pull_default_model
  refresh_local_model_state
  refresh_endpoint_state
fi

READINESS_STATE="not-ready"
READINESS_REASON="AI configuration is incomplete"
NEXT_ACTION="complete-ai-onboarding"

if ! is_truthy "$AI_ENABLED"; then
  READINESS_STATE="disabled"
  READINESS_REASON="AI was disabled during installation"
  NEXT_ACTION="enable-ai"
elif [[ "$LOCAL_MODEL_PRESENT" == true && "$ENDPOINT_CONFIGURED" == true && "$AI_MODE" == "hybrid" ]]; then
  READINESS_STATE="hybrid-ready"
  READINESS_REASON="local model and remote endpoint are both ready"
  NEXT_ACTION="none"
elif [[ "$LOCAL_MODEL_PRESENT" == true ]]; then
  READINESS_STATE="local-ready"
  READINESS_REASON="local model inventory is ready"
  NEXT_ACTION="none"
elif [[ "$ENDPOINT_CONFIGURED" == true ]]; then
  if [[ "$AI_MODE" == "hybrid" ]]; then
    READINESS_STATE="hybrid-remote-only"
    READINESS_REASON="remote endpoint is ready while local model inventory is empty"
  else
    READINESS_STATE="cloud-ready"
    READINESS_REASON="remote endpoint is configured"
  fi
  NEXT_ACTION="none"
elif [[ "$AUTO_PULL_ENABLED" == true ]]; then
  READINESS_STATE="setup-pending"
  if [[ "$AUTO_PULL_ATTEMPTED" == true && "$AUTO_PULL_STATUS" != "pulled" ]]; then
    READINESS_REASON="default model pull could not complete: ${AUTO_PULL_MESSAGE:-unknown failure}"
    NEXT_ACTION="resolve-auto-pull"
  else
    READINESS_REASON="default model pull is pending firstboot completion"
    NEXT_ACTION="auto-pull-default-model"
  fi
elif [[ "$AI_MODE" == "cloud" ]]; then
  READINESS_STATE="not-ready"
  READINESS_REASON="cloud mode was selected but remote endpoint is not configured"
  NEXT_ACTION="configure-remote-endpoint"
elif [[ "$AI_MODE" == "later" ]]; then
  READINESS_STATE="setup-pending"
  READINESS_REASON="AI configuration was deferred to later setup"
  NEXT_ACTION="open-ai-center"
else
  READINESS_STATE="not-ready"
  READINESS_REASON="no local model is registered and no remote endpoint is configured"
  NEXT_ACTION="import-local-model"
fi

cat >"$REPORT_FILE" <<EOF
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "install_id": "$(json_escape "$INSTALL_ID")",
  "install_source": "$(json_escape "$INSTALL_SOURCE")",
  "installer_version": "$(json_escape "$INSTALLER_VERSION")",
  "ai_enabled": $(json_bool "$AI_ENABLED"),
  "ai_mode": "$(json_escape "$AI_MODE")",
  "privacy_profile": "$(json_escape "$AI_PRIVACY_PROFILE")",
  "auto_pull_default_model": $(json_bool "$AI_AUTO_PULL_DEFAULT_MODEL"),
  "auto_pull_attempted": ${AUTO_PULL_ATTEMPTED},
  "auto_pull_status": "$(json_escape "$AUTO_PULL_STATUS")",
  "auto_pull_message": "$(json_escape "$AUTO_PULL_MESSAGE")",
  "auto_pull_endpoint_adopted": ${AUTO_PULL_ENDPOINT_ADOPTED},
  "auto_pull_command": "$(json_escape "$AUTO_PULL_COMMAND")",
  "auto_model_source": "$(json_escape "$AI_AUTO_MODEL_SOURCE")",
  "auto_model_id": "$(json_escape "$AI_AUTO_MODEL_ID")",
  "endpoint_base_url": "$(json_escape "$AI_ENDPOINT_BASE_URL")",
  "endpoint_model": "$(json_escape "$AI_ENDPOINT_MODEL")",
  "endpoint_configured": ${ENDPOINT_CONFIGURED},
  "local_model_dir": "$(json_escape "$MODEL_DIR_RAW")",
  "local_model_count": ${LOCAL_MODEL_COUNT},
  "first_local_model": "$(json_escape "$FIRST_LOCAL_MODEL")",
  "readiness_state": "$(json_escape "$READINESS_STATE")",
  "readiness_reason": "$(json_escape "$READINESS_REASON")",
  "next_action": "$(json_escape "$NEXT_ACTION")"
}
EOF

cat >"$READINESS_FILE" <<EOF
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "state": "$(json_escape "$READINESS_STATE")",
  "reason": "$(json_escape "$READINESS_REASON")",
  "next_action": "$(json_escape "$NEXT_ACTION")",
  "ai_enabled": $(json_bool "$AI_ENABLED"),
  "ai_mode": "$(json_escape "$AI_MODE")",
  "local_model_count": ${LOCAL_MODEL_COUNT},
  "endpoint_configured": ${ENDPOINT_CONFIGURED},
  "auto_pull_status": "$(json_escape "$AUTO_PULL_STATUS")",
  "auto_pull_message": "$(json_escape "$AUTO_PULL_MESSAGE")",
  "report_path": "/var/lib/aios/onboarding/ai-onboarding-report.json"
}
EOF

touch "$STAMP_FILE"

echo "AIOS_AI_ONBOARDING state=$READINESS_STATE ai_enabled=$AI_ENABLED ai_mode=$AI_MODE local_model_count=$LOCAL_MODEL_COUNT endpoint_configured=$ENDPOINT_CONFIGURED report=$REPORT_FILE readiness=$READINESS_FILE"
