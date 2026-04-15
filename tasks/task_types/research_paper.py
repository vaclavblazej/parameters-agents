from tasks.task_types import TaskData


class ResearchPaperData(TaskData):
    paper_id: str
    title: str
    doi: str
    url: str
    reason: str

    def priority(self) -> int:
        return 6

    def max_attempts(self) -> int:
        return 2

    def derive_title(self) -> str:
        return f"Research: {self.title}"
