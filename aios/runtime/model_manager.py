#!/usr/bin/env python3
"""
AIOS local model manager — manages model lifecycle for runtimed workers.

Responsibilities:
- Discover available local models (GGUF, safetensors)
- Validate model files (checksum, format detection)
- Provide model registry for runtimed workers
- Support model aliasing and default selection
- Emit machine-readable model inventory

Environment:
  AIOS_MODEL_DIR         - Root directory for models (default: /var/lib/aios/models)
  AIOS_MODEL_REGISTRY    - Path to model registry YAML (default: model-registry.yaml in MODEL_DIR)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, url2pathname, urlopen

try:
    import yaml  # type: ignore[import-untyped]

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

GGUF_MAGIC = b"GGUF"
SAFETENSORS_MAGIC_CHAR = ord("{")

MODEL_EXTENSIONS = {".gguf", ".safetensors", ".bin"}

CAPABILITY_VALUES = frozenset({"text-generation", "embedding", "reranking"})
FORMAT_VALUES = frozenset({"gguf", "safetensors", "bin", "unknown"})
MODEL_DISTRIBUTION_STRATEGIES = frozenset({"preload", "firstboot-download", "manual-import"})
AI_MODE_VALUES = frozenset({"local", "cloud", "hybrid", "later"})

DEFAULT_MODEL_DIR = os.environ.get("AIOS_MODEL_DIR", "/var/lib/aios/models")
DEFAULT_REGISTRY_FILENAME = "model-registry.yaml"
DEFAULT_RECOMMENDED_CATALOG_FILENAME = "recommended-model-catalog.yaml"
DEFAULT_RECOMMENDED_SOURCE_MAP_FILENAME = "recommended-model-sources.yaml"
DEFAULT_RECOMMENDED_DOWNLOAD_STAGING_DIRNAME = ".recommended-downloads"
DEFAULT_RECOMMENDED_PRELOAD_ROOTS = (
    "/var/lib/aios/preloaded-models",
    "/opt/aios/preloaded-models",
)
FORMAT_EXTENSION_MAP = {
    "gguf": ".gguf",
    "safetensors": ".safetensors",
    "bin": ".bin",
}


@dataclass
class ModelEntry:
    model_id: str
    path: str
    format: str = "unknown"
    size_bytes: int = 0
    sha256: str = ""
    aliases: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    quantization: str = ""
    parameters_estimate: str = ""
    source_kind: str = "local-scan"
    source_uri: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelEntry:
        return cls(
            model_id=data["model_id"],
            path=data["path"],
            format=data.get("format", "unknown"),
            size_bytes=data.get("size_bytes", 0),
            sha256=data.get("sha256", ""),
            aliases=list(data.get("aliases") or []),
            capabilities=list(data.get("capabilities") or []),
            quantization=data.get("quantization", ""),
            parameters_estimate=data.get("parameters_estimate", ""),
            source_kind=data.get("source_kind", "local-scan"),
            source_uri=data.get("source_uri", ""),
        )


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".gguf":
        return _verify_gguf_magic(path)
    if suffix == ".safetensors":
        return _verify_safetensors_magic(path)
    if suffix == ".bin":
        return _detect_by_magic(path)
    return "unknown"


def _verify_gguf_magic(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        if magic == GGUF_MAGIC:
            return "gguf"
    except OSError:
        pass
    return "unknown"


def _verify_safetensors_magic(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            first_byte = f.read(1)
        if first_byte and first_byte[0] == SAFETENSORS_MAGIC_CHAR:
            return "safetensors"
    except OSError:
        pass
    return "unknown"


def _detect_by_magic(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            header = f.read(4)
    except OSError:
        return "unknown"
    if header[:4] == GGUF_MAGIC:
        return "gguf"
    if header and header[0] == SAFETENSORS_MAGIC_CHAR:
        return "safetensors"
    return "bin"


def compute_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def default_recommended_catalog_path() -> Path:
    value = os.environ.get("AIOS_MODEL_RECOMMENDED_CATALOG")
    if value:
        return Path(value)
    return Path(__file__).resolve().with_name(DEFAULT_RECOMMENDED_CATALOG_FILENAME)


def _load_structured_document(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix in (".yaml", ".yml"):
            if not _HAS_YAML:
                raise RuntimeError("PyYAML is required to load YAML documents")
            payload = yaml.safe_load(f)
        else:
            payload = json.load(f)
    if not payload:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"expected object document: {path}")
    return payload


def _normalize_string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    raise ValueError(f"expected string list, got: {type(value).__name__}")


def _normalize_recommended_modes(value: Any) -> list[str]:
    normalized: list[str] = []
    for mode in _normalize_string_list(value):
        candidate = str(mode).strip().lower()
        if candidate not in AI_MODE_VALUES:
            raise ValueError(f"unsupported recommended mode: {candidate}")
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_recommended_formats(value: Any) -> list[str]:
    normalized: list[str] = []
    for fmt in _normalize_string_list(value):
        candidate = str(fmt).strip().lower()
        if candidate not in FORMAT_VALUES or candidate == "unknown":
            raise ValueError(f"unsupported recommended format: {candidate}")
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_recommended_sources(
    value: Any,
    *,
    distribution_strategy: str,
) -> list[dict[str, str]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("recommended model sources must be a list")

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("recommended model source entries must be objects")
        kind = str(item.get("kind") or "").strip()
        source_value = str(item.get("value") or "").strip()
        if not kind or not source_value:
            raise ValueError("recommended model source entries require kind and value")
        display = str(item.get("display") or source_value).strip()
        source_strategy = str(item.get("strategy") or distribution_strategy).strip().lower()
        if source_strategy not in MODEL_DISTRIBUTION_STRATEGIES:
            raise ValueError(f"unsupported source strategy: {source_strategy}")
        normalized.append(
            {
                "kind": kind,
                "value": source_value,
                "display": display,
                "strategy": source_strategy,
            }
        )
    return normalized


def normalize_recommended_model_entry(entry: dict[str, Any]) -> dict[str, Any]:
    model_id = str(entry.get("model_id") or "").strip()
    if not model_id:
        raise ValueError("recommended model entry requires model_id")

    distribution_strategy = str(entry.get("distribution_strategy") or "manual-import").strip().lower()
    if distribution_strategy not in MODEL_DISTRIBUTION_STRATEGIES:
        raise ValueError(f"unsupported distribution strategy: {distribution_strategy}")

    capabilities = normalize_capabilities(
        _normalize_string_list(entry.get("capabilities") or ["text-generation"])
    )
    aliases = normalize_aliases(_normalize_string_list(entry.get("aliases")))
    recommended_modes = _normalize_recommended_modes(entry.get("recommended_modes"))
    formats = _normalize_recommended_formats(entry.get("formats"))
    sources = _normalize_recommended_sources(
        entry.get("sources"),
        distribution_strategy=distribution_strategy,
    )

    return {
        "model_id": normalize_model_id(model_id),
        "display_name": str(entry.get("display_name") or model_id).strip(),
        "description": str(entry.get("description") or "").strip(),
        "capabilities": capabilities,
        "formats": formats,
        "aliases": aliases,
        "distribution_strategy": distribution_strategy,
        "recommended_modes": recommended_modes,
        "default_recommended": bool(entry.get("default_recommended", False)),
        "sources": sources,
    }


def load_recommended_model_catalog(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else default_recommended_catalog_path()
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "catalog_id": "aios-recommended-models",
        "catalog_label": "AIOS Recommended Models",
        "source_path": str(target),
        "source_status": "missing",
        "source_error": None,
        "models": [],
    }
    if not target.exists():
        return payload

    try:
        data = _load_structured_document(target)
        models_data = data.get("models") or []
        if not isinstance(models_data, list):
            raise ValueError("recommended model catalog models must be a list")
        payload.update(
            {
                "schema_version": str(data.get("schema_version") or payload["schema_version"]),
                "catalog_id": str(data.get("catalog_id") or payload["catalog_id"]),
                "catalog_label": str(data.get("catalog_label") or payload["catalog_label"]),
                "source_status": "ready",
                "models": [normalize_recommended_model_entry(entry) for entry in models_data],
            }
        )
    except Exception as error:
        payload["source_status"] = "error"
        payload["source_error"] = str(error)
    return payload


def _safe_normalize_identifier(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        return normalize_model_id(str(value))
    except ValueError:
        return None


def inventory_identifier_set(inventory: dict[str, Any] | None) -> set[str]:
    identifiers: set[str] = set()
    if not inventory:
        return identifiers
    for entry in inventory.get("models", []):
        if not isinstance(entry, dict):
            continue
        for candidate in [entry.get("model_id"), *(entry.get("aliases") or [])]:
            normalized = _safe_normalize_identifier(candidate)
            if normalized:
                identifiers.add(normalized)
    return identifiers


def summarize_recommended_model_catalog(
    catalog: dict[str, Any],
    *,
    inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    models = [item for item in catalog.get("models", []) if isinstance(item, dict)]
    inventory_ids = inventory_identifier_set(inventory)
    strategy_counts: dict[str, int] = {}
    capability_counts: dict[str, int] = {}
    installed_model_ids: list[str] = []
    summarized_models: list[dict[str, Any]] = []

    for entry in models:
        strategy = str(entry.get("distribution_strategy") or "manual-import")
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        for capability in list(entry.get("capabilities") or []):
            capability_counts[capability] = capability_counts.get(capability, 0) + 1

        candidates = [entry.get("model_id"), *(entry.get("aliases") or [])]
        installed = any(
            normalized in inventory_ids
            for normalized in (_safe_normalize_identifier(value) for value in candidates)
            if normalized is not None
        )
        if installed:
            installed_model_ids.append(str(entry.get("model_id")))
        summarized_models.append({**entry, "installed": installed})

    default_recommendations: dict[str, str] = {}
    for capability in sorted(CAPABILITY_VALUES):
        default_entry = next(
            (
                entry
                for entry in summarized_models
                if capability in list(entry.get("capabilities") or [])
                and entry.get("default_recommended")
            ),
            None,
        )
        if default_entry is None:
            default_entry = next(
                (
                    entry
                    for entry in summarized_models
                    if capability in list(entry.get("capabilities") or [])
                ),
                None,
            )
        if default_entry is not None:
            default_recommendations[capability] = str(default_entry["model_id"])

    return {
        "schema_version": catalog.get("schema_version") or "1.0.0",
        "catalog_id": catalog.get("catalog_id") or "aios-recommended-models",
        "catalog_label": catalog.get("catalog_label") or "AIOS Recommended Models",
        "source_path": catalog.get("source_path"),
        "source_status": catalog.get("source_status") or "missing",
        "source_error": catalog.get("source_error"),
        "model_count": len(summarized_models),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "capability_counts": dict(sorted(capability_counts.items())),
        "installed_count": len(installed_model_ids),
        "installed_model_ids": sorted(installed_model_ids),
        "default_recommendations": default_recommendations,
        "models": summarized_models,
    }


def _normalize_path_values(values: Any) -> list[Path]:
    if values in (None, ""):
        return []
    normalized: list[Path] = []
    if isinstance(values, (str, Path)):
        raw_values = [
            item
            for item in str(values).split(os.pathsep)
            if item.strip()
        ]
    elif isinstance(values, (list, tuple, set)):
        raw_values = [str(item) for item in values if item not in (None, "")]
    else:
        raise ValueError(f"expected path list, got: {type(values).__name__}")
    for item in raw_values:
        candidate = Path(item).expanduser()
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def default_recommended_preload_roots() -> list[Path]:
    configured = os.environ.get("AIOS_RECOMMENDED_MODEL_PRELOAD_ROOTS") or os.environ.get(
        "AIOS_MODEL_PRELOAD_ROOTS"
    )
    if configured:
        return _normalize_path_values(configured)
    return [Path(item) for item in DEFAULT_RECOMMENDED_PRELOAD_ROOTS]


def default_recommended_source_map_path() -> Path:
    configured = os.environ.get("AIOS_RECOMMENDED_MODEL_SOURCE_MAP")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().with_name(DEFAULT_RECOMMENDED_SOURCE_MAP_FILENAME)


def default_recommended_download_staging_dir(
    model_dir: str | Path | None = None,
) -> Path:
    configured = os.environ.get("AIOS_RECOMMENDED_MODEL_DOWNLOAD_STAGING_DIR")
    if configured:
        return Path(configured)
    root = Path(model_dir) if model_dir else Path(DEFAULT_MODEL_DIR)
    return root / DEFAULT_RECOMMENDED_DOWNLOAD_STAGING_DIRNAME


def load_recommended_source_map(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else default_recommended_source_map_path()
    payload: dict[str, Any] = {
        "source_path": str(target),
        "source_status": "missing",
        "source_error": None,
        "mappings": {},
    }
    if not target.exists():
        return payload
    try:
        data = _load_structured_document(target)
        mappings = data.get("mappings")
        if mappings is None:
            mappings = data.get("sources")
        if mappings is None:
            mappings = data
        if not isinstance(mappings, dict):
            raise ValueError("recommended source map must be an object")
        payload["source_status"] = "ready"
        payload["mappings"] = dict(mappings)
    except Exception as error:
        payload["source_status"] = "error"
        payload["source_error"] = str(error)
    return payload


def _is_url_value(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def _is_file_uri(value: str) -> bool:
    return urlparse(value).scheme == "file"


def _file_uri_to_path(value: str) -> Path:
    parsed = urlparse(value)
    return Path(url2pathname(parsed.path)).expanduser()


def _preferred_model_suffix(
    entry: dict[str, Any],
    value: str | None = None,
) -> str:
    if value:
        candidate = Path(urlparse(value).path).suffix.lower()
        if candidate in MODEL_EXTENSIONS:
            return candidate
    for fmt in list(entry.get("formats") or []):
        suffix = FORMAT_EXTENSION_MAP.get(str(fmt))
        if suffix:
            return suffix
    return ".bin"


def _normalize_source_map_entry(value: Any) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return {"resolved_value": value}
    if not isinstance(value, dict):
        raise ValueError("recommended source map entries must be strings or objects")
    resolved_value = value.get("value") or value.get("uri") or value.get("path")
    if resolved_value in (None, ""):
        raise ValueError("recommended source map object entries require value/uri/path")
    payload = dict(value)
    payload["resolved_value"] = str(resolved_value)
    return payload


def _lookup_source_map_entry(
    mappings: dict[str, Any],
    entry: dict[str, Any],
    source: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    lookup_keys = [
        f"{entry.get('model_id')}:{source.get('value')}",
        str(source.get("value") or ""),
        str(entry.get("model_id") or ""),
    ]
    for key in lookup_keys:
        if not key or key not in mappings:
            continue
        return key, _normalize_source_map_entry(mappings[key])
    return None, None


def _looks_like_local_path(value: str) -> bool:
    candidate = Path(value)
    if candidate.is_absolute():
        return True
    return any(
        (
            os.sep in value,
            os.altsep and os.altsep in value,
            value.startswith("."),
            candidate.exists(),
        )
    )


def _candidate_source_names(entry: dict[str, Any], source_value: str) -> tuple[set[str], set[str]]:
    raw_names: set[str] = set()
    raw_stems: set[str] = set()
    trimmed = source_value.rstrip("/\\")
    if trimmed:
        raw_names.add(Path(trimmed).name)
        raw_stems.add(Path(trimmed).stem)
    for value in [entry.get("model_id"), *(entry.get("aliases") or [])]:
        candidate = str(value or "").strip()
        if not candidate:
            continue
        raw_names.add(Path(candidate).name)
        raw_stems.add(Path(candidate).stem)
    expanded_names = set(raw_names)
    for name in list(raw_names):
        if "." not in name:
            for extension in MODEL_EXTENSIONS:
                expanded_names.add(f"{name}{extension}")
    return expanded_names, raw_stems


def _find_candidate_in_preload_roots(
    preload_roots: list[Path],
    entry: dict[str, Any],
    source_value: str,
) -> Path | None:
    if not preload_roots:
        return None
    relative = Path(source_value)
    if not relative.is_absolute() and source_value not in (None, ""):
        for root in preload_roots:
            if not root.exists():
                continue
            direct = (root / relative).expanduser()
            if direct.exists():
                return direct
    candidate_names, candidate_stems = _candidate_source_names(entry, source_value)
    for root in preload_roots:
        if not root.exists():
            continue
        for item in sorted(root.rglob("*")):
            if item.name in candidate_names or item.stem in candidate_stems:
                return item
    return None


def _resolve_recommended_local_candidate(
    entry: dict[str, Any],
    source_value: str,
    *,
    preload_roots: list[Path],
) -> Path | None:
    if _is_file_uri(source_value):
        return _file_uri_to_path(source_value)
    if _looks_like_local_path(source_value):
        return Path(source_value).expanduser()
    return _find_candidate_in_preload_roots(preload_roots, entry, source_value)


def _resolve_recommended_distribution_source(
    entry: dict[str, Any],
    source: dict[str, Any],
    *,
    preload_roots: list[Path],
    source_map: dict[str, Any],
) -> dict[str, Any]:
    mappings = dict(source_map.get("mappings") or {})
    map_key, mapped_entry = _lookup_source_map_entry(mappings, entry, source)
    resolved_value = str(mapped_entry.get("resolved_value")) if mapped_entry else str(source.get("value") or "")
    local_candidate = _resolve_recommended_local_candidate(
        entry,
        resolved_value,
        preload_roots=preload_roots,
    )
    if local_candidate is not None and local_candidate.exists():
        if local_candidate.is_dir():
            return {
                "status": "unsupported",
                "action": "manual",
                "actionable": False,
                "detail": f"directory-import-unsupported:{local_candidate}",
                "resolved_value": resolved_value,
                "resolved_from": map_key,
                "source_path": str(local_candidate),
                "filename": mapped_entry.get("filename") if mapped_entry else None,
            }
        return {
            "status": "ready-import",
            "action": "import",
            "actionable": True,
            "detail": f"local-source-ready:{local_candidate}",
            "resolved_value": resolved_value,
            "resolved_from": map_key,
            "source_path": str(local_candidate),
            "filename": mapped_entry.get("filename") if mapped_entry else None,
        }
    if _is_url_value(resolved_value):
        return {
            "status": "ready-download",
            "action": "download",
            "actionable": True,
            "detail": f"download-source-ready:{resolved_value}",
            "resolved_value": resolved_value,
            "resolved_from": map_key,
            "source_path": None,
            "filename": mapped_entry.get("filename") if mapped_entry else None,
        }
    if source.get("kind") == "openai-compatible":
        return {
            "status": "manual-required",
            "action": "manual",
            "actionable": False,
            "detail": f"remote-endpoint-source:{resolved_value}",
            "resolved_value": resolved_value,
            "resolved_from": map_key,
            "source_path": None,
            "filename": None,
        }
    if mapped_entry is not None:
        return {
            "status": "missing-source",
            "action": "manual",
            "actionable": False,
            "detail": f"mapped-source-missing:{resolved_value}",
            "resolved_value": resolved_value,
            "resolved_from": map_key,
            "source_path": None,
            "filename": mapped_entry.get("filename"),
        }
    if source.get("strategy") == "firstboot-download":
        return {
            "status": "missing-source",
            "action": "manual",
            "actionable": False,
            "detail": f"symbolic-download-source-unresolved:{resolved_value}",
            "resolved_value": resolved_value,
            "resolved_from": None,
            "source_path": None,
            "filename": None,
        }
    if source.get("strategy") == "preload":
        return {
            "status": "missing-source",
            "action": "manual",
            "actionable": False,
            "detail": f"preload-artifact-missing:{resolved_value}",
            "resolved_value": resolved_value,
            "resolved_from": None,
            "source_path": None,
            "filename": None,
        }
    return {
        "status": "manual-required",
        "action": "manual",
        "actionable": False,
        "detail": f"manual-import-required:{resolved_value}",
        "resolved_value": resolved_value,
        "resolved_from": None,
        "source_path": None,
        "filename": None,
    }


def build_recommended_distribution_plan(
    manager: "ModelManager",
    *,
    recommended_catalog_path: str | Path | None = None,
    preload_roots: list[str | Path] | None = None,
    source_map_path: str | Path | None = None,
    download_staging_dir: str | Path | None = None,
    model_ids: list[str] | None = None,
) -> dict[str, Any]:
    catalog = load_recommended_model_catalog(recommended_catalog_path)
    inventory = manager.export_inventory()
    catalog_summary = summarize_recommended_model_catalog(catalog, inventory=inventory)
    selected_ids = {
        normalize_model_id(value)
        for value in (model_ids or [])
        if value not in (None, "")
    }
    normalized_preload_roots = _normalize_path_values(preload_roots) if preload_roots is not None else default_recommended_preload_roots()
    normalized_source_map = load_recommended_source_map(source_map_path)
    normalized_download_staging_dir = (
        Path(download_staging_dir).expanduser()
        if download_staging_dir is not None
        else default_recommended_download_staging_dir(manager.model_dir)
    )
    plan_models: list[dict[str, Any]] = []
    actionable_count = 0
    pending_count = 0
    unsupported_count = 0
    manual_count = 0
    selected_model_count = 0

    for entry in list(catalog_summary.get("models") or []):
        model_id = str(entry.get("model_id") or "")
        selected = not selected_ids or model_id in selected_ids
        if selected:
            selected_model_count += 1
        installed = bool(entry.get("installed"))
        source_resolutions = [
            _resolve_recommended_distribution_source(
                entry,
                source,
                preload_roots=normalized_preload_roots,
                source_map=normalized_source_map,
            )
            for source in list(entry.get("sources") or [])
            if isinstance(source, dict)
        ]
        actionable_resolution = next(
            (item for item in source_resolutions if item.get("actionable")),
            None,
        )
        fallback_resolution = next(
            (item for item in source_resolutions if item.get("status") == "manual-required"),
            None,
        ) or next((item for item in source_resolutions if item.get("status") == "unsupported"), None)
        chosen_resolution = actionable_resolution or fallback_resolution or (
            source_resolutions[0] if source_resolutions else None
        )

        if installed:
            status = "installed"
            action = "none"
            actionable = False
        elif chosen_resolution is None:
            status = "manual-required"
            action = "manual"
            actionable = False
        else:
            status = str(chosen_resolution.get("status") or "manual-required")
            action = str(chosen_resolution.get("action") or "manual")
            actionable = bool(chosen_resolution.get("actionable", False))

        if selected and actionable:
            actionable_count += 1
        elif selected and status == "unsupported":
            unsupported_count += 1
        elif selected and status == "manual-required":
            manual_count += 1
        elif selected and status not in {"installed"}:
            pending_count += 1

        plan_models.append(
            {
                **entry,
                "selected": selected,
                "status": status,
                "action": action,
                "actionable": actionable,
                "resolved_source": chosen_resolution,
                "source_resolutions": source_resolutions,
            }
        )

    return {
        "catalog_id": catalog_summary.get("catalog_id"),
        "catalog_label": catalog_summary.get("catalog_label"),
        "catalog_status": catalog_summary.get("source_status"),
        "catalog_error": catalog_summary.get("source_error"),
        "source_map_status": normalized_source_map.get("source_status"),
        "source_map_error": normalized_source_map.get("source_error"),
        "source_map_path": normalized_source_map.get("source_path"),
        "preload_roots": [str(item) for item in normalized_preload_roots],
        "download_staging_dir": str(normalized_download_staging_dir),
        "selected_model_count": selected_model_count,
        "model_count": len(plan_models),
        "actionable_count": actionable_count,
        "pending_count": pending_count,
        "manual_count": manual_count,
        "unsupported_count": unsupported_count,
        "installed_count": int(catalog_summary.get("installed_count", 0)),
        "models": plan_models,
    }


def _download_recommended_source(
    entry: dict[str, Any],
    resolution: dict[str, Any],
    *,
    download_staging_dir: Path,
) -> Path:
    resolved_value = str(resolution.get("resolved_value") or "")
    if not resolved_value:
        raise ValueError("missing resolved source value")
    filename = str(resolution.get("filename") or "").strip()
    if not filename:
        filename = f"{entry.get('model_id')}{_preferred_model_suffix(entry, resolved_value)}"
    target_path = download_staging_dir / filename
    target_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        resolved_value,
        headers={"User-Agent": "AIOSModelManager/0.3"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=30.0) as response, open(target_path, "wb") as output:
            shutil.copyfileobj(response, output)
    except HTTPError as error:
        raise RuntimeError(f"download failed: HTTP {error.code} {resolved_value}") from error
    except URLError as error:
        raise RuntimeError(f"download failed: {resolved_value} ({error.reason})") from error
    return target_path


def _apply_recommended_default_policy(
    manager: "ModelManager",
    entry: dict[str, Any],
    *,
    set_default_policy: str,
) -> list[str]:
    applied: list[str] = []
    if not bool(entry.get("default_recommended")):
        return applied
    explicit_defaults = dict(manager.export_inventory().get("defaults") or {})
    for capability in list(entry.get("capabilities") or []):
        if set_default_policy == "never":
            continue
        if set_default_policy == "if-missing" and explicit_defaults.get(capability):
            continue
        manager.set_default_model(capability, str(entry.get("model_id") or ""))
        applied.append(capability)
    return applied


def apply_recommended_distribution(
    manager: "ModelManager",
    *,
    recommended_catalog_path: str | Path | None = None,
    preload_roots: list[str | Path] | None = None,
    source_map_path: str | Path | None = None,
    download_staging_dir: str | Path | None = None,
    model_ids: list[str] | None = None,
    set_default_policy: str = "if-missing",
) -> dict[str, Any]:
    if set_default_policy not in {"never", "if-missing", "always"}:
        raise ValueError(f"unsupported set_default_policy: {set_default_policy}")
    plan = build_recommended_distribution_plan(
        manager,
        recommended_catalog_path=recommended_catalog_path,
        preload_roots=preload_roots,
        source_map_path=source_map_path,
        download_staging_dir=download_staging_dir,
        model_ids=model_ids,
    )
    staging_dir = Path(plan["download_staging_dir"])
    results: list[dict[str, Any]] = []
    changed = False
    imported_count = 0
    downloaded_count = 0
    skipped_count = 0
    default_updates = 0

    for entry in list(plan.get("models") or []):
        if not entry.get("selected"):
            continue
        model_id = str(entry.get("model_id") or "")
        result: dict[str, Any] = {
            "model_id": model_id,
            "display_name": entry.get("display_name") or model_id,
            "status": None,
            "action": entry.get("action"),
            "detail": None,
        }
        try:
            if entry.get("installed"):
                result["status"] = "skipped-installed"
                result["detail"] = "already-installed"
                skipped_count += 1
            elif not entry.get("actionable"):
                result["status"] = f"skipped-{entry.get('status') or 'manual-required'}"
                resolved_source = entry.get("resolved_source") or {}
                result["detail"] = resolved_source.get("detail") or entry.get("status")
                skipped_count += 1
            elif entry.get("action") == "import":
                resolved_source = entry.get("resolved_source") or {}
                source_path = Path(str(resolved_source.get("source_path") or "")).expanduser()
                imported = manager.import_model(
                    source_path,
                    model_id=model_id,
                    capabilities=list(entry.get("capabilities") or []),
                    aliases=list(entry.get("aliases") or []),
                    set_default=False,
                )
                defaults = _apply_recommended_default_policy(
                    manager,
                    entry,
                    set_default_policy=set_default_policy,
                )
                changed = True
                imported_count += 1
                default_updates += len(defaults)
                result["status"] = "imported"
                result["detail"] = str(source_path)
                result["imported"] = imported.to_dict()
                result["default_capabilities"] = defaults
            elif entry.get("action") == "download":
                resolved_source = entry.get("resolved_source") or {}
                fetched_path = _download_recommended_source(
                    entry,
                    resolved_source,
                    download_staging_dir=staging_dir,
                )
                imported = manager.import_model(
                    fetched_path,
                    model_id=model_id,
                    capabilities=list(entry.get("capabilities") or []),
                    aliases=list(entry.get("aliases") or []),
                    set_default=False,
                )
                defaults = _apply_recommended_default_policy(
                    manager,
                    entry,
                    set_default_policy=set_default_policy,
                )
                changed = True
                imported_count += 1
                downloaded_count += 1
                default_updates += len(defaults)
                result["status"] = "downloaded-and-imported"
                result["detail"] = str(fetched_path)
                result["imported"] = imported.to_dict()
                result["default_capabilities"] = defaults
            else:
                result["status"] = f"skipped-{entry.get('action') or 'manual'}"
                result["detail"] = "unsupported-apply-action"
                skipped_count += 1
        except Exception as error:
            result["status"] = "error"
            result["detail"] = str(error)
        results.append(result)

    registry_path = manager.save_registry() if changed else None
    inventory = manager.export_inventory()
    return {
        "status": "applied" if changed else "no-op",
        "registry_path": str(registry_path) if registry_path is not None else None,
        "model_count": len(results),
        "imported_count": imported_count,
        "downloaded_count": downloaded_count,
        "skipped_count": skipped_count,
        "default_update_count": default_updates,
        "local_model_count": inventory.get("model_count", 0),
        "defaults": inventory.get("defaults", {}),
        "results": results,
        "plan": plan,
    }


class ModelManager:
    def __init__(self, model_dir: str | Path | None = None, registry_path: str | Path | None = None):
        self._model_dir = Path(model_dir) if model_dir else Path(DEFAULT_MODEL_DIR)
        if registry_path:
            self._registry_path = Path(registry_path)
        else:
            env_reg = os.environ.get("AIOS_MODEL_REGISTRY")
            if env_reg:
                self._registry_path = Path(env_reg)
            else:
                self._registry_path = self._model_dir / DEFAULT_REGISTRY_FILENAME
        self._models: dict[str, ModelEntry] = {}
        self._alias_map: dict[str, str] = {}
        self._defaults: dict[str, str] = {}

    @property
    def model_dir(self) -> Path:
        return self._model_dir

    @property
    def registry_path(self) -> Path:
        return self._registry_path

    def scan_directory(self, path: str | Path | None = None) -> list[ModelEntry]:
        scan_root = Path(path) if path else self._model_dir
        found: list[ModelEntry] = []
        if not scan_root.is_dir():
            return found
        for item in sorted(scan_root.rglob("*")):
            if not item.is_file():
                continue
            if item.suffix.lower() not in MODEL_EXTENSIONS:
                continue
            fmt = detect_format(item)
            existing = self._models.get(item.stem)
            entry = ModelEntry(
                model_id=item.stem,
                path=str(item),
                format=fmt,
                size_bytes=item.stat().st_size,
                aliases=list(existing.aliases) if existing else [],
                capabilities=list(existing.capabilities) if existing else [],
                quantization=existing.quantization if existing else "",
                parameters_estimate=existing.parameters_estimate if existing else "",
                source_kind=existing.source_kind if existing else "local-scan",
                source_uri=existing.source_uri if existing else "",
            )
            found.append(entry)
            self.register_model(entry)
        return found

    def register_model(self, entry: ModelEntry) -> None:
        existing = self._models.get(entry.model_id)
        if existing:
            for alias in existing.aliases:
                if self._alias_map.get(alias) == entry.model_id:
                    self._alias_map.pop(alias, None)
        self._models[entry.model_id] = entry
        for alias in entry.aliases:
            self._alias_map[alias] = entry.model_id

    def resolve_model_id(self, model_id_or_alias: str) -> str | None:
        if model_id_or_alias in self._models:
            return model_id_or_alias
        resolved = self._alias_map.get(model_id_or_alias)
        if resolved and resolved in self._models:
            return resolved
        return None

    def get_model(self, model_id_or_alias: str) -> ModelEntry | None:
        resolved = self.resolve_model_id(model_id_or_alias)
        if resolved is not None:
            return self._models[resolved]
        return None

    def set_default_model(self, capability: str, model_id: str) -> None:
        normalized_capability = normalize_capabilities([capability])[0]
        resolved_model_id = self.resolve_model_id(model_id)
        if resolved_model_id is None:
            raise KeyError(f"unknown model: {model_id}")
        self._defaults[normalized_capability] = resolved_model_id

    def get_default_model(self, capability: str) -> ModelEntry | None:
        model_id = self._defaults.get(capability)
        if model_id:
            return self.get_model(model_id)
        candidates = self.list_models(capability=capability)
        if candidates:
            return candidates[0]
        return None

    def list_models(self, capability: str | None = None) -> list[ModelEntry]:
        if capability is None:
            return list(self._models.values())
        return [m for m in self._models.values() if capability in m.capabilities]

    def validate_model(self, path: str | Path) -> dict[str, Any]:
        p = Path(path)
        result: dict[str, Any] = {
            "path": str(p),
            "exists": p.exists(),
            "valid": False,
            "format": "unknown",
            "size_bytes": 0,
            "sha256": "",
        }
        if not p.exists() or not p.is_file():
            return result
        result["size_bytes"] = p.stat().st_size
        result["format"] = detect_format(p)
        result["sha256"] = compute_sha256(p)
        result["valid"] = result["format"] != "unknown"
        return result

    def import_model(
        self,
        source: str | Path,
        *,
        model_id: str | None = None,
        capabilities: list[str] | None = None,
        aliases: list[str] | None = None,
        set_default: bool = False,
        symlink: bool = False,
        quantization: str = "",
        parameters_estimate: str = "",
    ) -> ModelEntry:
        source_path = Path(source).expanduser().resolve()
        validation = self.validate_model(source_path)
        if not validation["valid"]:
            raise ValueError(f"invalid model file: {source_path}")

        normalized_model_id = normalize_model_id(model_id or source_path.stem)
        normalized_capabilities = normalize_capabilities(capabilities or ["text-generation"])
        normalized_aliases = normalize_aliases(aliases or [])

        self._model_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._model_dir / f"{normalized_model_id}{source_path.suffix.lower()}"

        if target_path.exists() or target_path.is_symlink():
            if target_path.resolve() != source_path:
                raise FileExistsError(f"target model already exists: {target_path}")
        elif symlink:
            target_path.symlink_to(source_path)
        else:
            shutil.copy2(source_path, target_path)

        imported_validation = self.validate_model(target_path)
        entry = ModelEntry(
            model_id=normalized_model_id,
            path=str(target_path),
            format=imported_validation["format"],
            size_bytes=imported_validation["size_bytes"],
            sha256=imported_validation["sha256"],
            aliases=normalized_aliases,
            capabilities=normalized_capabilities,
            quantization=quantization,
            parameters_estimate=parameters_estimate,
            source_kind="local-import-symlink" if symlink else "local-import-copy",
            source_uri=str(source_path),
        )
        self.register_model(entry)
        if set_default:
            for capability in normalized_capabilities:
                self.set_default_model(capability, entry.model_id)
        return entry

    def delete_model(self, model_id_or_alias: str, *, remove_file: bool = True) -> ModelEntry:
        resolved_model_id = self.resolve_model_id(model_id_or_alias)
        if resolved_model_id is None:
            raise KeyError(f"unknown model: {model_id_or_alias}")

        entry = self._models.pop(resolved_model_id)
        for alias in entry.aliases:
            if self._alias_map.get(alias) == resolved_model_id:
                self._alias_map.pop(alias, None)

        for capability, default_model_id in list(self._defaults.items()):
            if default_model_id != resolved_model_id:
                continue
            replacement = next(
                (
                    candidate.model_id
                    for candidate in self.list_models(capability=capability)
                    if candidate.model_id != resolved_model_id
                ),
                None,
            )
            if replacement is None:
                self._defaults.pop(capability, None)
            else:
                self._defaults[capability] = replacement

        if remove_file:
            self._remove_model_file(entry)
        return entry

    def _remove_model_file(self, entry: ModelEntry) -> None:
        model_path = Path(entry.path)
        if not model_path.is_absolute():
            model_path = (self._model_dir / model_path).resolve()
        if not model_path.exists() and not model_path.is_symlink():
            return
        try:
            model_path.relative_to(self._model_dir.resolve())
        except ValueError:
            return
        if model_path.is_dir():
            return
        model_path.unlink(missing_ok=True)

    def export_inventory(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "timestamp_epoch": int(time.time()),
            "model_dir": str(self._model_dir),
            "model_count": len(self._models),
            "models": [m.to_dict() for m in self._models.values()],
            "defaults": dict(self._defaults),
        }

    def save_registry(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self._registry_path
        data = {
            "schema_version": "1.0.0",
            "models": {mid: entry.to_dict() for mid, entry in self._models.items()},
            "aliases": dict(self._alias_map),
            "defaults": dict(self._defaults),
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix in (".yaml", ".yml") and _HAS_YAML:
            with open(target, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            return target
        if target.suffix in (".yaml", ".yml"):
            json_target = target.with_suffix(".json")
            with open(json_target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return json_target
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return target

    def load_registry(self, path: str | Path | None = None) -> int:
        target = Path(path) if path else self._registry_path
        if not target.exists():
            json_fallback = target.with_suffix(".json")
            if json_fallback.exists():
                target = json_fallback
            else:
                return 0
        with open(target, "r", encoding="utf-8") as f:
            if target.suffix in (".yaml", ".yml"):
                if not _HAS_YAML:
                    raise RuntimeError("PyYAML is required to load YAML registries")
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        if not data or not isinstance(data, dict):
            return 0
        models_data = data.get("models", {})
        for mid, mdict in models_data.items():
            mdict.setdefault("model_id", mid)
            entry = ModelEntry.from_dict(mdict)
            self.register_model(entry)
        self._alias_map.update(data.get("aliases", {}))
        self._defaults.update(data.get("defaults", {}))
        return len(models_data)


def normalize_model_id(model_id: str) -> str:
    normalized = "".join(
        char.lower() if char.isalnum() else "-"
        for char in model_id.strip()
    ).strip("-")
    if not normalized:
        raise ValueError("model_id must not be empty")
    return normalized


def normalize_capabilities(capabilities: list[str]) -> list[str]:
    normalized: list[str] = []
    for capability in capabilities:
        if capability not in CAPABILITY_VALUES:
            raise ValueError(f"unsupported capability: {capability}")
        if capability not in normalized:
            normalized.append(capability)
    return normalized


def normalize_aliases(aliases: list[str]) -> list[str]:
    normalized: list[str] = []
    for alias in aliases:
        clean = alias.strip()
        if not clean:
            continue
        if clean not in normalized:
            normalized.append(clean)
    return normalized


def _cli_scan(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    entries = mgr.scan_directory(args.path or args.model_dir)
    for e in entries:
        print(f"  {e.model_id:30s}  {e.format:12s}  {e.size_bytes:>12d}  {e.path}")
    print(f"\n{len(entries)} model(s) found.")
    if args.save:
        out = mgr.save_registry()
        print(f"Registry saved to {out}")
    return 0


def _cli_list(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    loaded = mgr.load_registry()
    if loaded == 0:
        print("No registry found. Run 'scan' first.", file=sys.stderr)
        return 1
    models = mgr.list_models(capability=args.capability)
    for m in models:
        aliases = ", ".join(m.aliases) if m.aliases else "-"
        caps = ", ".join(m.capabilities) if m.capabilities else "-"
        print(f"  {m.model_id:30s}  {m.format:12s}  aliases={aliases}  caps={caps}")
    print(f"\n{len(models)} model(s).")
    return 0


def _cli_validate(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    result = mgr.validate_model(args.path)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


def _cli_inventory(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    mgr.load_registry()
    mgr.scan_directory()
    inv = mgr.export_inventory()
    print(json.dumps(inv, indent=2))
    return 0


def _cli_catalog(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    mgr.load_registry()
    mgr.scan_directory()
    catalog = load_recommended_model_catalog(args.recommended_catalog)
    summary = summarize_recommended_model_catalog(catalog, inventory=mgr.export_inventory())
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary.get("source_status") == "ready" else 1


def _recommended_preload_roots_from_args(args: argparse.Namespace) -> list[Path]:
    return _normalize_path_values(args.recommended_preload_root) if args.recommended_preload_root else default_recommended_preload_roots()


def _recommended_source_map_from_args(args: argparse.Namespace) -> Path | None:
    return Path(args.recommended_source_map) if args.recommended_source_map else None


def _recommended_download_staging_dir_from_args(args: argparse.Namespace) -> Path | None:
    return Path(args.recommended_download_staging_dir) if args.recommended_download_staging_dir else None


def _cli_recommend_plan(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    mgr.load_registry()
    mgr.scan_directory()
    plan = build_recommended_distribution_plan(
        mgr,
        recommended_catalog_path=args.recommended_catalog,
        preload_roots=_recommended_preload_roots_from_args(args),
        source_map_path=_recommended_source_map_from_args(args),
        download_staging_dir=_recommended_download_staging_dir_from_args(args),
        model_ids=args.model_id,
    )
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0 if plan.get("catalog_status") == "ready" else 1


def _cli_recommend_apply(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    mgr.load_registry()
    mgr.scan_directory()
    payload = apply_recommended_distribution(
        mgr,
        recommended_catalog_path=args.recommended_catalog,
        preload_roots=_recommended_preload_roots_from_args(args),
        source_map_path=_recommended_source_map_from_args(args),
        download_staging_dir=_recommended_download_staging_dir_from_args(args),
        model_ids=args.model_id,
        set_default_policy=args.set_default_policy,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("status") != "error" else 1


def _cli_import(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    mgr.load_registry()
    entry = mgr.import_model(
        args.source,
        model_id=args.model_id,
        capabilities=args.capability,
        aliases=args.alias,
        set_default=args.set_default,
        symlink=args.symlink,
        quantization=args.quantization or "",
        parameters_estimate=args.parameters_estimate or "",
    )
    registry_path = mgr.save_registry()
    print(
        json.dumps(
            {
                "imported": entry.to_dict(),
                "registry_path": str(registry_path),
                "defaults": mgr.export_inventory()["defaults"],
            },
            indent=2,
        )
    )
    return 0


def _cli_set_default(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    mgr.load_registry()
    mgr.scan_directory()
    mgr.set_default_model(args.capability, args.model_id)
    registry_path = mgr.save_registry()
    default_entry = mgr.get_default_model(args.capability)
    print(
        json.dumps(
            {
                "capability": args.capability,
                "model_id": default_entry.model_id if default_entry is not None else None,
                "registry_path": str(registry_path),
                "defaults": mgr.export_inventory()["defaults"],
            },
            indent=2,
        )
    )
    return 0


def _cli_delete(args: argparse.Namespace) -> int:
    mgr = ModelManager(model_dir=args.model_dir)
    mgr.load_registry()
    mgr.scan_directory()
    entry = mgr.delete_model(args.model_id, remove_file=not args.keep_file)
    registry_path = mgr.save_registry()
    print(
        json.dumps(
            {
                "deleted": entry.to_dict(),
                "removed_file": not args.keep_file,
                "registry_path": str(registry_path),
                "defaults": mgr.export_inventory()["defaults"],
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="model_manager",
        description="AIOS local model manager",
    )
    parser.add_argument(
        "--model-dir",
        default=os.environ.get("AIOS_MODEL_DIR", DEFAULT_MODEL_DIR),
        help="Root model directory",
    )
    parser.add_argument(
        "--recommended-catalog",
        default=str(default_recommended_catalog_path()),
        help="Recommended model catalog path",
    )
    parser.add_argument(
        "--recommended-preload-root",
        action="append",
        default=[],
        help="Search root for preload/manual recommended model artifacts; repeat to add multiple roots",
    )
    parser.add_argument(
        "--recommended-source-map",
        help="Optional YAML/JSON mapping file for symbolic recommended model download sources",
    )
    parser.add_argument(
        "--recommended-download-staging-dir",
        help="Directory used to stage downloaded recommended model artifacts",
    )
    sub = parser.add_subparsers(dest="command")

    scan_p = sub.add_parser("scan", help="Scan directory for model files")
    scan_p.add_argument("path", nargs="?", help="Directory to scan (default: AIOS_MODEL_DIR)")
    scan_p.add_argument("--save", action="store_true", help="Save registry after scan")

    list_p = sub.add_parser("list", help="List registered models")
    list_p.add_argument("--capability", help="Filter by capability")

    val_p = sub.add_parser("validate", help="Validate a model file")
    val_p.add_argument("path", help="Path to model file")

    sub.add_parser("inventory", help="Export JSON inventory")
    sub.add_parser("catalog", help="Export the recommended model catalog summary")

    recommend_plan_p = sub.add_parser(
        "recommend-plan",
        help="Build an executable distribution plan for recommended models",
    )
    recommend_plan_p.add_argument(
        "--model-id",
        action="append",
        default=[],
        help="Only plan the selected recommended model id; repeat to select multiple models",
    )

    recommend_apply_p = sub.add_parser(
        "recommend-apply",
        help="Apply executable recommended model distribution actions",
    )
    recommend_apply_p.add_argument(
        "--model-id",
        action="append",
        default=[],
        help="Only apply the selected recommended model id; repeat to select multiple models",
    )
    recommend_apply_p.add_argument(
        "--set-default-policy",
        choices=["never", "if-missing", "always"],
        default="if-missing",
        help="How recommended default models update capability defaults after import",
    )

    import_p = sub.add_parser("import", help="Import a local model into the AIOS model store")
    import_p.add_argument("source", help="Path to the local model file")
    import_p.add_argument("--model-id", help="Stable model identifier to register")
    import_p.add_argument(
        "--capability",
        action="append",
        choices=sorted(CAPABILITY_VALUES),
        help="Declared model capability; repeat to add multiple capabilities",
    )
    import_p.add_argument(
        "--alias",
        action="append",
        default=[],
        help="Optional model alias; repeat to add multiple aliases",
    )
    import_p.add_argument("--quantization", help="Quantization label written into the registry")
    import_p.add_argument(
        "--parameters-estimate",
        help="Optional parameter-size hint written into the registry",
    )
    import_p.add_argument(
        "--set-default",
        action="store_true",
        help="Set the imported model as default for each declared capability",
    )
    import_p.add_argument(
        "--symlink",
        action="store_true",
        help="Symlink the source file into AIOS_MODEL_DIR instead of copying it",
    )

    set_default_p = sub.add_parser("set-default", help="Set the default model for a capability")
    set_default_p.add_argument("capability", choices=sorted(CAPABILITY_VALUES))
    set_default_p.add_argument("model_id", help="Model id or alias")

    delete_p = sub.add_parser("delete", help="Delete a registered model")
    delete_p.add_argument("model_id", help="Model id or alias")
    delete_p.add_argument(
        "--keep-file",
        action="store_true",
        help="Keep the model file on disk and only remove the registry entry",
    )

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1

    dispatch = {
        "scan": _cli_scan,
        "list": _cli_list,
        "validate": _cli_validate,
        "inventory": _cli_inventory,
        "catalog": _cli_catalog,
        "recommend-plan": _cli_recommend_plan,
        "recommend-apply": _cli_recommend_apply,
        "import": _cli_import,
        "set-default": _cli_set_default,
        "delete": _cli_delete,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
