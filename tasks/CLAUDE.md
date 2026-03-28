# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this package is

`tasks/` is a Python package — the task queue library for the HOPS research orchestration pipeline. It is imported by `../orchestration/` scripts (e.g., `run.py`, `tasks.py` CLI). See the root `CLAUDE.md` for pipeline-level context.

## Commands

Run all tests from the repo root (tests are a package, must run from parent):

```bash
python3 -m pytest .
```

Run a single test:

```bash
python3 -m pytest test_tasks.py::test_get_next_task_unblocked_after_completion
```

Use the CLI directly (also from repo root, since `tasks` is a package):

```bash
cd .. && python3 -m tasks.tasks_cli list
python3 -m tasks.tasks_cli add --type web_search --data '{"topic":"...","description":"...","github_issue_number":0,"github_issue_url":"","github_labels":[],"max_papers":5}'
python3 -m tasks.tasks_cli next
python3 -m tasks.tasks_cli complete t-001 --result '{}'
```

## Architecture

```
tasks/
  tasks.py          ← core library: all CRUD functions (add_task, get_task, list_tasks, etc.)
  tasks_cli.py      ← argparse CLI wrapping tasks.py; entrypoint is main()
  task_types/
    __init__.py     ← REGISTRY dict + TaskType union + helper dispatch (default_priority, derive_title)
    web_search.py   ← TypedDict + DEFAULT_PRIORITY + DEFAULT_MAX_ATTEMPTS + derive_title()
    github_sync.py  ← (same pattern)
    research_paper.py
    compile_entry.py
    user_input.py
  test_tasks.py     ← pytest; uses monkeypatch to redirect TASKS_FILE to tmp_path
```

**Adding a new task type**: create `task_types/<name>.py` with `*Data(TypedDict)`, `DEFAULT_PRIORITY`, `DEFAULT_MAX_ATTEMPTS`, `derive_title(data)`, then register it in `task_types/__init__.py` (REGISTRY + TaskData union + TaskType Literal).

**Task selection**: `get_next_task()` picks the highest-priority unblocked pending task. `blocked_by` is a hard dependency (task waits). `parent_id` / `successor_ids` is lineage only — no scheduling effect.

**Storage**: single `data/tasks.json` file. All task states (pending through completed/failed) live there — no archiving yet.
