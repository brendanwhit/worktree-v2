"""Tests for WorkflowState enum and transitions."""

from superintendent.state.workflow import (
    WORKFLOW_ORDER,
    WorkflowState,
    is_terminal,
    next_state,
    valid_transition,
)


class TestWorkflowState:
    def test_all_states_exist(self):
        expected = [
            "INIT",
            "ENSURING_REPO",
            "CREATING_WORKTREE",
            "PREPARING_SANDBOX",
            "AUTHENTICATING",
            "INITIALIZING_STATE",
            "STARTING_AGENT",
            "AGENT_RUNNING",
            "COMPLETED",
            "FAILED",
        ]
        actual = [s.name for s in WorkflowState]
        assert actual == expected

    def test_state_count(self):
        assert len(WorkflowState) == 10


class TestTransitions:
    def test_valid_forward_transitions(self):
        """Each state in the linear order can move to the next."""
        for i in range(len(WORKFLOW_ORDER) - 1):
            current = WORKFLOW_ORDER[i]
            target = WORKFLOW_ORDER[i + 1]
            assert valid_transition(current, target), (
                f"{current.name} -> {target.name} should be valid"
            )

    def test_any_non_terminal_can_fail(self):
        """Every non-terminal state can transition to FAILED."""
        for state in WORKFLOW_ORDER:
            assert valid_transition(state, WorkflowState.FAILED), (
                f"{state.name} -> FAILED should be valid"
            )

    def test_agent_running_to_completed(self):
        assert valid_transition(WorkflowState.AGENT_RUNNING, WorkflowState.COMPLETED)

    def test_cannot_skip_states(self):
        assert not valid_transition(WorkflowState.INIT, WorkflowState.PREPARING_SANDBOX)
        assert not valid_transition(
            WorkflowState.ENSURING_REPO, WorkflowState.AGENT_RUNNING
        )

    def test_cannot_go_backwards(self):
        assert not valid_transition(
            WorkflowState.CREATING_WORKTREE, WorkflowState.ENSURING_REPO
        )
        assert not valid_transition(WorkflowState.AGENT_RUNNING, WorkflowState.INIT)

    def test_terminal_states_have_no_transitions(self):
        assert not valid_transition(WorkflowState.COMPLETED, WorkflowState.INIT)
        assert not valid_transition(WorkflowState.COMPLETED, WorkflowState.FAILED)
        assert not valid_transition(WorkflowState.FAILED, WorkflowState.INIT)
        assert not valid_transition(WorkflowState.FAILED, WorkflowState.COMPLETED)

    def test_cannot_transition_to_init(self):
        """INIT is only a starting state, nothing transitions into it."""
        for state in WorkflowState:
            if state != WorkflowState.INIT:
                assert not valid_transition(state, WorkflowState.INIT)


class TestNextState:
    def test_next_from_init(self):
        assert next_state(WorkflowState.INIT) == WorkflowState.ENSURING_REPO

    def test_next_from_agent_running(self):
        """AGENT_RUNNING is last in order, next is None (must go to COMPLETED or FAILED)."""
        assert next_state(WorkflowState.AGENT_RUNNING) is None

    def test_next_from_terminal(self):
        assert next_state(WorkflowState.COMPLETED) is None
        assert next_state(WorkflowState.FAILED) is None

    def test_linear_chain(self):
        """Walking next_state from INIT covers the full order."""
        visited = []
        state = WorkflowState.INIT
        while state is not None:
            visited.append(state)
            state = next_state(state)
        assert visited == WORKFLOW_ORDER


class TestIsTerminal:
    def test_completed_is_terminal(self):
        assert is_terminal(WorkflowState.COMPLETED)

    def test_failed_is_terminal(self):
        assert is_terminal(WorkflowState.FAILED)

    def test_non_terminal_states(self):
        for state in WORKFLOW_ORDER:
            assert not is_terminal(state), f"{state.name} should not be terminal"
