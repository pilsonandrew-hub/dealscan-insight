import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["outcomes"])
logger = logging.getLogger(__name__)

_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

supa = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client

        supa = create_client(_supabase_url, _supabase_key)
except Exception as exc:
    logger.warning(f"Outcomes Supabase client init failed (non-fatal): {exc}")


class OutcomePayload(BaseModel):
    opportunity_id: str
    sale_price: float
    sale_date: str
    days_to_sale: int
    notes: Optional[str] = None


def _verify_auth(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    token = authorization.split(" ", 1)[1]

    try:
        user = supa.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _mirror_outcome_to_dealer_sales(user_id: str, opportunity: dict, payload: OutcomePayload) -> bool:
    metadata = {
        "opportunity_id": payload.opportunity_id,
        "days_to_sale": payload.days_to_sale,
        "notes": payload.notes or "",
    }

    insert_payload = {
        "user_id": user_id,
        "vin": opportunity.get("vin"),
        "make": opportunity.get("make") or "Unknown",
        "model": opportunity.get("model") or "Unknown",
        "year": opportunity.get("year") or 0,
        "mileage": opportunity.get("mileage"),
        "sale_price": payload.sale_price,
        "sale_date": payload.sale_date,
        "location": opportunity.get("location") or opportunity.get("city"),
        "state": opportunity.get("state"),
        "source_type": "outcome_tracking",
        "metadata": metadata,
        "condition_grade": opportunity.get("condition_grade"),
    }

    try:
        supa.table("dealer_sales").insert(insert_payload).execute()
        return True
    except Exception as exc:
        logger.warning(
            "[OUTCOMES] dealer_sales mirror skipped for opportunity %s: %s",
            payload.opportunity_id,
            exc,
        )
        return False


@router.post("/outcomes")
async def create_outcome(
    payload: OutcomePayload,
    authorization: Optional[str] = Header(None),
):
    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    user_id = _verify_auth(authorization)

    try:
        opportunity_resp = (
            supa.table("opportunities")
            .select("*")
            .eq("id", payload.opportunity_id)
            .limit(1)
            .execute()
        )
        opportunities = opportunity_resp.data or []
        if not opportunities:
            raise HTTPException(status_code=404, detail="Opportunity not found")

        opportunity = opportunities[0]
        update_payload = {
            "outcome_sale_price": payload.sale_price,
            "outcome_sale_date": payload.sale_date,
            "outcome_days_to_sale": payload.days_to_sale,
            "outcome_notes": payload.notes,
            "outcome_recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        update_resp = (
            supa.table("opportunities")
            .update(update_payload)
            .eq("id", payload.opportunity_id)
            .execute()
        )
        if hasattr(update_resp, "data") and not update_resp.data:
            raise HTTPException(status_code=404, detail="Opportunity not found")

        mirrored = _mirror_outcome_to_dealer_sales(user_id, opportunity, payload)
        return {"success": True, "dealer_sales_mirrored": mirrored}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[OUTCOMES] Insert failed: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
