"""Canonical identity helpers for ingest deduplication.

These helpers preserve the existing ingest.py identity behavior while making the
pure canonical-id logic independently testable during the monolith split.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


MAKE_ALIASES = {
    "chev": "chevrolet",
    "chevy": "chevrolet",
    "vw": "volkswagen",
    "mercedes-benz": "mercedes",
    "mercedesbenz": "mercedes",
}


def normalize_make_for_identity(make: str) -> str:
    """Normalize make exactly as the legacy ingest canonical-id path did."""
    normalized = re.sub(r"[^a-z0-9]", "", (make or "").lower().strip())
    return MAKE_ALIASES.get(normalized, normalized)


def normalize_model_for_identity(model: str) -> str:
    """Normalize model exactly as the legacy ingest canonical-id path did."""
    words = re.sub(r"[^a-z0-9 ]", "", (model or "").lower().strip()).split()
    return " ".join(words[:2])


def compute_canonical_id(vehicle: dict[str, Any]) -> str:
    """Compute the canonical deduplication identity for an ingest vehicle.

    Precedence intentionally matches the historical router implementation:
    1. 17-character VIN hash
    2. listing_url hash
    3. year/make/model/state/mileage-bucket hash
    """
    vin = (vehicle.get("vin") or "").strip().upper()
    if len(vin) == 17:
        return hashlib.sha256(vin.encode()).hexdigest()[:32]

    # Use listing_url as high-entropy fallback when VIN is missing.
    # This prevents AllSurplus, GSA, and other no-VIN sources from false-deduplicating
    # distinct vehicles that share year/make/model/state but have no mileage/VIN.
    listing_url = (vehicle.get("listing_url") or "").strip()
    if listing_url:
        return hashlib.sha256(listing_url.encode()).hexdigest()[:32]

    year = str(vehicle.get("year") or vehicle.get("model_year") or "")
    make = normalize_make_for_identity(vehicle.get("make") or "")
    model = normalize_model_for_identity(vehicle.get("model") or "")
    state = (vehicle.get("state") or vehicle.get("location_state") or "")[:2].upper()
    mileage = int(vehicle.get("mileage") or vehicle.get("meter_count") or 0)
    bucket = round(mileage / 2500) * 2500
    key = f"{year}_{make}_{model}_{state}_{bucket}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]
