#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DEVICED_SOCKET = "/run/aios/deviced/deviced.sock"
DEFAULT_DEVICE_METADATA_SOCKET = "/run/aios/device-metadata-provider/device-metadata-provider.sock"
DEFAULT_METADATA_MODALITIES = ["screen", "audio", "input", "camera", "ui_tree"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect AIOS device validation artifacts and renderer args for hardware bring-up reports"
    )
    parser.add_argument("--output-dir", type=Path, help="Local output directory for collected artifacts")
    parser.add_argument("--deviced-socket", default=DEFAULT_DEVICED_SOCKET)
    parser.add_argument("--device-metadata-socket", default=DEFAULT_DEVICE_METADATA_SOCKET)
    parser.add_argument(
        "--vendor-runtime-evidence-dir",
        default="",
        help="Optional vendor runtime evidence directory or single JSON file path",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--remote-host", default="", help="Optional SSH host used for remote Linux collection")
    parser.add_argument("--remote-python", default="python3", help="Python executable on the remote host")
    parser.add_argument(
        "--remote-sudo",
        default="",
        help="Optional sudo prefix for remote collection, for example `sudo -n`",
    )
    parser.add_argument("--remote-collector", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--request-json", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.remote_collector and args.output_dir is None:
        parser.error("--output-dir is required")
    return args


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def json_clone(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def note_map(notes: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    if not isinstance(notes, list):
        return values
    for note in notes:
        if not isinstance(note, str) or "=" not in note:
            continue
        key, value = note.split("=", 1)
        values[key] = value
    return values


def sorted_join(values: set[str]) -> str:
    if not values:
        return ""
    return ",".join(sorted(values))


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in (part.strip() for part in value.split(",")) if item]


def sanitize_name(name: str) -> str:
    if not name:
        return "artifact.json"
    sanitized = "".join(ch if ch.isascii() and (ch.isalnum() or ch in ".-_") else "-" for ch in name)
    sanitized = sanitized.strip(".-") or "artifact"
    if "." not in sanitized:
        sanitized += ".json"
    return sanitized


def unique_destination(directory: Path, preferred_name: str, index: int) -> Path:
    candidate = directory / f"{index:02d}-{sanitize_name(preferred_name)}"
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        next_candidate = directory / f"{stem}-{counter}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        counter += 1


def backend_evidence_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def add(path_text: str | None) -> None:
        if not path_text:
            return
        normalized = str(Path(path_text))
        if normalized in seen:
            return
        seen.add(normalized)
        paths.append(normalized)

    notes = payload.get("notes")
    if isinstance(notes, list):
        for note in notes:
            if not isinstance(note, str):
                continue
            if note.startswith("backend_evidence_artifact[") and "=" in note:
                add(note.split("=", 1)[1])

    statuses = payload.get("statuses")
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict):
                continue
            details = status.get("details")
            if not isinstance(details, list):
                continue
            for detail in details:
                if isinstance(detail, str) and detail.startswith("evidence_artifact="):
                    add(detail.split("=", 1)[1])

    evidence_artifacts = payload.get("evidence_artifacts")
    if isinstance(evidence_artifacts, list):
        for artifact in evidence_artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_path = artifact.get("artifact_path")
            if isinstance(artifact_path, str):
                add(artifact_path)

    return paths


def vendor_runtime_evidence_artifacts(root_value: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    artifacts: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    if not root_value:
        return artifacts, errors

    root = Path(root_value)
    if not root.exists():
        return artifacts, [
            {
                "target": "vendor_runtime_evidence_dir",
                "message": f"configured path does not exist: {root}",
            }
        ]

    if root.is_file():
        candidates = [root] if root.suffix.lower() == ".json" else []
    else:
        candidates = sorted(path for path in root.rglob("*.json") if path.is_file())

    for candidate in candidates:
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(
                {
                    "target": "vendor_runtime_evidence",
                    "message": f"{candidate}: {exc}",
                }
            )
            continue
        artifacts.append(
            {
                "source_path": str(candidate),
                "content": content,
            }
        )

    if not artifacts and root.is_dir():
        errors.append(
            {
                "target": "vendor_runtime_evidence_dir",
                "message": f"no JSON evidence found under {root}",
            }
        )

    return artifacts, errors


def rpc_call(socket_path: str, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    if not hasattr(socket, "AF_UNIX"):
        raise RuntimeError("Python socket.AF_UNIX unsupported on this platform")
    path = Path(socket_path)
    if not path.exists():
        raise RuntimeError(f"socket not found: {socket_path}")
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8") or "{}")
    if response.get("error"):
        raise RuntimeError(f"RPC {method} failed: {response['error']}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"RPC {method} returned non-object result")
    return result


def metadata_request() -> dict[str, Any]:
    return {
        "modalities": DEFAULT_METADATA_MODALITIES,
        "only_available": False,
        "include_state_notes": True,
    }


def collect_local_snapshot(request: dict[str, Any]) -> dict[str, Any]:
    payloads: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []

    def capture(key: str, socket_path: str, method: str, params: dict[str, Any]) -> None:
        try:
            payloads[key] = rpc_call(socket_path, method, params, request["timeout"])
        except Exception as exc:  # noqa: BLE001
            errors.append({"target": key, "message": str(exc)})

    capture("deviced_system_health", request["deviced_socket"], "system.health.get", {})
    capture("device_state", request["deviced_socket"], "device.state.get", {})
    capture("device_metadata_system_health", request["device_metadata_socket"], "system.health.get", {})
    capture("device_metadata", request["device_metadata_socket"], "device.metadata.get", metadata_request())

    evidence_artifacts: list[dict[str, str]] = []
    device_state = payloads.get("device_state")
    if isinstance(device_state, dict):
        for artifact_path in backend_evidence_paths(device_state):
            try:
                content = Path(artifact_path).read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(
                    {
                        "target": "backend_evidence_artifact",
                        "message": f"{artifact_path}: {exc}",
                    }
                )
                continue
            evidence_artifacts.append(
                {
                    "source_path": artifact_path,
                    "content": content,
                }
            )

    vendor_runtime_evidence, vendor_runtime_errors = vendor_runtime_evidence_artifacts(
        str(request.get("vendor_runtime_evidence_dir") or "")
    )
    errors.extend(vendor_runtime_errors)

    return {
        "collected_at": now_iso(),
        "source": {
            "mode": "local",
            "deviced_socket": request["deviced_socket"],
            "device_metadata_socket": request["device_metadata_socket"],
            "vendor_runtime_evidence_dir": request.get("vendor_runtime_evidence_dir") or "",
        },
        "payloads": payloads,
        "evidence_artifacts": evidence_artifacts,
        "vendor_runtime_evidence_artifacts": vendor_runtime_evidence,
        "errors": errors,
    }


def collect_remote_snapshot(
    request: dict[str, Any],
    remote_host: str,
    remote_python: str,
    remote_sudo: str,
) -> dict[str, Any]:
    script_source = Path(__file__).read_text(encoding="utf-8")
    command = ["ssh", remote_host]
    if remote_sudo:
        command.extend(shlex.split(remote_sudo))
    command.extend([remote_python, "-", "--remote-collector", "--request-json", json.dumps(request, ensure_ascii=False)])
    completed = subprocess.run(
        command,
        input=script_source,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"returncode={completed.returncode}"
        raise RuntimeError(f"remote collection failed on {remote_host}: {detail}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("remote collection returned non-object JSON")
    payload["source"] = {
        "mode": "remote",
        "host": remote_host,
        "deviced_socket": request["deviced_socket"],
        "device_metadata_socket": request["device_metadata_socket"],
        "vendor_runtime_evidence_dir": request.get("vendor_runtime_evidence_dir") or "",
    }
    return payload


def rewrite_backend_state_paths(
    payload: dict[str, Any],
    replacements: dict[str, str],
    vendor_runtime_paths: list[Path],
) -> dict[str, Any]:
    rewritten = json_clone(payload)

    notes = rewritten.get("notes")
    if not isinstance(notes, list):
        notes = []
        rewritten["notes"] = notes

    for index, note in enumerate(notes):
        if not isinstance(note, str) or "=" not in note:
            continue
        if note.startswith("backend_evidence_artifact["):
            prefix, source_path = note.split("=", 1)
            replacement = replacements.get(source_path)
            if replacement:
                notes[index] = f"{prefix}={replacement}"

    statuses = rewritten.get("statuses")
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict):
                continue
            details = status.get("details")
            if not isinstance(details, list):
                continue
            for index, detail in enumerate(details):
                if not isinstance(detail, str) or not detail.startswith("evidence_artifact="):
                    continue
                source_path = detail.split("=", 1)[1]
                replacement = replacements.get(source_path)
                if replacement:
                    details[index] = f"evidence_artifact={replacement}"

    evidence_artifacts = rewritten.get("evidence_artifacts")
    if isinstance(evidence_artifacts, list):
        for artifact in evidence_artifacts:
            if not isinstance(artifact, dict):
                continue
            source_path = artifact.get("artifact_path")
            if not isinstance(source_path, str):
                continue
            replacement = replacements.get(source_path)
            if replacement:
                artifact["artifact_path"] = replacement

    existing_vendor_paths = {
        note.split("=", 1)[1]
        for note in notes
        if isinstance(note, str) and note.startswith("vendor_evidence_path=") and "=" in note
    }
    for vendor_path in vendor_runtime_paths:
        path_text = str(vendor_path)
        if path_text in existing_vendor_paths:
            continue
        notes.append(f"vendor_evidence_path={path_text}")
        existing_vendor_paths.add(path_text)

    return rewritten


def current_ui_tree_support(device_state: dict[str, Any]) -> str:
    backend_summary = device_state.get("backend_summary")
    if isinstance(backend_summary, dict):
        value = backend_summary.get("ui_tree_current_support")
        if isinstance(value, str) and value:
            return value
    matrix = device_state.get("ui_tree_support_matrix")
    if isinstance(matrix, list):
        for entry in matrix:
            if not isinstance(entry, dict):
                continue
            if entry.get("current") is True and isinstance(entry.get("readiness"), str):
                return str(entry["readiness"])
    return ""


def derive_release_grade_summary(
    metadata: dict[str, Any] | None,
    metadata_health: dict[str, Any] | None,
    evidence_payloads: list[dict[str, Any]],
) -> dict[str, str]:
    values = {
        "backend_ids": set(),
        "origins": set(),
        "stacks": set(),
        "contract_kinds": set(),
    }

    metadata_notes = note_map((metadata or {}).get("notes"))
    metadata_health_notes = note_map((metadata_health or {}).get("notes"))

    for note_key, result_key in [
        ("release_grade_backend_ids", "backend_ids"),
        ("release_grade_backend_origins", "origins"),
        ("release_grade_backend_stacks", "stacks"),
        ("release_grade_contract_kinds", "contract_kinds"),
    ]:
        for item in split_csv(metadata_notes.get(note_key)):
            values[result_key].add(item)

    for note_key, result_key in [
        ("device_release_grade_backend_ids", "backend_ids"),
        ("device_release_grade_backend_origins", "origins"),
        ("device_release_grade_backend_stacks", "stacks"),
        ("device_release_grade_contract_kinds", "contract_kinds"),
    ]:
        for item in split_csv(metadata_health_notes.get(note_key)):
            values[result_key].add(item)

    for payload in evidence_payloads:
        if not isinstance(payload, dict):
            continue
        backend_id = payload.get("release_grade_backend_id") or payload.get("release_grade_backend")
        origin = payload.get("release_grade_backend_origin")
        stack = payload.get("release_grade_backend_stack")
        contract_kind = payload.get("release_grade_contract_kind") or payload.get("contract_kind")
        if isinstance(backend_id, str) and backend_id:
            values["backend_ids"].add(backend_id)
        if isinstance(origin, str) and origin:
            values["origins"].add(origin)
        if isinstance(stack, str) and stack:
            values["stacks"].add(stack)
        if isinstance(contract_kind, str) and contract_kind:
            values["contract_kinds"].add(contract_kind)

    return {
        "backend_ids": sorted_join(values["backend_ids"]),
        "origins": sorted_join(values["origins"]),
        "stacks": sorted_join(values["stacks"]),
        "contract_kinds": sorted_join(values["contract_kinds"]),
    }


def append_arg(arguments: list[str], name: str, value: str | int | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    arguments.extend([f"--{name}", text])


def available_modalities(metadata: dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
        return ""
    summary = metadata.get("summary")
    if isinstance(summary, dict):
        values = summary.get("available_modalities")
        if isinstance(values, list):
            return ",".join(str(item) for item in values if str(item).strip())
    entries = metadata.get("entries")
    if isinstance(entries, list):
        values = [
            str(entry.get("modality"))
            for entry in entries
            if isinstance(entry, dict) and entry.get("available") and isinstance(entry.get("modality"), str)
        ]
        if values:
            return ",".join(sorted(values))
    return ""


def build_renderer_args(
    deviced_health: dict[str, Any] | None,
    device_state: dict[str, Any] | None,
    metadata_health: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    backend_state_path: Path | None,
    evidence_payloads: list[dict[str, Any]],
    vendor_runtime_paths: list[Path],
) -> list[str]:
    arguments: list[str] = []

    if isinstance(deviced_health, dict):
        append_arg(arguments, "deviced-health", deviced_health.get("status"))

    if isinstance(device_state, dict):
        backend_summary = device_state.get("backend_summary")
        if isinstance(backend_summary, dict):
            append_arg(arguments, "device-backend-overall-status", backend_summary.get("overall_status"))
            append_arg(arguments, "device-backend-available-count", backend_summary.get("available_status_count"))
        append_arg(arguments, "device-ui-tree-support", current_ui_tree_support(device_state))

    if isinstance(metadata, dict):
        summary = metadata.get("summary")
        if isinstance(summary, dict):
            append_arg(arguments, "device-metadata-status", summary.get("overall_status"))
        backend_summary = metadata.get("backend_summary")
        if isinstance(backend_summary, dict):
            append_arg(arguments, "device-metadata-backend-status", backend_summary.get("overall_status"))
        append_arg(arguments, "device-available-modalities", available_modalities(metadata))

    release_grade_summary = derive_release_grade_summary(metadata, metadata_health, evidence_payloads)
    append_arg(arguments, "device-release-grade-backend-ids", release_grade_summary["backend_ids"])
    append_arg(arguments, "device-release-grade-backend-origins", release_grade_summary["origins"])
    append_arg(arguments, "device-release-grade-backend-stacks", release_grade_summary["stacks"])
    append_arg(arguments, "device-release-grade-contract-kinds", release_grade_summary["contract_kinds"])

    if backend_state_path is not None:
        append_arg(arguments, "device-backend-state-artifact", str(backend_state_path))

    for vendor_runtime_path in vendor_runtime_paths:
        append_arg(arguments, "vendor-runtime-evidence", str(vendor_runtime_path))

    return arguments


def materialize_snapshot(snapshot: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = snapshot.get("payloads") if isinstance(snapshot.get("payloads"), dict) else {}

    deviced_health = payloads.get("deviced_system_health") if isinstance(payloads.get("deviced_system_health"), dict) else None
    device_state = payloads.get("device_state") if isinstance(payloads.get("device_state"), dict) else None
    metadata_health = (
        payloads.get("device_metadata_system_health")
        if isinstance(payloads.get("device_metadata_system_health"), dict)
        else None
    )
    metadata = payloads.get("device_metadata") if isinstance(payloads.get("device_metadata"), dict) else None

    artifact_paths: dict[str, str] = {}
    evidence_payloads: list[dict[str, Any]] = []
    evidence_dir = output_dir / "backend-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    vendor_runtime_dir = output_dir / "vendor-runtime-evidence"
    vendor_runtime_dir.mkdir(parents=True, exist_ok=True)
    vendor_runtime_paths: list[Path] = []

    for index, artifact in enumerate(snapshot.get("evidence_artifacts") or [], start=1):
        if not isinstance(artifact, dict):
            continue
        source_path = artifact.get("source_path")
        content = artifact.get("content")
        if not isinstance(source_path, str) or not isinstance(content, str):
            continue
        destination = unique_destination(evidence_dir, Path(source_path).name, index)
        write_text(destination, content)
        artifact_paths[source_path] = str(destination)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            evidence_payloads.append(parsed)

    for index, artifact in enumerate(snapshot.get("vendor_runtime_evidence_artifacts") or [], start=1):
        if not isinstance(artifact, dict):
            continue
        source_path = artifact.get("source_path")
        content = artifact.get("content")
        if not isinstance(source_path, str) or not isinstance(content, str):
            continue
        destination = unique_destination(vendor_runtime_dir, Path(source_path).name, index)
        write_text(destination, content)
        vendor_runtime_paths.append(destination)

    backend_state_path: Path | None = None
    if device_state is not None:
        backend_state_path = output_dir / "backend-state.json"
        rewritten_state = rewrite_backend_state_paths(device_state, artifact_paths, vendor_runtime_paths)
        write_json(backend_state_path, rewritten_state)
        device_state = rewritten_state

    file_map = {
        "deviced_system_health": deviced_health,
        "device_metadata_system_health": metadata_health,
        "device_metadata": metadata,
    }
    for name, payload in file_map.items():
        if payload is not None:
            write_json(output_dir / f"{name}.json", payload)

    renderer_args = build_renderer_args(
        deviced_health,
        device_state,
        metadata_health,
        metadata,
        backend_state_path,
        evidence_payloads,
        vendor_runtime_paths,
    )
    renderer_args_path = output_dir / "renderer-args.txt"
    write_text(renderer_args_path, "\n".join(renderer_args) + ("\n" if renderer_args else ""))

    summary = {
        "collected_at": snapshot.get("collected_at") or now_iso(),
        "source": snapshot.get("source") or {},
        "output_dir": str(output_dir),
        "backend_state_artifact": "" if backend_state_path is None else str(backend_state_path),
        "renderer_args_path": str(renderer_args_path),
        "renderer_args": renderer_args,
        "artifacts": {
            "deviced_system_health": ""
            if deviced_health is None
            else str(output_dir / "deviced_system_health.json"),
            "device_metadata_system_health": ""
            if metadata_health is None
            else str(output_dir / "device_metadata_system_health.json"),
            "device_metadata": ""
            if metadata is None
            else str(output_dir / "device_metadata.json"),
            "backend_evidence_dir": str(evidence_dir),
            "vendor_runtime_evidence_dir": str(vendor_runtime_dir),
        },
        "vendor_runtime_evidence_paths": [str(path) for path in vendor_runtime_paths],
        "errors": snapshot.get("errors") or [],
    }
    write_json(output_dir / "collection-summary.json", summary)
    return summary


def main() -> int:
    args = parse_args()
    if args.remote_collector:
        request = json.loads(args.request_json)
        snapshot = collect_local_snapshot(request)
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        return 0

    request = {
        "deviced_socket": args.deviced_socket,
        "device_metadata_socket": args.device_metadata_socket,
        "vendor_runtime_evidence_dir": args.vendor_runtime_evidence_dir,
        "timeout": args.timeout,
    }
    if args.remote_host:
        snapshot = collect_remote_snapshot(request, args.remote_host, args.remote_python, args.remote_sudo)
    else:
        snapshot = collect_local_snapshot(request)

    summary = materialize_snapshot(snapshot, args.output_dir)
    if not (
        summary["artifacts"]["deviced_system_health"]
        or summary["backend_state_artifact"]
        or summary["artifacts"]["device_metadata"]
    ):
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
