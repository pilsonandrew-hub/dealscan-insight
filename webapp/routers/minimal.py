"""
Minimal working routes to get the app running
"""
from fastapi import APIRouter
from typing import Dict, Any

router = APIRouter()

@router.get("/ping")
async def ping() -> Dict[str, str]:
    """Simple ping endpoint"""
    return {"message": "pong", "status": "ok"}

@router.get("/version")
async def version() -> Dict[str, str]:
    """Get API version"""
    return {"version": "1.0.0", "name": "DealerScope API"}

@router.get("/opportunities")
async def get_opportunities() -> Dict[str, Any]:
    """Mock opportunities endpoint"""
    return {
        "opportunities": [
            {
                "id": 1,
                "vehicle": "2020 Toyota Camry",
                "profit_potential": 3500,
                "confidence": 0.85
            },
            {
                "id": 2,
                "vehicle": "2019 Honda Civic",
                "profit_potential": 2200,
                "confidence": 0.78
            }
        ],
        "total": 2
    }