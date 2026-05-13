"""ACE test package bootstrap.

Keeps unittest discovery stable when run from either the workspace root
(`python -m unittest discover ace/tests`) or the ACE repo root
(`python -m unittest discover tests`).
"""

from __future__ import annotations

import sys
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))
