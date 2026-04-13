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
def manager():
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


def test_add_task_returns_id(manager):
    tid = manager.add_task("web_search", _test_data())
    assert tid == 1

