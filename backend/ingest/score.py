"""Deal scoring using the DOS (Deal Opportunity Score) formula.

DOS = (Margin Score × 0.35) + (Velocity Score × 0.25) +
      (Segment Score × 0.20) + (Model Score × 0.12) + (Source Score × 0.08)
"""
import functools
import os
from datetime import datetime, timezone as _tz
from typing import Optional

# Alias for backward compat
timezone = _tz

_CURRENT_YEAR = datetime.now().year
_HIGH_RUST = {"OH","MI","PA","NY","WI","MN","IL","IN","MO","IA","ND","SD","NE","KS","WV","ME","NH","VT","MA","RI","CT","NJ","MD","DE"}
_TARGET_STATES = {"AZ","CA","NV","CO","NM","UT","TX","FL","GA","SC","TN","NC","VA","WA","OR","HI"}
_HOT_MODELS = {("FORD","F-150"),("CHEVROLET","TAHOE"),("CHEVROLET","SILVERADO"),("GMC","SIERRA"),("TOYOTA","TACOMA"),("TOYOTA","4RUNNER"),("TOYOTA","RAV4"),("TOYOTA","CAMRY"),("HONDA","ACCORD"),("HONDA","CR-V"),("RAM","1500"),("FORD","EXPLORER"),("FORD","F-250")}
_KNOWN_MAKES = {"FORD","CHEVROLET","GMC","TOYOTA","HONDA","RAM","DODGE","JEEP","NISSAN","HYUNDAI","KIA","SUBARU","VOLKSWAGEN","BMW","MERCEDES-BENZ","LEXUS","ACURA","INFINITI","CADILLAC","LINCOLN","BUICK","CHRYSLER","PONTIAC"}
_TRUCKS = {"F-150","F-250","F-350","SILVERADO","SIERRA","RAM 1500","RAM 2500","RANGER","TACOMA","TUNDRA","COLORADO","CANYON","RIDGELINE","FRONTIER","TITAN"}
_SUVS = {"TAHOE","SUBURBAN","YUKON","EXPEDITION","EXPLORER","PILOT","4RUNNER","HIGHLANDER","TRAVERSE","DURANGO","GRAND CHEROKEE","CHEROKEE","WRANGLER","NAVIGATOR","ESCALADE","SEQUOIA","ARMADA","PATHFINDER","MURANO","ACADIA","ENCLAVE","ATLAS","ASCENT","RAV4","CR-V","EQUINOX","ROGUE","ESCAPE","TUCSON","SPORTAGE","FORESTER","OUTBACK","TIGUAN","RX","MDX","QX60","GX"}

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in minimal local environments
    from backend import yaml_compat as yaml

from .transport import calc_transport_cost
from .retail_comps import retail_comp_is_usable

HIGH_RUST_STATES = {
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
}

TARGET_STATES = {
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC',
    'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
}

# ═══════════════════════════════════════════════════════════════════════════════
# HARD GATES — reject deals before scoring (return dos_score=0)
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_hard_gates(vehicle: dict) -> tuple:
    """Apply hard gates. Returns (passed: bool, reason: str)."""
    current_year = datetime.now().year
    year = int(vehicle.get("year") or 0)
    mileage = int(vehicle.get("mileage") or 0)
    state = (vehicle.get("state") or "").upper()
    current_bid = float(vehicle.get("current_bid") or vehicle.get("bid") or 0)
    mmr = float(
        vehicle.get("mmr_mid") or
        vehicle.get("manheim_mmr_mid") or
        vehicle.get("estimated_sale_price") or 0
    )

    # Age gate: reject vehicles older than 4 years
    if year > 0 and (current_year - year) > 4:
        return False, f"age_rejected: {current_year - year}yr old"

    # Mileage gate: reject vehicles over 50k miles
    if mileage > 50000:
        return False, f"mileage_rejected: {mileage}mi"

    # Rust state gate (bypass for vehicles <=2 years old)
    if state in HIGH_RUST_STATES and year > 0 and (current_year - year) > 2:
        return False, f"rust_state_rejected: {state}"

    # Bid ceiling gate (88% of MMR)
    if mmr > 0:
        transport = 500 if state in TARGET_STATES else 800
        fees = 350
        max_bid = (mmr * 0.88) - transport - fees
        if current_bid > max_bid:
            return False, f"ceiling_exceeded: bid ${current_bid:.0f} > max ${max_bid:.0f}"

    return True, "passed"


# ═══════════════════════════════════════════════════════════════════════════════
# SPEC-COMPLIANT SCORING COMPONENTS (each returns 0-100)
# ═══════════════════════════════════════════════════════════════════════════════

def _spec_margin_score(gross_margin: float) -> float:
    """Margin score per spec: $1500 floor, linear 50-100 up to $10k."""
    if gross_margin <= 0:
        return 0.0
    if gross_margin < 1500:
        return 0.0  # hard floor
    if gross_margin >= 10000:
        return 100.0
    return min(100.0, 50.0 + (gross_margin - 1500) / (10000 - 1500) * 50.0)


def _spec_velocity_score(auction_end: str) -> float:
    """Days until auction closes — closer = higher urgency score."""
    if not auction_end:
        return 50.0
    try:
        end = datetime.fromisoformat(str(auction_end).replace("Z", "+00:00"))
        days = (end - datetime.now(timezone.utc)).total_seconds() / 86400
        if days <= 1:
            return 100.0
        if days <= 3:
            return 85.0
        if days <= 7:
            return 70.0
        if days <= 14:
            return 50.0
        return 25.0
    except Exception:
        return 50.0


SPEC_TRUCKS = {
    "F-150", "F-250", "F-350", "SILVERADO", "SIERRA", "RAM", "RANGER",
    "TACOMA", "TUNDRA", "COLORADO", "CANYON",
}
SPEC_SUVS = {
    "TAHOE", "SUBURBAN", "YUKON", "EXPEDITION", "EXPLORER", "PILOT",
    "4RUNNER", "HIGHLANDER", "TRAVERSE", "DURANGO", "CHEROKEE", "WRANGLER",
    "NAVIGATOR", "ESCALADE", "SEQUOIA", "ARMADA", "PATHFINDER", "MURANO",
    "ACADIA", "ENCLAVE", "ATLAS", "ASCENT",
}


def _spec_segment_score(make: str, model: str) -> float:
    """Segment score: trucks 90, SUVs 80, vans 55, other 50."""
    m = (model or "").upper()
    if m in SPEC_TRUCKS:
        return 90.0
    if m in SPEC_SUVS:
        return 80.0
    if any(x in m for x in ["PICKUP", "TRUCK", "SUV"]):
        return 75.0
    if any(x in m for x in ["VAN", "MINIVAN"]):
        return 55.0
    return 50.0


SPEC_HOT_MODELS = {
    ("FORD", "F-150"), ("CHEVROLET", "TAHOE"), ("CHEVROLET", "SILVERADO"),
    ("GMC", "SIERRA"), ("TOYOTA", "TACOMA"), ("TOYOTA", "4RUNNER"),
    ("TOYOTA", "RAV4"), ("TOYOTA", "CAMRY"), ("HONDA", "ACCORD"),
    ("HONDA", "CR-V"), ("FORD", "EXPLORER"), ("FORD", "F-250"), ("RAM", "1500"),
}
SPEC_KNOWN_MAKES = {
    "FORD", "CHEVROLET", "GMC", "TOYOTA", "HONDA", "RAM", "DODGE", "JEEP",
    "NISSAN", "HYUNDAI", "KIA", "SUBARU", "VOLKSWAGEN", "BMW", "MERCEDES",
    "LEXUS", "ACURA", "INFINITI", "CADILLAC", "LINCOLN",
}


