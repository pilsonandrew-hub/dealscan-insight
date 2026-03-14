"""Retail comp service layer for ingest scoring.

This module intentionally prefers low-fragility sources:
1. Cached retail market rows from `market_prices`
2. Derived dealer sale history from `dealer_sales`

If neither source can produce an adequate estimate, callers should fall back
to the existing MMR proxy path.
"""
from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, List, Optional


RETAIL_COMP_CACHE_TTL_SECONDS = int(os.getenv("RETAIL_COMP_CACHE_TTL_SECONDS", str(12 * 60 * 60)))
RETAIL_COMP_NEGATIVE_CACHE_TTL_SECONDS = int(
    os.getenv("RETAIL_COMP_NEGATIVE_CACHE_TTL_SECONDS", str(60 * 60))
)
RETAIL_COMP_CONFIDENCE_THRESHOLD = float(os.getenv("RETAIL_COMP_CONFIDENCE_THRESHOLD", "0.60"))
RETAIL_COMP_MIN_COUNT = int(os.getenv("RETAIL_COMP_MIN_COUNT", "2"))

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
_CACHE_PATH = os.getenv("RETAIL_COMP_CACHE_PATH", os.path.join(_CACHE_DIR, "retail_comps.json"))
_CACHE_LOCK = threading.Lock()
_FILE_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}


@dataclass
class RetailCompResult:
    retail_comp_price_estimate: Optional[float] = None
    retail_comp_low: Optional[float] = None
    retail_comp_high: Optional[float] = None
    retail_comp_count: int = 0
    retail_comp_confidence: Optional[float] = None
    pricing_source: Optional[str] = None
    pricing_updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload["retail_comp_confidence"] is not None:
            payload["retail_comp_confidence"] = round(float(payload["retail_comp_confidence"]), 3)
        for key in ("retail_comp_price_estimate", "retail_comp_low", "retail_comp_high"):
            if payload[key] is not None:
                payload[key] = round(float(payload[key]), 2)
        return payload


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("-", " ").split())


