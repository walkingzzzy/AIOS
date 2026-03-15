#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MASTER_DOC = ROOT / "docs/system-development/21-完整任务清单.md"
BOARD_DOC = ROOT / "docs/system-development/22-执行任务看板.md"
TASKS_DIR = ROOT / "aios" / "tasks"
MASTER_OUTPUT = TASKS_DIR / "master-task-list.yaml"
BOARD_OUTPUT = TASKS_DIR / "execution-board.yaml"

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.*)$")
SUBSECTION_RE = re.compile(r"^###\s+(.*)$")
PHASE_RE = re.compile(r"Phase\s+(\d+)")
TASK_ROW_RE = re.compile(r"^`([A-Z0-9-]+)`$")
QUEUE_ITEM_RE = re.compile(r"^\d+\.\s+`([^`]+)`\s+(.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync AIOS task metadata from markdown planning docs")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate generated content against committed outputs without rewriting files",
    )
    return parser.parse_args()


def clean_cell(value: str) -> str:
    return value.strip()


def unwrap_backticks(value: str) -> str:
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        return value[1:-1].strip()
    return value


def split_row(line: str) -> list[str]:
    return [clean_cell(cell) for cell in line.strip().strip("|").split("|")]


def is_separator_row(columns: list[str]) -> bool:
    if not columns:
        return False
    allowed = {"-", ":"}
    return all(cell and set(cell) <= allowed for cell in columns)


def phase_metadata(section_title: str) -> tuple[str, str]:
    match = PHASE_RE.search(section_title)
    if match:
        phase_number = int(match.group(1))
        track = section_title.split("·", 1)[1].strip() if "·" in section_title else section_title
        return f"phase{phase_number}", track
    if "跨阶段持续任务" in section_title:
        return "cross-stage", "跨阶段持续任务"
    return "reference", section_title