def _spec_model_score(make: str, model: str) -> float:
    """Model score: hot models 90, known makes 70, other 50."""
    key = ((make or "").upper(), (model or "").upper())
    if key in SPEC_HOT_MODELS:
        return 90.0
    if (make or "").upper() in SPEC_KNOWN_MAKES:
        return 70.0
    return 50.0


SPEC_TIER1_SOURCES = {"govplanet", "jjkane", "municibid", "gsaauctions"}
SPEC_TIER2_SOURCES = {"govdeals", "publicsurplus", "publicsurplus_tx"}
SPEC_TIER3_SOURCES = {"proxibid", "bidspotter", "hibid-v2", "hibid"}


def _spec_source_score(source_site: str) -> float:
    """Source score: tier1=80, tier2=70, tier3=60, other=50."""
    s = (source_site or "").lower()
    if s in SPEC_TIER1_SOURCES:
        return 80.0
    if s in SPEC_TIER2_SOURCES:
        return 70.0
    if s in SPEC_TIER3_SOURCES:
        return 60.0
    return 50.0


# ═══════════════════════════════════════════════════════════════════════════════
# SPEC-COMPLIANT DOS FORMULA & BID CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_dos(vehicle: dict, gross_margin: float) -> float:
    """Compute DOS: Margin×0.35 + Velocity×0.25 + Segment×0.20 + Model×0.12 + Source×0.08."""
    margin = _spec_margin_score(gross_margin)
    velocity = _spec_velocity_score(
        vehicle.get("auction_end_date") or vehicle.get("auction_end_time") or vehicle.get("auction_end") or ""
    )
    segment = _spec_segment_score(vehicle.get("make", ""), vehicle.get("model", ""))
    model = _spec_model_score(vehicle.get("make", ""), vehicle.get("model", ""))
    source = _spec_source_score(vehicle.get("source_site", ""))

    dos = (margin * 0.35 + velocity * 0.25 + segment * 0.20 + model * 0.12 + source * 0.08)
    return round(min(100.0, max(0.0, dos)), 1)


def _compute_max_bid(mmr: float, state: str) -> float:
    """Max bid = 88% MMR - transport - fees."""
    transport = 500 if (state or "").upper() in TARGET_STATES else 800
    fees = 350
    return round((mmr * 0.88) - transport - fees, 0)


def _compute_gross_margin(mmr: float, current_bid: float, state: str) -> float:
    """Gross margin = MMR - (bid + transport + fees)."""
    transport = 500 if (state or "").upper() in TARGET_STATES else 800
    fees = 350
    total_cost = current_bid + transport + fees
    return round(mmr - total_cost, 0)


def _spec_investment_grade(dos: float, gross_margin: float, roi_pct: float = 0) -> str:
    """Investment grade based on DOS and margin."""
    if dos >= 80 and gross_margin >= 3000:
        return "platinum"
    if dos >= 65 and gross_margin >= 2000:
        return "gold"
    if dos >= 50 and gross_margin >= 1500:
        return "silver"
    return "watch"


# ═══════════════════════════════════════════════════════════════════════════════
# V2 SCORING HELPERS — Codex-designed architecture
# ═══════════════════════════════════════════════════════════════════════════════

def _margin_score_v2(gross_margin: float) -> float:
    gm = float(gross_margin or 0)
    if gm <= 0: return 0.0
    if gm < 1500: return (gm / 1500.0) * 50.0
    if gm < 10000: return 50.0 + ((gm - 1500) / 8500.0) * 50.0
    return 100.0

def _velocity_score_v2(auction_end) -> float:
    try:
        if not auction_end: return 50.0
        end_str = str(auction_end).replace("Z", "+00:00")
        end = datetime.fromisoformat(end_str)
        if end.tzinfo is None: end = end.replace(tzinfo=_tz.utc)
        days = (end - datetime.now(_tz.utc)).total_seconds() / 86400
        if days <= 1: return 100.0
        if days <= 3: return 85.0
        if days <= 7: return 70.0
        if days <= 14: return 50.0
        return 25.0
    except: return 50.0

def _segment_score_v2(make: str, model: str) -> float:
    m = (model or "").upper().strip()
    if m in _TRUCKS: return 90.0
    if m in _SUVS: return 80.0
    if any(x in m for x in ["PICKUP","TRUCK"]): return 85.0
    if any(x in m for x in ["VAN","MINIVAN"]): return 55.0
    return 50.0

def _model_score_v2(make: str, model: str) -> float:
    key = ((make or "").upper().strip(), (model or "").upper().strip())
    if key in _HOT_MODELS: return 90.0
    if (make or "").upper().strip() in _KNOWN_MAKES: return 70.0
    return 50.0

def _source_score_v2(source_site: str) -> float:
    s = (source_site or "").lower().strip()
    if s in {"govplanet","jjkane","municibid","gsaauctions"}: return 80.0
    if s in {"govdeals","publicsurplus","publicsurplus_tx"}: return 70.0
    if s in {"proxibid","bidspotter","hibid-v2","hibid"}: return 60.0
    if s in {"allsurplus"}: return 55.0
    return 50.0

def _compute_dos_v2(vehicle: dict, gross_margin: float) -> float:
    margin = _margin_score_v2(gross_margin)
    velocity = _velocity_score_v2(vehicle.get("auction_end_date") or vehicle.get("auction_end_time") or vehicle.get("auction_end"))
    segment = _segment_score_v2(vehicle.get("make",""), vehicle.get("model",""))
    model = _model_score_v2(vehicle.get("make",""), vehicle.get("model",""))
    source = _source_score_v2(vehicle.get("source_site",""))
    dos = margin*0.35 + velocity*0.25 + segment*0.20 + model*0.12 + source*0.08
    return round(min(100.0, max(0.0, dos)), 1)

def _compute_max_bid_v2(mmr: float, state: str) -> float:
    transport = 500.0 if (state or "").upper() in _TARGET_STATES else 800.0
    fees = 350.0
    return round((mmr * 0.88) - transport - fees, 0)

def _compute_gross_margin_v2(mmr: float, current_bid: float, state: str) -> float:
    transport = 500.0 if (state or "").upper() in _TARGET_STATES else 800.0
    fees = 350.0
    return round(mmr - current_bid - transport - fees, 0)

def _apply_hard_gates_v2(vehicle: dict, gross_margin: float, max_bid: float) -> tuple:
    year = int(vehicle.get("year") or 0)
    mileage = int(vehicle.get("mileage") or 0)
    state = (vehicle.get("state") or "").upper()
    current_bid = float(vehicle.get("current_bid") or 0)

    if year > 0 and (_CURRENT_YEAR - year) > 4:
        return False, f"age_rejected:{_CURRENT_YEAR - year}yr"
    if mileage > 50000:
        return False, f"mileage_rejected:{mileage}mi"
    if state in _HIGH_RUST and year > 0 and (_CURRENT_YEAR - year) > 2:
        return False, f"rust_state:{state}"
    if gross_margin < 1500:
        return False, f"margin_rejected:${gross_margin:.0f}"
    if max_bid > 0 and current_bid > max_bid:
        return False, f"ceiling_exceeded:bid${current_bid:.0f}>max${max_bid:.0f}"
    return True, None

