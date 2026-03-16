#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ENGINE_ROOT = Path("/var/lib/aios/runtime/vendor-engines")
WORKER_CONTRACT = "runtime-worker-v1"
RUNTIME_SERVICE_ID = "aios-runtimed.jetson-vendor-helper"


@dataclass(frozen=True)
class VendorRuntimeSpec:
    backend_id: str
    provider_kind: str
    provider_id: str
    runtime_binary: str
    engine_path: Path
    evidence_dir: Path
    extra_args: list[str]
    dla_core: int | None = None


@dataclass(frozen=True)
class VendorExecutionResult:
    content: str
    reason: str
    evidence_path: Path
    notes: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jetson vendor accelerator worker")
    parser.add_argument("mode", choices=["stdio", "unix"])
    parser.add_argument("--backend", required=True, choices=["local-gpu", "local-npu"])
    parser.add_argument("--socket", type=Path, help="Unix socket path when mode=unix")
    return parser.parse_args()


def fail_config(message: str, code: int = 69) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def worker_contract() -> str:
    return os.environ.get("AIOS_RUNTIME_WORKER_CONTRACT", WORKER_CONTRACT)


def engine_root() -> Path:
    return Path(os.environ.get("AIOS_JETSON_VENDOR_ENGINE_ROOT", str(DEFAULT_ENGINE_ROOT)))


def evidence_dir() -> Path:
    configured = os.environ.get("AIOS_JETSON_VENDOR_EVIDENCE_DIR")
    if configured:
        return Path(configured)
    state_dir = os.environ.get("AIOS_RUNTIMED_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "jetson-vendor-evidence"
    return Path("/var/lib/aios/runtimed/jetson-vendor-evidence")


def default_engine_path(backend_id: str) -> Path:
    suffix = "local-gpu.plan" if backend_id == "local-gpu" else "local-npu.plan"
    return engine_root() / suffix


def backend_env_prefix(backend_id: str) -> str:
    return "AIOS_JETSON_VENDOR_GPU" if backend_id == "local-gpu" else "AIOS_JETSON_VENDOR_NPU"


def default_provider_kind(backend_id: str) -> str:
    return "trtexec" if backend_id == "local-gpu" else "dla-trtexec"


def default_provider_id(backend_id: str) -> str:
    return "nvidia.jetson.tensorrt" if backend_id == "local-gpu" else "nvidia.jetson.dla-trtexec"


def build_vendor_spec(backend_id: str) -> VendorRuntimeSpec:
    prefix = backend_env_prefix(backend_id)
    provider_kind = os.environ.get(
        f"{prefix}_PROVIDER", default_provider_kind(backend_id)
    ).strip() or default_provider_kind(backend_id)
    expected_kind = default_provider_kind(backend_id)
    if provider_kind != expected_kind:
        fail_config(
            f"unsupported provider kind for {backend_id}: {provider_kind} (expected {expected_kind})",
            code=64,
        )

    runtime_binary = os.environ.get("AIOS_JETSON_TRTEXEC_BIN", "trtexec").strip() or "trtexec"
    resolved_binary = shutil.which(runtime_binary)
    if resolved_binary is None and not Path(runtime_binary).exists():
        fail_config(f"missing vendor runtime binary for {backend_id}: {runtime_binary}")

    engine_path = Path(os.environ.get(f"{prefix}_ENGINE_PATH", str(default_engine_path(backend_id))))
    if not engine_path.exists():
        fail_config(f"missing vendor engine for {backend_id}: {engine_path}")

    extra_args = shlex.split(os.environ.get(f"{prefix}_EXTRA_ARGS", ""))
    provider_id = os.environ.get(f"{prefix}_PROVIDER_ID", default_provider_id(backend_id)).strip() or default_provider_id(backend_id)

    dla_core: int | None = None
    if backend_id == "local-npu":
        raw_core = os.environ.get("AIOS_JETSON_VENDOR_NPU_DLA_CORE", "0").strip() or "0"
        try:
            dla_core = int(raw_core)
        except ValueError:
            fail_config(f"invalid AIOS_JETSON_VENDOR_NPU_DLA_CORE: {raw_core}", code=64)

    target_evidence_dir = evidence_dir()
    target_evidence_dir.mkdir(parents=True, exist_ok=True)

    return VendorRuntimeSpec(
        backend_id=backend_id,
        provider_kind=provider_kind,
        provider_id=provider_id,
        runtime_binary=str(Path(resolved_binary) if resolved_binary is not None else Path(runtime_binary)),
        engine_path=engine_path,
        evidence_dir=target_evidence_dir,
        extra_args=extra_args,
        dla_core=dla_core,
    )


def request_work_dir(spec: VendorRuntimeSpec, request: dict[str, Any]) -> Path:
    task_id = str(request.get("task_id") or "task")
    safe_task_id = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-" for char in task_id
    )
    work_dir = spec.evidence_dir / spec.backend_id / safe_task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def excerpt(value: str, limit: int = 240) -> str:
    compact = " ".join(value.split())
    return compact[:limit]


