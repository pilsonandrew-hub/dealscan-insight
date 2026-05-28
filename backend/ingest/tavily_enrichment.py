"""Optional Tavily search enrichment for DealerScope ingest.

Tavily is a corroboration/search lane, not an auction page extraction lane.
It must never block ingest, gate acceptance by itself, or become required for
scoring. Tavily has a small monthly free-credit pool, so use it sparingly:
only for high-value rows that are already near alert/save territory and still
have important truth gaps after source/detail extraction.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TIMEOUT_SECONDS = 8
MAX_RESULTS = 2
_MAX_QUERY_CHARS = 220
_DEFAULT_MIN_SCORE = 80.0


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _min_score() -> float:
    raw = os.getenv("TAVILY_MIN_DOS_SCORE", str(_DEFAULT_MIN_SCORE)).strip()
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_MIN_SCORE


def _api_key() -> str:
    return os.getenv("TAVILY_API_KEY", "").strip()


def is_available() -> bool:
    """Return True when Tavily is explicitly configured."""
    return bool(_api_key())


def _score_value(vehicle: dict[str, Any]) -> Optional[float]:
    raw_score = vehicle.get("dos_score") or vehicle.get("score")
    if raw_score is None and isinstance(vehicle.get("score_breakdown"), dict):
        raw_score = vehicle["score_breakdown"].get("dos_score")
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return None


def should_enrich_vehicle(vehicle: dict[str, Any]) -> bool:
    """Return True only for scarce, high-value Tavily escalation cases."""
    if not _env_bool("TAVILY_ENRICHMENT_ENABLED", default=False):
        return False
    if not vehicle.get("listing_url") and not vehicle.get("title"):
        return False

    score = _score_value(vehicle)
    if score is None or score < _min_score():
        return False

    lacks_primary_identity = not vehicle.get("vin") and not vehicle.get("mileage")
    has_critical_condition_gap = str(vehicle.get("condition_grade") or "").lower() in {"", "unknown", "poor"}
    has_no_source_detail = not vehicle.get("description") and not vehicle.get("photos")
    return lacks_primary_identity or (has_critical_condition_gap and has_no_source_detail)


def build_vehicle_query(vehicle: dict[str, Any]) -> str:
    """Build a compact, non-secret public-web query for vehicle corroboration."""
    source = vehicle.get("source_site") or vehicle.get("source")
    tail_pieces = [vehicle.get("state"), source]
    head_pieces = [
        vehicle.get("vin"),
        vehicle.get("year"),
        vehicle.get("make"),
        vehicle.get("model"),
        vehicle.get("title"),
    ]
    tail = " ".join(str(piece).strip() for piece in tail_pieces if str(piece or "").strip())
    head = " ".join(str(piece).strip() for piece in head_pieces if str(piece or "").strip())
    query = " ".join(" ".join([head, tail]).split())
    if len(query) <= _MAX_QUERY_CHARS:
        return query
    if tail:
        head_limit = max(0, _MAX_QUERY_CHARS - len(tail) - 1)
        return f"{head[:head_limit].rstrip()} {tail}".strip()
    return query[:_MAX_QUERY_CHARS]


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    content = str(result.get("content") or result.get("snippet") or "")
    return {
        "title": str(result.get("title") or "")[:180],
        "url": str(result.get("url") or "")[:500],
        "content": content[:500],
        "score": result.get("score"),
    }


def search_vehicle_context(vehicle: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Search public web context for a vehicle without mutating the vehicle.

    Returns a compact provenance object or None. All errors are swallowed and
    logged because Tavily is optional/non-blocking.
    """
    key = _api_key()
    if not key:
        logger.info("[TAVILY] API key not configured — skipping enrichment")
        return None
    if not should_enrich_vehicle(vehicle):
        return None
    query = build_vehicle_query(vehicle)
    if not query:
        return None

    try:
        response = httpx.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": key,
                "query": query,
                "search_depth": "basic",
                "max_results": MAX_RESULTS,
                "include_raw_content": False,
                "topic": "general",
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results")
        if not isinstance(results, list) or not results:
            return None
        compact_results = [
            _compact_result(result)
            for result in results
            if isinstance(result, dict) and (result.get("url") or result.get("content") or result.get("title"))
        ][:MAX_RESULTS]
        if not compact_results:
            return None
        return {
            "source": "tavily",
            "query": query,
            "results": compact_results,
            "result_count": len(compact_results),
        }
    except httpx.TimeoutException:
        logger.warning("[TAVILY] Timeout enriching listing_url=%s", vehicle.get("listing_url"))
    except httpx.HTTPStatusError as exc:
        logger.warning("[TAVILY] HTTP %s enriching listing_url=%s", exc.response.status_code, vehicle.get("listing_url"))
    except Exception as exc:
        logger.warning("[TAVILY] Unexpected enrichment error for listing_url=%s: %s", vehicle.get("listing_url"), exc)
    return None


def apply_tavily_enrichment(vehicle: dict[str, Any]) -> dict[str, Any]:
    """Attach optional Tavily corroboration evidence to a copy of vehicle."""
    enriched = dict(vehicle)
    context = search_vehicle_context(enriched)
    if not context:
        return enriched
    evidence = list(enriched.get("external_enrichment") or [])
    evidence.append(context)
    enriched["external_enrichment"] = evidence
    enriched["tavily_enriched"] = True
    return enriched
