import hashlib

from backend.ingest.listing_identity import compute_listing_id


def test_compute_listing_id_matches_legacy_source_url_hash():
    assert compute_listing_id(" GovDeals ", " https://example.com/lot/123 ") == hashlib.sha256(
        "govdeals|https://example.com/lot/123".encode()
    ).hexdigest()[:40]


def test_compute_listing_id_defaults_missing_source_to_unknown():
    assert compute_listing_id("", "https://example.com/lot/123") == hashlib.sha256(
        "unknown|https://example.com/lot/123".encode()
    ).hexdigest()[:40]
