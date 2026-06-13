"""PublicSurplus completed-auction scraper -> competitor_sales rows.

PublicSurplus exposes closed auctions through its browse interface. Network
fetching is best-effort and robots/rate-limit aware; the pure normalizer
(``normalize_publicsurplus_record``) carries the logic that is unit-tested.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.scrapers.competitor_sales.base import (
    DEFAULT_USER_AGENT,
    RateLimiter,
    build_competitor_sale_row,
    extract_vin,
    robots_allows,
)

logger = logging.getLogger(__name__)

SOURCE = "publicsurplus"
BASE_URL = "https://www.publicsurplus.com"
# category 4 == "Cars/Trucks/Vehicles" on PublicSurplus.
COMPLETED_SEARCH_URL = (
    BASE_URL + "/sms/all,az/browse/cat?catid=4&slth=closed&page={page}"
)

_YEAR_MAKE_MODEL = re.compile(r"\b(19[8-9]\d|20[0-4]\d)\s+([A-Za-z][\w-]+)\s+([\w\-/]+)")


def _parse_year_make_model(title: str) -> Dict[str, Optional[str]]:
    match = _YEAR_MAKE_MODEL.search(title or "")
    if not match:
        return {"year": None, "make": None, "model": None}
    return {"year": match.group(1), "make": match.group(2), "model": match.group(3)}


def normalize_publicsurplus_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a PublicSurplus closed-auction record into a competitor_sales row.

    ``record`` is a dict with keys like ``auction_id``, ``title``, ``winning_bid``,
    ``end_date``, ``location``, ``make``, ``model``, ``year``, ``mileage``, ``vin``.
    Falls back to parsing year/make/model out of the title when not provided.
    """
    title = record.get("title") or ""
    parsed = _parse_year_make_model(title)
    auction_id = record.get("auction_id") or record.get("auctionId")
    listing_url = record.get("listing_url") or (
        f"{BASE_URL}/sms/all,az/auction/view?auc={auction_id}" if auction_id else BASE_URL
    )

    return build_competitor_sale_row(
        source=SOURCE,
        source_listing_id=str(auction_id) if auction_id else None,
        listing_url=listing_url,
        vin=record.get("vin") or extract_vin(title, record.get("description")),
        year=record.get("year") or parsed["year"],
        make=record.get("make") or parsed["make"],
        model=record.get("model") or parsed["model"],
        mileage=record.get("mileage"),
        sale_price=record.get("winning_bid") or record.get("sale_price"),
        auction_end_date=record.get("end_date") or record.get("auction_end_date"),
        condition_notes=record.get("description"),
        location=record.get("location"),
        state=record.get("state"),
        raw=record,
    )


async def fetch_publicsurplus_closed(max_pages: int = 5) -> List[Dict[str, Any]]:
    """Best-effort fetch of PublicSurplus closed vehicle auctions (raw records)."""
    import httpx

    if not robots_allows(COMPLETED_SEARCH_URL.format(page=0)):
        logger.warning("[%s] robots.txt disallows browse path; skipping", SOURCE)
        return []

    limiter = RateLimiter(min_interval=2.0)
    records: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": DEFAULT_USER_AGENT}
    ) as client:
        for page in range(max_pages):
            limiter.wait()
            url = COMPLETED_SEARCH_URL.format(page=page)
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning("[%s] page %d -> %d", SOURCE, page, resp.status_code)
                    break
                page_records = _parse_listing_html(resp.text)
                if not page_records:
                    break
                records.extend(page_records)
            except Exception as exc:  # pragma: no cover - network path
                logger.error("[%s] page %d failed: %s", SOURCE, page, exc)
                break
    return records


def _parse_listing_html(html: str) -> List[Dict[str, Any]]:
    """Parse a PublicSurplus closed-auction results page into raw records."""
    try:
        from bs4 import BeautifulSoup
    except Exception:  # pragma: no cover
        return []

    soup = BeautifulSoup(html, "html.parser")
    records: List[Dict[str, Any]] = []
    for row in soup.select("tr.auction, div.auctionListItem"):
        link = row.find("a", href=True)
        if not link:
            continue
        href = link["href"]
        auction_id = None
        match = re.search(r"auc=(\d+)", href)
        if match:
            auction_id = match.group(1)
        price_text = ""
        price_el = row.find(string=re.compile(r"Winning Bid|Sold|Final", re.IGNORECASE))
        if price_el and price_el.parent:
            price_text = price_el.parent.get_text(" ", strip=True)
        price_match = re.search(r"\$[\d,]+(?:\.\d{2})?", price_text)
        records.append(
            {
                "auction_id": auction_id,
                "title": link.get_text(" ", strip=True),
                "listing_url": href if href.startswith("http") else f"{BASE_URL}{href}",
                "winning_bid": price_match.group(0) if price_match else None,
            }
        )
    return records


async def scrape_publicsurplus_sold(max_pages: int = 5) -> List[Dict[str, Any]]:
    """Scrape PublicSurplus closed auctions and return competitor_sales rows."""
    raw_records = await fetch_publicsurplus_closed(max_pages=max_pages)
    rows: List[Dict[str, Any]] = []
    for record in raw_records:
        row = normalize_publicsurplus_record(record)
        if row is not None:
            rows.append(row)
    logger.info("[%s] normalized %d/%d records", SOURCE, len(rows), len(raw_records))
    return rows
