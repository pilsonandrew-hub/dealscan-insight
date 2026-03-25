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
from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from typing import Any, Optional
import hmac
import hashlib
import re
import os
import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import psycopg2
from psycopg2 import extras as psycopg2_extras
from psycopg2 import sql as psycopg2_sql

from backend.ingest.webhook_secret_posture import build_webhook_secret_posture
from backend.ingest.alert_gating import AlertThresholds, evaluate_alert_gate

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

try:
    from backend.ingest.condition import compute_condition_grade as _compute_condition_grade
except ImportError:
    def _compute_condition_grade(**kwargs):  # type: ignore[misc]
        return None

import time as _time

alerts_this_run: dict[str, int] = {}
alerts_this_run_ts: dict[str, float] = {}
AUDIT_FALLBACK_MARKER = "audit_fallbacks="


class CriticalAuditWriteError(RuntimeError):
    pass


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value in {None, ""}:
        return default
    try:
        return float(raw_value)
    except ValueError:
        logger.warning("[ALERT_GATE] Invalid %s=%r; using %s", name, raw_value, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value in {None, ""}:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("[INGEST_AUTH] Invalid %s=%r; using %s", name, raw_value, default)
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

WEBHOOK_SECRET = os.getenv("APIFY_WEBHOOK_SECRET", "").strip()
WEBHOOK_SECRET_PREVIOUS = os.getenv("APIFY_WEBHOOK_SECRET_PREVIOUS", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
# DeepSeek direct API (preferred over OpenRouter for deal validation)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
# ALERT CONTROL PLANE: FastAPI -> Telegram directly
# Decision: 2026-03-11, keep FastAPI direct, not OpenClaw messaging
# Reason: already deployed, working, single path

# Prefer backend-only env vars; fall back to VITE_* for compatibility during transition
_supabase_url = (
    os.getenv("SUPABASE_URL")
    or os.getenv("VITE_SUPABASE_URL")
) or None
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


def _apify_api_token() -> str:
    return (os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN") or "").strip()


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
        f"postgresql://postgres:{quote(db_password, safe='')}"
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
# NOTE: \b2500\b and \b3500\b removed — they incorrectly blocked Ram 2500, Silverado 2500,
# Sierra 2500, Ram 3500 etc. (desirable HD pickup trucks). Use _is_commercial_hd_tonnage()
# below to detect cargo-truck context for those numerals instead.
_COMMERCIAL_PATTERNS = [
    r"\bEconoline\b", r"\bExpress\s*Cargo\b", r"\bProMaster\s*Cargo\b",
    r"\bSprinter\s*Cargo\b", r"\bTransit\s*Cargo\b", r"\bSavana\s*Cargo\b",
    r"\bE-250\b", r"\bE-350\b", r"\b4500\b", r"\b5500\b",
    r"\bCutaway\b", r"\bChassis\s*Cab\b",
    r"\bDump\s*Truck\b", r"\bBox\s*Truck\b", r"\bBucket\s*Truck\b",
    r"\bStake\s*Bed\b", r"\bFlatbed\b", r"\bStep\s*Van\b", r"\bShuttle\b",
    r"\bUtility\s*Bed\b", r"\bRefrigerator\s*Truck\b",
]

# HD pickup truck makes — 2500/3500 suffixes on these are valid pickup trucks
_HD_PICKUP_MAKES = re.compile(
    r"\b(Ram|Chevy|Chevrolet|Silverado|GMC|Sierra|Ford|F-250|F-350)\b",
    re.IGNORECASE,
)


def _is_commercial_hd_tonnage(title: str) -> bool:
    """Return True only if title contains a cargo/commercial 2500 or 3500 (not a pickup truck).

    Blocks: "G2500 Cargo Van", "G3500 Express Cargo" etc.
    Allows: "Ram 2500 Big Horn", "Silverado 2500 HD", "Sierra 3500 Crew Cab", "F-350 XLT"
    """
    has_hd_numeral = bool(re.search(r"\b[23]500\b", title, re.IGNORECASE))
    if not has_hd_numeral:
        return False
    # If the title also mentions a known HD pickup make/model, it's a pickup — allow it
    if _HD_PICKUP_MAKES.search(title):
        return False
    # No pickup make context → likely a cargo/commercial van or cab-chassis → block it
    return True

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
        return {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}

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
                    "canonical_update": None,
                }

        if not canonical_id:
            return {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}

        result = (
            supabase_client.table("opportunities")
            .select("id, all_sources")
            .eq("canonical_id", canonical_id)
            .eq("is_duplicate", False)
            .limit(1)
            .execute()
        )
        if not result.data:
            return {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}

        existing = result.data[0]
        existing_id = existing["id"]
        existing_sources = existing.get("all_sources") or []
        canonical_update = None
        if new_source and new_source not in existing_sources:
            updated = existing_sources + [new_source]
            canonical_update = {
                "id": existing_id,
                "all_sources": updated,
                "duplicate_count": len(updated) - 1,
            }
        return {"is_duplicate": True, "canonical_record_id": existing_id, "canonical_update": canonical_update}
    except Exception as lookup_error:
        logger.warning(f"[DEDUP] check failed: {lookup_error}")
        return {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}


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
        "dataset_id": (
            resource.get("defaultDatasetId")
            or payload.get("defaultDatasetId")
            or payload.get("datasetId")
        ),
        "item_count": item_count,
        "created_at": _parse_datetime_utc(
            payload.get("createdAt") or resource.get("createdAt") or resource.get("startedAt")
        ),
    }


def insert_webhook_log(
    payload: dict,
    *,
    processing_status: str = "pending",
    error_message: Optional[str] = None,
    require_durable: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    metadata = extract_apify_webhook_metadata(payload)
    row = {
        "source": metadata["source"],
        "actor_id": metadata["actor_id"],
        "run_id": metadata["run_id"],
        "item_count": metadata["item_count"],
        "raw_payload": payload,
        "processing_status": processing_status,
        "error_message": error_message,
    }
    primary_error: Optional[Exception] = None
    if supabase_client is not None:
        try:
            result = supabase_client.table("webhook_log").insert(row).execute()
            if result.data:
                return result.data[0].get("id")
        except Exception as exc:
            primary_error = exc

    try:
        fallback_label = "webhook_log_insert_direct_pg"
        fallback_row = dict(row)
        fallback_row["error_message"] = _merge_audit_error_message(
            fallback_row.get("error_message"),
            [fallback_label],
        )
        inserted_id = _insert_webhook_log_direct_pg(fallback_row)
        _record_audit_fallback(audit_state, fallback_label)
        return inserted_id
    except Exception as fallback_error:
        if require_durable:
            raise CriticalAuditWriteError(
                _format_audit_failure(
                    surface="webhook_log",
                    operation="insert",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning("[WEBHOOK_LOG] insert failed: %s", primary_error)
        logger.warning("[WEBHOOK_LOG] direct PG fallback failed: %s", fallback_error)
        return None


def update_webhook_log(
    webhook_log_id: Optional[str],
    processing_status: str,
    *,
    error_message: Optional[str] = None,
    item_count: Optional[int] = None,
    require_durable: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> None:
    if not webhook_log_id:
        if require_durable:
            raise CriticalAuditWriteError("critical webhook_log update missing row id")
        return

    update_row = {
        "processing_status": processing_status,
        "error_message": error_message,
    }
    if item_count is not None:
        update_row["item_count"] = item_count

    primary_error: Optional[Exception] = None
    if supabase_client is not None:
        try:
            supabase_client.table("webhook_log").update(update_row).eq("id", webhook_log_id).execute()
            return
        except Exception as exc:
            primary_error = exc

    try:
        fallback_label = "webhook_log_update_direct_pg"
        fallback_row = dict(update_row)
        fallback_row["error_message"] = _merge_audit_error_message(
            fallback_row.get("error_message"),
            [fallback_label],
        )
        _update_webhook_log_direct_pg(webhook_log_id, fallback_row)
        _record_audit_fallback(audit_state, fallback_label)
        return
    except Exception as fallback_error:
        if require_durable:
            raise CriticalAuditWriteError(
                _format_audit_failure(
                    surface="webhook_log",
                    operation="update",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning("[WEBHOOK_LOG] update failed: %s", primary_error)
        logger.warning("[WEBHOOK_LOG] direct PG update fallback failed: %s", fallback_error)


def _configured_webhook_secret_entries() -> tuple[tuple[str, str], ...]:
    def _split_secret_values(raw_secret: str) -> list[str]:
        return [secret.strip() for secret in raw_secret.split(",") if secret.strip()]

    entries: list[tuple[str, str]] = [
        ("current", secret) for secret in _split_secret_values(WEBHOOK_SECRET)
    ]
    entries.extend(
        ("previous", secret) for secret in _split_secret_values(WEBHOOK_SECRET_PREVIOUS)
    )
    return tuple(entries)


def _webhook_secret_posture() -> dict[str, Any]:
    return build_webhook_secret_posture(WEBHOOK_SECRET, WEBHOOK_SECRET_PREVIOUS)


def _match_webhook_secret(presented_secret: Optional[str]) -> Optional[str]:
    presented = presented_secret or ""
    for label, configured_secret in _configured_webhook_secret_entries():
        if hmac.compare_digest(presented, configured_secret):
            return label
    return None


def _verify_webhook_secret(presented_secret: Optional[str]) -> bool:
    return _match_webhook_secret(presented_secret) is not None


def _webhook_replay_window_seconds() -> int:
    return max(_env_int("APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS", 3600), 0)


def _webhook_max_age_seconds() -> int:
    return max(_env_int("APIFY_WEBHOOK_MAX_AGE_SECONDS", 0), 0)


def _find_recent_webhook_replay(
    run_id: Optional[str],
    *,
    strict: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> Optional[dict]:
    replay_window_seconds = _webhook_replay_window_seconds()
    if not run_id or replay_window_seconds <= 0:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=replay_window_seconds)
    primary_error: Optional[Exception] = None
    if supabase_client is not None:
        try:
            result = (
                supabase_client.table("webhook_log")
                .select("id, received_at, processing_status, error_message")
                .eq("run_id", run_id)
                .gte("received_at", cutoff.isoformat())
                .order("received_at", desc=True)
                .limit(5)
                .execute()
            )
            rows = result.data or []
            return _select_recent_replay_row(rows)
        except Exception as exc:
            primary_error = exc

    try:
        rows = _find_recent_webhook_replay_direct_pg(run_id, cutoff)
        _record_audit_fallback(audit_state, "webhook_replay_lookup_direct_pg")
        return _select_recent_replay_row(rows)
    except Exception as fallback_error:
        if strict:
            raise CriticalAuditWriteError(
                _format_audit_failure(
                    surface="webhook_log",
                    operation="replay_lookup",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning("[INGEST_AUTH] replay lookup failed for run_id=%s: %s", run_id, primary_error)
        logger.warning("[INGEST_AUTH] direct PG replay lookup fallback failed for run_id=%s: %s", run_id, fallback_error)
        return None


def _select_recent_replay_row(rows: list[dict]) -> Optional[dict]:
    for row in rows:
        status = str(row.get("processing_status") or "").lower()
        if status in {"processed", "pending", "ignored_replay"}:
            return row
    return None


def _stale_webhook_error(metadata: dict) -> Optional[str]:
    max_age_seconds = _webhook_max_age_seconds()
    created_at = metadata.get("created_at")
    if max_age_seconds <= 0 or created_at is None:
        return None

    now = datetime.now(timezone.utc)
    age_seconds = (now - created_at).total_seconds()
    if age_seconds > max_age_seconds:
        return f"Webhook createdAt is stale ({int(age_seconds)}s old; max {max_age_seconds}s)"
    if age_seconds < -300:
        return f"Webhook createdAt is too far in the future ({int(abs(age_seconds))}s skew)"
    return None


def _request_client_ip_for_security_log(request: Request) -> str:
    try:
        from webapp.middleware.rate_limit import extract_client_ip

        return extract_client_ip(request)
    except Exception:
        return getattr(getattr(request, "client", None), "host", None) or "unknown"


def _raw_item_identity(item: Any, run_id: str, item_index: int) -> tuple[str, Optional[str]]:
    if not isinstance(item, dict):
        fallback_id = hashlib.sha256(f"{run_id}|raw|{item_index}".encode()).hexdigest()[:40]
        return fallback_id, None

    source = (item.get("source_site") or item.get("source") or "unknown").strip().lower()
    listing_url = (item.get("listing_url") or item.get("url") or "").strip() or None
    raw_listing_id = (
        item.get("listing_id")
        or item.get("assetId")
        or item.get("id")
        or item.get("url")
        or item.get("listing_url")
        or item.get("vin")
    )
    if raw_listing_id:
        listing_id = hashlib.sha256(f"{source}|{raw_listing_id}".encode()).hexdigest()[:40]
        return listing_id, listing_url

    title = (item.get("title") or "").strip()
    fallback_id = hashlib.sha256(f"{run_id}|{source}|{listing_url or title}|{item_index}".encode()).hexdigest()[:40]
    return fallback_id, listing_url


def _record_pre_save_skip(
    *,
    item: Any,
    run_id: str,
    item_index: int,
    status: str,
    error_message: Optional[str],
    audit_state: Optional[dict[str, Any]] = None,
) -> None:
    listing_id, listing_url = _raw_item_identity(item, run_id, item_index)
    _record_delivery_log(
        run_id=run_id,
        listing_id=listing_id,
        listing_url=listing_url,
        opportunity_id=None,
        channel="db_save",
        status=status,
        error_message=error_message,
        require_durable=True,
        audit_state=audit_state,
    )


async def _process_webhook_items(
    payload: dict,
    metadata: dict,
    apify_run_id: str,
    audit_state: dict,
    webhook_log_id: Any,
) -> None:
    """Background task: fetch Apify dataset and process all items."""
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
                        "[IDEMPOTENCY] run_id=%s already has existing rows — skipping duplicate batch processing",
                        apify_run_id,
                    )
                    return
            except Exception as e:
                logger.warning(f"[IDEMPOTENCY] lookup failed for run_id={apify_run_id}: {e}")

        dataset_id = metadata.get("dataset_id") or ""

        apify_token = _apify_api_token()
        if not dataset_id and apify_run_id and apify_token:
            import httpx
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
            logger.warning("[INGEST] dataset_id missing after all lookups — marking error")
            update_webhook_log(
                webhook_log_id,
                "error",
                item_count=metadata["item_count"],
                error_message=_merge_audit_error_message("dataset_id_missing", _audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

        if not re.match(r'^[a-zA-Z0-9_-]{5,50}$', dataset_id):
            logger.warning(f"[INGEST] Suspicious dataset_id rejected: {dataset_id}")
            update_webhook_log(
                webhook_log_id,
                "error",
                error_message=_merge_audit_error_message("invalid_dataset_id", _audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

        import httpx
        apify_token = _apify_api_token()
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.get(
                    f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                    params={"format": "json"},
                    headers={"Authorization": f"Bearer {apify_token}"},
                )
                resp.raise_for_status()
                items = resp.json()
        except Exception as e:
            logger.error(f"[INGEST] Failed to fetch Apify dataset {dataset_id}: {e}")
            update_webhook_log(
                webhook_log_id,
                "error",
                error_message=_merge_audit_error_message(f"fetch_failed: {e}", _audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

        if not isinstance(items, list):
            update_webhook_log(
                webhook_log_id,
                "processed",
                item_count=metadata["item_count"],
                error_message=_merge_audit_error_message(None, _audit_fallbacks(audit_state)),
                require_durable=True,
                audit_state=audit_state,
            )
            return

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

        for item_index, item in enumerate(items):
            try:
                vehicle = normalize_apify_vehicle(
                    item,
                    apify_run_id,
                    default_time_anchor=metadata.get("created_at"),
                    source_hint=metadata.get("source") or metadata.get("actor_id"),
                )
            except Exception as norm_err:
                logger.warning(f"[INGEST] item {item_index} normalize error: {norm_err}")
                skipped += 1
                _increment_reason_counter(skip_reasons, "normalize_exception")
                continue
            if vehicle is None:
                skipped += 1
                _increment_reason_counter(skip_reasons, "normalize_rejected")
                _record_pre_save_skip(
                    item=item,
                    run_id=apify_run_id,
                    item_index=item_index,
                    status="skipped_norm",
                    error_message="normalize_rejected",
                    audit_state=audit_state,
                )
                continue

            # Handle completed auction sources — write to dealer_sales for DOS calibration
            source_site = _canonical_source_site(vehicle.get("source_site") or vehicle.get("source")) or None
            vehicle["source_site"] = source_site  # persist normalized value
            vehicle["source"] = source_site
            if source_site == "govdeals-sold":
                if supabase_client is None:
                    logger.error("[INGEST] dealer_sales write skipped — supabase_client is None")
                    skipped += 1
                    continue
                try:
                    sold_row = {
                        "vin": vehicle.get("vin"),
                        "make": vehicle.get("make") or "Unknown",
                        "model": vehicle.get("model") or "Unknown",
                        "year": int(vehicle.get("year") or 0) or None,
                        "mileage": vehicle.get("mileage"),
                        "sale_price": item.get("sold_price") or vehicle.get("current_bid") or 0,
                        "sold_price": item.get("sold_price") or vehicle.get("current_bid") or 0,
                        "state": vehicle.get("state"),
                        "source_type": "govdeals_sold",
                        "source": "govdeals_sold",
                        "metadata": {"listing_url": vehicle.get("listing_url"), "run_id": apify_run_id},
                    }
                    supabase_client.table("dealer_sales").insert(sold_row).execute()
                    processed += 1
                    saved_count += 1
                    logger.info(f"[DEALER_SALES] Saved: {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')} @ ${sold_row['sold_price']:,.0f}")
                except Exception as exc:
                    logger.warning(f"[DEALER_SALES] Insert failed: {exc}")
                    failed_save_count += 1
                continue

            gate_result = passes_basic_gates(vehicle)
            if not gate_result["pass"]:
                logger.info(f"[GATE] Rejected — {gate_result['reason']}: {vehicle.get('title','?')[:60]}")
                skipped += 1
                _increment_reason_counter(skip_reasons, f"gate:{gate_result['reason']}")
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_gate",
                    error_message=gate_result["reason"],
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue

            score_result = score_vehicle(vehicle)
            vehicle["dos_score"] = score_result["dos_score"]
            vehicle["score_breakdown"] = score_result
            vehicle["ingested_at"] = datetime.now(timezone.utc).isoformat()
            evaluated += 1

            if score_result.get("wholesale_margin", 0) < 1500:
                logger.info(
                    f"[MARGIN] below $1500 wholesale floor (${score_result.get('wholesale_margin', 0):,.0f}): "
                    f"{vehicle.get('title','?')[:60]}"
                )
                skipped += 1
                _increment_reason_counter(skip_reasons, "margin_below_floor")
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_margin",
                    error_message="margin_below_floor",
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue

            if score_result.get("investment_grade") == "Bronze":
                logger.info(f"[CEILING] bronze reject: {vehicle.get('title','?')[:60]}")
                skipped += 1
                _increment_reason_counter(skip_reasons, "bronze_reject")
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_bronze",
                    error_message="bronze_reject",
                    require_durable=True,
                    audit_state=audit_state,
                )
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
                _record_delivery_log(
                    run_id=vehicle.get("run_id") or apify_run_id,
                    listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                    listing_url=vehicle.get("listing_url"),
                    opportunity_id=None,
                    channel="db_save",
                    status="skipped_ceiling",
                    error_message=score_result.get("ceiling_reason") or "ceiling_reject",
                    require_durable=True,
                    audit_state=audit_state,
                )
                continue

            dedup = {"is_duplicate": False, "canonical_record_id": None, "canonical_update": None}
            if vehicle["dos_score"] >= 50:
                dedup = check_and_handle_duplicate(supabase_client, vehicle)
            is_dup = dedup["is_duplicate"]
            if is_dup:
                vehicle["is_duplicate"] = True
                vehicle["canonical_record_id"] = dedup["canonical_record_id"]
                duplicate_count += 1
                logger.info(f"[DEDUP] duplicate of {dedup['canonical_record_id']}: {vehicle.get('title','?')[:50]}")

            # Try/except around save operation to handle failures
            try:
                saved_opportunity_id = await save_opportunity_to_supabase(vehicle)
            except Exception as exc:
                logger.error(f"[SAVE ERROR] failed to save vehicle {vehicle.get('title')} with error: {exc}")
                _increment_reason_counter(skip_reasons, "save_exception")
                continue
            save_status = vehicle.get("_save_status", "unknown")
            _increment_reason_counter(save_outcomes, save_status)
            if saved_opportunity_id:
                vehicle["opportunity_id"] = saved_opportunity_id

            if vehicle.get("is_duplicate") and not is_dup:
                is_dup = True
                duplicate_count += 1
                logger.info(
                    "[DEDUP] canonical conflict recovered for %s: %s",
                    vehicle.get("canonical_record_id"),
                    vehicle.get("title", "?")[:50],
                )

            _record_delivery_log(
                run_id=vehicle.get("run_id") or apify_run_id,
                listing_id=vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", vehicle.get("listing_url") or ""),
                listing_url=vehicle.get("listing_url"),
                opportunity_id=saved_opportunity_id,
                channel="db_save",
                status=save_status,
                error_message=None if save_status not in {"supabase_error", "direct_pg_error", "duplicate_unresolved", "direct_pg_unavailable"} else save_status,
                require_durable=True,
                audit_state=audit_state,
            )

            inserted_success = save_status in {
                "saved_supabase",
                "saved_supabase_duplicate",
                "saved_direct_pg",
                "saved_direct_pg_duplicate",
            }
            existing_success = save_status == "duplicate_existing"
            save_succeeded = inserted_success or existing_success
            is_existing_listing = save_status in {"duplicate_existing", "duplicate_unresolved"} or is_dup
            if save_succeeded:
                processed += 1
                if inserted_success:
                    saved_count += 1
            else:
                failed_save_count += 1

            if save_succeeded and is_dup and dedup.get("canonical_update"):
                if _apply_canonical_update(dedup.get("canonical_update")):
                    logger.info("[DEDUP] canonical source update applied for %s", dedup.get("canonical_record_id"))

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

        if hot_deals:
            validated_deals = await ai_validate_hot_deals(hot_deals)
            await send_telegram_alerts(validated_deals)

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

        update_webhook_log(
            webhook_log_id,
            "processed" if failed_save_count == 0 else "degraded",
            item_count=dataset_item_count,
            error_message=_merge_audit_error_message(
                (
                    None
                    if failed_save_count == 0
                    and (saved_count > 0 or save_outcomes.get("duplicate_existing", 0) > 0)
                    else f"save_outcomes={save_outcomes}; skip_reasons={skip_reasons}"
                ),
                _audit_fallbacks(audit_state),
            ),
            require_durable=True,
            audit_state=audit_state,
        )
    except CriticalAuditWriteError as e:
        logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, e)
    except Exception as e:
        logger.error("[INGEST] Background processing failed for run_id=%s: %s", apify_run_id, e)
        if webhook_log_id:
            try:
                update_webhook_log(
                    webhook_log_id,
                    "error",
                    error_message=_merge_audit_error_message(str(e), _audit_fallbacks(audit_state)),
                    require_durable=True,
                    audit_state=audit_state,
                )
            except CriticalAuditWriteError as audit_error:
                logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, audit_error)


@router.post("/apify")
async def apify_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_apify_webhook_secret: Optional[str] = Header(None)
):
    # Verify webhook secret
    matched_secret_label = _match_webhook_secret(x_apify_webhook_secret)
    if matched_secret_label is None:
        logger.warning(
            "[INGEST_AUTH] rejected_invalid_secret | client_ip=%s | path=/api/ingest/apify",
            _request_client_ip_for_security_log(request),
        )
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    if matched_secret_label == "previous":
        posture = _webhook_secret_posture()
        logger.warning(
            "[INGEST_AUTH] Accepted webhook with APIFY_WEBHOOK_SECRET_PREVIOUS; "
            "previous_fp=%s active_fp=%s finish rotation and remove the fallback secret.",
            posture["previous"]["fingerprint"] or "none",
            posture["active"]["fingerprint"] or "missing",
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Unexpected payload format")

    metadata = extract_apify_webhook_metadata(payload)
    apify_run_id = metadata["run_id"] or str(uuid.uuid4())[:8]
    audit_state: dict[str, Any] = {"fallbacks": []}
    webhook_log_id = None
    logger.info(f"[INGEST] Webhook received for run_id={apify_run_id}")

    try:
        stale_error = _stale_webhook_error(metadata)
        if stale_error:
            insert_webhook_log(
                payload,
                processing_status="ignored_stale",
                error_message=stale_error,
                require_durable=True,
                audit_state=audit_state,
            )
            raise HTTPException(status_code=401, detail="Stale webhook payload")

        recent_replay = _find_recent_webhook_replay(
            metadata["run_id"],
            strict=True,
            audit_state=audit_state,
        )

        if recent_replay:
            replay_message = (
                f"Replay ignored for run_id={apify_run_id}; prior status="
                f"{recent_replay.get('processing_status') or 'unknown'} at "
                f"{recent_replay.get('received_at') or 'unknown'}"
            )
            logger.warning("[INGEST_AUTH] %s", replay_message)
            insert_webhook_log(
                payload,
                processing_status="ignored_replay",
                error_message=replay_message,
                require_durable=True,
                audit_state=audit_state,
            )
            response = {
                "status": "ok",
                "run_id": apify_run_id,
                "replay_ignored": True,
                "message": "Duplicate webhook ignored",
            }
            _attach_audit_state(response, audit_state)
            return response

        webhook_log_id = insert_webhook_log(
            payload,
            require_durable=True,
            audit_state=audit_state,
        )

        background_tasks.add_task(
            _process_webhook_items,
            payload,
            metadata,
            apify_run_id,
            audit_state,
            webhook_log_id,
        )
        return {"status": "ok", "run_id": apify_run_id, "message": "Processing in background"}
    except CriticalAuditWriteError as e:
        logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, e)
        raise HTTPException(status_code=503, detail="Critical ingest audit write failed") from e
    except HTTPException as e:
        if webhook_log_id:
            try:
                update_webhook_log(
                    webhook_log_id,
                    "error",
                    error_message=_merge_audit_error_message(str(e.detail), _audit_fallbacks(audit_state)),
                    require_durable=True,
                    audit_state=audit_state,
                )
            except CriticalAuditWriteError as audit_error:
                logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, audit_error)
                raise HTTPException(status_code=503, detail="Critical ingest audit write failed") from audit_error
        raise
    except Exception as e:
        if webhook_log_id:
            try:
                update_webhook_log(
                    webhook_log_id,
                    "error",
                    error_message=_merge_audit_error_message(str(e), _audit_fallbacks(audit_state)),
                    require_durable=True,
                    audit_state=audit_state,
                )
            except CriticalAuditWriteError as audit_error:
                logger.error("[INGEST_AUDIT] run_id=%s %s", apify_run_id, audit_error)
                raise HTTPException(status_code=503, detail="Critical ingest audit write failed") from audit_error
        raise


def get_supabase_client():
    """Return the module-level supabase_client (used by standalone endpoints)."""
    return supabase_client


@router.post("/opportunities/{opportunity_id}/pass")
async def pass_opportunity(
    opportunity_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Mark an opportunity as passed by the current user. Writes to user_passes table."""
    # Auth: get user_id from Authorization Bearer header via Supabase
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "").strip()

    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")

    # Verify token via Supabase and get user_id
    supa = get_supabase_client()
    try:
        user_resp = supa.auth.get_user(token)
        user_id = user_resp.user.id if user_resp and user_resp.user else None
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Write to user_passes table
    try:
        supa.table("user_passes").upsert({
            "user_id": user_id,
            "opportunity_id": opportunity_id,
        }, on_conflict="user_id,opportunity_id").execute()
    except Exception as e:
        logger.warning(f"[PASS] user_passes upsert failed: {e}")
        # Non-fatal — return success anyway so UI doesn't break

    return {"status": "passed", "opportunity_id": opportunity_id}


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
        anchor = reference_dt or _parse_datetime_utc(datetime.now(timezone.utc))
        if anchor is None:
            return None
        return (anchor + total_delta).astimezone(timezone.utc).isoformat()

    return None


_SOURCE_SITE_ALIASES = {
    "allsurplus": "allsurplus",
    "bidspotter": "bidspotter",
    "equipmentfacts": "equipmentfacts",
    "gsa auctions": "gsaauctions",
    "gsaauctions": "gsaauctions",
    "govdeals": "govdeals",
    "govdeals.com": "govdeals",
    "govdeals-sold": "govdeals-sold",
    "govdeals_sold": "govdeals-sold",
    "govplanet": "govplanet",
    "hibid": "hibid",
    "hibid-v2": "hibid",
    "ironplanet": "ironplanet",
    "jjkane": "jjkane",
    "municibid": "municibid",
    "publicsurplus": "publicsurplus",
    "publicsurplus_tx": "publicsurplus",
    "proxibid": "proxibid",
    "usgovbid": "usgovbid",
}

_SOURCE_SITE_URL_HINTS = (
    ("allsurplus.com", "allsurplus"),
    ("bidspotter.com", "bidspotter"),
    ("equipmentfacts.com", "equipmentfacts"),
    ("gsaauctions.gov", "gsaauctions"),
    ("govdeals.com", "govdeals"),
    ("govplanet.com", "govplanet"),
    ("hibid.com", "hibid"),
    ("ironplanet.com", "ironplanet"),
    ("jjkane.com", "jjkane"),
    ("municibid.com", "municibid"),
    ("publicsurplus.com", "publicsurplus"),
    ("proxibid.com", "proxibid"),
    ("usgovbid.com", "usgovbid"),
)


def _canonical_source_site(raw_value: Any) -> str:
    text = str(raw_value or "").strip().lower()
    if not text or text in {"apify", "none", "null", "unknown"}:
        return ""
    if text in _SOURCE_SITE_ALIASES:
        return _SOURCE_SITE_ALIASES[text]
    normalized = text.replace("_", "-")
    return _SOURCE_SITE_ALIASES.get(normalized, "")


def _source_site_from_url(url: str) -> str:
    lowered = (url or "").strip().lower()
    if not lowered:
        return ""
    for needle, source_site in _SOURCE_SITE_URL_HINTS:
        if needle in lowered:
            return source_site
    return ""


def _infer_source_site(item: dict, *, source_hint: Optional[str] = None) -> Optional[str]:
    for candidate in (
        item.get("source_site"),
        item.get("source"),
        source_hint,
    ):
        source_site = _canonical_source_site(candidate)
        if source_site:
            return source_site

    for candidate in (
        item.get("listing_url"),
        item.get("auction_url"),
        item.get("url"),
    ):
        source_site = _source_site_from_url(str(candidate or ""))
        if source_site:
            return source_site

    return None


def normalize_apify_vehicle(
    item: dict,
    run_id: str,
    *,
    default_time_anchor: Optional[datetime] = None,
    source_hint: Optional[str] = None,
) -> Optional[dict]:
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

        # Make/model/year: parseforge provides these directly
        make = item.get("make") or extract_make(title) or ""
        model = item.get("model") or extract_model(title, make) or ""
        year_raw = item.get("modelYear") or item.get("year")
        year = int(year_raw) if year_raw and str(year_raw).isdigit() else extract_year(title)

        # Skip high rust states at normalize time — bypass allowed for ≤8yr old vehicles
        # (Consistent with MEMORY.md rule: vehicles ≤3yr bypass rust rejection, but
        #  government fleet sources can be older — use 8yr to match gov source max age)
        if state in HIGH_RUST_STATES:
            current_year = datetime.now().year
            source_check = (item.get("source_site") or item.get("source") or "").lower()
            gov_rust_bypass = {"govplanet", "municibid", "usgovbid", "jjkane", "publicsurplus", "publicsurplus_tx", "govdeals", "gsaauctions"}
            max_rust_age = 8 if source_check in gov_rust_bypass else 2
            if not year or year < current_year - max_rust_age:
                return None
            logger.info(f'[BYPASS] Rust state {state} allowed — vehicle is {year} (≤{max_rust_age}yr old)')

        # Bid: parseforge uses currentBid, ours uses current_bid
        current_bid = float(item.get("currentBid") or item.get("current_bid") or 0)

        # Mileage: parseforge puts in meterCount when type is odometer; jjkane uses odometer
        mileage = item.get("mileage") or item.get("meterCount") or item.get("odometer")

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
        source = _infer_source_site(item, source_hint=source_hint)

        normalized = {
            "listing_id": _compute_listing_id(source, listing_url),
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
        normalized["all_sources"] = [source] if source else []
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
    # Layer 0: Must be an actual vehicle (has make OR VIN OR title contains vehicle keywords)
    make = vehicle.get("make", "") or ""
    vin = vehicle.get("vin", "") or ""
    title = (vehicle.get("title") or "").lower()
    _VEHICLE_TITLE_KEYWORDS = [
        "ford", "chevrolet", "chevy", "dodge", "ram", "toyota", "honda", "nissan",
        "jeep", "gmc", "chrysler", "hyundai", "kia", "subaru", "mazda", "volkswagen",
        "bmw", "mercedes", "audi", "lexus", "acura", "infiniti", "cadillac", "lincoln",
        "buick", "mitsubishi", "volvo", "tesla", "truck", "pickup", "suv", "sedan",
        "coupe", "van", "vehicle", "automobile", "f-150", "silverado", "tacoma", "tundra",
    ]
    title_has_vehicle = any(kw in title for kw in _VEHICLE_TITLE_KEYWORDS)
    if not make.strip() and len(vin) != 17 and not title_has_vehicle:
        return {"pass": False, "reason": "not_a_vehicle (no make or valid VIN)"}

    bid = vehicle.get("current_bid", 0)
    state = vehicle.get("state", "")
    year = vehicle.get("year")
    mileage = vehicle.get("mileage")
    source = (vehicle.get("source_site") or "").lower()

    # Normalize source name variants to canonical form for gate lookups
    _source_aliases = {
        "hibid-v2": "hibid", "hibid-bidcal": "hibid", "hibid_v2": "hibid",
        "jj kane": "jjkane", "jj_kane": "jjkane", "jjkane.com": "jjkane",
    }
    source = _source_aliases.get(source, source)

    # Government/auction sources: lower min bid, higher age/mileage tolerance
    gov_sources_bid = {"publicsurplus", "publicsurplus_tx", "govdeals", "gsaauctions", "govplanet", "municibid", "usgovbid", "jjkane", "bidspotter", "hibid"}
    is_gov = source in gov_sources_bid
    min_bid = 500 if is_gov else 3000
    # Allow bid=0 for gov sources (auction not yet open — e.g. JJKane pre-auction lots)
    if (bid > 0 and bid < min_bid) or bid > 35000:
        return {"pass": False, "reason": f"bid_out_of_range (${bid:,.0f})"}

    # Reject non-US states (Canadian provinces, garbage codes)
    if state and state not in US_STATES:
        return {"pass": False, "reason": f"non_us_state ({state})"}

    if state in HIGH_RUST_STATES:
        current_year = datetime.now().year
        # Gov fleet sources run older vehicles — allow up to 8yr in rust states
        max_rust_age = 8 if is_gov else 2
        if not year or year < current_year - max_rust_age:
            return {"pass": False, "reason": f"high_rust_state ({state})"}
        logger.info(f'[BYPASS] Rust state {state} allowed — vehicle is {year} (≤{max_rust_age}yr old)')

    title_brand_issue = _find_title_brand_issue(vehicle)
    if title_brand_issue:
        return {"pass": False, "reason": title_brand_issue}

    # Reject commercial/fleet vehicles (cargo vans, box trucks, cutaways)
    title = (vehicle.get("title") or "").strip()
    if any(re.search(p, title, re.IGNORECASE) for p in _COMMERCIAL_PATTERNS):
        return {"pass": False, "reason": f"commercial_vehicle ({title[:50]})"}
    if _is_commercial_hd_tonnage(title):
        return {"pass": False, "reason": f"commercial_hd_tonnage ({title[:50]})"}

    if not year:
        # Missing year = pass through (can't confirm age, benefit of the doubt)
        # Per business rules: null year should not block a potentially good deal
        pass  # continue to next checks without year-based filtering

    current_year = datetime.now().year
    # Government/public auction sources run older fleet vehicles — allow up to 20 years
    gov_sources = {"publicsurplus", "publicsurplus_tx", "govdeals", "gsaauctions", "govplanet", "municibid", "usgovbid", "jjkane", "hibid"}
    max_age = 20 if source in gov_sources else 4
    if year:
        age = current_year - year
    else:
        age = 0  # unknown year — skip age check
    if year and (age > max_age or age < 0):
        return {"pass": False, "reason": f"age_exceeded ({age} years, max {max_age} for {source})"}

    if mileage is not None:
        try:
            # Gov fleet vehicles run 100k–200k miles routinely — higher cap for gov sources
            max_mileage = 200000 if is_gov else 50000
            if float(mileage) > max_mileage:
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
    if not listing_url:
        logger.info("[NOTION] Skipping — empty listing_url")
        return False
    run_id = vehicle.get("run_id") or "unknown"
    listing_id = vehicle.get("listing_id") or _compute_listing_id(vehicle.get("source_site") or "", listing_url)
    existing_delivery = _delivery_log_lookup(run_id, listing_id, "notion_sync")
    if existing_delivery and existing_delivery.get("status") == "sent":
        return True

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
                        page_id = existing_results[0].get("id")
                        logger.info("[NOTION] Existing page found for listing_url=%s; skipping create", listing_url)
                        _record_delivery_log(
                            run_id=run_id,
                            listing_id=listing_id,
                            listing_url=listing_url,
                            opportunity_id=vehicle.get("opportunity_id"),
                            channel="notion_sync",
                            status="sent",
                            external_id=page_id,
                        )
                        return True
                else:
                    logger.warning(f"[NOTION] Query failed: {query_resp.status_code} {query_resp.text[:200]}")

            resp = await client.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json={"parent": {"database_id": notion_db_id}, "properties": props},
            )
            if resp.status_code == 200:
                page_id = resp.json().get("id")
                _record_delivery_log(
                    run_id=run_id,
                    listing_id=listing_id,
                    listing_url=listing_url,
                    opportunity_id=vehicle.get("opportunity_id"),
                    channel="notion_sync",
                    status="sent",
                    external_id=page_id,
                )
                return True
            logger.warning(f"[NOTION] Failed to sync: {resp.status_code} {resp.text[:200]}")
            _record_delivery_log(
                run_id=run_id,
                listing_id=listing_id,
                listing_url=listing_url,
                opportunity_id=vehicle.get("opportunity_id"),
                channel="notion_sync",
                status="failed",
                error_message=f"http_{resp.status_code}",
            )
            return False
    except Exception as e:
        logger.error(f"[NOTION] Sync error (non-fatal): {e}")
        _record_delivery_log(
            run_id=run_id,
            listing_id=listing_id,
            listing_url=listing_url,
            opportunity_id=vehicle.get("opportunity_id"),
            channel="notion_sync",
            status="failed",
            error_message=str(e),
        )
        return False


async def send_telegram_alert(deal: dict) -> Optional[str]:
    """Send a single Telegram alert, log the receipt, and return the Telegram message_id."""
    run_id = deal.get("run_id") or "unknown"
    raw_listing_url = deal.get("listing_url") or ""
    # Strip query params from GovPlanet URLs — they trigger geo-redirects to European content
    if "govplanet.com" in raw_listing_url:
        listing_url = raw_listing_url.split("?")[0]
    else:
        listing_url = raw_listing_url
    listing_id = deal.get("listing_id") or _compute_listing_id(deal.get("source_site") or "", listing_url)
    existing_delivery = _delivery_log_lookup(run_id, listing_id, "telegram_alert")
    if existing_delivery and existing_delivery.get("status") == "sent":
        return existing_delivery.get("external_id")

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
            alert_suppression_cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
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

    # Per-run alert cap (max 20) with 1-hour TTL reset
    _now = _time.time()
    if _now - alerts_this_run_ts.get(run_id, 0) > 3600:
        alerts_this_run.pop(run_id, None)
        alerts_this_run_ts.pop(run_id, None)
    if alerts_this_run.get(run_id, 0) >= 20:
        logger.info(f"[ALERT CAP] max alerts reached for run {run_id}")
        return None
    alerts_this_run[run_id] = alerts_this_run.get(run_id, 0) + 1
    alerts_this_run_ts[run_id] = alerts_this_run_ts.get(run_id) or _time.time()

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
                f"[View Deal](https://dealscan-insight.vercel.app/deal/{deal.get('opportunity_id', '')}) | [Bid Direct →]({listing_url})"
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
                f"[View Deal](https://dealscan-insight.vercel.app/deal/{deal.get('opportunity_id', '')}) | [Bid Direct →]({listing_url})"
            )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": msg,
                    "parse_mode": "Markdown",
                    "link_preview_options": {"is_disabled": True},
                    "reply_markup": reply_markup,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.error(f"[TELEGRAM] Alert failed (non-fatal): {e}")
        _record_delivery_log(
            run_id=run_id,
            listing_id=listing_id,
            listing_url=listing_url,
            opportunity_id=deal.get("opportunity_id"),
            channel="telegram_alert",
            status="failed",
            error_message=str(e),
        )
        return None

    message_id = payload.get("result", {}).get("message_id")
    if message_id is None:
        logger.warning(f"[TELEGRAM] Missing message_id in response for run_id={deal.get('run_id')}")
        _record_delivery_log(
            run_id=run_id,
            listing_id=listing_id,
            listing_url=listing_url,
            opportunity_id=deal.get("opportunity_id"),
            channel="telegram_alert",
            status="failed",
            error_message="missing_message_id",
        )
        return None

    message_id_str = str(message_id)
    deal["message_id"] = message_id_str
    _record_delivery_log(
        run_id=run_id,
        listing_id=listing_id,
        listing_url=listing_url,
        opportunity_id=deal.get("opportunity_id"),
        channel="telegram_alert",
        status="sent",
        external_id=message_id_str,
    )
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
        "sent_at": datetime.now(timezone.utc).isoformat(),
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


async def ai_validate_hot_deals(deals: list) -> list:
    """Validate hot deals with OpenRouter DeepSeek R1 before alerting."""
    if not deals:
        return []

    import httpx

    validated_deals: list = []
    # Use DeepSeek direct API (cheaper, faster than OpenRouter)
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for deal in deals:
            deal_id = deal.get("id") or deal.get("opportunity_id") or deal.get("listing_id") or "unknown"
            prompt = (
                "You are a vehicle arbitrage expert. Validate this deal: "
                f"{deal.get('title')}, Year: {deal.get('year')}, Make: {deal.get('make')}, "
                f"Model: {deal.get('model')}, Current bid: ${deal.get('current_bid')}, "
                f"MMR estimate: ${deal.get('mmr_value')}, DOS score: {deal.get('dos_score')}, "
                f"Location: {deal.get('state')}. Is this a genuine arbitrage opportunity? "
                "Reply with VALID or INVALID and one sentence reason."
            )

            payload = {
                "model": "deepseek-reasoner",
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            }

            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = (
                    (data.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                first_line = content.splitlines()[0].strip() if content else ""
                verdict_match = re.search(r"\b(VALID|INVALID)\b", first_line, re.IGNORECASE) or re.search(
                    r"\b(VALID|INVALID)\b", content, re.IGNORECASE
                )
                verdict = verdict_match.group(1).upper() if verdict_match else ""
                reason = (
                    (content[verdict_match.end():] if verdict_match else content).strip(" :-")
                    if content
                    else ""
                )

                if verdict == "VALID":
                    logger.info(
                        "[AI_VALIDATE] deal_id=%s result=VALID reason=%s",
                        deal_id,
                        reason or "validated by model",
                    )
                    validated_deals.append(deal)
                elif verdict == "INVALID":
                    logger.warning(
                        "[AI_VALIDATE] deal_id=%s result=INVALID reason=%s",
                        deal_id,
                        reason or "rejected by model",
                    )
                else:
                    logger.warning(
                        "[AI_VALIDATE] deal_id=%s result=VALID reason=unparseable_response_kept_open content=%s",
                        deal_id,
                        content,
                    )
                    validated_deals.append(deal)
            except Exception as exc:
                logger.warning(
                    "[AI_VALIDATE] deal_id=%s result=VALID reason=api_error_fail_open error=%s",
                    deal_id,
                    exc,
                )
                validated_deals.append(deal)

    return validated_deals


def _prepare_direct_pg_value(value):
    if isinstance(value, dict):
        return psycopg2_extras.Json(value)
    return value


def _increment_reason_counter(counter: dict, reason: str) -> None:
    counter[reason] = counter.get(reason, 0) + 1


def _audit_fallbacks(audit_state: Optional[dict[str, Any]]) -> list[str]:
    fallbacks = (audit_state or {}).get("fallbacks") or []
    deduped: list[str] = []
    for fallback in fallbacks:
        if fallback and fallback not in deduped:
            deduped.append(str(fallback))
    return deduped


def _record_audit_fallback(audit_state: Optional[dict[str, Any]], fallback_label: str) -> None:
    if audit_state is None:
        return
    fallbacks = audit_state.setdefault("fallbacks", [])
    if fallback_label not in fallbacks:
        fallbacks.append(fallback_label)


def _merge_audit_error_message(
    error_message: Optional[str],
    fallback_labels: list[str],
) -> Optional[str]:
    labels = [label for label in fallback_labels if label]
    if not labels:
        return error_message
    marker = f"{AUDIT_FALLBACK_MARKER}{','.join(labels)}"
    if not error_message:
        return marker
    if marker in error_message:
        return error_message
    return f"{error_message}; {marker}"


def _attach_audit_state(response: dict[str, Any], audit_state: Optional[dict[str, Any]]) -> None:
    fallbacks = _audit_fallbacks(audit_state)
    response["audit_status"] = "fallback" if fallbacks else "ok"
    if fallbacks:
        response["audit_fallbacks"] = fallbacks


def _format_audit_failure(
    *,
    surface: str,
    operation: str,
    primary_error: Optional[BaseException],
    fallback_error: BaseException,
) -> str:
    if primary_error is not None:
        return (
            f"critical {surface} {operation} failed via Supabase and direct PG fallback: "
            f"supabase={primary_error}; direct_pg={fallback_error}"
        )
    return f"critical {surface} {operation} failed via direct PG fallback: direct_pg={fallback_error}"


def _insert_webhook_log_direct_pg(row: dict) -> Optional[str]:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG audit fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.webhook_log
                  (source, actor_id, run_id, item_count, raw_payload, processing_status, error_message)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    row.get("source"),
                    row.get("actor_id"),
                    row.get("run_id"),
                    row.get("item_count"),
                    psycopg2_extras.Json(row.get("raw_payload")),
                    row.get("processing_status"),
                    row.get("error_message"),
                ),
            )
            inserted = cur.fetchone()
            return str(inserted[0]) if inserted and inserted[0] else None


def _update_webhook_log_direct_pg(webhook_log_id: str, update_row: dict) -> None:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG audit fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update public.webhook_log
                set processing_status = %s,
                    error_message = %s,
                    item_count = coalesce(%s, item_count)
                where id = %s
                returning id
                """,
                (
                    update_row.get("processing_status"),
                    update_row.get("error_message"),
                    update_row.get("item_count"),
                    webhook_log_id,
                ),
            )
            updated = cur.fetchone()
            if not updated:
                raise RuntimeError(f"webhook_log row {webhook_log_id} not found for update")


def _find_recent_webhook_replay_direct_pg(run_id: str, cutoff: datetime) -> list[dict]:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG replay lookup fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
            cur.execute(
                """
                select id, received_at, processing_status, error_message
                from public.webhook_log
                where run_id = %s
                  and received_at >= %s
                order by received_at desc
                limit 5
                """,
                (run_id, cutoff),
            )
            return [dict(row) for row in cur.fetchall()]


def _delivery_log_lookup(run_id: str, listing_id: str, channel: str) -> Optional[dict]:
    if supabase_client is None or not run_id or not listing_id or not channel:
        return None
    try:
        result = (
            supabase_client.table("ingest_delivery_log")
            .select("id,status,attempt_count,external_id")
            .eq("run_id", run_id)
            .eq("listing_id", listing_id)
            .eq("channel", channel)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.warning("[DELIVERY_LOG] lookup failed for %s/%s/%s: %s", run_id, listing_id, channel, e)
    return None


def _record_delivery_log(
    *,
    run_id: str,
    listing_id: str,
    channel: str,
    status: str,
    listing_url: Optional[str] = None,
    opportunity_id: Optional[str] = None,
    external_id: Optional[str] = None,
    error_message: Optional[str] = None,
    require_durable: bool = False,
    audit_state: Optional[dict[str, Any]] = None,
) -> bool:
    if not run_id or not listing_id or not channel:
        if require_durable:
            raise CriticalAuditWriteError(
                "critical ingest_delivery_log write missing run_id, listing_id, or channel"
            )
        return False
    now_iso = datetime.now(timezone.utc).isoformat()
    row = {
        "run_id": run_id,
        "listing_id": listing_id,
        "listing_url": listing_url,
        "opportunity_id": opportunity_id,
        "channel": channel,
        "status": status,
        "external_id": external_id,
        "error_message": error_message,
        "updated_at": now_iso,
    }
    primary_error: Optional[Exception] = None
    try:
        if supabase_client is not None:
            existing = _delivery_log_lookup(run_id, listing_id, channel)
            if existing and existing.get("id"):
                row["attempt_count"] = int(existing.get("attempt_count") or 0) + 1
                (
                    supabase_client.table("ingest_delivery_log")
                    .update(row)
                    .eq("id", existing["id"])
                    .execute()
                )
            else:
                row["attempt_count"] = 1
                row["created_at"] = now_iso
                supabase_client.table("ingest_delivery_log").insert(row).execute()
            return False
    except Exception as exc:
        primary_error = exc

    try:
        fallback_label = "ingest_delivery_log_direct_pg"
        fallback_row = dict(row)
        fallback_row["error_message"] = _merge_audit_error_message(
            fallback_row.get("error_message"),
            [fallback_label],
        )
        _upsert_delivery_log_direct_pg(fallback_row)
        _record_audit_fallback(audit_state, fallback_label)
        return True
    except Exception as fallback_error:
        if require_durable:
            raise CriticalAuditWriteError(
                _format_audit_failure(
                    surface="ingest_delivery_log",
                    operation="upsert",
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            ) from fallback_error
        if primary_error is not None:
            logger.warning(
                "[DELIVERY_LOG] record failed for %s/%s/%s: %s",
                run_id,
                listing_id,
                channel,
                primary_error,
            )
        logger.warning(
            "[DELIVERY_LOG] direct PG fallback failed for %s/%s/%s: %s",
            run_id,
            listing_id,
            channel,
            fallback_error,
        )
        return False


def _compute_listing_id(source: str, listing_url: str) -> str:
    normalized_source = (source or "unknown").strip().lower()
    normalized_url = (listing_url or "").strip()
    return hashlib.sha256(f"{normalized_source}|{normalized_url}".encode()).hexdigest()[:40]


def _upsert_delivery_log_direct_pg(row: dict) -> None:
    if not _direct_supabase_db_url:
        raise RuntimeError("direct PG audit fallback unavailable")

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.ingest_delivery_log
                  (run_id, listing_id, listing_url, opportunity_id, channel, status, external_id,
                   error_message, attempt_count, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
                on conflict (run_id, listing_id, channel)
                do update set
                  listing_url = excluded.listing_url,
                  opportunity_id = excluded.opportunity_id,
                  status = excluded.status,
                  external_id = excluded.external_id,
                  error_message = excluded.error_message,
                  updated_at = excluded.updated_at,
                  attempt_count = public.ingest_delivery_log.attempt_count + 1
                """,
                (
                    row.get("run_id"),
                    row.get("listing_id"),
                    row.get("listing_url"),
                    row.get("opportunity_id"),
                    row.get("channel"),
                    row.get("status"),
                    row.get("external_id"),
                    row.get("error_message"),
                    row.get("created_at") or row.get("updated_at"),
                    row.get("updated_at"),
                ),
            )


def _apply_canonical_update(canonical_update: Optional[dict]) -> bool:
    if supabase_client is None or not canonical_update or not canonical_update.get("id"):
        return False
    try:
        (
            supabase_client.table("opportunities")
            .update({
                "all_sources": canonical_update.get("all_sources") or [],
                "duplicate_count": canonical_update.get("duplicate_count") or 0,
            })
            .eq("id", canonical_update["id"])
            .execute()
        )
        return True
    except Exception as e:
        logger.warning("[DEDUP] canonical update failed for %s: %s", canonical_update.get("id"), e)
        return False


def _lookup_existing_canonical_opportunity(canonical_id: Optional[str]) -> Optional[dict]:
    if not canonical_id:
        return None

    if supabase_client is not None:
        try:
            lookup = (
                supabase_client.table("opportunities")
                .select("id, all_sources")
                .eq("canonical_id", canonical_id)
                .eq("is_duplicate", False)
                .limit(1)
                .execute()
            )
            if lookup.data:
                row = lookup.data[0]
                return {
                    "id": row.get("id"),
                    "all_sources": row.get("all_sources") or [],
                }
        except Exception as lookup_err:
            logger.warning("[DEDUP] Supabase canonical lookup failed: %s", lookup_err)

    if not _direct_supabase_db_url:
        return None

    try:
        with psycopg2.connect(_direct_supabase_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, all_sources
                    from public.opportunities
                    where canonical_id = %s and is_duplicate = false
                    limit 1
                    """,
                    (canonical_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return {
                        "id": str(row[0]),
                        "all_sources": list(row[1] or []),
                    }
    except Exception as lookup_err:
        logger.warning("[DEDUP] Direct PG canonical lookup failed: %s", lookup_err)
    return None


def _build_duplicate_recovery_payload(row: dict, canonical_row: dict) -> tuple[dict, Optional[dict]]:
    duplicate_row = dict(row)
    duplicate_row["is_duplicate"] = True
    duplicate_row["canonical_record_id"] = canonical_row["id"]
    duplicate_row["all_sources"] = []
    duplicate_row["duplicate_count"] = 0

    existing_sources = canonical_row.get("all_sources") or []
    new_source = duplicate_row.get("source")
    canonical_update = None
    if new_source and new_source not in existing_sources:
        updated_sources = existing_sources + [new_source]
        canonical_update = {
            "id": canonical_row["id"],
            "all_sources": updated_sources,
            "duplicate_count": len(updated_sources) - 1,
        }
    return duplicate_row, canonical_update


def _finalize_duplicate_recovery(vehicle: dict, canonical_row: dict, canonical_update: Optional[dict]) -> None:
    vehicle["is_duplicate"] = True
    vehicle["canonical_record_id"] = canonical_row["id"]
    if canonical_update and _apply_canonical_update(canonical_update):
        logger.info("[DEDUP] canonical source update applied for %s", canonical_row["id"])


def _is_canonical_unique_conflict(error_text: str) -> bool:
    normalized = (error_text or "").lower()
    return (
        "idx_opportunities_canonical_unique" in normalized
        or (
            "duplicate key value" in normalized
            and "canonical_id" in normalized
            and "is_duplicate" in normalized
        )
    )


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


def _insert_opportunity_direct_pg(row: dict) -> Optional[str]:
    columns = list(row.keys())
    values = [_prepare_direct_pg_value(row[column]) for column in columns]
    insert_sql = psycopg2_sql.SQL(
        "INSERT INTO public.opportunities ({fields}) VALUES ({values}) RETURNING id"
    ).format(
        fields=psycopg2_sql.SQL(", ").join(psycopg2_sql.Identifier(column) for column in columns),
        values=psycopg2_sql.SQL(", ").join(psycopg2_sql.Placeholder() for _ in columns),
    )

    with psycopg2.connect(_direct_supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(insert_sql, values)
            inserted = cur.fetchone()
            return str(inserted[0]) if inserted and inserted[0] else None


def _save_opportunity_direct_pg(row: dict) -> tuple[Optional[str], str]:
    if not _direct_supabase_db_url:
        logger.warning(
            "[INGEST] Direct PG fallback unavailable; set SUPABASE_DB_URL or SUPABASE_DB_PASSWORD."
        )
        return None, "direct_pg_unavailable"

    try:
        return _insert_opportunity_direct_pg(row), "saved_direct_pg"
    except psycopg2.errors.UniqueViolation as pg_err:
        error_text = getattr(pg_err, "pgerror", None) or str(pg_err)
        if _is_canonical_unique_conflict(error_text):
            canonical_row = _lookup_existing_canonical_opportunity(row.get("canonical_id"))
            if canonical_row:
                duplicate_row, canonical_update = _build_duplicate_recovery_payload(row, canonical_row)
                try:
                    duplicate_id = _insert_opportunity_direct_pg(duplicate_row)
                    if canonical_update:
                        _apply_canonical_update(canonical_update)
                    return duplicate_id, "saved_direct_pg_duplicate"
                except Exception as recovery_err:
                    logger.warning(
                        "[DEDUP] Direct PG duplicate recovery failed for canonical_id=%s: %s",
                        row.get("canonical_id"),
                        recovery_err,
                    )
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


def _normalize_vin(vin: Optional[str]) -> Optional[str]:
    """Normalize a VIN: strip whitespace and uppercase."""
    if not vin:
        return None
    normalized = vin.strip().upper()
    return normalized if normalized else None


def _check_vin_duplicate(vin: str, new_dos_score: float) -> tuple[Optional[str], bool]:
    """
    Check if a live opportunity with this VIN already exists in Supabase.

    Returns (existing_id, should_update) where:
    - existing_id: the ID of the existing record, or None if no duplicate
    - should_update: True if new score is higher and we should UPDATE instead of skip

    Non-fatal: logs errors and returns (None, False) on failure so insert proceeds.
    """
    if supabase_client is None:
        return None, False
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        result = (
            supabase_client.table("opportunities")
            .select("id, listing_url, dos_score")
            .eq("vin", vin)
            .gte("auction_end_date", now_iso)
            .limit(1)
            .execute()
        )
        if result.data:
            existing = result.data[0]
            existing_id = existing.get("id")
            existing_score = float(existing.get("dos_score") or 0)
            should_update = new_dos_score > existing_score
            return existing_id, should_update
    except Exception as vin_check_err:
        logger.warning("[DEDUP] VIN duplicate check failed for VIN %s: %s", vin, vin_check_err)
    return None, False


async def save_opportunity_to_supabase(vehicle: dict) -> Optional[str]:
    """Save scored vehicle to Supabase. Min DOS 50 to save."""
    score = vehicle.get("dos_score", 0)
    if score < 50:
        vehicle["_save_status"] = "below_save_threshold"
        return None

    row = build_opportunity_row(vehicle)

    # Normalize VIN before dedup check and insert
    raw_vin = row.get("vin")
    normalized_vin = _normalize_vin(raw_vin)
    if normalized_vin != raw_vin:
        row["vin"] = normalized_vin

    # VIN deduplication check — non-fatal, skip or update if duplicate found
    if normalized_vin:
        try:
            existing_id, should_update = _check_vin_duplicate(normalized_vin, float(score))
            if existing_id:
                if should_update:
                    # New score is higher — update the existing record
                    try:
                        update_payload = {
                            "dos_score": row.get("dos_score"),
                            "current_bid": row.get("current_bid"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        supabase_client.table("opportunities").update(update_payload).eq("id", existing_id).execute()
                        logger.info(
                            "[DEDUP] VIN %s updated existing record %s with higher DOS score %.1f",
                            normalized_vin, existing_id, float(score),
                        )
                        vehicle["_save_status"] = "vin_dedup_updated"
                        return existing_id
                    except Exception as upd_err:
                        logger.warning("[DEDUP] VIN update failed for %s: %s", existing_id, upd_err)
                        vehicle["_save_status"] = "vin_dedup_skipped"
                        return existing_id
                else:
                    logger.warning(
                        "[DEDUP] Duplicate VIN %s skipped — already exists as %s",
                        normalized_vin, existing_id,
                    )
                    vehicle["_save_status"] = "vin_dedup_skipped"
                    return existing_id
        except Exception as dedup_err:
            logger.warning("[DEDUP] VIN dedup logic error for VIN %s: %s — proceeding with insert", normalized_vin, dedup_err)

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
                if _is_canonical_unique_conflict(error_text):
                    canonical_row = _lookup_existing_canonical_opportunity(row.get("canonical_id"))
                    if canonical_row:
                        duplicate_row, canonical_update = _build_duplicate_recovery_payload(row, canonical_row)
                        try:
                            retry = supabase_client.table("opportunities").insert(duplicate_row).execute()
                            if retry.data:
                                _finalize_duplicate_recovery(vehicle, canonical_row, canonical_update)
                                vehicle["_save_status"] = "saved_supabase_duplicate"
                                return retry.data[0].get("id")
                        except Exception as retry_err:
                            logger.warning(
                                "[DEDUP] Supabase duplicate recovery failed for '%s': %s",
                                title,
                                retry_err,
                            )
                existing_id = _lookup_existing_opportunity_id(row["listing_url"], row["listing_id"])
                if existing_id:
                    logger.info("[INGEST] Duplicate existing listing recovered for '%s'", title)
                    vehicle["_save_status"] = "duplicate_existing"
                    return existing_id
                vehicle["_save_status"] = "duplicate_unresolved"
                return None
            logger.warning(
                "[INGEST] Falling back to direct Postgres insert for '%s' after Supabase write failure.",
                title,
            )
    else:
        logger.warning("[INGEST] Supabase client unavailable; using direct Postgres fallback if configured.")

    saved_id, save_status = _save_opportunity_direct_pg(row)
    if save_status == "saved_direct_pg_duplicate":
        canonical_row = _lookup_existing_canonical_opportunity(row.get("canonical_id"))
        if canonical_row:
            vehicle["is_duplicate"] = True
            vehicle["canonical_record_id"] = canonical_row["id"]
    vehicle["_save_status"] = save_status
    return saved_id


def build_opportunity_row(vehicle: dict) -> dict:
    score_result = vehicle.get("score_breakdown", {})
    current_bid = float(vehicle.get("current_bid") or 0)
    source_site = _canonical_source_site(vehicle.get("source_site") or vehicle.get("source")) or None
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
        "listing_id": _compute_listing_id(source_site, vehicle.get("listing_url") or ""),
        "listing_url": vehicle.get("listing_url", ""),
        "source": source_site,
        "source_site": source_site,
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
        "processed_at": vehicle.get("processed_at") or datetime.now(timezone.utc).isoformat(),
    }
