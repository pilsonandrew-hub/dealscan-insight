from datetime import date
import os
from pathlib import Path
import subprocess
import sys

from scripts import run_sold_comp_verifier


REPO_ROOT = Path(__file__).resolve().parents[1]


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.mode = "select"
        self.payload = None
        self.filters = []
        self.conflict = None

    def select(self, *_args, **_kwargs):
        self.mode = "select"
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, tuple(values)))
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def limit(self, value):
        self.filters.append(("limit", value))
        return self

    def order(self, column, **kwargs):
        self.filters.append(("order", column, kwargs))
        return self

    def upsert(self, payload, **kwargs):
        self.mode = "upsert"
        self.payload = payload
        self.conflict = kwargs.get("on_conflict")
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = payload
        return self

    def execute(self):
        if self.mode == "upsert":
            self.client.writes.append(
                {
                    "table": self.table_name,
                    "mode": self.mode,
                    "payload": self.payload,
                    "on_conflict": self.conflict,
                }
            )
            return _Result(self.payload if isinstance(self.payload, list) else [self.payload])
        if self.mode == "update":
            self.client.writes.append(
                {
                    "table": self.table_name,
                    "mode": self.mode,
                    "payload": self.payload,
                    "filters": list(self.filters),
                }
            )
            return _Result([self.payload])
        self.client.reads.append(
            {
                "table": self.table_name,
                "filters": list(self.filters),
            }
        )
        rows = list(self.client.rows.get(self.table_name, []))
        for filter_item in self.filters:
            if filter_item[0] == "in":
                _kind, column, values = filter_item
                rows = [row for row in rows if row.get(column) in values]
            elif filter_item[0] == "eq":
                _kind, column, value = filter_item
                rows = [row for row in rows if row.get(column) == value]
            elif filter_item[0] == "order":
                _kind, column, kwargs = filter_item
                rows = sorted(
                    rows,
                    key=lambda row: row.get(column) or "",
                    reverse=bool(kwargs.get("desc")),
                )
            elif filter_item[0] == "limit":
                rows = rows[: filter_item[1]]
        return _Result(rows)


class _Client:
    def __init__(self, rows):
        self.rows = rows
        self.writes = []
        self.reads = []

    def table(self, name):
        return _Query(self, name)


def _candidate(**overrides):
    base = {
        "id": "candidate-1",
        "run_id": "run-1",
        "source_name": "govdeals-sold",
        "source_listing_id": "asset-1",
        "listing_url": "https://www.govdeals.com/asset/1/2",
        "evidence_ref": "https://www.govdeals.com/asset/1/2",
        "sale_date": "2026-06-01",
        "sold_price_hammer": 12400,
        "buyer_premium": 0,
        "fees": 0,
        "sold_price_all_in": 12400,
        "price_basis": "source_reported",
        "currency": "USD",
        "year": 2019,
        "make": "Ford",
        "model": "F-150",
        "trim": "XL",
        "vin": "1FTEW1E50KFA00001",
        "mileage": 82210,
        "channel": "gov",
        "dedup_key": "dedup-1",
        "extractor_version": "apify-webhook-govdeals-sold",
        "source_policy_version": "govdeals-sold-alpha-v1",
        "candidate_status": "candidate",
        "rejection_reason": None,
    }
    base.update(overrides)
    return base


def test_verifier_runner_dry_run_reports_decisions_without_writes():
    client = _Client(
        {
            "sold_comp_candidates": [
                _candidate(),
                _candidate(
                    id="candidate-2",
                    source_listing_id="asset-g-class",
                    make="Mercedes-Benz",
                    model="G-Class",
                    sold_price_all_in=99000,
                    sold_price_hammer=99000,
                    vin=None,
                    dedup_key="dedup-2",
                ),
                _candidate(
                    id="candidate-3",
                    source_listing_id="asset-bad",
                    candidate_status="rejected",
                    rejection_reason="missing_year_make_model",
                    year=None,
                    make=None,
                    model=None,
                    dedup_key="dedup-3",
                ),
            ],
            "verified_sold_comps": [],
        }
    )

    summary = run_sold_comp_verifier.run_verifier(
        client,
        dry_run=True,
        today=date(2026, 6, 3),
        reviewer_version="test-v1",
    )

    assert summary["dry_run"] is True
    assert summary["candidates_reviewed"] == 3
    assert summary["decision_counts"] == {"accepted": 1, "needs_review": 1, "rejected": 1}
    assert summary["rejection_reason_counts"] == {
        "missing_year_make_model": 1,
        "outside_approved_vehicle_scope": 1,
    }
    assert summary["review_rows_written"] == 0
    assert summary["verified_rows_written"] == 0
    assert client.writes == []


