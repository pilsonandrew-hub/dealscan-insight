"""Pure webhook security helpers for Apify ingest.

No FastAPI, database, or logger dependencies live here.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Any, Optional


def split_secret_values(raw_secret: str) -> list[str]:
    return [secret.strip() for secret in (raw_secret or "").split(",") if secret.strip()]


def configured_webhook_secret_entries(
    webhook_secret: str,
    webhook_secret_previous: str = "",
) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = [
        ("current", secret) for secret in split_secret_values(webhook_secret)
    ]
    entries.extend(
        ("previous", secret) for secret in split_secret_values(webhook_secret_previous)
    )
    return tuple(entries)


def match_webhook_secret(
    presented_secret: Optional[str],
    webhook_secret: str,
    webhook_secret_previous: str = "",
) -> Optional[str]:
    presented = presented_secret or ""
    for label, configured_secret in configured_webhook_secret_entries(
        webhook_secret,
        webhook_secret_previous,
    ):
        if hmac.compare_digest(presented, configured_secret):
            return label
    return None


def verify_webhook_secret(
    presented_secret: Optional[str],
    webhook_secret: str,
    webhook_secret_previous: str = "",
) -> bool:
    """Require an active current secret before accepting current/previous values."""
    if not (webhook_secret or "").strip():
        return False
    return match_webhook_secret(presented_secret, webhook_secret, webhook_secret_previous) is not None


def stale_webhook_error(metadata: dict[str, Any], max_age_seconds: int, *, now: Optional[datetime] = None) -> Optional[str]:
    created_at = metadata.get("created_at")
    if max_age_seconds <= 0 or created_at is None:
        return None

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if isinstance(created_at, datetime) and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_seconds = (current_time - created_at).total_seconds()
    if age_seconds > max_age_seconds:
        return f"Webhook createdAt is stale ({int(age_seconds)}s old; max {max_age_seconds}s)"
    if age_seconds < -300:
        return f"Webhook createdAt is too far in the future ({int(abs(age_seconds))}s skew)"
    return None


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def webhook_replay_window_seconds(*, env_name: str = "APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", default: int = 3600) -> int:
    return max(env_int(env_name, default), 0)


def webhook_max_age_seconds(*, env_name: str = "APIFY_WEBHOOK_MAX_AGE_SECONDS", default: int = 0) -> int:
    return max(env_int(env_name, default), 0)


def request_client_ip_for_security_log(request: Any, extractor: Any = None) -> str:
    if extractor is not None:
        try:
            return extractor(request)
        except Exception:
            pass
    return getattr(getattr(request, "client", None), "host", None) or "unknown"
