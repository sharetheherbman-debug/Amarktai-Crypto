"""
API Key Encryption/Decryption Module
Provides stable encryption functions for API key management.

This module MUST NOT depend on FastAPI or any router logic.
It only exports encryption/decryption utilities.
"""

import os
import base64
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cache for the encryption key to avoid repeated computation
_cached_fernet_key: Optional[bytes] = None


def get_encryption_key() -> bytes:
    """Get or create encryption key for API keys
    
    Priority:
    1. AMARKTAI_FERNET_KEY environment variable
    2. FERNET_KEY environment variable  
    3. Fallback: derived from JWT_SECRET (dev only)
    
    Returns:
        bytes: Fernet encryption key (32 bytes, url-safe base64 encoded)
    """
    global _cached_fernet_key
    
    if _cached_fernet_key is not None:
        return _cached_fernet_key
    
    # Try AMARKTAI_FERNET_KEY first
    key_env = os.getenv("AMARKTAI_FERNET_KEY")
    if not key_env:
        # Fallback to FERNET_KEY
        key_env = os.getenv("FERNET_KEY")
    
    if key_env:
        try:
            _cached_fernet_key = base64.urlsafe_b64decode(key_env.encode())
            return _cached_fernet_key
        except Exception as e:
            logger.warning(f"Invalid FERNET_KEY format: {e}, falling back to derived key")
    
    # Generate a deterministic key from JWT secret (NOT recommended for production)
    jwt_secret = os.getenv("JWT_SECRET", "default-dev-secret-change-in-production")
    key_material = hashlib.sha256(jwt_secret.encode()).digest()
    _cached_fernet_key = base64.urlsafe_b64encode(key_material)
    
    logger.warning("Using derived Fernet key from JWT_SECRET. Set AMARKTAI_FERNET_KEY or FERNET_KEY for production!")
    return _cached_fernet_key


def encrypt_api_key(value: str) -> str:
    """Encrypt an API key for storage
    
    Args:
        value: Plain text value to encrypt
        
    Returns:
        str: Encrypted value (base64 encoded token)
        
    Raises:
        Exception: If encryption fails
    """
    try:
        from cryptography.fernet import Fernet
        
        fernet = Fernet(get_encryption_key())
        encrypted = fernet.encrypt(value.encode())
        # Return base64-encoded token
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        raise Exception(f"Failed to encrypt API key: {e}")


def decrypt_api_key(token: str) -> str:
    """Decrypt an API key from storage
    
    Args:
        token: Encrypted token (base64 encoded)
        
    Returns:
        str: Decrypted plaintext value
        
    Note:
        If decryption fails (e.g., invalid token, corrupted data, or plaintext),
        returns the original token for backwards compatibility with old plaintext rows.
    """
    try:
        from cryptography.fernet import Fernet
        
        fernet = Fernet(get_encryption_key())
        decoded = base64.urlsafe_b64decode(token.encode())
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode()
    except Exception as e:
        # Backwards compatibility: if decryption fails, assume it's plaintext
        logger.debug(f"Decryption failed (likely plaintext): {e}")
        return token
