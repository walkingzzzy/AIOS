#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from prototype import default_agent_socket, default_socket, fixture_call, print_list, rpc_call
_PRIVACY_MEMORY_PROTOTYPE_MODULE: ModuleType | None = None


def _load_module(module_name: str, path: Path) -> ModuleType:
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_privacy_memory_prototype_module() -> ModuleType:
    global _PRIVACY_MEMORY_PROTOTYPE_MODULE
    if _PRIVACY_MEMORY_PROTOTYPE_MODULE is not None:
        return _PRIVACY_MEMORY_PROTOTYPE_MODULE
    module_path = Path(__file__).resolve().parents[1] / "privacy-memory" / "prototype.py"
    _PRIVACY_MEMORY_PROTOTYPE_MODULE = _load_module(
        "aios_shell_privacy_memory_prototype",
        module_path,
    )
    return _PRIVACY_MEMORY_PROTOTYPE_MODULE


def default_runtime_platform_env_path() -> Path:
    return load_privacy_memory_prototype_module().default_runtime_platform_env_path()


def build_privacy_memory_state(runtime_platform_env_path: Path | None) -> dict:
    return load_privacy_memory_prototype_module().build_privacy_memory_state(runtime_platform_env_path)


def build_summary(result: dict, privacy_memory: dict | None = None) -> dict:
    approvals = result.get("approvals", [])
    by_status: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    privacy_memory = privacy_memory or {}
    for item in approvals:
        status = item.get("status", "unknown")
        lane = item.get("approval_lane", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_lane[lane] = by_lane.get(lane, 0) + 1
    return {
        "total": len(approvals),
        "by_status": by_status,
        "by_lane": by_lane,
        "approval_default_policy": privacy_memory.get("approval_default_policy"),
        "remote_prompt_level": privacy_memory.get("remote_prompt_level"),
    }


def print_record(record: dict) -> None:
    print(f"approval_ref: {record.get('approval_ref')}")
    print(f"status: {record.get('status')}")
    print(f"capability: {record.get('capability_id')}")
    print(f"session_id: {record.get('session_id')}")
    print(f"task_id: {record.get('task_id')}")
    print(f"lane: {record.get('approval_lane')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS approval panel shell client")
    parser.add_argument(
        "command",
        nargs="?",
        default="list",
        choices=["list", "get", "create", "resolve", "summary"],
    )
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--agent-socket", type=Path, default=default_agent_socket())
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--approval-ref")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--session-id")
    parser.add_argument("--task-id")
    parser.add_argument("--capability-id", default="device.capture.audio")
    parser.add_argument("--approval-lane", default="high-risk")
    parser.add_argument("--execution-location", default="local")
    parser.add_argument("--status")
    parser.add_argument("--runtime-platform-env", type=Path, default=default_runtime_platform_env_path())
    parser.add_argument("--resolver", default="shell-approval-panel")
    parser.add_argument("--reason")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    command = args.command
    effective_command = "list" if command == "summary" else command
    if args.fixture is not None:
        result = fixture_call(args.fixture, effective_command, args)
    elif effective_command == "list":
        result = rpc_call(
            args.agent_socket,
            "agent.approval.list",
            {"session_id": args.session_id, "task_id": args.task_id, "status": args.status},
        )
    elif effective_command == "create":
        if not args.session_id or not args.task_id:
            raise SystemExit("--session-id and --task-id are required for create")
        result = rpc_call(
            args.agent_socket,
            "agent.approval.create",
            {
                "user_id": args.user_id,
                "session_id": args.session_id,
                "task_id": args.task_id,
                "capability_id": args.capability_id,
                "approval_lane": args.approval_lane,
                "execution_location": args.execution_location,
                "reason": args.reason,
            },
        )
    elif effective_command == "get":
        if not args.approval_ref:
            raise SystemExit("--approval-ref is required for get")
        result = rpc_call(args.agent_socket, "agent.approval.get", {"approval_ref": args.approval_ref})
    else:
        if not args.approval_ref:
            raise SystemExit("--approval-ref is required for resolve")
        result = rpc_call(
            args.agent_socket,
            "agent.approval.resolve",
            {
                "approval_ref": args.approval_ref,
                "status": args.status or "approved",
                "resolver": args.resolver,
                "reason": args.reason,
            },
        )

    if command == "summary":
        summary = build_summary(result, build_privacy_memory_state(args.runtime_platform_env))
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"total: {summary['total']}")
            print(f"by_status: {json.dumps(summary['by_status'], ensure_ascii=False, sort_keys=True)}")
            print(f"by_lane: {json.dumps(summary['by_lane'], ensure_ascii=False, sort_keys=True)}")
    elif command == "list" and not args.json:
        print_list(result)
    elif command in {"get", "create", "resolve"} and not args.json:
        print_record(result)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
