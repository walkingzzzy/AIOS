#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate AIOS hardware boot evidence across reboots")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--profile", type=Path, help="Optional Tier 1 hardware profile YAML/JSON")
    parser.add_argument("--min-boots", type=int, default=None)
    parser.add_argument("--expect-slot-transition", help="Expected current_slot transition, for example a:b")
    parser.add_argument("--expect-last-good-slot", help="Expected final last_good_slot value")
    parser.add_argument("--require-boot-success", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--require-deployment-state", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--require-boot-state", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--require-bootctl-status", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--require-firmware-status", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--require-sysupdate-listing", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-md", type=Path, help="Optional Markdown report path")
    parser.add_argument("--evidence-index-out", type=Path, help="Optional structured evidence index JSON path")
    return parser.parse_args()


def load_profile(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    text = path.read_text()
    if not text.strip():
        return {}
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return json.loads(text)


def resolve_flag(
    cli_value: bool | None,
    profile_expectations: dict[str, Any],
    key: str,
    default: bool,
) -> bool:
    if cli_value is not None:
        return cli_value
    value = profile_expectations.get(key)
    if value is None:
        return default
    return bool(value)


def resolve_value(
    cli_value: Any,
    profile_expectations: dict[str, Any],
    key: str,
    default: Any,
) -> Any:
    if cli_value is not None:
        return cli_value
    value = profile_expectations.get(key)
    if value is None:
        return default
    return value


def resolved_expectations(args: argparse.Namespace, profile: dict[str, Any]) -> dict[str, Any]:
    profile_expectations = profile.get("boot_evidence_expectations") or {}
    return {
        "min_boots": int(resolve_value(args.min_boots, profile_expectations, "min_boots", 2)),
        "expect_slot_transition": resolve_value(
            args.expect_slot_transition, profile_expectations, "expect_slot_transition", None
        ),
        "expect_last_good_slot": resolve_value(
            args.expect_last_good_slot, profile_expectations, "expect_last_good_slot", None
        ),
        "require_boot_success": resolve_flag(
            args.require_boot_success, profile_expectations, "require_boot_success", True
        ),
        "require_deployment_state": resolve_flag(
            args.require_deployment_state, profile_expectations, "require_deployment_state", False
        ),
        "require_boot_state": resolve_flag(
            args.require_boot_state, profile_expectations, "require_boot_state", False
        ),
        "require_bootctl_status": resolve_flag(
            args.require_bootctl_status, profile_expectations, "require_bootctl_status", False
        ),
        "require_firmware_status": resolve_flag(
            args.require_firmware_status, profile_expectations, "require_firmware_status", False
        ),
        "require_sysupdate_listing": resolve_flag(
            args.require_sysupdate_listing, profile_expectations, "require_sysupdate_listing", False
        ),
    }


def load_records(input_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.json")):
        if path.name == "latest.json":
            continue
        records.append({"path": str(path), "data": json.loads(path.read_text())})
    return records


def slot_value(record: dict[str, Any], key: str) -> str | None:
    boot_state = record.get("boot_state") or {}
    if isinstance(boot_state, dict):
        value = boot_state.get(key)
        if isinstance(value, str):
            return value
    return None


def bool_success(record: dict[str, Any], key: str) -> bool:
    payload = record.get(key) or {}
    return bool(isinstance(payload, dict) and payload.get("success") is True)


def present(value: Any) -> bool:
    return value is not None


def failing_record_names(
    records: list[dict[str, Any]],
    predicate,
) -> list[str]:
    failures: list[str] = []
    for record in records:
        if not predicate(record["data"]):
            failures.append(Path(record["path"]).name)
    return failures


def make_check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def make_record_summary(record: dict[str, Any]) -> dict[str, Any]:
    data = record["data"]
    return {
        "path": record["path"],
        "captured_at": data.get("captured_at"),
        "boot_id": data.get("boot_id"),
        "current_slot": slot_value(data, "current_slot"),
        "last_good_slot": slot_value(data, "last_good_slot"),
        "boot_success": bool((data.get("boot_state") or {}).get("boot_success") is True),
        "deployment_state_present": present(data.get("deployment_state")),
        "boot_state_present": present(data.get("boot_state")),
        "bootctl_success": bool_success(data, "bootctl_status"),
        "firmwarectl_success": bool_success(data, "firmwarectl_status"),
        "sysupdate_success": bool_success(data, "sysupdate_list"),
    }


def check_all_records(
    records: list[dict[str, Any]],
    name: str,
    predicate,
    success_detail: str,
    failure_label: str,
) -> dict[str, Any]:
    failures = failing_record_names(records, predicate)
    if not failures:
        return make_check(name, True, success_detail)
    return make_check(
        name,
        False,
        f"{failure_label}: {', '.join(failures)}",
    )


def evaluate(records: list[dict[str, Any]], expectations: dict[str, Any]) -> list[dict[str, Any]]:
    unique_boot_ids = sorted(
        {
            record["data"].get("boot_id")
            for record in records
            if record["data"].get("boot_id")
        }
    )
    checks: list[dict[str, Any]] = [
        make_check(
            "minimum_boots",
            len(unique_boot_ids) >= expectations["min_boots"],
            f"observed {len(unique_boot_ids)} unique boot ids",
        )
    ]

    if expectations["expect_slot_transition"] and records:
        expected_from, expected_to = str(expectations["expect_slot_transition"]).split(":", 1)
        first_slot = slot_value(records[0]["data"], "current_slot")
        last_slot = slot_value(records[-1]["data"], "current_slot")
        checks.append(
            make_check(
                "slot_transition",
                first_slot == expected_from and last_slot == expected_to,
                f"first={first_slot} last={last_slot} expected={expected_from}->{expected_to}",
            )
        )

    if expectations["expect_last_good_slot"] and records:
        final_last_good = slot_value(records[-1]["data"], "last_good_slot")
        checks.append(
            make_check(
                "last_good_slot",
                final_last_good == expectations["expect_last_good_slot"],
                f"final={final_last_good} expected={expectations['expect_last_good_slot']}",
            )
        )

    if expectations["require_boot_success"]:
        final_boot_state = records[-1]["data"].get("boot_state") if records else None
        checks.append(
            make_check(
                "boot_success",
                bool(isinstance(final_boot_state, dict) and final_boot_state.get("boot_success") is True),
                "final boot_success must be true",
            )
        )

    if expectations["require_deployment_state"]:
        checks.append(
            check_all_records(
                records,
                "deployment_state_present",
                lambda record: present(record.get("deployment_state")),
                "deployment_state present for every record",
                "deployment_state missing",
            )
        )

    if expectations["require_boot_state"]:
        checks.append(
            check_all_records(
                records,
                "boot_state_present",
                lambda record: present(record.get("boot_state")),
                "boot_state present for every record",
                "boot_state missing",
            )
        )

    if expectations["require_bootctl_status"]:
        checks.append(
            check_all_records(
                records,
                "bootctl_status",
                lambda record: bool_success(record, "bootctl_status"),
                "bootctl succeeded for every record",
                "bootctl did not report success",
            )
        )

    if expectations["require_firmware_status"]:
        checks.append(
            check_all_records(
                records,
                "firmwarectl_status",
                lambda record: bool_success(record, "firmwarectl_status"),
                "firmwarectl succeeded for every record",
                "firmwarectl did not report success",
            )
        )

    if expectations["require_sysupdate_listing"]:
        checks.append(
            check_all_records(
                records,
                "sysupdate_listing",
                lambda record: bool_success(record, "sysupdate_list"),
                "systemd-sysupdate listing succeeded for every record",
                "systemd-sysupdate listing did not report success",
            )
        )

    return checks


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Hardware Boot Evidence Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Input dir: `{report['input_dir']}`",
        f"- Profile: `{report['profile'] or 'none'}`",
        f"- Record count: `{report['record_count']}`",
        f"- Unique boot IDs: `{len(report['unique_boot_ids'])}`",
        f"- Passed: `{str(report['passed']).lower()}`",
        "",
        "## Resolved Expectations",
        "",
    ]
    for key, value in report["resolved_expectations"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Checks", ""])
    for check in report["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- `{status}` `{check['name']}`: {check['detail']}")

    lines.extend(["", "## Records", ""])
    for record in report["record_summaries"]:
        lines.append(
            "- "
            + ", ".join(
                [
                    f"`{Path(record['path']).name}`",
                    f"boot_id=`{record['boot_id']}`",
                    f"current_slot=`{record['current_slot']}`",
                    f"last_good_slot=`{record['last_good_slot']}`",
                    f"boot_success=`{str(record['boot_success']).lower()}`",
                    f"bootctl_success=`{str(record['bootctl_success']).lower()}`",
                    f"firmwarectl_success=`{str(record['firmwarectl_success']).lower()}`",
                    f"sysupdate_success=`{str(record['sysupdate_success']).lower()}`",
                ]
            )
        )

    return "\n".join(lines) + "\n"


def build_evidence_index(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": report["generated_at"],
        "input_dir": report["input_dir"],
        "profile": report["profile"],
        "validation_status": "passed" if report["passed"] else "failed",
        "record_count": report["record_count"],
        "unique_boot_ids": report["unique_boot_ids"],
        "checks": report["checks"],
        "records": report["record_summaries"],
    }


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    profile = load_profile(args.profile)
    expectations = resolved_expectations(args, profile)
    records = load_records(args.input_dir)
    checks = evaluate(records, expectations)
    unique_boot_ids = sorted(
        {
            record["data"].get("boot_id")
            for record in records
            if record["data"].get("boot_id")
        }
    )
    record_summaries = [make_record_summary(record) for record in records]
    passed = all(check["passed"] for check in checks)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input_dir),
        "profile": None if args.profile is None else str(args.profile),
        "record_count": len(records),
        "unique_boot_ids": unique_boot_ids,
        "resolved_expectations": expectations,
        "checks": checks,
        "passed": passed,
        "record_summaries": record_summaries,
        "records": records,
    }

    if args.output:
        write_json(args.output, report)
    if args.report_md:
        write_text(args.report_md, render_markdown(report))
    if args.evidence_index_out:
        write_json(args.evidence_index_out, build_evidence_index(report))

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
