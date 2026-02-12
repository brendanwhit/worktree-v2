"""WorkflowState enum and transition validation."""

from enum import Enum, auto


class WorkflowState(Enum):
    INIT = auto()
    ENSURING_REPO = auto()
    CREATING_WORKTREE = auto()
    PREPARING_SANDBOX = auto()
    AUTHENTICATING = auto()
    INITIALIZING_STATE = auto()
    STARTING_AGENT = auto()
    AGENT_RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


# Valid transitions: state -> set of states it can move to.
# FAILED is reachable from any non-terminal state.
_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.INIT: {WorkflowState.ENSURING_REPO, WorkflowState.FAILED},
    WorkflowState.ENSURING_REPO: {
        WorkflowState.CREATING_WORKTREE,
        WorkflowState.FAILED,
    },
    WorkflowState.CREATING_WORKTREE: {
        WorkflowState.PREPARING_SANDBOX,
        WorkflowState.FAILED,
    },
    WorkflowState.PREPARING_SANDBOX: {
        WorkflowState.AUTHENTICATING,
        WorkflowState.FAILED,
    },
    WorkflowState.AUTHENTICATING: {
        WorkflowState.INITIALIZING_STATE,
        WorkflowState.FAILED,
    },
    WorkflowState.INITIALIZING_STATE: {
        WorkflowState.STARTING_AGENT,
        WorkflowState.FAILED,
    },
    WorkflowState.STARTING_AGENT: {WorkflowState.AGENT_RUNNING, WorkflowState.FAILED},
    WorkflowState.AGENT_RUNNING: {WorkflowState.COMPLETED, WorkflowState.FAILED},
    WorkflowState.COMPLETED: set(),
    WorkflowState.FAILED: set(),
}

# The linear progression order (excluding terminal states)
WORKFLOW_ORDER: list[WorkflowState] = [
    WorkflowState.INIT,
    WorkflowState.ENSURING_REPO,
    WorkflowState.CREATING_WORKTREE,
    WorkflowState.PREPARING_SANDBOX,
    WorkflowState.AUTHENTICATING,
    WorkflowState.INITIALIZING_STATE,
    WorkflowState.STARTING_AGENT,
    WorkflowState.AGENT_RUNNING,
]


def valid_transition(current: WorkflowState, target: WorkflowState) -> bool:
    """Check if transitioning from current to target is allowed."""
    return target in _TRANSITIONS.get(current, set())


def next_state(current: WorkflowState) -> WorkflowState | None:
    """Return the next state in the linear progression, or None if terminal."""
    try:
        idx = WORKFLOW_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 < len(WORKFLOW_ORDER):
        return WORKFLOW_ORDER[idx + 1]
    return None


def is_terminal(state: WorkflowState) -> bool:
    """Return True if the state is a terminal state (COMPLETED or FAILED)."""
    return state in (WorkflowState.COMPLETED, WorkflowState.FAILED)
