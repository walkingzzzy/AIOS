#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PREFIX = ROOT / "out" / "validation" / "image-build-strategy-report"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that Linux x86_64 image builds prefer the container-native delivery path"
    )
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_script(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n")


def result(name: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": "passed", "detail": detail}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AIOS Image Build Strategy Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status']}`",
        f"- Image script: `{report['image_script']}`",
        f"- Overlay script: `{report['overlay_script']}`",
        "",
        "## Results",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
    ]
    for item in report["results"]:
        lines.append(f"| `{item['name']}` | `{item['status']}` | {item['detail']} |")

    lines.extend(
        [
            "",
            "## Preflight Snapshots",
            "",
            "### Image Preflight",
            "```json",
            json.dumps(report["image_preflight"], indent=2, ensure_ascii=False),
            "```",
            "",
            "### Overlay Preflight",
            "```json",
            json.dumps(report["overlay_preflight"], indent=2, ensure_ascii=False),
            "```",
            "",
            "### Explicit Bin Dir Preflight",
            "```json",
            json.dumps(report["explicit_bin_dir_preflight"], indent=2, ensure_ascii=False),
            "```",
        ]
    )
    return "\n".join(lines)


def run_preflight(script: Path, extra_env: dict[str, str]) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(extra_env)
    completed = subprocess.run(
        ["bash", str(script), "--preflight"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return json.loads(completed.stdout.strip() or "{}")


def build_report(
    *,
    results: list[dict[str, str]],
    image_preflight: dict[str, Any],
    overlay_preflight: dict[str, Any],
    explicit_bin_dir_preflight: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "passed",
        "image_script": "scripts/build-aios-image.sh",
        "overlay_script": "scripts/sync-aios-image-overlay.sh",
        "results": results,
        "image_preflight": image_preflight,
        "overlay_preflight": overlay_preflight,
        "explicit_bin_dir_preflight": explicit_bin_dir_preflight,
    }


def main() -> int:
    args = parse_args()

    with tempfile.TemporaryDirectory(prefix="aios-image-strategy-") as temp_dir:
        fake_bin = Path(temp_dir)
        cached_container_bin_dir = fake_bin / "cached-container-bin"
        fake_no_docker_bin = fake_bin / "no-docker-bin"
        cached_container_bin_dir.mkdir(parents=True, exist_ok=True)
        fake_no_docker_bin.mkdir(parents=True, exist_ok=True)
        write_script(
            fake_bin / "docker",
            """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "ps" ]]; then
  exit 0
fi
if [[ "${1:-}" == "version" ]]; then
  exit 0
fi
if [[ "${1:-}" == "buildx" && "${2:-}" == "version" ]]; then
  exit 0
fi
exit 64
""",
        )
        write_script(
            fake_bin / "git",
            """#!/usr/bin/env bash
set -euo pipefail
exit 0
""",
        )
        write_script(
            fake_no_docker_bin / "git",
            """#!/usr/bin/env bash
set -euo pipefail
exit 0
""",
        )
        write_script(
            fake_no_docker_bin / "docker",
            """#!/usr/bin/env bash
set -euo pipefail
exit 127
""",
        )
        for name in [
            "agentd",
            "sessiond",
            "policyd",
            "runtimed",
            "deviced",
            "updated",
            "device-metadata-provider",
            "runtime-local-inference-provider",
            "system-intent-provider",
            "system-files-provider",
        ]:
            write_script(
                cached_container_bin_dir / name,
                "#!/usr/bin/env bash\nexit 0\n",
            )

        base_env = {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "AIOS_HOST_TARGET_OVERRIDE": "x86_64-unknown-linux-gnu",
        }

        image_preflight = run_preflight(ROOT / "scripts" / "build-aios-image.sh", base_env)
        overlay_preflight = run_preflight(ROOT / "scripts" / "sync-aios-image-overlay.sh", base_env)
        explicit_bin_dir_preflight = run_preflight(
            ROOT / "scripts" / "build-aios-image.sh",
            {
                **base_env,
                "AIOS_BIN_DIR": str(ROOT / "aios" / "target" / "debug"),
            },
        )
        cached_container_preflight = run_preflight(
            ROOT / "scripts" / "build-aios-image.sh",
            {
                "PATH": f"{fake_no_docker_bin}:{os.environ['PATH']}",
                "AIOS_HOST_TARGET_OVERRIDE": "x86_64-unknown-linux-gnu",
                "AIOS_DELIVERY_CACHED_BIN_DIR": str(cached_container_bin_dir),
            },
        )
        cached_container_overlay_preflight = run_preflight(
            ROOT / "scripts" / "sync-aios-image-overlay.sh",
            {
                "PATH": f"{fake_no_docker_bin}:{os.environ['PATH']}",
                "AIOS_HOST_TARGET_OVERRIDE": "x86_64-unknown-linux-gnu",
                "AIOS_DELIVERY_CACHED_BIN_DIR": str(cached_container_bin_dir),
            },
        )

    results: list[dict[str, str]] = []

    require(
        image_preflight["linux_binary_strategy"] == "container-native-linux-x86_64",
        "image preflight should prefer container-native strategy on Linux x86_64 when docker buildx is available",
    )
    require(image_preflight["docker_available"] is True, "image preflight should report docker availability")
    require(image_preflight["buildx_available"] is True, "image preflight should report buildx availability")
    require(image_preflight["host_target"] == "x86_64-unknown-linux-gnu", "image preflight host_target mismatch")
    results.append(
        result(
            "image-preflight-preference",
            "build-aios-image preflight prefers container-native-linux-x86_64 on Linux x86_64 when docker buildx is available",
        )
    )

    require(
        overlay_preflight["linux_binary_strategy"] == "container-native-linux-x86_64",
        "overlay sync preflight should prefer container-native strategy on Linux x86_64 when docker buildx is available",
    )
    require(overlay_preflight["host_target"] == "x86_64-unknown-linux-gnu", "overlay preflight host_target mismatch")
    results.append(
        result(
            "overlay-preflight-preference",
            "sync-aios-image-overlay preflight follows the same container-native-linux-x86_64 preference on Linux x86_64",
        )
    )

    require(
        explicit_bin_dir_preflight["linux_binary_strategy"] == "host-bin-dir",
        "explicit AIOS_BIN_DIR should continue to force host-bin-dir strategy",
    )
    results.append(
        result(
            "explicit-bin-dir-override",
            "explicit AIOS_BIN_DIR continues to force host-bin-dir as the deterministic emergency fallback",
        )
    )

    require(
        cached_container_preflight["linux_binary_strategy"] == "container-cached-bin-dir",
        "image preflight should prefer cached container-native bin-dir on Linux x86_64 when docker buildx is unavailable",
    )
    require(
        cached_container_preflight["cached_container_bin_dir_ready"] is True,
        "image preflight should report cached container bin-dir readiness",
    )
    require(
        cached_container_overlay_preflight["linux_binary_strategy"] == "container-cached-bin-dir",
        "overlay sync preflight should prefer cached container-native bin-dir on Linux x86_64 when docker buildx is unavailable",
    )
    require(
        cached_container_overlay_preflight["cached_container_bin_dir_ready"] is True,
        "overlay preflight should report cached container bin-dir readiness",
    )
    results.append(
        result(
            "cached-container-bin-fallback",
            "when docker buildx is unavailable, Linux x86_64 now prefers a previously generated container-native bin-dir before falling back to host-bin-dir",
        )
    )

    report = build_report(
        results=results,
        image_preflight=image_preflight,
        overlay_preflight=overlay_preflight,
        explicit_bin_dir_preflight=explicit_bin_dir_preflight,
    )
    write_json(args.output_prefix.with_suffix(".json"), report)
    write_markdown(args.output_prefix.with_suffix(".md"), render_markdown(report))
    print("image build strategy smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
