"""
Two-Factor Authentication (2FA) Router
TOTP-based 2FA enrollment and verification
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timezone
from typing import Dict
import logging
import pyotp
import qrcode
import io
import base64

from auth import get_current_user
import database as db
from services.safe_audit_logger import SafeAuditLogger

logger = logging.getLogger(__name__)
audit_logger = SafeAuditLogger()

router = APIRouter(prefix="/api/auth/2fa", tags=["Two-Factor Authentication"])


@router.post("/enroll")
async def enroll_2fa(user_id: str = Depends(get_current_user)):
    """Start 2FA enrollment process
    
    Returns:
        - secret: TOTP secret key (store securely!)
        - qr_code: Base64-encoded QR code image for scanning with authenticator app
        - manual_entry: Secret for manual entry in authenticator app
    """
    try:
        # Check if user exists
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if 2FA is already enabled
        if user.get('two_factor_enabled', False):
            return {
                "success": False,
                "message": "2FA is already enabled for this account",
                "enabled": True
            }
        
        # Generate new TOTP secret
        secret = pyotp.random_base32()
        
        # Get user email for QR code
        user_email = user.get('email', f'user_{user_id[:8]}@amarktai.com')
        
        # Generate provisioning URI
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user_email,
            issuer_name="Amarktai Network"
        )
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        # Store secret temporarily (not enabled yet)
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "two_factor_secret": secret,
                    "two_factor_enabled": False,  # Not enabled until verified
                    "two_factor_enrolled_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        logger.info(f"2FA enrollment started for user {user_id[:8]}")
        
        # Audit log
        await audit_logger.log_action(
            user_id=user_id,
            action="2fa_enrollment_started",
            target_type="user",
            target_id=user_id,
            details={"method": "TOTP"}
        )
        
        return {
            "success": True,
            "message": "Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.)",
            "qr_code": f"data:image/png;base64,{qr_code_base64}",
            "manual_entry": secret,
            "provisioning_uri": provisioning_uri,
            "next_step": "Verify with a code from your authenticator app using /api/auth/2fa/verify"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA enrollment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
async def verify_2fa_enrollment(
    data: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """Verify 2FA enrollment with code from authenticator app
    
    Body:
        {
            "code": "123456"  # 6-digit code from authenticator app
        }
    """
    try:
        code = data.get('code')
        if not code:
            raise HTTPException(status_code=400, detail="Code is required")
        
        # Get user
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if secret exists
        secret = user.get('two_factor_secret')
        if not secret:
            raise HTTPException(status_code=400, detail="2FA enrollment not started. Please enroll first.")
        
        # Verify code
        totp = pyotp.TOTP(secret)
        is_valid = totp.verify(code, valid_window=1)  # Allow 1 time step tolerance (30 seconds)
        
        if is_valid:
            # Enable 2FA
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "two_factor_enabled": True,
                        "two_factor_verified_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"2FA enabled for user {user_id[:8]}")
            
            # Audit log
            await audit_logger.log_action(
                user_id=user_id,
                action="2fa_enabled",
                target_type="user",
                target_id=user_id,
                details={"method": "TOTP", "verified": True}
            )
            
            return {
                "success": True,
                "message": "2FA has been successfully enabled for your account",
                "enabled": True
            }
        else:
            return {
                "success": False,
                "message": "Invalid code. Please try again with a new code from your authenticator app.",
                "enabled": False
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disable")
async def disable_2fa(
    data: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """Disable 2FA for account
    
    Body:
        {
            "code": "123456",  # Current valid 2FA code
            "password": "user_password"  # User's password for additional security
        }
    """
    try:
        code = data.get('code')
        password = data.get('password')
        
        if not code or not password:
            raise HTTPException(status_code=400, detail="Code and password are required")
        
        # Get user
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify password
        from auth import verify_password
        if not verify_password(password, user.get('password_hash', '')):
            raise HTTPException(status_code=401, detail="Invalid password")
        
        # Check if 2FA is enabled
        if not user.get('two_factor_enabled', False):
            return {
                "success": False,
                "message": "2FA is not enabled for this account"
            }
        
        # Verify current 2FA code
        secret = user.get('two_factor_secret')
        totp = pyotp.TOTP(secret)
        
        if not totp.verify(code, valid_window=1):
            return {
                "success": False,
                "message": "Invalid 2FA code"
            }
        
        # Disable 2FA
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "two_factor_enabled": False,
                    "two_factor_disabled_at": datetime.now(timezone.utc).isoformat()
                },
                "$unset": {
                    "two_factor_secret": ""
                }
            }
        )
        
        logger.info(f"2FA disabled for user {user_id[:8]}")
        
        # Audit log
        await audit_logger.log_action(
            user_id=user_id,
            action="2fa_disabled",
            target_type="user",
            target_id=user_id,
            details={"method": "TOTP", "disabled_with_password": True}
        )
        
        return {
            "success": True,
            "message": "2FA has been disabled for your account",
            "enabled": False
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA disable error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_2fa_status(user_id: str = Depends(get_current_user)):
    """Get 2FA status for current user"""
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "enabled": user.get('two_factor_enabled', False),
            "enrolled_at": user.get('two_factor_enrolled_at'),
            "verified_at": user.get('two_factor_verified_at'),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get 2FA status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_2fa_code(
    data: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """Validate a 2FA code (used for critical operations)
    
    Body:
        {
            "code": "123456"
        }
    """
    try:
        code = data.get('code')
        if not code:
            raise HTTPException(status_code=400, detail="Code is required")
        
        # Get user
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if 2FA is enabled
        if not user.get('two_factor_enabled', False):
            return {
                "valid": False,
                "message": "2FA is not enabled for this account"
            }
        
        # Verify code
        secret = user.get('two_factor_secret')
        totp = pyotp.TOTP(secret)
        is_valid = totp.verify(code, valid_window=1)
        
        return {
            "valid": is_valid,
            "message": "Code is valid" if is_valid else "Invalid code",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
