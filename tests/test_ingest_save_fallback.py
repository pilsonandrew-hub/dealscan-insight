import asyncio
import os
import psycopg2
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


# Only install the fastapi stub if a real fastapi isn't already loaded.
# This prevents poisoning sys.modules for other test files when pytest
# collects the full suite.
if "fastapi" not in sys.modules:
    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.APIRouter = _StubRouter
    fastapi_stub.Request = object
    fastapi_stub.HTTPException = _StubHTTPException
    fastapi_stub.Header = lambda default=None, **kwargs: default
    fastapi_stub.BackgroundTasks = object
    fastapi_stub.Depends = lambda f=None: f
    fastapi_stub.status = types.SimpleNamespace(
        HTTP_200_OK=200, HTTP_400_BAD_REQUEST=400,
        HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403,
        HTTP_404_NOT_FOUND=404, HTTP_500_INTERNAL_SERVER_ERROR=500,
    )
    # Stub fastapi.responses submodule
    _responses_stub = types.ModuleType("fastapi.responses")
    _responses_stub.JSONResponse = dict
    fastapi_stub.__path__ = []  # make it look like a package
    sys.modules["fastapi"] = fastapi_stub
    sys.modules["fastapi.responses"] = _responses_stub

from webapp.routers import ingest


class _FailingInsert:
    def __init__(self, error_text: str):
        self.error_text = error_text

    def execute(self):
        raise RuntimeError(self.error_text)


class _SuccessfulInsert:
    def __init__(self, row_id: str):
        self.row_id = row_id

    def execute(self):
        return types.SimpleNamespace(data=[{"id": self.row_id}])


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


class _RecordingQuery:
    def __init__(self, table, result_rows):
        self.table = table
        self.result_rows = result_rows
        self.filters = []
        self.limit_value = None

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.table.select_calls.append((list(self.filters), self.limit_value))
        return types.SimpleNamespace(data=self.result_rows)


class _RecordingUpdate:
    def __init__(self, table, payload):
        self.table = table
        self.payload = payload
        self.filters = []

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        self.table.update_calls.append((self.payload, list(self.filters)))
        return types.SimpleNamespace(data=[{"id": "existing-42"}])


class _DuplicateBackfillTable(_StubTable):
    def __init__(self, row: dict, error_text: str, existing_row: dict | None = None):
        super().__init__(row, error_text)
        self.existing_row = existing_row or {}
        self.select_calls = []
        self.update_calls = []

    def select(self, columns):
        self.selected_columns = columns
        return _RecordingQuery(self, [self.existing_row])

    def update(self, payload):
        return _RecordingUpdate(self, payload)


class _DuplicateBackfillSupabase(_StubSupabase):
    def __init__(self, row: dict, error_text: str, existing_row: dict | None = None):
        self._table = _DuplicateBackfillTable(row, error_text, existing_row)

    def table(self, name):
        if name != "opportunities":
            raise AssertionError(f"unexpected table: {name}")
        return self._table


class _CanonicalConflictTable:
    def __init__(self, row: dict, duplicate_row_id: str):
        self.row = row
        self.duplicate_row_id = duplicate_row_id
        self.insert_calls = []

    def insert(self, payload):
        self.insert_calls.append(payload)
        if payload == self.row:
            return _FailingInsert(
                'duplicate key value violates unique constraint "idx_opportunities_canonical_unique" '
                'DETAIL: Key (canonical_id)=(abc) already exists. is_duplicate=false'
            )
        if payload.get("is_duplicate") and payload.get("canonical_record_id"):
            return _SuccessfulInsert(self.duplicate_row_id)
        raise AssertionError(f"unexpected payload: {payload!r}")


class _CanonicalConflictSupabase:
    def __init__(self, row: dict, duplicate_row_id: str):
        self._table = _CanonicalConflictTable(row, duplicate_row_id)

    def table(self, name):
        if name != "opportunities":
            raise AssertionError(f"unexpected table: {name}")
        return self._table


class _FakeUniqueViolation(psycopg2.errors.UniqueViolation):
    def __str__(self):
        return (
            'duplicate key value violates unique constraint "idx_opportunities_canonical_unique" '
            'DETAIL: Key (canonical_id)=(canon-5) already exists. is_duplicate=false'
        )


