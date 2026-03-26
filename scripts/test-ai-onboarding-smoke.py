#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from host_exec import bash_path, resolve_bash_binary


ROOT = Path(__file__).resolve().parent.parent
ONBOARDING_SCRIPT = ROOT / "aios" / "image" / "firstboot" / "aios-ai-onboarding.sh"
UTF8 = "utf-8"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding=UTF8))


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding=UTF8).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_executable(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=UTF8)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def render_path(path: Path) -> str:
    return bash_path(path) if os.name == "nt" else str(path)


def build_bash_runtime_path(bash_binary: Path, *extra_dirs: Path) -> str:
    entries: list[str] = []
    seen: set[str] = set()

    def append(directory: Path) -> None:
        if not directory.exists():
            return
        rendered = render_path(directory)
        key = rendered.lower() if os.name == "nt" else rendered
        if key in seen:
            return
        seen.add(key)
        entries.append(rendered)

    for directory in extra_dirs:
        append(directory)
    append(bash_binary.parent)
    append(bash_binary.parent.parent / "usr" / "bin")
    append(bash_binary.parent.parent / "bin")
    return os.pathsep.join(entries)


def run_onboarding(root_dir: Path, env_overrides: dict[str, str]) -> tuple[dict, dict, dict[str, str]]:
    bash_binary = resolve_bash_binary()
    if bash_binary is None:
        raise RuntimeError("usable bash runtime unavailable")

    env = os.environ.copy()
    env.update(
        {
            "AIOS_FIRSTBOOT_ROOT": render_path(root_dir),
            "AIOS_FIRSTBOOT_AI_ENABLED": "1",
            "AIOS_FIRSTBOOT_AI_MODE": "hybrid",
            "AIOS_FIRSTBOOT_AI_PRIVACY_PROFILE": "balanced",
            "AIOS_FIRSTBOOT_AI_AUTO_PULL_DEFAULT_MODEL": "1",
            "AIOS_FIRSTBOOT_AI_AUTO_MODEL_SOURCE": "ollama-library",
            "AIOS_FIRSTBOOT_AI_AUTO_MODEL_ID": "qwen2.5:7b-instruct",
            "PATH": build_bash_runtime_path(bash_binary),
        }
    )
    env.update(env_overrides)

    completed = subprocess.run(
        [str(bash_binary), render_path(ONBOARDING_SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    report_path = root_dir / "var" / "lib" / "aios" / "onboarding" / "ai-onboarding-report.json"
    readiness_path = root_dir / "var" / "lib" / "aios" / "runtime" / "ai-readiness.json"
    runtime_env_path = root_dir / "etc" / "aios" / "runtime" / "platform.env"

    require(report_path.exists(), f"missing onboarding report: {report_path}")
    require(readiness_path.exists(), f"missing AI readiness file: {readiness_path}")

    report = load_json(report_path)
    readiness = load_json(readiness_path)
    runtime_env = load_env(runtime_env_path)
    require(
        "AIOS_AI_ONBOARDING state=" in completed.stdout,
        "onboarding script did not emit completion summary",
    )
    return report, readiness, runtime_env


def validate_auto_pull_success(temp_root: Path) -> dict[str, object]:
    scenario_root = temp_root / "auto-pull-success"
    fake_bin_dir = scenario_root / "host-bin"
    ollama_log = scenario_root / "ollama.log"
    write_executable(
        fake_bin_dir / "ollama",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$AIOS_TEST_OLLAMA_LOG\"\n"
        "if [[ \"${1:-}\" != \"pull\" ]]; then\n"
        "  exit 2\n"
        "fi\n"
        "if [[ \"${2:-}\" != \"$AIOS_EXPECTED_MODEL_ID\" ]]; then\n"
        "  exit 3\n"
        "fi\n"
        "exit 0\n",
    )

    report, readiness, runtime_env = run_onboarding(
        scenario_root,
        {
            "PATH": build_bash_runtime_path(resolve_bash_binary() or Path("bash"), fake_bin_dir),
            "AIOS_TEST_OLLAMA_LOG": render_path(ollama_log),
            "AIOS_EXPECTED_MODEL_ID": "qwen2.5:7b-instruct",
            "AIOS_FIRSTBOOT_AI_LOCAL_OLLAMA_ENDPOINT_BASE_URL": "http://127.0.0.1:11434/v1",
        },
    )

    require(report.get("auto_pull_attempted") is True, "success scenario should attempt auto pull")
    require(report.get("auto_pull_status") == "pulled", "success scenario auto pull status mismatch")
    require(
        report.get("auto_pull_message") == "ollama pull completed",
        "success scenario auto pull message mismatch",
    )
    require(
        report.get("auto_pull_endpoint_adopted") is True,
        "success scenario should adopt endpoint after pull",
    )
    require(
        report.get("auto_pull_command") == "ollama pull qwen2.5:7b-instruct",
        "success scenario auto pull command mismatch",
    )
    require(
        report.get("endpoint_base_url") == "http://127.0.0.1:11434/v1",
        "success scenario endpoint base url mismatch",
    )
    require(
        report.get("endpoint_model") == "qwen2.5:7b-instruct",
        "success scenario endpoint model mismatch",
    )
    require(
        report.get("endpoint_configured") is True,
        "success scenario should configure endpoint",
    )
    require(
        report.get("readiness_state") == "hybrid-remote-only",
        "success scenario readiness state mismatch",
    )
    require(
        report.get("next_action") == "none",
        "success scenario next action mismatch",
    )
    require(
        readiness.get("state") == "hybrid-remote-only",
        "success scenario readiness file state mismatch",
    )
    require(
        readiness.get("next_action") == "none",
        "success scenario readiness file next_action mismatch",
    )
    require(
        runtime_env.get("AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL") == "http://127.0.0.1:11434/v1",
        "success scenario runtime env missing endpoint base url",
    )
    require(
        runtime_env.get("AIOS_RUNTIMED_AI_ENDPOINT_MODEL") == "qwen2.5:7b-instruct",
        "success scenario runtime env missing endpoint model",
    )
    require(
        ollama_log.read_text(encoding=UTF8).strip() == "pull qwen2.5:7b-instruct",
        "success scenario fake ollama invocation mismatch",
    )

    return {
        "scenario": "auto-pull-success",
        "readiness_state": report.get("readiness_state"),
        "endpoint_base_url": report.get("endpoint_base_url"),
        "endpoint_model": report.get("endpoint_model"),
        "auto_pull_status": report.get("auto_pull_status"),
    }


def validate_provider_unavailable(temp_root: Path) -> dict[str, object]:
    scenario_root = temp_root / "auto-pull-provider-unavailable"
    bash_binary = resolve_bash_binary()
    require(bash_binary is not None, "usable bash runtime unavailable")

    report, readiness, runtime_env = run_onboarding(
        scenario_root,
        {
            "PATH": build_bash_runtime_path(bash_binary),
        },
    )

    require(
        report.get("auto_pull_attempted") is True,
        "provider unavailable scenario should attempt auto pull",
    )
    require(
        report.get("auto_pull_status") == "provider-unavailable",
        "provider unavailable scenario auto pull status mismatch",
    )
    require(
        report.get("auto_pull_message") == "ollama CLI is not installed",
        "provider unavailable scenario auto pull message mismatch",
    )
    require(
        report.get("endpoint_configured") is False,
        "provider unavailable scenario should not configure endpoint",
    )
    require(
        report.get("readiness_state") == "setup-pending",
        "provider unavailable scenario readiness state mismatch",
    )
    require(
        report.get("next_action") == "resolve-auto-pull",
        "provider unavailable scenario next action mismatch",
    )
    require(
        "default model pull could not complete:" in str(report.get("readiness_reason")),
        "provider unavailable scenario readiness reason mismatch",
    )
    require(
        readiness.get("state") == "setup-pending",
        "provider unavailable scenario readiness file state mismatch",
    )
    require(
        readiness.get("next_action") == "resolve-auto-pull",
        "provider unavailable scenario readiness file next_action mismatch",
    )
    require(
        runtime_env.get("AIOS_RUNTIMED_AI_ENDPOINT_BASE_URL") is None,
        "provider unavailable scenario should not persist endpoint base url",
    )
    require(
        runtime_env.get("AIOS_RUNTIMED_AI_ENDPOINT_MODEL") is None,
        "provider unavailable scenario should not persist endpoint model",
    )

    return {
        "scenario": "auto-pull-provider-unavailable",
        "readiness_state": report.get("readiness_state"),
        "next_action": report.get("next_action"),
        "auto_pull_status": report.get("auto_pull_status"),
    }


def main() -> int:
    require(ONBOARDING_SCRIPT.exists(), f"missing onboarding script: {ONBOARDING_SCRIPT}")
    bash_binary = resolve_bash_binary()
    if bash_binary is None:
        print("AI onboarding smoke skipped: usable bash runtime unavailable on this platform")
        return 0

    temp_root = Path(tempfile.mkdtemp(prefix="aios-ai-onboarding-smoke-"))
    try:
        summary = {
            "onboarding_script": str(ONBOARDING_SCRIPT),
            "scenarios": [
                validate_auto_pull_success(temp_root),
                validate_provider_unavailable(temp_root),
            ],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
