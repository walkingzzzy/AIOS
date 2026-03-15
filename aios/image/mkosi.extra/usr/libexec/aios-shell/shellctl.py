#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parent
DEFAULT_PROFILE = ROOT / "profiles" / "default-shell-profile.yaml"

COMPONENT_CLIENTS = {
    "launcher": ROOT / "components" / "launcher" / "client.py",
    "task-surface": ROOT / "components" / "task-surface" / "client.py",
    "approval-panel": ROOT / "components" / "approval-panel" / "client.py",
    "recovery-surface": ROOT / "components" / "recovery-surface" / "client.py",
    "notification-center": ROOT / "components" / "notification-center" / "client.py",
    "portal-chooser": ROOT / "components" / "portal-chooser" / "client.py",
    "capture-indicators": ROOT / "components" / "capture-indicators" / "client.py",
    "device-backend-status": ROOT / "components" / "device-backend-status" / "client.py",
}

COMPONENT_PANELS = {
    "launcher": ROOT / "components" / "launcher" / "panel.py",
    "task-surface": ROOT / "components" / "task-surface" / "panel.py",
    "approval-panel": ROOT / "components" / "approval-panel" / "panel.py",
    "recovery-surface": ROOT / "components" / "recovery-surface" / "panel.py",
    "notification-center": ROOT / "components" / "notification-center" / "panel.py",
    "portal-chooser": ROOT / "components" / "portal-chooser" / "panel.py",
    "capture-indicators": ROOT / "components" / "capture-indicators" / "panel.py",
    "device-backend-status": ROOT / "components" / "device-backend-status" / "panel.py",
}

COMPONENT_STANDALONES = {
    "portal-chooser": ROOT / "components" / "portal-chooser" / "standalone.py",
}

PROFILE_COMPONENT_KEYS = {
    "launcher": "launcher",
    "task-surface": "task_surface",
    "approval-panel": "approval_panel",
    "recovery-surface": "recovery_surface",
    "notification-center": "notification_center",
    "portal-chooser": "portal_chooser",
    "capture-indicators": "capture_indicators",
    "device-backend-status": "device_backend_status",
}

DESKTOP_ENTRYPOINT = ROOT / "runtime" / "shell_desktop.py"
SESSION_ENTRYPOINT = ROOT / "runtime" / "shell_session.py"
DEFAULT_AGENTD_SOCKET = Path("/run/aios/agentd/agentd.sock")
DEFAULT_POLICYD_SOCKET = Path("/run/aios/policyd/policyd.sock")
DEFAULT_SHELL_CONTROL_PROVIDER_SOCKET = Path(
    "/run/aios/shell-provider/shell-control-provider.sock"
)
DEFAULT_SCREEN_CAPTURE_PROVIDER_SOCKET = Path(
    "/run/aios/screen-provider/screen-capture-provider.sock"
)

STATUS_COMPONENTS = [
    "recovery-surface",
    "notification-center",
    "device-backend-status",
    "capture-indicators",
]