def parse_master_doc(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    lines = path.read_text().splitlines()
    current_section = ""
    current_section_number = ""
    in_task_table = False
    tasks: list[dict[str, Any]] = []
    priority_order: list[str] = []

    for line in lines:
        section_match = SECTION_RE.match(line)
        if section_match:
            current_section_number = section_match.group(1)
            current_section = section_match.group(2).strip()
            in_task_table = False
            continue

        if current_section_number == "23" and line.strip():
            queue_match = QUEUE_ITEM_RE.match(line.strip())
            if queue_match:
                priority_order.append(queue_match.group(1))
            continue

        if line.startswith("| Task ID |"):
            in_task_table = True
            continue
        if in_task_table and line.startswith("|"):
            columns = split_row(line)
            if is_separator_row(columns):
                continue
            if len(columns) < 5:
                continue
            task_id = unwrap_backticks(columns[0])
            if not TASK_ROW_RE.match(f"`{task_id}`"):
                continue
            phase_id, track = phase_metadata(current_section)
            tasks.append(
                {
                    "task_id": task_id,
                    "owner_role": unwrap_backticks(columns[1]),
                    "status": unwrap_backticks(columns[2]),
                    "summary": columns[3],
                    "deliverable": columns[4],
                    "phase_id": phase_id,
                    "track": track,
                    "source_doc": path.relative_to(ROOT).as_posix(),
                    "source_section": current_section,
                }
            )
            continue
        if in_task_table and not line.startswith("|"):
            in_task_table = False

    priority_rank = {task_id: index + 1 for index, task_id in enumerate(priority_order)}
    for task in tasks:
        if task["task_id"] in priority_rank:
            task["priority_rank"] = priority_rank[task["task_id"]]

    return tasks, priority_order


def parse_markdown_table(lines: list[str], start_index: int) -> tuple[list[dict[str, str]], int]:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    index = start_index

    while index < len(lines):
        line = lines[index]
        if not line.startswith("|"):
            break
        columns = split_row(line)
        if header is None:
            header = [unwrap_backticks(column) for column in columns]
        elif is_separator_row(columns):
            pass
        else:
            row = {
                header[position]: unwrap_backticks(value)
                for position, value in enumerate(columns)
                if position < len(header)
            }
            rows.append(row)
        index += 1

    return rows, index


def parse_board_doc(path: Path, known_task_ids: set[str]) -> tuple[dict[str, Any], list[str]]:
    lines = path.read_text().splitlines()
    current_section = ""
    current_section_number = ""
    current_subsection = ""
    unknown_task_ids: list[str] = []
    current_streams: list[dict[str, str]] = []
    blockers: list[dict[str, str]] = []
    recent_completed: list[str] = []
    queue: dict[str, list[dict[str, Any]]] = {"now": [], "next": []}

    index = 0
    while index < len(lines):
        line = lines[index]
        section_match = SECTION_RE.match(line)
        if section_match:
            current_section_number = section_match.group(1)
            current_section = section_match.group(2).strip()
            current_subsection = ""
            index += 1
            continue

        subsection_match = SUBSECTION_RE.match(line)
        if subsection_match:
            current_subsection = subsection_match.group(1).strip()
            index += 1
            continue

        if current_section_number == "3" and line.startswith("| 顺位 |"):
            rows, index = parse_markdown_table(lines, index)
            current_streams = [
                {
                    "order": row["顺位"],
                    "stream": row["主线"],
                    "status": row["当前状态"],
                    "next_milestone": row["下一里程碑"],
                }
                for row in rows
            ]
            continue

        if current_section_number == "4" and current_subsection in {"Now", "Next"}:
            queue_key = current_subsection.lower()
            item_match = QUEUE_ITEM_RE.match(line.strip())
            if item_match:
                task_id = item_match.group(1)
                queue[queue_key].append(
                    {
                        "task_id": task_id,
                        "summary": item_match.group(2).strip(),
                    }
                )
                if task_id not in known_task_ids:
                    unknown_task_ids.append(task_id)
            index += 1
            continue

        if current_section_number == "5" and line.startswith("| 阻塞 |"):
            rows, index = parse_markdown_table(lines, index)
            blockers = [
                {
                    "blocker": row["阻塞"],
                    "impact": row["影响"],
                    "mitigation": row["当前处理方式"],
                }
                for row in rows
            ]
            continue

        if current_section_number == "6" and line.strip().startswith("- "):
            recent_completed.append(line.strip()[2:].strip())

        index += 1

    return (
        {
            "source_doc": path.relative_to(ROOT).as_posix(),
            "current_streams": current_streams,
            "queue": queue,
            "blockers": blockers,
            "recent_completed": recent_completed,
        },
        unknown_task_ids,
    )


def summarize_tasks(tasks: list[dict[str, Any]], priority_order: list[str]) -> dict[str, Any]:
    by_status = Counter(task["status"] for task in tasks)
    by_owner = Counter(task["owner_role"] for task in tasks)
    by_phase = Counter(task["phase_id"] for task in tasks)

    return {
        "total_tasks": len(tasks),
        "statuses": dict(sorted(by_status.items())),
        "owner_roles": dict(sorted(by_owner.items())),
        "phases": dict(sorted(by_phase.items())),
        "priority_backlog_size": len(priority_order),
    }


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def dump_yaml(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent

    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(dump_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(item)}")
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines = []
        for item in value:
            if isinstance(item, dict):
                first = True
                for key, nested in item.items():
                    if first:
                        if isinstance(nested, (dict, list)):
                            lines.append(f"{prefix}- {key}:")
                            lines.extend(dump_yaml(nested, indent + 4))
                        else:
                            lines.append(f"{prefix}- {key}: {yaml_scalar(nested)}")
                        first = False
                        continue
                    if isinstance(nested, (dict, list)):
                        lines.append(f"{prefix}  {key}:")
                        lines.extend(dump_yaml(nested, indent + 4))
                    else:
                        lines.append(f"{prefix}  {key}: {yaml_scalar(nested)}")
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(dump_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
        return lines

    return [f"{prefix}{yaml_scalar(value)}"]


def render_yaml(payload: dict[str, Any]) -> str:
    return "\n".join(dump_yaml(payload)) + "\n"


def build_master_payload(tasks: list[dict[str, Any]], priority_order: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "source_docs": [
            MASTER_DOC.relative_to(ROOT).as_posix(),
        ],
        "summary": summarize_tasks(tasks, priority_order),
        "priority_queue": priority_order,
        "tasks": tasks,
    }


def build_board_payload(board: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        **board,
    }


def write_or_check(path: Path, content: str, check_only: bool) -> bool:
    if check_only:
        return path.exists() and path.read_text() == content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def main() -> int:
    args = parse_args()

    tasks, priority_order = parse_master_doc(MASTER_DOC)
    task_ids = {task["task_id"] for task in tasks}
    board, unknown_board_task_ids = parse_board_doc(BOARD_DOC, task_ids)

    unknown_priority_task_ids = [task_id for task_id in priority_order if task_id not in task_ids]
    errors = []
    if unknown_priority_task_ids:
        errors.append(
            "priority queue references unknown task IDs: "
            + ", ".join(sorted(unknown_priority_task_ids))
        )
    if unknown_board_task_ids:
        errors.append(
            "execution board references unknown task IDs: "
            + ", ".join(sorted(set(unknown_board_task_ids)))
        )
    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        return 1

    master_content = render_yaml(build_master_payload(tasks, priority_order))
    board_content = render_yaml(build_board_payload(board))

    master_ok = write_or_check(MASTER_OUTPUT, master_content, args.check)
    board_ok = write_or_check(BOARD_OUTPUT, board_content, args.check)

    if args.check and not (master_ok and board_ok):
        print("error: generated task metadata is out of date; run scripts/sync-aios-task-metadata.py", file=sys.stderr)
        return 1

    if not args.check:
        print(
            json.dumps(
                {
                    "master_task_list": MASTER_OUTPUT.relative_to(ROOT).as_posix(),
                    "execution_board": BOARD_OUTPUT.relative_to(ROOT).as_posix(),
                    "task_count": len(tasks),
                    "priority_queue_size": len(priority_order),
                    "board_now": len(board["queue"]["now"]),
                    "board_next": len(board["queue"]["next"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
