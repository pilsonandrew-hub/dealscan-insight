"""Shared helpers for live production verification scripts."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import quote


DEFAULT_ENV_FILES = (
    ".env.live",
    ".env.local",
    ".env",
)

DIRECT_DATABASE_URL_KEYS = (
    "SUPABASE_DB_URL",
    "SUPABASE_DATABASE_URL",
    "SUPABASE_DIRECT_DB_URL",
)

DATABASE_URL_KEYS = (*DIRECT_DATABASE_URL_KEYS, "DATABASE_URL")
PROJECT_ID_KEYS = ("SUPABASE_PROJECT_ID", "VITE_SUPABASE_PROJECT_ID")
SUPABASE_URL_KEYS = ("SUPABASE_URL", "VITE_SUPABASE_URL")
POOLER_HOST_KEYS = ("SUPABASE_DB_POOLER_HOST", "SUPABASE_POOLER_HOST")
POOLER_PORT_KEYS = ("SUPABASE_DB_POOLER_PORT", "SUPABASE_POOLER_PORT")


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


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_project_ref(values: Mapping[str, str]) -> str:
    for key in PROJECT_ID_KEYS:
        project_ref = (values.get(key) or "").strip()
        if project_ref:
            return project_ref

    for key in SUPABASE_URL_KEYS:
        supabase_url = (values.get(key) or "").strip()
        if not supabase_url:
            continue
        match = re.search(r"https://([a-z0-9]+)\.supabase\.co", supabase_url)
        if match:
            return match.group(1)

    return ""


def _derive_supabase_pooler_db_url(values: Mapping[str, str]) -> Optional[str]:
    if not _truthy(values.get("SUPABASE_USE_POOLER")):
        return None

    db_password = (values.get("SUPABASE_DB_PASSWORD") or "").strip()
    project_ref = _resolve_project_ref(values)
    if not db_password or not project_ref:
        return None

    pooler_host = ""
    for key in POOLER_HOST_KEYS:
        pooler_host = (values.get(key) or "").strip()
        if pooler_host:
            break
    if not pooler_host:
        return None

    pooler_port = "6543"
    for key in POOLER_PORT_KEYS:
        configured_port = (values.get(key) or "").strip()
        if configured_port:
            pooler_port = configured_port
            break

    return (
        f"postgresql://postgres.{project_ref}:{quote(db_password, safe='')}"
        f"@{pooler_host}:{pooler_port}/postgres?sslmode=require"
    )


def _derive_supabase_direct_db_url(values: Mapping[str, str]) -> Optional[str]:
    for key in DIRECT_DATABASE_URL_KEYS:
        candidate = (values.get(key) or "").strip()
        if candidate:
            return candidate

    db_password = (values.get("SUPABASE_DB_PASSWORD") or "").strip()
    if not db_password:
        return None

    project_ref = _resolve_project_ref(values)
    if not project_ref:
        return None

    return (
        f"postgresql://postgres:{quote(db_password, safe='')}"
        f"@db.{project_ref}.supabase.co:5432/postgres?sslmode=require"
    )


def _resolve_database_url_from_values(
    values: Mapping[str, str],
    scope: str,
) -> tuple[Optional[str], Optional[str]]:
    for key in DIRECT_DATABASE_URL_KEYS:
        candidate = (values.get(key) or "").strip()
        if candidate:
            return candidate, f"{scope}.{key}"

    pooler = _derive_supabase_pooler_db_url(values)
    if pooler:
        return pooler, f"{scope}.derived_supabase_pooler"

    derived = _derive_supabase_direct_db_url(values)
    if derived:
        return derived, f"{scope}.derived_supabase_direct"

    database_url = (values.get("DATABASE_URL") or "").strip()
    if database_url:
        return database_url, f"{scope}.DATABASE_URL"

    return None, None


def resolve_database_url(
    explicit_dsn: Optional[str],
    env_file: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    if explicit_dsn:
        return explicit_dsn, "explicit_dsn"

    dsn, source = _resolve_database_url_from_values(os.environ, "env")
    if dsn:
        return dsn, source

    search_paths: list[Path] = []
    if env_file:
        search_paths.append(Path(env_file))
    else:
        search_paths.extend(Path(candidate) for candidate in DEFAULT_ENV_FILES)

    for path in search_paths:
        if not path.exists():
            continue
        file_values = _parse_env_file(path)
        dsn, source = _resolve_database_url_from_values(file_values, "env_file")
        if dsn:
            return dsn, source

    return None, None


def get_database_url(
    explicit_dsn: Optional[str],
    env_file: Optional[str] = None,
) -> Optional[str]:
    dsn, _source = resolve_database_url(explicit_dsn, env_file=env_file)
    return dsn