def load_profile(path: Path) -> dict:
    text = path.read_text()
    if not text.strip():
        return {}
    if yaml is not None:
        return yaml.safe_load(text) or {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return parse_simple_yaml(text)


def parse_simple_yaml(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            raise SystemExit(f"unsupported profile line: {raw_line}")
        key, raw_value = line.split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value = raw_value.strip()
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
            continue
        parent[key] = parse_scalar(value)

    return root


def parse_scalar(value: str):
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", "~"}:
        return None
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


def normalize_component(name: str) -> str:
    key = name.strip().lower().replace("_", "-")
    if key not in COMPONENT_CLIENTS:
        raise SystemExit(f"unknown component: {name}")
    return key


def component_enabled(profile: dict, component: str) -> bool:
    components = profile.get("components", {})
    profile_key = PROFILE_COMPONENT_KEYS[component]
    return bool(components.get(profile_key, False))


def profile_path(profile: dict, key: str, default: Path) -> Path:
    paths = profile.get("paths", {}) or {}
    value = paths.get(key)
    if value in (None, ""):
        return default
    return Path(value)


def policyd_socket(profile: dict) -> Path:
    return profile_path(profile, "policyd_socket", DEFAULT_POLICYD_SOCKET)


def agentd_socket(profile: dict) -> Path:
    return profile_path(profile, "agentd_socket", DEFAULT_AGENTD_SOCKET)


def shell_control_provider_socket(profile: dict, override: Path | None = None) -> Path:
    if override is not None:
        return override
    return profile_path(
        profile,
        "shell_control_provider_socket",
        DEFAULT_SHELL_CONTROL_PROVIDER_SOCKET,
    )


def screen_capture_provider_socket(profile: dict) -> Path:
    return profile_path(
        profile,
        "screen_capture_provider_socket",
        DEFAULT_SCREEN_CAPTURE_PROVIDER_SOCKET,
    )


def component_base_args(profile: dict, component: str) -> list[str]:
    paths = profile.get("paths", {})
    compositor = profile.get("compositor", {}) or {}
    if component == "launcher":
        return ["--socket", paths.get("sessiond_socket", "/run/aios/sessiond/sessiond.sock")]
    if component == "task-surface":
        return [
            "--socket",
            paths.get("sessiond_socket", "/run/aios/sessiond/sessiond.sock"),
            "--agent-socket",
            paths.get("agentd_socket", str(agentd_socket(profile))),
        ]
    if component == "approval-panel":
        return ["--socket", paths.get("policyd_socket", "/run/aios/policyd/policyd.sock")]
    if component == "recovery-surface":
        return [
            "--socket",
            paths.get("updated_socket", "/run/aios/updated/updated.sock"),
            "--surface",
            paths.get("recovery_surface_model", "/var/lib/aios/updated/recovery-surface.json"),
        ]
    if component == "notification-center":
        command = [
            "--recovery-surface",
            paths.get("recovery_surface_model", "/var/lib/aios/updated/recovery-surface.json"),
            "--updated-socket",
            paths.get("updated_socket", "/run/aios/updated/updated.sock"),
            "--indicator-state",
            paths.get("capture_indicator_state", "/var/lib/aios/deviced/indicator-state.json"),
            "--backend-state",
            paths.get("device_backend_state", "/var/lib/aios/deviced/backend-state.json"),
            "--deviced-socket",
            paths.get("deviced_socket", "/run/aios/deviced/deviced.sock"),
            "--policy-socket",
            paths.get("policyd_socket", "/run/aios/policyd/policyd.sock"),
        ]
        panel_action_log_path = paths.get("panel_action_log_path") or compositor.get(
            "panel_action_log_path"
        )
        if panel_action_log_path:
            command.extend(["--panel-action-log", panel_action_log_path])
        return command
    if component == "portal-chooser":
        return [
            "--socket",
            paths.get("sessiond_socket", "/run/aios/sessiond/sessiond.sock"),
            "--policy-socket",
            paths.get("policyd_socket", str(policyd_socket(profile))),
            "--deviced-socket",
            paths.get("deviced_socket", "/run/aios/deviced/deviced.sock"),
            "--screen-provider-socket",
            paths.get(
                "screen_capture_provider_socket",
                str(screen_capture_provider_socket(profile)),
            ),
        ]
    if component == "capture-indicators":
        return [
            "--path",
            paths.get("capture_indicator_state", "/var/lib/aios/deviced/indicator-state.json"),
        ]
    if component == "device-backend-status":
        return [
            "--path",
            paths.get("device_backend_state", "/var/lib/aios/deviced/backend-state.json"),
            "--socket",
            paths.get("deviced_socket", "/run/aios/deviced/deviced.sock"),
        ]
    raise SystemExit(f"unsupported component mapping: {component}")


def run_script(script: Path, command_args: list[str], expect_json: bool = False) -> str | dict:
    completed = subprocess.run([sys.executable, str(script), *command_args], check=True, text=True, capture_output=True)
    output = completed.stdout.strip()
    if expect_json:
        return json.loads(output or "{}")
    return output


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise SystemExit(f"RPC {method} failed: {response['error']}")
    return response["result"]


def issue_execution_token(
    profile: dict,
    *,
    user_id: str,
    session_id: str,
    task_id: str,
    capability_id: str,
) -> dict:
    return rpc_call(
        policyd_socket(profile),
        "policy.token.issue",
        {
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "capability_id": capability_id,
            "execution_location": "local",
            "constraints": {},
        },
    )


def shell_control_request(
    profile: dict,
    *,
    provider_socket: Path | None,
    user_id: str,
    session_id: str,
    task_id: str,
    capability_id: str,
    params: dict,
) -> dict:
    token = issue_execution_token(
        profile,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        capability_id=capability_id,
    )
    request = {"execution_token": token, **params}
    return rpc_call(
        shell_control_provider_socket(profile, provider_socket),
        capability_id,
        request,
    )


def run_component(profile: dict, component: str, extra_args: list[str], expect_json: bool = False) -> str | dict:
    script = COMPONENT_CLIENTS[component]
    command = [*component_base_args(profile, component), *extra_args]
    return run_script(script, command, expect_json=expect_json)


def run_panel(profile: dict, component: str, extra_args: list[str], expect_json: bool = False) -> str | dict:
    script = COMPONENT_PANELS[component]
    command = [*component_base_args(profile, component), *extra_args]
    return run_script(script, command, expect_json=expect_json)


def run_standalone(profile: dict, component: str, extra_args: list[str], expect_json: bool = False) -> str | dict:
    script = COMPONENT_STANDALONES[component]
    command = [*component_base_args(profile, component), *extra_args]
    return run_script(script, command, expect_json=expect_json)


def component_status(profile: dict, component: str) -> dict:
    if component == "recovery-surface":
        return run_component(profile, component, ["summary", "--json"], expect_json=True)
    if component == "notification-center":
        return run_component(profile, component, ["summary", "--json"], expect_json=True)
    if component == "device-backend-status":
        return run_component(profile, component, ["attention", "--json"], expect_json=True)
    if component == "capture-indicators":
        return run_component(profile, component, ["status", "--json"], expect_json=True)
    raise SystemExit(f"unsupported status component: {component}")


def command_components(profile: dict, as_json: bool) -> int:
    enabled = [name for name in COMPONENT_CLIENTS if component_enabled(profile, name)]
    disabled = [name for name in COMPONENT_CLIENTS if name not in enabled]
    payload = {
        "profile_id": profile.get("profile_id", "unknown"),
        "enabled": enabled,
        "disabled": disabled,
    }
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"profile_id: {payload['profile_id']}")
        print("enabled:")
        for item in enabled:
            print(f"- {item}")
        print("disabled:")
        for item in disabled:
            print(f"- {item}")
    return 0


def command_status(profile: dict, as_json: bool) -> int:
    payload = {
        "profile_id": profile.get("profile_id", "unknown"),
        "components": {},
    }
    for component in STATUS_COMPONENTS:
        if not component_enabled(profile, component):
            continue
        payload["components"][component] = component_status(profile, component)
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"profile_id: {payload['profile_id']}")
        for component, value in payload["components"].items():
            print(f"[{component}]")
            print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0


