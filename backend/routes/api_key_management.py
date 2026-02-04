"""
API Key Encryption/Decryption Module
Provides stable encryption functions for API key management.

This module exports encryption/decryption utilities and helper functions
for retrieving decrypted keys from database.
"""

import os
import base64
import hashlib
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Cache for the encryption key to avoid repeated computation
_cached_fernet_key: Optional[bytes] = None


def get_encryption_key() -> bytes:
    """Get or create encryption key for API keys
    
    Priority:
    1. AMARKTAI_FERNET_KEY environment variable (base64-encoded Fernet key)
    2. FERNET_KEY environment variable (base64-encoded Fernet key)
    3. FAIL in production / Generate for dev with warning
    
    Returns:
        bytes: Fernet encryption key (base64-encoded 32-byte key)
    
    Raises:
        RuntimeError: If no key is configured in production mode
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
            # Fernet key should be provided as base64-encoded string
            # Validate it's proper base64 and 32 bytes when decoded
            key_bytes = key_env.encode()
            decoded = base64.urlsafe_b64decode(key_bytes)
            if len(decoded) != 32:
                raise ValueError(f"Fernet key must be exactly 32 bytes when decoded, got {len(decoded)} bytes")
            # Return the base64-encoded bytes for Fernet constructor
            _cached_fernet_key = key_bytes
            logger.info("✅ Using AMARKTAI_FERNET_KEY for API key encryption")
            return _cached_fernet_key
        except Exception as e:
            logger.error(f"❌ Invalid FERNET_KEY format: {e}")
            raise RuntimeError(f"Invalid FERNET_KEY configuration: {e}")
    
    # Check if we're in production mode
    is_production = os.getenv("ENVIRONMENT", "development").lower() in ["production", "prod"]
    enable_dangerous_admin = os.getenv("ENABLE_DANGEROUS_ADMIN", "false").lower() == "true"
    
    if is_production and not enable_dangerous_admin:
        # In production, refuse to start without a proper key
        logger.critical("❌ CRITICAL: AMARKTAI_FERNET_KEY or FERNET_KEY must be set in production!")
        logger.critical("Generate a key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
        raise RuntimeError("Missing AMARKTAI_FERNET_KEY in production mode. Server cannot start.")
    
    # Development fallback: Generate a deterministic key from JWT secret
    jwt_secret = os.getenv("JWT_SECRET", "default-dev-secret-change-in-production")
    key_material = hashlib.sha256(jwt_secret.encode()).digest()
    _cached_fernet_key = base64.urlsafe_b64encode(key_material)
    
    logger.warning("⚠️ WARNING: Using derived Fernet key from JWT_SECRET (DEV ONLY!)")
    logger.warning("⚠️ Set AMARKTAI_FERNET_KEY for production: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
    return _cached_fernet_key


def encrypt_api_key(value: str) -> str:
    """Encrypt an API key for storage
    
    Args:
        value: Plain text value to encrypt
        
    Returns:
        str: Encrypted value (Fernet token as base64 string)
        
    Raises:
        Exception: If encryption fails
    """
    try:
        from cryptography.fernet import Fernet
        
        fernet = Fernet(get_encryption_key())
        encrypted = fernet.encrypt(value.encode())
        # Fernet.encrypt() already returns base64-encoded bytes, just decode to string
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        raise Exception(f"Failed to encrypt API key: {e}")


def decrypt_api_key(token: str) -> str:
    """Decrypt an API key from storage
    
    Args:
        token: Encrypted token (Fernet base64 string)
        
    Returns:
        str: Decrypted plaintext value
        
    Note:
        If decryption fails (e.g., invalid token, corrupted data, or plaintext),
        returns the original token for backwards compatibility with old plaintext rows.
    """
    try:
        from cryptography.fernet import Fernet
        
        fernet = Fernet(get_encryption_key())
        # Fernet expects base64 bytes, encode the string
        decrypted = fernet.decrypt(token.encode())
        return decrypted.decode()
    except Exception as e:
        # Backwards compatibility: if decryption fails, assume it's plaintext
        logger.debug(f"Decryption failed (likely plaintext): {e}")
        return token


async def get_decrypted_key(user_id: str, provider: str) -> Optional[Dict]:
    """Helper function to get and decrypt API keys
    
    Used internally by other services (e.g., ai_chat)
    Supports backward compatibility with ObjectId user_ids
    Supports multiple field name variants for encrypted keys
    
    Args:
        user_id: User ID (string)
        provider: Provider name
        
    Returns:
        Dict with decrypted api_key and api_secret, or None
    """
    try:
        import database as db
        
        # First try with string user_id (new format)
        key_doc = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": provider
        })
        
        # If not found and user_id looks like ObjectId (24 hex chars), try ObjectId lookup
        if not key_doc and len(user_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in user_id):
            from bson import ObjectId
            from bson.errors import InvalidId
            try:
                key_doc = await db.api_keys_collection.find_one({
                    "user_id": ObjectId(user_id),
                    "provider": provider
                })
            except InvalidId:
                pass  # Invalid ObjectId format, continue
        
        if not key_doc:
            # INFO level for normal case where key doesn't exist
            logger.info(f"No API key found for user {user_id[:8]} provider {provider}")
            return None
        
        # Support multiple field name variants for encrypted keys
        # Try canonical names first, then fallback to alternative names
        api_key_field = None
        api_secret_field = None
        
        # Check for API key field variants (in priority order)
        for field in ["api_key_encrypted", "apiKeyEncrypted", "api_key_ciphertext", "key_encrypted"]:
            if field in key_doc:
                api_key_field = field
                break
        
        # Check for API secret field variants (in priority order)
        for field in ["api_secret_encrypted", "apiSecretEncrypted", "api_secret_ciphertext", "secret_encrypted"]:
            if field in key_doc:
                api_secret_field = field
                break
        
        if not api_key_field:
            # WARN level for unexpected condition
            logger.warning(f"No encrypted API key field found for user {user_id[:8]} provider {provider}. Fields present: {list(key_doc.keys())}")
            return None
        
        return {
            "api_key": decrypt_api_key(key_doc[api_key_field]),
            "api_secret": decrypt_api_key(key_doc[api_secret_field]) if api_secret_field and key_doc.get(api_secret_field) else None,
            "provider": provider,
            "exchange": key_doc.get("exchange")
        }
    except Exception as e:
        logger.error(f"Get decrypted key error: {e}")
        return None
