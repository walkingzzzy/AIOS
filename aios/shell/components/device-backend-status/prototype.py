#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path


def default_backend_state() -> Path:
    return Path(
        os.environ.get(
            "AIOS_DEVICED_BACKEND_STATE_PATH",
            "/var/lib/aios/deviced/backend-state.json",
        )
    )


def default_socket() -> Path:
    return Path(os.environ.get("AIOS_DEVICED_SOCKET_PATH", "/run/aios/deviced/deviced.sock"))


def rpc_call(socket_path: Path, method: str, params: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
    response = json.loads(data.decode("utf-8"))
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response["result"]


def load_model(path: Path, fixture: Path | None, socket_path: Path) -> dict | None:
    source = fixture or path
    if source.exists():
        return attach_evidence_artifacts(json.loads(source.read_text()))
    if socket_path.exists():
        state = rpc_call(socket_path, "device.state.get", {})
        return attach_evidence_artifacts(
            {
                "updated_at": None,
                "statuses": state.get("backend_statuses", []),
                "adapters": state.get("capture_adapters", []),
                "ui_tree_snapshot": state.get("ui_tree_snapshot"),
                "backend_summary": state.get("backend_summary", {}),
                "ui_tree_support_matrix": state.get("ui_tree_support_matrix", []),
                "notes": state.get("notes", []),
            }
        )
    return None


def note_value(notes: list[object], prefix: str) -> str | None:
    for note in notes:
        if not isinstance(note, str):
            continue
        if note.startswith(prefix):
            return note[len(prefix) :]
    return None


def evidence_artifact_path(status: dict, notes: list[object]) -> Path | None:
    details = status.get("details", [])
    if isinstance(details, list):
        value = note_value(details, "evidence_artifact=")
        if value:
            return Path(value)
    modality = status.get("modality")
    if isinstance(modality, str) and modality:
        value = note_value(notes, f"backend_evidence_artifact[{modality}]=")
        if value:
            return Path(value)
    return None


def load_json_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def attach_evidence_artifacts(model: dict) -> dict:
    notes = list(model.get("notes", []))
    evidence_dir = note_value(notes, "backend_evidence_dir=")
    artifacts: list[dict] = []
    for status in model.get("statuses", []):
        if not isinstance(status, dict):
            continue
        artifact_path = evidence_artifact_path(status, notes)
        if artifact_path is None:
            continue
        artifact = load_json_file(artifact_path)
        artifacts.append(
            {
                "modality": status.get("modality"),
                "artifact_path": str(artifact_path),
                "artifact_present": artifact is not None,
                "baseline": (artifact or {}).get("baseline"),
                "execution_path": (artifact or {}).get("execution_path"),
                "source": (artifact or {}).get("source"),
                "readiness": (artifact or {}).get("readiness"),
                "release_grade_backend_id": (artifact or {}).get("release_grade_backend_id")
                or (artifact or {}).get("release_grade_backend"),
                "release_grade_backend_origin": (artifact or {}).get("release_grade_backend_origin"),
                "release_grade_backend_stack": (artifact or {}).get("release_grade_backend_stack"),
                "contract_kind": (artifact or {}).get("contract_kind"),
                "state_refs": list((artifact or {}).get("state_refs", [])),
                "probe": (artifact or {}).get("probe"),
                "baseline_payload": (artifact or {}).get("baseline_payload"),
                "payload": artifact,
            }
        )
    result = dict(model)
    result["evidence_artifacts"] = artifacts
    result["evidence_dir"] = evidence_dir
    return result


def render(model: dict | None) -> str:
    if model is None:
        return "no device backend state"

    lines: list[str] = []
    updated_at = model.get("updated_at")
    if updated_at:
        lines.append(f"updated_at: {updated_at}")
    backend_summary = model.get("backend_summary") or {}
    if isinstance(backend_summary, dict) and backend_summary:
        lines.append(
            "summary: "
            f"{backend_summary.get('overall_status', 'unknown')} "
            f"statuses={backend_summary.get('status_count', 0)} "
            f"attention={backend_summary.get('attention_count', 0)}"
        )
    for status in model.get("statuses", []):
        details = ", ".join(status.get("details", []))
        line = (
            f"- {status['modality']}: {status['backend']} "
            f"[{status['readiness']}] available={status['available']}"
        )
        if details:
            line = f"{line} details={details}"
        lines.append(line)
    for adapter in model.get("adapters", []):
        lines.append(
            f"adapter: {adapter['modality']} -> {adapter['adapter_id']} [{adapter['execution_path']}]"
        )
    ui_tree_snapshot = model.get("ui_tree_snapshot")
    if isinstance(ui_tree_snapshot, dict):
        focus = ui_tree_snapshot.get("focus_name") or ui_tree_snapshot.get("focus_node") or "-"
        lines.append(
            "ui_tree: "
            f"{ui_tree_snapshot.get('snapshot_id', '-')} "
            f"[{ui_tree_snapshot.get('capture_mode', 'unknown')}] "
            f"applications={ui_tree_snapshot.get('application_count', 0)} "
            f"focus={focus}"
        )
    for row in model.get("ui_tree_support_matrix", []):
        lines.append(
            "ui_tree_matrix: "
            f"{row.get('environment_id', '-')} "
            f"[{row.get('readiness', 'unknown')}] "
            f"available={row.get('available')}"
        )
    evidence_dir = model.get("evidence_dir")
    if evidence_dir:
        lines.append(f"evidence_dir: {evidence_dir}")
    for artifact in model.get("evidence_artifacts", []):
        state_refs = ",".join(artifact.get("state_refs", []))
        lines.append(
            "evidence: "
            f"{artifact.get('modality') or '-'} "
            f"backend_id={artifact.get('release_grade_backend_id') or '-'} "
            f"baseline={artifact.get('baseline') or 'unknown'} "
            f"origin={artifact.get('release_grade_backend_origin') or '-'} "
            f"stack={artifact.get('release_grade_backend_stack') or '-'} "
            f"contract={artifact.get('contract_kind') or '-'} "
            f"path={artifact.get('artifact_path')} "
            f"source={artifact.get('source') or '-'} "
            f"state_refs={state_refs or '-'}"
        )
    for note in model.get("notes", []):
        lines.append(f"note: {note}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOS device backend status prototype")
    parser.add_argument("--path", type=Path, default=default_backend_state())
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    print(render(load_model(args.path, args.fixture, args.socket)))


