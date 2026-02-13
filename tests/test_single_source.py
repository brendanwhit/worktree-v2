"""Tests for SingleTaskSource adapter."""

from superintendent.orchestrator.sources.models import TaskStatus
from superintendent.orchestrator.sources.single import SingleTaskSource


class TestSingleTaskSource:
    def test_get_tasks_returns_one_task(self):
        source = SingleTaskSource("fix the login bug")
        tasks = source.get_tasks()
        assert len(tasks) == 1

    def test_task_has_description(self):
        source = SingleTaskSource("fix the login bug")
        task = source.get_tasks()[0]
        assert task.description == "fix the login bug"

    def test_task_has_title(self):
        source = SingleTaskSource("fix the login bug")
        task = source.get_tasks()[0]
        assert task.title == "fix the login bug"

    def test_task_has_generated_id(self):
        source = SingleTaskSource("fix the login bug")
        task = source.get_tasks()[0]
        assert task.task_id
        assert isinstance(task.task_id, str)

    def test_task_starts_pending(self):
        source = SingleTaskSource("fix the login bug")
        task = source.get_tasks()[0]
        assert task.status == TaskStatus.pending

    def test_task_has_no_dependencies(self):
        source = SingleTaskSource("fix the login bug")
        task = source.get_tasks()[0]
        assert task.dependencies == []

    def test_task_has_source_ref(self):
        source = SingleTaskSource("fix the login bug")
        task = source.get_tasks()[0]
        assert task.source_ref == "single"

    def test_get_ready_tasks_returns_the_task(self):
        source = SingleTaskSource("do something")
        ready = source.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].description == "do something"

    def test_update_status_is_noop(self):
        """SingleTaskSource is ephemeral — status updates are no-ops."""
        source = SingleTaskSource("do something")
        task = source.get_tasks()[0]
        # Should not raise
        source.update_status(task.task_id, TaskStatus.completed)
        # Status in source doesn't change (ephemeral)

    def test_claim_task_returns_true(self):
        source = SingleTaskSource("do something")
        task = source.get_tasks()[0]
        assert source.claim_task(task.task_id) is True

    def test_custom_task_id(self):
        source = SingleTaskSource("do something", task_id="custom-1")
        task = source.get_tasks()[0]
        assert task.task_id == "custom-1"

    def test_stable_task_id(self):
        """Same source should return the same task ID each time."""
        source = SingleTaskSource("do something")
        id1 = source.get_tasks()[0].task_id
        id2 = source.get_tasks()[0].task_id
        assert id1 == id2
