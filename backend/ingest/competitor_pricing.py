"""Competitive pricing engine — real market comps from competitor_sales.

This module is the pricing endpoint for DealerScope's competitive pricing
intelligence. It queries the ``competitor_sales`` table (scraped sold auction
listings) for vehicles comparable to a target — same make/model, within
``+/- COMPETITOR_COMP_YEAR_WINDOW`` years and ``+/- COMPETITOR_COMP_MILEAGE_WINDOW``
miles — and returns the **actual median sale price**, the **count of comps**, a
low/high band, and the **date range** the comps span.

When at least ``COMPETITOR_COMP_MIN_COUNT`` real comps exist for a vehicle
class, the DOS scoring engine uses this actual market data instead of the
model-proxy MMR for ceiling/max-bid calculations (see ``backend.ingest.score``).

The pure helpers (``normalize_vehicle_class``, ``summarize_comps``,
``compute_divergence``) contain no I/O so they are unit-testable without a
database connection.
"""

from __future__ import annotations

import math
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional


# Thresholds (env-overridable for tuning without a redeploy).
COMPETITOR_COMP_MIN_COUNT = int(os.getenv("COMPETITOR_COMP_MIN_COUNT", "5"))
COMPETITOR_COMP_YEAR_WINDOW = int(os.getenv("COMPETITOR_COMP_YEAR_WINDOW", "2"))
COMPETITOR_COMP_MILEAGE_WINDOW = int(os.getenv("COMPETITOR_COMP_MILEAGE_WINDOW", "25000"))
COMPETITOR_COMP_DIVERGENCE_THRESHOLD = float(
    os.getenv("COMPETITOR_COMP_DIVERGENCE_THRESHOLD", "0.15")
)
COMPETITOR_COMP_MAX_AGE_DAYS = int(os.getenv("COMPETITOR_COMP_MAX_AGE_DAYS", "365"))
COMPETITOR_COMP_QUERY_LIMIT = int(os.getenv("COMPETITOR_COMP_QUERY_LIMIT", "400"))
COMPETITOR_COMP_CACHE_TTL_SECONDS = int(
    os.getenv("COMPETITOR_COMP_CACHE_TTL_SECONDS", str(6 * 60 * 60))
)

_CACHE_LOCK = threading.Lock()
_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Vehicle class normalization
# ---------------------------------------------------------------------------
# Top vehicle classes DealerScope scores most. Each entry maps a normalized
# class slug to the (make, model-pattern) it matches. Order matters: more
# specific patterns (e.g. f-250) must be checked before less specific ones.
_VEHICLE_CLASS_RULES: List[tuple] = [
    ("f-250", "ford", re.compile(r"\bf[\s\-]?250\b")),
    ("f-150", "ford", re.compile(r"\bf[\s\-]?150\b")),
    ("silverado-1500", "chevrolet", re.compile(r"silverado.*1500|1500.*silverado|\bsilverado\b")),
]


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").split())