def extract_latency_ms(payload: Any) -> float | None:
    if isinstance(payload, dict):
        for key in ("latencyMs", "computeMs", "enqueueMs", "gpuComputeMs"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for nested in payload.values():
            latency = extract_latency_ms(nested)
            if latency is not None:
                return latency
    elif isinstance(payload, list):
        for item in payload:
            latency = extract_latency_ms(item)
            if latency is not None:
                return latency
    return None


def build_trtexec_command(
    spec: VendorRuntimeSpec, request: dict[str, Any], work_dir: Path
) -> tuple[list[str], Path, Path]:
    times_path = work_dir / "trtexec-times.json"
    profile_path = work_dir / "trtexec-profile.json"
    command = [
        spec.runtime_binary,
        f"--loadEngine={spec.engine_path}",
        "--warmUp=0",
        "--duration=0",
        "--iterations=1",
        f"--exportTimes={times_path}",
        f"--exportProfile={profile_path}",
    ]
    if spec.dla_core is not None:
        command.extend([f"--useDLACore={spec.dla_core}", "--allowGPUFallback=0"])
    command.extend(spec.extra_args)
    request_json = work_dir / "request.json"
    write_json(
        request_json,
        {
            "worker_contract": request.get("worker_contract"),
            "backend_id": request.get("backend_id"),
            "session_id": request.get("session_id"),
            "task_id": request.get("task_id"),
            "model": request.get("model"),
            "prompt": request.get("prompt"),
            "estimated_latency_ms": request.get("estimated_latency_ms"),
            "timeout_ms": request.get("timeout_ms"),
        },
    )
    return command, times_path, profile_path


def vendor_env(spec: VendorRuntimeSpec, request: dict[str, Any], work_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AIOS_VENDOR_WORKER_BACKEND_ID": spec.backend_id,
            "AIOS_VENDOR_WORKER_PROVIDER_ID": spec.provider_id,
            "AIOS_VENDOR_WORKER_PROVIDER_KIND": spec.provider_kind,
            "AIOS_VENDOR_WORKER_ENGINE_PATH": str(spec.engine_path),
            "AIOS_VENDOR_WORKER_EVIDENCE_DIR": str(spec.evidence_dir),
            "AIOS_VENDOR_WORKER_REQUEST_DIR": str(work_dir),
            "AIOS_VENDOR_WORKER_REQUEST_JSON": str(work_dir / "request.json"),
            "AIOS_RUNTIME_REQUEST_SESSION_ID": str(request.get("session_id") or ""),
            "AIOS_RUNTIME_REQUEST_TASK_ID": str(request.get("task_id") or ""),
            "AIOS_RUNTIME_REQUEST_MODEL": str(request.get("model") or ""),
            "AIOS_RUNTIME_REQUEST_PROMPT": str(request.get("prompt") or ""),
        }
    )
    if spec.dla_core is not None:
        env["AIOS_VENDOR_WORKER_DLA_CORE"] = str(spec.dla_core)
    return env


