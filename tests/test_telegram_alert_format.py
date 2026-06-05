import asyncio
import importlib
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock


class TelegramAlertFormatTests(unittest.TestCase):
    def test_hot_alert_uses_html_parse_mode_and_escapes_markdown_sensitive_text(self):
        os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
        os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
        os.environ["ALERTS_ENABLED"] = "true"
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:TEST_TOKEN_FOR_UNIT_ONLY"
        os.environ["TELEGRAM_CHAT_ID"] = "-1001234567890"

        fake_httpx = types.ModuleType("httpx")
        client = AsyncMock()
        response = MagicMock()
        response.json.return_value = {"result": {"message_id": 123}}
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

        ingest = importlib.import_module("webapp.routers.ingest")
        ingest.TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
        ingest.TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
        ingest.supabase_client = None
        ingest._delivery_log_lookup = lambda *args, **kwargs: None
        ingest._record_delivery_log = lambda *args, **kwargs: None

        deal = {
            "run_id": "unit-run",
            "opportunity_id": "opp_123",
            "listing_url": "https://example.com/asset/1?utm=unit_test&x=1",
            "source_site": "unit",
            "year": 2024,
            "make": "Ford",
            "model": "F_150 & Co",
            "state": "CA",
            "current_bid": 12000,
            "max_bid": 15000,
            "projected_total_cost": 12500,
            "dos_score": 91,
            "investment_grade": "Gold",
            "pricing_maturity": "market_comp",
            "pricing_source": "make:model_with_underscore",
            "retail_comp_count": 3,
            "retail_comp_confidence": 0.82,
            "current_bid_trust_score": 0.9,
            "mmr_confidence_proxy": 90.0,
            "bid_headroom": 3000,
            "roi_per_day": 80,
            "vin": "1HGCM82633A004352",
            "mileage": 42000,
            "condition_grade": "Good",
            "raw_data": {
                "detail_text": "Starts, runs and drives. Minor scratches noted.",
            },
            "score_breakdown": {
                "dos_score": 91,
                "investment_grade": "Gold",
                "gross_margin": 4200,
                "pricing_maturity": "market_comp",
                "pricing_source": "make:model_with_underscore",
                "retail_comp_count": 3,
                "retail_comp_confidence": 0.82,
                "expected_close_source": "confidence_adjusted_current_bid",
                "acquisition_basis_source": "expected_close",
                "mmr_lookup_basis": "make:model_with_underscore",
                "mmr_confidence_proxy": 90.0,
            },
        }

        message_id = asyncio.run(ingest.send_telegram_alert(deal))

        self.assertEqual(message_id, "123")
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("<b>HOT DEAL ALERT</b>", payload["text"])
        self.assertIn("F_150 &amp; Co", payload["text"])
        self.assertIn("make:model_with_underscore", payload["text"])
        self.assertIn("href=\"https://example.com/asset/1?utm=unit_test&amp;x=1\"", payload["text"])
        self.assertNotIn("[Bid Direct", payload["text"])
        self.assertNotIn("*HOT DEAL ALERT*", payload["text"])


if __name__ == "__main__":
    unittest.main()
