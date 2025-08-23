"""
Vehicle and opportunity models with ML integration
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSON, ARRAY
from webapp.database import Base

class Vehicle(Base):
    __tablename__ = "vehicles"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Source tracking
    source = Column(String(50), nullable=False, index=True)  # 'govdeals', 'publicsurplus', etc.
    source_id = Column(String(100), nullable=False)  # External ID from source
    source_url = Column(Text, nullable=False)
    
    # Vehicle details
    vin = Column(String(17), nullable=True, index=True)
    make = Column(String(50), nullable=True, index=True)
    model = Column(String(100), nullable=True, index=True)
    year = Column(Integer, nullable=True, index=True)
    mileage = Column(Integer, nullable=True)
    trim = Column(String(100), nullable=True)
    
    # Listing details
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    current_bid = Column(Float, nullable=True)
    buy_now_price = Column(Float, nullable=True)
    reserve_met = Column(Boolean, default=False)
    
    # Location
    location = Column(String(200), nullable=True)
    state = Column(String(2), nullable=True, index=True)
    zip_code = Column(String(10), nullable=True)
    
    # Auction timing
    auction_start = Column(DateTime(timezone=True), nullable=True)
    auction_end = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    title_status = Column(String(20), nullable=True)  # 'clean', 'salvage', 'rebuilt', etc.
    
    # Media
    image_urls = Column(ARRAY(Text), nullable=True)
    image_analysis = Column(JSON, nullable=True)  # ML analysis results
    
    # Metadata
    scrape_metadata = Column(JSON, nullable=True)
    last_checked = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    opportunities = relationship("Opportunity", back_populates="vehicle", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        Index('ix_vehicle_source_compound', 'source', 'source_id'),
        CheckConstraint('year >= 1900 AND year <= EXTRACT(YEAR FROM NOW()) + 1', name='check_valid_year'),
        CheckConstraint('mileage >= 0', name='check_valid_mileage'),
        CheckConstraint('current_bid >= 0', name='check_valid_bid'),
    )
    
    def __repr__(self):
        return f"<Vehicle(id={self.id}, {self.year} {self.make} {self.model}, source={self.source})>"

class Opportunity(Base):
    __tablename__ = "opportunities"
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # For personalization
    
    # ML Predictions
    predicted_retail_price = Column(Float, nullable=True)
    predicted_wholesale_price = Column(Float, nullable=True)
    price_confidence = Column(Float, nullable=True)  # 0-1 confidence score
    
    # Cost calculations
    total_acquisition_cost = Column(Float, nullable=False)
    transportation_cost = Column(Float, default=0.0)
    fees_and_taxes = Column(Float, default=0.0)
    reconditioning_cost = Column(Float, default=0.0)
    
    # Profit calculations
    potential_profit = Column(Float, nullable=True)
    profit_margin = Column(Float, nullable=True)  # Percentage
    roi_percentage = Column(Float, nullable=True)
    days_to_sell_prediction = Column(Integer, nullable=True)
    
    # Risk assessment
    risk_score = Column(Float, nullable=True)  # 0-1 where 1 is highest risk
    risk_factors = Column(ARRAY(String), nullable=True)
    
    # Scoring
    opportunity_score = Column(Float, nullable=True, index=True)  # Overall score 0-1
    rank = Column(Integer, nullable=True, index=True)  # Global ranking
    
    # ML explanations
    price_factors = Column(JSON, nullable=True)  # SHAP-like explanations
    recommendation_reason = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    user_action = Column(String(20), nullable=True)  # 'saved', 'ignored', 'purchased'
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    scored_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    vehicle = relationship("Vehicle", back_populates="opportunities")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('opportunity_score >= 0 AND opportunity_score <= 1', name='check_valid_score'),
        CheckConstraint('risk_score >= 0 AND risk_score <= 1', name='check_valid_risk'),
        CheckConstraint('price_confidence >= 0 AND price_confidence <= 1', name='check_valid_confidence'),
        Index('ix_opportunity_scoring', 'opportunity_score', 'is_active'),
    )
    
    def __repr__(self):
        return f"<Opportunity(id={self.id}, vehicle_id={self.vehicle_id}, score={self.opportunity_score})>"

class MLModel(Base):
    __tablename__ = "ml_models"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    version = Column(String(50), nullable=False)
    model_type = Column(String(50), nullable=False)  # 'price_predictor', 'risk_assessor', etc.
    
    # Model metadata
    features = Column(ARRAY(String), nullable=False)
    performance_metrics = Column(JSON, nullable=True)
    training_data_hash = Column(String(64), nullable=True)
    
    # Model storage
    model_path = Column(String(500), nullable=False)  # S3/file path
    model_size_bytes = Column(Integer, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=False, nullable=False)
    is_production = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    trained_at = Column(DateTime(timezone=True), nullable=True)
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<MLModel(name='{self.name}', version='{self.version}', active={self.is_active})>"