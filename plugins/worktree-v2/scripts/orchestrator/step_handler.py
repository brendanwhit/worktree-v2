"""RealStepHandler: dispatches workflow steps to backend operations."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backends.factory import Backends
from orchestrator.executor import StepResult
from orchestrator.models import WorkflowStep
from state.ralph import RalphState


@dataclass
class ExecutionContext:
    """Context shared across step handlers during execution."""

    backends: Backends
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)


class RealStepHandler:
    """Dispatches workflow steps to real backend operations."""

    def __init__(self, context: ExecutionContext) -> None:
        self._context = context
        self._dispatch: dict[str, Callable[[WorkflowStep], StepResult]] = {
            "validate_repo": self._handle_validate_repo,
            "create_worktree": self._handle_create_worktree,
            "prepare_sandbox": self._handle_prepare_sandbox,
            "authenticate": self._handle_authenticate,
            "initialize_state": self._handle_initialize_state,
            "start_agent": self._handle_start_agent,
        }

    @property
    def registered_actions(self) -> list[str]:
        """Return all action names that have registered handlers."""
        return list(self._dispatch.keys())

    def execute(self, step: WorkflowStep) -> StepResult:
        """Execute a single workflow step by dispatching to the appropriate handler."""
        handler_fn = self._dispatch.get(step.action)
        if handler_fn is None:
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Unknown action: {step.action}",
            )
        result = handler_fn(step)
        if result.success and result.data:
            self._context.step_outputs[step.id] = result.data
        return result

    # -- Git handlers (validate_repo, create_worktree) -----------------------

    def _handle_validate_repo(self, step: WorkflowStep) -> StepResult:
        git = self._context.backends.git
        repo = step.params["repo"]
        is_url = step.params.get("is_url", False)

        repo_path = git.ensure_local(repo)
        if repo_path is not None:
            return StepResult(
                success=True,
                step_id=step.id,
                data={"repo_path": str(repo_path)},
            )

        if is_url:
            # Extract repo name for clone target
            name = repo.rstrip("/").rsplit("/", 1)[-1]
            if name.endswith(".git"):
                name = name[:-4]
            clone_target = Path.cwd() / name
            if not git.clone(repo, clone_target):
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message=f"Failed to clone {repo}",
                )
            return StepResult(
                success=True,
                step_id=step.id,
                data={"repo_path": str(clone_target)},
            )

        return StepResult(
            success=False,
            step_id=step.id,
            message=f"Repository not found: {repo}",
        )

    def _handle_create_worktree(self, step: WorkflowStep) -> StepResult:
        validate_output = self._context.step_outputs.get("validate_repo")
        if validate_output is None:
            return StepResult(
                success=False,
                step_id=step.id,
                message="Missing validate_repo output (repo_path)",
            )

        git = self._context.backends.git
        repo_path = Path(validate_output["repo_path"])
        branch = step.params["branch"]
        repo_name = step.params["repo_name"]
        worktree_path = repo_path.parent / f"{repo_name}-{branch.replace('/', '-')}"

        if not git.create_worktree(repo_path, branch, worktree_path):
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Failed to create worktree at {worktree_path}",
            )

        return StepResult(
            success=True,
            step_id=step.id,
            data={"worktree_path": str(worktree_path)},
        )

    # -- Docker handlers (prepare_sandbox) ------------------------------------

    def _handle_prepare_sandbox(self, step: WorkflowStep) -> StepResult:
        wt_output = self._context.step_outputs.get("create_worktree")
        if wt_output is None:
            return StepResult(
                success=False,
                step_id=step.id,
                message="Missing create_worktree output (worktree_path)",
            )

        docker = self._context.backends.docker
        sandbox_name = step.params["sandbox_name"]
        force = step.params.get("force", False)
        workspace = Path(wt_output["worktree_path"])

        if force and docker.sandbox_exists(sandbox_name):
            docker.stop_sandbox(sandbox_name)

        if not docker.create_sandbox(sandbox_name, workspace):
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Failed to create sandbox: {sandbox_name}",
            )

        return StepResult(
            success=True,
            step_id=step.id,
            data={"sandbox_name": sandbox_name},
        )

    # -- Auth handler (authenticate) ------------------------------------------

    def _handle_authenticate(self, step: WorkflowStep) -> StepResult:
        auth = self._context.backends.auth
        sandbox_name = step.params["sandbox_name"]

        if not auth.setup_git_auth(sandbox_name):
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Failed to configure auth in sandbox: {sandbox_name}",
            )

        return StepResult(success=True, step_id=step.id)

    # -- State handler (initialize_state) -------------------------------------

    def _handle_initialize_state(self, step: WorkflowStep) -> StepResult:
        wt_output = self._context.step_outputs.get("create_worktree")
        if wt_output is None:
            return StepResult(
                success=False,
                step_id=step.id,
                message="Missing create_worktree output (worktree_path)",
            )

        worktree_path = Path(wt_output["worktree_path"])
        task = step.params.get("task", "")
        ralph_dir = worktree_path / ".ralph"

        ralph_state = RalphState(ralph_dir)
        ralph_state.init(task=task)

        return StepResult(
            success=True,
            step_id=step.id,
            data={"ralph_dir": str(ralph_dir)},
        )

    # -- Terminal handler (start_agent) ---------------------------------------

    def _handle_start_agent(self, step: WorkflowStep) -> StepResult:
        sandbox_name = step.params.get("sandbox_name")
        task = step.params.get("task", "")

        wt_output = self._context.step_outputs.get("create_worktree")
        worktree_path = Path(wt_output["worktree_path"]) if wt_output else Path.cwd()

        if sandbox_name:
            docker = self._context.backends.docker
            if not docker.run_agent(sandbox_name, worktree_path, task):
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message=f"Failed to start agent in sandbox: {sandbox_name}",
                )
        else:
            terminal = self._context.backends.terminal
            cmd = f"claude --prompt '{task}'"
            if not terminal.spawn(cmd, worktree_path):
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message="Failed to spawn local agent",
                )

        return StepResult(success=True, step_id=step.id)
