from datetime import datetime, timedelta, timezone

from backend.ingest.webhook_security import (
    configured_webhook_secret_entries,
    match_webhook_secret,
    request_client_ip_for_security_log,
    stale_webhook_error,
    verify_webhook_secret,
    webhook_max_age_seconds,
    webhook_replay_window_seconds,
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


def test_webhook_window_helpers_clamp_invalid_and_negative_env(monkeypatch):
    monkeypatch.setenv("APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", "not-an-int")
    monkeypatch.setenv("APIFY_WEBHOOK_MAX_AGE_SECONDS", "-5")

    assert webhook_replay_window_seconds() == 3600
    assert webhook_max_age_seconds() == 0

    monkeypatch.setenv("APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", "120")
    monkeypatch.setenv("APIFY_WEBHOOK_MAX_AGE_SECONDS", "60")

    assert webhook_replay_window_seconds() == 120
    assert webhook_max_age_seconds() == 60


class _Client:
    host = "203.0.113.5"


class _Request:
    client = _Client()


def test_request_client_ip_uses_extractor_when_available():
    assert request_client_ip_for_security_log(_Request(), lambda request: "198.51.100.9") == "198.51.100.9"


def test_request_client_ip_falls_back_to_request_client_host_on_extractor_failure():
    def boom(_request):
        raise RuntimeError("middleware unavailable")

    assert request_client_ip_for_security_log(_Request(), boom) == "203.0.113.5"


def test_request_client_ip_returns_unknown_without_client():
    assert request_client_ip_for_security_log(object()) == "unknown"
