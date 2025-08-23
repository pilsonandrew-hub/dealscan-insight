"""
Opportunities API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from pydantic import BaseModel

from webapp.database import get_db
from webapp.models.user import User
from webapp.models.vehicle import Vehicle, Opportunity
from webapp.auth import get_current_user, get_optional_user

router = APIRouter()

class OpportunityResponse(BaseModel):
    id: int
    vehicle_id: int
    vehicle_info: dict
    opportunity_score: Optional[float] = None
    potential_profit: Optional[float] = None
    profit_margin: Optional[float] = None
    roi_percentage: Optional[float] = None
    risk_score: Optional[float] = None
    risk_factors: Optional[List[str]] = None
    recommendation_reason: Optional[str] = None
    total_acquisition_cost: float
    predicted_retail_price: Optional[float] = None
    days_to_sell_prediction: Optional[int] = None
    auction_end: Optional[str] = None
    is_active: bool
    created_at: str
    updated_at: str

class OpportunityListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[OpportunityResponse]

@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    max_risk: float = Query(1.0, ge=0.0, le=1.0),
    min_profit: Optional[float] = Query(None, gt=0),
    max_price: Optional[float] = Query(None, gt=0),
    state: Optional[str] = Query(None, max_length=2),
    make: Optional[str] = Query(None, max_length=50),
    model: Optional[str] = Query(None, max_length=100),
    sort_by: str = Query("score", regex="^(score|profit|risk|date)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100)
):
    """List opportunities with filtering and sorting"""
    
    # Build query
    query = db.query(Opportunity, Vehicle).join(
        Vehicle, Vehicle.id == Opportunity.vehicle_id
    ).filter(
        Opportunity.is_active == True,
        Vehicle.is_active == True
    )
    
    # Apply filters
    if min_score > 0:
        query = query.filter(Opportunity.opportunity_score >= min_score)
    
    if max_risk < 1.0:
        query = query.filter(Opportunity.risk_score <= max_risk)
    
    if min_profit:
        query = query.filter(Opportunity.potential_profit >= min_profit)
    
    if max_price:
        query = query.filter(Vehicle.current_bid <= max_price)
    
    if state:
        query = query.filter(Vehicle.state.ilike(f"%{state}%"))
    
    if make:
        query = query.filter(Vehicle.make.ilike(f"%{make}%"))
    
    if model:
        query = query.filter(Vehicle.model.ilike(f"%{model}%"))
    
    # Apply sorting
    if sort_by == "score":
        query = query.order_by(desc(Opportunity.opportunity_score))
    elif sort_by == "profit":
        query = query.order_by(desc(Opportunity.potential_profit))
    elif sort_by == "risk":
        query = query.order_by(Opportunity.risk_score)
    elif sort_by == "date":
        query = query.order_by(desc(Opportunity.created_at))
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    # Format response
    opportunities = []
    for opp, vehicle in items:
        opportunities.append(OpportunityResponse(
            id=opp.id,
            vehicle_id=vehicle.id,
            vehicle_info={
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "mileage": vehicle.mileage,
                "state": vehicle.state,
                "title": vehicle.title,
                "current_bid": vehicle.current_bid,
                "source": vehicle.source,
                "source_url": vehicle.source_url,
                "image_urls": vehicle.image_urls,
                "title_status": vehicle.title_status
            },
            opportunity_score=opp.opportunity_score,
            potential_profit=opp.potential_profit,
            profit_margin=opp.profit_margin,
            roi_percentage=opp.roi_percentage,
            risk_score=opp.risk_score,
            risk_factors=opp.risk_factors,
            recommendation_reason=opp.recommendation_reason,
            total_acquisition_cost=opp.total_acquisition_cost,
            predicted_retail_price=opp.predicted_retail_price,
            days_to_sell_prediction=opp.days_to_sell_prediction,
            auction_end=vehicle.auction_end.isoformat() if vehicle.auction_end else None,
            is_active=opp.is_active,
            created_at=opp.created_at.isoformat(),
            updated_at=opp.updated_at.isoformat()
        ))
    
    return OpportunityListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=opportunities
    )

@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get specific opportunity details"""
    
    result = db.query(Opportunity, Vehicle).join(
        Vehicle, Vehicle.id == Opportunity.vehicle_id
    ).filter(
        Opportunity.id == opportunity_id,
        Opportunity.is_active == True
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    
    opp, vehicle = result
    
    return OpportunityResponse(
        id=opp.id,
        vehicle_id=vehicle.id,
        vehicle_info={
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "mileage": vehicle.mileage,
            "state": vehicle.state,
            "title": vehicle.title,
            "description": vehicle.description,
            "current_bid": vehicle.current_bid,
            "buy_now_price": vehicle.buy_now_price,
            "reserve_met": vehicle.reserve_met,
            "location": vehicle.location,
            "zip_code": vehicle.zip_code,
            "source": vehicle.source,
            "source_url": vehicle.source_url,
            "image_urls": vehicle.image_urls,
            "title_status": vehicle.title_status,
            "auction_start": vehicle.auction_start.isoformat() if vehicle.auction_start else None,
            "auction_end": vehicle.auction_end.isoformat() if vehicle.auction_end else None
        },
        opportunity_score=opp.opportunity_score,
        potential_profit=opp.potential_profit,
        profit_margin=opp.profit_margin,
        roi_percentage=opp.roi_percentage,
        risk_score=opp.risk_score,
        risk_factors=opp.risk_factors,
        recommendation_reason=opp.recommendation_reason,
        total_acquisition_cost=opp.total_acquisition_cost,
        predicted_retail_price=opp.predicted_retail_price,
        days_to_sell_prediction=opp.days_to_sell_prediction,
        auction_end=vehicle.auction_end.isoformat() if vehicle.auction_end else None,
        is_active=opp.is_active,
        created_at=opp.created_at.isoformat(),
        updated_at=opp.updated_at.isoformat()
    )

@router.post("/{opportunity_id}/save")
async def save_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark opportunity as saved"""
    
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id
    ).first()
    
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    
    opportunity.user_action = "saved"
    opportunity.user_id = current_user.id
    db.commit()
    
    return {"message": "Opportunity saved"}

@router.post("/{opportunity_id}/ignore")
async def ignore_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark opportunity as ignored"""
    
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id
    ).first()
    
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    
    opportunity.user_action = "ignored"
    opportunity.user_id = current_user.id
    db.commit()
    
    return {"message": "Opportunity ignored"}

