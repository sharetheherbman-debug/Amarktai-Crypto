"""
TOTP Service - Production 2FA
Uses pyotp for TOTP generation and verification
"""

import pyotp
import logging
from typing import Optional, Dict
from datetime import datetime, timezone

import database as db

logger = logging.getLogger(__name__)


class TOTPService:
    """Two-Factor Authentication Service using TOTP"""
    
    async def generate_secret(self, user_id: str) -> Dict:
        """
        Generate new TOTP secret for user
        
        Returns:
            secret: Base32 encoded secret
            qr_uri: URI for QR code generation
        """
        try:
            secret = pyotp.random_base32()
            
            # Get user email for QR code
            user = await db.users_collection.find_one({"id": user_id})
            user_email = user.get("email", f"user_{user_id[:8]}@amarktai.com") if user else f"user_{user_id[:8]}@amarktai.com"
            
            # Generate provisioning URI for QR code
            totp = pyotp.TOTP(secret)
            qr_uri = totp.provisioning_uri(
                name=user_email,
                issuer_name="Amarktai Network"
            )
            
            return {
                "success": True,
                "secret": secret,
                "qr_uri": qr_uri
            }
            
        except Exception as e:
            logger.error(f"TOTP secret generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def verify_code(self, user_id: str, code: str, valid_window: int = 1) -> bool:
        """
        Verify TOTP code for user
        
        Args:
            user_id: User ID
            code: 6-digit TOTP code
            valid_window: Number of intervals to check (default 1 = ±30 seconds)
            
        Returns:
            True if code is valid, False otherwise
        """
        try:
            user = await db.users_collection.find_one({"id": user_id})
            if not user:
                logger.warning(f"TOTP verify: user not found {user_id}")
                return False
            
            encrypted_secret = user.get("two_factor_secret")
            if not encrypted_secret:
                logger.warning(f"TOTP verify: no secret for user {user_id}")
                return False
            
            # Decrypt secret if encrypted
            try:
                import config
                from cryptography.fernet import Fernet
                
                fernet_key = getattr(config, 'AMARKTAI_FERNET_KEY', None) or getattr(config, 'FERNET_KEY', None)
                if fernet_key:
                    cipher = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
                    secret = cipher.decrypt(encrypted_secret.encode()).decode()
                else:
                    # Assume unencrypted (legacy or dev)
                    secret = encrypted_secret
            except Exception as dec_err:
                logger.error(f"Failed to decrypt TOTP secret: {dec_err}")
                # Try using as-is (might be unencrypted)
                secret = encrypted_secret
            
            totp = pyotp.TOTP(secret)
            is_valid = totp.verify(code, valid_window=valid_window)
            
            if is_valid:
                # Update last verification timestamp
                await db.users_collection.update_one(
                    {"id": user_id},
                    {"$set": {"last_2fa_verify": datetime.now(timezone.utc).isoformat()}}
                )
            
            return is_valid
            
        except Exception as e:
            logger.error(f"TOTP verification failed: {e}")
            return False
    
    async def enable_2fa(self, user_id: str, secret: str, verification_code: str) -> Dict:
        """
        Enable 2FA for user after verifying initial code
        
        Args:
            user_id: User ID
            secret: TOTP secret to store (will be encrypted)
            verification_code: Code to verify before enabling
            
        Returns:
            Dict with success status
        """
        try:
            # Verify the code with the secret
            totp = pyotp.TOTP(secret)
            if not totp.verify(verification_code, valid_window=1):
                return {
                    "success": False,
                    "error": "INVALID_CODE",
                    "message": "Invalid verification code"
                }
            
            # Encrypt secret before storing (production security)
            try:
                import config
                from cryptography.fernet import Fernet
                
                # Get encryption key
                fernet_key = getattr(config, 'AMARKTAI_FERNET_KEY', None) or getattr(config, 'FERNET_KEY', None)
                if fernet_key:
                    cipher = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
                    encrypted_secret = cipher.encrypt(secret.encode()).decode()
                else:
                    # Fallback: store unencrypted with warning
                    logger.warning("No FERNET_KEY configured - storing TOTP secret unencrypted (NOT RECOMMENDED FOR PRODUCTION)")
                    encrypted_secret = secret
            except Exception as enc_err:
                logger.error(f"Failed to encrypt TOTP secret: {enc_err}")
                encrypted_secret = secret
            
            # Store encrypted secret
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "two_factor_enabled": True,
                        "two_factor_secret": encrypted_secret,
                        "two_factor_enabled_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"2FA enabled for user {user_id}")
            
            return {
                "success": True,
                "message": "2FA enabled successfully"
            }
            
        except Exception as e:
            logger.error(f"Enable 2FA failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def disable_2fa(self, user_id: str, verification_code: str) -> Dict:
        """
        Disable 2FA for user after verifying code
        
        Args:
            user_id: User ID
            verification_code: Current TOTP code to verify identity
            
        Returns:
            Dict with success status
        """
        try:
            # Verify code before disabling
            is_valid = await self.verify_code(user_id, verification_code)
            if not is_valid:
                return {
                    "success": False,
                    "error": "INVALID_CODE",
                    "message": "Invalid verification code"
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
            
            logger.info(f"2FA disabled for user {user_id}")
            
            return {
                "success": True,
                "message": "2FA disabled successfully"
            }
            
        except Exception as e:
            logger.error(f"Disable 2FA failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def is_2fa_enabled(self, user_id: str) -> bool:
        """Check if 2FA is enabled for user"""
        try:
            user = await db.users_collection.find_one({"id": user_id})
            return user.get("two_factor_enabled", False) if user else False
        except Exception as e:
            logger.error(f"Check 2FA status failed: {e}")
            return False
    
    async def require_2fa_verification(self, user_id: str, code: Optional[str], operation: str) -> Dict:
        """
        Check if 2FA is required and verify if provided
        
        Args:
            user_id: User ID
            code: Optional TOTP code
            operation: Operation being performed (for logging)
            
        Returns:
            Dict with verification status
        """
        try:
            is_enabled = await self.is_2fa_enabled(user_id)
            
            if not is_enabled:
                # 2FA not enabled, allow operation
                return {
                    "success": True,
                    "required": False,
                    "verified": False
                }
            
            if not code:
                # 2FA enabled but no code provided
                return {
                    "success": False,
                    "required": True,
                    "verified": False,
                    "error": "2FA_REQUIRED",
                    "message": f"2FA verification required for {operation}"
                }
            
            # Verify code
            is_valid = await self.verify_code(user_id, code)
            
            if not is_valid:
                return {
                    "success": False,
                    "required": True,
                    "verified": False,
                    "error": "INVALID_2FA",
                    "message": "Invalid 2FA code"
                }
            
            return {
                "success": True,
                "required": True,
                "verified": True
            }
            
        except Exception as e:
            logger.error(f"2FA verification check failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Global instance
totp_service = TOTPService()
