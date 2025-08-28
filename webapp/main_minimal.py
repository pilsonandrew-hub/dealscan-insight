"""
Minimal FastAPI app to get DealerScope running
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Create FastAPI app
app = FastAPI(
    title="DealerScope API",
    version="1.0.0",
    description="Intelligent Vehicle Arbitrage Platform"
)

# Basic CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Health check
@app.get("/healthz")
async def health_check():
    """Health check for load balancers"""
    return {"status": "healthy", "version": "1.0.0"}

# Include minimal routes
from webapp.routers.minimal import router as minimal_router
app.include_router(minimal_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(
        "webapp.main_minimal:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )