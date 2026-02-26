# Plan: HOPS Research Orchestration Framework

## Context

The HOPS project needs a systematic way to research academic papers on graph parameters, extract definitions/relations/BibTeX entries, and prepare them for import into `collection.rs` and `main.bib`. Currently this is done manually via ChatGPT-prompt-generating scripts (`query_param.py`, `query_relation.py`). The goal is an automated orchestration loop: a Python script invokes a Claude agent (`claude -p`) which picks the next task from a persistent queue, decomposes it, and delegates to specialized subagents.

**User choices:** `claude -p` CLI invocation · JSON-per-paper storage · Sequential execution · GitHub: `vaclavblazej/parameters-code`

---

## Directory Structure

```
parameters-agents/
  orchestration/
    run.py                    # Entry point: build prompt → invoke claude -p
    tasks.py                  # CLI: task queue CRUD (reads/writes tasks.json)
    research.py               # CLI: paper research storage
    github.py                 # CLI: GitHub issue → task sync
    prompts/
      orchestrator.md         # Main orchestrator agent prompt
      github_sync.md          # Subagent: sync GitHub issues
      web_search.md           # Subagent: find papers on a topic
      research_paper.md       # Subagent: deep-research one paper
      compile_entry.md        # Subagent: build collection.rs snippet
      user_input.md           # Subagent: surface question to human
    data/
      tasks.json              # Persistent task queue (created on first run)
      research/               # One JSON file per researched paper
```

---

## Data Schemas

### `data/tasks.json`

```json
{
  "tasks": [
    {
      "id": "t-001",
      "type": "web_search",
      "status": "pending",
      "priority": 5,
      "parent_id": null,
      "created_at": "2026-02-26T09:00:00Z",
      "updated_at": "2026-02-26T09:00:00Z",
      "data": { "topic": "twin-width parameterized complexity", "max_papers": 5 },
      "result": null
    }
  ]
}
```

**Fields:**
- `type`: `github_sync | web_search | research_paper | compile_entry | user_input`
- `status`: `pending | in_progress | completed | failed | blocked`
- `priority`: 1–10 (higher = processed first); `user_input` always 10, `research_paper` 6, `github_sync`/`web_search` 5, `compile_entry` 4
- `parent_id`: ID of the task that created this subtask, or null
- `data`: type-specific payload (see below)

**Per-type `data` payloads:**
```
github_sync:    { repo: "owner/repo" }
web_search:     { topic: string, max_papers: int }
research_paper: { paper_id: string, title: string, doi: string|null, url: string|null, reason: string }
compile_entry:  { paper_id: string, target: "parameter"|"relation"|"graph_class", parameter_name?: string, relation_from?: string, relation_to?: string }
user_input:     { question: string, context: string }
```

### `data/research/<paper_id>.json`

Paper ID: DOI with non-alphanumeric chars replaced by `_`; or `sha256(lowercase_title)[:16]` if no DOI.

```json
{
  "paper_id": "10_1145_3406325_3451088",
  "doi": "10.1145/3406325.3451088",
  "title": "Twin-width I: tractable FO model checking",
  "authors": ["Édouard Bonnet", "..."],
  "year": 2021,
  "venue": "STOC 2021",
  "url": "https://arxiv.org/abs/2004.14450",
  "pdf_accessible": true,
  "abstract": "...",
  "researched_at": "2026-02-26T10:00:00Z",
  "parameters_defined": [
    { "name": "twin-width", "definition_sentence": "...", "page": 3,
      "quote_verbatim": "...", "suggested_id": "aBcDeF", "score": 8 }
  ],
  "relations_found": [
    { "from": "twin-width", "to": "treewidth", "direction": "upper_bound",
      "bound_type": "Exponential", "theorem": "Theorem 2.3", "page": 7,
      "quote_verbatim": "..." }
  ],
  "bibtex": "@InProceedings{Bonnet2021,...}",
  "bibtex_key": "Bonnet2021",
  "suggested_source_id": "xY7mKp",
  "access_notes": "Open access via arXiv",
  "todo_flags": []
}
```

---

## Python Scripts CLI Interface

### `tasks.py`
```
tasks.py list [--status STATUS] [--type TYPE]   # → JSON array
tasks.py next [--type TYPE]                      # → single task JSON or {}
tasks.py add --type TYPE --data JSON [--priority N] [--parent-id ID]  # → {"id":"t-007"}
tasks.py update ID --status STATUS               # → {"ok": true}
tasks.py set-result ID --result JSON             # → {"ok": true}
tasks.py add-subtasks PARENT_ID --tasks JSON_ARRAY  # → {"ids": [...]}
tasks.py get ID                                  # → single task JSON
```

### `research.py`
```
research.py get PAPER_ID            # → paper JSON or exit 1
research.py save PAPER_ID --data JSON  # → {"ok": true, "path": "..."}
research.py exists PAPER_ID         # → {"exists": true/false}
research.py list [--format ids|summary]  # → JSON array
research.py derive-id --doi DOI     # → {"paper_id": "..."}
research.py derive-id --title TITLE # → {"paper_id": "..."}
```

### `github.py`
```
github.py sync [--repo OWNER/REPO] [--label LABEL] [--max N]
    # Uses GITHUB_TOKEN env var; deduplicates by issue number in tasks.json
    # → {"added": N, "skipped": M, "task_ids": [...]}
github.py list-issues [--repo OWNER/REPO] [--label LABEL]
    # → JSON array of {number, title, body, labels, url}
```

