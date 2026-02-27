#!/usr/bin/env python3
"""
Task queue CRUD CLI for the HOPS research orchestration framework.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict, get_args

DATA_DIR = Path(__file__).parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"

TaskType = Literal["github_sync", "web_search", "research_paper", "compile_entry", "user_input"]
TaskStatus = Literal["pending", "in_progress", "completed", "failed", "blocked"]

VALID_TYPES: frozenset[str] = frozenset(get_args(TaskType))
VALID_STATUSES: frozenset[str] = frozenset(get_args(TaskStatus))

DEFAULT_PRIORITIES: dict[TaskType, int] = {
    "user_input": 10,
    "research_paper": 6,
    "github_sync": 5,
    "web_search": 5,
    "compile_entry": 4,
}


class Task(TypedDict):
    id: str
    type: TaskType
    status: TaskStatus
    priority: int
    parent_id: str | None
    created_at: str
    updated_at: str
    data: dict[str, Any]
    result: dict[str, Any] | None


class TaskStore(TypedDict):
    tasks: list[Task]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_tasks() -> TaskStore:
    if not TASKS_FILE.exists():
        return {"tasks": []}
    with open(TASKS_FILE) as f:
        return json.load(f)


def save_tasks(data: TaskStore) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def next_id(tasks: list[Task]) -> str:
    if not tasks:
        return "t-001"
    nums = []
    for t in tasks:
        tid = t.get("id", "")
        if tid.startswith("t-") and tid[2:].isdigit():
            nums.append(int(tid[2:]))
    if not nums:
        return "t-001"
    return f"t-{max(nums) + 1:03d}"


def out(obj: object) -> None:
    print(json.dumps(obj, indent=2))


# ── Subcommands ────────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> None:
    data = load_tasks()
    tasks = data["tasks"]
    if args.status:
        tasks = [t for t in tasks if t.get("status") == args.status]
    if args.type:
        tasks = [t for t in tasks if t.get("type") == args.type]
    out(tasks)


def cmd_next(args: argparse.Namespace) -> None:
    data = load_tasks()
    candidates = [t for t in data["tasks"] if t.get("status") == "pending"]
    if args.type:
        candidates = [t for t in candidates if t.get("type") == args.type]
    if not candidates:
        out({})
        return
    best = max(candidates, key=lambda t: (t.get("priority", 5), t.get("id", "")))
    out(best)


def cmd_add(args: argparse.Namespace) -> None:
    try:
        task_data = json.loads(args.data)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --data: {e}", file=sys.stderr)
        sys.exit(1)

    if args.type not in VALID_TYPES:
        print(f"Error: unknown type '{args.type}'. Valid: {sorted(VALID_TYPES)}", file=sys.stderr)
        sys.exit(1)

    data = load_tasks()
    tid = next_id(data["tasks"])
    priority = args.priority if args.priority is not None else DEFAULT_PRIORITIES.get(args.type, 5)
    ts = now_iso()

    task: Task = {
        "id": tid,
        "type": args.type,
        "status": "pending",
        "priority": priority,
        "parent_id": args.parent_id,
        "created_at": ts,
        "updated_at": ts,
        "data": task_data,
        "result": None,
    }
    data["tasks"].append(task)
    save_tasks(data)
    out({"id": tid})


def cmd_update(args: argparse.Namespace) -> None:
    if args.status not in VALID_STATUSES:
        print(f"Error: unknown status '{args.status}'. Valid: {sorted(VALID_STATUSES)}", file=sys.stderr)
        sys.exit(1)

    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == args.id:
            task["status"] = args.status
            task["updated_at"] = now_iso()
            save_tasks(data)
            out({"ok": True})
            return

    print(f"Error: task '{args.id}' not found", file=sys.stderr)
    sys.exit(1)


def cmd_set_result(args: argparse.Namespace) -> None:
    try:
        result = json.loads(args.result)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --result: {e}", file=sys.stderr)
        sys.exit(1)

    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == args.id:
            task["result"] = result
            task["updated_at"] = now_iso()
            save_tasks(data)
            out({"ok": True})
            return

    print(f"Error: task '{args.id}' not found", file=sys.stderr)
    sys.exit(1)


def cmd_add_subtasks(args: argparse.Namespace) -> None:
    try:
        subtasks_raw = json.loads(args.tasks)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --tasks: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(subtasks_raw, list):
        print("Error: --tasks must be a JSON array", file=sys.stderr)
        sys.exit(1)

    data = load_tasks()
    ids = []
    ts = now_iso()

    for st in subtasks_raw:
        task_type = st.get("type")
        if task_type not in VALID_TYPES:
            print(f"Error: unknown type '{task_type}' in subtask", file=sys.stderr)
            sys.exit(1)
        tid = next_id(data["tasks"])
        priority = st.get("priority", DEFAULT_PRIORITIES.get(task_type, 5))
        task: Task = {
            "id": tid,
            "type": task_type,
            "status": "pending",
            "priority": priority,
            "parent_id": args.parent_id,
            "created_at": ts,
            "updated_at": ts,
            "data": st.get("data", {}),
            "result": None,
        }
        data["tasks"].append(task)
        ids.append(tid)

    save_tasks(data)
    out({"ids": ids})


def cmd_get(args: argparse.Namespace) -> None:
    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == args.id:
            out(task)
            return
    print(f"Error: task '{args.id}' not found", file=sys.stderr)
    sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Task queue CRUD CLI for the HOPS research orchestration framework")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List tasks")
    p_list.add_argument("--status", help="Filter by status")
    p_list.add_argument("--type", help="Filter by type")

    # next
    p_next = sub.add_parser("next", help="Get next pending task of the highest priority")
    p_next.add_argument("--type", help="Filter by type")

    # add
    p_add = sub.add_parser("add", help="Add a new task")
    p_add.add_argument("--type", required=True, help="Task type")
    p_add.add_argument("--data", required=True, help="Task data as JSON")
    p_add.add_argument("--priority", type=int, help="Priority 1–10")
    p_add.add_argument("--parent-id", help="Parent task ID")

    # update
    p_update = sub.add_parser("update", help="Update task status")
    p_update.add_argument("id", help="Task ID")
    p_update.add_argument("--status", required=True, help="New status")

    # set-result
    p_result = sub.add_parser("set-result", help="Set task result")
    p_result.add_argument("id", help="Task ID")
    p_result.add_argument("--result", required=True, help="Result as JSON")

    # add-subtasks
    p_sub = sub.add_parser("add-subtasks", help="Add multiple subtasks for a parent")
    p_sub.add_argument("parent_id", help="Parent task ID")
    p_sub.add_argument("--tasks", required=True, help="Array of subtask objects as JSON")

    # get
    p_get = sub.add_parser("get", help="Get a single task by ID")
    p_get.add_argument("id", help="Task ID")

    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "next": cmd_next,
        "add": cmd_add,
        "update": cmd_update,
        "set-result": cmd_set_result,
        "add-subtasks": cmd_add_subtasks,
        "get": cmd_get,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