def command_component(profile: dict, component_name: str, component_args: list[str], as_json: bool, allow_disabled: bool) -> int:
    component = normalize_component(component_name)
    if not component_enabled(profile, component) and not allow_disabled:
        raise SystemExit(f"component disabled in profile: {component}")

    args = list(component_args)
    if as_json and "--json" not in args:
        args.append("--json")
    result = run_component(profile, component, args, expect_json=False)
    print(result)
    return 0


def command_panel(profile: dict, component_name: str, panel_args: list[str], as_json: bool, allow_disabled: bool) -> int:
    component = normalize_component(component_name)
    if component not in COMPONENT_PANELS:
        raise SystemExit(f"panel entrypoint not available for component: {component}")
    if not component_enabled(profile, component) and not allow_disabled:
        raise SystemExit(f"component disabled in profile: {component}")

    args = list(panel_args)
    if as_json and "--json" not in args and "model" not in args and "watch" not in args:
        args.append("--json")
    result = run_panel(profile, component, args, expect_json=False)
    print(result)
    return 0


def command_chooser(profile: dict, chooser_args: list[str], as_json: bool, allow_disabled: bool) -> int:
    component = "portal-chooser"
    if component not in COMPONENT_STANDALONES:
        raise SystemExit("standalone chooser entrypoint not available")
    if not component_enabled(profile, component) and not allow_disabled:
        raise SystemExit(f"component disabled in profile: {component}")

    args = list(chooser_args)
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        args = ["snapshot"]
    if as_json and "--json" not in args:
        args.append("--json")
    result = run_standalone(profile, component, args, expect_json=False)
    print(result)
    return 0


