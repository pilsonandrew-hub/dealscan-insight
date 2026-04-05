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


class _StubBackgroundTasks:
    """Stand-in for FastAPI BackgroundTasks that runs tasks synchronously.

    This ensures that tests can inspect side-effects produced by background
    processing (skipped counts, delivery logs, audit state, etc.) without
    having to set up an actual async event loop or task runner.
    """
    def __init__(self):
        self._tasks = []

    def add_task(self, func, *args, **kwargs):
        self._tasks.append((func, args, kwargs))
        # Run synchronously so test assertions can inspect side-effects.
        import asyncio, inspect, concurrent.futures, threading
        if inspect.iscoroutinefunction(func):
            # We may be called from inside a running event loop (the test calls
            # asyncio.run(apify_webhook(...)), and add_task fires synchronously
            # from inside that coroutine).  asyncio.run() / run_until_complete()
            # both raise RuntimeError in that case.  Run the coroutine in a
            # dedicated background thread with its own fresh event loop instead.
            result_holder = []
            exc_holder = []

            def _thread_runner():
                try:
                    result = asyncio.run(func(*args, **kwargs))
                    result_holder.append(result)
                except Exception as e:  # noqa: BLE001
                    exc_holder.append(e)

            t = threading.Thread(target=_thread_runner, daemon=True)
            t.start()
            t.join(timeout=30)
            if exc_holder:
                raise exc_holder[0]
        else:
            func(*args, **kwargs)


if "fastapi" not in sys.modules:
    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.APIRouter = _StubRouter
    fastapi_stub.Request = object
    fastapi_stub.HTTPException = _StubHTTPException
    fastapi_stub.Header = lambda default=None, **kwargs: default
    fastapi_stub.BackgroundTasks = _StubBackgroundTasks
    fastapi_stub.Depends = lambda f=None: f
    fastapi_stub.status = types.SimpleNamespace(
        HTTP_200_OK=200, HTTP_400_BAD_REQUEST=400,
        HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403,
        HTTP_404_NOT_FOUND=404, HTTP_500_INTERNAL_SERVER_ERROR=500,
    )
    _responses_stub = types.ModuleType("fastapi.responses")
    _responses_stub.JSONResponse = dict
    fastapi_stub.__path__ = []
    sys.modules["fastapi"] = fastapi_stub
    sys.modules["fastapi.responses"] = _responses_stub

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


class _FailingExecute:
    def __init__(self, error_text):
        self.error_text = error_text

    def execute(self):
        raise RuntimeError(self.error_text)


class _FailingWebhookLogInsertTable:
    def __init__(self, error_text):
        self.error_text = error_text

    def insert(self, _payload):
        return _FailingExecute(self.error_text)


class _FailingWebhookLogInsertSupabase:
    def __init__(self, error_text):
        self.error_text = error_text

    def table(self, name):
        if name != "webhook_log":
            raise AssertionError(f"unexpected table: {name}")
        return _FailingWebhookLogInsertTable(self.error_text)


class _FailingReplayQuery(_Query):
    def __init__(self, error_text):
        super().__init__(rows=[])
        self.error_text = error_text

    def execute(self):
        raise RuntimeError(self.error_text)


