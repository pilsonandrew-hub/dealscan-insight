from datetime import datetime, timedelta, timezone

from backend.ingest.webhook_security import (
    configured_webhook_secret_entries,
    match_webhook_secret,
    stale_webhook_error,
    verify_webhook_secret,
)


def test_configured_webhook_secret_entries_supports_comma_separated_rotation_values():
    assert configured_webhook_secret_entries(" current-a, current-b ", " previous-a ") == (
        ("current", "current-a"),
        ("current", "current-b"),
        ("previous", "previous-a"),
    )


def test_match_webhook_secret_returns_current_or_previous_label():
    assert match_webhook_secret("newsecret", "newsecret", "oldsecret") == "current"
    assert match_webhook_secret("oldsecret", "newsecret", "oldsecret") == "previous"
    assert match_webhook_secret("wrong", "newsecret", "oldsecret") is None


def test_verify_webhook_secret_requires_active_current_secret():
    assert verify_webhook_secret("oldsecret", "", "oldsecret") is False
    assert verify_webhook_secret("oldsecret", "newsecret", "oldsecret") is True


def test_stale_webhook_error_reports_old_and_future_created_at():
    now = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    assert stale_webhook_error({"created_at": now - timedelta(seconds=120)}, 60, now=now) == (
        "Webhook createdAt is stale (120s old; max 60s)"
    )
    assert stale_webhook_error({"created_at": now + timedelta(seconds=301)}, 60, now=now) == (
        "Webhook createdAt is too far in the future (301s skew)"
    )
    assert stale_webhook_error({"created_at": now - timedelta(seconds=30)}, 60, now=now) is None
