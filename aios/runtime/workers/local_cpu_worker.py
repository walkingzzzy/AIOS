#!/usr/bin/env python3
"""
AIOS local-cpu inference worker implementing the runtime-worker-v1 contract.

Protocol:
  - Reads a single JSON request object from stdin.
  - Writes a single JSON response object to stdout.
  - All diagnostic output goes to stderr.

Environment variables:
  AIOS_WORKER_MODEL_PATH  - Path to a local model file (GGUF, safetensors, etc.)
  AIOS_WORKER_BACKEND     - Backend to use: llama-cpp | transformers | echo  (auto-detected if unset)
  AIOS_WORKER_MAX_TOKENS  - Maximum tokens to generate (default: 256)
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import traceback
from typing import Any

WORKER_CONTRACT = "runtime-worker-v1"
BACKEND_ID = "local-cpu"
ROUTE_STATE_OK = "local-cpu-worker-v1"
ROUTE_STATE_ECHO = "local-cpu-echo"
ROUTE_STATE_ERROR = "local-cpu-worker-error"

REQUEST_REQUIRED_FIELDS = {"backend_id", "session_id", "task_id", "prompt", "timeout_ms"}
RESPONSE_REQUIRED_FIELDS = {"worker_contract", "backend_id", "route_state", "content", "rejected", "degraded"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _make_response(
    content: str,
    *,
    route_state: str = ROUTE_STATE_OK,
    rejected: bool = False,
    degraded: bool = False,
    reason: str | None = None,
    provider_id: str | None = None,
    provider_status: str | None = None,
    estimated_latency_ms: int | None = None,
    notes: list[str] | None = None,
    worker_error: bool = False,
    worker_error_class: str | None = None,
) -> dict[str, Any]:
    resp: dict[str, Any] = {
        "worker_contract": WORKER_CONTRACT,
        "backend_id": BACKEND_ID,
        "route_state": route_state,
        "content": content,
        "rejected": rejected,
        "degraded": degraded,
    }
    if reason is not None:
        resp["reason"] = reason
    if provider_id is not None:
        resp["provider_id"] = provider_id
    resp["runtime_service_id"] = "aios-runtimed.local-cpu-worker"
    if provider_status is not None:
        resp["provider_status"] = provider_status
    resp["queue_saturated"] = False
    if estimated_latency_ms is not None:
        resp["estimated_latency_ms"] = estimated_latency_ms
    resp["notes"] = notes or []
    if worker_error:
        resp["worker_error"] = True
        if worker_error_class:
            resp["worker_error_class"] = worker_error_class
    return resp


def _make_error(
    reason: str,
    *,
    error_class: str = "command-failed",
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return _make_response(
        "",
        route_state=ROUTE_STATE_ERROR,
        rejected=True,
        degraded=True,
        reason=reason,
        provider_status="error",
        worker_error=True,
        worker_error_class=error_class,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _detect_backend() -> str:
    explicit = os.environ.get("AIOS_WORKER_BACKEND", "").strip().lower()
    if explicit in ("llama-cpp", "transformers", "echo"):
        return explicit

    try:
        import llama_cpp  # noqa: F401
        return "llama-cpp"
    except ImportError:
        pass
    try:
        import transformers  # noqa: F401
        return "transformers"
    except ImportError:
        pass
    return "echo"


def _infer_echo(prompt: str, _model_path: str | None, _max_tokens: int) -> dict[str, Any]:
    return _make_response(
        f"[echo] received prompt ({len(prompt)} chars)",
        route_state=ROUTE_STATE_ECHO,
        degraded=True,
        reason="no ML backend available; echo mode",
        provider_id="echo",
        provider_status="degraded",
        notes=["backend=echo", f"prompt_length={len(prompt)}"],
    )


def _infer_llama_cpp(prompt: str, model_path: str | None, max_tokens: int) -> dict[str, Any]:
    if not model_path:
        return _make_error(
            "AIOS_WORKER_MODEL_PATH is required for llama-cpp backend",
            notes=["backend=llama-cpp", "missing_model_path=true"],
        )
    if not os.path.isfile(model_path):
        return _make_error(
            f"model file not found: {model_path}",
            notes=["backend=llama-cpp", f"model_path={model_path}"],
        )
    try:
        from llama_cpp import Llama
    except ImportError:
        return _make_error(
            "llama-cpp-python package is not installed",
            error_class="unavailable",
            notes=["backend=llama-cpp", "import_error=true"],
        )

    t0 = _now_ms()
    try:
        llm = Llama(model_path=model_path, n_ctx=2048, verbose=False)
        output = llm(prompt, max_tokens=max_tokens, echo=False)
        text = output["choices"][0]["text"] if output.get("choices") else ""
        elapsed = _now_ms() - t0
        return _make_response(
            text.strip(),
            reason="llama-cpp inference completed",
            provider_id="llama-cpp",
            provider_status="available",
            estimated_latency_ms=elapsed,
            notes=["backend=llama-cpp", f"model_path={model_path}", f"max_tokens={max_tokens}"],
        )
    except Exception as exc:
        elapsed = _now_ms() - t0
        return _make_error(
            f"llama-cpp inference failed: {exc}",
            notes=["backend=llama-cpp", f"model_path={model_path}", f"elapsed_ms={elapsed}"],
        )


def _infer_transformers(prompt: str, model_path: str | None, max_tokens: int) -> dict[str, Any]:
    if not model_path:
        return _make_error(
            "AIOS_WORKER_MODEL_PATH is required for transformers backend",
            notes=["backend=transformers", "missing_model_path=true"],
        )
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        return _make_error(
            "transformers package is not installed",
            error_class="unavailable",
            notes=["backend=transformers", "import_error=true"],
        )

    t0 = _now_ms()
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForCausalLM.from_pretrained(model_path)
        inputs = tokenizer(prompt, return_tensors="pt")
        outputs = model.generate(**inputs, max_new_tokens=max_tokens)
        text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        elapsed = _now_ms() - t0
        return _make_response(
            text.strip(),
            reason="transformers inference completed",
            provider_id="transformers",
            provider_status="available",
            estimated_latency_ms=elapsed,
            notes=["backend=transformers", f"model_path={model_path}", f"max_tokens={max_tokens}"],
        )
    except Exception as exc:
        elapsed = _now_ms() - t0
        return _make_error(
            f"transformers inference failed: {exc}",
            notes=["backend=transformers", f"model_path={model_path}", f"elapsed_ms={elapsed}"],
        )


BACKENDS = {
    "echo": _infer_echo,
    "llama-cpp": _infer_llama_cpp,
    "transformers": _infer_transformers,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _read_request() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("empty request payload on stdin")
    return json.loads(raw)


def _validate_request(req: dict[str, Any]) -> list[str]:
    missing = REQUEST_REQUIRED_FIELDS - set(req.keys())
    return sorted(missing)


def _install_timeout(timeout_ms: int) -> None:
    if sys.platform == "win32":
        return
    deadline_sec = max(timeout_ms / 1000.0, 0.1)

    def _on_alarm(_signum: int, _frame: Any) -> None:
        response = _make_error(
            f"worker exceeded timeout budget of {timeout_ms}ms",
            error_class="timeout",
            notes=[f"timeout_ms={timeout_ms}"],
        )
        sys.stdout.write(json.dumps(response))
        sys.stdout.flush()
        sys.exit(1)

    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(int(deadline_sec) or 1)


def main() -> None:
    try:
        req = _read_request()
    except Exception as exc:
        response = _make_error(f"failed to read/parse request: {exc}")
        sys.stdout.write(json.dumps(response))
        sys.stdout.flush()
        sys.exit(1)

    missing = _validate_request(req)
    if missing:
        response = _make_error(
            f"request missing required fields: {', '.join(missing)}",
            notes=[f"missing_field={f}" for f in missing],
        )
        sys.stdout.write(json.dumps(response))
        sys.stdout.flush()
        sys.exit(1)

    timeout_ms = req.get("timeout_ms", 30000)
    _install_timeout(timeout_ms)

    backend_name = _detect_backend()
    backend_fn = BACKENDS.get(backend_name)
    if backend_fn is None:
        response = _make_error(
            f"unknown backend: {backend_name}",
            notes=[f"requested_backend={backend_name}"],
        )
        sys.stdout.write(json.dumps(response))
        sys.stdout.flush()
        sys.exit(1)

    model_path = os.environ.get("AIOS_WORKER_MODEL_PATH")
    max_tokens = _env_int("AIOS_WORKER_MAX_TOKENS", 256)

    t0 = _now_ms()
    try:
        response = backend_fn(req["prompt"], model_path, max_tokens)
    except Exception as exc:
        elapsed = _now_ms() - t0
        print(f"worker internal error: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        response = _make_error(
            f"worker internal error: {exc}",
            notes=[f"backend={backend_name}", f"elapsed_ms={elapsed}"],
        )

    if response.get("estimated_latency_ms") is None:
        response["estimated_latency_ms"] = _now_ms() - t0

    sys.stdout.write(json.dumps(response))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