class _FailingReplaySupabase:
    def __init__(self, error_text):
        self.error_text = error_text

    def table(self, name):
        if name != "webhook_log":
            raise AssertionError(f"unexpected table: {name}")
        return _FailingReplayQuery(self.error_text)


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

    def test_apify_webhook_rejects_invalid_secret_with_401(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-401", "defaultDatasetId": "dataset-401"},
        }

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ):
            with self.assertRaises(Exception) as exc:
                asyncio.run(
                    ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="wrongsecret")
                )

        self.assertEqual(getattr(exc.exception, "status_code", None), 401)
        self.assertEqual(getattr(exc.exception, "detail", None), "Invalid webhook secret")

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
            lambda run_id, **_kwargs: {
                "processing_status": "processed",
                "received_at": "2026-03-15T18:00:00+00:00",
                "run_id": run_id,
            },
        ), patch.object(ingest, "insert_webhook_log", fake_insert):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
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
                    ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
                )

        self.assertEqual(getattr(exc.exception, "status_code", None), 401)
        self.assertEqual(getattr(exc.exception, "detail", None), "Stale webhook payload")
        self.assertEqual(insert_calls[0]["processing_status"], "ignored_stale")

    def test_insert_webhook_log_falls_back_to_direct_pg_and_marks_audit_state(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-direct-log", "defaultDatasetId": "dataset-direct-log"},
        }
        inserted_rows = []
        audit_state = {"fallbacks": []}

        def fake_insert_direct_pg(row):
            inserted_rows.append(row)
            return "direct-log-1"

        with patch.object(
            ingest,
            "supabase_client",
            _FailingWebhookLogInsertSupabase("supabase webhook_log insert failed"),
        ), patch.object(ingest, "_direct_supabase_db_url", "postgresql://example"), patch.object(
            ingest,
            "_insert_webhook_log_direct_pg",
            fake_insert_direct_pg,
        ):
            webhook_log_id = ingest.insert_webhook_log(
                payload,
                require_durable=True,
                audit_state=audit_state,
            )

        self.assertEqual(webhook_log_id, "direct-log-1")
        self.assertEqual(audit_state["fallbacks"], ["webhook_log_insert_direct_pg"])
        self.assertIn(
            "audit_fallbacks=webhook_log_insert_direct_pg",
            inserted_rows[0]["error_message"],
        )

    def test_apify_webhook_marks_audit_fallback_when_critical_rows_use_direct_pg(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-audit-fallback", "defaultDatasetId": "dataset-audit-fallback"},
        }
        webhook_inserts = []
        webhook_updates = []
        delivery_rows = []
        fake_httpx = types.SimpleNamespace(AsyncClient=_HTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", None), patch.object(
            ingest, "_direct_supabase_db_url", "postgresql://example"
        ), patch.object(
            ingest,
            "_find_recent_webhook_replay_direct_pg",
            lambda *_args, **_kwargs: [],
        ), patch.object(
            ingest,
            "_insert_webhook_log_direct_pg",
            lambda row: webhook_inserts.append(row) or "log-direct-1",
        ), patch.object(
            ingest,
            "_update_webhook_log_direct_pg",
            lambda webhook_log_id, update_row: webhook_updates.append((webhook_log_id, update_row)),
        ), patch.object(
            ingest,
            "_upsert_delivery_log_direct_pg",
            lambda row: delivery_rows.append(row),
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: None
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        # audit_status/audit_fallbacks are populated during background processing,
        # not in the immediate HTTP response — verify via side-effect collectors.
        self.assertTrue(len(delivery_rows) > 0, "expected delivery log entry from background task")
        self.assertEqual(delivery_rows[0]["status"], "skipped_norm")
        self.assertIn(
            "audit_fallbacks=ingest_delivery_log_direct_pg",
            delivery_rows[0]["error_message"],
        )
        self.assertTrue(len(webhook_updates) > 0, "expected webhook_log update from background task")
        self.assertIn("audit_fallbacks=", webhook_updates[-1][1]["error_message"])

    def test_apify_webhook_fails_loudly_when_db_save_audit_write_cannot_land(self):
        """When the initial (synchronous) webhook-log insert cannot land durably,
        the handler must raise HTTP 503 immediately rather than silently swallowing
        the failure inside a background task."""
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-audit-503", "defaultDatasetId": "dataset-audit-503"},
        }

        def _raise_critical(*_args, **_kwargs):
            raise ingest.CriticalAuditWriteError(
                "critical webhook_log insert failed: no durable write path available"
            )

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", None), patch.object(
            ingest, "_direct_supabase_db_url", None
        ), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", _raise_critical
        ):
            with self.assertRaises(Exception) as exc:
                asyncio.run(
                    ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
                )

        self.assertEqual(getattr(exc.exception, "status_code", None), 503)
        self.assertEqual(getattr(exc.exception, "detail", None), "Critical ingest audit write failed")

    def test_apify_webhook_fails_loudly_when_replay_lookup_cannot_land_durably(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-replay-lookup-503", "defaultDatasetId": "dataset-replay-lookup-503"},
        }

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(
            ingest,
            "supabase_client",
            _FailingReplaySupabase("supabase replay lookup failed"),
        ), patch.object(ingest, "_direct_supabase_db_url", None):
            with self.assertRaises(Exception) as exc:
                asyncio.run(
                    ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
                )

        self.assertEqual(getattr(exc.exception, "status_code", None), 503)
        self.assertEqual(getattr(exc.exception, "detail", None), "Critical ingest audit write failed")

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
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
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
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        # skipped count lives in background processing state, not the immediate
        # HTTP ack — verify via the delivery-log and webhook-update side effects.
        self.assertEqual(len(delivery_calls), 1, "expected exactly one delivery log call")
        self.assertEqual(delivery_calls[0]["run_id"], "run-skip-1")
        self.assertEqual(delivery_calls[0]["channel"], "db_save")
        self.assertEqual(delivery_calls[0]["status"], "skipped_norm")
        self.assertEqual(delivery_calls[0]["error_message"], "normalize_rejected")
        self.assertTrue(len(webhook_updates) > 0, "expected at least one webhook_log update")
        self.assertIn("skip_reasons={'normalize_rejected': 1}", webhook_updates[-1][1]["error_message"])


if __name__ == "__main__":
    unittest.main()
