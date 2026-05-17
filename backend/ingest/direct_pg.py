"""Small direct-Postgres value adapters for ingest fallback paths."""

from __future__ import annotations

from typing import Any

from psycopg2 import extras as psycopg2_extras


def prepare_direct_pg_value(value: Any) -> Any:
    if isinstance(value, dict):
        return psycopg2_extras.Json(value)
    return value
