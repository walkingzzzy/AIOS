#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "placeholder-implementation-gate-report"
UTF8 = "utf-8"

LOCAL_CPU_WORKER = ROOT / "aios" / "runtime" / "workers" / "local_cpu_worker.py"
DEFAULT_RUNTIME_PROFILE = ROOT / "aios" / "runtime" / "profiles" / "default-runtime-profile.yaml"
WORKER_INTEGRATION_PROFILE = ROOT / "aios" / "runtime" / "profiles" / "worker-integration-profile.yaml"
RUNTIMED_CPU_BACKEND = ROOT / "aios" / "services" / "runtimed" / "src" / "backend" / "cpu.rs"
DEVICED_ADAPTERS = ROOT / "aios" / "services" / "deviced" / "src" / "adapters.rs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that placeholder AI implementations do not leak into product paths"
    )
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding=UTF8)


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding=UTF8)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Placeholder Implementation Gate Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
    ]
    for item in report["checks"]:
        lines.append(
            f"| `{item['check_id']}` | `{item['status']}` | {item['detail']} |"
        )
    return "\n".join(lines)


def make_request(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "worker_contract": "runtime-worker-v1",
        "backend_id": "local-cpu",
        "session_id": "placeholder-gate-session",
        "task_id": "placeholder-gate-task",
        "prompt": "Describe AI readiness state.",
        "model": "placeholder-gate-model",
        "estimated_latency_ms": 100,
        "timeout_ms": 5000,
    }
    payload.update(overrides)
    return payload


def invoke_local_cpu_worker(env_overrides: dict[str, str]) -> dict[str, Any]:
    env = os.environ.copy()
    for name in [
        "AIOS_WORKER_BACKEND",
        "AIOS_WORKER_ALLOW_ECHO_FALLBACK",
        "AIOS_WORKER_PRODUCT_MODE",
        "AIOS_RUNTIMED_PRODUCT_MODE",
        "AIOS_WORKER_MODEL_PATH",
        "AIOS_MODEL_DIR",
    ]:
        env.pop(name, None)
    env.update(env_overrides)

    completed = subprocess.run(
        [sys.executable, str(LOCAL_CPU_WORKER)],
        input=json.dumps(make_request()),
        capture_output=True,
        text=True,
        timeout=10.0,
        cwd=ROOT,
        env=env,
        check=False,
    )
    require(
        completed.returncode == 0,
        f"local_cpu_worker exited with {completed.returncode}: {completed.stderr.strip()}",
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"local_cpu_worker returned non-json payload: {exc}") from exc


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding=UTF8))


def check_worker_product_mode_blocks_explicit_echo() -> tuple[str, list[str]]:
    response = invoke_local_cpu_worker(
        {
            "AIOS_WORKER_BACKEND": "echo",
            "AIOS_WORKER_ALLOW_ECHO_FALLBACK": "0",
            "AIOS_WORKER_PRODUCT_MODE": "1",
            "AIOS_RUNTIMED_PRODUCT_MODE": "1",
        }
    )
    require(
        response.get("route_state") == "local-cpu-not-ready",
        f"unexpected route_state: {response.get('route_state')!r}",
    )
    require(response.get("rejected") is True, "product mode echo path must be rejected")
    require(
        response.get("worker_error_class") == "unavailable",
        f"unexpected worker_error_class: {response.get('worker_error_class')!r}",
    )
    require(
        response.get("provider_status") == "unavailable",
        f"unexpected provider_status: {response.get('provider_status')!r}",
    )
    reason = str(response.get("reason") or "")
    require("AI is not ready" in reason, f"unexpected reason: {reason!r}")
    notes = response.get("notes") or []
    require("product_mode=true" in notes, "product_mode note missing from unavailable response")
    require(
        "echo_fallback_enabled=false" in notes,
        "echo fallback disabled note missing from unavailable response",
    )
    return (
        "product mode explicit echo path is rejected with not-ready semantics",
        [str(LOCAL_CPU_WORKER)],
    )


def check_worker_dev_echo_remains_opt_in() -> tuple[str, list[str]]:
    response = invoke_local_cpu_worker(
        {
            "AIOS_WORKER_BACKEND": "echo",
            "AIOS_WORKER_ALLOW_ECHO_FALLBACK": "1",
            "AIOS_WORKER_PRODUCT_MODE": "0",
            "AIOS_RUNTIMED_PRODUCT_MODE": "0",
        }
    )
    require(
        response.get("route_state") == "local-cpu-echo",
        f"unexpected route_state: {response.get('route_state')!r}",
    )
    require(response.get("rejected") is False, "dev echo path should remain available")
    require(response.get("degraded") is True, "dev echo path should stay degraded")
    require(
        response.get("provider_status") == "degraded",
        f"unexpected provider_status: {response.get('provider_status')!r}",
    )
    notes = response.get("notes") or []
    require("backend=echo" in notes, "echo backend note missing from dev path response")
    return (
        "dev/test echo path remains explicit opt-in and is still separated from product mode",
        [str(LOCAL_CPU_WORKER)],
    )


