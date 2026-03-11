"""
Apify webhook ingest router.
Normalizes, gates, scores, and saves vehicle listings to Supabase.

Fixes applied (2026-03-11):
- Real DOS formula via backend.ingest.score.score_deal()
- MMR estimates by segment (placeholder until Manheim API is live)
- extract_model() now uses regex
- Age gate tightened to 4 years (SOP compliance)
- Mileage gate added (50k max)
- Bid range tightened ($3k-$35k)
- APIFY_TOKEN sent via Authorization header (not query param)
- 500 errors genericized (no internal details leaked)
- Telegram hot deal alerts wired
- Dataset ID format validated before fetch
"""
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
import re
import os
import logging
from datetime import datetime

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.getenv("APIFY_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8770839167:AAEPvbNtS5Fr3LPmoEUM-9CJ14r7OXhIgzI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7529788084")

_supabase_url = os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

supabase_client = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        supabase_client = create_client(_supabase_url, _supabase_key)
        logger.info("Supabase client initialized for ingest")
    else:
        logger.warning("Supabase client NOT initialized — missing env vars.")
except Exception as _supa_err:
    logger.warning(f"Supabase client init failed (non-fatal): {_supa_err}")

# State classification
LOW_RUST_STATES = {
    "AZ","CA","NV","CO","NM","UT","TX","FL","GA","SC","TN","NC","VA","WA","OR","HI",
    "OK","AR","LA","MS","AL"
}
HIGH_RUST_STATES = {
    "OH","MI","PA","NY","WI","MN","IL","IN","MO","IA","ND","SD","NE","KS","WV",
    "ME","NH","VT","MA","RI","CT","NJ","MD","DE"
}

# MMR estimates by segment — placeholder until Manheim API is live
# Based on 2024-2026 wholesale market averages
_SEGMENT_MMR = {
    "truck":        28000,
    "suv_large":    26000,
    "suv_mid":      22000,
    "luxury":       24000,
    "ev_trending":  25000,
    "sedan_popular":18000,
    "ev_other":     16000,
    "sedan_other":  15000,
    "coupe":        14000,
    "minivan":      13000,
}

# Make → rough segment for MMR lookup
_MAKE_SEGMENT = {
    "ford": "truck", "gmc": "truck", "ram": "truck", "chevrolet": "truck", "chevy": "truck",
    "toyota": "suv_mid", "honda": "suv_mid", "nissan": "sedan_popular",
    "hyundai": "sedan_popular", "kia": "sedan_popular", "subaru": "suv_mid",
    "jeep": "suv_mid", "dodge": "sedan_other",
    "bmw": "luxury", "mercedes": "luxury", "lexus": "luxury",
    "cadillac": "luxury", "lincoln": "luxury", "audi": "luxury",
    "tesla": "ev_trending", "rivian": "ev_trending",
    "volkswagen": "sedan_other", "buick": "sedan_other",
}

KNOWN_MAKES = [
    "Ford","Chevrolet","Chevy","Toyota","Ram","Dodge","GMC","Honda","Jeep",
    "Nissan","Hyundai","Kia","Subaru","Volkswagen","BMW","Mercedes","Lexus",
    "Cadillac","Buick","Lincoln","Tesla","Rivian","Lucid","Mazda","Mitsubishi",
    "Chrysler","Acura","Infiniti","Genesis","Volvo","Land Rover","Audi","Porsche",
]

