import os
import asyncio
import logging

from .structures import PublicListing

OFFLINE = os.getenv("OFFLINE_MODE", "0") == "1"


class PublicSurplusScraper:
    def __init__(self, spec):
        self.spec = spec

    async def fetch(self):
        if OFFLINE:
            await asyncio.sleep(0.01)
            yield PublicListing(
                source_site="PublicSurplus",
                listing_url="https://example.com/ps/lot/bravo",
                auction_end="2025-08-22T16:30:00Z",
                year=2018,
                make="Honda",
                model="Accord",
                trim="Sport",
                mileage=102000,
                current_bid=8200.0,
                location="Phoenix, AZ",
                state="AZ",
                vin="1HGEN3F59JA000000",
                description="Clean title. No accidents.",
            )
            yield PublicListing(
                source_site="PublicSurplus",
                listing_url="https://example.com/ps/lot/ohio-unit",
                auction_end="2025-08-23T15:00:00Z",
                year=2017,
                make="Toyota",
                model="Camry",
                trim="LE",
                mileage=118000,
                current_bid=6200.0,
                location="Columbus, OH",
                state="OH",
                vin="4T1BF1FK7HU000000",
                description="No Rust. Midwest unit.",
            )
            return
        logging.info("Live scraping PublicSurplus...")
        # Live scraping implementation goes here
        return
