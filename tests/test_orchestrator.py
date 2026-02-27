"""Tests for the Orchestrator: multi-agent spawn, monitor, and completion."""

import asyncio
from pathlib import Path

from superintendent.backends.auth import MockAuthBackend
from superintendent.backends.docker import MockDockerBackend
from superintendent.backends.factory import Backends
from superintendent.backends.git import MockGitBackend
from superintendent.backends.terminal import MockTerminalBackend
from superintendent.orchestrator.models import Mode, Target
from superintendent.orchestrator.orchestrator import (
    _AGENT_STATUS_CMD,
    AgentHandle,
    AgentStatus,
    FailurePolicy,
    Orchestrator,
    OrchestratorResult,
    _PendingGroup,
)
from superintendent.orchestrator.reporter import MockReporter
from superintendent.orchestrator.sources.models import Task, TaskStatus
from superintendent.orchestrator.sources.protocol import TaskSource
from superintendent.orchestrator.strategy import ExecutionDecision, TaskInfo


def _mock_backends(**overrides) -> Backends:
    """Create a Backends container with all-mock implementations."""
    return Backends(
        docker=overrides.get("docker", MockDockerBackend()),
        git=overrides.get("git", MockGitBackend()),
        terminal=overrides.get("terminal", MockTerminalBackend()),
        auth=overrides.get("auth", MockAuthBackend()),
    )


def _decision(
    task_groups: list[list[TaskInfo]],
    target: Target = Target.sandbox,
    mode: Mode = Mode.autonomous,
    parallelism: int = 3,
) -> ExecutionDecision:
    """Helper to create an ExecutionDecision."""
    return ExecutionDecision(
        mode=mode,
        target=target,
        parallelism=parallelism,
        task_groups=task_groups,
    )


class MockTaskSource(TaskSource):
    """Simple mock task source for testing newly-unblocked tasks."""

    source_name = "mock"

    def __init__(
        self,
        tasks: list[Task] | None = None,
        ready_tasks: list[Task] | None = None,
    ) -> None:
        self._tasks = tasks or []
        self._ready_tasks = ready_tasks or []
        self.status_updates: list[tuple[str, TaskStatus]] = []
        self.claims: list[str] = []

    def get_tasks(self) -> list[Task]:
        return self._tasks

    def get_ready_tasks(self) -> list[Task]:
        return self._ready_tasks

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        self.status_updates.append((task_id, status))

    def claim_task(self, task_id: str) -> bool:
        self.claims.append(task_id)
        return True


