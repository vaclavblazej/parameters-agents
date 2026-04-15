"""
Task queue library for the HOPS research orchestration pipeline.
"""

from pydantic import BaseModel
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast, get_args

from .task_types import (
    TaskData,
    TaskType,
)

DATA_DIR = Path(__file__).parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"

TaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]

def done(status: TaskStatus) -> bool:
    return status in ["completed", "failed"]

VALID_TYPES: frozenset[str] = frozenset(REGISTRY.keys())
VALID_STATUSES: frozenset[str] = frozenset(get_args(TaskStatus))


def time_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AttemptInfo(BaseModel):
    current: int
    max: int


class TimeInfo(BaseModel):
    created: str
    started: str | None = None
    updated: str


class Task(BaseModel):
    id: int
    type: TaskType
    title: str
    status: TaskStatus
    priority: int
    parent_id: int | None
    children_ids: list[int]
    waiting_for: list[int]
    attempt: AttemptInfo
    time: TimeInfo
    data: TaskData
    result: dict[str, Any] | None

    def __init__(
        self,
        tid: int,
        task_type: TaskType,
        task_data: TaskData,
        priority: int,
        parent_id: int | None,
        waiting_for: list[int],
        max_attempts: int,
        title: str,
        time_now: str,
    ) -> None:
        super().__init__(
            id=tid,
            type=task_type,
            title=title,
            status="pending",
            priority=priority,
            parent_id=parent_id,
            children_ids=[],
            waiting_for=waiting_for,
            attempt=AttemptInfo(current=1, max=max_attempts),
            time=TimeInfo(created=time_now, updated=time_now),
            data=task_data,
            result=None,
        )


class TaskStore(BaseModel):
    version: int
    next_id: int
    time: TimeInfo
    tasks: dict[int, Task]


class TaskManager:
    def __init__(self, file=TASKS_FILE):
        self.store = self.load()
        self.file = file

    def load(self) -> TaskStore:
        time_now = time_iso()
        if not self.file.exists():
            return TaskStore(version=1, next_id=1, time=TimeInfo(created=time_now, started=None, updated=time_now), tasks={})
        try:
            with open(self.file) as f:
                return TaskStore(**json.load(f))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Corrupt tasks file {self.file}: {e}") from e
        except TypeError as e:
            raise SystemExit(f"Schema mismatch in {self.file}: {e}") from e

    def save(self) -> None:
        self.store.time.updated = time_iso()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.store, f, indent=2)
            f.write("\n")
        tmp.rename(self.file)  # atomic on POSIX

    def is_unblocked(self, task: Task) -> bool:
        waiting_for = task.waiting_for
        if not waiting_for:
            return True
        for bid in waiting_for:
            btask = self.get_task(bid)
            if btask and not done(btask.status):
                return False
        return True

    def _get_task(self, task_id: int) -> Task:
        for task_id in self.store.tasks:
            return self.store.tasks[task_id]
        raise KeyError(f"Task '{task_id}' not found")

    def get_task(self, task_id: int) -> Task | None:
        try:
            return self._get_task(task_id)
        except KeyError:
            return None

    def get_next_task(self, task_type: TaskType | None = None) -> Task | None:
        candidates = [
            t for t in self.store.tasks.values()
            if t.status == "pending"
        ]
        if task_type:
            candidates = [t for t in candidates if t.type == task_type]
        if not candidates:
            return None
        return max(candidates, key=lambda t: (t.priority, -t.id))

    def _get_new_task_id(self) -> int:
        res = self.store.next_id
        self.store.next_id += 1
        return res

################################################################################
    def add_task(
        self,
        task_type: TaskType,
        task_data: TaskData,
        priority: int | None = None,
        parent_id: int | None = None,
        title: str | None = None,
        waiting_for: list[int] | None = None,
        max_attempts: int | None = None,
    ) -> int:
        resolved_priority = priority if priority is not None else default_priority(task_type)
        resolved_max_attempts = max_attempts if max_attempts is not None else default_max_attempts(task_type)
        resolved_title = title if title else derive_title(task_type, task_data)
        resolved_blocked_by = waiting_for if waiting_for is not None else []
        time_now = time_iso()

        task = Task(
            tid=self._get_new_task_id(),
            task_type=task_type,
            task_data=task_data,
            priority=resolved_priority,
            parent_id=parent_id,
            waiting_for=resolved_blocked_by,
            max_attempts=resolved_max_attempts,
            title=resolved_title,
            time_now=time_now,
        )
        self.store.tasks[task.id] = task

        if parent_id:
            for t in self.store.tasks.values():
                if t.id == parent_id:
                    t.children_ids.append(task.id)
                    t.time.updated = time_now
                    break

        self.save()
        return task.id

    def update_task_status(self, task_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown status '{status}'. Valid: {sorted(VALID_STATUSES)}")

        task = self._get_task(task_id)
        old_status = task.status
        task.status = cast(TaskStatus, status)
        time_now = time_iso()
        task.time.updated = time_now
        if status == "running" and old_status != "running":
            task.time.started = time_now
        self.save()

    def set_task_result(self, task_id: int, result: dict[str, Any]) -> None:
        task = self._get_task(task_id)
        task.result = result
        task.time.updated = time_iso()
        self.save()

    def complete_task(self, task_id: int, result: dict[str, Any], status: str = "completed") -> None:
        if status not in ("completed", "failed"):
            raise ValueError("status must be 'completed' or 'failed'")
        task = self._get_task(task_id)
        task.result = result
        task.status = cast(TaskStatus, status)
        task.time.updated = time_iso()
        self.save()

    def add_subtasks(self, parent_id: int, subtasks: list[dict[str, Any]]) -> list[int]:
        parent_task = self._get_task(parent_id)

        ids = []
        time_now = time_iso()

        for st in subtasks:
            task_type = st.type
            if task_type not in VALID_TYPES:
                raise ValueError(f"Unknown type '{task_type}' in subtask")
            tid = self.store.next_id
            self.store.next_id += 1
            priority = st.get("priority", default_priority(task_type))
            max_attempts = st.get("max_attempts", default_max_attempts(task_type))
            subtask_data = st.data
            title = st.title or derive_title(task_type, subtask_data)
            waiting_for = st.waiting_for
            task = Task(
                tid=tid,
                task_type=task_type,
                task_data=subtask_data,
                priority=priority,
                parent_id=parent_id,
                waiting_for=waiting_for,
                max_attempts=max_attempts,
                title=title,
                time_now=time_now,
            )
            self.store.tasks[tid] = task
            ids.append(tid)

        parent_task.children_ids.extend(ids)
        parent_task.time.updated = time_now
        self.save()
        return ids

    def retry_task(self, task_id: int) -> dict[str, Any]:
        task = self._get_task(task_id)
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
        task.time.updated = time_iso()
        self.save()
        return {"attempt": task.attempt}

    def list_tasks(self, status: str | None = None, task_type: str | None = None) -> list[Task]:
        tasks = self.store.tasks
        if status:
            tasks = [t for t in tasks if t.status == status]
        if task_type:
            tasks = [t for t in tasks if t.type == task_type]
        return tasks