def _investment_grade_v2(dos: float, gross_margin: float) -> str:
    if dos >= 80 and gross_margin >= 3000: return "platinum"
    if dos >= 65 and gross_margin >= 2000: return "gold"
    if dos >= 50 and gross_margin >= 1500: return "silver"
    return "watch"


_CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


def _normalize_vehicle_text(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("-", " ").split())

SEGMENT_SCORES = {
    "truck": 95,
    "suv_large": 90,
    "suv_mid": 85,
    "luxury": 80,
    "ev_trending": 78,
    "sedan_popular": 65,
    "ev_other": 55,
    "sedan_other": 45,
    "coupe": 35,
    "minivan": 30,
}

TIER_1_MODELS = [
    "F-150", "Silverado 1500", "Ram 1500", "Tacoma", "RAV4",
    "CR-V", "Rogue", "Camry", "Accord", "Tesla Model Y", "Tesla Model 3",
    # High-demand gov fleet trucks
    "F-250", "F-350", "Silverado 2500", "Silverado 3500", "Ram 2500", "Ram 3500",
    "Tundra", "Sierra 1500", "Sierra 2500", "Sierra 3500",
]

TIER_2_MODELS = [
    "Highlander", "Pilot", "Explorer", "Equinox", "Corolla",
    "Civic", "Altima", "Escape", "Colorado", "Frontier",
    # Common gov fleet vehicles
    "Tahoe", "Suburban", "Yukon", "Expedition", "Durango",
    "Charger", "Impala", "Fusion", "Malibu", "Patrol",
    "Transit", "Express Van", "Savana",
]

# Model → segment classification
_MODEL_SEGMENT_MAP = {
    "F-150": "truck", "Silverado 1500": "truck", "Ram 1500": "truck",
    "Tacoma": "truck", "Tundra": "truck", "Colorado": "truck", "Frontier": "truck",
    "RAV4": "suv_mid", "CR-V": "suv_mid", "Rogue": "suv_mid", "Escape": "suv_mid",
    "Equinox": "suv_mid",
    "Highlander": "suv_large", "Pilot": "suv_large", "Explorer": "suv_large",
    "Camry": "sedan_popular", "Accord": "sedan_popular", "Corolla": "sedan_popular",
    "Civic": "sedan_popular", "Altima": "sedan_popular",
    "Tesla Model Y": "ev_trending", "Tesla Model 3": "ev_trending",
}


@functools.lru_cache(maxsize=1)
def _load_fees() -> dict:
    with open(os.path.join(_CONFIGS_DIR, "fees.yml")) as f:
        return yaml.safe_load(f).get("sites", {})


def _margin_score(bid: float, mmr_ca: float, total_cost: float) -> float:
    """Score 0-100 based on margin percentage."""
    if mmr_ca <= 0:
        return 50.0
    margin_pct = (mmr_ca - total_cost) / mmr_ca * 100
    # Map margin_pct to 0-100: 0% → 50, 20%+ → 100, negative → 0
    if margin_pct >= 20:
        return 100.0
    if margin_pct <= 0:
        return max(0.0, 50.0 + margin_pct * 2.5)
    return 50.0 + (margin_pct / 20.0) * 50.0


def _velocity_score(bid: float, year: int, mileage: float = None) -> float:
    """Score based on price point, age, and mileage (proxy for days-to-sell velocity)."""
    score = 50.0
    if bid < 10000:
        score += 20
    elif bid < 20000:
        score += 10
    if year:
        age = datetime.now().year - year
        if 1 <= age <= 3:
            score += 25
        elif age <= 5:
            score += 15
        elif age <= 7:
            score += 5
    # Mileage proxy for velocity — lower mileage = faster wholesale movement
    if mileage is not None:
        if mileage < 30000:
            score += 15
        elif mileage < 60000:
            score += 10
        elif mileage < 100000:
            score += 5
        # > 100k miles: no bonus (slower moving)
    return min(100.0, score)


def _segment_score(model: str, make: str) -> float:
    """Look up segment score from SEGMENT_SCORES."""
    segment = _MODEL_SEGMENT_MAP.get(model)
    if not segment:
        make_lower = (make or "").lower()
        model_lower = (model or "").lower()
        if any(t in model_lower for t in ["f-150", "f150", "silverado", "ram", "tacoma",
                                           "tundra", "colorado", "frontier", "ranger",
                                           "canyon", "gladiator"]):
            segment = "truck"
        elif any(t in model_lower for t in ["suv", "4runner", "pathfinder", "rav4",
                                             "cr-v", "forester", "outback", "tiguan"]):
            segment = "suv_mid"
        elif any(t in model_lower for t in ["model s", "model x", "leaf", "bolt"]):
            segment = "ev_other"
        elif make_lower in {"bmw", "mercedes", "lexus", "cadillac", "lincoln", "audi"}:
            segment = "luxury"
        else:
            segment = "sedan_other"
    return float(SEGMENT_SCORES.get(segment, 45))


def _model_score(model: str) -> float:
    """Score based on model tier."""
    if model in TIER_1_MODELS:
        return 100.0
    if model in TIER_2_MODELS:
        return 75.0
    return 50.0


# Dynamic source weights for DOS calculation (replaces flat 0.08)
# Higher weight = source has more impact on final DOS score
SOURCE_WEIGHTS = {
    # Proven government sources — highest confidence, most weight
    "govplanet": 0.10,
    "govdeals": 0.10,
    "municibid": 0.10,
    "publicsurplus": 0.10,
    "gsaauctions": 0.10,
    "usgovbid": 0.10,
    "jjkane": 0.10,
    # Mid-tier reliability
    "ritchiebros": 0.08,
    "ironplanet": 0.08,
    "proxibid": 0.06,
    "bidspotter": 0.06,
    # Lowest confidence — minimal weight
    "hibid": 0.04,
    "hibid-bidcal": 0.04,
    "hibid-v2": 0.04,
    "allsurplus": 0.04,
    # Salvage sources — very low confidence
    "iaa": 0.03,
    "copart": 0.03,
}
DEFAULT_SOURCE_WEIGHT = 0.05


def _source_weight(source_site: str) -> float:
    """Return dynamic DOS weight for source (replaces flat 0.08)."""
    source_lower = (source_site or "").lower().strip()
    for key, weight in SOURCE_WEIGHTS.items():
        if key in source_lower:
            return weight
    return DEFAULT_SOURCE_WEIGHT


def _source_score(source_site: str) -> float:
    """Score based on auction source — government fleet sources rank highest."""
    source_lower = (source_site or "").lower().strip()
    scores = {
        # Government fleet — highest quality, clean title, maintained
        "govdeals": 100.0,
        "publicsurplus": 95.0,
        "govplanet": 95.0,
        "gsaauctions": 93.0,
        "municibid": 88.0,
        "usgovbid": 85.0,
        # Government-adjacent — reliable but mixed quality
        "jjkane": 82.0,
        "ritchiebros": 80.0,
        "ironplanet": 80.0,
        # Commercial aggregators — variable quality
        "allsurplus": 75.0,
        "proxibid": 72.0,
        "bidspotter": 70.0,
        "hibid": 68.0,
        "hibid-bidcal": 68.0,
        "hibid-v2": 68.0,
        # Salvage/insurance — lower quality
        "iaa": 55.0,
        "copart": 50.0,
    }
    # Check for partial matches
    for key, score in scores.items():
        if key in source_lower:
            return score
    return 60.0  # default


_SEGMENT_TIER_1_MODELS = {
    "f150", "silverado", "ram1500", "rav4", "rogue", "crv", "tacoma",
    "camry", "accord", "model3", "modely", "tucson", "equinox", "escape",
}

