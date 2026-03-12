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
import hashlib
import json
import re
import os
import logging
import uuid
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

_alerts_per_run: dict = {}

WEBHOOK_SECRET = os.getenv("APIFY_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7529788084")
# ALERT CONTROL PLANE: FastAPI -> Telegram directly
# Decision: 2026-03-11, keep FastAPI direct, not OpenClaw messaging
# Reason: already deployed, working, single path

# Prefer backend-only env vars; fall back to VITE_* for compatibility during transition
_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
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


MAKE_ALIASES = {
    "chev": "chevrolet", "chevy": "chevrolet", "vw": "volkswagen",
    "mercedes-benz": "mercedes", "mercedesbenz": "mercedes",
}


def _normalize_make(make: str) -> str:
    m = re.sub(r"[^a-z0-9]", "", (make or "").lower().strip())
    return MAKE_ALIASES.get(m, m)


def _normalize_model(model: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", "", (model or "").lower().strip()).split()
    return " ".join(words[:2])


def compute_canonical_id(vehicle: dict) -> str:
    vin = (vehicle.get("vin") or "").strip().upper()
    if len(vin) == 17:
        return hashlib.sha256(vin.encode()).hexdigest()[:32]
    year = str(vehicle.get("year") or vehicle.get("model_year") or "")
    make = _normalize_make(vehicle.get("make") or "")
    model = _normalize_model(vehicle.get("model") or "")
    state = (vehicle.get("state") or vehicle.get("location_state") or "")[:2].upper()
    mileage = int(vehicle.get("mileage") or vehicle.get("meter_count") or 0)
    bucket = round(mileage / 2500) * 2500
    key = f"{year}_{make}_{model}_{state}_{bucket}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def check_and_handle_duplicate(supabase_client, vehicle: dict) -> dict:
    if supabase_client is None:
        return {"is_duplicate": False, "canonical_record_id": None}

    canonical_id = vehicle.get("canonical_id", "")
    new_source = vehicle.get("source_site", "")
    row = build_opportunity_row(vehicle)

    try:
        supabase_client.table("opportunities").insert(row).execute()
        return {"is_duplicate": False, "canonical_record_id": None}
    except Exception as e:
        error_text = str(e)
        if "duplicate key value violates unique constraint" not in error_text:
            logger.warning(f"[DEDUP] check failed: {e}")
            return {"is_duplicate": False, "canonical_record_id": None}

        if "canonical" not in error_text:
            try:
                existing = (
                    supabase_client.table("opportunities")
                    .select("id, is_duplicate, canonical_record_id")
                    .eq("listing_url", row["listing_url"])
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    existing_row = existing.data[0]
                    return {
                        "is_duplicate": existing_row.get("is_duplicate", False),
                        "canonical_record_id": existing_row.get("canonical_record_id"),
                    }
            except Exception as lookup_error:
                logger.warning(f"[DEDUP] listing lookup failed: {lookup_error}")

            logger.warning(f"[DEDUP] non-canonical unique conflict: {e}")
            return {"is_duplicate": False, "canonical_record_id": None}

        try:
            result = (
                supabase_client.table("opportunities")
                .select("id, all_sources")
                .eq("canonical_id", canonical_id)
                .eq("is_duplicate", False)
                .limit(1)
                .execute()
            )
            if not result.data:
                return {"is_duplicate": True, "canonical_record_id": canonical_id}

            existing = result.data[0]
            existing_id = existing["id"]
            existing_sources = existing.get("all_sources") or []
            if new_source and new_source not in existing_sources:
                updated = existing_sources + [new_source]
                supabase_client.table("opportunities").update({
                    "all_sources": updated,
                    "duplicate_count": len(updated) - 1,
                }).eq("id", existing_id).execute()
            return {"is_duplicate": True, "canonical_record_id": existing_id}
        except Exception as lookup_error:
            logger.warning(f"[DEDUP] conflict lookup failed: {lookup_error}")
            return {"is_duplicate": True, "canonical_record_id": canonical_id}


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

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Unexpected payload format")

    apify_run_id = payload.get("resource", {}).get("id", "") or str(uuid.uuid4())[:8]
    logger.info(f"[INGEST] Webhook received for run_id={apify_run_id}")

    if supabase_client is not None:
        try:
            existing = (
                supabase_client.table("opportunities")
                .select("id")
                .eq("run_id", apify_run_id)
                .limit(1)
                .execute()
            )
            if existing.data:
                logger.info(f"[IDEMPOTENCY] run_id={apify_run_id} already processed; skipping batch")
                return {
                    "status": "ok",
                    "run_id": apify_run_id,
                    "processed": 0,
                    "skipped": 0,
                    "hot_deals": 0,
                    "message": "Duplicate run_id skipped",
                }
        except Exception as e:
            logger.warning(f"[IDEMPOTENCY] lookup failed for run_id={apify_run_id}: {e}")

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
        vehicle = normalize_apify_vehicle(item, apify_run_id)
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

        # $1500 margin floor — capital protection
        if score_result.get("margin", 0) < 1500:
            logger.info(f"[MARGIN] below $1500 floor (${score_result.get('margin', 0):,.0f}): {vehicle.get('title','?')[:60]}")
            skipped += 1
            continue

        # Deduplication check
        dedup = {"is_duplicate": False, "canonical_record_id": None}
        if vehicle["dos_score"] >= 50:
            dedup = check_and_handle_duplicate(supabase_client, vehicle)
        is_dup = dedup["is_duplicate"]
        if is_dup:
            vehicle["is_duplicate"] = True
            vehicle["canonical_record_id"] = dedup["canonical_record_id"]
            logger.info(f"[DEDUP] duplicate of {dedup['canonical_record_id']}: {vehicle.get('title','?')[:50]}")

        # Save to Supabase always (audit trail)
        saved_opportunity_id = await save_opportunity_to_supabase(vehicle)
        if saved_opportunity_id:
            vehicle["opportunity_id"] = saved_opportunity_id

        # Only alert and sync Notion on canonical records
        if not is_dup and vehicle["dos_score"] >= 65:
            await sync_to_notion(vehicle)

        logger.info(
            f"[INGEST] {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')} "
            f"| DOS={vehicle['dos_score']} | Bid=${vehicle.get('current_bid'):,.0f} "
            f"| Margin=${score_result.get('margin',0):,.0f} | {vehicle.get('state')}"
            + (" [DUP]" if is_dup else "")
        )

        processed += 1
        if not is_dup and vehicle["dos_score"] >= 80:
            hot_deals.append(vehicle)

    # Fire Telegram alerts for hot deals
    if hot_deals:
        await send_telegram_alerts(hot_deals)

    return {
        "status": "ok",
        "run_id": apify_run_id,
        "processed": processed,
        "skipped": skipped,
        "hot_deals": len(hot_deals),
        "hot_deal_vehicles": [
            f"{v.get('year')} {v.get('make')} {v.get('model')} | "
            f"DOS={v['dos_score']} | ${v.get('current_bid'):,.0f}"
            for v in hot_deals
        ],
    }


def normalize_apify_vehicle(item: dict, run_id: str) -> Optional[dict]:
    """Normalize raw Apify scraper output to DealerScope vehicle format.

    Handles two formats:
    - Our custom scrapers: snake_case (current_bid, listing_url, etc.)
    - parseforge/govdeals-scraper: camelCase (currentBid, url, locationState, etc.)
    """
    try:
        title = item.get("title", "")

        # State: parseforge uses locationState, ours uses state
        state = (
            item.get("locationState") or
            item.get("state") or ""
        ).strip().upper()

        # Skip high rust states at normalize time
        if state in HIGH_RUST_STATES:
            return None

        # Make/model/year: parseforge provides these directly
        make = item.get("make") or extract_make(title) or ""
        model = item.get("model") or extract_model(title, make) or ""
        year_raw = item.get("modelYear") or item.get("year")
        year = int(year_raw) if year_raw and str(year_raw).isdigit() else extract_year(title)

        # Bid: parseforge uses currentBid, ours uses current_bid
        current_bid = float(item.get("currentBid") or item.get("current_bid") or 0)

        # Mileage: parseforge puts in meterCount when type is odometer
        mileage = item.get("mileage") or item.get("meterCount")

        # End time: parseforge uses auctionEndUtc
        auction_end = (
            item.get("auctionEndUtc") or
            item.get("auction_end_time") or
            item.get("auction_end_date")
        )

        # URL: parseforge uses url, ours uses listing_url
        listing_url = item.get("url") or item.get("listing_url") or ""

        # Photo: parseforge uses imageUrl or photos[]
        photos = item.get("photos", [])
        photo_url = (
            item.get("imageUrl") or item.get("photo_url") or
            item.get("image_url") or (photos[0] if photos else "")
        )

        # Agency: parseforge uses seller
        agency = item.get("seller") or item.get("agency_name") or ""

        # Source
        source = item.get("source_site") or item.get("source") or "govdeals"

        normalized = {
            "title": title,
            "current_bid": current_bid,
            "buyer_premium_pct": float(item.get("buyer_premium_pct") or 10.0),
            "doc_fee": float(item.get("doc_fee") or 75),
            "mileage": mileage,
            "state": state,
            "location": (
                item.get("location") or
                f"{item.get('locationCity','')}, {state}".strip(", ")
            ),
            "auction_end_time": auction_end,
            "listing_url": listing_url,
            "source_site": source,
            "photo_url": photo_url,
            "agency_name": agency,
            "vin": item.get("vin"),
            "year": year,
            "make": make,
            "model": model,
            "run_id": run_id,
            "source_run_id": run_id,
        }
        normalized["canonical_id"] = compute_canonical_id(normalized)
        normalized["all_sources"] = [normalized.get("source_site", "unknown")]
        normalized["is_duplicate"] = False
        normalized["canonical_record_id"] = None
        normalized["duplicate_count"] = 0
        return normalized
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

    # 88% MMR ceiling — capital protection
    make = vehicle.get("make", "")
    model = vehicle.get("model", "")
    mmr = _estimate_mmr(make, model)
    if mmr > 0 and bid > mmr * 0.88:
        return {"pass": False, "reason": f"bid_exceeds_88pct_mmr (${bid:,.0f} > ${mmr * 0.88:,.0f})"}

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


async def sync_to_notion(vehicle: dict) -> bool:
    """Push a scored deal to the Notion Dealerscope Deals database."""
    notion_token = os.getenv("NOTION_TOKEN", "")
    notion_db_id = os.getenv("NOTION_DEALS_DB_ID", "")
    if not notion_token or not notion_db_id:
        return False

    score = vehicle.get("dos_score", 0)
    breakdown = vehicle.get("score_breakdown", {})

    if score >= 80:
        status = "🔥 Hot"
    elif score >= 65:
        status = "✅ Good"
    else:
        status = "👀 Watching"

    title = f"{vehicle.get('year','')} {vehicle.get('make','')} {vehicle.get('model','')}".strip() or vehicle.get("title", "Unknown")

    # Parse auction end date
    end_date = None
    raw_end = vehicle.get("auction_end_time")
    if raw_end:
        try:
            from dateutil import parser as dateparser
            end_date = dateparser.parse(str(raw_end)).strftime("%Y-%m-%d")
        except Exception:
            pass

    props = {
        "Name": {"title": [{"text": {"content": title[:100]}}]},
        "DOS Score": {"number": score},
        "Status": {"select": {"name": status}},
        "Bid Price": {"number": vehicle.get("current_bid")},
        "MMR": {"number": breakdown.get("mmr_estimated")},
        "Gross Margin": {"number": breakdown.get("margin")},
        "Source": {"select": {"name": vehicle.get("source_site", "GovDeals")}},
        "Year": {"number": vehicle.get("year")},
        "Listing URL": {"url": vehicle.get("listing_url") or None},
    }

    if vehicle.get("state"):
        props["State"] = {"select": {"name": vehicle["state"][:2]}}
    if vehicle.get("make"):
        props["Make"] = {"rich_text": [{"text": {"content": vehicle["make"][:100]}}]}
    if vehicle.get("model"):
        props["Model"] = {"rich_text": [{"text": {"content": vehicle["model"][:100]}}]}
    if vehicle.get("mileage"):
        try:
            props["Mileage"] = {"number": int(float(vehicle["mileage"]))}
        except (ValueError, TypeError):
            pass
    if end_date:
        props["Auction Ends"] = {"date": {"start": end_date}}

    # Structured deal summary for the Notes field
    bid        = vehicle.get("current_bid", 0)
    mmr        = breakdown.get("mmr_estimated", 0)
    margin     = breakdown.get("margin", 0)
    state_str  = vehicle.get("state", "?")
    end_str    = end_date or "?"
    rec        = "🔥 BUY HOT" if score >= 80 else "✅ BUY" if score >= 65 else "⚠️ WATCH"
    notes_text = (
        f"{title} | Bid: ${bid:,.0f} | MMR: ${mmr:,.0f} | "
        f"Margin: ${margin:,.0f} | DOS: {score} | "
        f"Ends: {end_str} | State: {state_str} | {rec}"
    )
    props["Notes"] = {"rich_text": [{"text": {"content": notes_text[:2000]}}]}

    # Remove None values (Notion rejects null numbers)
    props = {k: v for k, v in props.items() if not (
        isinstance(v, dict) and v.get("number") is None
    )}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {notion_token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={"parent": {"database_id": notion_db_id}, "properties": props},
            )
            if resp.status_code == 200:
                return True
            logger.warning(f"[NOTION] Failed to sync: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[NOTION] Sync error (non-fatal): {e}")
        return False


async def send_telegram_alert(deal: dict) -> Optional[str]:
    """Send a single Telegram alert, log the receipt, and return the Telegram message_id."""
    # Kill switch
    if os.getenv("ALERTS_ENABLED", "true").lower() != "true":
        logger.info("[ALERTS DISABLED] skipping alert via kill switch")
        return None

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[TELEGRAM] Missing bot token or chat ID; skipping alert")
        return None

    # 6-hour suppression check
    if supabase_client is not None:
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=6)).isoformat()
            recent = (
                supabase_client.table("alert_log")
                .select("id")
                .eq("opportunity_id", deal.get("id"))
                .gte("sent_at", cutoff)
                .execute()
            )
            if recent.data:
                logger.info(f"[SUPPRESSED] already alerted within 6hrs for {deal.get('title', '?')[:40]}")
                return None
        except Exception as e:
            logger.warning(f"[SUPPRESSION CHECK] failed: {e}")

    # Per-run alert cap (max 5)
    run_id = deal.get("run_id", "unknown")
    _alerts_per_run[run_id] = _alerts_per_run.get(run_id, 0) + 1
    if _alerts_per_run[run_id] > 5:
        logger.info(f"[ALERT CAP] max 5 alerts reached for run {run_id}")
        return None

    try:
        import httpx

        opp_id = deal.get("id", "unknown")
        reply_markup = json.dumps({
            "inline_keyboard": [[
                {"text": "🔥 BUY", "callback_data": f"buy_{opp_id}"},
                {"text": "👀 WATCH", "callback_data": f"watch_{opp_id}"},
                {"text": "❌ PASS", "callback_data": f"pass_{opp_id}"},
            ]]
        })

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
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": msg,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                    "reply_markup": reply_markup,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.error(f"[TELEGRAM] Alert failed (non-fatal): {e}")
        return None

    message_id = payload.get("result", {}).get("message_id")
    if message_id is None:
        logger.warning(f"[TELEGRAM] Missing message_id in response for run_id={deal.get('run_id')}")
        return None

    message_id_str = str(message_id)
    deal["message_id"] = message_id_str
    await insert_alert_log(deal, message_id_str)
    return message_id_str


