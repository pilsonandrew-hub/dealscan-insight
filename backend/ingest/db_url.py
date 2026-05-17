"""Supabase direct Postgres URL resolution helpers for DealerScope ingest."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Optional
from urllib.parse import quote

_DIRECT_DB_ENV_KEYS = (
    "SUPABASE_DB_URL",
    "SUPABASE_DATABASE_URL",
    "SUPABASE_DIRECT_DB_URL",
)
_PROJECT_ID_ENV_KEYS = ("SUPABASE_PROJECT_ID", "VITE_SUPABASE_PROJECT_ID")


def derive_supabase_direct_db_url(values: Mapping[str, str | None]) -> Optional[str]:
    """Resolve the direct Supabase Postgres DSN from explicit or derived env values."""
    for key in _DIRECT_DB_ENV_KEYS:
        candidate = values.get(key)
        if candidate:
            return candidate

    db_password = values.get("SUPABASE_DB_PASSWORD")
    if not db_password:
        return None

    project_ref = None
    for key in _PROJECT_ID_ENV_KEYS:
        if values.get(key):
            project_ref = values[key]
            break

    supabase_url = values.get("SUPABASE_URL") or values.get("VITE_SUPABASE_URL")
    if not project_ref and supabase_url:
        match = re.search(r"https://([a-z0-9]+)\.supabase\.co", supabase_url)
        if match:
            project_ref = match.group(1)

    if not project_ref:
        return None

    return (
        f"postgresql://postgres:{quote(str(db_password), safe='')}"
        f"@db.{project_ref}.supabase.co:5432/postgres?sslmode=require"
    )


def derive_supabase_direct_db_url_from_env(environ: Mapping[str, str | None]) -> Optional[str]:
    """Compatibility convenience wrapper for environment mappings."""
    return derive_supabase_direct_db_url(environ)
