"""Optional Tavily search enrichment for DealerScope ingest.

Tavily is a corroboration/search lane, not an auction page extraction lane.
It must never block ingest, gate acceptance by itself, or become required for
scoring. Use it only when source fields are missing or suspicious and keep the
returned evidence compact/provenance-labelled.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TIMEOUT_SECONDS = 12
MAX_RESULTS = 3
_MAX_QUERY_CHARS = 220


def _api_key() -> str:
    return os.getenv("TAVILY_API_KEY", "").strip()


def is_available() -> bool:
    """Return True when Tavily is explicitly configured."""
    return bool(_api_key())


def should_enrich_vehicle(vehicle: dict[str, Any]) -> bool:
    """Return True only for listings with gaps Tavily can plausibly corroborate."""
    if not vehicle.get("listing_url") and not vehicle.get("title"):
        return False
    missing_or_suspicious = [
        not vehicle.get("vin"),
        not vehicle.get("mileage"),
        not vehicle.get("description"),
        not vehicle.get("photos"),
        str(vehicle.get("condition_grade") or "").lower() in {"", "unknown", "poor"},
    ]
    return any(missing_or_suspicious)


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
