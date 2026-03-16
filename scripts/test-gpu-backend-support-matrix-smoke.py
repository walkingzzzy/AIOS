#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "aios" / "runtime" / "gpu-backend-support-matrix.yaml"
DOC_PATH = ROOT / "docs" / "system-development" / "38-GPU-backend-首选支持矩阵评估.md"
DEFAULT_RUNTIME_PROFILE = ROOT / "aios" / "runtime" / "profiles" / "default-runtime-profile.yaml"
JETSON_RUNTIME_PROFILE = (
    ROOT / "aios" / "runtime" / "platforms" / "nvidia-jetson-orin-agx" / "default-runtime-profile.yaml"
)
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "gpu-backend-support-matrix-report"
JETSON_VENDOR_HELPER_SMOKE = "scripts/test-runtimed-jetson-platform-vendor-helper-smoke.py"
JETSON_VENDOR_SMOKE = "scripts/test-runtimed-jetson-platform-vendor-worker-smoke.py"
JETSON_FAILURE_SMOKE = "scripts/test-runtimed-jetson-platform-worker-failure-smoke.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the AIOS GPU backend support matrix against runtime assets"
    )
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
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
        "# AIOS GPU Backend Support Matrix Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Matrix: `{report['matrix_path']}`",
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


def validate_matrix_structure(matrix: dict[str, Any], matrix_path: Path) -> list[dict[str, str]]:
    require(matrix.get("task_id") == "P5-GPU-001", "matrix task_id must be P5-GPU-001")
    require(matrix.get("schema_version") == "1.0.0", "matrix schema_version must be 1.0.0")
    require(isinstance(matrix.get("backends"), list) and matrix["backends"], "matrix backends must be non-empty")
    require(isinstance(matrix.get("platforms"), list) and matrix["platforms"], "matrix platforms must be non-empty")
    require(isinstance(matrix.get("evidence_docs"), list) and matrix["evidence_docs"], "matrix evidence_docs must be non-empty")

    backend_ids = {entry.get("backend_id") for entry in matrix["backends"]}
    require({"local-cpu", "local-gpu"}.issubset(backend_ids), "matrix must cover local-cpu and local-gpu")

    platform_ids = {entry.get("hardware_profile_id") for entry in matrix["platforms"]}
    require(
        {"qemu-x86_64", "generic-x86_64-uefi", "nvidia-jetson-orin-agx"}.issubset(platform_ids),
        "matrix must cover qemu-x86_64, generic-x86_64-uefi, and nvidia-jetson-orin-agx",
    )

    for doc in matrix["evidence_docs"]:
        require((ROOT / doc).exists(), f"matrix evidence doc missing: {doc}")

    for backend in matrix["backends"]:
        require(backend.get("validation"), f"backend validation list missing: {backend.get('backend_id')}")
        for path in backend["validation"]:
            require((ROOT / path).exists(), f"backend validation path missing: {path}")

    for platform in matrix["platforms"]:
        runtime_profile = platform.get("runtime_profile")
        require(runtime_profile, f"platform runtime_profile missing: {platform.get('hardware_profile_id')}")
        require((ROOT / runtime_profile).exists(), f"platform runtime profile missing: {runtime_profile}")
        require(platform.get("evidence"), f"platform evidence list missing: {platform.get('hardware_profile_id')}")
        for path in platform["evidence"]:
            require((ROOT / path).exists(), f"platform evidence path missing: {path}")
        bridge = platform.get("managed_worker_bridge")
        if bridge:
            require((ROOT / bridge).exists(), f"managed worker bridge missing: {bridge}")

    backend_rows = {entry["backend_id"]: entry for entry in matrix["backends"]}
    require(
        JETSON_VENDOR_HELPER_SMOKE in backend_rows["local-gpu"]["validation"],
        "local-gpu validation list must include the Jetson vendor helper smoke",
    )
    require(
        JETSON_VENDOR_SMOKE in backend_rows["local-gpu"]["validation"],
        "local-gpu validation list must include the Jetson vendor worker smoke",
    )

    platform_rows = {entry["hardware_profile_id"]: entry for entry in matrix["platforms"]}
    jetson_row = platform_rows["nvidia-jetson-orin-agx"]
    require(
        JETSON_VENDOR_HELPER_SMOKE in jetson_row["evidence"],
        "Jetson platform evidence must include the vendor helper smoke",
    )
    require(
        JETSON_VENDOR_SMOKE in jetson_row["evidence"],
        "Jetson platform evidence must include the vendor worker smoke",
    )
    require(
        any("vendor-command" in note for note in jetson_row.get("notes", [])),
        "Jetson platform notes must mention the vendor-command bridge evidence",
    )

    return [
        result(
            "matrix-structure",
            f"validated {len(matrix['backends'])} backends and {len(matrix['platforms'])} platform rows from {matrix_path.relative_to(ROOT)}",
        )
    ]


