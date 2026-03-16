#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from aios_cargo_bins import cargo_target_bin_dir, detect_host_target

ROOT = Path(__file__).resolve().parent.parent
AIOS_DIR = ROOT / 'aios'
PYTHON = sys.executable
DEFAULT_OUTPUT_PREFIX = ROOT / 'out' / 'validation' / 'full-regression-report'
REGRESSION_REPORT_SCHEMA = ROOT / 'aios' / 'observability' / 'schemas' / 'full-regression-report.schema.json'
SYSTEM_VALIDATION_LINUX_ONLY_STEPS = {
    'Build system image',
    'Build recovery image',
    'Build installer image',
    'Run full system delivery validation',
    'Build governance evidence index',
    'Run release gate',
}

PY_COMPILE_TARGETS = [
    'scripts/aios_cargo_bins.py', 'scripts/test-aios-cargo-bins.py',
    'scripts/aios_governance_common.py',
    'scripts/test-observability-schema-smoke.py', 'scripts/check-release-gate.py',
    'scripts/build-governance-evidence-index.py',
    'scripts/build-observability-correlation-report.py', 'scripts/test-observability-correlation-smoke.py',
    'scripts/build-audit-evidence-report.py', 'scripts/test-audit-evidence-export-smoke.py',
    'scripts/build-cross-service-health-report.py', 'scripts/test-cross-service-health-smoke.py',
    'scripts/test-validation-matrix-smoke.py', 'scripts/test-high-risk-audit-coverage-smoke.py',
    'scripts/test-gpu-backend-support-matrix-smoke.py',
    'scripts/test-tier1-machine-nominations-smoke.py',
    'scripts/build-default-hardware-evidence-index.py',
    'scripts/test-release-gate-smoke.py',
    'scripts/collect-aios-device-validation.py',
    'scripts/render-aios-hardware-validation-report.py',
    'scripts/build-aios-platform-media.py',
    'scripts/test-device-validation-collector-smoke.py',
    'scripts/test-hardware-validation-report-smoke.py',
    'scripts/test-platform-media-smoke.py',
    'scripts/test-image-build-strategy-smoke.py',
    'scripts/test-ci-artifact-governance-smoke.py',
    'scripts/test-compat-registration-contract-smoke.py',
    'scripts/sync-aios-task-metadata.py', 'scripts/build-aios-delivery.py', 'scripts/test-image-delivery-smoke.py',
    'scripts/test-firstboot-hygiene-smoke.py', 'scripts/test-boot-qemu-smoke.py', 'scripts/test-boot-qemu-bringup.py',
    'scripts/test-ipc-smoke.py', 'scripts/test-code-sandbox-smoke.py', 'scripts/test-compat-runtime-smoke.py',
    'scripts/test-policyd-audit-store-smoke.py', 'scripts/test-provider-registry-smoke.py',
    'scripts/test-portal-file-handle-smoke.py',
    'scripts/test-device-metadata-provider-smoke.py', 'scripts/test-system-intent-provider-smoke.py',
    'scripts/test-runtime-local-inference-provider-smoke.py', 'scripts/test-provider-startup-edge-smoke.py',
    'scripts/test-provider-registry-recovery-smoke.py', 'scripts/test-full-regression-suite-smoke.py',
    'scripts/test-installer-ux-smoke.py',
    'scripts/test-vendor-firmware-hook-smoke.py', 'scripts/test-build-container-native-smoke.py',
    'scripts/test-shell-provider-smoke.py', 'scripts/test-shell-chooser-smoke.py', 'scripts/test-portal-flow-smoke.py', 'scripts/test-portal-capture-chain-smoke.py', 'scripts/test-shell-release-profile-smoke.py', 'scripts/test-shellctl-smoke.py', 'scripts/test-shell-panel-bridge-service-smoke.py', 'scripts/test-shell-panel-clients-smoke.py', 'scripts/test-shell-panel-embedding-live-smoke.py', 'scripts/test-shell-compositor-acceptance-smoke.py', 'scripts/test-shell-acceptance-smoke.py', 'scripts/test-shell-stability-smoke.py', 'scripts/test-screen-capture-provider-smoke.py',
    'scripts/test-runtimed-backend-smoke.py', 'scripts/test-runtimed-worker-contract-smoke.py', 'scripts/test-runtimed-managed-worker-smoke.py', 'scripts/test-runtimed-managed-worker-restart-smoke.py', 'scripts/test-runtimed-managed-worker-restart-exhausted-smoke.py', 'scripts/test-runtimed-events-smoke.py', 'scripts/test-runtimed-hardware-profile-managed-worker-smoke.py', 'scripts/test-runtimed-jetson-platform-worker-smoke.py', 'scripts/test-runtimed-jetson-platform-vendor-helper-smoke.py', 'scripts/test-runtimed-jetson-platform-vendor-worker-smoke.py', 'scripts/test-runtimed-jetson-platform-worker-failure-smoke.py', 'scripts/test-shell-desktop-smoke.py', 'scripts/test-shell-session-smoke.py', 'scripts/test-deviced-smoke.py',
    'scripts/test-deviced-readiness-matrix-smoke.py', 'scripts/test-deviced-continuous-native-smoke.py',
    'aios/compat/browser/runtime/browser_provider.py', 'aios/compat/office/runtime/office_provider.py',
    'aios/compat/mcp-bridge/runtime/mcp_bridge_provider.py', 'aios/compat/code-sandbox/runtime/aios_sandbox_executor.py',
    'aios/shell/runtime/shell_control_provider.py', 'aios/shell/runtime/shell_panel_bridge_service.py', 'aios/shell/runtime/shell_panel_clients_gtk.py', 'aios/shell/runtime/screen_capture_portal_provider.py',
    'aios/shell/runtime/shell_desktop.py', 'aios/shell/components/portal-chooser/prototype.py',
    'aios/shell/components/portal-chooser/client.py', 'aios/shell/components/portal-chooser/panel.py',
    'aios/shell/components/portal-chooser/standalone.py',
]


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    cwd: Path = ROOT
    env: dict[str, str] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run AIOS local validation in CI order')
    parser.add_argument('--stage', choices=['validate', 'system-validation', 'full'], default='validate')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument(
        '--keep-going',
        action='store_true',
        help='Continue executing remaining steps after a failure and record every result in the final report.',
    )
    parser.add_argument(
        '--output-prefix',
        type=Path,
        default=DEFAULT_OUTPUT_PREFIX,
        help='Output prefix for the generated .json and .md regression reports',
    )
    return parser.parse_args()


