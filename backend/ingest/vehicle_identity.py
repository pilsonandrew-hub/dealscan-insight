"""Vehicle title parsing and proxy MMR estimate helpers for ingest.

Extracted from the Apify ingest router without behavior changes. These helpers
remain heuristic/proxy logic; live Manheim/retail evidence still outranks them.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

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


def estimate_mmr(make: str, model: str) -> float:
    return estimate_mmr_details(make, model)["mmr"]


def estimate_mmr_details(make: str, model: str) -> dict:
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
