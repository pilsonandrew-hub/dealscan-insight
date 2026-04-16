import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

try:
    from fastapi import APIRouter, Header, HTTPException
    from pydantic import BaseModel
except ModuleNotFoundError:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @staticmethod
        def _decorator(*_args, **_kwargs):
            def wrapper(func):
                return func
            return wrapper

        get = post = patch = delete = put = _decorator

    def Header(default=None):
        return default

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

from webapp.database import supabase_client

router = APIRouter(prefix="/outcomes", tags=["outcomes"])
logger = logging.getLogger(__name__)


class OutcomePayload(BaseModel):
    opportunity_id: str
    sale_price: float
    sale_date: str
    days_to_sale: int
    notes: Optional[str] = None


class BidOutcomePayload(BaseModel):
    opportunity_id: str
    bid: bool
    won: bool = False
    purchase_price: Optional[float] = None
    notes: Optional[str] = None


class BidOutcomeNormalized(BaseModel):
    bid: bool
    outcome: Literal["won", "lost", "passed", "pending"]
    purchase_price: Optional[float] = None
    bid_amount: Optional[float] = None


class OutcomePatchPayload(BaseModel):
    outcome: Literal["won", "lost", "passed"]
    sold_price: Optional[float] = None


def _verify_auth(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    if not supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    token = authorization.split(" ", 1)[1]
    try:
        user = supabase_client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _safe_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_bid_outcome(payload: BidOutcomePayload, opportunity: dict) -> BidOutcomeNormalized:
    if payload.won and not payload.bid:
        raise HTTPException(status_code=400, detail="Cannot mark won=true when bid=false")
    if payload.purchase_price is not None and not payload.won:
        raise HTTPException(status_code=400, detail="purchase_price is only valid when won=true")

    if not payload.bid:
        return BidOutcomeNormalized(
            bid=False,
            outcome="passed",
            purchase_price=None,
            bid_amount=None,
        )

    bid_amount = _safe_float(opportunity.get("current_bid"))
    return BidOutcomeNormalized(
        bid=True,
        outcome="won" if payload.won else "lost",
        purchase_price=payload.purchase_price if payload.won else None,
        bid_amount=bid_amount,
    )


def _fetch_opportunity(opportunity_id: str, require_user_id: Optional[str] = None) -> dict:
    if not supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    resp = (
        supabase_client.table("opportunities")
        .select("id,user_id,make,model,year,mileage,current_bid,state")
        .eq("id", opportunity_id)
        .limit(1)
        .execute()
    )
    opportunities = resp.data or []
    if not opportunities:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opp = opportunities[0]
    if require_user_id and opp.get("user_id") != require_user_id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this opportunity")
    return opp


def _legacy_mirror_to_dealer_sales(user_id: str, opportunity: dict, payload: OutcomePayload) -> bool:
    asking_price = _safe_float(opportunity.get("current_bid"))
    gross_margin = None
    roi_pct = None
    if asking_price and asking_price > 0:
        gross_margin = round(payload.sale_price - asking_price, 2)
        roi_pct = round((gross_margin / asking_price) * 100, 4)

    insert_payload = {
        "user_id": user_id,
        "opportunity_id": payload.opportunity_id,
        "make": opportunity.get("make") or "Unknown",
        "model": opportunity.get("model") or "Unknown",
        "year": opportunity.get("year") or 0,
        "mileage": opportunity.get("mileage"),
        "sale_price": payload.sale_price,
        "sold_price": payload.sale_price,
        "outcome": "won",
        "gross_margin": gross_margin,
        "roi_pct": roi_pct,
        "state": opportunity.get("state"),
        "sale_date": payload.sale_date,
        "days_to_sale": payload.days_to_sale,
        "metadata": {"notes": payload.notes or ""},
        "source": "outcome_tracking",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        supabase_client.table("dealer_sales").upsert(insert_payload, on_conflict="opportunity_id,user_id").execute()
        return True
    except Exception as exc:
        logger.warning("[OUTCOMES] dealer_sales mirror skipped for opportunity %s: %s", payload.opportunity_id, exc)
        return False


@router.patch("/{opportunity_id}")
async def patch_outcome(
    opportunity_id: str,
    payload: OutcomePatchPayload,
    authorization: Optional[str] = Header(None),
):
    if not supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    user_id = _verify_auth(authorization)
    opportunity = _fetch_opportunity(opportunity_id, require_user_id=user_id)
    current_bid = _safe_float(opportunity.get("current_bid")) or 0.0

    sold_price = _safe_float(payload.sold_price)
    gross_margin = None
    roi_pct = None

    if payload.outcome == "won":
        if sold_price is None:
            raise HTTPException(status_code=400, detail="sold_price is required when outcome is won")
        if current_bid <= 0:
            raise HTTPException(status_code=400, detail="current_bid is required to calculate outcome metrics")
        gross_margin = round(sold_price - current_bid, 2)
        roi_pct = round((gross_margin / current_bid) * 100, 4)
    else:
        sold_price = None

    outcome_map = {"won": "won", "lost": "lost", "passed": "passed"}
    mapped_outcome = outcome_map[payload.outcome]

    timestamp = datetime.now(timezone.utc).isoformat()
    upsert_payload = {
        "opportunity_id": opportunity_id,
        "user_id": user_id,
        "make": opportunity.get("make"),
        "model": opportunity.get("model"),
        "year": opportunity.get("year"),
        "mileage": opportunity.get("mileage"),
        "sale_price": sold_price if sold_price is not None else current_bid,
        "sold_price": sold_price,
        "outcome": mapped_outcome,
        "gross_margin": gross_margin,
        "roi_pct": roi_pct,
        "state": opportunity.get("state"),
        "updated_at": timestamp,
    }

    try:
        supabase_client.table("dealer_sales").upsert(upsert_payload, on_conflict="opportunity_id,user_id").execute()

        opportunity_update = {
            "won": payload.outcome == "won",
            "outcome_sale_price": sold_price,
            "outcome_recorded_at": timestamp,
            "outcome_notes": json.dumps({
                "type": "manual_outcome",
                "outcome": payload.outcome,
                "sold_price": sold_price,
            }),
        }
        supabase_client.table("opportunities").update(opportunity_update).eq("id", opportunity_id).eq("user_id", user_id).execute()

        return {
            "success": True,
            "opportunity_id": opportunity_id,
            "outcome": payload.outcome,
            "sold_price": sold_price,
            "gross_margin": gross_margin,
            "roi_pct": roi_pct,
        }
    except Exception as exc:
        logger.error("[OUTCOMES] patch failed for opportunity %s: %s", opportunity_id, exc)
        raise HTTPException(status_code=500, detail="Failed to record outcome")


@router.get("/summary")
async def get_outcomes_summary(authorization: Optional[str] = Header(None)):
    user_id = _verify_auth(authorization)
    if not supabase_client:
        return {
            "count_by_outcome": {"pending": 0, "won": 0, "lost": 0, "passed": 0},
            "total_gross_margin": 0,
            "avg_roi": None,
        }

    try:
        resp = (
            supabase_client.table("dealer_sales")
            .select("outcome,gross_margin,roi_pct")
            .eq("user_id", user_id)
            .execute()
        )
        rows = resp.data or []
        counts = {"pending": 0, "won": 0, "lost": 0, "passed": 0}
        gross_margin_total = 0.0
        roi_values: list[float] = []
        outcome_aliases = {
            "sold": "won",
            "won": "won",
            "lost": "lost",
            "passed": "passed",
            "pending": "pending",
        }

        for row in rows:
            raw_outcome = (row.get("outcome") or "pending").strip().lower()
            outcome = outcome_aliases.get(raw_outcome, "pending")
            counts[outcome] = counts.get(outcome, 0) + 1
            margin = _safe_float(row.get("gross_margin"))
            if margin is not None:
                gross_margin_total += margin
            roi = _safe_float(row.get("roi_pct"))
            if roi is not None:
                roi_values.append(roi)

        avg_roi = round(sum(roi_values) / len(roi_values), 2) if roi_values else None
        return {
            "count_by_outcome": counts,
            "total_gross_margin": round(gross_margin_total, 2),
            "avg_roi": avg_roi,
        }
    except Exception as exc:
        logger.error("[OUTCOMES] summary failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load outcome summary")


@router.post("")
async def create_outcome(
    payload: OutcomePayload,
    authorization: Optional[str] = Header(None),
):
    if not supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    user_id = _verify_auth(authorization)
    opportunity = _fetch_opportunity(payload.opportunity_id, require_user_id=user_id)
    _legacy_mirror_to_dealer_sales(user_id, opportunity, payload)

    return {"success": True}


@router.post("/bid")
async def create_bid_outcome(
    payload: BidOutcomePayload,
    authorization: Optional[str] = Header(None),
):
    if not supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    user_id = _verify_auth(authorization)
    opportunity = _fetch_opportunity(payload.opportunity_id, require_user_id=user_id)

    normalized = _normalize_bid_outcome(payload, opportunity)

    notes_blob = json.dumps(
        {
            "type": "bid_outcome",
            "bid": normalized.bid,
            "outcome": normalized.outcome,
            "won": normalized.outcome == "won",
            "purchase_price": normalized.purchase_price,
            "bid_amount": normalized.bid_amount,
            "user_notes": payload.notes or "",
        }
    )

    update_payload = {
        "bid_amount": normalized.bid_amount,
        "won": normalized.outcome == "won",
        "outcome_notes": notes_blob,
        "outcome_recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if normalized.outcome == "won" and normalized.purchase_price is not None:
        update_payload["outcome_sale_price"] = normalized.purchase_price

    try:
        supabase_client.table("opportunities").update(update_payload).eq("id", payload.opportunity_id).execute()
        logger.info("[OUTCOMES/BID] recorded bid=%s won=%s opp=%s user=%s", payload.bid, payload.won, payload.opportunity_id, user_id)
        return {"success": True, "opportunity": opportunity}
    except Exception as exc:
        logger.error("[OUTCOMES/BID] failed for opportunity %s: %s", payload.opportunity_id, exc)
        raise HTTPException(status_code=500, detail="Failed to record bid outcome")
