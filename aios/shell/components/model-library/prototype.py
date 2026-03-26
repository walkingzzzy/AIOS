#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


_MODEL_MANAGER_MODULE: ModuleType | None = None
_AI_CENTER_PROTOTYPE_MODULE: ModuleType | None = None


def _load_module(module_name: str, path: Path) -> ModuleType:
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_model_manager_module() -> ModuleType:
    global _MODEL_MANAGER_MODULE
    if _MODEL_MANAGER_MODULE is not None:
        return _MODEL_MANAGER_MODULE
    module_path = Path(__file__).resolve().parents[3] / "runtime" / "model_manager.py"
    _MODEL_MANAGER_MODULE = _load_module("aios_runtime_model_manager", module_path)
    return _MODEL_MANAGER_MODULE


def load_ai_center_prototype_module() -> ModuleType:
    global _AI_CENTER_PROTOTYPE_MODULE
    if _AI_CENTER_PROTOTYPE_MODULE is not None:
        return _AI_CENTER_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "ai-center" / "prototype.py"
    _AI_CENTER_PROTOTYPE_MODULE = _load_module("aios_shell_ai_center_prototype", module_path)
    return _AI_CENTER_PROTOTYPE_MODULE


def default_ai_readiness_path() -> Path:
    return load_ai_center_prototype_module().default_ai_readiness_path()


def default_ai_onboarding_report_path() -> Path:
    return load_ai_center_prototype_module().default_ai_onboarding_report_path()


def default_model_dir() -> Path:
    return load_ai_center_prototype_module().default_model_dir()


def default_model_registry() -> Path:
    return load_ai_center_prototype_module().default_model_registry()


def default_import_source() -> Path | None:
    value = os.environ.get("AIOS_SHELL_MODEL_IMPORT_SOURCE") or os.environ.get("AIOS_MODEL_IMPORT_SOURCE")
    if not value:
        return None
    return Path(value)


def default_recommended_preload_roots() -> list[Path]:
    module = load_model_manager_module()
    return [Path(item) for item in module.default_recommended_preload_roots()]


def default_recommended_source_map() -> Path | None:
    value = os.environ.get("AIOS_SHELL_RECOMMENDED_MODEL_SOURCE_MAP")
    if value:
        return Path(value)
    module = load_model_manager_module()
    return Path(module.default_recommended_source_map_path())


def default_recommended_download_staging_dir() -> Path:
    value = os.environ.get("AIOS_SHELL_RECOMMENDED_MODEL_DOWNLOAD_STAGING_DIR")
    if value:
        return Path(value)
    module = load_model_manager_module()
    return Path(module.default_recommended_download_staging_dir(default_model_dir()))


def build_ai_state(
    readiness_path: Path | None,
    report_path: Path | None,
    model_dir: Path | None,
    model_registry: Path | None,
) -> dict[str, Any]:
    return load_ai_center_prototype_module().build_ai_center_state(
        readiness_path,
        report_path,
        model_dir,
        model_registry,
    )


def suggested_model_id(path: Path) -> str:
    module = load_model_manager_module()
    try:
        return module.normalize_model_id(path.stem)
    except Exception:
        return path.stem


def inspect_import_source(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "configured": False,
            "ready": False,
            "source_path": None,
            "exists": False,
            "valid": False,
            "format": "unknown",
            "size_bytes": 0,
            "sha256": "",
            "suggested_model_id": None,
            "error": None,
        }

    module = load_model_manager_module()
    manager = module.ModelManager(model_dir=default_model_dir(), registry_path=default_model_registry())
    resolved_path = path.expanduser()
    validation = manager.validate_model(resolved_path)
    error = None
    if not validation.get("exists"):
        error = f"missing:{resolved_path}"
    elif not validation.get("valid"):
        error = f"invalid-model:{resolved_path}"

    return {
        "configured": True,
        "ready": bool(validation.get("valid")),
        "source_path": str(resolved_path),
        "exists": bool(validation.get("exists")),
        "valid": bool(validation.get("valid")),
        "format": validation.get("format", "unknown"),
        "size_bytes": int(validation.get("size_bytes") or 0),
        "sha256": validation.get("sha256", ""),
        "suggested_model_id": suggested_model_id(resolved_path),
        "error": error,
    }


def load_manager(model_dir: Path | None, model_registry: Path | None):
    module = load_model_manager_module()
    manager = module.ModelManager(model_dir=model_dir, registry_path=model_registry)
    manager.load_registry(model_registry)
    manager.scan_directory(model_dir)
    return manager


def build_recommended_distribution_state(
    model_dir: Path | None,
    model_registry: Path | None,
    *,
    preload_roots: list[Path] | None = None,
    source_map: Path | None = None,
    download_staging_dir: Path | None = None,
) -> dict[str, Any]:
    module = load_model_manager_module()
    manager = load_manager(model_dir, model_registry)
    try:
        return module.build_recommended_distribution_plan(
            manager,
            preload_roots=preload_roots or default_recommended_preload_roots(),
            source_map_path=source_map,
            download_staging_dir=download_staging_dir,
        )
    except Exception as error:
        return {
            "catalog_status": "error",
            "catalog_error": str(error),
            "source_map_status": "error",
            "source_map_error": str(error),
            "source_map_path": str(source_map) if source_map else None,
            "preload_roots": [str(item) for item in (preload_roots or [])],
            "download_staging_dir": str(download_staging_dir) if download_staging_dir else None,
            "model_count": 0,
            "selected_model_count": 0,
            "actionable_count": 0,
            "pending_count": 0,
            "manual_count": 0,
            "unsupported_count": 0,
            "installed_count": 0,
            "models": [],
        }


