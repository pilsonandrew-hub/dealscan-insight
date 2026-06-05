import asyncio
import importlib
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock


def _install_fake_httpx(message_id=987):
    fake_httpx = types.ModuleType("httpx")
    client = AsyncMock()
    response = MagicMock()
    response.json.return_value = {"result": {"message_id": message_id}}
    response.raise_for_status.return_value = None
    client.post.return_value = response

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return client

        async def __aexit__(self, exc_type, exc, tb):
            return None

    fake_httpx.AsyncClient = FakeAsyncClient
    sys.modules["httpx"] = fake_httpx
    return client


def _ingest_module(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:TEST_TOKEN_FOR_UNIT_ONLY")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567890")
    ingest = importlib.import_module("webapp.routers.ingest")
    monkeypatch.setattr(ingest, "TELEGRAM_BOT_TOKEN", os.environ["TELEGRAM_BOT_TOKEN"])
    monkeypatch.setattr(ingest, "TELEGRAM_CHAT_ID", os.environ["TELEGRAM_CHAT_ID"])
    monkeypatch.setattr(ingest, "supabase_client", None)
    monkeypatch.setattr(ingest, "_delivery_log_lookup", lambda *args, **kwargs: None)
    monkeypatch.setattr(ingest, "_record_delivery_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(ingest, "insert_alert_log", AsyncMock(return_value=False))
    ingest.alerts_this_run.clear()
    ingest.alerts_this_run_ts.clear()
    return ingest


def _send_eligible_deal(**overrides):
    deal = {
        "run_id": "issue-5-test-run",
        "opportunity_id": "opp-issue-5",
        "listing_id": "listing-issue-5",
        "listing_url": "https://example.com/listing/123",
        "source_site": "GovDeals",
        "title": "2021 Honda Civic",
        "year": 2021,
        "make": "Honda",
        "model": "Civic",
        "state": "CA",
        "dos_score": 95,
        "score": 95,
        "investment_grade": "Platinum",
        "pricing_maturity": "market_comp",
        "pricing_source": "market_comp",
        "retail_comp_count": 3,
        "retail_comp_confidence": 0.82,
        "current_bid_trust_score": 0.9,
        "mmr_confidence_proxy": 90.0,
        "bid_headroom": 5000,
        "roi_per_day": 100,
        "vin": "1HGCM82633A004352",
        "mileage": 42000,
        "condition_grade": "Good",
        "current_bid": 10000,
        "max_bid": 15000,
        "projected_total_cost": 11000,
        "score_breakdown": {
            "dos_score": 95,
            "investment_grade": "Platinum",
            "pricing_maturity": "market_comp",
            "pricing_source": "market_comp",
            "retail_comp_count": 3,
            "retail_comp_confidence": 0.82,
            "mmr_confidence_proxy": 90.0,
        },
    }
    deal.update(overrides)
    return deal


def test_send_telegram_alert_recomputes_gate_and_blocks_missing_confidence_despite_stale_allow_gate(monkeypatch):
    client = _install_fake_httpx()
    ingest = _ingest_module(monkeypatch)
    deal = _send_eligible_deal(
        alert_gate={"eligible": True, "alert_type": "platinum", "blocking_reasons": []},
    )
    deal.pop("mmr_confidence_proxy")
    deal.pop("retail_comp_confidence")
    deal["score_breakdown"].pop("mmr_confidence_proxy")
    deal["score_breakdown"].pop("retail_comp_confidence")

    message_id = asyncio.run(ingest.send_telegram_alert(deal))

    assert message_id is None
    assert client.post.call_count == 0
    assert deal["alert_gate"]["eligible"] is False
    assert "confidence_missing" in deal["alert_gate"]["blocking_reasons"]


def test_send_telegram_alert_blocks_malformed_primary_confidence_despite_fallback_and_stale_allow_gate(monkeypatch):
    client = _install_fake_httpx()
    ingest = _ingest_module(monkeypatch)
    deal = _send_eligible_deal(
        mmr_confidence_proxy="not-a-number",
        manheim_confidence=90.0,
        alert_gate={"eligible": True, "alert_type": "platinum", "blocking_reasons": []},
    )
    deal["score_breakdown"]["mmr_confidence_proxy"] = "not-a-number"
    deal["score_breakdown"]["manheim_confidence"] = 90.0

    message_id = asyncio.run(ingest.send_telegram_alert(deal))

    assert message_id is None
    assert client.post.call_count == 0
    assert deal["alert_gate"]["eligible"] is False
    assert "confidence_invalid" in deal["alert_gate"]["blocking_reasons"]


def test_send_telegram_alert_sends_when_recomputed_confidence_gate_passes(monkeypatch):
    client = _install_fake_httpx(message_id=654)
    ingest = _ingest_module(monkeypatch)
    deal = _send_eligible_deal(
        alert_gate={"eligible": False, "blocking_reasons": ["stale_old_failure"]},
    )

    message_id = asyncio.run(ingest.send_telegram_alert(deal))

    assert message_id == "654"
    assert client.post.call_count == 1
    assert deal["alert_gate"]["eligible"] is True
    assert deal["alert_gate"]["blocking_reasons"] == []


def test_send_telegram_alert_records_delivery_skip_when_telegram_config_missing(monkeypatch):
    client = _install_fake_httpx()
    ingest = _ingest_module(monkeypatch)
    monkeypatch.setattr(ingest, "TELEGRAM_CHAT_ID", "")
    recorded = []
    monkeypatch.setattr(
        ingest,
        "_record_delivery_log",
        lambda **kwargs: recorded.append(kwargs),
    )
    deal = _send_eligible_deal()

    message_id = asyncio.run(ingest.send_telegram_alert(deal))

    assert message_id is None
    assert client.post.call_count == 0
    assert recorded == [
        {
            "run_id": "issue-5-test-run",
            "listing_id": "listing-issue-5",
            "listing_url": "https://example.com/listing/123",
            "opportunity_id": "opp-issue-5",
            "channel": "telegram_alert",
            "status": "skipped_config",
            "error_message": "missing_telegram_chat_id",
        }
    ]


def test_duplicate_existing_opportunity_re_enters_alert_pipeline_when_no_alert_delivery(monkeypatch):
    ingest = _ingest_module(monkeypatch)
    monkeypatch.setattr(ingest, "_alert_delivery_exists_for_opportunity", lambda opportunity_id: False)

    assert ingest._should_evaluate_alert_delivery("duplicate_existing", True, "opp-issue-5") is True


def test_duplicate_existing_opportunity_does_not_realert_when_delivery_exists(monkeypatch):
    ingest = _ingest_module(monkeypatch)
    monkeypatch.setattr(ingest, "_alert_delivery_exists_for_opportunity", lambda opportunity_id: True)

    assert ingest._should_evaluate_alert_delivery("duplicate_existing", True, "opp-issue-5") is False
