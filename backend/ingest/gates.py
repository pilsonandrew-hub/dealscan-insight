"""Pure ingest gating helpers for DealerScope vehicle listings.

Extracted from the ingest router without changing rejection reasons or thresholds.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Optional

LOW_RUST_STATES = {
    "AZ", "CA", "NV", "CO", "NM", "UT", "TX", "FL", "GA", "SC", "TN", "NC", "VA", "WA", "OR", "HI"
}

from backend.business_rules.constants import HIGH_RUST_STATES as _CANONICAL_HIGH_RUST_STATES

HIGH_RUST_STATES = set(_CANONICAL_HIGH_RUST_STATES)

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
}

TARGET_STATES = {
    "AZ", "CA", "NV", "CO", "NM", "UT", "TX", "FL", "GA", "SC", "TN", "NC", "VA", "WA", "OR", "HI"
}

COMMERCIAL_PATTERNS = [
    r"\bEconoline\b", r"\bExpress\s*Cargo\b", r"\bProMaster\s*Cargo\b",
    r"\bSprinter\s*Cargo\b", r"\bTransit\s*Cargo\b", r"\bSavana\s*Cargo\b",
    r"\bE-250\b", r"\bE-350\b", r"\b4500\b", r"\b5500\b",
    r"\bCutaway\b", r"\bChassis\s*Cab\b",
    r"\bDump\s*Truck\b", r"\bBox\s*Truck\b", r"\bBucket\s*Truck\b",
    r"\bStake\s*Bed\b", r"\bFlatbed\b", r"\bStep\s*Van\b", r"\bShuttle\b",
    r"\bUtility\s*Bed\b", r"\bRefrigerator\s*Truck\b",
]

HD_PICKUP_MAKES = re.compile(
    r"\b(Ram|Chevy|Chevrolet|Silverado|GMC|Sierra|Ford|F-250|F-350)\b",
    re.IGNORECASE,
)

TITLE_BRAND_PATTERNS = [
    ("salvage", r"\bsalvage\b"),
    ("rebuilt", r"\brebuilt\s+title\b"),
    ("flood", r"\bflood\b"),
    ("lemon", r"\blemon\s+law\b|\blemon\s+title\b"),
    ("no title", r"\bno[\s-]title\b|\btitle[\s-]?less\b|\bmissing[\s-]title\b"),
    ("frame damage", r"\bframe[\s-]+damage\b"),
    ("structural damage", r"\bstructural[\s-]+damage\b"),
    ("crash", r"\bcrash(?:ed)?\b|\bcollision\s+damage\b|\baccident\s+damage\b"),
    ("front end damage", r"\bfront[\s-]+end[\s-]+damage\b"),
    ("rear end damage", r"\brear[\s-]+end[\s-]+damage\b"),
    ("side damage", r"\bside[\s-]+damage\b"),
    ("fire damage", r"\bfire[\s-]+damage\b"),
    ("hail damage", r"\bhail[\s-]+damage\b"),
    ("airbag deployed", r"\bair\s*bag\s+deployed\b"),
    ("rust damage", r"\brust[\s-]+damage\b|\brust[\s-]+through\b|\brusted[\s-]+out\b|\bheavy[\s-]+rust\b"),
    ("won't start", r"\bwon'?t\s+start\b|\bdoes\s+not\s+start\b|\bno\s+start\b|\binop(?:erable)?\b"),
    ("needs engine", r"\bneeds?\s+engine\b|\bbad\s+engine\b|\bblown\s+engine\b|\bengine\s+knock\b|\bengine\s+miss\b"),
    ("won't go into gear", r"\bwon'?t\s+(?:go\s+into|shift\s+into|engage)\s+gear\b|\bno\s+reverse\b|\bno\s+drive\b|\bstuck\s+in\s+(?:park|neutral|gear)\b|\bslipping\s+(?:trans|transmission)\b"),
    ("needs transmission", r"\bneeds?\s+trans(?:mission)?\b|\bbad\s+trans(?:mission)?\b|\bno\s+trans(?:mission)?\b|\btransmission\s+(?:fail|issues?|problem|gone|dead|shot)\b"),
    ("needs repair", r"\bneeds?\s+(?:major\s+)?repair\b|\bproject\s+(?:car|vehicle|truck)\b"),
    ("as-is no warranty", r"\bas[\s-]?is\b.*\bno\s+warrant|\bno\s+warrant.*\bas[\s-]?is\b"),
    ("parts only", r"\bparts[\s-]+only\b|\bfor\s+parts\b|\bfor\s+scrap\b"),
    ("non-op", r"\bnon[\s-]?op\b"),
    ("incomplete", r"\bincomplete\s+vehicle\b|\bmissing\s+(?:engine|drivetrain|motor)\b"),
]

VEHICLE_TITLE_KEYWORDS = [
    "ford", "chevrolet", "chevy", "dodge", "ram", "toyota", "honda", "nissan",
    "jeep", "gmc", "chrysler", "hyundai", "kia", "subaru", "mazda", "volkswagen",
    "bmw", "mercedes", "audi", "lexus", "acura", "infiniti", "cadillac", "lincoln",
    "buick", "mitsubishi", "volvo", "tesla", "truck", "pickup", "suv", "sedan",
    "coupe", "van", "vehicle", "automobile", "f-150", "silverado", "tacoma", "tundra",
]


def is_commercial_hd_tonnage(title: str) -> bool:
    """Return True only if title contains a cargo/commercial 2500 or 3500."""
    has_hd_numeral = bool(re.search(r"\b[23]500\b", title, re.IGNORECASE))
    if not has_hd_numeral:
        return False
    if HD_PICKUP_MAKES.search(title):
        return False
    return True


def find_title_brand_issue(vehicle: dict[str, Any]) -> Optional[str]:
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
        for label, pattern in TITLE_BRAND_PATTERNS:
            matched = re.search(pattern, value, re.IGNORECASE)
            if not matched and field_name == "vin":
                compact_pattern = pattern.replace(r"\b", "")
                if compact_pattern != pattern:
                    matched = re.search(compact_pattern, value, re.IGNORECASE)
            if matched:
                return f"title_brand_rejected ({field_name} matched '{label}')"
    return None


def passes_basic_gates(
    vehicle: dict[str, Any],
    *,
    determine_vehicle_tier: Callable[[Any, Any], str],
    current_year: Optional[int] = None,
) -> dict[str, Any]:
    """Five-layer institutional filter preserving legacy rejection reasons."""
    make = vehicle.get("make", "") or ""
    vin = vehicle.get("vin", "") or ""
    title = (vehicle.get("title") or "").lower()
    title_has_vehicle = any(kw in title for kw in VEHICLE_TITLE_KEYWORDS)
    if not make.strip() and len(vin) != 17 and not title_has_vehicle:
        return {"pass": False, "reason": "not_a_vehicle (no make or valid VIN)"}

    bid = vehicle.get("current_bid", 0)
    state = vehicle.get("state", "")
    year = vehicle.get("year")
    mileage = vehicle.get("mileage")
    if bid <= 0:
        return {"pass": False, "reason": f"bid_not_positive (${bid:,.0f})"}

    if state and state not in US_STATES:
        return {"pass": False, "reason": f"non_us_state ({state})"}

    if state in HIGH_RUST_STATES:
        resolved_year = current_year if current_year is not None else datetime.now().year
        if not year or year < resolved_year - 2:
            return {"pass": False, "reason": f"high_rust_state ({state})"}

    title_brand_issue = find_title_brand_issue(vehicle)
    if title_brand_issue:
        return {"pass": False, "reason": title_brand_issue}

    display_title = (vehicle.get("title") or "").strip()
    if any(re.search(p, display_title, re.IGNORECASE) for p in COMMERCIAL_PATTERNS):
        return {"pass": False, "reason": f"commercial_vehicle ({display_title[:50]})"}
    if is_commercial_hd_tonnage(display_title):
        return {"pass": False, "reason": f"commercial_hd_tonnage ({display_title[:50]})"}

    vehicle_tier = determine_vehicle_tier(year, mileage)
    if vehicle_tier == "rejected":
        return {"pass": False, "reason": "age_or_mileage_exceeded"}

    if not vehicle.get("listing_url"):
        return {"pass": False, "reason": "no_listing_url"}

    return {"pass": True, "reason": "ok"}
