#!/usr/bin/env python3
"""
Task queue CRUD CLI for the HOPS research orchestration.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, get_args

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

DEFAULT_MAX_ATTEMPTS: dict[str, int] = {
    "github_sync": 2,
    "web_search": 2,
    "research_paper": 2,
    "compile_entry": 1,
    "user_input": 1,
}


class GithubSyncData(TypedDict):
    repo: str


class WebSearchData(TypedDict):
    topic: str
    description: str
    github_issue_number: int
    github_issue_url: str
    github_labels: list[str]
    max_papers: int


class ResearchPaperData(TypedDict):
    paper_id: str
    title: str
    doi: str
    url: str
    reason: str


class CompileEntryData(TypedDict):
    paper_id: str
    target: Literal["parameter", "relation"]
    parameter_name: NotRequired[str]
    relation_from: NotRequired[str]
    relation_to: NotRequired[str]


class UserInputData(TypedDict):
    question: str
    context: NotRequired[str]


TaskData = GithubSyncData | WebSearchData | ResearchPaperData | CompileEntryData | UserInputData


class Task(TypedDict):
    id: str
    type: TaskType
    title: str
    status: TaskStatus
    priority: int
    parent_id: str | None
    successor_ids: list[str]
    blocked_by: list[str]
    attempt: int
    max_attempts: int
    created_at: str
    started_at: str | None
    updated_at: str
    data: TaskData
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


def derive_title(task_type: str, data: dict[str, Any]) -> str:
    if task_type == "github_sync":
        return f"Sync: {data.get('repo', '')}"
    elif task_type == "web_search":
        return f"Search: {data.get('topic', '')}"
    elif task_type == "research_paper":
        return f"Research: {data.get('title', '')}"
    elif task_type == "compile_entry":
        target = data.get("target", "")
        if target == "parameter":
            return f"Compile parameter: {data.get('parameter_name', '')}"
        else:
            return f"Compile relation: {data.get('relation_from', '')} \u2192 {data.get('relation_to', '')}"
    elif task_type == "user_input":
        question = data.get("question", "")
        return f"Input: {question[:60]}"
    return ""


def is_unblocked(task: Task, completed_ids: set[str]) -> bool:
    blocked_by = task.get("blocked_by", [])
    return not blocked_by or all(bid in completed_ids for bid in blocked_by)


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
    completed_ids = {t["id"] for t in data["tasks"] if t.get("status") == "completed"}
    candidates = [
        t for t in data["tasks"]
        if t.get("status") == "pending" and is_unblocked(t, completed_ids)
    ]
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

    blocked_by = []
    if args.blocked_by:
        try:
            blocked_by = json.loads(args.blocked_by)
            if not isinstance(blocked_by, list):
                raise ValueError("must be array")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: invalid JSON for --blocked-by: {e}", file=sys.stderr)
            sys.exit(1)

    data = load_tasks()
    tid = next_id(data["tasks"])
    priority = args.priority if args.priority is not None else DEFAULT_PRIORITIES.get(args.type, 5)
    max_attempts = args.max_attempts if args.max_attempts is not None else DEFAULT_MAX_ATTEMPTS.get(args.type, 1)
    title = args.title if args.title else derive_title(args.type, task_data)
    ts = now_iso()

    task: Task = {
        "id": tid,
        "type": args.type,
        "title": title,
        "status": "pending",
        "priority": priority,
        "parent_id": args.parent_id,
        "successor_ids": [],
        "blocked_by": blocked_by,
        "attempt": 1,
        "max_attempts": max_attempts,
        "created_at": ts,
        "started_at": None,
        "updated_at": ts,
        "data": task_data,
        "result": None,
    }
    data["tasks"].append(task)

    if args.parent_id:
        for t in data["tasks"]:
            if t["id"] == args.parent_id:
                t.setdefault("successor_ids", []).append(tid)
                t["updated_at"] = ts
                break

    save_tasks(data)
    out({"id": tid})


def cmd_update(args: argparse.Namespace) -> None:
    if args.status not in VALID_STATUSES:
        print(f"Error: unknown status '{args.status}'. Valid: {sorted(VALID_STATUSES)}", file=sys.stderr)
        sys.exit(1)

    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == args.id:
            old_status = task.get("status")
            task["status"] = args.status
            ts = now_iso()
            task["updated_at"] = ts
            if args.status == "in_progress" and old_status != "in_progress":
                task["started_at"] = ts
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

    parent_task = None
    for t in data["tasks"]:
        if t["id"] == args.parent_id:
            parent_task = t
            break
    if parent_task is None:
        print(f"Error: parent task '{args.parent_id}' not found", file=sys.stderr)
        sys.exit(1)

    ids = []
    ts = now_iso()

    for st in subtasks_raw:
        task_type = st.get("type")
        if task_type not in VALID_TYPES:
            print(f"Error: unknown type '{task_type}' in subtask", file=sys.stderr)
            sys.exit(1)
        tid = next_id(data["tasks"])
        priority = st.get("priority", DEFAULT_PRIORITIES.get(task_type, 5))
        max_attempts = st.get("max_attempts", DEFAULT_MAX_ATTEMPTS.get(task_type, 1))
        subtask_data = st.get("data", {})
        title = st.get("title") or derive_title(task_type, subtask_data)
        blocked_by = st.get("blocked_by", [])
        task: Task = {
            "id": tid,
            "type": task_type,
            "title": title,
            "status": "pending",
            "priority": priority,
            "parent_id": args.parent_id,
            "successor_ids": [],
            "blocked_by": blocked_by,
            "attempt": 1,
            "max_attempts": max_attempts,
            "created_at": ts,
            "started_at": None,
            "updated_at": ts,
            "data": subtask_data,
            "result": None,
        }
        data["tasks"].append(task)
        ids.append(tid)

    parent_task.setdefault("successor_ids", []).extend(ids)
    parent_task["updated_at"] = ts
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


def cmd_complete(args: argparse.Namespace) -> None:
    try: 
        result = json.loads(args.result)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --result: {e}", file=sys.stderr)
        sys.exit(1)

    status = args.status if args.status else "completed"
    if status not in ("completed", "failed"):
        print("Error: --status must be 'completed' or 'failed'", file=sys.stderr)
        sys.exit(1)

    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == args.id:
            task["result"] = result
            task["status"] = status
            task["updated_at"] = now_iso()
            save_tasks(data)
            out({"ok": True})
            return

    print(f"Error: task '{args.id}' not found", file=sys.stderr)
    sys.exit(1)


def cmd_retry(args: argparse.Namespace) -> None:
    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == args.id:
            if task.get("status") != "failed":
                print(f"Error: task '{args.id}' is not failed (status={task.get('status')})", file=sys.stderr)
                sys.exit(1)
            attempt = task.get("attempt", 1)
            max_attempts = task.get("max_attempts", 1)
            if attempt >= max_attempts:
                print(f"Error: task '{args.id}' has reached max_attempts ({max_attempts})", file=sys.stderr)
                sys.exit(1)
            task["attempt"] = attempt + 1
            task["status"] = "pending"
            task["result"] = None
            task["started_at"] = None
            task["updated_at"] = now_iso()
            save_tasks(data)
            out({"ok": True, "attempt": task["attempt"], "max_attempts": max_attempts})
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
    p_add.add_argument("--priority", type=int, help="Priority 1-10")
    p_add.add_argument("--parent-id", help="Parent task ID")
    p_add.add_argument("--title", help="Task title (auto-derived if omitted)")
    p_add.add_argument("--blocked-by", help="JSON array of blocking task IDs")
    p_add.add_argument("--max-attempts", type=int, help="Max retry attempts")

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

    # complete
    p_complete = sub.add_parser("complete", help="Atomically set result and status")
    p_complete.add_argument("id", help="Task ID")
    p_complete.add_argument("--result", required=True, help="Result as JSON")
    p_complete.add_argument("--status", default="completed", help="Final status (completed|failed)")

    # retry
    p_retry = sub.add_parser("retry", help="Re-queue a failed task")
    p_retry.add_argument("id", help="Task ID")

    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "next": cmd_next,
        "add": cmd_add,
        "update": cmd_update,
        "set-result": cmd_set_result,
        "add-subtasks": cmd_add_subtasks,
        "get": cmd_get,
        "complete": cmd_complete,
        "retry": cmd_retry,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
