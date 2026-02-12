# Superintendent: Agent Orchestration Architecture

## Vision

A testable, maintainable orchestration system for spawning autonomous Claude agents
in isolated Docker sandboxes, with proper state management and feedback loops.

## Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                            │
│  (Stateless - takes inputs, produces WorkflowPlan)          │
├─────────────────────────────────────────────────────────────┤
│  Inputs:                                                     │
│    - repo: Path | URL                                        │
│    - task: str                                               │
│    - execution_mode: sandbox | local                         │
│    - options: branch, context_file, etc.                     │
│                                                              │
│  Output: WorkflowPlan                                        │
│    - steps: List[WorkflowStep]                               │
│    - metadata: repo_name, branch, sandbox_name, etc.         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Executor                               │
│  (Stateful - runs steps, manages state, handles errors)     │
├─────────────────────────────────────────────────────────────┤
│  - Runs each WorkflowStep through appropriate Backend       │
│  - Saves checkpoints for resume                              │
│  - Handles errors with rollback/retry logic                  │
│  - Emits events for observability                            │
│                                                              │
│  State Machine:                                              │
│    INIT → CLONING → SANDBOX_READY → AGENT_RUNNING           │
│         → COMPLETED | FAILED                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Backends                               │
│  (Abstractions over external systems)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DockerBackend          GitBackend          TerminalBackend  │
│  ├─ create_sandbox()    ├─ clone()          ├─ spawn()       │
│  ├─ start_sandbox()     ├─ create_worktree()├─ wait()        │
│  ├─ stop_sandbox()      ├─ fetch()          └─ is_running()  │
│  ├─ exec_in_sandbox()   ├─ checkout()                        │
│  ├─ sandbox_exists()    └─ ensure_local()   AuthBackend      │
│  └─ list_sandboxes()                        ├─ setup_git_auth│
│                                              ├─ inject_token  │
│  Each backend has:                           ├─ validate_token│
│    - Real implementation (actual systems)    └─ setup_ssh_key │
│    - Mock implementation (for testing)                        │
│    - DryRun implementation (prints commands)                 │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. One Sandbox Per Repository

```
Sandbox naming: claude-{repo-name}
Workspace: passed as arg to `docker sandbox run`

Benefits:
- Auth persists across runs (login once per repo)
- Simpler sandbox management
- Resume is trivial (sandbox already exists)
```

### 2. Explicit Workflow Steps

```python
@dataclass
class WorkflowStep:
    id: str
    action: str  # "clone", "create_sandbox", "start_agent", etc.
    params: dict
    depends_on: list[str]  # Step IDs this depends on

@dataclass
class WorkflowPlan:
    steps: list[WorkflowStep]
    metadata: dict

    def to_json(self) -> str: ...  # For dry-run output
    def from_checkpoint(cls, path: Path) -> "WorkflowPlan": ...
```

### 3. State Machine for Execution

```python
class WorkflowState(Enum):
    INIT = auto()
    ENSURING_REPO = auto()      # Clone if URL, validate if path
    CREATING_WORKTREE = auto()  # git worktree add
    PREPARING_SANDBOX = auto()  # docker sandbox create/start
    AUTHENTICATING = auto()     # gh auth in sandbox
    INITIALIZING_STATE = auto() # .ralph/ setup
    STARTING_AGENT = auto()     # Terminal spawn
    AGENT_RUNNING = auto()      # Monitoring (optional)
    COMPLETED = auto()
    FAILED = auto()
```

### 4. Backend Abstraction

```python
class DockerBackend(Protocol):
    def sandbox_exists(self, name: str) -> bool: ...
    def create_sandbox(self, name: str, workspace: Path, template: str | None) -> bool: ...
    def start_sandbox(self, name: str) -> bool: ...
    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]: ...
    def run_agent(self, name: str, workspace: Path, prompt: str) -> bool: ...

class RealDockerBackend(DockerBackend):
    """Actually runs docker commands"""

class MockDockerBackend(DockerBackend):
    """Returns canned responses for testing"""

class DryRunDockerBackend(DockerBackend):
    """Prints what would be run"""
```

### 5. Checkpoint/Resume

```python
# Saved to .ralph/workflow_state.json
{
    "workflow_id": "abc123",
    "current_state": "AGENT_RUNNING",
    "completed_steps": ["clone", "create_sandbox", "auth"],
    "sandbox_name": "claude-my-repo",
    "worktree_path": "/path/to/worktree",
    "started_at": "2024-02-07T10:00:00Z",
    "last_checkpoint": "2024-02-07T10:05:00Z"
}
```

## File Structure

