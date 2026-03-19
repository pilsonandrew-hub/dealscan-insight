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
    vin_data = {
        "year": req.year,
        "make": req.make,
        "model": req.model,
        "body_type": req.body_type,
        "engine": req.engine
    }

    scoring_input = {
        "vin_data": vin_data,
        "asking_price": req.asking_price,
        "location_state": req.location_state
    }

    # Placeholder: invoke existing scoring logic here
    result = score.run_score(scoring_input)  # Adjust call to actual API

    return result
