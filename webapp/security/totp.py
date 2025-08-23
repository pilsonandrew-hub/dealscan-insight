"""
TOTP (Time-based One-Time Password) implementation for 2FA
"""
import pyotp
import qrcode
import io
import base64
from typing import Tuple, List
import secrets

def generate_totp_secret() -> str:
    """Generate a new TOTP secret"""
    return pyotp.random_base32()

def generate_qr_code(username: str, secret: str, issuer: str = "DealerScope") -> str:
    """Generate QR code for TOTP setup"""
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=username,
        issuer_name=issuer
    )
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    # Convert to base64 image
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def verify_totp_code(secret: str, code: str, valid_window: int = 1) -> bool:
    """Verify TOTP code"""
    if not code or len(code) != 6:
        return False
    
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=valid_window)
    except Exception:
        return False

def generate_backup_codes(count: int = 10) -> List[str]:
    """Generate backup codes for account recovery"""
    codes = []
    for _ in range(count):
        # Generate 8-character backup code
        code = secrets.token_hex(4).upper()
        # Format as XXXX-XXXX
        formatted_code = f"{code[:4]}-{code[4:]}"
        codes.append(formatted_code)
    return codes

def verify_backup_code(stored_codes: List[str], provided_code: str) -> Tuple[bool, List[str]]:
    """
    Verify backup code and return updated codes list
    Returns (is_valid, remaining_codes)
    """
    if not provided_code:
        return False, stored_codes
    
    # Normalize format
    normalized_code = provided_code.upper().replace("-", "")
    if len(normalized_code) != 8:
        return False, stored_codes
    
    formatted_code = f"{normalized_code[:4]}-{normalized_code[4:]}"
    
    if formatted_code in stored_codes:
        # Remove used code
        remaining_codes = [code for code in stored_codes if code != formatted_code]
        return True, remaining_codes
    
    return False, stored_codes

def get_current_totp_code(secret: str) -> str:
    """Get current TOTP code (for testing)"""
    totp = pyotp.TOTP(secret)
    return totp.now()