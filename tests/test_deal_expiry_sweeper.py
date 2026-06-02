from datetime import datetime, timezone

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

    def select(self, *_args, **_kwargs):
        self.mode = "select"
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

        key = tuple((method, column, value) for method, column, value in self.filters)
        rows = self.client.select_rows.get(key, [])
        return _Result(rows)


class _Client:
    def __init__(self, select_rows):
        self.select_rows = select_rows
        self.updates = []

    def table(self, name):
        return _Query(self, name)


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
