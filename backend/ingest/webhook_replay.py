"""Pure helpers for Apify webhook replay detection."""

from __future__ import annotations

from typing import Optional


BLOCKING_REPLAY_STATUSES = {"pending", "processing", "processed"}


def select_recent_replay_row(rows: list[dict]) -> Optional[dict]:
    for row in rows:
        status = str(row.get("processing_status") or "").lower()
        # Block duplicate deliveries once a run is already claimed or processed.
        # Duplicate Apify webhooks can arrive nearly simultaneously; allowing a
        # second delivery while the first is still "pending" can enqueue the same
        # run twice before either row reaches "processed". Error/degraded rows
        # remain retryable so a genuinely failed run can be replayed.
        if status in BLOCKING_REPLAY_STATUSES:
            return row
    return None
