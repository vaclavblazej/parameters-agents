"""
Task queue library for the HOPS research orchestration pipeline.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict, cast, get_args

from .task_types import (
    REGISTRY,
    TaskData,
    TaskType,
    default_max_attempts,
    default_priority,
    derive_title,
)

DATA_DIR = Path(__file__).parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"

TaskStatus = Literal["pending", "in_progress", "completed", "failed", "blocked"]

VALID_TYPES: frozenset[str] = frozenset(REGISTRY.keys())
VALID_STATUSES: frozenset[str] = frozenset(get_args(TaskStatus))


def time_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Task(TypedDict):
    id: int
    type: TaskType
    title: str
    status: TaskStatus
    priority: int
    parent_id: int | None
    successor_ids: list[int]
    blocked_by: list[int]
    attempt: int
    max_attempts: int
    created_at: str
    started_at: str | None
    updated_at: str
    data: TaskData
    result: dict[str, Any] | None


class TaskStore(TypedDict):
    version: int
    next_id: int
    created_at: str
    updated_at: str
    tasks: list[Task]


def load_task_store() -> TaskStore:
    ts = time_now()
    if not TASKS_FILE.exists():
        return TaskStore(version=1, next_id=1, created_at=ts, updated_at=ts, tasks=[])
    with open(TASKS_FILE) as f:
        data = json.load(f)
    needs_save = False
    # absence of "version" means old bare-list format — migrate all metadata at once
    if "version" not in data:
        tasks = data.get("tasks", [])
        nums = [t["id"] for t in tasks if isinstance(t.get("id"), int)]
        data["version"] = 1
        data["next_id"] = max(nums) + 1 if nums else 1
        data["created_at"] = ts
        data["updated_at"] = ts
        needs_save = True
    store = TaskStore(
        version=data["version"],
        next_id=data["next_id"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        tasks=data.get("tasks", []),
    )
    if needs_save:
        save_task_store(store)
    return store


def save_task_store(store: TaskStore) -> None:
    store["updated_at"] = time_now()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(store, f, indent=2)
        f.write("\n")


class TaskManager:
    def __init__(self):
        self.store = load_task_store()

    def is_unblocked(self, task: Task, completed_ids: set[str]) -> bool:
        blocked_by = task.get("blocked_by", [])
        return not blocked_by or all(bid in completed_ids for bid in blocked_by)

    def get_next_task(self, task_type: str | None = None) -> Task | None:
        completed_ids = {t["id"] for t in self.store["tasks"] if t.get("status") == "completed"}
        candidates = [
            t for t in self.store["tasks"]
            if t.get("status") == "pending" and self.is_unblocked(t, completed_ids)
        ]
        if task_type:
            candidates = [t for t in candidates if t.get("type") == task_type]
        if not candidates:
            return None
        return max(candidates, key=lambda t: (t.get("priority", 5), t.get("id", 0)))

    def get_task(self, task_id: int) -> Task | None:
        for task in self.store["tasks"]:
            if task["id"] == task_id:
                return task
        return None

    def add_task(
        self,
        task_type: str,
        task_data: dict[str, Any],
        priority: int | None = None,
        parent_id: int | None = None,
        title: str | None = None,
        blocked_by: list[int] | None = None,
        max_attempts: int | None = None,
    ) -> int:
        if task_type not in VALID_TYPES:
            raise ValueError(f"Unknown type '{task_type}'. Valid: {sorted(VALID_TYPES)}")

        tid = self.store["next_id"]
        self.store["next_id"] += 1
        resolved_priority = priority if priority is not None else default_priority(task_type)
        resolved_max_attempts = max_attempts if max_attempts is not None else default_max_attempts(task_type)
        resolved_title = title if title else derive_title(task_type, task_data)
        resolved_blocked_by = blocked_by if blocked_by is not None else []
        ts = time_now()

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
        self.store["tasks"].append(task)

        if parent_id:
            for t in self.store["tasks"]:
                if t["id"] == parent_id:
                    t.setdefault("successor_ids", []).append(tid)
                    t["updated_at"] = ts
                    break

        save_task_store(self.store)
        return tid

    def update_task_status(self, task_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown status '{status}'. Valid: {sorted(VALID_STATUSES)}")

        for task in self.store["tasks"]:
            if task["id"] == task_id:
                old_status = task.get("status")
                task["status"] = cast(TaskStatus, status)
                ts = time_now()
                task["updated_at"] = ts
                if status == "in_progress" and old_status != "in_progress":
                    task["started_at"] = ts
                save_task_store(self.store)
                return

        raise KeyError(f"Task '{task_id}' not found")

    def set_task_result(self, task_id: int, result: dict[str, Any]) -> None:
        for task in self.store["tasks"]:
            if task["id"] == task_id:
                task["result"] = result
                task["updated_at"] = time_now()
                save_task_store(self.store)
                return
        raise KeyError(f"Task '{task_id}' not found")

    def complete_task(self, task_id: int, result: dict[str, Any], status: str = "completed") -> None:
        if status not in ("completed", "failed"):
            raise ValueError("status must be 'completed' or 'failed'")
        for task in self.store["tasks"]:
            if task["id"] == task_id:
                task["result"] = result
                task["status"] = cast(TaskStatus, status)
                task["updated_at"] = time_now()
                save_task_store(self.store)
                return
        raise KeyError(f"Task '{task_id}' not found")

    def add_subtasks(self, parent_id: int, subtasks: list[dict[str, Any]]) -> list[int]:
        parent_task = None
        for t in self.store["tasks"]:
            if t["id"] == parent_id:
                parent_task = t
                break
        if parent_task is None:
            raise KeyError(f"Parent task '{parent_id}' not found")

        ids = []
        ts = time_now()

        for st in subtasks:
            task_type = st.get("type")
            if task_type not in VALID_TYPES:
                raise ValueError(f"Unknown type '{task_type}' in subtask")
            tid = self.store["next_id"]
            self.store["next_id"] += 1
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
            self.store["tasks"].append(task)
            ids.append(tid)

        parent_task.setdefault("successor_ids", []).extend(ids)
        parent_task["updated_at"] = ts
        save_task_store(self.store)
        return ids

    def retry_task(self, task_id: int) -> dict[str, Any]:
        for task in self.store["tasks"]:
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
                task["updated_at"] = time_now()
                save_task_store(self.store)
                return {"attempt": task["attempt"], "max_attempts": max_attempts}
        raise KeyError(f"Task '{task_id}' not found")

    def list_tasks(self, status: str | None = None, task_type: str | None = None) -> list[Task]:
        tasks = self.store["tasks"]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if task_type:
            tasks = [t for t in tasks if t.get("type") == task_type]
        return tasks