class SaveOpportunityFallbackTests(unittest.TestCase):
    def _updates_with_key(self, table, key: str):
        return [
            (payload, filters)
            for payload, filters in table.update_calls
            if key in payload
        ]

    def test_below_threshold_save_records_queryable_outcome(self):
        vehicle = {
            "dos_score": 49,
            "score_breakdown": {
                "score_version": "v3_two_lane",
                "score_engine_impl": "score_deal_v3_two_lane",
                "assumption_level": "minor",
                "fallback_flags": ["mmr_proxy_used"],
            },
        }

        saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertIsNone(saved_id)
        self.assertEqual(vehicle["_save_status"], "below_save_threshold")
        self.assertEqual(vehicle["_save_outcome"]["status"], "below_save_threshold")
        self.assertEqual(vehicle["_save_outcome"]["score_version"], "v3_two_lane")
        self.assertEqual(vehicle["_save_outcome"]["score_engine_impl"], "score_deal_v3_two_lane")
        self.assertEqual(vehicle["_save_outcome"]["score_assumption_level"], "minor")
        self.assertEqual(vehicle["_save_outcome"]["score_fallback_flags"], ["mmr_proxy_used"])

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
        self.assertEqual(vehicle["_save_outcome"]["status"], "saved_direct_pg")
        self.assertEqual(vehicle["_save_outcome"]["opportunity_id"], "pg-123")
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

    def test_duplicate_recovery_backfills_enrichment_fields_without_direct_pg(self):
        row = {
            "listing_id": "listing-2",
            "listing_url": "https://example.com/vehicle/2",
            "title": "2024 Honda Accord",
            "vin": "1HGCM82633A004352",
            "mileage": 32100,
            "condition_grade": "good",
            "raw_data": {"detail_enriched": True, "vin": "1HGCM82633A004352", "mileage": 32100},
            "source_run_id": "run-123",
            "run_id": "run-123",
        }
        vehicle = {"dos_score": 80, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(
            row,
            'duplicate key value violates unique constraint "opportunities_listing_key" (23505)',
        )
        fallback_calls = []

        def fake_direct_pg(payload):
            fallback_calls.append(payload)
            return "pg-should-not-run", "saved_direct_pg"

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: (None, False)), patch.object(
            ingest, "_lookup_existing_opportunity_id", lambda *_: "existing-42"
        ), patch.object(ingest, "_save_opportunity_direct_pg", fake_direct_pg):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-42")
        self.assertEqual(vehicle["_save_status"], "duplicate_existing")
        self.assertEqual(fallback_calls, [])
        self.assertIn(([("id", "existing-42")], 1), supabase._table.select_calls)
        enrichment_updates = self._updates_with_key(supabase._table, "raw_data")
        lifecycle_updates = self._updates_with_key(supabase._table, "last_seen_at")
        self.assertEqual(len(enrichment_updates), 1)
        self.assertEqual(len(lifecycle_updates), 1)
        update_payload, filters = enrichment_updates[0]
        self.assertEqual(filters, [("id", "existing-42")])
        self.assertEqual(update_payload["vin"], row["vin"])
        self.assertEqual(update_payload["mileage"], row["mileage"])
        self.assertEqual(update_payload["condition_grade"], row["condition_grade"])
        self.assertEqual(update_payload["raw_data"], row["raw_data"])
        self.assertEqual(update_payload["source_run_id"], row["source_run_id"])
        self.assertIn("updated_at", update_payload)

    def test_duplicate_recovery_merges_missing_raw_data_without_overwriting_existing_enrichment_fields(self):
        row = {
            "listing_id": "listing-3",
            "listing_url": "https://example.com/vehicle/3",
            "title": "2024 Honda Accord",
            "vin": "1HGCM82633A004352",
            "mileage": 32100,
            "condition_grade": "good",
            "raw_data": {"detail_enriched": True, "description": "New detail-page condition text."},
            "source_run_id": "run-123",
            "run_id": "run-123",
        }
        existing_row = {
            "vin": "EXISTINGVIN1234567",
            "mileage": None,
            "condition_grade": "fair",
            "raw_data": {"original": True, "description": "Existing source text wins."},
            "source_run_id": None,
            "run_id": "old-run",
        }
        vehicle = {"dos_score": 80, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(
            row,
            'duplicate key value violates unique constraint "opportunities_listing_key" (23505)',
            existing_row,
        )

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: (None, False)), patch.object(
            ingest, "_lookup_existing_opportunity_id", lambda *_: "existing-42"
        ), patch.object(ingest, "_save_opportunity_direct_pg", lambda _: ("pg-should-not-run", "saved_direct_pg")):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-42")
        update_payload, _filters = supabase._table.update_calls[0]
        self.assertNotIn("vin", update_payload)
        self.assertEqual(update_payload["mileage"], row["mileage"])
        self.assertNotIn("condition_grade", update_payload)
        self.assertEqual(
            update_payload["raw_data"],
            {
                "original": True,
                "description": "Existing source text wins.",
                "detail_enriched": True,
            },
        )
        self.assertEqual(update_payload["source_run_id"], row["source_run_id"])
        self.assertNotIn("run_id", update_payload)

    def test_vin_duplicate_merges_missing_raw_data_condition_text_without_new_insert(self):
        row = {
            "listing_id": "listing-durango",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "title": "2020 Dodge Durango SRT",
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Poor",
            "raw_data": {
                "title": "2020 Dodge Durango SRT",
                "description": "Starts, runs and drives. Minor scratches noted.",
                "detail_text": "Starts, runs and drives. Minor scratches noted.",
            },
            "source_run_id": "bu9WOTzo6VpaGa0be",
            "run_id": "bu9WOTzo6VpaGa0be",
            "dos_score": 86.9,
            "pricing_maturity": "market_comp",
            "pricing_source": "retail_market_cache",
        }
        existing_row = {
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Poor",
            "raw_data": {"title": "2020 Dodge Durango SRT"},
            "source_run_id": "old-run",
            "run_id": "old-run",
            "pricing_maturity": "market_comp",
            "pricing_source": "retail_market_cache",
        }
        vehicle = {"dos_score": 86.9, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(row, "unused", existing_row)

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: ("existing-durango", False)):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-durango")
        self.assertEqual(vehicle["_save_status"], "vin_dedup_skipped")
        enrichment_updates = self._updates_with_key(supabase._table, "raw_data")
        lifecycle_updates = self._updates_with_key(supabase._table, "last_seen_at")
        self.assertEqual(len(enrichment_updates), 1)
        self.assertEqual(len(lifecycle_updates), 1)
        update_payload, filters = enrichment_updates[0]
        self.assertEqual(filters, [("id", "existing-durango")])
        self.assertEqual(
            update_payload["raw_data"],
            {
                "title": "2020 Dodge Durango SRT",
                "description": "Starts, runs and drives. Minor scratches noted.",
                "detail_text": "Starts, runs and drives. Minor scratches noted.",
            },
        )
        self.assertNotIn("source_run_id", update_payload)
        self.assertNotIn("vin", update_payload)
        self.assertIn("updated_at", update_payload)

    def test_vin_duplicate_records_lifecycle_bid_change_without_new_insert(self):
        row = {
            "listing_id": "listing-durango",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "auction_end_date": "2026-06-20T18:00:00+00:00",
            "title": "2020 Dodge Durango SRT",
            "vin": "1C4SDJGJ6LC324462",
            "current_bid": 12500,
            "dos_score": 86.9,
            "source_site": "govdeals",
            "source": "govdeals",
            "canonical_id": "canon-durango",
        }
        existing_row = {
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "auction_end_date": "2026-06-20T18:00:00+00:00",
            "current_bid": 12000,
            "first_seen_at": "2026-06-12T05:00:00+00:00",
            "last_seen_at": "2026-06-12T05:00:00+00:00",
            "relist_count": 1,
            "bid_change_count": 2,
            "source_fingerprint": "old-fingerprint",
        }
        vehicle = {"dos_score": 86.9, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(row, "unused", existing_row)

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: ("existing-durango", False)):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-durango")
        self.assertEqual(vehicle["_save_status"], "vin_dedup_skipped")
        lifecycle_payloads = [
            payload
            for payload, _filters in supabase._table.update_calls
            if "last_seen_at" in payload
        ]
        self.assertEqual(len(lifecycle_payloads), 1)
        self.assertEqual(lifecycle_payloads[0]["bid_change_count"], 3)
        self.assertNotIn("relist_count", lifecycle_payloads[0])
        self.assertIn("source_fingerprint", lifecycle_payloads[0])

    def test_vin_duplicate_upgrades_stale_poor_condition_when_new_detail_proves_non_poor(self):
        row = {
            "listing_id": "listing-durango",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "title": "2020 Dodge Durango SRT",
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Fair",
            "raw_data": {
                "title": "2020 Dodge Durango SRT",
                "description": "Starts, runs and drives. Minor scratches noted.",
                "detail_text": "Starts, runs and drives. Minor scratches noted.",
            },
            "source_run_id": "run-with-detail-text",
            "run_id": "run-with-detail-text",
            "dos_score": 86.9,
            "pricing_maturity": "market_comp",
            "pricing_source": "retail_market_cache",
        }
        existing_row = {
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Poor",
            "raw_data": {"title": "2020 Dodge Durango SRT"},
            "source_run_id": "old-run",
            "run_id": "old-run",
            "pricing_maturity": "market_comp",
            "pricing_source": "retail_market_cache",
        }
        vehicle = {"dos_score": 86.9, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(row, "unused", existing_row)

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: ("existing-durango", False)):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-durango")
        update_payload, _filters = supabase._table.update_calls[0]
        self.assertEqual(update_payload["condition_grade"], "Fair")
        self.assertEqual(update_payload["raw_data"]["detail_text"], "Starts, runs and drives. Minor scratches noted.")

    def test_vin_duplicate_does_not_upgrade_condition_when_existing_has_negative_evidence(self):
        row = {
            "listing_id": "listing-durango",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "title": "2020 Dodge Durango SRT",
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Fair",
            "raw_data": {
                "description": "Starts, runs and drives. Minor scratches noted.",
                "detail_text": "Starts, runs and drives. Minor scratches noted.",
            },
            "source_run_id": "run-with-detail-text",
            "run_id": "run-with-detail-text",
        }
        existing_row = {
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Poor",
            "raw_data": {
                "title": "2020 Dodge Durango SRT",
                "description": "Vehicle does not run. No start condition.",
            },
            "source_run_id": "old-run",
            "run_id": "old-run",
        }
        vehicle = {"dos_score": 86.9, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(row, "unused", existing_row)

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: ("existing-durango", False)):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-durango")
        update_payload, _filters = supabase._table.update_calls[0]
        self.assertNotIn("condition_grade", update_payload)
        self.assertEqual(update_payload["raw_data"]["detail_text"], "Starts, runs and drives. Minor scratches noted.")

    def test_vin_duplicate_does_not_upgrade_condition_from_title_only_evidence(self):
        row = {
            "listing_id": "listing-durango",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "title": "2020 Dodge Durango SRT",
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Fair",
            "raw_data": {
                "title": "2020 Dodge Durango SRT",
                "description": "2020 Dodge Durango SRT",
            },
            "source_run_id": "title-only-run",
            "run_id": "title-only-run",
        }
        existing_row = {
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 13983,
            "condition_grade": "Poor",
            "raw_data": {"title": "2020 Dodge Durango SRT"},
            "source_run_id": "old-run",
            "run_id": "old-run",
        }
        vehicle = {"dos_score": 86.9, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(row, "unused", existing_row)

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: ("existing-durango", False)):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-durango")
        update_payload, _filters = supabase._table.update_calls[0]
        self.assertNotIn("condition_grade", update_payload)
        self.assertEqual(update_payload["raw_data"]["description"], "2020 Dodge Durango SRT")

    def test_vin_duplicate_refreshes_existing_proxy_pricing_when_new_truth_is_market_comp(self):
        row = {
            "listing_id": "listing-durango",
            "listing_url": "https://www.govdeals.com/asset/123/456",
            "title": "2020 Dodge Durango SRT",
            "vin": "1C4SDJGJ6LC324462",
            "current_bid": 10600,
            "dos_score": 86.9,
            "pricing_maturity": "market_comp",
            "pricing_source": "retail_market_cache",
            "pricing_updated_at": "2026-06-02T10:53:00+00:00",
            "retail_asking_price_estimate": 46004,
            "retail_comp_price_estimate": 46004,
            "retail_comp_low": 41536,
            "retail_comp_high": 55171,
            "retail_comp_count": 5,
            "retail_comp_confidence": 0.89,
            "expected_close_bid": 13685.15,
            "current_bid_trust_score": 0.75,
            "expected_close_source": "auction_stage_adjusted",
            "acquisition_price_basis": 14000,
            "acquisition_basis_source": "expected_close_bid",
            "gross_margin": 15300,
            "max_bid": 23270,
            "bid_headroom": 12670,
            "ceiling_reason": "score_deal_v3_two_lane",
            "score_version": "score_deal_v3_two_lane",
        }
        existing_row = {
            "pricing_maturity": "proxy",
            "pricing_source": "model:durango",
            "pricing_updated_at": None,
        }
        vehicle = {"dos_score": 86.9, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(row, "unused", existing_row)

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: ("existing-durango", False)):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-durango")
        self.assertEqual(vehicle["_save_status"], "vin_dedup_pricing_refreshed")
        pricing_updates = self._updates_with_key(supabase._table, "pricing_maturity")
        lifecycle_updates = self._updates_with_key(supabase._table, "last_seen_at")
        self.assertEqual(len(pricing_updates), 1)
        self.assertEqual(len(lifecycle_updates), 1)
        update_payload, filters = pricing_updates[0]
        self.assertEqual(filters, [("id", "existing-durango")])
        self.assertEqual(update_payload["pricing_maturity"], "market_comp")
        self.assertEqual(update_payload["pricing_source"], "retail_market_cache")
        self.assertEqual(update_payload["retail_comp_price_estimate"], 46004)
        self.assertEqual(update_payload["retail_comp_count"], 5)
        self.assertEqual(update_payload["expected_close_bid"], 13685.15)
        self.assertEqual(update_payload["max_bid"], 23270)
        self.assertEqual(update_payload["bid_headroom"], 12670)
        self.assertNotIn("vin", update_payload)
        self.assertNotIn("listing_url", update_payload)
        self.assertIn("updated_at", update_payload)

    def test_vin_duplicate_backfills_missing_enrichment_without_new_insert(self):
        row = {
            "listing_id": "listing-durango",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "title": "2020 Dodge Durango SRT",
            "vin": "1C4SDJGJ6LC324462",
            "mileage": 43122,
            "condition_grade": "Fair",
            "raw_data": {
                "description": "Runs and drives. Interior wear noted.",
                "detail_text": "Runs and drives. Interior wear noted.",
            },
            "source_run_id": "3PEh74Eh4q7K4pYsY",
            "run_id": "3PEh74Eh4q7K4pYsY",
            "dos_score": 86.9,
            "pricing_maturity": "market_comp",
            "pricing_source": "retail_market_cache",
            "retail_comp_price_estimate": 46004,
            "retail_comp_count": 5,
            "expected_close_bid": 13685.15,
            "max_bid": 23270,
            "bid_headroom": 12670,
        }
        existing_row = {
            "vin": "1C4SDJGJ6LC324462",
            "mileage": None,
            "condition_grade": None,
            "raw_data": {},
            "source_run_id": None,
            "run_id": "old-run",
            "pricing_maturity": "market_comp",
            "pricing_source": "retail_market_cache",
            "retail_comp_price_estimate": 46004,
            "retail_comp_count": 5,
            "expected_close_bid": 13685.15,
            "max_bid": 23270,
            "bid_headroom": 12670,
        }
        vehicle = {"dos_score": 86.9, "title": row["title"]}
        supabase = _DuplicateBackfillSupabase(row, "unused", existing_row)

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest, "supabase_client", supabase
        ), patch.object(ingest, "_check_vin_duplicate", lambda *_: ("existing-durango", False)):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "existing-durango")
        self.assertEqual(vehicle["_save_status"], "vin_dedup_skipped")
        enrichment_updates = self._updates_with_key(supabase._table, "raw_data")
        lifecycle_updates = self._updates_with_key(supabase._table, "last_seen_at")
        self.assertEqual(len(enrichment_updates), 1)
        self.assertEqual(len(lifecycle_updates), 1)
        update_payload, filters = enrichment_updates[0]
        self.assertEqual(filters, [("id", "existing-durango")])
        self.assertEqual(update_payload["mileage"], row["mileage"])
        self.assertEqual(update_payload["condition_grade"], row["condition_grade"])
        self.assertEqual(update_payload["raw_data"], row["raw_data"])
        self.assertEqual(update_payload["source_run_id"], row["source_run_id"])
        self.assertNotIn("vin", update_payload)
        self.assertNotIn("run_id", update_payload)
        self.assertIn("updated_at", update_payload)

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

    def test_canonical_conflict_retries_as_duplicate_via_supabase(self):
        row = {
            "listing_id": "listing-4",
            "listing_url": "https://example.com/vehicle/4",
            "title": "2024 Toyota RAV4",
            "canonical_id": "canon-4",
            "source": "publicsurplus",
            "is_duplicate": False,
            "canonical_record_id": None,
            "all_sources": ["govdeals"],
            "duplicate_count": 0,
        }
        vehicle = {"dos_score": 80, "title": row["title"]}
        canonical_row = {"id": "canonical-4", "all_sources": ["govdeals"]}
        applied_updates = []

        with patch.object(ingest, "build_opportunity_row", lambda _: dict(row)), patch.object(
            ingest,
            "supabase_client",
            _CanonicalConflictSupabase(row, "dup-4"),
        ), patch.object(
            ingest,
            "_lookup_existing_canonical_opportunity",
            lambda canonical_id: canonical_row if canonical_id == "canon-4" else None,
        ), patch.object(
            ingest,
            "_apply_canonical_update",
            lambda update: applied_updates.append(update) or True,
        ):
            saved_id = asyncio.run(ingest.save_opportunity_to_supabase(vehicle))

        self.assertEqual(saved_id, "dup-4")
        self.assertEqual(vehicle["_save_status"], "saved_supabase_duplicate")
        self.assertTrue(vehicle["is_duplicate"])
        self.assertEqual(vehicle["canonical_record_id"], "canonical-4")
        self.assertEqual(
            applied_updates,
            [
                {
                    "id": "canonical-4",
                    "all_sources": ["govdeals", "publicsurplus"],
                    "duplicate_count": 1,
                }
            ],
        )

    def test_direct_pg_canonical_conflict_retries_as_duplicate(self):
        row = {
            "listing_id": "listing-5",
            "listing_url": "https://example.com/vehicle/5",
            "title": "2024 Honda CR-V",
            "canonical_id": "canon-5",
            "source": "publicsurplus",
            "is_duplicate": False,
            "canonical_record_id": None,
            "all_sources": [],
            "duplicate_count": 0,
        }
        canonical_row = {"id": "canonical-5", "all_sources": ["govdeals"]}
        insert_calls = []
        unique_violation = _FakeUniqueViolation()

        def fake_insert(payload):
            insert_calls.append(payload)
            if len(insert_calls) == 1:
                raise unique_violation
            return "dup-5"

        applied_updates = []
        with patch.object(ingest, "_direct_supabase_db_url", "postgresql://example"), patch.object(
            ingest,
            "_insert_opportunity_direct_pg",
            fake_insert,
        ), patch.object(
            ingest,
            "_lookup_existing_canonical_opportunity",
            lambda canonical_id: canonical_row if canonical_id == "canon-5" else None,
        ), patch.object(
            ingest,
            "_apply_canonical_update",
            lambda update: applied_updates.append(update) or True,
        ):
            saved_id, save_status = ingest._save_opportunity_direct_pg(row)

        self.assertEqual(saved_id, "dup-5")
        self.assertEqual(save_status, "saved_direct_pg_duplicate")
        self.assertEqual(insert_calls[1]["canonical_record_id"], "canonical-5")
        self.assertTrue(insert_calls[1]["is_duplicate"])
        self.assertEqual(
            applied_updates,
            [
                {
                    "id": "canonical-5",
                    "all_sources": ["govdeals", "publicsurplus"],
                    "duplicate_count": 1,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
