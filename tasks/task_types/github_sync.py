from typing import Any, TypedDict


class GithubSyncData(TypedDict):
    repo: str


DEFAULT_PRIORITY = 5
DEFAULT_MAX_ATTEMPTS = 2


def derive_title(data: dict[str, Any]) -> str:
    return f"Sync: {data.get('repo', '')}"
