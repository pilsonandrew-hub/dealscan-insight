"""Supabase ingest configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class SupabaseIngestConfig:
    url: Optional[str]
    service_role_key: Optional[str]
    anon_key: Optional[str]
    environment: str
    key: Optional[str]
    key_source: Optional[str]
    message: Optional[str]
    severity: Optional[str]


def resolve_supabase_ingest_config(env: Mapping[str, str]) -> SupabaseIngestConfig:
    url = env.get("SUPABASE_URL") or env.get("VITE_SUPABASE_URL") or None
    service_role_key = env.get("SUPABASE_SERVICE_ROLE_KEY") or None
    anon_key = env.get("SUPABASE_ANON_KEY") or env.get("VITE_SUPABASE_ANON_KEY") or None
    environment = env.get("ENVIRONMENT", "production")

    if service_role_key:
        return SupabaseIngestConfig(
            url=url,
            service_role_key=service_role_key,
            anon_key=anon_key,
            environment=environment,
            key=service_role_key,
            key_source="service_role",
            message=None,
            severity=None,
        )

    if anon_key and environment == "development":
        return SupabaseIngestConfig(
            url=url,
            service_role_key=service_role_key,
            anon_key=anon_key,
            environment=environment,
            key=anon_key,
            key_source="anon_development_fallback",
            message="SUPABASE_SERVICE_ROLE_KEY missing in development; falling back to anon key.",
            severity="warning",
        )

    if anon_key:
        return SupabaseIngestConfig(
            url=url,
            service_role_key=service_role_key,
            anon_key=anon_key,
            environment=environment,
            key=None,
            key_source=None,
            message="SUPABASE_SERVICE_ROLE_KEY env var required for privileged ingest operations in production.",
            severity="critical",
        )

    message = (
        "SUPABASE_SERVICE_ROLE_KEY missing in development and no anon key is available."
        if environment == "development"
        else "SUPABASE_SERVICE_ROLE_KEY env var required for privileged ingest operations."
    )
    return SupabaseIngestConfig(
        url=url,
        service_role_key=service_role_key,
        anon_key=anon_key,
        environment=environment,
        key=None,
        key_source=None,
        message=message,
        severity="warning" if environment == "development" else "critical",
    )
