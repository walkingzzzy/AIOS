#!/bin/sh
set -eu

json_escape() {
    printf '%s' "${1:-}" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g'
}

append_note() {
    escaped="$(json_escape "${1:-}")"
    if [ -n "${notes_json}" ]; then
        notes_json="${notes_json},"
    fi
    notes_json="${notes_json}\"${escaped}\""
}

platform_probe_id="${AIOS_UPDATED_PLATFORM_PROBE_ID:-generic-x86_64-uefi}"
deployment_status="${AIOS_UPDATED_DEPLOYMENT_STATUS:-idle}"
boot_backend="${AIOS_UPDATED_BOOT_BACKEND:-unknown}"
current_slot="${AIOS_UPDATED_CURRENT_SLOT:-unknown}"
last_good_slot="${AIOS_UPDATED_LAST_GOOD_SLOT:-unknown}"
staged_slot="${AIOS_UPDATED_STAGED_SLOT:-}"
boot_success="${AIOS_UPDATED_BOOT_SUCCESS:-false}"
sysupdate_dir="${AIOS_UPDATED_SYSUPDATE_DIR:-}"
boot_state_path="${AIOS_UPDATED_BOOT_STATE_PATH:-}"
recovery_dir="${AIOS_UPDATED_RECOVERY_DIR:-}"
diagnostics_dir="${AIOS_UPDATED_DIAGNOSTICS_DIR:-}"
recovery_point_count="${AIOS_UPDATED_RECOVERY_POINT_COUNT:-0}"
diagnostic_bundle_count="${AIOS_UPDATED_DIAGNOSTIC_BUNDLE_COUNT:-0}"

notes_json=""
summary="platform delivery backend ready"
overall_status="healthy"

if [ -n "${sysupdate_dir}" ] && [ ! -d "${sysupdate_dir}" ]; then
    overall_status="failed"
    summary="sysupdate definitions directory missing"
elif [ -n "${recovery_dir}" ] && [ ! -d "${recovery_dir}" ]; then
    overall_status="failed"
    summary="recovery state directory missing"
elif [ -n "${diagnostics_dir}" ] && [ ! -d "${diagnostics_dir}" ]; then
    overall_status="warning"
    summary="diagnostics directory missing"
fi

case "${deployment_status}" in
    missing-sysupdate-dir|apply-failed|rollback-failed|boot-switch-failed)
        overall_status="failed"
        summary="deployment state requires operator recovery"
        ;;
    apply-triggered|staged-update)
        if [ "${overall_status}" != "failed" ]; then
            overall_status="warning"
            summary="update staged and awaiting reboot verification"
        fi
        ;;
    rollback-triggered|rollback-staged)
        if [ "${overall_status}" != "failed" ]; then
            overall_status="warning"
            summary="rollback staged and awaiting reboot verification"
        fi
        ;;
    waiting-for-artifacts)
        if [ "${overall_status}" != "failed" ]; then
            overall_status="warning"
            summary="update artifacts are incomplete"
        fi
        ;;
    up-to-date)
        if [ "${overall_status}" = "healthy" ]; then
            summary="system image is up to date"
        fi
        ;;
    ready-to-stage|idle)
        ;;
    *)
        if [ "${overall_status}" = "healthy" ]; then
            overall_status="warning"
            summary="deployment state requires review"
        fi
        ;;
esac

if [ "${boot_success}" != "true" ] && [ -n "${staged_slot}" ] && [ "${overall_status}" = "healthy" ]; then
    overall_status="warning"
    summary="boot verification still pending"
fi

if [ -n "${boot_state_path}" ] && [ ! -f "${boot_state_path}" ] && [ "${overall_status}" = "healthy" ] \
    && [ "${current_slot}" = "unknown" ] && [ "${last_good_slot}" = "unknown" ]; then
    overall_status="warning"
    summary="boot state file has not been written yet"
fi

append_note "platform_probe_id=${platform_probe_id}"
append_note "deployment_status=${deployment_status}"
append_note "boot_backend=${boot_backend}"
append_note "current_slot=${current_slot}"
append_note "last_good_slot=${last_good_slot}"
if [ -n "${staged_slot}" ]; then
    append_note "staged_slot=${staged_slot}"
fi
append_note "boot_success=${boot_success}"
append_note "recovery_points=${recovery_point_count}"
append_note "diagnostic_bundles=${diagnostic_bundle_count}"
append_note "sysupdate_dir_exists=$(if [ -n "${sysupdate_dir}" ] && [ -d "${sysupdate_dir}" ]; then printf true; else printf false; fi)"
append_note "boot_state_exists=$(if [ -n "${boot_state_path}" ] && [ -f "${boot_state_path}" ]; then printf true; else printf false; fi)"
append_note "recovery_dir_exists=$(if [ -n "${recovery_dir}" ] && [ -d "${recovery_dir}" ]; then printf true; else printf false; fi)"
append_note "diagnostics_dir_exists=$(if [ -n "${diagnostics_dir}" ] && [ -d "${diagnostics_dir}" ]; then printf true; else printf false; fi)"

printf '{\n'
printf '  "overall_status": "%s",\n' "$(json_escape "${overall_status}")"
printf '  "summary": "%s",\n' "$(json_escape "${summary}")"
printf '  "notes": [%s]\n' "${notes_json}"
printf '}\n'
