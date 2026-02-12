"""Executor: runs a WorkflowPlan step by step, managing state transitions."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from superintendent.orchestrator.models import WorkflowPlan, WorkflowStep
from superintendent.state.workflow import (
    WORKFLOW_ORDER,
    WorkflowState,
    valid_transition,
)


@runtime_checkable
class StepHandler(Protocol):
    """Protocol for step execution handlers."""

    def execute(self, step: WorkflowStep) -> "StepResult": ...


@dataclass
class StepResult:
    """Result of executing a single workflow step."""

    success: bool
    step_id: str
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of executing an entire workflow plan."""

    state: WorkflowState
    completed_steps: list[str] = field(default_factory=list)
    failed_step: str | None = None
    error: str | None = None
    step_results: dict[str, StepResult] = field(default_factory=dict)


# Map from step action to the workflow state entered when running that action.
_ACTION_TO_STATE: dict[str, WorkflowState] = {
    "validate_repo": WorkflowState.ENSURING_REPO,
    "create_worktree": WorkflowState.CREATING_WORKTREE,
    "prepare_sandbox": WorkflowState.PREPARING_SANDBOX,
    "authenticate": WorkflowState.AUTHENTICATING,
    "initialize_state": WorkflowState.INITIALIZING_STATE,
    "start_agent": WorkflowState.STARTING_AGENT,
}


class Executor:
    """Runs a WorkflowPlan through backends, managing state and checkpoints."""

    def __init__(self, handler: StepHandler | None = None) -> None:
        self._handler = handler
        self._state = WorkflowState.INIT
        self._checkpoints: list[dict[str, Any]] = []

    @property
    def state(self) -> WorkflowState:
        return self._state

    @property
    def checkpoints(self) -> list[dict[str, Any]]:
        return list(self._checkpoints)

    def _transition(self, target: WorkflowState) -> None:
        """Transition to target state, advancing through intermediates if needed.

        In local mode, some states (PREPARING_SANDBOX, AUTHENTICATING) are
        skipped. Rather than requiring the plan to know about the state machine,
        the executor walks forward through the linear order to reach the target.
        """
        if valid_transition(self._state, target):
            self._state = target
            return

        # Try to advance through intermediate states to reach target
        current_idx = (
            WORKFLOW_ORDER.index(self._state) if self._state in WORKFLOW_ORDER else -1
        )
        target_idx = WORKFLOW_ORDER.index(target) if target in WORKFLOW_ORDER else -1

        if current_idx >= 0 and target_idx > current_idx:
            # Walk forward through intermediate states
            for i in range(current_idx + 1, target_idx + 1):
                self._state = WORKFLOW_ORDER[i]
            return

        raise InvalidTransitionError(
            f"Cannot transition from {self._state.name} to {target.name}"
        )

    def _save_checkpoint(
        self,
        step: WorkflowStep,
        result: StepResult,
        completed: list[str],
    ) -> None:
        self._checkpoints.append(
            {
                "step_id": step.id,
                "state": self._state.name,
                "success": result.success,
                "completed_steps": list(completed),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def run(self, plan: WorkflowPlan) -> ExecutionResult:
        """Execute all steps in the plan in topological order."""
        errors = plan.validate()
        if errors:
            return ExecutionResult(
                state=WorkflowState.FAILED,
                error=f"Invalid plan: {'; '.join(errors)}",
            )

        if self._handler is None:
            return ExecutionResult(
                state=WorkflowState.FAILED,
                error="No step handler configured",
            )

        ordered_steps = plan.execution_order()
        result = ExecutionResult(state=WorkflowState.INIT)

        for step in ordered_steps:
            # Transition to the appropriate state for this action
            target_state = _ACTION_TO_STATE.get(step.action)
            if target_state is None:
                result.state = WorkflowState.FAILED
                result.failed_step = step.id
                result.error = f"Unknown action: {step.action}"
                self._transition(WorkflowState.FAILED)
                return result

            try:
                self._transition(target_state)
            except InvalidTransitionError as e:
                result.state = WorkflowState.FAILED
                result.failed_step = step.id
                result.error = str(e)
                self._state = WorkflowState.FAILED
                return result

            # Execute the step
            step_result = self._handler.execute(step)
            result.step_results[step.id] = step_result
            self._save_checkpoint(step, step_result, result.completed_steps)

            if step_result.success:
                result.completed_steps.append(step.id)
            else:
                self._transition(WorkflowState.FAILED)
                result.state = WorkflowState.FAILED
                result.failed_step = step.id
                result.error = step_result.message
                return result

        # All steps completed — transition through final states
        if self._state == WorkflowState.STARTING_AGENT:
            self._transition(WorkflowState.AGENT_RUNNING)

        result.state = self._state
        return result


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