def validate_runtime_profiles(matrix: dict[str, Any]) -> list[dict[str, str]]:
    default_profile = load_yaml(DEFAULT_RUNTIME_PROFILE)
    jetson_profile = load_yaml(JETSON_RUNTIME_PROFILE)

    require(default_profile.get("default_backend") == "local-cpu", "default runtime profile must prefer local-cpu")
    require(default_profile.get("cpu_fallback") is True, "default runtime profile must keep cpu_fallback enabled")
    require(
        "local-gpu" in set(default_profile.get("allowed_backends", [])),
        "default runtime profile must declare local-gpu as optional backend",
    )

    require(jetson_profile.get("default_backend") == "local-gpu", "Jetson runtime profile must prefer local-gpu")
    require(jetson_profile.get("cpu_fallback") is True, "Jetson runtime profile must keep cpu_fallback enabled")
    worker_commands = jetson_profile.get("hardware_profile_managed_worker_commands", {}).get("nvidia-jetson-orin-agx", {})
    require(
        worker_commands.get("local-gpu"),
        "Jetson runtime profile missing local-gpu managed worker command",
    )
    require(
        worker_commands.get("local-npu"),
        "Jetson runtime profile missing local-npu managed worker command",
    )
    require(
        worker_commands["local-gpu"].endswith("bin/launch-managed-worker.sh"),
        "Jetson local-gpu worker command should use launch-managed-worker.sh",
    )
    require(
        worker_commands["local-npu"].endswith("bin/launch-managed-worker.sh"),
        "Jetson local-npu worker command should use launch-managed-worker.sh",
    )

    platform_rows = {entry["hardware_profile_id"]: entry for entry in matrix["platforms"]}
    require(
        platform_rows["generic-x86_64-uefi"]["preferred_backend"] == "local-cpu",
        "generic-x86_64-uefi should prefer local-cpu",
    )
    require(
        platform_rows["nvidia-jetson-orin-agx"]["preferred_backend"] == "local-gpu",
        "Jetson platform row should prefer local-gpu",
    )
    require(
        platform_rows["nvidia-jetson-orin-agx"].get("fallback_backend") == "local-cpu",
        "Jetson platform row should declare local-cpu fallback",
    )

    return [
        result(
            "runtime-profile-alignment",
            "default profile keeps local-cpu baseline; Jetson profile prefers local-gpu with managed worker bridge and cpu fallback",
        )
    ]


def validate_doc(doc_path: Path, matrix: dict[str, Any]) -> list[dict[str, str]]:
    require(doc_path.exists(), f"GPU backend support doc missing: {doc_path}")
    text = doc_path.read_text(encoding="utf-8")
    for needle in [
        "`P5-GPU-001`",
        "`local-cpu`",
        "`local-gpu`",
        "`nvidia-jetson-orin-agx`",
        "CPU fallback",
        "machine-readable",
        JETSON_VENDOR_HELPER_SMOKE,
        JETSON_VENDOR_SMOKE,
        JETSON_FAILURE_SMOKE,
        "vendor command bridge",
        "vendor helper",
    ]:
        require(needle in text, f"GPU backend support doc missing required text: {needle}")

    require(
        "aios/runtime/gpu-backend-support-matrix.yaml" in text,
        "GPU backend support doc should reference the machine-readable matrix asset",
    )

    jetson_row = next(
        entry for entry in matrix["platforms"] if entry["hardware_profile_id"] == "nvidia-jetson-orin-agx"
    )
    require(
        jetson_row["support_state"] in text,
        "GPU backend support doc should mention the Jetson support state from the matrix",
    )
    return [
        result(
            "doc-alignment",
            f"doc references matrix asset, key backends, Jetson vendor bridge success path, and failure-mode evidence in {doc_path.relative_to(ROOT)}",
        )
    ]


def build_report(results: list[dict[str, str]], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "passed",
        "matrix_path": str(args.matrix.relative_to(ROOT)),
        "doc_path": str(args.doc.relative_to(ROOT)),
        "results": results,
    }


def main() -> int:
    args = parse_args()
    matrix = load_yaml(args.matrix)

    results: list[dict[str, str]] = []
    results.extend(validate_matrix_structure(matrix, args.matrix))
    results.extend(validate_runtime_profiles(matrix))
    results.extend(validate_doc(args.doc, matrix))

    report = build_report(results, args)
    write_json(args.output_prefix.with_suffix(".json"), report)
    write_markdown(args.output_prefix.with_suffix(".md"), render_markdown(report))
    print("gpu backend support matrix smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
