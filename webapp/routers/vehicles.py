"""
Vehicles API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from pydantic import BaseModel

from webapp.database import get_db
from webapp.models.user import User
from webapp.models.vehicle import Vehicle
from webapp.auth import get_optional_user

router = APIRouter()

class VehicleResponse(BaseModel):
    id: int
    source: str
    source_id: str
    source_url: str
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    trim: Optional[str] = None
    vin: Optional[str] = None
    title: str
    description: Optional[str] = None
    current_bid: Optional[float] = None
    buy_now_price: Optional[float] = None
    reserve_met: bool
    location: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    title_status: Optional[str] = None
    auction_start: Optional[str] = None
    auction_end: Optional[str] = None
    is_active: bool
    image_urls: Optional[List[str]] = None
    created_at: str
    updated_at: str

class VehicleListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[VehicleResponse]

@router.get("", response_model=VehicleListResponse)
async def list_vehicles(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    # Filters
    make: Optional[str] = Query(None, max_length=50),
    model: Optional[str] = Query(None, max_length=100),
    year_min: Optional[int] = Query(None, ge=1900),
    year_max: Optional[int] = Query(None, le=2030),
    mileage_max: Optional[int] = Query(None, gt=0),
    price_min: Optional[float] = Query(None, gt=0),
    price_max: Optional[float] = Query(None, gt=0),
    state: Optional[str] = Query(None, max_length=2),
    title_status: Optional[str] = Query(None, max_length=20),
    source: Optional[str] = Query(None, max_length=50),
    has_reserve: Optional[bool] = Query(None),
    ending_soon: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    # Sorting and pagination
    sort_by: str = Query("auction_end", regex="^(auction_end|current_bid|year|mileage|created_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100)
):
    """List vehicles with filtering and sorting"""
    
    # Build base query
    query = db.query(Vehicle).filter(Vehicle.is_active == True)
    
    # Apply filters
    if make:
        query = query.filter(Vehicle.make.ilike(f"%{make}%"))
    
    if model:
        query = query.filter(Vehicle.model.ilike(f"%{model}%"))
    
    if year_min:
        query = query.filter(Vehicle.year >= year_min)
    
    if year_max:
        query = query.filter(Vehicle.year <= year_max)
    
    if mileage_max:
        query = query.filter(Vehicle.mileage <= mileage_max)
    
    if price_min:
        query = query.filter(Vehicle.current_bid >= price_min)
    
    if price_max:
        query = query.filter(Vehicle.current_bid <= price_max)
    
    if state:
        query = query.filter(Vehicle.state.ilike(f"%{state}%"))
    
    if title_status:
        query = query.filter(Vehicle.title_status.ilike(f"%{title_status}%"))
    
    if source:
        query = query.filter(Vehicle.source.ilike(f"%{source}%"))
    
    if has_reserve is not None:
        if has_reserve:
            query = query.filter(Vehicle.reserve_met == False)
        else:
            query = query.filter(or_(Vehicle.reserve_met == True, Vehicle.reserve_met.is_(None)))
    
    if ending_soon:
        from datetime import datetime, timedelta
        soon_threshold = datetime.now() + timedelta(hours=24)
        query = query.filter(
            and_(
                Vehicle.auction_end.isnot(None),
                Vehicle.auction_end <= soon_threshold
            )
        )
    
    if search:
        # Search across multiple fields
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Vehicle.title.ilike(search_term),
                Vehicle.description.ilike(search_term),
                Vehicle.make.ilike(search_term),
                Vehicle.model.ilike(search_term),
                Vehicle.vin.ilike(search_term)
            )
        )
    
    # Apply sorting
    sort_column = getattr(Vehicle, sort_by)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    vehicles = query.offset((page - 1) * page_size).limit(page_size).all()
    
    # Format response
    items = []
    for vehicle in vehicles:
        items.append(VehicleResponse(
            id=vehicle.id,
            source=vehicle.source,
            source_id=vehicle.source_id,
            source_url=vehicle.source_url,
            make=vehicle.make,
            model=vehicle.model,
            year=vehicle.year,
            mileage=vehicle.mileage,
            trim=vehicle.trim,
            vin=vehicle.vin,
            title=vehicle.title,
            description=vehicle.description,
            current_bid=vehicle.current_bid,
            buy_now_price=vehicle.buy_now_price,
            reserve_met=vehicle.reserve_met,
            location=vehicle.location,
            state=vehicle.state,
            zip_code=vehicle.zip_code,
            title_status=vehicle.title_status,
            auction_start=vehicle.auction_start.isoformat() if vehicle.auction_start else None,
            auction_end=vehicle.auction_end.isoformat() if vehicle.auction_end else None,
            is_active=vehicle.is_active,
            image_urls=vehicle.image_urls,
            created_at=vehicle.created_at.isoformat(),
            updated_at=vehicle.updated_at.isoformat()
        ))
    
    return VehicleListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )

@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get specific vehicle details"""
    
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.is_active == True
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    return VehicleResponse(
        id=vehicle.id,
        source=vehicle.source,
        source_id=vehicle.source_id,
        source_url=vehicle.source_url,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        mileage=vehicle.mileage,
        trim=vehicle.trim,
        vin=vehicle.vin,
        title=vehicle.title,
        description=vehicle.description,
        current_bid=vehicle.current_bid,
        buy_now_price=vehicle.buy_now_price,
        reserve_met=vehicle.reserve_met,
        location=vehicle.location,
        state=vehicle.state,
        zip_code=vehicle.zip_code,
        title_status=vehicle.title_status,
        auction_start=vehicle.auction_start.isoformat() if vehicle.auction_start else None,
        auction_end=vehicle.auction_end.isoformat() if vehicle.auction_end else None,
        is_active=vehicle.is_active,
        image_urls=vehicle.image_urls,
        created_at=vehicle.created_at.isoformat(),
        updated_at=vehicle.updated_at.isoformat()
    )

