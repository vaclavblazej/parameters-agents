from typing import Literal
from tasks.task_types import TaskData


class CompileEntryData(TaskData):
    paper_id: str
    target: Literal["parameter", "relation"] # todo typing
    parameter_name: str
    relation_from: str
    relation_to: str

    def priority(self) -> int:
        return 4

    def max_attempts(self) -> int:
        return 1

    def derive_title(self) -> str:
        target = self.target
        if target == "parameter":
            return f"Compile parameter: {self.parameter_name}"
        return f"Compile relation: {self.relation_from} \u2192 {self.relation_to}"
