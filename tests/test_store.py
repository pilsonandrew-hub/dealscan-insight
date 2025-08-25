import os
import sqlite3
import pytest
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.store import db_connection, upsert_public_listing
from src.ingest.scrapers.structures import PublicListing


@pytest.fixture
def db():
    os.environ['DB_PATH'] = ':memory:'
    with db_connection() as conn:
        yield conn


def example_listing(**overrides):
    data = dict(
        source_site="Test",
        listing_url="http://test.com/1",
        auction_end="2025-08-20T18:00:00Z",
        year=2020,
        make="TestMake",
        model="TestModel",
        trim="TestTrim",
        mileage=50000,
        current_bid=1000.0,
        location="TestCity, TS",
        state="TS",
        vin="TESTVIN123",
        photo_url=None,
        description="Test listing",
    )
    data.update(overrides)
    return PublicListing(**data)


def test_upsert_listing(db):
    listing = example_listing()
    upsert_public_listing(db, listing)
    cursor = db.cursor()
    cursor.execute("SELECT source_site, listing_url FROM public_listings")
    row = cursor.fetchone()
    assert row == ("Test", "http://test.com/1")


def test_upsert_conflict_updates(db):
    listing = example_listing()
    upsert_public_listing(db, listing)
    updated = example_listing(current_bid=1500.0)
    upsert_public_listing(db, updated)
    cursor = db.cursor()
    cursor.execute("SELECT current_bid FROM public_listings WHERE listing_url=?", (listing.listing_url,))
    assert cursor.fetchone()[0] == 1500.0


def test_invalid_data_raises(db):
    listing = example_listing(listing_url=None)
    with pytest.raises(ValueError):
        upsert_public_listing(db, listing)


def test_duplicate_vin_raises(db):
    listing1 = example_listing()
    listing2 = example_listing(listing_url="http://test.com/2")
    upsert_public_listing(db, listing1)
    with pytest.raises(sqlite3.IntegrityError):
        upsert_public_listing(db, listing2)