### `run.py`
```
run.py [--task-type TYPE] [--dry-run] [--max-turns N]
    1. tasks.py next → get highest-priority pending task
    2. tasks.py update → mark in_progress
    3. Inject task JSON into prompts/orchestrator.md
    4. claude -p "<prompt>" --allowedTools "Bash,Task,WebSearch,WebFetch" --max-turns N
```

**Exact `claude -p` invocation:**
```bash
claude -p "<orchestrator_prompt_with_injected_task_json>" \
  --allowedTools "Bash,Task,WebSearch,WebFetch" \
  --max-turns 30 \
  --output-format text
```

---

## Agent Prompt Design

All prompts in `prompts/` follow a standard structure:
1. **Context block** — injected task JSON
2. **Steps** — numbered actions using Bash (Python scripts) and/or WebSearch/WebFetch
3. **Output format** — explicit JSON structure the orchestrator reads

### `prompts/orchestrator.md`
Receives the current task JSON (injected by `run.py`). Decision table:
- `github_sync` → delegate to `github_sync.md` subagent
- `web_search` → delegate to `web_search.md`; on return, call `tasks.py add-subtasks` with discovered papers
- `research_paper` → check `research.py exists <paper_id>` first; if exists mark completed (skipped); else delegate to `research_paper.md`; on return, add `compile_entry` subtask per finding
- `compile_entry` → read `research.py get <paper_id>`; delegate to `compile_entry.md` with paper data injected
- `user_input` → delegate to `user_input.md` which prints the question to stdout and waits

After any subagent: call `tasks.py set-result` + `tasks.py update --status completed|failed`.

The orchestrator reads subagent prompts from disk via Bash (`cat prompts/<type>.md`) and passes them to the `Task` tool.

### `prompts/web_search.md`
Uses `WebSearch` to find papers on the topic. For each: derives `paper_id` via `research.py derive-id`, checks `research.py exists`, excludes already-researched. Returns `{papers_found: [...], already_researched: [...]}`.

### `prompts/research_paper.md`
Adapts the logic from `scripts/query_param.py` (ID generation, score, verbatim-quote requirements) into an automated form. Fetches the paper, extracts all parameters/relations/BibTeX, generates IDs via `python3 -c "import random,string; ..."`, saves via `research.py save`. Returns `{parameters_found: N, relations_found: M, pdf_accessible: bool}`.

### `prompts/compile_entry.md`
Adapts logic from both `query_param.py` and `query_relation.py`. Checks for name conflicts in `collection.rs`. Produces: Rust parameter/relation snippet, source entry, BibTeX entry. Uses IDs from the research JSON (never generates new ones). Returns `{collection_rs_snippet, bibtex_snippet, status, todo_items}`.

### `prompts/user_input.md`
Prints a formatted human-readable question to stdout. Returns `{status: "awaiting_human_input", task_id: "..."}`. The human then runs `tasks.py set-result` and `tasks.py update --status completed` manually.

---

## Paper Deduplication

**Level 1** (in `web_search` subagent): for each discovered paper, call `research.py exists` — skip if found, include if new.

**Level 2** (in orchestrator before `research_paper`): check again as a safety net to handle concurrent discovery. If already exists, mark task completed with `{skipped: true}`.

---

## Extensibility Pattern

To add a new agent type (e.g., `validate_entry`):
1. Create `prompts/validate_entry.md` following the standard structure
2. Add a `### validate_entry` case to `prompts/orchestrator.md`
3. Add `"validate_entry"` to `VALID_TYPES` in `tasks.py`

No other code changes required.

---

## Seeding

Create `data/tasks.json` with an initial task to bootstrap:
```json
{"tasks": [
  {"id": "t-001", "type": "github_sync", "status": "pending", "priority": 5,
   "parent_id": null, "created_at": "...", "updated_at": "...",
   "data": {"repo": "vaclavblazej/parameters-code"}, "result": null}
]}
```

---

## Critical Files to Reference During Implementation

- `scripts/query_param.py` — ID generation pattern, score system, verbatim-quote requirements → used by `research_paper.md` and `compile_entry.md`
- `scripts/query_relation.py` — relation types and entity-type dispatch → used by `compile_entry.md`
- `parameters/hops/src/collection.rs` — Rust syntax patterns for generated snippets; conflict checking
- `parameters/handcrafted/main.bib` — BibTeX entry format (`@InProceedings`, `@Article`, field names)
- `parameters/hops/src/input/source.rs` — `Cpx` enum variants and `RawWrote` structure used in generated Rust

---

## Implementation Order

1. Write this plan to `plans/orchestration.md`
2. Create directory structure
3. Implement `tasks.py`
4. Implement `research.py`
5. Implement `github.py`
6. Write all agent prompts
7. Implement `run.py`
8. Seed `data/tasks.json`

## Verification

1. `python3 tasks.py list` — confirm tasks.json is created and readable
2. `python3 run.py --dry-run` — confirm prompt is built correctly without invoking claude
3. `python3 run.py --task-type github_sync` — run a live github_sync task; confirm issues appear in tasks.json
4. `python3 run.py --task-type web_search` — run a web_search task; confirm `research_paper` subtasks are added
5. `python3 run.py` — run a `research_paper` task; confirm `data/research/<paper_id>.json` is written
6. Inspect the JSON for a researched paper and verify all fields (definitions, relations, BibTeX) are present
7. Run `python3 run.py` on a `compile_entry` task; verify Rust snippet is valid syntax
