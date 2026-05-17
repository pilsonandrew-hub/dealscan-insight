from backend.ingest.telegram_alerts import (
    build_telegram_alert_message,
    build_telegram_reply_markup,
    clean_bid_direct_url,
    redact_telegram_bot_token,
)


def test_clean_bid_direct_url_strips_govplanet_query_params_only():
    assert clean_bid_direct_url("https://www.govplanet.com/item/123?foo=bar") == "https://www.govplanet.com/item/123"
    assert clean_bid_direct_url("https://example.com/item/123?foo=bar") == "https://example.com/item/123?foo=bar"


def test_build_telegram_reply_markup_preserves_callback_actions():
    markup = build_telegram_reply_markup("opp-1")

    buttons = markup["inline_keyboard"][0]
    assert [button["callback_data"] for button in buttons] == ["buy_opp-1", "watch_opp-1", "pass_opp-1"]


def test_build_hot_telegram_alert_message_escapes_html_and_includes_truth_note():
    deal = {
        "opportunity_id": "opp_123",
        "year": 2024,
        "make": "Ford",
        "model": "F_150 & Co",
        "state": "CA",
        "current_bid": 12000,
        "dos_score": 91,
        "score_breakdown": {
            "investment_grade": "A_Buy & Hold",
            "gross_margin": 4200,
            "pricing_maturity": "proxy",
            "pricing_source": "make:model_with_underscore",
            "expected_close_source": "confidence_adjusted_current_bid",
            "acquisition_basis_source": "expected_close",
            "mmr_lookup_basis": "make:model_with_underscore",
        },
    }
    alert_gate = {
        "eligible": True,
        "alert_type": "hot",
        "signals": {
            "pricing_maturity": "proxy",
            "pricing_source": "make:model_with_underscore",
            "expected_close_source": "confidence_adjusted_current_bid",
            "acquisition_basis_source": "expected_close",
            "mmr_lookup_basis": "make:model_with_underscore",
        },
    }

    text = build_telegram_alert_message(deal, "https://example.com/asset/1?utm=unit_test&x=1", alert_gate=alert_gate)

    assert "<b>HOT DEAL ALERT</b>" in text
    assert "F_150 &amp; Co" in text
    assert "make:model_with_underscore" in text
    assert "Proxy-priced: expected close and basis are synthetic" in text
    assert 'href="https://example.com/asset/1?utm=unit_test&amp;x=1"' in text


def test_build_platinum_telegram_alert_message_includes_roi_and_headroom():
    deal = {
        "opportunity_id": "opp_123",
        "year": 2024,
        "make": "Toyota",
        "model": "Camry",
        "state": "CA",
        "current_bid": 12000,
        "dos_score": 95,
        "score_breakdown": {
            "investment_grade": "Platinum",
            "roi_per_day": 125,
            "bid_headroom": 2500,
            "max_bid": 18000,
            "pricing_maturity": "retail_comp",
            "pricing_source": "market_comps",
            "expected_close_source": "retail_comp_projection",
            "acquisition_basis_source": "expected_close",
        },
    }
    alert_gate = {
        "eligible": True,
        "alert_type": "platinum",
        "signals": {
            "pricing_maturity": "retail_comp",
            "pricing_source": "market_comps",
            "expected_close_source": "retail_comp_projection",
            "acquisition_basis_source": "expected_close",
            "retail_comp_count": 5,
            "retail_comp_confidence": 0.82,
        },
    }

    text = build_telegram_alert_message(deal, "https://example.com/asset/2", alert_gate=alert_gate)

    assert "<b>PLATINUM ALERT</b>" in text
    assert "ROI/Day: $125 | Headroom: $2,500" in text
    assert "Retail evidence: count=5, conf=0.82" in text


def test_redact_telegram_bot_token_removes_token_from_url():
    redacted = redact_telegram_bot_token(
        "https://api.telegram.org/bot1234567890:ABCdef_ghi-JKLmnopQRSTuvwxYZ/sendMessage"
    )

    assert "1234567890:ABCdef" not in redacted
    assert "bot[REDACTED_TELEGRAM_TOKEN]/sendMessage" in redacted
