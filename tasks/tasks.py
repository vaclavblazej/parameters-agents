"""
Task queue library for the HOPS research orchestration pipeline.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict, cast, get_args

from .task_types import (
    REGISTRY,
    CompileEntryData,
    GithubSyncData,
    ResearchPaperData,
    TaskData,
    UserInputData,
    WebSearchData,
    default_max_attempts,
    default_priority,
    derive_title,
)

DATA_DIR = Path(__file__).parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"

TaskType = Literal["github_sync", "web_search", "research_paper", "compile_entry", "user_input"]
TaskStatus = Literal["pending", "in_progress", "completed", "failed", "blocked"]

VALID_TYPES: frozenset[str] = frozenset(REGISTRY.keys())
VALID_STATUSES: frozenset[str] = frozenset(get_args(TaskStatus))


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


def is_unblocked(task: Task, completed_ids: set[str]) -> bool:
    blocked_by = task.get("blocked_by", [])
    return not blocked_by or all(bid in completed_ids for bid in blocked_by)


def get_next_task(task_type: str | None = None) -> Task | None:
    data = load_tasks()
    completed_ids = {t["id"] for t in data["tasks"] if t.get("status") == "completed"}
    candidates = [
        t for t in data["tasks"]
        if t.get("status") == "pending" and is_unblocked(t, completed_ids)
    ]
    if task_type:
        candidates = [t for t in candidates if t.get("type") == task_type]
    if not candidates:
        return None
    return max(candidates, key=lambda t: (t.get("priority", 5), t.get("id", "")))


def get_task(task_id: str) -> Task | None:
    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task
    return None


def add_task(
    task_type: str,
    task_data: dict[str, Any],
    priority: int | None = None,
    parent_id: str | None = None,
    title: str | None = None,
    blocked_by: list[str] | None = None,
    max_attempts: int | None = None,
) -> str:
    if task_type not in VALID_TYPES:
        raise ValueError(f"Unknown type '{task_type}'. Valid: {sorted(VALID_TYPES)}")

    data = load_tasks()
    tid = next_id(data["tasks"])
    resolved_priority = priority if priority is not None else default_priority(task_type)
    resolved_max_attempts = max_attempts if max_attempts is not None else default_max_attempts(task_type)
    resolved_title = title if title else derive_title(task_type, task_data)
    resolved_blocked_by = blocked_by if blocked_by is not None else []
    ts = now_iso()

    task: Task = {
        "id": tid,
        "type": cast(TaskType, task_type),
        "title": resolved_title,
        "status": "pending",
        "priority": resolved_priority,
        "parent_id": parent_id,
        "successor_ids": [],
        "blocked_by": resolved_blocked_by,
        "attempt": 1,
        "max_attempts": resolved_max_attempts,
        "created_at": ts,
        "started_at": None,
        "updated_at": ts,
        "data": cast(TaskData, task_data),
        "result": None,
    }
    data["tasks"].append(task)

    if parent_id:
        for t in data["tasks"]:
            if t["id"] == parent_id:
                t.setdefault("successor_ids", []).append(tid)
                t["updated_at"] = ts
                break

    save_tasks(data)
    return tid


def update_task_status(task_id: str, status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unknown status '{status}'. Valid: {sorted(VALID_STATUSES)}")

    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == task_id:
            old_status = task.get("status")
            task["status"] = cast(TaskStatus, status)
            ts = now_iso()
            task["updated_at"] = ts
            if status == "in_progress" and old_status != "in_progress":
                task["started_at"] = ts
            save_tasks(data)
            return

    raise KeyError(f"Task '{task_id}' not found")


def set_task_result(task_id: str, result: dict[str, Any]) -> None:
    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["result"] = result
            task["updated_at"] = now_iso()
            save_tasks(data)
            return
    raise KeyError(f"Task '{task_id}' not found")


def complete_task(task_id: str, result: dict[str, Any], status: str = "completed") -> None:
    if status not in ("completed", "failed"):
        raise ValueError("status must be 'completed' or 'failed'")
    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["result"] = result
            task["status"] = cast(TaskStatus, status)
            task["updated_at"] = now_iso()
            save_tasks(data)
            return
    raise KeyError(f"Task '{task_id}' not found")


def add_subtasks(parent_id: str, subtasks: list[dict[str, Any]]) -> list[str]:
    data = load_tasks()

    parent_task = None
    for t in data["tasks"]:
        if t["id"] == parent_id:
            parent_task = t
            break
    if parent_task is None:
        raise KeyError(f"Parent task '{parent_id}' not found")

    ids = []
    ts = now_iso()

    for st in subtasks:
        task_type = st.get("type")
        if task_type not in VALID_TYPES:
            raise ValueError(f"Unknown type '{task_type}' in subtask")
        tid = next_id(data["tasks"])
        priority = st.get("priority", default_priority(task_type))
        max_attempts = st.get("max_attempts", default_max_attempts(task_type))
        subtask_data = st.get("data", {})
        title = st.get("title") or derive_title(task_type, subtask_data)
        blocked_by = st.get("blocked_by", [])
        task: Task = {
            "id": tid,
            "type": cast(TaskType, task_type),
            "title": title,
            "status": "pending",
            "priority": priority,
            "parent_id": parent_id,
            "successor_ids": [],
            "blocked_by": blocked_by,
            "attempt": 1,
            "max_attempts": max_attempts,
            "created_at": ts,
            "started_at": None,
            "updated_at": ts,
            "data": cast(TaskData, subtask_data),
            "result": None,
        }
        data["tasks"].append(task)
        ids.append(tid)

    parent_task.setdefault("successor_ids", []).extend(ids)
    parent_task["updated_at"] = ts
    save_tasks(data)
    return ids


def retry_task(task_id: str) -> dict[str, Any]:
    data = load_tasks()
    for task in data["tasks"]:
        if task["id"] == task_id:
            if task.get("status") != "failed":
                raise ValueError(f"Task '{task_id}' is not failed (status={task.get('status')})")
            attempt = task.get("attempt", 1)
            max_attempts = task.get("max_attempts", 1)
            if attempt >= max_attempts:
                raise ValueError(f"Task '{task_id}' has reached max_attempts ({max_attempts})")
            task["attempt"] = attempt + 1
            task["status"] = "pending"
            task["result"] = None
            task["started_at"] = None
            task["updated_at"] = now_iso()
            save_tasks(data)
            return {"attempt": task["attempt"], "max_attempts": max_attempts}
    raise KeyError(f"Task '{task_id}' not found")


def list_tasks(status: str | None = None, task_type: str | None = None) -> list[Task]:
    data = load_tasks()
    tasks = data["tasks"]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if task_type:
        tasks = [t for t in tasks if t.get("type") == task_type]
    return tasks
