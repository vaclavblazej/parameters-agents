from typing import Any, Literal, NotRequired, TypedDict


class CompileEntryData(TypedDict):
    paper_id: str
    target: Literal["parameter", "relation"]
    parameter_name: NotRequired[str]
    relation_from: NotRequired[str]
    relation_to: NotRequired[str]


DEFAULT_PRIORITY = 4
DEFAULT_MAX_ATTEMPTS = 1


def derive_title(data: dict[str, Any]) -> str:
    target = data.get("target", "")
    if target == "parameter":
        return f"Compile parameter: {data.get('parameter_name', '')}"
    return f"Compile relation: {data.get('relation_from', '')} \u2192 {data.get('relation_to', '')}"
