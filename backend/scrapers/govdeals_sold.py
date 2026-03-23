"""
GovDeals COMPLETED Auctions Scraper — Sold prices for DOS calibration.

Strategy:
1. Load GovDeals with ?timing=completed in Playwright
2. Intercept requests to maestro.lqdt1.com to capture x-api-key
3. Call search API with timing: 'completed' to get closed auctions
4. Write to Supabase dealer_sales table
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timezone

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

VIN_PATTERN = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)
MAX_PAGES = 10
PAGE_SIZE = 50


def extract_vin_from_lot(lot: dict) -> str | None:
    """Extract VIN from lot JSON fields."""
    # Check explicit vin field
    vin = lot.get("vin") or ""
    if VIN_PATTERN.match(vin):
        return vin.upper()

    # Regex over text fields
    text_fields = " ".join(
        str(lot.get(f) or "")
        for f in [
            "assetShortDescription",
            "longDescription",
            "itemDescription",
            "description",
            "notes",
            "assetLongDescription",
        ]
    )
    match = VIN_PATTERN.search(text_fields)
    return match.group(1).upper() if match else None


def normalize_lot(lot: dict) -> dict | None:
    """Normalize API lot to dealer_sales schema. Returns None if required data missing."""
    sold_price = (
        lot.get("winningBid")
        or lot.get("soldPrice")
        or lot.get("assetWinningBid")
        or lot.get("closingBid")
        or lot.get("awardAmount")
        or None
    )
    if sold_price is None:
        return None  # Skip records without sold price

    year = lot.get("modelYear") or lot.get("year")
    if not year or int(year) == 0:
        return None  # Skip records without valid year

    asset_id = lot.get("assetId", "")
    account_id = lot.get("accountId", "")

    return {
        "make": lot.get("makebrand") or lot.get("make") or "",
        "model": lot.get("model") or "",
        "year": int(year),
        "mileage": lot.get("meterCount"),
        "state": lot.get("locationState") or lot.get("state") or "",
        "city": lot.get("locationCity") or lot.get("city") or "",
        "vin": extract_vin_from_lot(lot),
        "sale_price": sold_price,
        "sold_price": sold_price,
        "listing_url": lot.get("url") or f"https://www.govdeals.com/asset/{asset_id}/{account_id}",
        "auction_end_date": lot.get("assetAuctionEndDateUtc") or lot.get("auctionEndUtc"),
        "source_type": "govdeals_sold",
        "source": "govdeals_sold",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


async def capture_api_key(page) -> tuple[str | None, dict | None]:
    """Intercept requests to maestro.lqdt1.com and capture the x-api-key."""
    captured = {"api_key": None, "headers": None}

    def on_request(request):
        url = request.url
        if "maestro.lqdt1.com" not in url:
            return
        headers = request.headers
        if not captured["api_key"] and headers.get("x-api-key"):
            captured["api_key"] = headers["x-api-key"]
            captured["headers"] = {
                "accept": headers.get("accept", "application/json, text/plain, */*"),
                "content-type": headers.get("content-type", "application/json"),
                "x-api-key": headers["x-api-key"],
                "origin": "https://www.govdeals.com",
                "referer": "https://www.govdeals.com/",
            }
            logger.info(f"[GOVDEALS] Captured x-api-key: {captured['api_key'][:20]}...")

    page.on("request", on_request)

    # Load homepage first to init Angular
    await page.goto("https://www.govdeals.com/", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(3)

    # Navigate to completed vehicles to trigger API calls
    await page.goto(
        "https://www.govdeals.com/vehicles?timing=completed",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    await asyncio.sleep(5)

    return captured["api_key"], captured["headers"]


async def fetch_completed_auctions(api_key: str, headers: dict) -> list[dict]:
    """Paginate through completed auctions API."""
    all_lots = []
    search_url = "https://maestro.lqdt1.com/search/list"

    async with httpx.AsyncClient(timeout=30) as client:
        for page_num in range(1, MAX_PAGES + 1):
            payload = {
                "pageSize": PAGE_SIZE,
                "pageNumber": page_num,
                "timing": "completed",
                "categories": [{"name": "Automobiles & Trucks"}],
            }

            try:
                resp = await client.post(search_url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"[GOVDEALS] Page {page_num} returned {resp.status_code}")
                    break

                data = resp.json()

                # Extract lots from various API shapes
                lots = (
                    data.get("assetSearchResults")
                    or data.get("assets")
                    or data.get("lots")
                    or data.get("items")
                    or data.get("results")
                    or data.get("data", {}).get("assets")
                    or data.get("data", {}).get("lots")
                    or []
                )

                if not lots:
                    logger.info(f"[GOVDEALS] Page {page_num} empty — done")
                    break

                logger.info(f"[GOVDEALS] Page {page_num}: {len(lots)} lots")
                all_lots.extend(lots)

                # Rate limit
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"[GOVDEALS] Page {page_num} failed: {e}")
                break

    return all_lots


async def write_to_supabase(records: list[dict]) -> int:
    """Write records to dealer_sales table via Supabase."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        logger.error("[GOVDEALS] Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        return 0

    client = create_client(url, key)

    # Filter to records with essential data
    valid_records = [
        r
        for r in records
        if r.get("make") or r.get("model") or r.get("vin") or r.get("listing_url")
    ]

    if not valid_records:
        logger.info("[GOVDEALS] No valid records to insert")
        return 0

    # Upsert to handle duplicates (based on vin + source if vin exists)
    try:
        result = client.table("dealer_sales").upsert(
            valid_records,
            on_conflict="vin,source",
            ignore_duplicates=True,
        ).execute()
        inserted = len(result.data) if result.data else 0
        logger.info(f"[GOVDEALS] Upserted {inserted} records to dealer_sales")
        return inserted
    except Exception as e:
        logger.error(f"[GOVDEALS] Supabase upsert failed: {e}")
        # Fallback: insert without conflict handling
        try:
            result = client.table("dealer_sales").insert(valid_records).execute()
            inserted = len(result.data) if result.data else 0
            logger.info(f"[GOVDEALS] Inserted {inserted} records to dealer_sales (fallback)")
            return inserted
        except Exception as e2:
            logger.error(f"[GOVDEALS] Supabase insert fallback failed: {e2}")
            return 0


async def run_govdeals_sold_scraper():
    """Main scraper entry point."""
    logger.info("[GOVDEALS-SOLD] Starting completed auctions scraper")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        try:
            api_key, headers = await capture_api_key(page)

            if not api_key:
                logger.error("[GOVDEALS-SOLD] Failed to capture API key")
                return 0

            lots = await fetch_completed_auctions(api_key, headers)
            logger.info(f"[GOVDEALS-SOLD] Fetched {len(lots)} completed auctions")

            if not lots:
                return 0

            records = [r for r in (normalize_lot(lot) for lot in lots) if r is not None]
            inserted = await write_to_supabase(records)

            logger.info(f"[GOVDEALS-SOLD] Complete: {inserted} records written to dealer_sales")
            return inserted

        finally:
            await browser.close()


def run_govdeals_sold_scraper_sync():
    """Synchronous wrapper for scheduler compatibility."""
    return asyncio.run(run_govdeals_sold_scraper())
