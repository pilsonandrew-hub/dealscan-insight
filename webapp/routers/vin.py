from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from backend.ingest import score

router = APIRouter()

class VinDecodeRequest(BaseModel):
    vin: str

class VinScoreRequest(BaseModel):
    year: int
    make: str
    model: str
    body_type: str
    engine: str
    asking_price: float
    location_state: str

@router.post("/decode")
async def decode_vin(req: VinDecodeRequest):
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{req.vin}?format=json"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="NHTSA API request failed")
        resp = r.json()

    results = resp.get("Results", [{}])[0]
    return {
        "year": results.get("ModelYear", ""),
        "make": results.get("Make", ""),
        "model": results.get("Model", ""),
        "body_type": results.get("BodyClass", ""),
        "engine": results.get("EngineModel", "")
    }

@router.post("/score")
def score_vin(req: VinScoreRequest):
    # B7-4: Call score_deal with correct parameters
    result = score.score_deal(
        bid=req.asking_price,
        mmr_ca=req.asking_price,  # Use asking_price as proxy when MMR unknown
        state=req.location_state,
        source_site="vin_decode",
        make=req.make,
        model=req.model,
        year=req.year,
    )

    return result
