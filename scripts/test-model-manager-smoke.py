#!/usr/bin/env python3
"""
Smoke tests for the AIOS model manager (ModelEntry, ModelManager, format detection).
"""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from aios.runtime.model_manager import (
    ModelEntry,
    ModelManager,
    apply_recommended_distribution,
    build_recommended_distribution_plan,
    GGUF_MAGIC,
    compute_sha256,
    detect_format,
    load_recommended_model_catalog,
    summarize_recommended_model_catalog,
)


def _write_fake_gguf(path: Path, payload: bytes = b"\x00" * 64) -> None:
    with open(path, "wb") as f:
        f.write(GGUF_MAGIC)
        f.write(payload)


def _write_fake_safetensors(path: Path) -> None:
    with open(path, "wb") as f:
        f.write(b'{"__metadata__": {}}')


def _write_fake_bin(path: Path) -> None:
    with open(path, "wb") as f:
        f.write(b"\x89\x50\x4e\x47" + b"\x00" * 32)


class TestModelEntry(unittest.TestCase):
    def test_round_trip(self):
        entry = ModelEntry(
            model_id="test-model",
            path="/tmp/test.gguf",
            format="gguf",
            size_bytes=1024,
            sha256="abc123",
            aliases=["tm", "test"],
            capabilities=["text-generation"],
            quantization="Q4_K_M",
            parameters_estimate="7B",
        )
        d = entry.to_dict()
        restored = ModelEntry.from_dict(d)
        self.assertEqual(entry.model_id, restored.model_id)
        self.assertEqual(entry.path, restored.path)
        self.assertEqual(entry.format, restored.format)
        self.assertEqual(entry.sha256, restored.sha256)
        self.assertEqual(entry.aliases, restored.aliases)
        self.assertEqual(entry.capabilities, restored.capabilities)
        self.assertEqual(entry.quantization, restored.quantization)

    def test_defaults(self):
        entry = ModelEntry(model_id="bare", path="/tmp/bare.bin")
        self.assertEqual(entry.format, "unknown")
        self.assertEqual(entry.size_bytes, 0)
        self.assertEqual(entry.aliases, [])
        self.assertEqual(entry.capabilities, [])

    def test_from_dict_missing_optional(self):
        entry = ModelEntry.from_dict({"model_id": "x", "path": "/x"})
        self.assertEqual(entry.format, "unknown")
        self.assertEqual(entry.sha256, "")


class TestFormatDetection(unittest.TestCase):
    def test_gguf_by_extension_and_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as tmp:
            tmp.write(GGUF_MAGIC + b"\x00" * 16)
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "gguf")
        finally:
            p.unlink()

    def test_gguf_bad_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as tmp:
            tmp.write(b"NOPE" + b"\x00" * 16)
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "unknown")
        finally:
            p.unlink()

    def test_safetensors_by_extension_and_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".safetensors", delete=False) as tmp:
            tmp.write(b'{"metadata": {}}')
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "safetensors")
        finally:
            p.unlink()

    def test_safetensors_bad_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".safetensors", delete=False) as tmp:
            tmp.write(b"\x00binary")
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "unknown")
        finally:
            p.unlink()

    def test_bin_gguf_magic_detection(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(GGUF_MAGIC + b"\x00" * 16)
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "gguf")
        finally:
            p.unlink()

    def test_bin_safetensors_magic_detection(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(b'{"data": 1}')
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "safetensors")
        finally:
            p.unlink()

    def test_bin_plain_detection(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(b"\x89PNG" + b"\x00" * 16)
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "bin")
        finally:
            p.unlink()

    def test_unknown_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"just text")
            tmp.flush()
            p = Path(tmp.name)
        try:
            self.assertEqual(detect_format(p), "unknown")
        finally:
            p.unlink()


