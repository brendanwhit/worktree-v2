"""Orchestrator: spawns, monitors, and coordinates multiple agents in parallel.

Sits above the Executor layer. Takes an ExecutionDecision (from strategy)
and runs agents through the Planner -> Executor -> StepHandler -> Backends
pipeline, managing parallelism, monitoring, and failure handling.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from superintendent.backends.factory import Backends
from superintendent.orchestrator.executor import ExecutionResult, Executor
from superintendent.orchestrator.models import Target
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.orchestrator.reporter import MockReporter, Reporter
from superintendent.orchestrator.sources.models import TaskStatus
from superintendent.orchestrator.sources.protocol import TaskSource
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.orchestrator.strategy import ExecutionDecision, TaskInfo
from superintendent.state.workflow import WorkflowState


class FailurePolicy(StrEnum):
    """Policy for handling agent failures."""

    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"


class AgentStatus(StrEnum):
    """Current status of a monitored agent."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentHandle:
    """Tracks a running agent."""

    id: str
    task_group: list[TaskInfo]
    sandbox_name: str | None = None
    started_at: datetime | None = None
    execution_result: ExecutionResult | None = None
    retry_count: int = 0


@dataclass
class OrchestratorResult:
    """Final result of an orchestration run."""

    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    skipped_tasks: list[str] = field(default_factory=list)
    agents_spawned: int = 0
    prs_created: list[str] = field(default_factory=list)
    total_time_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class _PendingGroup:
    """Internal: a task group waiting to be spawned."""

    tasks: list[TaskInfo]
    retry_count: int = 0


# Shell command to check if an agent process has completed.
# Returns 0 with exit code in stdout if done, returns 1 if still running.
_AGENT_STATUS_CMD = "test -f /tmp/.agent-done && cat /tmp/.agent-exit-code || exit 1"


