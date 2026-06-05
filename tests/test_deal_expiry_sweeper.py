from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from scripts import deal_expiry_sweeper


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table_name, mode="select"):
        self.client = client
        self.table_name = table_name
        self.mode = mode
        self.filters = []
        self.payload = None
        self.ids = None
        self.conflict = None

    def select(self, *_args, **_kwargs):
        self.mode = "select"
        self.client.selects.append({"table": self.table_name, "select": _args[0] if _args else ""})
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args, **_kwargs):
        return self

    def lt(self, column, value):
        self.filters.append(("lt", column, value))
        return self

    def neq(self, column, value):
        self.filters.append(("neq", column, value))
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.filters.append(("lte", column, value))
        return self

    def is_(self, column, value):
        self.filters.append(("is", column, value))
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = payload
        return self

    def upsert(self, payload, **kwargs):
        self.mode = "upsert"
        self.payload = payload
        self.conflict = kwargs.get("on_conflict")
        self.upsert_kwargs = kwargs
        return self

    def in_(self, column, values):
        self.ids = list(values)
        self.filters.append(("in", column, tuple(values)))
        return self

    def execute(self):
        if self.mode == "update":
            self.client.updates.append(
                {
                    "table": self.table_name,
                    "payload": self.payload,
                    "ids": self.ids,
                    "filters": list(self.filters),
                }
            )
            return _Result([{"id": value} for value in self.ids])
        if self.mode == "upsert":
            self.client.upserts.append(
                {
                    "table": self.table_name,
                    "payload": self.payload,
                    "on_conflict": self.conflict,
                    **getattr(self, "upsert_kwargs", {}),
                }
            )
            return _Result(self.payload if isinstance(self.payload, list) else [self.payload])

        key = tuple((method, column, value) for method, column, value in self.filters)
        rows = self.client.select_rows.get(key, [])
        return _Result(rows)


class _Client:
    def __init__(self, select_rows):
        self.select_rows = select_rows
        self.selects = []
        self.updates = []
        self.upserts = []
        self.operations = []

    def table(self, name):
        return _Query(self, name)


def test_sweeper_script_starts_without_pythonpath():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "deal_expiry_sweeper.py"
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONPATH",
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "BOT_TOKEN",
            "CHAT_ID",
        }
    }

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "ModuleNotFoundError: No module named 'backend'" not in result.stderr
    assert "SUPABASE_URL" in result.stderr


def test_sweeper_archives_stale_saved_inactive_deals():
    now = datetime(2026, 6, 2, 1, 11, tzinfo=timezone.utc)
    archive_cutoff = "2026-05-26T01:11:00+00:00"
    client = _Client(
        {
            (
                ("eq", "pipeline_step", "saved"),
                ("eq", "is_active", False),
                ("lt", "updated_at", archive_cutoff),
            ): [{"id": "saved-inactive-1"}, {"id": "saved-inactive-2"}],
        }
    )

    summary = deal_expiry_sweeper.run_sweep(client, now=now, notify=lambda _text: True)

    assert summary["archived_stale_saved_inactive"] == 2
    assert {
        "table": "opportunities",
        "payload": {"pipeline_step": "archived"},
        "ids": ["saved-inactive-1", "saved-inactive-2"],
        "filters": [("in", "id", ("saved-inactive-1", "saved-inactive-2"))],
    } in client.updates


def test_sweeper_archives_active_high_dos_rows_with_missing_or_invalid_mileage():
    now = datetime(2026, 6, 2, 1, 11, tzinfo=timezone.utc)
    client = _Client(
        {
            (
                ("eq", "is_active", True),
                ("gte", "dos_score", 80),
                ("is", "mileage", "null"),
            ): [{"id": "missing-mileage-1"}, {"id": "missing-mileage-2"}],
            (
                ("eq", "is_active", True),
                ("gte", "dos_score", 80),
                ("lte", "mileage", 0),
            ): [{"id": "zero-mileage-1"}],
        }
    )

    summary = deal_expiry_sweeper.run_sweep(client, now=now, notify=lambda _text: True)

    assert summary["archived_untrusted_active_high_dos_missing_mileage"] == 3
    assert {
        "table": "opportunities",
        "payload": {
            "is_active": False,
            "pipeline_step": "archived",
            "step_status": "q_no_mileage",
        },
        "ids": ["missing-mileage-1", "missing-mileage-2", "zero-mileage-1"],
        "filters": [("in", "id", ("missing-mileage-1", "missing-mileage-2", "zero-mileage-1"))],
    } in client.updates


