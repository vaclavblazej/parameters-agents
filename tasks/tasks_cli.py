#!/usr/bin/env python3
"""
Task queue CRUD CLI for the HOPS research orchestration.
"""

import argparse
import json
import sys

from .tasks import (
    VALID_TYPES,
    VALID_STATUSES,
    add_subtasks,
    add_task,
    complete_task,
    get_next_task,
    get_task,
    list_tasks,
    retry_task,
    set_task_result,
    update_task_status,
)


def out(obj: object) -> None:
    print(json.dumps(obj, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    out(list_tasks(status=args.status, task_type=args.type))


def cmd_next(args: argparse.Namespace) -> None:
    task = get_next_task(task_type=args.type)
    out(task if task is not None else {})


def cmd_add(args: argparse.Namespace) -> None:
    try:
        task_data = json.loads(args.data)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --data: {e}", file=sys.stderr)
        sys.exit(1)

    if args.type not in VALID_TYPES:
        print(f"Error: unknown type '{args.type}'. Valid: {sorted(VALID_TYPES)}", file=sys.stderr)
        sys.exit(1)

    blocked_by = []
    if args.blocked_by:
        try:
            blocked_by = json.loads(args.blocked_by)
            if not isinstance(blocked_by, list):
                raise ValueError("must be array")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: invalid JSON for --blocked-by: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        tid = add_task(
            task_type=args.type,
            task_data=task_data,
            priority=args.priority,
            parent_id=args.parent_id,
            title=args.title,
            blocked_by=blocked_by,
            max_attempts=args.max_attempts,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out({"id": tid})


def cmd_update(args: argparse.Namespace) -> None:
    if args.status not in VALID_STATUSES:
        print(f"Error: unknown status '{args.status}'. Valid: {sorted(VALID_STATUSES)}", file=sys.stderr)
        sys.exit(1)

    try:
        update_task_status(args.id, args.status)
    except (KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out({"ok": True})


def cmd_set_result(args: argparse.Namespace) -> None:
    try:
        result = json.loads(args.result)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --result: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        set_task_result(args.id, result)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out({"ok": True})


def cmd_add_subtasks(args: argparse.Namespace) -> None:
    try:
        subtasks_raw = json.loads(args.tasks)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --tasks: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(subtasks_raw, list):
        print("Error: --tasks must be a JSON array", file=sys.stderr)
        sys.exit(1)

    try:
        ids = add_subtasks(args.parent_id, subtasks_raw)
    except (KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out({"ids": ids})


def cmd_get(args: argparse.Namespace) -> None:
    task = get_task(args.id)
    if task is None:
        print(f"Error: task '{args.id}' not found", file=sys.stderr)
        sys.exit(1)
    out(task)


def cmd_complete(args: argparse.Namespace) -> None:
    try:
        result = json.loads(args.result)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON for --result: {e}", file=sys.stderr)
        sys.exit(1)

    status = args.status if args.status else "completed"
    try:
        complete_task(args.id, result, status)
    except (KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out({"ok": True})


def cmd_retry(args: argparse.Namespace) -> None:
    try:
        info = retry_task(args.id)
    except (KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out({"ok": True, **info})


def main():
    parser = argparse.ArgumentParser(description="Task queue CRUD CLI for the HOPS research orchestration framework")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List tasks")
    p_list.add_argument("--status", help="Filter by status")
    p_list.add_argument("--type", help="Filter by type")

    # next
    p_next = sub.add_parser("next", help="Get next pending task of the highest priority")
    p_next.add_argument("--type", help="Filter by type")

    # add
    p_add = sub.add_parser("add", help="Add a new task")
    p_add.add_argument("--type", required=True, help="Task type")
    p_add.add_argument("--data", required=True, help="Task data as JSON")
    p_add.add_argument("--priority", type=int, help="Priority 1-10")
    p_add.add_argument("--parent-id", help="Parent task ID")
    p_add.add_argument("--title", help="Task title (auto-derived if omitted)")
    p_add.add_argument("--blocked-by", help="JSON array of blocking task IDs")
    p_add.add_argument("--max-attempts", type=int, help="Max retry attempts")

    # update
    p_update = sub.add_parser("update", help="Update task status")
    p_update.add_argument("id", help="Task ID")
    p_update.add_argument("--status", required=True, help="New status")

    # set-result
    p_result = sub.add_parser("set-result", help="Set task result")
    p_result.add_argument("id", help="Task ID")
    p_result.add_argument("--result", required=True, help="Result as JSON")

    # add-subtasks
    p_sub = sub.add_parser("add-subtasks", help="Add multiple subtasks for a parent")
    p_sub.add_argument("parent_id", help="Parent task ID")
    p_sub.add_argument("--tasks", required=True, help="Array of subtask objects as JSON")

    # get
    p_get = sub.add_parser("get", help="Get a single task by ID")
    p_get.add_argument("id", help="Task ID")

    # complete
    p_complete = sub.add_parser("complete", help="Atomically set result and status")
    p_complete.add_argument("id", help="Task ID")
    p_complete.add_argument("--result", required=True, help="Result as JSON")
    p_complete.add_argument("--status", default="completed", help="Final status (completed|failed)")

    # retry
    p_retry = sub.add_parser("retry", help="Re-queue a failed task")
    p_retry.add_argument("id", help="Task ID")

    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "next": cmd_next,
        "add": cmd_add,
        "update": cmd_update,
        "set-result": cmd_set_result,
        "add-subtasks": cmd_add_subtasks,
        "get": cmd_get,
        "complete": cmd_complete,
        "retry": cmd_retry,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
