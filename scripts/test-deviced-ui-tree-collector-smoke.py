#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COLLECTOR = ROOT / "aios/services/deviced/runtime/ui_tree_atspi_snapshot.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aios-ui-tree-collector-") as temp_dir:
        temp_root = Path(temp_dir)
        fixture_path = temp_root / "ui-tree-fixture.json"
        state_output_path = temp_root / "ui-tree-state.json"
        fixture_path.write_text(
            json.dumps(
                {
                    "snapshot_id": "fixture-tree-1",
                    "applications": [
                        {
                            "node_id": "desktop-0/app-0",
                            "name": "AIOS Shell",
                            "role": "application",
                            "states": ["active"],
                            "children": [
                                {
                                    "node_id": "desktop-0/app-0/0",
                                    "name": "Approve",
                                    "role": "push button",
                                    "states": ["focused"],
                                }
                            ],
                        }
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(COLLECTOR),
                "--fixture",
                str(fixture_path),
                "--state-output",
                str(state_output_path),
                "--json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        require(payload["available"] is True, "collector envelope should be available")
        require(payload["readiness"] == "native-live", "collector readiness mismatch")
        require(payload["source"] == "atspi-live-collector", "collector source mismatch")
        require("collector=fixture" in payload["details"], "collector detail missing")
        snapshot = payload["payload"]
        require(snapshot["snapshot_id"] == "fixture-tree-1", "snapshot id mismatch")
        require(snapshot["backend"] == "at-spi", "snapshot backend mismatch")
        require(snapshot["collector"] == "fixture", "snapshot collector mismatch")
        require(snapshot["application_count"] == 1, "snapshot application count mismatch")
        require(snapshot["node_count"] == 2, "snapshot node count mismatch")
        require(snapshot["focus_node"] == "desktop-0/app-0/0", "focus inference mismatch")
        require(state_output_path.exists(), "collector should write state output")
        persisted = json.loads(state_output_path.read_text())
        require(persisted["collector"] == "fixture", "persisted snapshot mismatch")

        raw_completed = subprocess.run(
            [
                sys.executable,
                str(COLLECTOR),
                "--fixture",
                str(fixture_path),
                "--raw",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        raw_snapshot = json.loads(raw_completed.stdout)
        require(raw_snapshot["snapshot_id"] == "fixture-tree-1", "raw snapshot mismatch")
        print("deviced ui_tree collector smoke passed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