@router.get("/stats/summary")
async def get_vehicle_stats(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get vehicle statistics summary"""
    
    from sqlalchemy import func
    
    stats = db.query(
        func.count(Vehicle.id).label('total_vehicles'),
        func.count(Vehicle.id).filter(Vehicle.auction_end > func.now()).label('active_auctions'),
        func.avg(Vehicle.current_bid).filter(Vehicle.current_bid.isnot(None)).label('avg_price'),
        func.min(Vehicle.current_bid).filter(Vehicle.current_bid.isnot(None)).label('min_price'),
        func.max(Vehicle.current_bid).filter(Vehicle.current_bid.isnot(None)).label('max_price'),
        func.count(Vehicle.id.distinct()).filter(Vehicle.make.isnot(None)).label('unique_makes')
    ).filter(Vehicle.is_active == True).first()
    
    # Get top makes
    top_makes = db.query(
        Vehicle.make,
        func.count(Vehicle.id).label('count')
    ).filter(
        Vehicle.is_active == True,
        Vehicle.make.isnot(None)
    ).group_by(Vehicle.make).order_by(desc(func.count(Vehicle.id))).limit(10).all()
    
    # Get vehicles by state
    by_state = db.query(
        Vehicle.state,
        func.count(Vehicle.id).label('count')
    ).filter(
        Vehicle.is_active == True,
        Vehicle.state.isnot(None)
    ).group_by(Vehicle.state).order_by(desc(func.count(Vehicle.id))).limit(10).all()
    
    return {
        "summary": {
            "total_vehicles": stats.total_vehicles or 0,
            "active_auctions": stats.active_auctions or 0,
            "avg_price": float(stats.avg_price) if stats.avg_price else 0,
            "min_price": float(stats.min_price) if stats.min_price else 0,
            "max_price": float(stats.max_price) if stats.max_price else 0,
            "unique_makes": stats.unique_makes or 0
        },
        "top_makes": [{"make": make, "count": count} for make, count in top_makes],
        "by_state": [{"state": state, "count": count} for state, count in by_state]
    }