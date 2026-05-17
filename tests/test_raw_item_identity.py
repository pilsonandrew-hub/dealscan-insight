import hashlib

from backend.ingest.raw_item_identity import raw_item_identity


def test_raw_item_identity_handles_non_dict_items_with_run_and_index():
    expected = hashlib.sha256("run-1|raw|3".encode()).hexdigest()[:40]
    assert raw_item_identity("bad-row", "run-1", 3) == (expected, None)


def test_raw_item_identity_prefers_source_and_listing_id_with_url():
    expected = hashlib.sha256("govdeals|A-123".encode()).hexdigest()[:40]
    assert raw_item_identity(
        {"source_site": "GovDeals", "listing_id": "A-123", "listing_url": "https://example.test/a"},
        "run-1",
        0,
    ) == (expected, "https://example.test/a")


def test_raw_item_identity_uses_asset_id_id_url_listing_url_or_vin():
    assert raw_item_identity({"source": "GSA", "assetId": "asset-1"}, "run", 0)[0] == hashlib.sha256(
        "gsa|asset-1".encode()
    ).hexdigest()[:40]
    assert raw_item_identity({"source": "GSA", "id": "id-1"}, "run", 0)[0] == hashlib.sha256(
        "gsa|id-1".encode()
    ).hexdigest()[:40]
    assert raw_item_identity({"source": "GSA", "url": "https://x.test/listing"}, "run", 0) == (
        hashlib.sha256("gsa|https://x.test/listing".encode()).hexdigest()[:40],
        "https://x.test/listing",
    )
    assert raw_item_identity({"source": "GSA", "vin": "VIN123"}, "run", 0)[0] == hashlib.sha256(
        "gsa|VIN123".encode()
    ).hexdigest()[:40]


def test_raw_item_identity_falls_back_to_run_source_title_and_index():
    expected = hashlib.sha256("run-7|unknown|2019 Ford F-150|2".encode()).hexdigest()[:40]
    assert raw_item_identity({"title": "2019 Ford F-150"}, "run-7", 2) == (expected, None)
