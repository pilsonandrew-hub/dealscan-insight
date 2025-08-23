"""
Audit log model for security and compliance
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSON, INET
from webapp.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # User context
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    username = Column(String(50), nullable=True)  # Cached for efficiency
    
    # Request context
    request_id = Column(String(36), nullable=True, index=True)
    ip_address = Column(INET, nullable=True, index=True)
    user_agent = Column(Text, nullable=True)
    
    # Action details
    action = Column(String(100), nullable=False, index=True)
    resource = Column(String(100), nullable=True, index=True)
    resource_id = Column(String(100), nullable=True)
    
    # Results
    status = Column(String(20), nullable=False, index=True)  # 'success', 'failure', 'blocked'
    status_code = Column(Integer, nullable=True)
    
    # Additional data
    details = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('ix_audit_user_action', 'user_id', 'action'),
        Index('ix_audit_time_status', 'created_at', 'status'),
        Index('ix_audit_ip_time', 'ip_address', 'created_at'),
    )
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', status='{self.status}')>"

class SecurityEvent(Base):
    __tablename__ = "security_events"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Event classification
    event_type = Column(String(50), nullable=False, index=True)  # 'rate_limit', 'ssrf', 'auth_failure'
    severity = Column(String(20), nullable=False, index=True)    # 'low', 'medium', 'high', 'critical'
    
    # Context
    ip_address = Column(INET, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    request_id = Column(String(36), nullable=True)
    
    # Event details
    description = Column(Text, nullable=False)
    raw_data = Column(JSON, nullable=True)
    
    # Response
    action_taken = Column(String(100), nullable=True)  # 'blocked', 'throttled', 'alerted'
    resolved = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('ix_security_type_severity', 'event_type', 'severity'),
        Index('ix_security_unresolved', 'resolved', 'created_at'),
    )
    
    def __repr__(self):
        return f"<SecurityEvent(id={self.id}, type='{self.event_type}', severity='{self.severity}')>"