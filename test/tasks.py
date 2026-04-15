"""
Experimenting with typing, saving and loading json
"""

from pydantic import BaseModel
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

TASKS_FILE = Path(__file__).parent / "data.json"

DataStatus = Literal["pending", "running", "completed", "failed", "blocked"]



def time_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ComplexData(BaseModel):
    version: int = 1
    time: str
    numbers: list[int]


class Data(BaseModel):
    number: int
    title: str
    decimal: float
    optional: int | None
    time: str
    complex: ComplexData
    status: DataStatus


def load() -> Data:
    with open(TASKS_FILE) as f:
        return Data(**json.load(f))


def save(object: Data):
    print("## SAVING ######################################################################")
    print(json.dumps(object.model_dump(), indent=4))
    with open(TASKS_FILE, "w") as f:
        json.dump(object.model_dump(), f, indent=4)
        f.write("\n")
    print("################################################################################")


obj = Data(
    number=1,
    title="hello world",
    decimal=2.3,
    optional=None,
    time=time_now(),
    complex=ComplexData(
        time="inner hello",
        numbers=[5,6,7,8,9,0],
    ),
    status="pending",
)


print(obj)
save(obj)
res=load()
print(res)
assert obj==res