_SEGMENT_TIER_2_MODELS = {
    "tahoe", "suburban", "expedition", "tundra", "ranger", "explorer",
    "highlander", "pilot", "durango", "traverse", "odyssey", "sienna",
    "carnival", "pacifica",
}

_LUXURY_MAKES = {"bmw", "mercedes", "mercedes benz", "lexus", "cadillac", "lincoln", "audi"}

PROXY_RETAIL_MULTIPLIER_MIN = 1.10
PROXY_RETAIL_MULTIPLIER_MAX = 1.28
ESTIMATED_DAYS_TO_SALE_BY_TIER = {
    1: 25,
    2: 35,
    3: 50,
    4: 70,
}
SCORE_VERSION = "manheim_ready_v5"
INVESTMENT_GRADE_PROXY_SCORES = {
    "Platinum": 100.0,
    "Gold": 82.0,
    "Silver": 64.0,
    "Bronze": 25.0,
}
PRICE_BASIS_INCREMENT = 50.0


def _is_hd_commercial_truck(
    normalized_model: str,
    normalized_model_compact: str,
    normalized_make: str,
) -> bool:
    if "silverado" in normalized_model and ("2500" in normalized_model or "3500" in normalized_model):
        return True
    if "sierra" in normalized_model and ("2500" in normalized_model or "3500" in normalized_model):
        return True
    if "ram" in normalized_model and ("2500" in normalized_model or "3500" in normalized_model):
        return True
    if normalized_make in {"chevrolet", "chevy", "gmc", "ram"} and (
        "2500" in normalized_model or "3500" in normalized_model
    ):
        return True
    if any(token in normalized_model for token in ("f-250", "f 250", "f-350", "f 350")):
        return True
    if normalized_make == "ford" and any(token in normalized_model_compact for token in ("f250", "f350")):
        return True
    return False


def _segment_tier(model: str, make: str) -> int:
    normalized_model = _normalize_vehicle_text(model)
    normalized_model_compact = normalized_model.replace(" ", "").replace("-", "")
    normalized_make = _normalize_vehicle_text(make)

    if _is_hd_commercial_truck(normalized_model, normalized_model_compact, normalized_make):
        return 3

    if any(token in normalized_model_compact for token in _SEGMENT_TIER_1_MODELS):
        return 1
    if any(token in normalized_model_compact for token in _SEGMENT_TIER_2_MODELS):
        return 2

    if normalized_make in _LUXURY_MAKES:
        return 3

    segment = _MODEL_SEGMENT_MAP.get(model)
    if segment in {"sedan_popular", "sedan_other", "luxury"}:
        return 3

    if "sedan" in normalized_model:
        return 3

    return 4


def _estimated_days_to_sale(segment_tier: int) -> int:
    return int(ESTIMATED_DAYS_TO_SALE_BY_TIER.get(segment_tier, 70))


def _investment_grade(retail_ctm_pct: float, estimated_days_to_sale: int, segment_tier: int) -> str:
    if segment_tier >= 4:
        return "Bronze"
    if retail_ctm_pct <= 62 and estimated_days_to_sale <= 25 and segment_tier == 1:
        return "Platinum"
    if retail_ctm_pct <= 66 and estimated_days_to_sale <= 35 and segment_tier <= 2:
        return "Gold"
    if retail_ctm_pct <= 72 and estimated_days_to_sale <= 50:
        return "Silver"
    return "Bronze"


def _segment_tier_score(segment_tier: int) -> float:
    return {
        1: 100.0,
        2: 80.0,
        3: 55.0,
        4: 30.0,
    }.get(segment_tier, 30.0)


def _roi_per_day_score(roi_per_day: float) -> float:
    if roi_per_day <= 0:
        return 0.0
    if roi_per_day >= 250:
        return 100.0
    return max(0.0, min(100.0, (roi_per_day / 250.0) * 100.0))


def _transport_cost_score(transport_cost: float) -> float:
    if transport_cost <= 300:
        return 100.0
    if transport_cost <= 600:
        return 80.0
    if transport_cost <= 900:
        return 60.0
    if transport_cost <= 1200:
        return 40.0
    return 20.0


def _time_pressure_score(auction_end: Optional[str]) -> float:
    if not auction_end:
        return 40.0

    parsed_end: Optional[datetime] = None
    try:
        parsed_end = datetime.fromisoformat(str(auction_end).replace("Z", "+00:00"))
    except ValueError:
        try:
            from dateutil import parser as dateparser  # type: ignore
            parsed_end = dateparser.parse(str(auction_end))
        except Exception:
            return 40.0

    if parsed_end is None:
        return 40.0

    if parsed_end.tzinfo is not None:
        now = datetime.now(parsed_end.tzinfo)
    else:
        now = datetime.now()
    hours_remaining = max((parsed_end - now).total_seconds() / 3600.0, 0.0)

    if hours_remaining <= 6:
        return 100.0
    if hours_remaining <= 24:
        return 85.0
    if hours_remaining <= 48:
        return 65.0
    if hours_remaining <= 72:
        return 50.0
    return 35.0


def _weighted_score(
    investment_grade: str,
    roi_per_day: float,
    segment_tier: int,
    mmr_confidence_proxy: float,
    transport_cost: float,
    source_score: float,
    auction_end: Optional[str],
) -> float:
    return (
        INVESTMENT_GRADE_PROXY_SCORES.get(investment_grade, 25.0) * 0.30
        + _roi_per_day_score(roi_per_day) * 0.20
        + _segment_tier_score(segment_tier) * 0.15
        + max(0.0, min(100.0, mmr_confidence_proxy)) * 0.10
        + _transport_cost_score(transport_cost) * 0.10
        + source_score * 0.10
        + _time_pressure_score(auction_end) * 0.05
    )


def _range_width_penalty(range_width_pct: Optional[float]) -> float:
    if range_width_pct is None:
        return 0.0
    width = max(float(range_width_pct), 0.0)
    if width >= 24:
        return 22.0
    if width >= 20:
        return 16.0
    if width >= 16:
        return 10.0
    if width >= 12:
        return 5.0
    return 0.0


def _resolve_confidence_proxy(
    mmr_confidence_proxy: Optional[float],
    manheim_confidence: Optional[float],
    manheim_source_status: Optional[str],
    manheim_range_width_pct: Optional[float],
) -> float:
    if manheim_confidence is not None:
        confidence_proxy = float(manheim_confidence)
        if confidence_proxy <= 1.0:
            confidence_proxy *= 100.0
    elif mmr_confidence_proxy is not None:
        confidence_proxy = float(mmr_confidence_proxy)
    else:
        confidence_proxy = 50.0

    if manheim_source_status == "live":
        confidence_proxy -= _range_width_penalty(manheim_range_width_pct)

    return max(0.0, min(100.0, confidence_proxy))


def _resolve_proxy_retail_multiplier(
    mmr_lookup_basis: Optional[str],
    confidence_proxy: float,
) -> float:
    basis = (mmr_lookup_basis or "unknown").strip().lower()
    normalized_confidence = max(0.0, min(float(confidence_proxy or 0.0), 100.0))

    if basis.startswith("model:"):
        multiplier = 1.24
    elif basis.startswith("make:"):
        multiplier = 1.20
    elif basis.startswith("special:police_interceptor"):
        multiplier = 1.17
    elif basis.startswith("special:commercial_vehicle"):
        multiplier = 1.12
    elif basis.startswith("segment:"):
        multiplier = 1.15
    else:
        multiplier = 1.14

    if normalized_confidence >= 85.0:
        multiplier += 0.02
    elif normalized_confidence >= 70.0:
        multiplier += 0.0
    elif normalized_confidence >= 55.0:
        multiplier -= 0.02
    else:
        multiplier -= 0.04

    return round(
        max(PROXY_RETAIL_MULTIPLIER_MIN, min(PROXY_RETAIL_MULTIPLIER_MAX, multiplier)),
        3,
    )


