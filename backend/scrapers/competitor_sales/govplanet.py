"""GovPlanet sold-listing scraper -> competitor_sales rows.

GovPlanet (Ritchie Bros / IronPlanet network) exposes completed-item results
through a JSON search endpoint. Network fetching is best-effort and
robots/rate-limit aware; the pure normalizer (``normalize_govplanet_record``)
carries the unit-tested logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.scrapers.competitor_sales.base import (
    DEFAULT_USER_AGENT,
    RateLimiter,
    build_competitor_sale_row,
    extract_vin,
    robots_allows,
)

logger = logging.getLogger(__name__)

SOURCE = "govplanet"
BASE_URL = "https://www.govplanet.com"
# IronPlanet/GovPlanet shared search API; ``status=sold`` returns completed items.
SEARCH_API = BASE_URL + "/jsp/s/item/search-results.json"


def _first(record: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_govplanet_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a GovPlanet sold-item record into a competitor_sales row."""
    item_id = _first(record, "itemId", "id", "item_id")
    listing_url = _first(record, "itemUrl", "url", "listing_url")
    if not listing_url and item_id:
        listing_url = f"{BASE_URL}/jsp/s/item/{item_id}"

    sale_price = _first(
        record, "soldAmount", "sellingPrice", "winningBid", "salePrice", "currentBid"
    )
    location = _first(record, "location", "itemLocation", "city_state")

    return build_competitor_sale_row(
        source=SOURCE,
        source_listing_id=str(item_id) if item_id else None,
        listing_url=listing_url or BASE_URL,
        vin=_first(record, "vin", "VIN") or extract_vin(record.get("title"), record.get("description")),
        year=_first(record, "year", "modelYear"),
        make=_first(record, "make", "manufacturer"),
        model=_first(record, "model", "modelName"),
        mileage=_first(record, "mileage", "meterReading", "hours"),
        sale_price=sale_price,
        auction_end_date=_first(record, "saleDate", "endDate", "closeDate", "auction_end_date"),
        condition_notes=_first(record, "description", "conditionNotes"),
        location=location,
        state=_first(record, "state", "locationState"),
        raw=record,
    )


async def fetch_govplanet_sold(max_pages: int = 5, page_size: int = 50) -> List[Dict[str, Any]]:
    """Best-effort fetch of GovPlanet sold vehicle items (raw records)."""
    import httpx

    if not robots_allows(SEARCH_API):
        logger.warning("[%s] robots.txt disallows search path; skipping", SOURCE)
        return []

    limiter = RateLimiter(min_interval=2.0)
    records: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    ) as client:
        for page in range(max_pages):
            limiter.wait()
            params = {
                "category": "Cars and Trucks",
                "status": "sold",
                "page": page,
                "pageSize": page_size,
            }
            try:
                resp = await client.get(SEARCH_API, params=params)
                if resp.status_code != 200:
                    logger.warning("[%s] page %d -> %d", SOURCE, page, resp.status_code)
                    break
                data = resp.json()
                page_records = (
                    data.get("items")
                    or data.get("results")
                    or data.get("searchResults")
                    or []
                )
                if not page_records:
                    break
                records.extend(page_records)
            except Exception as exc:  # pragma: no cover - network path
                logger.error("[%s] page %d failed: %s", SOURCE, page, exc)
                break
    return records


async def scrape_govplanet_sold(max_pages: int = 5) -> List[Dict[str, Any]]:
    """Scrape GovPlanet sold items and return competitor_sales rows."""
    raw_records = await fetch_govplanet_sold(max_pages=max_pages)
    rows: List[Dict[str, Any]] = []
    for record in raw_records:
        row = normalize_govplanet_record(record)
        if row is not None:
            rows.append(row)
    logger.info("[%s] normalized %d/%d records", SOURCE, len(rows), len(raw_records))
    return rows
