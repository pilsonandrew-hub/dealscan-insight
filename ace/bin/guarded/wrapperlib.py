#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ACE_DIR = Path(__file__).resolve().parents[2]
ROOT = ACE_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ace.scope_guard import ScopeAction, ScopeDecisionType, ScopeGuard, ScopeGuardError

AUTHORIZATION_PATH = ACE_DIR / "state" / "v1_1_required_items" / "authorization.json"
BLOCK_LOG_PATH = ACE_DIR / "state" / "v1_1_required_items" / "operator-scope-block-log.jsonl"

REAL_BINARIES = {
    "git": "/usr/bin/git",
    "sqlite3": "/usr/bin/sqlite3",
    "curl": "/usr/bin/curl",
    "python3": "/usr/bin/python3",
}

READ_ONLY_GIT = {"status", "diff", "log", "show", "rev-parse", "branch", "config"}
SIDE_EFFECT_GIT = {
    "add": "git_stage",
    "commit": "git_commit",
    "push": "git_push",
    "reset": "git_rewrite",
    "revert": "git_rewrite",
    "rebase": "git_rewrite",
    "checkout": "git_rewrite",
    "switch": "git_rewrite",
    "merge": "git_rewrite",
    "cherry-pick": "git_rewrite",
    "tag": "git_rewrite",
}
SQLITE_WRITE_TOKENS = (
    "insert", "update", "delete", "replace", "create", "drop", "alter", "pragma", "vacuum", "attach",
    "detach", "reindex", "begin", "commit", "rollback",
)
TELEGRAM_SEND_MARKERS = ("api.telegram.org", "/sendmessage", "/sendphoto", "/senddocument", "/sendmediagroup")


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv)
    wrapper_name = Path(raw[0]).name
    args = raw[1:]
    if wrapper_name not in REAL_BINARIES:
        return _deny_without_guard(wrapper_name, args, "unknown wrapper", action_class="config_change")

    real_binary = Path(REAL_BINARIES[wrapper_name])
    if not real_binary.exists():
        return _deny_without_guard(wrapper_name, args, f"real binary missing: {real_binary}", action_class="config_change")

    action = classify(wrapper_name, args)
    try:
        decision = ScopeGuard(AUTHORIZATION_PATH, BLOCK_LOG_PATH, ROOT).authorize(action)
    except ScopeGuardError as exc:
        _log_direct_block(action, str(exc))
        print(f"ACE guarded wrapper refused {wrapper_name}: {exc}", file=sys.stderr)
        return 1
    if decision.decision is not ScopeDecisionType.ALLOW:
        print(
            f"ACE guarded wrapper refused {wrapper_name}: {decision.decision.value}: {decision.reason}",
            file=sys.stderr,
        )
        return 1

    os.execv(str(real_binary), [str(real_binary), *args])
    return 127  # pragma: no cover - os.execv replaces this process on success


def classify(wrapper_name: str, args: Sequence[str]) -> ScopeAction:
    command = " ".join([wrapper_name, *args]).strip()
    if wrapper_name == "git":
        subcommand = _first_git_subcommand(args)
        paths = tuple(_git_candidate_paths(subcommand, args))
        if subcommand in READ_ONLY_GIT:
            return ScopeAction("read", paths=paths, command=command, description="guarded git read-only command")
        return ScopeAction(SIDE_EFFECT_GIT.get(subcommand, "git_rewrite"), paths=paths, command=command, description="guarded git command")
    if wrapper_name == "sqlite3":
        db_paths = tuple(arg for arg in args if arg.endswith((".db", ".sqlite", ".sqlite3")))
        query_text = " ".join(arg for arg in args if not arg.startswith("-") and not arg.endswith((".db", ".sqlite", ".sqlite3")))
        if _sqlite_query_is_read_only(query_text):
            return ScopeAction("read", paths=db_paths, command=command, description="guarded sqlite read-only command")
        return ScopeAction("db_mutation", paths=db_paths, command=command, description="guarded sqlite mutation command")
    if wrapper_name == "curl":
        destination = _curl_destination(args)
        if _curl_is_external_send(args):
            return ScopeAction("external_send", command=command, destination=destination, description="guarded curl external send")
        return ScopeAction("read", command=command, destination=destination, description="guarded curl read-only command")
    if wrapper_name == "python3":
        if _contains_inline_eval(args):
            return ScopeAction("test_side_effecting", command=command, description="guarded python inline eval")
        paths = tuple(arg for arg in args if arg.endswith(".py"))
        if _looks_like_test_command(args):
            return ScopeAction("test_side_effecting", paths=paths, command=command, description="guarded python test command")
        return ScopeAction("read", paths=paths, command=command, description="guarded python command")
    return ScopeAction("config_change", command=command, description="guarded unknown command")


def _first_git_subcommand(args: Sequence[str]) -> str:
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-C", "-c", "--git-dir", "--work-tree"}:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        return arg.lower()
    return "status"


def _git_candidate_paths(subcommand: str, args: Sequence[str]) -> list[str]:
    if "--" in args:
        index = list(args).index("--")
        return [arg for arg in args[index + 1 :] if not arg.startswith("-")]
    if subcommand == "add":
        return [arg for arg in args[1:] if not arg.startswith("-")]
    return []


def _sqlite_query_is_read_only(query: str) -> bool:
    stripped = query.strip().lower()
    if not stripped:
        return False
    compact = stripped.replace("\n", " ").replace("\t", " ")
    if any(token in compact for token in SQLITE_WRITE_TOKENS):
        return False
    return compact.startswith(("select", ".schema", ".tables", ".indexes"))


def _curl_destination(args: Sequence[str]) -> str | None:
    for arg in args:
        if arg.startswith("http://") or arg.startswith("https://"):
            return arg
    return None


def _curl_is_external_send(args: Sequence[str]) -> bool:
    joined = " ".join(args).lower()
    if any(marker in joined for marker in TELEGRAM_SEND_MARKERS):
        return True
    return any(arg in {"-x", "-X", "--request"} for arg in args) and "post" in joined


def _contains_inline_eval(args: Sequence[str]) -> bool:
    return any(arg in {"-c", "-m"} for arg in args)


def _looks_like_test_command(args: Sequence[str]) -> bool:
    joined = " ".join(args).lower()
    return "unittest" in joined or "pytest" in joined or "ace.tests" in joined or "/tests/" in joined


def _deny_without_guard(wrapper_name: str, args: Sequence[str], reason: str, *, action_class: str) -> int:
    action = ScopeAction(action_class, command=" ".join([wrapper_name, *args]).strip(), description="guarded wrapper setup failure")
    _log_direct_block(action, reason)
    print(f"ACE guarded wrapper refused {wrapper_name}: {reason}", file=sys.stderr)
    return 1


def _log_direct_block(action: ScopeAction, reason: str) -> None:
    BLOCK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BLOCK_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "action_class": action.action_class,
            "command": action.command,
            "decision": "BLOCK",
            "description": action.description,
            "destination": action.destination,
            "paths": list(action.paths),
            "reason": reason,
            "source": "ace.bin.guarded",
        }, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
