#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${AIOS_BOOT_EVIDENCE_OUTPUT_DIR:-/var/lib/aios/hardware-evidence/boots}"
BOOT_ID_PATH="${AIOS_BOOT_EVIDENCE_BOOT_ID_PATH:-/proc/sys/kernel/random/boot_id}"
CMDLINE_PATH="${AIOS_BOOT_EVIDENCE_CMDLINE_PATH:-/proc/cmdline}"
DEPLOYMENT_STATE_PATH="${AIOS_BOOT_EVIDENCE_DEPLOYMENT_STATE_PATH:-/var/lib/aios/updated/deployment-state.json}"
BOOT_STATE_PATH="${AIOS_BOOT_EVIDENCE_BOOT_STATE_PATH:-/var/lib/aios/updated/boot-control.json}"
BOOTCTL_BIN="${AIOS_BOOT_EVIDENCE_BOOTCTL_BIN:-${AIOS_UPDATED_BOOTCTL_BIN:-bootctl}}"
FIRMWARECTL_BIN="${AIOS_BOOT_EVIDENCE_FIRMWARECTL_BIN:-${AIOS_UPDATED_FIRMWARECTL_BIN:-firmwarectl}}"
SYSUPDATE_BIN="${AIOS_BOOT_EVIDENCE_SYSUPDATE_BIN:-${AIOS_UPDATED_SYSUPDATE_BIN:-systemd-sysupdate}}"
SYSUPDATE_DEFINITIONS_DIR="${AIOS_BOOT_EVIDENCE_SYSUPDATE_DEFINITIONS_DIR:-${AIOS_UPDATED_SYSUPDATE_DEFINITIONS_DIR:-/etc/systemd/sysupdate.d}}"
BOOT_ENTRY_STATE_DIR="${AIOS_BOOT_EVIDENCE_BOOT_ENTRY_STATE_DIR:-${AIOS_UPDATED_BOOT_ENTRY_STATE_DIR:-/var/lib/aios/updated/boot}}"

json_string() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

json_file_or_null() {
  local path="$1"
  if [[ -f "$path" ]]; then
    python3 - "$path" <<'PYJSON'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    value = json.loads(path.read_text())
except Exception:
    print('null')
else:
    print(json.dumps(value, ensure_ascii=False))
PYJSON
  else
    printf 'null\n'
  fi
}

command_output_json() {
  local label="$1"
  shift
  local stdout_path="/tmp/aios-boot-evidence.$$.out"
  local stderr_path="/tmp/aios-boot-evidence.$$.err"
  if "$@" >"$stdout_path" 2>"$stderr_path"; then
    python3 - "$label" "$stdout_path" "$stderr_path" <<'PYJSON'
import json
import sys
from pathlib import Path
label, out_path, err_path = sys.argv[1:4]
out = Path(out_path).read_text().strip()
err = Path(err_path).read_text().strip()
print(json.dumps({"label": label, "success": True, "stdout": out, "stderr": err}, ensure_ascii=False))
PYJSON
  else
    python3 - "$label" "$stdout_path" "$stderr_path" <<'PYJSON'
import json
import sys
from pathlib import Path
label, out_path, err_path = sys.argv[1:4]
out = Path(out_path).read_text().strip() if Path(out_path).exists() else ""
err = Path(err_path).read_text().strip() if Path(err_path).exists() else ""
print(json.dumps({"label": label, "success": False, "stdout": out, "stderr": err}, ensure_ascii=False))
PYJSON
  fi
  rm -f "$stdout_path" "$stderr_path"
}

boot_id="unknown"
if [[ -f "$BOOT_ID_PATH" ]]; then
  boot_id="$(tr -d ' \r\n' < "$BOOT_ID_PATH")"
fi
kernel_cmdline=""
if [[ -f "$CMDLINE_PATH" ]]; then
  kernel_cmdline="$(tr -d '\n' < "$CMDLINE_PATH")"
fi

mkdir -p "$OUTPUT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
outfile="$OUTPUT_DIR/${timestamp}-${boot_id}.json"

cat > "$outfile" <<EOF
{
  "captured_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "boot_id": $(printf '%s' "$boot_id" | json_string),
  "kernel_cmdline": $(printf '%s' "$kernel_cmdline" | json_string),
  "deployment_state": $(json_file_or_null "$DEPLOYMENT_STATE_PATH"),
  "boot_state": $(json_file_or_null "$BOOT_STATE_PATH"),
  "bootctl_status": $(command_output_json bootctl "$BOOTCTL_BIN" status),
  "firmwarectl_status": $(command_output_json firmwarectl "$FIRMWARECTL_BIN" status --state-dir "$BOOT_ENTRY_STATE_DIR"),
  "sysupdate_list": $(command_output_json systemd-sysupdate "$SYSUPDATE_BIN" --definitions "$SYSUPDATE_DEFINITIONS_DIR" list)
}
EOF

ln -sfn "$(basename "$outfile")" "$OUTPUT_DIR/latest.json"
printf 'AIOS_BOOT_EVIDENCE_REPORT path=%s boot_id=%s\n' "$outfile" "$boot_id"