def test_sweeper_archives_active_high_dos_rows_with_missing_vin():
    now = datetime(2026, 6, 2, 8, 18, tzinfo=timezone.utc)
    client = _Client(
        {
            (
                ("eq", "is_active", True),
                ("gte", "dos_score", 80),
                ("is", "vin", "null"),
            ): [{"id": "missing-vin-1"}, {"id": "missing-vin-2"}],
            (
                ("eq", "is_active", True),
                ("gte", "dos_score", 80),
                ("eq", "vin", ""),
            ): [{"id": "blank-vin-1"}],
        }
    )

    summary = deal_expiry_sweeper.run_sweep(client, now=now, notify=lambda _text: True)

    assert summary["archived_untrusted_active_high_dos_missing_vin"] == 3
    assert {
        "table": "opportunities",
        "payload": {
            "is_active": False,
            "pipeline_step": "archived",
            "step_status": "q_no_vin",
        },
        "ids": ["missing-vin-1", "missing-vin-2", "blank-vin-1"],
        "filters": [("in", "id", ("missing-vin-1", "missing-vin-2", "blank-vin-1"))],
    } in client.updates


def test_sweeper_archives_active_high_dos_rows_missing_source_condition_evidence():
    now = datetime(2026, 6, 5, 9, 5, tzinfo=timezone.utc)
    client = _Client(
        {
            (
                ("eq", "is_active", True),
                ("gte", "dos_score", 80),
            ): [
                {
                    "id": "missing-condition-evidence-1",
                    "title": "2023 Toyota Camry",
                    "condition_grade": "Good",
                    "raw_data": {},
                },
                {
                    "id": "missing-condition-evidence-2",
                    "title": "2022 Ford Explorer",
                    "condition_grade": "Fair",
                    "raw_data": {"detail_text": "2022 Ford Explorer"},
                },
                {
                    "id": "condition-evidence-present",
                    "title": "2023 Toyota Camry",
                    "condition_grade": "Good",
                    "raw_data": {"detail_text": "Starts and runs, normal wear reported."},
                },
                {
                    "id": "weak-condition-grade",
                    "title": "2021 Chevrolet Malibu",
                    "condition_grade": "Unknown",
                    "raw_data": {},
                },
            ],
        }
    )

    summary = deal_expiry_sweeper.run_sweep(client, now=now, notify=lambda _text: True)

    assert summary["archived_untrusted_active_high_dos_missing_condition_evidence"] == 2
    assert {
        "table": "opportunities",
        "payload": {
            "is_active": False,
            "pipeline_step": "archived",
            "step_status": "q_no_cond_ev",
        },
        "ids": ["missing-condition-evidence-1", "missing-condition-evidence-2"],
        "filters": [("in", "id", ("missing-condition-evidence-1", "missing-condition-evidence-2"))],
    } in client.updates


def test_sweeper_condition_evidence_query_uses_live_opportunity_columns_only():
    now = datetime(2026, 6, 5, 10, 15, tzinfo=timezone.utc)
    client = _Client({})

    deal_expiry_sweeper.run_sweep(client, now=now, notify=lambda _text: True, dry_run=True)

    condition_selects = [
        item["select"]
        for item in client.selects
        if "condition_grade" in item["select"] and "raw_data" in item["select"]
    ]
    assert condition_selects
    for select in condition_selects:
        columns = {column.strip() for column in select.split(",")}
        assert "condition" not in columns
        assert "description" not in columns
        assert "details" not in columns
        assert "condition_notes" not in columns
        assert "detail_text" not in columns
        assert "assetLongDesc" not in columns
        assert "damage_type" not in columns
        assert "damage" not in columns


def test_sweeper_archive_step_status_values_fit_live_schema_limit():
    now = datetime(2026, 6, 5, 10, 25, tzinfo=timezone.utc)
    client = _Client(
        {
            (
                ("eq", "is_active", True),
                ("gte", "dos_score", 80),
            ): [
                {
                    "id": "missing-condition-evidence",
                    "title": "2023 Toyota Camry",
                    "condition_grade": "Good",
                    "raw_data": {},
                },
            ],
        }
    )

    deal_expiry_sweeper.run_sweep(client, now=now, notify=lambda _text: True)

    step_statuses = [
        update["payload"].get("step_status")
        for update in client.updates
        if update["payload"].get("step_status")
    ]
    assert step_statuses
    assert all(len(step_status) <= 16 for step_status in step_statuses)


def test_sweeper_refers_expired_deals_for_post_close_outcome_check_without_creating_comp_candidates():
    now = datetime(2026, 6, 2, 8, 18, tzinfo=timezone.utc)
    expired_cutoff = "2026-06-01T08:18:00+00:00"
    client = _Client(
        {
            (
                ("lt", "auction_end_date", expired_cutoff),
                ("neq", "pipeline_step", "expired"),
                ("eq", "is_active", True),
            ): [
                {
                    "id": "opp-1",
                    "source_site": "govdeals",
                    "listing_id": "asset-123",
                    "listing_url": "https://www.govdeals.com/asset/123",
                    "auction_end_date": "2026-06-01T06:00:00+00:00",
                    "year": 2019,
                    "make": "Ford",
                    "model": "F-150",
                    "vin": "1FTEW1E50KFA00001",
                    "mileage": 82210,
                }
            ],
        }
    )

    summary = deal_expiry_sweeper.run_sweep(client, now=now, notify=lambda _text: True)

    assert summary["post_close_outcome_requests"] == 1
    assert {
        "table": "post_close_outcome_requests",
        "payload": [
            {
                "opportunity_id": "opp-1",
                "source_site": "govdeals",
                "source_listing_id": "asset-123",
                "listing_url": "https://www.govdeals.com/asset/123",
                "auction_end_date": "2026-06-01T06:00:00+00:00",
                "referral_source": "deal_expiry_sweeper",
                "referral_reason": "auction_expired",
                "outcome_status": "pending_outcome_check",
                "year": 2019,
                "make": "Ford",
                "model": "F-150",
                "vin": "1FTEW1E50KFA00001",
                "mileage": 82210,
            }
            ],
            "on_conflict": "source_site,source_listing_id",
            "ignore_duplicates": True,
        } in client.upserts
    assert all(upsert["table"] != "sold_comp_candidates" for upsert in client.upserts)


