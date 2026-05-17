import hashlib

from backend.ingest.pre_save_skip import build_pre_save_skip_delivery_log_kwargs


def test_build_pre_save_skip_delivery_log_kwargs_uses_raw_listing_identity():
    item = {
        "source_site": "GovDeals",
        "listing_id": "GD-123",
        "listing_url": "https://govdeals.com/asset/123",
    }
    expected_listing_id = hashlib.sha256("govdeals|GD-123".encode()).hexdigest()[:40]

    row = build_pre_save_skip_delivery_log_kwargs(
        item=item,
        run_id="run-1",
        item_index=2,
        status="filtered_out",
        error_message="mileage too high",
    )

    assert row == {
        "run_id": "run-1",
        "listing_id": expected_listing_id,
        "listing_url": "https://govdeals.com/asset/123",
        "opportunity_id": None,
        "channel": "db_save",
        "status": "filtered_out",
        "error_message": "mileage too high",
        "require_durable": True,
    }


def test_build_pre_save_skip_delivery_log_kwargs_hashes_non_dict_items():
    row = build_pre_save_skip_delivery_log_kwargs(
        item="bad item",
        run_id="run-2",
        item_index=3,
        status="normalization_error",
        error_message=None,
    )

    assert row["run_id"] == "run-2"
    assert row["listing_id"] == hashlib.sha256("run-2|raw|3".encode()).hexdigest()[:40]
    assert row["listing_url"] is None
    assert row["channel"] == "db_save"
    assert row["status"] == "normalization_error"
    assert row["error_message"] is None
    assert row["require_durable"] is True