def normalize_vehicle_class(make: Any, model: Any) -> Optional[str]:
    """Map a (make, model) pair to a normalized DealerScope vehicle-class slug.

    Returns ``None`` when the vehicle is not one of the tracked classes.
    """
    make_norm = _normalize_text(make)
    model_norm = _normalize_text(model)
    blob = f"{make_norm} {model_norm}".strip()
    for slug, required_make, pattern in _VEHICLE_CLASS_RULES:
        if required_make and required_make not in make_norm and required_make not in blob:
            continue
        if pattern.search(blob):
            return slug
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "")
        if value == "":
            return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _safe_int(value: Any) -> Optional[int]:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _percentile(values: List[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return float(ordered[idx])


@dataclass
class CompetitorCompResult:
    competitor_comp_price: Optional[float] = None
    competitor_comp_low: Optional[float] = None
    competitor_comp_high: Optional[float] = None
    competitor_comp_count: int = 0
    competitor_comp_date_start: Optional[str] = None
    competitor_comp_date_end: Optional[str] = None
    competitor_comp_sources: List[str] = field(default_factory=list)
    vehicle_class: Optional[str] = None
    pricing_source: Optional[str] = None
    pricing_updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key in ("competitor_comp_price", "competitor_comp_low", "competitor_comp_high"):
            if payload[key] is not None:
                payload[key] = round(float(payload[key]), 2)
        return payload


def _empty_result() -> Dict[str, Any]:
    return CompetitorCompResult().to_dict()


def summarize_comps(
    rows: List[Dict[str, Any]],
    *,
    year: Optional[int],
    mileage: Optional[float],
    vehicle_class: Optional[str] = None,
    year_window: int = COMPETITOR_COMP_YEAR_WINDOW,
    mileage_window: int = COMPETITOR_COMP_MILEAGE_WINDOW,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Reduce raw competitor_sales rows to a comp summary.

    A row is a comparable when its year is within ``+/- year_window`` of the
    target and, when both mileages are known, its mileage is within
    ``+/- mileage_window``. Rows missing a mileage are kept (year/class match is
    still informative); rows missing a positive sale_price are dropped.
    """
    now = now or datetime.now(timezone.utc)
    target_year = _safe_int(year)
    target_mileage = _safe_float(mileage)

    prices: List[float] = []
    dates: List[datetime] = []
    sources: List[str] = []

    for row in rows:
        sale_price = _safe_float(row.get("sale_price"))
        if not sale_price or sale_price <= 0:
            continue

        row_year = _safe_int(row.get("year"))
        if target_year is not None and row_year is not None:
            if abs(row_year - target_year) > year_window:
                continue

        row_mileage = _safe_float(row.get("mileage"))
        if target_mileage is not None and row_mileage is not None and row_mileage > 0:
            if abs(row_mileage - target_mileage) > mileage_window:
                continue

        prices.append(sale_price)
        source = str(row.get("source") or "").strip().lower()
        if source:
            sources.append(source)
        sale_dt = _parse_dt(row.get("auction_end_date")) or _parse_dt(row.get("scraped_at"))
        if sale_dt:
            dates.append(sale_dt)

    if not prices:
        result = CompetitorCompResult(vehicle_class=vehicle_class)
        return result.to_dict()

    dates.sort()
    result = CompetitorCompResult(
        competitor_comp_price=float(median(prices)),
        competitor_comp_low=_percentile(prices, 0.2),
        competitor_comp_high=_percentile(prices, 0.8),
        competitor_comp_count=len(prices),
        competitor_comp_date_start=dates[0].isoformat() if dates else None,
        competitor_comp_date_end=dates[-1].isoformat() if dates else None,
        competitor_comp_sources=sorted(set(sources)),
        vehicle_class=vehicle_class,
        pricing_source="competitor_sales",
        pricing_updated_at=(dates[-1].isoformat() if dates else now.isoformat()),
    )
    return result.to_dict()


def competitor_comp_is_usable(
    result: Optional[Dict[str, Any]],
    min_count: int = COMPETITOR_COMP_MIN_COUNT,
) -> bool:
    """True when a comp summary has enough real comps to drive ceiling pricing."""
    if not result:
        return False
    price = _safe_float(result.get("competitor_comp_price"))
    count = int(result.get("competitor_comp_count") or 0)
    return bool(price and price > 0 and count >= min_count)


def compute_divergence(
    proxy_value: Any,
    actual_value: Any,
    threshold: float = COMPETITOR_COMP_DIVERGENCE_THRESHOLD,
) -> Dict[str, Any]:
    """Compare model-proxy pricing against actual comp pricing.

    Returns the signed divergence fraction (actual relative to proxy) and a
    boolean flag set when the magnitude exceeds ``threshold``.
    """
    proxy = _safe_float(proxy_value)
    actual = _safe_float(actual_value)
    if not proxy or proxy <= 0 or actual is None or actual <= 0:
        return {"divergence_pct": None, "divergence_flag": False}
    divergence = (actual - proxy) / proxy
    return {
        "divergence_pct": round(divergence, 4),
        "divergence_flag": abs(divergence) > threshold,
    }


# ---------------------------------------------------------------------------
# Database-backed lookup
# ---------------------------------------------------------------------------
def _cache_key(year: Optional[int], make: str, model: str, mileage: Optional[float]) -> str:
    mileage_bucket = ""
    mileage_value = _safe_float(mileage)
    if mileage_value is not None:
        mileage_bucket = str(int(mileage_value // 5000) * 5000)
    return f"{year}|{_normalize_text(make)}|{_normalize_text(model)}|{mileage_bucket}"


def _get_cached(key: str, now: datetime) -> Optional[Dict[str, Any]]:
    with _CACHE_LOCK:
        entry = _MEMORY_CACHE.get(key)
        if not entry:
            return None
        if _parse_dt(entry.get("expires_at")) and _parse_dt(entry["expires_at"]) < now:
            _MEMORY_CACHE.pop(key, None)
            return None
        return dict(entry["result"])


def _set_cached(key: str, result: Dict[str, Any], now: datetime) -> None:
    expires_at = now.timestamp() + COMPETITOR_COMP_CACHE_TTL_SECONDS
    with _CACHE_LOCK:
        _MEMORY_CACHE[key] = {
            "result": dict(result),
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        }


def _fetch_rows(
    *,
    year: Optional[int],
    make: str,
    model: str,
    vehicle_class: Optional[str],
    supabase_client: Any,
) -> List[Dict[str, Any]]:
    """Fetch candidate comp rows from competitor_sales via the Supabase client."""
    queries = []
    select_cols = "id,source,sale_price,year,make,model,mileage,vehicle_class,auction_end_date,scraped_at,state"

    if vehicle_class:
        query = (
            supabase_client.table("competitor_sales")
            .select(select_cols)
            .eq("vehicle_class", vehicle_class)
        )
        if year is not None:
            query = query.gte("year", int(year) - COMPETITOR_COMP_YEAR_WINDOW).lte(
                "year", int(year) + COMPETITOR_COMP_YEAR_WINDOW
            )
        queries.append(query.order("auction_end_date", desc=True).limit(COMPETITOR_COMP_QUERY_LIMIT))

    make_norm = (make or "").strip()
    model_norm = (model or "").strip()
    if make_norm and model_norm:
        query = (
            supabase_client.table("competitor_sales")
            .select(select_cols)
            .ilike("make", make_norm)
            .ilike("model", f"%{model_norm}%")
        )
        if year is not None:
            query = query.gte("year", int(year) - COMPETITOR_COMP_YEAR_WINDOW).lte(
                "year", int(year) + COMPETITOR_COMP_YEAR_WINDOW
            )
        queries.append(query.order("auction_end_date", desc=True).limit(COMPETITOR_COMP_QUERY_LIMIT))

    rows: List[Dict[str, Any]] = []
    seen_ids = set()
    for query in queries:
        try:
            response = query.execute()
        except Exception:
            continue
        for row in response.data or []:
            row_id = row.get("id")
            if row_id is not None and row_id in seen_ids:
                continue
            if row_id is not None:
                seen_ids.add(row_id)
            rows.append(row)
    return rows


def get_competitor_comps(
    year: Optional[int],
    make: str,
    model: str,
    mileage: Optional[float] = None,
    supabase_client: Any = None,
) -> Dict[str, Any]:
    """Return actual-market comp metadata for a target vehicle.

    Looks up comparable sold listings (same make/model, +/-2 years, +/-25k miles)
    from ``competitor_sales`` and returns median sale price, comp count, low/high
    band, the date range the comps span, and the contributing sources. Falls back
    to a safe empty result when no client is available or the lookup fails.
    """
    vehicle_class = normalize_vehicle_class(make, model)
    if supabase_client is None:
        result = _empty_result()
        result["vehicle_class"] = vehicle_class
        return result

    now = datetime.now(timezone.utc)
    key = _cache_key(year, make, model, mileage)
    cached = _get_cached(key, now)
    if cached is not None:
        return cached

    try:
        rows = _fetch_rows(
            year=year,
            make=make,
            model=model,
            vehicle_class=vehicle_class,
            supabase_client=supabase_client,
        )
        result = summarize_comps(
            rows,
            year=year,
            mileage=mileage,
            vehicle_class=vehicle_class,
            now=now,
        )
    except Exception:
        result = _empty_result()
        result["vehicle_class"] = vehicle_class

    _set_cached(key, result, now)
    return result
