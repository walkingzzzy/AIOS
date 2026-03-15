#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PREFIX = ROOT / 'out' / 'validation' / 'system-delivery-validation-report'


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    summary: str
    command: list[str]
    evidence_paths: tuple[str, ...] = ()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run the AIOS system delivery validation suite and write a consolidated report'
    )
    parser.add_argument(
        '--output-prefix',
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help='Output prefix for the generated .json and .md reports',
    )
    parser.add_argument(
        '--evidence-index-out',
        type=Path,
        help='Optional output path for the generated evidence index JSON',
    )
    return parser.parse_args()


def checks() -> list[CheckSpec]:
    python = sys.executable
    return [
        CheckSpec(
            check_id='delivery-rootfs-hygiene',
            summary='Validate delivery bundle layout, enabled units, compat descriptors, and machine-id hygiene',
            command=[python, str(ROOT / 'scripts' / 'test-image-delivery-smoke.py'), '--bundle-dir', str(ROOT / 'out' / 'aios-system-delivery')],
            evidence_paths=('out/aios-system-delivery/manifest.json',),
        ),
        CheckSpec(
            check_id='firstboot-offline-hygiene',
            summary='Validate firstboot idempotence, machine-id initialization, and report generation against the delivery bundle',
            command=[python, str(ROOT / 'scripts' / 'test-firstboot-hygiene-smoke.py'), '--bundle-dir', str(ROOT / 'out' / 'aios-system-delivery')],
            evidence_paths=('out/aios-system-delivery/rootfs/usr/libexec/aios/aios-firstboot.sh',),
        ),
        CheckSpec(
            check_id='installer-integration',
            summary='Validate installer sysroot staging, firstboot install identity metadata, and recovery manifest integration',
            command=[python, str(ROOT / 'scripts' / 'test-installer-smoke.py')],
            evidence_paths=('scripts/install-aios-system.py',),
        ),
        CheckSpec(
            check_id='installer-guided-ux',
            summary='Validate the guided installer summary/session flow without triggering disk writes',
            command=[python, str(ROOT / 'scripts' / 'test-installer-ux-smoke.py')],
            evidence_paths=('aios/image/installer/aios-installer-guided.sh',),
        ),
        CheckSpec(
            check_id='vendor-firmware-adapter',
            summary='Validate the NVIDIA nvbootctrl adapter across platform media export, installer hooks, and firmware bridge persistence',
            command=[python, str(ROOT / 'scripts' / 'test-vendor-firmware-hook-smoke.py')],
            evidence_paths=(
                'aios/image/platforms/nvidia-jetson-orin-agx/profile.yaml',
                'aios/services/updated/platforms/nvidia-jetson-orin-agx/share/profile.yaml',
            ),
        ),
        CheckSpec(
            check_id='container-native-delivery-preflight',
            summary='Validate the container-native delivery builder definition and preflight metadata',
            command=[python, str(ROOT / 'scripts' / 'test-build-container-native-smoke.py')],
            evidence_paths=('scripts/build-aios-delivery-container.sh', 'docker/aios-delivery.Dockerfile'),
        ),
        CheckSpec(
            check_id='qemu-preflight',
            summary='Validate mkosi/image/QEMU prerequisites before booting the image',
            command=[python, str(ROOT / 'scripts' / 'test-boot-qemu-smoke.py')],
            evidence_paths=('aios/image/mkosi.output/aios-qemu-x86_64.raw',),
        ),
        CheckSpec(
            check_id='qemu-bringup-firstboot',
            summary='Boot the QEMU raw image and require AIOS firstboot evidence in the serial log',
            command=[python, str(ROOT / 'scripts' / 'test-boot-qemu-bringup.py'), '--timeout', '180', '--expect-firstboot'],
            evidence_paths=('out/boot-qemu-bringup.log',),
        ),
        CheckSpec(
            check_id='qemu-recovery-bringup',
            summary='Boot the QEMU recovery image and require recovery-target evidence in the serial log',
            command=[python, str(ROOT / 'scripts' / 'test-boot-qemu-recovery.py'), '--timeout', '180'],
            evidence_paths=('out/boot-qemu-recovery.log',),
        ),
        CheckSpec(
            check_id='installer-media-qemu',
            summary='Boot the installer image, provision a target disk, then boot the installed target through a real QEMU reset',
            command=[python, str(ROOT / 'scripts' / 'test-boot-qemu-installer.py'), '--timeout', '600', '--boot-installed-target', '--cross-reboot'],
            evidence_paths=(
                'aios/image/installer.output/aios-qemu-x86_64-installer.raw',
                'out/boot-qemu-installer.log',
                'out/boot-qemu-installed-cross-reboot.log',
            ),
        ),
        CheckSpec(
            check_id='platform-media-export',
            summary='Validate platform installer/recovery media export, embedded payload overlay generation, and flash manifest output',
            command=[python, str(ROOT / 'scripts' / 'test-platform-media-smoke.py')],
            evidence_paths=('scripts/build-aios-platform-media.py', 'aios/image/platforms/generic-x86_64-uefi/profile.yaml'),
        ),
        CheckSpec(
            check_id='updated-recovery-surface',
            summary='Validate updated RPCs, recovery surface export, diagnostic bundle export, and rollback acceptance',
            command=[python, str(ROOT / 'scripts' / 'test-updated-smoke.py')],
            evidence_paths=(),
        ),
        CheckSpec(
            check_id='updated-cross-restart',
            summary='Validate staged boot slot switch, post-restart convergence, and rollback across simulated restarts',
            command=[python, str(ROOT / 'scripts' / 'test-updated-restart-smoke.py')],
            evidence_paths=(),
        ),
        CheckSpec(
            check_id='updated-firmware-backend',
            summary='Validate firmware backend slot switching, mark-good persistence, and rollback convergence across simulated restarts',
            command=[python, str(ROOT / 'scripts' / 'test-updated-firmware-backend-smoke.py')],
            evidence_paths=('scripts/test-updated-firmware-backend-smoke.py',),
        ),
        CheckSpec(
            check_id='updated-platform-profile',
            summary='Validate updated platform-profile loading and generic x86_64 UEFI systemd-sysupdate/firmware bridges',
            command=[python, str(ROOT / 'scripts' / 'test-updated-platform-profile-smoke.py')],
            evidence_paths=('aios/services/updated/platforms/generic-x86_64-uefi/share/profile.yaml',),
        ),
        CheckSpec(
            check_id='hardware-boot-evidence',
            summary='Validate hardware boot evidence collection and cross-reboot report evaluation against synthetic boots',
            command=[python, str(ROOT / 'scripts' / 'test-hardware-boot-evidence-smoke.py')],
            evidence_paths=('aios/hardware/evidence/aios-boot-evidence.sh', 'scripts/evaluate-aios-hardware-boot-evidence.py'),
        ),
    ]


