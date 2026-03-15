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
import re
import os
import logging
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2 import extras as psycopg2_extras
from psycopg2 import sql as psycopg2_sql

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

try:
    from backend.ingest.alert_gating import AlertThresholds, evaluate_alert_gate
except ImportError:
    AlertThresholds = None  # type: ignore[assignment]

    def evaluate_alert_gate(*args, **kwargs):  # type: ignore[no-redef]
        return {
            "eligible": False,
            "alert_type": None,
            "blocking_reasons": ["alert_gate_import_failed"],
            "summary": "type=blocked | import_failed",
            "signals": {},
        }

try:
    from backend.ingest.condition import compute_condition_grade as _compute_condition_grade
except ImportError:
    def _compute_condition_grade(**kwargs):  # type: ignore[misc]
        return None

alerts_this_run: dict = {}


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value in {None, ""}:
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning("[ALERT_GATE] Invalid %s=%r; using %s", name, raw_value, default)
        return default


def _alert_thresholds() -> Optional["AlertThresholds"]:
    if AlertThresholds is None:
        return None
    return AlertThresholds(
        min_score=_env_float("HOT_DEAL_MIN_SCORE", 80.0),
        platinum_min_roi_day=_env_float("PLATINUM_MIN_ROI_DAY", 75.0),
        min_bid_headroom=_env_float("ALERT_MIN_BID_HEADROOM", 0.0),
        min_trust_score=_env_float("ALERT_MIN_TRUST_SCORE", 0.25),
        min_confidence=_env_float("ALERT_MIN_CONFIDENCE", 55.0),
    )

WEBHOOK_SECRET = os.getenv("APIFY_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7529788084")
# ALERT CONTROL PLANE: FastAPI -> Telegram directly
# Decision: 2026-03-11, keep FastAPI direct, not OpenClaw messaging
# Reason: already deployed, working, single path

# Prefer backend-only env vars; fall back to VITE_* for compatibility during transition
_supabase_url = (
    os.getenv("SUPABASE_URL")
    or os.getenv("VITE_SUPABASE_URL")
    or "https://lbnxzvqppccajllsqaaw.supabase.co"
)
_supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
_supabase_anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
_environment = os.getenv("ENVIRONMENT", "production")

if _supabase_service_role_key:
    _supabase_key = _supabase_service_role_key
elif _supabase_anon_key:
    if _environment == "development":
        _supabase_key = _supabase_anon_key
        logger.warning(
            "SUPABASE_SERVICE_ROLE_KEY missing in development; falling back to anon key."
        )
    else:
        logger.critical(
            "SUPABASE_SERVICE_ROLE_KEY env var required for privileged ingest operations in production."
        )
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY env var required for privileged ingest operations in production."
        )
else:
    _supabase_key = None
    if _environment == "development":
        logger.warning(
            "SUPABASE_SERVICE_ROLE_KEY missing in development and no anon key is available."
        )
    else:
        logger.critical(
            "SUPABASE_SERVICE_ROLE_KEY env var required for privileged ingest operations."
        )
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY env var required for privileged ingest operations."
        )

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


def _derive_supabase_direct_db_url() -> Optional[str]:
    candidates = (
        os.getenv("SUPABASE_DB_URL"),
        os.getenv("SUPABASE_DATABASE_URL"),
        os.getenv("SUPABASE_DIRECT_DB_URL"),
    )
    for candidate in candidates:
        if candidate:
            return candidate

    db_password = os.getenv("SUPABASE_DB_PASSWORD")
    if not db_password:
        return None

    project_ref = os.getenv("SUPABASE_PROJECT_ID") or os.getenv("VITE_SUPABASE_PROJECT_ID")
    if not project_ref and _supabase_url:
        match = re.search(r"https://([a-z0-9]+)\.supabase\.co", _supabase_url)
        if match:
            project_ref = match.group(1)

    if not project_ref:
        return None

    return (
        f"postgresql://postgres:{db_password}"
        f"@db.{project_ref}.supabase.co:5432/postgres?sslmode=require"
    )


_direct_supabase_db_url = _derive_supabase_direct_db_url()

# State classification
LOW_RUST_STATES = {
    "AZ","CA","NV","CO","NM","UT","TX","FL","GA","SC","TN","NC","VA","WA","OR","HI",
    "OK","AR","LA","MS","AL"
}
HIGH_RUST_STATES = {
    "OH","MI","PA","NY","WI","MN","IL","IN","MO","IA","ND","SD","NE","KS","WV",
    "ME","NH","VT","MA","RI","CT","NJ","MD","DE"
}

# Whitelist of valid US state codes — reject anything else (Canadian provinces, garbage)
US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC"
}

# Passenger vehicle target states (no rust belt)
TARGET_STATES = {
    "AZ","CA","NV","CO","NM","UT","TX","FL","GA","SC","TN","NC","VA","WA","OR","HI"
}

# Commercial/fleet vehicle patterns to reject — not passenger cars
_COMMERCIAL_PATTERNS = [
    r"\bEconoline\b", r"\bExpress\s*Cargo\b", r"\bProMaster\s*Cargo\b",
    r"\bSprinter\s*Cargo\b", r"\bTransit\s*Cargo\b", r"\bSavana\s*Cargo\b",
    r"\bE-250\b", r"\bE-350\b", r"\b2500\b", r"\b3500\b", r"\b4500\b", r"\b5500\b",
    r"\bCutaway\b", r"\bChassis\s*Cab\b",
    r"\bDump\s*Truck\b", r"\bBox\s*Truck\b", r"\bBucket\s*Truck\b",
    r"\bStake\s*Bed\b", r"\bFlatbed\b", r"\bStep\s*Van\b", r"\bShuttle\b",
    r"\bUtility\s*Bed\b", r"\bRefrigerator\s*Truck\b",
]

_TITLE_BRAND_PATTERNS = [
    ("salvage", r"\bsalvage\b"),
    ("rebuilt", r"\brebuilt\s+title\b"),
    ("flood", r"\bflood\b"),
    ("lemon", r"\blemon\s+law\b|\blemon\s+title\b"),
    ("frame damage", r"\bframe[\s-]+damage\b"),
    ("structural damage", r"\bstructural[\s-]+damage\b"),
    ("airbag deployed", r"\bair\s*bag\s+deployed\b"),
    ("parts only", r"\bparts[\s-]+only\b"),
    ("non-op", r"\bnon[\s-]?op\b"),
    ("fire damage", r"\bfire[\s-]+damage\b"),
    ("hail damage", r"\bhail[\s-]+damage\b"),
]

