#!/usr/bin/env python3
"""
Smoke tests for the AIOS local-cpu inference worker (runtime-worker-v1 contract).

Runs the worker as a subprocess and validates the JSON protocol without
requiring any ML libraries.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKER_SCRIPT = REPO_ROOT / "aios" / "runtime" / "workers" / "local_cpu_worker.py"

WORKER_CONTRACT = "runtime-worker-v1"
BACKEND_ID = "local-cpu"
RESPONSE_REQUIRED_FIELDS = {"worker_contract", "backend_id", "route_state", "content", "rejected", "degraded"}


def _invoke_worker(
    payload: dict[str, Any] | str,
    *,
    timeout: float = 10.0,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env["AIOS_WORKER_BACKEND"] = "echo"
    env.pop("AIOS_WORKER_MODEL_PATH", None)
    if env_overrides:
        env.update(env_overrides)

    stdin_data = payload if isinstance(payload, str) else json.dumps(payload)

    return subprocess.run(
        [sys.executable, str(WORKER_SCRIPT)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _make_request(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "worker_contract": WORKER_CONTRACT,
        "backend_id": BACKEND_ID,
        "session_id": "smoke-session-1",
        "task_id": "smoke-task-1",
        "prompt": "What is AIOS?",
        "model": "smoke-model",
        "estimated_latency_ms": 100,
        "timeout_ms": 5000,
    }
    base.update(overrides)
    return base


class TestLocalCpuWorkerSmoke(unittest.TestCase):
    """Verify the local-cpu worker honours the runtime-worker-v1 contract."""

    def test_worker_script_exists(self) -> None:
        self.assertTrue(WORKER_SCRIPT.is_file(), f"worker script not found at {WORKER_SCRIPT}")

    # ------------------------------------------------------------------
    # Echo mode – basic contract conformance
    # ------------------------------------------------------------------

    def test_echo_returns_valid_contract_response(self) -> None:
        result = _invoke_worker(_make_request())
        self.assertEqual(result.returncode, 0, f"worker exited with error: {result.stderr}")
        resp = json.loads(result.stdout)

        missing = RESPONSE_REQUIRED_FIELDS - set(resp.keys())
        self.assertFalse(missing, f"response missing required fields: {missing}")

        self.assertEqual(resp["worker_contract"], WORKER_CONTRACT)
        self.assertEqual(resp["backend_id"], BACKEND_ID)
        self.assertIsInstance(resp["content"], str)
        self.assertIsInstance(resp["rejected"], bool)
        self.assertIsInstance(resp["degraded"], bool)
        self.assertIsInstance(resp["route_state"], str)

    def test_echo_content_contains_prompt_info(self) -> None:
        prompt = "Hello from smoke test"
        result = _invoke_worker(_make_request(prompt=prompt))
        resp = json.loads(result.stdout)
        self.assertIn(str(len(prompt)), resp["content"])

    def test_echo_is_degraded(self) -> None:
        result = _invoke_worker(_make_request())
        resp = json.loads(result.stdout)
        self.assertTrue(resp["degraded"])
        self.assertFalse(resp["rejected"])

    def test_echo_route_state(self) -> None:
        result = _invoke_worker(_make_request())
        resp = json.loads(result.stdout)
        self.assertEqual(resp["route_state"], "local-cpu-echo")

    def test_echo_notes_are_list_of_strings(self) -> None:
        result = _invoke_worker(_make_request())
        resp = json.loads(result.stdout)
        self.assertIn("notes", resp)
        self.assertIsInstance(resp["notes"], list)
        for note in resp["notes"]:
            self.assertIsInstance(note, str)

    def test_echo_has_optional_metadata_fields(self) -> None:
        result = _invoke_worker(_make_request())
        resp = json.loads(result.stdout)
        self.assertIn("runtime_service_id", resp)
        self.assertIn("queue_saturated", resp)
        self.assertFalse(resp["queue_saturated"])

    # ------------------------------------------------------------------
    # Request validation
    # ------------------------------------------------------------------

    def test_missing_required_fields_returns_error(self) -> None:
        incomplete = {"prompt": "hello"}
        result = _invoke_worker(incomplete)
        self.assertNotEqual(result.returncode, 0)
        resp = json.loads(result.stdout)
        self.assertTrue(resp.get("worker_error", False))
        self.assertIn("missing required fields", resp.get("reason", ""))

    def test_empty_stdin_returns_error(self) -> None:
        result = _invoke_worker("")
        self.assertNotEqual(result.returncode, 0)
        resp = json.loads(result.stdout)
        self.assertTrue(resp.get("worker_error", False))

    def test_invalid_json_returns_error(self) -> None:
        result = _invoke_worker("{not valid json}")
        self.assertNotEqual(result.returncode, 0)
        resp = json.loads(result.stdout)
        self.assertTrue(resp.get("worker_error", False))

    # ------------------------------------------------------------------
    # Error response structure
    # ------------------------------------------------------------------

    def test_error_response_has_required_contract_fields(self) -> None:
        result = _invoke_worker("")
        resp = json.loads(result.stdout)
        missing = RESPONSE_REQUIRED_FIELDS - set(resp.keys())
        self.assertFalse(missing, f"error response missing required fields: {missing}")
        self.assertEqual(resp["worker_contract"], WORKER_CONTRACT)
        self.assertEqual(resp["backend_id"], BACKEND_ID)
        self.assertTrue(resp["rejected"])
        self.assertTrue(resp["degraded"])

    def test_error_response_has_worker_error_flag(self) -> None:
        result = _invoke_worker("{bad")
        resp = json.loads(result.stdout)
        self.assertTrue(resp.get("worker_error", False))
        self.assertIn("worker_error_class", resp)

    # ------------------------------------------------------------------
    # Timeout handling
    # ------------------------------------------------------------------

    def test_worker_completes_within_reasonable_time(self) -> None:
        t0 = time.monotonic()
        result = _invoke_worker(_make_request(timeout_ms=5000))
        elapsed = time.monotonic() - t0
        self.assertEqual(result.returncode, 0)
        self.assertLess(elapsed, 5.0, "echo worker should complete well within timeout")

    def test_subprocess_timeout_kills_worker(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            _invoke_worker(
                _make_request(timeout_ms=60000),
                timeout=0.001,
            )

    # ------------------------------------------------------------------
    # Backend selection via environment
    # ------------------------------------------------------------------

    def test_explicit_echo_backend_env(self) -> None:
        result = _invoke_worker(
            _make_request(),
            env_overrides={"AIOS_WORKER_BACKEND": "echo"},
        )
        resp = json.loads(result.stdout)
        self.assertEqual(resp["route_state"], "local-cpu-echo")
        self.assertIn("backend=echo", resp.get("notes", []))

    def test_llama_cpp_without_model_path_returns_error(self) -> None:
        result = _invoke_worker(
            _make_request(),
            env_overrides={"AIOS_WORKER_BACKEND": "llama-cpp"},
        )
        resp = json.loads(result.stdout)
        self.assertTrue(resp.get("worker_error", False) or resp.get("rejected", False))

    def test_transformers_without_model_path_returns_error(self) -> None:
        result = _invoke_worker(
            _make_request(),
            env_overrides={"AIOS_WORKER_BACKEND": "transformers"},
        )
        resp = json.loads(result.stdout)
        self.assertTrue(resp.get("worker_error", False) or resp.get("rejected", False))

    # ------------------------------------------------------------------
    # Estimated latency is present
    # ------------------------------------------------------------------

    def test_response_includes_estimated_latency(self) -> None:
        result = _invoke_worker(_make_request())
        resp = json.loads(result.stdout)
        self.assertIn("estimated_latency_ms", resp)
        self.assertIsInstance(resp["estimated_latency_ms"], int)
        self.assertGreaterEqual(resp["estimated_latency_ms"], 0)

    # ------------------------------------------------------------------
    # Multiple sequential requests work (worker is one-shot per process)
    # ------------------------------------------------------------------

    def test_sequential_invocations_are_independent(self) -> None:
        r1 = _invoke_worker(_make_request(task_id="task-a", prompt="first"))
        r2 = _invoke_worker(_make_request(task_id="task-b", prompt="second is longer"))
        self.assertEqual(r1.returncode, 0)
        self.assertEqual(r2.returncode, 0)
        resp1 = json.loads(r1.stdout)
        resp2 = json.loads(r2.stdout)
        self.assertNotEqual(resp1["content"], resp2["content"])


if __name__ == "__main__":
    unittest.main()
