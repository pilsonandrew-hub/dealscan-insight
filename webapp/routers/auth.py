"""
Authentication router with JWT and TOTP support
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from webapp.database import get_db
from webapp.models.user import User
from webapp.models.audit_log import AuditLog
from webapp.security.password import hash_password, verify_password
from webapp.security.jwt import create_access_token, create_refresh_token, verify_token, token_blacklist
from webapp.security.totp import generate_totp_secret, generate_qr_code, verify_totp_code, generate_backup_codes
from webapp.auth import get_current_user, log_security_event

router = APIRouter()
security = HTTPBearer()

# Pydantic models
class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class EnableTOTPResponse(BaseModel):
    secret: str
    qr_code: str
    backup_codes: list[str]

class VerifyTOTPRequest(BaseModel):
    totp_code: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Authenticate user and return tokens"""
    
    # Find user
    user = db.query(User).filter(
        (User.username == login_data.username) | (User.email == login_data.username)
    ).first()
    
    if not user or not user.is_active:
        await log_security_event(
            db, "auth_failure", "medium",
            f"Login attempt for non-existent or inactive user: {login_data.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Check account lockout
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        await log_security_event(
            db, "auth_failure", "high",
            f"Login attempt for locked account: {user.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked"
        )
    
    # Verify password
    if not verify_password(login_data.password, user.hashed_password):
        # Increment failed attempts
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        db.commit()
        
        await log_security_event(
            db, "auth_failure", "medium",
            f"Invalid password for user: {user.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Check TOTP if enabled
    if user.totp_enabled:
        if not login_data.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP code required"
            )
        
        if not verify_totp_code(user.totp_secret, login_data.totp_code):
            await log_security_event(
                db, "auth_failure", "high",
                f"Invalid TOTP code for user: {user.username}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code"
            )
    
    # Successful login - reset failed attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    
    # Create tokens
    token_data = {"sub": str(user.id), "username": user.username}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    # Log successful login
    audit_log = AuditLog(
        user_id=user.id,
        username=user.username,
        action="login",
        status="success",
        status_code=200
    )
    db.add(audit_log)
    db.commit()
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user.to_dict()
    )

@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    refresh_data: RefreshRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token"""
    
    # Verify refresh token
    payload = verify_token(refresh_data.refresh_token, "refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Check if token is blacklisted
    if token_blacklist.is_blacklisted(refresh_data.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked"
        )
    
    # Get user
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    token_data = {"sub": str(user.id), "username": user.username}
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)
    
    # Blacklist old refresh token
    token_blacklist.add_token(refresh_data.refresh_token)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=user.to_dict()
    )

@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Logout user and blacklist token"""
    
    # Blacklist the current token
    token_blacklist.add_token(credentials.credentials)
    
    # Log logout
    audit_log = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="logout",
        status="success",
        status_code=200
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Successfully logged out"}

@router.post("/enable-totp", response_model=EnableTOTPResponse)
async def enable_totp(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enable TOTP for user account"""
    
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP is already enabled"
        )
    
    # Generate secret and backup codes
    secret = generate_totp_secret()
    backup_codes = generate_backup_codes()
    qr_code = generate_qr_code(current_user.username, secret)
    
    # Store in database (not yet enabled)
    current_user.totp_secret = secret
    current_user.backup_codes = ",".join(backup_codes)
    db.commit()
    
    return EnableTOTPResponse(
        secret=secret,
        qr_code=qr_code,
        backup_codes=backup_codes
    )

@router.post("/verify-totp")
async def verify_totp_setup(
    verify_data: VerifyTOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify TOTP setup and enable it"""
    
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP setup not initiated"
        )
    
    if not verify_totp_code(current_user.totp_secret, verify_data.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code"
        )
    
    # Enable TOTP
    current_user.totp_enabled = True
    db.commit()
    
    return {"message": "TOTP successfully enabled"}

@router.post("/disable-totp")
async def disable_totp(
    verify_data: VerifyTOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disable TOTP for user account"""
    
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP is not enabled"
        )
    
    if not verify_totp_code(current_user.totp_secret, verify_data.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code"
        )
    
    # Disable TOTP
    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.backup_codes = None
    db.commit()
    
    return {"message": "TOTP successfully disabled"}

@router.post("/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid current password"
        )
    
    # Validate new password strength
    if len(password_data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    # Update password
    current_user.hashed_password = hash_password(password_data.new_password)
    db.commit()
    
    # Log password change
    audit_log = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="password_change",
        status="success",
        status_code=200
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Password successfully changed"}

@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user.to_dict()