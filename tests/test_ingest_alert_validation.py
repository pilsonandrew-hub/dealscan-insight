from webapp.routers.ingest import (
    _alert_validation_mmr_estimate,
    _build_alert_validation_prompt,
    _redact_telegram_bot_token,
)


def test_alert_validation_mmr_uses_estimated_sale_price_when_mmr_estimated_missing():
    deal = {
        "title": "2018 Dodge Grand Caravan",
        "year": 2018,
        "make": "Dodge",
        "model": "Grand Caravan",
        "current_bid": 2800,
        "estimated_sale_price": 11575,
        "dos_score": 89.8,
        "state": "CA",
    }

    assert _alert_validation_mmr_estimate(deal) == 11575
    prompt = _build_alert_validation_prompt(deal)

    assert "MMR estimate: $11575" in prompt
    assert "MMR estimate: $None" not in prompt


def test_alert_validation_prompt_defines_dos_as_positive_score():
    prompt = _build_alert_validation_prompt({"dos_score": 89.8})

    assert "higher DOS score is better" in prompt
    assert "not a damage score" in prompt
    assert "80+ means high-priority arbitrage candidate" in prompt


def test_telegram_error_redaction_removes_bot_token_from_api_url():
    raw_error = (
        "Client error '401 Unauthorized' for url "
        "'https://api.telegram.org/bot1234567890:ABCdef_ghi-JKLmnopQRSTuvwxYZ/sendMessage'"
    )

    redacted = _redact_telegram_bot_token(raw_error)

    assert "1234567890:ABCdef" not in redacted
    assert "bot[REDACTED_TELEGRAM_TOKEN]/sendMessage" in redacted
