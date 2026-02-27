#!/usr/bin/env python3
"""
Entry point for the HOPS research orchestration loop.

Picks the next pending task, injects it into the orchestrator prompt,
and invokes claude -p to process it.

Usage:
  run.py [--task-type TYPE] [--dry-run] [--max-turns N]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ORCHESTRATION_DIR = Path(__file__).parent
PROMPTS_DIR = ORCHESTRATION_DIR / "prompts"
ORCHESTRATOR_PROMPT = PROMPTS_DIR / "orchestrator.md"

TASKS_PY = ORCHESTRATION_DIR / "tasks.py"
DEFAULT_MAX_TURNS = 30


def run_tasks(args: list[str]) -> dict | list:
    """Run tasks.py with given args and return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, str(TASKS_PY)] + args,
        capture_output=True,
        text=True,
        cwd=str(ORCHESTRATION_DIR),
    )
    if result.returncode != 0:
        print(f"Error running tasks.py: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def build_prompt(task: dict) -> str:
    """Read orchestrator.md and inject the task JSON."""
    template = ORCHESTRATOR_PROMPT.read_text()
    task_json = json.dumps(task, indent=2)
    return template.replace("{{TASK_JSON}}", task_json)


def invoke_claude(prompt: str, max_turns: int, dry_run: bool) -> int:
    """Invoke claude -p with the given prompt. Returns exit code."""
    cmd = [
        "claude",
        "-p", prompt,
        "--allowedTools", "Bash,Task,WebSearch,WebFetch",
        "--max-turns", str(max_turns),
        "--output-format", "text",
    ]

    if dry_run:
        print("=== DRY RUN: would invoke ===")
        print(f"claude -p <prompt> --allowedTools Bash,Task,WebSearch,WebFetch --max-turns {max_turns} --output-format text")
        print("\n=== Prompt preview (first 500 chars) ===")
        print(prompt[:500])
        print("...")
        return 0

    print(f"Invoking claude with max-turns={max_turns}...")
    result = subprocess.run(cmd, cwd=str(ORCHESTRATION_DIR))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="HOPS orchestration runner")
    parser.add_argument("--task-type", help="Only process tasks of this type")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build prompt but do not invoke claude")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS,
                        help=f"Max claude turns (default {DEFAULT_MAX_TURNS})")
    args = parser.parse_args()

    # 1. Get next pending task
    next_args = ["next"]
    if args.task_type:
        next_args += ["--type", args.task_type]

    task = run_tasks(next_args)

    if not task:
        print("No pending tasks found.")
        # Show queue summary
        all_tasks = run_tasks(["list"])
        if isinstance(all_tasks, list):
            status_counts: dict[str, int] = {}
            for t in all_tasks:
                s = t.get("status", "unknown")
                status_counts[s] = status_counts.get(s, 0) + 1
            if status_counts:
                print("Task queue summary:")
                for status, count in sorted(status_counts.items()):
                    print(f"  {status}: {count}")
        return

    task_id = task["id"]
    task_type = task["type"]
    print(f"Processing task {task_id} (type: {task_type}, priority: {task.get('priority')})")

    # 2. Mark in_progress
    if not args.dry_run:
        run_tasks(["update", task_id, "--status", "in_progress"])

    # 3. Build prompt
    prompt = build_prompt(task)

    # 4. Invoke claude
    exit_code = invoke_claude(prompt, args.max_turns, args.dry_run)

    if exit_code != 0:
        print(f"claude exited with code {exit_code}", file=sys.stderr)
        if not args.dry_run:
            run_tasks(["update", task_id, "--status", "failed"])
            run_tasks(["set-result", task_id, "--result",
                       json.dumps({"error": f"claude exit code {exit_code}"})])
        sys.exit(exit_code)

    print(f"Task {task_id} processed.")


if __name__ == "__main__":
    main()