# MMR estimates by model — much more accurate than segment-only
# Based on 2025-2026 wholesale (Manheim/Black Book averages)
_MODEL_MMR = {
    # Trucks — high demand
    "f-150": 32000, "f-250": 38000, "f-350": 42000,
    "silverado 1500": 30000, "silverado 2500": 38000,
    "ram 1500": 29000, "ram 2500": 36000,
    "tacoma": 31000, "tundra": 38000,
    "colorado": 24000, "canyon": 24000,
    "ranger": 26000, "frontier": 22000, "ridgeline": 28000,
    "maverick": 24000,
    # SUVs large
    "explorer": 24000, "expedition": 42000,
    "tahoe": 32000, "suburban": 38000, "yukon": 34000,
    "highlander": 28000, "pilot": 34000, "sequoia": 46000,
    "pathfinder": 28000, "armada": 36000,
    "durango": 30000,
    # SUVs mid
    "rav4": 28000, "cr-v": 26000, "rogue": 24000,
    "escape": 20000, "equinox": 21000, "terrain": 20000,
    "tucson": 22000, "sportage": 21000, "forester": 23000,
    "outback": 24000, "cx-5": 24000, "compass": 19000,
    "cherokee": 20000, "grand cherokee": 28000, "wrangler": 34000,
    "bronco": 36000,
    # Sedans popular
    "camry": 22000, "accord": 22000, "altima": 18000,
    "civic": 20000, "corolla": 18000, "sentra": 16000,
    "elantra": 16000, "sonata": 18000, "optima": 17000,
    "malibu": 16000, "fusion": 17000, "impala": 14000,
    # EVs
    "model y": 38000, "model 3": 32000, "model s": 35000, "model x": 38000,
    "ioniq 5": 30000, "ioniq 6": 28000,
    # Vans (passenger, not cargo)
    "odyssey": 26000, "sienna": 30000, "pacifica": 24000,
    "town & country": 14000, "caravan": 12000,
    # Commercial (low MMR — we reject these, but score accurately if they slip through)
    "econoline": 9000, "express cargo": 9000, "promaster cargo": 10000,
    "transit cargo": 9000, "sprinter cargo": 14000,
    "transit connect": 11000,
    # Interceptors (police) — popular resale
    "explorer interceptor": 22000, "police interceptor": 22000,
    "tahoe ppv": 28000,
}

# Fallback: make → segment MMR when model not found
_MAKE_SEGMENT_MMR = {
    "ford": 22000, "chevrolet": 22000, "chevy": 22000, "gmc": 24000,
    "ram": 22000, "dodge": 16000, "toyota": 24000, "honda": 20000,
    "nissan": 18000, "hyundai": 17000, "kia": 17000, "subaru": 20000,
    "jeep": 22000, "bmw": 26000, "mercedes": 28000, "lexus": 28000,
    "cadillac": 22000, "lincoln": 22000, "audi": 24000,
    "tesla": 36000, "rivian": 40000, "volkswagen": 18000,
    "buick": 16000, "mitsubishi": 14000, "mazda": 18000,
    "acura": 22000, "infiniti": 20000, "volvo": 20000,
}

# Keep for backward compat
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

