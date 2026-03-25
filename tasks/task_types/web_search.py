from typing import Any, TypedDict


class WebSearchData(TypedDict):
    topic: str
    description: str
    github_issue_number: int
    github_issue_url: str
    github_labels: list[str]
    max_papers: int


DEFAULT_PRIORITY = 5
DEFAULT_MAX_ATTEMPTS = 2


def derive_title(data: dict[str, Any]) -> str:
    return f"Search: {data.get('topic', '')}"
