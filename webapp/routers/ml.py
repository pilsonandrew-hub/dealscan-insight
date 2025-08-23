"""
Machine Learning API endpoints for pricing and scoring
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from webapp.database import get_db
from webapp.models.user import User
from webapp.models.vehicle import Vehicle, Opportunity, MLModel
from webapp.auth import get_current_user, get_current_admin_user
from webapp.ml.price_predictor import PricePredictor
from webapp.ml.risk_assessor import RiskAssessor
from webapp.ml.opportunity_scorer import OpportunityScorer

router = APIRouter()

# Pydantic models
class PredictionRequest(BaseModel):
    make: str
    model: str
    year: int
    mileage: Optional[int] = None
    state: Optional[str] = None
    condition: Optional[str] = "fair"
    features: Optional[Dict[str, Any]] = {}

class PredictionResponse(BaseModel):
    predicted_price: float
    confidence: float
    price_range: Dict[str, float]  # low, high
    factors: List[Dict[str, Any]]
    model_version: str

class BatchPredictionRequest(BaseModel):
    vehicles: List[PredictionRequest]

class ScoringRequest(BaseModel):
    vehicle_id: int
    current_bid: float
    fees: Optional[float] = 0.0
    transportation_cost: Optional[float] = 0.0

class ModelPerformanceResponse(BaseModel):
    model_name: str
    version: str
    metrics: Dict[str, float]
    last_trained: str
    status: str

# Initialize ML models
price_predictor = PricePredictor()
risk_assessor = RiskAssessor()
opportunity_scorer = OpportunityScorer()

@router.post("/predict-price", response_model=PredictionResponse)
async def predict_price(
    request: PredictionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Predict vehicle price using ML model"""
    try:
        # Prepare features for prediction
        features = {
            "make": request.make,
            "model": request.model,
            "year": request.year,
            "mileage": request.mileage or 0,
            "state": request.state or "unknown",
            "condition": request.condition,
            **request.features
        }
        
        # Get prediction
        result = await price_predictor.predict(features)
        
        return PredictionResponse(
            predicted_price=result["predicted_price"],
            confidence=result["confidence"],
            price_range={
                "low": result["price_range"]["low"],
                "high": result["price_range"]["high"]
            },
            factors=result["factors"],
            model_version=result["model_version"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

@router.post("/batch-predict")
async def batch_predict_prices(
    request: BatchPredictionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Batch price prediction for multiple vehicles"""
    try:
        results = []
        
        for vehicle_req in request.vehicles:
            features = {
                "make": vehicle_req.make,
                "model": vehicle_req.model,
                "year": vehicle_req.year,
                "mileage": vehicle_req.mileage or 0,
                "state": vehicle_req.state or "unknown",
                "condition": vehicle_req.condition,
                **vehicle_req.features
            }
            
            result = await price_predictor.predict(features)
            results.append(result)
        
        return {"predictions": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {str(e)}")

@router.post("/score-opportunity")
async def score_opportunity(
    request: ScoringRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Score an opportunity for profitability"""
    try:
        # Get vehicle data
        vehicle = db.query(Vehicle).filter(Vehicle.id == request.vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        # Prepare data for scoring
        scoring_data = {
            "vehicle": {
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "mileage": vehicle.mileage,
                "state": vehicle.state,
                "title_status": vehicle.title_status
            },
            "current_bid": request.current_bid,
            "fees": request.fees,
            "transportation_cost": request.transportation_cost
        }
        
        # Get opportunity score
        score_result = await opportunity_scorer.score(scoring_data)
        
        # Get risk assessment
        risk_result = await risk_assessor.assess(scoring_data["vehicle"])
        
        # Create or update opportunity record
        opportunity = db.query(Opportunity).filter(
            Opportunity.vehicle_id == request.vehicle_id,
            Opportunity.user_id == current_user.id
        ).first()
        
        if not opportunity:
            opportunity = Opportunity(
                vehicle_id=request.vehicle_id,
                user_id=current_user.id
            )
            db.add(opportunity)
        
        # Update opportunity with ML results
        opportunity.opportunity_score = score_result["score"]
        opportunity.potential_profit = score_result["potential_profit"]
        opportunity.profit_margin = score_result["profit_margin"]
        opportunity.roi_percentage = score_result["roi_percentage"]
        opportunity.predicted_retail_price = score_result["predicted_retail_price"]
        opportunity.price_confidence = score_result["confidence"]
        opportunity.total_acquisition_cost = request.current_bid + request.fees + request.transportation_cost
        opportunity.risk_score = risk_result["risk_score"]
        opportunity.risk_factors = risk_result["risk_factors"]
        opportunity.price_factors = score_result["factors"]
        opportunity.days_to_sell_prediction = score_result.get("days_to_sell", None)
        
        db.commit()
        
        return {
            "opportunity_id": opportunity.id,
            "score": score_result["score"],
            "potential_profit": score_result["potential_profit"],
            "profit_margin": score_result["profit_margin"],
            "roi_percentage": score_result["roi_percentage"],
            "risk_score": risk_result["risk_score"],
            "risk_factors": risk_result["risk_factors"],
            "recommendation": score_result["recommendation"],
            "confidence": score_result["confidence"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {str(e)}")

@router.post("/retrain-models")
async def retrain_models(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Trigger model retraining (admin only)"""
    
    # Add retraining tasks to background
    background_tasks.add_task(price_predictor.retrain)
    background_tasks.add_task(risk_assessor.retrain)
    background_tasks.add_task(opportunity_scorer.retrain)
    
    return {"message": "Model retraining initiated"}

@router.get("/model-status", response_model=List[ModelPerformanceResponse])
async def get_model_status(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get status and performance of ML models"""
    
    models = db.query(MLModel).filter(MLModel.is_active == True).all()
    
    status_list = []
    for model in models:
        status_list.append(ModelPerformanceResponse(
            model_name=model.name,
            version=model.version,
            metrics=model.performance_metrics or {},
            last_trained=model.trained_at.isoformat() if model.trained_at else "Never",
            status="active" if model.is_production else "inactive"
        ))
    
    return status_list

@router.get("/feature-importance/{model_type}")
async def get_feature_importance(
    model_type: str,
    current_user: User = Depends(get_current_user)
):
    """Get feature importance for a specific model type"""
    
    if model_type == "price":
        importance = await price_predictor.get_feature_importance()
    elif model_type == "risk":
        importance = await risk_assessor.get_feature_importance()
    elif model_type == "opportunity":
        importance = await opportunity_scorer.get_feature_importance()
    else:
        raise HTTPException(status_code=400, detail="Invalid model type")
    
    return {"model_type": model_type, "feature_importance": importance}

@router.post("/explain-prediction")
async def explain_prediction(
    request: PredictionRequest,
    current_user: User = Depends(get_current_user)
):
    """Get detailed explanation for a prediction"""
    
    features = {
        "make": request.make,
        "model": request.model,
        "year": request.year,
        "mileage": request.mileage or 0,
        "state": request.state or "unknown",
        "condition": request.condition,
        **request.features
    }
    
    explanation = await price_predictor.explain_prediction(features)
    
    return {
        "explanation": explanation,
        "features_used": features,
        "model_version": explanation.get("model_version")
    }