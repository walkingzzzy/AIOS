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
    detect_format,
    compute_sha256,
    GGUF_MAGIC,
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


if __name__ == "__main__":
    unittest.main()
