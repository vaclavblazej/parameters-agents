from typing import Any, NotRequired, TypedDict


class UserInputData(TypedDict):
    question: str
    context: NotRequired[str]


DEFAULT_PRIORITY = 10
DEFAULT_MAX_ATTEMPTS = 1


def derive_title(data: dict[str, Any]) -> str:
    question = data.get("question", "")
    return f"Input: {question[:60]}"
