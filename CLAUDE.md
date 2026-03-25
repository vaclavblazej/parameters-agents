# HOPS Research Orchestration Pipeline

## Project Overview

HOPS (Hierarchy of Parameters) is a database of graph-theoretic parameters and their relationships, intended for use by researchers. The `parameters/` directory contains the HOPS web project itself. This repo adds an automated research pipeline (`orchestration/`) that uses LLMs to populate HOPS by processing research papers.

The goal: run continuously (long-term), process papers automatically, and keep up with new publications. Human users can also inject work via GitHub issues or direct queries.

---

## Repository Layout

```
orchestration/          ← pipeline code (the main focus of this repo)
  tasks.py             ← task queue CRUD CLI
  run.py               ← runner: picks next task, invokes claude -p
  research.py          ← paper storage CLI
  github.py            ← GitHub issues sync CLI
  prompts/             ← subagent prompt templates (one per task type)
    orchestrator.md    ← central routing prompt (injected by run.py)
    github_sync.md
    web_search.md
    research_paper.md
    compile_entry.md
    user_input.md
  data/
    tasks.json         ← active task queue (all tasks, no archive yet)
    research/          ← per-paper JSON files (paper_id.json)
  tests/               ← test fixtures (one JSON per task type)
parameters/            ← HOPS web project (Hugo site + data)
web/                   ← (purpose TBD)
```

---

## Pipeline Flow (Current)

```
[GitHub issues]  →  github_sync  →  web_search (one per issue)
                                         ↓
                               research_paper (one per paper found)
                                         ↓
                               compile_entry (one per parameter/relation found)

[User query]  →  user_input  →  (human resolves, manually spawns follow-ups)
```

Each stage spawns successors upon completion; the spawning task does not wait for them.

---

## Implemented

### Task Queue (`tasks.py`)

Full CRUD CLI. Task fields: `id`, `type`, `title`, `status`, `priority`, `parent_id`, `subtask_ids`, `blocked_by`, `attempt`, `max_attempts`, `created_at`, `started_at`, `updated_at`, `data`, `result`.

- **Types**: `github_sync`, `web_search`, `research_paper`, `compile_entry`, `user_input`
- **Statuses**: `pending`, `in_progress`, `completed`, `failed`, `blocked`
- **Commands**: `list`, `next`, `add`, `update`, `set-result`, `add-subtasks`, `get`, `complete`, `retry`
- `next` picks highest-priority unblocked pending task
- `blocked_by` is for true dependencies (task cannot start until listed tasks complete)
- `parent_id`/`successor_ids` is for lineage/audit only ("spawned by"), not dependency

### Runner (`run.py`)

- Picks next task, marks `in_progress`, builds prompt (injects task JSON into `orchestrator.md`), calls `claude -p`
- `--test AGENT_TYPE`: runs a subagent directly with a fixture from `tests/`, bypasses the queue
- `--dry-run`: builds prompt but does not invoke Claude
- `--max-turns N`: cap claude turns (default 30)
- On non-zero exit: marks task `failed` with error

### Orchestrator (`prompts/orchestrator.md`)

Central decision table prompt. For each task type, it describes:
1. What subagent prompt to read
2. What to inject
3. What the subagent returns
4. What successors to spawn
5. How to record the result

**Known limitation**: adding a new task type requires editing this file. See "Planned Improvements" below.

### Paper Manager (`research.py`)

Stores per-paper data as individual JSON files in `data/research/`. Commands: `get`, `save`, `exists`, `list`, `derive-id`. Paper ID is derived from DOI (slug) or title (SHA-256 prefix). Used for deduplication: before spawning a `research_paper` task, the orchestrator checks `research.py exists PAPER_ID`.

### GitHub Sync (`github.py`)

Pulls open issues from a GitHub repo (default: `vaclavblazej/parameters-code`) and creates `web_search` tasks. Deduplicates by `github_issue_number`. Supports `--label` filter. Requires `GITHUB_TOKEN` env var.

**Current gap**: issues are imported wholesale as `web_search` tasks with no human review step and no per-issue local state tracking beyond what's embedded in the task.

---

## Partially Implemented / Known Gaps

### 1. Orchestrator Decision Table (extensibility friction)

`orchestrator.md` has a manual switch on task type. The fix: make it self-routing — load `prompts/{type}.md` without a decision table. Adding a new type would then only require adding a prompt file and registering the type in `tasks.py`. **Not yet done.**

### 2. `subtask_ids` Naming

Done. `subtask_ids` was renamed to `successor_ids` in `tasks.py` and `tasks.json`.

### 3. Task Archive

All tasks (active and finished) live in one `tasks.json`. The design calls for archiving completed/failed tasks into separate files split by creation date, keeping `tasks.json` lean. **Not yet done.**

### 4. GitHub Issues Local State

The full design calls for a separate issues store tracking: issue ID, title, open/closed state, labels, whether the system should handle it (`autohops` label), and local processing status. Currently there's no label-based gating — all open issues get imported. **Not yet done.**

### 5. Partial Resume / Stage Checkpointing

Tasks restart from scratch on retry. The fix: each per-type prompt should check the existing `result` field for partial work before re-running stages. No schema change needed. **Not yet done.**

---

## Not Yet Implemented

### New Paper Scraper

A system to discover new publications automatically:
- Local list of scraper sources (RSS feeds, email lists, etc.)
- Per-source config (pull method, auth, etc.)
- RSS state: last-seen item identifier/timestamp stored locally
- Email: mark messages as read after processing
- Output: entries added to a "new publications queue" for triage
- Papers found here may be irrelevant; no result is forced

Data needed:
- `Scraper source`: URL/identifier, pull method, method-specific config
- `RSS feed state`: per-source last-seen identifier or timestamp
- `New publications queue entry`: paper reference, source, timestamp found, processing status

### Autohops Runner

Automated runner that monitors Claude API usage:
- Checks current API usage against limits
- If usage is high enough and refresh is near, runs the next task
- Saves runner state: last run timestamp, API usage snapshot, next scheduled run

### User-Entered Query Pipeline

`user_input` task type exists but the full parsing pipeline does not: receiving a free-text query, classifying it (complex/split vs. direct paper reference vs. unrelated bug report), and spawning the right subtasks.

### HOPS Unknown Entry Tracking

Entries that HOPS doesn't have information about yet:
- Identifier of the unknown entry
- Timestamp of when the system last searched for it
- Search status
- Distinct from "doesn't exist" — absence of a result doesn't confirm absence of the thing

### Complex Query Splitting

A task type for decomposing a vague high-level request into concrete subtasks. Currently `web_search` is the entry point for all issue-derived queries, but some issues describe multiple distinct asks.

---

## Data Conventions

- **Paper ID**: DOI with non-alphanumeric chars replaced by `_` (preferred), or SHA-256 prefix of lowercase title
- **Task ID**: `t-NNN` sequential
- **Timestamps**: ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`)
- **Task `data` field**: typed per task type (see TypedDicts in `tasks.py`)
- **Task `result` field**: set by the subagent on completion; structure varies by type

## Running

```bash
# Process next pending task
cd orchestration && python3 run.py

# Process only a specific type
python3 run.py --task-type research_paper

# Test a subagent directly (no queue changes)
python3 run.py --test web_search

# Add a task manually
python3 tasks.py add --type web_search --data '{"topic":"...","description":"...","github_issue_number":0,"github_issue_url":"","github_labels":[],"max_papers":5}'

# Sync GitHub issues
GITHUB_TOKEN=... python3 github.py sync
```
