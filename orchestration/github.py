#!/usr/bin/env python3
"""
GitHub issue → task sync CLI for the HOPS research orchestration framework.

Requires GITHUB_TOKEN environment variable.

Usage:
  github.py sync [--repo OWNER/REPO] [--label LABEL] [--max N]
  github.py list-issues [--repo OWNER/REPO] [--label LABEL]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Add parent dir so we can import tasks helper functions
sys.path.insert(0, str(Path(__file__).parent))

DATA_DIR = Path(__file__).parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"

DEFAULT_REPO = "vaclavblazej/parameters-code"
GITHUB_API = "https://api.github.com"


def out(obj) -> None:
    print(json.dumps(obj, indent=2))


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)
    return token


def github_get(path: str, token: str) -> list | dict:
    url = f"{GITHUB_API}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Error: GitHub API {e.code} for {url}: {body}", file=sys.stderr)
        sys.exit(1)


def fetch_issues(repo: str, label: str | None, token: str, max_issues: int = 100) -> list:
    """Fetch open issues from a repo, optionally filtered by label."""
    per_page = min(max_issues, 100)
    params = f"state=open&per_page={per_page}"
    if label:
        params += f"&labels={urllib.parse.quote(label)}"
    path = f"/repos/{repo}/issues?{params}"
    issues = github_get(path, token)
    if not isinstance(issues, list):
        return []
    # Filter out pull requests (GitHub returns PRs in issues endpoint)
    return [i for i in issues if "pull_request" not in i]


def load_tasks() -> dict:
    if not TASKS_FILE.exists():
        return {"tasks": []}
    with open(TASKS_FILE) as f:
        return json.load(f)


def save_tasks(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def existing_issue_numbers(tasks: list) -> set:
    """Return set of GitHub issue numbers already in the task queue."""
    nums = set()
    for t in tasks:
        if t.get("type") == "web_search":
            d = t.get("data", {})
            if "github_issue_number" in d:
                nums.add(d["github_issue_number"])
    return nums


def next_id(tasks: list) -> str:
    if not tasks:
        return "t-001"
    nums = []
    for t in tasks:
        tid = t.get("id", "")
        if tid.startswith("t-") and tid[2:].isdigit():
            nums.append(int(tid[2:]))
    if not nums:
        return "t-001"
    return f"t-{max(nums) + 1:03d}"


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Subcommands ────────────────────────────────────────────────────────────────

def cmd_sync(args) -> None:
    token = get_token()
    repo = args.repo or DEFAULT_REPO
    max_issues = args.max or 50

    issues = fetch_issues(repo, args.label, token, max_issues)

    data = load_tasks()
    existing = existing_issue_numbers(data["tasks"])

    added = 0
    skipped = 0
    task_ids = []
    ts = now_iso()

    for issue in issues:
        num = issue.get("number")
        if num in existing:
            skipped += 1
            continue

        title = issue.get("title", "")
        body = issue.get("body", "") or ""
        url = issue.get("html_url", "")
        labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]

        tid = next_id(data["tasks"])
        task = {
            "id": tid,
            "type": "web_search",
            "status": "pending",
            "priority": 5,
            "parent_id": None,
            "created_at": ts,
            "updated_at": ts,
            "data": {
                "topic": title,
                "description": body[:500] if body else "",
                "github_issue_number": num,
                "github_issue_url": url,
                "github_labels": labels,
                "max_papers": 5,
            },
            "result": None,
        }
        data["tasks"].append(task)
        task_ids.append(tid)
        added += 1

    save_tasks(data)
    out({"added": added, "skipped": skipped, "task_ids": task_ids})


def cmd_list_issues(args) -> None:
    token = get_token()
    repo = args.repo or DEFAULT_REPO
    issues = fetch_issues(repo, args.label, token)

    result = []
    for issue in issues:
        result.append({
            "number": issue.get("number"),
            "title": issue.get("title", ""),
            "body": (issue.get("body", "") or "")[:300],
            "labels": [lbl.get("name", "") for lbl in issue.get("labels", [])],
            "url": issue.get("html_url", ""),
        })
    out(result)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HOPS GitHub issue sync CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # sync
    p_sync = sub.add_parser("sync", help="Sync GitHub issues into task queue")
    p_sync.add_argument("--repo", help="GitHub repo (owner/repo)")
    p_sync.add_argument("--label", help="Filter by label")
    p_sync.add_argument("--max", type=int, help="Max issues to fetch")

    # list-issues
    p_list = sub.add_parser("list-issues", help="List open GitHub issues")
    p_list.add_argument("--repo", help="GitHub repo (owner/repo)")
    p_list.add_argument("--label", help="Filter by label")

    args = parser.parse_args()

    dispatch = {
        "sync": cmd_sync,
        "list-issues": cmd_list_issues,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
