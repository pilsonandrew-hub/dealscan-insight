from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Sequence

COMPLETION_VERBS = ("close", "done", "ship", "complete", "fix")
COMPLETION_VERB_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(verb) for verb in COMPLETION_VERBS) + r")\b",
    flags=re.IGNORECASE,
)

ADVISORY_PREFIX = "ACE false-closure advisory:"


def commit_message_has_completion_verbs(message: str) -> bool:
    return bool(COMPLETION_VERB_PATTERN.search(message))


def load_loose_end_rows(db_path: Path | str) -> list[dict[str, str]]:
    from ace.ace import _loose_end_rows

    return _loose_end_rows(db_path)


def format_false_closure_warning(
    *,
    loose_rows: Sequence[dict[str, str]],
    matched_verbs: Sequence[str],
    max_items: int = 5,
) -> str:
    item_ids = [str(row["item_id"]) for row in loose_rows]
    shown = item_ids[:max_items]
    suffix = ""
    if len(item_ids) > max_items:
        suffix = f" (+{len(item_ids) - max_items} more)"
    verb_label = ", ".join(sorted(set(matched_verbs)))
    items_label = ", ".join(shown) + suffix if shown else "unknown"
    return (
        f"{ADVISORY_PREFIX} commit message uses completion language ({verb_label}) "
        f"but ace loose-ends still reports {len(loose_rows)} open gap(s): {items_label}. "
        "Review with: ace loose-ends"
    )


def matched_completion_verbs(message: str) -> list[str]:
    return sorted({match.group(0).lower() for match in COMPLETION_VERB_PATTERN.finditer(message)})


def evaluate_false_closure_advisory(
    message: str,
    *,
    db_path: Path | str,
) -> str | None:
    if not commit_message_has_completion_verbs(message):
        return None
    loose_rows = load_loose_end_rows(db_path)
    if not loose_rows:
        return None
    return format_false_closure_warning(
        loose_rows=loose_rows,
        matched_verbs=matched_completion_verbs(message),
    )


def run_commit_msg_advisory(message_path: Path | str, *, db_path: Path | str) -> int:
    path = Path(message_path)
    message = path.read_text(encoding="utf-8", errors="replace")
    warning = evaluate_false_closure_advisory(message, db_path=db_path)
    if warning:
        print(warning, file=sys.stderr)
    return 0
