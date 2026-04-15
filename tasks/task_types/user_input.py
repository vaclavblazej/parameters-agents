from tasks.task_types import TaskData


class UserInputData(TaskData):
    question: str
    context: str

    def priority(self) -> int:
        return 10

    def derive_title(self) -> str:
        return f"Input: {self.question[:60]}"
