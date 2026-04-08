"""RealStepHandler: dispatches workflow steps to backend operations."""

import hashlib
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from superintendent.backends.factory import Backends
from superintendent.backends.terminal import build_agent_command, wrap_with_lifecycle
from superintendent.orchestrator.executor import StepResult
from superintendent.orchestrator.models import Verbosity, WorkflowStep
from superintendent.state.ralph import RalphState
from superintendent.state.token_store import TokenStore

SANDBOX_BASE_IMAGE = "docker/sandbox-templates:claude-code"


def default_worktrees_dir() -> Path:
    """Return the default base directory for agent worktrees."""
    return Path.home() / ".claude-worktrees"


@dataclass
class ExecutionContext:
    """Context shared across step handlers during execution."""

    backends: Backends
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    verbosity: Verbosity = Verbosity.normal
    token_store: TokenStore = field(default_factory=TokenStore)
    dry_run: bool = False


class RealStepHandler:
    """Dispatches workflow steps to real backend operations."""

    def __init__(self, context: ExecutionContext) -> None:
        self._context = context
        self._dispatch: dict[str, Callable[[WorkflowStep], StepResult]] = {
            "validate_repo": self._handle_validate_repo,
            "validate_auth": self._handle_validate_auth,
            "create_worktree": self._handle_create_worktree,
            "prepare_template": self._handle_prepare_template,
            "prepare_sandbox": self._handle_prepare_sandbox,
            "prepare_container": self._handle_prepare_container,
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

    def _handle_validate_auth(self, step: WorkflowStep) -> StepResult:
        """Validate auth before expensive operations (clone, sandbox creation).

        Checks that a token can be resolved for the target repo. Fails fast
        with an actionable message if the repo belongs to an org that requires
        an explicit token.
        """
        if self._context.dry_run:
            return StepResult(success=True, step_id=step.id)

        store = self._context.token_store

        # Try to identify the repo from validate_repo output
        validate_output = self._context.step_outputs.get("validate_repo")
        if validate_output:
            repo_path = Path(validate_output["repo_path"])
            repo_id = self._get_repo_identifier(repo_path)
            if repo_id:
                result = store.resolve(repo_id)
                if result.source == "org_requires_explicit":
                    return StepResult(
                        success=False,
                        step_id=step.id,
                        message=(
                            f"No token configured for org repo '{repo_id}'. "
                            f"Run: superintendent token add {repo_id}"
                        ),
                    )
                if result.token:
                    return StepResult(success=True, step_id=step.id)

        # Fall back to full token resolution chain
        token = self._resolve_token()
        if token:
            return StepResult(success=True, step_id=step.id)

        return StepResult(
            success=False,
            step_id=step.id,
            message=(
                "No GitHub token available. Options:\n"
                "  1. superintendent token set-default (for personal repos)\n"
                "  2. superintendent token add <owner/repo> (for org repos)\n"
                "  3. gh auth login (GitHub CLI)"
            ),
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
        standalone = step.params.get("standalone", False)
        force = step.params.get("force", False)
        slug = branch.replace("/", "-")
        worktree_path = default_worktrees_dir() / repo_name / slug
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if standalone:
            ok = git.clone_for_sandbox(repo_path, worktree_path, branch)
        elif self._context.dry_run:
            # Dry-run uses DryRunGitBackend (logs command, no side effects).
            # Skip reuse/attach checks since filesystem state is irrelevant.
            ok = git.create_worktree(repo_path, branch, worktree_path)
        elif force and worktree_path.exists():
            # --force: remove existing worktree and recreate from scratch
            git.remove_worktree(repo_path, worktree_path)
            ok = git.create_worktree(repo_path, branch, worktree_path)
        elif worktree_path.exists() and git.branch_exists(repo_path, branch):
            # Scenario 1: worktree + branch already exist — reuse
            ok = True
        elif git.branch_exists(repo_path, branch):
            # Scenario 2: branch exists but no worktree — attach
            ok = git.create_worktree_from_existing(repo_path, branch, worktree_path)
        else:
            # Scenario 3: neither exists — create new branch + worktree
            ok = git.create_worktree(repo_path, branch, worktree_path)

        if not ok:
            action = "clone for sandbox" if standalone else "create worktree"
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Failed to {action} at {worktree_path}",
            )

        return StepResult(
            success=True,
            step_id=step.id,
            data={"worktree_path": str(worktree_path)},
        )

    # -- Template handler (prepare_template) ----------------------------------

    def _handle_prepare_template(self, step: WorkflowStep) -> StepResult:
        dockerfile = (
            "FROM dolthub/dolt:latest AS dolt-binary\n"
            f"FROM {SANDBOX_BASE_IMAGE}\n"
            "COPY --from=dolt-binary /usr/local/bin/dolt /usr/local/bin/dolt\n"
            "RUN npm install -g @beads/bd\n"
        )
        tag = "supt-sandbox:" + hashlib.sha256(dockerfile.encode()).hexdigest()[:12]

        docker = self._context.backends.docker
        if not docker.template_exists(tag) and not docker.build_template(
            dockerfile, tag
        ):
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Failed to build template: {tag}",
            )

        return StepResult(
            success=True,
            step_id=step.id,
            data={"template": tag},
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

        # Pick up template tag from prepare_template step, if available
        template_output = self._context.step_outputs.get("prepare_template")
        template = template_output["template"] if template_output else None

        if force and docker.sandbox_exists(sandbox_name):
            docker.stop_sandbox(sandbox_name)
            docker.remove_sandbox(sandbox_name)

        if not docker.create_sandbox(sandbox_name, workspace, template=template):
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

    # -- Docker handlers (prepare_container) -----------------------------------

    def _handle_prepare_container(self, step: WorkflowStep) -> StepResult:
        wt_output = self._context.step_outputs.get("create_worktree")
        if wt_output is None:
            return StepResult(
                success=False,
                step_id=step.id,
                message="Missing create_worktree output (worktree_path)",
            )

        docker = self._context.backends.docker
        container_name = step.params["container_name"]
        force = step.params.get("force", False)
        workspace = Path(wt_output["worktree_path"])

        if force and docker.container_exists(container_name):
            docker.stop_container(container_name)

        if not docker.create_container(container_name, workspace):
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Failed to create container: {container_name}",
            )

        return StepResult(
            success=True,
            step_id=step.id,
            data={"container_name": container_name},
        )

    # -- Auth handler (authenticate) ------------------------------------------

    def _handle_authenticate(self, step: WorkflowStep) -> StepResult:
        auth = self._context.backends.auth
        env_name = step.params.get("sandbox_name") or step.params.get(
            "container_name", ""
        )

        # Resolve token: TokenStore (per-repo or default) → host gh auth → fail
        token = self._resolve_token()
        if token:
            if not auth.inject_token(env_name, token):
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message=f"Failed to inject token into {env_name}",
                )
        else:
            # No token available — fall back to bare setup_git_auth
            if not auth.setup_git_auth(env_name):
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message=f"Failed to configure auth in {env_name} (no token available)",
                )

        return StepResult(success=True, step_id=step.id)

    def _resolve_token(self) -> str | None:
        """Resolve a GitHub token from TokenStore or host gh CLI."""
        store = self._context.token_store

        # Try repo-specific token from validate_repo output
        validate_output = self._context.step_outputs.get("validate_repo")
        if validate_output:
            repo_path = Path(validate_output["repo_path"])
            repo_id = self._get_repo_identifier(repo_path)
            if repo_id:
                result = store.resolve(repo_id)
                if result.token:
                    return result.token

        # Try default token
        default = store.get("_default")
        if default:
            return default.token

        # Fall back to host's gh auth token
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Check environment variables
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _get_repo_identifier(self, repo_path: Path) -> str | None:
        """Extract owner/repo from a git repo's remote URL."""
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            url = result.stdout.strip()
            # Parse SSH or HTTPS URL
            if url.startswith("git@"):
                # git@github.com:owner/repo.git
                path = url.split(":", 1)[1]
            elif "github.com" in url:
                # https://github.com/owner/repo.git
                path = url.split("github.com/", 1)[1] if "github.com/" in url else None
                if not path:
                    return None
            else:
                return None
            return path.removesuffix(".git")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

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

        # Copy context file into .ralph/ so it survives reconnection
        context_file = step.params.get("context_file")
        if context_file:
            src = Path(context_file).expanduser()
            if src.is_file():
                dest = ralph_dir / "context.md"
                dest.write_text(src.read_text())
            else:
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message=f"Context file not found: {context_file}",
                )

        # Initialize beads with Dolt for sandbox/container targets
        is_sandbox = "prepare_sandbox" in self._context.step_outputs
        is_container = "prepare_container" in self._context.step_outputs
        if is_sandbox or is_container:
            env_name = ""
            if is_sandbox:
                env_name = self._context.step_outputs["prepare_sandbox"]["sandbox_name"]
            else:
                env_name = self._context.step_outputs["prepare_container"][
                    "container_name"
                ]
            repo_name = Path(
                self._context.step_outputs.get("validate_repo", {}).get("repo_path", "")
            ).name

            init_result = self._init_beads(env_name, repo_name)
            if not init_result:
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message=f"Failed to initialize beads/Dolt in {env_name}",
                )

        return StepResult(
            success=True,
            step_id=step.id,
            data={"ralph_dir": str(ralph_dir)},
        )

    def _init_beads(self, env_name: str, repo_name: str) -> bool:
        """Initialize beads with Dolt SQL server inside a sandbox/container.

        bd init auto-starts the Dolt server internally (AutoStart flag),
        so a single command handles everything: creates .beads/, runs
        dolt init, starts dolt sql-server, and creates the schema.

        Sanitizes the repo name for Dolt (no dots, must be valid MySQL
        identifier) and passes both --prefix and --database explicitly
        to avoid bd deriving invalid names from directory names.

        Retries once on failure to handle transient Dolt fsync issues
        in container environments.

        Returns True on success, False on failure.
        """
        docker = self._context.backends.docker

        # Sanitize repo name for use as Dolt database/prefix name
        # Dolt database names follow MySQL rules: no dots, no leading hyphens
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", repo_name).strip("_")
        if not sanitized:
            sanitized = "beads"

        init_cmd = (
            f"bd init --sandbox --skip-hooks -p {sanitized} --database {sanitized} -q"
        )

        exit_code, _ = docker.exec_in_sandbox(env_name, init_cmd)
        if exit_code == 0:
            return True

        # Retry once: Dolt can fail on first start in containers due to
        # fsync issues on overlay filesystems. Clean up and try again.
        docker.exec_in_sandbox(env_name, "rm -rf .beads && sleep 2")
        exit_code, _ = docker.exec_in_sandbox(env_name, init_cmd)
        return exit_code == 0

    # -- Terminal handler (start_agent) ---------------------------------------

    @staticmethod
    def _notify_plugin_installed() -> bool:
        """Check if the notify plugin is installed globally."""
        plugin_dir = (
            Path.home() / ".claude" / "plugins" / "cache" / "fdy-skills" / "notify"
        )
        return plugin_dir.exists()

    def _gather_branch_context(self, worktree_path: Path, branch: str) -> str | None:
        """Gather pre-flight context about the branch state.

        Returns a context string for the agent prompt, or None if there's
        nothing notable to report (fresh branch with no prior work).
        """
        if self._context.dry_run:
            return None

        git = self._context.backends.git
        parts: list[str] = []

        # Check for existing commits ahead of default branch
        default_branch = git.get_default_branch(worktree_path)
        result = subprocess.run(
            [
                "git",
                "-C",
                str(worktree_path),
                "log",
                f"origin/{default_branch}..HEAD",
                "--oneline",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            commits = result.stdout.strip().splitlines()
            parts.append(
                f"This branch has {len(commits)} existing commit(s) ahead of "
                f"{default_branch}. Review them before starting new work:\n"
                + "\n".join(f"  {c}" for c in commits)
            )

        # Check for existing PR
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "open",
                "--json",
                "number,title,url",
                "--limit",
                "1",
            ],
            capture_output=True,
            text=True,
        )
        if pr_result.returncode == 0 and pr_result.stdout.strip() not in ("", "[]"):
            import json

            try:
                prs = json.loads(pr_result.stdout)
                if prs:
                    pr = prs[0]
                    parts.append(
                        f'An open PR already exists: #{pr["number"]} "{pr["title"]}"\n'
                        f"  {pr['url']}\n"
                        "Update this PR rather than creating a new one."
                    )
            except (json.JSONDecodeError, KeyError):
                pass

        if not parts:
            return None
        return "PRE-FLIGHT CONTEXT:\n" + "\n\n".join(parts)

    def _enrich_prompt(self, task: str, autonomous: bool) -> str:
        """Add session-setup instructions to the agent prompt."""
        preamble_parts: list[str] = []
        if not autonomous and self._notify_plugin_installed():
            preamble_parts.append(
                "First, run /notify:notify to enable audio notifications."
            )

        suffix_parts: list[str] = []
        if autonomous:
            suffix_parts.append(
                "IMPORTANT: Run the project's test suite after completing each "
                "task. Do NOT proceed to the next task if tests fail — fix the "
                "failure first."
            )
            suffix_parts.append(
                "IMPORTANT: When you have finished all tasks, do NOT exit the "
                "conversation. Instead, summarize what you accomplished and wait "
                "for the user to review your work. The user may have follow-up "
                "questions or corrections."
            )

        parts = []
        if preamble_parts:
            parts.append(" ".join(preamble_parts))
        parts.append(task)
        if suffix_parts:
            parts.append("\n".join(suffix_parts))
        return "\n\n".join(parts)

    def _handle_start_agent(self, step: WorkflowStep) -> StepResult:
        env_name = step.params.get("sandbox_name") or step.params.get("container_name")
        task = step.params.get("task", "")
        autonomous = step.params.get("mode") == "autonomous"
        branch = step.params.get("branch", "")

        # Point the agent at the context file persisted in .ralph/
        context_file = step.params.get("context_file")
        if context_file:
            task = (
                f"{task}\n\n"
                "A context file with detailed instructions has been saved to "
                ".ralph/context.md in your workspace. Read it before starting work."
            )

        wt_output = self._context.step_outputs.get("create_worktree")
        worktree_path = Path(wt_output["worktree_path"]) if wt_output else Path.cwd()

        # Gather pre-flight context about existing branch/PR state
        if branch:
            branch_context = self._gather_branch_context(worktree_path, branch)
            if branch_context:
                task = f"{task}\n\n{branch_context}"

        task = self._enrich_prompt(task, autonomous)

        if env_name:
            docker = self._context.backends.docker
            if not docker.run_agent(
                env_name, task, autonomous=autonomous, cwd=worktree_path
            ):
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message=f"Failed to start agent in {env_name}",
                )
        else:
            terminal = self._context.backends.terminal
            cmd = build_agent_command(task, autonomous=autonomous)
            ralph_dir = worktree_path / ".ralph"
            if ralph_dir.is_dir():
                cmd = wrap_with_lifecycle(cmd, ralph_dir)
            if not terminal.spawn(cmd, worktree_path):
                return StepResult(
                    success=False,
                    step_id=step.id,
                    message="Failed to spawn local agent",
                )

        return StepResult(success=True, step_id=step.id)
