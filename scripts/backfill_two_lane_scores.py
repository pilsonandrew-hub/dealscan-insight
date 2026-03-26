#!/usr/bin/env python3
"""Backfill two-lane DOS scores for existing opportunities in Supabase."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from supabase import create_client

from backend.ingest.score import score_deal

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PAGE_SIZE = 200
BATCH_SIZE = 50


def _require_env(name: str, value: str | None) -> str:
    if value:
        return value
    print(f"Error: {name} environment variable is required.", file=sys.stderr, flush=True)
    raise SystemExit(1)


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _effective_mmr(row: dict[str, Any]) -> float | None:
    mmr = _coerce_float(row.get("mmr"))
    if mmr is not None:
        return mmr
    return _coerce_float(row.get("manheim_mmr_mid"))


def _fetch_page(client, after_id: str | None) -> list[dict[str, Any]]:
    query = (
        client.table("opportunities")
        .select("id,year,make,model,mileage,state,source_site,current_bid,mmr,manheim_mmr_mid,vehicle_tier,dos_premium")
        .or_("vehicle_tier.is.null,vehicle_tier.eq.unassigned,dos_premium.is.null")
        .order("id", desc=False)
        .limit(PAGE_SIZE)
    )
    if after_id:
        query = query.gt("id", after_id)
    response = query.execute()
    return response.data or []


def _score_row(row: dict[str, Any]) -> dict[str, Any]:
    result = score_deal(
        bid=_coerce_float(row.get("current_bid")) or 0.0,
        mmr_ca=_effective_mmr(row),
        state=str(row.get("state") or ""),
        source_site=str(row.get("source_site") or ""),
        model=str(row.get("model") or ""),
        make=str(row.get("make") or ""),
        year=_coerce_int(row.get("year")),
        mileage=_coerce_float(row.get("mileage")),
        manheim_mmr_mid=_coerce_float(row.get("manheim_mmr_mid")),
    )
    return {
        "id": row.get("id"),
        "designated_lane": result.get("designated_lane"),
        "vehicle_tier": result.get("vehicle_tier"),
        "dos_premium": result.get("dos_premium"),
        "dos_standard": result.get("dos_standard"),
        "bid_ceiling_pct": result.get("bid_ceiling_pct"),
        "min_margin_target": result.get("min_margin_target"),
        "gross_margin": result.get("gross_margin"),
        "investment_grade": result.get("investment_grade"),
    }


def _flush_batch(client, batch: list[dict[str, Any]]) -> tuple[int, int]:
    if not batch:
        return 0, 0

    updated = 0
    errors = 0
    for row in batch:
        row_id = row.get("id")
        try:
            payload = {k: v for k, v in row.items() if k != "id"}
            client.table("opportunities").update(payload).eq("id", row_id).execute()
            updated += 1
        except Exception as exc:
            errors += 1
            print(f"[error] Failed to update id={row_id}: {exc}", flush=True)
    return updated, errors


def main() -> int:
    supabase_url = _require_env("SUPABASE_URL", SUPABASE_URL)
    service_role_key = _require_env("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY)

    client = create_client(supabase_url, service_role_key)

    total_processed = 0
    total_updated = 0
    total_skipped = 0
    total_errors = 0
    last_id: str | None = None
    pending_updates: list[dict[str, Any]] = []

    print("Starting two-lane score backfill...", flush=True)

    while True:
        rows = _fetch_page(client, last_id)
        if not rows:
            break

        for row in rows:
            total_processed += 1
            row_id = row.get("id")
            last_id = str(row_id)

            if row_id is None:
                total_skipped += 1
                print("[warn] Skipping row without id", flush=True)
                continue

            try:
                pending_updates.append(_score_row(row))
            except Exception as exc:
                total_errors += 1
                print(f"[error] Failed to score id={row_id}: {exc}", flush=True)
                continue

            if len(pending_updates) >= BATCH_SIZE:
                updated, errors = _flush_batch(client, pending_updates)
                total_updated += updated
                total_errors += errors
                pending_updates.clear()

            if total_processed % 100 == 0:
                print(
                    f"[progress] processed={total_processed} "
                    f"updated={total_updated} skipped={total_skipped} errors={total_errors}"
                    ,
                    flush=True,
                )
    if pending_updates:
        updated, errors = _flush_batch(client, pending_updates)
        total_updated += updated
        total_errors += errors

    print(
        "Backfill complete. "
        f"total_processed={total_processed} "
        f"updated={total_updated} "
        f"skipped={total_skipped} "
        f"errors={total_errors}"
        ,
        flush=True,
    )
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
