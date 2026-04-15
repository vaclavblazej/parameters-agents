"""
Task queue library for the HOPS research orchestration pipeline.
"""

from pydantic import BaseModel
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast, get_args

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

TaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]

VALID_TYPES: frozenset[str] = frozenset(REGISTRY.keys())
VALID_STATUSES: frozenset[str] = frozenset(get_args(TaskStatus))


def time_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AttemptInfo(BaseModel):
    current: int
    max: int


class TimeInfo(BaseModel):
    created: str
    started: str | None
    updated: str


class Task(BaseModel):
    id: int
    type: TaskType
    title: str
    status: TaskStatus
    priority: int
    parent_id: int | None
    children_ids: list[int]
    blocked_by: list[int]
    attempt: AttemptInfo
    time: TimeInfo
    data: TaskData
    result: dict[str, Any] | None


class TaskStore(BaseModel):
    version: int
    next_id: int
    time: TimeInfo
    tasks: list[Task]

    @classmethod
    def load(cls) -> TaskStore:
        ts = time_now()
        if not TASKS_FILE.exists():
            return TaskStore(version=1, next_id=1, time=TimeInfo(created=ts, started=None, updated=ts), tasks=[])
        try:
            with open(TASKS_FILE) as f:
                return TaskStore(**json.load(f))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Corrupt tasks file {TASKS_FILE}: {e}") from e
        except TypeError as e:
            raise SystemExit(f"Schema mismatch in {TASKS_FILE}: {e}") from e

    def save(self) -> None:
        self.time.updated = time_now()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = TASKS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self, f, indent=2)
            f.write("\n")
        tmp.rename(TASKS_FILE)  # atomic on POSIX


class TaskManager:
    def __init__(self):
        self.store = TaskStore.load()

    @staticmethod
    def is_unblocked(task: Task, completed_ids: set[str]) -> bool:
        blocked_by = task.blocked_by
        return not blocked_by or all(bid in completed_ids for bid in blocked_by)

    def get_next_task(self, task_type: str | None = None) -> Task | None:
        completed_ids = {t.id for t in self.store.tasks if t.status == "completed"}
        candidates = [
            t for t in self.store.tasks
            if t.status == "pending" and self.is_unblocked(t, completed_ids)
        ]
        if task_type:
            candidates = [t for t in candidates if t.type == task_type]
        if not candidates:
            return None
        return max(candidates, key=lambda t: (t.priority, -t.id))

    def _find_task(self, task_id: int) -> Task:
        for task in self.store.tasks:
            if task.id == task_id:
                return task
        raise KeyError(f"Task '{task_id}' not found")

    def get_task(self, task_id: int) -> Task | None:
        try:
            return self._find_task(task_id)
        except KeyError:
            return None

    def _make_task(
        self,
        tid: int,
        task_type: str,
        task_data: dict[str, Any],
        priority: int,
        parent_id: int | None,
        blocked_by: list[int],
        max_attempts: int,
        title: str,
        ts: str,
    ) -> Task:
        return {
            "id": tid,
            "type": cast(TaskType, task_type),
            "title": title,
            "status": "pending",
            "priority": priority,
            "parent_id": parent_id,
            "successor_ids": [],
            "blocked_by": blocked_by,
            "attempt": {"current": 1, "max": max_attempts},
            "time": {"created": ts, "started": None, "updated": ts},
            "data": cast(TaskData, task_data),
            "result": None,
        }

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

        tid = self.store.next_id
        self.store.next_id += 1
        resolved_priority = priority if priority is not None else default_priority(task_type)
        resolved_max_attempts = max_attempts if max_attempts is not None else default_max_attempts(task_type)
        resolved_title = title if title else derive_title(task_type, task_data)
        resolved_blocked_by = blocked_by if blocked_by is not None else []
        ts = time_now()

        task = self._make_task(
            tid=tid,
            task_type=task_type,
            task_data=task_data,
            priority=resolved_priority,
            parent_id=parent_id,
            blocked_by=resolved_blocked_by,
            max_attempts=resolved_max_attempts,
            title=resolved_title,
            ts=ts,
        )
        self.store.tasks.append(task)

        if parent_id:
            for t in self.store.tasks:
                if t.id == parent_id:
                    t.setdefault("successor_ids", []).append(tid)
                    t.time.updated = ts
                    break

        self.store.save()
        return tid

    def update_task_status(self, task_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown status '{status}'. Valid: {sorted(VALID_STATUSES)}")

        task = self._find_task(task_id)
        old_status = task.status
        task.status = cast(TaskStatus, status)
        ts = time_now()
        task.time.updated = ts
        if status == "running" and old_status != "running":
            task.time.started = ts
        self.store.save()

    def set_task_result(self, task_id: int, result: dict[str, Any]) -> None:
        task = self._find_task(task_id)
        task.result = result
        task.time.updated = time_now()
        self.store.save()

    def complete_task(self, task_id: int, result: dict[str, Any], status: str = "completed") -> None:
        if status not in ("completed", "failed"):
            raise ValueError("status must be 'completed' or 'failed'")
        task = self._find_task(task_id)
        task.result = result
        task.status = cast(TaskStatus, status)
        task.time.updated = time_now()
        self.store.save()

    def add_subtasks(self, parent_id: int, subtasks: list[dict[str, Any]]) -> list[int]:
        parent_task = self._find_task(parent_id)

        ids = []
        ts = time_now()

        for st in subtasks:
            task_type = st.type
            if task_type not in VALID_TYPES:
                raise ValueError(f"Unknown type '{task_type}' in subtask")
            tid = self.store.next_id
            self.store.next_id += 1
            priority = st.get("priority", default_priority(task_type))
            max_attempts = st.get("max_attempts", default_max_attempts(task_type))
            subtask_data = st.data
            title = st.get("title") or derive_title(task_type, subtask_data)
            blocked_by = st.blocked_by
            task = self._make_task(
                tid=tid,
                task_type=task_type,
                task_data=subtask_data,
                priority=priority,
                parent_id=parent_id,
                blocked_by=blocked_by,
                max_attempts=max_attempts,
                title=title,
                ts=ts,
            )
            self.store.tasks.append(task)
            ids.append(tid)

        parent_task.setdefault("successor_ids", []).extend(ids)
        parent_task.time.updated = ts
        self.store.save()
        return ids

    def retry_task(self, task_id: int) -> dict[str, Any]:
        task = self._find_task(task_id)
        if task.status != "failed":
            raise ValueError(f"Task '{task_id}' is not failed (status={task.status})")
        attempt_info = task.attempt
        current = attempt_info.current
        max_attempts = attempt_info.max
        if current >= max_attempts:
            raise ValueError(f"Task '{task_id}' has reached max_attempts ({max_attempts})")
        attempt_info.current = current + 1
        task.attempt = attempt_info
        task.status = "pending"
        task.result = None
        task.time.started = None
        task.time.updated = time_now()
        self.store.save()
        return {"attempt": task.attempt}

    def list_tasks(self, status: str | None = None, task_type: str | None = None) -> list[Task]:
        tasks = self.store.tasks
        if status:
            tasks = [t for t in tasks if t.status == status]
        if task_type:
            tasks = [t for t in tasks if t.type == task_type]
        return tasks
