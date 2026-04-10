"""Tests for the tasks.py library."""

import pytest

from .tasks import TaskManager


@pytest.fixture(autouse=True)
def isolated_tasks(tmp_path, monkeypatch):
    """Redirect TASKS_FILE to a temp directory for every test."""
    import tasks.tasks as mod

    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "TASKS_FILE", tmp_path / "tasks.json")


@pytest.fixture
def store():
    return TaskManager()


def _test_data():
    return {
        "topic": "treewidth",
        "description": "find papers",
        "github_issue_number": 0,
        "github_issue_url": "",
        "github_labels": [],
        "max_papers": 5,
    }


# ---------------------------------------------------------------------------
# add_task / get_task / list_tasks
# ---------------------------------------------------------------------------


def test_add_task_returns_id(store):
    tid = store.add_task("web_search", _test_data())
    assert tid == 1


def test_add_task_persisted(store):
    store.add_task("web_search", _test_data())
    task = store.get_task(1)
    assert task is not None
    assert task["type"] == "web_search"
    assert task["status"] == "pending"


def test_add_task_default_title(store):
    store.add_task("web_search", _test_data())
    task = store.get_task(1)
    assert task["title"] == "Search: treewidth"


def test_add_task_custom_title(store):
    store.add_task("web_search", _test_data(), title="My custom title")
    assert store.get_task(1)["title"] == "My custom title"


def test_add_task_invalid_type(store):
    with pytest.raises(ValueError, match="Unknown type"):
        store.add_task("nonexistent_type", {})


def test_add_task_increments_id(store):
    t1 = store.add_task("web_search", _test_data())
    t2 = store.add_task("web_search", _test_data())
    assert t1 == 1
    assert t2 == 2


def test_get_task_missing_returns_none(store):
    assert store.get_task(999) is None


def test_list_tasks_empty(store):
    assert store.list_tasks() == []


def test_list_tasks_filter_status(store):
    store.add_task("web_search", _test_data())
    store.update_task_status(1, "in_progress")
    store.add_task("web_search", _test_data())

    pending = store.list_tasks(status="pending")
    in_progress = store.list_tasks(status="in_progress")
    assert len(pending) == 1
    assert len(in_progress) == 1


def test_list_tasks_filter_type(store):
    store.add_task("web_search", _test_data())
    store.add_task("github_sync", {})
    assert len(store.list_tasks(task_type="web_search")) == 1


# ---------------------------------------------------------------------------
# update_task_status
# ---------------------------------------------------------------------------


def test_update_status(store):
    store.add_task("web_search", _test_data())
    store.update_task_status(1, "in_progress")
    assert store.get_task(1)["status"] == "in_progress"


def test_update_status_sets_started_at(store):
    store.add_task("web_search", _test_data())
    assert store.get_task(1)["started_at"] is None
    store.update_task_status(1, "in_progress")
    assert store.get_task(1)["started_at"] is not None


def test_update_status_invalid(store):
    store.add_task("web_search", _test_data())
    with pytest.raises(ValueError, match="Unknown status"):
        store.update_task_status(1, "flying")


def test_update_status_missing_task(store):
    with pytest.raises(KeyError):
        store.update_task_status(999, "pending")


# ---------------------------------------------------------------------------
# set_task_result
# ---------------------------------------------------------------------------


def test_set_task_result(store):
    store.add_task("web_search", _test_data())
    store.set_task_result(1, {"papers": ["p1"]})
    assert store.get_task(1)["result"] == {"papers": ["p1"]}


def test_set_task_result_missing_task(store):
    with pytest.raises(KeyError):
        store.set_task_result(999, {})


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------


def test_complete_task(store):
    store.add_task("web_search", _test_data())
    store.complete_task(1, {"done": True})
    task = store.get_task(1)
    assert task["status"] == "completed"
    assert task["result"] == {"done": True}


def test_complete_task_as_failed(store):
    store.add_task("web_search", _test_data())
    store.complete_task(1, {"error": "timeout"}, status="failed")
    assert store.get_task(1)["status"] == "failed"


def test_complete_task_invalid_status(store):
    store.add_task("web_search", _test_data())
    with pytest.raises(ValueError):
        store.complete_task(1, {}, status="pending")


def test_complete_task_missing_task(store):
    with pytest.raises(KeyError):
        store.complete_task(999, {})


# ---------------------------------------------------------------------------
# get_next_task
# ---------------------------------------------------------------------------


def test_get_next_task_none_when_empty(store):
    assert store.get_next_task() is None


def test_get_next_task_returns_pending(store):
    store.add_task("web_search", _test_data())
    task = store.get_next_task()
    assert task is not None
    assert task["id"] == 1


def test_get_next_task_prefers_higher_priority(store):
    store.add_task("web_search", _test_data(), priority=3)
    store.add_task("web_search", _test_data(), priority=8)
    assert store.get_next_task()["id"] == 2


def test_get_next_task_skips_in_progress(store):
    store.add_task("web_search", _test_data())
    store.update_task_status(1, "in_progress")
    assert store.get_next_task() is None


def test_get_next_task_skips_blocked(store):
    store.add_task("web_search", _test_data())
    store.add_task("web_search", _test_data(), blocked_by=[1])
    # only task 1 is eligible
    assert store.get_next_task()["id"] == 1


def test_get_next_task_unblocked_after_completion(store):
    store.add_task("web_search", _test_data())
    store.add_task("web_search", _test_data(), blocked_by=[1])
    store.complete_task(1, {})
    # now task 2 is unblocked; task 1 is completed so not pending
    assert store.get_next_task()["id"] == 2


def test_get_next_task_filter_by_type(store):
    store.add_task("web_search", _test_data())
    store.add_task("github_sync", {})
    task = store.get_next_task(task_type="github_sync")
    assert task["type"] == "github_sync"


# ---------------------------------------------------------------------------
# add_subtasks
# ---------------------------------------------------------------------------


def test_add_subtasks(store):
    store.add_task("web_search", _test_data())
    ids = store.add_subtasks(1, [{"type": "web_search", "data": _test_data()}])
    assert ids == [2]
    child = store.get_task(2)
    assert child["parent_id"] == 1
    assert 2 in store.get_task(1)["successor_ids"]


def test_add_subtasks_invalid_parent(store):
    with pytest.raises(KeyError):
        store.add_subtasks(999, [{"type": "web_search", "data": _test_data()}])


def test_add_subtasks_invalid_type(store):
    store.add_task("web_search", _test_data())
    with pytest.raises(ValueError, match="Unknown type"):
        store.add_subtasks(1, [{"type": "bad_type", "data": {}}])


# ---------------------------------------------------------------------------
# retry_task
# ---------------------------------------------------------------------------


def test_retry_task(store):
    store.add_task("web_search", _test_data(), max_attempts=3)
    store.complete_task(1, {"error": "x"}, status="failed")
    info = store.retry_task(1)
    assert info["attempt"] == 2
    task = store.get_task(1)
    assert task["status"] == "pending"
    assert task["result"] is None


def test_retry_task_not_failed(store):
    store.add_task("web_search", _test_data())
    with pytest.raises(ValueError, match="not failed"):
        store.retry_task(1)


def test_retry_task_exceeds_max_attempts(store):
    store.add_task("web_search", _test_data(), max_attempts=1)
    store.complete_task(1, {}, status="failed")
    with pytest.raises(ValueError, match="max_attempts"):
        store.retry_task(1)


def test_retry_task_missing(store):
    with pytest.raises(KeyError):
        store.retry_task(999)
