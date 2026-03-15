#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a live ui_tree snapshot from AT-SPI or a fixture"
    )
    parser.add_argument("--fixture", type=Path, help="Load a snapshot fixture instead of AT-SPI")
    parser.add_argument(
        "--state-output",
        type=Path,
        help="Optional path to persist the normalized ui_tree snapshot",
    )
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--max-children", type=int, default=32)
    parser.add_argument("--max-nodes", type=int, default=256)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Emit the raw snapshot payload instead of a probe envelope",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Accepted for compatibility; output is JSON by default",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def count_nodes(nodes: list[dict[str, Any]]) -> int:
    total = 0
    stack = list(nodes)
    while stack:
        current = stack.pop()
        total += 1
        stack.extend(current.get("children") or [])
    return total


def find_focus(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    active_candidate: dict[str, Any] | None = None
    stack = list(reversed(nodes))
    while stack:
        current = stack.pop()
        states = {state.lower() for state in current.get("states") or []}
        if "focused" in states:
            return current
        if "active" in states and active_candidate is None:
            active_candidate = current
        stack.extend(reversed(current.get("children") or []))
    return active_candidate


def normalize_snapshot(snapshot: dict[str, Any], collector: str) -> dict[str, Any]:
    applications = snapshot.get("applications")
    if not isinstance(applications, list):
        applications = []

    focus = find_focus(applications)
    normalized = dict(snapshot)
    normalized.setdefault(
        "snapshot_id",
        f"atspi-live-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
    )
    normalized.setdefault("generated_at", now_iso())
    normalized.setdefault("source", "at-spi")
    normalized.setdefault("backend", "at-spi")
    normalized["collector"] = collector
    normalized["applications"] = applications
    normalized["application_count"] = len(applications)
    normalized["desktop_count"] = int(snapshot.get("desktop_count", 1 if applications else 0))
    normalized["node_count"] = int(snapshot.get("node_count", count_nodes(applications)))
    if focus is not None:
        normalized.setdefault("focus_node", focus.get("node_id"))
        normalized.setdefault("focus_name", focus.get("name"))
        normalized.setdefault("focus_role", focus.get("role"))
    else:
        normalized.setdefault("focus_node", snapshot.get("focus_node"))
        normalized.setdefault("focus_name", snapshot.get("focus_name"))
        normalized.setdefault("focus_role", snapshot.get("focus_role"))
    return normalized


def probe_envelope(snapshot: dict[str, Any], collector: str) -> dict[str, Any]:
    return {
        "available": True,
        "readiness": "native-live",
        "source": "atspi-live-collector",
        "details": [
            f"collector={collector}",
            f"application_count={snapshot['application_count']}",
            f"node_count={snapshot['node_count']}",
            f"desktop_count={snapshot['desktop_count']}",
        ],
        "payload": snapshot,
    }


def maybe_write_state(snapshot: dict[str, Any], explicit_path: Path | None) -> None:
    output_path = explicit_path
    if output_path is None:
        state_path = os.environ.get("AIOS_DEVICED_UI_TREE_STATE_PATH")
        output_path = Path(state_path) if state_path else None
    if output_path is None:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")


def safe_call(callback, default=None):
    try:
        value = callback()
    except Exception:
        return default
    return default if value is None else value


@dataclass
class AtspiCollector:
    max_depth: int
    max_children: int
    remaining_nodes: int

    def collect_accessible(
        self,
        accessible: Any,
        node_id: str,
        depth: int,
    ) -> dict[str, Any] | None:
        if self.remaining_nodes <= 0 or accessible is None:
            return None
        self.remaining_nodes -= 1

        name = safe_call(lambda: str(accessible.name).strip(), "") or None
        description = safe_call(lambda: str(accessible.description).strip(), "") or None
        role = safe_call(accessible.getRoleName, "unknown")
        child_count = int(safe_call(lambda: accessible.childCount, 0) or 0)
        states = self.read_states(accessible)

        node: dict[str, Any] = {
            "node_id": node_id,
            "name": name,
            "role": str(role),
            "states": states,
            "child_count": child_count,
        }
        if description:
            node["description"] = description

        if depth >= self.max_depth:
            node["truncated"] = child_count > 0
            return node

        children: list[dict[str, Any]] = []
        for index in range(min(child_count, self.max_children)):
            if self.remaining_nodes <= 0:
                node["truncated"] = True
                break
            child = safe_call(lambda index=index: accessible[index], None)
            child_node = self.collect_accessible(child, f"{node_id}/{index}", depth + 1)
            if child_node is not None:
                children.append(child_node)
        if children:
            node["children"] = children
        if child_count > self.max_children:
            node["truncated"] = True
        return node

    def read_states(self, accessible: Any) -> list[str]:
        state_set = safe_call(accessible.getState, None)
        if state_set is None:
            return []
        raw_states = safe_call(state_set.getStates, [])
        states: list[str] = []
        for state in raw_states or []:
            if hasattr(state, "real"):
                state = state.real
            label = safe_call(lambda state=state: state.value_name, None)
            if not label:
                label = str(state)
            label = str(label).split(".")[-1].lower()
            if label and label not in states:
                states.append(label)
        states.sort()
        return states


def collect_from_pyatspi(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if os.environ.get("AT_SPI_BUS_ADDRESS") is None:
        raise RuntimeError("AT_SPI_BUS_ADDRESS is not set")
    try:
        import pyatspi  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on host packages
        raise RuntimeError(f"pyatspi unavailable: {exc}") from exc

    collector = AtspiCollector(
        max_depth=max(args.max_depth, 1),
        max_children=max(args.max_children, 1),
        remaining_nodes=max(args.max_nodes, 1),
    )
    desktop_count = int(pyatspi.Registry.getDesktopCount())
    applications: list[dict[str, Any]] = []
    for desktop_index in range(desktop_count):
        desktop = pyatspi.Registry.getDesktop(desktop_index)
        child_count = int(safe_call(lambda: desktop.childCount, 0) or 0)
        for child_index in range(min(child_count, collector.max_children)):
            app = safe_call(lambda child_index=child_index: desktop[child_index], None)
            node = collector.collect_accessible(
                app,
                f"desktop-{desktop_index}/app-{child_index}",
                0,
            )
            if node is not None:
                applications.append(node)
            if collector.remaining_nodes <= 0:
                break
        if collector.remaining_nodes <= 0:
            break

    snapshot = normalize_snapshot(
        {
            "generated_at": now_iso(),
            "desktop_count": desktop_count,
            "applications": applications,
        },
        "pyatspi",
    )
    return snapshot, "pyatspi"


def collect_from_fixture(path: Path) -> tuple[dict[str, Any], str]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError("fixture must be a JSON object")
    snapshot = normalize_snapshot(value, "fixture")
    return snapshot, "fixture"


def emit_payload(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")


def main() -> int:
    args = parse_args()
    try:
        if args.fixture is not None:
            snapshot, collector = collect_from_fixture(args.fixture)
        else:
            snapshot, collector = collect_from_pyatspi(args)
        maybe_write_state(snapshot, args.state_output)
        if args.raw:
            emit_payload(snapshot)
        else:
            emit_payload(probe_envelope(snapshot, collector))
        return 0
    except Exception as exc:
        print(f"ui_tree collector failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