def _proxy_ceiling_penalty_pct(
    *,
    pricing_maturity: Optional[str],
    mmr_lookup_basis: Optional[str],
    confidence_proxy: float,
    manheim_source_status: Optional[str],
) -> float:
    if manheim_source_status == "live" or pricing_maturity == "live_market":
        return 0.0

    normalized_confidence = max(0.0, min(float(confidence_proxy or 0.0), 100.0))
    basis = (mmr_lookup_basis or "unknown").strip().lower()

    if pricing_maturity == "market_comp":
        return 0.0 if normalized_confidence >= 75.0 else 1.0

    if basis.startswith("model:") and normalized_confidence >= 80.0:
        return 2.0
    if basis.startswith("make:") and normalized_confidence >= 65.0:
        return 4.0
    return 6.0


def compute_bid_ceiling(
    current_bid: float,
    mmr_ca: float,
    total_cost: float,
    segment_tier: int,
    investment_grade: str,
    buyer_premium_pct: float,
    doc_fee: float,
    transport: float,
    recon_reserve: float,
    manheim_range_width_pct: Optional[float] = None,
    manheim_source_status: Optional[str] = None,
    pricing_maturity: Optional[str] = None,
    mmr_lookup_basis: Optional[str] = None,
    confidence_proxy: float = 0.0,
) -> dict:
    if investment_grade == "Bronze":
        return {
            "bid_ceiling_pct": None,
            "max_bid": 0.0,
            "bid_headroom": -max(float(current_bid or 0), 0.0),
            "ceiling_reason": "bronze_reject",
            "ceiling_pass": False,
        }

    ceiling_pct = None
    reason = None
    if investment_grade == "Platinum" and segment_tier == 1:
        ceiling_pct = 88.0
        reason = "platinum_tier1_all_in_le_88pct_mmr"
    elif investment_grade in {"Platinum", "Gold"} and segment_tier in {1, 2}:
        ceiling_pct = 85.0
        reason = "gold_band_tier1_2_all_in_le_85pct_mmr"
    elif investment_grade == "Silver":
        ceiling_pct = 82.0
        reason = "silver_all_in_le_82pct_mmr"
    else:
        return {
            "bid_ceiling_pct": None,
            "max_bid": 0.0,
            "bid_headroom": -max(float(current_bid or 0), 0.0),
            "ceiling_reason": f"unsupported_grade_tier ({investment_grade}/Tier{segment_tier})",
            "ceiling_pass": False,
        }

    if manheim_source_status == "live" and manheim_range_width_pct is not None:
        width = max(float(manheim_range_width_pct), 0.0)
        if width > 20:
            ceiling_pct -= 4.0
            reason = f"{reason}; live_range_penalty_4pct"
        elif width > 16:
            ceiling_pct -= 3.0
            reason = f"{reason}; live_range_penalty_3pct"
        elif width > 12:
            ceiling_pct -= 2.0
            reason = f"{reason}; live_range_penalty_2pct"
        elif width > 8:
            ceiling_pct -= 1.0
            reason = f"{reason}; live_range_penalty_1pct"
        else:
            reason = f"{reason}; live_range_preserved"

    proxy_penalty_pct = _proxy_ceiling_penalty_pct(
        pricing_maturity=pricing_maturity,
        mmr_lookup_basis=mmr_lookup_basis,
        confidence_proxy=confidence_proxy,
        manheim_source_status=manheim_source_status,
    )
    if proxy_penalty_pct > 0:
        ceiling_pct = max(70.0, float(ceiling_pct) - proxy_penalty_pct)
        reason = f"{reason}; proxy_penalty_{int(proxy_penalty_pct)}pct"

    if mmr_ca <= 0:
        return {
            "bid_ceiling_pct": ceiling_pct,
            "max_bid": 0.0,
            "bid_headroom": -max(float(current_bid or 0), 0.0),
            "ceiling_reason": "missing_mmr_for_ceiling",
            "ceiling_pass": False,
        }

    ceiling_total_cost = mmr_ca * (ceiling_pct / 100.0)
    fixed_costs = float(doc_fee or 0.0) + float(transport or 0.0) + float(recon_reserve or 0.0)
    bid_multiplier = 1.0 + max(float(buyer_premium_pct or 0.0), 0.0)
    max_bid = (ceiling_total_cost - fixed_costs) / bid_multiplier if bid_multiplier > 0 else 0.0
    max_bid = max(0.0, max_bid)
    bid_headroom = max_bid - max(float(current_bid or 0.0), 0.0)
    ceiling_pass = total_cost <= ceiling_total_cost and bid_headroom >= 0

    if not ceiling_pass and bid_headroom < 0:
        reason = f"{reason}; negative_headroom"
    elif not ceiling_pass:
        reason = f"{reason}; total_cost_exceeds_ceiling"

    return {
        "bid_ceiling_pct": round(ceiling_pct, 2),
        "max_bid": round(max_bid, 2),
        "bid_headroom": round(bid_headroom, 2),
        "ceiling_reason": reason,
        "ceiling_pass": ceiling_pass,
    }


def _recon_reserve(mileage: float = None, is_police_or_fleet: bool = False) -> float:
    miles = max(float(mileage or 0), 0.0)
    mileage_component = 3.0 * (miles / 1000.0)
    reserve = min(500.0 + mileage_component, 1200.0)
    if is_police_or_fleet:
        reserve += 300.0
    return reserve


def _parse_auction_end(auction_end: Optional[str]) -> Optional[datetime]:
    if not auction_end:
        return None
    raw_value = str(auction_end).strip()
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _auction_stage_hours_remaining(auction_end: Optional[str]) -> Optional[float]:
    parsed = _parse_auction_end(auction_end)
    if parsed is None:
        return None
    hours_remaining = (parsed - datetime.now(timezone.utc)).total_seconds() / 3600.0
    return round(max(hours_remaining, 0.0), 2)


def resolve_pricing_maturity(
    *,
    manheim_source_status: Optional[str],
    manheim_mmr_mid: Optional[float],
    pricing_source: Optional[str],
    retail_comp_price_estimate: Optional[float],
    retail_comp_count: Optional[int],
    retail_comp_confidence: Optional[float],
    retail_comp_usable: bool,
    mmr_lookup_basis: Optional[str],
) -> str:
    if manheim_source_status == "live" and (manheim_mmr_mid or 0) > 0:
        return "live_market"

    market_comp_sources = {"retail_market_cache", "dealer_sales_history"}
    if retail_comp_usable and pricing_source in market_comp_sources:
        return "market_comp"
    if retail_comp_usable and (retail_comp_price_estimate or 0) > 0 and int(retail_comp_count or 0) > 0:
        return "market_comp"
    if retail_comp_usable and (retail_comp_confidence or 0) > 0:
        return "market_comp"

    if pricing_source == "mmr_proxy":
        return "proxy"
    if manheim_source_status in {"fallback", "unavailable"}:
        return "proxy"
    if mmr_lookup_basis and mmr_lookup_basis != "unknown":
        return "proxy"

    return "unknown"


