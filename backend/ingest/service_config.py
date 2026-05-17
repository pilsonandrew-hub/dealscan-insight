"""Small service configuration helpers for ingest integrations."""

from __future__ import annotations

from typing import Mapping, Optional


DEFAULT_APP_PUBLIC_URL = "https://dealscan-insight-production.up.railway.app"


def resolve_apify_api_token(env: Mapping[str, str]) -> str:
    """Return the configured Apify API token, honoring the legacy alias."""
    return (env.get("APIFY_TOKEN") or env.get("APIFY_API_TOKEN") or "").strip()


def resolve_app_public_url(env: Mapping[str, str], *, default: str = DEFAULT_APP_PUBLIC_URL) -> str:
    return (env.get("APP_PUBLIC_URL") or default).strip()


def resolve_rover_actions_base_url(
    env: Mapping[str, str],
    *,
    app_public_url: Optional[str] = None,
    default: str = DEFAULT_APP_PUBLIC_URL,
) -> str:
    return (
        env.get("ROVER_API_BASE_URL")
        or env.get("VITE_API_URL")
        or app_public_url
        or resolve_app_public_url(env, default=default)
    ).rstrip("/")
