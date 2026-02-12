"""Tests for the Planner."""

from superintendent.orchestrator.planner import Planner, PlannerInput


class TestPlannerInput:
    def test_defaults(self):
        inp = PlannerInput(repo="/test/repo", task="implement feature")
        assert inp.mode == "autonomous"
        assert inp.target == "sandbox"
        assert inp.branch is None
        assert inp.context_file is None
        assert inp.sandbox_name is None
        assert inp.force is False


class TestPlanner:
    def test_sandbox_mode_creates_six_steps(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/test/repo", task="implement feature")
        )
        assert len(plan.steps) == 6

    def test_sandbox_mode_step_actions(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/test/repo", task="implement feature")
        )
        actions = [s.action for s in plan.steps]
        assert actions == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
            "authenticate",
            "initialize_state",
            "start_agent",
        ]

    def test_sandbox_mode_step_order(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/test/repo", task="implement feature")
        )
        order = plan.execution_order()
        ids = [s.id for s in order]
        assert ids == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
            "authenticate",
            "initialize_state",
            "start_agent",
        ]

    def test_local_mode_creates_four_steps(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/test/repo", task="test", target="local")
        )
        assert len(plan.steps) == 4

    def test_local_mode_step_actions(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/test/repo", task="test", target="local")
        )
        actions = [s.action for s in plan.steps]
        assert actions == [
            "validate_repo",
            "create_worktree",
            "initialize_state",
            "start_agent",
        ]

    def test_container_target_creates_six_steps(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/test/repo", task="test", target="container")
        )
        assert len(plan.steps) == 6

    def test_metadata_includes_target(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/test/repo", task="test", target="local")
        )
        assert plan.metadata["target"] == "local"

    def test_metadata_from_path(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/home/user/my-project", task="fix bug")
        )
        assert plan.metadata["repo"] == "/home/user/my-project"
        assert plan.metadata["repo_name"] == "my-project"
        assert plan.metadata["task"] == "fix bug"
        assert plan.metadata["sandbox_name"] == "claude-my-project"
        assert plan.metadata["branch"] == "agent/my-project"

    def test_metadata_from_url(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(
                repo="https://github.com/user/awesome-repo.git",
                task="add feature",
            )
        )
        assert plan.metadata["repo_name"] == "awesome-repo"
        assert plan.metadata["sandbox_name"] == "claude-awesome-repo"

    def test_custom_branch(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/repo", task="test", branch="my-branch")
        )
        assert plan.metadata["branch"] == "my-branch"

    def test_custom_sandbox_name(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/repo", task="test", sandbox_name="my-sandbox")
        )
        assert plan.metadata["sandbox_name"] == "my-sandbox"
        sandbox_step = plan.get_step("prepare_sandbox")
        assert sandbox_step.params["sandbox_name"] == "my-sandbox"

    def test_context_file_in_metadata(self):
        planner = Planner()
        plan = planner.create_plan(
            PlannerInput(repo="/repo", task="test", context_file="context.md")
        )
        assert plan.metadata["context_file"] == "context.md"
        init_step = plan.get_step("initialize_state")
        assert init_step.params["context_file"] == "context.md"

    def test_no_context_file_not_in_metadata(self):
        planner = Planner()
        plan = planner.create_plan(PlannerInput(repo="/repo", task="test"))
        assert "context_file" not in plan.metadata

    def test_force_flag_passed_to_sandbox(self):
        planner = Planner()
        plan = planner.create_plan(PlannerInput(repo="/repo", task="test", force=True))
        sandbox_step = plan.get_step("prepare_sandbox")
        assert sandbox_step.params["force"] is True

    def test_url_detection(self):
        planner = Planner()
        for url in [
            "https://github.com/user/repo",
            "http://github.com/user/repo",
            "git@github.com:user/repo.git",
        ]:
            plan = planner.create_plan(PlannerInput(repo=url, task="test"))
            step = plan.get_step("validate_repo")
            assert step.params["is_url"] is True

    def test_path_detection(self):
        planner = Planner()
        plan = planner.create_plan(PlannerInput(repo="/local/repo", task="test"))
        step = plan.get_step("validate_repo")
        assert step.params["is_url"] is False

    def test_plan_is_valid(self):
        planner = Planner()
        plan = planner.create_plan(PlannerInput(repo="/repo", task="test"))
        assert plan.validate() == []

    def test_plan_json_roundtrip(self):
        planner = Planner()
        plan = planner.create_plan(PlannerInput(repo="/repo", task="test"))
        json_str = plan.to_json()
        from superintendent.orchestrator.models import WorkflowPlan

        restored = WorkflowPlan.from_json(json_str)
        assert len(restored.steps) == len(plan.steps)
        assert restored.metadata == plan.metadata


class TestExtractRepoName:
    def test_https_url(self):
        assert Planner._extract_repo_name("https://github.com/user/repo") == "repo"

    def test_https_url_with_git_suffix(self):
        assert Planner._extract_repo_name("https://github.com/user/repo.git") == "repo"

    def test_ssh_url(self):
        assert Planner._extract_repo_name("git@github.com:user/repo.git") == "repo"

    def test_local_path(self):
        assert Planner._extract_repo_name("/home/user/my-project") == "my-project"

    def test_trailing_slash(self):
        assert Planner._extract_repo_name("https://github.com/user/repo/") == "repo"