class TestModelManager(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aios_model_test_")
        self.tmpdir = Path(self._tmpdir)
        self.mgr = ModelManager(model_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_init_paths(self):
        self.assertEqual(self.mgr.model_dir, self.tmpdir)
        self.assertEqual(self.mgr.registry_path, self.tmpdir / "model-registry.yaml")

    def test_scan_empty_directory(self):
        entries = self.mgr.scan_directory()
        self.assertEqual(entries, [])

    def test_scan_finds_models(self):
        _write_fake_gguf(self.tmpdir / "alpha.gguf")
        _write_fake_safetensors(self.tmpdir / "beta.safetensors")
        _write_fake_bin(self.tmpdir / "gamma.bin")
        (self.tmpdir / "readme.txt").write_text("not a model")

        entries = self.mgr.scan_directory()
        ids = {e.model_id for e in entries}
        self.assertIn("alpha", ids)
        self.assertIn("beta", ids)
        self.assertIn("gamma", ids)
        self.assertEqual(len(entries), 3)

    def test_scan_subdirectories(self):
        subdir = self.tmpdir / "nested" / "deep"
        subdir.mkdir(parents=True)
        _write_fake_gguf(subdir / "nested_model.gguf")
        entries = self.mgr.scan_directory()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].model_id, "nested_model")

    def test_register_and_get(self):
        entry = ModelEntry(model_id="my-model", path="/tmp/m.gguf", format="gguf")
        self.mgr.register_model(entry)
        result = self.mgr.get_model("my-model")
        self.assertIsNotNone(result)
        self.assertEqual(result.model_id, "my-model")

    def test_alias_resolution(self):
        entry = ModelEntry(
            model_id="full-name-model",
            path="/tmp/m.gguf",
            aliases=["short", "alt"],
        )
        self.mgr.register_model(entry)
        self.assertIsNotNone(self.mgr.get_model("short"))
        self.assertIsNotNone(self.mgr.get_model("alt"))
        self.assertEqual(self.mgr.get_model("short").model_id, "full-name-model")

    def test_get_model_not_found(self):
        self.assertIsNone(self.mgr.get_model("nonexistent"))

    def test_list_models_all(self):
        self.mgr.register_model(ModelEntry(model_id="a", path="/a"))
        self.mgr.register_model(ModelEntry(model_id="b", path="/b"))
        self.assertEqual(len(self.mgr.list_models()), 2)

    def test_list_models_by_capability(self):
        self.mgr.register_model(ModelEntry(model_id="gen", path="/g", capabilities=["text-generation"]))
        self.mgr.register_model(ModelEntry(model_id="emb", path="/e", capabilities=["embedding"]))
        self.mgr.register_model(ModelEntry(model_id="both", path="/b", capabilities=["text-generation", "embedding"]))

        gen_models = self.mgr.list_models(capability="text-generation")
        self.assertEqual(len(gen_models), 2)

        emb_models = self.mgr.list_models(capability="embedding")
        self.assertEqual(len(emb_models), 2)

    def test_default_model(self):
        entry = ModelEntry(model_id="default-gen", path="/dg", capabilities=["text-generation"])
        self.mgr.register_model(entry)
        self.mgr.set_default_model("text-generation", "default-gen")
        result = self.mgr.get_default_model("text-generation")
        self.assertIsNotNone(result)
        self.assertEqual(result.model_id, "default-gen")

    def test_default_model_fallback(self):
        entry = ModelEntry(model_id="only-emb", path="/oe", capabilities=["embedding"])
        self.mgr.register_model(entry)
        result = self.mgr.get_default_model("embedding")
        self.assertIsNotNone(result)
        self.assertEqual(result.model_id, "only-emb")

    def test_default_model_missing(self):
        self.assertIsNone(self.mgr.get_default_model("reranking"))

    def test_validate_model_valid_gguf(self):
        p = self.tmpdir / "valid.gguf"
        _write_fake_gguf(p)
        result = self.mgr.validate_model(p)
        self.assertTrue(result["valid"])
        self.assertEqual(result["format"], "gguf")
        self.assertGreater(result["size_bytes"], 0)
        self.assertTrue(len(result["sha256"]) == 64)

    def test_validate_model_missing(self):
        result = self.mgr.validate_model(self.tmpdir / "nope.gguf")
        self.assertFalse(result["valid"])
        self.assertFalse(result["exists"])

    def test_inventory_export(self):
        _write_fake_gguf(self.tmpdir / "inv_model.gguf")
        self.mgr.scan_directory()
        inv = self.mgr.export_inventory()
        self.assertIn("schema_version", inv)
        self.assertIn("timestamp_epoch", inv)
        self.assertEqual(inv["model_count"], 1)
        self.assertIsInstance(inv["models"], list)
        self.assertEqual(inv["models"][0]["model_id"], "inv_model")
        json_str = json.dumps(inv)
        self.assertIsInstance(json.loads(json_str), dict)

    def test_registry_save_load_roundtrip(self):
        self.mgr.register_model(ModelEntry(
            model_id="persist-me",
            path="/tmp/persist.gguf",
            format="gguf",
            size_bytes=4096,
            sha256="deadbeef" * 8,
            aliases=["pm"],
            capabilities=["text-generation"],
            quantization="Q5_K_S",
            parameters_estimate="13B",
        ))
        self.mgr.set_default_model("text-generation", "persist-me")

        saved_path = self.mgr.save_registry()
        self.assertTrue(saved_path.exists())

        mgr2 = ModelManager(model_dir=self.tmpdir)
        loaded = mgr2.load_registry(saved_path)
        self.assertEqual(loaded, 1)

        restored = mgr2.get_model("persist-me")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.format, "gguf")
        self.assertEqual(restored.quantization, "Q5_K_S")
        self.assertEqual(restored.capabilities, ["text-generation"])

        self.assertIsNotNone(mgr2.get_model("pm"))

        default = mgr2.get_default_model("text-generation")
        self.assertIsNotNone(default)
        self.assertEqual(default.model_id, "persist-me")

    def test_load_registry_missing(self):
        mgr = ModelManager(model_dir=self.tmpdir)
        loaded = mgr.load_registry(self.tmpdir / "nonexistent.yaml")
        self.assertEqual(loaded, 0)

    def test_scan_nonexistent_directory(self):
        entries = self.mgr.scan_directory(self.tmpdir / "does_not_exist")
        self.assertEqual(entries, [])

    def test_import_model_copies_into_store_and_sets_default(self):
        source = self.tmpdir / "source-model.gguf"
        _write_fake_gguf(source)

        entry = self.mgr.import_model(
            source,
            model_id="Qwen Mini",
            capabilities=["text-generation"],
            aliases=["default-text"],
            set_default=True,
            quantization="Q4_K_M",
            parameters_estimate="7B",
        )

        self.assertEqual(entry.model_id, "qwen-mini")
        self.assertTrue(Path(entry.path).exists())
        self.assertEqual(entry.source_kind, "local-import-copy")
        self.assertEqual(entry.source_uri, str(source.resolve()))
        self.assertEqual(entry.aliases, ["default-text"])
        self.assertEqual(entry.capabilities, ["text-generation"])
        self.assertEqual(self.mgr.get_default_model("text-generation").model_id, "qwen-mini")

    def test_scan_preserves_imported_metadata(self):
        source = self.tmpdir / "preserve-source.gguf"
        _write_fake_gguf(source)
        imported = self.mgr.import_model(
            source,
            model_id="Preserve Me",
            capabilities=["text-generation", "embedding"],
            aliases=["preserve"],
            set_default=True,
        )

        self.mgr.scan_directory()
        restored = self.mgr.get_model(imported.model_id)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.aliases, ["preserve"])
        self.assertEqual(restored.capabilities, ["text-generation", "embedding"])
        self.assertEqual(restored.source_kind, "local-import-copy")
        self.assertEqual(self.mgr.get_model("preserve").model_id, imported.model_id)

    def test_set_default_model_resolves_alias(self):
        source = self.tmpdir / "alias-source.gguf"
        _write_fake_gguf(source)
        imported = self.mgr.import_model(
            source,
            model_id="Alias Default",
            capabilities=["text-generation"],
            aliases=["alias-default"],
        )

        self.mgr.set_default_model("text-generation", "alias-default")

        default_model = self.mgr.get_default_model("text-generation")
        self.assertIsNotNone(default_model)
        self.assertEqual(default_model.model_id, imported.model_id)

    def test_delete_model_removes_file_alias_and_default(self):
        source = self.tmpdir / "delete-source.gguf"
        _write_fake_gguf(source)
        imported = self.mgr.import_model(
            source,
            model_id="Delete Me",
            capabilities=["text-generation"],
            aliases=["delete-alias"],
            set_default=True,
        )

        deleted = self.mgr.delete_model("delete-alias")

        self.assertEqual(deleted.model_id, imported.model_id)
        self.assertIsNone(self.mgr.get_model(imported.model_id))
        self.assertIsNone(self.mgr.get_model("delete-alias"))
        self.assertIsNone(self.mgr.get_default_model("text-generation"))
        self.assertFalse(Path(imported.path).exists())

    def test_delete_model_keeps_file_when_requested(self):
        source = self.tmpdir / "delete-keep.gguf"
        _write_fake_gguf(source)
        imported = self.mgr.import_model(
            source,
            model_id="Keep File",
            capabilities=["text-generation"],
        )

        deleted = self.mgr.delete_model(imported.model_id, remove_file=False)

        self.assertEqual(deleted.model_id, imported.model_id)
        self.assertTrue(Path(imported.path).exists())
        self.assertEqual(self.mgr.export_inventory()["model_count"], 0)


