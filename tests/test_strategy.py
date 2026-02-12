"""Tests for ExecutionStrategy and ExecutionDecision models."""

from superintendent.orchestrator.models import Mode, Target
from superintendent.orchestrator.repo_info import RepoInfo
from superintendent.orchestrator.strategy import (
    ExecutionDecision,
    ExecutionStrategy,
    GroupStrategy,
    TaskInfo,
)


class TestTaskInfo:
    def test_create_minimal(self):
        task = TaskInfo(name="Fix bug")
        assert task.name == "Fix bug"
        assert task.is_destructive is False
        assert task.complexity == "simple"
        assert task.depends_on == []
        assert task.labels == []

    def test_create_full(self):
        task = TaskInfo(
            name="Deploy to prod",
            is_destructive=True,
            complexity="complex",
            depends_on=["build", "test"],
            labels=["infra", "deploy"],
        )
        assert task.is_destructive is True
        assert task.complexity == "complex"
        assert task.depends_on == ["build", "test"]
        assert task.labels == ["infra", "deploy"]

    def test_complexity_values(self):
        for complexity in ("simple", "moderate", "complex"):
            task = TaskInfo(name="t", complexity=complexity)
            assert task.complexity == complexity


class TestExecutionDecision:
    def test_create_decision(self):
        decision = ExecutionDecision(
            mode=Mode.autonomous,
            target=Target.sandbox,
            parallelism=2,
            reasoning="Tasks are well-scoped with clear criteria",
            task_groups=[[TaskInfo(name="t1")], [TaskInfo(name="t2")]],
        )
        assert decision.mode == Mode.autonomous
        assert decision.target == Target.sandbox
        assert decision.parallelism == 2
        assert len(decision.task_groups) == 2

    def test_default_values(self):
        decision = ExecutionDecision(
            mode=Mode.autonomous,
            target=Target.local,
        )
        assert decision.parallelism == 1
        assert decision.reasoning == ""
        assert decision.task_groups == []

    def test_mode_is_mode_enum(self):
        decision = ExecutionDecision(mode=Mode.interactive, target=Target.local)
        assert isinstance(decision.mode, Mode)

    def test_target_is_target_enum(self):
        decision = ExecutionDecision(mode=Mode.autonomous, target=Target.container)
        assert isinstance(decision.target, Target)