def print_control_result(command: str, result: dict) -> None:
    if command == "notification-open":
        print(f"provider_id: {result.get('provider_id')}")
        print(f"status: {result.get('status')}")
        print(f"notification_count: {result.get('notification_count', 0)}")
        model = result.get("model") or {}
        if model:
            print(f"panel_id: {model.get('panel_id')}")
        return

    if command == "window-focus":
        print(f"provider_id: {result.get('provider_id')}")
        print(f"status: {result.get('status')}")
        print(f"focused_target: {result.get('focused_target')}")
        print(f"state_path: {result.get('state_path')}")
        return

    print(f"provider_id: {result.get('provider_id')}")
    print(f"status: {result.get('status')}")
    print(f"entry_count: {result.get('entry_count', 0)}")
    print(f"matched_entry_count: {result.get('matched_entry_count', 0)}")
    print(f"panel_action_log_path: {result.get('panel_action_log_path') or '-'}")
    for entry in result.get("entries", []) or []:
        component = entry.get("component") or entry.get("slot_id") or "panel-slot"
        action_id = entry.get("action_id") or "unknown"
        status = entry.get("status") or "unknown"
        print(f"{entry.get('event_id')}: {component}::{action_id} [{status}]")
        summary = entry.get("summary")
        if summary not in (None, ""):
            print(f"summary: {summary}")


def command_control(profile: dict, args: argparse.Namespace, as_json: bool) -> int:
    provider_socket = getattr(args, "provider_socket", None)

    if args.control_command == "notification-open":
        result = shell_control_request(
            profile,
            provider_socket=provider_socket,
            user_id=args.user_id,
            session_id=args.session_id,
            task_id=args.task_id,
            capability_id="shell.notification.open",
            params={
                "include_model": args.include_model,
                "source": args.source,
            },
        )
    elif args.control_command == "window-focus":
        result = shell_control_request(
            profile,
            provider_socket=provider_socket,
            user_id=args.user_id,
            session_id=args.session_id,
            task_id=args.task_id,
            capability_id="shell.window.focus",
            params={
                "target": args.target,
                "reason": args.reason,
            },
        )
    else:
        result = shell_control_request(
            profile,
            provider_socket=provider_socket,
            user_id=args.user_id,
            session_id=args.session_id,
            task_id=args.task_id,
            capability_id="shell.panel-events.list",
            params={
                "limit": args.limit,
                "kind": args.kind,
                "component": args.component,
                "slot_id": args.slot_id,
                "panel_id": args.panel_id,
                "action_id": args.action_id,
                "status_filter": args.status_filter,
                "include_payload": args.include_payload,
            },
        )

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_control_result(args.control_command, result)
    return 0



def command_desktop(profile_path: Path, desktop_args: list[str], as_json: bool) -> int:
    args = ["--profile", str(profile_path), *desktop_args]
    if as_json and "--json" not in args:
        args.append("--json")
    result = run_script(DESKTOP_ENTRYPOINT, args, expect_json=False)
    print(result)
    return 0