class TestOrchestratorBasic:
    """Basic orchestrator spawn and completion tests."""

    def test_single_group_completes(self, tmp_path: Path) -> None:
        """A single task group spawns one agent and completes."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=3,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert result.completed_tasks == ["task-1"]
        assert result.failed_tasks == []
        assert result.skipped_tasks == []
        assert result.agents_spawned == 1
        assert result.errors == []
        assert result.total_time_seconds >= 0

    def test_multiple_groups_all_complete(self, tmp_path: Path) -> None:
        """Multiple independent groups all complete successfully."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision(
            [
                [TaskInfo(name="task-1")],
                [TaskInfo(name="task-2")],
                [TaskInfo(name="task-3")],
            ]
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=3,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert sorted(result.completed_tasks) == ["task-1", "task-2", "task-3"]
        assert result.failed_tasks == []
        assert result.agents_spawned == 3

    def test_group_with_multiple_tasks(self, tmp_path: Path) -> None:
        """A group with multiple tasks marks all as completed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        reporter = MockReporter()

        decision = _decision(
            [
                [TaskInfo(name="task-a"), TaskInfo(name="task-b")],
            ]
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=3,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert sorted(result.completed_tasks) == ["task-a", "task-b"]
        assert result.agents_spawned == 1

    def test_empty_decision(self, tmp_path: Path) -> None:
        """An empty decision with no task groups returns immediately."""
        repo_path = tmp_path / "my-repo"
        backends = _mock_backends()
        reporter = MockReporter()

        decision = _decision([])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert result.completed_tasks == []
        assert result.failed_tasks == []
        assert result.agents_spawned == 0


class TestOrchestratorParallelism:
    """Tests that parallelism limits are respected."""

    def test_respects_max_parallel(self, tmp_path: Path) -> None:
        """With max_parallel=2 and 3 groups, at most 2 spawn at once."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision(
            [
                [TaskInfo(name="task-1")],
                [TaskInfo(name="task-2")],
                [TaskInfo(name="task-3")],
            ]
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=2,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        # All tasks eventually complete
        assert sorted(result.completed_tasks) == ["task-1", "task-2", "task-3"]
        assert result.agents_spawned == 3

        # Check progress events to verify parallelism was bounded
        # With mock backends, agents complete immediately, so we see
        # the progress updates after each batch
        progress_events = [e for e in reporter.events if e.event_type == "progress"]
        for event in progress_events:
            # running count should never exceed max_parallel
            assert event.data["running"] <= 2

    def test_max_parallel_one_serializes(self, tmp_path: Path) -> None:
        """With max_parallel=1, agents run one at a time."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision(
            [
                [TaskInfo(name="task-1")],
                [TaskInfo(name="task-2")],
            ]
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=1,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert sorted(result.completed_tasks) == ["task-1", "task-2"]
        assert result.agents_spawned == 2

        # Verify serialized: started events for agent-1 and agent-2
        started_events = [e for e in reporter.events if e.event_type == "started"]
        assert len(started_events) == 2


class TestOrchestratorFailureSkip:
    """Tests for FailurePolicy.SKIP (default)."""

    def test_spawn_failure_records_error(self, tmp_path: Path) -> None:
        """If Executor fails to start agent, tasks are marked as failed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(fail_on="create_sandbox")
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
            failure_policy=FailurePolicy.SKIP,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert result.completed_tasks == []
        assert result.failed_tasks == ["task-1"]
        assert result.agents_spawned == 0
        assert len(result.errors) == 1

    def test_skip_continues_other_groups(self, tmp_path: Path) -> None:
        """With SKIP, failure in one group doesn't block other groups."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        # Agent fails for sandbox names containing "agent-1"
        # We use exec_results to simulate agent failure
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        # Two groups - first will "fail" (agent exits with code 1),
        # but with mock exec_results applying to ALL agents,
        # both will fail. Let's test spawn failure instead.
        decision = _decision(
            [
                [TaskInfo(name="task-1")],
                [TaskInfo(name="task-2")],
            ]
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=3,
            poll_interval=0,
            failure_policy=FailurePolicy.SKIP,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        # Both agents spawned, both failed (exec_results says exit code 1)
        assert result.agents_spawned == 2
        assert sorted(result.failed_tasks) == ["task-1", "task-2"]
        assert result.completed_tasks == []

    def test_agent_runtime_failure_skip(self, tmp_path: Path) -> None:
        """Agent that fails at runtime is recorded with SKIP policy."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
            failure_policy=FailurePolicy.SKIP,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert result.completed_tasks == []
        assert result.failed_tasks == ["task-1"]
        assert result.agents_spawned == 1
        assert len(result.errors) == 1

        # Verify failure was reported
        failed_events = [e for e in reporter.events if e.event_type == "failed"]
        assert len(failed_events) == 1