class TestExecutionStrategy:
    def _default_repo_info(self) -> RepoInfo:
        return RepoInfo(
            has_dockerfile=False,
            has_devcontainer=False,
            has_env_file=False,
            needs_auth=False,
            languages=["python"],
            estimated_complexity="simple",
        )

    def _simple_tasks(self) -> list[TaskInfo]:
        return [TaskInfo(name="Fix typo", complexity="simple")]

    def test_decide_returns_execution_decision(self):
        strategy = ExecutionStrategy()
        decision = strategy.decide(self._simple_tasks(), self._default_repo_info())
        assert isinstance(decision, ExecutionDecision)

    def test_explain_returns_string(self):
        strategy = ExecutionStrategy()
        decision = ExecutionDecision(
            mode=Mode.autonomous,
            target=Target.local,
            reasoning="Simple task",
        )
        explanation = strategy.explain(decision)
        assert isinstance(explanation, str)
        assert len(explanation) > 0

    def test_explain_includes_mode_and_target(self):
        strategy = ExecutionStrategy()
        decision = ExecutionDecision(
            mode=Mode.autonomous,
            target=Target.sandbox,
            reasoning="Needs persistent auth",
        )
        explanation = strategy.explain(decision)
        assert "autonomous" in explanation.lower()
        assert "sandbox" in explanation.lower()

    # --- Mode decision tests ---

    def test_destructive_task_forces_interactive(self):
        strategy = ExecutionStrategy()
        tasks = [TaskInfo(name="Force push to main", is_destructive=True)]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.mode == Mode.interactive

    def test_complex_tasks_suggest_interactive(self):
        strategy = ExecutionStrategy()
        tasks = [
            TaskInfo(name="Refactor auth system", complexity="complex"),
            TaskInfo(name="Migrate database", complexity="complex"),
        ]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.mode == Mode.interactive

    def test_simple_tasks_suggest_autonomous(self):
        strategy = ExecutionStrategy()
        tasks = [TaskInfo(name="Fix typo", complexity="simple")]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.mode == Mode.autonomous

    def test_moderate_single_task_autonomous(self):
        strategy = ExecutionStrategy()
        tasks = [TaskInfo(name="Add validation", complexity="moderate")]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.mode == Mode.autonomous

    # --- Target decision tests ---

    def test_needs_auth_suggests_sandbox(self):
        strategy = ExecutionStrategy()
        repo = RepoInfo(
            has_dockerfile=False,
            has_devcontainer=False,
            has_env_file=False,
            needs_auth=True,
            languages=["python"],
            estimated_complexity="simple",
        )
        tasks = self._simple_tasks()
        decision = strategy.decide(tasks, repo)
        assert decision.target == Target.sandbox

    def test_has_env_file_suggests_sandbox(self):
        strategy = ExecutionStrategy()
        repo = RepoInfo(
            has_dockerfile=False,
            has_devcontainer=False,
            has_env_file=True,
            needs_auth=False,
            languages=["python"],
            estimated_complexity="simple",
        )
        tasks = self._simple_tasks()
        decision = strategy.decide(tasks, repo)
        assert decision.target == Target.sandbox

    def test_dockerfile_suggests_container(self):
        strategy = ExecutionStrategy()
        repo = RepoInfo(
            has_dockerfile=True,
            has_devcontainer=False,
            has_env_file=False,
            needs_auth=False,
            languages=["python"],
            estimated_complexity="simple",
        )
        tasks = self._simple_tasks()
        decision = strategy.decide(tasks, repo)
        assert decision.target == Target.container

    def test_devcontainer_suggests_container(self):
        strategy = ExecutionStrategy()
        repo = RepoInfo(
            has_dockerfile=False,
            has_devcontainer=True,
            has_env_file=False,
            needs_auth=False,
            languages=["python"],
            estimated_complexity="simple",
        )
        tasks = self._simple_tasks()
        decision = strategy.decide(tasks, repo)
        assert decision.target == Target.container

    def test_plain_repo_suggests_local(self):
        strategy = ExecutionStrategy()
        tasks = self._simple_tasks()
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.target == Target.local

    def test_auth_overrides_dockerfile(self):
        """Auth needs take priority over dockerfile presence."""
        strategy = ExecutionStrategy()
        repo = RepoInfo(
            has_dockerfile=True,
            has_devcontainer=False,
            has_env_file=False,
            needs_auth=True,
            languages=["python"],
            estimated_complexity="simple",
        )
        tasks = self._simple_tasks()
        decision = strategy.decide(tasks, repo)
        assert decision.target == Target.sandbox

    # --- Parallelism tests ---

    def test_single_task_parallelism_one(self):
        strategy = ExecutionStrategy()
        tasks = [TaskInfo(name="t1")]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.parallelism == 1

    def test_independent_tasks_enable_parallelism(self):
        strategy = ExecutionStrategy()
        tasks = [
            TaskInfo(name="t1"),
            TaskInfo(name="t2"),
            TaskInfo(name="t3"),
        ]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.parallelism >= 2

    def test_dependent_tasks_limit_parallelism(self):
        strategy = ExecutionStrategy()
        tasks = [
            TaskInfo(name="t1"),
            TaskInfo(name="t2", depends_on=["t1"]),
            TaskInfo(name="t3", depends_on=["t2"]),
        ]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.parallelism == 1

    def test_parallelism_capped_at_max(self):
        strategy = ExecutionStrategy(max_parallel_agents=4)
        tasks = [TaskInfo(name=f"t{i}") for i in range(10)]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert decision.parallelism <= 4

    # --- Task grouping tests ---

    def test_task_groups_populated(self):
        strategy = ExecutionStrategy()
        tasks = [
            TaskInfo(name="t1"),
            TaskInfo(name="t2"),
        ]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert len(decision.task_groups) > 0
        # All tasks should appear in exactly one group
        all_tasks = [t for group in decision.task_groups for t in group]
        assert len(all_tasks) == len(tasks)

    def test_dependent_tasks_in_same_group(self):
        strategy = ExecutionStrategy()
        tasks = [
            TaskInfo(name="build"),
            TaskInfo(name="test", depends_on=["build"]),
        ]
        decision = strategy.decide(tasks, self._default_repo_info())
        # Dependent tasks should be in the same group
        assert len(decision.task_groups) == 1
        group_names = [t.name for t in decision.task_groups[0]]
        assert "build" in group_names
        assert "test" in group_names

    def test_independent_tasks_in_separate_groups(self):
        strategy = ExecutionStrategy()
        tasks = [
            TaskInfo(name="t1"),
            TaskInfo(name="t2"),
        ]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert len(decision.task_groups) == 2

    # --- CLI override tests ---

    def test_mode_override(self):
        strategy = ExecutionStrategy()
        tasks = self._simple_tasks()
        decision = strategy.decide(
            tasks, self._default_repo_info(), mode_override=Mode.interactive
        )
        assert decision.mode == Mode.interactive

    def test_target_override(self):
        strategy = ExecutionStrategy()
        tasks = self._simple_tasks()
        decision = strategy.decide(
            tasks, self._default_repo_info(), target_override=Target.sandbox
        )
        assert decision.target == Target.sandbox

    def test_parallelism_override(self):
        strategy = ExecutionStrategy()
        tasks = [TaskInfo(name=f"t{i}") for i in range(5)]
        decision = strategy.decide(
            tasks, self._default_repo_info(), parallelism_override=2
        )
        assert decision.parallelism == 2

    # --- Reasoning tests ---

    def test_decision_has_reasoning(self):
        strategy = ExecutionStrategy()
        tasks = self._simple_tasks()
        decision = strategy.decide(tasks, self._default_repo_info())
        assert len(decision.reasoning) > 0

    def test_destructive_reasoning_mentions_destructive(self):
        strategy = ExecutionStrategy()
        tasks = [TaskInfo(name="delete db", is_destructive=True)]
        decision = strategy.decide(tasks, self._default_repo_info())
        assert "destructive" in decision.reasoning.lower()


class TestGroupStrategy:
    def test_enum_values(self):
        assert GroupStrategy.BY_INDEPENDENCE.value == "by_independence"
        assert GroupStrategy.BY_LABEL.value == "by_label"
        assert GroupStrategy.SINGLE.value == "single"