def _cache_key(year: int, make: str, model: str, state: Optional[str]) -> str:
    return f"{int(year)}|{_normalize_text(make)}|{_normalize_text(model)}|{(state or '').strip().upper()}"


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _percentile(values: List[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return float(ordered[idx])


def retail_comp_is_usable(result: Optional[Dict[str, Any]]) -> bool:
    if not result:
        return False
    price = _safe_float(result.get("retail_comp_price_estimate"))
    count = int(result.get("retail_comp_count") or 0)
    confidence = _safe_float(result.get("retail_comp_confidence")) or 0.0
    return bool(price and price > 0 and count >= RETAIL_COMP_MIN_COUNT and confidence >= RETAIL_COMP_CONFIDENCE_THRESHOLD)


def _empty_result() -> Dict[str, Any]:
    return RetailCompResult().to_dict()


def _text_candidates(value: str) -> List[str]:
    normalized = _normalize_text(value)
    raw = (value or "").strip()
    candidates: List[str] = []
    for candidate in (normalized, raw):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _load_file_cache_locked() -> Dict[str, Dict[str, Any]]:
    global _FILE_CACHE
    if _FILE_CACHE is not None:
        return _FILE_CACHE

    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                _FILE_CACHE = data
            else:
                _FILE_CACHE = {}
    except FileNotFoundError:
        _FILE_CACHE = {}
    except Exception:
        _FILE_CACHE = {}
    return _FILE_CACHE


def _write_file_cache_locked(cache: Dict[str, Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        temp_path = f"{_CACHE_PATH}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, sort_keys=True)
        os.replace(temp_path, _CACHE_PATH)
    except Exception:
        return


def _get_cached_result(key: str, now: datetime) -> Optional[Dict[str, Any]]:
    now_ts = now.timestamp()
    cached = _MEMORY_CACHE.get(key)
    if cached and cached.get("expires_at_ts", 0) > now_ts:
        return dict(cached["payload"])

    with _CACHE_LOCK:
        file_cache = _load_file_cache_locked()
        cached = file_cache.get(key)
        if not cached:
            return None
        if float(cached.get("expires_at_ts", 0)) <= now_ts:
            file_cache.pop(key, None)
            _write_file_cache_locked(file_cache)
            return None
        payload = dict(cached.get("payload") or {})
        _MEMORY_CACHE[key] = {"expires_at_ts": float(cached["expires_at_ts"]), "payload": payload}
        return payload


def _set_cached_result(key: str, payload: Dict[str, Any], ttl_seconds: int, now: datetime) -> None:
    expires_at_ts = now.timestamp() + max(int(ttl_seconds), 60)
    entry = {"expires_at_ts": expires_at_ts, "payload": payload}
    _MEMORY_CACHE[key] = entry
    with _CACHE_LOCK:
        file_cache = _load_file_cache_locked()
        file_cache[key] = entry
        _write_file_cache_locked(file_cache)


class RetailCompService:
    def get_retail_comps(
        self,
        year: Optional[int],
        make: str,
        model: str,
        state: Optional[str] = None,
        supabase_client: Any = None,
    ) -> Dict[str, Any]:
        if not year or not make or not model or supabase_client is None:
            return _empty_result()

        now = datetime.now(timezone.utc)
        key = _cache_key(year, make, model, state)
        cached = _get_cached_result(key, now)
        if cached is not None:
            return cached

        result = (
            self._from_market_prices(year=year, make=make, model=model, state=state, supabase_client=supabase_client)
            or self._from_dealer_sales(
                year=year, make=make, model=model, state=state, supabase_client=supabase_client
            )
            or _empty_result()
        )

        ttl_seconds = RETAIL_COMP_CACHE_TTL_SECONDS if result.get("pricing_source") else RETAIL_COMP_NEGATIVE_CACHE_TTL_SECONDS
        _set_cached_result(key, result, ttl_seconds=ttl_seconds, now=now)
        return result

    def _market_price_candidates(
        self,
        year: int,
        make: str,
        model: str,
        state: Optional[str],
        supabase_client: Any,
    ) -> List[Dict[str, Any]]:
        make_candidates = _text_candidates(make)
        model_candidates = _text_candidates(model)
        queries = []

        for make_value in make_candidates:
            for model_value in model_candidates:
                if state:
                    queries.append(
                        supabase_client.table("market_prices")
                        .select("*")
                        .eq("make", make_value)
                        .eq("model", model_value)
                        .eq("year", int(year))
                        .eq("state", state.strip().lower())
                        .order("last_updated", desc=True)
                        .limit(3)
                    )
                queries.append(
                    supabase_client.table("market_prices")
                    .select("*")
                    .eq("make", make_value)
                    .eq("model", model_value)
                    .eq("year", int(year))
                    .order("last_updated", desc=True)
                    .limit(5)
                )

        rows: List[Dict[str, Any]] = []
        seen_ids = set()
        for query in queries:
            try:
                response = query.execute()
            except Exception:
                continue
            for row in response.data or []:
                row_id = row.get("id")
                if row_id in seen_ids:
                    continue
                seen_ids.add(row_id)
                rows.append(row)
        return rows

    def _from_market_prices(
        self,
        year: int,
        make: str,
        model: str,
        state: Optional[str],
        supabase_client: Any,
    ) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        for row in self._market_price_candidates(year, make, model, state, supabase_client):
            expires_at = _parse_dt(row.get("expires_at"))
            if expires_at and expires_at < now:
                continue

            avg_price = _safe_float(row.get("avg_price"))
            low_price = _safe_float(row.get("low_price"))
            high_price = _safe_float(row.get("high_price"))
            if not avg_price or not low_price or not high_price:
                continue

            sample_size = int(row.get("sample_size") or 0)
            exact_state = bool(state) and (row.get("state") or "").strip().lower() == state.strip().lower()
            last_updated = _parse_dt(row.get("last_updated")) or now
            age_hours = max((now - last_updated).total_seconds() / 3600.0, 0.0)

            confidence = 0.45
            confidence += min(sample_size, 8) * 0.04
            confidence += 0.12 if exact_state else 0.04
            if age_hours <= 24:
                confidence += 0.12
            elif age_hours <= 72:
                confidence += 0.08
            elif age_hours <= 24 * 7:
                confidence += 0.04

            result = RetailCompResult(
                retail_comp_price_estimate=avg_price,
                retail_comp_low=low_price,
                retail_comp_high=high_price,
                retail_comp_count=max(sample_size, 1),
                retail_comp_confidence=min(confidence, 0.95),
                pricing_source="retail_market_cache",
                pricing_updated_at=last_updated.isoformat(),
            )
            return result.to_dict()
        return None

    def _dealer_sales_rows(
        self,
        year: int,
        make: str,
        model: str,
        state: Optional[str],
        supabase_client: Any,
    ) -> List[Dict[str, Any]]:
        make_candidates = _text_candidates(make)
        model_candidates = _text_candidates(model)
        queries = []

        for make_value in make_candidates:
            for model_value in model_candidates:
                if state:
                    queries.append(
                        supabase_client.table("dealer_sales")
                        .select("sale_price,sale_date,year,state")
                        .eq("make", make_value)
                        .eq("model", model_value)
                        .eq("state", state.strip().upper())
                        .gte("year", int(year) - 1)
                        .lte("year", int(year) + 1)
                        .order("sale_date", desc=True)
                        .limit(18)
                    )
                queries.append(
                    supabase_client.table("dealer_sales")
                    .select("sale_price,sale_date,year,state")
                    .eq("make", make_value)
                    .eq("model", model_value)
                    .gte("year", int(year) - 1)
                    .lte("year", int(year) + 1)
                    .order("sale_date", desc=True)
                    .limit(30)
                )

        rows: List[Dict[str, Any]] = []
        seen_rows = set()
        for query in queries:
            try:
                response = query.execute()
            except Exception:
                continue
            for row in response.data or []:
                key = (
                    row.get("sale_date"),
                    row.get("sale_price"),
                    row.get("year"),
                    row.get("state"),
                )
                if key in seen_rows:
                    continue
                seen_rows.add(key)
                rows.append(row)
        return rows

    def _from_dealer_sales(
        self,
        year: int,
        make: str,
        model: str,
        state: Optional[str],
        supabase_client: Any,
    ) -> Optional[Dict[str, Any]]:
        rows = self._dealer_sales_rows(year, make, model, state, supabase_client)
        if not rows:
            return None

        now = datetime.now(timezone.utc)
        weighted_prices: List[float] = []
        raw_prices: List[float] = []
        latest_sale: Optional[datetime] = None
        exact_state_hits = 0
        exact_year_hits = 0

        for row in rows:
            sale_price = _safe_float(row.get("sale_price"))
            sale_year = int(row.get("year") or 0)
            sale_dt = _parse_dt(row.get("sale_date"))
            if not sale_price or sale_price <= 0:
                continue

            year_gap = abs(sale_year - int(year))
            if year_gap > 1:
                continue

            if sale_dt and sale_dt < now - timedelta(days=365):
                continue

            weight = 1.0 if year_gap == 0 else 0.8
            if year_gap == 0:
                exact_year_hits += 1

            sale_state = (row.get("state") or "").strip().upper()
            if state and sale_state == state.strip().upper():
                weight += 0.2
                exact_state_hits += 1

            raw_prices.append(sale_price)
            weighted_prices.extend([sale_price] * max(int(round(weight * 5)), 1))
            if sale_dt and (latest_sale is None or sale_dt > latest_sale):
                latest_sale = sale_dt

        if not raw_prices:
            return None

        comp_count = len(raw_prices)
        estimate = float(median(weighted_prices))
        low_price = _percentile(raw_prices, 0.2)
        high_price = _percentile(raw_prices, 0.8)
        latest_sale = latest_sale or now
        age_days = max((now - latest_sale).days, 0)

        confidence = 0.35
        confidence += min(comp_count, 8) * 0.05
        confidence += min(exact_year_hits, 4) * 0.03
        confidence += 0.10 if exact_state_hits else 0.02
        if age_days <= 30:
            confidence += 0.12
        elif age_days <= 90:
            confidence += 0.08
        elif age_days <= 180:
            confidence += 0.04

        result = RetailCompResult(
            retail_comp_price_estimate=estimate,
            retail_comp_low=low_price,
            retail_comp_high=high_price,
            retail_comp_count=comp_count,
            retail_comp_confidence=min(confidence, 0.92),
            pricing_source="dealer_sales_history",
            pricing_updated_at=latest_sale.isoformat(),
        )
        return result.to_dict()


_SERVICE = RetailCompService()


def get_retail_comps(
    year: Optional[int],
    make: str,
    model: str,
    state: Optional[str] = None,
    supabase_client: Any = None,
) -> Dict[str, Any]:
    """Return retail comp metadata if available, otherwise a fallback-safe empty result."""
    try:
        return _SERVICE.get_retail_comps(
            year=year,
            make=make,
            model=model,
            state=state,
            supabase_client=supabase_client,
        )
    except Exception:
        return _empty_result()
