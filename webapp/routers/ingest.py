from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
import re
import os
import logging
from datetime import datetime

from supabase import create_client

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.getenv("APIFY_WEBHOOK_SECRET", "sbEC0dNgb7Ohg3rDV")

_supabase_url = os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

if _supabase_url and _supabase_key:
    supabase_client = create_client(_supabase_url, _supabase_key)
    logger.info("Supabase client initialized for ingest")
else:
    supabase_client = None
    logger.warning("Supabase client NOT initialized — missing VITE_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. Deals will be logged but not saved.")

# Rust state classification
LOW_RUST_STATES = {"AZ","CA","NV","CO","NM","UT","TX","FL","GA","SC","TN","NC","VA","WA","OR","HI","OK","AR","LA","MS","AL"}
HIGH_RUST_STATES = {"OH","MI","PA","NY","WI","MN","IL","IN","MO","IA","ND","SD","NE","KS","WV","ME","NH","VT","MA","RI","CT","NJ","MD","DE"}


@router.post("/apify")
async def apify_webhook(request: Request, x_apify_webhook_secret: Optional[str] = Header(None)):
    # Verify webhook secret
    if x_apify_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = await request.json()

    # Extract dataset items from Apify webhook payload
    dataset_id = payload.get("resource", {}).get("defaultDatasetId")
    if not dataset_id:
        return {"status": "ok", "message": "No dataset to process"}

    # Fetch dataset items from Apify API
    import httpx
    apify_token = os.getenv("APIFY_API_TOKEN", "")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            params={"token": apify_token, "format": "json"}
        )
        items = resp.json()

    processed = 0
    hot_deals = []

    for item in items:
        # Normalize the vehicle data
        vehicle = normalize_apify_vehicle(item)
        if vehicle is None:
            continue

        # Run basic gate checks
        if not passes_basic_gates(vehicle):
            continue

        # Calculate DOS score
        score = calculate_dos_score(vehicle)
        vehicle["dos_score"] = score
        vehicle["ingested_at"] = datetime.utcnow().isoformat()

        await save_opportunity_to_supabase(vehicle)
        print(f"[INGEST] {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')} | Score: {score} | Bid: ${vehicle.get('current_bid')}")

        processed += 1
        if score >= 80:
            hot_deals.append(vehicle)

    return {
        "status": "ok",
        "processed": processed,
        "hot_deals": len(hot_deals),
        "hot_deal_vehicles": [f"{v.get('year')} {v.get('make')} {v.get('model')}" for v in hot_deals]
    }


def normalize_apify_vehicle(item: dict) -> Optional[dict]:
    """Normalize raw Apify scraper output to DealerScope vehicle format"""
    try:
        title = item.get("title", "")
        state = item.get("state", "")

        # Skip high rust states
        if state.upper() in HIGH_RUST_STATES:
            return None

        return {
            "title": title,
            "current_bid": float(item.get("current_bid", 0)),
            "buyer_premium": float(item.get("buyer_premium", 0.125)),
            "doc_fee": float(item.get("doc_fee", 75)),
            "state": state.upper(),
            "location": item.get("location", ""),
            "auction_end_time": item.get("auction_end_time"),
            "listing_url": item.get("listing_url", ""),
            "source_site": item.get("source_site", "govdeals"),
            "photo_url": item.get("photo_url"),
            "agency_name": item.get("agency_name", ""),
            "year": extract_year(title),
            "make": extract_make(title),
            "model": extract_model(title),
        }
    except Exception as e:
        print(f"[INGEST] Normalize error: {e}")
        return None


def extract_year(title: str) -> Optional[int]:
    match = re.search(r"\b(19|20)\d{2}\b", title)
    return int(match.group()) if match else None


def extract_make(title: str) -> str:
    makes = [
        "Ford", "Chevrolet", "Chevy", "Toyota", "Ram", "Dodge", "GMC", "Honda", "Jeep",
        "Nissan", "Hyundai", "Kia", "Subaru", "Volkswagen", "BMW", "Mercedes", "Lexus",
        "Cadillac", "Buick", "Lincoln", "Tesla", "Rivian", "Lucid",
    ]
    title_upper = title.upper()
    for make in makes:
        if make.upper() in title_upper:
            return make
    return ""


def extract_model(title: str) -> str:
    # Extract word after make as rough model estimate
    return ""  # TODO: improve with regex per make


def passes_basic_gates(vehicle: dict) -> bool:
    """Quick pre-filter before full ML scoring"""
    bid = vehicle.get("current_bid", 0)
    state = vehicle.get("state", "")

    if bid < 500 or bid > 40000:
        return False
    if state in HIGH_RUST_STATES:
        return False
    if not vehicle.get("year"):
        return False

    current_year = datetime.now().year
    age = current_year - vehicle["year"]
    if age > 8 or age < 0:
        return False

    return True


def calculate_dos_score(vehicle: dict) -> float:
    """Simplified DOS score for ingested vehicles (full ML scoring happens in frontend)"""
    score = 50.0  # Base score

    state = vehicle.get("state", "")
    if state in LOW_RUST_STATES:
        score += 10

    bid = vehicle.get("current_bid", 0)
    if bid < 10000:
        score += 8  # Sub-$10k high velocity segment

    make = vehicle.get("make", "").upper()
    tier1 = {"FORD", "TOYOTA", "RAM", "CHEVROLET", "CHEVY", "GMC", "HONDA", "NISSAN", "TESLA"}
    if make in tier1:
        score += 15

    year = vehicle.get("year", 2000)
    age = datetime.now().year - year
    if 1 <= age <= 4:
        score += 12
    elif age <= 6:
        score += 6

    return min(100, round(score, 1))


async def save_opportunity_to_supabase(vehicle: dict) -> bool:
    """Save a scored vehicle to the Supabase opportunities table.

    Only saves if dos_score >= 50. Upserts on listing_url.
    """
    if supabase_client is None:
        logger.warning(f"[INGEST] Supabase not configured — skipping save for {vehicle.get('title')}")
        return False

    score = vehicle.get("dos_score", 0)
    if score < 50:
        logging.info(f"[INGEST] Skipping weak deal (score={score}): {vehicle.get('listing_url')}")
        return False

    if score >= 80:
        status = "hot"
    elif score >= 65:
        status = "good"
    else:
        status = "moderate"

    row = {
        "listing_url": vehicle.get("listing_url", ""),
        "acquisition_cost": vehicle.get("current_bid"),
        "score": score,
        "source_site": vehicle.get("source_site"),
        "state": vehicle.get("state"),
        "location": vehicle.get("location"),
        "photo_url": vehicle.get("photo_url"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "year": vehicle.get("year"),
        "auction_end": vehicle.get("auction_end_time"),
        "status": status,
    }

    try:
        supabase_client.table("opportunities").upsert(
            row, on_conflict="listing_url"
        ).execute()
        logging.info(
            f"[INGEST] Saved to Supabase: {vehicle.get('year')} {vehicle.get('make')} "
            f"{vehicle.get('model')} | score={score} | status={status}"
        )
        return True
    except Exception as e:
        logging.error(f"[INGEST] Supabase save failed for {vehicle.get('listing_url')}: {e}")
        return False
