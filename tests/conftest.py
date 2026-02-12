"""Configure test path so superintendent packages are importable."""

import sys
from pathlib import Path

# Add src/ to path so `from superintendent.orchestrator.models import ...` works
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
