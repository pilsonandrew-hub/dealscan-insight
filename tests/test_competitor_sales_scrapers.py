import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.scrapers.competitor_sales.base import (
    RateLimiter,
    build_competitor_sale_row,
    dedup_key,
    extract_vin,
    normalize_state,
)
from backend.scrapers.competitor_sales.govdeals import normalize_govdeals_lot
from backend.scrapers.competitor_sales.govplanet import normalize_govplanet_record
from backend.scrapers.competitor_sales.publicsurplus import normalize_publicsurplus_record


def test_build_row_requires_positive_price_and_identity():
    assert build_competitor_sale_row(source="govdeals", listing_url="u", sale_price=0, make="Ford", model="F-150") is None
    assert build_competitor_sale_row(source="govdeals", listing_url="u", sale_price=100) is None  # no identity
    row = build_competitor_sale_row(
        source="govdeals", listing_url="u", sale_price="$18,500", make="Ford", model="F-150",
        year="2022", mileage="40,000", location="Dallas, TX",
    )
    assert row["sale_price"] == 18500.0
    assert row["year"] == 2022
    assert row["mileage"] == 40000
    assert row["state"] == "TX"
    assert row["vehicle_class"] == "f-150"
    assert row["currency"] == "USD"


def test_extract_vin_and_state_helpers():
    assert extract_vin("Truck VIN 1FTFW1ET5DFC12345 clean") == "1FTFW1ET5DFC12345"
    assert extract_vin("no vin here") is None
    assert normalize_state("Phoenix, AZ") == "AZ"
    assert normalize_state(None, "ca") == "CA"
    assert normalize_state("Nowhere") is None


def test_dedup_key_prefers_listing_id():
    assert dedup_key("GovDeals", "123", "http://x") == "govdeals|123"
    assert dedup_key("GovDeals", None, "http://x") == "govdeals|http://x"


def test_normalize_govdeals_lot():
    lot = {
        "assetId": "555",
        "winningBid": 23500,
        "modelYear": 2021,
        "makebrand": "Ford",
        "model": "F-250",
        "meterCount": 60000,
        "locationCity": "Austin",
        "locationState": "TX",
        "assetAuctionEndDateUtc": "2026-04-01T00:00:00Z",
        "vin": "1FT7W2BT0MED00000",
    }
    row = normalize_govdeals_lot(lot)
    assert row["source"] == "govdeals"
    assert row["source_listing_id"] == "555"
    assert row["sale_price"] == 23500.0
    assert row["vehicle_class"] == "f-250"
    assert row["state"] == "TX"
    assert row["vin"] == "1FT7W2BT0MED00000"


def test_normalize_govdeals_lot_without_price_is_dropped():
    assert normalize_govdeals_lot({"assetId": "1", "modelYear": 2021, "make": "Ford", "model": "F-150"}) is None


def test_normalize_publicsurplus_record_parses_title():
    record = {
        "auction_id": "987",
        "title": "2020 Chevrolet Silverado 1500 LT",
        "winning_bid": "$21,000",
        "end_date": "2026-03-15T00:00:00Z",
        "location": "Columbus, OH",
    }
    row = normalize_publicsurplus_record(record)
    assert row["source"] == "publicsurplus"
    assert row["make"].lower() == "chevrolet"
    assert row["year"] == 2020
    assert row["vehicle_class"] == "silverado-1500"
    assert row["sale_price"] == 21000.0
    assert row["state"] == "OH"


def test_normalize_govplanet_record():
    record = {
        "itemId": "42",
        "soldAmount": 19500,
        "year": 2023,
        "make": "Ford",
        "model": "F-150 XLT",
        "mileage": 30000,
        "saleDate": "2026-02-20T00:00:00Z",
        "location": "Reno, NV",
        "vin": "1FTFW1E84PFA00000",
    }
    row = normalize_govplanet_record(record)
    assert row["source"] == "govplanet"
    assert row["source_listing_id"] == "42"
    assert row["sale_price"] == 19500.0
    assert row["vehicle_class"] == "f-150"
    assert row["state"] == "NV"


def test_rate_limiter_enforces_min_interval():
    limiter = RateLimiter(min_interval=0.05)
    limiter.wait()
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start >= 0.04
