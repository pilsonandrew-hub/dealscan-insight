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
    fastapi_stub.Path = lambda default=None, **kwargs: default
    fastapi_stub.Query = lambda default=None, **kwargs: default
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


class _NoDealerSalesSupabase:
    def table(self, name):
        if name == "dealer_sales":
            raise AssertionError("govdeals-sold must stage candidates, not write dealer_sales")
        if name == "opportunities":
            return _Query([])
        raise AssertionError(f"unexpected table: {name}")


class _RecordingExecute:
    def execute(self):
        return types.SimpleNamespace(data=[])


class _RecordingTable:
    def __init__(self, operations, name):
        self.operations = operations
        self.name = name

    def insert(self, payload):
        self.operations.append((self.name, "insert", payload))
        return _RecordingExecute()

    def upsert(self, payload, **kwargs):
        self.operations.append((self.name, "upsert", payload, kwargs))
        return _RecordingExecute()


class _RecordingSupabase:
    def __init__(self):
        self.operations = []

    def table(self, name):
        if name == "dealer_sales":
            raise AssertionError("sold comp staging must not write dealer_sales")
        return _RecordingTable(self.operations, name)


class _ExistingCandidateQuery:
    def __init__(self, rows, operations, table_name):
        self.rows = rows
        self.operations = operations
        self.table_name = table_name
        self.filters = []

    def select(self, *_args, **_kwargs):
        self.operations.append((self.table_name, "select"))
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.rows)


class _ExistingCandidateTable(_RecordingTable):
    def __init__(self, operations, name, existing_rows):
        super().__init__(operations, name)
        self.existing_rows = existing_rows

    def select(self, *_args, **_kwargs):
        self.operations.append((self.name, "select"))
        return _ExistingCandidateQuery(self.existing_rows, self.operations, self.name)

    def upsert(self, payload, **kwargs):
        self.operations.append((self.name, "upsert", payload, kwargs))
        self.existing_rows[:] = [
            {
                "id": payload.get("id") or "candidate-created",
                "run_id": payload.get("run_id"),
                "candidate_status": payload.get("candidate_status") or "candidate",
            }
        ]
        return _RecordingExecute()


class _ExistingCandidateSupabase(_RecordingSupabase):
    def __init__(self, existing_rows):
        super().__init__()
        self.existing_rows = existing_rows

    def table(self, name):
        if name == "dealer_sales":
            raise AssertionError("sold comp staging must not write dealer_sales")
        if name == "sold_comp_candidates":
            return _ExistingCandidateTable(self.operations, name, self.existing_rows)
        return _RecordingTable(self.operations, name)


class _NonDurableCandidateTable(_RecordingTable):
    def select(self, *_args, **_kwargs):
        self.operations.append((self.name, "select"))
        return _ExistingCandidateQuery([], self.operations, self.name)


class _NonDurableCandidateSupabase(_RecordingSupabase):
    def table(self, name):
        if name == "dealer_sales":
            raise AssertionError("sold comp staging must not write dealer_sales")
        if name == "sold_comp_candidates":
            return _NonDurableCandidateTable(self.operations, name)
        return _RecordingTable(self.operations, name)


class _FailingCandidateLookupTable(_RecordingTable):
    def select(self, *_args, **_kwargs):
        raise RuntimeError("candidate lookup unavailable")