def _current_bid_trust_score(
    auction_stage_hours_remaining: Optional[float],
    pricing_maturity: str,
) -> Optional[float]:
    if auction_stage_hours_remaining is None:
        return None

    hours_remaining = max(float(auction_stage_hours_remaining), 0.0)
    if hours_remaining > 72:
        base_score = 0.15
    elif hours_remaining > 24:
        base_score = 0.25
    elif hours_remaining > 6:
        base_score = 0.4
    elif hours_remaining > 1:
        base_score = 0.6
    else:
        base_score = 0.8

    maturity_adjustment = {
        "live_market": 0.05,
        "market_comp": -0.05,
        "proxy": -0.15,
        "unknown": -0.25,
    }.get(pricing_maturity, -0.25)

    return round(max(0.05, min(0.9, base_score + maturity_adjustment)), 2)


def _round_price_basis(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    normalized_value = max(float(value), 0.0)
    if normalized_value <= 0:
        return 0.0
    return round(round(normalized_value / PRICE_BASIS_INCREMENT) * PRICE_BASIS_INCREMENT, 2)


def _expected_close_floor_pct(
    auction_stage_hours_remaining: Optional[float],
    pricing_maturity: str,
    confidence_proxy: float,
) -> float:
    if auction_stage_hours_remaining is None:
        base_floor_pct = 0.9
    else:
        hours_remaining = max(float(auction_stage_hours_remaining), 0.0)
        if hours_remaining > 72:
            base_floor_pct = 0.7
        elif hours_remaining > 24:
            base_floor_pct = 0.78
        elif hours_remaining > 6:
            base_floor_pct = 0.86
        elif hours_remaining > 1:
            base_floor_pct = 0.93
        else:
            base_floor_pct = 0.98

    maturity_adjustment = {
        "live_market": -0.01,
        "market_comp": 0.0,
        "proxy": 0.04,
        "unknown": 0.07,
    }.get(pricing_maturity, 0.07)

    normalized_confidence = max(0.0, min(float(confidence_proxy or 0.0), 100.0))
    if normalized_confidence >= 80.0:
        confidence_adjustment = -0.02
    elif normalized_confidence >= 65.0:
        confidence_adjustment = -0.01
    elif normalized_confidence <= 45.0:
        confidence_adjustment = 0.02
    else:
        confidence_adjustment = 0.0

    return max(0.6, min(0.99, base_floor_pct + maturity_adjustment + confidence_adjustment))


def resolve_expected_close_bid(
    *,
    current_bid: float,
    max_bid: Optional[float],
    current_bid_trust_score: Optional[float],
    auction_stage_hours_remaining: Optional[float],
    pricing_maturity: str,
    confidence_proxy: float,
) -> dict:
    normalized_current_bid = max(float(current_bid or 0.0), 0.0)
    if normalized_current_bid <= 0:
        return {
            "expected_close_bid": None,
            "expected_close_source": None,
        }

    conservative_anchor = max(float(max_bid or 0.0), 0.0)
    if conservative_anchor <= 0:
        rounded_current_bid = _round_price_basis(normalized_current_bid)
        return {
            "expected_close_bid": rounded_current_bid,
            "expected_close_source": "current_bid_no_ceiling_anchor",
        }

    floor_pct = _expected_close_floor_pct(
        auction_stage_hours_remaining=auction_stage_hours_remaining,
        pricing_maturity=pricing_maturity,
        confidence_proxy=confidence_proxy,
    )
    expected_close_floor = conservative_anchor * floor_pct

    if expected_close_floor <= normalized_current_bid:
        return {
            "expected_close_bid": _round_price_basis(normalized_current_bid),
            "expected_close_source": "current_bid_at_or_above_conservative_floor",
        }

    trust_score = current_bid_trust_score
    if trust_score is None:
        trust_score = 0.5
    trust_score = max(0.0, min(float(trust_score), 1.0))

    expected_close_bid = normalized_current_bid + (
        (expected_close_floor - normalized_current_bid) * (1.0 - trust_score)
    )
    expected_close_bid = max(normalized_current_bid, min(expected_close_bid, expected_close_floor))

    return {
        "expected_close_bid": _round_price_basis(expected_close_bid),
        "expected_close_source": f"blend_current_bid_with_{pricing_maturity}_max_bid_floor",
    }


def resolve_acquisition_price_basis(
    *,
    current_bid: float,
    expected_close_bid: Optional[float],
    current_bid_trust_score: Optional[float],
) -> dict:
    normalized_current_bid = max(float(current_bid or 0.0), 0.0)
    normalized_expected_close = max(float(expected_close_bid or 0.0), 0.0)

    if normalized_expected_close <= normalized_current_bid or normalized_expected_close <= 0:
        resolved_basis = _round_price_basis(normalized_current_bid)
        return {
            "acquisition_price_basis": resolved_basis,
            "acquisition_basis_source": "current_bid",
        }

    if current_bid_trust_score is None:
        blended_basis = (normalized_current_bid + normalized_expected_close) / 2.0
        return {
            "acquisition_price_basis": _round_price_basis(blended_basis),
            "acquisition_basis_source": "blend_current_bid_expected_close",
        }

    trust_score = max(0.0, min(float(current_bid_trust_score), 1.0))
    if trust_score <= 0.3:
        return {
            "acquisition_price_basis": _round_price_basis(normalized_expected_close),
            "acquisition_basis_source": "expected_close",
        }

    if trust_score >= 0.75:
        return {
            "acquisition_price_basis": _round_price_basis(normalized_current_bid),
            "acquisition_basis_source": "current_bid",
        }

    blended_basis = (
        normalized_current_bid * trust_score
        + normalized_expected_close * (1.0 - trust_score)
    )
    return {
        "acquisition_price_basis": _round_price_basis(blended_basis),
        "acquisition_basis_source": "blend_current_bid_expected_close",
    }


def score_deal(
    bid: float,
    mmr_ca: float,
    state: str,
    source_site: str,
    model: str = "",
    make: str = "",
    year: int = None,
    fees_cfg: dict = None,
    rates_cfg: dict = None,
    miles_cfg: dict = None,
    mileage: float = None,
    is_police_or_fleet: bool = False,
    auction_end: Optional[str] = None,
    mmr_lookup_basis: Optional[str] = None,
    mmr_confidence_proxy: Optional[float] = None,
    retail_comp_price_estimate: Optional[float] = None,
    retail_comp_low: Optional[float] = None,
    retail_comp_high: Optional[float] = None,
    retail_comp_count: Optional[int] = None,
    retail_comp_confidence: Optional[float] = None,
    pricing_source: Optional[str] = None,
    pricing_updated_at: Optional[str] = None,
    manheim_mmr_mid: Optional[float] = None,
    manheim_mmr_low: Optional[float] = None,
    manheim_mmr_high: Optional[float] = None,
    manheim_range_width_pct: Optional[float] = None,
    manheim_confidence: Optional[float] = None,
    manheim_source_status: Optional[str] = None,
    manheim_updated_at: Optional[str] = None,
    # Condition enrichment (optional)
    condition_grade: Optional[str] = None,
    condition_score: Optional[int] = None,
    condition_signals: Optional[list] = None,
) -> dict:
    """
    Compute full DOS score and deal metrics.

    Returns a dict with premium, doc_fee, transport, recon_reserve, total_cost,
    margin, margin_score, velocity_score, segment_score, model_score,
    source_score, and dos_score (0-100).
    """
    if fees_cfg is None:
        fees_cfg = _load_fees()

    site_fees = fees_cfg.get(source_site, {"buyers_premium_pct": 10.0, "doc_fee": 50})
    buyer_premium_pct = site_fees.get("buyers_premium_pct", 10.0) / 100.0
    raw_bid = max(float(bid or 0.0), 0.0)
    raw_premium = raw_bid * buyer_premium_pct
    doc_fee = site_fees.get("doc_fee", 50)
    transport = calc_transport_cost(state, rates_cfg=rates_cfg, miles_cfg=miles_cfg)
    recon_reserve = _recon_reserve(mileage=mileage, is_police_or_fleet=is_police_or_fleet)
    raw_total_cost = raw_bid + raw_premium + doc_fee + transport + recon_reserve
    selected_mmr = float(manheim_mmr_mid) if manheim_mmr_mid is not None and float(manheim_mmr_mid) > 0 else float(mmr_ca or 0)

    # ═══════════════════════════════════════════════════════════════════════════
    # V2 BID CEILING AND MARGIN — compute early for hard gates
    # ═══════════════════════════════════════════════════════════════════════════
    _v2_max_bid = _compute_max_bid_v2(selected_mmr, state) if selected_mmr > 0 else 0
    _v2_gross_margin = _compute_gross_margin_v2(selected_mmr, raw_bid, state) if selected_mmr > 0 else -9999

    # ═══════════════════════════════════════════════════════════════════════════
    # HARD GATES — reject before scoring (using v2 logic)
    # ═══════════════════════════════════════════════════════════════════════════
    vehicle_for_gates = {
        "year": year,
        "mileage": mileage,
        "state": state,
        "current_bid": raw_bid,
        "mmr_mid": selected_mmr,
        "manheim_mmr_mid": manheim_mmr_mid,
    }
    _v2_passed, _v2_rejection_reason = _apply_hard_gates_v2(vehicle_for_gates, _v2_gross_margin, _v2_max_bid)

    # Compute v2 DOS and grade
    vehicle_for_dos_v2 = {
        "make": make,
        "model": model,
        "source_site": source_site,
        "auction_end": auction_end,
        "auction_end_date": auction_end,
    }
    _v2_dos = _compute_dos_v2(vehicle_for_dos_v2, _v2_gross_margin) if _v2_passed else 0.0
    _v2_grade = _investment_grade_v2(_v2_dos, _v2_gross_margin) if _v2_passed else "rejected"

    # Also run legacy gate check for comparison — log divergence when legacy rejects but v2 passes
    gate_passed, gate_reason = _apply_hard_gates(vehicle_for_gates)
    if not gate_passed and _v2_passed:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "[GATE_DIVERGENCE] Legacy gate rejected (%s) but v2 passed — review gate logic", gate_reason
        )
    if not _v2_passed:
        # Return early with dos_score=0 and rejection reason (using v2 values)
        return {
            "dos_score": 0,
            "score": 0,
            "rejection_reason": _v2_rejection_reason,
            "gate_passed": False,
            "premium": round(raw_premium, 2),
            "buyer_premium_amount": round(raw_premium, 2),
            "buyer_premium_pct": round(buyer_premium_pct, 4),
            "doc_fee": doc_fee,
            "transport": round(transport, 2),
            "recon_reserve": round(recon_reserve, 2),
            "total_cost": round(raw_total_cost, 2),
            "gross_margin": round(_v2_gross_margin, 2) if selected_mmr > 0 else 0,
            "margin": round(_v2_gross_margin, 2) if selected_mmr > 0 else 0,
            "max_bid": round(_v2_max_bid, 2) if _v2_max_bid > 0 else 0,
            "investment_grade": "rejected",
            "score_version": SCORE_VERSION,
        }

    retail_comp_result = {
        "retail_comp_price_estimate": retail_comp_price_estimate,
        "retail_comp_low": retail_comp_low,
        "retail_comp_high": retail_comp_high,
        "retail_comp_count": retail_comp_count,
        "retail_comp_confidence": retail_comp_confidence,
        "pricing_source": pricing_source,
        "pricing_updated_at": pricing_updated_at,
    }
    use_retail_comps = retail_comp_is_usable(retail_comp_result)
    confidence_proxy = _resolve_confidence_proxy(
        mmr_confidence_proxy=mmr_confidence_proxy,
        manheim_confidence=manheim_confidence,
        manheim_source_status=manheim_source_status,
        manheim_range_width_pct=manheim_range_width_pct,
    )
    retail_proxy_multiplier = (
        None
        if use_retail_comps
        else _resolve_proxy_retail_multiplier(
            mmr_lookup_basis=mmr_lookup_basis,
            confidence_proxy=confidence_proxy,
        )
    )
    retail_asking_price_estimate = (
        float(retail_comp_price_estimate)
        if use_retail_comps and retail_comp_price_estimate is not None
        else selected_mmr * float(retail_proxy_multiplier or PROXY_RETAIL_MULTIPLIER_MIN)
    )
    selected_pricing_source = (pricing_source or "retail_comps") if use_retail_comps else "mmr_proxy"
    pricing_maturity = resolve_pricing_maturity(
        manheim_source_status=manheim_source_status,
        manheim_mmr_mid=manheim_mmr_mid,
        pricing_source=selected_pricing_source,
        retail_comp_price_estimate=retail_comp_price_estimate,
        retail_comp_count=retail_comp_count,
        retail_comp_confidence=retail_comp_confidence,
        retail_comp_usable=use_retail_comps,
        mmr_lookup_basis=mmr_lookup_basis,
    )
    auction_stage_hours_remaining = _auction_stage_hours_remaining(auction_end)
    current_bid_trust_score = _current_bid_trust_score(
        auction_stage_hours_remaining=auction_stage_hours_remaining,
        pricing_maturity=pricing_maturity,
    )
    segment_tier = _segment_tier(model, make)
    estimated_days_to_sale = _estimated_days_to_sale(segment_tier)
    provisional_retail_ctm_pct = (
        (raw_total_cost / retail_asking_price_estimate * 100.0)
        if retail_asking_price_estimate > 0
        else 100.0
    )
    provisional_investment_grade = _investment_grade(
        provisional_retail_ctm_pct,
        estimated_days_to_sale,
        segment_tier,
    )
    ceiling_metrics = compute_bid_ceiling(
        current_bid=raw_bid,
        mmr_ca=selected_mmr,
        total_cost=raw_total_cost,
        segment_tier=segment_tier,
        investment_grade=provisional_investment_grade,
        buyer_premium_pct=buyer_premium_pct,
        doc_fee=doc_fee,
        transport=transport,
        recon_reserve=recon_reserve,
        manheim_range_width_pct=manheim_range_width_pct,
        manheim_source_status=manheim_source_status,
        pricing_maturity=pricing_maturity,
        mmr_lookup_basis=mmr_lookup_basis,
        confidence_proxy=confidence_proxy,
    )
    expected_close_result = resolve_expected_close_bid(
        current_bid=raw_bid,
        max_bid=ceiling_metrics.get("max_bid"),
        current_bid_trust_score=current_bid_trust_score,
        auction_stage_hours_remaining=auction_stage_hours_remaining,
        pricing_maturity=pricing_maturity,
        confidence_proxy=confidence_proxy,
    )
    basis_result = resolve_acquisition_price_basis(
        current_bid=raw_bid,
        expected_close_bid=expected_close_result.get("expected_close_bid"),
        current_bid_trust_score=current_bid_trust_score,
    )
    acquisition_price_basis = max(float(basis_result.get("acquisition_price_basis") or raw_bid), 0.0)
    projected_buyer_premium = acquisition_price_basis * buyer_premium_pct
    projected_total_cost = (
        acquisition_price_basis
        + projected_buyer_premium
        + doc_fee
        + transport
        + recon_reserve
    )
    wholesale_margin = selected_mmr - projected_total_cost
    gross_margin = retail_asking_price_estimate - projected_total_cost
    m_score = _margin_score(acquisition_price_basis, selected_mmr, projected_total_cost)
    v_score = _velocity_score(acquisition_price_basis, year, mileage=mileage)
    seg_score = _segment_score(model, make)
    mod_score = _model_score(model)
    src_score = _source_score(source_site)
    wholesale_ctm_pct = (projected_total_cost / selected_mmr * 100.0) if selected_mmr > 0 else 100.0
    retail_ctm_pct = (
        (projected_total_cost / retail_asking_price_estimate * 100.0)
        if retail_asking_price_estimate > 0
        else 100.0
    )
    roi_per_day = gross_margin / estimated_days_to_sale if estimated_days_to_sale > 0 else 0.0
    investment_grade = _investment_grade(retail_ctm_pct, estimated_days_to_sale, segment_tier)

    current_year = datetime.now().year
    rust_state_bypass = bool(
        state and state.upper() in HIGH_RUST_STATES
        and year and year >= current_year - 2
    )
    if rust_state_bypass:
        print(f'[BYPASS] Rust state {state.upper()} allowed — vehicle is {year} (≤3yr old)')

    # Dynamic source weight (replaces flat 0.08)
    src_weight = _source_weight(source_site)
    # Normalize other weights: they sum to 0.92 at flat 0.08, scale to (1 - src_weight)
    other_weight_scale = (1.0 - src_weight) / 0.92
    legacy_dos_score = (
        m_score * (0.35 * other_weight_scale)
        + v_score * (0.25 * other_weight_scale)
        + seg_score * (0.20 * other_weight_scale)
        + mod_score * (0.12 * other_weight_scale)
        + src_score * src_weight
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # SPEC-COMPLIANT DOS FORMULA
    # DOS = Margin×0.35 + Velocity×0.25 + Segment×0.20 + Model×0.12 + Source×0.08
    # ═══════════════════════════════════════════════════════════════════════════
    vehicle_for_dos = {
        "make": make,
        "model": model,
        "source_site": source_site,
        "auction_end": auction_end,
        "auction_end_date": auction_end,
    }
    spec_dos_score = _compute_dos(vehicle_for_dos, gross_margin)
    spec_max_bid = _compute_max_bid(selected_mmr, state) if selected_mmr > 0 else 0
    spec_gross_margin = _compute_gross_margin(selected_mmr, raw_bid, state) if selected_mmr > 0 else gross_margin
    spec_investment_grade = _spec_investment_grade(spec_dos_score, spec_gross_margin)

    # Keep weighted_score for backward compatibility comparison
    weighted_score = _weighted_score(
        investment_grade=investment_grade,
        roi_per_day=roi_per_day,
        segment_tier=segment_tier,
        mmr_confidence_proxy=confidence_proxy,
        transport_cost=transport,
        source_score=src_score,
        auction_end=auction_end,
    )

    return {
        "premium": round(projected_buyer_premium, 2),
        "buyer_premium_amount": round(projected_buyer_premium, 2),
        "buyer_premium_pct": round(buyer_premium_pct, 4),
        "doc_fee": doc_fee,
        "transport": round(transport, 2),
        "recon_reserve": round(recon_reserve, 2),
        "total_cost": round(projected_total_cost, 2),
        "projected_total_cost": round(projected_total_cost, 2),
        "acquisition_price_basis": round(acquisition_price_basis, 2),
        "acquisition_basis_source": basis_result.get("acquisition_basis_source"),
        "margin": round(_v2_gross_margin, 2) if selected_mmr > 0 else round(gross_margin, 2),
        "gross_margin": round(_v2_gross_margin, 2) if selected_mmr > 0 else round(gross_margin, 2),
        "wholesale_margin": round(wholesale_margin, 2),
        "margin_score": round(m_score, 2),
        "velocity_score": round(v_score, 2),
        "segment_score": round(seg_score, 2),
        "model_score": round(mod_score, 2),
        "source_score": round(src_score, 2),
        "source_weight": round(src_weight, 4),
        "retail_proxy_multiplier": retail_proxy_multiplier,
        "retail_asking_price_estimate": round(retail_asking_price_estimate, 2),
        "retail_comp_price_estimate": round(float(retail_comp_price_estimate), 2) if retail_comp_price_estimate is not None else None,
        "retail_comp_low": round(float(retail_comp_low), 2) if retail_comp_low is not None else None,
        "retail_comp_high": round(float(retail_comp_high), 2) if retail_comp_high is not None else None,
        "retail_comp_count": int(retail_comp_count or 0),
        "retail_comp_confidence": round(float(retail_comp_confidence), 3) if retail_comp_confidence is not None else None,
        "pricing_source": selected_pricing_source,
        "pricing_maturity": pricing_maturity,
        "pricing_updated_at": pricing_updated_at,
        "expected_close_bid": expected_close_result.get("expected_close_bid"),
        "expected_close_source": expected_close_result.get("expected_close_source"),
        "current_bid_trust_score": current_bid_trust_score,
        "auction_stage_hours_remaining": auction_stage_hours_remaining,
        "manheim_mmr_mid": round(float(manheim_mmr_mid), 2) if manheim_mmr_mid is not None else None,
        "manheim_mmr_low": round(float(manheim_mmr_low), 2) if manheim_mmr_low is not None else None,
        "manheim_mmr_high": round(float(manheim_mmr_high), 2) if manheim_mmr_high is not None else None,
        "manheim_range_width_pct": round(float(manheim_range_width_pct), 2) if manheim_range_width_pct is not None else None,
        "manheim_confidence": round(float(manheim_confidence), 3) if manheim_confidence is not None else None,
        "manheim_source_status": manheim_source_status or "unavailable",
        "manheim_updated_at": manheim_updated_at,
        "ctm_pct": round(retail_ctm_pct, 2),
        "wholesale_ctm_pct": round(wholesale_ctm_pct, 2),
        "retail_ctm_pct": round(retail_ctm_pct, 2),
        "segment_tier": segment_tier,
        "estimated_days_to_sale": estimated_days_to_sale,
        "roi_per_day": round(roi_per_day, 2),
        "mmr_lookup_basis": mmr_lookup_basis or "unknown",
        "mmr_confidence_proxy": round(confidence_proxy, 2),
        "investment_grade": _v2_grade,
        "legacy_investment_grade": investment_grade,
        "legacy_dos_score": round(legacy_dos_score, 2),
        "weighted_dos_score": round(weighted_score, 2),
        "dos_score": round(_v2_dos, 2),
        "score": round(_v2_dos, 2),
        "max_bid": round(_v2_max_bid, 2) if _v2_max_bid > 0 else ceiling_metrics.get("max_bid"),
        "spec_gross_margin": round(spec_gross_margin, 2),
        "spec_dos_score": round(spec_dos_score, 2),
        "spec_investment_grade": spec_investment_grade,
        "score_version": SCORE_VERSION,
        "gate_passed": True,
        "rejection_reason": _v2_rejection_reason,
        "rust_state_bypass": rust_state_bypass,
        # Condition enrichment (from score_condition() in condition.py)
        "condition_grade": condition_grade,
        "condition_score": condition_score,
        "condition_signals": condition_signals or [],
        **ceiling_metrics,
    }