class TestOrchestratorFailureAbort:
    """Tests for FailurePolicy.ABORT."""

    def test_abort_skips_pending_tasks(self, tmp_path: Path) -> None:
        """With ABORT, remaining pending tasks are marked as skipped."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision(
            [
                [TaskInfo(name="task-1")],
                [TaskInfo(name="task-2")],
                [TaskInfo(name="task-3")],
            ]
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=1,  # serialize so abort takes effect
            poll_interval=0,
            failure_policy=FailurePolicy.ABORT,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        # First agent spawns and fails → abort
        assert result.failed_tasks == ["task-1"]
        assert sorted(result.skipped_tasks) == ["task-2", "task-3"]
        assert result.agents_spawned == 1


class TestOrchestratorFailureRetry:
    """Tests for FailurePolicy.RETRY."""

    def test_retry_re_enqueues_failed_group(self, tmp_path: Path) -> None:
        """With RETRY, a failed group is re-enqueued and retried."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        # Agent always fails (exit code 1)
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=3,
            poll_interval=0,
            failure_policy=FailurePolicy.RETRY,
            max_retries=2,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        # Agent spawned initially + 2 retries = 3 total spawns
        assert result.agents_spawned == 3
        # After all retries exhausted, task is failed
        assert result.failed_tasks == ["task-1"]
        assert len(result.errors) == 1

    def test_retry_exhausted_then_fails(self, tmp_path: Path) -> None:
        """After max_retries exhausted, task is marked as failed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            max_parallel=3,
            poll_interval=0,
            failure_policy=FailurePolicy.RETRY,
            max_retries=1,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        # Initial + 1 retry = 2 spawns
        assert result.agents_spawned == 2
        assert result.failed_tasks == ["task-1"]


class TestOrchestratorAgentStatus:
    """Tests for _check_agent_status."""

    def test_local_target_always_completed(self, tmp_path: Path) -> None:
        """Local agents are considered completed immediately."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        reporter = MockReporter()

        decision = _decision(
            [[TaskInfo(name="task-1")]],
            target=Target.local,
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert result.completed_tasks == ["task-1"]
        assert result.agents_spawned == 1

    def test_sandbox_agent_status_completed(self) -> None:
        """Sandbox agent returns COMPLETED when exec returns (0, '')."""
        backends = _mock_backends()

        orch = Orchestrator(backends=backends, poll_interval=0)
        handle = AgentHandle(
            id="test-1",
            task_group=[TaskInfo(name="t")],
            sandbox_name="sb-1",
        )

        # Default mock exec returns (0, "")
        status = orch._check_agent_status(handle, Target.sandbox)
        assert status == AgentStatus.COMPLETED

    def test_sandbox_agent_status_running(self) -> None:
        """Sandbox agent returns RUNNING when exec returns non-zero."""
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (1, "")})
        backends = _mock_backends(docker=docker)

        orch = Orchestrator(backends=backends, poll_interval=0)
        handle = AgentHandle(
            id="test-1",
            task_group=[TaskInfo(name="t")],
            sandbox_name="sb-1",
        )

        status = orch._check_agent_status(handle, Target.sandbox)
        assert status == AgentStatus.RUNNING

    def test_sandbox_agent_status_failed(self) -> None:
        """Sandbox agent returns FAILED when exec returns (0, '1')."""
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(docker=docker)

        orch = Orchestrator(backends=backends, poll_interval=0)
        handle = AgentHandle(
            id="test-1",
            task_group=[TaskInfo(name="t")],
            sandbox_name="sb-1",
        )

        status = orch._check_agent_status(handle, Target.sandbox)
        assert status == AgentStatus.FAILED

    def test_no_sandbox_name_returns_completed(self) -> None:
        """Handle with no sandbox_name returns COMPLETED."""
        backends = _mock_backends()
        orch = Orchestrator(backends=backends, poll_interval=0)
        handle = AgentHandle(
            id="test-1",
            task_group=[TaskInfo(name="t")],
            sandbox_name=None,
        )

        status = orch._check_agent_status(handle, Target.sandbox)
        assert status == AgentStatus.COMPLETED


