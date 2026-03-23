"""
Analytics summary endpoint.
GET /api/analytics/summary — aggregates KPIs from Supabase.

Uses the opportunities table which now carries outcome_* columns,
and the alert_log table for alert delivery stats.
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional

from webapp.routers.outcomes import _verify_auth
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
async def analytics_summary(authorization: Optional[str] = Header(None)):
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
    user_id = _verify_auth(authorization)
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


@router.get("/dos-calibration")
async def dos_calibration(authorization: Optional[str] = Header(None)):
    """
    Return DOS scoring calibration status:
      - Current weight breakdown
      - Data availability (recon count, dealer_sales count)
      - Which components are estimated vs data-driven
      - Recommendations for calibration when real data arrives
    """
    user_id = _verify_auth(authorization)
    # Base DOS formula weights
    base_weights = {
        "margin": 0.35,
        "velocity": 0.25,
        "segment": 0.20,
        "model": 0.12,
        "source": 0.08,  # baseline, now dynamic
    }

    # Dynamic source weights by tier
    source_weight_tiers = {
        "proven_gov": {"weight": 0.10, "sources": ["govplanet", "govdeals", "municibid", "publicsurplus", "gsaauctions", "usgovbid", "jjkane"]},
        "mid_tier": {"weight": 0.08, "sources": ["ritchiebros", "ironplanet"]},
        "less_reliable": {"weight": 0.06, "sources": ["proxibid", "bidspotter"]},
        "lowest_confidence": {"weight": 0.04, "sources": ["hibid", "allsurplus"]},
        "salvage": {"weight": 0.03, "sources": ["iaa", "copart"]},
    }

    # Component estimation status
    component_status = {
        "margin": {
            "data_driven": False,
            "source": "Marketcheck retail comps or proxy multiplier",
            "confidence": "medium",
            "notes": "Uses retail comp prices when available, otherwise proxy estimate from MMR",
        },
        "velocity": {
            "data_driven": False,
            "source": "Hardcoded heuristics based on price/age/mileage",
            "confidence": "low",
            "notes": "No actual days-to-sale data — uses segment tier estimates (25-70 days)",
        },
        "segment": {
            "data_driven": True,
            "source": "Static model→segment mapping",
            "confidence": "high",
            "notes": "Segment demand patterns are stable; scoring is appropriate",
        },
        "model": {
            "data_driven": True,
            "source": "TIER_1/TIER_2 model lists",
            "confidence": "high",
            "notes": "Model desirability is well-understood",
        },
        "source": {
            "data_driven": True,
            "source": "Dynamic weight by source tier (0.03-0.10)",
            "confidence": "high",
            "notes": "Source reliability is known from government fleet patterns",
        },
    }

    # Query data availability
    recon_count = 0
    dealer_sales_count = 0
    outcomes_with_bids = 0

    if supa is not None:
        try:
            # Count recon evaluations (opportunities with dos_score)
            recon_resp = supa.table("opportunities").select("id", count="exact").not_.is_("dos_score", "null").execute()
            recon_count = recon_resp.count or 0

            # Count dealer_sales comps
            ds_resp = supa.table("dealer_sales").select("id", count="exact").execute()
            dealer_sales_count = ds_resp.count or 0

            # Count bid outcomes
            outcomes_resp = supa.table("opportunities").select("outcome_notes", count="exact").not_.is_("outcome_recorded_at", "null").execute()
            for row in (outcomes_resp.data or []):
                notes = row.get("outcome_notes") or ""
                if '"type": "bid_outcome"' in notes or '"bid":' in notes:
                    outcomes_with_bids += 1
        except Exception as e:
            logger.warning(f"[DOS-CALIBRATION] Data query failed: {e}")

    # Calibration recommendations
    recommendations = []
    if dealer_sales_count < 50:
        recommendations.append({
            "priority": 1,
            "component": "margin",
            "action": "Collect more dealer_sales comps to improve margin accuracy",
            "threshold": "50+ comps enables data-driven margin scoring",
        })
    if outcomes_with_bids < 10:
        recommendations.append({
            "priority": 2,
            "component": "velocity",
            "action": "Log bid outcomes with actual days-to-sale to calibrate velocity",
            "threshold": "10+ bid outcomes enables real velocity measurement",
        })
    if outcomes_with_bids >= 10:
        recommendations.append({
            "priority": 1,
            "component": "velocity",
            "action": "Replace heuristic velocity with actual days-to-sale from outcomes",
            "threshold": "Ready for calibration — sufficient bid data exists",
        })
    if not recommendations:
        recommendations.append({
            "priority": 0,
            "component": "all",
            "action": "DOS scoring is appropriately calibrated for current data volume",
            "threshold": "n/a",
        })

    return {
        "formula": "DOS = Margin×W1 + Velocity×W2 + Segment×W3 + Model×W4 + Source×W_src",
        "base_weights": base_weights,
        "source_weight_tiers": source_weight_tiers,
        "component_status": component_status,
        "data_availability": {
            "recon_evaluations": recon_count,
            "dealer_sales_comps": dealer_sales_count,
            "bid_outcomes": outcomes_with_bids,
        },
        "recommendations": recommendations,
        "next_calibration_target": "velocity" if outcomes_with_bids < 10 else "margin",
    }