async def insert_alert_log(vehicle: dict, message_id: str) -> bool:
    """Persist a Telegram delivery receipt to Supabase."""
    if supabase_client is None:
        return False

    alert_key = vehicle.get("opportunity_id") or vehicle.get("listing_url") or vehicle.get("title") or "unknown"
    alert_id = hashlib.sha256(f"{vehicle.get('run_id', '')}:{alert_key}".encode()).hexdigest()[:64]
    row = {
        "opportunity_id": vehicle.get("opportunity_id"),
        "run_id": vehicle.get("run_id"),
        "alert_id": alert_id,
        "message_id": message_id,
        "channel": "telegram",
        "delivery_state": "sent",
        "dos_score": vehicle.get("dos_score"),
        "vehicle_title": (
            f"{vehicle.get('year', '')} {vehicle.get('make', '')} {vehicle.get('model', '')}".strip()
            or vehicle.get("title")
        ),
    }

    try:
        supabase_client.table("alert_log").insert(row).execute()
        return True
    except Exception as e:
        logger.error(f"[ALERT_LOG] Failed to write receipt for run_id={vehicle.get('run_id')}: {e}")
        return False


async def send_telegram_alerts(hot_deals: list) -> None:
    """Send Telegram alerts for hot deals (DOS >= 80) and store receipts."""
    for deal in hot_deals[:5]:  # Max 5 alerts per run
        await send_telegram_alert(deal)


