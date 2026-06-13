from backend.ingest.lifecycle_memory import (
    build_initial_lifecycle_fields,
    build_lifecycle_update,
    compute_source_fingerprint,
)


def test_compute_source_fingerprint_prefers_source_and_canonical_identity():
    row = {
        "source_site": "GovDeals",
        "canonical_id": "canon-123",
        "listing_url": "https://example.test/asset/1",
    }

    assert compute_source_fingerprint(row) == compute_source_fingerprint({
        "source": "govdeals",
        "canonical_id": "canon-123",
        "listing_url": "https://example.test/asset/2",
    })


def test_initial_lifecycle_fields_set_first_and_last_seen_once():
    now = "2026-06-13T05:30:00+00:00"
    row = {"source_site": "allsurplus", "listing_url": "https://example.test/lot/1"}

    fields = build_initial_lifecycle_fields(row, now_iso=now)

    assert fields["first_seen_at"] == now
    assert fields["last_seen_at"] == now
    assert fields["relist_count"] == 0
    assert fields["bid_change_count"] == 0
    assert fields["source_fingerprint"]


def test_lifecycle_update_increments_bid_change_without_relist_for_same_auction_identity():
    now = "2026-06-13T05:31:00+00:00"
    incoming = {
        "listing_url": "https://example.test/lot/1",
        "auction_end_date": "2026-06-20T18:00:00+00:00",
        "current_bid": 12500,
    }
    existing = {
        "listing_url": "https://example.test/lot/1",
        "auction_end_date": "2026-06-20T18:00:00+00:00",
        "current_bid": 12000,
        "relist_count": 2,
        "bid_change_count": 4,
    }

    update = build_lifecycle_update(incoming, existing, now_iso=now)

    assert update["last_seen_at"] == now
    assert update["bid_change_count"] == 5
    assert "relist_count" not in update


def test_lifecycle_update_increments_relist_when_auction_identity_changes():
    now = "2026-06-13T05:32:00+00:00"
    incoming = {
        "listing_url": "https://example.test/lot/relisted",
        "auction_end_date": "2026-06-25T18:00:00+00:00",
        "current_bid": 12000,
    }
    existing = {
        "listing_url": "https://example.test/lot/original",
        "auction_end_date": "2026-06-20T18:00:00+00:00",
        "current_bid": 12000,
        "relist_count": 2,
        "bid_change_count": 4,
    }

    update = build_lifecycle_update(incoming, existing, now_iso=now)

    assert update["last_seen_at"] == now
    assert update["relist_count"] == 3
    assert "bid_change_count" not in update
