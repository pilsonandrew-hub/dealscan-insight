from backend.ingest.sonar_listings import build_sonar_listing_row


def test_build_sonar_listing_row_preserves_no_filter_mapping_and_fallbacks():
    vehicle = {
        "listing_id": "lot-1",
        "source_site": "GovDeals",
        "title": "2024 Toyota Camry",
        "year": 2024,
        "make": "Toyota",
        "model": "Camry",
        "trim": "SE",
        "mileage": 12000,
        "state": "CA",
        "city": "Irvine",
        "current_bid": "15000",
        "auction_end_date": "2026-01-01T00:00:00Z",
        "listing_url": "https://example.com/lot-1",
        "photo_url": "https://example.com/photo.jpg",
        "issuing_agency": "City of Irvine",
        "condition": "Runs",
        "title_status": "clean",
        "vin": "VIN123",
        "dos_score": 82.5,
    }

    row = build_sonar_listing_row(vehicle)

    assert row["source"] == "GovDeals"
    assert row["source_site"] == "GovDeals"
    assert row["current_bid"] == 15000.0
    assert row["image_url"] == "https://example.com/photo.jpg"
    assert row["photo_url"] == "https://example.com/photo.jpg"
    assert row["agency_name"] == "City of Irvine"
    assert row["dos_score"] == 82.5


def test_build_sonar_listing_row_uses_normalized_auction_end_time_fallback():
    row = build_sonar_listing_row({
        "source_site": "publicsurplus",
        "listing_url": "https://example.com/lot-2",
        "auction_end_time": "2026-06-05T12:00:00+00:00",
    })

    assert row["auction_end_date"] == "2026-06-05T12:00:00+00:00"


def test_build_sonar_listing_row_defaults_current_bid_to_zero():
    assert build_sonar_listing_row({"source": "GSA"})["current_bid"] == 0.0
