#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from aios_cargo_bins import (
    cargo_target_bin_dir,
    default_aios_bin_dir,
    default_container_native_bin_dir,
    detect_host_target,
    expected_aios_binaries,
    has_expected_aios_binaries,
    resolve_binary_path,
)


ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = ROOT / "out" / "tmp"


@contextmanager
def temporary_dir(prefix: str):
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class CargoBinResolutionTests(unittest.TestCase):
    def test_cargo_target_bin_dir_uses_plain_debug_when_target_missing(self) -> None:
        with temporary_dir("aios-bin-helper-") as root:
            self.assertEqual(
                cargo_target_bin_dir(root, None),
                root / "aios" / "target" / "debug",
            )

    def test_cargo_target_bin_dir_uses_target_specific_debug_directory(self) -> None:
        with temporary_dir("aios-bin-helper-") as root:
            self.assertEqual(
                cargo_target_bin_dir(root, "custom-target"),
                root / "aios" / "target" / "custom-target" / "debug",
            )

    def test_detect_host_target_prefers_environment_override(self) -> None:
        with mock.patch.dict(os.environ, {"CARGO_BUILD_TARGET": "custom-target"}, clear=False):
            self.assertEqual(detect_host_target(Path("/tmp/unused")), "custom-target")

    def test_default_bin_dir_prefers_explicit_target_directory(self) -> None:
        with temporary_dir("aios-bin-helper-") as root:
            host_bin_dir = root / "aios" / "target" / "custom-target" / "debug"
            fallback_bin_dir = root / "aios" / "target" / "debug"
            host_bin_dir.mkdir(parents=True, exist_ok=True)
            fallback_bin_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch.dict(
                os.environ,
                {"CARGO_BUILD_TARGET": "custom-target"},
                clear=False,
            ):
                self.assertEqual(default_aios_bin_dir(root), host_bin_dir)

    def test_default_bin_dir_falls_back_to_plain_debug_directory(self) -> None:
        with temporary_dir("aios-bin-helper-") as root:
            fallback_bin_dir = root / "aios" / "target" / "debug"
            fallback_bin_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("aios_cargo_bins.detect_host_target", return_value="missing-target"):
                    self.assertEqual(default_aios_bin_dir(root), fallback_bin_dir)

    def test_default_bin_dir_prefers_plain_debug_for_default_host_builds(self) -> None:
        with temporary_dir("aios-bin-helper-") as root:
            host_bin_dir = root / "aios" / "target" / "aarch64-apple-darwin" / "debug"
            fallback_bin_dir = root / "aios" / "target" / "debug"
            host_bin_dir.mkdir(parents=True, exist_ok=True)
            fallback_bin_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch(
                    "aios_cargo_bins.detect_host_target",
                    return_value="aarch64-apple-darwin",
                ):
                    self.assertEqual(default_aios_bin_dir(root), fallback_bin_dir)

    def test_default_container_native_bin_dir_uses_repo_out_path(self) -> None:
        with temporary_dir("aios-bin-helper-") as root:
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    default_container_native_bin_dir(root),
                    root / "out" / "aios-delivery-container-target" / "debug",
                )

    def test_default_container_native_bin_dir_respects_override(self) -> None:
        with temporary_dir("aios-bin-helper-") as root:
            override = root / "custom-container-bin"
            with mock.patch.dict(
                os.environ,
                {"AIOS_DELIVERY_CACHED_BIN_DIR": str(override)},
                clear=True,
            ):
                self.assertEqual(default_container_native_bin_dir(root), override)

    def test_resolve_binary_path_accepts_windows_exe_artifact(self) -> None:
        with temporary_dir("aios-bin-helper-") as bin_dir:
            with mock.patch("aios_cargo_bins.os.name", "nt"):
                artifact = bin_dir / "updated.exe"
                artifact.write_text("")
                self.assertEqual(resolve_binary_path(bin_dir, "updated"), artifact)

    def test_has_expected_aios_binaries_requires_complete_set(self) -> None:
        with temporary_dir("aios-bin-helper-") as bin_dir:
            for name in expected_aios_binaries()[:-1]:
                (bin_dir / name).write_text("")
            self.assertFalse(has_expected_aios_binaries(bin_dir))
            (bin_dir / expected_aios_binaries()[-1]).write_text("")
            self.assertTrue(has_expected_aios_binaries(bin_dir))


if __name__ == "__main__":
    unittest.main()