def execute_vendor_runtime(spec: VendorRuntimeSpec, request: dict[str, Any]) -> VendorExecutionResult:
    work_dir = request_work_dir(spec, request)
    command, times_path, profile_path = build_trtexec_command(spec, request, work_dir)
    timeout_ms = max(int(request.get("timeout_ms") or 1), 1)
    started_at = time.time()
    completed = subprocess.run(
        command,
        cwd=work_dir,
        env=vendor_env(spec, request, work_dir),
        capture_output=True,
        text=True,
        timeout=max(timeout_ms / 1000.0, 1.0),
        check=False,
    )
    finished_at = time.time()
    times_payload = load_json(times_path)
    profile_payload = load_json(profile_path)
    latency_ms = extract_latency_ms(times_payload)
    stdout_excerpt = excerpt(completed.stdout)
    stderr_excerpt = excerpt(completed.stderr)

    evidence_path = work_dir / "vendor-execution.json"
    evidence = {
        "backend_id": spec.backend_id,
        "provider_id": spec.provider_id,
        "provider_kind": spec.provider_kind,
        "provider_status": "available",
        "runtime_service_id": RUNTIME_SERVICE_ID,
        "worker_contract": worker_contract(),
        "contract_kind": "vendor-runtime-evidence-v1",
        "runtime_binary": spec.runtime_binary,
        "engine_path": str(spec.engine_path),
        "task_id": request.get("task_id"),
        "session_id": request.get("session_id"),
        "model": request.get("model"),
        "prompt_excerpt": excerpt(str(request.get("prompt") or ""), 120),
        "command": command,
        "returncode": completed.returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": int((finished_at - started_at) * 1000),
        "stdout_excerpt": stdout_excerpt,
        "stderr_excerpt": stderr_excerpt,
        "times_path": str(times_path),
        "profile_path": str(profile_path),
        "times_payload": times_payload,
        "profile_payload": profile_payload,
        "latency_ms": latency_ms,
    }
    if spec.dla_core is not None:
        evidence["dla_core"] = spec.dla_core
    write_json(evidence_path, evidence)

    if completed.returncode != 0:
        raise RuntimeError(
            f"vendor runtime failed for {spec.backend_id}: returncode={completed.returncode}, stderr={stderr_excerpt or '<empty>'}"
        )

    latency_note = f"vendor_latency_ms={latency_ms:.3f}" if latency_ms is not None else None
    notes = [
        f"vendor_provider={spec.provider_id}",
        f"vendor_provider_kind={spec.provider_kind}",
        f"vendor_runtime_binary={spec.runtime_binary}",
        f"vendor_engine_path={spec.engine_path}",
        f"vendor_evidence_path={evidence_path}",
    ]
    if latency_note is not None:
        notes.append(latency_note)
    if spec.dla_core is not None:
        notes.append(f"vendor_dla_core={spec.dla_core}")
    if stdout_excerpt:
        notes.append(f"vendor_stdout_excerpt={stdout_excerpt}")
    if stderr_excerpt:
        notes.append(f"vendor_stderr_excerpt={stderr_excerpt}")

    content = f"jetson vendor {spec.provider_id} completed {request.get('task_id', 'task')}"
    if latency_ms is not None:
        content += f" in {latency_ms:.3f}ms"
    reason = f"jetson vendor runtime {spec.provider_kind} executed request"
    return VendorExecutionResult(
        content=content,
        reason=reason,
        evidence_path=evidence_path,
        notes=notes,
    )


def build_response(spec: VendorRuntimeSpec, request: dict[str, Any]) -> dict[str, Any]:
    execution = execute_vendor_runtime(spec, request)
    return {
        "worker_contract": worker_contract(),
        "backend_id": spec.backend_id,
        "route_state": f"{spec.backend_id}-worker-v1",
        "content": execution.content,
        "rejected": False,
        "degraded": False,
        "reason": execution.reason,
        "estimated_latency_ms": request.get("estimated_latency_ms"),
        "provider_id": spec.provider_id,
        "runtime_service_id": RUNTIME_SERVICE_ID,
        "provider_status": "available",
        "notes": execution.notes,
    }


def handle_payload(spec: VendorRuntimeSpec, payload: bytes) -> bytes | None:
    request = json.loads(payload.decode("utf-8") or "{}")
    request.setdefault("worker_contract", worker_contract())
    try:
        response = build_response(spec, request)
    except Exception as exc:  # noqa: BLE001
        error_path = request_work_dir(spec, request) / "vendor-error.json"
        write_json(
            error_path,
            {
                "backend_id": spec.backend_id,
                "provider_id": spec.provider_id,
                "runtime_service_id": RUNTIME_SERVICE_ID,
                "task_id": request.get("task_id"),
                "session_id": request.get("session_id"),
                "error": str(exc),
            },
        )
        return None
    return json.dumps(response, ensure_ascii=False).encode("utf-8")


def run_stdio(spec: VendorRuntimeSpec) -> int:
    payload = os.read(0, 1024 * 1024)
    response = handle_payload(spec, payload)
    if response is None:
        return 70
    os.write(1, response)
    return 0


def run_unix(spec: VendorRuntimeSpec, socket_path: Path) -> int:
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(16)
    try:
        while True:
            connection, _ = server.accept()
            with connection:
                payload = b""
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    payload += chunk
                response = handle_payload(spec, payload)
                if response is not None:
                    connection.sendall(response)
    finally:
        server.close()
        if socket_path.exists():
            socket_path.unlink()


def main() -> int:
    args = parse_args()
    spec = build_vendor_spec(args.backend)
    if args.mode == "stdio":
        return run_stdio(spec)
    if args.socket is None:
        raise SystemExit("--socket is required when mode=unix")
    return run_unix(spec, args.socket)


if __name__ == "__main__":
    raise SystemExit(main())
