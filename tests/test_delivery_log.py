from backend.ingest.delivery_log import (
    build_delivery_log_insert_row,
    build_delivery_log_row,
    build_delivery_log_update_row,
)


def test_build_delivery_log_row_preserves_delivery_fields_with_injected_timestamp():
    row = build_delivery_log_row(
        run_id="run-1",
        listing_id="listing-1",
        listing_url="https://example.com/listing-1",
        opportunity_id="opp-1",
        channel="telegram",
        status="sent",
        external_id="msg-1",
        error_message=None,
        now_fn=lambda: "2026-05-17T15:00:00+00:00",
    )

    assert row == {
        "run_id": "run-1",
        "listing_id": "listing-1",
        "listing_url": "https://example.com/listing-1",
        "opportunity_id": "opp-1",
        "channel": "telegram",
        "status": "sent",
        "external_id": "msg-1",
        "error_message": None,
        "updated_at": "2026-05-17T15:00:00+00:00",
    }


def test_build_delivery_log_insert_row_sets_first_attempt_and_created_at():
    base = build_delivery_log_row(
        run_id="run-1",
        listing_id="listing-1",
        channel="db_save",
        status="skipped_norm",
        now_fn=lambda: "2026-05-17T15:00:00+00:00",
    )

    insert_row = build_delivery_log_insert_row(base)

    assert insert_row["attempt_count"] == 1
    assert insert_row["created_at"] == "2026-05-17T15:00:00+00:00"
    assert insert_row["updated_at"] == "2026-05-17T15:00:00+00:00"
    assert "created_at" not in base
    assert "attempt_count" not in base


def test_build_delivery_log_update_row_increments_existing_attempt_count():
    base = build_delivery_log_row(
        run_id="run-1",
        listing_id="listing-1",
        channel="db_save",
        status="saved",
        now_fn=lambda: "2026-05-17T15:00:00+00:00",
    )

    assert build_delivery_log_update_row(base, {"attempt_count": 4})["attempt_count"] == 5
    assert build_delivery_log_update_row(base, {"attempt_count": None})["attempt_count"] == 1
    assert build_delivery_log_update_row(base, None)["attempt_count"] == 1
    assert "attempt_count" not in base
