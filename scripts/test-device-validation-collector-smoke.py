#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = ROOT / "out" / "tmp"
SCRIPT_PATH = ROOT / "scripts" / "collect-aios-device-validation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("collect_aios_device_validation", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    collector = load_module()
    temp_root = make_temp_dir("aios-device-validation-collector-")
    output_dir = temp_root / "device-validation"

    remote_screen = "/var/lib/aios/deviced/backend-evidence/screen-backend.json"
    remote_audio = "/var/lib/aios/deviced/backend-evidence/audio-backend.json"
    remote_vendor = "/var/lib/aios/runtimed/jetson-vendor-evidence/local-gpu/task-1/vendor-execution.json"
    snapshot = {
        "collected_at": "2026-03-16T00:00:00+00:00",
        "source": {
            "mode": "remote",
            "host": "root@test-device",
        },
        "payloads": {
            "deviced_system_health": {
                "service_id": "aios-deviced",
                "status": "ready",
                "notes": ["socket_path=/run/aios/deviced/deviced.sock"],
            },
            "device_state": {
                "backend_summary": {
                    "overall_status": "ready",
                    "available_status_count": 5,
                    "ui_tree_current_support": "native-live",
                },
                "notes": [
                    f"backend_evidence_artifact[screen]={remote_screen}",
                    f"backend_evidence_artifact[audio]={remote_audio}",
                ],
                "statuses": [
                    {"modality": "screen", "details": [f"evidence_artifact={remote_screen}"]},
                    {"modality": "audio", "details": [f"evidence_artifact={remote_audio}"]},
                ],
                "evidence_artifacts": [
                    {"artifact_path": remote_screen, "baseline": "os-native-backend"},
                    {"artifact_path": remote_audio, "baseline": "runtime-helper-backend"},
                ],
                "ui_tree_support_matrix": [
                    {"environment_id": "current-session", "current": True, "readiness": "native-live"}
                ],
            },
            "device_metadata_system_health": {
                "service_id": "aios-device-metadata-provider",
                "status": "ready",
                "notes": [],
            },
            "device_metadata": {
                "provider_id": "device.metadata.local",
                "summary": {
                    "overall_status": "ready",
                    "available_modalities": ["audio", "screen", "ui_tree"],
                },
                "backend_summary": {
                    "overall_status": "ready",
                },
                "notes": [
                    "hardware_profile_id=framework-laptop-13-amd-7040",
                    "hardware_profile_path=/usr/share/aios/hardware/profiles/framework-laptop-13-amd-7040.yaml",
                    "hardware_profile_canonical_id=generic-x86_64-uefi",
                    "hardware_profile_platform_media_id=generic-x86_64-uefi",
                    "hardware_profile_platform_tier=tier1",
                    "hardware_profile_bringup_status=nominated-formal-tier1",
                    "hardware_profile_validation_status=matched",
                    "hardware_profile_required_modalities=audio,screen,ui_tree",
                    "hardware_profile_conditional_modalities=",
                    "hardware_profile_available_expected_modalities=audio,screen,ui_tree",
                    "hardware_profile_missing_required_modalities=",
                    "hardware_profile_missing_conditional_modalities=",
                    "hardware_profile_release_track_intent=developer-preview,product-preview",
                ],
                "entries": [
                    {"modality": "audio", "available": True},
                    {"modality": "screen", "available": True},
                    {"modality": "ui_tree", "available": True},
                ],
            },
        },
        "evidence_artifacts": [
            {
                "source_path": remote_screen,
                "content": json.dumps(
                    {
                        "modality": "screen",
                        "release_grade_backend_id": "xdg-desktop-portal-screencast",
                        "release_grade_backend_origin": "os-native",
                        "release_grade_backend_stack": "portal+pipewire",
                        "release_grade_contract_kind": "release-grade-runtime-helper",
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "source_path": remote_audio,
                "content": json.dumps(
                    {
                        "modality": "audio",
                        "release_grade_backend_id": "pipewire",
                        "release_grade_backend_origin": "os-native",
                        "release_grade_backend_stack": "pipewire",
                        "contract_kind": "release-grade-runtime-helper",
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "vendor_runtime_evidence_artifacts": [
            {
                "source_path": remote_vendor,
                "content": json.dumps(
                    {
                        "backend_id": "local-gpu",
                        "provider_id": "nvidia.jetson.tensorrt",
                        "provider_kind": "trtexec",
                        "provider_status": "available",
                        "runtime_service_id": "aios-runtimed.jetson-vendor-helper",
                        "contract_kind": "vendor-runtime-evidence-v1",
                        "engine_path": "/var/lib/aios/runtime/vendor-engines/local-gpu.plan",
                        "runtime_binary": "/usr/bin/trtexec",
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "errors": [],
    }

    summary = collector.materialize_snapshot(snapshot, output_dir)
    backend_state_path = output_dir / "backend-state.json"
    renderer_args_path = output_dir / "renderer-args.txt"
    collection_summary_path = output_dir / "collection-summary.json"

    require(backend_state_path.exists(), "missing materialized backend-state artifact")
    require(renderer_args_path.exists(), "missing renderer args file")
    require(collection_summary_path.exists(), "missing collection summary")

    backend_state = json.loads(backend_state_path.read_text(encoding="utf-8"))
    renderer_args = renderer_args_path.read_text(encoding="utf-8")
    collection_summary = json.loads(collection_summary_path.read_text(encoding="utf-8"))
    vendor_runtime_dir = output_dir / "vendor-runtime-evidence"

    rewritten_notes = backend_state.get("notes") or []
    require(all(remote_screen not in note for note in rewritten_notes if isinstance(note, str)), "screen artifact path was not rewritten")
    require(all(remote_audio not in note for note in rewritten_notes if isinstance(note, str)), "audio artifact path was not rewritten")
    require(any(str(vendor_runtime_dir) in note for note in rewritten_notes if isinstance(note, str) and note.startswith("vendor_evidence_path=")), "vendor runtime evidence note was not attached")
    evidence_artifacts = backend_state.get("evidence_artifacts") or []
    require(all(str(output_dir / "backend-evidence") in item.get("artifact_path", "") for item in evidence_artifacts), "backend evidence not localized")
    vendor_runtime_files = sorted(vendor_runtime_dir.glob("*.json"))
    require(vendor_runtime_files, "vendor runtime evidence was not localized")
    require("--device-metadata-artifact" in renderer_args, "renderer args missing device metadata artifact")
    require("--device-backend-state-artifact" in renderer_args, "renderer args missing backend-state artifact")
    require("--device-release-grade-backend-ids" in renderer_args, "renderer args missing release-grade backend ids")
    require("pipewire,xdg-desktop-portal-screencast" in renderer_args, "renderer args missing aggregated backend ids")
    require("--device-release-grade-contract-kinds" in renderer_args, "renderer args missing release-grade contract kinds")
    require("release-grade-runtime-helper" in renderer_args, "renderer args missing contract kind fallback")
    require("--vendor-runtime-evidence" in renderer_args, "renderer args missing vendor runtime evidence wiring")
    require("nvidia.jetson.tensorrt" in vendor_runtime_files[0].read_text(encoding="utf-8"), "vendor runtime evidence payload mismatch")
    require(collection_summary["backend_state_artifact"] == str(backend_state_path), "collection summary backend-state path mismatch")
    require(collection_summary["vendor_runtime_evidence_paths"], "collection summary missing vendor runtime evidence paths")

    print(
        json.dumps(
            {
                "backend_state_artifact": str(backend_state_path),
                "renderer_args_path": str(renderer_args_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
