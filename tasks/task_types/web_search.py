from tasks.task_types import TaskData

class WebSearchData(TaskData):
    topic: str
    description: str
    github_issue_number: int
    github_issue_url: str
    github_labels: list[str]
    max_papers: int

    def max_attempts(self) -> int:
        return 2

    def derive_title(self) -> str:
        return f"Search: {self.topic}"