```
superintendent/
├── .claude-plugin/
│   ├── marketplace.json
│   └── plugin.json
├── commands/
│   ├── spawn.md
│   ├── ralph.md
│   ├── list.md
│   ├── resume.md
│   └── cleanup.md
├── src/
│   └── superintendent/
│       ├── orchestrator/
│       │   ├── __init__.py
│       │   ├── planner.py      # Creates WorkflowPlan
│       │   ├── executor.py     # Runs steps, manages state
│       │   ├── step_handler.py # Executes individual steps
│       │   └── models.py       # WorkflowStep, WorkflowPlan, etc.
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── docker.py       # DockerBackend implementations
│       │   ├── git.py          # GitBackend implementations
│       │   ├── terminal.py     # TerminalBackend implementations
│       │   ├── auth.py         # AuthBackend implementations
│       │   └── factory.py      # Backend factory and DI
│       ├── state/
│       │   ├── __init__.py
│       │   ├── workflow.py     # Workflow state machine
│       │   ├── ralph.py        # .ralph/ directory management
│       │   ├── checkpoint.py   # Checkpoint/resume support
│       │   └── registry.py     # Global entry registry
│       └── cli/
│           └── main.py         # CLI entry point
├── tests/
│   ├── test_planner.py
│   ├── test_executor.py
│   ├── test_step_handler.py
│   ├── test_backends.py
│   └── test_e2e.py
├── docs/
│   ├── BEADS_BEST_PRACTICES.md
│   └── ARCHITECTURE.md
└── CLAUDE.md
```

## Testing Strategy

### Unit Tests (Fast, No External Deps)

```python
def test_planner_creates_correct_steps():
    plan = Planner().create_plan(
        repo=Path("/test/repo"),
        task="implement feature",
        mode="sandbox"
    )
    assert len(plan.steps) == 6
    assert plan.steps[0].action == "validate_repo"
    assert plan.steps[-1].action == "start_agent"

def test_executor_handles_step_failure():
    mock_backend = MockDockerBackend(fail_on="create_sandbox")
    executor = Executor(docker=mock_backend)
    result = executor.run(plan)
    assert result.state == WorkflowState.FAILED
    assert result.failed_step == "create_sandbox"
```

### Integration Tests (With Mocks)

```python
def test_full_workflow_with_mocks():
    executor = Executor(
        docker=MockDockerBackend(),
        git=MockGitBackend(),
        terminal=MockTerminalBackend()
    )
    result = executor.run(plan)
    assert result.state == WorkflowState.AGENT_RUNNING
```

### E2E Tests (Actual Docker, CI only)

```python
@pytest.mark.e2e
def test_superintendent_spawns_sandbox():
    result = subprocess.run([
        "superintendent", "run",
        "--repo", TEST_REPO,
        "--task", "test task",
        "--wait"  # Wait for agent to start
    ])
    assert result.returncode == 0
    # Verify sandbox exists
    assert subprocess.run(["docker", "sandbox", "ls"]).returncode == 0
```

### Dry-Run Tests

```python
def test_dryrun_shows_all_commands():
    output = subprocess.check_output([
        "superintendent", "run",
        "--repo", "https://github.com/test/repo",
        "--task", "test",
        "--dry-run"
    ])
    assert "git clone" in output
    assert "docker sandbox create" in output
    assert "docker sandbox run" in output
```

## Beads Epic Structure

```
wt2-xxx: Epic: Core Architecture
├── wt2-xxx.1: Implement WorkflowStep and WorkflowPlan models
├── wt2-xxx.2: Implement Planner (creates workflow from inputs)
├── wt2-xxx.3: Implement Executor (runs steps, manages state)
└── wt2-xxx.4: Implement state machine with transitions

wt2-yyy: Epic: Backends
├── wt2-yyy.1: DockerBackend (Real, Mock, DryRun)
├── wt2-yyy.2: GitBackend (Real, Mock, DryRun)
├── wt2-yyy.3: TerminalBackend (Real, Mock, DryRun)
└── wt2-yyy.4: Backend factory and dependency injection

wt2-zzz: Epic: State Management
├── wt2-zzz.1: Workflow checkpoint/resume
├── wt2-zzz.2: Ralph state (.ralph/ directory)
└── wt2-zzz.3: Global entry registry

wt2-aaa: Epic: CLI & Commands
├── wt2-aaa.1: superintendent CLI with all flags
├── wt2-aaa.2: Slash command .md files
└── wt2-aaa.3: Resume and cleanup commands

wt2-bbb: Epic: Testing
├── wt2-bbb.1: Unit tests for planner/executor
├── wt2-bbb.2: Integration tests with mock backends
├── wt2-bbb.3: E2E test script
└── wt2-bbb.4: Dry-run verification tests

wt2-ccc: Epic: Documentation & Polish
├── wt2-ccc.1: CLAUDE.md with project context
├── wt2-ccc.2: README with usage examples
└── wt2-ccc.3: Inline code documentation
```
