import os
import sqlite3
import tempfile
import unittest
import sys
from unittest.mock import patch, MagicMock
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.store import db_connection, upsert_public_listing, batch_upsert_public_listings
from src.ingest.scrapers.structures import PublicListing


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


class StoreTests(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            self.tmp_path = tmp.name
        os.environ["DB_PATH"] = self.tmp_path

    def tearDown(self):
        os.environ.pop("DB_PATH", None)
        try:
            os.unlink(self.tmp_path)
        except OSError:
            pass

    def test_upsert_listing(self):
        listing = example_listing()
        upsert_public_listing(listing)

        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source_site, listing_url FROM public_listings")
            row = cursor.fetchone()
            self.assertEqual(row, ("Test", "http://test.com/1"))

    def test_upsert_conflict_updates(self):
        listing = example_listing()
        upsert_public_listing(listing)
        updated = example_listing(current_bid=1500.0)
        upsert_public_listing(updated)

        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_bid FROM public_listings WHERE listing_url=?", (listing.listing_url,))
            self.assertEqual(cursor.fetchone()[0], 1500.0)

    def test_invalid_data_raises(self):
        listing = example_listing(listing_url=None)
        with self.assertRaises(ValueError):
            upsert_public_listing(listing)

    def test_duplicate_vin_raises(self):
        listing1 = example_listing()
        listing2 = example_listing(listing_url="http://test.com/2")
        upsert_public_listing(listing1)
        with self.assertRaises(sqlite3.IntegrityError):
            upsert_public_listing(listing2)

    def test_batch_upsert_success(self):
        listings = [
            example_listing(listing_url="http://test.com/1", vin="VIN1"),
            example_listing(listing_url="http://test.com/2", vin="VIN2"),
            example_listing(listing_url="http://test.com/3", vin="VIN3"),
        ]

        batch_upsert_public_listings(listings)

        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM public_listings")
            self.assertEqual(cursor.fetchone()[0], 3)

    def test_batch_upsert_rollback_on_failure(self):
        initial_listing = example_listing(vin="EXISTING_VIN")
        upsert_public_listing(initial_listing)

        listings = [
            example_listing(listing_url="http://test.com/batch1", vin="NEW_VIN1"),
            example_listing(listing_url="http://test.com/batch2", vin="NEW_VIN2"),
            example_listing(listing_url="http://test.com/batch3", vin="EXISTING_VIN"),
        ]

        with self.assertRaises(sqlite3.IntegrityError):
            batch_upsert_public_listings(listings)

        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM public_listings")
            self.assertEqual(cursor.fetchone()[0], 1)

            cursor.execute("SELECT vin FROM public_listings")
            self.assertEqual(cursor.fetchone()[0], "EXISTING_VIN")

    def test_upsert_rollback_on_database_error(self):
        listing = example_listing()

        with patch("src.utils.store.db_connection") as mock_db_connection:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = sqlite3.DatabaseError("Simulated database error")
            mock_db_connection.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(sqlite3.DatabaseError):
                upsert_public_listing(listing)

        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM public_listings")
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_validation_error_no_database_interaction(self):
        listing = example_listing(make="")

        with patch("src.utils.store.db_connection") as mock_db_connection:
            with self.assertRaises(ValueError):
                upsert_public_listing(listing)

            mock_db_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
