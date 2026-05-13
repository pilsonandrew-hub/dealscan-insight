"""Local Python path bootstrap for ACE repo-root commands.

When commands are run from the nested `ace/` repo root, Python can resolve
`import ace` to `ace.py` instead of the package directory from the workspace
parent. Put the workspace root before the current directory so both supported
test invocations work:

- from workspace root: python -m unittest discover ace/tests
- from ace repo root: python -m unittest discover tests
"""

from __future__ import annotations

import sys
from pathlib import Path

_WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
while _WORKSPACE_ROOT in sys.path:
    sys.path.remove(_WORKSPACE_ROOT)
sys.path.insert(0, _WORKSPACE_ROOT)
