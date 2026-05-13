"""Import shim for running ACE tests from the nested ACE repo root.

`python -m unittest discover tests` adds this tests directory to sys.path.
Without this shim, `import ace.*` resolves to ../ace.py as a plain module,
which is not a package. Expose the ACE repo root as the package search path
so repo-root and workspace-root test commands both work.
"""

from __future__ import annotations

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[1])]
