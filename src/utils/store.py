import os
import sqlite3
import logging
from contextlib import contextmanager
from dataclasses import asdict
from typing import Iterable

from src.ingest.scrapers.structures import PublicListing

logger = logging.getLogger(__name__)

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.getenv("DB_PATH", os.path.join(APP_ROOT, "data", "auction.db"))


@contextmanager
def db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS public_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_site TEXT NOT NULL,
            listing_url TEXT NOT NULL UNIQUE,
            auction_end TEXT,
            year INTEGER,
            make TEXT,
            model TEXT,
            trim TEXT,
            mileage INTEGER,
            current_bid REAL,
            location TEXT,
            state TEXT,
            vin TEXT UNIQUE,
            photo_url TEXT,
            description TEXT
        )
        """
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _validate_listing(listing: PublicListing) -> None:
    required: Iterable[str] = [
        "source_site",
        "listing_url",
        "auction_end",
        "year",
        "make",
        "model",
        "trim",
        "mileage",
        "current_bid",
        "location",
        "state",
    ]
    data = asdict(listing)
    missing = [key for key in required if data.get(key) in (None, "")]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


def upsert_public_listing(listing: PublicListing) -> None:
    """Upsert a public listing using internal transaction management."""
    _validate_listing(listing)
    data = asdict(listing)
    sql = (
        """
        INSERT INTO public_listings (
            source_site, listing_url, auction_end, year, make, model, trim,
            mileage, current_bid, location, state, vin, photo_url, description
        ) VALUES (
            :source_site, :listing_url, :auction_end, :year, :make, :model, :trim,
            :mileage, :current_bid, :location, :state, :vin, :photo_url, :description
        )
        ON CONFLICT(listing_url) DO UPDATE SET
            source_site=excluded.source_site,
            auction_end=excluded.auction_end,
            year=excluded.year,
            make=excluded.make,
            model=excluded.model,
            trim=excluded.trim,
            mileage=excluded.mileage,
            current_bid=excluded.current_bid,
            location=excluded.location,
            state=excluded.state,
            vin=excluded.vin,
            photo_url=excluded.photo_url,
            description=excluded.description
        """
    )
    try:
        with db_connection() as conn:
            conn.execute(sql, data)
    except sqlite3.Error as e:
        logger.error("DB error upserting listing %s: %s", listing.listing_url, e.__class__.__name__)
        raise


def batch_upsert_public_listings(listings: Iterable[PublicListing]) -> None:
    """Batch upsert multiple listings in a single transaction."""
    with db_connection() as conn:
        for listing in listings:
            _validate_listing(listing)
            data = asdict(listing)
            sql = (
                """
                INSERT INTO public_listings (
                    source_site, listing_url, auction_end, year, make, model, trim,
                    mileage, current_bid, location, state, vin, photo_url, description
                ) VALUES (
                    :source_site, :listing_url, :auction_end, :year, :make, :model, :trim,
                    :mileage, :current_bid, :location, :state, :vin, :photo_url, :description
                )
                ON CONFLICT(listing_url) DO UPDATE SET
                    source_site=excluded.source_site,
                    auction_end=excluded.auction_end,
                    year=excluded.year,
                    make=excluded.make,
                    model=excluded.model,
                    trim=excluded.trim,
                    mileage=excluded.mileage,
                    current_bid=excluded.current_bid,
                    location=excluded.location,
                    state=excluded.state,
                    vin=excluded.vin,
                    photo_url=excluded.photo_url,
                    description=excluded.description
                """
            )
            try:
                conn.execute(sql, data)
            except sqlite3.Error as e:
                logger.error("DB error upserting listing %s: %s", listing.listing_url, e.__class__.__name__)
                raise