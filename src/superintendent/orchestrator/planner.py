"""Planner: creates a WorkflowPlan from inputs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from superintendent.orchestrator.models import WorkflowPlan, WorkflowStep


@dataclass
class PlannerInput:
    """Inputs for the Planner."""

    repo: str  # Path or URL
    task: str
    mode: str = "autonomous"  # "autonomous" or "interactive"
    target: str = "sandbox"  # "sandbox", "container", or "local"
    branch: str | None = None
    context_file: str | None = None
    sandbox_name: str | None = None
    force: bool = False


class Planner:
    """Creates a WorkflowPlan from inputs.

    The Planner is stateless — it takes inputs and produces a plan.
    The Executor is responsible for running the plan.
    """

    def create_plan(self, inputs: PlannerInput) -> WorkflowPlan:
        """Build and validate a WorkflowPlan from the given inputs."""
        repo_name = self._extract_repo_name(inputs.repo)
        env_name = inputs.sandbox_name or f"claude-{repo_name}"
        branch = inputs.branch or f"agent/{repo_name}"

        metadata: dict[str, Any] = {
            "repo": inputs.repo,
            "repo_name": repo_name,
            "task": inputs.task,
            "mode": inputs.mode,
            "target": inputs.target,
            "branch": branch,
        }
        if inputs.target == "container":
            metadata["container_name"] = env_name
        else:
            metadata["sandbox_name"] = env_name
        if inputs.context_file:
            metadata["context_file"] = inputs.context_file

        steps = self._build_steps(inputs, metadata)
        plan = WorkflowPlan(steps=steps, metadata=metadata)

        errors = plan.validate()
        if errors:
            raise ValueError(f"Planner produced invalid plan: {'; '.join(errors)}")

        return plan

    def _build_steps(
        self, inputs: PlannerInput, metadata: dict[str, Any]
    ) -> list[WorkflowStep]:
        steps: list[WorkflowStep] = []

        # Step 1: Validate/ensure the repo is available locally
        is_url = inputs.repo.startswith(("http://", "https://", "git@"))
        steps.append(
            WorkflowStep(
                id="validate_repo",
                action="validate_repo",
                params={
                    "repo": inputs.repo,
                    "is_url": is_url,
                },
            )
        )

        # Step 2: Create worktree
        steps.append(
            WorkflowStep(
                id="create_worktree",
                action="create_worktree",
                params={
                    "branch": metadata["branch"],
                    "repo_name": metadata["repo_name"],
                },
                depends_on=["validate_repo"],
            )
        )

        if inputs.target == "container":
            self._build_container_steps(steps, inputs, metadata)
        elif inputs.target == "sandbox":
            self._build_sandbox_steps(steps, inputs, metadata)
        else:
            # Local mode: no sandbox, no auth
            # Step 3: Initialize state
            steps.append(
                WorkflowStep(
                    id="initialize_state",
                    action="initialize_state",
                    params={
                        "task": inputs.task,
                        "context_file": inputs.context_file,
                    },
                    depends_on=["create_worktree"],
                )
            )

            # Step 4: Start agent locally
            steps.append(
                WorkflowStep(
                    id="start_agent",
                    action="start_agent",
                    params={
                        "task": inputs.task,
                    },
                    depends_on=["initialize_state"],
                )
            )

        return steps

    def _build_sandbox_steps(
        self,
        steps: list[WorkflowStep],
        inputs: "PlannerInput",
        metadata: dict[str, Any],
    ) -> None:
        sandbox_name = metadata["sandbox_name"]

        steps.append(
            WorkflowStep(
                id="prepare_sandbox",
                action="prepare_sandbox",
                params={
                    "sandbox_name": sandbox_name,
                    "force": inputs.force,
                },
                depends_on=["create_worktree"],
            )
        )
        steps.append(
            WorkflowStep(
                id="authenticate",
                action="authenticate",
                params={"sandbox_name": sandbox_name},
                depends_on=["prepare_sandbox"],
            )
        )
        steps.append(
            WorkflowStep(
                id="initialize_state",
                action="initialize_state",
                params={
                    "task": inputs.task,
                    "context_file": inputs.context_file,
                },
                depends_on=["authenticate"],
            )
        )
        steps.append(
            WorkflowStep(
                id="start_agent",
                action="start_agent",
                params={
                    "sandbox_name": sandbox_name,
                    "task": inputs.task,
                },
                depends_on=["initialize_state"],
            )
        )

    def _build_container_steps(
        self,
        steps: list[WorkflowStep],
        inputs: "PlannerInput",
        metadata: dict[str, Any],
    ) -> None:
        container_name = metadata["container_name"]

        steps.append(
            WorkflowStep(
                id="prepare_container",
                action="prepare_container",
                params={
                    "container_name": container_name,
                    "force": inputs.force,
                },
                depends_on=["create_worktree"],
            )
        )
        steps.append(
            WorkflowStep(
                id="authenticate",
                action="authenticate",
                params={"container_name": container_name},
                depends_on=["prepare_container"],
            )
        )
        steps.append(
            WorkflowStep(
                id="initialize_state",
                action="initialize_state",
                params={
                    "task": inputs.task,
                    "context_file": inputs.context_file,
                },
                depends_on=["authenticate"],
            )
        )
        steps.append(
            WorkflowStep(
                id="start_agent",
                action="start_agent",
                params={
                    "container_name": container_name,
                    "task": inputs.task,
                },
                depends_on=["initialize_state"],
            )
        )

    @staticmethod
    def _extract_repo_name(repo: str) -> str:
        """Extract a short repo name from a path or URL."""
        # Handle URLs like https://github.com/user/repo.git
        if repo.startswith(("http://", "https://", "git@")):
            name = repo.rstrip("/").rsplit("/", 1)[-1]
            if name.endswith(".git"):
                name = name[:-4]
            return name

        # Handle local paths
        path = Path(repo)
        return path.name or path.parent.name
