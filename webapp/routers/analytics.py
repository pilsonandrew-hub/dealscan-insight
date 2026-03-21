"""
Analytics summary endpoint.
GET /api/analytics/summary — aggregates KPIs from Supabase.

Uses the opportunities table which now carries outcome_* columns,
and the alert_log table for alert delivery stats.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
import os
import logging
import json
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_ANON_KEY", "")
)

supa = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        supa = create_client(_supabase_url, _supabase_key)
        logger.info("[ANALYTICS] Supabase client initialised")
    else:
        logger.warning("[ANALYTICS] Supabase env vars not set — analytics will return zeros")
except Exception as _e:
    logger.warning(f"[ANALYTICS] Supabase client init failed (non-fatal): {_e}")


def _safe_avg(values: list, field: str) -> Optional[float]:
    """Return average of a numeric field from a list of dicts, ignoring None."""
    nums = [float(r[field]) for r in values if r.get(field) is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


@router.get("/summary")
async def analytics_summary():
    """
    Return high-level KPIs:
      - total_opportunities      (from opportunities table)
      - total_outcomes           (rows where outcome_recorded_at is not null)
      - avg_gross_margin         (avg gross_margin on outcome rows)
      - avg_roi_pct              (avg roi on outcome rows)
      - wins_by_source           (count of sold outcomes grouped by source)
      - top_makes                (top 5 makes by avg dos_score)
      - alerts_sent_last_30d     (count from alert_log where sent_at > now()-30d)
    """
    if supa is None:
        # Return zeroed structure so the UI still renders
        return {
            "total_opportunities": 0,
            "total_outcomes": 0,
            "avg_gross_margin": None,
            "avg_roi_pct": None,
            "wins_by_source": [],
            "top_makes": [],
            "alerts_sent_last_30d": 0,
            "total_bids": 0,
            "total_wins": 0,
            "win_rate": None,
            "avg_purchase_price": None,
            "avg_max_bid": None,
        }

    try:
        # ── 1. Total opportunities ────────────────────────────────────────────
        opp_resp = (
            supa.table("opportunities")
            .select("id", count="exact")
            .execute()
        )
        total_opportunities = opp_resp.count or 0

        # ── 2. Outcomes (rows with outcome_recorded_at set) ───────────────────
        outcomes_resp = (
            supa.table("opportunities")
            .select("id,gross_margin,roi,source,outcome_notes,outcome_sale_price,max_bid", count="exact")
            .not_.is_("outcome_recorded_at", "null")
            .execute()
        )
        outcome_rows = outcomes_resp.data or []
        total_outcomes = outcomes_resp.count or len(outcome_rows)
        avg_gross_margin = _safe_avg(outcome_rows, "gross_margin")
        avg_roi_pct = _safe_avg(outcome_rows, "roi")

        # ── 3. Wins by source + bid outcome stats ─────────────────────────────
        source_map: dict[str, int] = {}
        total_bids = 0
        total_wins = 0
        purchase_prices: list[float] = []
        max_bids_on_bid_rows: list[float] = []

        for row in outcome_rows:
            notes_raw = row.get("outcome_notes") or ""
            bid_data: dict = {}
            try:
                parsed = json.loads(notes_raw)
                if isinstance(parsed, dict) and parsed.get("type") == "bid_outcome":
                    bid_data = parsed
            except (json.JSONDecodeError, TypeError):
                pass

            if bid_data:
                # This is a bid outcome row
                if bid_data.get("bid"):
                    total_bids += 1
                    mb = row.get("max_bid")
                    if mb is not None:
                        max_bids_on_bid_rows.append(float(mb))
                if bid_data.get("won"):
                    total_wins += 1
                    pp = bid_data.get("purchase_price") or row.get("outcome_sale_price")
                    if pp is not None:
                        purchase_prices.append(float(pp))
            else:
                # Legacy sale-outcome row — count toward wins_by_source
                src = row.get("source") or row.get("source_site") or "unknown"
                source_map[src] = source_map.get(src, 0) + 1

        wins_by_source = [
            {"source": k, "count": v}
            for k, v in sorted(source_map.items(), key=lambda x: -x[1])
        ]
        win_rate = round(total_wins / total_bids * 100, 1) if total_bids > 0 else None
        avg_purchase_price = round(sum(purchase_prices) / len(purchase_prices), 2) if purchase_prices else None
        avg_max_bid = round(sum(max_bids_on_bid_rows) / len(max_bids_on_bid_rows), 2) if max_bids_on_bid_rows else None

        # ── 4. Top makes by avg DOS score ─────────────────────────────────────
        makes_resp = (
            supa.table("opportunities")
            .select("make,dos_score")
            .not_.is_("make", "null")
            .not_.is_("dos_score", "null")
            .execute()
        )
        make_scores: dict[str, list[float]] = {}
        for row in (makes_resp.data or []):
            m = (row.get("make") or "").strip()
            s = row.get("dos_score")
            if m and s is not None:
                make_scores.setdefault(m, []).append(float(s))
        top_makes = [
            {"make": m, "avg_dos_score": round(sum(v) / len(v), 1), "count": len(v)}
            for m, v in make_scores.items()
        ]
        top_makes.sort(key=lambda x: -x["avg_dos_score"])
        top_makes = top_makes[:5]

        # ── 5. Alerts sent in last 30 days ────────────────────────────────────
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        alerts_resp = (
            supa.table("alert_log")
            .select("id", count="exact")
            .gte("sent_at", cutoff)
            .execute()
        )
        alerts_sent_last_30d = alerts_resp.count or 0

        return {
            "total_opportunities": total_opportunities,
            "total_outcomes": total_outcomes,
            "avg_gross_margin": avg_gross_margin,
            "avg_roi_pct": avg_roi_pct,
            "wins_by_source": wins_by_source,
            "top_makes": top_makes,
            "alerts_sent_last_30d": alerts_sent_last_30d,
            "total_bids": total_bids,
            "total_wins": total_wins,
            "win_rate": win_rate,
            "avg_purchase_price": avg_purchase_price,
            "avg_max_bid": avg_max_bid,
        }

    except Exception as exc:
        logger.error(f"[ANALYTICS] summary error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Analytics query failed")
