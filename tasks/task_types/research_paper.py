from typing import Any, TypedDict


class ResearchPaperData(TypedDict):
    paper_id: str
    title: str
    doi: str
    url: str
    reason: str


DEFAULT_PRIORITY = 6
DEFAULT_MAX_ATTEMPTS = 2


def derive_title(data: dict[str, Any]) -> str:
    return f"Research: {data.get('title', '')}"