def require_python_deps() -> None:
    try:
        import yaml  # noqa: F401
        import jsonschema  # noqa: F401
    except ImportError as exc:
        raise SystemExit('Missing Python dependencies: require PyYAML and jsonschema before running local CI parity.') from exc


def require_tools(names: list[str]) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"Missing required tools for requested stage: {', '.join(missing)}")



def platform_supports_unix_socket_smokes() -> bool:
    return hasattr(socket, 'AF_UNIX') and os.name != 'nt'

def step_script_path(step: Step) -> Path | None:
    if not step.command or step.command[0] != PYTHON or len(step.command) < 2:
        return None
    script_path = Path(step.command[1])
    if script_path.suffix != '.py':
        return None
    if script_path.is_absolute():
        return script_path
    return ROOT / script_path

def step_requires_unix_socket_support(step: Step) -> bool:
    script_path = step_script_path(step)
    if script_path is None or not script_path.exists():
        return False
    try:
        content = script_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return False
    return 'socket.AF_UNIX' in content

def platform_skip_detail(step: Step) -> str | None:
    if os.name == 'nt' and step.name in SYSTEM_VALIDATION_LINUX_ONLY_STEPS:
        return 'skipped on this host: system image validation requires Linux host tooling and QEMU'
    if platform_supports_unix_socket_smokes():
        return None
    if step_requires_unix_socket_support(step):
        return 'skipped on this host: requires POSIX Unix domain socket support'
    return None

