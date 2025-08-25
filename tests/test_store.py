import os
import sqlite3
import pytest
import sys
from unittest.mock import patch, MagicMock
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.store import db_connection, upsert_public_listing, batch_upsert_public_listings
from src.ingest.scrapers.structures import PublicListing


@pytest.fixture
def setup_test_db():
    """Setup test database environment."""
    os.environ['DB_PATH'] = ':memory:'


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


def test_upsert_listing(setup_test_db):
    listing = example_listing()
    upsert_public_listing(listing)
    
    # Verify the listing was inserted
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT source_site, listing_url FROM public_listings")
        row = cursor.fetchone()
        assert row == ("Test", "http://test.com/1")


def test_upsert_conflict_updates(setup_test_db):
    listing = example_listing()
    upsert_public_listing(listing)
    updated = example_listing(current_bid=1500.0)
    upsert_public_listing(updated)
    
    # Verify the listing was updated
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_bid FROM public_listings WHERE listing_url=?", (listing.listing_url,))
        assert cursor.fetchone()[0] == 1500.0


def test_invalid_data_raises(setup_test_db):
    listing = example_listing(listing_url=None)
    with pytest.raises(ValueError):
        upsert_public_listing(listing)


def test_duplicate_vin_raises(setup_test_db):
    listing1 = example_listing()
    listing2 = example_listing(listing_url="http://test.com/2")
    upsert_public_listing(listing1)
    with pytest.raises(sqlite3.IntegrityError):
        upsert_public_listing(listing2)


def test_batch_upsert_success(setup_test_db):
    """Test successful batch upsert operation."""
    listings = [
        example_listing(listing_url="http://test.com/1", vin="VIN1"),
        example_listing(listing_url="http://test.com/2", vin="VIN2"),
        example_listing(listing_url="http://test.com/3", vin="VIN3"),
    ]
    
    batch_upsert_public_listings(listings)
    
    # Verify all listings were inserted
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM public_listings")
        count = cursor.fetchone()[0]
        assert count == 3


def test_batch_upsert_rollback_on_failure(setup_test_db):
    """Test that batch upsert rolls back completely on failure."""
    # Insert a listing first
    initial_listing = example_listing(vin="EXISTING_VIN")
    upsert_public_listing(initial_listing)
    
    # Create batch with duplicate VIN (will cause constraint violation)
    listings = [
        example_listing(listing_url="http://test.com/batch1", vin="NEW_VIN1"),
        example_listing(listing_url="http://test.com/batch2", vin="NEW_VIN2"),
        example_listing(listing_url="http://test.com/batch3", vin="EXISTING_VIN"),  # Duplicate VIN
    ]
    
    # Batch should fail due to VIN constraint
    with pytest.raises(sqlite3.IntegrityError):
        batch_upsert_public_listings(listings)
    
    # Verify rollback - only the initial listing should exist
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM public_listings")
        count = cursor.fetchone()[0]
        assert count == 1
        
        cursor.execute("SELECT vin FROM public_listings")
        vin = cursor.fetchone()[0]
        assert vin == "EXISTING_VIN"


def test_upsert_rollback_on_database_error(setup_test_db):
    """Test that individual upsert rolls back on database errors."""
    listing = example_listing()
    
    # Mock a database error during execution
    with patch('src.utils.store.db_connection') as mock_db_connection:
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlite3.DatabaseError("Simulated database error")
        mock_db_connection.return_value.__enter__.return_value = mock_conn
        
        with pytest.raises(sqlite3.DatabaseError):
            upsert_public_listing(listing)
    
    # Verify no data was committed due to rollback
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM public_listings")
        count = cursor.fetchone()[0]
        assert count == 0


def test_validation_error_no_database_interaction(setup_test_db):
    """Test that validation errors don't interact with database."""
    listing = example_listing(make="")  # Invalid data
    
    with patch('src.utils.store.db_connection') as mock_db_connection:
        with pytest.raises(ValueError):
            upsert_public_listing(listing)
        
        # Database connection should never be called for validation errors
        mock_db_connection.assert_not_called()