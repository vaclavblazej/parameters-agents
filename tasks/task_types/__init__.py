"""
"""

from typing import Literal
from pydantic import BaseModel

# from . import compile_entry, github_sync, research_paper, user_input, web_search

TaskType = Literal["github_sync", "web_search", "research_paper", "compile_entry", "user_input"]

# # Map type name → module
# REGISTRY: dict[str, ModuleType] = {
#     "github_sync": github_sync,
#     "web_search": web_search,
#     "research_paper": research_paper,
#     "compile_entry": compile_entry,
#     "user_input": user_input,
# }
#
# # Re-export data TypedDicts for convenience
# from .compile_entry import CompileEntryData
# from .github_sync import GithubSyncData
# from .research_paper import ResearchPaperData
# from .user_input import UserInputData
# from .web_search import WebSearchData


class TaskExecutionResult(BaseModel):
    span: list[TaskData] = []
    result: dict | None = None


class TaskData(BaseModel):

    def priority(self) -> int:
        return 5

    def max_attempts(self) -> int:
        return 1

    def derive_title(self) -> str:
        assert False

    def execute(self) -> TaskExecutionResult:
        assert False
