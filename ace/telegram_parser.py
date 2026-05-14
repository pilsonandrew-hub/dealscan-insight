from __future__ import annotations

from dataclasses import dataclass


_DIRECT_MARKERS = (
    "can you ",
    "please ",
    "check ",
    "follow up",
    "look into",
    "remind me",
    "make sure",
)

_DIRECT_PREFIXES = (
    "audit ",
    "verify ",
    "inspect ",
    "investigate ",
    "review ",
    "run ",
    "fix ",
    "harden ",
    "summarize ",
    "write ",
    "create ",
    "update ",
)

_STRONG_DIRECT_PATTERNS = (
    "do not ",
    "don't ",
    "keep working",
    "continue",
    "proceed",
)


@dataclass(frozen=True)
class TelegramParseResult:
    actionable: bool
    classification: str
    title: str | None
    description: str | None
    parser_rule: str
    parser_reason: str
    source_text: str
    source_chat_id: str
    source_message_id: str
    source_received_at: str


def parse_telegram_message(
    text: str,
    *,
    chat_id: str,
    message_id: str,
    received_at: str,
) -> TelegramParseResult:
    normalized = " ".join(text.split())
    if not normalized:
        return TelegramParseResult(
            actionable=False,
            classification="ignore",
            title=None,
            description=None,
            parser_rule="empty_text",
            parser_reason="telegram message text was empty after normalization",
            source_text=normalized,
            source_chat_id=chat_id,
            source_message_id=message_id,
            source_received_at=received_at,
        )

    lowered = normalized.lower()
    matched_marker = next((marker for marker in _DIRECT_MARKERS if marker in lowered), None)
    if matched_marker is None:
        matched_marker = next((marker for marker in _DIRECT_PREFIXES if lowered.startswith(marker)), None)
    if matched_marker is None:
        matched_marker = next((marker for marker in _STRONG_DIRECT_PATTERNS if marker in lowered), None)
    if matched_marker is None:
        return TelegramParseResult(
            actionable=False,
            classification="ignore",
            title=None,
            description=None,
            parser_rule="no_direct_work_rule_matched",
            parser_reason="no bounded direct-work marker matched inbound telegram message",
            source_text=normalized,
            source_chat_id=chat_id,
            source_message_id=message_id,
            source_received_at=received_at,
        )

    return TelegramParseResult(
        actionable=True,
        classification="direct_work",
        title=normalized[:120],
        description=normalized,
        parser_rule="bounded_direct_work_rule",
        parser_reason=f"matched direct-work marker: {matched_marker.strip()}",
        source_text=normalized,
        source_chat_id=chat_id,
        source_message_id=message_id,
        source_received_at=received_at,
    )
