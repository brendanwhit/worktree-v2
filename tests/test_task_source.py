"""Tests for TaskSource protocol and Task model."""

from superintendent.orchestrator.sources.models import Task, TaskStatus


class TestTaskStatus:
    def test_status_values(self):
        assert TaskStatus.pending == "pending"
        assert TaskStatus.in_progress == "in_progress"
        assert TaskStatus.completed == "completed"
        assert TaskStatus.failed == "failed"

    def test_status_is_str(self):
        assert isinstance(TaskStatus.pending, str)


class TestTask:
    def test_minimal_creation(self):
        task = Task(task_id="t1", title="Fix bug", description="Fix the login bug")
        assert task.task_id == "t1"
        assert task.title == "Fix bug"
        assert task.description == "Fix the login bug"
        assert task.status == TaskStatus.pending
        assert task.dependencies == []
        assert task.labels == {}
        assert task.source_ref == ""

    def test_full_creation(self):
        task = Task(
            task_id="t2",
            title="Add feature",
            description="Add dark mode",
            status=TaskStatus.in_progress,
            dependencies=["t1"],
            labels={"phase": "ui", "priority": "P1"},
            source_ref="worktree-v2-10",
        )
        assert task.task_id == "t2"
        assert task.status == TaskStatus.in_progress
        assert task.dependencies == ["t1"]
        assert task.labels == {"phase": "ui", "priority": "P1"}
        assert task.source_ref == "worktree-v2-10"

    def test_to_dict(self):
        task = Task(
            task_id="t1",
            title="Fix bug",
            description="Fix it",
            labels={"priority": "P0"},
        )
        data = task.to_dict()
        assert data == {
            "task_id": "t1",
            "title": "Fix bug",
            "description": "Fix it",
            "status": "pending",
            "dependencies": [],
            "labels": {"priority": "P0"},
            "source_ref": "",
        }

    def test_from_dict(self):
        data = {
            "task_id": "t1",
            "title": "Fix bug",
            "description": "Fix it",
            "status": "in_progress",
            "dependencies": ["t0"],
            "labels": {"phase": "core"},
            "source_ref": "bead-123",
        }
        task = Task.from_dict(data)
        assert task.task_id == "t1"
        assert task.status == TaskStatus.in_progress
        assert task.dependencies == ["t0"]
        assert task.labels == {"phase": "core"}
        assert task.source_ref == "bead-123"

    def test_from_dict_minimal(self):
        data = {"task_id": "t1", "title": "Do thing", "description": "Do it"}
        task = Task.from_dict(data)
        assert task.status == TaskStatus.pending
        assert task.dependencies == []
        assert task.labels == {}
        assert task.source_ref == ""

    def test_serialization_roundtrip(self):
        original = Task(
            task_id="t1",
            title="Fix bug",
            description="Fix the login",
            status=TaskStatus.completed,
            dependencies=["t0"],
            labels={"phase": "auth"},
            source_ref="bead-42",
        )
        restored = Task.from_dict(original.to_dict())
        assert restored == original

    def test_is_blocked_no_deps(self):
        task = Task(task_id="t1", title="No deps", description="")
        assert not task.is_blocked(set())

    def test_is_blocked_with_completed_deps(self):
        task = Task(task_id="t2", title="Has deps", description="", dependencies=["t1"])
        completed = {"t1"}
        assert not task.is_blocked(completed)

    def test_is_blocked_with_incomplete_deps(self):
        task = Task(
            task_id="t3", title="Blocked", description="", dependencies=["t1", "t2"]
        )
        completed = {"t1"}
        assert task.is_blocked(completed)


class TestTaskSourceABC:
    """Test that TaskSource enforces the interface via ABC."""

    def test_subclass_is_instance(self):
        from superintendent.orchestrator.sources.protocol import TaskSource

        class ValidSource(TaskSource):
            def get_tasks(self) -> list[Task]:
                return []

            def get_ready_tasks(self) -> list[Task]:
                return []

            def update_status(self, _task_id: str, _status: TaskStatus) -> None:
                pass

            def claim_task(self, _task_id: str) -> bool:
                return True

        source = ValidSource()
        assert isinstance(source, TaskSource)

    def test_incomplete_subclass_cannot_instantiate(self):
        import pytest

        from superintendent.orchestrator.sources.protocol import TaskSource

        class IncompleteSource(TaskSource):
            def get_tasks(self) -> list[Task]:
                return []

        with pytest.raises(TypeError):
            IncompleteSource()  # type: ignore[abstract]

    def test_concrete_sources_are_subclasses(self):
        from superintendent.orchestrator.sources.beads import BeadsSource
        from superintendent.orchestrator.sources.markdown import MarkdownSource
        from superintendent.orchestrator.sources.protocol import TaskSource
        from superintendent.orchestrator.sources.single import SingleTaskSource

        assert issubclass(BeadsSource, TaskSource)
        assert issubclass(MarkdownSource, TaskSource)
        assert issubclass(SingleTaskSource, TaskSource)