def validate_steps(host_target: str, bin_dir: str) -> list[Step]:
    return [
        Step('Validate task metadata', [PYTHON, 'scripts/sync-aios-task-metadata.py', '--check']),
        Step('Python syntax checks', [PYTHON, '-m', 'py_compile', *PY_COMPILE_TARGETS]),
        Step('Observability schema smoke', [PYTHON, 'scripts/test-observability-schema-smoke.py']),
        Step('Validation matrix smoke', [PYTHON, 'scripts/test-validation-matrix-smoke.py']),
        Step('High-risk audit coverage smoke', [PYTHON, 'scripts/test-high-risk-audit-coverage-smoke.py']),
        Step('GPU backend support matrix smoke', [PYTHON, 'scripts/test-gpu-backend-support-matrix-smoke.py']),
        Step('Tier1 machine nominations smoke', [PYTHON, 'scripts/test-tier1-machine-nominations-smoke.py']),
        Step('Build default Tier1 hardware evidence', [PYTHON, 'scripts/build-default-hardware-evidence-index.py']),
        Step('Release gate vendor runtime smoke', [PYTHON, 'scripts/test-release-gate-smoke.py']),
        Step('Device validation collector smoke', [PYTHON, 'scripts/test-device-validation-collector-smoke.py']),
        Step('Hardware validation report smoke', [PYTHON, 'scripts/test-hardware-validation-report-smoke.py']),
        Step('Platform media smoke', [PYTHON, 'scripts/test-platform-media-smoke.py']),
        Step('Image build strategy smoke', [PYTHON, 'scripts/test-image-build-strategy-smoke.py']),
        Step('CI artifact governance smoke', [PYTHON, 'scripts/test-ci-artifact-governance-smoke.py']),
        Step('Cargo bin-dir helper tests', [PYTHON, 'scripts/test-aios-cargo-bins.py']),
        Step('Cargo test', ['cargo', 'test', '--workspace'], cwd=AIOS_DIR),
        Step('Build smoke binaries', ['cargo', 'build', '--target', host_target, '-p', 'aios-agentd', '-p', 'aios-sessiond', '-p', 'aios-policyd', '-p', 'aios-runtimed', '-p', 'aios-deviced', '-p', 'aios-updated', '-p', 'aios-device-metadata-provider', '-p', 'aios-runtime-local-inference-provider', '-p', 'aios-system-intent-provider', '-p', 'aios-system-files-provider'], cwd=AIOS_DIR),
        Step('IPC smoke', [PYTHON, 'scripts/test-ipc-smoke.py', '--bin-dir', bin_dir]),
        Step('Portal file-handle smoke', [PYTHON, 'scripts/test-portal-file-handle-smoke.py', '--bin-dir', bin_dir]),
        Step('Policyd audit-store smoke', [PYTHON, 'scripts/test-policyd-audit-store-smoke.py', '--bin-dir', bin_dir]),
        Step('Provider registry smoke', [PYTHON, 'scripts/test-provider-registry-smoke.py', '--bin-dir', bin_dir]),
        Step('Compat registration contract smoke', [PYTHON, 'scripts/test-compat-registration-contract-smoke.py']),
        Step('Device metadata provider smoke', [PYTHON, 'scripts/test-device-metadata-provider-smoke.py', '--bin-dir', bin_dir]),
        Step('System intent provider smoke', [PYTHON, 'scripts/test-system-intent-provider-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtime local inference provider smoke', [PYTHON, 'scripts/test-runtime-local-inference-provider-smoke.py', '--bin-dir', bin_dir]),
        Step('Provider startup-edge smoke', [PYTHON, 'scripts/test-provider-startup-edge-smoke.py', '--bin-dir', bin_dir]),
        Step('Provider registry recovery smoke', [PYTHON, 'scripts/test-provider-registry-recovery-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed backend smoke', [PYTHON, 'scripts/test-runtimed-backend-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed worker contract smoke', [PYTHON, 'scripts/test-runtimed-worker-contract-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed managed worker smoke', [PYTHON, 'scripts/test-runtimed-managed-worker-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed managed worker restart smoke', [PYTHON, 'scripts/test-runtimed-managed-worker-restart-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed managed worker restart exhausted smoke', [PYTHON, 'scripts/test-runtimed-managed-worker-restart-exhausted-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed events smoke', [PYTHON, 'scripts/test-runtimed-events-smoke.py', '--bin-dir', bin_dir]),
        Step('Observability correlation smoke', [PYTHON, 'scripts/test-observability-correlation-smoke.py', '--bin-dir', bin_dir]),
        Step('Audit evidence export smoke', [PYTHON, 'scripts/test-audit-evidence-export-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed hardware-profile managed worker smoke', [PYTHON, 'scripts/test-runtimed-hardware-profile-managed-worker-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed Jetson platform worker smoke', [PYTHON, 'scripts/test-runtimed-jetson-platform-worker-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed Jetson platform vendor helper smoke', [PYTHON, 'scripts/test-runtimed-jetson-platform-vendor-helper-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed Jetson platform vendor worker smoke', [PYTHON, 'scripts/test-runtimed-jetson-platform-vendor-worker-smoke.py', '--bin-dir', bin_dir]),
        Step('Runtimed Jetson platform worker failure smoke', [PYTHON, 'scripts/test-runtimed-jetson-platform-worker-failure-smoke.py', '--bin-dir', bin_dir]),
        Step('Filesystem provider smoke', [PYTHON, 'scripts/test-provider-fs-smoke.py', '--bin-dir', bin_dir], env={'TMPDIR': '/tmp'}),
        Step('Updated restart smoke', [PYTHON, 'scripts/test-updated-restart-smoke.py', '--bin-dir', bin_dir]),
        Step('Shell live smoke', [PYTHON, 'scripts/test-shell-live-smoke.py', '--bin-dir', bin_dir]),
        Step('Shell desktop smoke', [PYTHON, 'scripts/test-shell-desktop-smoke.py']),
        Step('Shell session smoke', [PYTHON, 'scripts/test-shell-session-smoke.py']),
        Step('Shell acceptance smoke', [PYTHON, 'scripts/test-shell-acceptance-smoke.py']),
        Step('Shell stability smoke', [PYTHON, 'scripts/test-shell-stability-smoke.py']),
        Step('Shellctl smoke', [PYTHON, 'scripts/test-shellctl-smoke.py']),
        Step('Shell panel bridge service smoke', [PYTHON, 'scripts/test-shell-panel-bridge-service-smoke.py']),
        Step('Shell panel clients smoke', [PYTHON, 'scripts/test-shell-panel-clients-smoke.py']),
        Step('Shell panel embedding live smoke', [PYTHON, 'scripts/test-shell-panel-embedding-live-smoke.py']),
        Step('Deviced smoke', [PYTHON, 'scripts/test-deviced-smoke.py', '--bin-dir', bin_dir]),
        Step('Deviced readiness matrix smoke', [PYTHON, 'scripts/test-deviced-readiness-matrix-smoke.py', '--bin-dir', bin_dir]),
        Step('Deviced continuous native smoke', [PYTHON, 'scripts/test-deviced-continuous-native-smoke.py', '--bin-dir', bin_dir]),
        Step('Shell chooser smoke', [PYTHON, 'scripts/test-shell-chooser-smoke.py']),
        Step('Portal flow smoke', [PYTHON, 'scripts/test-portal-flow-smoke.py']),
        Step('Portal capture chain smoke', [PYTHON, 'scripts/test-portal-capture-chain-smoke.py', '--bin-dir', bin_dir]),
        Step('Shell release profile smoke', [PYTHON, 'scripts/test-shell-release-profile-smoke.py']),
        Step('Shell compositor acceptance smoke', [PYTHON, 'scripts/test-shell-compositor-acceptance-smoke.py']),
        Step('Shell provider smoke', [PYTHON, 'scripts/test-shell-provider-smoke.py', '--bin-dir', bin_dir]),
        Step('Screen capture provider smoke', [PYTHON, 'scripts/test-screen-capture-provider-smoke.py', '--bin-dir', bin_dir]),
        Step('Browser provider smoke', [PYTHON, 'scripts/test-browser-provider-smoke.py']),
        Step('Office provider smoke', [PYTHON, 'scripts/test-office-provider-smoke.py']),
        Step('MCP bridge provider smoke', [PYTHON, 'scripts/test-mcp-bridge-provider-smoke.py']),
        Step('Code sandbox smoke', [PYTHON, 'scripts/test-code-sandbox-smoke.py']),
        Step('Compat runtime smoke', [PYTHON, 'scripts/test-compat-runtime-smoke.py', '--bin-dir', bin_dir]),
        Step('Build system delivery bundle', [PYTHON, 'scripts/build-aios-delivery.py', '--no-archive', '--bin-dir', bin_dir, '--cargo-target', host_target, '--sync-overlay', 'aios/image/mkosi.extra']),
        Step('Cross-service health smoke', [PYTHON, 'scripts/test-cross-service-health-smoke.py', '--bin-dir', bin_dir, '--delivery-manifest', 'out/aios-system-delivery/manifest.json']),
        Step('Delivery smoke', [PYTHON, 'scripts/test-image-delivery-smoke.py', '--bundle-dir', 'out/aios-system-delivery']),
        Step('Firstboot hygiene smoke', [PYTHON, 'scripts/test-firstboot-hygiene-smoke.py', '--bundle-dir', 'out/aios-system-delivery']),
        Step('Installer UX smoke', [PYTHON, 'scripts/test-installer-ux-smoke.py']),
        Step('Vendor firmware adapter smoke', [PYTHON, 'scripts/test-vendor-firmware-hook-smoke.py']),
        Step('Container-native build smoke', [PYTHON, 'scripts/test-build-container-native-smoke.py']),
        Step('Image staging smoke', [PYTHON, 'scripts/test-image-staging-smoke.py']),
        Step('Boot preflight smoke', [PYTHON, 'scripts/test-boot-qemu-smoke.py']),
        Step('Full regression suite smoke', [PYTHON, 'scripts/test-full-regression-suite-smoke.py']),
    ]


def system_validation_steps(host_target: str, bin_dir: str) -> list[Step]:
    return [
        Step('Build AIOS binaries', ['cargo', 'build', '--target', host_target, '-p', 'aios-agentd', '-p', 'aios-sessiond', '-p', 'aios-policyd', '-p', 'aios-runtimed', '-p', 'aios-deviced', '-p', 'aios-updated', '-p', 'aios-device-metadata-provider', '-p', 'aios-runtime-local-inference-provider', '-p', 'aios-system-intent-provider', '-p', 'aios-system-files-provider'], cwd=AIOS_DIR),
        Step('Build system delivery bundle', [PYTHON, 'scripts/build-aios-delivery.py', '--no-archive', '--bin-dir', bin_dir, '--cargo-target', host_target, '--sync-overlay', 'aios/image/mkosi.extra']),
        Step('Cross-service health smoke', [PYTHON, 'scripts/test-cross-service-health-smoke.py', '--bin-dir', bin_dir, '--delivery-manifest', 'out/aios-system-delivery/manifest.json']),
        Step('Build system image', ['bash', 'scripts/build-aios-image.sh']),
        Step('Build recovery image', ['bash', 'scripts/build-aios-recovery-image.sh']),
        Step('Build installer image', ['bash', 'scripts/build-aios-installer-image.sh']),
        Step('Run full system delivery validation', [PYTHON, 'scripts/test-system-delivery-validation.py']),
        Step('Build governance evidence index', [PYTHON, 'scripts/build-governance-evidence-index.py']),
        Step('Run release gate', [PYTHON, 'scripts/check-release-gate.py']),
    ]


def steps_for(stage: str, host_target: str, bin_dir: str) -> list[Step]:
    if stage == 'validate':
        return validate_steps(host_target, bin_dir)
    if stage == 'system-validation':
        return system_validation_steps(host_target, bin_dir)
    return [*validate_steps(host_target, bin_dir), *system_validation_steps(host_target, bin_dir)]


def step_slug(index: int, name: str) -> str:
    collapsed = ''.join(ch.lower() if ch.isalnum() else '-' for ch in name)
    while '--' in collapsed:
        collapsed = collapsed.replace('--', '-')
    collapsed = collapsed.strip('-') or 'step'
    return f'{index:02d}-{collapsed}'


def make_skipped_result(step: Step, detail: str) -> dict[str, Any]:
    return {
        'name': step.name,
        'command': ' '.join(step.command),
        'cwd': str(step.cwd),
        'env_overrides': dict(step.env or {}),
        'status': 'skipped',
        'returncode': None,
        'duration_seconds': 0.0,
        'stdout_log': None,
        'stderr_log': None,
        'detail': detail,
    }


def run_step(step: Step, dry_run: bool, logs_dir: Path | None, index: int) -> dict[str, Any]:
    print(f'==> {step.name}')
    print(' '.join(step.command))

    if dry_run:
        return {
            'name': step.name,
            'command': ' '.join(step.command),
            'cwd': str(step.cwd),
            'env_overrides': dict(step.env or {}),
            'status': 'planned',
            'returncode': None,
            'duration_seconds': 0.0,
            'stdout_log': None,
            'stderr_log': None,
            'detail': 'dry-run only; command not executed',
        }

    assert logs_dir is not None
    logs_dir.mkdir(parents=True, exist_ok=True)
    slug = step_slug(index, step.name)
    stdout_log = logs_dir / f'{slug}.stdout.log'
    stderr_log = logs_dir / f'{slug}.stderr.log'

    env = os.environ.copy()
    if step.env:
        env.update(step.env)

    started = time.monotonic()
    with stdout_log.open('w') as stdout_handle, stderr_log.open('w') as stderr_handle:
        completed = subprocess.run(
            step.command,
            cwd=step.cwd,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            check=False,
        )
    duration_seconds = round(time.monotonic() - started, 3)
    status = 'passed' if completed.returncode == 0 else 'failed'
    detail = f'returncode={completed.returncode}'

    return {
        'name': step.name,
        'command': ' '.join(step.command),
        'cwd': str(step.cwd),
        'env_overrides': dict(step.env or {}),
        'status': status,
        'returncode': completed.returncode,
        'duration_seconds': duration_seconds,
        'stdout_log': str(stdout_log),
        'stderr_log': str(stderr_log),
        'detail': detail,
    }


def count_statuses(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {'planned': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
    for item in results:
        status = item.get('status')
        if status in counts:
            counts[status] += 1
    return counts


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        '# AIOS Full Regression Report',
        '',
        f"- Generated at: `{report['generated_at']}`",
        f"- Stage: `{report['stage']}`",
        f"- Execution mode: `{report['execution_mode']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Host target: `{report['host_target']}`",
        f"- Bin dir: `{report['bin_dir']}`",
        f"- Duration: `{report['duration_seconds']}` seconds",
        '',
        '## Step Counts',
        '',
        f"- Planned: `{report['step_counts']['planned']}`",
        f"- Passed: `{report['step_counts']['passed']}`",
        f"- Failed: `{report['step_counts']['failed']}`",
        f"- Skipped: `{report['step_counts']['skipped']}`",
        '',
        '## Steps',
        '',
        '| Step | Status | Returncode | Duration | Detail |',
        '|------|--------|------------|----------|--------|',
    ]
    for item in report['steps']:
        returncode = '' if item['returncode'] is None else str(item['returncode'])
        lines.append(
            f"| `{item['name']}` | `{item['status']}` | `{returncode}` | `{item['duration_seconds']}` | {item['detail']} |"
        )
        if item.get('stdout_log') or item.get('stderr_log'):
            if item.get('stdout_log'):
                lines.append(f"stdout log: `{item['stdout_log']}`")
            if item.get('stderr_log'):
                lines.append(f"stderr log: `{item['stderr_log']}`")
    return '\n'.join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + '\n')


def validate_report(path: Path) -> None:
    schema = json.loads(REGRESSION_REPORT_SCHEMA.read_text())
    payload = json.loads(path.read_text())
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)


def resolve_host_target(dry_run: bool) -> tuple[str, str]:
    host_target = detect_host_target(AIOS_DIR)
    if host_target is None:
        if dry_run:
            return 'unknown-host-target', '<target-bin-dir-unavailable>'
        raise SystemExit('Failed to detect rustc host target')
    return host_target, str(cargo_target_bin_dir(ROOT, host_target))


def build_report(
    args: argparse.Namespace,
    steps: list[Step],
    results: list[dict[str, Any]],
    host_target: str,
    bin_dir: str,
    duration_seconds: float,
) -> dict[str, Any]:
    counts = count_statuses(results)
    if args.dry_run:
        overall_status = 'planned'
    elif counts['failed'] > 0:
        overall_status = 'failed'
    else:
        overall_status = 'passed'

    json_path = args.output_prefix.with_suffix('.json')
    markdown_path = args.output_prefix.with_suffix('.md')
    step_logs_dir = None if args.dry_run else str(args.output_prefix.parent / f'{args.output_prefix.name}-logs')

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'workspace': str(ROOT),
        'stage': args.stage,
        'execution_mode': 'dry-run' if args.dry_run else 'execute',
        'overall_status': overall_status,
        'host_target': host_target,
        'bin_dir': bin_dir,
        'keep_going': args.keep_going,
        'json_report': str(json_path),
        'markdown_report': str(markdown_path),
        'step_logs_dir': step_logs_dir,
        'duration_seconds': round(duration_seconds, 3),
        'step_counts': counts,
        'steps': results,
        'declared_steps': [step.name for step in steps],
    }


def main() -> int:
    args = parse_args()
    require_python_deps()
    host_target, bin_dir = resolve_host_target(args.dry_run)

    if not args.dry_run:
        require_tools(['cargo', 'bash', 'rustc'])

    steps = steps_for(args.stage, host_target, bin_dir)
    results: list[dict[str, Any]] = []
    logs_dir = args.output_prefix.parent / f'{args.output_prefix.name}-logs'
    started = time.monotonic()

    for index, step in enumerate(steps, start=1):
        if not args.dry_run:
            skip_detail = platform_skip_detail(step)
            if skip_detail is not None:
                results.append(make_skipped_result(step, skip_detail))
                continue

        result = run_step(step, args.dry_run, None if args.dry_run else logs_dir, index)
        results.append(result)
        if result['status'] == 'failed' and not args.keep_going:
            for remaining in steps[index:]:
                results.append(make_skipped_result(remaining, 'skipped after earlier step failure'))
            break

    report = build_report(args, steps, results, host_target, bin_dir, time.monotonic() - started)
    json_path = args.output_prefix.with_suffix('.json')
    markdown_path = args.output_prefix.with_suffix('.md')
    write_json(json_path, report)
    write_markdown(markdown_path, render_markdown(report))
    validate_report(json_path)

    print(json.dumps({
        'overall_status': report['overall_status'],
        'stage': report['stage'],
        'execution_mode': report['execution_mode'],
        'json_report': str(json_path),
        'markdown_report': str(markdown_path),
        'step_counts': report['step_counts'],
    }, indent=2, ensure_ascii=False))

    if args.dry_run:
        return 0
    return 1 if report['overall_status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())