class _FailingCandidateLookupSupabase(_RecordingSupabase):
    def table(self, name):
        if name == "dealer_sales":
            raise AssertionError("sold comp staging must not write dealer_sales")
        if name == "sold_comp_candidates":
            return _FailingCandidateLookupTable(self.operations, name)
        return _RecordingTable(self.operations, name)


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

    def test_find_recent_webhook_replay_blocks_pending_run_claim(self):
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {"processing_status": "pending", "received_at": now, "id": "claim-row"},
        ]
        with patch.object(ingest, "supabase_client", _Supabase(rows)), patch.dict(
            os.environ,
            {"APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS": "3600"},
            clear=False,
        ):
            replay = ingest._find_recent_webhook_replay("run-claim")

        self.assertIsNotNone(replay)
        self.assertEqual(replay["id"], "claim-row")
        self.assertEqual(replay["processing_status"], "pending")

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


    def test_claim_webhook_log_direct_pg_serializes_pending_claim(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-claim-direct", "defaultDatasetId": "dataset-claim-direct"},
        }
        executed = []
        existing_rows = [
            {
                "id": "existing-claim",
                "run_id": "run-claim-direct",
                "processing_status": "pending",
                "received_at": datetime.now(timezone.utc).isoformat(),
                "error_message": None,
            }
        ]

        class _Cursor:
            def __init__(self):
                self._inserted = None

            def execute(self, query, params=None):
                executed.append((query, params))
                if "insert into public.webhook_log" in query:
                    self._inserted = {"id": "should-not-insert"}

            def fetchall(self):
                return existing_rows

            def fetchone(self):
                return self._inserted

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class _Connection:
            def cursor(self, *args, **kwargs):
                return _Cursor()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        audit_state = {"fallbacks": []}
        with patch.object(ingest, "_direct_supabase_db_url", "postgresql://example"), patch.object(
            ingest.psycopg2, "connect", return_value=_Connection()
        ):
            webhook_log_id, replay = ingest._claim_webhook_log(
                payload,
                require_durable=True,
                audit_state=audit_state,
            )

        self.assertIsNone(webhook_log_id)
        self.assertEqual(replay["id"], "existing-claim")
        self.assertIn("webhook_log_claim_direct_pg", audit_state["fallbacks"])
        self.assertTrue(any("pg_advisory_xact_lock" in query for query, _ in executed))
        self.assertFalse(any("insert into public.webhook_log" in query for query, _ in executed))

    def test_claim_webhook_log_falls_back_to_rest_when_direct_pg_unreachable(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-direct-unreachable", "defaultDatasetId": "dataset-direct-unreachable"},
        }
        audit_state = {"fallbacks": []}
        insert_calls = []

        def fake_insert(_payload, **kwargs):
            insert_calls.append(kwargs)
            return "rest-log-1"

        with patch.object(ingest, "_direct_supabase_db_url", "postgresql://unreachable"), patch.object(
            ingest, "supabase_client", _Supabase([])
        ), patch.object(
            ingest.psycopg2, "connect", side_effect=OSError("network is unreachable")
        ), patch.object(
            ingest, "insert_webhook_log", fake_insert
        ):
            webhook_log_id, replay = ingest._claim_webhook_log(
                payload,
                require_durable=True,
                audit_state=audit_state,
            )

        self.assertEqual(webhook_log_id, "rest-log-1")
        self.assertIsNone(replay)
        self.assertIn("webhook_log_claim_direct_pg_unavailable", audit_state["fallbacks"])
        self.assertEqual(insert_calls[0]["require_durable"], True)

    def test_claim_webhook_log_fails_loudly_when_direct_pg_and_rest_unavailable(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-no-durable-path", "defaultDatasetId": "dataset-no-durable-path"},
        }
        audit_state = {"fallbacks": []}

        with patch.object(ingest, "_direct_supabase_db_url", "postgresql://unreachable"), patch.object(
            ingest, "supabase_client", None
        ), patch.object(
            ingest.psycopg2, "connect", side_effect=OSError("network is unreachable")
        ):
            with self.assertRaises(ingest.CriticalAuditWriteError):
                ingest._claim_webhook_log(
                    payload,
                    require_durable=True,
                    audit_state=audit_state,
                )

        self.assertIn("webhook_log_claim_direct_pg_unavailable", audit_state["fallbacks"])

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
            "_claim_webhook_log",
            lambda payload, **kwargs: (webhook_inserts.append(payload) or "log-direct-1", None),
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

    def test_apify_webhook_counts_save_exception_as_failed_save_with_ledger(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-save-fail", "defaultDatasetId": "dataset-save-fail"},
        }
        vehicle = {
            "run_id": "run-save-fail",
            "listing_id": "listing-save-fail",
            "listing_url": "https://example.com/vehicle/save-fail",
            "title": "2024 Toyota Camry",
            "year": 2024,
            "make": "Toyota",
            "model": "Camry",
            "current_bid": 10000,
            "state": "CA",
            "mileage": 25000,
            "source_site": "govdeals",
        }
        delivery_calls = []
        webhook_updates = []
        fake_httpx = types.SimpleNamespace(AsyncClient=_HTTPXAsyncClient)

        async def _raise_save_exception(_vehicle):
            raise RuntimeError("database write exploded")

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", object()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-save-fail"
        ), patch.object(
            ingest,
            "update_webhook_log",
            lambda *args, **kwargs: webhook_updates.append((args, kwargs)),
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: dict(vehicle)
        ), patch.object(
            ingest, "passes_basic_gates", lambda *_args, **_kwargs: {"pass": True, "reason": "ok"}
        ), patch.object(
            ingest, "passes_ingest_margin_floor", lambda *_args, **_kwargs: True
        ), patch.object(
            ingest,
            "score_vehicle",
            lambda _vehicle: {
                "dos_score": 80,
                "vehicle_tier": "premium",
                "wholesale_margin": 5000,
                "ceiling_pass": True,
                "current_bid": 10000,
                "gross_margin": 5000,
                "bid_headroom": 2000,
            },
        ), patch.object(
            ingest, "check_and_handle_duplicate", lambda *_args, **_kwargs: {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}
        ), patch.object(
            ingest, "save_opportunity_to_supabase", _raise_save_exception
        ), patch.object(
            ingest, "_save_to_sonar_listings", lambda _vehicle: None
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(
            [call["channel"] for call in delivery_calls],
            ["sonar_mirror", "db_save"],
        )
        self.assertEqual(
            [call["status"] for call in delivery_calls],
            ["saved_sonar", "save_exception"],
        )
        self.assertEqual(delivery_calls[1]["run_id"], "run-save-fail")
        self.assertEqual(delivery_calls[1]["listing_id"], "listing-save-fail")
        self.assertIn("database write exploded", delivery_calls[1]["error_message"])
        self.assertTrue(len(webhook_updates) > 0, "expected webhook_log update")
        self.assertEqual(webhook_updates[-1][0][1], "error")
        self.assertIn("failed:1", webhook_updates[-1][1]["error_message"])
        self.assertIn("save_outcomes={'save_exception': 1}", webhook_updates[-1][1]["error_message"])
        self.assertIn("skip_reasons={'save_exception': 1}", webhook_updates[-1][1]["error_message"])

    def test_apify_webhook_mirrors_gate_rejected_rows_to_sonar_before_skip(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-gate-sonar", "defaultDatasetId": "dataset-gate-sonar"},
        }
        vehicle = {
            "run_id": "run-gate-sonar",
            "listing_id": "listing-gate-sonar",
            "listing_url": "https://example.com/vehicle/gate-sonar",
            "title": "2012 Toyota Camry",
            "year": 2012,
            "make": "Toyota",
            "model": "Camry",
            "current_bid": 7000,
            "state": "CA",
            "mileage": 155000,
            "source_site": "govdeals",
        }
        delivery_calls = []
        sonar_rows = []
        fake_httpx = types.SimpleNamespace(AsyncClient=_HTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", object()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-gate-sonar"
        ), patch.object(
            ingest, "update_webhook_log", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: dict(vehicle)
        ), patch.object(
            ingest, "passes_basic_gates", lambda *_args, **_kwargs: {"pass": False, "reason": "age_or_mileage_exceeded"}
        ), patch.object(
            ingest, "_save_to_sonar_listings", lambda row: sonar_rows.append(dict(row))
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual([row["listing_id"] for row in sonar_rows], ["listing-gate-sonar"])
        self.assertEqual([call["channel"] for call in delivery_calls], ["sonar_mirror", "db_save"])
        self.assertEqual([call["status"] for call in delivery_calls], ["saved_sonar", "skipped_gate"])
        self.assertEqual(delivery_calls[0]["listing_id"], "listing-gate-sonar")
        self.assertEqual(delivery_calls[1]["error_message"], "age_or_mileage_exceeded")

    def test_apify_webhook_mirrors_margin_rejected_rows_to_sonar_before_skip(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-margin-sonar", "defaultDatasetId": "dataset-margin-sonar"},
        }
        vehicle = {
            "run_id": "run-margin-sonar",
            "listing_id": "listing-margin-sonar",
            "listing_url": "https://example.com/vehicle/margin-sonar",
            "title": "2020 Ford F-150",
            "year": 2020,
            "make": "Ford",
            "model": "F-150",
            "current_bid": 19000,
            "state": "TX",
            "mileage": 42000,
            "source_site": "publicsurplus",
        }
        delivery_calls = []
        sonar_rows = []
        fake_httpx = types.SimpleNamespace(AsyncClient=_HTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", object()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-margin-sonar"
        ), patch.object(
            ingest, "update_webhook_log", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: dict(vehicle)
        ), patch.object(
            ingest, "passes_basic_gates", lambda *_args, **_kwargs: {"pass": True, "reason": "ok"}
        ), patch.object(
            ingest,
            "score_vehicle",
            lambda _vehicle: {
                "dos_score": 55,
                "vehicle_tier": "standard",
                "wholesale_margin": 100,
                "ceiling_pass": True,
                "gross_margin": 100,
                "mmr_estimated": 21500,
                "total_cost": 21400,
                "max_bid": 20500,
                "bid_headroom": 1500,
                "pricing_maturity": "market_comp",
                "retail_comp_price_estimate": 41182.33,
                "retail_comp_count": 3,
                "retail_comp_confidence": 0.69,
            },
        ), patch.object(
            ingest, "passes_ingest_margin_floor", lambda *_args, **_kwargs: False
        ), patch.object(
            ingest, "_save_to_sonar_listings", lambda row: sonar_rows.append(dict(row))
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual([row["listing_id"] for row in sonar_rows], ["listing-margin-sonar"])
        self.assertEqual([call["channel"] for call in delivery_calls], ["sonar_mirror", "db_save"])
        self.assertEqual([call["status"] for call in delivery_calls], ["saved_sonar", "skipped_margin"])
        self.assertEqual(delivery_calls[0]["listing_id"], "listing-margin-sonar")
        self.assertEqual(
            delivery_calls[1]["error_message"],
            "margin_below_floor | margin=$100 floor=$2500 tier=standard bid=$19000 mmr=$21500 cost=$21400 max_bid=$20500 headroom=$1500 pricing=market_comp comp_price=$41182 comp_count=3 comp_conf=0.69",
        )

    def test_apify_webhook_classifies_proxy_pricing_before_margin_floor(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-proxy-ceiling", "defaultDatasetId": "dataset-proxy-ceiling"},
        }
        vehicle = {
            "run_id": "run-proxy-ceiling",
            "listing_id": "govdeals-2025-mustang",
            "listing_url": "https://www.govdeals.com/asset/697/26928",
            "title": "New (Surplus Inventory) 2025 Ford Mustang EcoBoost Premium Coupe",
            "year": 2025,
            "make": "Ford",
            "model": "Mustang",
            "current_bid": 37283,
            "state": "GA",
            "mileage": 38,
            "source_site": "govdeals",
        }
        delivery_calls = []
        sonar_rows = []
        fake_httpx = types.SimpleNamespace(AsyncClient=_HTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", object()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-proxy-ceiling"
        ), patch.object(
            ingest, "update_webhook_log", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: dict(vehicle)
        ), patch.object(
            ingest, "passes_basic_gates", lambda *_args, **_kwargs: {"pass": True, "reason": "ok"}
        ), patch.object(
            ingest,
            "score_vehicle",
            lambda _vehicle: {
                "dos_score": 0,
                "vehicle_tier": "premium",
                "wholesale_margin": -21037,
                "ceiling_pass": False,
                "ceiling_reason": "pricing_maturity_proxy",
                "pricing_trust_blocked": True,
                "pricing_trust_reason": "pricing_maturity_proxy",
                "current_bid": 37283,
                "gross_margin": -21037,
                "mmr_estimated": 22000,
                "total_cost": 43037,
                "max_bid": 0,
                "bid_headroom": 0,
                "pricing_maturity": "proxy",
            },
        ), patch.object(
            ingest, "passes_ingest_margin_floor", lambda *_args, **_kwargs: False
        ), patch.object(
            ingest, "_save_to_sonar_listings", lambda row: sonar_rows.append(dict(row))
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual([row["listing_id"] for row in sonar_rows], ["govdeals-2025-mustang"])
        self.assertEqual([call["channel"] for call in delivery_calls], ["sonar_mirror", "db_save"])
        self.assertEqual([call["status"] for call in delivery_calls], ["saved_sonar", "skipped_ceiling"])
        self.assertTrue(delivery_calls[1]["error_message"].startswith("pricing_maturity_proxy |"))
        self.assertIn("bid=$37,283", delivery_calls[1]["error_message"])

    def test_govdeals_sold_webhook_stages_candidate_instead_of_dealer_sales(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-sold-1", "defaultDatasetId": "dataset-sold-1"},
        }
        vehicle = {
            "run_id": "run-sold-1",
            "listing_id": "govdeals-sold-asset-1",
            "listing_url": "https://www.govdeals.com/asset/123/456",
            "title": "2016 Ford F-150",
            "year": 2016,
            "make": "Ford",
            "model": "F-150",
            "current_bid": 3650,
            "state": "TX",
            "mileage": 98000,
            "vin": "1FTFW1EF1GFA00001",
            "source_site": "govdeals-sold",
        }
        raw_item = {
            "sold_price": 3650,
            "source_site": "govdeals-sold",
            "listing_url": vehicle["listing_url"],
        }
        delivery_calls = []
        webhook_updates = []
        staged_candidates = []

        class _SoldHTTPXAsyncClient(_HTTPXAsyncClient):
            async def get(self, url, *args, **kwargs):
                if "/datasets/" not in url:
                    raise AssertionError(f"unexpected url: {url}")
                return _HTTPXResponse([raw_item])

        fake_httpx = types.SimpleNamespace(AsyncClient=_SoldHTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", _NoDealerSalesSupabase()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-sold-1"
        ), patch.object(
            ingest,
            "update_webhook_log",
            lambda *args, **kwargs: webhook_updates.append((args, kwargs)),
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: dict(vehicle)
        ), patch.object(
            ingest,
            "stage_sold_comp_candidate",
            lambda **kwargs: staged_candidates.append(kwargs),
            create=True,
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(staged_candidates), 1)
        self.assertEqual(staged_candidates[0]["vehicle"]["source_site"], "govdeals-sold")
        self.assertEqual(staged_candidates[0]["raw_item"], raw_item)
        self.assertEqual(staged_candidates[0]["run_id"], "run-sold-1")
        self.assertEqual(len(delivery_calls), 1)
        self.assertEqual(delivery_calls[0]["status"], "candidate_staged")
        self.assertTrue(len(webhook_updates) > 0)
        self.assertNotIn("save_outcomes={'candidate_staged': 1}", webhook_updates[-1][1]["error_message"])
        self.assertIn("funnel=items:1", webhook_updates[-1][1]["error_message"])

    def test_govdeals_sold_webhook_reports_existing_reviewed_candidate_as_skipped(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-sold-reviewed", "defaultDatasetId": "dataset-sold-reviewed"},
        }
        raw_item = {
            "sold_price": 3650,
            "source_site": "govdeals-sold",
            "listing_url": "https://www.govdeals.com/asset/123/456",
        }
        delivery_calls = []
        webhook_updates = []

        class _SoldHTTPXAsyncClient(_HTTPXAsyncClient):
            async def get(self, url, *args, **kwargs):
                if "/datasets/" not in url:
                    raise AssertionError(f"unexpected url: {url}")
                return _HTTPXResponse([raw_item])

        fake_httpx = types.SimpleNamespace(AsyncClient=_SoldHTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", _NoDealerSalesSupabase()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-sold-reviewed"
        ), patch.object(
            ingest,
            "update_webhook_log",
            lambda *args, **kwargs: webhook_updates.append((args, kwargs)),
        ), patch.object(
            ingest,
            "stage_sold_comp_candidate",
            lambda **_kwargs: "candidate_already_reviewed",
            create=True,
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual([call["status"] for call in delivery_calls], ["candidate_already_reviewed"])
        self.assertTrue(len(webhook_updates) > 0)
        self.assertIn("save_outcomes={'candidate_already_reviewed': 1}", webhook_updates[-1][1]["error_message"])

    def test_govdeals_sold_webhook_stages_raw_items_before_opportunity_normalization(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-sold-raw", "defaultDatasetId": "dataset-sold-raw"},
        }
        raw_items = [
            {
                "source_site": "govdeals-sold",
                "url": "https://www.govdeals.com/asset/1/25917",
                "title": "Visit Our Subsidiary Marketplace Sierra Auction at www.sierraauction.com",
                "sold_price": 100000,
            },
            {
                "source_site": "govdeals-sold",
                "url": "https://www.govdeals.com/asset/99/31398",
                "title": "2021 Mercedes-Benz G-Class",
                "year": 2021,
                "make": "Mercedes-Benz",
                "model": "G-63",
                "sold_price": 99000,
            },
            {
                "source_site": "govdeals-sold",
                "url": "https://www.govdeals.com/asset/504/24329",
                "title": "2014 Winnebago Ellipse 42GD RV",
                "year": 2014,
                "make": "WINNEBAGO",
                "model": "ELLIPSE 42GD",
                "sold_price": 83000,
            },
        ]
        delivery_calls = []
        webhook_updates = []
        staged_candidates = []

        class _SoldHTTPXAsyncClient(_HTTPXAsyncClient):
            async def get(self, url, *args, **kwargs):
                if "/datasets/" not in url:
                    raise AssertionError(f"unexpected url: {url}")
                return _HTTPXResponse(raw_items)

        fake_httpx = types.SimpleNamespace(AsyncClient=_SoldHTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", _NoDealerSalesSupabase()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-sold-raw"
        ), patch.object(
            ingest,
            "update_webhook_log",
            lambda *args, **kwargs: webhook_updates.append((args, kwargs)),
        ), patch.object(
            ingest, "normalize_apify_vehicle", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("sold comps must bypass opportunity normalization"))
        ), patch.object(
            ingest,
            "stage_sold_comp_candidate",
            lambda **kwargs: staged_candidates.append(kwargs),
            create=True,
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(staged_candidates), 3)
        self.assertEqual([call["item_index"] for call in staged_candidates], [0, 1, 2])
        self.assertEqual(staged_candidates[1]["vehicle"]["make"], "Mercedes-Benz")
        self.assertEqual(staged_candidates[2]["vehicle"]["model"], "ELLIPSE 42GD")
        self.assertEqual(len(delivery_calls), 3)
        self.assertEqual([call["status"] for call in delivery_calls], ["candidate_staged"] * 3)
        self.assertTrue(len(webhook_updates) > 0)
        self.assertNotIn("save_outcomes={'candidate_staged': 3}", webhook_updates[-1][1]["error_message"])
        self.assertIn("funnel=items:3", webhook_updates[-1][1]["error_message"])

    def test_sold_comp_candidate_row_rejects_missing_vehicle_identity(self):
        raw_item = {
            "source_site": "govdeals-sold",
            "url": "https://www.govdeals.com/asset/1/25917",
            "title": "Visit Our Subsidiary Marketplace Sierra Auction at www.sierraauction.com",
            "sold_price": 100000,
        }
        vehicle = ingest._sold_comp_vehicle_from_raw_item(raw_item, run_id="run-rejected", source_hint=None)

        row = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle,
            raw_item=raw_item,
            run_id="run-rejected",
            item_index=0,
        )

        self.assertEqual(row["candidate_status"], "rejected")
        self.assertEqual(row["rejection_reason"], "missing_year_make_model")
        self.assertEqual(row["source_name"], "govdeals-sold")
        self.assertEqual(row["listing_url"], raw_item["url"])

    def test_sold_comp_candidate_row_accepts_complete_raw_vehicle_identity(self):
        raw_item = {
            "source_site": "govdeals-sold",
            "url": "https://www.govdeals.com/asset/99/31398",
            "title": "2021 Mercedes-Benz G-Class",
            "year": 2021,
            "make": "Mercedes-Benz",
            "model": "G-63",
            "sold_price": 99000,
            "auction_end_time": "2026-06-01T15:00:00Z",
        }
        vehicle = ingest._sold_comp_vehicle_from_raw_item(raw_item, run_id="run-candidate", source_hint=None)

        row = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle,
            raw_item=raw_item,
            run_id="run-candidate",
            item_index=0,
        )

        self.assertEqual(row["candidate_status"], "candidate")
        self.assertIsNone(row["rejection_reason"])
        self.assertEqual(row["year"], 2021)
        self.assertEqual(row["make"], "Mercedes-Benz")
        self.assertEqual(row["model"], "G-63")
        self.assertEqual(row["sale_date"], "2026-06-01")

    def test_sold_comp_candidate_row_rejects_missing_sale_date(self):
        raw_item = {
            "source_site": "govdeals-sold",
            "url": "https://www.govdeals.com/asset/99/31398",
            "title": "2021 Mercedes-Benz G-Class",
            "year": 2021,
            "make": "Mercedes-Benz",
            "model": "G-63",
            "sold_price": 99000,
        }
        vehicle = ingest._sold_comp_vehicle_from_raw_item(raw_item, run_id="run-no-sale-date", source_hint=None)

        row = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle,
            raw_item=raw_item,
            run_id="run-no-sale-date",
            item_index=0,
        )

        self.assertEqual(row["candidate_status"], "rejected")
        self.assertEqual(row["rejection_reason"], "invalid_sale_date")
        self.assertIsNone(row["sale_date"])

    def test_sold_comp_candidate_row_accepts_normalized_auction_end_date(self):
        raw_item = {
            "source_site": "govdeals-sold",
            "url": "https://www.govdeals.com/asset/99/31398",
            "title": "2021 Mercedes-Benz G-Class",
            "year": 2021,
            "make": "Mercedes-Benz",
            "model": "G-63",
            "sold_price": 99000,
            "auction_end_date": "2020-06-01T15:00:00Z",
        }
        vehicle = ingest._sold_comp_vehicle_from_raw_item(raw_item, run_id="run-auction-end-date", source_hint=None)

        row = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle,
            raw_item=raw_item,
            run_id="run-auction-end-date",
            item_index=0,
        )

        self.assertEqual(row["candidate_status"], "candidate")
        self.assertIsNone(row["rejection_reason"])
        self.assertEqual(row["sale_date"], "2020-06-01")

    def test_sold_comp_candidate_row_rejects_unparseable_sale_date(self):
        raw_item = {
            "source_site": "govdeals-sold",
            "url": "https://www.govdeals.com/asset/99/31398",
            "title": "2021 Mercedes-Benz G-Class",
            "year": 2021,
            "make": "Mercedes-Benz",
            "model": "G-63",
            "sold_price": 99000,
            "auction_end_time": "not-a-date",
        }
        vehicle = ingest._sold_comp_vehicle_from_raw_item(raw_item, run_id="run-bad-sale-date", source_hint=None)

        row = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle,
            raw_item=raw_item,
            run_id="run-bad-sale-date",
            item_index=0,
        )

        self.assertEqual(row["candidate_status"], "rejected")
        self.assertEqual(row["rejection_reason"], "invalid_sale_date")
        self.assertIsNone(row["sale_date"])

    def test_sold_comp_candidate_row_rejects_future_sale_date(self):
        raw_item = {
            "source_site": "govdeals-sold",
            "url": "https://www.govdeals.com/asset/99/31398",
            "title": "2021 Mercedes-Benz G-Class",
            "year": 2021,
            "make": "Mercedes-Benz",
            "model": "G-63",
            "sold_price": 99000,
            "auction_end_time": "2999-01-25T15:38:33Z",
        }
        vehicle = ingest._sold_comp_vehicle_from_raw_item(raw_item, run_id="run-future-sale-date", source_hint=None)

        row = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle,
            raw_item=raw_item,
            run_id="run-future-sale-date",
            item_index=0,
        )

        self.assertEqual(row["candidate_status"], "rejected")
        self.assertEqual(row["rejection_reason"], "invalid_sale_date")
        self.assertEqual(row["sale_date"], "2999-01-25")

    def test_missing_listing_url_rejections_use_unique_replay_safe_source_ids(self):
        raw_item_one = {
            "source_site": "govdeals-sold",
            "title": "Incomplete sold listing one",
            "year": 2019,
            "make": "Ford",
            "model": "F-150",
            "sold_price": 9100,
            "auction_end_date": "2020-06-01T15:00:00Z",
        }
        raw_item_two = {
            **raw_item_one,
            "title": "Incomplete sold listing two",
        }
        vehicle_one = ingest._sold_comp_vehicle_from_raw_item(raw_item_one, run_id="run-missing-url", source_hint=None)
        vehicle_two = ingest._sold_comp_vehicle_from_raw_item(raw_item_two, run_id="run-missing-url", source_hint=None)

        row_one = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle_one,
            raw_item=raw_item_one,
            run_id="run-missing-url",
            item_index=0,
        )
        row_two = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle_two,
            raw_item=raw_item_two,
            run_id="run-missing-url",
            item_index=1,
        )

        self.assertEqual(row_one["rejection_reason"], "missing_listing_url")
        self.assertEqual(row_two["rejection_reason"], "missing_listing_url")
        self.assertNotEqual(row_one["source_listing_id"], row_two["source_listing_id"])

    def test_sold_comp_candidate_row_maps_visible_fee_price_basis_to_all_in(self):
        raw_item = {
            "source_site": "govdeals-sold",
            "listing_url": "https://www.govdeals.com/asset/17167/7167",
            "title": "3052A/ 2014 Ford F-150",
            "year": 2014,
            "make": "Ford",
            "model": "F-150",
            "sold_price": 3074,
            "sold_price_all_in": 3458.25,
            "price_basis": "source_sold_amount_with_visible_fees",
            "auction_end_time": "2026-05-16T00:08:00Z",
        }
        vehicle = ingest._sold_comp_vehicle_from_raw_item(raw_item, run_id="run-visible-fees", source_hint=None)

        row = ingest._build_sold_comp_candidate_row(
            vehicle=vehicle,
            raw_item=raw_item,
            run_id="run-visible-fees",
            item_index=0,
        )

        self.assertEqual(row["price_basis"], "all_in")
        self.assertEqual(row["sold_price_hammer"], 3074)
        self.assertEqual(row["sold_price_all_in"], 3458.25)

    def test_govdeals_sold_webhook_skips_source_quality_proof_before_candidate_staging(self):
        payload = {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "resource": {"id": "run-sold-proof-skip", "defaultDatasetId": "dataset-sold-proof-skip"},
        }
        raw_items = [
            {
                "record_type": "source_quality_proof",
                "source_site": "govdeals-sold",
                "source_quality_proof": {"pushed_rows_total": 1},
            },
            {
                "source_site": "govdeals-sold",
                "listing_url": "https://www.govdeals.com/asset/17167/7167",
                "title": "3052A/ 2014 Ford F-150",
                "year": 2014,
                "make": "Ford",
                "model": "F-150",
                "sold_price": 3074,
                "auction_end_time": "2026-05-16T00:08:00Z",
            },
        ]
        delivery_calls = []
        staged_candidates = []

        class _SoldHTTPXAsyncClient(_HTTPXAsyncClient):
            async def get(self, url, *args, **kwargs):
                if "/datasets/" not in url:
                    raise AssertionError(f"unexpected url: {url}")
                return _HTTPXResponse(raw_items)

        fake_httpx = types.SimpleNamespace(AsyncClient=_SoldHTTPXAsyncClient)

        with patch.object(ingest, "WEBHOOK_SECRET", "topsecret"), patch.object(
            ingest, "WEBHOOK_SECRET_PREVIOUS", ""
        ), patch.object(ingest, "supabase_client", _NoDealerSalesSupabase()), patch.object(
            ingest, "_find_recent_webhook_replay", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest, "insert_webhook_log", lambda *_args, **_kwargs: "log-sold-proof-skip"
        ), patch.object(
            ingest, "update_webhook_log", lambda *_args, **_kwargs: None
        ), patch.object(
            ingest,
            "stage_sold_comp_candidate",
            lambda **kwargs: staged_candidates.append(kwargs) or "candidate_staged",
            create=True,
        ), patch.object(
            ingest,
            "_record_delivery_log",
            lambda **kwargs: delivery_calls.append(kwargs),
        ), patch.dict(sys.modules, {"httpx": fake_httpx}):
            response = asyncio.run(
                ingest.apify_webhook(_Request(payload), _StubBackgroundTasks(), x_apify_webhook_secret="topsecret")
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(staged_candidates), 1)
        self.assertEqual(staged_candidates[0]["raw_item"]["title"], "3052A/ 2014 Ford F-150")
        self.assertEqual([call["status"] for call in delivery_calls], ["skipped_proof", "candidate_staged"])
        self.assertEqual(delivery_calls[0]["channel"], "db_save")
        self.assertEqual(delivery_calls[0]["error_message"], "source_quality_proof_record")

    def test_stage_sold_comp_candidate_creates_run_ledger_before_candidate(self):
        supabase = _ExistingCandidateSupabase([])
        vehicle = {
            "run_id": "run-sold-ledger",
            "listing_id": "asset-ledger-1",
            "listing_url": "https://www.govdeals.com/asset/321/654",
            "source_site": "govdeals-sold",
            "year": 2018,
            "make": "Ford",
            "model": "F-150",
            "state": "TX",
        }
        raw_item = {
            "sold_price": 9100,
            "source_site": "govdeals-sold",
            "listing_url": vehicle["listing_url"],
        }

        with patch.object(ingest, "supabase_client", supabase):
            staging_status = ingest.stage_sold_comp_candidate(
                vehicle=vehicle,
                raw_item=raw_item,
                run_id="run-sold-ledger",
                item_index=0,
            )

        operations = supabase.operations
        self.assertEqual(staging_status, "candidate_staged")
        self.assertEqual(operations[0][0], "market_scout_runs")
        self.assertEqual(operations[0][1], "upsert")
        self.assertEqual(operations[0][2]["run_id"], "run-sold-ledger")
        self.assertEqual(operations[0][3]["on_conflict"], "run_id")
        self.assertEqual(operations[0][3]["ignore_duplicates"], True)
        self.assertEqual(operations[1][0], "sold_comp_candidates")
        self.assertEqual(operations[1][1], "select")
        self.assertEqual(operations[2][0], "sold_comp_candidates")
        self.assertEqual(operations[2][1], "upsert")
        self.assertEqual(operations[2][2]["run_id"], "run-sold-ledger")
        self.assertEqual(operations[2][3]["on_conflict"], "source_name,source_listing_id")
        self.assertNotIn("created_at", operations[2][2])

    def test_stage_sold_comp_candidate_fails_if_upsert_is_not_durable(self):
        supabase = _NonDurableCandidateSupabase()
        vehicle = {
            "run_id": "run-sold-ledger",
            "listing_id": "asset-ledger-1",
            "listing_url": "https://www.govdeals.com/asset/321/654",
            "source_site": "govdeals-sold",
            "year": 2018,
            "make": "Ford",
            "model": "F-150",
            "state": "TX",
        }
        raw_item = {
            "sold_price": 9100,
            "source_site": "govdeals-sold",
            "listing_url": vehicle["listing_url"],
        }

        with patch.object(ingest, "supabase_client", supabase):
            with self.assertRaisesRegex(RuntimeError, "sold_comp_candidate_not_durable"):
                ingest.stage_sold_comp_candidate(
                    vehicle=vehicle,
                    raw_item=raw_item,
                    run_id="run-sold-ledger",
                    item_index=0,
                )

        candidate_writes = [
            operation for operation in supabase.operations
            if operation[0] == "sold_comp_candidates" and operation[1] == "upsert"
        ]
        self.assertEqual(len(candidate_writes), 1)

    def test_stage_sold_comp_candidate_does_not_downgrade_already_reviewed_candidate(self):
        supabase = _ExistingCandidateSupabase(
            [{"id": "candidate-existing", "candidate_status": "verified"}]
        )
        vehicle = {
            "run_id": "run-sold-ledger",
            "listing_id": "asset-ledger-1",
            "listing_url": "https://www.govdeals.com/asset/321/654",
            "source_site": "govdeals-sold",
            "year": 2018,
            "make": "Ford",
            "model": "F-150",
            "state": "TX",
        }
        raw_item = {
            "sold_price": 9100,
            "source_site": "govdeals-sold",
            "listing_url": vehicle["listing_url"],
            "auction_end_date": "2020-06-01T15:00:00Z",
        }

        with patch.object(ingest, "supabase_client", supabase):
            staging_status = ingest.stage_sold_comp_candidate(
                vehicle=vehicle,
                raw_item=raw_item,
                run_id="run-sold-ledger",
                item_index=0,
            )

        self.assertEqual(staging_status, "candidate_already_reviewed")
        candidate_writes = [
            operation for operation in supabase.operations
            if operation[0] == "sold_comp_candidates" and operation[1] == "upsert"
        ]
        self.assertEqual(candidate_writes, [])

    def test_stage_sold_comp_candidate_fails_closed_when_existing_status_lookup_fails(self):
        supabase = _FailingCandidateLookupSupabase()
        vehicle = {
            "run_id": "run-sold-ledger",
            "listing_id": "asset-ledger-1",
            "listing_url": "https://www.govdeals.com/asset/321/654",
            "source_site": "govdeals-sold",
            "year": 2018,
            "make": "Ford",
            "model": "F-150",
            "state": "TX",
        }
        raw_item = {
            "sold_price": 9100,
            "source_site": "govdeals-sold",
            "listing_url": vehicle["listing_url"],
            "auction_end_date": "2020-06-01T15:00:00Z",
        }

        with patch.object(ingest, "supabase_client", supabase):
            with self.assertRaisesRegex(RuntimeError, "sold_comp_candidate_status_lookup_failed"):
                ingest.stage_sold_comp_candidate(
                    vehicle=vehicle,
                    raw_item=raw_item,
                    run_id="run-sold-ledger",
                    item_index=0,
                )

        candidate_writes = [
            operation for operation in supabase.operations
            if operation[0] == "sold_comp_candidates" and operation[1] == "upsert"
        ]
        self.assertEqual(candidate_writes, [])

    def test_stage_sold_comp_candidate_direct_pg_does_not_downgrade_already_reviewed_candidate(self):
        vehicle = {
            "run_id": "run-sold-ledger",
            "listing_id": "asset-ledger-1",
            "listing_url": "https://www.govdeals.com/asset/321/654",
            "source_site": "govdeals-sold",
            "year": 2018,
            "make": "Ford",
            "model": "F-150",
            "state": "TX",
        }
        raw_item = {
            "sold_price": 9100,
            "source_site": "govdeals-sold",
            "listing_url": vehicle["listing_url"],
            "auction_end_date": "2020-06-01T15:00:00Z",
        }
        writes = []

        with patch.object(ingest, "supabase_client", None), patch.object(
            ingest, "_direct_supabase_db_url", "postgresql://example"
        ), patch.object(
            ingest,
            "_existing_sold_comp_candidate_status_direct_pg",
            lambda *_args, **_kwargs: "verified",
        ), patch.object(
            ingest,
            "_upsert_market_scout_run_direct_pg",
            lambda *_args, **_kwargs: writes.append("run"),
        ), patch.object(
            ingest,
            "_upsert_sold_comp_candidate_direct_pg",
            lambda *_args, **_kwargs: writes.append("candidate"),
        ):
            staging_status = ingest.stage_sold_comp_candidate(
                vehicle=vehicle,
                raw_item=raw_item,
                run_id="run-sold-ledger",
                item_index=0,
            )

        self.assertEqual(staging_status, "candidate_already_reviewed")
        self.assertEqual(writes, [])

    def test_stage_sold_comp_candidate_direct_pg_fails_closed_when_existing_status_lookup_fails(self):
        vehicle = {
            "run_id": "run-sold-ledger",
            "listing_id": "asset-ledger-1",
            "listing_url": "https://www.govdeals.com/asset/321/654",
            "source_site": "govdeals-sold",
            "year": 2018,
            "make": "Ford",
            "model": "F-150",
            "state": "TX",
        }
        raw_item = {
            "sold_price": 9100,
            "source_site": "govdeals-sold",
            "listing_url": vehicle["listing_url"],
            "auction_end_date": "2020-06-01T15:00:00Z",
        }
        writes = []

        def _raise_lookup_failure(*_args, **_kwargs):
            raise RuntimeError("sold_comp_candidate_status_lookup_failed")

        with patch.object(ingest, "supabase_client", None), patch.object(
            ingest, "_direct_supabase_db_url", "postgresql://example"
        ), patch.object(
            ingest,
            "_existing_sold_comp_candidate_status_direct_pg",
            _raise_lookup_failure,
        ), patch.object(
            ingest,
            "_upsert_market_scout_run_direct_pg",
            lambda *_args, **_kwargs: writes.append("run"),
        ), patch.object(
            ingest,
            "_upsert_sold_comp_candidate_direct_pg",
            lambda *_args, **_kwargs: writes.append("candidate"),
        ):
            with self.assertRaisesRegex(RuntimeError, "sold_comp_candidate_status_lookup_failed"):
                ingest.stage_sold_comp_candidate(
                    vehicle=vehicle,
                    raw_item=raw_item,
                    run_id="run-sold-ledger",
                    item_index=0,
                )

        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