class Orchestrator:
    """Spawns, monitors, and coordinates multiple agents in parallel.

    Takes an ExecutionDecision and manages the full lifecycle:
    spawn agents up to max_parallel, monitor for completion,
    handle successes/failures, detect newly-unblocked tasks,
    and report progress.
    """

    def __init__(
        self,
        backends: Backends,
        task_source: TaskSource | None = None,
        reporter: Reporter | None = None,
        max_parallel: int = 3,
        poll_interval: float = 5.0,
        failure_policy: FailurePolicy = FailurePolicy.SKIP,
        max_retries: int = 1,
    ) -> None:
        self._backends = backends
        self._task_source = task_source
        self._reporter: Reporter = reporter or MockReporter()
        self._max_parallel = max_parallel
        self._poll_interval = poll_interval
        self._failure_policy = failure_policy
        self._max_retries = max_retries
        self._planner = Planner()
        self._agent_counter = 0

    def _next_agent_id(self) -> str:
        """Generate a unique sequential agent ID."""
        self._agent_counter += 1
        return f"agent-{self._agent_counter}"

    async def run(self, decision: ExecutionDecision, repo: str) -> OrchestratorResult:
        """Run the full orchestration loop.

        Spawns agents for task groups (up to max_parallel concurrently),
        monitors their status, handles completions/failures, checks for
        newly-unblocked tasks, and returns a summary result.
        """
        start_time = datetime.now(UTC)
        pending = [_PendingGroup(tasks=list(g)) for g in decision.task_groups]
        running: dict[str, AgentHandle] = {}
        result = OrchestratorResult()
        completed_task_names: set[str] = set()
        all_task_names: set[str] = {
            t.name for group in decision.task_groups for t in group
        }
        aborted = False

        while (pending or running) and not aborted:
            # Spawn agents up to parallelism limit
            while pending and len(running) < self._max_parallel and not aborted:
                pg = pending.pop(0)
                handle = self._spawn_agent(pg, decision, repo)
                if handle:
                    running[handle.id] = handle
                    result.agents_spawned += 1
                    task_names = [t.name for t in pg.tasks]
                    self._reporter.on_agent_started(
                        handle.id,
                        task_names,
                        sandbox_name=handle.sandbox_name,
                    )
                else:
                    for task in pg.tasks:
                        result.failed_tasks.append(task.name)
                    result.errors.append(
                        f"Failed to spawn agent for: "
                        f"{', '.join(t.name for t in pg.tasks)}"
                    )

            if not running:
                break

            # Check status of all running agents
            done_agents: list[tuple[str, AgentStatus]] = []
            for agent_id, handle in running.items():
                status = self._check_agent_status(handle, decision.target)
                if status != AgentStatus.RUNNING:
                    done_agents.append((agent_id, status))

            # Process completed/failed agents
            for agent_id, status in done_agents:
                handle = running.pop(agent_id)
                task_names = [t.name for t in handle.task_group]
                duration = 0.0
                if handle.started_at:
                    duration = (datetime.now(UTC) - handle.started_at).total_seconds()

                if status == AgentStatus.COMPLETED:
                    self._handle_success(handle, result, completed_task_names)
                    self._reporter.on_agent_completed(agent_id, task_names, duration)
                    # Check for newly-unblocked tasks from task source
                    new_groups = self._find_newly_unblocked(all_task_names)
                    for ng in new_groups:
                        pending.append(_PendingGroup(tasks=ng))
                        for t in ng:
                            all_task_names.add(t.name)
                else:
                    error_msg = f"Agent {agent_id} failed"
                    self._reporter.on_agent_failed(agent_id, task_names, error_msg)
                    aborted = self._handle_failure(handle, result, pending)

            # Report progress
            self._reporter.on_progress(
                running=len(running),
                completed=len(result.completed_tasks),
                pending=sum(len(pg.tasks) for pg in pending),
                failed=len(result.failed_tasks),
            )

            if running:
                await asyncio.sleep(self._poll_interval)

        # Mark remaining pending tasks as skipped on abort
        if aborted:
            for pg in pending:
                for task in pg.tasks:
                    result.skipped_tasks.append(task.name)
            pending.clear()

        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        result.total_time_seconds = elapsed

        # Any tasks not accounted for are skipped
        accounted = (
            set(result.completed_tasks)
            | set(result.failed_tasks)
            | set(result.skipped_tasks)
        )
        for name in all_task_names:
            if name not in accounted:
                result.skipped_tasks.append(name)

        self._reporter.summarize(
            completed_tasks=result.completed_tasks,
            failed_tasks=result.failed_tasks,
            skipped_tasks=result.skipped_tasks,
            agents_spawned=result.agents_spawned,
            total_time_seconds=result.total_time_seconds,
            errors=result.errors,
        )

        return result

    def _spawn_agent(
        self,
        pg: "_PendingGroup",
        decision: ExecutionDecision,
        repo: str,
    ) -> AgentHandle | None:
        """Create a plan and run the executor to start an agent.

        Returns an AgentHandle if the agent started successfully, None on failure.
        """
        agent_id = self._next_agent_id()
        task_description = "; ".join(t.name for t in pg.tasks)
        sandbox_name = f"ralph-{agent_id}"

        plan_input = PlannerInput(
            repo=repo,
            task=task_description,
            mode=decision.mode.value,
            target=decision.target.value,
            sandbox_name=sandbox_name,
        )

        try:
            plan = self._planner.create_plan(plan_input)
        except ValueError:
            return None

        ctx = ExecutionContext(backends=self._backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)
        exec_result = executor.run(plan)

        if exec_result.state == WorkflowState.FAILED:
            return None

        return AgentHandle(
            id=agent_id,
            task_group=pg.tasks,
            sandbox_name=(sandbox_name if decision.target != Target.local else None),
            started_at=datetime.now(UTC),
            execution_result=exec_result,
            retry_count=pg.retry_count,
        )

    def _check_agent_status(self, handle: AgentHandle, target: Target) -> AgentStatus:
        """Poll the agent's environment to check if it has finished."""
        if target == Target.local or not handle.sandbox_name:
            # Local agents complete when the executor finishes
            return AgentStatus.COMPLETED

        exit_code, output = self._backends.docker.exec_in_sandbox(
            handle.sandbox_name, _AGENT_STATUS_CMD
        )

        if exit_code != 0:
            return AgentStatus.RUNNING

        # Agent is done — check its exit code
        output = output.strip()
        if output == "" or output == "0":
            return AgentStatus.COMPLETED
        return AgentStatus.FAILED

    def _handle_success(
        self,
        handle: AgentHandle,
        result: OrchestratorResult,
        completed_task_names: set[str],
    ) -> None:
        """Record successful agent completion and update task source."""
        for task in handle.task_group:
            result.completed_tasks.append(task.name)
            completed_task_names.add(task.name)
            if self._task_source:
                self._task_source.update_status(task.name, TaskStatus.completed)

    def _handle_failure(
        self,
        handle: AgentHandle,
        result: OrchestratorResult,
        pending: list["_PendingGroup"],
    ) -> bool:
        """Handle a failed agent. Returns True if orchestration should abort."""
        task_names = [t.name for t in handle.task_group]

        # Retry if policy allows and retries remaining
        if (
            self._failure_policy == FailurePolicy.RETRY
            and handle.retry_count < self._max_retries
        ):
            pending.append(
                _PendingGroup(
                    tasks=handle.task_group,
                    retry_count=handle.retry_count + 1,
                )
            )
            return False

        # Record as failed
        for task in handle.task_group:
            result.failed_tasks.append(task.name)
            if self._task_source:
                self._task_source.update_status(task.name, TaskStatus.failed)
        result.errors.append(
            f"Agent {handle.id} failed (tasks: {', '.join(task_names)})"
        )

        return self._failure_policy == FailurePolicy.ABORT

    def _find_newly_unblocked(
        self,
        known_task_names: set[str],
    ) -> list[list[TaskInfo]]:
        """Query task source for tasks that became unblocked."""
        if not self._task_source:
            return []

        ready_tasks = self._task_source.get_ready_tasks()
        new_tasks = [t for t in ready_tasks if t.task_id not in known_task_names]

        if not new_tasks:
            return []

        # Each newly-unblocked task gets its own group
        return [[TaskInfo(name=t.task_id)] for t in new_tasks]
