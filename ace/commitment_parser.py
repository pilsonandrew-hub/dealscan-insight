from __future__ import annotations

import re
from dataclasses import dataclass

COMMITMENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("commitment_i_will", re.compile(r"\bi will\b", re.IGNORECASE)),
    ("commitment_i_need_to", re.compile(r"\bi need to\b", re.IGNORECASE)),
    ("commitment_let_me", re.compile(r"\blet me\b", re.IGNORECASE)),
    ("commitment_remember_to", re.compile(r"\bremember to\b", re.IGNORECASE)),
)


@dataclass(frozen=True)
class CommitmentParseResult:
    actionable: bool
    parser_rule: str
    matched_phrase: str
    title: str
    description: str
    source_text: str


def _title_from_commitment(text: str, *, match: re.Match[str]) -> str:
    tail = text[match.end() :].strip(" .,:;-")
    if not tail:
        tail = text.strip()
    if len(tail) > 120:
        return tail[:117] + "..."
    return tail


def parse_commitment_message(text: str) -> CommitmentParseResult:
    normalized = " ".join(text.split())
    if not normalized:
        return CommitmentParseResult(
            actionable=False,
            parser_rule="empty_text",
            matched_phrase="",
            title="",
            description="",
            source_text=normalized,
        )

    for rule_name, pattern in COMMITMENT_RULES:
        match = pattern.search(normalized)
        if match is None:
            continue
        return CommitmentParseResult(
            actionable=True,
            parser_rule=rule_name,
            matched_phrase=match.group(0).lower(),
            title=_title_from_commitment(normalized, match=match),
            description=normalized,
            source_text=normalized,
        )

    return CommitmentParseResult(
        actionable=False,
        parser_rule="no_commitment_rule_matched",
        matched_phrase="",
        title="",
        description="",
        source_text=normalized,
    )
