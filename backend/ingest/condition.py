"""Condition grade proxy — infer vehicle condition from available metadata."""

import re
import threading
from datetime import datetime
from typing import Optional

# -------------------------------------------------------------------
# Module-level VIN decode cache (lives for duration of the process)
# -------------------------------------------------------------------
_vin_cache: dict = {}
_vin_cache_lock = threading.Lock()

_NHTSA_TIMEOUT = 3.0  # seconds — non-fatal on timeout/error

# ---------------------------------------------------------------------------
# Legacy damage / no-start signal lists (kept for correctness)
# ---------------------------------------------------------------------------
_DAMAGE_SIGNALS = (
    "flood", "fire", "hail", "storm", "water damage", "salvage",
    "frame damage", "structural damage", "rollover", "totaled",
)

_NO_START_SIGNALS = (
    "no start", "not running", "does not run", "non-runner",
    "non runner", "will not start", "won't start",
)

# ---------------------------------------------------------------------------
# NLP keyword scoring tables
# ---------------------------------------------------------------------------
# Negative signals → lower score
_NEGATIVE_SIGNALS: dict[str, int] = {
    "salvage": -10,
    "flood": -10,
    "fire damage": -10,
    "frame damage": -10,
    "rebuilt": -8,
    "as-is": -5,
    "as is": -5,
    "no start": -10,
    "needs work": -7,
    "parts only": -10,
    "wrecked": -10,
    "branded title": -10,
    "odometer rollback": -10,
    "lemon": -8,
}

# Positive signals → raise score
_POSITIVE_SIGNALS: dict[str, int] = {
    "fleet maintained": 5,
    "fleet vehicle": 4,
    "low miles": 5,
    "one owner": 4,
    "service records": 4,
    "carfax": 3,
    "clean title": 5,
    "government fleet": 5,
    "well maintained": 4,
    "runs and drives": 10,
    "runs & drives": 10,
    "runs and moves": 8,
    "runs & moves": 8,
    "fleet maintained": 6,
    "fleet vehicle": 5,
    "maintenance records": 5,
    "jump to start": -8,
    "jump start": -8,
    "body damage": -10,
    "paint damage": -6,
    "body/paint damage": -10,
    "frame damage": -20,
    "structural damage": -20,

}

# Numeric grade-code patterns in descriptions ("Grade 5", "Condition 3", etc.)
_GRADE_CODE_SCORES: dict[int, int] = {
    5: 25,   # Grade 5 / Condition 5 → strong positive
    4: 15,
    3: 0,    # neutral
    2: -20,
    1: -30,
}


# ---------------------------------------------------------------------------
# NHTSA VIN decode
# ---------------------------------------------------------------------------

def _fetch_nhtsa_vin(vin: str) -> Optional[dict]:
    """Fetch NHTSA VIN decode synchronously with a short timeout.

    Returns a dict with keys: ModelYear, Make, Model, VehicleType, ErrorCode.
    Returns None on network error / timeout (non-fatal).
    Results are cached in _vin_cache for the lifetime of the process.
    """
    if not vin or len(vin.strip()) < 11:
        return None

    vin = vin.strip().upper()

    with _vin_cache_lock:
        if vin in _vin_cache:
            return _vin_cache[vin]

    parsed: Optional[dict] = None
    try:
        import json
        import urllib.request

        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
        with urllib.request.urlopen(url, timeout=_NHTSA_TIMEOUT) as resp:  # noqa: S310
            data = json.loads(resp.read())

        results_map = {item["Variable"]: item["Value"] for item in data.get("Results", [])}
        parsed = {
            "ModelYear": results_map.get("Model Year"),
            "Make": results_map.get("Make"),
            "Model": results_map.get("Model"),
            "VehicleType": results_map.get("Vehicle Type"),
            "ErrorCode": str(results_map.get("Error Code") or "0").strip(),
        }
    except Exception:  # timeout, network error, JSON parse — all non-fatal
        parsed = None

    with _vin_cache_lock:
        _vin_cache[vin] = parsed

    return parsed


# ---------------------------------------------------------------------------
# Keyword NLP helpers
# ---------------------------------------------------------------------------

def _keyword_score(text: str) -> tuple[int, list[str]]:
    """Scan lowercased text for positive/negative condition signals.

    Returns (score_delta, list_of_matched_keywords).
    """
    text_lower = text.lower()
    delta = 0
    matched: list[str] = []

    for keyword, adjustment in _NEGATIVE_SIGNALS.items():
        if keyword in text_lower:
            delta += adjustment
            matched.append(keyword)

    for keyword, adjustment in _POSITIVE_SIGNALS.items():
        if keyword in text_lower:
            delta += adjustment
            matched.append(keyword)

    return delta, matched


def _grade_code_score(text: str) -> tuple[int, list[str]]:
    """Detect numeric grade/condition codes in description text.

    Patterns matched: 'grade 5', 'condition 3', 'grade code 4', etc.
    Returns (score_delta, list_of_matched_tags).
    """
    text_lower = text.lower()
    delta = 0
    matched: list[str] = []
    pattern = re.compile(r"\b(?:grade|condition)(?:\s+code)?\s+([1-5])\b")
    for m in pattern.finditer(text_lower):
        code = int(m.group(1))
        if code in _GRADE_CODE_SCORES:
            delta += _GRADE_CODE_SCORES[code]
            matched.append(f"grade_{code}")
    return delta, matched


# ---------------------------------------------------------------------------
# Main scoring entry-point
# ---------------------------------------------------------------------------

