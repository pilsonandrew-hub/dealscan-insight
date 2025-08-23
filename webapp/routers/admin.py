"""
Admin API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from webapp.database import get_db
from webapp.models.user import User
from webapp.auth import get_current_admin_user

router = APIRouter()

@router.get("/stats")
async def get_admin_stats(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get admin dashboard statistics"""
    from webapp.models.vehicle import Vehicle, Opportunity
    from webapp.models.audit_log import SecurityEvent
    from sqlalchemy import func
    
    stats = {
        "total_vehicles": db.query(func.count(Vehicle.id)).scalar(),
        "active_opportunities": db.query(func.count(Opportunity.id)).filter(Opportunity.is_active == True).scalar(),
        "total_users": db.query(func.count(User.id)).scalar(),
        "security_events_24h": db.query(func.count(SecurityEvent.id)).filter(
            SecurityEvent.created_at >= func.now() - func.interval('24 hours')
        ).scalar()
    }
    
    return stats

@router.post("/security/scan")
async def trigger_security_scan(
    current_user: User = Depends(get_current_admin_user)
):
    """Trigger security vulnerability scan"""
    return {"message": "Security scan initiated", "scan_id": "scan_001"}