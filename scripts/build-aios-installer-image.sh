#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_IMAGE_DIR="$ROOT_DIR/aios/image"
BASE_OUTPUT_DIR="${AIOS_BASE_IMAGE_OUTPUT_DIR:-$BASE_IMAGE_DIR/mkosi.output}"
STAGING_DIR="${AIOS_INSTALLER_IMAGE_STAGING_DIR:-$ROOT_DIR/.cache/aios-installer-image-src}"
OUTPUT_DIR="${AIOS_INSTALLER_IMAGE_OUTPUT_DIR:-$BASE_IMAGE_DIR/installer.output}"
CMDLINE_FILE="${AIOS_INSTALLER_KERNEL_CMDLINE_FILE:-$BASE_IMAGE_DIR/installer/kernel-command-line.txt}"
EXTRA_OVERLAY_DIR="${AIOS_IMAGE_EXTRA_OVERLAY_DIR:-}"
DERIVE_FROM_BASE="${AIOS_IMAGE_DERIVE_VARIANTS_FROM_BASE:-1}"
BASE_STEM="${AIOS_BASE_IMAGE_OUTPUT_STEM:-aios-qemu-x86_64}"
INSTALLER_STEM="${AIOS_INSTALLER_IMAGE_OUTPUT_STEM:-aios-qemu-x86_64-installer}"

installer_artifacts_ready() {
  [[ -f "$OUTPUT_DIR/$INSTALLER_STEM.raw" ]] || return 1
  [[ -f "$OUTPUT_DIR/$INSTALLER_STEM.efi" ]] || return 1
  [[ -f "$OUTPUT_DIR/$INSTALLER_STEM.initrd" ]] || return 1
  [[ -f "$OUTPUT_DIR/$INSTALLER_STEM.vmlinuz" ]] || return 1
}

base_artifacts_ready() {
  [[ -f "$BASE_OUTPUT_DIR/$BASE_STEM.raw" ]] || return 1
  [[ -f "$BASE_OUTPUT_DIR/$BASE_STEM.efi" ]] || return 1
  [[ -f "$BASE_OUTPUT_DIR/$BASE_STEM.initrd" ]] || return 1
  [[ -f "$BASE_OUTPUT_DIR/$BASE_STEM.vmlinuz" ]] || return 1
}

write_manifest() {
  python3 - "$OUTPUT_DIR" <<'PYMANIFEST'
from pathlib import Path
import json
import sys

output_dir = Path(sys.argv[1])
images = sorted(str(path.name) for path in output_dir.glob('*.raw'))
manifest = {
    'profile': 'qemu-x86_64-installer',
    'output_dir': str(output_dir),
    'images': images,
    'default_target': 'aios-installer.target',
    'kernel_command_line_asset': 'aios/image/installer/kernel-command-line.txt',
    'source_disk': '/dev/vdb',
    'target_disk': '/dev/vdc',
    'optional_recovery_disk': '/dev/vdd',
    'install_mode': 'image-clone',
}
(output_dir / 'installer-image-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
PYMANIFEST
}

derive_from_base_if_possible() {
  if [[ -n "$EXTRA_OVERLAY_DIR" || "$DERIVE_FROM_BASE" != "1" ]]; then
    return 1
  fi

  mkdir -p "$OUTPUT_DIR"

  if installer_artifacts_ready; then
    printf 'reusing existing installer image artifacts in %s\n' "$OUTPUT_DIR" >&2
    write_manifest
    exit 0
  fi

  if ! base_artifacts_ready; then
    return 1
  fi

  printf 'deriving installer image artifacts from base output %s\n' "$BASE_OUTPUT_DIR" >&2
  cp -f "$BASE_OUTPUT_DIR/$BASE_STEM.raw" "$OUTPUT_DIR/$INSTALLER_STEM.raw"
  cp -f "$BASE_OUTPUT_DIR/$BASE_STEM.efi" "$OUTPUT_DIR/$INSTALLER_STEM.efi"
  cp -f "$BASE_OUTPUT_DIR/$BASE_STEM.initrd" "$OUTPUT_DIR/$INSTALLER_STEM.initrd"
  cp -f "$BASE_OUTPUT_DIR/$BASE_STEM.vmlinuz" "$OUTPUT_DIR/$INSTALLER_STEM.vmlinuz"
  if [[ -f "$BASE_OUTPUT_DIR/initrd.cpio.zst" ]]; then
    cp -f "$BASE_OUTPUT_DIR/initrd.cpio.zst" "$OUTPUT_DIR/initrd.cpio.zst"
  fi
  write_manifest
  exit 0
}

print_preflight() {
  local variant_ready=false
  local base_ready=false
  local base_preflight_status="unknown"
  if installer_artifacts_ready; then
    variant_ready=true
  fi
  if base_artifacts_ready; then
    base_ready=true
  fi
  base_preflight_status="$(
    AIOS_IMAGE_OUTPUT_DIR_OVERRIDE="$BASE_OUTPUT_DIR" \
    bash "$ROOT_DIR/scripts/build-aios-image.sh" --preflight | \
    python3 -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("status","unknown"))'
  )"
  python3 - "$OUTPUT_DIR" "$BASE_OUTPUT_DIR" "$variant_ready" "$base_ready" "$base_preflight_status" "$DERIVE_FROM_BASE" "$EXTRA_OVERLAY_DIR" <<'PY'
