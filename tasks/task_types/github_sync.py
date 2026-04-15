from tasks.task_types import TaskData
from pydantic import BaseModel
from typing import Union


class Gathering(BaseModel):
    input: str

class Researching(BaseModel):
    context: str
    subtask_ids: list[str]

class Writing(BaseModel):
    context: str
    research: dict[str, str]   # subtask_id → result

Phase = Union[Gathering, Researching, Writing]


class GithubSyncData(TaskData):
    repo: str
    id: str
    phase: Phase

    def priority(self) -> int:
        return 5

    def max_attempts(self) -> int:
        return 2

    def derive_title(self) -> str:
        return f"Sync: {self.repo}"

    def execute(self, subtask_results: dict) -> list[Task]:
        match self.phase:
            case Gathering(input=inp):
                ctx = do_gather(inp)
                subs = [Task(..., Researching(ctx, [])) for _ in ...]
                self.phase = Researching(context=ctx, subtask_ids=[s.id for s in subs])
                return subs

            case Researching(context=ctx, subtask_ids=ids):
                self.phase = Writing(context=ctx, research=subtask_results)
                return []

            case Writing(context=ctx, research=res):
                self.result = do_write(ctx, res)
                return []
