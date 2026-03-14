"""Backend Manheim market-data abstraction with live and fallback providers."""
from __future__ import annotations

import logging
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _safe_updated_at(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _first_present(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _extract_range_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("market_range", "marketRange", "mmr_range", "mmrRange", "range", "band"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return {}


def _normalize_confidence(value: Any) -> Optional[float]:
    confidence = _safe_float(value)
    if confidence is None:
        return None
    if confidence > 1:
        confidence /= 100.0
    return max(0.0, min(1.0, confidence))


def _compute_range_width_pct(mid: Optional[float], low: Optional[float], high: Optional[float]) -> Optional[float]:
    if mid is None or low is None or high is None or mid <= 0:
        return None
    return max(0.0, ((high - low) / mid) * 100.0)


@dataclass
class ManheimMarketResult:
    manheim_mmr_mid: Optional[float] = None
    manheim_mmr_low: Optional[float] = None
    manheim_mmr_high: Optional[float] = None
    manheim_range_width_pct: Optional[float] = None
    manheim_confidence: Optional[float] = None
    manheim_source_status: str = "unavailable"
    manheim_updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key in (
            "manheim_mmr_mid",
            "manheim_mmr_low",
            "manheim_mmr_high",
            "manheim_range_width_pct",
        ):
            if payload[key] is not None:
                payload[key] = round(float(payload[key]), 2)
        if payload["manheim_confidence"] is not None:
            payload["manheim_confidence"] = round(float(payload["manheim_confidence"]), 3)
        return payload


class BaseManheimProvider:
    def get_market_data(
        self,
        *,
        year: Optional[int],
        make: str,
        model: str,
        trim: Optional[str] = None,
        state: Optional[str] = None,
        mileage: Optional[float] = None,
    ) -> ManheimMarketResult:
        raise NotImplementedError


class ConfiguredHTTPManheimProvider(BaseManheimProvider):
    def __init__(self) -> None:
        self.endpoint = (os.getenv("MANHEIM_MARKET_DATA_URL") or "").strip()
        self.method = (os.getenv("MANHEIM_MARKET_DATA_METHOD") or "GET").strip().upper()
        self.timeout_seconds = _safe_float(os.getenv("MANHEIM_API_TIMEOUT_SECONDS")) or 8.0
        self.api_token = (os.getenv("MANHEIM_API_TOKEN") or "").strip()
        self.username = (os.getenv("MANHEIM_API_USERNAME") or "").strip()
        self.password = (os.getenv("MANHEIM_API_PASSWORD") or "").strip()
        self.api_key = (os.getenv("MANHEIM_API_KEY") or "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint)

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _build_query(self, **kwargs: Any) -> Dict[str, Any]:
        query = {key: value for key, value in kwargs.items() if value not in (None, "", [])}
        if "state" in query and isinstance(query["state"], str):
            query["state"] = query["state"].strip().upper()
        return query

    def _normalize_live_payload(self, payload: Dict[str, Any]) -> ManheimMarketResult:
        candidate = payload
        for key in ("result", "data", "marketData", "market_data", "vehicle", "mmr"):
            nested = candidate.get(key)
            if isinstance(nested, dict):
                candidate = nested
                break
        if isinstance(candidate.get("results"), list) and candidate["results"]:
            first = candidate["results"][0]
            if isinstance(first, dict):
                candidate = first

        range_payload = _extract_range_payload(candidate)

        mid = _safe_float(
            _first_present(
                candidate,
                "manheim_mmr_mid",
                "mmr_mid",
                "market_value",
                "marketValue",
                "mmr",
                "mid",
                "average",
                "avg",
            )
        )
        low = _safe_float(_first_present(candidate, "manheim_mmr_low", "mmr_low", "low"))
        high = _safe_float(_first_present(candidate, "manheim_mmr_high", "mmr_high", "high"))

        if low is None:
            low = _safe_float(_first_present(range_payload, "low", "min"))
        if high is None:
            high = _safe_float(_first_present(range_payload, "high", "max"))
        if mid is None:
            mid = _safe_float(_first_present(range_payload, "average", "avg", "mid", "mmr"))
        if mid is None and low is not None and high is not None:
            mid = (low + high) / 2.0

        range_width_pct = _safe_float(
            _first_present(candidate, "manheim_range_width_pct", "range_width_pct", "rangeWidthPct")
        )
        if range_width_pct is None:
            range_width_pct = _safe_float(_first_present(range_payload, "width_pct", "widthPct"))
        if range_width_pct is None:
            range_width_pct = _compute_range_width_pct(mid, low, high)

        confidence = _normalize_confidence(
            _first_present(candidate, "manheim_confidence", "confidence", "confidence_score", "confidenceScore")
        )
        updated_at = _safe_updated_at(
            _first_present(candidate, "manheim_updated_at", "updated_at", "updatedAt", "last_updated", "lastUpdated")
        )

        if mid is None or mid <= 0:
            return ManheimMarketResult()

        return ManheimMarketResult(
            manheim_mmr_mid=mid,
            manheim_mmr_low=low,
            manheim_mmr_high=high,
            manheim_range_width_pct=range_width_pct,
            manheim_confidence=confidence,
            manheim_source_status="live",
            manheim_updated_at=updated_at,
        )

    def get_market_data(
        self,
        *,
        year: Optional[int],
        make: str,
        model: str,
        trim: Optional[str] = None,
        state: Optional[str] = None,
        mileage: Optional[float] = None,
    ) -> ManheimMarketResult:
        if not self.is_configured or not year or not make or not model:
            return ManheimMarketResult()

        try:
            import httpx

            query = self._build_query(
                year=int(year),
                make=make,
                model=model,
                trim=trim,
                state=state,
                mileage=mileage,
            )
            auth = (self.username, self.password) if self.username and self.password else None
            with httpx.Client(timeout=self.timeout_seconds, headers=self._build_headers(), auth=auth) as client:
                if self.method == "POST":
                    response = client.post(self.endpoint, json=query)
                else:
                    response = client.get(self.endpoint, params=query)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning(
                "[MANHEIM] live provider request failed for %s %s %s: %s",
                year,
                make,
                model,
                exc,
            )
            return ManheimMarketResult()

        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            return ManheimMarketResult()
        return self._normalize_live_payload(payload)


class ProxyFallbackManheimProvider(BaseManheimProvider):
    def __init__(self, proxy_mmr: Optional[float], proxy_basis: Optional[str], proxy_confidence: Optional[float]) -> None:
        self.proxy_mmr = _safe_float(proxy_mmr)
        self.proxy_basis = (proxy_basis or "").strip().lower()
        self.proxy_confidence = _safe_float(proxy_confidence)

    def _estimated_width_pct(self) -> float:
        confidence = self.proxy_confidence if self.proxy_confidence is not None else 45.0
        if self.proxy_basis.startswith("model:"):
            base_width = 10.0
        elif self.proxy_basis.startswith("make:"):
            base_width = 14.0
        elif self.proxy_basis.startswith("special:police_interceptor"):
            base_width = 17.0
        elif self.proxy_basis.startswith("special:commercial_vehicle"):
            base_width = 22.0
        elif self.proxy_basis.startswith("segment:"):
            base_width = 20.0
        else:
            base_width = 18.0

        if confidence >= 85:
            adjustment = -1.0
        elif confidence >= 70:
            adjustment = 0.0
        elif confidence >= 55:
            adjustment = 2.0
        else:
            adjustment = 4.0

        return max(8.0, min(26.0, base_width + adjustment))

    def get_market_data(
        self,
        *,
        year: Optional[int],
        make: str,
        model: str,
        trim: Optional[str] = None,
        state: Optional[str] = None,
        mileage: Optional[float] = None,
    ) -> ManheimMarketResult:
        del year, make, model, trim, state, mileage
        if self.proxy_mmr is None or self.proxy_mmr <= 0:
            return ManheimMarketResult()

        width_pct = self._estimated_width_pct()
        half_spread_ratio = width_pct / 200.0
        low = self.proxy_mmr * (1.0 - half_spread_ratio)
        high = self.proxy_mmr * (1.0 + half_spread_ratio)
        confidence = None
        if self.proxy_confidence is not None:
            confidence = max(0.0, min(1.0, self.proxy_confidence / 100.0))

        return ManheimMarketResult(
            manheim_mmr_mid=self.proxy_mmr,
            manheim_mmr_low=low,
            manheim_mmr_high=high,
            manheim_range_width_pct=width_pct,
            manheim_confidence=confidence,
            manheim_source_status="fallback",
            manheim_updated_at=None,
        )


def get_manheim_provider_strategy() -> str:
    return "configured_http_live_then_proxy_fallback" if os.getenv("MANHEIM_MARKET_DATA_URL") else "proxy_fallback_only"


def get_manheim_market_data(
    *,
    year: Optional[int],
    make: str,
    model: str,
    trim: Optional[str] = None,
    state: Optional[str] = None,
    mileage: Optional[float] = None,
    proxy_mmr: Optional[float] = None,
    proxy_basis: Optional[str] = None,
    proxy_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    live_provider = ConfiguredHTTPManheimProvider()
    if live_provider.is_configured:
        live_result = live_provider.get_market_data(
            year=year,
            make=make,
            model=model,
            trim=trim,
            state=state,
            mileage=mileage,
        )
        if live_result.manheim_source_status == "live" and live_result.manheim_mmr_mid:
            return live_result.to_dict()

    fallback_result = ProxyFallbackManheimProvider(
        proxy_mmr=proxy_mmr,
        proxy_basis=proxy_basis,
        proxy_confidence=proxy_confidence,
    ).get_market_data(
        year=year,
        make=make,
        model=model,
        trim=trim,
        state=state,
        mileage=mileage,
    )
    return fallback_result.to_dict()