class TestOrchestratorReporter:
    """Tests that reporter receives correct events."""

    def test_reporter_receives_started_event(self, tmp_path: Path) -> None:
        """Reporter.on_agent_started called when agent spawns."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
        )
        asyncio.run(orch.run(decision, repo=str(repo_path)))

        started = [e for e in reporter.events if e.event_type == "started"]
        assert len(started) == 1
        assert started[0].data["task_names"] == ["task-1"]
        assert started[0].data["sandbox_name"] is not None

    def test_reporter_receives_completed_event(self, tmp_path: Path) -> None:
        """Reporter.on_agent_completed called on success."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
        )
        asyncio.run(orch.run(decision, repo=str(repo_path)))

        completed = [e for e in reporter.events if e.event_type == "completed"]
        assert len(completed) == 1
        assert completed[0].data["task_names"] == ["task-1"]

    def test_reporter_receives_failed_event(self, tmp_path: Path) -> None:
        """Reporter.on_agent_failed called on failure."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
            failure_policy=FailurePolicy.SKIP,
        )
        asyncio.run(orch.run(decision, repo=str(repo_path)))

        failed = [e for e in reporter.events if e.event_type == "failed"]
        assert len(failed) == 1

    def test_reporter_receives_progress_events(self, tmp_path: Path) -> None:
        """Reporter.on_progress called during each loop iteration."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        reporter = MockReporter()

        decision = _decision(
            [
                [TaskInfo(name="task-1")],
                [TaskInfo(name="task-2")],
            ]
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            max_parallel=3,
            poll_interval=0,
        )
        asyncio.run(orch.run(decision, repo=str(repo_path)))

        progress = [e for e in reporter.events if e.event_type == "progress"]
        assert len(progress) >= 1

    def test_reporter_summarize_called(self, tmp_path: Path) -> None:
        """Reporter.summarize is called at the end of orchestration."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        reporter = MockReporter()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
        )
        asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert len(reporter.summaries) == 1


class TestOrchestratorTaskSource:
    """Tests for task source integration and newly-unblocked tasks."""

    def test_task_source_updated_on_success(self, tmp_path: Path) -> None:
        """Task source receives status updates when tasks complete."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        task_source = MockTaskSource()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            task_source=task_source,
            poll_interval=0,
        )
        asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert ("task-1", TaskStatus.completed) in task_source.status_updates

    def test_task_source_updated_on_failure(self, tmp_path: Path) -> None:
        """Task source receives failed status when agent fails."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)
        task_source = MockTaskSource()

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            task_source=task_source,
            poll_interval=0,
            failure_policy=FailurePolicy.SKIP,
        )
        asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert ("task-1", TaskStatus.failed) in task_source.status_updates

    def test_newly_unblocked_tasks_spawned(self, tmp_path: Path) -> None:
        """When tasks complete, newly-unblocked tasks from source are spawned."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)

        # After task-1 completes, task-source reports task-2 as ready
        new_task = Task(
            task_id="task-2",
            title="New task",
            description="Unblocked task",
            status=TaskStatus.pending,
        )
        task_source = MockTaskSource(ready_tasks=[new_task])

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            task_source=task_source,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert "task-1" in result.completed_tasks
        assert "task-2" in result.completed_tasks
        # Two agents spawned: one for task-1, one for newly-unblocked task-2
        assert result.agents_spawned == 2

    def test_already_known_tasks_not_re_spawned(self, tmp_path: Path) -> None:
        """Tasks already in the decision are not re-spawned."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)

        # Task source returns task-1 as ready (but we're already running it)
        existing_task = Task(
            task_id="task-1",
            title="Already running",
            description="Already in the decision",
            status=TaskStatus.pending,
        )
        task_source = MockTaskSource(ready_tasks=[existing_task])

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            task_source=task_source,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        # Only one agent spawned — task-1 was not duplicated
        assert result.agents_spawned == 1
        assert result.completed_tasks == ["task-1"]


class TestOrchestratorResult:
    """Tests for OrchestratorResult contents."""

    def test_result_captures_timing(self, tmp_path: Path) -> None:
        """Result total_time_seconds is populated."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert result.total_time_seconds >= 0

    def test_result_errors_list(self, tmp_path: Path) -> None:
        """Errors are recorded in the result."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(exec_results={_AGENT_STATUS_CMD: (0, "1")})
        backends = _mock_backends(git=git, docker=docker)

        decision = _decision([[TaskInfo(name="task-1")]])

        orch = Orchestrator(
            backends=backends,
            poll_interval=0,
            failure_policy=FailurePolicy.SKIP,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert len(result.errors) == 1
        assert "agent-1" in result.errors[0].lower()


class TestOrchestratorContainerTarget:
    """Tests for container target type."""

    def test_container_target_completes(self, tmp_path: Path) -> None:
        """Container target works through the full pipeline."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        reporter = MockReporter()

        decision = _decision(
            [[TaskInfo(name="task-1")]],
            target=Target.container,
        )

        orch = Orchestrator(
            backends=backends,
            reporter=reporter,
            poll_interval=0,
        )
        result = asyncio.run(orch.run(decision, repo=str(repo_path)))

        assert result.completed_tasks == ["task-1"]
        assert result.agents_spawned == 1
        # Verify container was created (not sandbox)
        assert len(docker.containers_created) == 1
        assert len(docker.created) == 0


class TestOrchestratorModels:
    """Tests for data models."""

    def test_agent_handle_defaults(self) -> None:
        handle = AgentHandle(id="a1", task_group=[])
        assert handle.sandbox_name is None
        assert handle.started_at is None
        assert handle.execution_result is None
        assert handle.retry_count == 0

    def test_orchestrator_result_defaults(self) -> None:
        result = OrchestratorResult()
        assert result.completed_tasks == []
        assert result.failed_tasks == []
        assert result.skipped_tasks == []
        assert result.agents_spawned == 0
        assert result.prs_created == []
        assert result.total_time_seconds == 0.0
        assert result.errors == []

    def test_failure_policy_values(self) -> None:
        assert FailurePolicy.RETRY == "retry"
        assert FailurePolicy.SKIP == "skip"
        assert FailurePolicy.ABORT == "abort"

    def test_agent_status_values(self) -> None:
        assert AgentStatus.RUNNING == "running"
        assert AgentStatus.COMPLETED == "completed"
        assert AgentStatus.FAILED == "failed"

    def test_pending_group_defaults(self) -> None:
        pg = _PendingGroup(tasks=[TaskInfo(name="t")])
        assert pg.retry_count == 0
