"""Tests for the Executor."""

from superintendent.orchestrator.executor import (
    Executor,
    InvalidTransitionError,
    StepResult,
)
from superintendent.orchestrator.models import WorkflowPlan, WorkflowStep
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.state.workflow import WorkflowState


class MockHandler:
    """A configurable mock step handler for testing."""

    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on
        self.executed: list[str] = []

    def execute(self, step: WorkflowStep) -> StepResult:
        self.executed.append(step.id)
        if step.id == self.fail_on:
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Simulated failure on {step.id}",
            )
        return StepResult(success=True, step_id=step.id)


class TestExecutor:
    def _sandbox_plan(self) -> WorkflowPlan:
        return Planner().create_plan(PlannerInput(repo="/test/repo", task="test task"))

    def _local_plan(self) -> WorkflowPlan:
        return Planner().create_plan(
            PlannerInput(repo="/test/repo", task="test task", target="local")
        )

    def test_successful_sandbox_execution(self):
        handler = MockHandler()
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        result = executor.run(plan)

        assert result.state == WorkflowState.AGENT_RUNNING
        assert result.failed_step is None
        assert result.error is None
        assert len(result.completed_steps) == 6
        assert result.completed_steps == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
            "authenticate",
            "initialize_state",
            "start_agent",
        ]

    def test_successful_local_execution(self):
        handler = MockHandler()
        executor = Executor(handler=handler)
        plan = self._local_plan()
        result = executor.run(plan)

        assert result.state == WorkflowState.AGENT_RUNNING
        assert len(result.completed_steps) == 4

    def test_failure_stops_execution(self):
        handler = MockHandler(fail_on="prepare_sandbox")
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "prepare_sandbox"
        assert "Simulated failure" in result.error
        assert result.completed_steps == ["validate_repo", "create_worktree"]

    def test_failure_on_first_step(self):
        handler = MockHandler(fail_on="validate_repo")
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "validate_repo"
        assert result.completed_steps == []

    def test_handler_sees_all_steps(self):
        handler = MockHandler()
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        executor.run(plan)

        assert handler.executed == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
            "authenticate",
            "initialize_state",
            "start_agent",
        ]

    def test_handler_stops_after_failure(self):
        handler = MockHandler(fail_on="authenticate")
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        executor.run(plan)

        assert handler.executed == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
            "authenticate",
        ]

    def test_no_handler_returns_failed(self):
        executor = Executor()
        plan = self._sandbox_plan()
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert "No step handler" in result.error

    def test_invalid_plan_returns_failed(self):
        handler = MockHandler()
        executor = Executor(handler=handler)
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="a", depends_on=["s2"]),
                WorkflowStep(id="s2", action="b", depends_on=["s1"]),
            ]
        )
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert "Invalid plan" in result.error

    def test_step_results_recorded(self):
        handler = MockHandler()
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        result = executor.run(plan)

        assert "validate_repo" in result.step_results
        assert result.step_results["validate_repo"].success is True
        assert len(result.step_results) == 6

    def test_step_results_on_failure(self):
        handler = MockHandler(fail_on="authenticate")
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        result = executor.run(plan)

        assert result.step_results["authenticate"].success is False
        assert len(result.step_results) == 4

    def test_checkpoints_saved(self):
        handler = MockHandler()
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        executor.run(plan)

        assert len(executor.checkpoints) == 6
        assert executor.checkpoints[0]["step_id"] == "validate_repo"
        assert executor.checkpoints[0]["success"] is True
        assert "timestamp" in executor.checkpoints[0]

    def test_state_property_tracks_current(self):
        handler = MockHandler()
        executor = Executor(handler=handler)
        assert executor.state == WorkflowState.INIT

        plan = self._sandbox_plan()
        executor.run(plan)
        assert executor.state == WorkflowState.AGENT_RUNNING

    def test_state_property_after_failure(self):
        handler = MockHandler(fail_on="create_worktree")
        executor = Executor(handler=handler)
        plan = self._sandbox_plan()
        executor.run(plan)
        assert executor.state == WorkflowState.FAILED


class TestInvalidTransitionError:
    def test_is_exception(self):
        assert issubclass(InvalidTransitionError, Exception)

    def test_message(self):
        err = InvalidTransitionError("bad transition")
        assert str(err) == "bad transition"
