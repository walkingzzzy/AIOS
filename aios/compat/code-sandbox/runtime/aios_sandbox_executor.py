#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil

try:
    import resource
except ModuleNotFoundError:  # Windows does not expose the POSIX resource module.
    resource = None

import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios.compat.runtime_support import (
    CompatPolicyContext,
    CompatPolicyError,
    add_policy_args,
    append_jsonl,
    resolve_policy_context,
    standalone_policy_context,
)


PROVIDER_ID = "compat.code.sandbox.local"
EXECUTION_LOCATION = "sandbox"
CAPABILITY_ID = "compat.code.execute"
WORKER_CONTRACT = "compat-sandbox-executor-v1"
REQUIRED_PERMISSIONS = [
    "sandbox.local",
]
COMPAT_PERMISSION_SCHEMA_REF = "aios/compat-permission-manifest.schema.json"
RESULT_PROTOCOL_SCHEMA_REF = "aios/compat-sandbox-result.schema.json"
AUDIT_SCHEMA_VERSION = "2026-03-13"
DESCRIPTOR_FILENAME = "code.sandbox.local.json"
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MEMORY_MB = 128
DEFAULT_CPU_SECONDS = 2
DEFAULT_AUDIT_LOG_ENV = "AIOS_COMPAT_CODE_SANDBOX_AUDIT_LOG"
DEFAULT_SANDBOX_WORK_ROOT_ENV = "AIOS_CODE_SANDBOX_WORK_ROOT"
DEFAULT_USER_ID = "compat-runtime"
DEFAULT_SESSION_ID = "compat-code-sandbox"
DEFAULT_TASK_ID = "compat.code.execute"
DEFAULT_TAINT_BEHAVIOR = "dynamic-code-tainted"
BWRAP_WORKSPACE = "/workspace"

BOOTSTRAP = """
from __future__ import annotations

import builtins
import os
import runpy
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(os.environ[\"AIOS_CODE_SANDBOX_ROOT\"]).resolve()
TARGET = os.environ[\"AIOS_CODE_SANDBOX_TARGET\"]
ALLOW_NETWORK = os.environ.get(\"AIOS_CODE_SANDBOX_ALLOW_NETWORK\") == \"1\"
ALLOW_SUBPROCESS = os.environ.get(\"AIOS_CODE_SANDBOX_ALLOW_SUBPROCESS\") == \"1\"


def _resolve_candidate(path):
    if isinstance(path, int):
        return None
    try:
        return Path(path).expanduser().resolve(strict=False)
    except (TypeError, ValueError):
        return None


def _inside_root(path: Path | None) -> bool:
    if path is None:
        return True
    root_text = str(ROOT)
    path_text = str(path)
    return path_text == root_text or path_text.startswith(root_text + os.sep)


def _guard_write(path) -> None:
    candidate = _resolve_candidate(path)
    if candidate is not None and not _inside_root(candidate):
        raise PermissionError(f\"AIOS sandbox denies writes outside {ROOT}\")


_original_open = builtins.open


def _sandbox_open(file, mode=\"r\", *args, **kwargs):
    if any(flag in mode for flag in (\"w\", \"a\", \"x\", \"+\")):
        _guard_write(file)
    return _original_open(file, mode, *args, **kwargs)


builtins.open = _sandbox_open
_original_os_open = os.open


def _sandbox_os_open(path, flags, mode=0o777, *, dir_fd=None):
    write_flags = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC)
    if write_flags:
        _guard_write(path)
    return _original_os_open(path, flags, mode, dir_fd=dir_fd)


os.open = _sandbox_os_open


def _wrap_single_path(fn):
    def wrapped(path, *args, **kwargs):
        _guard_write(path)
        return fn(path, *args, **kwargs)

    return wrapped


def _wrap_double_path(fn):
    def wrapped(src, dst, *args, **kwargs):
        _guard_write(src)
        _guard_write(dst)
        return fn(src, dst, *args, **kwargs)

    return wrapped


os.remove = _wrap_single_path(os.remove)
os.unlink = _wrap_single_path(os.unlink)
os.rmdir = _wrap_single_path(os.rmdir)
os.mkdir = _wrap_single_path(os.mkdir)
os.makedirs = _wrap_single_path(os.makedirs)
os.rename = _wrap_double_path(os.rename)
os.replace = _wrap_double_path(os.replace)


def _blocked_network(*args, **kwargs):
    raise PermissionError(\"AIOS sandbox network disabled\")


if not ALLOW_NETWORK:
    class _BlockedSocket:
        def __init__(self, *args, **kwargs):
            _blocked_network()

    socket.socket = _BlockedSocket
    socket.create_connection = _blocked_network
    if hasattr(socket, \"socketpair\"):
        socket.socketpair = _blocked_network


def _blocked_subprocess(*args, **kwargs):
    raise PermissionError(\"AIOS sandbox subprocess disabled\")


if not ALLOW_SUBPROCESS:
    subprocess.Popen = _blocked_subprocess
    subprocess.run = _blocked_subprocess
    subprocess.call = _blocked_subprocess
    subprocess.check_call = _blocked_subprocess
    subprocess.check_output = _blocked_subprocess
    os.system = _blocked_subprocess
    if hasattr(os, \"popen\"):
        os.popen = _blocked_subprocess


os.chdir(ROOT)
sys.argv = [TARGET]
runpy.run_path(TARGET, run_name=\"__main__\")
"""