def command_session(profile_path: Path, session_args: list[str], as_json: bool) -> int:
    args = ["--profile", str(profile_path), *session_args]
    if as_json and "--json" not in args:
        args.append("--json")
    result = run_script(SESSION_ENTRYPOINT, args, expect_json=False)
    print(result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOS unified shell control CLI")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser("components", help="List enabled and disabled components")
    subparsers.add_parser("status", help="Collect status summaries from enabled shell surfaces")

    component_parser = subparsers.add_parser("component", help="Run a specific shell component client")
    component_parser.add_argument("name")
    component_parser.add_argument("--allow-disabled", action="store_true")
    component_parser.add_argument("args", nargs=argparse.REMAINDER)

    panel_parser = subparsers.add_parser("panel", help="Run a shell panel skeleton entrypoint")
    panel_parser.add_argument("name")
    panel_parser.add_argument("--allow-disabled", action="store_true")
    panel_parser.add_argument("args", nargs=argparse.REMAINDER)

    chooser_parser = subparsers.add_parser("chooser", help="Run the standalone portal chooser host")
    chooser_parser.add_argument("--allow-disabled", action="store_true")
    chooser_parser.add_argument("args", nargs=argparse.REMAINDER)

    control_parser = subparsers.add_parser("control", help="Call shell control provider capabilities")
    control_parser.add_argument("--provider-socket", type=Path)
    control_subparsers = control_parser.add_subparsers(dest="control_command", required=True)

    notification_parser = control_subparsers.add_parser(
        "notification-open",
        help="Open notification center through shell.control.local",
    )
    notification_parser.add_argument("--user-id", default="local-user")
    notification_parser.add_argument("--session-id", required=True)
    notification_parser.add_argument("--task-id", required=True)
    notification_parser.add_argument("--source", default="shellctl")
    notification_parser.add_argument("--include-model", action="store_true")

    focus_parser = control_subparsers.add_parser(
        "window-focus",
        help="Focus a shell target through shell.control.local",
    )
    focus_parser.add_argument("--user-id", default="local-user")
    focus_parser.add_argument("--session-id", required=True)
    focus_parser.add_argument("--task-id", required=True)
    focus_parser.add_argument("--target", required=True)
    focus_parser.add_argument("--reason")

    panel_events_parser = control_subparsers.add_parser(
        "panel-events",
        help="List compositor panel action events through shell.control.local",
    )
    panel_events_parser.add_argument("--user-id", default="local-user")
    panel_events_parser.add_argument("--session-id", required=True)
    panel_events_parser.add_argument("--task-id", required=True)
    panel_events_parser.add_argument("--limit", type=int)
    panel_events_parser.add_argument("--kind")
    panel_events_parser.add_argument("--component")
    panel_events_parser.add_argument("--slot-id")
    panel_events_parser.add_argument("--panel-id")
    panel_events_parser.add_argument("--action-id")
    panel_events_parser.add_argument("--status-filter")
    panel_events_parser.add_argument("--include-payload", action="store_true")

    desktop_parser = subparsers.add_parser("desktop", help="Run the shell desktop host")
    desktop_parser.add_argument("args", nargs=argparse.REMAINDER)

    session_parser = subparsers.add_parser("session", help="Run the shell session bootstrap")
    session_parser.add_argument("args", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    command = args.command or "status"
    profile = load_profile(args.profile)

    if command == "components":
        return command_components(profile, args.json)
    if command == "status":
        return command_status(profile, args.json)
    if command == "panel":
        return command_panel(profile, args.name, args.args, args.json, args.allow_disabled)
    if command == "chooser":
        return command_chooser(profile, args.args, args.json, args.allow_disabled)
    if command == "control":
        return command_control(profile, args, args.json)
    if command == "desktop":
        return command_desktop(args.profile, args.args, args.json)
    if command == "session":
        return command_session(args.profile, args.args, args.json)
    return command_component(profile, args.name, args.args, args.json, args.allow_disabled)


if __name__ == "__main__":
    raise SystemExit(main())
