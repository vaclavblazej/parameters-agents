"""
Registry of task types. Each module exposes:
  - A TypedDict subclass for the task's data field
  - DEFAULT_PRIORITY: int
  - DEFAULT_MAX_ATTEMPTS: int
  - derive_title(data: dict) -> str
"""

from types import ModuleType
from typing import Any, Literal

from . import compile_entry, github_sync, research_paper, user_input, web_search

TaskType = Literal["github_sync", "web_search", "research_paper", "compile_entry", "user_input"]

# Map type name → module
REGISTRY: dict[str, ModuleType] = {
    "github_sync": github_sync,
    "web_search": web_search,
    "research_paper": research_paper,
    "compile_entry": compile_entry,
    "user_input": user_input,
}

# Re-export data TypedDicts for convenience
from .compile_entry import CompileEntryData
from .github_sync import GithubSyncData
from .research_paper import ResearchPaperData
from .user_input import UserInputData
from .web_search import WebSearchData

TaskData = GithubSyncData | WebSearchData | ResearchPaperData | CompileEntryData | UserInputData


def default_priority(task_type: str) -> int:
    mod = REGISTRY.get(task_type)
    return mod.DEFAULT_PRIORITY if mod else 5


def default_max_attempts(task_type: str) -> int:
    mod = REGISTRY.get(task_type)
    return mod.DEFAULT_MAX_ATTEMPTS if mod else 1


def derive_title(task_type: str, data: dict[str, Any]) -> str:
    mod = REGISTRY.get(task_type)
    if mod:
        return mod.derive_title(data)
    return ""
