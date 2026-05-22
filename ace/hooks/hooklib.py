#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ace.scope_guard import ScopeAction, ScopeDecisionType, ScopeGuard, ScopeGuardError

AUTHORIZATION_PATH = ROOT / "ace" / "state" / "v1_1_required_items" / "authorization.json"
BLOCK_LOG_PATH = ROOT / "ace" / "state" / "v1_1_required_items" / "operator-scope-block-log.jsonl"

PROTECTED_PATTERNS = (
    "ace/*.py",
    "ace/**/*.py",
    "ace/tests/**",
    "ace/state/*.db",
    "ace/state/*.sqlite",
    "ace/state/telegram_runtime.db",
    "ace/state/v1_1_required_items/**",
    "ace/hooks/**",
    ".github/workflows/**",
)


def main(argv: Sequence[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "pre-commit":
        return pre_commit()
    if command == "commit-msg":
        if len(argv) != 3:
            return _fail("usage: hooklib.py commit-msg <message-file>")
        return commit_msg(Path(argv[2]))
    if command == "pre-push":
        return pre_push(sys.stdin.read())
    if command == "pre-rebase":
        return pre_rebase()
    if command == "post-checkout":
        return post_checkout()
    return _fail(f"unknown hook command: {command}")


def pre_commit() -> int:
    paths = _git_lines("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return _authorize_git_action(
        "git_commit",
        paths,
        command="git commit",
        description="pre-commit staged path authorization",
    )


def commit_msg(message_path: Path) -> int:
    message = message_path.read_text(encoding="utf-8", errors="replace")
    if "Operator-Scope:" not in message:
        _log_direct_block(
            action_class="git_commit",
            paths=tuple(_git_lines("diff", "--cached", "--name-only", "--diff-filter=ACMR")),
            command="git commit",
            description="commit-msg missing Operator-Scope trailer",
            reason="commit message missing Operator-Scope trailer",
        )
        print("ACE operator-scope hook refused commit: missing Operator-Scope trailer", file=sys.stderr)
        return 1
    return 0


def pre_push(stdin_payload: str) -> int:
    paths: set[str] = set()
    for line in stdin_payload.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local_sha = parts[1]
        remote_sha = parts[3]
        if _is_delete_sha(local_sha):
            continue
        if _is_zero_sha(remote_sha):
            rev = f"{local_sha}^..{local_sha}"
        else:
            rev = f"{remote_sha}..{local_sha}"
        changed = _git_lines("diff", "--name-only", "--diff-filter=ACMR", rev)
        if not changed and _is_zero_sha(remote_sha):
            changed = _git_lines("show", "--pretty=format:", "--name-only", "--diff-filter=ACMR", local_sha)
        paths.update(changed)
    if not paths:
        paths.update(_git_lines("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
    protected_paths = _protected_paths(paths)
    if not protected_paths:
        return 0
    return _authorize_git_action(
        "git_push",
        sorted(protected_paths),
        command="git push",
        description="pre-push protected path authorization",
    )


def pre_rebase() -> int:
    return _authorize_git_action(
        "git_rewrite",
        (),
        command="git rebase",
        description="pre-rebase rewrite authorization",
    )


def post_checkout() -> int:
    try:
        ScopeGuard(AUTHORIZATION_PATH, BLOCK_LOG_PATH, ROOT).load()
    except ScopeGuardError as exc:
        print(f"ACE operator-scope hook warning: authorization invalid after checkout: {exc}", file=sys.stderr)
    return 0


def _authorize_git_action(action_class: str, paths: Iterable[str], *, command: str, description: str) -> int:
    path_tuple = tuple(paths)
    try:
        decision = ScopeGuard(AUTHORIZATION_PATH, BLOCK_LOG_PATH, ROOT).authorize(
            ScopeAction(action_class, paths=path_tuple, command=command, description=description)
        )
    except ScopeGuardError as exc:
        _log_direct_block(
            action_class=action_class,
            paths=path_tuple,
            command=command,
            description=description,
            reason=str(exc),
        )
        print(f"ACE operator-scope hook refused {command}: {exc}", file=sys.stderr)
        return 1
    if decision.decision is not ScopeDecisionType.ALLOW:
        print(f"ACE operator-scope hook refused {command}: {decision.decision.value}: {decision.reason}", file=sys.stderr)
        return 1
    return 0


def _log_direct_block(*, action_class: str, paths: tuple[str, ...], command: str, description: str, reason: str) -> None:
    BLOCK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "action_class": action_class,
        "command": command,
        "decision": "BLOCK",
        "description": description,
        "paths": list(paths),
        "reason": reason,
        "source": "ace.hooks",
    }
    with BLOCK_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _protected_paths(paths: Iterable[str]) -> set[str]:
    import fnmatch

    return {path for path in paths if any(fnmatch.fnmatch(path, pattern) for pattern in PROTECTED_PATTERNS)}


def _git_lines(*args: str) -> list[str]:
    result = subprocess.run(("git", *args), cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_zero_sha(value: str) -> bool:
    return bool(value) and set(value) == {"0"}


def _is_delete_sha(value: str) -> bool:
    return _is_zero_sha(value)


def _fail(message: str) -> int:
    print(f"ACE operator-scope hook error: {message}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
