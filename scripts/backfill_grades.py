#!/usr/bin/env python3
"""Backfill NULL opportunity grades via the Supabase REST API."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.ingest.score import score_deal

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lbnxzvqppccajllsqaaw.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxibnh6dnFwcGNjYWpsbHNxYWF3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzIwMTQ3MSwiZXhwIjoyMDg4Nzc3NDcxfQ.gLFMWuEVDbwMMHYL1CPRwNv1oGukhBTFYZGYTuXftSg",
)
PAGE_SIZE = 200
TIMEOUT_SECONDS = 30

SOURCE_MAP = {
    "govdeals": "GovDeals",
    "publicsurplus": "PublicSurplus",
    "gsaauctions": "GSAAuctions",
    "municibid": "Municibid",
    "govplanet": "GovPlanet",
}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _source_site(row: dict[str, Any]) -> str:
    raw_data = row.get("raw_data") or {}
    raw_source = row.get("source") or raw_data.get("source_site") or raw_data.get("source") or "GovDeals"
    return SOURCE_MAP.get(str(raw_source).lower(), raw_source)


def _current_bid(row: dict[str, Any]) -> float:
    raw_data = row.get("raw_data") or {}
    return _coerce_float(
        row.get("current_bid")
        or raw_data.get("current_bid")
        or raw_data.get("currentBid")
        or raw_data.get("buy_now_price")
        or raw_data.get("price")
        or raw_data.get("estimated_sale_price"),
        0.0,
    )


def _mmr_value(row: dict[str, Any]) -> float:
    raw_data = row.get("raw_data") or {}
    score_breakdown = raw_data.get("score_breakdown") or {}
    return _coerce_float(
        row.get("mmr")
        or score_breakdown.get("mmr_estimated")
        or raw_data.get("mmr")
        or raw_data.get("estimated_sale_price"),
        0.0,
    )


def _is_police_or_fleet(row: dict[str, Any]) -> bool:
    raw_data = row.get("raw_data") or {}
    haystack = " ".join(
        str(value or "").lower()
        for value in (
            row.get("title"),
            row.get("model"),
            raw_data.get("agency_name"),
        )
    )
    return any(term in haystack for term in ("police", "interceptor", "ppv", "pursuit", "fleet"))


def _recalculate(row: dict[str, Any]) -> dict[str, Any]:
    raw_data = row.get("raw_data") or {}
    result = score_deal(
        bid=_current_bid(row),
        mmr_ca=_mmr_value(row),
        state=row.get("state") or raw_data.get("state") or "",
        source_site=_source_site(row),
        model=row.get("model") or raw_data.get("model") or "",
        make=row.get("make") or raw_data.get("make") or "",
        year=_coerce_int(row.get("year") or raw_data.get("year")),
        mileage=_coerce_float(row.get("mileage") or raw_data.get("mileage")),
        is_police_or_fleet=_is_police_or_fleet(row),
    )
    return {
        "ctm_pct": result["ctm_pct"],
        "segment_tier": result["segment_tier"],
        "investment_grade": result["investment_grade"],
    }


def _request(method: str, path: str, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
    query = urllib.parse.urlencode(params or {})
    url = f"{SUPABASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=body,
        method=method,
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content = response.read().decode("utf-8").strip()
        if not content:
            return None
        return json.loads(content)


def _fetch_batch() -> list[dict[str, Any]]:
    rows = _request(
        "GET",
        "/rest/v1/opportunities",
        params={
            "select": "id,make,model,year,mileage,state,source,title,current_bid,mmr,raw_data",
            "investment_grade": "is.null",
            "order": "id.asc",
            "limit": PAGE_SIZE,
        },
    )
    return rows or []


def _patch_row(row_id: Any, payload: dict[str, Any]) -> None:
    _request(
        "PATCH",
        "/rest/v1/opportunities",
        params={"id": f"eq.{row_id}"},
        payload=payload,
    )


def main() -> int:
    updated = 0
    failed = 0
    failed_ids: set[str] = set()

    print("Starting investment grade backfill...")

    try:
        while True:
            rows = _fetch_batch()
            if not rows:
                break

            pending_rows = [row for row in rows if str(row.get("id")) not in failed_ids]
            if not pending_rows:
                print("Stopping because only previously failed rows remain.")
                break

            print(f"Fetched {len(rows)} rows with NULL investment_grade.")
            for row in pending_rows:
                row_id = row.get("id")
                try:
                    payload = _recalculate(row)
                    _patch_row(row_id, payload)
                    updated += 1
                    print(
                        f"[{updated}] Updated id={row_id} "
                        f"ctm_pct={payload['ctm_pct']} "
                        f"segment_tier={payload['segment_tier']} "
                        f"investment_grade={payload['investment_grade']}"
                    )
                except Exception as exc:
                    failed += 1
                    failed_ids.add(str(row_id))
                    print(f"[error] Failed id={row_id}: {exc}")
    except urllib.error.URLError as exc:
        print(f"Backfill failed: unable to reach Supabase REST API ({exc}).")
        return 1

    print(f"Backfill complete. updated={updated} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
