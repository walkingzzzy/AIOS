#!/usr/bin/env python3
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMP_ROOT_DIR = ROOT / "out" / "tmp"


def make_temp_dir(prefix: str) -> Path:
    TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT_DIR / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_python(script: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    return completed.stdout.strip()


@contextmanager
def static_http_root(root: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    handler = functools.partial(QuietHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    temp_root = make_temp_dir("aios-model-library-distribution-")
    failed = False
    try:
        model_dir = temp_root / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_registry = temp_root / "model-registry.json"
        ai_readiness = temp_root / "ai-readiness.json"
        ai_onboarding_report = temp_root / "ai-onboarding-report.json"
        preload_root = temp_root / "preload"
        preload_root.mkdir(parents=True, exist_ok=True)
        download_stage = temp_root / "downloads"
        source_root = temp_root / "source-root"
        source_root.mkdir(parents=True, exist_ok=True)
        source_map = temp_root / "recommended-model-sources.json"
        profile = temp_root / "shell-profile.json"
        catalog = temp_root / "recommended-model-catalog.json"

        ai_readiness.write_text(
            json.dumps(
                {
                    "state": "setup-pending",
                    "reason": "recommended models pending",
                    "ai_enabled": True,
                    "ai_mode": "local",
                    "local_model_count": 0,
                    "endpoint_configured": False,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        ai_onboarding_report.write_text(
            json.dumps(
                {
                    "ai_enabled": True,
                    "ai_mode": "local",
                    "privacy_profile": "balanced",
                    "readiness_state": "setup-pending",
                    "readiness_reason": "recommended models pending",
                    "local_model_count": 0,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        preload_model = preload_root / "phi-mini.gguf"
        preload_model.write_bytes(b"GGUF" + b"\x00" * 64)
        download_model = source_root / "embed-demo.safetensors"
        download_model.write_bytes(b'{"__metadata__": {}}')

        with static_http_root(source_root) as base_url:
            source_map.write_text(
                json.dumps(
                    {
                        "mappings": {
                            "embed-demo": {
                                "value": f"{base_url}/embed-demo.safetensors",
                                "filename": "embed-demo.safetensors",
                            }
                        }
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            catalog.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "catalog_id": "smoke-recommended-models",
                        "models": [
                            {
                                "model_id": "phi-mini",
                                "display_name": "Phi Mini",
                                "capabilities": ["text-generation"],
                                "formats": ["gguf"],
                                "distribution_strategy": "preload",
                                "default_recommended": True,
                                "sources": [
                                    {
                                        "kind": "preload-image",
                                        "value": "phi-mini.gguf",
                                    }
                                ],
                            },
                            {
                                "model_id": "embed-demo",
                                "display_name": "Embed Demo",
                                "capabilities": ["embedding"],
                                "formats": ["safetensors"],
                                "distribution_strategy": "firstboot-download",
                                "default_recommended": True,
                                "sources": [
                                    {
                                        "kind": "firstboot-download",
                                        "value": "embed-demo",
                                    }
                                ],
                            },
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            profile.write_text(
                json.dumps(
                    {
                        "profile_id": "model-library-distribution-smoke",
                        "components": {
                            "model_library": True,
                        },
                        "paths": {
                            "ai_readiness_path": str(ai_readiness),
                            "ai_onboarding_report_path": str(ai_onboarding_report),
                            "ai_model_dir": str(model_dir),
                            "ai_model_registry": str(model_registry),
                            "ai_recommended_preload_root": str(preload_root),
                            "ai_recommended_source_map": str(source_map),
                            "ai_recommended_download_staging_dir": str(download_stage),
                        },
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["AIOS_MODEL_RECOMMENDED_CATALOG"] = str(catalog)

            output = run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
                "--profile",
                str(profile),
                "--json",
                "panel",
                "model-library",
                "model",
                env=env,
            )
            panel = json.loads(output)
            require(panel["panel_id"] == "model-library-panel", "model-library panel id mismatch")
            require(
                panel["meta"]["recommended_distribution_actionable_count"] == 2,
                "model-library actionable recommended count mismatch",
            )

            output = run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
                "--profile",
                str(profile),
                "--json",
                "panel",
                "model-library",
                "action",
                "--action",
                "install-recommended-model",
                "--model-id",
                "phi-mini",
                env=env,
            )
            install_single = json.loads(output)
            require(install_single["status"] == "applied", "single recommended install status mismatch")
            require(install_single["imported_count"] == 1, "single recommended install imported count mismatch")
            require(install_single["local_model_count"] == 1, "single recommended install local count mismatch")

            output = run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
                "--profile",
                str(profile),
                "--json",
                "panel",
                "model-library",
                "action",
                "--action",
                "apply-recommended-strategies",
                env=env,
            )
            apply_all = json.loads(output)
            require(apply_all["status"] == "applied", "recommended strategy apply status mismatch")
            require(apply_all["imported_count"] == 1, "recommended strategy apply imported count mismatch")
            require(apply_all["downloaded_count"] == 1, "recommended strategy apply download count mismatch")
            require(apply_all["local_model_count"] == 2, "recommended strategy apply local count mismatch")
            require(
                apply_all["defaults"].get("text-generation") == "phi-mini",
                "recommended strategy text default mismatch",
            )
            require(
                apply_all["defaults"].get("embedding") == "embed-demo",
                "recommended strategy embedding default mismatch",
            )

            output = run_python(
                ROOT / "aios" / "shell" / "shellctl.py",
                "--profile",
                str(profile),
                "--json",
                "panel",
                "model-library",
                "model",
                env=env,
            )
            final_panel = json.loads(output)
            require(
                final_panel["meta"]["recommended_installed_count"] == 2,
                "model-library final recommended installed count mismatch",
            )
            require(
                final_panel["meta"]["local_model_count"] == 2,
                "model-library final local count mismatch",
            )

        print("model library distribution smoke passed")
        return 0
    except Exception as error:  # noqa: BLE001
        failed = True
        print(f"model library distribution smoke failed: {error}")
        return 1
    finally:
        if failed:
            print(f"state kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
