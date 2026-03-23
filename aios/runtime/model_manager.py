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
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

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

DEFAULT_MODEL_DIR = os.environ.get("AIOS_MODEL_DIR", "/var/lib/aios/models")
DEFAULT_REGISTRY_FILENAME = "model-registry.yaml"


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
            entry = ModelEntry(
                model_id=item.stem,
                path=str(item),
                format=fmt,
                size_bytes=item.stat().st_size,
            )
            found.append(entry)
            self.register_model(entry)
        return found

    def register_model(self, entry: ModelEntry) -> None:
        self._models[entry.model_id] = entry
        for alias in entry.aliases:
            self._alias_map[alias] = entry.model_id

    def get_model(self, model_id_or_alias: str) -> ModelEntry | None:
        if model_id_or_alias in self._models:
            return self._models[model_id_or_alias]
        resolved = self._alias_map.get(model_id_or_alias)
        if resolved and resolved in self._models:
            return self._models[resolved]
        return None

    def set_default_model(self, capability: str, model_id: str) -> None:
        self._defaults[capability] = model_id

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
        if _HAS_YAML:
            with open(target, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        else:
            json_target = target.with_suffix(".json")
            with open(json_target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return json_target
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
            self._models[mid] = entry
        self._alias_map.update(data.get("aliases", {}))
        self._defaults.update(data.get("defaults", {}))
        return len(models_data)


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
    sub = parser.add_subparsers(dest="command")

    scan_p = sub.add_parser("scan", help="Scan directory for model files")
    scan_p.add_argument("path", nargs="?", help="Directory to scan (default: AIOS_MODEL_DIR)")
    scan_p.add_argument("--save", action="store_true", help="Save registry after scan")

    list_p = sub.add_parser("list", help="List registered models")
    list_p.add_argument("--capability", help="Filter by capability")

    val_p = sub.add_parser("validate", help="Validate a model file")
    val_p.add_argument("path", help="Path to model file")

    sub.add_parser("inventory", help="Export JSON inventory")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1

    dispatch = {
        "scan": _cli_scan,
        "list": _cli_list,
        "validate": _cli_validate,
        "inventory": _cli_inventory,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
