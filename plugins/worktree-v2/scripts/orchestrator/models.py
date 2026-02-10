"""WorkflowStep and WorkflowPlan models for the orchestrator."""

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Mode(StrEnum):
    interactive = "interactive"
    autonomous = "autonomous"


class Target(StrEnum):
    sandbox = "sandbox"
    container = "container"
    local = "local"


@dataclass
class WorkflowStep:
    """A single step in a workflow plan."""

    id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "params": self.params,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        return cls(
            id=data["id"],
            action=data["action"],
            params=data.get("params", {}),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class WorkflowPlan:
    """An ordered collection of workflow steps with metadata."""

    steps: list[WorkflowStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    _step_by_id: dict[str, WorkflowStep] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._step_by_id = {step.id: step for step in self.steps}

    def get_step(self, step_id: str) -> WorkflowStep | None:
        return self._step_by_id.get(step_id)

    def add_step(self, step: WorkflowStep) -> None:
        self.steps.append(step)
        self._step_by_id[step.id] = step

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty if valid)."""
        errors: list[str] = []

        # Check for duplicate IDs
        seen_ids: set[str] = set()
        for step in self.steps:
            if step.id in seen_ids:
                errors.append(f"Duplicate step ID: {step.id}")
            seen_ids.add(step.id)

        # Check for missing dependencies
        all_ids = {step.id for step in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in all_ids:
                    errors.append(f"Step '{step.id}' depends on unknown step '{dep}'")

        # Check for cycles
        if not errors:
            cycle = self._find_cycle()
            if cycle:
                errors.append(f"Dependency cycle detected: {' -> '.join(cycle)}")

        return errors

    def _find_cycle(self) -> list[str] | None:
        """Detect cycles using DFS. Returns cycle path or None."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {step.id: WHITE for step in self.steps}
        parent: dict[str, str | None] = {step.id: None for step in self.steps}

        def dfs(node: str) -> list[str] | None:
            color[node] = GRAY
            step = self._step_by_id[node]
            for dep in step.depends_on:
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    # Found cycle — reconstruct path
                    cycle = [dep, node]
                    current = node
                    while parent[current] is not None and parent[current] != dep:
                        current = parent[current]  # type: ignore[assignment]
                        cycle.append(current)
                    cycle.reverse()
                    return cycle
                if color[dep] == WHITE:
                    parent[dep] = node
                    result = dfs(dep)
                    if result:
                        return result
            color[node] = BLACK
            return None

        for step in self.steps:
            if color[step.id] == WHITE:
                result = dfs(step.id)
                if result:
                    return result
        return None

    def execution_order(self) -> list[WorkflowStep]:
        """Return steps in topological order (dependencies first)."""
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid plan: {'; '.join(errors)}")

        in_degree: dict[str, int] = {step.id: 0 for step in self.steps}
        dependents: dict[str, list[str]] = {step.id: [] for step in self.steps}

        for step in self.steps:
            for dep in step.depends_on:
                in_degree[step.id] += 1
                dependents[dep].append(step.id)

        # Kahn's algorithm
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        # Sort for deterministic ordering among steps with equal priority
        queue.sort()
        result: list[WorkflowStep] = []

        while queue:
            current = queue.pop(0)
            result.append(self._step_by_id[current])
            neighbors = sorted(dependents[current])
            for neighbor in neighbors:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()

        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, json_str: str) -> "WorkflowPlan":
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowPlan":
        steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
        metadata = data.get("metadata", {})
        return cls(steps=steps, metadata=metadata)
