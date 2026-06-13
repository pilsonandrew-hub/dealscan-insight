"""Competitor sold-listing scrapers for DealerScope's pricing intelligence engine.

Each scraper collects completed/sold vehicle auctions from a competitor site and
normalizes them into ``competitor_sales`` rows consumed by
``backend.ingest.competitor_pricing``.
"""

from backend.scrapers.competitor_sales.base import (
    RateLimiter,
    build_competitor_sale_row,
    dedup_key,
    robots_allows,
    write_competitor_sales,
)

__all__ = [
    "RateLimiter",
    "build_competitor_sale_row",
    "dedup_key",
    "robots_allows",
    "write_competitor_sales",
]