@router.get("/saved/list")
async def list_saved_opportunities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100)
):
    """List user's saved opportunities"""
    
    query = db.query(Opportunity, Vehicle).join(
        Vehicle, Vehicle.id == Opportunity.vehicle_id
    ).filter(
        Opportunity.user_id == current_user.id,
        Opportunity.user_action == "saved",
        Opportunity.is_active == True
    ).order_by(desc(Opportunity.updated_at))
    
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    opportunities = []
    for opp, vehicle in items:
        opportunities.append({
            "id": opp.id,
            "vehicle_info": {
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "current_bid": vehicle.current_bid,
                "auction_end": vehicle.auction_end.isoformat() if vehicle.auction_end else None
            },
            "opportunity_score": opp.opportunity_score,
            "potential_profit": opp.potential_profit,
            "saved_at": opp.updated_at.isoformat()
        })
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": opportunities
    }

@router.post("/rescore-all")
async def rescore_all_opportunities(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Trigger rescoring of all active opportunities"""
    
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Add background task to rescore opportunities
    background_tasks.add_task(rescore_opportunities_task, db)
    
    return {"message": "Opportunity rescoring initiated"}

async def rescore_opportunities_task(db: Session):
    """Background task to rescore opportunities"""
    try:
        from webapp.ml.opportunity_scorer import OpportunityScorer
        scorer = OpportunityScorer()
        
        # Get all active opportunities
        opportunities = db.query(Opportunity).join(Vehicle).filter(
            Opportunity.is_active == True,
            Vehicle.is_active == True
        ).all()
        
        for opp in opportunities:
            try:
                # Prepare data for scoring
                scoring_data = {
                    "vehicle": {
                        "make": opp.vehicle.make,
                        "model": opp.vehicle.model,
                        "year": opp.vehicle.year,
                        "mileage": opp.vehicle.mileage,
                        "state": opp.vehicle.state,
                        "title_status": opp.vehicle.title_status
                    },
                    "current_bid": opp.vehicle.current_bid or 0,
                    "fees": opp.fees_and_taxes or 0,
                    "transportation_cost": opp.transportation_cost or 0
                }
                
                # Get new score
                result = await scorer.score(scoring_data)
                
                # Update opportunity
                opp.opportunity_score = result["score"]
                opp.potential_profit = result["potential_profit"]
                opp.profit_margin = result["profit_margin"]
                opp.roi_percentage = result["roi_percentage"]
                
            except Exception as e:
                print(f"Failed to score opportunity {opp.id}: {e}")
                continue
        
        db.commit()
        print(f"Rescored {len(opportunities)} opportunities")
        
    except Exception as e:
        print(f"Rescoring task failed: {e}")
        db.rollback()