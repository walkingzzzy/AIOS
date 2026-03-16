#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
NOMINATIONS_PATH = ROOT / "aios" / "hardware" / "tier1-nominated-machines.yaml"
DOC_PATH = ROOT / "docs" / "system-development" / "39-Tier1-正式机器冻结清单.md"
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "tier1-machine-nominations-report"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the AIOS formal Tier 1 machine nomination list"
    )
    parser.add_argument("--nominations", type=Path, default=NOMINATIONS_PATH)
    parser.add_argument("--doc", type=Path, default=DOC_PATH)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")


def result(name: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": "passed", "detail": detail}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Tier 1 Machine Nominations Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Nominations: `{report['nominations_path']}`",
        f"- Doc: `{report['doc_path']}`",
        "",
        "## Results",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
    ]
    for item in report["results"]:
        lines.append(f"| `{item['name']}` | `{item['status']}` | {item['detail']} |")
    return "\n".join(lines)


def validate_nominations(payload: dict[str, Any]) -> list[dict[str, str]]:
    require(payload.get("task_id") == "P5-HW-001", "task_id must be P5-HW-001")
    require(payload.get("schema_version") == "1.0.0", "schema_version must be 1.0.0")
    entries = payload.get("nominated_machines")
    require(isinstance(entries, list) and len(entries) >= 2, "must nominate at least two Tier 1 machines")

    by_id = {}
    for entry in entries:
        require(isinstance(entry, dict), "each nomination must be a mapping")
        machine_id = entry.get("machine_id")
        require(isinstance(machine_id, str) and machine_id, "machine_id must be a non-empty string")
        require(machine_id not in by_id, f"duplicate machine_id: {machine_id}")
        profile_path = ROOT / str(entry.get("profile_path", ""))
        require(profile_path.exists(), f"profile missing for {machine_id}: {profile_path}")
        image_platform_profile = ROOT / "aios" / "image" / "platforms" / str(entry.get("platform_media_id", "")) / "profile.yaml"
        require(image_platform_profile.exists(), f"platform media profile missing for {machine_id}: {image_platform_profile}")
        by_id[machine_id] = {"entry": entry, "profile_path": profile_path, "profile": load_yaml(profile_path)}

    x86 = by_id.get("framework-laptop-13-amd-7040")
    require(x86 is not None, "missing framework-laptop-13-amd-7040 nomination")
    require(x86["profile"].get("arch") == "x86_64", "framework nomination must be x86_64")
    require(x86["profile"].get("canonical_hardware_profile_id") == "generic-x86_64-uefi", "framework nomination must map to generic-x86_64-uefi")
    require(x86["profile"].get("bringup_status") == "nominated-formal-tier1", "framework nomination bringup_status mismatch")
    for field in ["wifi", "bluetooth", "audio", "camera"]:
        require(x86["profile"].get(field) == "required", f"framework nomination must require {field}")

    jetson = by_id.get("nvidia-jetson-orin-agx")
    require(jetson is not None, "missing nvidia-jetson-orin-agx nomination")
    require(jetson["profile"].get("model") == "jetson-agx-orin-devkit", "Jetson nomination model mismatch")
    require(jetson["entry"].get("runtime_profile") == "/usr/share/aios/runtime/platforms/nvidia-jetson-orin-agx/default-runtime-profile.yaml", "Jetson nomination runtime profile mismatch")

    return [
        result(
            "nominations-structure",
            f"validated {len(entries)} formal Tier 1 nominations with x86_64 and Jetson coverage",
        )
    ]


def validate_doc(doc_path: Path) -> list[dict[str, str]]:
    require(doc_path.exists(), f"doc missing: {doc_path}")
    text = doc_path.read_text(encoding="utf-8")
    for needle in [
        "`P5-HW-001`",
        "`framework-laptop-13-amd-7040`",
        "`nvidia-jetson-orin-agx`",
        "aios/hardware/tier1-nominated-machines.yaml",
        "generic-x86_64-uefi",
    ]:
        require(needle in text, f"doc missing required text: {needle}")
    return [result("doc-alignment", f"doc captures both formal machine nominations in {doc_path.relative_to(ROOT)}")]


def build_report(results: list[dict[str, str]], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "passed",
        "nominations_path": str(args.nominations.relative_to(ROOT)),
        "doc_path": str(args.doc.relative_to(ROOT)),
        "results": results,
    }


def main() -> int:
    args = parse_args()
    payload = load_yaml(args.nominations)

    results: list[dict[str, str]] = []
    results.extend(validate_nominations(payload))
    results.extend(validate_doc(args.doc))

    report = build_report(results, args)
    write_json(args.output_prefix.with_suffix(".json"), report)
    write_markdown(args.output_prefix.with_suffix(".md"), render_markdown(report))
    print("tier1 machine nominations smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
