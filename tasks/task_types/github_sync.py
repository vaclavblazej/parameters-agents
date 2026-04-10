from typing import Any, TypedDict
from dataclasses import dataclass
from typing import Union

@dataclass
class Gathering:
    input: str

@dataclass
class Researching:
    context: str
    subtask_ids: list[str]

@dataclass
class Writing:
    context: str
    research: dict[str, str]   # subtask_id → result

Phase = Union[Gathering, Researching, Writing]

class GithubSyncData(TypedDict):
    repo: str
    id: str
    phase: Phase

def execute(task: Task, subtask_results: dict) -> list["Task"]:
    match task.phase:
        case Gathering(input=inp):
            ctx = do_gather(inp)
            subs = [Task(..., Researching(ctx, [])) for _ in ...]
            task.phase = Researching(context=ctx, subtask_ids=[s.id for s in subs])
            return subs

        case Researching(context=ctx, subtask_ids=ids):
            task.phase = Writing(context=ctx, research=subtask_results)
            return []

        case Writing(context=ctx, research=res):
            task.result = do_write(ctx, res)
            return []


DEFAULT_PRIORITY = 5
DEFAULT_MAX_ATTEMPTS = 2


def derive_title(data: dict[str, Any]) -> str:
    return f"Sync: {data.get('repo', '')}"
