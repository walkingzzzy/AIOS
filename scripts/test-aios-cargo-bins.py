#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aios_cargo_bins import (
    cargo_target_bin_dir,
    default_aios_bin_dir,
    default_container_native_bin_dir,
    detect_host_target,
    expected_aios_binaries,
    has_expected_aios_binaries,
)


class CargoBinResolutionTests(unittest.TestCase):
    def test_cargo_target_bin_dir_uses_plain_debug_when_target_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            root = Path(temp_root)
            self.assertEqual(
                cargo_target_bin_dir(root, None),
                root / "aios" / "target" / "debug",
            )

    def test_cargo_target_bin_dir_uses_target_specific_debug_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            root = Path(temp_root)
            self.assertEqual(
                cargo_target_bin_dir(root, "custom-target"),
                root / "aios" / "target" / "custom-target" / "debug",
            )

    def test_detect_host_target_prefers_environment_override(self) -> None:
        with mock.patch.dict(os.environ, {"CARGO_BUILD_TARGET": "custom-target"}, clear=False):
            self.assertEqual(detect_host_target(Path("/tmp/unused")), "custom-target")

    def test_default_bin_dir_prefers_explicit_target_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            root = Path(temp_root)
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
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            root = Path(temp_root)
            fallback_bin_dir = root / "aios" / "target" / "debug"
            fallback_bin_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("aios_cargo_bins.detect_host_target", return_value="missing-target"):
                    self.assertEqual(default_aios_bin_dir(root), fallback_bin_dir)

    def test_default_bin_dir_prefers_plain_debug_for_default_host_builds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            root = Path(temp_root)
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
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            root = Path(temp_root)
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    default_container_native_bin_dir(root),
                    root / "out" / "aios-delivery-container-target" / "debug",
                )

    def test_default_container_native_bin_dir_respects_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            root = Path(temp_root)
            override = root / "custom-container-bin"
            with mock.patch.dict(
                os.environ,
                {"AIOS_DELIVERY_CACHED_BIN_DIR": str(override)},
                clear=True,
            ):
                self.assertEqual(default_container_native_bin_dir(root), override)

    def test_has_expected_aios_binaries_requires_complete_set(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-bin-helper-") as temp_root:
            bin_dir = Path(temp_root)
            for name in expected_aios_binaries()[:-1]:
                (bin_dir / name).write_text("")
            self.assertFalse(has_expected_aios_binaries(bin_dir))
            (bin_dir / expected_aios_binaries()[-1]).write_text("")
            self.assertTrue(has_expected_aios_binaries(bin_dir))


if __name__ == "__main__":
    unittest.main()
