"""Configure test path so orchestrator and state packages are importable."""

import sys
from pathlib import Path

# Add scripts/ to path so `from orchestrator.models import ...` works
scripts_dir = Path(__file__).resolve().parent.parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))
