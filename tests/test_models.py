"""Tests for WorkflowStep and WorkflowPlan models."""

import json

import pytest

from superintendent.orchestrator.models import WorkflowPlan, WorkflowStep


class TestWorkflowStep:
    def test_create_step(self):
        step = WorkflowStep(id="s1", action="validate_repo", params={"path": "/repo"})
        assert step.id == "s1"
        assert step.action == "validate_repo"
        assert step.params == {"path": "/repo"}
        assert step.depends_on == []

    def test_step_with_dependencies(self):
        step = WorkflowStep(id="s2", action="create_worktree", depends_on=["s1"])
        assert step.depends_on == ["s1"]

    def test_step_to_dict(self):
        step = WorkflowStep(
            id="s1", action="clone", params={"url": "https://example.com"}
        )
        d = step.to_dict()
        assert d == {
            "id": "s1",
            "action": "clone",
            "params": {"url": "https://example.com"},
            "depends_on": [],
        }

    def test_step_from_dict(self):
        data = {
            "id": "s1",
            "action": "clone",
            "params": {"url": "x"},
            "depends_on": ["s0"],
        }
        step = WorkflowStep.from_dict(data)
        assert step.id == "s1"
        assert step.action == "clone"
        assert step.depends_on == ["s0"]

    def test_step_from_dict_defaults(self):
        data = {"id": "s1", "action": "clone"}
        step = WorkflowStep.from_dict(data)
        assert step.params == {}
        assert step.depends_on == []

    def test_step_roundtrip(self):
        original = WorkflowStep(
            id="s1", action="auth", params={"token": "abc"}, depends_on=["s0"]
        )
        restored = WorkflowStep.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.action == original.action
        assert restored.params == original.params
        assert restored.depends_on == original.depends_on


class TestWorkflowPlan:
    def _make_linear_plan(self) -> WorkflowPlan:
        """Create a simple 3-step linear plan."""
        return WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="validate_repo"),
                WorkflowStep(id="s2", action="create_worktree", depends_on=["s1"]),
                WorkflowStep(id="s3", action="start_agent", depends_on=["s2"]),
            ],
            metadata={"repo": "test-repo"},
        )

    def test_get_step(self):
        plan = self._make_linear_plan()
        assert plan.get_step("s1") is not None
        assert plan.get_step("s1").action == "validate_repo"
        assert plan.get_step("nonexistent") is None

    def test_add_step(self):
        plan = WorkflowPlan()
        plan.add_step(WorkflowStep(id="s1", action="clone"))
        assert len(plan.steps) == 1
        assert plan.get_step("s1") is not None

    def test_validate_valid_plan(self):
        plan = self._make_linear_plan()
        errors = plan.validate()
        assert errors == []

    def test_validate_duplicate_ids(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="clone"),
                WorkflowStep(id="s1", action="auth"),
            ]
        )
        errors = plan.validate()
        assert any("Duplicate step ID: s1" in e for e in errors)

    def test_validate_missing_dependency(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="clone", depends_on=["missing"]),
            ]
        )
        errors = plan.validate()
        assert any("unknown step 'missing'" in e for e in errors)

    def test_validate_cycle(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="a", depends_on=["s2"]),
                WorkflowStep(id="s2", action="b", depends_on=["s1"]),
            ]
        )
        errors = plan.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_validate_self_cycle(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="a", depends_on=["s1"]),
            ]
        )
        errors = plan.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_validate_three_node_cycle(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="a", depends_on=["s3"]),
                WorkflowStep(id="s2", action="b", depends_on=["s1"]),
                WorkflowStep(id="s3", action="c", depends_on=["s2"]),
            ]
        )
        errors = plan.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_execution_order_linear(self):
        plan = self._make_linear_plan()
        order = plan.execution_order()
        ids = [s.id for s in order]
        assert ids == ["s1", "s2", "s3"]

    def test_execution_order_diamond(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="start"),
                WorkflowStep(id="s2", action="left", depends_on=["s1"]),
                WorkflowStep(id="s3", action="right", depends_on=["s1"]),
                WorkflowStep(id="s4", action="join", depends_on=["s2", "s3"]),
            ]
        )
        order = plan.execution_order()
        ids = [s.id for s in order]
        assert ids.index("s1") < ids.index("s2")
        assert ids.index("s1") < ids.index("s3")
        assert ids.index("s2") < ids.index("s4")
        assert ids.index("s3") < ids.index("s4")

    def test_execution_order_no_deps(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="b", action="second"),
                WorkflowStep(id="a", action="first"),
            ]
        )
        order = plan.execution_order()
        # Deterministic alphabetical order when no deps
        ids = [s.id for s in order]
        assert ids == ["a", "b"]

    def test_execution_order_invalid_plan_raises(self):
        plan = WorkflowPlan(
            steps=[
                WorkflowStep(id="s1", action="a", depends_on=["s2"]),
                WorkflowStep(id="s2", action="b", depends_on=["s1"]),
            ]
        )
        with pytest.raises(ValueError, match="Invalid plan"):
            plan.execution_order()

    def test_to_json(self):
        plan = self._make_linear_plan()
        json_str = plan.to_json()
        data = json.loads(json_str)
        assert "steps" in data
        assert "metadata" in data
        assert len(data["steps"]) == 3
        assert data["metadata"]["repo"] == "test-repo"

    def test_from_json(self):
        json_str = json.dumps(
            {
                "steps": [
                    {"id": "s1", "action": "clone", "params": {}, "depends_on": []},
                ],
                "metadata": {"branch": "main"},
            }
        )
        plan = WorkflowPlan.from_json(json_str)
        assert len(plan.steps) == 1
        assert plan.metadata["branch"] == "main"
        assert plan.get_step("s1").action == "clone"

    def test_json_roundtrip(self):
        original = self._make_linear_plan()
        json_str = original.to_json()
        restored = WorkflowPlan.from_json(json_str)
        assert len(restored.steps) == len(original.steps)
        assert restored.metadata == original.metadata
        for orig, rest in zip(original.steps, restored.steps, strict=True):
            assert orig.id == rest.id
            assert orig.action == rest.action
            assert orig.params == rest.params
            assert orig.depends_on == rest.depends_on

    def test_empty_plan_is_valid(self):
        plan = WorkflowPlan()
        assert plan.validate() == []
        assert plan.execution_order() == []