def test_sweeper_referral_does_not_fallback_to_internal_opportunity_id():
    row = {
        "id": "internal-opportunity-uuid",
        "source_site": "govdeals",
        "listing_url": "https://www.govdeals.com/asset/missing",
    }

    assert deal_expiry_sweeper._build_post_close_outcome_request(row) is None


def test_sweeper_upsert_preserves_existing_worker_outcomes():
    client = _Client({})

    count = deal_expiry_sweeper._upsert_post_close_outcome_requests(
        client,
        [
            {
                "id": "opp-1",
                "source_site": "govdeals",
                "listing_id": "asset-123",
                "listing_url": "https://www.govdeals.com/asset/123",
            }
        ],
    )

    assert count == 1
    assert client.upserts[0]["on_conflict"] == "source_site,source_listing_id"
    assert client.upserts[0]["ignore_duplicates"] is True


def test_sweeper_fetch_rows_reuses_generator_filters_on_every_page():
    calls = []
    rows_by_range = {
        (0, 499): [{"id": "row-1"}] * 500,
        (500, 999): [{"id": "row-2"}],
    }

    class PagingQuery:
        def __init__(self):
            self.filters = []
            self.bounds = None

        def select(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def eq(self, column, value):
            self.filters.append(("eq", column, value))
            return self

        def range(self, start, end):
            self.bounds = (start, end)
            return self

        def execute(self):
            calls.append(tuple(self.filters))
            return _Result(rows_by_range.get(self.bounds, []))

    class PagingClient:
        def table(self, _name):
            return PagingQuery()

    filters = (filter_fn for filter_fn in [lambda q: q.eq("is_active", True)])

    rows = deal_expiry_sweeper._fetch_rows(PagingClient(), "id", filters)

    assert len(rows) == 501
    assert calls == [
        (("eq", "is_active", True),),
        (("eq", "is_active", True),),
    ]


def test_sweeper_dry_run_reports_referrals_without_mutating_rows_or_queue():
    now = datetime(2026, 6, 2, 8, 18, tzinfo=timezone.utc)
    expired_cutoff = "2026-06-01T08:18:00+00:00"
    client = _Client(
        {
            (
                ("lt", "auction_end_date", expired_cutoff),
                ("neq", "pipeline_step", "expired"),
                ("eq", "is_active", True),
            ): [
                {
                    "id": "opp-1",
                    "source_site": "govdeals",
                    "listing_id": "asset-123",
                    "listing_url": "https://www.govdeals.com/asset/123",
                    "auction_end_date": "2026-06-01T06:00:00+00:00",
                    "year": 2019,
                    "make": "Ford",
                    "model": "F-150",
                    "vin": "1FTEW1E50KFA00001",
                    "mileage": 82210,
                }
            ],
        }
    )

    summary = deal_expiry_sweeper.run_sweep(
        client,
        now=now,
        notify=lambda _text: True,
        dry_run=True,
    )

    assert summary["dry_run"] is True
    assert summary["expired"] == 1
    assert summary["post_close_outcome_requests"] == 1
    assert client.updates == []
    assert client.upserts == []


def test_sweeper_message_reports_post_close_outcome_referrals():
    message = deal_expiry_sweeper.build_message(
        {
            "expired": 2,
            "post_close_outcome_requests": 2,
            "archived_passed": 0,
            "archived_stale_saved_inactive": 0,
            "archived_untrusted_active_high_dos_missing_mileage": 0,
            "archived_untrusted_active_high_dos_missing_vin": 0,
            "archived_untrusted_active_high_dos_missing_condition_evidence": 0,
            "run_time": "2026-06-02 08:18 UTC",
        }
    )

    assert "Post-close outcome referrals: <b>2</b>" in message


def test_sweeper_message_labels_dry_run():
    message = deal_expiry_sweeper.build_message(
        {
            "dry_run": True,
            "expired": 1,
            "post_close_outcome_requests": 1,
            "archived_passed": 0,
            "archived_stale_saved_inactive": 0,
            "archived_untrusted_active_high_dos_missing_mileage": 0,
            "archived_untrusted_active_high_dos_missing_vin": 0,
            "archived_untrusted_active_high_dos_missing_condition_evidence": 0,
            "run_time": "2026-06-02 08:18 UTC",
        }
    )

    assert "DRY RUN" in message
