from tasks.task_types import TaskData, TaskExecutionResult


class TestHelloWorldData(TaskData):

    def derive_title(self) -> str:
        return "Test: Hello World"

    def execute(self) -> TaskExecutionResult:
        print("Hello World")
        return TaskExecutionResult(result={"message": "Hello World"})