async def save_opportunity_to_supabase(vehicle: dict) -> Optional[str]:
    """Save scored vehicle to Supabase. Min DOS 50 to save."""
    if supabase_client is None:
        return None

    score = vehicle.get("dos_score", 0)
    if score < 50:
        return None

    row = build_opportunity_row(vehicle)

    try:
        result = supabase_client.table("opportunities").upsert(
            row, on_conflict="listing_url"
        ).execute()
        if result.data:
            return result.data[0].get("id")

        lookup = (
            supabase_client.table("opportunities")
            .select("id")
            .eq("listing_url", row["listing_url"])
            .limit(1)
            .execute()
        )
        if lookup.data:
            return lookup.data[0].get("id")
        return None
    except Exception as e:
        title = vehicle.get("title", "unknown")[:80]
        logger.error(f"[INGEST] Supabase save FAILED for '{title}': {e}")
        return None


def build_opportunity_row(vehicle: dict) -> dict:
    breakdown = vehicle.get("score_breakdown", {})
    return {
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
        "dos_score": vehicle.get("dos_score"),
        "auction_end_date": vehicle.get("auction_end_time"),
        "image_url": vehicle.get("photo_url"),
        "raw_data": vehicle,
        "canonical_id": vehicle.get("canonical_id"),
        "is_duplicate": vehicle.get("is_duplicate", False),
        "canonical_record_id": vehicle.get("canonical_record_id"),
        "all_sources": vehicle.get("all_sources", []),
        "duplicate_count": vehicle.get("duplicate_count", 0),
        "run_id": vehicle.get("run_id"),
        "source_run_id": vehicle.get("source_run_id"),
        "pipeline_step": "saved",
        "step_status": "complete",
        "processed_at": vehicle.get("processed_at") or datetime.utcnow().isoformat(),
    }
