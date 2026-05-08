from __future__ import annotations

from typing import Any


def fetch_unprocessed_telegram_messages() -> list[dict[str, Any]]:
    """Bounded transport stub for cycle integration tests.

    Real inbound transport is intentionally not implemented in Slice 2.
    """
    return []