def parse_embedded_json(stdout: str):
    stripped = stdout.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    for index, char in enumerate(stripped):
        if char != '{':
            continue
        candidate = stripped[index:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def run_check(spec: CheckSpec) -> dict:
    started = time.monotonic()
    completed = subprocess.run(
        spec.command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    duration_seconds = round(time.monotonic() - started, 3)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    return {
        'check_id': spec.check_id,
        'summary': spec.summary,
        'command': ' '.join(spec.command),
        'status': 'passed' if completed.returncode == 0 else 'failed',
        'returncode': completed.returncode,
        'duration_seconds': duration_seconds,
        'stdout': stdout,
        'stderr': stderr,
        'parsed_output': parse_embedded_json(stdout),
        'evidence_paths': list(spec.evidence_paths),
    }


def refresh_delivery_bundle() -> dict:
    command = [
        sys.executable,
        str(ROOT / 'scripts' / 'build-aios-delivery.py'),
        '--build-missing',
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    duration_seconds = round(time.monotonic() - started, 3)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    return {
        'command': ' '.join(command),
        'status': 'passed' if completed.returncode == 0 else 'failed',
        'returncode': completed.returncode,
        'duration_seconds': duration_seconds,
        'stdout': stdout,
        'stderr': stderr,
        'parsed_output': parse_embedded_json(stdout),
    }


def write_json_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append('# AIOS System Delivery Validation Report')
    lines.append('')
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Overall status: `{report['overall_status']}`")
    lines.append(f"- Workspace: `{report['workspace']}`")
    if report.get('delivery_bundle_refresh') is not None:
        bundle_refresh = report['delivery_bundle_refresh']
        lines.append(
            f"- Delivery bundle refresh: `{bundle_refresh['status']}` in `{bundle_refresh['duration_seconds']}` seconds"
        )
    lines.append('')
    lines.append('## Checklist')
    lines.append('')
    lines.append('| Check | Status | Duration (s) |')
    lines.append('|-------|--------|--------------|')
    for item in report['checks']:
        lines.append(f"| `{item['check_id']}` | `{item['status']}` | `{item['duration_seconds']}` |")
    lines.append('')

    for item in report['checks']:
        lines.append(f"## {item['check_id']}")
        lines.append('')
        lines.append(f"- Summary: {item['summary']}")
        lines.append(f"- Status: `{item['status']}`")
        lines.append(f"- Command: `{item['command']}`")
        lines.append(f"- Duration: `{item['duration_seconds']}` seconds")
        if item['evidence_paths']:
            lines.append('- Evidence paths:')
            for evidence in item['evidence_paths']:
                lines.append(f"  - `{evidence}`")
        if item['parsed_output'] is not None:
            lines.append('- Parsed output:')
            lines.append('```json')
            lines.append(json.dumps(item['parsed_output'], indent=2, ensure_ascii=False))
            lines.append('```')
        elif item['stdout']:
            lines.append('- Stdout:')
            lines.append('```text')
            lines.append(item['stdout'])
            lines.append('```')
        if item['stderr']:
            lines.append('- Stderr:')
            lines.append('```text')
            lines.append(item['stderr'])
            lines.append('```')
        lines.append('')

    return '\n'.join(lines)


def write_markdown_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report) + '\n')


def classify_artifact(path: str) -> str:
    lowered = path.lower()
    suffix = Path(path).suffix.lower()
    if suffix == '.log':
        return 'logs'
    if suffix in {'.raw', '.img', '.qcow2'}:
        return 'images'
    if suffix in {'.py', '.sh'}:
        return 'scripts'
    if suffix in {'.json', '.yaml', '.yml', '.conf', '.service'} or 'manifest' in lowered:
        return 'configs'
    return 'other'


def build_evidence_index(report: dict, json_path: Path, md_path: Path) -> dict:
    categorized_artifacts = {
        'logs': [],
        'images': [],
        'scripts': [],
        'configs': [],
        'other': [],
    }
    unique_artifacts: set[str] = set()
    for item in report['checks']:
        for artifact_path in item.get('evidence_paths', []):
            if artifact_path in unique_artifacts:
                continue
            unique_artifacts.add(artifact_path)
            category = classify_artifact(artifact_path)
            categorized_artifacts[category].append(artifact_path)

    status_counts = {
        'passed': sum(1 for item in report['checks'] if item['status'] == 'passed'),
        'failed': sum(1 for item in report['checks'] if item['status'] == 'failed'),
    }

    return {
        'index_id': 'system-delivery-validation',
        'generated_at': report['generated_at'],
        'validation_kind': 'system-delivery',
        'validation_status': report['overall_status'],
        'workspace': report['workspace'],
        'report_paths': {
            'json_report': str(json_path),
            'markdown_report': str(md_path),
        },
        'status_counts': status_counts,
        'artifacts': categorized_artifacts,
        'checks': [
            {
                'check_id': item['check_id'],
                'summary': item['summary'],
                'status': item['status'],
                'evidence_paths': item['evidence_paths'],
            }
            for item in report['checks']
        ],
        'failing_checks': [
            item['check_id']
            for item in report['checks']
            if item['status'] != 'passed'
        ],
    }


def write_evidence_index(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')


def main() -> int:
    args = parse_args()
    prefix = args.output_prefix
    json_path = prefix.with_suffix('.json')
    md_path = prefix.with_suffix('.md')
    evidence_index_path = args.evidence_index_out or prefix.with_name(
        prefix.name.replace('-report', '-evidence-index')
    ).with_suffix('.json')

    delivery_bundle_refresh = refresh_delivery_bundle()
    if delivery_bundle_refresh['status'] != 'passed':
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'workspace': str(ROOT),
            'overall_status': 'failed',
            'json_report': str(json_path),
            'markdown_report': str(md_path),
            'delivery_bundle_refresh': delivery_bundle_refresh,
            'checks': [],
        }
        write_json_report(json_path, report)
        write_markdown_report(md_path, report)
        evidence_index = build_evidence_index(report, json_path, md_path)
        write_evidence_index(evidence_index_path, evidence_index)
        print(json.dumps({
            'overall_status': 'failed',
            'json_report': str(json_path),
            'markdown_report': str(md_path),
            'evidence_index': str(evidence_index_path),
            'delivery_bundle_refresh': {
                'status': delivery_bundle_refresh['status'],
                'duration_seconds': delivery_bundle_refresh['duration_seconds'],
                'returncode': delivery_bundle_refresh['returncode'],
            },
            'checks': [],
        }, ensure_ascii=False, indent=2))
        return 1

    results = [run_check(spec) for spec in checks()]
    overall_status = 'passed' if all(item['status'] == 'passed' for item in results) else 'failed'
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'workspace': str(ROOT),
        'overall_status': overall_status,
        'json_report': str(json_path),
        'markdown_report': str(md_path),
        'delivery_bundle_refresh': delivery_bundle_refresh,
        'checks': results,
    }

    write_json_report(json_path, report)
    write_markdown_report(md_path, report)
    evidence_index = build_evidence_index(report, json_path, md_path)
    write_evidence_index(evidence_index_path, evidence_index)
    print(json.dumps({
        'overall_status': overall_status,
        'json_report': str(json_path),
        'markdown_report': str(md_path),
        'evidence_index': str(evidence_index_path),
        'checks': [
            {
                'check_id': item['check_id'],
                'status': item['status'],
                'duration_seconds': item['duration_seconds'],
            }
            for item in results
        ],
    }, ensure_ascii=False, indent=2))
    return 0 if overall_status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
