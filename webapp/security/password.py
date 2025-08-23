"""
Password hashing and verification
"""
from passlib.context import CryptContext
from passlib.hash import bcrypt

# Create password context with bcrypt
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # Increased rounds for better security
)

def hash_password(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def needs_update(hashed_password: str) -> bool:
    """Check if password hash needs updating"""
    return pwd_context.needs_update(hashed_password)