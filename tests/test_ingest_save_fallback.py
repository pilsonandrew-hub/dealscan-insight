import asyncio
import os
import sys
import types
import unittest
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


class _FailingInsert:
    def __init__(self, error_text: str):
        self.error_text = error_text

    def execute(self):
        raise RuntimeError(self.error_text)


class _StubTable:
    def __init__(self, row: dict, error_text: str):
        self.row = row
        self.error_text = error_text

    def insert(self, payload):
        if payload != self.row:
            raise AssertionError(f"unexpected payload: {payload!r}")
        return _FailingInsert(self.error_text)


class _StubSupabase:
    def __init__(self, row: dict, error_text: str):
        self.row = row
        self.error_text = error_text

    def table(self, name):
        if name != "opportunities":
            raise AssertionError(f"unexpected table: {name}")
        return _StubTable(self.row, self.error_text)


class SaveOpportunityFallbackTests(unittest.TestCase):
    def test_generic_supabase_failure_falls_back_to_direct_pg(self):
        row = {
            "listing_id": "listing-1",
            "listing_url": "https://example.com/vehicle/1",
            "title": "2024 Toyota Camry",
        }
        vehicle = {"dos_score": 80, "title": row["title"]}
        fallback_calls = []

        def fake_direct_pg(payload):
            fallback_calls.append(payload)
            return "pg-123", "saved_direct_pg"

        with patch.object(ingest, "build_opportunity_row", lambda _: row), patch.object(
            ingest,
            "supabase_client",
            _StubSupabase(row, "connection reset by peer"),
        ), patch.object(ingest, "_save_opportunity_direct_pg", fake_direct_pg):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "pg-123")
        self.assertEqual(vehicle["_save_status"], "saved_direct_pg")
        self.assertEqual(fallback_calls, [row])

    def test_duplicate_recovery_does_not_fall_through_to_direct_pg(self):
        row = {
            "listing_id": "listing-2",
            "listing_url": "https://example.com/vehicle/2",
            "title": "2024 Honda Accord",
        }
        vehicle = {"dos_score": 80, "title": row["title"]}
        fallback_calls = []

        def fake_direct_pg(payload):
            fallback_calls.append(payload)
            return "pg-should-not-run", "saved_direct_pg"

        with patch.object(ingest, "build_opportunity_row", lambda _: row), patch.object(
            ingest,
            "supabase_client",
            _StubSupabase(
                row,
                'duplicate key value violates unique constraint "opportunities_listing_key" (23505)',
            ),
        ), patch.object(ingest, "_lookup_existing_opportunity_id", lambda *_: "existing-42"), patch.object(
            ingest, "_save_opportunity_direct_pg", fake_direct_pg
        ):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-42")
        self.assertEqual(vehicle["_save_status"], "duplicate_existing")
        self.assertEqual(fallback_calls, [])

    def test_pgrst204_still_falls_back_to_direct_pg(self):
        row = {
            "listing_id": "listing-3",
            "listing_url": "https://example.com/vehicle/3",
            "title": "2024 Mazda CX-5",
        }
        vehicle = {"dos_score": 80, "title": row["title"]}

        with patch.object(ingest, "build_opportunity_row", lambda _: row), patch.object(
            ingest,
            "supabase_client",
            _StubSupabase(row, "PGRST204 column processed_at not found"),
        ), patch.object(ingest, "_save_opportunity_direct_pg", lambda payload: ("pg-204", "saved_direct_pg")):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "pg-204")
        self.assertEqual(vehicle["_save_status"], "saved_direct_pg")


if __name__ == "__main__":
    unittest.main()
