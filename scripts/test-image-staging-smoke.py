#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'prepare-aios-image-staging.py'


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='aios-image-stage-') as tmp:
        root = Path(tmp)
        source = root / 'source'
        staging = root / 'staging'
        source.mkdir()
        staging.mkdir()

        write_text(source / 'mkosi.conf', 'Output=aios-qemu-x86_64\n')
        write_text(source / 'README.md', 'source readme\n')
        write_text(source / 'mkosi.extra' / 'etc' / 'aios.conf', 'overlay\n')
        write_text(source / 'mkosi.output' / 'system.raw', 'skip me\n')
        write_text(source / 'recovery.output' / 'recovery.raw', 'skip me\n')
        write_text(source / 'installer.output' / 'installer.raw', 'skip me\n')

        write_text(staging / 'obsolete.txt', 'old\n')
        write_text(staging / 'mkosi.cache' / 'cache.txt', 'keep cache\n')
        write_text(staging / 'mkosi.builddir' / 'build.txt', 'keep builddir\n')
        write_text(staging / 'mkosi.tools' / 'tool.txt', 'keep tools\n')

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(source),
                str(staging),
                '--preserve', 'mkosi.cache',
                '--preserve', 'mkosi.builddir',
                '--preserve', 'mkosi.tools',
                '--exclude-copy', 'mkosi.output',
                '--exclude-copy', 'recovery.output',
                '--exclude-copy', 'installer.output',
            ],
            check=True,
            cwd=ROOT,
        )

        ensure((staging / 'README.md').read_text() == 'source readme\n', 'expected README to sync into staging')
        ensure((staging / 'mkosi.extra' / 'etc' / 'aios.conf').read_text() == 'overlay\n', 'expected overlay to sync into staging')
        ensure(not (staging / 'obsolete.txt').exists(), 'staging cleanup should remove obsolete entries')
        ensure(not (staging / 'mkosi.output').exists(), 'staging should not copy mkosi.output artifacts')
        ensure(not (staging / 'recovery.output').exists(), 'staging should not copy recovery.output artifacts')
        ensure(not (staging / 'installer.output').exists(), 'staging should not copy installer.output artifacts')
        ensure((staging / 'mkosi.cache' / 'cache.txt').read_text() == 'keep cache\n', 'mkosi.cache should be preserved')
        ensure((staging / 'mkosi.builddir' / 'build.txt').read_text() == 'keep builddir\n', 'mkosi.builddir should be preserved')
        ensure((staging / 'mkosi.tools' / 'tool.txt').read_text() == 'keep tools\n', 'mkosi.tools should be preserved')

        summary = {
            'source': str(source),
            'staging': str(staging),
            'copied_files': sorted(str(path.relative_to(staging)) for path in staging.rglob('*') if path.is_file()),
            'preserved_dirs': sorted(name for name in ('mkosi.cache', 'mkosi.builddir', 'mkosi.tools') if (staging / name).exists()),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