def test_verifier_runner_can_scope_candidates_to_one_run_id():
    client = _Client(
        {
            "sold_comp_candidates": [
                _candidate(id="old-candidate", run_id="old-run", source_listing_id="old-asset"),
                _candidate(id="fresh-candidate", run_id="fresh-run", source_listing_id="fresh-asset"),
            ],
            "verified_sold_comps": [],
        }
    )

    summary = run_sold_comp_verifier.run_verifier(
        client,
        dry_run=True,
        today=date(2026, 6, 3),
        run_id="fresh-run",
        reviewer_version="test-v1",
    )

    assert summary["run_id"] == "fresh-run"
    assert summary["candidates_reviewed"] == 1
    assert summary["decision_counts"] == {"accepted": 1}
    candidate_read = next(read for read in client.reads if read["table"] == "sold_comp_candidates")
    assert ("eq", "run_id", "fresh-run") in candidate_read["filters"]


def test_verifier_runner_does_not_order_unscoped_default_query():
    client = _Client(
        {
            "sold_comp_candidates": [
                _candidate(id="first-candidate", source_listing_id="asset-first", created_at="2026-06-01T00:00:00Z"),
                _candidate(id="second-candidate", source_listing_id="asset-second", created_at="2026-06-02T00:00:00Z"),
            ],
            "verified_sold_comps": [],
        }
    )

    run_sold_comp_verifier.run_verifier(
        client,
        dry_run=True,
        today=date(2026, 6, 3),
        reviewer_version="test-v1",
    )

    candidate_read = next(read for read in client.reads if read["table"] == "sold_comp_candidates")
    assert not any(filter_item[0] == "order" for filter_item in candidate_read["filters"])


def test_verifier_runner_orders_scoped_query_by_newest_candidate():
    client = _Client(
        {
            "sold_comp_candidates": [
                _candidate(id="old-candidate", run_id="fresh-run", source_listing_id="old-asset", created_at="2026-06-01T00:00:00Z"),
                _candidate(id="new-candidate", run_id="fresh-run", source_listing_id="new-asset", created_at="2026-06-02T00:00:00Z"),
            ],
            "verified_sold_comps": [],
        }
    )

    summary = run_sold_comp_verifier.run_verifier(
        client,
        dry_run=True,
        today=date(2026, 6, 3),
        limit=1,
        run_id="fresh-run",
        reviewer_version="test-v1",
    )

    candidate_read = next(read for read in client.reads if read["table"] == "sold_comp_candidates")
    assert ("order", "created_at", {"desc": True}) in candidate_read["filters"]
    assert summary["candidates_reviewed"] == 1
    assert summary["run_id"] == "fresh-run"


def test_verifier_runner_write_mode_touches_only_comp_ledger_tables():
    client = _Client(
        {
            "sold_comp_candidates": [_candidate()],
            "verified_sold_comps": [],
        }
    )

    summary = run_sold_comp_verifier.run_verifier(
        client,
        dry_run=False,
        today=date(2026, 6, 3),
        reviewer_version="test-v1",
    )

    assert summary["review_rows_written"] == 1
    assert summary["verified_rows_written"] == 1
    assert {write["table"] for write in client.writes} == {
        "sold_comp_reviews",
        "verified_sold_comps",
        "sold_comp_candidates",
        "market_scout_runs",
    }
    assert all(write["table"] not in {"opportunities", "dealer_sales"} for write in client.writes)


def test_verifier_message_is_aggregate_only():
    message = run_sold_comp_verifier.build_message(
        {
            "dry_run": True,
            "candidates_reviewed": 3,
            "decision_counts": {"accepted": 1, "needs_review": 1, "rejected": 1},
            "rejection_reason_counts": {
                "missing_year_make_model": 1,
                "outside_approved_vehicle_scope": 1,
            },
            "review_rows_written": 0,
            "verified_rows_written": 0,
            "candidate_rows_updated": 0,
            "run_rows_updated": 0,
        }
    )

    assert "DRY RUN" in message
    assert "Candidates reviewed: 3" in message
    assert "accepted=1" in message
    assert "missing_year_make_model=1" in message
    assert "https://" not in message
    assert "1FTEW" not in message


def test_verifier_script_can_be_executed_from_repo_root_like_github_actions():
    env = {
        **os.environ,
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
        "SOLD_COMP_VERIFIER_DRY_RUN": "true",
        "SOLD_COMP_VERIFIER_IMPORT_CHECK": "true",
    }
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_sold_comp_verifier.py",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "SOLD_COMP_VERIFIER_IMPORT_OK" in result.stdout
    assert "ModuleNotFoundError: No module named 'scripts'" not in result.stderr