def check_default_profile_does_not_bind_dev_worker() -> tuple[str, list[str]]:
    profile = load_yaml(DEFAULT_RUNTIME_PROFILE)
    managed_worker_commands = profile.get("managed_worker_commands") or {}
    hardware_profile_managed_worker_commands = (
        profile.get("hardware_profile_managed_worker_commands") or {}
    )
    require(
        isinstance(managed_worker_commands, dict),
        "default runtime profile managed_worker_commands must be a mapping",
    )
    require(
        isinstance(hardware_profile_managed_worker_commands, dict),
        "default runtime profile hardware_profile_managed_worker_commands must be a mapping",
    )
    require(
        "local-cpu" not in managed_worker_commands,
        "default runtime profile must not bind local-cpu to a dev worker command",
    )
    serialized = json.dumps(profile, ensure_ascii=False)
    require(
        "local_cpu_worker.py" not in serialized,
        "default runtime profile must not reference local_cpu_worker.py",
    )
    require(
        "AIOS_RUNTIMED_ALLOW_INLINE_LOCAL_CPU" not in serialized,
        "default runtime profile must not enable inline local CPU override",
    )
    return (
        "default runtime profile does not wire dev-only local CPU worker or inline override",
        [str(DEFAULT_RUNTIME_PROFILE)],
    )


def check_worker_integration_profile_keeps_dev_worker_separate() -> tuple[str, list[str]]:
    profile = load_yaml(WORKER_INTEGRATION_PROFILE)
    backends = profile.get("backends") or {}
    local_cpu = backends.get("local-cpu") or {}
    worker_command = str(local_cpu.get("worker_command") or "").strip()
    require(worker_command, "worker-integration profile must keep a dedicated local-cpu worker command")
    require(
        "local_cpu_worker.py" in worker_command,
        "worker-integration profile must isolate the dev/test local CPU worker path",
    )
    require(
        str(local_cpu.get("transport") or "") == "stdio",
        "worker-integration profile local-cpu transport must stay explicit",
    )
    return (
        "worker-integration profile keeps the dev/test worker path separate from the default product profile",
        [str(WORKER_INTEGRATION_PROFILE)],
    )


def check_runtimed_source_guard_present() -> tuple[str, list[str]]:
    content = RUNTIMED_CPU_BACKEND.read_text(encoding=UTF8)
    require(
        'env_truthy("AIOS_RUNTIMED_PRODUCT_MODE")' in content,
        "runtimed local-cpu backend must still read AIOS_RUNTIMED_PRODUCT_MODE",
    )
    require(
        'env_truthy("AIOS_RUNTIMED_ALLOW_INLINE_LOCAL_CPU")' in content,
        "runtimed local-cpu backend must keep the explicit inline override gate",
    )
    require(
        "built-in worker is reserved for dev/test use" in content,
        "runtimed local-cpu backend lost the product-mode block reason",
    )
    require(
        "BackendReadiness::unavailable" in content,
        "runtimed local-cpu backend must expose unavailable readiness when inline worker is blocked",
    )
    return (
        "runtimed local-cpu source retains explicit product-mode guard and unavailable readiness path",
        [str(RUNTIMED_CPU_BACKEND)],
    )


def check_deviced_source_guard_present() -> tuple[str, list[str]]:
    content = DEVICED_ADAPTERS.read_text(encoding=UTF8)
    require(
        "product mode forbids preview-only execution path" in content,
        "deviced adapters lost the product-mode preview-path guard",
    )
    require(
        re.search(
            r'matches!\(\s*plan\.execution_path\.as_str\(\)\s*,\s*"builtin-preview"\s*\|\s*"native-stub"\s*\)',
            content,
            re.DOTALL,
        )
        is not None,
        "deviced adapters must keep builtin-preview/native-stub grouped under the product-mode guard",
    )
    require(
        "product_mode_blocks_builtin_preview_capture" in content,
        "deviced regression test for builtin-preview guard is missing",
    )
    require(
        "product_mode_blocks_native_stub_ui_tree_snapshot" in content,
        "deviced regression test for native-stub guard is missing",
    )
    return (
        "deviced adapters retain preview-path product-mode guard and regression anchors",
        [str(DEVICED_ADAPTERS)],
    )


def run_check(
    check_id: str,
    fn: Callable[[], tuple[str, list[str]]],
) -> dict[str, Any]:
    try:
        detail, artifacts = fn()
        return {
            "check_id": check_id,
            "status": "passed",
            "detail": detail,
            "artifacts": artifacts,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "check_id": check_id,
            "status": "failed",
            "detail": str(exc),
            "artifacts": [],
        }


def main() -> int:
    args = parse_args()
    checks = [
        run_check(
            "worker-product-mode-blocks-explicit-echo",
            check_worker_product_mode_blocks_explicit_echo,
        ),
        run_check(
            "worker-dev-echo-remains-opt-in",
            check_worker_dev_echo_remains_opt_in,
        ),
        run_check(
            "default-profile-does-not-bind-dev-worker",
            check_default_profile_does_not_bind_dev_worker,
        ),
        run_check(
            "worker-integration-profile-keeps-dev-worker-separate",
            check_worker_integration_profile_keeps_dev_worker_separate,
        ),
        run_check("runtimed-source-guard-present", check_runtimed_source_guard_present),
        run_check("deviced-source-guard-present", check_deviced_source_guard_present),
    ]
    overall_status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "checks": checks,
    }
    json_path = args.output_prefix.with_suffix(".json")
    markdown_path = args.output_prefix.with_suffix(".md")
    write_json(json_path, report)
    write_markdown(markdown_path, render_markdown(report))
    print(
        json.dumps(
            {
                "overall_status": overall_status,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "failed_checks": [
                    item["check_id"] for item in checks if item["status"] != "passed"
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if overall_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