class TestSha256(unittest.TestCase):
    def test_known_hash(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"hello world")
            tmp.flush()
            p = Path(tmp.name)
        try:
            h = compute_sha256(p)
            import hashlib
            expected = hashlib.sha256(b"hello world").hexdigest()
            self.assertEqual(h, expected)
        finally:
            p.unlink()


class TestRecommendedCatalog(unittest.TestCase):
    def test_load_recommended_catalog_from_repo(self):
        catalog = load_recommended_model_catalog(
            REPO_ROOT / "aios" / "runtime" / "recommended-model-catalog.yaml"
        )
        self.assertEqual(catalog["source_status"], "ready")
        self.assertGreaterEqual(len(catalog["models"]), 4)

    def test_catalog_summary_marks_installed_recommendation(self):
        catalog = load_recommended_model_catalog(
            REPO_ROOT / "aios" / "runtime" / "recommended-model-catalog.yaml"
        )
        summary = summarize_recommended_model_catalog(
            catalog,
            inventory={
                "models": [
                    {
                        "model_id": "qwen2-5-7b-instruct",
                        "aliases": ["qwen2.5:7b-instruct"],
                    }
                ]
            },
        )
        self.assertEqual(summary["source_status"], "ready")
        self.assertEqual(summary["installed_count"], 1)
        self.assertIn("qwen2-5-7b-instruct", summary["installed_model_ids"])
        self.assertIn("manual-import", summary["strategy_counts"])
        self.assertEqual(
            summary["default_recommendations"]["text-generation"],
            "qwen2-5-7b-instruct",
        )

    def test_recommended_distribution_plan_resolves_source_map(self):
        with tempfile.TemporaryDirectory(prefix="aios-recommended-plan-") as tempdir:
            root = Path(tempdir)
            model_dir = root / "models"
            model_dir.mkdir(parents=True, exist_ok=True)
            manager = ModelManager(model_dir=model_dir)

            catalog_path = root / "recommended-model-catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "models": [
                            {
                                "model_id": "embed-demo",
                                "display_name": "Embed Demo",
                                "capabilities": ["embedding"],
                                "formats": ["safetensors"],
                                "distribution_strategy": "firstboot-download",
                                "sources": [{"kind": "firstboot-download", "value": "embed-demo"}],
                            }
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            source_map_path = root / "recommended-model-sources.json"
            source_file = root / "embed-demo.safetensors"
            _write_fake_safetensors(source_file)
            source_map_path.write_text(
                json.dumps(
                    {
                        "mappings": {
                            "embed-demo": {
                                "value": str(source_file),
                            }
                        }
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = build_recommended_distribution_plan(
                manager,
                recommended_catalog_path=catalog_path,
                source_map_path=source_map_path,
            )
            self.assertEqual(plan["actionable_count"], 1)
            self.assertEqual(plan["models"][0]["status"], "ready-import")

    def test_apply_recommended_distribution_imports_file(self):
        with tempfile.TemporaryDirectory(prefix="aios-recommended-apply-") as tempdir:
            root = Path(tempdir)
            model_dir = root / "models"
            model_dir.mkdir(parents=True, exist_ok=True)
            manager = ModelManager(model_dir=model_dir)

            source_model = root / "phi-mini.gguf"
            _write_fake_gguf(source_model)
            catalog_path = root / "recommended-model-catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "models": [
                            {
                                "model_id": "phi-mini",
                                "display_name": "Phi Mini",
                                "capabilities": ["text-generation"],
                                "formats": ["gguf"],
                                "distribution_strategy": "preload",
                                "default_recommended": True,
                                "sources": [{"kind": "preload-image", "value": source_model.name}],
                            }
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = apply_recommended_distribution(
                manager,
                recommended_catalog_path=catalog_path,
                preload_roots=[root],
                set_default_policy="always",
            )
            self.assertEqual(payload["status"], "applied")
            self.assertEqual(payload["imported_count"], 1)
            self.assertEqual(manager.get_default_model("text-generation").model_id, "phi-mini")


if __name__ == "__main__":
    unittest.main()