from pathlib import Path
import json
import sys

output_dir = Path(sys.argv[1])
base_output_dir = Path(sys.argv[2])
variant_ready = sys.argv[3] == "true"
base_ready = sys.argv[4] == "true"
base_preflight_status = sys.argv[5]
derive_from_base = sys.argv[6]
extra_overlay_dir = sys.argv[7]

strategy = "mkosi-build"
status = "ready" if base_preflight_status == "ready" else "blocked"
if variant_ready:
    strategy = "reuse-existing"
    status = "ready"
elif derive_from_base == "1" and not extra_overlay_dir and base_ready:
    strategy = "derive-from-base"
    status = "ready"

print(json.dumps({
    "status": status,
    "strategy": strategy,
    "output_dir": str(output_dir),
    "base_output_dir": str(base_output_dir),
    "variant_output_ready": variant_ready,
    "base_output_ready": base_ready,
    "derive_from_base": derive_from_base,
    "extra_overlay_dir": extra_overlay_dir,
    "kernel_command_line_asset": "aios/image/installer/kernel-command-line.txt",
}, ensure_ascii=False))
PY
}

if [[ "${1:-}" == "--preflight" ]]; then
  print_preflight
  exit 0
fi

if derive_from_base_if_possible "$@"; then
  exit 0
fi

python3 "$ROOT_DIR/scripts/prepare-aios-image-staging.py" \
  "$BASE_IMAGE_DIR" \
  "$STAGING_DIR" \
  --preserve mkosi.cache \
  --preserve mkosi.builddir \
  --preserve mkosi.tools \
  --exclude-copy mkosi.output \
  --exclude-copy recovery.output \
  --exclude-copy installer.output
mkdir -p "$OUTPUT_DIR"

bash "$ROOT_DIR/scripts/sync-aios-image-overlay.sh" \
  --overlay-dir "$STAGING_DIR/mkosi.extra"

if [[ -n "$EXTRA_OVERLAY_DIR" ]]; then
  mkdir -p "$STAGING_DIR/mkosi.extra"
  cp -a "$EXTRA_OVERLAY_DIR"/. "$STAGING_DIR/mkosi.extra"/
fi

python3 - "$STAGING_DIR/mkosi.conf" "$CMDLINE_FILE" <<'PYCONF'
from pathlib import Path
import sys

mkosi_conf = Path(sys.argv[1])
cmdline_file = Path(sys.argv[2])
text = mkosi_conf.read_text()
if 'Output=aios-qemu-x86_64\n' not in text:
    raise SystemExit('expected base Output=aios-qemu-x86_64 in mkosi.conf')
text = text.replace('Output=aios-qemu-x86_64\n', 'Output=aios-qemu-x86_64-installer\n', 1)
lines = []
replaced = False
for line in text.splitlines():
    if line.strip() == 'systemd.unit=multi-user.target':
        if not replaced:
            for cmd in cmdline_file.read_text().splitlines():
                if cmd.strip():
                    lines.append(f'  {cmd.strip()}')
            replaced = True
        continue
    lines.append(line)
if not replaced:
    raise SystemExit('failed to replace base kernel target with installer cmdline')
mkosi_conf.write_text('\n'.join(lines) + '\n')
PYCONF

AIOS_IMAGE_SOURCE_DIR="$STAGING_DIR" \
AIOS_IMAGE_OUTPUT_DIR_OVERRIDE="$OUTPUT_DIR" \
AIOS_SKIP_OVERLAY_SYNC=1 \
bash "$ROOT_DIR/scripts/build-aios-image.sh" "$@"

write_manifest
