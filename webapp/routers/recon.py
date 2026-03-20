"""
Recon manual vehicle evaluation router for DealerScope.
"""

import os
import re
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Path
from fastapi.security import HTTPAuthorizationCredentials
from typing import List, Optional
from urllib.parse import quote
from pydantic import BaseModel, Field
from webapp.auth import get_current_user
from webapp.models.user import User

_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
_supabase_client = None
if _supabase_url and _supabase_key:
    from supabase import create_client
    _supabase_client = create_client(_supabase_url, _supabase_key)

router = APIRouter(prefix="/recon", tags=["recon"])

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{1,17}$")

# Data models

class EvaluateRequest(BaseModel):
    vin: str = Field(..., description="VIN sanitized")
    mileage: int = Field(..., ge=1, le=300000)
    year: int = Field(..., ge=1990, le=2030)
    make: str
    model: str
    asking_price: float = Field(..., gt=0)
    title_status: str
    condition: str
    source: str
    state: str

class PromoteResponse(BaseModel):
    success: bool
    message: str

@router.get("/vin/{vin}")
async def vin_decode(vin: str = Path(..., description="VIN to decode"), user: User = Depends(get_current_user)):
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
async def evaluate_vehicle(req: EvaluateRequest, user: User = Depends(get_current_user)):
    """Main evaluation endpoint"""
    # Validation
    if req.title_status.lower() in {"rebuilt", "salvage", "flood", "fire", "hail", "lemon"}:
        return {"verdict": "IMMEDIATE PASS"}

    # Placeholder: Fetch comps and compute pessimistic sale price & grade
    pessimistic_sale = 10000.0  # TODO: implement
    grade = "C"  # TODO: implement

    # Costing placeholders
    condition_penalty_map = {"Excellent": 0, "Good": 750, "Fair": 2000, "Poor": 5000}
    condition_penalty = condition_penalty_map.get(req.condition, 2000)
    fleet_stigma = 750  # Placeholder no records
    transport = 500  # Placeholder transport cost
    buyer_premium = 0.125  # Placeholder for GovDeals
    doc_fee = 150  # Placeholder
    manheim_sell_fee = 275  # Placeholder

    all_costs = condition_penalty + fleet_stigma + transport + doc_fee + manheim_sell_fee + (pessimistic_sale * buyer_premium)

    max_bid = pessimistic_sale * 0.90 - all_costs  # using CTM ceiling 90% placeholder

    margin = req.asking_price - max_bid
    velocity = 5  # Placeholder
    segment_score = 2  # Placeholder
    model_score = 1  # Placeholder

    # Compute DOS scoring
    base_dos = margin * 0.41 + velocity * 0.27 + segment_score * 0.20 + model_score * 0.12
    confidence = 1.0  # Placeholder
    adjusted_dos = base_dos * confidence

    # Decide verdict based on thresholds
    if req.title_status.lower() in {"rebuilt", "salvage", "flood", "fire", "hail", "lemon"}:
        verdict = "IMMEDIATE PASS"
    elif adjusted_dos >= 80 and margin >= 3000:
        verdict = "HOT BUY"
    elif adjusted_dos >= 65 and margin >= 1500:
        verdict = "BUY"
    elif adjusted_dos >= 45 and margin >= 1000:
        verdict = "WATCH"
    else:
        verdict = "PASS"

    # Save evaluation to Supabase
    eval_data = {
        "user_id": user.id,
        "vin": req.vin,
        "mileage": req.mileage,
        "year": req.year,
        "make": req.make,
        "model": req.model,
        "asking_price": req.asking_price,
        "title_status": req.title_status,
        "condition": req.condition,
        "source": req.source,
        "state": req.state,
        "pessimistic_sale_price": pessimistic_sale,
        "grade": grade,
        "max_bid": max_bid,
        "margin": margin,
        "adjusted_dos": adjusted_dos,
        "verdict": verdict
    }

    if _supabase_client:
        result = _supabase_client.table("recon_evaluations").insert(eval_data).execute()
        if result.error:
            raise HTTPException(status_code=500, detail="Failed to save evaluation")

    return {"verdict": verdict, "adjusted_dos": adjusted_dos, "margin": margin}

@router.get("/history")
async def get_history(user: User = Depends(get_current_user)):
    """List past evaluations for authenticated user"""
    if not _supabase_client:
        raise HTTPException(status_code=503, detail="Supabase client not configured")
    result = _supabase_client.table("recon_evaluations").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
    if result.error:
        raise HTTPException(status_code=500, detail="Failed to fetch history")

    return result.data

@router.post("/promote/{recon_id}")
async def promote_recon(recon_id: int = Path(...), user: User = Depends(get_current_user)):
    """Promote to opportunities pipeline, atomic guard"""
    if not _supabase_client:
        raise HTTPException(status_code=503, detail="Supabase client not configured")

    # Check if already promoted
    res = _supabase_client.table("opportunities").select("id").eq("recon_id", recon_id).limit(1).execute()
    if res.error:
        raise HTTPException(status_code=500, detail="Failed to check promotion status")
    if res.data:
        return {"success": False, "message": "Already promoted"}

    # Fetch recon eval
    recon_res = _supabase_client.table("recon_evaluations").select("*").eq("id", recon_id).limit(1).execute()
    if recon_res.error or not recon_res.data:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    eval_data = recon_res.data[0]

    # Insert into opportunities
    opp_data = {
        "user_id": user.id,
        "recon_id": recon_id,
        "vin": eval_data.get("vin"),
        "make": eval_data.get("make"),
        "model": eval_data.get("model"),
        "year": eval_data.get("year"),
        "asking_price": eval_data.get("asking_price"),
        "status": "new",
    }

    insert_res = _supabase_client.table("opportunities").insert(opp_data).execute()
    if insert_res.error:
        raise HTTPException(status_code=500, detail="Failed to promote evaluation")

    return {"success": True, "message": "Promoted to opportunities"}
