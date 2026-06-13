"""GovDeals completed-auction scraper -> competitor_sales rows.

Reuses the proven maestro API-key interception flow from
``backend.scrapers.govdeals_sold`` and normalizes lots into the competitor_sales
schema (instead of dealer_sales).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.scrapers.competitor_sales.base import (
    build_competitor_sale_row,
    extract_vin,
)

logger = logging.getLogger(__name__)

SOURCE = "govdeals"


def _condition_notes(lot: Dict[str, Any]) -> Optional[str]:
    for key in ("assetShortDescription", "longDescription", "itemDescription", "description", "notes"):
        value = lot.get(key)
        if value:
            return str(value)[:1000]
    return None


def normalize_govdeals_lot(lot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a GovDeals completed-auction lot into a competitor_sales row."""
    sold_price = (
        lot.get("winningBid")
        or lot.get("soldPrice")
        or lot.get("assetWinningBid")
        or lot.get("closingBid")
        or lot.get("awardAmount")
    )
    asset_id = lot.get("assetId", "")
    account_id = lot.get("accountId", "")
    listing_url = lot.get("url") or f"https://www.govdeals.com/asset/{asset_id}/{account_id}"
    city = lot.get("locationCity") or lot.get("city") or ""
    state = lot.get("locationState") or lot.get("state") or ""
    location = ", ".join(part for part in (city, state) if part) or None

    return build_competitor_sale_row(
        source=SOURCE,
        source_listing_id=str(asset_id) or None,
        listing_url=listing_url,
        vin=extract_vin(
            lot.get("vin"),
            lot.get("assetShortDescription"),
            lot.get("longDescription"),
            lot.get("itemDescription"),
            lot.get("description"),
        ),
        year=lot.get("modelYear") or lot.get("year"),
        make=lot.get("makebrand") or lot.get("make"),
        model=lot.get("model"),
        mileage=lot.get("meterCount"),
        sale_price=sold_price,
        auction_end_date=lot.get("assetAuctionEndDateUtc") or lot.get("auctionEndUtc"),
        condition_notes=_condition_notes(lot),
        location=location,
        state=state,
        raw=lot,
    )


async def scrape_govdeals_sold(max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    """Scrape GovDeals completed auctions and return competitor_sales rows."""
    from playwright.async_api import async_playwright

    from backend.scrapers import govdeals_sold

    if max_pages is not None:
        govdeals_sold.MAX_PAGES = max_pages

    rows: List[Dict[str, Any]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        try:
            api_key, headers = await govdeals_sold.capture_api_key(page)
            if not api_key:
                logger.error("[%s] failed to capture API key", SOURCE)
                return rows
            lots = await govdeals_sold.fetch_completed_auctions(api_key, headers)
            logger.info("[%s] fetched %d completed lots", SOURCE, len(lots))
            for lot in lots:
                row = normalize_govdeals_lot(lot)
                if row is not None:
                    rows.append(row)
        finally:
            await browser.close()
    return rows
