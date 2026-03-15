#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare an AIOS mkosi staging directory while preserving incremental caches.")
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("staging_dir", type=Path)
    parser.add_argument("--preserve", action="append", default=[])
    parser.add_argument("--exclude-copy", action="append", default=[])
    return parser.parse_args()


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def copy_path(source: Path, target: Path) -> None:
    if source.is_symlink():
        target.symlink_to(source.readlink())
    elif source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target, follow_symlinks=False)


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    staging_dir = args.staging_dir.resolve()
    preserve = set(args.preserve)
    exclude_copy = set(args.exclude_copy) | preserve

    if not source_dir.is_dir():
        raise SystemExit(f"source directory does not exist: {source_dir}")

    staging_dir.mkdir(parents=True, exist_ok=True)

    for child in staging_dir.iterdir():
        if child.name in preserve:
            continue
        remove_path(child)

    for child in source_dir.iterdir():
        if child.name in exclude_copy:
            continue
        copy_path(child, staging_dir / child.name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