def score_condition(
    title: str = "",
    description: str = "",
    mileage: int = 0,
    year: int = 0,
    damage_type: str = "",
    vin: str = "",
) -> dict:
    # Add type coercion for mileage
    if isinstance(mileage, str):
        try:
            mileage = float(re.sub(r'[^-9.]', '', mileage)) if mileage else None
        except (ValueError, TypeError):
            mileage = None
    """Full condition scoring.

    Returns a dict:
        condition_grade   : "A" / "B" / "C" / "D" / "F"
        condition_score   : int 0-100
        condition_signals : list[str] — detected positive/negative keywords
        vin_suspicious    : bool — True if NHTSA reports the VIN as invalid
        vin_decoded       : dict | None — raw NHTSA fields (or None on failure)
    """
    combined_text = f"{title} {description} {damage_type}"
    signals: list[str] = []

    # ------------------------------------------------------------------
    # FAST PATH: critical damage / no-start signals → immediate F grade
    # ------------------------------------------------------------------

    # Check damage_type first (exact field)
    if damage_type:
        for signal in _DAMAGE_SIGNALS:
            if signal in damage_type.lower():
                signals.append(signal)
                return {
                    "condition_grade": "F",
                    "condition_score": 0,
                    "condition_signals": signals,
                    "vin_suspicious": False,
                    "vin_decoded": None,
                }

    text_lower = combined_text.lower()

    # Check no-start signals anywhere in the combined text
    for signal in _NO_START_SIGNALS:
        if signal in text_lower:
            signals.append(signal)
            return {
                "condition_grade": "F",
                "condition_score": 0,
                "condition_signals": signals,
                "vin_suspicious": False,
                "vin_decoded": None,
            }

    # Check damage signals in title/description as well
    for signal in _DAMAGE_SIGNALS:
        if signal in text_lower:
            signals.append(signal)
            return {
                "condition_grade": "F",
                "condition_score": 0,
                "condition_signals": signals,
                "vin_suspicious": False,
                "vin_decoded": None,
            }

    # ------------------------------------------------------------------
    # 1. Base score from age heuristic
    # ------------------------------------------------------------------
    if year and year > 1900:
        age = datetime.now().year - year
        if age <= 0:
            base_score = 85
        elif age <= 1:
            base_score = 82
        elif age <= 2:
            base_score = 70
        elif age <= 3:
            base_score = 65
        elif age <= 5:
            base_score = 55
        elif age <= 7:
            base_score = 45
        else:
            base_score = 35
    else:
        base_score = 55  # unknown year → neutral

    # ------------------------------------------------------------------
    # 2. Mileage penalty
    # ------------------------------------------------------------------
    if mileage:
        if mileage >= 100_000:
            base_score -= 25
        elif mileage >= 80_000:
            base_score -= 20
        elif mileage >= 50_000:
            base_score -= 15
        elif mileage >= 30_000:
            base_score -= 8

    # ------------------------------------------------------------------
    # 3. Grade-code signals from description
    # ------------------------------------------------------------------
    gc_delta, gc_signals = _grade_code_score(combined_text)
    base_score += gc_delta
    signals.extend(gc_signals)

    # ------------------------------------------------------------------
    # 4. Keyword NLP
    # ------------------------------------------------------------------
    kw_delta, kw_signals = _keyword_score(combined_text)
    signals.extend(kw_signals)
    base_score += kw_delta

    # ------------------------------------------------------------------
    # 5. NHTSA VIN decode
    # ------------------------------------------------------------------
    vin_suspicious = False
    vin_decoded: Optional[dict] = None

    if vin:
        vin_decoded = _fetch_nhtsa_vin(vin)
        if vin_decoded is not None:
            error_code = vin_decoded.get("ErrorCode", "0") or "0"
            # Error code "0" means success; anything else = problem VIN
            if str(error_code).strip() not in ("0", ""):
                vin_suspicious = True
                base_score -= 15
                signals.append("vin_invalid")

    # ------------------------------------------------------------------
    # 6. Clamp and grade
    # ------------------------------------------------------------------
    condition_score = max(0, min(100, base_score))

    if condition_score >= 80:
        grade = "A"
    elif condition_score >= 65:
        grade = "B"
    elif condition_score >= 50:
        grade = "C"
    elif condition_score >= 35:
        grade = "D"
    else:
        grade = "F"

    return {
        "condition_grade": grade,
        "condition_score": condition_score,
        "condition_signals": signals,
        "vin_suspicious": vin_suspicious,
        "vin_decoded": vin_decoded,
    }


# ---------------------------------------------------------------------------
# Legacy compatibility wrapper
# ---------------------------------------------------------------------------

def compute_condition_grade(
    title: str = "",
    description: str = "",
    mileage: int = 0,
    year: int = 0,
    damage_type: str = "",
) -> str:
    """Legacy wrapper — returns one of: "Excellent", "Good", "Fair", "Poor".

    New callers should use score_condition() for the full result dict.

    Priority order (preserved from original implementation):
    1. Damage-type / no-start signals → "Poor" immediately
    2. Grade-code signals in description ("Grade 5", "Condition 2", etc.)
    3. Age-based baseline
    4. Mileage adjustment
    5. Keyword NLP (positive/negative signals)
    """
    result = score_condition(
        title=title,
        description=description,
        mileage=mileage,
        year=year,
        damage_type=damage_type,
    )
    _grade_map = {"A": "Excellent", "B": "Good", "C": "Fair", "D": "Poor", "F": "Poor"}
    return _grade_map.get(result["condition_grade"], "Fair")
