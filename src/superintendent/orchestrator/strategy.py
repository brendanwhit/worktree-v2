"""ExecutionStrategy: decides HOW to run tasks based on task characteristics and repo context."""

from dataclasses import dataclass, field
from enum import StrEnum

from superintendent.orchestrator.models import Mode, Target
from superintendent.orchestrator.repo_info import RepoInfo


class GroupStrategy(StrEnum):
    """Strategy for grouping tasks for parallel execution."""

    BY_INDEPENDENCE = "by_independence"
    BY_LABEL = "by_label"
    SINGLE = "single"


@dataclass
class TaskInfo:
    """Lightweight task descriptor for strategy decisions.

    This is the minimal info the strategy needs to make decisions.
    The full Task model lives in the TaskSource abstraction (Epic 26).
    """

    name: str
    is_destructive: bool = False
    complexity: str = "simple"  # simple, moderate, complex
    depends_on: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass
class ExecutionDecision:
    """The result of an execution strategy decision."""

    mode: Mode
    target: Target
    parallelism: int = 1
    reasoning: str = ""
    task_groups: list[list[TaskInfo]] = field(default_factory=list)


# Complexity weights for mode decision scoring
_COMPLEXITY_WEIGHTS = {
    "simple": 1,
    "moderate": 2,
    "complex": 4,
}

# Threshold above which total complexity triggers interactive mode
_INTERACTIVE_COMPLEXITY_THRESHOLD = 6

# Default maximum parallel agents
_DEFAULT_MAX_PARALLEL = 8


class ExecutionStrategy:
    """Decides how to run tasks based on task characteristics and repo context.

    Determines:
    - mode: interactive vs autonomous
    - target: local vs container vs sandbox
    - parallelism: how many concurrent agents
    - task_groups: how tasks are grouped for parallel execution
    """

    def __init__(self, max_parallel_agents: int = _DEFAULT_MAX_PARALLEL) -> None:
        self.max_parallel_agents = max_parallel_agents

    def decide(
        self,
        tasks: list[TaskInfo],
        repo: RepoInfo,
        *,
        mode_override: Mode | None = None,
        target_override: Target | None = None,
        parallelism_override: int | None = None,
    ) -> ExecutionDecision:
        """Decide how to execute the given tasks in the given repo context."""
        reasons: list[str] = []

        # Determine mode
        mode = self._decide_mode(tasks, reasons)
        if mode_override is not None:
            mode = mode_override
            reasons.append(f"Mode overridden to {mode.value}")

        # Determine target
        target = self._decide_target(repo, reasons)
        if target_override is not None:
            target = target_override
            reasons.append(f"Target overridden to {target.value}")

        # Group tasks and determine parallelism
        task_groups = self._group_tasks(tasks)
        parallelism = min(len(task_groups), self.max_parallel_agents)
        if parallelism_override is not None:
            parallelism = parallelism_override
            reasons.append(f"Parallelism overridden to {parallelism}")

        return ExecutionDecision(
            mode=mode,
            target=target,
            parallelism=parallelism,
            reasoning="; ".join(reasons),
            task_groups=task_groups,
        )

    def explain(self, decision: ExecutionDecision) -> str:
        """Return a human-readable explanation of the decision."""
        lines = [
            f"Mode: {decision.mode.value}",
            f"Target: {decision.target.value}",
            f"Parallelism: {decision.parallelism}",
            f"Task groups: {len(decision.task_groups)}",
        ]
        if decision.reasoning:
            lines.append(f"Reasoning: {decision.reasoning}")
        return "\n".join(lines)

    def _decide_mode(
        self,
        tasks: list[TaskInfo],
        reasons: list[str],
    ) -> Mode:
        """Decide between interactive and autonomous mode."""
        # Any destructive task forces interactive
        if any(t.is_destructive for t in tasks):
            reasons.append("Destructive operations detected, using interactive mode")
            return Mode.interactive

        # High total complexity suggests interactive
        total_complexity = sum(_COMPLEXITY_WEIGHTS.get(t.complexity, 1) for t in tasks)
        if total_complexity >= _INTERACTIVE_COMPLEXITY_THRESHOLD:
            reasons.append(
                f"High total complexity ({total_complexity}), using interactive mode"
            )
            return Mode.interactive

        reasons.append("Tasks are well-scoped, using autonomous mode")
        return Mode.autonomous

    def _decide_target(
        self,
        repo: RepoInfo,
        reasons: list[str],
    ) -> Target:
        """Decide between local, container, and sandbox targets."""
        # Auth/secrets needs → sandbox (highest priority)
        if repo.needs_auth or repo.has_env_file:
            reason_parts = []
            if repo.needs_auth:
                reason_parts.append("auth requirements")
            if repo.has_env_file:
                reason_parts.append("environment files")
            reasons.append(
                f"Detected {' and '.join(reason_parts)}, using sandbox for persistent auth"
            )
            return Target.sandbox

        # Dockerfile/devcontainer → container
        if repo.has_dockerfile or repo.has_devcontainer:
            reasons.append(
                "Detected container configuration, using container for isolation"
            )
            return Target.container

        # Default → local
        reasons.append("No special requirements, using local execution")
        return Target.local

    def _group_tasks(self, tasks: list[TaskInfo]) -> list[list[TaskInfo]]:
        """Group tasks by independence for parallel execution.

        Tasks that depend on each other are placed in the same group.
        Independent tasks each get their own group.
        """
        if not tasks:
            return []

        task_by_name: dict[str, TaskInfo] = {t.name: t for t in tasks}

        # Build adjacency: union-find to group connected tasks
        parent: dict[str, str] = {t.name: t.name for t in tasks}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Union tasks that have dependency relationships
        for task in tasks:
            for dep_name in task.depends_on:
                if dep_name in task_by_name:
                    union(task.name, dep_name)

        # Collect groups
        groups: dict[str, list[TaskInfo]] = {}
        for task in tasks:
            root = find(task.name)
            if root not in groups:
                groups[root] = []
            groups[root].append(task)

        return list(groups.values())