# Model patterns: (make_lower, regex_pattern, canonical_model)
_MODEL_PATTERNS = [
    ("ford",     r"\bF[-\s]?150\b",      "F-150"),
    ("ford",     r"\bF[-\s]?250\b",      "F-250"),
    ("ford",     r"\bF[-\s]?350\b",      "F-350"),
    ("ford",     r"\bExplorer\b",        "Explorer"),
    ("ford",     r"\bEscape\b",          "Escape"),
    ("ford",     r"\bEdge\b",            "Edge"),
    ("ford",     r"\bMaverick\b",        "Maverick"),
    ("chevrolet",r"\bSilverado\b",       "Silverado 1500"),
    ("chevrolet",r"\bEquinox\b",         "Equinox"),
    ("chevrolet",r"\bColorado\b",        "Colorado"),
    ("chevrolet",r"\bTraverse\b",        "Traverse"),
    ("chevy",    r"\bSilverado\b",       "Silverado 1500"),
    ("toyota",   r"\bTacoma\b",          "Tacoma"),
    ("toyota",   r"\bRAV[-\s]?4\b",      "RAV4"),
    ("toyota",   r"\bCamry\b",           "Camry"),
    ("toyota",   r"\bCorolla\b",         "Corolla"),
    ("toyota",   r"\bHighlander\b",      "Highlander"),
    ("toyota",   r"\bTundra\b",          "Tundra"),
    ("honda",    r"\bCR[-\s]?V\b",       "CR-V"),
    ("honda",    r"\bAccord\b",          "Accord"),
    ("honda",    r"\bCivic\b",           "Civic"),
    ("honda",    r"\bPilot\b",           "Pilot"),
    ("honda",    r"\bOdyssey\b",         "Odyssey"),
    ("nissan",   r"\bRogue\b",           "Rogue"),
    ("nissan",   r"\bAltima\b",          "Altima"),
    ("nissan",   r"\bFrontier\b",        "Frontier"),
    ("nissan",   r"\bTitan\b",           "Titan"),
    ("ram",      r"\b1500\b",            "Ram 1500"),
    ("ram",      r"\b2500\b",            "Ram 2500"),
    ("jeep",     r"\bGrand\s+Cherokee\b","Grand Cherokee"),
    ("jeep",     r"\bWrangler\b",        "Wrangler"),
    ("jeep",     r"\bGladiator\b",       "Gladiator"),
    ("gmc",      r"\bSierra\b",          "Sierra 1500"),
    ("gmc",      r"\bTerrain\b",         "Terrain"),
    ("tesla",    r"\bModel\s*[Yy]\b",    "Tesla Model Y"),
    ("tesla",    r"\bModel\s*[3Tt]\b",   "Tesla Model 3"),
    ("tesla",    r"\bModel\s*[Ss]\b",    "Tesla Model S"),
    ("subaru",   r"\bOutback\b",         "Outback"),
    ("subaru",   r"\bForester\b",        "Forester"),
    ("hyundai",  r"\bTucson\b",          "Tucson"),
    ("hyundai",  r"\bSanta\s+Fe\b",      "Santa Fe"),
    ("kia",      r"\bSorento\b",         "Sorento"),
    ("kia",      r"\bSportage\b",        "Sportage"),
    ("kia",      r"\bTelluride\b",       "Telluride"),
    ("mazda",    r"\bCX[-\s]?5\b",       "CX-5"),
]


@router.post("/apify")
async def apify_webhook(
    request: Request,
    x_apify_webhook_secret: Optional[str] = Header(None)
):
    # Verify webhook secret
    if not WEBHOOK_SECRET or x_apify_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract and validate dataset ID
    dataset_id = payload.get("resource", {}).get("defaultDatasetId", "")
    if not dataset_id:
        return {"status": "ok", "message": "No dataset to process"}

    # Validate dataset ID format (alphanumeric, no path traversal)
    if not re.match(r'^[a-zA-Z0-9_-]{5,50}$', dataset_id):
        logger.warning(f"[INGEST] Suspicious dataset_id rejected: {dataset_id}")
        raise HTTPException(status_code=400, detail="Invalid dataset ID")

    # Fetch dataset items from Apify API using Authorization header (not query param)
    import httpx
    apify_token = os.getenv("APIFY_TOKEN", "")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                params={"format": "json"},
                headers={"Authorization": f"Bearer {apify_token}"},
            )
            resp.raise_for_status()
            items = resp.json()
    except Exception as e:
        logger.error(f"[INGEST] Failed to fetch Apify dataset {dataset_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch dataset")

    if not isinstance(items, list):
        return {"status": "ok", "message": "No items in dataset"}

    processed = 0
    skipped = 0
    hot_deals = []

    for item in items:
        vehicle = normalize_apify_vehicle(item)
        if vehicle is None:
            skipped += 1
            continue

        gate_result = passes_basic_gates(vehicle)
        if not gate_result["pass"]:
            logger.info(f"[GATE] Rejected — {gate_result['reason']}: {vehicle.get('title','?')[:60]}")
            skipped += 1
            continue

        # Score using real DOS formula
        score_result = score_vehicle(vehicle)
        vehicle["dos_score"] = score_result["dos_score"]
        vehicle["score_breakdown"] = score_result
        vehicle["ingested_at"] = datetime.utcnow().isoformat()

        await save_opportunity_to_supabase(vehicle)
        logger.info(
            f"[INGEST] {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')} "
            f"| DOS={vehicle['dos_score']} | Bid=${vehicle.get('current_bid'):,.0f} "
            f"| Margin=${score_result.get('margin',0):,.0f} | {vehicle.get('state')}"
        )

        processed += 1
        if vehicle["dos_score"] >= 80:
            hot_deals.append(vehicle)

    # Fire Telegram alerts for hot deals
    if hot_deals:
        await send_telegram_alerts(hot_deals)

    return {
        "status": "ok",
        "processed": processed,
        "skipped": skipped,
        "hot_deals": len(hot_deals),
        "hot_deal_vehicles": [
            f"{v.get('year')} {v.get('make')} {v.get('model')} | "
            f"DOS={v['dos_score']} | ${v.get('current_bid'):,.0f}"
            for v in hot_deals
        ]
    }


