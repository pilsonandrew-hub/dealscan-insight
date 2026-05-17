"""Environment parsing helpers for DealerScope ingest."""

from __future__ import annotations

import logging
from collections.abc import Mapping

logger = logging.getLogger(__name__)


def env_float(
    values: Mapping[str, str | None],
    name: str,
    default: float,
    *,
    log: logging.Logger | None = None,
    context: str = "INGEST_ENV",
) -> float:
    raw_value = values.get(name)
    if raw_value in {None, ""}:
        return default
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        (log or logger).warning("[%s] Invalid %s=%r; using %s", context, name, raw_value, default)
        return default


def env_int(
    values: Mapping[str, str | None],
    name: str,
    default: int,
    *,
    log: logging.Logger | None = None,
    context: str = "INGEST_ENV",
) -> int:
    raw_value = values.get(name)
    if raw_value in {None, ""}:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        (log or logger).warning("[%s] Invalid %s=%r; using %s", context, name, raw_value, default)
        return default
