import asyncio
import importlib
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("ENVIRONMENT", "development")


class _StubRouter:
    def __init__(self, *args, **kwargs):
        pass

    def _decorator(self, *args, **kwargs):
        def wrap(func):
            return func

        return wrap

    get = post = put = patch = delete = api_route = _decorator


class _StubHTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.APIRouter = _StubRouter
fastapi_stub.Request = object
fastapi_stub.HTTPException = _StubHTTPException
fastapi_stub.Header = lambda default=None, **kwargs: default
sys.modules.setdefault("fastapi", fastapi_stub)

from webapp.routers import ingest


class _Request:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.rows)


class _Supabase:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        if name != "webhook_log":
            raise AssertionError(f"unexpected table: {name}")
        return _Query(self.rows)


class _HTTPXResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _HTTPXAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, *args, **kwargs):
        if "/datasets/" not in url:
            raise AssertionError(f"unexpected url: {url}")
        return _HTTPXResponse([{"url": "https://example.com/vehicle/1"}])


class WebhookSecurityTests(unittest.TestCase):
    def test_apify_api_token_helper_accepts_legacy_alias(self):
        with patch.dict(
            os.environ,
            {"APIFY_TOKEN": "", "APIFY_API_TOKEN": "alias-token-123"},
            clear=False,
        ):
            self.assertEqual(ingest._apify_api_token(), "alias-token-123")

    def test_derive_supabase_direct_db_url_urlencodes_password(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_DB_PASSWORD": "p@ss:w/or d",
                "SUPABASE_PROJECT_ID": "projectref123",
            },
            clear=False,
        ):
            derived = ingest._derive_supabase_direct_db_url()

        self.assertEqual(
            derived,
            "postgresql://postgres:p%40ss%3Aw%2For%20d@db.projectref123.supabase.co:5432/postgres?sslmode=require",
        )

    def test_supabase_url_has_no_hardcoded_fallback(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "",
                "VITE_SUPABASE_URL": "",
                "SUPABASE_SERVICE_ROLE_KEY": "",
                "SUPABASE_ANON_KEY": "",
                "VITE_SUPABASE_ANON_KEY": "",
                "ENVIRONMENT": "development",
            },
            clear=False,
        ):
            reloaded = importlib.reload(ingest)
            self.assertIsNone(reloaded._supabase_url)
        importlib.reload(ingest)

    def test_verify_webhook_secret_accepts_current_and_previous_secret(self):
        with patch.object(ingest, "WEBHOOK_SECRET", "newsecretvalue1234567890"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", "oldsecretvalue1234567890"
        ):
            self.assertTrue(ingest._verify_webhook_secret("newsecretvalue1234567890"))
            self.assertTrue(ingest._verify_webhook_secret("oldsecretvalue1234567890"))
            self.assertFalse(ingest._verify_webhook_secret("wrongsecret"))

    def test_verify_webhook_secret_requires_current_secret_to_be_set(self):
        with patch.object(ingest, "WEBHOOK_SECRET", ""), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", "oldsecretvalue1234567890"
        ):
            self.assertFalse(ingest._verify_webhook_secret("oldsecretvalue1234567890"))

    def test_find_recent_webhook_replay_ignores_degraded_rows(self):
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {"processing_status": "degraded", "received_at": now},
            {"processing_status": "error", "received_at": now},
        ]
        with patch.object(ingest, "supabase_client", _Supabase(rows)), patch.dict(
            os.environ,
            {"APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS": "3600"},
            clear=False,
        ):
            replay = ingest._find_recent_webhook_replay("run-123")

        self.assertIsNone(replay)

    def test_apify_webhook_ignores_recent_processed_replay(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-123", "defaultDatasetId": "dataset-123"},
        }
        insert_calls = []

        def fake_insert(_payload, **kwargs):
            insert_calls.append(kwargs)
            return "log-1"

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(
            ingest,
            "_find_recent_webhook_replay",
            lambda run_id: {
                "processing_status": "processed",
                "received_at": "2026-03-15T18:00:00+00:00",
                "run_id": run_id,
            },
        ), patch.object(ingest, "insert_webhook_log", fake_insert):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertTrue(response["replay_ignored"])
        self.assertEqual(response["run_id"], "run-123")
        self.assertEqual(insert_calls[0]["processing_status"], "ignored_replay")
        self.assertIn("Replay ignored for run_id=run-123", insert_calls[0]["error_message"])

    def test_apify_webhook_rejects_stale_payload_when_max_age_enabled(self):
        payload = {
            "createdAt": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "resource": {"id": "run-999", "defaultDatasetId": "dataset-999"},
        }
        insert_calls = []

        def fake_insert(_payload, **kwargs):
            insert_calls.append(kwargs)
            return "log-2"

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(
            ingest, "insert_webhook_log", fake_insert
        ), patch.dict(
            os.environ,
            {"APIFY_WEBHOOK_MAX_AGE_SECONDS": "60"},
            clear=False,
        ):
            with self.assertRaises(Exception) as exc:
                asyncio.run(
                    ingest.apify_webhook(_Request(payload), x_apify_webhook_secret="topsecret")
                )

        self.assertEqual(getattr(exc.exception, "status_code", None), 401)
        self.assertEqual(getattr(exc.exception, "detail", None), "Stale webhook payload")
        self.assertEqual(insert_calls[0]["processing_status"], "ignored_stale")

    def test_apify_webhook_records_pre_save_skip_ledger_for_normalize_rejection(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-skip-1", "defaultDatasetId": "dataset-skip-1"},
        }
        delivery_calls = []
        webhook_updates = []
        fake_httpx = types.SimpleNamespace(AsyncClient=_HTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", None), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-skip-1"
        ), patch.object(
            ingest,
            "update_webhook_log",
            lambda *args, **kwargs: webhook_updates.append((args, kwargs)),
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["skipped"], 1)
        self.assertEqual(len(delivery_calls), 1)
        self.assertEqual(delivery_calls[0]["run_id"], "run-skip-1")
        self.assertEqual(delivery_calls[0]["channel"], "db_save")
        self.assertEqual(delivery_calls[0]["status"], "skipped_norm")
        self.assertEqual(delivery_calls[0]["error_message"], "normalize_rejected")
        self.assertIn("skip_reasons={'normalize_rejected': 1}", webhook_updates[-1][1]["error_message"])


if __name__ == "__main__":
    unittest.main()
