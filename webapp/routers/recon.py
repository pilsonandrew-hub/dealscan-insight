"""
Recon manual vehicle evaluation router for DealerScope.
"""

import os
import re
import httpx
import logging
from fastapi import APIRouter, HTTPException, Header, Path, status
from typing import List, Optional
from urllib.parse import quote
from pydantic import BaseModel, Field

_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
_supabase_client = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        _supabase_client = create_client(_supabase_url, _supabase_key)
except Exception as e:
    logging.warning(f"Supabase client init failed: {e}")

async def get_retail_market_value(year: int, make: str, model: str, mileage: int) -> dict:
    """Fetch real-time retail listings from Marketcheck. Returns median price and range."""
    try:
        miles_min = max(0, mileage - 15000)
        miles_max = mileage + 15000
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://mc-api.marketcheck.com/v2/search/car/active",
                params={
                    "api_key": os.getenv("MARKETCHECK_API_KEY", "Z56KBF2WRBWXcnPpbFBY8FEuRoUujiz4"),
                    "year": year,
                    "make": make.lower(),
                    "model": model.lower(),
                    "miles_min": miles_min,
                    "miles_max": miles_max,
                    "rows": 50,
                    "fields": "price,miles"
                }
            )
        if resp.status_code != 200:
            return {"retail_value": None, "retail_low": None, "retail_high": None, "retail_count": 0, "retail_source": "unavailable"}
        listings = resp.json().get("listings", [])
        prices = sorted([l["price"] for l in listings if l.get("price") and l["price"] > 5000])
        if not prices:
            return {"retail_value": None, "retail_low": None, "retail_high": None, "retail_count": 0, "retail_source": "no_listings"}
        median = prices[len(prices) // 2]
        return {
            "retail_value": median,
            "retail_low": prices[0],
            "retail_high": prices[-1],
            "retail_count": len(prices),
            "retail_source": "marketcheck"
        }
    except Exception as e:
        logging.warning(f"Marketcheck lookup failed: {e}")
        return {"retail_value": None, "retail_low": None, "retail_high": None, "retail_count": 0, "retail_source": "error"}


router = APIRouter(prefix="/recon", tags=["recon"])

def _verify_auth(authorization: Optional[str]) -> str:
    """Validate Supabase JWT. Returns user_id on success."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1]
    if not _supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")
    try:
        user = _supabase_client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")



VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{1,17}$")

# Data models

class EvaluateRequest(BaseModel):
    vin: Optional[str] = Field(None, description="VIN — optional, provide for more accurate comp matching")
    mileage: int = Field(..., ge=1, le=300000)
    year: int = Field(..., ge=1990, le=2030)
    make: str
    model: str
    asking_price: Optional[float] = Field(None, gt=0)
    title_status: str
    condition: str
    condition_grade: Optional[str] = None  # Overrides condition for penalty lookup
    fleet: bool = False
    fleet_has_records: Optional[bool] = None
    source: str
    state: str

class PromoteResponse(BaseModel):
    success: bool
    message: str

@router.get("/vin/{vin}")
async def vin_decode(vin: str = Path(..., description="VIN to decode"), authorization: Optional[str] = Header(None)):
    """Decode VIN via NHTSA free API"""
    vin = vin.upper()
    if not VIN_PATTERN.match(vin):
        raise HTTPException(status_code=400, detail="Invalid VIN format")
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="VIN decode service unavailable")
        data = resp.json()
    return data

@router.post("/evaluate")
async def evaluate_vehicle(req: EvaluateRequest, authorization: Optional[str] = Header(None)):
    """Main evaluation endpoint — real scoring against dealer_sales comps"""
    user_id = _verify_auth(authorization)
    auction_mode = req.asking_price is None
    reason = ""

    # Normalize inputs
    req.title_status = req.title_status.strip().lower()
    req.condition = req.condition.strip().title()
    if req.condition_grade:
        req.condition_grade = req.condition_grade.strip().title()
    req.make = req.make.strip().title()
    req.model = req.model.strip()
    req.state = req.state.strip().upper()

    # Non-clean title immediate pass
    if req.title_status.lower() not in {"clean"}:
        verdict = "PASS"
        reason = "Non-clean title — immediate pass"
        return {"verdict": verdict, "reason": reason}

    if not _supabase_client:
        raise HTTPException(status_code=503, detail="Supabase client not configured")

    # ── FIX 2a: Query dealer_sales for comps ─────────────────────────────────
    low_odo = req.mileage - 25000
    high_odo = req.mileage + 25000
    comps_res = (
        _supabase_client
        .table("dealer_sales")
        .select("sale_price,sale_date_label")
        .eq("make", req.make)
        .ilike("model", req.model)
        .eq("year", req.year)
        .gte("odometer", low_odo)
        .lte("odometer", high_odo)
        .gt("sale_price", 0)
        .limit(20)
        .execute()
    )
    comp_records = comps_res.data or []
    comp_count = len(comp_records)
    distinct_dates = len(set(r["sale_date_label"] for r in comp_records if r.get("sale_date_label")))

    retail_data = await get_retail_market_value(req.year, req.make, req.model, req.mileage)
    retail_value = retail_data.get("retail_value")

    if comp_count >= 3 and distinct_dates >= 2:
        grade = "A+"
        pessimistic = float(min(r["sale_price"] for r in comp_records))
    else:
        grade = "C"
        if auction_mode:
            pessimistic = None
        else:
            if retail_value is not None:
                pessimistic = retail_value * 0.85  # wholesale = ~85% of retail
            else:
                pessimistic = req.asking_price * 0.70

    # ── FIX 2b: Condition penalty ─────────────────────────────────────────────
    cg = req.condition_grade or req.condition
    v = pessimistic if pessimistic is not None else 0
    penalties = {
        "Excellent": 0,
        "Good": 750 if v < 25000 else 1250,
        "Fair": 2000 if v < 25000 else 4000,
        "Poor": 5000 if v < 25000 else 8000,
    }
    condition_penalty = penalties.get(cg, 0)

    # ── FIX 2c: Fleet penalty ─────────────────────────────────────────────────
    if req.fleet and comp_count < 3:
        fleet_penalty = 750
    elif req.fleet and comp_count >= 3:
        fleet_penalty = 400
    else:
        fleet_penalty = 0

    # ── FIX 2d: Manheim sell fee ──────────────────────────────────────────────
    p = pessimistic if pessimistic is not None else 0
    if p < 15000:
        sell_fee = 275
    elif p < 25000:
        sell_fee = 325
    elif p < 40000:
        sell_fee = 375
    else:
        sell_fee = 450

    # ── FIX 2e: Total cost ────────────────────────────────────────────────────
    transport = 800  # default
    total_cost = condition_penalty + fleet_penalty + sell_fee + transport

    # ── FIX 2f: DOS ───────────────────────────────────────────────────────────
    if auction_mode or pessimistic is None:
        margin_score = 50.0
    else:
        margin_pct = max(0.0, (pessimistic - req.asking_price) / pessimistic) if pessimistic > 0 else 0.0
        margin_score = min(100.0, margin_pct * 300)
    dos = margin_score * 0.41 + 50 * 0.27 + 50 * 0.20 + 50 * 0.12

    # ── FIX 2g: Multiplier ────────────────────────────────────────────────────
    multiplier_map = {"A+": 1.0, "A": 1.0, "B": 0.90, "C": 0.80}
    multiplier = multiplier_map.get(grade, 0.80)
    adjusted_dos = dos * multiplier

    # ── FIX 2h: CTM, max_bid, profit ─────────────────────────────────────────
    ctm = 0.90 if adjusted_dos >= 80 else 0.88
    max_bid = (pessimistic * ctm - total_cost) if pessimistic is not None else None
    profit = (max_bid - req.asking_price) if (not auction_mode and max_bid is not None) else None

    # ── FIX 2i: Verdict ───────────────────────────────────────────────────────
    if auction_mode:
        if adjusted_dos >= 75:
            verdict = "HOT BUY"
        elif adjusted_dos >= 60:
            verdict = "BUY"
        elif adjusted_dos >= 45:
            verdict = "WATCH"
        else:
            verdict = "PASS"
    else:
        if req.asking_price is not None and max_bid is not None and req.asking_price > max_bid:
            verdict = "PASS"
            reason = "Asking price exceeds max bid"
        elif adjusted_dos >= 80 and profit is not None and profit >= 3000 and comp_count >= 3:
            verdict = "HOT BUY"
        elif adjusted_dos >= 65 and profit is not None and profit >= 1500:
            verdict = "BUY"
        elif adjusted_dos >= 45 and profit is not None and profit >= 1000:
            verdict = "WATCH"
        else:
            verdict = "PASS"

        if comp_count < 3 and verdict in {"HOT BUY", "BUY"}:
            verdict = "WATCH"
            reason = "Insufficient comps (<3)"

    # Save evaluation to Supabase
    eval_row = {
        "user_id": user_id,
        "vin": req.vin,
        "mileage": req.mileage,
        "year": req.year,
        "make": req.make,
        "model": req.model,
        "title_status": req.title_status,
        "condition_grade": cg,
        "source": req.source,
        "state": req.state,
        "pessimistic_sale": pessimistic,
        "reliability_grade": grade,
        "comp_count": comp_count,
        "condition_penalty": condition_penalty,
        "fleet_stigma_penalty": fleet_penalty,
        "manheim_sell_fee": sell_fee,
        "transport_cost": transport,
        "total_all_in_cost": total_cost,
        "dos_score": round(dos, 2),
        "adjusted_dos": round(adjusted_dos, 2),
        "max_bid": round(max_bid, 2) if max_bid is not None else None,
        "verdict": verdict,
        "verdict_reason": reason,
        "promoted_to_pipeline": False,
    }
    # asking_price — use actual value or 0 as sentinel (DB column is NOT NULL)
    eval_row["asking_price"] = req.asking_price if req.asking_price is not None else 0.0
    if profit is not None:
        eval_row["profit_expected"] = round(profit, 2)
        eval_row["profit_pessimistic"] = round(profit, 2)
        eval_row["profit_optimistic"] = round(profit, 2)

    insert_res = _supabase_client.table("recon_evaluations").insert(eval_row).execute()
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Failed to save evaluation")

    new_id = insert_res.data[0]["id"] if insert_res.data else None

    return {
        "id": new_id,
        "auction_mode": auction_mode,
        "verdict": verdict,
        "verdict_reason": reason,
        "reliability_grade": grade,
        "comp_count": comp_count,
        "pessimistic_sale": pessimistic,
        "pessimistic_sale_price": pessimistic,
        "condition_penalty": condition_penalty,
        "fleet_stigma_penalty": fleet_penalty,
        "manheim_sell_fee": sell_fee,
        "transport_cost": transport,
        "total_all_in_cost": total_cost,
        "dos": round(dos, 2),
        "adjusted_dos": round(adjusted_dos, 2),
        "max_bid": round(max_bid, 2) if max_bid is not None else None,
        "profit_expected": round(profit, 2) if profit is not None else None,
        "profit_pessimistic": round(profit, 2) if profit is not None else None,
        "profit_optimistic": round(profit, 2) if profit is not None else None,
        "asking_price": req.asking_price,
        "pricing_source": "Manheim" if comp_count >= 3 else "Estimated",
        "promoted_to_pipeline": False,
        "retail_market_value": retail_data.get("retail_value"),
        "retail_low": retail_data.get("retail_low"),
        "retail_high": retail_data.get("retail_high"),
        "retail_count": retail_data.get("retail_count"),
        "retail_source": retail_data.get("retail_source"),
    }

@router.get("/history")
async def get_history(authorization: Optional[str] = Header(None)):
    """List past evaluations for authenticated user"""
    user_id = _verify_auth(authorization)
    if not _supabase_client:
        raise HTTPException(status_code=503, detail="Supabase client not configured")
    result = _supabase_client.table("recon_evaluations").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    if result.data is None:
        raise HTTPException(status_code=500, detail="Failed to fetch history")

    # Normalize DB column names → ReconResult interface field names
    def normalize(row: dict) -> dict:
        return {
            "id": row.get("id"),
            "verdict": row.get("verdict"),
            "verdict_reason": row.get("verdict_reason") or row.get("reason", ""),
            "reliability_grade": row.get("reliability_grade") or row.get("grade", "C"),
            "max_bid": row.get("max_bid", 0),
            "asking_price": row.get("asking_price", 0),
            "profit_expected": row.get("profit_expected") or row.get("profit", 0),
            "profit_pessimistic": row.get("profit_pessimistic") or row.get("profit", 0),
            "profit_optimistic": row.get("profit_optimistic") or row.get("profit", 0),
            "adjusted_dos": row.get("adjusted_dos", 0),
            "comp_count": row.get("comp_count", 0),
            "condition_penalty": row.get("condition_penalty", 0),
            "fleet_stigma_penalty": row.get("fleet_stigma_penalty") or row.get("fleet_penalty", 0),
            "manheim_sell_fee": row.get("manheim_sell_fee") or row.get("sell_fee", 0),
            "transport_cost": row.get("transport_cost", 800),
            "total_all_in_cost": row.get("total_all_in_cost") or row.get("total_cost", 0),
            "promoted_to_pipeline": row.get("promoted_to_pipeline", False),
            "pricing_source": row.get("pricing_source") or row.get("source", "Estimated"),
            "make": row.get("make", ""),
            "model": row.get("model", ""),
            "year": row.get("year", 0),
            "vin": row.get("vin", ""),
            "created_at": row.get("created_at"),
        }

    return [normalize(r) for r in result.data]

@router.post("/promote/{recon_id}")
async def promote_recon(recon_id: str = Path(...), authorization: Optional[str] = Header(None)):
    """Promote to opportunities pipeline — atomic ownership guard"""
    user_id = _verify_auth(authorization)
    if not _supabase_client:
        raise HTTPException(status_code=503, detail="Supabase client not configured")

    # ── FIX 1: Fetch eval with ownership check ────────────────────────────────
    recon_res = (
        _supabase_client
        .table("recon_evaluations")
        .select("*")
        .eq("id", recon_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not recon_res.data:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    eval_data = recon_res.data[0]

    if eval_data.get("promoted_to_pipeline"):
        raise HTTPException(status_code=409, detail="Already promoted")

    # Create opportunity record
    opp_data = {
        "user_id": user_id,
        "recon_id": recon_id,
        "vin": eval_data.get("vin"),
        "make": eval_data.get("make"),
        "model": eval_data.get("model"),
        "year": eval_data.get("year"),
        "asking_price": eval_data.get("asking_price"),
        "status": "new",
    }
    insert_res = _supabase_client.table("opportunities").insert(opp_data).execute()
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Failed to create opportunity")

    new_opp_id = insert_res.data[0]["id"]

    # Atomic update — only flips if still false (guards against race)
    update_res = (
        _supabase_client
        .table("recon_evaluations")
        .update({"promoted_to_pipeline": True, "opportunity_id": new_opp_id})
        .eq("id", recon_id)
        .eq("promoted_to_pipeline", False)
        .execute()
    )
    if not update_res.data:
        raise HTTPException(status_code=409, detail="Already promoted")

    return {"success": True, "message": "Promoted to opportunities", "opportunity_id": new_opp_id}

