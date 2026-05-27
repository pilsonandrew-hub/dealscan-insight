from __future__ import annotations

import subprocess
import sys
from pathlib import Path

OPERATIONAL_HOOKS_PATH = Path("ace/hooks/operational")
COMMIT_MSG_HOOK = OPERATIONAL_HOOKS_PATH / "commit-msg"


def default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def operational_hooks_path(repo_root: Path | None = None) -> Path:
    root = repo_root or default_repo_root()
    return root / OPERATIONAL_HOOKS_PATH


def install_operational_hooks(*, repo_root: Path | None = None) -> int:
    root = repo_root or default_repo_root()
    hook_path = operational_hooks_path(root)
    commit_msg = hook_path / "commit-msg"
    if not commit_msg.is_file():
        print(f"error=missing hook script: {commit_msg}", file=sys.stderr)
        return 1

    relative_hooks = OPERATIONAL_HOOKS_PATH.as_posix()
    result = subprocess.run(
        ["git", "config", "core.hooksPath", relative_hooks],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        print(f"error=git config core.hooksPath failed: {stderr}", file=sys.stderr)
        return 1

    print(f"hooks.installed_path={relative_hooks}")
    print("hooks.advisory=commit-msg false-closure (non-blocking)")
    print("hooks.note=completion-verb check runs at commit-msg when the message is available")
    return 0


def status_operational_hooks(*, repo_root: Path | None = None) -> int:
    root = repo_root or default_repo_root()
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    configured = (result.stdout or "").strip()
    expected = OPERATIONAL_HOOKS_PATH.as_posix()
    if result.returncode != 0 or not configured:
        print("hooks.status=not_installed")
        return 0
    active = configured == expected
    print(f"hooks.status={'active' if active else 'other'}")
    print(f"hooks.configured_path={configured}")
    print(f"hooks.expected_path={expected}")
    return 0


def run_hooks_command(command: str, *, repo_root: Path | None = None) -> int:
    if command == "install":
        return install_operational_hooks(repo_root=repo_root)
    if command == "status":
        return status_operational_hooks(repo_root=repo_root)
    print(f"error=unknown hooks command: {command}", file=sys.stderr)
    return 1