def normalize_apify_vehicle(item: dict) -> Optional[dict]:
    """Normalize raw Apify scraper output to DealerScope vehicle format."""
    try:
        title = item.get("title", "")
        state = (item.get("state", "") or "").strip().upper()

        # Skip high rust states at normalize time
        if state in HIGH_RUST_STATES:
            return None

        make = extract_make(title)
        model = extract_model(title, make)
        year = extract_year(title)

        return {
            "title": title,
            "current_bid": float(item.get("current_bid") or 0),
            "buyer_premium_pct": float(item.get("buyer_premium_pct") or 12.5),
            "doc_fee": float(item.get("doc_fee") or 75),
            "mileage": item.get("mileage"),
            "state": state,
            "location": item.get("location", ""),
            "auction_end_time": item.get("auction_end_time") or item.get("auction_end_date"),
            "listing_url": item.get("listing_url", ""),
            "source_site": item.get("source") or item.get("source_site") or "GovDeals",
            "photo_url": item.get("image_url") or item.get("photo_url"),
            "agency_name": item.get("agency_name", ""),
            "vin": item.get("vin"),
            "year": year,
            "make": make,
            "model": model,
        }
    except Exception as e:
        logger.error(f"[INGEST] Normalize error: {e}")
        return None


def extract_year(title: str) -> Optional[int]:
    match = re.search(r"\b(20[12]\d|19[89]\d)\b", title)
    if match:
        y = int(match.group())
        return y if 1990 <= y <= datetime.now().year + 1 else None
    return None


def extract_make(title: str) -> str:
    title_upper = title.upper()
    for make in KNOWN_MAKES:
        if make.upper() in title_upper:
            return make
    return ""


def extract_model(title: str, make: str) -> str:
    """Extract model using per-make regex patterns."""
    make_lower = make.lower()
    for pat_make, pattern, canonical in _MODEL_PATTERNS:
        if pat_make == make_lower and re.search(pattern, title, re.IGNORECASE):
            return canonical

    # Fallback: extract 1-2 words after the year/make
    year_match = re.search(r"\b(20[12]\d|19[89]\d)\b", title)
    make_match = re.search(re.escape(make), title, re.IGNORECASE) if make else None

    start_pos = 0
    if year_match:
        start_pos = year_match.end()
    if make_match and make_match.end() > start_pos:
        start_pos = make_match.end()

    if start_pos > 0:
        remainder = title[start_pos:].strip()
        words = re.findall(r"[A-Za-z0-9][-A-Za-z0-9]*", remainder)
        if words:
            return " ".join(words[:2])

    return ""


def _estimate_mmr(make: str, model: str) -> float:
    """Estimate MMR by make/segment — placeholder until Manheim API is live."""
    make_lower = make.lower()
    segment = _MAKE_SEGMENT.get(make_lower, "sedan_other")

    # Refine by model keywords
    model_lower = model.lower()
    if any(t in model_lower for t in ["f-150", "silverado", "ram 1500", "tacoma", "sierra", "tundra", "frontier", "colorado"]):
        segment = "truck"
    elif any(t in model_lower for t in ["model y", "model 3"]):
        segment = "ev_trending"
    elif any(t in model_lower for t in ["highlander", "pilot", "explorer", "grand cherokee", "telluride", "4runner"]):
        segment = "suv_large"
    elif any(t in model_lower for t in ["rav4", "cr-v", "rogue", "escape", "equinox", "tucson", "sorento", "cx-5", "outback", "forester"]):
        segment = "suv_mid"

    return float(_SEGMENT_MMR.get(segment, 16000))


