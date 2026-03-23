"""
GovDeals ACTIVE Listings Scraper — Opportunities for deal hunting.

Strategy:
1. Load GovDeals with ?timing=current in Playwright
2. Intercept requests to maestro.lqdt1.com to capture x-api-key
3. Call search API with timing: 'current' to get active auctions
4. Filter using passes() logic (bid range, year, rust states)
5. Write to Supabase opportunities table
6. Run DOS scoring on each inserted record
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

MIN_BID = 500
MAX_BID = 75000

HIGH_RUST_STATES = {
    "OH", "MI", "PA", "NY", "WI", "MN", "IL", "IN", "MO", "IA",
    "ND", "SD", "NE", "KS", "WV", "ME", "NH", "VT", "MA", "RI",
    "CT", "NJ", "MD", "DE",
}


def passes(lot: dict) -> bool:
    """Filter logic matching the Apify actor."""
    bid = (
        lot.get("currentBid")
        or lot.get("current_bid")
        or lot.get("assetBidPrice")
        or 0
    )
    if bid < MIN_BID or bid > MAX_BID:
        return False

    year = int(lot.get("modelYear") or lot.get("year") or 0)
    current_year = datetime.now().year
    if year and (current_year - year) > 12:
        return False

    state = (lot.get("locationState") or lot.get("state") or "").upper()
    if state in HIGH_RUST_STATES:
        # Only allow rust belt if vehicle is <= 2 years old
        if not (year and year >= current_year - 2):
            return False
        logger.info(f"[BYPASS] Rust state {state} allowed — vehicle is {year} (<=3yr old)")

    return True


def extract_vin_from_lot(lot: dict) -> str | None:
    """Extract VIN from lot JSON fields."""
    vin = lot.get("vin") or ""
    if VIN_PATTERN.match(vin):
        return vin.upper()

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


def normalize_lot(lot: dict) -> dict:
    """Normalize API lot to opportunities schema."""
    current_bid = (
        lot.get("currentBid")
        or lot.get("current_bid")
        or lot.get("assetBidPrice")
        or 0
    )
    asset_id = lot.get("assetId", "")
    account_id = lot.get("accountId", "")

    # Resolve MMR from available fields
    mmr = float(
        lot.get("estimated_sale_price") or
        lot.get("manheim_mmr_mid") or
        lot.get("retail_value") or
        lot.get("mmr_mid") or
        0
    )

    return {
        "title": lot.get("assetShortDescription") or lot.get("title") or "",
        "make": lot.get("makebrand") or lot.get("make") or "",
        "model": lot.get("model") or "",
        "year": lot.get("modelYear") or lot.get("year"),
        "current_bid": current_bid,
        "state": lot.get("locationState") or lot.get("state") or "",
        "city": lot.get("locationCity") or lot.get("city") or "",
        "auction_end_time": lot.get("assetAuctionEndDateUtc") or lot.get("auctionEndUtc"),
        "listing_url": lot.get("url") or f"https://www.govdeals.com/asset/{asset_id}/{account_id}",
        "photo_url": lot.get("imageUrl") or "",
        "vin": extract_vin_from_lot(lot),
        "mileage": lot.get("meterCount"),
        "source_site": "govdeals",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        # Preserve MMR fields for scoring
        "estimated_sale_price": mmr if mmr > 0 else None,
        "manheim_mmr_mid": lot.get("manheim_mmr_mid"),
        "retail_value": lot.get("retail_value"),
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
            logger.info(f"[GOVDEALS-ACTIVE] Captured x-api-key: {captured['api_key'][:20]}...")

    page.on("request", on_request)

    # Load homepage first to init Angular
    await page.goto("https://www.govdeals.com/", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(3)

    # Navigate to active vehicles to trigger API calls
    await page.goto(
        "https://www.govdeals.com/vehicles?timing=current",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    await asyncio.sleep(5)

    return captured["api_key"], captured["headers"]


async def fetch_active_auctions(api_key: str, headers: dict) -> list[dict]:
    """Paginate through active auctions API."""
    all_lots = []
    search_url = "https://maestro.lqdt1.com/search/list"

    async with httpx.AsyncClient(timeout=30) as client:
        for page_num in range(1, MAX_PAGES + 1):
            payload = {
                "pageSize": PAGE_SIZE,
                "pageNumber": page_num,
                "timing": "current",  # active listings
                "categories": [{"name": "Automobiles & Trucks"}],
            }

            try:
                resp = await client.post(search_url, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"[GOVDEALS-ACTIVE] Page {page_num} returned {resp.status_code}")
                    break

                data = resp.json()

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
                    logger.info(f"[GOVDEALS-ACTIVE] Page {page_num} empty — done")
                    break

                logger.info(f"[GOVDEALS-ACTIVE] Page {page_num}: {len(lots)} lots")
                all_lots.extend(lots)

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"[GOVDEALS-ACTIVE] Page {page_num} failed: {e}")
                break

    return all_lots


async def write_to_supabase(records: list[dict]) -> int:
    """Write records to opportunities table via Supabase, then score each.

    Returns the count of records that passed DOS scoring (>= 50).
    """
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        logger.error("[GOVDEALS-ACTIVE] Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        return 0

    client = create_client(url, key)

    valid_records = [
        r for r in records
        if r.get("make") or r.get("model") or r.get("vin")
    ]

    if not valid_records:
        logger.info("[GOVDEALS-ACTIVE] No valid records to insert")
        return 0

    try:
        result = client.table("opportunities").upsert(
            valid_records,
            on_conflict="listing_url",
            ignore_duplicates=False,
        ).execute()
        upserted = len(result.data) if result.data else 0
        logger.info(f"[GOVDEALS-ACTIVE] Upserted {upserted} records to opportunities")

        # Run DOS scoring on inserted records — updates DB with scores,
        # deletes records with DOS < 50, alerts for DOS >= 80
        kept = await run_scoring(result.data or [], client)

        return kept
    except Exception as e:
        logger.error(f"[GOVDEALS-ACTIVE] Supabase upsert failed: {e}")
        return 0


async def run_scoring(records: list[dict], supabase_client) -> int:
    """Run DOS scoring on inserted records, update DB, filter low scores, alert hot deals.

    Returns the count of records that passed the DOS threshold (>= 50).
    """
    try:
        from backend.ingest.score import score_deal
    except ImportError:
        logger.warning("[GOVDEALS-ACTIVE] Could not import score_deal — skipping scoring")
        return len(records)

    MIN_DOS_THRESHOLD = 50
    HOT_DEAL_THRESHOLD = 80

    scored = 0
    kept = 0
    hot_deals = []

    for record in records:
        listing_url = record.get("listing_url")
        try:
            bid = record.get("current_bid") or 0
            state = record.get("state") or ""
            model = record.get("model") or ""
            make = record.get("make") or ""
            year = record.get("year")
            mileage = record.get("mileage")

            # Get MMR from vehicle data (estimated_sale_price first, then manheim, then retail)
            mmr = float(
                record.get("estimated_sale_price") or
                record.get("manheim_mmr_mid") or
                record.get("retail_value") or
                record.get("mmr_mid") or
                0
            )
            auction_end = record.get("auction_end_date") or record.get("auction_end_time") or record.get("auction_end")

            # score_deal returns a dict with dos_score and breakdown
            result = score_deal(
                bid=bid,
                mmr_ca=mmr,
                state=state,
                source_site="govdeals",
                model=model,
                make=make,
                year=year,
                mileage=mileage,
                auction_end=auction_end,
                manheim_mmr_mid=record.get("manheim_mmr_mid"),
            )

            dos_score = result.get("dos_score") if result else None

            if dos_score is None:
                logger.warning(f"[GOVDEALS-ACTIVE] No dos_score for {listing_url}")
                continue

            scored += 1
            logger.debug(f"[GOVDEALS-ACTIVE] Scored {listing_url}: DOS={dos_score}")

            if dos_score < MIN_DOS_THRESHOLD:
                # Delete low-scoring records
                try:
                    supabase_client.table("opportunities").delete().eq(
                        "listing_url", listing_url
                    ).execute()
                    logger.info(f"[GOVDEALS-ACTIVE] Deleted low-score record DOS={dos_score}: {listing_url}")
                except Exception as del_err:
                    logger.warning(f"[GOVDEALS-ACTIVE] Failed to delete low-score record: {del_err}")
                continue

            # Update the record with dos_score
            try:
                supabase_client.table("opportunities").update({
                    "dos_score": dos_score,
                    "total_cost": result.get("total_cost"),
                    "gross_margin": result.get("gross_margin"),
                    "investment_grade": result.get("investment_grade"),
                }).eq("listing_url", listing_url).execute()
                kept += 1
            except Exception as upd_err:
                logger.warning(f"[GOVDEALS-ACTIVE] Failed to update dos_score for {listing_url}: {upd_err}")
                continue

            # Collect hot deals for alerting
            if dos_score >= HOT_DEAL_THRESHOLD:
                record["dos_score"] = dos_score
                record["total_cost"] = result.get("total_cost")
                record["gross_margin"] = result.get("gross_margin")
                record["investment_grade"] = result.get("investment_grade")
                hot_deals.append(record)

        except Exception as e:
            logger.warning(f"[GOVDEALS-ACTIVE] Scoring failed for {listing_url}: {e}")

    logger.info(f"[GOVDEALS-ACTIVE] Scored {scored}/{len(records)}, kept {kept} (DOS>={MIN_DOS_THRESHOLD})")

    # Send alerts for hot deals
    if hot_deals:
        await send_hot_deal_alerts(hot_deals)

    return kept


async def send_hot_deal_alerts(hot_deals: list[dict]):
    """Send Telegram alerts for hot deals (DOS >= 80)."""
    try:
        from webapp.routers.ingest import send_telegram_alert
        for deal in hot_deals:
            try:
                await send_telegram_alert(deal)
                logger.info(f"[GOVDEALS-ACTIVE] Alert sent for DOS={deal.get('dos_score')}: {deal.get('listing_url')}")
            except Exception as alert_err:
                logger.warning(f"[GOVDEALS-ACTIVE] Alert failed for {deal.get('listing_url')}: {alert_err}")
    except ImportError:
        logger.warning("[GOVDEALS-ACTIVE] Could not import send_telegram_alert — skipping alerts")


async def run_govdeals_active_scraper():
    """Main scraper entry point."""
    logger.info("[GOVDEALS-ACTIVE] Starting active listings scraper")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        try:
            api_key, headers = await capture_api_key(page)

            if not api_key:
                logger.error("[GOVDEALS-ACTIVE] Failed to capture API key")
                return 0

            lots = await fetch_active_auctions(api_key, headers)
            logger.info(f"[GOVDEALS-ACTIVE] Fetched {len(lots)} active auctions")

            if not lots:
                return 0

            # Filter using passes() logic
            passing_lots = [lot for lot in lots if passes(lot)]
            logger.info(f"[GOVDEALS-ACTIVE] {len(passing_lots)}/{len(lots)} lots passed filters")

            records = [normalize_lot(lot) for lot in passing_lots]
            inserted = await write_to_supabase(records)

            logger.info(f"[GOVDEALS-ACTIVE] Complete: {inserted} records written to opportunities")
            return inserted

        finally:
            await browser.close()


def run_govdeals_active_scraper_sync():
    """Synchronous wrapper for scheduler compatibility."""
    return asyncio.run(run_govdeals_active_scraper())