def build_model_library_state(
    readiness_path: Path | None,
    report_path: Path | None,
    model_dir: Path | None,
    model_registry: Path | None,
    import_source: Path | None = None,
    recommended_preload_roots: list[Path] | None = None,
    recommended_source_map: Path | None = None,
    recommended_download_staging_dir: Path | None = None,
) -> dict[str, Any]:
    ai_state = build_ai_state(readiness_path, report_path, model_dir, model_registry)
    import_candidate = inspect_import_source(import_source)
    recommended_distribution = build_recommended_distribution_state(
        model_dir,
        model_registry,
        preload_roots=recommended_preload_roots,
        source_map=recommended_source_map,
        download_staging_dir=recommended_download_staging_dir,
    )
    diagnostics = list(ai_state.get("diagnostics") or [])
    if import_candidate.get("error"):
        diagnostics.append(f"import_source={import_candidate['error']}")
    if recommended_distribution.get("catalog_error"):
        diagnostics.append(f"recommended_distribution={recommended_distribution['catalog_error']}")
    if recommended_distribution.get("source_map_error"):
        diagnostics.append(f"recommended_source_map={recommended_distribution['source_map_error']}")
    return {
        **ai_state,
        "import_candidate": import_candidate,
        "recommended_distribution": recommended_distribution,
        "diagnostics": diagnostics,
    }


def import_local_model(
    model_dir: Path | None,
    model_registry: Path | None,
    source_path: Path,
    *,
    model_id: str | None = None,
    capabilities: list[str] | None = None,
    aliases: list[str] | None = None,
    set_default: bool = False,
    symlink: bool = False,
    quantization: str = "",
    parameters_estimate: str = "",
) -> dict[str, Any]:
    manager = load_manager(model_dir, model_registry)
    entry = manager.import_model(
        source_path,
        model_id=model_id,
        capabilities=capabilities or ["text-generation"],
        aliases=aliases or [],
        set_default=set_default,
        symlink=symlink,
        quantization=quantization,
        parameters_estimate=parameters_estimate,
    )
    registry_path = manager.save_registry(model_registry)
    inventory = manager.export_inventory()
    return {
        "status": "imported",
        "imported": entry.to_dict(),
        "registry_path": str(registry_path),
        "defaults": inventory.get("defaults", {}),
        "local_model_count": inventory.get("model_count", 0),
    }


def set_default_model_selection(
    model_dir: Path | None,
    model_registry: Path | None,
    capability: str,
    model_id: str,
) -> dict[str, Any]:
    manager = load_manager(model_dir, model_registry)
    manager.set_default_model(capability, model_id)
    registry_path = manager.save_registry(model_registry)
    default_entry = manager.get_default_model(capability)
    inventory = manager.export_inventory()
    return {
        "status": "default-updated",
        "capability": capability,
        "model_id": default_entry.model_id if default_entry is not None else None,
        "registry_path": str(registry_path),
        "defaults": inventory.get("defaults", {}),
        "local_model_count": inventory.get("model_count", 0),
    }


def delete_registered_model(
    model_dir: Path | None,
    model_registry: Path | None,
    model_id: str,
    *,
    keep_file: bool = False,
) -> dict[str, Any]:
    manager = load_manager(model_dir, model_registry)
    entry = manager.delete_model(model_id, remove_file=not keep_file)
    registry_path = manager.save_registry(model_registry)
    inventory = manager.export_inventory()
    return {
        "status": "deleted",
        "deleted": entry.to_dict(),
        "keep_file": keep_file,
        "registry_path": str(registry_path),
        "defaults": inventory.get("defaults", {}),
        "local_model_count": inventory.get("model_count", 0),
    }


def apply_recommended_distribution_selection(
    model_dir: Path | None,
    model_registry: Path | None,
    *,
    model_ids: list[str] | None = None,
    preload_roots: list[Path] | None = None,
    source_map: Path | None = None,
    download_staging_dir: Path | None = None,
    set_default_policy: str = "if-missing",
) -> dict[str, Any]:
    module = load_model_manager_module()
    manager = load_manager(model_dir, model_registry)
    payload = module.apply_recommended_distribution(
        manager,
        model_ids=model_ids,
        preload_roots=preload_roots or default_recommended_preload_roots(),
        source_map_path=source_map,
        download_staging_dir=download_staging_dir,
        set_default_policy=set_default_policy,
    )
    inventory = manager.export_inventory()
    payload.update(
        {
            "defaults": inventory.get("defaults", {}),
            "local_model_count": inventory.get("model_count", 0),
        }
    )
    return payload