def passes_basic_gates(vehicle: dict) -> dict:
    """
    Five-layer institutional filter.
    Returns {"pass": bool, "reason": str}
    """
    bid = vehicle.get("current_bid", 0)
    state = vehicle.get("state", "")
    year = vehicle.get("year")
    mileage = vehicle.get("mileage")

    if bid < 3000 or bid > 35000:
        return {"pass": False, "reason": f"bid_out_of_range (${bid:,.0f})"}

    if state in HIGH_RUST_STATES:
        return {"pass": False, "reason": f"high_rust_state ({state})"}

    if not year:
        return {"pass": False, "reason": "no_year"}

    current_year = datetime.now().year
    age = current_year - year
    if age > 4 or age < 0:  # SOP: max 4 years
        return {"pass": False, "reason": f"age_exceeded ({age} years)"}

    if mileage is not None:
        try:
            if float(mileage) > 50000:  # SOP: max 50k miles
                return {"pass": False, "reason": f"mileage_exceeded ({mileage:,} mi)"}
        except (ValueError, TypeError):
            pass  # No mileage data is OK at this stage

    if not vehicle.get("listing_url"):
        return {"pass": False, "reason": "no_listing_url"}

    return {"pass": True, "reason": "ok"}


def score_vehicle(vehicle: dict) -> dict:
    """
    Score using the real DOS formula from backend.ingest.score.
    Falls back to simplified scoring if import fails.
    """
    try:
        from backend.ingest.score import score_deal

        bid = vehicle.get("current_bid", 0)
        state = vehicle.get("state", "")
        source = vehicle.get("source_site", "GovDeals")
        make = vehicle.get("make", "")
        model = vehicle.get("model", "")
        year = vehicle.get("year")
        mmr = _estimate_mmr(make, model)

        result = score_deal(
            bid=bid,
            mmr_ca=mmr,
            state=state,
            source_site=source,
            model=model,
            make=make,
            year=year,
        )
        result["mmr_estimated"] = mmr
        return result

    except Exception as e:
        logger.error(f"[SCORE] Real DOS formula failed, using fallback: {e}")
        return _fallback_score(vehicle)


def _fallback_score(vehicle: dict) -> dict:
    """Simple fallback scorer if the main formula errors."""
    score = 50.0
    if vehicle.get("state") in LOW_RUST_STATES:
        score += 8
    make = vehicle.get("make", "").upper()
    if make in {"FORD","TOYOTA","RAM","CHEVROLET","CHEVY","GMC","HONDA","NISSAN","TESLA"}:
        score += 12
    year = vehicle.get("year", 2000)
    age = datetime.now().year - year
    if 1 <= age <= 4:
        score += 10
    return {"dos_score": min(100, round(score, 1)), "score": min(100, round(score, 1)), "mmr_estimated": 0}


async def send_telegram_alerts(hot_deals: list) -> None:
    """Send Telegram alert for hot deals (DOS >= 80)."""
    try:
        import httpx
        for deal in hot_deals[:5]:  # Max 5 alerts per run
            msg = (
                f"🔥 *HOT DEAL ALERT*\n"
                f"{deal.get('year')} {deal.get('make')} {deal.get('model')}\n"
                f"DOS Score: *{deal['dos_score']}*\n"
                f"Bid: ${deal.get('current_bid', 0):,.0f}\n"
                f"State: {deal.get('state', '?')}\n"
                f"Margin: ${deal.get('score_breakdown', {}).get('margin', 0):,.0f}\n"
                f"[View Listing]({deal.get('listing_url', '')})"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": msg,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": False,
                    }
                )
    except Exception as e:
        logger.error(f"[TELEGRAM] Alert failed (non-fatal): {e}")


async def save_opportunity_to_supabase(vehicle: dict) -> bool:
    """Save scored vehicle to Supabase. Min DOS 50 to save."""
    if supabase_client is None:
        return False

    score = vehicle.get("dos_score", 0)
    if score < 50:
        return False

    if score >= 80:
        status = "hot"
    elif score >= 65:
        status = "good"
    else:
        status = "moderate"

    breakdown = vehicle.get("score_breakdown", {})
    row = {
        "listing_id": vehicle.get("listing_url", "")[-80:],  # truncated unique ID
        "listing_url": vehicle.get("listing_url", ""),
        "source": vehicle.get("source_site"),
        "title": vehicle.get("title"),
        "year": vehicle.get("year"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "mileage": vehicle.get("mileage"),
        "state": vehicle.get("state"),
        "vin": vehicle.get("vin"),
        "current_bid": vehicle.get("current_bid"),
        "mmr": breakdown.get("mmr_estimated"),
        "estimated_transport": breakdown.get("transport"),
        "auction_fees": breakdown.get("premium"),
        "gross_margin": breakdown.get("margin"),
        "dos_score": score,
        "auction_end_date": vehicle.get("auction_end_time"),
        "image_url": vehicle.get("photo_url"),
        "raw_data": vehicle,
    }

    try:
        supabase_client.table("opportunities").upsert(
            row, on_conflict="listing_url"
        ).execute()
        return True
    except Exception as e:
        logger.error(f"[INGEST] Supabase save failed: {e}")
        return False
