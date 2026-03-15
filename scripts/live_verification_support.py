"""Shared helpers for live production verification scripts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


DEFAULT_ENV_FILES = (
    ".env.live",
    ".env.local",
    ".env",
)

DATABASE_URL_KEYS = (
    "DATABASE_URL",
    "SUPABASE_DB_URL",
    "SUPABASE_DATABASE_URL",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def get_database_url(
    explicit_dsn: Optional[str],
    env_file: Optional[str] = None,
) -> Optional[str]:
    if explicit_dsn:
        return explicit_dsn

    for key in DATABASE_URL_KEYS:
        value = os.getenv(key)
        if value:
            return value

    search_paths: list[Path] = []
    if env_file:
        search_paths.append(Path(env_file))
    else:
        search_paths.extend(Path(candidate) for candidate in DEFAULT_ENV_FILES)

    for path in search_paths:
        if not path.exists():
            continue
        file_values = _parse_env_file(path)
        for key in DATABASE_URL_KEYS:
            value = file_values.get(key)
            if value:
                return value

    return None