# Segment MMR fallback
_SEGMENT_MMR = {
    "truck":        28000,
    "suv_large":    32000,
    "suv_mid":      22000,
    "luxury":       26000,
    "ev_trending":  36000,
    "sedan_popular":18000,
    "ev_other":     16000,
    "sedan_other":  15000,
    "coupe":        14000,
    "minivan":      22000,
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


def _find_title_brand_issue(vehicle: dict) -> Optional[str]:
    text_to_check = " ".join(filter(None, [
        vehicle.get("title", ""),
        vehicle.get("description", ""),
        vehicle.get("notes", ""),
    ]))
    search_fields = [
        ("title_status", vehicle.get("title_status")),
        ("listing_text", text_to_check),
        ("vin", vehicle.get("vin")),
    ]
    for field_name, raw_value in search_fields:
        value = str(raw_value or "").strip()
        if not value:
            continue
        for label, pattern in _TITLE_BRAND_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return f"title_brand_rejected ({field_name} matched '{label}')"
    return None


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
    listing_url = vehicle.get("listing_url", "")

    try:
        if listing_url:
            existing = (
                supabase_client.table("opportunities")
                .select("id, is_duplicate, canonical_record_id")
                .eq("listing_url", listing_url)
                .limit(1)
                .execute()
            )
            if existing.data:
                existing_row = existing.data[0]
                return {
                    "is_duplicate": existing_row.get("is_duplicate", False),
                    "canonical_record_id": existing_row.get("canonical_record_id"),
                }

        if not canonical_id:
            return {"is_duplicate": False, "canonical_record_id": None}

        result = (
            supabase_client.table("opportunities")
            .select("id, all_sources")
            .eq("canonical_id", canonical_id)
            .eq("is_duplicate", False)
            .limit(1)
            .execute()
        )
        if not result.data:
            return {"is_duplicate": False, "canonical_record_id": None}

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
        logger.warning(f"[DEDUP] check failed: {lookup_error}")
        return {"is_duplicate": False, "canonical_record_id": None}


def _parse_datetime_utc(raw_value) -> Optional[datetime]:
    if raw_value in {None, ""}:
        return None
    if isinstance(raw_value, datetime):
        dt = raw_value
    else:
        text = str(raw_value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def extract_apify_webhook_metadata(payload: dict) -> dict:
    resource = payload.get("resource", {}) if isinstance(payload, dict) else {}
    item_count = None
    for candidate in (
        payload.get("item_count"),
        payload.get("itemCount"),
        resource.get("item_count"),
        resource.get("itemCount"),
    ):
        if candidate is not None:
            item_count = candidate
            break

    if item_count is None and isinstance(payload.get("items"), list):
        item_count = len(payload["items"])

    try:
        item_count = int(item_count) if item_count is not None else None
    except (TypeError, ValueError):
        item_count = None

    return {
        "source": payload.get("source") or "apify",
        "actor_id": resource.get("actId") or resource.get("actorId") or payload.get("actor_id"),
        "run_id": resource.get("id") or payload.get("run_id"),
        "item_count": item_count,
        "created_at": _parse_datetime_utc(
            payload.get("createdAt") or resource.get("createdAt") or resource.get("startedAt")
        ),
    }


def insert_webhook_log(payload: dict) -> Optional[str]:
    if supabase_client is None:
        return None

    metadata = extract_apify_webhook_metadata(payload)
    row = {
        "source": metadata["source"],
        "actor_id": metadata["actor_id"],
        "run_id": metadata["run_id"],
        "item_count": metadata["item_count"],
        "raw_payload": payload,
        "processing_status": "pending",
    }
    result = supabase_client.table("webhook_log").insert(row).execute()
    if result.data:
        return result.data[0].get("id")
    return None


def update_webhook_log(
    webhook_log_id: Optional[str],
    processing_status: str,
    *,
    error_message: Optional[str] = None,
    item_count: Optional[int] = None,
) -> None:
    if supabase_client is None or not webhook_log_id:
        return

    update_row = {
        "processing_status": processing_status,
        "error_message": error_message,
    }
    if item_count is not None:
        update_row["item_count"] = item_count

    supabase_client.table("webhook_log").update(update_row).eq("id", webhook_log_id).execute()


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

    webhook_log_id = None
    try:
        webhook_log_id = insert_webhook_log(payload)
    except Exception as e:
        logger.warning(f"[WEBHOOK_LOG] insert failed (non-fatal): {e}")

    metadata = extract_apify_webhook_metadata(payload)
    apify_run_id = metadata["run_id"] or str(uuid.uuid4())[:8]
    logger.info(f"[INGEST] Webhook received for run_id={apify_run_id}")

    try:
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
                    logger.warning(
                        "[IDEMPOTENCY] run_id=%s has existing rows; replaying batch to avoid partial-run data loss",
                        apify_run_id,
                    )
            except Exception as e:
                logger.warning(f"[IDEMPOTENCY] lookup failed for run_id={apify_run_id}: {e}")

        # Extract and validate dataset ID. Some Apify webhook payloads omit
        # resource.defaultDatasetId even though the run itself has it, so fall
        # back to resolving the run details directly from Apify before giving up.
        resource = payload.get("resource", {}) if isinstance(payload.get("resource"), dict) else {}
        dataset_id = (
            resource.get("defaultDatasetId")
            or payload.get("defaultDatasetId")
            or payload.get("datasetId")
            or payload.get("defaultDatasetId")
            or ""
        )

        if not dataset_id and apify_run_id and os.getenv("APIFY_TOKEN", ""):
            import httpx
            apify_token = os.getenv("APIFY_TOKEN", "")
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    run_resp = await client.get(
                        f"https://api.apify.com/v2/actor-runs/{apify_run_id}",
                        headers={"Authorization": f"Bearer {apify_token}"},
                    )
                    run_resp.raise_for_status()
                    run_data = run_resp.json().get("data", {})
                    dataset_id = run_data.get("defaultDatasetId", "") or ""
                    if dataset_id:
                        logger.info(
                            f"[INGEST] Resolved missing dataset_id via actor run lookup for run_id={apify_run_id}"
                        )
            except Exception as e:
                logger.warning(
                    f"[INGEST] Unable to resolve dataset_id from actor run {apify_run_id}: {e}"
                )

        if not dataset_id:
            response = {"status": "ok", "message": "No dataset to process"}
            try:
                update_webhook_log(
                    webhook_log_id,
                    "processed",
                    item_count=metadata["item_count"],
                )
            except Exception as e:
                logger.warning(f"[WEBHOOK_LOG] update failed (non-fatal): {e}")
            return response

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
            response = {"status": "ok", "message": "No items in dataset"}
            try:
                update_webhook_log(webhook_log_id, "processed", item_count=metadata["item_count"])
            except Exception as e:
                logger.warning(f"[WEBHOOK_LOG] update failed (non-fatal): {e}")
            return response

        processed = 0
        evaluated = 0
        saved_count = 0
        failed_save_count = 0
        skipped = 0
        hot_deals = []
        dataset_item_count = len(items)
        skip_reasons: dict[str, int] = {}
        save_outcomes: dict[str, int] = {}
        duplicate_count = 0
        notion_sync_count = 0

        logger.info(
            "[INGEST_RUN] start | run_id=%s | dataset_id=%s | items=%s",
            apify_run_id,
            dataset_id,
            dataset_item_count,
        )

        for item in items:
            vehicle = normalize_apify_vehicle(
                item,
                apify_run_id,
                default_time_anchor=metadata.get("created_at"),
            )
            if vehicle is None:
                skipped += 1
                _increment_reason_counter(skip_reasons, "normalize_rejected")
                continue

            gate_result = passes_basic_gates(vehicle)
            if not gate_result["pass"]:
                logger.info(f"[GATE] Rejected — {gate_result['reason']}: {vehicle.get('title','?')[:60]}")
                skipped += 1
                _increment_reason_counter(skip_reasons, f"gate:{gate_result['reason']}")
                continue

            # Score using real DOS formula
            score_result = score_vehicle(vehicle)
            vehicle["dos_score"] = score_result["dos_score"]
            vehicle["score_breakdown"] = score_result
            vehicle["ingested_at"] = datetime.utcnow().isoformat()
            evaluated += 1

            # $1500 wholesale margin floor — capital protection
            if score_result.get("wholesale_margin", 0) < 1500:
                logger.info(
                    f"[MARGIN] below $1500 wholesale floor (${score_result.get('wholesale_margin', 0):,.0f}): "
                    f"{vehicle.get('title','?')[:60]}"
                )
                skipped += 1
                _increment_reason_counter(skip_reasons, "margin_below_floor")
                continue

            if score_result.get("investment_grade") == "Bronze":
                logger.info(f"[CEILING] bronze reject: {vehicle.get('title','?')[:60]}")
                skipped += 1
                _increment_reason_counter(skip_reasons, "bronze_reject")
                continue

            if not score_result.get("ceiling_pass", True):
                logger.info(
                    f"[CEILING] rejected — {score_result.get('ceiling_reason')} | "
                    f"headroom=${score_result.get('bid_headroom', 0):,.0f}: {vehicle.get('title','?')[:60]}"
                )
                skipped += 1
                _increment_reason_counter(
                    skip_reasons,
                    f"ceiling:{score_result.get('ceiling_reason') or 'unknown'}",
                )
                continue

            # Deduplication check
            dedup = {"is_duplicate": False, "canonical_record_id": None}
            if vehicle["dos_score"] >= 50:
                dedup = check_and_handle_duplicate(supabase_client, vehicle)
            is_dup = dedup["is_duplicate"]
            if is_dup:
                vehicle["is_duplicate"] = True
                vehicle["canonical_record_id"] = dedup["canonical_record_id"]
                duplicate_count += 1
                logger.info(f"[DEDUP] duplicate of {dedup['canonical_record_id']}: {vehicle.get('title','?')[:50]}")

            # Save to Supabase always (audit trail)
            saved_opportunity_id = await save_opportunity_to_supabase(vehicle)
            save_status = vehicle.get("_save_status", "unknown")
            _increment_reason_counter(save_outcomes, save_status)
            if saved_opportunity_id:
                vehicle["opportunity_id"] = saved_opportunity_id

            inserted_success = save_status in {"saved_supabase", "saved_direct_pg"}
            existing_success = save_status == "duplicate_existing"
            save_succeeded = inserted_success or existing_success
            is_existing_listing = save_status in {"duplicate_existing", "duplicate_unresolved"} or is_dup
            if save_succeeded:
                processed += 1
                if inserted_success:
                    saved_count += 1
            else:
                failed_save_count += 1

            # Replay-safe side effects for canonical records; downstream sinks dedupe independently.
            if save_succeeded and not is_dup and vehicle["dos_score"] >= 65:
                notion_synced = await sync_to_notion(vehicle)
                if notion_synced:
                    notion_sync_count += 1

            logger.info(
                f"[INGEST] {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')} "
                f"| DOS={vehicle['dos_score']} | Bid=${vehicle.get('current_bid'):,.0f} "
                f"| Gross=${score_result.get('gross_margin',0):,.0f} "
                f"| Headroom=${score_result.get('bid_headroom',0):,.0f} | {vehicle.get('state')}"
                + (" [DUP]" if is_dup else "")
                + f" | save={save_status}"
            )

            if not is_existing_listing and save_status in {"saved_supabase", "saved_direct_pg"}:
                alert_gate = _alert_gate_for_vehicle(vehicle)
                if alert_gate.get("eligible"):
                    logger.info(
                        "[ALERT_GATE] eligible | %s | %s",
                        alert_gate.get("summary"),
                        vehicle.get("title", "?")[:80],
                    )
                    hot_deals.append(vehicle)
                elif (
                    vehicle["dos_score"] >= _env_float("HOT_DEAL_MIN_SCORE", 80.0)
                    or score_result.get("investment_grade") in {"Gold", "Platinum"}
                ):
                    logger.info(
                        "[ALERT_GATE] blocked | %s | reasons=%s | %s",
                        alert_gate.get("summary"),
                        ",".join(alert_gate.get("blocking_reasons") or ["unknown"]),
                        vehicle.get("title", "?")[:80],
                    )

        # Fire Telegram alerts for hot deals
        if hot_deals:
            await send_telegram_alerts(hot_deals)

        logger.info(
            "[INGEST_RUN] complete | run_id=%s | dataset_id=%s | items=%s | evaluated=%s | inserted=%s | existing=%s | failed_save=%s | skipped=%s | duplicates=%s | notion_sync=%s | hot_deals=%s | save_outcomes=%s | skip_reasons=%s",
            apify_run_id,
            dataset_id,
            dataset_item_count,
            evaluated,
            saved_count,
            save_outcomes.get("duplicate_existing", 0),
            failed_save_count,
            skipped,
            duplicate_count,
            notion_sync_count,
            len(hot_deals),
            save_outcomes,
            skip_reasons,
        )

        response_status = "degraded" if failed_save_count else "ok"
        response = {
            "status": response_status,
            "run_id": apify_run_id,
            "dataset_id": dataset_id,
            "evaluated": evaluated,
            "processed": processed,
            "inserted": saved_count,
            "existing": save_outcomes.get("duplicate_existing", 0),
            "saved": saved_count,
            "failed_save": failed_save_count,
            "skipped": skipped,
            "duplicates": duplicate_count,
            "notion_sync": notion_sync_count,
            "save_outcomes": save_outcomes,
            "skip_reasons": skip_reasons,
            "hot_deals": len(hot_deals),
            "hot_deal_vehicles": [
                f"{v.get('year')} {v.get('make')} {v.get('model')} | "
                f"{v.get('score_breakdown', {}).get('investment_grade', 'Watch')} | "
                f"Score={v['dos_score']} | ${v.get('current_bid'):,.0f}"
                for v in hot_deals
            ],
        }
        try:
            update_webhook_log(
                webhook_log_id,
                "processed" if failed_save_count == 0 else "degraded",
                item_count=dataset_item_count,
                error_message=(
                    None if failed_save_count == 0
                    else f"save_outcomes={save_outcomes}; skip_reasons={skip_reasons}"
                ),
            )
        except Exception as e:
            logger.warning(f"[WEBHOOK_LOG] update failed (non-fatal): {e}")
        return response
    except HTTPException as e:
        try:
            update_webhook_log(webhook_log_id, "error", error_message=str(e.detail))
        except Exception as update_error:
            logger.warning(f"[WEBHOOK_LOG] error update failed (non-fatal): {update_error}")
        raise
    except Exception as e:
        try:
            update_webhook_log(webhook_log_id, "error", error_message=str(e))
        except Exception as update_error:
            logger.warning(f"[WEBHOOK_LOG] error update failed (non-fatal): {update_error}")
        raise


def _normalize_auction_end_time(raw_value, *, reference_dt: Optional[datetime] = None) -> Optional[str]:
    if raw_value in {None, ""}:
        return None
    if isinstance(raw_value, datetime):
        dt = _parse_datetime_utc(raw_value)
        return dt.isoformat() if dt else None

    text = str(raw_value).strip()
    if not text:
        return None

    parsed_absolute = _parse_datetime_utc(text)
    if parsed_absolute:
        return parsed_absolute.isoformat()

    lower_text = text.lower()
    total_delta = timedelta(0)
    matched = False
    for pattern, unit in (
        (r"(\d+)\s*day", "days"),
        (r"(\d+)\s*hour", "hours"),
        (r"(\d+)\s*min", "minutes"),
    ):
        match = re.search(pattern, lower_text)
        if match:
            matched = True
            total_delta += timedelta(**{unit: int(match.group(1))})

    if matched:
        anchor = reference_dt or _parse_datetime_utc(datetime.utcnow())
        if anchor is None:
            return None
        return (anchor + total_delta).astimezone(timezone.utc).isoformat()

    return None


def normalize_apify_vehicle(item: dict, run_id: str, *, default_time_anchor: Optional[datetime] = None) -> Optional[dict]:
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
        time_anchor = (
            _parse_datetime_utc(item.get("scraped_at") or item.get("scrapedAt") or item.get("createdAt"))
            or default_time_anchor
        )
        auction_end = _normalize_auction_end_time(
            item.get("auctionEndUtc") or
            item.get("auction_end_time") or
            item.get("auction_end_date") or
            item.get("auction_end"),
            reference_dt=time_anchor,
        )

        # URL: parseforge uses url, ours uses listing_url
        listing_url = item.get("url") or item.get("listing_url") or ""

        # Photo: parseforge uses imageUrl or photos[]
        photos = item.get("photos", [])
        photo_url = (
            item.get("image_url") or item.get("photo_url") or
            item.get("imageUrl") or (photos[0] if photos else "")
        )

        # Agency: parseforge uses seller
        agency = item.get("seller") or item.get("agency_name") or ""

        # Source
        source = item.get("source_site") or item.get("source") or "govdeals"

        normalized = {
            "title": title,
            "title_status": item.get("title_status") or item.get("titleStatus") or "",
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


def _alert_gate_for_vehicle(vehicle: dict) -> dict:
    gate = evaluate_alert_gate(vehicle, thresholds=_alert_thresholds())
    vehicle["alert_gate"] = gate
    return gate


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
    return _estimate_mmr_details(make, model)["mmr"]


def _estimate_mmr_details(make: str, model: str) -> dict:
    """
    Estimate MMR by model-level lookup first, then make fallback.
    Far more accurate than segment-only — a Ford Explorer ≠ a Ford Econoline.
    """
    model_lower = (model or "").lower().strip()
    make_lower = (make or "").lower().strip()

    # 1. Direct model lookup (most accurate)
    for key in sorted(_MODEL_MMR, key=len, reverse=True):
        val = _MODEL_MMR[key]
        if key in model_lower or model_lower in key:
            return {"mmr": float(val), "basis": f"model:{key}", "confidence_proxy": 90.0}

    # 2. Police/interceptor check
    if any(t in model_lower for t in ["interceptor", "ppv", "police", "pursuit"]):
        return {"mmr": 22000.0, "basis": "special:police_interceptor", "confidence_proxy": 62.0}

    # 3. Commercial vehicle detection — low MMR
    if any(t in model_lower for t in ["cargo", "cutaway", "chassis cab", "box truck",
                                       "econoline", "promaster", "sprinter", "express",
                                       "transit connect", "e-250", "e-350", "g2500",
                                       "g3500", "4500", "5500"]):
        return {"mmr": 9000.0, "basis": "special:commercial_vehicle", "confidence_proxy": 50.0}

    # 4. Make-level fallback
    if make_lower in _MAKE_SEGMENT_MMR:
        return {
            "mmr": float(_MAKE_SEGMENT_MMR[make_lower]),
            "basis": f"make:{make_lower}",
            "confidence_proxy": 72.0,
        }

    # 5. Segment fallback (legacy)
    segment = _MAKE_SEGMENT.get(make_lower, "sedan_other")
    return {
        "mmr": float(_SEGMENT_MMR.get(segment, 16000)),
        "basis": f"segment:{segment}",
        "confidence_proxy": 45.0,
    }


def passes_basic_gates(vehicle: dict) -> dict:
    """
    Five-layer institutional filter.
    Returns {"pass": bool, "reason": str}
    """
    # Layer 0: Must be an actual vehicle (has make OR VIN — rejects equipment/parts)
    make = vehicle.get("make", "") or ""
    vin = vehicle.get("vin", "") or ""
    if not make.strip() and len(vin) != 17:
        return {"pass": False, "reason": "not_a_vehicle (no make or valid VIN)"}

    bid = vehicle.get("current_bid", 0)
    state = vehicle.get("state", "")
    year = vehicle.get("year")
    mileage = vehicle.get("mileage")

    # Government sources often have lower opening bids on older fleet vehicles
    gov_sources_bid = {"publicsurplus", "govdeals", "gsaauctions"}
    source_bid = (vehicle.get("source_site") or "").lower()
    min_bid = 500 if source_bid in gov_sources_bid else 3000
    if bid < min_bid or bid > 35000:
        return {"pass": False, "reason": f"bid_out_of_range (${bid:,.0f})"}

    # Reject non-US states (Canadian provinces, garbage codes)
    if state and state not in US_STATES:
        return {"pass": False, "reason": f"non_us_state ({state})"}

    if state in HIGH_RUST_STATES:
        return {"pass": False, "reason": f"high_rust_state ({state})"}

    title_brand_issue = _find_title_brand_issue(vehicle)
    if title_brand_issue:
        return {"pass": False, "reason": title_brand_issue}

    # Reject commercial/fleet vehicles (cargo vans, box trucks, cutaways)
    title = (vehicle.get("title") or "").strip()
    if any(re.search(p, title, re.IGNORECASE) for p in _COMMERCIAL_PATTERNS):
        return {"pass": False, "reason": f"commercial_vehicle ({title[:50]})"}

    if not year:
        return {"pass": False, "reason": "no_year"}

    current_year = datetime.now().year
    age = current_year - year
    # Government/public auction sources run older fleet vehicles — allow up to 12 years
    gov_sources = {"publicsurplus", "govdeals", "gsaauctions"}
    source = (vehicle.get("source_site") or "").lower()
    max_age = 12 if source in gov_sources else 4
    if age > max_age or age < 0:
        return {"pass": False, "reason": f"age_exceeded ({age} years, max {max_age} for {source})"}

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
        from backend.ingest.manheim_market import get_manheim_market_data
        from backend.ingest.retail_comps import get_retail_comps

        bid = vehicle.get("current_bid", 0)
        state = vehicle.get("state", "")
        source = vehicle.get("source_site", "GovDeals")
        SOURCE_MAP = {
            "govdeals": "GovDeals",
            "publicsurplus": "PublicSurplus",
            "gsaauctions": "GSAAuctions",
            "municibid": "Municibid",
            "govplanet": "GovPlanet",
        }
        source_site = SOURCE_MAP.get((source or "").lower(), source)
        make = vehicle.get("make", "")
        model = vehicle.get("model", "")
        year = vehicle.get("year")
        mileage = vehicle.get("mileage")
        police_fleet_text = " ".join(
            str(vehicle.get(field) or "").lower()
            for field in ("title", "model", "agency_name")
        )
        is_police_or_fleet = any(
            term in police_fleet_text
            for term in ("police", "interceptor", "ppv", "pursuit", "fleet")
        )
        mmr_details = _estimate_mmr_details(make, model)
        manheim_result = get_manheim_market_data(
            year=year,
            make=make,
            model=model,
            state=state,
            mileage=mileage,
            proxy_mmr=mmr_details.get("mmr"),
            proxy_basis=mmr_details.get("basis"),
            proxy_confidence=mmr_details.get("confidence_proxy"),
        )
        mmr = manheim_result.get("manheim_mmr_mid") or mmr_details["mmr"]
        mmr_lookup_basis = (
            "manheim_live"
            if manheim_result.get("manheim_source_status") == "live"
            else mmr_details.get("basis")
        )
        retail_comp_result = get_retail_comps(
            year=year,
            make=make,
            model=model,
            state=state,
            supabase_client=supabase_client,
        )

        result = score_deal(
            bid=bid,
            mmr_ca=mmr,
            state=state,
            source_site=source_site,
            model=model,
            make=make,
            year=year,
            mileage=mileage,
            is_police_or_fleet=is_police_or_fleet,
            auction_end=vehicle.get("auction_end_time"),
            mmr_lookup_basis=mmr_lookup_basis,
            mmr_confidence_proxy=mmr_details.get("confidence_proxy"),
            retail_comp_price_estimate=retail_comp_result.get("retail_comp_price_estimate"),
            retail_comp_low=retail_comp_result.get("retail_comp_low"),
            retail_comp_high=retail_comp_result.get("retail_comp_high"),
            retail_comp_count=retail_comp_result.get("retail_comp_count"),
            retail_comp_confidence=retail_comp_result.get("retail_comp_confidence"),
            pricing_source=retail_comp_result.get("pricing_source"),
            pricing_updated_at=retail_comp_result.get("pricing_updated_at"),
            manheim_mmr_mid=manheim_result.get("manheim_mmr_mid"),
            manheim_mmr_low=manheim_result.get("manheim_mmr_low"),
            manheim_mmr_high=manheim_result.get("manheim_mmr_high"),
            manheim_range_width_pct=manheim_result.get("manheim_range_width_pct"),
            manheim_confidence=manheim_result.get("manheim_confidence"),
            manheim_source_status=manheim_result.get("manheim_source_status"),
            manheim_updated_at=manheim_result.get("manheim_updated_at"),
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
    auction_stage_hours_remaining = None
    current_bid_trust_score = None
    pricing_maturity = "proxy"
    try:
        from backend.ingest.score import (
            _auction_stage_hours_remaining,
            _current_bid_trust_score,
            _round_price_basis,
        )

        auction_stage_hours_remaining = _auction_stage_hours_remaining(vehicle.get("auction_end_time"))
        current_bid_trust_score = _current_bid_trust_score(
            auction_stage_hours_remaining=auction_stage_hours_remaining,
            pricing_maturity=pricing_maturity,
        )
        acquisition_price_basis = _round_price_basis(vehicle.get("current_bid") or 0)
    except Exception:
        acquisition_price_basis = vehicle.get("current_bid") or 0
        pass
    return {
        "dos_score": min(100, round(score, 1)),
        "score": min(100, round(score, 1)),
        "legacy_dos_score": min(100, round(score, 1)),
        "score_version": "fallback_v1",
        "mmr_estimated": 0,
        "margin": 0,
        "gross_margin": 0,
        "wholesale_margin": 0,
        "retail_asking_price_estimate": 0,
        "retail_comp_price_estimate": None,
        "retail_comp_low": None,
        "retail_comp_high": None,
        "retail_comp_count": 0,
        "retail_comp_confidence": None,
        "pricing_source": "mmr_proxy",
        "pricing_maturity": pricing_maturity,
        "pricing_updated_at": None,
        "expected_close_bid": acquisition_price_basis,
        "expected_close_source": "fallback_current_bid_only",
        "current_bid_trust_score": current_bid_trust_score,
        "auction_stage_hours_remaining": auction_stage_hours_remaining,
        "acquisition_price_basis": acquisition_price_basis,
        "acquisition_basis_source": "current_bid_fallback",
        "projected_total_cost": acquisition_price_basis,
        "manheim_mmr_mid": None,
        "manheim_mmr_low": None,
        "manheim_mmr_high": None,
        "manheim_range_width_pct": None,
        "manheim_confidence": None,
        "manheim_source_status": "unavailable",
        "manheim_updated_at": None,
        "retail_proxy_multiplier": 1.35,
        "wholesale_ctm_pct": None,
        "retail_ctm_pct": None,
        "ctm_pct": None,
        "estimated_days_to_sale": None,
        "roi_per_day": None,
        "investment_grade": None,
        "bid_ceiling_pct": None,
        "max_bid": 0,
        "bid_headroom": 0,
        "ceiling_reason": "fallback_score",
        "ceiling_pass": True,
    }


async def sync_to_notion(vehicle: dict) -> bool:
    """Push a scored deal to the Notion Dealerscope Deals database."""
    notion_token = os.getenv("NOTION_TOKEN", "")
    notion_db_id = os.getenv("NOTION_DEALS_DB_ID", "")
    if not notion_token or not notion_db_id:
        return False

    listing_url = vehicle.get("listing_url") or ""

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
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            if listing_url:
                query_resp = await client.post(
                    f"https://api.notion.com/v1/databases/{notion_db_id}/query",
                    headers=headers,
                    json={
                        "filter": {
                            "property": "Listing URL",
                            "url": {"equals": listing_url},
                        },
                        "page_size": 1,
                    },
                )
                if query_resp.status_code == 200:
                    existing_results = query_resp.json().get("results") or []
                    if existing_results:
                        logger.info("[NOTION] Existing page found for listing_url=%s; skipping create", listing_url)
                        return True
                else:
                    logger.warning(f"[NOTION] Query failed: {query_resp.status_code} {query_resp.text[:200]}")

            resp = await client.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
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
    if os.getenv("ALERTS_ENABLED", "false").lower() != "true":
        logger.info("[ALERTS DISABLED] skipping alert")
        return None

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[TELEGRAM] Missing bot token or chat ID; skipping alert")
        return None

    opp_id = deal.get("opportunity_id")

    # 6-hour suppression check
    if supabase_client is not None and opp_id:
        try:
            alert_suppression_cutoff = (datetime.utcnow() - timedelta(hours=6)).isoformat()
            recent = (
                supabase_client.table("alert_log")
                .select("id")
                .eq("opportunity_id", opp_id)
                .gte("sent_at", alert_suppression_cutoff)
                .execute()
            )
            if recent.data:
                logger.info("[ALERT SUPPRESSED] already alerted within 6hrs")
                return None
        except Exception as e:
            logger.warning(f"[SUPPRESSION CHECK] failed: {e}")

    # Per-run alert cap (max 5)
    run_id = deal.get("run_id", "unknown")
    if alerts_this_run.get(run_id, 0) >= 5:
        logger.info(f"[ALERT CAP] max alerts reached for run {run_id}")
        return None
    alerts_this_run[run_id] = alerts_this_run.get(run_id, 0) + 1

    try:
        import httpx

        callback_id = opp_id or "unknown"
        score_breakdown = deal.get("score_breakdown", {})
        investment_grade = score_breakdown.get("investment_grade") or "Watch"
        roi_per_day = float(score_breakdown.get("roi_per_day") or 0)
        headroom = float(score_breakdown.get("bid_headroom") or 0)
        alert_gate = deal.get("alert_gate")
        if not isinstance(alert_gate, dict):
            alert_gate = _alert_gate_for_vehicle(deal)
        if not alert_gate.get("eligible"):
            logger.info(
                "[ALERT_GATE] send skipped | %s | reasons=%s | %s",
                alert_gate.get("summary"),
                ",".join(alert_gate.get("blocking_reasons") or ["unknown"]),
                deal.get("title", "?")[:80],
            )
            return None
        is_platinum = alert_gate.get("alert_type") == "platinum"
        gate_signals = alert_gate.get("signals", {})
        pricing_maturity = gate_signals.get("pricing_maturity") or score_breakdown.get("pricing_maturity") or "unknown"
        pricing_source = gate_signals.get("pricing_source") or score_breakdown.get("pricing_source") or "unknown"
        trust_score = gate_signals.get("current_bid_trust_score")
        confidence = gate_signals.get("confidence")
        expected_close_source = gate_signals.get("expected_close_source") or score_breakdown.get("expected_close_source") or "unknown"
        acquisition_basis_source = gate_signals.get("acquisition_basis_source") or score_breakdown.get("acquisition_basis_source") or "unknown"
        mmr_lookup_basis = gate_signals.get("mmr_lookup_basis") or score_breakdown.get("mmr_lookup_basis") or "unknown"
        retail_comp_count = gate_signals.get("retail_comp_count")
        retail_comp_confidence = gate_signals.get("retail_comp_confidence")
        truth_note = ""
        if pricing_maturity == "proxy":
            truth_note = (
                f"Proxy-priced: expected close and basis are synthetic ({mmr_lookup_basis})\n"
            )
        elif retail_comp_count is not None:
            truth_note = (
                "Retail evidence: "
                f"count={int(float(retail_comp_count))}, "
                f"conf={retail_comp_confidence if retail_comp_confidence is not None else 'n/a'}\n"
            )
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🔥 BUY", "callback_data": f"buy_{callback_id}"},
                {"text": "👀 WATCH", "callback_data": f"watch_{callback_id}"},
                {"text": "❌ PASS", "callback_data": f"pass_{callback_id}"},
            ]]
        }

        if is_platinum:
            msg = (
                f"💎 *PLATINUM ALERT*\n"
                f"{deal.get('year')} {deal.get('make')} {deal.get('model')}\n"
                f"Grade: *{investment_grade}* | Score: *{deal['dos_score']}*\n"
                f"ROI/Day: ${roi_per_day:,.0f} | Headroom: ${headroom:,.0f}\n"
                f"Bid: ${deal.get('current_bid', 0):,.0f} | Max Bid: ${score_breakdown.get('max_bid', 0):,.0f}\n"
                f"Pricing: {pricing_maturity} via {pricing_source} | Trust: {trust_score if trust_score is not None else 'n/a'} | Conf: {confidence if confidence is not None else 'n/a'}\n"
                f"Expected Close: {expected_close_source}\n"
                f"Basis: {acquisition_basis_source}\n"
                f"{truth_note}"
                f"State: {deal.get('state', '?')}\n"
                f"[View Listing]({deal.get('listing_url', '')})"
            )
        else:
            msg = (
                f"🔥 *HOT DEAL ALERT*\n"
                f"{deal.get('year')} {deal.get('make')} {deal.get('model')}\n"
                f"Grade: *{investment_grade}* | Score: *{deal['dos_score']}*\n"
                f"Bid: ${deal.get('current_bid', 0):,.0f}\n"
                f"Pricing: {pricing_maturity} via {pricing_source} | Trust: {trust_score if trust_score is not None else 'n/a'} | Conf: {confidence if confidence is not None else 'n/a'}\n"
                f"Expected Close: {expected_close_source}\n"
                f"Basis: {acquisition_basis_source}\n"
                f"{truth_note}"
                f"State: {deal.get('state', '?')}\n"
                f"Gross: ${score_breakdown.get('gross_margin', 0):,.0f}\n"
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

    # Also send to Slack #general (non-blocking — never fail the Telegram receipt on Slack error)
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    slack_channel = os.getenv("SLACK_CHANNEL_ID", "C0ALM52FV25")
    if slack_token:
        try:
            prefix = "💎 *PLATINUM*" if is_platinum else "🔥 *HOT DEAL*"
            slack_text = (
                f"{prefix} | {deal.get('year')} {deal.get('make')} {deal.get('model')} "
                f"| {investment_grade} | Score {deal['dos_score']} | ${deal.get('current_bid', 0):,.0f} "
                f"| {deal.get('state', '?')} | <{deal.get('listing_url', '')}|View>"
            )
            async with httpx.AsyncClient(timeout=5.0) as sc:
                slack_resp = await sc.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {slack_token}"},
                    json={"channel": slack_channel, "text": slack_text},
                )
                if not slack_resp.json().get("ok"):
                    logger.warning(f"[SLACK] Alert not ok: {slack_resp.json().get('error')}")
                else:
                    logger.info(f"[SLACK] Alert sent for {deal.get('make')} {deal.get('model')}")
        except Exception as e:
            logger.warning(f"[SLACK] Alert failed (non-fatal): {e}")

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
        "sent_at": datetime.utcnow().isoformat(),
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
    for deal in hot_deals:
        await send_telegram_alert(deal)


def _prepare_direct_pg_value(value):
    if isinstance(value, dict):
        return psycopg2_extras.Json(value)
    return value


def _increment_reason_counter(counter: dict, reason: str) -> None:
    counter[reason] = counter.get(reason, 0) + 1


def _compute_listing_id(source: str, listing_url: str) -> str:
    normalized_source = (source or "unknown").strip().lower()
    normalized_url = (listing_url or "").strip()
    return hashlib.sha256(f"{normalized_source}|{normalized_url}".encode()).hexdigest()[:40]


def _lookup_existing_opportunity_id(listing_url: str, listing_id: str) -> Optional[str]:
    if supabase_client is not None:
        try:
            if listing_url:
                lookup = (
                    supabase_client.table("opportunities")
                    .select("id")
                    .eq("listing_url", listing_url)
                    .limit(1)
                    .execute()
                )
                if lookup.data:
                    return lookup.data[0].get("id")
            if listing_id:
                lookup = (
                    supabase_client.table("opportunities")
                    .select("id")
                    .eq("listing_id", listing_id)
                    .limit(1)
                    .execute()
                )
                if lookup.data:
                    return lookup.data[0].get("id")
        except Exception as lookup_err:
            logger.warning("[INGEST] Supabase lookup fallback failed: %s", lookup_err)

    if not _direct_supabase_db_url:
        return None

    try:
        with psycopg2.connect(_direct_supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id
                    from public.opportunities
                    where listing_url = %s or listing_id = %s
                    limit 1
                    """,
                    (listing_url, listing_id),
                )
                row = cur.fetchone()
                return str(row[0]) if row and row[0] else None
    except Exception as lookup_err:
        logger.warning("[INGEST] Direct PG lookup fallback failed: %s", lookup_err)
        return None


def _save_opportunity_direct_pg(row: dict) -> tuple[Optional[str], str]:
    if not _direct_supabase_db_url:
        logger.warning(
            "[INGEST] Direct PG fallback unavailable; set SUPABASE_DB_URL or SUPABASE_DB_PASSWORD."
        )
        return None, "direct_pg_unavailable"

    columns = list(row.keys())
    values = [_prepare_direct_pg_value(row[column]) for column in columns]
    insert_sql = psycopg2_sql.SQL(
        "INSERT INTO public.opportunities ({fields}) VALUES ({values}) RETURNING id"
    ).format(
        fields=psycopg2_sql.SQL(", ").join(psycopg2_sql.Identifier(column) for column in columns),
        values=psycopg2_sql.SQL(", ").join(psycopg2_sql.Placeholder() for _ in columns),
    )

    try:
        with psycopg2.connect(_direct_supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(insert_sql, values)
                inserted = cur.fetchone()
                return (str(inserted[0]) if inserted and inserted[0] else None), "saved_direct_pg"
    except psycopg2.errors.UniqueViolation:
        existing_id = _lookup_existing_opportunity_id(row["listing_url"], row["listing_id"])
        if existing_id:
            return existing_id, "duplicate_existing"
        return None, "duplicate_unresolved"
    except Exception as pg_err:
        logger.error(
            "[INGEST] Direct PG save FAILED for '%s': %s",
            (row.get("title") or "unknown")[:80],
            pg_err,
        )
        return None, "direct_pg_error"


async def save_opportunity_to_supabase(vehicle: dict) -> Optional[str]:
    """Save scored vehicle to Supabase. Min DOS 50 to save."""
    score = vehicle.get("dos_score", 0)
    if score < 50:
        vehicle["_save_status"] = "below_save_threshold"
        return None

    row = build_opportunity_row(vehicle)

    if supabase_client is not None:
        try:
            result = supabase_client.table("opportunities").insert(row).execute()
            if result.data:
                vehicle["_save_status"] = "saved_supabase"
                return result.data[0].get("id")

            existing_id = _lookup_existing_opportunity_id(row["listing_url"], row["listing_id"])
            if existing_id:
                vehicle["_save_status"] = "duplicate_existing"
                return existing_id
        except Exception as e:
            title = vehicle.get("title", "unknown")[:80]
            logger.error(f"[INGEST] Supabase save FAILED for '{title}': {e}")
            error_text = str(e)
            if "23505" in error_text or "duplicate key value" in error_text:
                existing_id = _lookup_existing_opportunity_id(row["listing_url"], row["listing_id"])
                if existing_id:
                    logger.info("[INGEST] Duplicate existing listing recovered for '%s'", title)
                    vehicle["_save_status"] = "duplicate_existing"
                    return existing_id
                vehicle["_save_status"] = "duplicate_unresolved"
                return None
            if "PGRST204" not in error_text:
                vehicle["_save_status"] = "supabase_error"
                return None
            logger.warning(
                "[INGEST] Falling back to direct Postgres insert for '%s' after PostgREST schema error.",
                title,
            )
    else:
        logger.warning("[INGEST] Supabase client unavailable; using direct Postgres fallback if configured.")

    saved_id, save_status = _save_opportunity_direct_pg(row)
    vehicle["_save_status"] = save_status
    return saved_id


def build_opportunity_row(vehicle: dict) -> dict:
    score_result = vehicle.get("score_breakdown", {})
    current_bid = float(vehicle.get("current_bid") or 0)
    buyer_premium = score_result.get("buyer_premium_amount")
    if buyer_premium is None:
        buyer_premium = score_result.get("premium")
    if buyer_premium is None:
        buyer_premium = current_bid * 0.125
    buyer_premium_pct = score_result.get("buyer_premium_pct")
    if buyer_premium_pct is None:
        premium_basis = score_result.get("buyer_premium_amount")
        if premium_basis is None:
            premium_basis = score_result.get("premium")
        if premium_basis is not None and current_bid > 0:
            buyer_premium_pct = float(premium_basis) / current_bid
        else:
            buyer_premium_pct = 0.125
    else:
        buyer_premium_pct = float(buyer_premium_pct)
        if buyer_premium_pct > 1:
            buyer_premium_pct /= 100.0
    projected_buyer_premium = score_result.get("buyer_premium_amount")
    if projected_buyer_premium is None:
        projected_buyer_premium = score_result.get("premium")
    if projected_buyer_premium is not None:
        buyer_premium = round(float(projected_buyer_premium), 2)
    else:
        buyer_premium = round(current_bid * buyer_premium_pct, 2)
    doc_fee = float(score_result.get("doc_fee", 75) or 75)
    auction_fees = round(doc_fee, 2)
    condition_grade = _compute_condition_grade(
        title=vehicle.get("title") or "",
        description=vehicle.get("description") or "",
        mileage=vehicle.get("mileage") or 0,
        year=vehicle.get("year") or 0,
        damage_type=vehicle.get("damage_type") or "",
    )
    pricing_source = score_result.get("pricing_source")
    pricing_maturity = score_result.get("pricing_maturity") or "unknown"
    return {
        "listing_id": _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
        "listing_url": vehicle.get("listing_url", ""),
        "source": vehicle.get("source_site"),
        "title": vehicle.get("title"),
        "year": vehicle.get("year"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "mileage": vehicle.get("mileage"),
        "state": vehicle.get("state"),
        "city": vehicle.get("city") or vehicle.get("location_city") or "",
        "vin": vehicle.get("vin"),
        "current_bid": vehicle.get("current_bid"),
        "mmr": score_result.get("mmr_estimated"),
        "estimated_transport": score_result.get("transport"),
        "buyer_premium": buyer_premium,
        "auction_fees": auction_fees,
        "recon_reserve": score_result.get("recon_reserve"),
        "total_cost": score_result.get("total_cost"),
        "projected_total_cost": score_result.get("projected_total_cost", score_result.get("total_cost")),
        "acquisition_price_basis": score_result.get("acquisition_price_basis"),
        "acquisition_basis_source": score_result.get("acquisition_basis_source"),
        "gross_margin": score_result.get("gross_margin", score_result.get("margin")),
        "retail_asking_price_estimate": score_result.get("retail_asking_price_estimate"),
        "retail_comp_price_estimate": score_result.get("retail_comp_price_estimate"),
        "retail_comp_low": score_result.get("retail_comp_low"),
        "retail_comp_high": score_result.get("retail_comp_high"),
        "retail_comp_count": score_result.get("retail_comp_count"),
        "retail_comp_confidence": score_result.get("retail_comp_confidence"),
        "pricing_source": pricing_source,
        "pricing_maturity": pricing_maturity,
        "pricing_updated_at": score_result.get("pricing_updated_at"),
        "expected_close_bid": score_result.get("expected_close_bid"),
        "current_bid_trust_score": score_result.get("current_bid_trust_score"),
        "expected_close_source": score_result.get("expected_close_source"),
        "auction_stage_hours_remaining": score_result.get("auction_stage_hours_remaining"),
        "manheim_mmr_mid": score_result.get("manheim_mmr_mid"),
        "manheim_mmr_low": score_result.get("manheim_mmr_low"),
        "manheim_mmr_high": score_result.get("manheim_mmr_high"),
        "manheim_range_width_pct": score_result.get("manheim_range_width_pct"),
        "manheim_confidence": score_result.get("manheim_confidence"),
        "manheim_source_status": score_result.get("manheim_source_status"),
        "manheim_updated_at": score_result.get("manheim_updated_at"),
        "retail_proxy_multiplier": score_result.get("retail_proxy_multiplier"),
        "dos_score": vehicle.get("dos_score"),
        "ctm_pct": score_result.get("ctm_pct"),
        "wholesale_ctm_pct": score_result.get("wholesale_ctm_pct"),
        "retail_ctm_pct": score_result.get("retail_ctm_pct"),
        "segment_tier": score_result.get("segment_tier"),
        "estimated_days_to_sale": score_result.get("estimated_days_to_sale"),
        "roi_per_day": score_result.get("roi_per_day"),
        "mmr_lookup_basis": score_result.get("mmr_lookup_basis"),
        "mmr_confidence_proxy": score_result.get("mmr_confidence_proxy"),
        "investment_grade": score_result.get("investment_grade"),
        "bid_ceiling_pct": score_result.get("bid_ceiling_pct"),
        "max_bid": score_result.get("max_bid"),
        "bid_headroom": score_result.get("bid_headroom"),
        "ceiling_reason": score_result.get("ceiling_reason"),
        "score_version": score_result.get("score_version"),
        "legacy_dos_score": score_result.get("legacy_dos_score"),
        "condition_grade": condition_grade,
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
