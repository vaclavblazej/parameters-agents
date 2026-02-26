#!/usr/bin/env python3
"""
Paper research storage CLI for the HOPS research orchestration framework.

Usage:
  research.py get PAPER_ID
  research.py save PAPER_ID --data JSON
  research.py exists PAPER_ID
  research.py list [--format ids|summary]
  research.py derive-id --doi DOI
  research.py derive-id --title TITLE
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RESEARCH_DIR = DATA_DIR / "research"


def out(obj) -> None:
    print(json.dumps(obj, indent=2))


def doi_to_paper_id(doi: str) -> str:
    """Replace non-alphanumeric chars in DOI with underscores."""
    return re.sub(r"[^A-Za-z0-9]", "_", doi)


def title_to_paper_id(title: str) -> str:
    """sha256 of lowercase title, first 16 hex chars."""
    h = hashlib.sha256(title.strip().lower().encode()).hexdigest()
    return h[:16]


def paper_path(paper_id: str) -> Path:
    return RESEARCH_DIR / f"{paper_id}.json"


# ── Subcommands ────────────────────────────────────────────────────────────────

def cmd_get(args) -> None:
    path = paper_path(args.paper_id)
    if not path.exists():
        print(f"Error: paper '{args.paper_id}' not found", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        out(json.load(f))


def cmd_save(args) -> None:
    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --data: {e}", file=sys.stderr)
        sys.exit(1)

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    path = paper_path(args.paper_id)

    # Ensure paper_id is set in the data
    data["paper_id"] = args.paper_id
    if "researched_at" not in data:
        data["researched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    out({"ok": True, "path": str(path)})


def cmd_exists(args) -> None:
    exists = paper_path(args.paper_id).exists()
    out({"exists": exists})


def cmd_list(args) -> None:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    papers = sorted(RESEARCH_DIR.glob("*.json"))

    if args.format == "ids":
        out([p.stem for p in papers])
        return

    # summary format (default)
    result = []
    for p in papers:
        try:
            with open(p) as f:
                d = json.load(f)
            result.append({
                "paper_id": d.get("paper_id", p.stem),
                "title": d.get("title", ""),
                "year": d.get("year"),
                "parameters_defined": len(d.get("parameters_defined", [])),
                "relations_found": len(d.get("relations_found", [])),
                "researched_at": d.get("researched_at", ""),
            })
        except Exception:
            result.append({"paper_id": p.stem, "error": "unreadable"})
    out(result)


def cmd_derive_id(args) -> None:
    if args.doi:
        out({"paper_id": doi_to_paper_id(args.doi)})
    elif args.title:
        out({"paper_id": title_to_paper_id(args.title)})
    else:
        print("Error: must supply --doi or --title", file=sys.stderr)
        sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HOPS paper research storage CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # get
    p_get = sub.add_parser("get", help="Retrieve a paper's research JSON")
    p_get.add_argument("paper_id", help="Paper ID")

    # save
    p_save = sub.add_parser("save", help="Save/update a paper's research JSON")
    p_save.add_argument("paper_id", help="Paper ID")
    p_save.add_argument("--data", required=True, help="Full paper JSON to save")

    # exists
    p_exists = sub.add_parser("exists", help="Check if a paper has been researched")
    p_exists.add_argument("paper_id", help="Paper ID")

    # list
    p_list = sub.add_parser("list", help="List all researched papers")
    p_list.add_argument("--format", choices=["ids", "summary"], default="summary")

    # derive-id
    p_derive = sub.add_parser("derive-id", help="Compute paper_id from DOI or title")
    p_derive.add_argument("--doi", help="DOI string")
    p_derive.add_argument("--title", help="Paper title")

    args = parser.parse_args()

    dispatch = {
        "get": cmd_get,
        "save": cmd_save,
        "exists": cmd_exists,
        "list": cmd_list,
        "derive-id": cmd_derive_id,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