@dataclass(frozen=True)
class SandboxLayout:
    root: Path
    code_path: Path
    input_path: Path
    output_path: Path
    bootstrap_path: Path
    temp_path: Path


@dataclass(frozen=True)
class SandboxCommandError(Exception):
    category: str
    error_code: str
    message: str
    retryable: bool
    exit_code: int = 1

    def to_payload(self) -> dict[str, object]:
        return {
            "category": self.category,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }


def add_execute_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--language", default="python", choices=["python"])
    parser.add_argument("--code-file", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--memory-mb", type=int, default=DEFAULT_MEMORY_MB)
    parser.add_argument("--cpu-seconds", type=int, default=DEFAULT_CPU_SECONDS)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-env", action="append", default=[])
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-subprocess", action="store_true")
    parser.add_argument("--retain-sandbox", action="store_true")
    parser.add_argument("--audit-log", type=Path)
    parser.add_argument("--json", action="store_true")
    add_policy_args(parser)


def build_modern_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIOS code sandbox compat provider runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("manifest")
    health_parser = subparsers.add_parser("health")
    add_policy_args(health_parser)
    subparsers.add_parser("permissions")
    execute_parser = subparsers.add_parser("execute")
    add_execute_args(execute_parser)
    return parser


def build_legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIOS code sandbox compat provider runtime")
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--permissions", action="store_true")
    add_execute_args(parser)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"manifest", "health", "permissions", "execute"}:
        return build_modern_parser().parse_args(argv)

    args = build_legacy_parser().parse_args(argv)
    if args.describe:
        args.command = "manifest"
    elif args.health:
        args.command = "health"
    elif args.permissions:
        args.command = "permissions"
    else:
        args.command = "execute"
    return args


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def limit_resources(memory_mb: int, cpu_seconds: int) -> None:
    if resource is None:
        return

    address_space = max(64, memory_mb) * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    except (OSError, ValueError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    except (OSError, ValueError):
        pass


def resolve_audit_log(args: argparse.Namespace) -> Path | None:
    if getattr(args, "audit_log", None) is not None:
        return args.audit_log
    raw = os.environ.get(DEFAULT_AUDIT_LOG_ENV)
    return Path(raw) if raw else None


def resolve_descriptor_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[1] / "providers" / DESCRIPTOR_FILENAME,
        current.parents[3] / "share" / "aios" / "providers" / DESCRIPTOR_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_compat_permission_manifest() -> dict[str, object]:
    descriptor_path = resolve_descriptor_path()
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    permission_manifest = descriptor.get("compat_permission_manifest")
    if not isinstance(permission_manifest, dict):
        raise RuntimeError(f"descriptor missing compat_permission_manifest: {descriptor_path}")

    capability_ids = [
        item.get("capability_id")
        for item in permission_manifest.get("capabilities", [])
        if isinstance(item, dict)
    ]
    if permission_manifest.get("schema_version") != "1.0.0":
        raise RuntimeError("unsupported compat permission manifest schema_version")
    if permission_manifest.get("provider_id") != PROVIDER_ID:
        raise RuntimeError("compat permission manifest provider_id mismatch")
    if permission_manifest.get("execution_location") != EXECUTION_LOCATION:
        raise RuntimeError("compat permission manifest execution_location mismatch")
    if permission_manifest.get("required_permissions") != REQUIRED_PERMISSIONS:
        raise RuntimeError("compat permission manifest required_permissions mismatch")
    if capability_ids != [CAPABILITY_ID]:
        raise RuntimeError("compat permission manifest capability list mismatch")

    return permission_manifest


def sandbox_capability(permission_manifest: dict[str, object]) -> dict[str, object]:
    for candidate in permission_manifest.get("capabilities", []):
        if isinstance(candidate, dict) and candidate.get("capability_id") == CAPABILITY_ID:
            return candidate
    raise SandboxCommandError(
        category="internal",
        error_code="sandbox_capability_missing",
        message="compat permission manifest does not define sandbox capability",
        retryable=False,
    )


def audit_tags(permission_manifest: dict[str, object], capability: dict[str, object]) -> list[str]:
    tags = capability.get("audit_tags")
    if isinstance(tags, list) and all(isinstance(item, str) for item in tags):
        return list(tags)
    tags = permission_manifest.get("audit_tags")
    if isinstance(tags, list) and all(isinstance(item, str) for item in tags):
        return list(tags)
    return ["sandbox", "compat"]


def taint_behavior(permission_manifest: dict[str, object]) -> str:
    value = permission_manifest.get("taint_behavior")
    if isinstance(value, str) and value:
        return value
    return DEFAULT_TAINT_BEHAVIOR


def optional_arg_path(value: Path | None) -> str | None:
    return str(value) if value is not None else None


def optional_error(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def build_manifest() -> dict[str, object]:
    sandbox_class, _ = resolve_sandbox_engine()
    return {
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "execution_location": EXECUTION_LOCATION,
        "status": "available",
        "declared_capabilities": [
            CAPABILITY_ID,
        ],
        "required_permissions": REQUIRED_PERMISSIONS,
        "implemented_methods": [
            "manifest",
            "health",
            "permission-manifest",
            "execute-python-script",
            "export-output-artifacts",
            "audit-jsonl",
            WORKER_CONTRACT,
        ],
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": load_compat_permission_manifest(),
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "notes": [
            "Bounded local Python sandbox runtime is available",
            f"preferred_engine={sandbox_class}",
            "Network and subprocess access are denied by default",
            "Input files are copied under ./input and outputs are collected from ./output",
            "Structured compat-sandbox-executor-v1 payloads are enabled",
        ],
    }


def enforce_compat_permission_manifest(args: argparse.Namespace, permission_manifest: dict[str, object]) -> None:
    resource_budget = permission_manifest.get("resource_budget", {})
    if isinstance(resource_budget, dict):
        max_timeout_seconds = resource_budget.get("max_timeout_seconds")
        if isinstance(max_timeout_seconds, int | float) and args.timeout_seconds > float(max_timeout_seconds):
            raise SandboxCommandError(
                category="policy",
                error_code="sandbox_timeout_budget_exceeded",
                message=(
                    "requested timeout exceeds compat permission manifest budget: "
                    f"{args.timeout_seconds}s > {max_timeout_seconds}s"
                ),
                retryable=False,
                exit_code=77,
            )

        max_memory_mb = resource_budget.get("max_memory_mb")
        if isinstance(max_memory_mb, int | float) and args.memory_mb > int(max_memory_mb):
            raise SandboxCommandError(
                category="policy",
                error_code="sandbox_memory_budget_exceeded",
                message=(
                    "requested memory exceeds compat permission manifest budget: "
                    f"{args.memory_mb}MB > {int(max_memory_mb)}MB"
                ),
                retryable=False,
                exit_code=77,
            )

        max_cpu_seconds = resource_budget.get("max_cpu_seconds")
        if isinstance(max_cpu_seconds, int | float) and args.cpu_seconds > int(max_cpu_seconds):
            raise SandboxCommandError(
                category="policy",
                error_code="sandbox_cpu_budget_exceeded",
                message=(
                    "requested cpu exceeds compat permission manifest budget: "
                    f"{args.cpu_seconds}s > {int(max_cpu_seconds)}s"
                ),
                retryable=False,
                exit_code=77,
            )

    capability = sandbox_capability(permission_manifest)

    network_access = str(capability.get("network_access", ""))
    if args.allow_network and network_access not in {"optional-flag", "allowed"}:
        raise SandboxCommandError(
            category="policy",
            error_code="sandbox_network_access_denied",
            message="compat permission manifest denies requested network access",
            retryable=False,
            exit_code=77,
        )

    subprocess_access = str(capability.get("subprocess_access", ""))
    if args.allow_subprocess and subprocess_access not in {"optional-flag", "allowed"}:
        raise SandboxCommandError(
            category="policy",
            error_code="sandbox_subprocess_access_denied",
            message="compat permission manifest denies requested subprocess access",
            retryable=False,
            exit_code=77,
        )


def allocate_sandbox_root() -> Path:
    override = os.environ.get(DEFAULT_SANDBOX_WORK_ROOT_ENV)
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = REPO_ROOT / "out" / "validation" / "code-sandbox-runtime"
    else:
        return Path(tempfile.mkdtemp(prefix="aios-code-sandbox-"))

    base.mkdir(parents=True, exist_ok=True)
    root = base / f"aios-code-sandbox-{os.getpid()}-{time.time_ns()}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=False)
    return root


def prepare_sandbox(code_file: Path, input_dir: Path | None) -> SandboxLayout:
    root = allocate_sandbox_root()
    temp_path = root / "tmp"
    input_path = root / "input"
    output_path = root / "output"
    code_path = root / "main.py"
    bootstrap_path = root / "bootstrap.py"
    temp_path.mkdir(parents=True, exist_ok=True)
    input_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(code_file, code_path)
    if input_dir is not None:
        if not input_dir.exists() or not input_dir.is_dir():
            raise SandboxCommandError(
                category="invalid-request",
                error_code="sandbox_input_dir_missing",
                message=f"missing input dir: {input_dir}",
                retryable=False,
                exit_code=2,
            )
        shutil.copytree(input_dir, input_path, dirs_exist_ok=True)
    bootstrap_path.write_text(BOOTSTRAP)
    return SandboxLayout(
        root=root,
        code_path=code_path,
        input_path=input_path,
        output_path=output_path,
        bootstrap_path=bootstrap_path,
        temp_path=temp_path,
    )


def resolve_sandbox_engine() -> tuple[str, str | None]:
    bwrap = shutil.which("bwrap")
    if bwrap:
        return "os-level-bwrap", bwrap
    return "bounded-local-python", None


def build_environment(
    layout: SandboxLayout,
    args: argparse.Namespace,
    *,
    sandbox_root: str,
    temp_dir: str,
) -> dict[str, str]:
    env = {
        "HOME": sandbox_root,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", os.environ.get("LANG", "C.UTF-8")),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": temp_dir,
        "AIOS_CODE_SANDBOX_ROOT": sandbox_root,
        "AIOS_CODE_SANDBOX_TARGET": layout.code_path.name,
        "AIOS_CODE_SANDBOX_ALLOW_NETWORK": "1" if args.allow_network else "0",
        "AIOS_CODE_SANDBOX_ALLOW_SUBPROCESS": "1" if args.allow_subprocess else "0",
    }
    for name in args.allow_env:
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def build_command(
    layout: SandboxLayout,
    args: argparse.Namespace,
    *,
    sandbox_class: str,
    bwrap_path: str | None,
) -> tuple[list[str], dict[str, str]]:
    if sandbox_class == "os-level-bwrap" and bwrap_path is not None:
        env = build_environment(
            layout,
            args,
            sandbox_root=BWRAP_WORKSPACE,
            temp_dir="/tmp",
        )
        command = [
            bwrap_path,
            "--die-with-parent",
            "--new-session",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--unshare-cgroup-try",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            str(layout.root),
            BWRAP_WORKSPACE,
            "--chdir",
            BWRAP_WORKSPACE,
            "--tmpfs",
            "/tmp",
        ]
        if not args.allow_network:
            command.extend(["--unshare-net"])
        command.extend([sys.executable, "-I", f"{BWRAP_WORKSPACE}/{layout.bootstrap_path.name}"])
        return command, env

    env = build_environment(
        layout,
        args,
        sandbox_root=str(layout.root),
        temp_dir=str(layout.temp_path),
    )
    return [sys.executable, "-I", layout.bootstrap_path.name], env


def compat_policy_error_to_sandbox(error: CompatPolicyError) -> SandboxCommandError:
    if error.category == "invalid_request":
        return SandboxCommandError(
            category="invalid-request",
            error_code=error.error_code,
            message=error.message,
            retryable=error.retryable,
            exit_code=2,
        )
    if error.category in {"precondition_failed", "permission_denied"}:
        return SandboxCommandError(
            category="policy",
            error_code=error.error_code,
            message=error.message,
            retryable=error.retryable,
            exit_code=77,
        )
    if error.category == "unavailable":
        return SandboxCommandError(
            category="unavailable",
            error_code=error.error_code,
            message=error.message,
            retryable=error.retryable,
            exit_code=69,
        )
    return SandboxCommandError(
        category="internal",
        error_code=error.error_code,
        message=error.message,
        retryable=error.retryable,
        exit_code=1,
    )


def copy_output_artifacts(layout: SandboxLayout, output_dir: Path | None) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
    for file in sorted(layout.output_path.rglob("*")):
        if not file.is_file():
            continue
        relative_path = file.relative_to(layout.output_path)
        artifact: dict[str, object] = {
            "relative_path": relative_path.as_posix(),
            "size_bytes": file.stat().st_size,
        }
        if output_dir is not None:
            target = output_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
            artifact["output_path"] = str(target)
        artifacts.append(artifact)
    return artifacts


def build_health(audit_log: Path | None, policy_context: CompatPolicyContext) -> dict[str, object]:
    permission_manifest = load_compat_permission_manifest()
    sandbox_class, _ = resolve_sandbox_engine()
    return {
        "status": "available",
        "provider_id": PROVIDER_ID,
        "worker_contract": WORKER_CONTRACT,
        "execution_location": EXECUTION_LOCATION,
        "declared_capabilities": [CAPABILITY_ID],
        "required_permissions": REQUIRED_PERMISSIONS,
        "compat_permission_schema_ref": COMPAT_PERMISSION_SCHEMA_REF,
        "compat_permission_manifest": permission_manifest,
        "result_protocol_schema_ref": RESULT_PROTOCOL_SCHEMA_REF,
        "engine": sandbox_class,
        "supported_engines": ["os-level-bwrap", "bounded-local-python"],
        "network_access": "disabled-by-default",
        "subprocess_access": "disabled-by-default",
        "audit_log_configured": audit_log is not None,
        "audit_log_path": str(audit_log) if audit_log is not None else None,
        "shared_audit_log_configured": policy_context.shared_audit_log is not None,
        "shared_audit_log_path": (
            str(policy_context.shared_audit_log)
            if policy_context.shared_audit_log is not None
            else None
        ),
        "policyd_socket": (
            str(policy_context.policyd_socket)
            if policy_context.policyd_socket is not None
            else None
        ),
        "policy_mode": policy_context.mode,
        "notes": [
            "Execution happens in an isolated temporary workspace",
            "Input files are copied under ./input and outputs are collected from ./output",
            "Bubblewrap OS-level isolation is used automatically when available",
            "Python-level guards still deny network and subprocess access by default",
            "Structured compat-sandbox-executor-v1 payloads are enabled",
        ],
    }


def append_audit_log(
    audit_log: Path | None,
    payload: dict[str, object],
    args: argparse.Namespace,
    permission_manifest: dict[str, object],
    policy_context: CompatPolicyContext,
) -> str | None:
    if audit_log is None and policy_context.shared_audit_log is None:
        return None
    if audit_log is not None and audit_log.parent:
        audit_log.parent.mkdir(parents=True, exist_ok=True)
    audit_id = f"code-sandbox-{time.time_ns()}"
    capability = sandbox_capability(permission_manifest)
    error = optional_error(payload.get("error"))
    status = str(payload.get("status", "error"))
    if status == "error" and error is not None and error.get("category") in {
        "policy",
        "invalid-request",
    }:
        decision = "denied"
    else:
        decision = "allowed"
    timestamp = now_iso()
    token_context = policy_context.token_context or {}
    artifact_path = str(audit_log or policy_context.shared_audit_log)
    entry = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audit_id": audit_id,
        "timestamp": timestamp,
        "generated_at": timestamp,
        "user_id": token_context.get("user_id")
        or os.environ.get("AIOS_COMPAT_CODE_SANDBOX_AUDIT_USER_ID", DEFAULT_USER_ID),
        "session_id": token_context.get("session_id")
        or os.environ.get(
            "AIOS_COMPAT_CODE_SANDBOX_AUDIT_SESSION_ID", DEFAULT_SESSION_ID
        ),
        "task_id": token_context.get("task_id")
        or os.environ.get("AIOS_COMPAT_CODE_SANDBOX_AUDIT_TASK_ID", DEFAULT_TASK_ID),
        "provider_id": PROVIDER_ID,
        "capability_id": CAPABILITY_ID,
        "approval_id": token_context.get("approval_ref"),
        "decision": decision,
        "execution_location": EXECUTION_LOCATION,
        "route_state": (
            "compat-sandbox-centralized-policy"
            if policy_context.mode == "policyd-verified"
            else "bounded-local-sandbox"
        ),
        "taint_summary": token_context.get("taint_summary")
        or taint_behavior(permission_manifest),
        "artifact_path": artifact_path,
        "status": status,
        "operation": CAPABILITY_ID,
        "audit_tags": audit_tags(permission_manifest, capability),
        "result": {
            "provider_id": PROVIDER_ID,
            "language": args.language,
            "code_file": optional_arg_path(args.code_file),
            "exit_code": payload["exit_code"],
            "timed_out": payload["timed_out"],
            "duration_ms": payload["duration_ms"],
            "artifact_count": payload["artifact_count"],
            "network_access": payload["network_access"],
            "subprocess_access": payload["subprocess_access"],
            "error_category": error.get("category") if error is not None else None,
            "error_code": error.get("error_code") if error is not None else None,
            "policy_mode": policy_context.mode,
            "token_verified": policy_context.token_verified,
            "session_id": token_context.get("session_id"),
            "task_id": token_context.get("task_id"),
            "approval_ref": token_context.get("approval_ref"),
        },
        "execution_token": token_context or None,
        "token_verification": policy_context.verification,
        "notes": [
            f"worker_contract={WORKER_CONTRACT}",
            f"result_protocol_schema_ref={RESULT_PROTOCOL_SCHEMA_REF}",
            f"policy_mode={policy_context.mode}",
        ],
    }
    append_jsonl(audit_log, entry)
    append_jsonl(policy_context.shared_audit_log, entry)
    return audit_id


def build_result_protocol(
    args: argparse.Namespace,
    payload: dict[str, object],
    permission_manifest: dict[str, object],
    started_at: str,
    finished_at: str,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    capability = sandbox_capability(permission_manifest)
    result: dict[str, object] = {
        "protocol_version": "1.0.0",
        "worker_contract": WORKER_CONTRACT,
        "provider_id": PROVIDER_ID,
        "status": payload["status"],
        "execution_location": EXECUTION_LOCATION,
        "sandbox_class": payload["sandbox_class"],
        "request": {
            "language": args.language,
            "code_file": optional_arg_path(args.code_file),
            "input_dir": optional_arg_path(args.input_dir),
            "output_dir": optional_arg_path(args.output_dir),
            "timeout_seconds": args.timeout_seconds,
            "memory_mb": args.memory_mb,
            "cpu_seconds": args.cpu_seconds,
            "allow_network": args.allow_network,
            "allow_subprocess": args.allow_subprocess,
            "allow_env": args.allow_env,
        },
        "policy": {
            "network_access": payload["network_access"],
            "subprocess_access": payload["subprocess_access"],
            "filesystem_access": capability.get("filesystem_access"),
            "approval_required": capability.get("approval_required"),
            "compat_permission_manifest": permission_manifest,
            **policy_context.describe(),
        },
        "resources": {
            "timed_out": payload["timed_out"],
            "exit_code": payload["exit_code"],
            "duration_ms": payload["duration_ms"],
        },
        "streams": {
            "stdout": payload["stdout"],
            "stderr": payload["stderr"],
        },
        "artifacts": payload["artifacts"],
        "audit": {
            "audit_id": payload["audit_id"],
            "audit_log": payload["audit_log"],
            "capability_id": CAPABILITY_ID,
            "audit_tags": audit_tags(permission_manifest, capability),
            "taint_behavior": taint_behavior(permission_manifest),
            "shared_audit_log": (
                str(policy_context.shared_audit_log)
                if policy_context.shared_audit_log is not None
                else None
            ),
            "execution_token": policy_context.token_context,
            "token_verification": policy_context.verification,
        },
        "timestamps": {
            "started_at": started_at,
            "finished_at": finished_at,
        },
        "error": optional_error(payload.get("error")),
    }
    if "sandbox_root" in payload:
        result["sandbox_root"] = payload["sandbox_root"]
    return result


def finalize_payload(
    args: argparse.Namespace,
    payload: dict[str, object],
    permission_manifest: dict[str, object],
    started_at: str,
    finished_at: str,
    audit_log: Path | None,
    policy_context: CompatPolicyContext,
) -> dict[str, object]:
    payload["worker_contract"] = WORKER_CONTRACT
    payload["audit_id"] = append_audit_log(
        audit_log,
        payload,
        args,
        permission_manifest,
        policy_context,
    )
    payload["audit_log"] = str(audit_log) if audit_log is not None else None
    payload["result_protocol_schema_ref"] = RESULT_PROTOCOL_SCHEMA_REF
    payload["result_protocol"] = build_result_protocol(
        args,
        payload,
        permission_manifest,
        started_at,
        finished_at,
        policy_context,
    )
    return payload


def execute(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    audit_log = resolve_audit_log(args)
    started_at = now_iso()
    started = time.perf_counter()
    permission_manifest = load_compat_permission_manifest()
    policy_context = CompatPolicyContext(
        mode="standalone-local",
        policyd_socket=None,
        execution_token=None,
        token_context=None,
        verification=None,
        shared_audit_log=None,
    )
    sandbox_class, bwrap_path = resolve_sandbox_engine()
    layout: SandboxLayout | None = None
    try:
        policy_context = standalone_policy_context(args)
        if args.code_file is None:
            raise SandboxCommandError(
                category="invalid-request",
                error_code="sandbox_code_file_missing",
                message="--code-file is required for execute",
                retryable=False,
                exit_code=2,
            )
        if not args.code_file.exists():
            raise SandboxCommandError(
                category="invalid-request",
                error_code="sandbox_code_file_not_found",
                message=f"missing code file: {args.code_file}",
                retryable=False,
                exit_code=2,
            )

        policy_context = resolve_policy_context(
            args,
            capability_id=CAPABILITY_ID,
            execution_location=EXECUTION_LOCATION,
            consume=True,
        )
        enforce_compat_permission_manifest(args, permission_manifest)
        layout = prepare_sandbox(args.code_file, args.input_dir)
        command, env = build_command(
            layout,
            args,
            sandbox_class=sandbox_class,
            bwrap_path=bwrap_path,
        )

        run_kwargs = {
            "cwd": layout.root,
            "text": True,
            "capture_output": True,
            "timeout": args.timeout_seconds,
            "env": env,
        }
        if os.name != "nt":
            run_kwargs["preexec_fn"] = lambda: limit_resources(args.memory_mb, args.cpu_seconds)

        completed = subprocess.run(command, **run_kwargs)
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except CompatPolicyError as error:
        return execute_policy_error(
            args,
            error,
            permission_manifest,
            started_at,
            started,
            audit_log,
            policy_context,
            layout,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        finished_at = now_iso()
        artifacts = copy_output_artifacts(layout, args.output_dir) if layout is not None else []
        payload: dict[str, object] = {
            "provider_id": PROVIDER_ID,
            "status": "timed-out",
            "execution_location": EXECUTION_LOCATION,
            "sandbox_class": sandbox_class,
            "language": args.language,
            "code_file": optional_arg_path(args.code_file),
            "input_dir": optional_arg_path(args.input_dir),
            "output_dir": optional_arg_path(args.output_dir),
            "timeout_seconds": args.timeout_seconds,
            "memory_mb": args.memory_mb,
            "cpu_seconds": args.cpu_seconds,
            "timed_out": True,
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_ms": duration_ms,
            "network_access": "allowed" if args.allow_network else "disabled",
            "subprocess_access": "allowed" if args.allow_subprocess else "disabled",
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "error": {
                "category": "timeout",
                "error_code": "sandbox_execution_timed_out",
                "message": f"sandbox execution exceeded timeout {args.timeout_seconds}s",
                "retryable": False,
            },
        }
        if layout is not None and args.retain_sandbox:
            payload["sandbox_root"] = str(layout.root)
        finalized = finalize_payload(
            args,
            payload,
            permission_manifest,
            started_at,
            finished_at,
            audit_log,
            policy_context,
        )
        if layout is not None and not args.retain_sandbox:
            shutil.rmtree(layout.root, ignore_errors=True)
        return 124, finalized
    except SandboxCommandError as error:
        duration_ms = int((time.perf_counter() - started) * 1000)
        finished_at = now_iso()
        payload = {
            "provider_id": PROVIDER_ID,
            "status": "error",
            "execution_location": EXECUTION_LOCATION,
            "sandbox_class": sandbox_class,
            "language": args.language,
            "code_file": optional_arg_path(args.code_file),
            "input_dir": optional_arg_path(args.input_dir),
            "output_dir": optional_arg_path(args.output_dir),
            "timeout_seconds": args.timeout_seconds,
            "memory_mb": args.memory_mb,
            "cpu_seconds": args.cpu_seconds,
            "timed_out": False,
            "exit_code": error.exit_code,
            "stdout": "",
            "stderr": error.message,
            "duration_ms": duration_ms,
            "network_access": "allowed" if args.allow_network else "disabled",
            "subprocess_access": "allowed" if args.allow_subprocess else "disabled",
            "artifact_count": 0,
            "artifacts": [],
            "error": error.to_payload(),
        }
        finalized = finalize_payload(
            args,
            payload,
            permission_manifest,
            started_at,
            finished_at,
            audit_log,
            policy_context,
        )
        if layout is not None and not args.retain_sandbox:
            shutil.rmtree(layout.root, ignore_errors=True)
        return error.exit_code, finalized

    duration_ms = int((time.perf_counter() - started) * 1000)
    finished_at = now_iso()
    artifacts = copy_output_artifacts(layout, args.output_dir) if layout is not None else []
    error_payload = None
    status = "ok"
    if exit_code != 0:
        status = "error"
        error_payload = {
            "category": "runtime",
            "error_code": "sandbox_exit_non_zero",
            "message": f"sandbox process exited with code {exit_code}",
            "retryable": False,
        }
    payload = {
        "provider_id": PROVIDER_ID,
        "status": status,
        "execution_location": EXECUTION_LOCATION,
        "sandbox_class": sandbox_class,
        "language": args.language,
        "code_file": optional_arg_path(args.code_file),
        "input_dir": optional_arg_path(args.input_dir),
        "output_dir": optional_arg_path(args.output_dir),
        "timeout_seconds": args.timeout_seconds,
        "memory_mb": args.memory_mb,
        "cpu_seconds": args.cpu_seconds,
        "timed_out": False,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "network_access": "allowed" if args.allow_network else "disabled",
        "subprocess_access": "allowed" if args.allow_subprocess else "disabled",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "error": error_payload,
    }
    if layout is not None and args.retain_sandbox:
        payload["sandbox_root"] = str(layout.root)
    finalized = finalize_payload(
        args,
        payload,
        permission_manifest,
        started_at,
        finished_at,
        audit_log,
        policy_context,
    )
    if layout is not None and not args.retain_sandbox:
        shutil.rmtree(layout.root, ignore_errors=True)
    return (0 if exit_code == 0 else exit_code), finalized


def execute_policy_error(
    args: argparse.Namespace,
    error: CompatPolicyError,
    permission_manifest: dict[str, object],
    started_at: str,
    started: float,
    audit_log: Path | None,
    fallback_policy_context: CompatPolicyContext,
    layout: SandboxLayout | None,
) -> tuple[int, dict[str, object]]:
    sandbox_error = compat_policy_error_to_sandbox(error)
    duration_ms = int((time.perf_counter() - started) * 1000)
    finished_at = now_iso()
    policy_context = error.policy_context or fallback_policy_context
    payload = {
        "provider_id": PROVIDER_ID,
        "status": "error",
        "execution_location": EXECUTION_LOCATION,
        "sandbox_class": resolve_sandbox_engine()[0],
        "language": args.language,
        "code_file": optional_arg_path(args.code_file),
        "input_dir": optional_arg_path(args.input_dir),
        "output_dir": optional_arg_path(args.output_dir),
        "timeout_seconds": args.timeout_seconds,
        "memory_mb": args.memory_mb,
        "cpu_seconds": args.cpu_seconds,
        "timed_out": False,
        "exit_code": sandbox_error.exit_code,
        "stdout": "",
        "stderr": sandbox_error.message,
        "duration_ms": duration_ms,
        "network_access": "allowed" if args.allow_network else "disabled",
        "subprocess_access": "allowed" if args.allow_subprocess else "disabled",
        "artifact_count": 0,
        "artifacts": [],
        "error": sandbox_error.to_payload(),
    }
    if layout is not None and args.retain_sandbox:
        payload["sandbox_root"] = str(layout.root)
    finalized = finalize_payload(
        args,
        payload,
        permission_manifest,
        started_at,
        finished_at,
        audit_log,
        policy_context,
    )
    if layout is not None and not args.retain_sandbox:
        shutil.rmtree(layout.root, ignore_errors=True)
    return sandbox_error.exit_code, finalized


def main() -> int:
    args = parse_args()
    audit_log = resolve_audit_log(args)
    policy_context = CompatPolicyContext(
        mode="standalone-local",
        policyd_socket=None,
        execution_token=None,
        token_context=None,
        verification=None,
        shared_audit_log=None,
    )

    if args.command == "manifest":
        print(json.dumps(build_manifest(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "health":
        try:
            policy_context = standalone_policy_context(args)
        except CompatPolicyError as error:
            print(json.dumps(error.to_payload(), indent=2, ensure_ascii=False))
            return compat_policy_error_to_sandbox(error).exit_code
        print(json.dumps(build_health(audit_log, policy_context), indent=2, ensure_ascii=False))
        return 0
    if args.command == "permissions":
        print(json.dumps(load_compat_permission_manifest(), indent=2, ensure_ascii=False))
        return 0

    exit_code, payload = execute(args)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
