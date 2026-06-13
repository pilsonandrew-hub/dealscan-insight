import asyncio

from backend.ingest.observability import (
    record_parse_event,
    upsert_scrape_run_completion,
    upsert_scrape_run_start,
)


class _Result:
    data = [{"id": "row-1"}]


class _Table:
    def __init__(self, name):
        self.name = name
        self.inserts = []
        self.upserts = []

    def insert(self, payload):
        self.inserts.append(payload)
        return self

    def upsert(self, payload, **kwargs):
        self.upserts.append((payload, kwargs))
        return self

    def execute(self):
        return _Result()


class _Client:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        table = self.tables.get(name)
        if table is None:
            table = _Table(name)
            self.tables[name] = table
        return table


def test_upsert_scrape_run_start_writes_source_run_identity():
    client = _Client()

    assert upsert_scrape_run_start(
        client,
        run_id="run-123",
        source_name="allsurplus",
        actor_id="actor-1",
        dataset_id="dataset-1",
        item_count=6,
    )

    payload, options = client.tables["scrape_runs"].upserts[0]
    assert options["on_conflict"] == "run_id"
    assert payload["run_id"] == "run-123"
    assert payload["source_name"] == "allsurplus"
    assert payload["actor_id"] == "actor-1"
    assert payload["dataset_id"] == "dataset-1"
    assert payload["item_count"] == 6
    assert payload["status"] == "started"
    assert "started_at" in payload
    assert "updated_at" in payload


def test_upsert_scrape_run_completion_writes_aggregate_counts():
    client = _Client()

    assert upsert_scrape_run_completion(
        client,
        run_id="run-123",
        source_name="allsurplus",
        status="processed",
        item_count=6,
        evaluated_count=5,
        saved_count=0,
        existing_count=4,
        skipped_count=2,
        failed_count=0,
        duplicate_count=4,
        hot_deal_count=0,
        alert_blocked_count=0,
        parse_event_count=6,
        skip_reasons={"source_quality_proof_record": 1, "margin_below_floor": 1},
        save_outcomes={"vin_dedup_lifecycle_refreshed": 4},
        error_message=None,
    )

    payload, options = client.tables["scrape_runs"].upserts[0]
    assert options["on_conflict"] == "run_id"
    assert payload["status"] == "processed"
    assert payload["existing_count"] == 4
    assert payload["parse_event_count"] == 6
    assert payload["skip_reasons"] == {"source_quality_proof_record": 1, "margin_below_floor": 1}
    assert payload["save_outcomes"] == {"vin_dedup_lifecycle_refreshed": 4}
    assert payload["completed_at"]


def test_record_parse_event_sanitizes_metadata_and_inserts_event():
    client = _Client()

    assert record_parse_event(
        client,
        run_id="run-123",
        source_name="allsurplus",
        event_type="db_save",
        status="vin_dedup_lifecycle_refreshed",
        item_index=3,
        listing_id="listing-1",
        reason="duplicate_lifecycle",
        error_message=None,
        metadata={
            "listing_url": "https://example.com/private",
            "vin": "SECRET-VIN",
            "score": 82.5,
        },
    )

    payload = client.tables["parse_events"].inserts[0]
    assert payload["run_id"] == "run-123"
    assert payload["source_name"] == "allsurplus"
    assert payload["event_type"] == "db_save"
    assert payload["status"] == "vin_dedup_lifecycle_refreshed"
    assert payload["item_index"] == 3
    assert payload["listing_id"] == "listing-1"
    assert payload["reason"] == "duplicate_lifecycle"
    assert payload["metadata"] == {"score": 82.5}
    assert "listing_url" not in payload["metadata"]
    assert "vin" not in payload["metadata"]


def test_process_webhook_items_records_run_start_and_bad_dataset_completion(monkeypatch):
    from webapp.routers import ingest
    import httpx

    calls = {"starts": [], "completions": [], "webhook_updates": []}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": "shape"}

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", _AsyncClient)
    monkeypatch.setattr(ingest, "supabase_client", None)
    monkeypatch.setattr(ingest, "_apify_api_token", lambda: "token")
    monkeypatch.setattr(
        ingest,
        "upsert_scrape_run_start",
        lambda *args, **kwargs: calls["starts"].append((args, kwargs)) or True,
    )
    monkeypatch.setattr(
        ingest,
        "upsert_scrape_run_completion",
        lambda *args, **kwargs: calls["completions"].append((args, kwargs)) or True,
    )
    monkeypatch.setattr(
        ingest,
        "update_webhook_log",
        lambda *args, **kwargs: calls["webhook_updates"].append((args, kwargs)),
    )

    asyncio.run(
        ingest._process_webhook_items(
            payload={},
            metadata={
                "run_id": "run-bad-shape",
                "dataset_id": "dataset123",
                "actor_id": "actor-1",
                "source": "ds-allsurplus",
                "item_count": 7,
            },
            apify_run_id="run-bad-shape",
            audit_state={"fallbacks": []},
            webhook_log_id="webhook-1",
        )
    )

    assert calls["starts"][0][1]["run_id"] == "run-bad-shape"
    assert calls["starts"][0][1]["dataset_id"] == "dataset123"
    assert calls["starts"][0][1]["item_count"] == 7
    assert calls["completions"][0][1]["status"] == "error"
    assert calls["completions"][0][1]["error_message"] == "dataset_items_not_list"
    assert calls["webhook_updates"][0][0][1] == "error"
