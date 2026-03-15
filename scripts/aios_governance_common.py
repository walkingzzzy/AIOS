#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
RELEASE_CHECKLIST = ROOT / "docs" / "RELEASE_CHECKLIST.md"
RELEASE_GATE_RULES_START = "<!-- aios-release-gate-rules:start -->"
RELEASE_GATE_RULES_END = "<!-- aios-release-gate-rules:end -->"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def get_nested_field(payload: Any, field: str) -> Any:
    current = payload
    for segment in field.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return None
    return current


def parse_release_gate_rules(checklist_path: Path = RELEASE_CHECKLIST) -> dict[str, Any]:
    text = checklist_path.read_text()
    if RELEASE_GATE_RULES_START not in text or RELEASE_GATE_RULES_END not in text:
        raise RuntimeError(f"release gate rules markers missing in {checklist_path}")

    block = text.split(RELEASE_GATE_RULES_START, 1)[1].split(RELEASE_GATE_RULES_END, 1)[0].strip()
    if block.startswith("```yaml"):
        block = block.removeprefix("```yaml").strip()
    elif block.startswith("```yml"):
        block = block.removeprefix("```yml").strip()
    if block.endswith("```"):
        block = block[:-3].strip()

    payload = yaml.safe_load(block)
    if not isinstance(payload, dict):
        raise RuntimeError("release gate rules block must decode to a mapping")
    return payload
