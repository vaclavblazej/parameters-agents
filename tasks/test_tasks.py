"""Tests for the tasks.py library."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from .tasks import (
    add_subtasks,
    add_task,
    complete_task,
    get_next_task,
    get_task,
    list_tasks,
    next_id,
    retry_task,
    set_task_result,
    update_task_status,
)


@pytest.fixture(autouse=True)
def isolated_tasks(tmp_path, monkeypatch):
    """Redirect TASKS_FILE to a temp directory for every test."""
    import tasks.tasks as mod

    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "TASKS_FILE", tmp_path / "tasks.json")


# ---------------------------------------------------------------------------
# next_id
# ---------------------------------------------------------------------------


def test_next_id_empty():
    assert next_id([]) == "t-001"


def test_next_id_sequential(tmp_path):
    tasks = [{"id": "t-003"}]
    assert next_id(tasks) == "t-004"


def test_next_id_gap(tmp_path):
    tasks = [{"id": "t-001"}, {"id": "t-005"}]
    assert next_id(tasks) == "t-006"


def test_next_id_ignores_non_standard():
    tasks = [{"id": "t-001"}, {"id": "custom-99"}]
    assert next_id(tasks) == "t-002"


# ---------------------------------------------------------------------------
# add_task / get_task / list_tasks
# ---------------------------------------------------------------------------


def _web_search_data():
    return {
        "topic": "treewidth",
        "description": "find papers",
        "github_issue_number": 0,
        "github_issue_url": "",
        "github_labels": [],
        "max_papers": 5,
    }


def test_add_task_returns_id():
    tid = add_task("web_search", _web_search_data())
    assert tid == "t-001"


def test_add_task_persisted():
    add_task("web_search", _web_search_data())
    task = get_task("t-001")
    assert task is not None
    assert task["type"] == "web_search"
    assert task["status"] == "pending"


def test_add_task_default_title():
    add_task("web_search", _web_search_data())
    task = get_task("t-001")
    assert task["title"] == "Search: treewidth"


def test_add_task_custom_title():
    add_task("web_search", _web_search_data(), title="My custom title")
    assert get_task("t-001")["title"] == "My custom title"


def test_add_task_invalid_type():
    with pytest.raises(ValueError, match="Unknown type"):
        add_task("nonexistent_type", {})


def test_add_task_increments_id():
    t1 = add_task("web_search", _web_search_data())
    t2 = add_task("web_search", _web_search_data())
    assert t1 == "t-001"
    assert t2 == "t-002"


def test_get_task_missing_returns_none():
    assert get_task("t-999") is None


def test_list_tasks_empty():
    assert list_tasks() == []


def test_list_tasks_filter_status():
    add_task("web_search", _web_search_data())
    update_task_status("t-001", "in_progress")
    add_task("web_search", _web_search_data())

    pending = list_tasks(status="pending")
    in_progress = list_tasks(status="in_progress")
    assert len(pending) == 1
    assert len(in_progress) == 1


def test_list_tasks_filter_type():
    add_task("web_search", _web_search_data())
    add_task("github_sync", {})
    assert len(list_tasks(task_type="web_search")) == 1


# ---------------------------------------------------------------------------
# update_task_status
# ---------------------------------------------------------------------------


def test_update_status():
    add_task("web_search", _web_search_data())
    update_task_status("t-001", "in_progress")
    assert get_task("t-001")["status"] == "in_progress"


def test_update_status_sets_started_at():
    add_task("web_search", _web_search_data())
    assert get_task("t-001")["started_at"] is None
    update_task_status("t-001", "in_progress")
    assert get_task("t-001")["started_at"] is not None


def test_update_status_invalid():
    add_task("web_search", _web_search_data())
    with pytest.raises(ValueError, match="Unknown status"):
        update_task_status("t-001", "flying")


def test_update_status_missing_task():
    with pytest.raises(KeyError):
        update_task_status("t-999", "pending")


# ---------------------------------------------------------------------------
# set_task_result
# ---------------------------------------------------------------------------


def test_set_task_result():
    add_task("web_search", _web_search_data())
    set_task_result("t-001", {"papers": ["p1"]})
    assert get_task("t-001")["result"] == {"papers": ["p1"]}


def test_set_task_result_missing_task():
    with pytest.raises(KeyError):
        set_task_result("t-999", {})


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------


def test_complete_task():
    add_task("web_search", _web_search_data())
    complete_task("t-001", {"done": True})
    task = get_task("t-001")
    assert task["status"] == "completed"
    assert task["result"] == {"done": True}


def test_complete_task_as_failed():
    add_task("web_search", _web_search_data())
    complete_task("t-001", {"error": "timeout"}, status="failed")
    assert get_task("t-001")["status"] == "failed"


def test_complete_task_invalid_status():
    add_task("web_search", _web_search_data())
    with pytest.raises(ValueError):
        complete_task("t-001", {}, status="pending")


def test_complete_task_missing_task():
    with pytest.raises(KeyError):
        complete_task("t-999", {})


# ---------------------------------------------------------------------------
# get_next_task
# ---------------------------------------------------------------------------


def test_get_next_task_none_when_empty():
    assert get_next_task() is None


def test_get_next_task_returns_pending():
    add_task("web_search", _web_search_data())
    task = get_next_task()
    assert task is not None
    assert task["id"] == "t-001"


def test_get_next_task_prefers_higher_priority():
    add_task("web_search", _web_search_data(), priority=3)
    add_task("web_search", _web_search_data(), priority=8)
    assert get_next_task()["id"] == "t-002"


def test_get_next_task_skips_in_progress():
    add_task("web_search", _web_search_data())
    update_task_status("t-001", "in_progress")
    assert get_next_task() is None


def test_get_next_task_skips_blocked():
    add_task("web_search", _web_search_data())
    add_task("web_search", _web_search_data(), blocked_by=["t-001"])
    # only t-001 is eligible
    assert get_next_task()["id"] == "t-001"


def test_get_next_task_unblocked_after_completion():
    add_task("web_search", _web_search_data())
    add_task("web_search", _web_search_data(), blocked_by=["t-001"])
    complete_task("t-001", {})
    # now t-002 is unblocked; t-001 is completed so not pending
    assert get_next_task()["id"] == "t-002"


def test_get_next_task_filter_by_type():
    add_task("web_search", _web_search_data())
    add_task("github_sync", {})
    task = get_next_task(task_type="github_sync")
    assert task["type"] == "github_sync"


# ---------------------------------------------------------------------------
# add_subtasks
# ---------------------------------------------------------------------------


def test_add_subtasks():
    add_task("web_search", _web_search_data())
    ids = add_subtasks("t-001", [{"type": "web_search", "data": _web_search_data()}])
    assert ids == ["t-002"]
    child = get_task("t-002")
    assert child["parent_id"] == "t-001"
    assert "t-002" in get_task("t-001")["successor_ids"]


def test_add_subtasks_invalid_parent():
    with pytest.raises(KeyError):
        add_subtasks("t-999", [{"type": "web_search", "data": _web_search_data()}])


def test_add_subtasks_invalid_type():
    add_task("web_search", _web_search_data())
    with pytest.raises(ValueError, match="Unknown type"):
        add_subtasks("t-001", [{"type": "bad_type", "data": {}}])


# ---------------------------------------------------------------------------
# retry_task
# ---------------------------------------------------------------------------


def test_retry_task():
    add_task("web_search", _web_search_data(), max_attempts=3)
    complete_task("t-001", {"error": "x"}, status="failed")
    info = retry_task("t-001")
    assert info["attempt"] == 2
    task = get_task("t-001")
    assert task["status"] == "pending"
    assert task["result"] is None


def test_retry_task_not_failed():
    add_task("web_search", _web_search_data())
    with pytest.raises(ValueError, match="not failed"):
        retry_task("t-001")


def test_retry_task_exceeds_max_attempts():
    add_task("web_search", _web_search_data(), max_attempts=1)
    complete_task("t-001", {}, status="failed")
    with pytest.raises(ValueError, match="max_attempts"):
        retry_task("t-001")


def test_retry_task_missing():
    with pytest.raises(KeyError):
        retry_task("t-999")
